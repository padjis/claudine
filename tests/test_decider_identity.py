"""Tests for inferring who decided (D-061).

`--by` was mandatory on the reasoning that a decision with no decider is not a
decision. That reasoning survives; what did not is the idea that *typing* a
name made it stronger. `--by` is a free string nobody checks, so a typed name
and a name read from git config are equally unverified — the mandatory flag
bought friction, not assurance.

So the tests here are not about trust. They are about the record saying which
of the two happened, and about refusing when neither is available.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.cli import EXIT_OK, EXIT_USAGE, main
from constat.git.adapter import configured_identity
from constat.store import Review, RuleProposals, Workspace

from test_acceptance import a_reading, record, register


@pytest.fixture
def workspace(tmp_path: Path):
    """A workspace with a registered repository and ticket 622 open.

    `record` opens a run against that ticket, so the ticket has to exist —
    found by writing the fixture without one.
    """
    with Workspace.create(tmp_path / "ws") as ws:
        register(ws, tmp_path)
        yield ws


def a_proposal(workspace) -> int:
    return record(workspace, a_reading())


class TestTheRecordSaysWhichHappened:
    def test_a_stated_name_is_recorded_as_stated(self, workspace):
        proposal_id = a_proposal(workspace)
        Review(workspace).accept(proposal_id, decided_by="Someone", attribution="stated")

        item = RuleProposals(workspace).find(proposal_id)
        assert item.decided_by == "Someone"
        assert item.decided_attribution == "stated"
        assert item.decided_by_description == "Someone"

    def test_an_inferred_name_says_so_wherever_it_is_shown(self, workspace):
        proposal_id = a_proposal(workspace)
        Review(workspace).accept(
            proposal_id, decided_by="A Person <a@b>", attribution="inferred"
        )

        item = RuleProposals(workspace).find(proposal_id)
        assert item.decided_attribution == "inferred"
        assert "inferred from git config" in item.decided_by_description

    def test_the_default_is_stated(self, workspace):
        """A caller that forgets the argument claims the weaker thing — that a
        person said this — rather than silently claiming a machine did."""
        proposal_id = a_proposal(workspace)
        Review(workspace).accept(proposal_id, decided_by="Someone")

        assert RuleProposals(workspace).find(proposal_id).decided_attribution == "stated"

    def test_rejection_records_it_too(self, workspace):
        proposal_id = a_proposal(workspace)
        Review(workspace).reject(
            proposal_id, decided_by="A Person", attribution="inferred"
        )

        item = RuleProposals(workspace).find(proposal_id)
        assert item.decision == "rejected"
        assert item.decided_attribution == "inferred"

    def test_it_does_not_collide_with_the_reader_attribution(self, workspace):
        """`attribution` already meant who *read* the evidence (D-057). Two
        different people and two different questions — the collision was found
        by hitting it, and the fix is two names."""
        proposal_id = a_proposal(workspace)
        Review(workspace).accept(
            proposal_id, decided_by="A Person", attribution="inferred"
        )
        item = RuleProposals(workspace).find(proposal_id)

        assert "self-reported" in item.attribution          # who read it
        assert item.decided_attribution == "inferred"       # who decided


class TestTheCommandLine:
    @pytest.fixture
    def home(self, tmp_path: Path):
        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init", "--reader", "mcp"])
        with Workspace.open(ws) as workspace:
            register(workspace, tmp_path)
            record(workspace, a_reading())
        return ws

    def test_accept_works_with_no_by(self, home, capsys):
        assert main(["--workspace", home, "rule", "accept", "1"]) == EXIT_OK
        assert "inferred from git config" in capsys.readouterr().out

    def test_reject_works_with_no_by(self, home, capsys):
        assert main(["--workspace", home, "rule", "reject", "1"]) == EXIT_OK
        assert "inferred from git config" in capsys.readouterr().out

    def test_by_still_wins(self, home):
        main(["--workspace", home, "rule", "accept", "1", "--by", "Someone Else"])

        with Workspace.open(home) as ws:
            item = RuleProposals(ws).find(1)
        assert item.decided_by == "Someone Else"
        assert item.decided_attribution == "stated"

    def test_history_shows_the_inference(self, home, capsys):
        """The audit view is where this matters most."""
        main(["--workspace", home, "rule", "accept", "1"])
        capsys.readouterr()
        main(["--workspace", home, "rule", "history", "1"])

        assert "inferred from git config" in capsys.readouterr().out

    def test_the_queue_shows_who_decided(self, home, capsys):
        main(["--workspace", home, "rule", "accept", "1"])
        capsys.readouterr()
        main(["--workspace", home, "rule", "proposals", "622", "--all"])

        out = capsys.readouterr().out
        assert "accepted by" in out
        assert "inferred from git config" in out


class TestItRefusesRatherThanGuessing:
    def test_no_git_identity_refuses(self, tmp_path: Path, monkeypatch, capsys):
        """`$USER` names an account, not a person. "Who accepted this rule" is
        the last question to answer with a guess (D-028's posture)."""
        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init", "--reader", "mcp"])
        with Workspace.open(ws) as workspace:
            register(workspace, tmp_path)
            record(workspace, a_reading())

        # A git with no identity anywhere it can see. The chdir matters as
        # much as the env: git reads a repository's local config first, and
        # the suite runs inside a repository that has one.
        empty = tmp_path / "nogitconfig"
        empty.mkdir()
        monkeypatch.chdir(empty)
        monkeypatch.setenv("HOME", str(empty))
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty / "none"))
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty / "none"))

        assert configured_identity() is None   # the precondition this rests on

        code = main(["--workspace", ws, "rule", "accept", "1"])
        assert code == EXIT_USAGE
        assert "a decision needs a person" in capsys.readouterr().err

    def test_the_refusal_names_both_ways_out(self, tmp_path: Path, monkeypatch, capsys):
        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init", "--reader", "mcp"])
        with Workspace.open(ws) as workspace:
            register(workspace, tmp_path)
            record(workspace, a_reading())

        empty = tmp_path / "nogit2"
        empty.mkdir()
        monkeypatch.chdir(empty)
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty / "none"))
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty / "none"))
        monkeypatch.setenv("HOME", str(empty))

        main(["--workspace", ws, "rule", "accept", "1"])
        err = capsys.readouterr().err

        assert "--by" in err
        assert "user.name" in err


class TestMigration:
    def test_existing_decisions_become_stated(self, tmp_path: Path):
        """They were typed, so that is what happened. Marking them `inferred`
        would claim a machine supplied a name a person actually chose."""
        import sqlite3

        ws = str(tmp_path / "old")
        with Workspace.create(ws) as workspace:
            register(workspace, tmp_path)
            proposal_id = a_proposal(workspace)
            Review(workspace).accept(proposal_id, decided_by="Historic Person")
            db = workspace.path

        connection = sqlite3.connect(db)
        connection.execute(
            "CREATE TABLE d2 AS SELECT id, rule_proposal_id, decision, "
            "decided_by, decided_at, rationale FROM rule_proposal_decision"
        )
        connection.commit()
        connection.close()

        with Workspace.open(ws) as workspace:
            item = RuleProposals(workspace).find(proposal_id)
        assert item.decided_attribution == "stated"
