"""The rule catalogue (D-038).

Business rules are declared by people, not inferred from code. Each rule
carries its behaviours and anchors — the paths whose code is understood to
implement it.

Nothing here decides what a behaviour *does*. Anchors let Constat say "the
code behind this behaviour changed in this ticket", which is a statement about
code. What it now does is for a reviewer to state.
"""

from __future__ import annotations

from datetime import datetime

from ..globs import matches_path
from ..errors import AlreadyRegistered, NotRegistered
from ..models import Anchor, Behaviour, Rule
from .workspace import Workspace, utc_now


class Catalogue:
    """Declared business rules in a workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    # -- writing -----------------------------------------------------------

    def add_rule(self, name: str, statement: str) -> Rule:
        if self.find(name) is not None:
            raise AlreadyRegistered(
                f"rule {name!r} already exists. Add behaviours or anchors to "
                "it rather than declaring it twice."
            )
        self._workspace.execute(
            "INSERT INTO rule (name, statement, created_at) VALUES (?, ?, ?)",
            (name, statement, utc_now()),
        )
        found = self.find(name)
        assert found is not None  # just inserted
        return found

    def add_behaviour(self, rule_name: str, description: str) -> Rule:
        rule_id = self._rule_id(rule_name)
        existing = self._workspace.execute(
            "SELECT 1 FROM behaviour WHERE rule_id = ? AND description = ?",
            (rule_id, description),
        ).fetchone()
        if existing:
            raise AlreadyRegistered(
                f"rule {rule_name!r} already has that behaviour."
            )
        self._workspace.execute(
            "INSERT INTO behaviour (rule_id, description, created_at) "
            "VALUES (?, ?, ?)",
            (rule_id, description, utc_now()),
        )
        found = self.find(rule_name)
        assert found is not None
        return found

    def add_anchor(
        self, rule_name: str, path_glob: str, repository_alias: str | None = None
    ) -> Rule:
        rule_id = self._rule_id(rule_name)
        repository_id = None
        if repository_alias is not None:
            row = self._workspace.execute(
                "SELECT id FROM repository WHERE alias = ?", (repository_alias,)
            ).fetchone()
            if row is None:
                raise NotRegistered(
                    f"no repository registered as {repository_alias!r}."
                )
            repository_id = int(row["id"])

        existing = self._workspace.execute(
            "SELECT 1 FROM anchor WHERE rule_id = ? "
            "AND IFNULL(repository_id, -1) = IFNULL(?, -1) AND path_glob = ?",
            (rule_id, repository_id, path_glob),
        ).fetchone()
        if existing:
            raise AlreadyRegistered(
                f"rule {rule_name!r} already has that anchor."
            )

        self._workspace.execute(
            "INSERT INTO anchor (rule_id, repository_id, path_glob, created_at) "
            "VALUES (?, ?, ?, ?)",
            (rule_id, repository_id, path_glob, utc_now()),
        )
        found = self.find(rule_name)
        assert found is not None
        return found

    # -- reading -----------------------------------------------------------

    def find(self, name: str) -> Rule | None:
        row = self._workspace.execute(
            "SELECT * FROM rule WHERE name = ?", (name,)
        ).fetchone()
        return self._hydrate(row) if row else None

    def list(self) -> tuple[Rule, ...]:
        rows = self._workspace.execute("SELECT * FROM rule ORDER BY name").fetchall()
        return tuple(self._hydrate(row) for row in rows)

    def rules_matching(
        self, repository_alias: str, paths: tuple[str, ...]
    ) -> dict[str, tuple[str, ...]]:
        """Rules whose anchors match any of `paths`, with the paths matched.

        A statement about code, not about meaning: these rules' implementations
        were touched. Whether their behaviours changed is a reviewer's call.
        """
        hits: dict[str, list[str]] = {}
        for rule in self.list():
            matched = [
                path
                for path in paths
                for anchor in rule.anchors
                if anchor.repository_alias in (None, repository_alias)
                and matches_path(path, anchor.path_glob)
            ]
            if matched:
                hits[rule.name] = sorted(dict.fromkeys(matched))
        return {name: tuple(paths) for name, paths in sorted(hits.items())}

    def unmatched_paths(
        self, repository_alias: str, paths: tuple[str, ...]
    ) -> tuple[str, ...]:
        """Paths no declared rule claims.

        The catalogue's failure mode, and it must be visible. A document
        listing two impacted rules while silently ignoring eight unanchored
        files is exactly the confident under-report this product exists to
        prevent (D-038).
        """
        claimed = {
            path
            for matched in self.rules_matching(repository_alias, paths).values()
            for path in matched
        }
        return tuple(sorted(set(paths) - claimed))

    # -- internals ---------------------------------------------------------

    def _rule_id(self, name: str) -> int:
        row = self._workspace.execute(
            "SELECT id FROM rule WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            known = ", ".join(r.name for r in self.list()) or "none"
            raise NotRegistered(f"no rule {name!r}. Declared: {known}.")
        return int(row["id"])

    def _hydrate(self, row) -> Rule:
        rule_id = row["id"]
        behaviours = tuple(
            Behaviour(description=b["description"])
            for b in self._workspace.execute(
                "SELECT description FROM behaviour WHERE rule_id = ? "
                "ORDER BY description",
                (rule_id,),
            )
        )
        anchors = tuple(
            Anchor(path_glob=a["path_glob"], repository_alias=a["alias"])
            for a in self._workspace.execute(
                "SELECT a.path_glob, r.alias FROM anchor a "
                "LEFT JOIN repository r ON r.id = a.repository_id "
                "WHERE a.rule_id = ? ORDER BY a.path_glob",
                (rule_id,),
            )
        )
        return Rule(
            name=row["name"],
            statement=row["statement"],
            created_at=datetime.fromisoformat(row["created_at"]),
            behaviours=behaviours,
            anchors=anchors,
        )
