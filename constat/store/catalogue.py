"""The rule catalogue — read-only (D-038, D-048).

Each rule carries its behaviours and anchors: the paths whose code is
understood to implement it.

**Nothing here writes.** A rule is created by `Review.accept` and by nothing
else, which is what makes "no proposal becomes official without an explicit
human decision" structural rather than a CLI convention. This class used to
carry `add_rule`, `add_behaviour` and `add_anchor`; no command ever reached
them, so they were a writable door into the governance store with nothing
guarding it. They now live in `tests/helpers.py`, where a writable door is
harmless, and a test asserts this class has no write surface.

Their validation went with them — a duplicate-name guard keyed on `name`,
which `test_the_schema_no_longer_makes_a_name_unique` already recorded as a
leftover of the pre-D-050 model. Identity is the surrogate id, and the real
path has its own rules about versions.

Nothing here decides what a behaviour *does*. Anchors let Constat say "the
code behind this behaviour changed in this ticket", which is a statement about
code. What it now does is for a reviewer to state.
"""

from __future__ import annotations

from datetime import datetime

from ..globs import matches_path
from ..models import Anchor, Behaviour, Rule
from .workspace import Workspace


class Catalogue:
    """Declared business rules in a workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

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
