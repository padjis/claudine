"""Tests for workspace storage.

Done-when for CON-31 is "a restart does not lose registered repositories,
tickets or documents", so persistence across reopen is tested directly rather
than inferred from a successful insert.

The append-only tests matter most: ARCHITECTURE.md section 5 rules 1-3 are
enforced by database triggers, and a trigger that does not fire is worse than
no trigger, because it looks like protection.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from constat.errors import ConstatError, WorkspaceError, WorkspaceVersionError
from constat.store import SCHEMA_VERSION, Workspace, database_path, utc_now, workspace_home


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "workspace-home"


@pytest.fixture
def workspace(home: Path):
    with Workspace.create(home) as ws:
        yield ws


def add_repository(ws: Workspace, alias: str = "subject-a") -> int:
    cursor = ws.execute(
        "INSERT INTO repository (alias, source, source_kind, added_at) "
        "VALUES (?, ?, 'local', ?)",
        (alias, f"/somewhere/{alias}", utc_now()),
    )
    return int(cursor.lastrowid)


def add_ticket(ws: Workspace, reference: str = "CON-31") -> int:
    cursor = ws.execute(
        "INSERT INTO ticket (reference, created_at) VALUES (?, ?)",
        (reference, utc_now()),
    )
    return int(cursor.lastrowid)


def add_document(ws: Workspace, ticket_id: int) -> int:
    now = utc_now()
    cursor = ws.execute(
        "INSERT INTO document (ticket_id, created_at, updated_at, body) "
        "VALUES (?, ?, ?, ?)",
        (ticket_id, now, now, "draft body"),
    )
    return int(cursor.lastrowid)


def approve(ws: Workspace, document_id: int, version_no: int, content: str) -> int:
    cursor = ws.execute(
        "INSERT INTO document_version "
        "(document_id, version_no, content, content_hash, decision, "
        " decided_by, decided_at) "
        "VALUES (?, ?, ?, ?, 'approved', 'Reviewer', ?)",
        (document_id, version_no, content, f"hash-{version_no}", utc_now()),
    )
    return int(cursor.lastrowid)


class TestLocation:
    def test_explicit_path_wins(self, tmp_path: Path):
        assert workspace_home(tmp_path / "here") == tmp_path / "here"

    def test_environment_variable_is_used(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("CONSTAT_HOME", str(tmp_path / "from-env"))
        assert workspace_home() == tmp_path / "from-env"

    def test_default_is_under_the_user_home(self, monkeypatch):
        monkeypatch.delenv("CONSTAT_HOME", raising=False)
        assert workspace_home() == Path("~/.constat").expanduser()

    def test_database_sits_inside_the_home(self, tmp_path: Path):
        assert database_path(tmp_path).parent == tmp_path
        assert database_path(tmp_path).name == "workspace.db"


class TestLifecycle:
    def test_create_builds_the_schema(self, home: Path):
        with Workspace.create(home) as ws:
            tables = {
                row["name"]
                for row in ws.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert {
            "schema_meta",
            "repository",
            "ticket",
            "document",
            "document_version",
            "operation",
        } <= tables

    def test_create_records_the_schema_version(self, workspace: Workspace):
        assert workspace.schema_version == SCHEMA_VERSION

    def test_create_records_the_constat_version(self, workspace: Workspace):
        import constat

        row = workspace.execute("SELECT constat_version FROM schema_meta").fetchone()
        assert row["constat_version"] == constat.__version__

    def test_create_refuses_to_overwrite(self, home: Path):
        """Stored decisions must never be destroyed by a second `init`."""
        Workspace.create(home).close()
        with pytest.raises(WorkspaceError, match="already exists"):
            Workspace.create(home)

    def test_open_requires_an_existing_workspace(self, home: Path):
        with pytest.raises(WorkspaceError, match="no workspace at"):
            Workspace.open(home)

    def test_open_or_create_is_idempotent(self, home: Path):
        first = Workspace.open_or_create(home)
        first.close()
        second = Workspace.open_or_create(home)
        second.close()
        assert database_path(home).exists()

    def test_a_non_workspace_file_is_refused(self, tmp_path: Path):
        home = tmp_path / "junk"
        home.mkdir()
        (home / "workspace.db").write_text("this is not a database")

        with pytest.raises(WorkspaceError):
            Workspace.open(home)

    def test_context_manager_closes(self, home: Path):
        with Workspace.create(home) as ws:
            connection = ws.connection
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


class TestSchemaVersioning:
    def test_a_newer_schema_is_refused_rather_than_read(self, home: Path):
        """Reading records under a schema we do not understand risks
        misinterpreting an approval. Failing to open is the safer outcome."""
        Workspace.create(home).close()
        connection = sqlite3.connect(database_path(home))
        connection.execute("UPDATE schema_meta SET schema_version = 99 WHERE id = 1")
        connection.commit()
        connection.close()

        with pytest.raises(WorkspaceVersionError, match="version 99"):
            Workspace.open(home)

    def test_an_older_schema_with_no_migration_path_is_refused(self, home: Path):
        Workspace.create(home).close()
        connection = sqlite3.connect(database_path(home))
        connection.execute("UPDATE schema_meta SET schema_version = 0 WHERE id = 1")
        connection.commit()
        connection.close()

        with pytest.raises(WorkspaceVersionError, match="no migration"):
            Workspace.open(home)

    def test_version_errors_are_catchable_as_workspace_errors(self):
        assert issubclass(WorkspaceVersionError, WorkspaceError)
        assert issubclass(WorkspaceError, ConstatError)


class TestPersistence:
    def test_repositories_survive_a_restart(self, home: Path):
        with Workspace.create(home) as ws:
            add_repository(ws, "subject-a")
            add_repository(ws, "subject-b")

        with Workspace.open(home) as ws:
            aliases = [
                row["alias"]
                for row in ws.execute("SELECT alias FROM repository ORDER BY alias")
            ]
        assert aliases == ["subject-a", "subject-b"]

    def test_tickets_and_documents_survive_a_restart(self, home: Path):
        with Workspace.create(home) as ws:
            document_id = add_document(ws, add_ticket(ws, "CON-31"))
            approve(ws, document_id, 1, "approved content")

        with Workspace.open(home) as ws:
            assert ws.execute("SELECT COUNT(*) c FROM ticket").fetchone()["c"] == 1
            assert ws.execute("SELECT COUNT(*) c FROM document").fetchone()["c"] == 1
            row = ws.execute("SELECT content FROM document_version").fetchone()
            assert row["content"] == "approved content"

    def test_a_ticket_reference_is_unique(self, workspace: Workspace):
        add_ticket(workspace, "CON-31")
        with pytest.raises(sqlite3.IntegrityError):
            add_ticket(workspace, "CON-31")

    def test_a_repository_alias_is_unique(self, workspace: Workspace):
        add_repository(workspace, "subject-a")
        with pytest.raises(sqlite3.IntegrityError):
            add_repository(workspace, "subject-a")

    def test_a_ticket_owns_at_most_one_document(self, workspace: Workspace):
        """One living document per ticket is the model, not an optimisation
        (D-029)."""
        ticket_id = add_ticket(workspace)
        add_document(workspace, ticket_id)
        with pytest.raises(sqlite3.IntegrityError):
            add_document(workspace, ticket_id)

    def test_source_kind_is_constrained(self, workspace: Workspace):
        with pytest.raises(sqlite3.IntegrityError):
            workspace.execute(
                "INSERT INTO repository (alias, source, source_kind, added_at) "
                "VALUES ('x', '/x', 'carrier-pigeon', ?)",
                (utc_now(),),
            )

    def test_foreign_keys_are_enforced(self, workspace: Workspace):
        """SQLite leaves these off by default, so it has to be asked for."""
        with pytest.raises(sqlite3.IntegrityError):
            workspace.execute(
                "INSERT INTO document (ticket_id, created_at, updated_at) "
                "VALUES (9999, ?, ?)",
                (utc_now(), utc_now()),
            )


class TestAppendOnlyHistory:
    """ARCHITECTURE.md section 5, rules 1-3. Enforced by triggers, because
    application-level immutability is a convention a future bug can break."""

    def test_an_approved_version_cannot_be_updated(self, workspace: Workspace):
        document_id = add_document(workspace, add_ticket(workspace))
        approve(workspace, document_id, 1, "original")

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            workspace.execute(
                "UPDATE document_version SET content = 'tampered' WHERE id = 1"
            )

    def test_an_approved_version_cannot_be_deleted(self, workspace: Workspace):
        document_id = add_document(workspace, add_ticket(workspace))
        approve(workspace, document_id, 1, "original")

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            workspace.execute("DELETE FROM document_version WHERE id = 1")

    def test_a_later_approval_creates_a_new_version(self, workspace: Workspace):
        document_id = add_document(workspace, add_ticket(workspace))
        approve(workspace, document_id, 1, "first")
        approve(workspace, document_id, 2, "second")

        contents = [
            row["content"]
            for row in workspace.execute(
                "SELECT content FROM document_version ORDER BY version_no"
            )
        ]
        assert contents == ["first", "second"]

    def test_earlier_content_remains_recoverable(self, workspace: Workspace):
        """The integrity rule that matters most: a later approval must not
        make an earlier one unreadable."""
        document_id = add_document(workspace, add_ticket(workspace))
        approve(workspace, document_id, 1, "the originally approved text")
        approve(workspace, document_id, 2, "a revised text")

        row = workspace.execute(
            "SELECT content FROM document_version WHERE version_no = 1"
        ).fetchone()
        assert row["content"] == "the originally approved text"

    def test_version_numbers_are_unique_per_document(self, workspace: Workspace):
        document_id = add_document(workspace, add_ticket(workspace))
        approve(workspace, document_id, 1, "first")
        with pytest.raises(sqlite3.IntegrityError):
            approve(workspace, document_id, 1, "a second version one")

    def test_a_rejection_is_recorded_and_kept(self, workspace: Workspace):
        """Rejections stay traceable too (product rule 5), not just approvals."""
        document_id = add_document(workspace, add_ticket(workspace))
        workspace.execute(
            "INSERT INTO document_version "
            "(document_id, version_no, content, content_hash, decision, "
            " decided_by, decided_at, rationale) "
            "VALUES (?, 1, 'rejected draft', 'h', 'rejected', 'Reviewer', ?, ?)",
            (document_id, utc_now(), "not supported by the evidence"),
        )

        row = workspace.execute(
            "SELECT decision, rationale FROM document_version"
        ).fetchone()
        assert row["decision"] == "rejected"
        assert row["rationale"] == "not supported by the evidence"

    def test_an_unknown_decision_is_refused(self, workspace: Workspace):
        """Only an explicit human decision counts (product rule 4)."""
        document_id = add_document(workspace, add_ticket(workspace))
        with pytest.raises(sqlite3.IntegrityError):
            workspace.execute(
                "INSERT INTO document_version "
                "(document_id, version_no, content, content_hash, decision, "
                " decided_by, decided_at) "
                "VALUES (?, 1, 'c', 'h', 'probably-fine', 'Reviewer', ?)",
                (document_id, utc_now()),
            )

    def test_deleting_a_ticket_cannot_orphan_approved_history(self, workspace: Workspace):
        """Documents cascade from tickets, but approved versions must not
        silently disappear with them."""
        ticket_id = add_ticket(workspace)
        document_id = add_document(workspace, ticket_id)
        approve(workspace, document_id, 1, "approved")

        with pytest.raises(sqlite3.IntegrityError):
            workspace.execute("DELETE FROM ticket WHERE id = ?", (ticket_id,))


class TestOperations:
    def test_an_operation_is_recorded_against_a_document(self, workspace: Workspace):
        """Without this a document becomes unattributable prose (D-029)."""
        repository_id = add_repository(workspace)
        document_id = add_document(workspace, add_ticket(workspace))
        workspace.execute(
            "INSERT INTO operation (document_id, repository_id, kind, ran_at, summary) "
            "VALUES (?, ?, 'collect_evidence', ?, '29 files')",
            (document_id, repository_id, utc_now()),
        )

        row = workspace.execute(
            "SELECT kind, summary, repository_id FROM operation"
        ).fetchone()
        assert row["kind"] == "collect_evidence"
        assert row["repository_id"] == repository_id

    def test_operations_survive_a_restart(self, home: Path):
        with Workspace.create(home) as ws:
            document_id = add_document(ws, add_ticket(ws))
            ws.execute(
                "INSERT INTO operation (document_id, kind, ran_at) "
                "VALUES (?, 'collect_evidence', ?)",
                (document_id, utc_now()),
            )

        with Workspace.open(home) as ws:
            assert ws.execute("SELECT COUNT(*) c FROM operation").fetchone()["c"] == 1


class TestMigration:
    """A version bump carries a migration, not a refusal.

    A governance tool that discarded stored decisions whenever its schema
    changed would contradict product rule 5 on the one surface where it
    matters most.
    """

    # A frozen copy of schema version 1, not derived from the current one.
    # Deriving it would make this test rebuild itself on every schema change,
    # so it would stop testing the migration it claims to test.
    V1 = """
    CREATE TABLE schema_meta (
        id INTEGER PRIMARY KEY CHECK (id = 1), schema_version INTEGER NOT NULL,
        constat_version TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE repository (
        id INTEGER PRIMARY KEY, alias TEXT NOT NULL UNIQUE, source TEXT NOT NULL,
        source_kind TEXT NOT NULL CHECK (source_kind IN ('local', 'remote')),
        cache_path TEXT, identity TEXT, default_branch TEXT,
        added_at TEXT NOT NULL, last_fetched_at TEXT);
    CREATE TABLE ticket (
        id INTEGER PRIMARY KEY, reference TEXT NOT NULL UNIQUE, title TEXT,
        created_at TEXT NOT NULL);
    CREATE TABLE document (
        id INTEGER PRIMARY KEY,
        ticket_id INTEGER NOT NULL UNIQUE REFERENCES ticket(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '');
    CREATE TABLE document_version (
        id INTEGER PRIMARY KEY,
        document_id INTEGER NOT NULL REFERENCES document(id),
        version_no INTEGER NOT NULL, content TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        previous_version_id INTEGER REFERENCES document_version(id),
        decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
        decided_by TEXT NOT NULL, decided_at TEXT NOT NULL, rationale TEXT,
        UNIQUE (document_id, version_no));
    CREATE TABLE operation (
        id INTEGER PRIMARY KEY,
        document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
        repository_id INTEGER REFERENCES repository(id),
        kind TEXT NOT NULL, ran_at TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '', payload TEXT);
    """

    def _make_v1(self, home: Path) -> None:
        """Build a workspace at schema version 1, title column and all."""
        home.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(home / "workspace.db")
        connection.executescript(self.V1)
        connection.execute(
            "INSERT INTO schema_meta (id, schema_version, constat_version, created_at) "
            "VALUES (1, 1, '0.0.1', ?)",
            (utc_now(),),
        )
        connection.execute(
            "INSERT INTO ticket (reference, title, created_at) "
            "VALUES ('622', 'A title', ?)",
            (utc_now(),),
        )
        connection.commit()
        connection.close()

    def test_a_v1_workspace_is_migrated_on_open(self, home: Path):
        self._make_v1(home)
        with Workspace.open(home) as ws:
            assert ws.schema_version == SCHEMA_VERSION

    def test_migration_preserves_the_stored_ticket(self, home: Path):
        """Dropping a column must not drop the row."""
        self._make_v1(home)
        with Workspace.open(home) as ws:
            row = ws.execute("SELECT reference FROM ticket").fetchone()
        assert row["reference"] == "622"

    def test_migration_removes_the_title_column(self, home: Path):
        self._make_v1(home)
        with Workspace.open(home) as ws:
            columns = {
                r["name"] for r in ws.execute("PRAGMA table_info(ticket)")
            }
        assert "title" not in columns
        assert {"id", "reference", "created_at"} <= columns

    def test_migration_adds_the_catalogue_tables(self, home: Path):
        """v2 -> v3 brings the rule catalogue (D-038)."""
        self._make_v1(home)
        with Workspace.open(home) as ws:
            tables = {
                r["name"]
                for r in ws.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        assert {"rule", "behaviour", "anchor"} <= tables

    def test_migration_runs_every_step_in_order(self, home: Path):
        """A v1 workspace must cross every step, not just the first.

        Asserted against `SCHEMA_VERSION` rather than a literal so a later
        bump that forgets its migration fails here instead of quietly
        rewriting the expectation.
        """
        self._make_v1(home)
        with Workspace.open(home) as ws:
            assert ws.schema_version == SCHEMA_VERSION
            columns = {r["name"] for r in ws.execute("PRAGMA table_info(ticket)")}
            tables = {
                r["name"]
                for r in ws.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        assert "title" not in columns  # step 1 -> 2
        assert "rule" in tables  # step 2 -> 3
        assert "run" in tables  # step 3 -> 4

    def test_migration_is_persisted_not_repeated(self, home: Path):
        self._make_v1(home)
        Workspace.open(home).close()

        connection = sqlite3.connect(home / "workspace.db")
        stored = connection.execute(
            "SELECT schema_version FROM schema_meta"
        ).fetchone()[0]
        connection.close()
        assert stored == SCHEMA_VERSION

    def test_a_version_with_no_migration_is_still_refused(self, home: Path):
        """Migrating is the rule; guessing is not."""
        Workspace.create(home).close()
        connection = sqlite3.connect(home / "workspace.db")
        connection.execute("UPDATE schema_meta SET schema_version = -5 WHERE id = 1")
        connection.commit()
        connection.close()

        with pytest.raises(WorkspaceVersionError, match="no migration"):
            Workspace.open(home)
