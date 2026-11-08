"""Deterministic change and state summaries.

Two questions, two functions, deliberately not sharing a return type (D-016):

* ``compare_revisions`` — what changed between two revisions.
* ``summarise_state`` — what files a single revision contains.

State is read with ``ls-tree`` rather than as a diff against the empty tree.
The empty-tree trick works, but it labels every file ``ADDED``, which is change
vocabulary answering a state question. A snapshot asserts "this is what is
here", not "this was all just added".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..errors import BackwardsRange, GitCommandFailed, NoCommonAncestor
from .adapter import Repository, Revision, run_git


class ChangeType(Enum):
    """Git's own status letters, named.

    ``UNKNOWN`` exists because an unrecognised letter must not be guessed at —
    `unknown` is an acceptable result (product rule 1).
    """

    ADDED = "A"
    COPIED = "C"
    DELETED = "D"
    MODIFIED = "M"
    RENAMED = "R"
    TYPE_CHANGED = "T"
    UNMERGED = "U"
    UNKNOWN = "X"

    @classmethod
    def parse(cls, letter: str) -> "ChangeType":
        try:
            return cls(letter[:1].upper())
        except ValueError:
            return cls.UNKNOWN


@dataclass(frozen=True)
class FileChange:
    """One file's change between two revisions.

    A rename keeps ``previous_path``. Reporting a rename as a delete plus an add
    would misstate the change and break any evidence anchored to the old path.
    """

    change_type: ChangeType
    path: str
    previous_path: str | None = None
    similarity: int | None = None
    """Git's similarity score for a rename or copy, 0-100. None otherwise."""

    @property
    def is_rename(self) -> bool:
        return self.change_type in (ChangeType.RENAMED, ChangeType.COPIED)


@dataclass(frozen=True)
class ChangeSummary:
    """What changed between two revisions, and what was actually compared."""

    base: Revision
    target: Revision
    merge_base: str
    """The commit the comparison ran *from* (D-021). Recorded because it is not
    necessarily ``base``, and a reviewer cannot verify the summary without it."""
    changes: tuple[FileChange, ...]

    @property
    def is_empty(self) -> bool:
        return not self.changes

    @property
    def base_is_merge_base(self) -> bool:
        """True when base is a direct ancestor of target — the simple case."""
        return self.merge_base == self.base.sha

    def of_type(self, change_type: ChangeType) -> tuple[FileChange, ...]:
        return tuple(c for c in self.changes if c.change_type is change_type)


@dataclass(frozen=True)
class StateSummary:
    """What a single revision contains. Not a change (D-016)."""

    revision: Revision
    paths: tuple[str, ...]

    @property
    def file_count(self) -> int:
        return len(self.paths)


# Config forced on every diff so output does not depend on the user's settings.
# Rename detection must be on for `previous_path` to ever be populated, and
# quotePath off keeps paths literal.
_DIFF_CONFIG = ["-c", "diff.renames=true", "-c", "core.quotePath=false"]


def find_merge_base(repo: Repository, base: Revision, target: Revision) -> str:
    """The commit from which `target` diverged from `base`.

    Raises NoCommonAncestor when the histories are unrelated.
    """
    result = run_git(["merge-base", base.sha, target.sha], cwd=repo.root)
    merge_base = result.stdout.strip()

    if result.returncode != 0 or not merge_base:
        raise NoCommonAncestor(
            f"{base.symbolic!r} and {target.symbolic!r} share no common ancestor "
            f"in {repo.root}, so there is no point to compare from."
        )
    return merge_base


def compare_revisions(
    repo: Repository, base: Revision, target: Revision
) -> ChangeSummary:
    """Summarise what `target` introduced relative to `base`.

    Compares from the merge base rather than between the two endpoints (D-021):
    the question is what target added since it diverged, not how two trees
    happen to differ.

    Raises NoCommonAncestor or BackwardsRange.
    """
    merge_base = find_merge_base(repo, base, target)

    # Under merge-base comparison, a target that is an ancestor of base gives an
    # empty diff. That reads as "nothing changed" when the real cause is
    # reversed arguments, so refuse it.
    if merge_base == target.sha and target.sha != base.sha:
        raise BackwardsRange(
            f"{target.symbolic!r} is an ancestor of {base.symbolic!r}, so the "
            "range runs backwards and would show no changes. Swap --base and "
            "--target if that was the intent."
        )

    result = run_git(
        [
            *_DIFF_CONFIG,
            "diff",
            "--name-status",
            "--find-renames",
            "-z",
            "--no-color",
            merge_base,
            target.sha,
        ],
        cwd=repo.root,
    )
    if result.returncode != 0:
        raise GitCommandFailed(
            f"could not diff {merge_base} against {target.sha} in {repo.root}: "
            f"{result.stderr.strip()}"
        )

    changes = _parse_name_status(result.stdout)
    return ChangeSummary(
        base=base,
        target=target,
        merge_base=merge_base,
        # Sorted explicitly: determinism is the acceptance criterion, and it
        # must not depend on git's output order staying stable across versions.
        changes=tuple(sorted(changes, key=lambda c: (c.path, c.change_type.value))),
    )


def _parse_name_status(payload: str) -> list[FileChange]:
    """Parse `git diff --name-status -z` output.

    NUL-separated rather than line-based, because a path may legitimately
    contain a space or a newline and line parsing would silently mangle it.

    Records are ``status NUL path NUL``, except renames and copies which are
    ``status NUL old NUL new NUL``.
    """
    fields = [field for field in payload.split("\0") if field != ""]
    changes: list[FileChange] = []

    index = 0
    while index < len(fields):
        status = fields[index]
        change_type = ChangeType.parse(status)
        index += 1

        if index >= len(fields):
            break  # truncated record; nothing to attach the status to

        if change_type in (ChangeType.RENAMED, ChangeType.COPIED):
            if index + 1 >= len(fields):
                break
            previous_path, path = fields[index], fields[index + 1]
            index += 2
            changes.append(
                FileChange(
                    change_type=change_type,
                    path=path,
                    previous_path=previous_path,
                    similarity=_similarity(status),
                )
            )
        else:
            changes.append(FileChange(change_type=change_type, path=fields[index]))
            index += 1

    return changes


def _similarity(status: str) -> int | None:
    """The numeric score in a status like ``R100``, or None if absent."""
    digits = status[1:]
    return int(digits) if digits.isdigit() else None


def summarise_state(repo: Repository, revision: Revision) -> StateSummary:
    """List the files present at `revision`.

    Uses ``ls-tree`` rather than a diff against the empty tree, so nothing in a
    state description is expressed in change vocabulary (D-016).
    """
    result = run_git(
        ["ls-tree", "-r", "-z", "--name-only", "--full-tree", revision.sha],
        cwd=repo.root,
    )
    if result.returncode != 0:
        raise GitCommandFailed(
            f"could not list files at {revision.symbolic} in {repo.root}: "
            f"{result.stderr.strip()}"
        )

    paths = [path for path in result.stdout.split("\0") if path != ""]
    return StateSummary(revision=revision, paths=tuple(sorted(paths)))
