"""Command-line entry point.

Thin by design: parse, validate, dispatch, render. No product logic lives here
(ARCHITECTURE.md section 2). Validation rules live in config.py; this module
only maps them onto argv and exit codes.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import build_request, build_snapshot_request
from .errors import InvalidInput, ProviderError, RepositoryError, WorkspaceError
from .evidence import collect_evidence, describe_commit
from .mapping import change_proposal, commit_record, state_proposal
from .store import Catalogue, Registry, TicketStore, Workspace, database_path
from .operations import gather
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
        help="declare and inspect business rules",
        description=(
            "Inspect the rule catalogue. Rules are generated and maintained by "
            "the AI interpretation pass (D-039); the add/behaviour/anchor "
            "commands are a bootstrap and test path for running without a "
            "provider configured, not the intended way to author rules."
        ),
    )
    rule_actions = rule.add_subparsers(dest="rule_action", metavar="ACTION")

    rule_add = rule_actions.add_parser("add", help="declare a rule")
    rule_add.add_argument("name", metavar="NAME")
    rule_add.add_argument("statement", metavar="STATEMENT",
                          help="the rule in business language")

    rule_behaviour = rule_actions.add_parser(
        "behaviour", help="add a behaviour to a rule"
    )
    rule_behaviour.add_argument("name", metavar="NAME")
    rule_behaviour.add_argument("description", metavar="TEXT")

    rule_anchor = rule_actions.add_parser(
        "anchor", help="say where a rule is implemented"
    )
    rule_anchor.add_argument("name", metavar="NAME")
    rule_anchor.add_argument("path_glob", metavar="GLOB")
    rule_anchor.add_argument("--repo", metavar="ALIAS",
                             help="restrict to one repository")

    rule_actions.add_parser("list", help="list declared rules")

    rule_show = rule_actions.add_parser("show", help="show one rule")
    rule_show.add_argument("name", metavar="NAME")

    rule_remove = rule_actions.add_parser("remove", help="withdraw a rule")
    rule_remove.add_argument("name", metavar="NAME")

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
        "--show", action="store_true", help="print the document body"
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

            if args.rule_action == "add":
                rule = catalogue.add_rule(args.name, args.statement)
                _print_rule(rule)
                print()
                print("Declared. Add behaviours and at least one anchor, or it")
                print("cannot be matched to any change.")
                return EXIT_OK

            if args.rule_action == "behaviour":
                _print_rule(catalogue.add_behaviour(args.name, args.description))
                return EXIT_OK

            if args.rule_action == "anchor":
                _print_rule(
                    catalogue.add_anchor(args.name, args.path_glob, args.repo)
                )
                return EXIT_OK

            if args.rule_action == "list":
                rules = catalogue.list()
                if not rules:
                    print("No rules declared. Declare one with `rule add`.")
                    print()
                    print("Rules are generated by the AI interpretation pass.")
                    print("Without a provider configured there are no rules —")
                    print("evidence is still collected, but no rule impact is")
                    print("reported. That is not the same as nothing changing.")
                    return EXIT_OK
                print(f"{len(rules)} rule(s):")
                for rule in rules:
                    unanchored = "" if rule.anchors else "  (no anchors)"
                    print(f"  {rule.name}: {rule.statement}{unanchored}")
                return EXIT_OK

            if args.rule_action == "show":
                rule = catalogue.find(args.name)
                if rule is None:
                    print(f"{PROG}: error: no rule {args.name!r}.", file=sys.stderr)
                    return EXIT_WORKSPACE
                _print_rule(rule)
                return EXIT_OK

            if args.rule_action == "remove":
                rule = catalogue.remove_rule(args.name)
                print(f"withdrawn: {rule.name}")
                print("Its behaviours and anchors are removed with it.")
                return EXIT_OK
    except WorkspaceError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_WORKSPACE

    parser.error(f"unknown rule action: {args.rule_action}")
    return EXIT_USAGE  # pragma: no cover


def _print_interpretation(interpretation) -> None:
    """Report the rules outcome of a run.

    Shared by `document` and `ticket add`, which both gather. A user who only
    ever runs `ticket add` would otherwise never be told that no rules were
    identified, and would reasonably read the silence as "there are none".
    """
    if interpretation is None:
        return

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
    try:
        with Workspace.open(args.workspace) as workspace:
            result = gather(workspace, args.reference)
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
                result = gather(workspace, entry.reference)
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
