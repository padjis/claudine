"""Attributing commits to a ticket.

A ticket's work is expected to be merged onto an integration or release branch
but not yet into mainline (D-031), so the search window is everything
reachable from any ref *except* what mainline already has.

Two attribution sources, in the priority order set by D-030:

1. **A branch whose name encodes the ticket** — `feat/622-prune-dead-tokens`.
   Unambiguous, and independent of commit-message discipline.
2. **Commit-message references** — only about 5% of Subject A's commits carry
   any reference at all, so this finds less than it appears to.

Where a commit was found is recorded. "On `refs/heads/develop`" and "on an
abandoned branch" are different provenance (product rule 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .errors import GitCommandFailed
from .git.adapter import Repository, run_git


class Attribution(str, Enum):
    """How a commit was tied to a ticket."""

    BRANCH_NAME = "branch_name"
    COMMIT_MESSAGE = "commit_message"


class TicketStatus(str, Enum):
    """Where a ticket's work was found. Three distinct answers (D-031)."""

    PENDING = "pending"
    """Commits found outside mainline. The expected case: merged, not landed."""

    LANDED = "landed"
    """Commits found, but only in mainline. Already shipped — not "nothing"."""

    NOT_FOUND = "not_found"
    """No commits matched anywhere. The reference matched nothing, which is not
    the same as "this ticket changed nothing"."""


@dataclass(frozen=True)
class TicketCommit:
    sha: str
    subject: str
    attribution: Attribution
    found_on: tuple[str, ...]
    """Refs this commit is reachable from. Evidence, not decoration."""


@dataclass(frozen=True)
class TicketMatch:
    """What a repository knows about a ticket."""

    repository_alias: str
    status: TicketStatus
    commits: tuple[TicketCommit, ...] = ()
    branches: tuple[str, ...] = ()
    """Branches whose name encodes the ticket."""

    @property
    def commit_count(self) -> int:
        return len(self.commits)


def reference_pattern(reference: str) -> str:
    """A regex matching the reference as a whole token.

    Bare numeric references are the reason this exists: a plain `622` would
    otherwise match `6220` and `1622`. Anchored on non-alphanumeric
    boundaries rather than `\\b`, because `#617` and `ABC-123` both start or
    end on punctuation.
    """
    escaped = re.escape(reference)
    return f"(^|[^0-9A-Za-z]){escaped}([^0-9A-Za-z]|$)"


def branches_naming(repo: Repository, reference: str) -> tuple[str, ...]:
    """Refs whose name contains the reference as a token.

    Matches `feat/622-prune-dead-tokens` for `622`, but not `feat/6220-other`.
    """
    result = run_git(
        ["for-each-ref", "--format=%(refname)", "refs/heads/", "refs/remotes/"],
        cwd=repo.root,
    )
    if result.returncode != 0:
        return ()

    pattern = re.compile(reference_pattern(reference))
    names = (line.strip() for line in result.stdout.split("\n") if line.strip())
    return tuple(sorted(name for name in names if pattern.search(name)))


def _refs_containing(repo: Repository, sha: str) -> tuple[str, ...]:
    result = run_git(
        ["for-each-ref", "--contains", sha, "--format=%(refname)"], cwd=repo.root
    )
    if result.returncode != 0:
        return ()
    return tuple(sorted(line.strip() for line in result.stdout.split("\n") if line.strip()))


def _log(repo: Repository, args: list[str]) -> list[tuple[str, str]]:
    result = run_git(["log", "--format=%H%x1f%s", *args], cwd=repo.root)
    if result.returncode != 0:
        raise GitCommandFailed(
            f"could not search commits in {repo.root}: {result.stderr.strip()}"
        )

    found = []
    for line in result.stdout.split("\n"):
        if "\x1f" not in line:
            continue
        sha, subject = line.split("\x1f", 1)
        if sha.strip():
            found.append((sha.strip(), subject))
    return found


def find_ticket_commits(
    repo: Repository, reference: str, mainline: str, alias: str | None = None
) -> TicketMatch:
    """Find commits attributable to `reference` that mainline does not have.

    Returns a match whose status distinguishes "not yet in mainline" from
    "already landed" from "found nothing" (D-031). The three are different
    answers and must not be rendered alike.
    """
    alias = alias or repo.root.name
    pattern = reference_pattern(reference)
    named_branches = branches_naming(repo, reference)

    collected: dict[str, TicketCommit] = {}

    # 1. Branch-name attribution: everything those branches add to mainline.
    for branch in named_branches:
        for sha, subject in _log(repo, [branch, "--not", mainline]):
            collected[sha] = TicketCommit(
                sha=sha,
                subject=subject,
                attribution=Attribution.BRANCH_NAME,
                found_on=_refs_containing(repo, sha),
            )

    # 2. Commit-message attribution, across everything mainline lacks.
    for sha, subject in _log(
        repo, ["--all", "--not", mainline, "-E", f"--grep={pattern}"]
    ):
        if sha not in collected:
            collected[sha] = TicketCommit(
                sha=sha,
                subject=subject,
                attribution=Attribution.COMMIT_MESSAGE,
                found_on=_refs_containing(repo, sha),
            )

    if collected:
        commits = tuple(sorted(collected.values(), key=lambda c: c.sha))
        return TicketMatch(
            repository_alias=alias,
            status=TicketStatus.PENDING,
            commits=commits,
            branches=named_branches,
        )

    # Nothing ahead of mainline. Distinguish "already landed" from "no such
    # reference" — reporting both as "nothing found" would be misleading.
    landed = _log(repo, [mainline, "-E", f"--grep={pattern}"])
    if landed:
        return TicketMatch(
            repository_alias=alias,
            status=TicketStatus.LANDED,
            commits=tuple(
                TicketCommit(
                    sha=sha,
                    subject=subject,
                    attribution=Attribution.COMMIT_MESSAGE,
                    found_on=(f"refs/heads/{mainline}",),
                )
                for sha, subject in sorted(landed)
            ),
            branches=named_branches,
        )

    return TicketMatch(
        repository_alias=alias,
        status=TicketStatus.NOT_FOUND,
        branches=named_branches,
    )
