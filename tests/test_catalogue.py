"""Tests for the rule catalogue — a read-only view (D-038, D-048).

A rule is created by `Review.accept` and by nothing else. `Catalogue` used to
carry `add_rule`, `add_behaviour` and `add_anchor`, which no command reached;
they now live in `tests/helpers.py` as `seed_rule`, so this file seeds rows and
tests what reading them does.

`TestDeclaring` went with them. It asserted the validation inside those
methods — duplicate names, unknown rules, unknown repository aliases — on a
path production never took, and keeping it would have meant testing test code.
The one test in it that was about the *store* rather than the API survives, as
`TestTheCatalogueCannotBeEmptied`.

The tests that matter most are the ones about *coverage*: a catalogue only
knows the rules someone accepted, so what it fails to claim must stay visible.
"""

from __future__ import annotations

import sqlite3

from pathlib import Path

import pytest

from constat.store import Catalogue, Registry, Workspace

from helpers import commit_file, git, seed_anchor, seed_behaviour, seed_rule


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


@pytest.fixture
def catalogue(workspace: Workspace) -> Catalogue:
    return Catalogue(workspace)


def a_rule(workspace: Workspace, name: str = "daily-limit") -> None:
    seed_rule(workspace, name, "A customer may transfer at most the daily limit.")


class TestTheCatalogueCannotBeEmptied:
    """What survives of `TestDeclaring`: the parts about the store itself.

    The rest asserted validation inside `add_rule`/`add_behaviour`/`add_anchor`
    — duplicate names, unknown rules, unknown aliases — which went with those
    methods to `tests/helpers.py`. Keeping those tests would have meant
    asserting the behaviour of a test fixture.
    """

    def test_a_rule_cannot_be_deleted(self, workspace: Workspace, catalogue: Catalogue):
        """D-048: supersession replaces removal, enforced by trigger.

        A catalogue that can be emptied by a `DELETE` is protected by
        convention only, and the convention is what a future bug forgets —
        the same reasoning as `document_version` (CON-31).
        """
        a_rule(workspace)

        with pytest.raises(sqlite3.DatabaseError, match="cannot be removed"):
            workspace.execute("DELETE FROM rule WHERE name = 'daily-limit'")

        assert len(catalogue.list()) == 1

    def test_the_storage_api_has_no_removal(self):
        """The command went, and so did the method behind it. Leaving the
        method would make the prohibition a CLI detail rather than a rule."""
        assert not hasattr(Catalogue, "remove_rule")

    def test_the_storage_api_has_no_writes_at_all(self):
        """D-048 structurally. A rule is created by `Review.accept` and by
        nothing else, so the catalogue has no door for anything to write
        through — not a convention, an absence. This is the test that stops
        `add_rule` coming back as a convenience.
        """
        surface = [
            name
            for name in dir(Catalogue)
            if not name.startswith("_")
        ]
        assert sorted(surface) == ["find", "list", "rules_matching", "unmatched_paths"]

    def test_the_schema_no_longer_makes_a_name_unique(self, workspace: Workspace):
        """`rule.name` lost UNIQUE (D-050): a name is a label that may change
        between versions, and identity is the surrogate id.

        The name-keyed duplicate guard this used to coexist with was in
        `add_rule`, and went with it — so the pre-D-050 model is now gone from
        both halves rather than one.
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
    def test_a_changed_path_matches_its_rule(self, workspace: Workspace, catalogue: Catalogue):
        a_rule(workspace)
        seed_anchor(workspace, "daily-limit", "rules.py")

        hits = catalogue.rules_matching("billing", ("rules.py", "unrelated.py"))
        assert hits == {"daily-limit": ("rules.py",)}

    def test_a_glob_matches_several_paths(self, workspace: Workspace, catalogue: Catalogue):
        a_rule(workspace)
        seed_anchor(workspace, "daily-limit", "billing/*.py")

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

        a_rule(workspace)
        seed_anchor(workspace, "daily-limit", "rules.py", "billing")

        assert catalogue.rules_matching("billing", ("rules.py",))
        assert catalogue.rules_matching("other-repo", ("rules.py",)) == {}

    def test_an_unanchored_rule_never_matches(self, workspace: Workspace, catalogue: Catalogue):
        """A rule with no anchors cannot be tied to any change, which is why
        the CLI says so when one is declared."""
        a_rule(workspace)
        assert catalogue.rules_matching("billing", ("rules.py",)) == {}

    def test_two_rules_can_claim_one_path(self, workspace: Workspace, catalogue: Catalogue):
        seed_rule(workspace, "limit", "Transfer limit.", anchors=("rules.py",))
        seed_rule(workspace, "audit", "Transfers are audited.", anchors=("rules.py",))

        hits = catalogue.rules_matching("billing", ("rules.py",))
        assert set(hits) == {"audit", "limit"}

    def test_matching_is_deterministic(self, workspace: Workspace, catalogue: Catalogue):
        a_rule(workspace)
        seed_anchor(workspace, "daily-limit", "*.py")
        paths = ("b.py", "a.py", "c.py")
        assert catalogue.rules_matching("billing", paths) == catalogue.rules_matching(
            "billing", paths
        )


class TestCoverage:
    """The catalogue's failure mode is what it does not claim (D-038)."""

    def test_unclaimed_paths_are_reported(self, workspace: Workspace, catalogue: Catalogue):
        a_rule(workspace)
        seed_anchor(workspace, "daily-limit", "rules.py")

        unmatched = catalogue.unmatched_paths(
            "billing", ("rules.py", "eligibility.py", "report.py")
        )
        assert unmatched == ("eligibility.py", "report.py")

    def test_everything_is_unclaimed_when_no_rules_exist(self, catalogue: Catalogue):
        """An empty catalogue must not look like "nothing was affected"."""
        paths = ("a.py", "b.py")
        assert catalogue.unmatched_paths("billing", paths) == ("a.py", "b.py")

    def test_nothing_is_unclaimed_when_all_paths_are_anchored(self, workspace: Workspace, catalogue: Catalogue):
        a_rule(workspace)
        seed_anchor(workspace, "daily-limit", "*.py")
        assert catalogue.unmatched_paths("billing", ("a.py", "b.py")) == ()

    def test_a_path_claimed_by_any_rule_is_covered(self, workspace: Workspace, catalogue: Catalogue):
        seed_rule(workspace, "one", "First.", anchors=("a.py",))
        seed_rule(workspace, "two", "Second.", anchors=("b.py",))

        assert catalogue.unmatched_paths("billing", ("a.py", "b.py", "c.py")) == ("c.py",)


class TestPersistence:
    def test_the_catalogue_survives_a_restart(self, tmp_path: Path):
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            seed_rule(
                ws,
                "daily-limit",
                "At most the daily limit.",
                behaviours=("Refused above the limit.",),
                anchors=("rules.py",),
            )

        with Workspace.open(home) as ws:
            rule = Catalogue(ws).find("daily-limit")

        assert rule is not None
        assert len(rule.behaviours) == 1
        assert len(rule.anchors) == 1
        assert rule.created_at.tzinfo is not None

    def test_rules_are_listed_by_name(self, workspace: Workspace, catalogue: Catalogue):
        seed_rule(workspace, "zebra", "Z.")
        seed_rule(workspace, "apple", "A.")
        assert [r.name for r in catalogue.list()] == ["apple", "zebra"]
