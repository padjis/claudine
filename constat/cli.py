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
from .errors import InvalidInput, RepositoryError, WorkspaceError
from .evidence import collect_evidence, describe_commit
from .mapping import change_proposal, commit_record, state_proposal
from .store import Registry, Workspace, database_path
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
