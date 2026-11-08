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
from .errors import InvalidInput

PROG = "constat"
DESCRIPTION = "Turn software changes into evidence-backed, human-approved knowledge."
EPILOGUE = (
    "Nothing reads a repository yet: both commands validate their input and "
    "stop. See PROJECT_STATUS.md for what lands next."
)

EXIT_OK = 0
EXIT_USAGE = 2  # argparse's own convention for a usage error; reused for bad input.


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

    # Deliberately reports only what it was asked to do. Printing anything that
    # resembled findings would be unsupported certainty (PRODUCT_SPEC.md rule 1)
    # since no repository has been read.
    print(f"repository: {request.repo}")
    print(f"base:       {request.base}")
    print(f"target:     {request.target}")
    print()
    print("Input accepted. No repository has been read and no analysis performed:")
    print("reading the repository is Session 04, comparison is Session 05.")
    return EXIT_OK


def _run_snapshot(args: argparse.Namespace) -> int:
    try:
        request = build_snapshot_request(args.repo, args.rev)
    except InvalidInput as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    print(f"repository: {request.repo}")
    print(f"revision:   {request.rev}")
    print()
    print("Input accepted. No repository has been read and no state described:")
    print("reading the repository is Session 04.")
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
