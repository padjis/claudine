"""Tests for the CLI skeleton.

These assert observable behaviour — exit codes and output — rather than merely
that nothing raised. See CLAUDE.md, testing rules.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import constat
from helpers import git
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
    def test_valid_invocation_resolves_both_revisions(self, repo, capsys):
        assert (
            main(
                ["analyse", "--repo", str(repo), "--base", "v1.0.0", "--target", "main"]
            )
            == 0
        )

        out = capsys.readouterr().out
        assert str(repo.resolve()) in out
        assert "v1.0.0" in out and "main" in out
        # Both forms shown: the SHA for integrity, the symbolic name to read.
        assert git(repo, "rev-parse", "main") in out

    def test_output_does_not_claim_any_findings(self, repo, capsys):
        """Revisions are resolved but nothing is compared, so nothing may
        resemble a result (PRODUCT_SPEC.md rule 1)."""
        main(["analyse", "--repo", str(repo), "--base", "v1.0.0", "--target", "main"])

        out = capsys.readouterr().out.lower()
        assert "not classified" in out
        assert "not rendered as a" in out

    def test_missing_repository_exits_three_not_two(self, tmp_path, capsys):
        """A well-formed command against a missing repository is a different
        failure from a malformed command, and gets a different exit code."""
        code = main(
            [
                "analyse",
                "--repo",
                str(tmp_path / "nope"),
                "--base",
                "a",
                "--target",
                "b",
            ]
        )
        assert code == 3

        captured = capsys.readouterr()
        assert "no such path" in captured.err
        assert captured.out == ""

    def test_unresolvable_revision_exits_three(self, repo, capsys):
        code = main(
            ["analyse", "--repo", str(repo), "--base", "v1.0.0", "--target", "v99.0.0"]
        )
        assert code == 3
        assert "v99.0.0" in capsys.readouterr().err

    def test_subdirectory_reports_the_actual_repository_read(self, repo, capsys):
        """Scope was widened to the enclosing repository; the user must see it."""
        subdir = repo / "nested"
        subdir.mkdir()

        assert (
            main(
                ["analyse", "--repo", str(subdir), "--base", "v1.0.0", "--target", "main"]
            )
            == 0
        )

        out = capsys.readouterr().out
        assert str(repo.resolve()) in out
        assert "which is inside this repository" in out

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
    def test_valid_invocation_resolves_the_revision(self, repo, capsys):
        assert main(["snapshot", "--repo", str(repo), "--rev", "main"]) == 0

        out = capsys.readouterr().out
        assert str(repo.resolve()) in out
        assert git(repo, "rev-parse", "main") in out

    def test_output_does_not_claim_any_findings(self, repo, capsys):
        main(["snapshot", "--repo", str(repo), "--rev", "main"])
        out = capsys.readouterr().out.lower()
        assert "file inventory and commit metadata only" in out
        assert "nothing here describes" in out

    def test_detached_head_is_reported_as_such(self, repo, capsys):
        """Never present a detached HEAD as if it were a branch."""
        git(repo, "checkout", "--quiet", "--detach", "HEAD")
        assert main(["snapshot", "--repo", str(repo), "--rev", "HEAD"]) == 0
        assert "detached HEAD" in capsys.readouterr().out

    def test_directory_that_is_not_a_repository_exits_three(self, empty_dir, capsys):
        code = main(["snapshot", "--repo", str(empty_dir), "--rev", "main"])
        assert code == 3
        assert "not a Git repository" in capsys.readouterr().err

    def test_ambiguous_revision_is_refused_rather_than_guessed(self, repo, capsys):
        """A name matching both a branch and a tag must not be silently
        disambiguated — that is how the wrong thing gets documented."""
        git(repo, "branch", "collision")
        git(repo, "tag", "collision", "HEAD~1")

        code = main(["snapshot", "--repo", str(repo), "--rev", "collision"])
        assert code == 3
        assert "more than one ref" in capsys.readouterr().err

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
