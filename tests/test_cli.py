"""Tests for the CLI skeleton.

These assert observable behaviour — exit codes and output — rather than merely
that nothing raised. See CLAUDE.md, testing rules.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import constat
from constat.store import SCHEMA_VERSION
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


class TestJsonOutput:
    def test_analyse_json_is_a_valid_proposal(self, repo, capsys):
        from constat.models import Proposal

        assert main(
            ["analyse", "--repo", str(repo), "--base", "v1.0.0", "--target", "main", "--json"]
        ) == 0

        proposal = Proposal.model_validate_json(capsys.readouterr().out)
        assert proposal.is_change is True
        assert proposal.schema_version == 1

    def test_snapshot_json_is_a_state_proposal(self, repo, capsys):
        from constat.models import Proposal, SelectionKind

        assert main(["snapshot", "--repo", str(repo), "--rev", "main", "--json"]) == 0

        proposal = Proposal.model_validate_json(capsys.readouterr().out)
        assert proposal.selection.kind is SelectionKind.STATE
        assert proposal.changes == ()

    def test_json_output_carries_no_prose(self, repo, capsys):
        """Machine output must be parseable without stripping commentary."""
        import json

        main(["analyse", "--repo", str(repo), "--base", "v1.0.0", "--target", "main", "--json"])
        json.loads(capsys.readouterr().out)  # raises if anything else was printed

    def test_repeated_json_runs_differ_only_in_identity(self, repo, capsys):
        """Append-only history, idempotent lookup (D-025)."""
        from constat.models import Proposal

        args = ["analyse", "--repo", str(repo), "--base", "v1.0.0", "--target", "main", "--json"]
        main(args)
        first = Proposal.model_validate_json(capsys.readouterr().out)
        main(args)
        second = Proposal.model_validate_json(capsys.readouterr().out)

        assert first.proposal_id != second.proposal_id
        assert first.selection_key == second.selection_key
        assert first.changes == second.changes
        assert first.evidence == second.evidence


class TestInitCommand:
    def test_init_creates_a_workspace(self, tmp_path, capsys):
        assert main(["--workspace", str(tmp_path / "ws"), "init"]) == 0

        out = capsys.readouterr().out
        assert "workspace:" in out
        assert f"schema:     version {SCHEMA_VERSION}" in out
        assert (tmp_path / "ws" / "workspace.db").exists()

    def test_init_reports_the_workspace_it_used(self, tmp_path, capsys):
        """A default location is acceptable; an undisclosed one is not."""
        target = tmp_path / "ws"
        main(["--workspace", str(target), "init"])
        assert str(target) in capsys.readouterr().out

    def test_init_refuses_to_overwrite_and_exits_four(self, tmp_path, capsys):
        """Stored decisions must survive a careless second init."""
        target = str(tmp_path / "ws")
        main(["--workspace", target, "init"])
        capsys.readouterr()

        assert main(["--workspace", target, "init"]) == 4
        captured = capsys.readouterr()
        assert "already exists" in captured.err
        assert captured.out == ""

    def test_workspace_errors_use_their_own_exit_code(self, tmp_path, capsys):
        """2 is malformed input, 3 is the repository, 4 is our own state."""
        target = str(tmp_path / "ws")
        main(["--workspace", target, "init"])
        capsys.readouterr()
        assert main(["--workspace", target, "init"]) == 4


class TestRepoCommands:
    def _ws(self, tmp_path):
        target = str(tmp_path / "ws")
        main(["--workspace", target, "init"])
        return target

    def _clone(self, tmp_path, repo):
        target = tmp_path / "cloned"
        git(tmp_path, "clone", "--quiet", str(repo), str(target))
        return target

    def test_add_then_list(self, tmp_path, repo, capsys):
        ws = self._ws(tmp_path)
        cloned = self._clone(tmp_path, repo)
        capsys.readouterr()

        assert main(["--workspace", ws, "repo", "add", str(cloned), "--name", "s"]) == 0
        assert main(["--workspace", ws, "repo", "list"]) == 0

        out = capsys.readouterr().out
        assert "s" in out
        assert "main" in out

    def test_list_on_an_empty_workspace_says_so(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "repo", "list"]) == 0
        assert "No repositories registered" in capsys.readouterr().out

    def test_duplicate_exits_four_with_the_existing_alias(self, tmp_path, repo, capsys):
        ws = self._ws(tmp_path)
        cloned = self._clone(tmp_path, repo)
        main(["--workspace", ws, "repo", "add", str(cloned), "--name", "first"])
        capsys.readouterr()

        assert main(["--workspace", ws, "repo", "add", str(cloned), "--name", "second"]) == 4
        assert "first" in capsys.readouterr().err

    def test_unresolvable_default_branch_exits_three(self, tmp_path, repo, capsys):
        """A repository problem, not a workspace problem."""
        ws = self._ws(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "repo", "add", str(repo), "--name", "x"]) == 3
        assert "--default-branch" in capsys.readouterr().err

    def test_explicit_default_branch_is_accepted(self, tmp_path, repo, capsys):
        ws = self._ws(tmp_path)
        capsys.readouterr()

        code = main(
            ["--workspace", ws, "repo", "add", str(repo), "--name", "x",
             "--default-branch", "main"]
        )
        assert code == 0
        assert "default branch: main" in capsys.readouterr().out

    def test_remove_reports_the_repository_is_untouched(self, tmp_path, repo, capsys):
        ws = self._ws(tmp_path)
        cloned = self._clone(tmp_path, repo)
        main(["--workspace", ws, "repo", "add", str(cloned), "--name", "s"])
        capsys.readouterr()

        assert main(["--workspace", ws, "repo", "remove", "s"]) == 0
        assert "untouched" in capsys.readouterr().out
        assert cloned.exists()

    def test_removing_an_unknown_alias_exits_four(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "repo", "remove", "nope"]) == 4
        assert "nope" in capsys.readouterr().err

    def test_repo_without_an_action_shows_help(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        capsys.readouterr()

        with pytest.raises(SystemExit):
            main(["--workspace", ws, "repo"])
        assert "add" in capsys.readouterr().out


class TestTicketCommands:
    def _ws(self, tmp_path):
        target = str(tmp_path / "ws")
        main(["--workspace", target, "init"])
        return target

    def test_add_opens_the_ticket_and_fills_its_document(self, tmp_path, capsys):
        """Opening a ticket writes its document immediately; an empty one
        would say nothing and require a second command to be useful."""
        ws = self._ws(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "ticket", "add", "622"]) == 0
        out = capsys.readouterr().out
        assert "opened ticket: 622" in out
        assert "Document written" in out

        capsys.readouterr()
        main(["--workspace", ws, "document", "622", "--show"])
        assert "# Ticket 622" in capsys.readouterr().out

    def test_add_is_refused_twice(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        main(["--workspace", ws, "ticket", "add", "622"])
        capsys.readouterr()

        assert main(["--workspace", ws, "ticket", "add", "622"]) == 4
        assert "already exists" in capsys.readouterr().err

    def test_list_and_show(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        main(["--workspace", ws, "ticket", "add", "622"])
        capsys.readouterr()

        assert main(["--workspace", ws, "ticket", "list"]) == 0
        assert "622" in capsys.readouterr().out

        assert main(["--workspace", ws, "ticket", "show", "622"]) == 0
        shown = capsys.readouterr().out
        assert "document:  filled" in shown
        assert "operations:" in shown

    def test_show_an_unknown_ticket_exits_four(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "ticket", "show", "nope"]) == 4
        assert "no ticket" in capsys.readouterr().err

    def test_pending_work_is_reported_as_ahead_of_mainline(self, tmp_path, repo, capsys):
        """The case D-031 expects: merged outside mainline."""
        ws = self._ws(tmp_path)
        clone = tmp_path / "clone"
        git(tmp_path, "clone", "--quiet", str(repo), str(clone))
        git(clone, "checkout", "--quiet", "-b", "develop")
        (clone / "x.txt").write_text("x\n")
        git(clone, "add", "x.txt")
        git(clone, "commit", "-m", "Change a rule (#77)")
        git(clone, "checkout", "--quiet", "main")

        main(["--workspace", ws, "repo", "add", str(clone), "--name", "s"])
        capsys.readouterr()

        assert main(["--workspace", ws, "ticket", "add", "77"]) == 0
        assert "s: pending — 1 commit(s)" in capsys.readouterr().out

    def test_landed_work_is_distinguished_from_nothing(self, tmp_path, repo, capsys):
        ws = self._ws(tmp_path)
        clone = tmp_path / "clone"
        git(tmp_path, "clone", "--quiet", str(repo), str(clone))
        (clone / "y.txt").write_text("y\n")
        git(clone, "add", "y.txt")
        git(clone, "commit", "-m", "Already shipped (#88)")

        main(["--workspace", ws, "repo", "add", str(clone), "--name", "s"])
        capsys.readouterr()

        main(["--workspace", ws, "ticket", "add", "88"])
        assert "s: landed" in capsys.readouterr().out

        main(["--workspace", ws, "ticket", "add", "99999"])
        assert "s: not_found" in capsys.readouterr().out


class TestDocumentCommand:
    def _setup(self, tmp_path, with_repo=True):
        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init"])
        if with_repo:
            source = tmp_path / "src"
            source.mkdir()
            git(source, "init", "--initial-branch=main", "--quiet")
            (source / "a.py").write_text("x = 1\n")
            git(source, "add", "a.py")
            git(source, "commit", "-m", "Initial")

            clone = tmp_path / "clone"
            git(tmp_path, "clone", "--quiet", str(source), str(clone))
            git(clone, "checkout", "--quiet", "-b", "develop")
            (clone / "a.py").write_text("x = 2\n")
            git(clone, "add", "a.py")
            git(clone, "commit", "-m", "Change the rule (#622)")
            git(clone, "checkout", "--quiet", "main")
            main(["--workspace", ws, "repo", "add", str(clone), "--name", "billing"])
        main(["--workspace", ws, "ticket", "add", "622"])
        return ws

    def test_document_gathers_and_reports(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "document", "622"]) == 0
        out = capsys.readouterr().out
        assert "document updated" in out
        assert "billing: pending" in out

    def test_show_prints_the_document(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "document", "622", "--show"]) == 0
        body = capsys.readouterr().out
        assert "# Ticket 622" in body
        assert "a.py" in body
        assert "carries no authority" in body

    def test_an_unknown_ticket_exits_four(self, tmp_path, capsys):
        ws = self._setup(tmp_path, with_repo=False)
        capsys.readouterr()

        assert main(["--workspace", ws, "document", "nope"]) == 4
        assert "no ticket" in capsys.readouterr().err


class TestRuleCommands:
    def _ws(self, tmp_path):
        target = str(tmp_path / "ws")
        main(["--workspace", target, "init"])
        return target

    def test_declare_show_and_list(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "add", "limit", "At most the limit."]) == 0
        assert main(["--workspace", ws, "rule", "behaviour", "limit", "Refused above."]) == 0
        assert main(["--workspace", ws, "rule", "anchor", "limit", "rules.py"]) == 0
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "show", "limit"]) == 0
        shown = capsys.readouterr().out
        assert "At most the limit." in shown
        assert "Refused above." in shown
        assert "rules.py" in shown

    def test_a_new_rule_is_told_it_cannot_match_anything(self, tmp_path, capsys):
        """An unanchored rule is inert; saying so prevents silent uselessness."""
        ws = self._ws(tmp_path)
        capsys.readouterr()

        main(["--workspace", ws, "rule", "add", "limit", "At most the limit."])
        out = capsys.readouterr().out
        assert "can never be matched" in out

    def test_an_empty_catalogue_explains_the_consequence(self, tmp_path, capsys):
        """No rules must not read as "nothing is affected"."""
        ws = self._ws(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "list"]) == 0
        out = capsys.readouterr().out
        assert "No rules declared" in out
        assert "not the same as nothing changing" in out

    def test_duplicate_declaration_exits_four(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        main(["--workspace", ws, "rule", "add", "limit", "At most."])
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "add", "limit", "At most."]) == 4
        assert "already exists" in capsys.readouterr().err

    def test_remove_withdraws_the_rule(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        main(["--workspace", ws, "rule", "add", "limit", "At most."])
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "remove", "limit"]) == 0
        assert "withdrawn" in capsys.readouterr().out

    def test_show_an_unknown_rule_exits_four(self, tmp_path, capsys):
        ws = self._ws(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "show", "nope"]) == 4
        assert "no rule" in capsys.readouterr().err
