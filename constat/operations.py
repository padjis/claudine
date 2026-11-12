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

from dataclasses import dataclass, field

from .ai import (
    NULL_PROVIDER_NAME,
    Interpretation,
    Provider,
    ProviderPayload,
    Rejection,
    KnownRule,
    SecretFinding,
    describe_scan,
    guard_release,
    parse,
    redact,
    scan,
)
from .ai import resolve as resolve_provider
from .errors import PayloadRefused, RepositoryError
from .evidence import DEFAULT_LIMITS, EvidenceBundle, ExcerptLimits, collect_evidence
from .git.adapter import Repository, Revision, discover_repository, resolve_revision
from .git.diff import compare_revisions
from .models import RegisteredRepository
from .store import Catalogue, Registry, RuleProposals, TicketStore, Workspace
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
    run_id: int | None = None
    """The run this result belongs to. A rule proposal reads the evidence one
    run gathered (D-046), so the caller needs the identity, not just the
    body."""

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


PR_BODY_LIMIT = 65_536
"""GitHub's pull-request body limit.

The rendered document has to work as a PR body, and GitHub **truncates a longer
one silently** — which is the failure D-023 refuses for diff excerpts, one
level up. So Constat bounds it itself and states the omission.

A real 30-commit document measures about 21 KB, so this bites only on large
tickets. Stated rather than discovered on the day it does.
"""

EVIDENCE_HEADING = "## Evidence"


def bound_for_pr(body: str, reference: str, limit: int = PR_BODY_LIMIT) -> str:
    """Trim a document to fit a pull-request body, saying what was dropped.

    The **business half is never trimmed** — it is the half a reviewer decides
    from. Only the evidence goes, and it goes wholesale with a pointer to the
    command that shows it in full, the same contract every truncated excerpt
    carries (D-023).
    """
    if len(body) <= limit:
        return body

    head, _, tail = body.partition(EVIDENCE_HEADING)
    omitted = len(tail) + len(EVIDENCE_HEADING)
    notice = [
        EVIDENCE_HEADING,
        "",
        f"**Omitted here: {omitted} characters of evidence.** The full document "
        f"exceeds the {limit}-character limit for a pull-request body, which "
        "would otherwise be truncated silently.",
        "",
        f"See it in full with `constat document {reference} --show`.",
        "",
        "---",
        "",
        "The business section above is complete and was not trimmed.",
        "",
    ]
    bounded = head + "\n".join(notice)
    # The notice itself must fit. If the business half alone exceeds the limit,
    # say so rather than returning something a forge will cut mid-sentence.
    if len(bounded) > limit:
        return (
            f"# Ticket {reference}\n\n"
            f"This document is {len(body)} characters and does not fit a "
            f"pull-request body ({limit}). Read it with "
            f"`constat document {reference} --show`.\n"
        )
    return bounded


@dataclass(frozen=True)
class CatalogueView:
    """What the workspace holds about rules, as the document shows it.

    Passed *into* `render` rather than letting it reach for a workspace:
    rendering stays a pure function of stored structure (ARCHITECTURE.md § 2),
    so it can never discover a fact the store does not already hold.
    """

    impacted: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Current rule name -> the changed paths its anchors matched."""
    unclaimed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Repository alias -> changed paths no rule claims. The catalogue's
    failure mode, and it must stay visible (D-038, D-039)."""
    queue: tuple = ()
    """Rule proposals awaiting a human decision."""
    rule_count: int = 0
    """Rules in the catalogue, impacted or not — so "no rules were identified"
    can never be printed next to a catalogue that holds some."""


def _changed_paths(finding: RepositoryFindings) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                excerpt.path
                for commit in finding.commits
                if commit.bundle is not None
                for excerpt in commit.bundle.excerpts
            }
        )
    )


def catalogue_view(
    workspace: Workspace,
    reference: str,
    findings: tuple[RepositoryFindings, ...],
) -> CatalogueView:
    """Read what the workspace knows about rules for this ticket.

    Exists because the document used to render rules from the *current run's*
    interpretation, so a ticket whose catalogue held three rules still printed
    "no rules were identified" — a statement about configuration presented as a
    statement about the code, which is product rule 1's failure mode.
    """
    catalogue = Catalogue(workspace)
    impacted: dict[str, list[str]] = {}
    unclaimed: dict[str, tuple[str, ...]] = {}

    for finding in findings:
        paths = _changed_paths(finding)
        if not paths:
            continue
        alias = finding.repository.alias
        for name, matched in catalogue.rules_matching(alias, paths).items():
            impacted.setdefault(name, []).extend(matched)
        missing = catalogue.unmatched_paths(alias, paths)
        if missing:
            unclaimed[alias] = missing

    return CatalogueView(
        impacted={
            name: tuple(sorted(dict.fromkeys(paths)))
            for name, paths in sorted(impacted.items())
        },
        unclaimed=unclaimed,
        queue=RuleProposals(workspace).undecided(reference),
        rule_count=len(catalogue.list()),
    )


def _render_catalogue(view: CatalogueView) -> list[str]:
    """What the workspace knows about rules touched by this change.

    The business half of the document (product rule 8). It reports *code*
    being touched, never what a behaviour now does — that remains a reviewer's
    call (D-035, D-038).
    """
    lines: list[str] = []

    if view.impacted:
        lines += [
            f"{len(view.impacted)} rule(s) in the catalogue have anchors in what "
            "this ticket changed. That their implementation was touched is an "
            "observed fact; whether their behaviour changed is for a reviewer "
            "to say.",
            "",
        ]
        for name, paths in view.impacted.items():
            listed = ", ".join(f"`{path}`" for path in paths)
            lines.append(f"- **{name}** — matched {listed}")
        lines.append("")
    elif view.rule_count:
        lines += [
            f"None of the {view.rule_count} rule(s) in the catalogue has an "
            "anchor in what this ticket changed.",
            "",
        ]

    if view.unclaimed:
        total = sum(len(paths) for paths in view.unclaimed.values())
        lines += [
            f"**{total} changed path(s) are claimed by no rule.** A catalogue "
            "only knows the rules it holds, so this is where it is incomplete "
            "rather than where nothing happened (D-038).",
            "",
        ]
        # One per line rather than a comma-joined run: a real ticket produced
        # 29 of these, and a single paragraph of 29 paths is not readable in a
        # document or a pull request. Never abbreviated with "and N more" —
        # coverage is the thing that has to stay prominent (D-038, D-039).
        for alias, paths in sorted(view.unclaimed.items()):
            lines.append(f"In `{alias}`:")
            lines.append("")
            lines += [f"- `{path}`" for path in paths]
            lines.append("")

    if view.queue:
        lines += [
            f"{len(view.queue)} rule proposal(s) await a human decision. None "
            "carries any authority until accepted (D-036, D-037).",
            "",
        ]
        for item in view.queue:
            revises = (
                f", claiming to revise rule {item.revises_rule_id}"
                if item.revises_rule_id is not None
                else ""
            )
            # A GitHub task list, because this document also has to work as a
            # pull-request body. Ticking one is inert today; reading ticks back
            # is CON-58, and it is the *unverified* channel when it lands.
            lines.append(f"- [ ] `#{item.id}` **{item.proposal.name}**{revises}")
            lines.append(f"  {item.proposal.statement}")
            lines.append(f"  Read by {item.attribution}.")
        lines += [
            "",
            "Ticking a box above records nothing yet. Accept or reject with "
            "`constat rule accept <ID> --by <who>`.",
            "",
        ]

    return lines


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


def _render_rules(
    interpretation: Interpretation, view: CatalogueView | None = None
) -> list[str]:
    """Render the rules section, which always appears.

    An absent section would be read as "there are no rules here" — the one
    thing Constat must never imply (product rule 1). So the section is
    unconditional and its note carries the distinction between *no rules were
    identified* and *no rules exist*.
    """
    lines = ["## Business rules", ""]
    if view is not None:
        lines += _render_catalogue(view)

    if not interpretation.identified_rules:
        # Scoped to *this run*. Without the qualifier the note read as a
        # statement about the ticket, while the catalogue beside it held rules.
        note = (
            interpretation.note
            or "No rules were identified. That is not a statement that none exist."
        )
        lines += [f"**This run:** {note}", ""]
        return lines + _render_rejections(interpretation)

    lines += [
        f"**This run:** {len(interpretation.proposals)} rule(s) proposed by "
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
    view: CatalogueView | None = None,
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

    # Business view first, evidence under its own heading. The two must not be
    # conflated (product rule 8): one says what this means, the other says what
    # it rests on.
    if interpretation is not None:
        lines += _render_rules(interpretation, view)

    lines += ["## Evidence", ""]

    for finding in findings:
        entry = finding.repository
        lines.append(f"### {entry.alias}")
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
            lines.append(f"#### `{commit.sha[:12]}` {commit.subject}")
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


def known_rules(workspace: Workspace) -> tuple[KnownRule, ...]:
    """The catalogue as a provider sees it.

    Without this a reading has never been shown what exists, so every reading
    claims to be new and the second reading of a rule creates a duplicate —
    the failure CON-43 exists to prevent (D-050).
    """
    rows = workspace.execute(
        "SELECT id, name, statement FROM rule ORDER BY id"
    ).fetchall()
    rules = []
    for row in rows:
        anchors = workspace.execute(
            "SELECT path_glob FROM anchor WHERE rule_id = ? ORDER BY path_glob",
            (row["id"],),
        ).fetchall()
        rules.append(
            KnownRule(
                rule_id=row["id"],
                name=row["name"],
                statement=row["statement"],
                anchors=tuple(a["path_glob"] for a in anchors),
            )
        )
    return tuple(rules)


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
    run_id: int | None = None
    """Set only when a run was recorded — an export that found nothing to
    accept made no decision, and so is not an event."""


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
    payload = redact(reference, findings, known_rules(workspace))
    scan_findings = guard_release(payload, accepted=accept_scan_findings)

    accepted = bool(scan_findings)
    run_id = None
    if accepted:
        # Only recorded when there is something to record. An export that
        # found nothing made no decision, so inventing a run for it would put
        # an empty event in the audit trail.
        run_id = open_run(workspace, reference, "export_payload")
        _record_scan_override(
            workspace, reference, scan_findings, "scan_override_export", run_id
        )

    return ExportResult(
        payload=payload,
        scan_findings=scan_findings,
        accepted=accepted,
        run_id=run_id,
    )


@dataclass(frozen=True)
class SubmitResult:
    """What a submitted reply produced."""

    run_id: int
    stored: tuple[int, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    candidates: dict[int, tuple[int, ...]] = field(default_factory=dict)
    """Rule proposal id -> rules its anchors overlap, for readings that claimed
    to be new. A warning to the reviewer, never a decision (D-050)."""

    @property
    def stored_count(self) -> int:
        return len(self.stored)

    @property
    def possible_duplicates(self) -> int:
        return len(self.candidates)


def submit_reply(
    workspace: Workspace,
    reference: str,
    text: str,
    provider: str = "external",
    model: str | None = None,
    limits: ExcerptLimits = DEFAULT_LIMITS,
) -> SubmitResult:
    """Turn a reply produced outside Constat into stored rule proposals.

    The inbound half of D-045: `export_payload` hands the evidence out, this
    takes the reading back. Everything after the reply is the same as the
    provider path — the same `parse`, the same anchor grounding, the same
    append-only storage — because `parse` takes `(text, payload)` and does not
    care where the text came from (D-046).

    **The evidence is re-gathered rather than trusted.** Grounding has to be
    checked against what Constat can see now, not against whatever the caller
    claims it read; a caller who could supply the payload could also supply a
    payload that makes any anchor look grounded.

    **No credential gate here.** The payload is rebuilt locally to check
    grounding and is never transmitted, so there is nothing to refuse. The gate
    belongs on egress (D-047), and applying it to an inbound path would refuse
    a reply about evidence the user already, knowingly, exported.

    **Nothing is accepted.** Everything stored is pending a human decision
    (D-036, D-037); this fills the review queue and never writes to the
    catalogue.
    """
    findings = collect(workspace, reference, limits)
    payload = redact(reference, findings, known_rules(workspace))

    # Raises MalformedResponse for an unusable reply, rather than storing
    # nothing and letting that read as "no rules were identified" (D-046).
    result = parse(text, payload)

    run_id = open_run(workspace, reference, "submit_reply")
    proposals = RuleProposals(workspace)
    stored = []
    candidates: dict[int, tuple[int, ...]] = {}
    for proposal in result.proposals:
        proposal_id = proposals.record(
            run_id=run_id,
            proposal=proposal,
            provider=provider,
            model=model,
            revises_rule_id=proposal.revises_rule_id,
        )
        stored.append(proposal_id)

        if proposal.revises_rule_id is None:
            # The reading claims to be new. Anchor overlap cannot decide that
            # for it (D-050) — one file routinely implements several rules —
            # but a reviewer about to accept a duplicate needs to see the
            # candidates rather than discover them later.
            overlapping = proposals.candidates_for(proposal.anchors)
            if overlapping:
                candidates[proposal_id] = overlapping

    return SubmitResult(
        run_id=run_id,
        stored=tuple(stored),
        rejections=result.rejections,
        candidates=candidates,
    )


def _document_id(workspace: Workspace, reference: str) -> int:
    return workspace.execute(
        "SELECT d.id FROM document d JOIN ticket t ON t.id = d.ticket_id "
        "WHERE t.reference = ?",
        (reference,),
    ).fetchone()["id"]


def open_run(workspace: Workspace, reference: str, kind: str) -> int:
    """Record that a run happened, and return its identity.

    A gather writes one `operation` row per repository, so no operation row
    answers "which run produced this". A rule proposal is a reading of the
    evidence one run gathered (D-046), so it needs a single thing to point at.
    """
    document_id = _document_id(workspace, reference)
    with workspace.transaction() as ws:
        cursor = ws.execute(
            "INSERT INTO run (document_id, kind, started_at) VALUES (?, ?, ?)",
            (document_id, kind, utc_now()),
        )
        return int(cursor.lastrowid)


def _record_scan_override(
    workspace: Workspace,
    reference: str,
    scan_findings: tuple[SecretFinding, ...],
    kind: str,
    run_id: int,
) -> None:
    """Record that a human let credential findings through.

    Against the document rather than a repository: the decision was about the
    payload as a whole. Locations are kept so the override stays auditable; the
    matched text never is.
    """
    with workspace.transaction() as ws:
        ws.execute(
            "INSERT INTO operation "
            "(document_id, run_id, repository_id, kind, ran_at, summary, payload) "
            "VALUES (?, ?, NULL, ?, ?, ?, ?)",
            (
                _document_id(workspace, reference),
                run_id,
                kind,
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
    payload = redact(reference, findings, known_rules(workspace))

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

    document_id = _document_id(workspace, reference)
    run_id = open_run(workspace, reference, "gather_evidence")

    # Stored *before* the document is rendered, so the body shows the queue a
    # reviewer actually faces — including what this run just proposed. Storing
    # afterwards left the queue a run behind: a reader saw "1 rule proposed"
    # and an empty queue in the same document.
    #
    # Still a separate write from the body, because a reading has to survive
    # the next regeneration of the prose it appears in (D-048). Rendering it is
    # display; this is the record.
    proposals = RuleProposals(workspace)
    for proposal in interpretation.proposals:
        proposals.record(
            run_id=run_id,
            proposal=proposal,
            provider=interpretation.provider,
            model=interpretation.model,
            model_attested=interpretation.model_attested,
            revises_rule_id=proposal.revises_rule_id,
        )

    view = catalogue_view(workspace, reference, findings)
    body = render(reference, findings, interpretation, scan_section, view)

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
                "(document_id, run_id, repository_id, kind, ran_at, summary, payload) "
                "VALUES (?, ?, NULL, 'scan_override', ?, ?, ?)",
                (
                    document_id,
                    run_id,
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
                "(document_id, run_id, repository_id, kind, ran_at, summary) "
                "VALUES (?, ?, ?, 'gather_evidence', ?, ?)",
                (
                    document_id,
                    run_id,
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
        run_id=run_id,
    )
