"""Operations: gathering evidence for a ticket across the registered set.

An operation reads every registered repository, resolves the ticket's commit
set (D-030, D-031), collects bounded evidence for it, and expands the ticket's
document. Each run is recorded — what ran, against which repository, when, and
what it contributed — because a document whose contents cannot be attributed
is the failure this product exists to prevent (D-029).

**Evidence is collected per commit, not as one cumulative diff.** A ticket's
commits need not be contiguous, so there is no single revision range that
means "this ticket's effect". Diffing the first commit's parent against the
last would sweep in whatever else landed between them. Per-commit collection
costs some duplication — a file touched three times appears three times — but
each hunk stays attributable to the commit that made it, which is the whole
point of provenance (product rule 3).
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import RepositoryError
from .evidence import DEFAULT_LIMITS, EvidenceBundle, ExcerptLimits, collect_evidence
from .git.adapter import Repository, Revision, discover_repository, resolve_revision
from .git.diff import compare_revisions
from .models import RegisteredRepository
from .store import Registry, TicketStore, Workspace
from .store.workspace import utc_now
from .tickets import TicketMatch, TicketStatus, find_ticket_commits


@dataclass(frozen=True)
class CommitEvidence:
    """One attributed commit and the evidence for what it changed."""

    sha: str
    subject: str
    attribution: str
    found_on: tuple[str, ...]
    bundle: EvidenceBundle | None
    error: str | None = None


@dataclass(frozen=True)
class RepositoryFindings:
    """What one repository contributed, including nothing."""

    repository: RegisteredRepository
    status: TicketStatus
    match: TicketMatch
    commits: tuple[CommitEvidence, ...] = ()
    error: str | None = None

    @property
    def contributed(self) -> bool:
        return bool(self.commits)


@dataclass(frozen=True)
class OperationResult:
    reference: str
    findings: tuple[RepositoryFindings, ...]
    body: str

    @property
    def repositories_searched(self) -> int:
        return len(self.findings)

    @property
    def repositories_contributing(self) -> int:
        return sum(1 for f in self.findings if f.contributed)


def _evidence_for_commit(
    repo: Repository, sha: str, limits: ExcerptLimits
) -> EvidenceBundle:
    """Evidence for a single commit, relative to its first parent.

    First parent rather than a merge base: for a merge commit this yields what
    the merge brought in, which is what the merge contributed.
    """
    parent = resolve_revision(repo, f"{sha}^")
    target = resolve_revision(repo, sha)
    summary = compare_revisions(repo, parent, target)
    return collect_evidence(repo, summary, limits)


def _collect_repository(
    entry: RegisteredRepository, reference: str, limits: ExcerptLimits
) -> RepositoryFindings:
    try:
        repo = discover_repository(entry.source)
    except RepositoryError as exc:
        from .tickets import TicketMatch as _Match

        return RepositoryFindings(
            repository=entry,
            status=TicketStatus.NOT_FOUND,
            match=_Match(repository_alias=entry.alias, status=TicketStatus.NOT_FOUND),
            error=str(exc),
        )

    match = find_ticket_commits(repo, reference, entry.default_branch, entry.alias)
    if match.status is not TicketStatus.PENDING:
        # Landed and not-found both contribute no evidence, but they are
        # different answers and the document must say which (D-031).
        return RepositoryFindings(
            repository=entry, status=match.status, match=match
        )

    collected = []
    for commit in match.commits:
        try:
            bundle = _evidence_for_commit(repo, commit.sha, limits)
            error = None
        except RepositoryError as exc:
            # A root commit has no parent. Record the reason rather than
            # dropping the commit, which would under-report silently.
            bundle, error = None, str(exc)
        collected.append(
            CommitEvidence(
                sha=commit.sha,
                subject=commit.subject,
                attribution=commit.attribution.value,
                found_on=commit.found_on,
                bundle=bundle,
                error=error,
            )
        )

    return RepositoryFindings(
        repository=entry,
        status=match.status,
        match=match,
        commits=tuple(collected),
    )


def render(reference: str, findings: tuple[RepositoryFindings, ...]) -> str:
    """Render the machine-derived part of a document.

    Every searched repository appears, including those that contributed
    nothing. Silence about a repository is indistinguishable from "no changes
    there", and the two are not the same claim.
    """
    lines: list[str] = [f"# Ticket {reference}", ""]

    if not findings:
        lines += [
            "No repositories are registered, so nothing was searched.",
            "",
            "This is not a statement that the ticket changed nothing.",
        ]
        return "\n".join(lines)

    contributing = [f for f in findings if f.contributed]
    lines += [
        f"{len(findings)} repository(ies) searched; "
        f"{len(contributing)} contributed evidence.",
        "",
    ]

    for finding in findings:
        entry = finding.repository
        lines.append(f"## {entry.alias}")
        lines.append("")
        lines.append(f"Measured against `{entry.default_branch}`.")
        lines.append("")

        if finding.error:
            lines += [f"Could not be read: {finding.error}", ""]
            continue

        if finding.status is TicketStatus.LANDED:
            lines += [
                f"Already in `{entry.default_branch}` "
                f"({finding.match.commit_count} commit(s)). Outside the window "
                "Constat documents, so no evidence was gathered here — which is "
                "not the same as finding nothing.",
                "",
            ]
            continue

        if finding.status is TicketStatus.NOT_FOUND:
            lines += [
                "No commits reference this ticket. That means the reference "
                "matched nothing here, not that the ticket changed nothing.",
                "",
            ]
            continue

        refs = sorted({r for c in finding.commits for r in c.found_on})
        if refs:
            lines += ["Found on: " + ", ".join(f"`{r}`" for r in refs), ""]

        for commit in finding.commits:
            lines.append(f"### `{commit.sha[:12]}` {commit.subject}")
            lines.append("")
            lines.append(f"Attributed by {commit.attribution.replace('_', ' ')}.")
            lines.append("")

            if commit.error or commit.bundle is None:
                lines += [f"No diff available: {commit.error}", ""]
                continue

            bundle = commit.bundle
            if not bundle.excerpts:
                lines += ["No file changes in this commit.", ""]
                continue

            lines.append(f"{len(bundle.excerpts)} file(s) changed:")
            lines.append("")
            for excerpt in bundle.excerpts:
                name = (
                    f"{excerpt.previous_path} → {excerpt.path}"
                    if excerpt.previous_path
                    else excerpt.path
                )
                lines.append(f"- `{name}` ({excerpt.change_type.name.lower()})")
            lines.append("")
            lines.append(bundle.completeness_note())
            lines.append("")

    lines += [
        "---",
        "",
        "Observed facts only. Nothing here is classified, interpreted or "
        "approved: every excerpt records the command that regenerates it, and "
        "this document carries no authority until a human approves a version "
        "of it.",
    ]
    return "\n".join(lines)


def gather(
    workspace: Workspace,
    reference: str,
    limits: ExcerptLimits = DEFAULT_LIMITS,
) -> OperationResult:
    """Run the gathering operation for a ticket and expand its document."""
    tickets = TicketStore(workspace)
    tickets.document(reference)  # raises NotRegistered if the ticket is unknown

    registry = Registry(workspace)
    findings = tuple(
        _collect_repository(entry, reference, limits) for entry in registry.list()
    )
    body = render(reference, findings)

    document_id = workspace.execute(
        "SELECT d.id FROM document d JOIN ticket t ON t.id = d.ticket_id "
        "WHERE t.reference = ?",
        (reference,),
    ).fetchone()["id"]

    now = utc_now()
    with workspace.transaction() as ws:
        ws.execute(
            "UPDATE document SET body = ?, updated_at = ? WHERE id = ?",
            (body, now, document_id),
        )
        for finding in findings:
            repository_id = ws.execute(
                "SELECT id FROM repository WHERE alias = ?",
                (finding.repository.alias,),
            ).fetchone()["id"]
            ws.execute(
                "INSERT INTO operation "
                "(document_id, repository_id, kind, ran_at, summary) "
                "VALUES (?, ?, 'gather_evidence', ?, ?)",
                (
                    document_id,
                    repository_id,
                    now,
                    f"{finding.status.value}: {len(finding.commits)} commit(s)",
                ),
            )

    return OperationResult(reference=reference, findings=findings, body=body)
