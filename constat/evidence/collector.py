"""Collect inspectable evidence from a repository.

Two guarantees shape everything here:

1. **Nothing is invented.** Every field is read from Git, never inferred.
2. **Constat never becomes the only copy.** Excerpts are bounded (D-005), but
   each one carries a source pointer and the exact command that regenerates it
   in full, so a reviewer can always go back to the original.

The second guarantee is what makes bounding safe. Truncation that lost evidence
would violate "evidence is inspectable"; truncation that leaves a verifiable
route back to the source does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..errors import GitCommandFailed
from ..git.adapter import Repository, Revision, run_git
from ..git.diff import ChangeSummary, ChangeType

# ASCII unit and record separators. Used instead of newlines because commit
# messages contain newlines, and instead of a made-up delimiter because these
# are the characters the job is actually for.
UNIT = "\x1f"
RECORD = "\x1e"

_LOG_FORMAT = UNIT.join(
    [
        "%H",  # commit sha
        "%an",  # author name
        "%ae",  # author email
        "%aI",  # author date, strict ISO 8601
        "%cn",  # committer name
        "%ce",  # committer email
        "%cI",  # committer date, strict ISO 8601
        "%P",  # parent shas, space separated
        "%s",  # subject
        "%b",  # body
    ]
) + RECORD


@dataclass(frozen=True)
class ExcerptLimits:
    """Bounds on how much diff text is captured.

    Defaults were measured rather than invented, against the two subject
    repositories on 2026-11-08:

    * `237feed` `v2611f845`→`v26113ec4`: 29 files, 2255 diff lines, largest
      file 345 lines. Fits entirely within these limits.
    * `237feed-app` `v2.3.0`→`v2.3.1`: 50 files, 7442 diff lines — of which
      `package-lock.json` alone is 2255. A generated lockfile consuming 30% of
      the budget while saying nothing about business rules (D-010) is exactly
      the "diffs become too large or noisy" risk, and is the reason the
      per-file cap exists separately from the total.
    """

    max_lines_per_file: int = 400
    max_lines_total: int = 4000


DEFAULT_LIMITS = ExcerptLimits()


@dataclass(frozen=True)
class SourcePointer:
    """Where a piece of evidence came from, precisely enough to re-read it.

    ``reproduce`` is the point of this class: a reviewer does not have to trust
    the excerpt, because the command that regenerates it in full is recorded
    alongside it.
    """

    repository_root: Path
    revision: str
    path: str
    reproduce: str

    def __str__(self) -> str:
        return f"{self.revision[:12]}:{self.path}"


@dataclass(frozen=True)
class Commit:
    """One commit, as Git reports it.

    Author and committer are both kept and never collapsed. A rebase or
    cherry-pick rewrites the committer while preserving the author, so merging
    them would misattribute work.
    """

    sha: str
    author_name: str
    author_email: str
    authored_at: datetime
    committer_name: str
    committer_email: str
    committed_at: datetime
    subject: str
    body: str
    parent_shas: tuple[str, ...]

    @property
    def is_merge(self) -> bool:
        return len(self.parent_shas) > 1

    @property
    def short_sha(self) -> str:
        return self.sha[:12]


@dataclass(frozen=True)
class DiffExcerpt:
    """A bounded excerpt of one file's diff.

    ``truncated`` and ``omitted_lines`` are not decoration. An excerpt that
    silently dropped content would be evidence that misrepresents itself, so
    every omission is stated and countable.
    """

    path: str
    previous_path: str | None
    change_type: ChangeType
    pointer: SourcePointer
    text: str
    total_lines: int
    truncated: bool = False
    omitted_lines: int = 0
    is_binary: bool = False
    omitted_reason: str | None = None

    @property
    def has_text(self) -> bool:
        return bool(self.text)


@dataclass(frozen=True)
class EvidenceBundle:
    """Everything collected for one comparison."""

    commits: tuple[Commit, ...]
    excerpts: tuple[DiffExcerpt, ...]
    limits: ExcerptLimits = DEFAULT_LIMITS
    lines_captured: int = 0
    lines_omitted: int = 0
    files_without_excerpt: tuple[str, ...] = field(default_factory=tuple)

    @property
    def commit_count(self) -> int:
        return len(self.commits)

    @property
    def merge_commits(self) -> tuple[Commit, ...]:
        return tuple(c for c in self.commits if c.is_merge)

    @property
    def is_complete(self) -> bool:
        """True when no excerpt was truncated and none omitted.

        A report built from an incomplete bundle must say so; see
        `completeness_note`.
        """
        return self.lines_omitted == 0 and not self.files_without_excerpt

    def completeness_note(self) -> str:
        """A plain statement of what was and was not captured."""
        if self.is_complete:
            return "All diff content for this range was captured."
        parts = [f"{self.lines_captured} diff line(s) captured"]
        if self.lines_omitted:
            parts.append(f"{self.lines_omitted} omitted by the excerpt limits")
        if self.files_without_excerpt:
            parts.append(
                f"{len(self.files_without_excerpt)} file(s) have no excerpt at all"
            )
        return (
            "; ".join(parts)
            + ". Every file is still listed with a source pointer, and the full"
            " diff remains available from Git using the recorded command."
        )


def _parse_commit_record(record: str) -> Commit | None:
    fields = record.split(UNIT)
    if len(fields) < 10:
        return None

    sha, an, ae, aI, cn, ce, cI, parents, subject, body = fields[:10]
    if not sha.strip():
        return None

    return Commit(
        sha=sha.strip(),
        author_name=an,
        author_email=ae,
        authored_at=datetime.fromisoformat(aI),
        committer_name=cn,
        committer_email=ce,
        committed_at=datetime.fromisoformat(cI),
        subject=subject,
        body=body.strip("\n"),
        parent_shas=tuple(p for p in parents.split() if p),
    )


def collect_commits(repo: Repository, from_sha: str, to_sha: str) -> tuple[Commit, ...]:
    """Commits reachable from `to_sha` but not `from_sha`, newest first.

    ``git log A..B`` already excludes everything reachable from A, which is the
    same boundary the merge-base diff uses (D-021). The two therefore agree
    without special handling.

    Merge commits are included and flagged rather than filtered out: they are
    part of what happened, and dropping them would make the commit list
    disagree with the file changes.
    """
    result = run_git(
        ["log", f"--format={_LOG_FORMAT}", f"{from_sha}..{to_sha}"], cwd=repo.root
    )
    if result.returncode != 0:
        raise GitCommandFailed(
            f"could not list commits {from_sha}..{to_sha} in {repo.root}: "
            f"{result.stderr.strip()}"
        )

    commits = []
    for record in result.stdout.split(RECORD):
        if not record.strip():
            continue
        parsed = _parse_commit_record(record.lstrip("\n"))
        if parsed is not None:
            commits.append(parsed)
    return tuple(commits)


def describe_commit(repo: Repository, revision: Revision) -> Commit:
    """The single commit a revision points at.

    Used for a state snapshot, which has a revision but no range.
    """
    result = run_git(
        ["log", "-1", f"--format={_LOG_FORMAT}", revision.sha], cwd=repo.root
    )
    if result.returncode != 0:
        raise GitCommandFailed(
            f"could not read commit {revision.sha} in {repo.root}: "
            f"{result.stderr.strip()}"
        )

    record = result.stdout.split(RECORD)[0]
    commit = _parse_commit_record(record)
    if commit is None:
        raise GitCommandFailed(
            f"could not parse commit metadata for {revision.sha} in {repo.root}"
        )
    return commit


def _binary_paths(repo: Repository, from_sha: str, to_sha: str) -> set[str]:
    """Paths Git reports as binary, where '-' replaces the line counts."""
    result = run_git(
        ["diff", "--numstat", "-z", "--find-renames", from_sha, to_sha],
        cwd=repo.root,
    )
    if result.returncode != 0:
        return set()

    binary: set[str] = set()
    fields = result.stdout.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        if not entry.strip():
            index += 1
            continue
        parts = entry.split("\t")
        if len(parts) < 3:
            index += 1
            continue
        added, removed, path = parts[0], parts[1], parts[2]
        # A rename in -z numstat output leaves the path empty and follows with
        # old and new paths as separate fields.
        if path == "":
            if index + 2 < len(fields):
                path = fields[index + 2]
            index += 3
        else:
            index += 1
        if added == "-" and removed == "-":
            binary.add(path)
    return binary


def _diff_one_file(
    repo: Repository, from_sha: str, to_sha: str, path: str, previous_path: str | None
) -> str:
    """The full diff for a single path.

    One git invocation per file rather than splitting a combined diff on
    ``diff --git`` boundaries: slower, but a filename containing that string
    cannot corrupt the split.
    """
    paths = [previous_path, path] if previous_path else [path]
    result = run_git(
        [
            "-c",
            "core.quotePath=false",
            "diff",
            "--find-renames",
            "--no-color",
            from_sha,
            to_sha,
            "--",
            *paths,
        ],
        cwd=repo.root,
    )
    if result.returncode != 0:
        raise GitCommandFailed(
            f"could not diff {path} between {from_sha} and {to_sha} in "
            f"{repo.root}: {result.stderr.strip()}"
        )
    return result.stdout


def _reproduce_command(repo: Repository, from_sha: str, to_sha: str, paths: list[str]) -> str:
    quoted = " ".join(f"'{p}'" for p in paths)
    return f"git -C '{repo.root}' diff {from_sha} {to_sha} -- {quoted}"


def _allocate(sizes: dict[str, int], limits: ExcerptLimits) -> dict[str, int]:
    """Share the total line budget across files, smallest need first.

    Each file is offered an equal share of what remains. A file needing less
    than its share takes only what it needs, and the surplus is redistributed
    to the files still waiting. The result is that small files are captured in
    full and large ones split the remainder — rather than whichever file sorts
    first consuming the budget and starving the rest.

    Deterministic: ties are broken by path, so the allocation does not depend
    on dictionary ordering.
    """
    allowances: dict[str, int] = {}
    remaining_budget = limits.max_lines_total
    pending = sorted(sizes.items(), key=lambda item: (item[1], item[0]))

    for position, (path, size) in enumerate(pending):
        files_left = len(pending) - position
        fair_share = remaining_budget // files_left if files_left else 0
        granted = min(size, limits.max_lines_per_file, fair_share)
        allowances[path] = max(granted, 0)
        remaining_budget -= allowances[path]

    return allowances


def collect_evidence(
    repo: Repository,
    summary: ChangeSummary,
    limits: ExcerptLimits = DEFAULT_LIMITS,
) -> EvidenceBundle:
    """Gather commits and bounded diff excerpts for a comparison.

    Every changed file gets an excerpt record, even when its text is truncated
    or omitted entirely. Dropping a file from the record would under-report the
    change; dropping only its *text*, and saying so, does not.
    """
    commits = collect_commits(repo, summary.merge_base, summary.target.sha)
    binary = _binary_paths(repo, summary.merge_base, summary.target.sha)

    # Phase 1: read every diff before allocating any budget. Spending it
    # first-come would let alphabetical order decide which evidence a reviewer
    # sees — a generated lockfile early in the sort could starve a genuine
    # business-rule change later in it. Measured on 237feed-app: package-lock
    # .json is 3835 of 7442 diff lines in a single range.
    raw_diffs: dict[str, str] = {}
    for change in summary.changes:
        if change.path in binary:
            continue
        raw_diffs[change.path] = _diff_one_file(
            repo,
            summary.merge_base,
            summary.target.sha,
            change.path,
            change.previous_path,
        )

    allowances = _allocate(
        {path: len(text.splitlines()) for path, text in raw_diffs.items()}, limits
    )

    excerpts: list[DiffExcerpt] = []
    without_excerpt: list[str] = []
    captured = 0
    omitted = 0

    for change in summary.changes:
        paths = (
            [change.previous_path, change.path]
            if change.previous_path
            else [change.path]
        )
        pointer = SourcePointer(
            repository_root=repo.root,
            revision=summary.target.sha,
            path=change.path,
            reproduce=_reproduce_command(
                repo, summary.merge_base, summary.target.sha, paths
            ),
        )

        if change.path in binary:
            excerpts.append(
                DiffExcerpt(
                    path=change.path,
                    previous_path=change.previous_path,
                    change_type=change.change_type,
                    pointer=pointer,
                    text="",
                    total_lines=0,
                    is_binary=True,
                    omitted_reason="binary file; Git reports no textual diff",
                )
            )
            without_excerpt.append(change.path)
            continue

        lines = raw_diffs[change.path].splitlines()
        total = len(lines)
        allowance = allowances.get(change.path, 0)

        if allowance <= 0:
            omitted += total
            without_excerpt.append(change.path)
            excerpts.append(
                DiffExcerpt(
                    path=change.path,
                    previous_path=change.previous_path,
                    change_type=change.change_type,
                    pointer=pointer,
                    text="",
                    total_lines=total,
                    truncated=True,
                    omitted_lines=total,
                    omitted_reason=(
                        f"no share of the {limits.max_lines_total}-line excerpt "
                        "budget was available for this file"
                    ),
                )
            )
            continue

        kept = lines[:allowance]
        dropped = total - len(kept)

        captured += len(kept)
        omitted += dropped

        excerpts.append(
            DiffExcerpt(
                path=change.path,
                previous_path=change.previous_path,
                change_type=change.change_type,
                pointer=pointer,
                text="\n".join(kept),
                total_lines=total,
                truncated=dropped > 0,
                omitted_lines=dropped,
                omitted_reason=(
                    f"excerpt limited to {allowance} of {total} lines"
                    if dropped
                    else None
                ),
            )
        )

    return EvidenceBundle(
        commits=commits,
        excerpts=tuple(excerpts),
        limits=limits,
        lines_captured=captured,
        lines_omitted=omitted,
        files_without_excerpt=tuple(without_excerpt),
    )
