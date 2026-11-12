"""Tests for proposing a revision rather than a new rule (CON-55).

The last piece of rule maintenance. Before this, a reading had never been shown
the catalogue, so every reading claimed to be new and the second reading of a
rule created a duplicate — the failure CON-43 exists to prevent, arriving by a
different route.

Three properties:

1. **The payload carries the catalogue.** A reading cannot claim to revise a
   rule it was never shown.
2. **A `revises` claim is checked like an anchor.** Naming a rule that was not
   in the payload is inventing a relationship, not observing one.
3. **Anchor overlap warns; it never decides** (D-050). A reading that claims to
   be new is stored as new, and the reviewer is told what it overlaps.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from constat.ai import as_dict, redact
from constat.cli import main
from constat.operations import collect, known_rules, open_run, submit_reply
from constat.store import (
    Catalogue,
    Registry,
    Review,
    RuleProposals,
    TicketStore,
    Workspace,
)

from test_acceptance import a_reading, record
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


def a_rule(name: str = "daily-limit", **overrides) -> dict:
    base = {
        "name": name,
        "statement": "A transfer over the daily limit is refused.",
        "anchors": [{"path_glob": "rules.py", "repository_alias": "billing"}],
    }
    base.update(overrides)
    return base


def accepted_rule(workspace, tmp_path) -> int:
    register(workspace, tmp_path)
    return Review(workspace).accept(
        record(workspace, a_reading()), decided_by="emmanuel"
    ).rule_id


class TestThePayloadCarriesTheCatalogue:
    def test_an_empty_catalogue_is_empty(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        payload = redact("622", collect(workspace, "622"), known_rules(workspace))
        assert payload.catalogue == ()

    def test_an_accepted_rule_appears_with_its_id_and_anchors(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The id is what a reply names in its `revises` field."""
        rule_id = accepted_rule(workspace, tmp_path)
        payload = redact("622", collect(workspace, "622"), known_rules(workspace))

        assert len(payload.catalogue) == 1
        known = payload.catalogue[0]
        assert known.rule_id == rule_id
        assert known.name == "daily-limit"
        assert known.anchors == ("rules.py",)

    def test_it_survives_serialisation(
        self, workspace: Workspace, tmp_path: Path
    ):
        accepted_rule(workspace, tmp_path)
        payload = redact("622", collect(workspace, "622"), known_rules(workspace))
        again = json.loads(json.dumps(as_dict(payload), default=str))

        assert again["catalogue"][0]["name"] == "daily-limit"

    def test_the_catalogue_carries_no_identity(
        self, workspace: Workspace, tmp_path: Path
    ):
        """D-040 still holds: the catalogue is the user's own rules, and adding
        it must not reintroduce a person."""
        from test_ai import FIXTURE_EMAIL

        accepted_rule(workspace, tmp_path)
        payload = redact("622", collect(workspace, "622"), known_rules(workspace))
        assert FIXTURE_EMAIL not in str(as_dict(payload))

    def test_the_cli_export_includes_it(self, tmp_path, capsys):
        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init"])
        clone = distinct_subject(tmp_path, "billing", "LIMIT = 250\n")
        main(["--workspace", ws, "repo", "add", str(clone), "--name", "billing"])
        main(["--workspace", ws, "ticket", "add", "622"])
        with Workspace.open(ws) as workspace:
            Review(workspace).accept(
                record(workspace, a_reading()), decided_by="emmanuel"
            )
        capsys.readouterr()

        main(["--workspace", ws, "document", "622", "--payload"])
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["catalogue"][0]["name"] == "daily-limit"


class TestAClaimToRevise:
    def test_a_valid_claim_is_stored(self, workspace: Workspace, tmp_path: Path):
        rule_id = accepted_rule(workspace, tmp_path)
        result = submit_reply(
            workspace, "622", reply(a_rule("revised", revises=rule_id))
        )

        assert result.stored_count == 1
        stored = RuleProposals(workspace).find(result.stored[0])
        assert stored.claims_to_revise
        assert stored.revises_rule_id == rule_id

    def test_accepting_it_adds_a_version_rather_than_a_rule(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The whole point: CON-43's failure mode closed from the other end."""
        rule_id = accepted_rule(workspace, tmp_path)
        result = submit_reply(
            workspace, "622", reply(a_rule("revised", revises=rule_id))
        )

        acceptance = Review(workspace).accept(
            result.stored[0], decided_by="emmanuel"
        )
        assert acceptance.is_revision
        assert acceptance.version_no == 2
        assert len(Catalogue(workspace).list()) == 1

    def test_a_claim_naming_a_rule_not_in_the_payload_is_discarded(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Symmetric with an ungrounded anchor: the reading cannot have read a
        rule it was never shown, so claiming a relationship invents one."""
        register(workspace, tmp_path)  # empty catalogue
        result = submit_reply(workspace, "622", reply(a_rule(revises=999)))

        assert result.stored_count == 0
        assert "not in the evidence supplied" in result.rejections[0].reason

    def test_a_non_integer_claim_is_discarded(
        self, workspace: Workspace, tmp_path: Path
    ):
        accepted_rule(workspace, tmp_path)
        result = submit_reply(
            workspace, "622", reply(a_rule(revises="daily-limit"))
        )

        assert result.stored_count == 0
        assert "not a rule id" in result.rejections[0].reason

    def test_a_boolean_is_not_a_rule_id(
        self, workspace: Workspace, tmp_path: Path
    ):
        """`True` is an int in Python, which would otherwise pass as id 1."""
        accepted_rule(workspace, tmp_path)
        result = submit_reply(workspace, "622", reply(a_rule(revises=True)))

        assert result.stored_count == 0
        assert "not a rule id" in result.rejections[0].reason

    def test_an_absent_claim_means_new(self, workspace: Workspace, tmp_path: Path):
        accepted_rule(workspace, tmp_path)
        result = submit_reply(workspace, "622", reply(a_rule("fresh")))

        stored = RuleProposals(workspace).find(result.stored[0])
        assert not stored.claims_to_revise


class TestOverlapWarnsButNeverDecides:
    """D-050: one file routinely implements several rules."""

    def test_a_new_claim_overlapping_an_existing_rule_is_flagged(
        self, workspace: Workspace, tmp_path: Path
    ):
        rule_id = accepted_rule(workspace, tmp_path)
        result = submit_reply(workspace, "622", reply(a_rule("fresh")))

        assert result.possible_duplicates == 1
        assert result.candidates[result.stored[0]] == (rule_id,)

    def test_it_is_still_stored_as_new(self, workspace: Workspace, tmp_path: Path):
        """A warning, not a decision. Rewriting the claim would be exactly the
        structural key D-050 refused."""
        accepted_rule(workspace, tmp_path)
        result = submit_reply(workspace, "622", reply(a_rule("fresh")))

        stored = RuleProposals(workspace).find(result.stored[0])
        assert stored.revises_rule_id is None

    def test_accepting_it_creates_a_second_rule(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Which is correct when the reviewer meant it — two rules can share a
        file. The warning exists so the choice is informed, not prevented."""
        accepted_rule(workspace, tmp_path)
        result = submit_reply(workspace, "622", reply(a_rule("fresh")))

        Review(workspace).accept(result.stored[0], decided_by="emmanuel")
        assert len(Catalogue(workspace).list()) == 2

    def test_overlap_is_exact_glob_equality_and_misses_the_rest(
        self, workspace: Workspace, tmp_path: Path
    ):
        """An honest limit, asserted so it cannot change silently.

        `candidates_for` matches anchors by *identical glob string*, not by
        whether two globs cover any path in common. So a rule anchored to
        `rules.py` and a reading anchored to `**/*.py` clearly overlap in
        reality and are **not** flagged. The warning therefore has false
        negatives by construction — it catches the common case (a reading
        re-anchoring to the same path) and nothing cleverer.

        Widening it means comparing globs for intersection, which has no exact
        answer in general. Left narrow deliberately: a warning that fired on
        every broad glob would be noise, and D-050 already says overlap is
        never a verdict.
        """
        accepted_rule(workspace, tmp_path)  # anchored to "rules.py"
        result = submit_reply(
            workspace, "622", reply(a_rule("fresh", anchors=["**/*.py"]))
        )

        assert result.stored_count == 1
        assert result.candidates == {}

    def test_a_claimed_revision_is_not_flagged(
        self, workspace: Workspace, tmp_path: Path
    ):
        """It already decided. Warning about it would be noise."""
        rule_id = accepted_rule(workspace, tmp_path)
        result = submit_reply(
            workspace, "622", reply(a_rule("revised", revises=rule_id))
        )
        assert result.candidates == {}

    def test_an_empty_catalogue_warns_about_nothing(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        result = submit_reply(workspace, "622", reply(a_rule()))
        assert result.candidates == {}


class TestTheCommandLine:
    def _setup(self, tmp_path) -> str:
        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init"])
        clone = distinct_subject(tmp_path, "billing", "LIMIT = 250\n")
        main(["--workspace", ws, "repo", "add", str(clone), "--name", "billing"])
        main(["--workspace", ws, "ticket", "add", "622"])
        with Workspace.open(ws) as workspace:
            Review(workspace).accept(
                record(workspace, a_reading()), decided_by="emmanuel"
            )
        return ws

    def test_the_overlap_warning_is_printed(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text(reply(a_rule("fresh")))
        capsys.readouterr()

        main(["--workspace", ws, "rule", "submit", "622", "--from", str(path)])
        out = capsys.readouterr().out
        assert "claimed to be new but overlap existing rules" in out
        assert "candidate, not a verdict" in out

    def test_the_queue_shows_a_revision_claim(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text(reply(a_rule("revised", revises=1)))
        main(["--workspace", ws, "rule", "submit", "622", "--from", str(path)])
        capsys.readouterr()

        main(["--workspace", ws, "rule", "proposals", "622"])
        assert "claims to revise rule 1" in capsys.readouterr().out

    def test_an_invented_revision_claim_is_reported(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        path = tmp_path / "reply.json"
        path.write_text(reply(a_rule(revises=999)))
        capsys.readouterr()

        main(["--workspace", ws, "rule", "submit", "622", "--from", str(path)])
        out = capsys.readouterr().out
        assert "discarded" in out
        assert "not in the evidence supplied" in out
