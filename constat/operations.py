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

from .ai import (
    NULL_PROVIDER_NAME,
    Interpretation,
    Provider,
    ProviderPayload,
    SecretFinding,
    describe_scan,
    guard_release,
    redact,
    scan,
)
from .ai import resolve as resolve_provider
from .errors import PayloadRefused, RepositoryError
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
    interpretation: Interpretation | None = None
    scan_findings: tuple[SecretFinding, ...] = ()
    scan_accepted: bool = False

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


def _render_rejections(interpretation: Interpretation) -> list[str]:
    """List proposals the provider offered and the parser discarded.

    Omitting these would show a reviewer two rules when the provider offered
    eight, which misstates what the pass did. The reasons matter too: an
    ungrounded anchor means the model invented a path, and a reviewer should
    know that happened.
    """
    if not interpretation.rejections:
        return []

    lines = [
        f"{len(interpretation.rejections)} proposal(s) returned by "
        f"{interpretation.describe()} were **discarded** before reaching this "
        "document, for the reasons given. They are listed because a silently "
        "shortened list would misstate what the pass produced.",
        "",
    ]
    lines += [f"- {rejection.describe()}" for rejection in interpretation.rejections]
    lines.append("")
    return lines


def _render_rules(interpretation: Interpretation) -> list[str]:
    """Render the rules section, which always appears.

    An absent section would be read as "there are no rules here" — the one
    thing Constat must never imply (product rule 1). So the section is
    unconditional and its note carries the distinction between *no rules were
    identified* and *no rules exist*.
    """
    lines = ["## Business rules", ""]

    if not interpretation.identified_rules:
        lines += [
            interpretation.note
            or "No rules were identified. That is not a statement that none exist.",
            "",
        ]
        return lines + _render_rejections(interpretation)

    lines += [
        f"{len(interpretation.proposals)} rule(s) proposed by "
        f"{interpretation.describe()}. Every one is an interpretation, not a "
        "finding: proposals carry no authority until a human accepts them "
        "individually (D-036, D-039).",
        "",
    ]
    for proposal in interpretation.proposals:
        lines.append(f"### {proposal.name}")
        lines.append("")
        lines.append(f"{proposal.statement}")
        lines.append("")
        lines.append(f"Provenance: `{proposal.provenance.value}`.")
        lines.append("")
        if proposal.behaviours:
            lines.append("Behaviours:")
            lines.append("")
            for behaviour in proposal.behaviours:
                lines.append(f"- {behaviour.description}")
            lines.append("")
        if proposal.anchors:
            lines.append("Anchors:")
            lines.append("")
            for anchor in proposal.anchors:
                scope = f"{anchor.repository_alias}:" if anchor.repository_alias else ""
                lines.append(f"- `{scope}{anchor.path_glob}`")
            lines.append("")
        else:
            lines += [
                "No anchors proposed, so this rule can never be matched to a "
                "future change.",
                "",
            ]
    return lines + _render_rejections(interpretation)


def render(
    reference: str,
    findings: tuple[RepositoryFindings, ...],
    interpretation: Interpretation | None = None,
    scan_section: list[str] | None = None,
) -> str:
    """Render the machine-derived part of a document.

    Every searched repository appears, including those that contributed
    nothing. Silence about a repository is indistinguishable from "no changes
    there", and the two are not the same claim.

    `interpretation` and `scan_section` are optional only so the evidence
    rendering stays callable on its own. When either is absent its section is
    omitted entirely rather than rendered as empty, because an empty section is
    itself a claim.
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

    if scan_section:
        lines += scan_section

    if interpretation is not None:
        lines += _render_rules(interpretation)

    lines += ["---", ""]
    if interpretation is not None and interpretation.identified_rules:
        lines.append(
            "Evidence above is observed fact; the rules are "
            "`ai_interpretation`. The two are kept separate on purpose "
            "(product rule 3), and neither is approved: this document carries "
            "no authority until a human approves a version of it."
        )
    else:
        lines.append(
            "Observed facts only. Nothing here is classified, interpreted or "
            "approved: every excerpt records the command that regenerates it, "
            "and this document carries no authority until a human approves a "
            "version of it."
        )
    return "\n".join(lines)


def collect(
    workspace: Workspace,
    reference: str,
    limits: ExcerptLimits = DEFAULT_LIMITS,
) -> tuple[RepositoryFindings, ...]:
    """Read every registered repository for a ticket. Writes nothing.

    Shared by `gather` and `export_payload` so the two cannot disagree about
    what a ticket's evidence is.
    """
    TicketStore(workspace).document(reference)  # NotRegistered if unknown
    registry = Registry(workspace)
    return tuple(
        _collect_repository(entry, reference, limits) for entry in registry.list()
    )


@dataclass(frozen=True)
class ExportResult:
    """A payload cleared to leave the process, and what the scan found."""

    payload: ProviderPayload
    scan_findings: tuple[SecretFinding, ...] = ()
    accepted: bool = False


def export_payload(
    workspace: Workspace,
    reference: str,
    limits: ExcerptLimits = DEFAULT_LIMITS,
    accept_scan_findings: bool = False,
) -> ExportResult:
    """Produce the payload for something outside this process to read.

    **This is the second front door** (D-045). Whatever reads the result — an
    agent, an MCP client, a person with a clipboard — is outside Constat, so
    the payload is leaving: redaction applies, and the credential gate applies
    *unconditionally*, not only when a provider is configured.

    That is the one asymmetry with `gather`. A local run that sends nothing can
    tolerate a false positive; an export cannot, because by the time it has
    printed, it has left.

    Writes nothing except an override record when findings were accepted — an
    override nobody can see afterwards is the same as no scan (D-044).
    """
    findings = collect(workspace, reference, limits)
    payload = redact(reference, findings)
    scan_findings = guard_release(payload, accepted=accept_scan_findings)

    accepted = bool(scan_findings)
    if accepted:
        _record_scan_override(workspace, reference, scan_findings, kind="scan_override_export")

    return ExportResult(
        payload=payload, scan_findings=scan_findings, accepted=accepted
    )


def _record_scan_override(
    workspace: Workspace,
    reference: str,
    scan_findings: tuple[SecretFinding, ...],
    kind: str,
) -> None:
    """Record that a human let credential findings through.

    Against the document rather than a repository: the decision was about the
    payload as a whole. Locations are kept so the override stays auditable; the
    matched text never is.
    """
    document_id = workspace.execute(
        "SELECT d.id FROM document d JOIN ticket t ON t.id = d.ticket_id "
        "WHERE t.reference = ?",
        (reference,),
    ).fetchone()["id"]

    with workspace.transaction() as ws:
        ws.execute(
            "INSERT INTO operation "
            "(document_id, repository_id, kind, ran_at, summary, payload) "
            f"VALUES (?, NULL, '{kind}', ?, ?, ?)",
            (
                document_id,
                utc_now(),
                f"accepted {len(scan_findings)} credential-scan finding(s)",
                "\n".join(f.describe() for f in scan_findings),
            ),
        )


def gather(
    workspace: Workspace,
    reference: str,
    limits: ExcerptLimits = DEFAULT_LIMITS,
    provider: Provider | None = None,
    accept_scan_findings: bool = False,
) -> OperationResult:
    """Run the gathering operation for a ticket and expand its document.

    The provider is resolved **before** any repository is read, so a
    misconfiguration fails immediately rather than after the expensive part.
    With none configured this is the null provider and nothing leaves the
    machine.

    The payload is scanned for credentials on every run, and refused if any are
    found *and* a provider would actually receive it (CON-45). Scanning always
    but refusing only at the point of transmission keeps two things true at
    once: a false positive cannot block a local run that sends nothing, and the
    scanner is not dead code until a provider exists.

    `accept_scan_findings` overrides the refusal for this run only. It is
    recorded in the document and as an operation, because an override nobody
    can see afterwards is indistinguishable from no scan at all.
    """
    if provider is None:
        provider = resolve_provider()

    findings = collect(workspace, reference, limits)

    # Redaction happens on the real path rather than only where a provider
    # exists. A privacy boundary first exercised by the code that needs it is
    # a boundary first tested in production.
    payload = redact(reference, findings)

    sends_payload = provider.name != NULL_PROVIDER_NAME
    if sends_payload:
        # Refused before `interpret`, and before the document is written. A
        # partially updated document would be worse than none: it would record
        # evidence as if the run had succeeded.
        scan_findings = guard_release(payload, accepted=accept_scan_findings)
    else:
        # Nothing is transmitted, so nothing is refused — but the scan still
        # runs and is still reported (D-044).
        scan_findings = scan(payload)

    accepted = bool(scan_findings) and sends_payload and accept_scan_findings
    now = utc_now()
    scan_section = describe_scan(
        payload,
        scan_findings,
        sent=sends_payload,
        accepted=accepted,
        accepted_at=now if accepted else None,
    )

    interpretation = provider.interpret(payload)

    body = render(reference, findings, interpretation, scan_section)

    document_id = workspace.execute(
        "SELECT d.id FROM document d JOIN ticket t ON t.id = d.ticket_id "
        "WHERE t.reference = ?",
        (reference,),
    ).fetchone()["id"]

    with workspace.transaction() as ws:
        ws.execute(
            "UPDATE document SET body = ?, updated_at = ? WHERE id = ?",
            (body, now, document_id),
        )
        if accepted:
            # Recorded against the document rather than a repository: the
            # decision was about the payload as a whole. The locations are kept
            # so the override stays auditable; the matched text never is.
            ws.execute(
                "INSERT INTO operation "
                "(document_id, repository_id, kind, ran_at, summary, payload) "
                "VALUES (?, NULL, 'scan_override', ?, ?, ?)",
                (
                    document_id,
                    now,
                    f"accepted {len(scan_findings)} credential-scan finding(s)",
                    "\n".join(f.describe() for f in scan_findings),
                ),
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

    return OperationResult(
        reference=reference,
        findings=findings,
        body=body,
        interpretation=interpretation,
        scan_findings=scan_findings,
        scan_accepted=accepted,
    )
