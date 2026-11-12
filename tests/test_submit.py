"""Tests for submitting a reply produced outside Constat (CON-52).

The inbound half of D-045: `export_payload` hands the evidence out, this takes
the reading back. Everything after the reply is the provider path's machinery —
same `parse`, same anchor grounding, same append-only storage.

Three properties carry it:

1. **The evidence is re-gathered, never trusted.** A caller who could supply
   the payload could supply one that makes any anchor look grounded.
2. **An unusable reply is an error.** Storing nothing would read as "no rules
   were identified", which is a caller's fault wearing the costume of a
   finding (D-046).
3. **Nothing is accepted.** Everything stored awaits a human decision; the
   catalogue is untouched (D-036, D-037).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from constat.cli import main
from constat.errors import MalformedResponse
from constat.operations import submit_reply
from constat.store import Catalogue, Registry, RuleProposals, TicketStore, Workspace

from helpers import seed_rule

from test_runs import distinct_subject


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


def register(workspace, tmp_path, alias: str = "billing"):
    Registry(workspace).add(
        str(distinct_subject(tmp_path, alias, "LIMIT = 250\n")), alias=alias
    )
    TicketStore(workspace).add("622")


def reply(*rules: dict) -> str:
    return json.dumps({"rules": list(rules)})


def grounded(name: str = "daily-limit", **overrides) -> dict:
    base = {
        "name": name,
        "statement": "A transfer over the daily limit is refused.",
        "behaviours": ["Refuse and explain the limit"],
        "anchors": [{"path_glob": "rules.py", "repository_alias": "billing"}],
    }
    base.update(overrides)
    return base


class TestStoringAReply:
    def test_a_grounded_reading_is_stored(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        result = submit_reply(workspace, "622", reply(grounded()))

        assert result.stored_count == 1
        stored = RuleProposals(workspace).for_ticket("622")
        assert [p.proposal.name for p in stored] == ["daily-limit"]

    def test_the_reader_is_recorded_as_self_reported(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        submit_reply(
            workspace, "622", reply(grounded()), provider="claude", model="opus-5"
        )

        stored = RuleProposals(workspace).for_ticket("622")[0]
        assert stored.provider == "claude"
        assert stored.model == "opus-5"

    def test_it_opens_its_own_run(self, workspace: Workspace, tmp_path: Path):
        """A reading belongs to a run (D-049), and a submitted one was not
        produced by the gather that happened to come before it."""
        register(workspace, tmp_path)
        result = submit_reply(workspace, "622", reply(grounded()))

        kind = workspace.execute(
            "SELECT kind FROM run WHERE id = ?", (result.run_id,)
        ).fetchone()["kind"]
        assert kind == "submit_reply"

    def test_two_submissions_accumulate(self, workspace: Workspace, tmp_path: Path):
        register(workspace, tmp_path)
        first = submit_reply(workspace, "622", reply(grounded()))
        second = submit_reply(workspace, "622", reply(grounded()))

        assert first.run_id != second.run_id
        assert len(RuleProposals(workspace).for_ticket("622")) == 2

    def test_the_body_is_not_touched(self, workspace: Workspace, tmp_path: Path):
        """`document` writes the body; submitting does not."""
        register(workspace, tmp_path)
        before = TicketStore(workspace).document("622").body

        submit_reply(workspace, "622", reply(grounded()))
        assert TicketStore(workspace).document("622").body == before


class TestGroundingIsCheckedAgainstRealEvidence:
    def test_an_invented_anchor_is_discarded(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        result = submit_reply(
            workspace,
            "622",
            reply(grounded(anchors=[{"path_glob": "src/payments/gateway.py"}])),
        )

        assert result.stored_count == 0
        assert len(result.rejections) == 1
        assert "grounded" in result.rejections[0].reason

    def test_the_good_survives_alongside_the_bad(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        result = submit_reply(
            workspace,
            "622",
            reply(
                grounded(),
                grounded("invented", anchors=[{"path_glob": "nope.py"}]),
            ),
        )

        assert result.stored_count == 1
        assert [r.name for r in result.rejections] == ["invented"]

    def test_a_discarded_reading_is_not_stored(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        submit_reply(
            workspace, "622", reply(grounded("invented", anchors=["nope.py"]))
        )
        assert RuleProposals(workspace).for_ticket("622") == ()

    def test_grounding_uses_the_evidence_now_not_a_claim(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The payload is rebuilt here. A caller cannot widen the grounding
        set by asserting it read something else."""
        register(workspace, tmp_path)
        result = submit_reply(
            workspace, "622", reply(grounded(anchors=["**/*.py"]))
        )
        # The glob matches a path that really is in the evidence.
        assert result.stored_count == 1


class TestAnUnusableReply:
    @pytest.mark.parametrize(
        "text",
        ["", "   ", "I found no rules.", "{broken", '{"no_rules_key": []}'],
    )
    def test_it_is_refused(self, workspace: Workspace, tmp_path: Path, text):
        register(workspace, tmp_path)
        with pytest.raises(MalformedResponse):
            submit_reply(workspace, "622", text)

    def test_nothing_is_stored_when_refused(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        with pytest.raises(MalformedResponse):
            submit_reply(workspace, "622", "not json")

        assert RuleProposals(workspace).for_ticket("622") == ()

    def test_a_refusal_opens_no_run(self, workspace: Workspace, tmp_path: Path):
        """Parsing happens before the run is opened, so a bad reply leaves no
        empty event behind."""
        register(workspace, tmp_path)
        before = workspace.execute("SELECT COUNT(*) c FROM run").fetchone()["c"]

        with pytest.raises(MalformedResponse):
            submit_reply(workspace, "622", "not json")

        after = workspace.execute("SELECT COUNT(*) c FROM run").fetchone()["c"]
        assert after == before

    def test_an_empty_rules_list_is_not_an_error(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A reader that genuinely found nothing is a finding, not a fault."""
        register(workspace, tmp_path)
        result = submit_reply(workspace, "622", '{"rules": []}')
        assert result.stored_count == 0
        assert result.rejections == ()


class TestNothingIsAccepted:
    def test_the_catalogue_is_untouched(self, workspace: Workspace, tmp_path: Path):
        """Submitting fills the review queue. Accepting is a separate human
        act (D-036, D-037) and does not happen here."""
        register(workspace, tmp_path)
        submit_reply(workspace, "622", reply(grounded()))

        assert Catalogue(workspace).list() == ()

    def test_everything_stored_awaits_a_decision(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        submit_reply(workspace, "622", reply(grounded(), grounded("audit")))

        proposals = RuleProposals(workspace)
        assert len(proposals.undecided("622")) == 2
        assert all(not p.is_decided for p in proposals.for_ticket("622"))


class TestTheCommandLine:
    def _setup(self, tmp_path) -> str:
        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init"])
        clone = distinct_subject(tmp_path, "billing", "LIMIT = 250\n")
        main(["--workspace", ws, "repo", "add", str(clone), "--name", "billing"])
        main(["--workspace", ws, "ticket", "add", "622", "--no-provider"])
        return ws

    def test_it_reads_a_reply_from_a_file(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text(reply(grounded()))
        capsys.readouterr()

        code = main(
            ["--workspace", ws, "rule", "submit", "622", "--from", str(path)]
        )
        assert code == 0
        assert "1 rule proposal(s) stored" in capsys.readouterr().out

    def test_it_reads_from_stdin(self, tmp_path, capsys, monkeypatch):
        import io

        ws = self._setup(tmp_path)
        monkeypatch.setattr("sys.stdin", io.StringIO(reply(grounded())))
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "submit", "622"]) == 0
        assert "1 rule proposal(s) stored" in capsys.readouterr().out

    def test_discards_are_reported_before_the_kept_count(self, tmp_path, capsys):
        """A reader shown only the kept number has been told a shorter truth
        than the one that happened (D-046)."""
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text(reply(grounded(), grounded("invented", anchors=["nope.py"])))
        capsys.readouterr()

        main(["--workspace", ws, "rule", "submit", "622", "--from", str(path)])
        out = capsys.readouterr().out
        assert out.index("discarded") < out.index("stored")
        assert "invented" in out

    def test_it_says_nothing_is_accepted(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text(reply(grounded()))
        capsys.readouterr()

        main(["--workspace", ws, "rule", "submit", "622", "--from", str(path)])
        assert "None of them is accepted" in capsys.readouterr().out

    def test_an_unusable_reply_exits_five(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text("I could not find any rules.")
        capsys.readouterr()

        code = main(
            ["--workspace", ws, "rule", "submit", "622", "--from", str(path)]
        )
        assert code == 5
        assert "not valid JSON" in capsys.readouterr().err

    def test_an_unknown_ticket_exits_four(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text(reply(grounded()))
        capsys.readouterr()

        code = main(
            ["--workspace", ws, "rule", "submit", "nope", "--from", str(path)]
        )
        assert code == 4

    def test_the_queue_lists_what_was_stored(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text(reply(grounded()))
        main(
            [
                "--workspace", ws, "rule", "submit", "622",
                "--from", str(path), "--provider", "claude", "--model", "opus-5",
            ]
        )
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "proposals", "622"]) == 0
        out = capsys.readouterr().out
        assert "daily-limit" in out
        assert "awaiting a decision" in out
        assert "self-reported" in out

    def test_an_empty_queue_is_not_a_statement_about_the_ticket(
        self, tmp_path, capsys
    ):
        ws = self._setup(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "proposals", "622"]) == 0
        out = capsys.readouterr().out
        assert "No undecided rule proposals" in out
        assert "not a statement that this ticket has no rules" in out


class TestTheSharedGlobMatcher:
    """Grounding and catalogue matching must give the same answer.

    Two matchers that disagree would accept a rule proposal at submit time and
    then never match it to a change, or the reverse.
    """

    def test_a_recursive_prefix_also_matches_at_the_root(self):
        """`**/rules.py` is the natural way to write "this file anywhere", and
        a model asked to anchor to evidence writes it often. Plain fnmatch
        requires a directory, so this would be a false rejection."""
        from constat.globs import matches_path

        assert matches_path("rules.py", "**/rules.py")
        assert matches_path("src/rules.py", "**/rules.py")

    def test_a_plain_glob_is_unchanged(self):
        from constat.globs import matches_path

        assert matches_path("rules.py", "*.py")
        assert matches_path("src/billing/rules.py", "src/*/rules.py")
        assert not matches_path("rules.txt", "*.py")

    def test_a_recursive_glob_submits_successfully(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        result = submit_reply(
            workspace, "622", reply(grounded(anchors=["**/rules.py"]))
        )
        assert result.stored_count == 1

    def test_grounding_and_the_catalogue_agree(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        catalogue = Catalogue(workspace)
        seed_rule(workspace, "limit", "At most the limit.", anchors=("**/rules.py",))

        # Grounded at submit time...
        assert submit_reply(
            workspace, "622", reply(grounded(anchors=["**/rules.py"]))
        ).stored_count == 1
        # ...and matched by the catalogue against the same path.
        assert catalogue.rules_matching("billing", ("rules.py",))
