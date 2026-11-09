"""The repository registry (D-027, CON-32).

Add, list and remove the repositories a workspace knows about. Registration
resolves and stores two things that must not be re-guessed later: the
repository's durable identity (D-025) and its default branch (D-028).
"""

from __future__ import annotations

from datetime import datetime

from ..errors import AlreadyRegistered, NotRegistered
from ..git.adapter import Repository, discover_repository, resolve_default_branch, root_commits
from ..git.adapter import Revision
from ..models import RegisteredRepository
from .workspace import Workspace, utc_now


def _row_to_model(row) -> RegisteredRepository:
    return RegisteredRepository(
        alias=row["alias"],
        source=row["source"],
        source_kind=row["source_kind"],
        identity=row["identity"],
        default_branch=row["default_branch"],
        added_at=datetime.fromisoformat(row["added_at"]),
        cache_path=row["cache_path"],
        last_fetched_at=(
            datetime.fromisoformat(row["last_fetched_at"])
            if row["last_fetched_at"]
            else None
        ),
    )


def _identity_of(repo: Repository, default_branch: str) -> str:
    """The repository's durable identity, read from the default branch."""
    tip = Revision(symbolic=default_branch, sha=_resolve(repo, default_branch))
    return min(root_commits(repo, tip))


def _resolve(repo: Repository, symbolic: str) -> str:
    from ..git.adapter import resolve_revision

    return resolve_revision(repo, symbolic).sha


class Registry:
    """Repositories known to a workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def add(
        self,
        path: str,
        alias: str | None = None,
        default_branch: str | None = None,
    ) -> RegisteredRepository:
        """Register a local repository.

        Raises the existing repository errors for a bad path, so "that is not
        a repository" is reported the same way everywhere. Remote URLs arrive
        with CON-35.
        """
        repo = discover_repository(path)
        branch = default_branch or resolve_default_branch(repo)
        identity = _identity_of(repo, branch)
        name = alias or repo.root.name

        existing = self.find_by_identity(identity)
        if existing is not None:
            raise AlreadyRegistered(
                f"this repository is already registered as {existing.alias!r} "
                f"({existing.source}). It is the same repository: both share "
                f"root commit {identity[:12]}. Remove the existing entry first "
                "if you mean to re-register it."
            )
        if self.find(name) is not None:
            raise AlreadyRegistered(
                f"an unrelated repository is already registered as {name!r}. "
                "Choose another alias with --name."
            )

        self._workspace.execute(
            "INSERT INTO repository "
            "(alias, source, source_kind, cache_path, identity, "
            " default_branch, added_at) "
            "VALUES (?, ?, 'local', NULL, ?, ?, ?)",
            (name, str(repo.root), identity, branch, utc_now()),
        )
        found = self.find(name)
        assert found is not None  # just inserted
        return found

    def find(self, alias: str) -> RegisteredRepository | None:
        row = self._workspace.execute(
            "SELECT * FROM repository WHERE alias = ?", (alias,)
        ).fetchone()
        return _row_to_model(row) if row else None

    def find_by_identity(self, identity: str) -> RegisteredRepository | None:
        row = self._workspace.execute(
            "SELECT * FROM repository WHERE identity = ?", (identity,)
        ).fetchone()
        return _row_to_model(row) if row else None

    def list(self) -> tuple[RegisteredRepository, ...]:
        rows = self._workspace.execute(
            "SELECT * FROM repository ORDER BY alias"
        ).fetchall()
        return tuple(_row_to_model(row) for row in rows)

    def remove(self, alias: str) -> RegisteredRepository:
        """Unregister a repository.

        Removes Constat's knowledge of it and nothing else: the repository on
        disk is untouched, because Constat is read-only against it.
        """
        found = self.find(alias)
        if found is None:
            known = ", ".join(r.alias for r in self.list()) or "none"
            raise NotRegistered(
                f"no repository registered as {alias!r}. Registered: {known}."
            )
        self._workspace.execute("DELETE FROM repository WHERE alias = ?", (alias,))
        return found
