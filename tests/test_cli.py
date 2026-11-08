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


class TestAnalyseCommand:
    def test_valid_invocation_succeeds_and_echoes_the_inputs(self, capsys):
        assert main(["analyse", "--repo", "/tmp/r", "--base", "a", "--target", "b"]) == 0

        out = capsys.readouterr().out
        assert "/tmp/r" in out
        assert "a" in out and "b" in out

    def test_output_does_not_claim_any_findings(self, capsys):
        """Nothing has read a repository, so nothing may resemble a result.

        Printing anything findings-shaped here would be unsupported certainty
        (PRODUCT_SPEC.md rule 1).
        """
        main(["analyse", "--repo", "/tmp/r", "--base", "a", "--target", "b"])

        out = capsys.readouterr().out
        assert "no analysis performed" in out.lower()

    @pytest.mark.parametrize("missing", ["--repo", "--base", "--target"])
    def test_each_option_is_required(self, missing, capsys):
        args = ["analyse", "--repo", "/tmp/r", "--base", "a", "--target", "b"]
        index = args.index(missing)
        del args[index : index + 2]

        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
        assert missing in capsys.readouterr().err

    def test_repo_has_no_implicit_current_directory_default(self, capsys):
        """A governance tool must never silently analyse whatever directory it
        happens to be standing in."""
        with pytest.raises(SystemExit) as exc:
            main(["analyse", "--base", "a", "--target", "b"])
        assert exc.value.code == 2
        assert "--repo" in capsys.readouterr().err

    def test_invalid_input_exits_two_with_a_message_on_stderr(self, capsys):
        assert main(["analyse", "--repo", "/tmp/r", "--base", "x", "--target", "x"]) == 2

        captured = capsys.readouterr()
        assert "nothing to compare" in captured.err
        assert captured.out == ""


class TestSnapshotCommand:
    def test_valid_invocation_succeeds_and_echoes_the_inputs(self, capsys):
        assert main(["snapshot", "--repo", "/tmp/r", "--rev", "main"]) == 0

        out = capsys.readouterr().out
        assert "/tmp/r" in out
        assert "main" in out

    def test_output_does_not_claim_any_findings(self, capsys):
        main(["snapshot", "--repo", "/tmp/r", "--rev", "main"])
        assert "no state described" in capsys.readouterr().out.lower()

    @pytest.mark.parametrize("missing", ["--repo", "--rev"])
    def test_each_option_is_required(self, missing, capsys):
        args = ["snapshot", "--repo", "/tmp/r", "--rev", "main"]
        index = args.index(missing)
        del args[index : index + 2]

        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
        assert missing in capsys.readouterr().err

    def test_invalid_input_exits_two_with_a_message_on_stderr(self, capsys):
        assert main(["snapshot", "--repo", "/tmp/r", "--rev", "  "]) == 2
        assert "--rev must not be empty" in capsys.readouterr().err


def test_both_commands_are_listed_in_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])

    out = capsys.readouterr().out
    assert "analyse" in out
    assert "snapshot" in out


def test_unknown_subcommand_is_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["frobnicate"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


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
