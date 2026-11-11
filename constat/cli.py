"""Command-line entry point.

Thin by design: parse, validate, dispatch, render. No product logic lives here
(ARCHITECTURE.md section 2). Validation rules live in config.py; this module
only maps them onto argv and exit codes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import build_request, build_snapshot_request
from .errors import InvalidInput, ProviderError, RepositoryError, WorkspaceError
from .evidence import collect_evidence, describe_commit
from .mapping import change_proposal, commit_record, state_proposal
from .store import (
    Catalogue,
    Registry,
    RuleProposals,
    TicketStore,
    Workspace,
    database_path,
)
from .ai import as_dict as payload_as_dict
from .operations import export_payload, gather, submit_reply
from .tickets import TicketStatus, find_ticket_commits
from .git import (
    compare_revisions,
    discover_repository,
    resolve_revision,
    summarise_state,
)

PROG = "constat"
DESCRIPTION = "Turn software changes into evidence-backed, human-approved knowledge."
EPILOGUE = (
    "Reports file changes, commits and bounded evidence. Nothing is classified "
    "or interpreted yet, and no report is rendered. See PROJECT_STATUS.md."
)

EXIT_OK = 0
EXIT_USAGE = 2  # argparse's own convention for a usage error; reused for bad input.
EXIT_REPOSITORY = 3  # the input was fine; the repository or revision was not.
EXIT_WORKSPACE = 4  # Constat's own stored state could not be opened or created.
EXIT_PROVIDER = 5  # the interpretation layer was misconfigured; nothing else was.


def _describe_repository(repo) -> None:
    print(f"repository: {repo.root}")
    if repo.given != repo.root:
        # Git widens a subdirectory to its enclosing repository. Say so, rather
        # than letting the user believe only the subtree was read.
        print(f"  (given {repo.given}, which is inside this repository)")
    print(f"branch:     {repo.branch or '(detached HEAD)'}")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser.

    Separated from main() so tests can inspect the parser without running it.
    """
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=DESCRIPTION,
        epilog=EPILOGUE,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROG} {__version__}",
        help="show the version and exit",
    )

    parser.add_argument(
        "--workspace",
        metavar="PATH",
        help=(
            "workspace directory (default: $CONSTAT_HOME, else ~/.constat). "
            "The workspace in use is always reported, never assumed silently."
        ),
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    rule = subparsers.add_parser(
        "rule",
        help="inspect the business rules in the catalogue",
        description=(
            "Inspect the rule catalogue. Read-only: a rule enters only as an "
            "accepted rule proposal and can never be removed (D-048). There is "
            "no human-authored path, and supersession replaces deletion."
        ),
    )
    rule_actions = rule.add_subparsers(dest="rule_action", metavar="ACTION")

    rule_actions.add_parser("list", help="list rules in the catalogue")

    rule_show = rule_actions.add_parser("show", help="show one rule")
    rule_show.add_argument("name", metavar="NAME")

    rule_submit = rule_actions.add_parser(
        "submit",
        help="turn a reply produced outside Constat into rule proposals",
        description=(
            "Parse a reply, check every anchor against the ticket's evidence, "
            "and store what survives as rule proposals awaiting a human "
            "decision. Nothing is accepted here: this fills the review queue "
            "and never writes to the catalogue."
        ),
    )
    rule_submit.add_argument("reference", metavar="REF")
    rule_submit.add_argument(
        "--from",
        dest="source",
        metavar="PATH",
        default="-",
        help="file to read the reply from (default: - for stdin)",
    )
    rule_submit.add_argument(
        "--provider",
        default="external",
        help=(
            "what produced the reply. Self-reported and unverified (D-045): "
            "recorded so a reviewer knows what to weigh, never as an observed "
            "fact."
        ),
    )
    rule_submit.add_argument(
        "--model", default=None, help="model name, also self-reported"
    )

    rule_proposals = rule_actions.add_parser(
        "proposals", help="list the rule proposals awaiting a decision"
    )
    rule_proposals.add_argument("reference", metavar="REF")
    rule_proposals.add_argument(
        "--all",
        action="store_true",
        help="include rule proposals already decided",
    )

    document = subparsers.add_parser(
        "document",
        help="gather evidence for a ticket across the registered repositories",
        description=(
            "Run the gathering operation for a ticket: resolve its commits in "
            "every registered repository, collect bounded evidence, and expand "
            "the ticket's document. The document is a draft and carries no "
            "authority until a human approves a version of it."
        ),
    )
    document.add_argument("reference", metavar="REF")
    document.add_argument(
        "--accept-scan-findings",
        action="store_true",
        help=(
            "send the evidence to the AI provider even though the credential "
            "scan found something. Recorded in the document as a human "
            "decision; applies to this run only."
        ),
    )
    document.add_argument(
        "--show", action="store_true", help="print the document body"
    )
    document.add_argument(
        "--payload",
        action="store_true",
        help=(
            "print the redacted evidence payload as JSON, for a model outside "
            "Constat to read. Identity never crosses this boundary (D-040), "
            "and the credential scan refuses unconditionally here — unlike a "
            "local run, an export has left by the time it has printed."
        ),
    )

    ticket = subparsers.add_parser(
        "ticket",
        help="manage tickets and their documents",
        description=(
            "A ticket owns exactly one living document. Constat expects a "
            "ticket's work to be already merged onto an integration or "
            "release branch, but not yet in mainline."
        ),
    )
    ticket_actions = ticket.add_subparsers(dest="ticket_action", metavar="ACTION")

    ticket_add = ticket_actions.add_parser("add", help="open a ticket")
    ticket_add.add_argument("reference", metavar="REF", help="e.g. 622, ABC-123")
    ticket_add.add_argument(
        "--accept-scan-findings",
        action="store_true",
        help=(
            "as on `document`: send the evidence despite credential-scan "
            "findings. `ticket add` gathers, so it can be refused too."
        ),
    )

    ticket_actions.add_parser("list", help="list tickets")

    ticket_show = ticket_actions.add_parser(
        "show", help="show a ticket and where its work was found"
    )
    ticket_show.add_argument("reference", metavar="REF")

    repo = subparsers.add_parser(
        "repo",
        help="manage the registered repositories",
        description="Add, list and remove the repositories in the workspace.",
    )
    repo_actions = repo.add_subparsers(dest="repo_action", metavar="ACTION")

    repo_add = repo_actions.add_parser(
        "add", help="register a local repository"
    )
    repo_add.add_argument("path", metavar="PATH", help="path to a Git repository")
    repo_add.add_argument(
        "--name", metavar="ALIAS", help="alias (default: the directory name)"
    )
    repo_add.add_argument(
        "--default-branch",
        metavar="BRANCH",
        help=(
            "the branch every comparison is measured against. Resolved from "
            "refs/remotes/origin/HEAD when not given; never guessed from "
            "whichever branch happens to be checked out."
        ),
    )

    repo_actions.add_parser("list", help="list registered repositories")

    repo_remove = repo_actions.add_parser(
        "remove", help="unregister a repository (the repository itself is untouched)"
    )
    repo_remove.add_argument("name", metavar="ALIAS")

    subparsers.add_parser(
        "init",
        help="create a workspace",
        description=(
            "Create the workspace that holds registered repositories, tickets "
            "and the immutable record of approvals. Refuses to overwrite an "
            "existing workspace."
        ),
    )

    analyse = subparsers.add_parser(
        "analyse",
        help="examine a revision range in one repository",
        description=(
            "Examine what changed between two revisions of one repository. "
            "All three options are required: there are no defaults for inputs "
            "this important."
        ),
    )
    analyse.add_argument(
        "--repo",
        required=True,
        metavar="PATH",
        help="path to the local Git repository (required; no default)",
    )
    analyse.add_argument(
        "--base",
        required=True,
        metavar="REV",
        help="revision representing the already-known state (tag, branch or SHA)",
    )
    analyse.add_argument(
        "--target",
        required=True,
        metavar="REV",
        help="revision representing the new state to document",
    )
    analyse.add_argument(
        "--json",
        action="store_true",
        help="emit the structured proposal instead of the human summary",
    )

    snapshot = subparsers.add_parser(
        "snapshot",
        help="document the current state of one revision, such as main",
        description=(
            "Describe what a single revision does now, rather than what changed. "
            "This is what an initial baseline is made from, and what later drift "
            "is measured against. Both options are required."
        ),
    )
    snapshot.add_argument(
        "--repo",
        required=True,
        metavar="PATH",
        help="path to the local Git repository (required; no default)",
    )
    snapshot.add_argument(
        "--rev",
        required=True,
        metavar="REV",
        help="revision to describe, typically main or master (required; no default)",
    )
    snapshot.add_argument(
        "--json",
        action="store_true",
        help="emit the structured proposal instead of the human summary",
    )

    return parser


def _run_init(args: argparse.Namespace) -> int:
    try:
        with Workspace.create(args.workspace) as workspace:
            path = workspace.path
            version = workspace.schema_version
    except WorkspaceError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_WORKSPACE

    print(f"workspace:  {path}")
    print(f"schema:     version {version}")
    print()
    print("Created. It holds registered repositories, tickets and documents.")
    print("Nothing is registered yet: `repo add` arrives with CON-32.")
    return EXIT_OK


def _report_submission(result) -> int:
    """Report a submission: what was stored, and what was discarded.

    Discards are printed first. A reader shown only the kept count has been
    told a shorter truth than the one that happened (D-046).
    """
    if result.rejections:
        print(f"{len(result.rejections)} discarded as ungrounded or malformed:")
        for rejection in result.rejections:
            print(f"    {rejection.describe()}")

    print(f"{result.stored_count} rule proposal(s) stored, run {result.run_id}")
    if result.stored_count:
        print()
        print("None of them is accepted. They await a human decision —")
        print("see them with `constat rule proposals <REF>`.")
    return EXIT_OK


def _report_proposals(proposals, reference: str, include_decided: bool) -> int:
    stored = (
        proposals.for_ticket(reference)
        if include_decided
        else proposals.undecided(reference)
    )
    if not stored:
        scope = "rule proposals" if include_decided else "undecided rule proposals"
        print(f"No {scope} for {reference}.")
        print()
        print("That is not a statement that this ticket has no rules —")
        print("nothing has read its evidence yet.")
        return EXIT_OK

    print(f"{len(stored)} rule proposal(s) for {reference}:")
    for item in stored:
        state = item.decision or "awaiting a decision"
        reader = item.provider + (f" ({item.model})" if item.model else "")
        print(f"  [{item.id}] {item.proposal.name} — {state}")
        print(f"      {item.proposal.statement}")
        print(f"      read by {reader} (self-reported), run {item.run_id}")
        if item.claims_to_revise:
            print(f"      claims to revise rule {item.revises_rule_id}")
    return EXIT_OK


def _print_rule(rule) -> None:
    print(f"{rule.name}")
    print(f"  statement:  {rule.statement}")
    if rule.behaviours:
        print(f"  behaviours ({len(rule.behaviours)}):")
        for behaviour in rule.behaviours:
            print(f"    - {behaviour.description}")
    else:
        print("  behaviours: none declared yet")
    if rule.anchors:
        print(f"  anchors ({len(rule.anchors)}):")
        for anchor in rule.anchors:
            scope = anchor.repository_alias or "any repository"
            print(f"    - {anchor.path_glob}  [{scope}]")
    else:
        print("  anchors: none — this rule can never be matched to a change")


def _run_rule(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.rule_action is None:
        parser.parse_args(["rule", "--help"])
        return EXIT_USAGE

    try:
        with Workspace.open(args.workspace) as workspace:
            catalogue = Catalogue(workspace)

            if args.rule_action == "list":
                rules = catalogue.list()
                if not rules:
                    print("No rules in the catalogue.")
                    print()
                    print("A rule enters only as an accepted rule proposal")
                    print("(D-048), and nothing generates one until a provider")
                    print("or host is wired up. Evidence is still collected; no")
                    print("rule impact is reported. That is not the same as")
                    print("nothing changing.")
                    return EXIT_OK
                print(f"{len(rules)} rule(s):")
                for rule in rules:
                    unanchored = "" if rule.anchors else "  (no anchors)"
                    print(f"  {rule.name}: {rule.statement}{unanchored}")
                return EXIT_OK

            if args.rule_action == "submit":
                text = (
                    sys.stdin.read()
                    if args.source == "-"
                    else Path(args.source).read_text()
                )
                result = submit_reply(
                    workspace,
                    args.reference,
                    text,
                    provider=args.provider,
                    model=args.model,
                )
                return _report_submission(result)

            if args.rule_action == "proposals":
                return _report_proposals(
                    RuleProposals(workspace), args.reference, args.all
                )

            if args.rule_action == "show":
                rule = catalogue.find(args.name)
                if rule is None:
                    print(f"{PROG}: error: no rule {args.name!r}.", file=sys.stderr)
                    return EXIT_WORKSPACE
                _print_rule(rule)
                return EXIT_OK

    except ProviderError as exc:
        # A reply that cannot be parsed is a provider fault, not a workspace
        # one, and must never read as "no rules were identified" (D-046).
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_PROVIDER
    except RepositoryError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_REPOSITORY
    except WorkspaceError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_WORKSPACE

    parser.error(f"unknown rule action: {args.rule_action}")
    return EXIT_USAGE  # pragma: no cover


def _run_export(args: argparse.Namespace) -> int:
    """Print the redacted payload for something outside Constat to read.

    Everything about this path assumes the output leaves: the credential gate
    is unconditional, and the warning goes to stderr so stdout stays a clean
    JSON document a pipe can consume.
    """
    try:
        with Workspace.open(args.workspace) as workspace:
            result = export_payload(
                workspace,
                args.reference,
                accept_scan_findings=args.accept_scan_findings,
            )
    except WorkspaceError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_WORKSPACE
    except ProviderError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_PROVIDER
    except RepositoryError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_REPOSITORY

    print(json.dumps(payload_as_dict(result.payload), indent=2, default=str))

    if result.accepted:
        print(
            f"{PROG}: warning: {len(result.scan_findings)} credential-scan "
            "finding(s) were accepted and are present in this payload; "
            "recorded in the document as a human decision",
            file=sys.stderr,
        )
    return EXIT_OK


def _print_scan(result) -> None:
    """Report the credential scan.

    The clean case is printed too. A scan that only speaks when it fails
    cannot be told apart from a scan that never ran.
    """
    findings = result.scan_findings
    if not findings:
        print("  credential scan: no findings (known formats only)")
        return

    print(f"  credential scan: {len(findings)} possible credential(s) found")
    for finding in findings:
        print(f"    {finding.describe()}")
    if result.scan_accepted:
        print("  accepted via --accept-scan-findings and recorded in the document")
    else:
        print("  nothing was sent — no AI provider is configured")


def _print_interpretation(interpretation) -> None:
    """Report the rules outcome of a run.

    Shared by `document` and `ticket add`, which both gather. A user who only
    ever runs `ticket add` would otherwise never be told that no rules were
    identified, and would reasonably read the silence as "there are none".
    """
    if interpretation is None:
        return

    if interpretation.rejections:
        # Printed before the kept count: a reviewer who sees only the kept
        # number has been told a shorter truth than the one that happened.
        print(
            f"  {len(interpretation.rejections)} proposal(s) discarded as "
            "ungrounded or malformed"
        )

    if interpretation.identified_rules:
        print(
            f"  {len(interpretation.proposals)} rule(s) proposed by "
            f"{interpretation.describe()} — proposals, not findings"
        )
    elif interpretation.ran:
        print(
            f"  no rules identified by {interpretation.describe()} — "
            "not a finding that none exist"
        )
    else:
        print("  no rules identified — no AI provider is configured")
        print("  (that is a statement about configuration, not about the code)")


def _run_document(args: argparse.Namespace) -> int:
    if args.payload and args.show:
        print(
            f"{PROG}: error: --payload and --show print different things; "
            "pick one",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if args.payload:
        return _run_export(args)

    try:
        with Workspace.open(args.workspace) as workspace:
            result = gather(
                workspace,
                args.reference,
                accept_scan_findings=args.accept_scan_findings,
            )
    except WorkspaceError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_WORKSPACE
    except ProviderError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_PROVIDER
    except RepositoryError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_REPOSITORY

    if args.show:
        print(result.body)
        return EXIT_OK

    print(f"ticket {result.reference}: document updated")
    print(
        f"  {result.repositories_searched} repository(ies) searched, "
        f"{result.repositories_contributing} contributed evidence"
    )
    for finding in result.findings:
        detail = finding.error or f"{len(finding.commits)} commit(s)"
        print(f"    {finding.repository.alias}: {finding.status.value} — {detail}")

    _print_scan(result)
    _print_interpretation(result.interpretation)
    print()
    print("Use --show to print the document. It is a draft: nothing here is")
    print("approved, and approval is a separate, explicit step.")
    return EXIT_OK


def _run_ticket(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.ticket_action is None:
        parser.parse_args(["ticket", "--help"])
        return EXIT_USAGE

    try:
        with Workspace.open(args.workspace) as workspace:
            tickets = TicketStore(workspace)

            if args.ticket_action == "add":
                entry = tickets.add(args.reference)
                print(f"opened ticket: {entry.reference}")

                # Fill the document immediately. Opening a ticket and then
                # requiring a second command to populate it would leave an
                # empty document lying around that says nothing.
                result = gather(
                    workspace,
                    entry.reference,
                    accept_scan_findings=args.accept_scan_findings,
                )
                print(
                    f"  {result.repositories_searched} repository(ies) searched, "
                    f"{result.repositories_contributing} contributed evidence"
                )
                for finding in result.findings:
                    detail = finding.error or f"{len(finding.commits)} commit(s)"
                    print(
                        f"    {finding.repository.alias}: "
                        f"{finding.status.value} — {detail}"
                    )
                _print_scan(result)
                _print_interpretation(result.interpretation)
                print()
                print(f"Document written. See it with `constat document "
                      f"{entry.reference} --show`.")
                print("It is a draft and carries no authority until approved.")
                return EXIT_OK

            if args.ticket_action == "list":
                entries = tickets.list()
                if not entries:
                    print("No tickets. Open one with `ticket add`.")
                    return EXIT_OK
                print(f"{len(entries)} ticket(s):")
                for entry in entries:
                    print(f"  {entry.reference}")
                return EXIT_OK

            if args.ticket_action == "show":
                entry = tickets.find(args.reference)
                if entry is None:
                    print(
                        f"{PROG}: error: no ticket {args.reference!r}.",
                        file=sys.stderr,
                    )
                    return EXIT_WORKSPACE
                document = tickets.document(entry.reference)
                operations = workspace.execute(
                    "SELECT o.kind, o.ran_at, o.summary, r.alias "
                    "FROM operation o "
                    "JOIN document d ON d.id = o.document_id "
                    "JOIN ticket tk ON tk.id = d.ticket_id "
                    "LEFT JOIN repository r ON r.id = o.repository_id "
                    "WHERE tk.reference = ? ORDER BY o.ran_at, r.alias",
                    (entry.reference,),
                ).fetchall()

                # Stored state only. Re-searching here would make `show`
                # disagree with the document it is describing.
                print(f"ticket:    {entry.reference}")
                print(f"opened:    {entry.created_at.isoformat()}")
                print(f"document:  {'empty' if document.is_empty else 'filled'}"
                      f", updated {document.updated_at.isoformat()}")
                print(f"operations: {len(operations)} recorded")
                for row in operations:
                    alias = row["alias"] or "(no repository)"
                    print(f"    {row['ran_at']}  {alias}  {row['summary']}")
                print()
                print(f"Run `constat document {entry.reference} --show` for the "
                      "document itself,")
                print(f"or `constat document {entry.reference}` to gather again.")
                return EXIT_OK
    except ProviderError as exc:
        # `ticket add` gathers, so it can hit a provider misconfiguration too.
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_PROVIDER
    except WorkspaceError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_WORKSPACE

    parser.error(f"unknown ticket action: {args.ticket_action}")
    return EXIT_USAGE  # pragma: no cover


def _run_repo(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.repo_action is None:
        parser.parse_args(["repo", "--help"])
        return EXIT_USAGE

    try:
        with Workspace.open(args.workspace) as workspace:
            registry = Registry(workspace)

            if args.repo_action == "add":
                entry = registry.add(args.path, args.name, args.default_branch)
                print(f"registered: {entry.alias}")
                print(f"  source:         {entry.source}")
                print(f"  identity:       {entry.identity}")
                print(f"  default branch: {entry.default_branch}")
                print()
                print("Identity is the root commit, so this stays the same")
                print("repository if the checkout moves or is re-cloned.")
                return EXIT_OK

            if args.repo_action == "list":
                entries = registry.list()
                if not entries:
                    print("No repositories registered. Add one with `repo add`.")
                    return EXIT_OK
                print(f"{len(entries)} repository(ies):")
                for entry in entries:
                    print(f"  {entry.alias}")
                    print(f"    source:         {entry.source}")
                    print(f"    default branch: {entry.default_branch}")
                    print(f"    identity:       {entry.identity[:12]}")
                return EXIT_OK

            if args.repo_action == "remove":
                entry = registry.remove(args.name)
                print(f"unregistered: {entry.alias} ({entry.source})")
                print("The repository on disk is untouched; Constat only reads.")
                return EXIT_OK
    except WorkspaceError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_WORKSPACE
    except RepositoryError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_REPOSITORY

    parser.error(f"unknown repo action: {args.repo_action}")
    return EXIT_USAGE  # pragma: no cover


def _run_analyse(args: argparse.Namespace) -> int:
    try:
        request = build_request(args.repo, args.base, args.target)
    except InvalidInput as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        repo = discover_repository(request.repo)
        base = resolve_revision(repo, request.base)
        target = resolve_revision(repo, request.target)
        summary = compare_revisions(repo, base, target)
        bundle = collect_evidence(repo, summary)
        proposal = change_proposal(repo, summary, bundle)
    except RepositoryError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_REPOSITORY

    if args.json:
        print(proposal.model_dump_json(indent=2))
        return EXIT_OK

    _describe_repository(repo)
    print(f"base:       {base.symbolic} -> {base.sha}")
    print(f"target:     {target.symbolic} -> {target.sha}")

    # Always stated, because the comparison did not necessarily start at base
    # (D-021) and the summary cannot be verified without knowing where it did.
    if summary.base_is_merge_base:
        print("compared:   from base (base is an ancestor of target)")
    else:
        print(f"compared:   from merge base {summary.merge_base}")
        print("            base and target have diverged; changes made only on")
        print("            base are excluded, not reported as deletions")

    print()
    if summary.is_empty:
        print("No file changes in this range.")
    else:
        print(f"{len(summary.changes)} changed file(s):")
        for change in summary.changes:
            if change.previous_path is not None:
                score = f" ({change.similarity}% similar)" if change.similarity else ""
                print(
                    f"  {change.change_type.name:<12} {change.previous_path}"
                    f" -> {change.path}{score}"
                )
            else:
                print(f"  {change.change_type.name:<12} {change.path}")

    print()
    print(f"{bundle.commit_count} commit(s) in this range:")
    for commit in bundle.commits:
        merge = " [merge]" if commit.is_merge else ""
        date = commit.authored_at.date().isoformat()
        print(f"  {commit.short_sha}  {date}  {commit.author_name}{merge}")
        print(f"              {commit.subject}")

    print()
    print("Evidence:")
    print(f"  {bundle.completeness_note()}")
    truncated = [e for e in bundle.excerpts if e.truncated and not e.is_binary]
    if truncated:
        print(f"  {len(truncated)} file(s) truncated:")
        for excerpt in sorted(truncated, key=lambda e: -e.omitted_lines)[:5]:
            kept = len(excerpt.text.splitlines())
            print(f"    {kept} of {excerpt.total_lines} lines — {excerpt.path}")

    print()
    # Says only what was established. Anything interpretive would be
    # unsupported certainty (PRODUCT_SPEC.md rule 1): nothing has been
    # classified and no report has been rendered.
    print(f"proposal:   {proposal.proposal_id}")
    print(f"selection:  {proposal.selection_key[:16]}…")
    print()
    print("Evidence collected but not classified (CON-08) and not rendered as a")
    print("report (CON-09). Each excerpt records the command that regenerates it.")
    print("Use --json for the structured proposal.")
    return EXIT_OK


def _run_snapshot(args: argparse.Namespace) -> int:
    try:
        request = build_snapshot_request(args.repo, args.rev)
    except InvalidInput as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        repo = discover_repository(request.repo)
        revision = resolve_revision(repo, request.rev)
        state = summarise_state(repo, revision)
        commit = describe_commit(repo, revision)
        proposal = state_proposal(repo, state, commit_record(commit))
    except RepositoryError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_REPOSITORY

    if args.json:
        print(proposal.model_dump_json(indent=2))
        return EXIT_OK

    _describe_repository(repo)
    print(f"revision:   {revision.symbolic} -> {revision.sha}")
    print(f"authored:   {commit.authored_at.date().isoformat()} by {commit.author_name}")
    print(f"subject:    {commit.subject}")
    print()
    print(f"{state.file_count} file(s) present at this revision.")
    print()
    print("File inventory and commit metadata only. Nothing here describes")
    print("behaviour yet: that needs interpretation (CON-09 onwards).")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # With no subcommand, explain rather than doing nothing silently.
    if args.command is None:
        parser.print_help()
        return EXIT_OK

    if args.command == "init":
        return _run_init(args)

    if args.command == "repo":
        return _run_repo(args, parser)

    if args.command == "ticket":
        return _run_ticket(args, parser)

    if args.command == "document":
        return _run_document(args)

    if args.command == "rule":
        return _run_rule(args, parser)

    if args.command == "analyse":
        return _run_analyse(args)

    if args.command == "snapshot":
        return _run_snapshot(args)

    # Unreachable while argparse validates the choice, but an explicit failure
    # beats falling off the end and returning None.
    parser.error(f"unknown command: {args.command}")
    return EXIT_USAGE  # pragma: no cover - parser.error raises SystemExit


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    sys.exit(main())
