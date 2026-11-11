"""Tests for the rule catalogue.

Rules are declared by people, not inferred from code (D-038). The tests that
matter most are the ones about *coverage*: a catalogue only knows the rules
someone declared, so what it fails to claim must stay visible.
"""

from __future__ import annotations

import sqlite3

from pathlib import Path

import pytest

from constat.errors import AlreadyRegistered, NotRegistered
from constat.store import Catalogue, Registry, Workspace

from helpers import commit_file, git


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


@pytest.fixture
def catalogue(workspace: Workspace) -> Catalogue:
    return Catalogue(workspace)


def a_rule(catalogue: Catalogue, name: str = "daily-limit") -> None:
    catalogue.add_rule(name, "A customer may transfer at most the daily limit.")


class TestDeclaring:
    def test_a_rule_is_declared_with_a_business_statement(self, catalogue: Catalogue):
        rule = catalogue.add_rule(
            "daily-limit", "A customer may transfer at most the daily limit."
        )
        assert rule.name == "daily-limit"
        assert "daily limit" in rule.statement
        assert rule.behaviours == ()
        assert rule.anchors == ()

    def test_a_rule_cannot_be_declared_twice(self, catalogue: Catalogue):
        a_rule(catalogue)
        with pytest.raises(AlreadyRegistered, match="already exists"):
            a_rule(catalogue)

    def test_behaviours_are_added_to_a_rule(self, catalogue: Catalogue):
        a_rule(catalogue)
        catalogue.add_behaviour("daily-limit", "A transfer above the limit is refused.")
        rule = catalogue.add_behaviour("daily-limit", "The limit resets at midnight.")

        assert len(rule.behaviours) == 2
        assert [b.description for b in rule.behaviours] == sorted(
            b.description for b in rule.behaviours
        )

    def test_a_duplicate_behaviour_is_refused(self, catalogue: Catalogue):
        a_rule(catalogue)
        catalogue.add_behaviour("daily-limit", "Refused above the limit.")
        with pytest.raises(AlreadyRegistered, match="already has that behaviour"):
            catalogue.add_behaviour("daily-limit", "Refused above the limit.")

    def test_a_behaviour_needs_an_existing_rule(self, catalogue: Catalogue):
        with pytest.raises(NotRegistered, match="no rule"):
            catalogue.add_behaviour("nonexistent", "Something.")

    def test_the_error_lists_declared_rules(self, catalogue: Catalogue):
        a_rule(catalogue)
        with pytest.raises(NotRegistered) as exc:
            catalogue.add_behaviour("typo", "Something.")
        assert "daily-limit" in str(exc.value)

    def test_an_anchor_can_be_scoped_to_a_repository(
        self, workspace: Workspace, catalogue: Catalogue, tmp_path: Path
    ):
        source = tmp_path / "src"
        source.mkdir()
        git(source, "init", "--initial-branch=main", "--quiet")
        commit_file(source, "a.py", "x\n", "Initial")
        clone = tmp_path / "clone"
        git(tmp_path, "clone", "--quiet", str(source), str(clone))
        Registry(workspace).add(str(clone), alias="billing")

        a_rule(catalogue)
        rule = catalogue.add_anchor("daily-limit", "rules.py", "billing")

        assert rule.anchors[0].repository_alias == "billing"

    def test_an_unscoped_anchor_applies_to_any_repository(self, catalogue: Catalogue):
        a_rule(catalogue)
        rule = catalogue.add_anchor("daily-limit", "**/rules.py")
        assert rule.anchors[0].repository_alias is None

    def test_an_anchor_for_an_unknown_repository_is_refused(self, catalogue: Catalogue):
        a_rule(catalogue)
        with pytest.raises(NotRegistered, match="no repository"):
            catalogue.add_anchor("daily-limit", "rules.py", "nope")

    def test_a_duplicate_anchor_is_refused(self, catalogue: Catalogue):
        a_rule(catalogue)
        catalogue.add_anchor("daily-limit", "rules.py")
        with pytest.raises(AlreadyRegistered, match="already has that anchor"):
            catalogue.add_anchor("daily-limit", "rules.py")

    def test_a_rule_cannot_be_deleted(
        self, workspace: Workspace, catalogue: Catalogue
    ):
        """D-048: supersession replaces removal, enforced by trigger.

        A catalogue that can be emptied by a `DELETE` is protected by
        convention only, and the convention is what a future bug forgets —
        the same reasoning as `document_version` (CON-31).
        """
        a_rule(catalogue)

        with pytest.raises(sqlite3.DatabaseError, match="cannot be removed"):
            workspace.execute("DELETE FROM rule WHERE name = 'daily-limit'")

        assert len(catalogue.list()) == 1

    def test_the_storage_api_has_no_removal(self):
        """The command went, and so did the method behind it. Leaving the
        method would make the prohibition a CLI detail rather than a rule."""
        assert not hasattr(Catalogue, "remove_rule")

    def test_the_schema_no_longer_makes_a_name_unique(self, workspace: Workspace):
        """`rule.name` lost UNIQUE (D-050): a name is a label that may change
        between versions, and identity is the surrogate id.

        Asserted against the schema, not through `Catalogue`, because the
        application API is still name-keyed — `add_rule` keeps its own
        duplicate guard and `find` looks up by name. That guard is a leftover
        of the pre-D-050 model and goes when the catalogue becomes id-keyed and
        versioned (CON-43). The constraint it used to rely on is gone now, so
        this records which half has moved.
        """
        now = "2026-11-11T00:00:00Z"
        workspace.execute(
            "INSERT INTO rule (name, statement, created_at) VALUES (?, ?, ?)",
            ("daily-limit", "One reading.", now),
        )
        workspace.execute(
            "INSERT INTO rule (name, statement, created_at) VALUES (?, ?, ?)",
            ("daily-limit", "A different reading of the same name.", now),
        )

        count = workspace.execute(
            "SELECT COUNT(*) c FROM rule WHERE name = 'daily-limit'"
        ).fetchone()["c"]
        assert count == 2


class TestMatching:
    def test_a_changed_path_matches_its_rule(self, catalogue: Catalogue):
        a_rule(catalogue)
        catalogue.add_anchor("daily-limit", "rules.py")

        hits = catalogue.rules_matching("billing", ("rules.py", "unrelated.py"))
        assert hits == {"daily-limit": ("rules.py",)}

    def test_a_glob_matches_several_paths(self, catalogue: Catalogue):
        a_rule(catalogue)
        catalogue.add_anchor("daily-limit", "billing/*.py")

        hits = catalogue.rules_matching(
            "billing", ("billing/a.py", "billing/b.py", "other/c.py")
        )
        assert hits["daily-limit"] == ("billing/a.py", "billing/b.py")

    def test_a_scoped_anchor_ignores_other_repositories(
        self, workspace: Workspace, catalogue: Catalogue, tmp_path: Path
    ):
        source = tmp_path / "src"
        source.mkdir()
        git(source, "init", "--initial-branch=main", "--quiet")
        commit_file(source, "a.py", "x\n", "Initial")
        clone = tmp_path / "clone"
        git(tmp_path, "clone", "--quiet", str(source), str(clone))
        Registry(workspace).add(str(clone), alias="billing")

        a_rule(catalogue)
        catalogue.add_anchor("daily-limit", "rules.py", "billing")

        assert catalogue.rules_matching("billing", ("rules.py",))
        assert catalogue.rules_matching("other-repo", ("rules.py",)) == {}

    def test_an_unanchored_rule_never_matches(self, catalogue: Catalogue):
        """A rule with no anchors cannot be tied to any change, which is why
        the CLI says so when one is declared."""
        a_rule(catalogue)
        assert catalogue.rules_matching("billing", ("rules.py",)) == {}

    def test_two_rules_can_claim_one_path(self, catalogue: Catalogue):
        catalogue.add_rule("limit", "Transfer limit.")
        catalogue.add_rule("audit", "Transfers are audited.")
        catalogue.add_anchor("limit", "rules.py")
        catalogue.add_anchor("audit", "rules.py")

        hits = catalogue.rules_matching("billing", ("rules.py",))
        assert set(hits) == {"audit", "limit"}

    def test_matching_is_deterministic(self, catalogue: Catalogue):
        a_rule(catalogue)
        catalogue.add_anchor("daily-limit", "*.py")
        paths = ("b.py", "a.py", "c.py")
        assert catalogue.rules_matching("billing", paths) == catalogue.rules_matching(
            "billing", paths
        )


class TestCoverage:
    """The catalogue's failure mode is what it does not claim (D-038)."""

    def test_unclaimed_paths_are_reported(self, catalogue: Catalogue):
        a_rule(catalogue)
        catalogue.add_anchor("daily-limit", "rules.py")

        unmatched = catalogue.unmatched_paths(
            "billing", ("rules.py", "eligibility.py", "report.py")
        )
        assert unmatched == ("eligibility.py", "report.py")

    def test_everything_is_unclaimed_when_no_rules_exist(self, catalogue: Catalogue):
        """An empty catalogue must not look like "nothing was affected"."""
        paths = ("a.py", "b.py")
        assert catalogue.unmatched_paths("billing", paths) == ("a.py", "b.py")

    def test_nothing_is_unclaimed_when_all_paths_are_anchored(
        self, catalogue: Catalogue
    ):
        a_rule(catalogue)
        catalogue.add_anchor("daily-limit", "*.py")
        assert catalogue.unmatched_paths("billing", ("a.py", "b.py")) == ()

    def test_a_path_claimed_by_any_rule_is_covered(self, catalogue: Catalogue):
        catalogue.add_rule("one", "First.")
        catalogue.add_rule("two", "Second.")
        catalogue.add_anchor("one", "a.py")
        catalogue.add_anchor("two", "b.py")

        assert catalogue.unmatched_paths("billing", ("a.py", "b.py", "c.py")) == ("c.py",)


class TestPersistence:
    def test_the_catalogue_survives_a_restart(self, tmp_path: Path):
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            catalogue = Catalogue(ws)
            catalogue.add_rule("daily-limit", "At most the daily limit.")
            catalogue.add_behaviour("daily-limit", "Refused above the limit.")
            catalogue.add_anchor("daily-limit", "rules.py")

        with Workspace.open(home) as ws:
            rule = Catalogue(ws).find("daily-limit")

        assert rule is not None
        assert len(rule.behaviours) == 1
        assert len(rule.anchors) == 1
        assert rule.created_at.tzinfo is not None

    def test_rules_are_listed_by_name(self, catalogue: Catalogue):
        catalogue.add_rule("zebra", "Z.")
        catalogue.add_rule("apple", "A.")
        assert [r.name for r in catalogue.list()] == ["apple", "zebra"]
