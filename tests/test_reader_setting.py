"""Tests for the reader setting (D-060).

D-059 made a rule-generating command refuse when nothing could read the
evidence, and the signal for "something else will read it" was
`--no-provider` on every invocation. That punished the recommended workflow:
on MCP the host supplies the model, so having no provider is correct.

How evidence gets read belongs to a *setup*, not an invocation. These tests
are mostly about that: the setting is remembered, it is consulted, the default
leans towards the refusal, and an existing workspace does not have one
switched off by a migration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.cli import EXIT_OK, EXIT_PROVIDER, EXIT_USAGE, main
from constat.errors import InvalidInput
from constat.store import READER_MCP, READER_PROVIDER, Settings, TicketStore, Workspace

from test_ai import make_subject


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> str:
    """A workspace with one repository and no provider configured."""
    monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
    ws = str(tmp_path / "ws")
    main(["--workspace", ws, "init"])
    main([
        "--workspace", ws, "repo", "add",
        str(make_subject(tmp_path, "billing")), "--name", "billing",
    ])
    return ws


class TestTheSettingIsConsulted:
    def test_mcp_does_not_ask_for_a_provider(self, home):
        """The point of the whole entry."""
        main(["--workspace", home, "config", "reader", "mcp"])
        assert main(["--workspace", home, "ticket", "add", "622"]) == EXIT_OK

    def test_provider_still_refuses(self, home):
        """D-059 is amended, not reverted. The case it was built for — a
        provider workspace with nothing configured — still fails."""
        assert main(["--workspace", home, "ticket", "add", "622"]) == EXIT_PROVIDER

    def test_document_follows_the_same_setting(self, home):
        main(["--workspace", home, "config", "reader", "mcp"])
        main(["--workspace", home, "ticket", "add", "622"])
        assert main(["--workspace", home, "document", "622"]) == EXIT_OK

    def test_the_setting_survives_the_process(self, home):
        """It is a setup, so it has to outlive the command that set it."""
        main(["--workspace", home, "config", "reader", "mcp"])
        with Workspace.open(home) as ws:
            assert Settings(ws).reader == READER_MCP

    def test_it_can_be_set_at_creation(self, tmp_path: Path):
        ws = str(tmp_path / "fresh")
        assert main(["--workspace", ws, "init", "--reader", "mcp"]) == EXIT_OK
        with Workspace.open(ws) as workspace:
            assert Settings(workspace).reader == READER_MCP

    def test_it_can_be_changed_back(self, home):
        main(["--workspace", home, "config", "reader", "mcp"])
        main(["--workspace", home, "config", "reader", "provider"])
        assert main(["--workspace", home, "ticket", "add", "622"]) == EXIT_PROVIDER


class TestTheDefaultLeansTowardsTheRefusal:
    def test_a_new_workspace_expects_a_provider(self, tmp_path: Path):
        ws = str(tmp_path / "fresh")
        main(["--workspace", ws, "init"])
        with Workspace.open(ws) as workspace:
            assert Settings(workspace).reader == READER_PROVIDER

    def test_a_workspace_that_never_said_is_treated_as_strict(self, home):
        """Belt and braces: even with the row deleted, the default holds."""
        with Workspace.open(home) as ws:
            with ws.transaction() as tx:
                tx.execute("DELETE FROM setting WHERE key = 'reader'")
            assert Settings(ws).reader == READER_PROVIDER

    def test_init_tells_an_mcp_user_what_to_do(self, tmp_path: Path, capsys):
        """The one time they meet this, they should fix it permanently rather
        than learn a flag to repeat."""
        main(["--workspace", str(tmp_path / "fresh"), "init"])
        out = capsys.readouterr().out

        assert "config reader mcp" in out

    def test_the_refusal_names_the_cure_first(self, home, capsys):
        main(["--workspace", home, "ticket", "add", "622"])
        err = capsys.readouterr().err

        assert "constat config reader mcp" in err
        assert err.index("config reader mcp") < err.index("CONSTAT_AI_PROVIDER=anthropic")


class TestTheOverrideStillWorks:
    def test_no_provider_works_on_a_provider_workspace(self, home):
        """The genuine one-off: gather evidence without spending anything."""
        code = main([
            "--workspace", home, "ticket", "add", "622", "--no-provider"
        ])
        assert code == EXIT_OK

    def test_it_does_not_change_the_setting(self, home):
        """A per-run override must not quietly reconfigure the workspace."""
        main(["--workspace", home, "ticket", "add", "622", "--no-provider"])
        with Workspace.open(home) as ws:
            assert Settings(ws).reader == READER_PROVIDER


class TestMigrationDoesNotChangeBehaviour:
    def test_an_existing_workspace_becomes_strict(self, tmp_path: Path):
        """Schema 7 had no setting, and refused without a provider. Migrating
        it to `mcp` would silently switch that off — a migration must not
        change behaviour on a guess."""
        import sqlite3

        ws = str(tmp_path / "old")
        main(["--workspace", ws, "init"])
        db = Path(ws) / "workspace.db"

        # Rewind to schema 7 as a workspace created yesterday would be.
        connection = sqlite3.connect(db)
        connection.execute("DROP TABLE setting")
        connection.execute("UPDATE schema_meta SET schema_version = 7")
        connection.commit()
        connection.close()

        with Workspace.open(ws) as workspace:   # migrates 7 -> 8
            assert workspace.schema_version == 8
            assert Settings(workspace).reader == READER_PROVIDER


class TestTheSettingIsValidated:
    def test_an_unknown_reader_is_refused(self, home):
        with Workspace.open(home) as ws:
            with pytest.raises(InvalidInput, match="must be one of"):
                Settings(ws).set_reader("telepathy")

    def test_the_cli_refuses_one_too(self, home):
        with pytest.raises(SystemExit):   # argparse choices
            main(["--workspace", home, "config", "reader", "telepathy"])

    def test_settings_are_not_append_only(self, home):
        """Deliberately unlike every other table here. A setting says how the
        workspace is operated, never what anyone decided, so a history of
        changes would imply an authority it does not have."""
        with Workspace.open(home) as ws:
            settings = Settings(ws)
            settings.set_reader(READER_MCP)
            settings.set_reader(READER_PROVIDER)

            rows = ws.execute("SELECT * FROM setting WHERE key = 'reader'").fetchall()
            assert len(rows) == 1
