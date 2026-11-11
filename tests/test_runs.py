"""Tests for run identity (schema 4).

A gather writes one `operation` row per repository, so no operation row can
answer "which run produced this". A rule proposal is a reading of the evidence
one run gathered (D-046), so it needs a single thing to point at. That is what
`run` is for, and these tests fix the two properties a later rule-proposal
table will depend on:

1. **One run per invocation**, whatever the number of repositories.
2. **Every operation row a run writes belongs to it** — no orphans, because an
   orphaned operation is unattributable, which is the failure D-029 names.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from constat.operations import export_payload, gather, open_run
from constat.store import SCHEMA_VERSION, Registry, TicketStore, Workspace

from helpers import commit_file, git
from test_ai import FakeProvider
from test_scanning import AWS_KEY


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


def distinct_subject(tmp_path: Path, alias: str, content: str) -> Path:
    """A clone with a root commit unique to this alias.

    `make_subject` seeds every repository with identical history, so the root
    commits collide and the second `repo add` is refused as a duplicate — which
    is D-025 working correctly, not a bug. Runs are per invocation and need
    several *distinct* repositories to be worth testing, so the initial commit
    is varied here.
    """
    source = tmp_path / f"{alias}-src"
    source.mkdir()
    git(source, "init", "--initial-branch=main", "--quiet")
    commit_file(source, "rules.py", f"# {alias}\nLIMIT = 100\n", f"Initial ({alias})")

    clone = tmp_path / alias
    git(tmp_path, "clone", "--quiet", str(source), str(clone))
    git(clone, "checkout", "--quiet", "-b", "develop")
    commit_file(clone, "rules.py", f"# {alias}\n{content}", "Raise the limit (#622)")
    git(clone, "checkout", "--quiet", "main")
    return clone


def register(workspace, tmp_path, *aliases: str, content: str = "LIMIT = 250\n"):
    registry = Registry(workspace)
    for alias in aliases:
        registry.add(str(distinct_subject(tmp_path, alias, content)), alias=alias)
    TicketStore(workspace).add("622")


def runs(workspace) -> list[sqlite3.Row]:
    return workspace.execute(
        "SELECT id, kind, started_at FROM run ORDER BY id"
    ).fetchall()


class TestOneRunPerInvocation:
    def test_a_gather_opens_exactly_one_run(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        before = len(runs(workspace))

        gather(workspace, "622")
        assert len(runs(workspace)) == before + 1

    def test_three_repositories_are_still_one_run(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The whole reason the table exists: operation rows are per
        repository, runs are per invocation."""
        register(workspace, tmp_path, "billing", "web", "api")
        before = len(runs(workspace))

        result = gather(workspace, "622")
        assert result.repositories_searched == 3
        assert len(runs(workspace)) == before + 1

    def test_two_gathers_are_two_runs(self, workspace: Workspace, tmp_path: Path):
        register(workspace, tmp_path, "billing")
        before = len(runs(workspace))

        first = gather(workspace, "622").run_id
        second = gather(workspace, "622").run_id

        assert first != second
        assert len(runs(workspace)) == before + 2

    def test_the_result_carries_the_identity(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A caller that has to re-query for the run it just made would have
        to guess which row is its own."""
        register(workspace, tmp_path, "billing")
        result = gather(workspace, "622")

        assert result.run_id is not None
        stored = {row["id"] for row in runs(workspace)}
        assert result.run_id in stored

    def test_the_run_records_its_kind(self, workspace: Workspace, tmp_path: Path):
        register(workspace, tmp_path, "billing")
        result = gather(workspace, "622")

        kind = workspace.execute(
            "SELECT kind FROM run WHERE id = ?", (result.run_id,)
        ).fetchone()["kind"]
        assert kind == "gather_evidence"


class TestOperationsBelongToTheirRun:
    def test_every_gather_row_is_attached(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing", "web")
        result = gather(workspace, "622")

        rows = workspace.execute(
            "SELECT run_id FROM operation WHERE kind = 'gather_evidence' "
            "AND run_id = ?",
            (result.run_id,),
        ).fetchall()
        assert len(rows) == 2  # one per repository, both on this run

    def test_no_operation_this_run_wrote_is_orphaned(
        self, workspace: Workspace, tmp_path: Path
    ):
        """An orphaned operation row is unattributable, which is the failure
        D-029 exists to prevent."""
        register(workspace, tmp_path, "billing", "web")
        gather(workspace, "622")

        orphans = workspace.execute(
            "SELECT id FROM operation WHERE run_id IS NULL"
        ).fetchall()
        assert orphans == []

    def test_a_scan_override_joins_the_same_run(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The override and the evidence it let through are one event."""
        register(workspace, tmp_path, "billing", content=f"K = '{AWS_KEY}'\n")
        result = gather(
            workspace, "622", provider=FakeProvider(), accept_scan_findings=True
        )

        kinds = {
            row["kind"]
            for row in workspace.execute(
                "SELECT kind FROM operation WHERE run_id = ?", (result.run_id,)
            ).fetchall()
        }
        assert kinds == {"gather_evidence", "scan_override"}

    def test_runs_are_distinguishable_after_several_invocations(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing", "web")
        first = gather(workspace, "622").run_id
        second = gather(workspace, "622").run_id

        def count(run_id: int) -> int:
            return len(
                workspace.execute(
                    "SELECT id FROM operation WHERE run_id = ?", (run_id,)
                ).fetchall()
            )

        assert count(first) == 2
        assert count(second) == 2


class TestExportOnlyRecordsARunWhenItDecidedSomething:
    def test_a_clean_export_opens_no_run(
        self, workspace: Workspace, tmp_path: Path
    ):
        """An export that found nothing made no decision. Recording it would
        put an empty event in the audit trail."""
        register(workspace, tmp_path, "billing")
        before = len(runs(workspace))

        result = export_payload(workspace, "622")
        assert result.run_id is None
        assert len(runs(workspace)) == before

    def test_an_accepted_export_opens_one(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing", content=f"K = '{AWS_KEY}'\n")
        before = len(runs(workspace))

        result = export_payload(workspace, "622", accept_scan_findings=True)
        assert result.run_id is not None
        assert len(runs(workspace)) == before + 1

        row = workspace.execute(
            "SELECT kind FROM run WHERE id = ?", (result.run_id,)
        ).fetchone()
        assert row["kind"] == "export_payload"

    def test_the_export_override_is_attached_to_it(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing", content=f"K = '{AWS_KEY}'\n")
        result = export_payload(workspace, "622", accept_scan_findings=True)

        rows = workspace.execute(
            "SELECT kind FROM operation WHERE run_id = ?", (result.run_id,)
        ).fetchall()
        assert [r["kind"] for r in rows] == ["scan_override_export"]

    def test_a_refused_export_opens_no_run(
        self, workspace: Workspace, tmp_path: Path
    ):
        from constat.errors import PayloadRefused

        register(workspace, tmp_path, "billing", content=f"K = '{AWS_KEY}'\n")
        before = len(runs(workspace))

        with pytest.raises(PayloadRefused):
            export_payload(workspace, "622")
        assert len(runs(workspace)) == before


class TestOpenRunDirectly:
    def test_it_refuses_an_unknown_ticket(self, workspace: Workspace):
        with pytest.raises(TypeError):
            # No document row to attach to; the lookup returns None and
            # subscripting it fails. Asserted so the failure stays loud rather
            # than silently writing an orphaned run.
            open_run(workspace, "nope", "gather_evidence")

    def test_runs_belong_to_the_ticket_s_document(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, "billing")
        run_id = open_run(workspace, "622", "gather_evidence")

        joined = workspace.execute(
            "SELECT t.reference FROM run r "
            "JOIN document d ON d.id = r.document_id "
            "JOIN ticket t ON t.id = d.ticket_id WHERE r.id = ?",
            (run_id,),
        ).fetchone()
        assert joined["reference"] == "622"


class TestTheMigration:
    """A workspace written before runs existed must survive, and must not be
    given fabricated provenance."""

    def _make_v3(self, home: Path) -> None:
        """A version-3 workspace with a document and one operation row."""
        home.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(home / "workspace.db")
        connection.executescript(
            """
            CREATE TABLE schema_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version INTEGER NOT NULL,
                constat_version TEXT NOT NULL,
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
            CREATE TABLE operation (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES document(id),
                repository_id INTEGER REFERENCES repository(id),
                kind TEXT NOT NULL, ran_at TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '', payload TEXT);
            CREATE TABLE rule (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                statement TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE behaviour (
                id INTEGER PRIMARY KEY,
                rule_id INTEGER NOT NULL REFERENCES rule(id),
                description TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE (rule_id, description));
            CREATE TABLE anchor (
                id INTEGER PRIMARY KEY,
                rule_id INTEGER NOT NULL REFERENCES rule(id),
                repository_id INTEGER REFERENCES repository(id),
                path_glob TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE (rule_id, repository_id, path_glob));

            INSERT INTO schema_meta VALUES (1, 3, '0.0.1', '2026-11-10T00:00:00Z');
            INSERT INTO ticket (id, reference, created_at)
                VALUES (1, 'legacy', '2026-11-10T00:00:00Z');
            INSERT INTO document (id, ticket_id, created_at, updated_at, body)
                VALUES (1, 1, '2026-11-10T00:00:00Z', '2026-11-10T00:00:00Z', 'old');
            INSERT INTO operation (document_id, kind, ran_at, summary)
                VALUES (1, 'gather_evidence', '2026-11-10T00:00:00Z', 'landed');
            """
        )
        connection.commit()
        connection.close()

    def test_a_v3_workspace_migrates(self, tmp_path: Path):
        home = tmp_path / "legacy"
        self._make_v3(home)

        with Workspace.open(home) as ws:
            assert ws.schema_version == SCHEMA_VERSION
            tables = {
                r["name"]
                for r in ws.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        assert "run" in tables

    def test_the_stored_document_survives(self, tmp_path: Path):
        home = tmp_path / "legacy"
        self._make_v3(home)

        with Workspace.open(home) as ws:
            body = ws.execute("SELECT body FROM document WHERE id = 1").fetchone()
        assert body["body"] == "old"

    def test_a_pre_run_operation_keeps_a_null_run(self, tmp_path: Path):
        """Back-filling a run for it would fabricate provenance — it was
        written before runs existed, and saying so is the honest record."""
        home = tmp_path / "legacy"
        self._make_v3(home)

        with Workspace.open(home) as ws:
            row = ws.execute(
                "SELECT run_id FROM operation WHERE id = 1"
            ).fetchone()
        assert row["run_id"] is None

    def test_a_migrated_workspace_can_still_open_a_run(self, tmp_path: Path):
        """The migration has to leave the table usable, not merely present."""
        home = tmp_path / "legacy"
        self._make_v3(home)

        with Workspace.open(home) as ws:
            run_id = open_run(ws, "legacy", "gather_evidence")
            assert run_id > 0
