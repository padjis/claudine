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
from .errors import InvalidInput, RepositoryError
from .git import discover_repository, resolve_revision

PROG = "constat"
DESCRIPTION = "Turn software changes into evidence-backed, human-approved knowledge."
EPILOGUE = (
    "Both commands read the repository and resolve revisions, then stop: "
    "nothing is compared or described yet. See PROJECT_STATUS.md."
)

EXIT_OK = 0
EXIT_USAGE = 2  # argparse's own convention for a usage error; reused for bad input.
EXIT_REPOSITORY = 3  # the input was fine; the repository or revision was not.


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

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

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

    return parser


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
    except RepositoryError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_REPOSITORY

    _describe_repository(repo)
    print(f"base:       {base.symbolic} -> {base.sha}")
    print(f"target:     {target.symbolic} -> {target.sha}")
    print()
    # Reports only what was actually established. Anything resembling findings
    # would be unsupported certainty (PRODUCT_SPEC.md rule 1): no diff has run.
    print("Revisions resolved. No comparison performed yet: that is CON-05.")
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
    except RepositoryError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_REPOSITORY

    _describe_repository(repo)
    print(f"revision:   {revision.symbolic} -> {revision.sha}")
    print()
    print("Revision resolved. No state described yet: that is CON-05 onwards.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # With no subcommand, explain rather than doing nothing silently.
    if args.command is None:
        parser.print_help()
        return EXIT_OK

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
