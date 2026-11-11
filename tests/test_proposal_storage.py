"""Tests for rule proposal storage (CON-51, schema 5).

A rule proposal is a **dated, attributed reading of the evidence one run
gathered** (D-048). Three properties, and the first is the reason the table
exists at all:

1. **A reading survives the regeneration of the document body it was rendered
   into.** Before this, a rule proposal lived for one `gather()` call and the
   next run wiped the prose that held it.
2. **A reading is never edited or deleted.** Enforced by trigger, not by this
   module — the same reasoning as `document_version` (CON-31).
3. **A decision does not mutate the reading.** It appends to its own table, so
   accepting or rejecting leaves the reading as the reviewer saw it.

Plus the D-048/D-050 prohibitions: a rule cannot be deleted, and `rule.name` is
no longer unique.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from constat.errors import NotRegistered
from constat.models import Anchor, Behaviour, RuleProposal
from constat.operations import gather, open_run
from constat.store import Registry, RuleProposals, TicketStore, Workspace

from test_ai import FakeProvider
from test_runs import distinct_subject


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


@pytest.fixture
def proposals(workspace: Workspace) -> RuleProposals:
    return RuleProposals(workspace)


def register(workspace, tmp_path, *aliases: str):
    registry = Registry(workspace)
    for alias in aliases:
        registry.add(str(distinct_subject(tmp_path, alias, "LIMIT = 250\n")), alias=alias)
    TicketStore(workspace).add("622")


def a_reading(name: str = "daily-transfer-limit", **overrides) -> RuleProposal:
    fields = {
        "name": name,
        "statement": "A transfer over the daily limit is refused.",
        "behaviours": (Behaviour(description="Refuse and explain the limit"),),
        "anchors": (Anchor(path_glob="rules.py", repository_alias="billing"),),
    }
    fields.update(overrides)
    return RuleProposal(**fields)


class TestARecordedReadingRoundTrips:
    def test_it_keeps_its_parts(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")

        stored_id = proposals.record(run_id, a_reading(), provider="fake", model="f-1")
        stored = proposals.find(stored_id)

        assert stored is not None
        assert stored.proposal.name == "daily-transfer-limit"
        assert [b.description for b in stored.proposal.behaviours] == [
            "Refuse and explain the limit"
        ]
        assert stored.proposal.anchors[0].path_glob == "rules.py"
        assert stored.proposal.anchors[0].repository_alias == "billing"

    def test_the_reader_is_recorded(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        """A reviewer cannot weigh a reading without knowing what made it —
        self-reported under D-045, and never an observed fact."""
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")

        stored = proposals.find(
            proposals.record(run_id, a_reading(), provider="fake", model="f-1")
        )
        assert stored.provider == "fake"
        assert stored.model == "f-1"

    def test_it_belongs_to_its_run(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")
        proposals.record(run_id, a_reading(), provider="fake")

        assert [p.run_id for p in proposals.for_run(run_id)] == [run_id]

    def test_an_anchor_for_an_unregistered_repository_keeps_its_glob(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        """Losing the scope is better than losing the reading."""
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")

        reading = a_reading(
            anchors=(Anchor(path_glob="rules.py", repository_alias="gone"),)
        )
        stored = proposals.find(proposals.record(run_id, reading, provider="fake"))

        assert stored.proposal.anchors[0].path_glob == "rules.py"
        assert stored.proposal.anchors[0].repository_alias is None

    def test_a_reading_starts_undecided(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")
        stored = proposals.find(proposals.record(run_id, a_reading(), provider="fake"))

        assert not stored.is_decided
        assert stored.decision is None


class TestItSurvivesRegeneration:
    """The reason the table exists."""

    def test_a_rule_proposal_outlives_the_body_it_was_rendered_into(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        provider = FakeProvider([a_reading()])

        first = gather(workspace, "622", provider=provider)
        assert "daily-transfer-limit" in first.body

        # A later run with nothing to say regenerates the body from scratch.
        second = gather(workspace, "622")
        assert "daily-transfer-limit" not in second.body

        stored = RuleProposals(workspace).for_ticket("622")
        assert [p.proposal.name for p in stored] == ["daily-transfer-limit"]

    def test_gather_records_what_the_provider_returned(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        gather(
            workspace,
            "622",
            provider=FakeProvider([a_reading(), a_reading("audit-trail")]),
        )

        stored = RuleProposals(workspace).for_ticket("622")
        assert {p.proposal.name for p in stored} == {
            "daily-transfer-limit",
            "audit-trail",
        }
        assert all(p.provider == "fake" for p in stored)

    def test_two_runs_accumulate_rather_than_replace(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A reading cannot be edited, so a later run adds one. 'Current' is
        derived, never stored."""
        register(workspace, tmp_path, "billing")
        gather(workspace, "622", provider=FakeProvider([a_reading()]))
        gather(workspace, "622", provider=FakeProvider([a_reading()]))

        stored = RuleProposals(workspace).for_ticket("622")
        assert len(stored) == 2
        assert stored[0].run_id != stored[1].run_id

    def test_a_run_with_no_proposals_records_none(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        gather(workspace, "622")  # null provider
        assert RuleProposals(workspace).for_ticket("622") == ()


class TestAppendOnly:
    def _one(self, workspace, tmp_path, proposals) -> int:
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")
        return proposals.record(run_id, a_reading(), provider="fake")

    def test_a_reading_cannot_be_edited(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        """Editing would rewrite what a reviewer was shown."""
        stored_id = self._one(workspace, tmp_path, proposals)

        with pytest.raises(sqlite3.DatabaseError, match="cannot be edited"):
            workspace.execute(
                "UPDATE rule_proposal SET statement = 'rewritten' WHERE id = ?",
                (stored_id,),
            )

    def test_a_reading_cannot_be_deleted(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        """Deleting would erase that it was ever offered — the same loss D-046
        refuses for discarded readings."""
        stored_id = self._one(workspace, tmp_path, proposals)

        with pytest.raises(sqlite3.DatabaseError, match="cannot be deleted"):
            workspace.execute(
                "DELETE FROM rule_proposal WHERE id = ?", (stored_id,)
            )

    def test_a_decision_cannot_be_modified(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        stored_id = self._one(workspace, tmp_path, proposals)
        proposals.decide(stored_id, "accepted", decided_by="emmanuel")

        with pytest.raises(sqlite3.DatabaseError, match="cannot be modified"):
            workspace.execute(
                "UPDATE rule_proposal_decision SET decision = 'rejected'"
            )

    def test_a_decision_cannot_be_deleted(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        stored_id = self._one(workspace, tmp_path, proposals)
        proposals.decide(stored_id, "rejected", decided_by="emmanuel")

        with pytest.raises(sqlite3.DatabaseError, match="cannot be deleted"):
            workspace.execute("DELETE FROM rule_proposal_decision")


class TestDeciding:
    def _one(self, workspace, tmp_path, proposals) -> int:
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")
        return proposals.record(run_id, a_reading(), provider="fake")

    def test_an_acceptance_is_recorded(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        stored_id = self._one(workspace, tmp_path, proposals)
        proposals.decide(stored_id, "accepted", decided_by="emmanuel", rationale="ok")

        stored = proposals.find(stored_id)
        assert stored.is_decided
        assert stored.decision == "accepted"
        assert stored.decided_by == "emmanuel"
        assert stored.rationale == "ok"

    def test_the_reading_is_unchanged_by_the_decision(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        """The decision lives in its own table precisely so this holds."""
        stored_id = self._one(workspace, tmp_path, proposals)
        before = proposals.find(stored_id).proposal

        proposals.decide(stored_id, "rejected", decided_by="emmanuel")
        assert proposals.find(stored_id).proposal == before

    def test_rejection_is_recorded_as_rejected(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        """D-036: rejected means inconclusive, not wrong — so it has to be
        distinguishable from acceptance rather than simply absent."""
        stored_id = self._one(workspace, tmp_path, proposals)
        proposals.decide(stored_id, "rejected", decided_by="emmanuel")

        assert proposals.find(stored_id).decision == "rejected"

    def test_changing_one_s_mind_keeps_both(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        """History rather than a correction to be hidden."""
        stored_id = self._one(workspace, tmp_path, proposals)
        proposals.decide(stored_id, "rejected", decided_by="emmanuel")
        proposals.decide(stored_id, "accepted", decided_by="emmanuel")

        assert proposals.find(stored_id).decision == "accepted"
        rows = workspace.execute(
            "SELECT decision FROM rule_proposal_decision ORDER BY id"
        ).fetchall()
        assert [r["decision"] for r in rows] == ["rejected", "accepted"]

    def test_an_invalid_decision_is_refused(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        stored_id = self._one(workspace, tmp_path, proposals)
        with pytest.raises(ValueError, match="accepted"):
            proposals.decide(stored_id, "maybe", decided_by="emmanuel")

    def test_deciding_an_unknown_reading_is_refused(
        self, proposals: RuleProposals
    ):
        with pytest.raises(NotRegistered, match="no rule proposal"):
            proposals.decide(999, "accepted", decided_by="emmanuel")

    def test_undecided_is_the_review_queue(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")
        first = proposals.record(run_id, a_reading(), provider="fake")
        proposals.record(run_id, a_reading("audit-trail"), provider="fake")

        proposals.decide(first, "accepted", decided_by="emmanuel")

        waiting = proposals.undecided("622")
        assert [p.proposal.name for p in waiting] == ["audit-trail"]


class TestAnchorsAreCandidatesNotKeys:
    """D-050: anchor overlap finds a rule; it never proves identity."""

    def test_overlapping_anchors_produce_a_candidate(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        from constat.store import Catalogue

        catalogue = Catalogue(workspace)
        catalogue.add_rule("limit", "At most the limit.")
        catalogue.add_anchor("limit", "rules.py")

        candidates = proposals.candidates_for((Anchor(path_glob="rules.py"),))
        assert len(candidates) == 1

    def test_one_file_yields_several_candidates(
        self, workspace: Workspace, proposals: RuleProposals
    ):
        """The reason anchors cannot be the key: one file routinely implements
        several rules, so overlap is ambiguous by construction."""
        from constat.store import Catalogue

        catalogue = Catalogue(workspace)
        catalogue.add_rule("limit", "At most the limit.")
        catalogue.add_rule("audit", "Transfers are audited.")
        catalogue.add_anchor("limit", "rules.py")
        catalogue.add_anchor("audit", "rules.py")

        assert len(proposals.candidates_for((Anchor(path_glob="rules.py"),))) == 2

    def test_no_anchors_means_no_candidates(self, proposals: RuleProposals):
        assert proposals.candidates_for(()) == ()

    def test_a_claim_to_revise_is_stored_as_a_claim(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        """`revises_rule_id` records what the reading claims, which a human can
        still reject — it is not a key that silently merges two rules."""
        from constat.store import Catalogue

        register(workspace, tmp_path, "billing")
        Catalogue(workspace).add_rule("limit", "At most the limit.")
        rule_id = workspace.execute(
            "SELECT id FROM rule WHERE name = 'limit'"
        ).fetchone()["id"]

        run_id = open_run(workspace, "622", "gather_evidence")
        stored = proposals.find(
            proposals.record(
                run_id, a_reading(), provider="fake", revises_rule_id=rule_id
            )
        )

        assert stored.claims_to_revise
        assert stored.revises_rule_id == rule_id

    def test_a_new_rule_claims_nothing(
        self, workspace: Workspace, proposals: RuleProposals, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")
        stored = proposals.find(proposals.record(run_id, a_reading(), provider="fake"))

        assert not stored.claims_to_revise
        assert stored.revises_rule_id is None


class TestTheMigration:
    """Schema 5 rebuilds `rule`, `behaviour` and `anchor` to drop a UNIQUE.

    The riskiest migration so far: `rule` is the parent of two cascading
    children, so a careless drop would take the catalogue with it. These assert
    the rows survive, not merely that the tables exist.
    """

    def _make_v4(self, home: Path) -> None:
        from constat.store.schema import MIGRATIONS

        home.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(home / "workspace.db")
        connection.executescript(
            """
            CREATE TABLE schema_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version INTEGER NOT NULL, constat_version TEXT NOT NULL,
                created_at TEXT NOT NULL);
            CREATE TABLE repository (
                id INTEGER PRIMARY KEY, alias TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL, source_kind TEXT NOT NULL,
                cache_path TEXT, identity TEXT, default_branch TEXT,
                added_at TEXT NOT NULL, last_fetched_at TEXT);
            CREATE TABLE ticket (
                id INTEGER PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL);
            CREATE TABLE document (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER NOT NULL UNIQUE REFERENCES ticket(id),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '');
            CREATE TABLE document_version (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES document(id),
                version_no INTEGER NOT NULL, content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                previous_version_id INTEGER REFERENCES document_version(id),
                decision TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
                decided_by TEXT NOT NULL, decided_at TEXT NOT NULL,
                rationale TEXT, UNIQUE (document_id, version_no));
            CREATE TABLE run (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES document(id),
                kind TEXT NOT NULL, started_at TEXT NOT NULL);
            CREATE TABLE operation (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES document(id),
                run_id INTEGER REFERENCES run(id),
                repository_id INTEGER REFERENCES repository(id),
                kind TEXT NOT NULL, ran_at TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '', payload TEXT);
            CREATE TABLE rule (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                statement TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE behaviour (
                id INTEGER PRIMARY KEY,
                rule_id INTEGER NOT NULL REFERENCES rule(id) ON DELETE CASCADE,
                description TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE (rule_id, description));
            CREATE TABLE anchor (
                id INTEGER PRIMARY KEY,
                rule_id INTEGER NOT NULL REFERENCES rule(id) ON DELETE CASCADE,
                repository_id INTEGER REFERENCES repository(id) ON DELETE CASCADE,
                path_glob TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE (rule_id, repository_id, path_glob));
            CREATE INDEX idx_behaviour_rule ON behaviour(rule_id);
            CREATE INDEX idx_anchor_rule ON anchor(rule_id);

            INSERT INTO schema_meta VALUES (1, 4, '0.0.1', '2026-11-11T00:00:00Z');
            INSERT INTO ticket (id, reference, created_at)
                VALUES (1, 'legacy', '2026-11-11T00:00:00Z');
            INSERT INTO document (id, ticket_id, created_at, updated_at, body)
                VALUES (1, 1, '2026-11-11T00:00:00Z', '2026-11-11T00:00:00Z', 'old');
            INSERT INTO rule (id, name, statement, created_at)
                VALUES (7, 'daily-limit', 'At most the limit.', '2026-11-11T00:00:00Z');
            INSERT INTO behaviour (rule_id, description, created_at)
                VALUES (7, 'Refused above.', '2026-11-11T00:00:00Z');
            INSERT INTO anchor (rule_id, repository_id, path_glob, created_at)
                VALUES (7, NULL, 'rules.py', '2026-11-11T00:00:00Z');
            """
        )
        connection.commit()
        connection.close()

    def test_the_catalogue_survives_the_rebuild(self, tmp_path: Path):
        """`rule` is the parent of two cascading children. A drop that took
        them with it would silently empty the catalogue."""
        home = tmp_path / "legacy"
        self._make_v4(home)

        with Workspace.open(home) as ws:
            rules = ws.execute("SELECT id, name FROM rule").fetchall()
            behaviours = ws.execute("SELECT rule_id, description FROM behaviour").fetchall()
            anchors = ws.execute("SELECT rule_id, path_glob FROM anchor").fetchall()

        assert [(r["id"], r["name"]) for r in rules] == [(7, "daily-limit")]
        assert [(b["rule_id"], b["description"]) for b in behaviours] == [
            (7, "Refused above.")
        ]
        assert [(a["rule_id"], a["path_glob"]) for a in anchors] == [(7, "rules.py")]

    def test_the_unique_name_constraint_is_gone(self, tmp_path: Path):
        home = tmp_path / "legacy"
        self._make_v4(home)

        with Workspace.open(home) as ws:
            ws.execute(
                "INSERT INTO rule (name, statement, created_at) VALUES (?, ?, ?)",
                ("daily-limit", "A second reading.", "2026-11-11T00:00:00Z"),
            )
            count = ws.execute(
                "SELECT COUNT(*) c FROM rule WHERE name = 'daily-limit'"
            ).fetchone()["c"]
        assert count == 2

    def test_the_delete_trigger_arrives_with_it(self, tmp_path: Path):
        home = tmp_path / "legacy"
        self._make_v4(home)

        with Workspace.open(home) as ws:
            with pytest.raises(sqlite3.DatabaseError, match="cannot be removed"):
                ws.execute("DELETE FROM rule WHERE id = 7")

    def test_the_rule_proposal_tables_are_usable(self, tmp_path: Path):
        """Present is not the same as working — the FK to `run` has to resolve
        after three tables were renamed around it."""
        home = tmp_path / "legacy"
        self._make_v4(home)

        with Workspace.open(home) as ws:
            run_id = open_run(ws, "legacy", "gather_evidence")
            proposals = RuleProposals(ws)
            stored_id = proposals.record(run_id, a_reading(), provider="fake")
            assert proposals.find(stored_id) is not None

    def test_the_document_body_survives(self, tmp_path: Path):
        home = tmp_path / "legacy"
        self._make_v4(home)

        with Workspace.open(home) as ws:
            body = ws.execute("SELECT body FROM document WHERE id = 1").fetchone()
        assert body["body"] == "old"
