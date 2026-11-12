"""The privacy boundary: evidence in, provider payload out.

Settles the question deferred at D-023. Collected evidence carries author and
committer names, email addresses and timestamps. That is harmless while it
stays on the machine that produced it, and it is a personal-data disclosure
the moment it is sent to a third party, so product rule 7 (least privilege)
decides it: **identity does not cross this boundary at all.**

Rule generation needs to know *what* changed. It never needs to know *who*
changed it. There is therefore no reason for a name, an address or a date to
be in the payload, and the cheapest way to guarantee they are not is to build
a separate type that has nowhere to put them.

Two things make this more than a field-copying exercise:

- **Free text leaks identity.** A commit body carries `Signed-off-by:` and
  `Co-Authored-By:` trailers, and people write addresses into messages. Those
  are removed from messages rather than trusted to be absent.
- **Diffs leak identity too.** A changed `AUTHORS`, mailmap or contributor
  list puts addresses in the diff text itself. Addresses are masked there, but
  lines are never dropped: removing a line from a diff would misrepresent the
  change, and this module must not trade one kind of dishonesty for another.

The payload types are deliberately constructible only by going through
`redact`. If a caller could assemble one by hand, sooner or later one will,
with the author field it happened to have to hand.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance only
    from ..operations import RepositoryFindings

REDACTED = "[redacted]"

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
"""Deliberately broad. Over-masking a string that merely looks like an address
costs nothing a rule statement needs; under-masking discloses a real one."""

IDENTITY_TRAILER = re.compile(
    r"(?im)^[ \t]*(?:co-authored-by|signed-off-by|reported-by|reviewed-by"
    r"|tested-by|acked-by|suggested-by|helped-by|requested-by|cc)[ \t]*:.*$"
)
"""Git's conventional identity trailers. Removed from messages entirely —
their whole content is a person."""


def scrub_message(text: str) -> str:
    """Remove identity from a commit subject or body.

    Trailers go completely; anything address-shaped left in the prose is
    masked. Blank lines left behind by a removed trailer are collapsed so the
    result does not advertise how many people were stripped out.
    """
    without_trailers = IDENTITY_TRAILER.sub("", text)
    collapsed = re.sub(r"\n{3,}", "\n\n", without_trailers)
    return EMAIL.sub(REDACTED, collapsed).strip()


def scrub_diff(text: str) -> str:
    """Mask addresses in diff text without altering its line structure.

    A diff is evidence. Dropping a line would change what the evidence says,
    so only the address itself is replaced.
    """
    return EMAIL.sub(REDACTED, text)


@dataclass(frozen=True)
class FileChange:
    """One changed file as the provider sees it."""

    path: str
    change_type: str
    diff: str
    previous_path: str | None = None
    truncated: bool = False
    omitted_lines: int = 0
    is_binary: bool = False

    @property
    def is_complete(self) -> bool:
        return not self.truncated and not self.is_binary


@dataclass(frozen=True)
class CommitContext:
    """One commit, with no author, no committer and no dates.

    `sha` is kept: it identifies a commit, not a person, and it is how a
    proposal stays traceable to the evidence that produced it (product rule 2).
    """

    sha: str
    subject: str
    body: str
    files: tuple[FileChange, ...] = ()


@dataclass(frozen=True)
class RepositoryContext:
    """One repository's contribution, including nothing.

    Repositories that contributed nothing are still present, for the same
    reason the document keeps them: absence and silence are different claims.
    """

    alias: str
    default_branch: str
    status: str
    commits: tuple[CommitContext, ...] = ()
    unreadable: bool = False


@dataclass(frozen=True)
class KnownRule:
    """A rule already in the catalogue, as the provider sees it.

    Without this a reading cannot propose a *revision* — it has never been
    shown what exists, so every reading claims to be new and the second
    reading of a rule creates a duplicate (CON-43). The id is what a reply
    names in its `revises` field.
    """

    rule_id: int
    name: str
    statement: str
    anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderPayload:
    """Everything a provider is given, and nothing else."""

    reference: str
    repositories: tuple[RepositoryContext, ...] = ()
    catalogue: tuple[KnownRule, ...] = ()
    """Rules already accepted, so a reading can revise one instead of
    duplicating it. Carries no identity and no evidence — just what the
    workspace already holds."""

    @property
    def commit_count(self) -> int:
        return sum(len(r.commits) for r in self.repositories)

    @property
    def is_empty(self) -> bool:
        return self.commit_count == 0


def as_dict(payload: ProviderPayload) -> dict:
    """The payload as plain data, for handing to something outside this process.

    A deliberate function rather than `dataclasses.asdict` at the call site:
    the serialised shape is a contract once anything reads it, and it belongs
    next to the types it serialises so the two cannot drift.
    """
    return asdict(payload)


def redact(
    reference: str,
    findings: tuple[RepositoryFindings, ...],
    catalogue: tuple[KnownRule, ...] = (),
) -> ProviderPayload:
    """Build the provider payload from gathered findings, stripping identity."""
    repositories = []
    for finding in findings:
        commits = []
        for commit in finding.commits:
            files: list[FileChange] = []
            if commit.bundle is not None:
                for excerpt in commit.bundle.excerpts:
                    files.append(
                        FileChange(
                            path=excerpt.path,
                            previous_path=excerpt.previous_path,
                            change_type=excerpt.change_type.name.lower(),
                            diff=scrub_diff(excerpt.text),
                            truncated=excerpt.truncated,
                            omitted_lines=excerpt.omitted_lines,
                            is_binary=excerpt.is_binary,
                        )
                    )
            commits.append(
                CommitContext(
                    sha=commit.sha,
                    subject=scrub_message(commit.subject),
                    body=scrub_message(_commit_body(commit)),
                    files=tuple(files),
                )
            )
        repositories.append(
            RepositoryContext(
                alias=finding.repository.alias,
                default_branch=finding.repository.default_branch,
                status=finding.status.value,
                commits=tuple(commits),
                unreadable=finding.error is not None,
            )
        )
    return ProviderPayload(
        reference=reference,
        repositories=tuple(repositories),
        catalogue=catalogue,
    )


def _commit_body(commit) -> str:
    """The commit body, which lives on the evidence bundle rather than the
    attributed commit.

    Returns an empty string when no bundle was collected — a root commit, or a
    repository that could not be read. An absent body is not an error here.
    """
    if commit.bundle is None:
        return ""
    for record in commit.bundle.commits:
        if record.sha == commit.sha:
            return record.body
    return ""
