"""The workspace: persistent local state.

Holds registered repositories, tickets, documents and the immutable record of
approvals (D-027, D-029). SQLite, with no service to run (D-002).

Nothing here interprets anything. It stores what it is given and refuses to
open a database it does not understand.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from ..errors import WorkspaceError, WorkspaceVersionError
from .schema import MIGRATIONS, SCHEMA, SCHEMA_VERSION

DEFAULT_HOME = Path("~/.constat")
HOME_ENV = "CONSTAT_HOME"
DB_NAME = "workspace.db"


def workspace_home(override: str | os.PathLike[str] | None = None) -> Path:
    """Where the workspace lives.

    An explicit path wins, then ``CONSTAT_HOME``, then ``~/.constat``.

    This is a default, but not a *silent* one: every command reports the
    workspace it opened. The product rule forbids guessing at analysis inputs
    (PRODUCT_SPEC.md section 7), not at a configuration location that is
    disclosed.
    """
    if override is not None:
        return Path(override).expanduser()
    from_env = os.environ.get(HOME_ENV)
    if from_env:
        return Path(from_env).expanduser()
    return DEFAULT_HOME.expanduser()


def database_path(override: str | os.PathLike[str] | None = None) -> Path:
    return workspace_home(override) / DB_NAME


def utc_now() -> str:
    """Timestamps are UTC and ISO 8601. A governance record whose timestamps
    depend on the reader's timezone is not much of a record."""
    return datetime.now(timezone.utc).isoformat()


class Workspace:
    """An open workspace.

    Usable as a context manager. Connections are not shared between threads;
    a CLI invocation opens one and closes it.
    """

    def __init__(self, connection: sqlite3.Connection, path: Path) -> None:
        self._connection = connection
        self.path = path

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, override: str | os.PathLike[str] | None = None) -> "Workspace":
        """Create a new workspace. Refuses to overwrite an existing one."""
        path = database_path(override)
        if path.exists():
            raise WorkspaceError(
                f"a workspace already exists at {path}. Remove it deliberately "
                "if you mean to start again; Constat will not overwrite stored "
                "decisions."
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        connection = cls._connect(path)
        try:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT INTO schema_meta "
                "(id, schema_version, constat_version, created_at) "
                "VALUES (1, ?, ?, ?)",
                (SCHEMA_VERSION, __version__, utc_now()),
            )
            connection.commit()
        except Exception:
            connection.close()
            path.unlink(missing_ok=True)
            raise
        return cls(connection, path)

    @classmethod
    def open(cls, override: str | os.PathLike[str] | None = None) -> "Workspace":
        """Open an existing workspace, refusing a schema it cannot handle."""
        path = database_path(override)
        if not path.exists():
            raise WorkspaceError(
                f"no workspace at {path}. Run `constat init` to create one."
            )

        connection = cls._connect(path)
        try:
            found = cls._stored_version(connection)
        except Exception:
            connection.close()
            raise

        if found > SCHEMA_VERSION:
            connection.close()
            raise WorkspaceVersionError(
                f"the workspace at {path} uses schema version {found}, but this "
                f"Constat understands version {SCHEMA_VERSION}. Upgrade Constat "
                "rather than letting an older version read records it may "
                "misinterpret."
            )
        if found < SCHEMA_VERSION:
            try:
                cls._migrate(connection, found, path)
            except Exception:
                connection.close()
                raise
        return cls(connection, path)

    @staticmethod
    def _migrate(connection: sqlite3.Connection, found: int, path: Path) -> None:
        """Bring an older workspace up to the current schema.

        Each step runs in a transaction, so a failed migration leaves the
        workspace on its previous version rather than half-converted.
        """
        version = found
        while version < SCHEMA_VERSION:
            step = MIGRATIONS.get(version)
            if step is None:
                raise WorkspaceVersionError(
                    f"the workspace at {path} uses schema version {version} and "
                    f"no migration to {version + 1} exists. Constat will not "
                    "guess at the shape of stored decisions."
                )
            connection.execute("BEGIN")
            try:
                for statement in step:
                    connection.execute(statement)
                connection.execute(
                    "UPDATE schema_meta SET schema_version = ? WHERE id = 1",
                    (version + 1,),
                )
            except Exception:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
            version += 1

    @classmethod
    def open_or_create(cls, override: str | os.PathLike[str] | None = None) -> "Workspace":
        if database_path(override).exists():
            return cls.open(override)
        return cls.create(override)

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            # SQLite leaves foreign keys off by default, so referential
            # integrity has to be asked for on every connection.
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError as exc:
            # Opening a non-database file fails here rather than at the first
            # query. A raw sqlite error would reach the user as a traceback,
            # which is not "fail clearly".
            connection.close()
            raise WorkspaceError(
                f"{path} is not a Constat workspace, or is corrupt: {exc}"
            ) from exc
        return connection

    @staticmethod
    def _stored_version(connection: sqlite3.Connection) -> int:
        try:
            row = connection.execute(
                "SELECT schema_version FROM schema_meta WHERE id = 1"
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise WorkspaceError(
                "this file is not a Constat workspace, or is corrupt."
            ) from exc
        if row is None:
            raise WorkspaceError(
                "this workspace has no schema metadata; it is not a Constat "
                "workspace, or was not created successfully."
            )
        return int(row["schema_version"])

    # -- access ------------------------------------------------------------

    @property
    def schema_version(self) -> int:
        return self._stored_version(self._connection)

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection.

        Typed accessors for repositories, tickets and documents arrive with
        CON-32 and CON-33; this is the seam they will be built on.
        """
        return self._connection

    def execute(self, sql: str, parameters: tuple = ()) -> sqlite3.Cursor:
        return self._connection.execute(sql, parameters)

    @contextmanager
    def transaction(self):
        """Run several statements atomically.

        Needed where a half-finished write would leave a state the model does
        not allow — a ticket without its document, for instance (D-029).
        """
        self._connection.execute("BEGIN")
        try:
            yield self
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        self._connection.execute("COMMIT")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Workspace {self.path} schema={SCHEMA_VERSION}>"
