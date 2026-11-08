"""Tests for the CLI skeleton.

These assert observable behaviour — exit codes and output — rather than merely
that nothing raised. See CLAUDE.md, testing rules.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import constat
from constat.cli import PROG, build_parser, main


def test_version_flag_exits_zero_and_prints_version(capsys):
    """`--version` is a successful exit, not an error, and names the version."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0

    out = capsys.readouterr().out
    assert constat.__version__ in out
    assert PROG in out


def test_version_matches_package_metadata():
    """Guard against the CLI version drifting from the installed metadata.

    pyproject.toml derives the version from constat.__version__, so these must
    agree. If they ever differ, the build is reporting something untrue.
    """
    from importlib.metadata import version

    assert version("constat") == constat.__version__


def test_help_flag_exits_zero_and_describes_the_tool(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0

    out = capsys.readouterr().out
    assert PROG in out
    assert "evidence-backed" in out


def test_no_arguments_prints_help_and_succeeds(capsys):
    """Running bare `constat` must explain itself, not silently do nothing."""
    assert main([]) == 0

    out = capsys.readouterr().out
    assert "usage" in out.lower()
    assert PROG in out


def test_unknown_argument_fails_with_usage_error(capsys):
    """Invalid input must fail loudly. Exit 2 is the argparse convention."""
    with pytest.raises(SystemExit) as exc:
        main(["--definitely-not-a-flag"])
    assert exc.value.code == 2

    err = capsys.readouterr().err
    assert "unrecognized arguments" in err


def test_parser_is_constructible_without_running():
    parser = build_parser()
    assert parser.prog == PROG


def test_module_is_runnable_without_installation():
    """`python -m constat` must work, so the CLI is testable before install."""
    result = subprocess.run(
        [sys.executable, "-m", "constat", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert constat.__version__ in result.stdout


def test_installed_console_script_runs():
    """The `constat` entry point declared in pyproject.toml actually works."""
    executable = f"{sys.prefix}/bin/constat"
    result = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert constat.__version__ in result.stdout
