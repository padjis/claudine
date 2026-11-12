"""Tests for accepting and rejecting rule proposals (CON-44, CON-43).

Acceptance is the only way a rule enters or changes the catalogue (D-048), and
it is a human act. Four properties carry these tests:

1. **Accepting baselines a frozen version** that points back at the reading
   accepted — the same split `document`/`document_version` already uses.
2. **A revision adds a version; it does not duplicate the rule.** That is
   CON-43's done-when, and it works because `revises_rule_id` is the reading's
   claim and a human accepting it is accepting that claim (D-050).
3. **Rejecting changes nothing.** Under D-036 it means inconclusive, not
   wrong, so there is nothing to unwind.
4. **History is durable.** A later acceptance never rewrites an earlier
   version.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from constat.cli import main
from constat.errors import InvalidInput, NotRegistered
from constat.models import Anchor, Behaviour, RuleProposal
from constat.operations import open_run, submit_reply
from constat.store import (
    Catalogue,
    Registry,
    Review,
    RuleProposals,
    TicketStore,
    Workspace,
)

from test_runs import distinct_subject


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


@pytest.fixture
def review(workspace: Workspace) -> Review:
    return Review(workspace)


def register(workspace, tmp_path, alias: str = "billing"):
    Registry(workspace).add(
        str(distinct_subject(tmp_path, alias, "LIMIT = 250\n")), alias=alias
    )
    TicketStore(workspace).add("622")


def a_reading(
    name: str = "daily-limit",
    statement: str = "A transfer over the daily limit is refused.",
    behaviours: tuple[str, ...] = ("Refuse and explain the limit",),
    glob: str = "rules.py",
) -> RuleProposal:
    return RuleProposal(
        name=name,
        statement=statement,
        behaviours=tuple(Behaviour(description=b) for b in behaviours),
        anchors=(Anchor(path_glob=glob, repository_alias="billing"),),
    )


def record(workspace, reading: RuleProposal, revises: int | None = None) -> int:
    run_id = open_run(workspace, "622", "submit_reply")
    return RuleProposals(workspace).record(
        run_id, reading, provider="claude", model="opus-5", revises_rule_id=revises
    )


class TestAcceptingCreatesARule:
    def test_a_rule_appears_in_the_catalogue(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        result = review.accept(record(workspace, a_reading()), decided_by="emmanuel")

        assert result.created_rule
        assert result.version_no == 1
        rules = Catalogue(workspace).list()
        assert [r.name for r in rules] == ["daily-limit"]

    def test_behaviours_and_anchors_come_with_it(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        review.accept(record(workspace, a_reading()), decided_by="emmanuel")

        rule = Catalogue(workspace).find("daily-limit")
        assert [b.description for b in rule.behaviours] == [
            "Refuse and explain the limit"
        ]
        assert rule.anchors[0].path_glob == "rules.py"
        assert rule.anchors[0].repository_alias == "billing"

    def test_the_version_points_back_at_the_reading(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        """Traceability: a rule leads to the reading accepted, which leads to
        the run whose evidence it read."""
        register(workspace, tmp_path)
        proposal_id = record(workspace, a_reading())
        result = review.accept(proposal_id, decided_by="emmanuel")

        row = workspace.execute(
            "SELECT from_rule_proposal_id FROM rule_version WHERE id = ?",
            (result.rule_version_id,),
        ).fetchone()
        assert row["from_rule_proposal_id"] == proposal_id

    def test_the_decision_is_recorded_against_the_reading(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        proposal_id = record(workspace, a_reading())
        review.accept(proposal_id, decided_by="emmanuel", rationale="matches")

        stored = RuleProposals(workspace).find(proposal_id)
        assert stored.decision == "accepted"
        assert stored.decided_by == "emmanuel"
        assert stored.rationale == "matches"

    def test_it_leaves_the_review_queue(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        review.accept(record(workspace, a_reading()), decided_by="emmanuel")
        assert RuleProposals(workspace).undecided("622") == ()

    def test_accepting_twice_is_refused(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        """A second acceptance would baseline an identical version."""
        register(workspace, tmp_path)
        proposal_id = record(workspace, a_reading())
        review.accept(proposal_id, decided_by="emmanuel")

        with pytest.raises(InvalidInput, match="already accepted"):
            review.accept(proposal_id, decided_by="emmanuel")

    def test_an_unknown_reading_is_refused(self, review: Review):
        with pytest.raises(NotRegistered, match="no rule proposal"):
            review.accept(999, decided_by="emmanuel")


class TestARevisionAddsAVersion:
    """CON-43's done-when: an update, not a duplicate."""

    def _accepted_rule(self, workspace, review, tmp_path) -> int:
        register(workspace, tmp_path)
        return review.accept(
            record(workspace, a_reading()), decided_by="emmanuel"
        ).rule_id

    def test_the_rule_is_not_duplicated(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        rule_id = self._accepted_rule(workspace, review, tmp_path)

        revision = a_reading(
            name="daily-transfer-limit",
            statement="A transfer over the daily limit is refused, and resets at midnight.",
            behaviours=("Refuse and explain the limit", "Reset at midnight"),
        )
        result = review.accept(
            record(workspace, revision, revises=rule_id), decided_by="emmanuel"
        )

        assert result.is_revision
        assert result.rule_id == rule_id
        assert result.version_no == 2
        assert len(Catalogue(workspace).list()) == 1

    def test_both_versions_remain_readable(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        rule_id = self._accepted_rule(workspace, review, tmp_path)
        review.accept(
            record(workspace, a_reading(name="renamed"), revises=rule_id),
            decided_by="emmanuel",
        )

        versions = review.versions(rule_id)
        assert [v["version_no"] for v in versions] == [1, 2]
        assert [v["name"] for v in versions] == ["daily-limit", "renamed"]

    def test_the_current_state_follows_the_latest_version(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        rule_id = self._accepted_rule(workspace, review, tmp_path)
        review.accept(
            record(
                workspace,
                a_reading(name="renamed", behaviours=("Only this one",)),
                revises=rule_id,
            ),
            decided_by="emmanuel",
        )

        rule = Catalogue(workspace).find("renamed")
        assert rule is not None
        assert [b.description for b in rule.behaviours] == ["Only this one"]
        assert Catalogue(workspace).find("daily-limit") is None

    def test_versions_are_chained(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        rule_id = self._accepted_rule(workspace, review, tmp_path)
        review.accept(
            record(workspace, a_reading(name="renamed"), revises=rule_id),
            decided_by="emmanuel",
        )

        rows = workspace.execute(
            "SELECT id, previous_version_id FROM rule_version "
            "WHERE rule_id = ? ORDER BY version_no",
            (rule_id,),
        ).fetchall()
        assert rows[0]["previous_version_id"] is None
        assert rows[1]["previous_version_id"] == rows[0]["id"]

    def test_a_claim_to_revise_a_missing_rule_cannot_even_be_recorded(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The foreign key refuses it at record time, before any human sees it.

        `Review._target_rule` also refuses it at acceptance — unreachable while
        the key holds, and kept because the alternative if it were ever relaxed
        is silently creating a *new* rule when the reviewer accepted a
        revision, which is the duplicate CON-43 exists to prevent.
        """
        register(workspace, tmp_path)

        with pytest.raises(sqlite3.DatabaseError, match="FOREIGN KEY"):
            record(workspace, a_reading(), revises=999)

    def test_the_rule_name_may_change_between_versions(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        """D-050: a name is a label, and identity is the surrogate id."""
        rule_id = self._accepted_rule(workspace, review, tmp_path)
        review.accept(
            record(workspace, a_reading(name="completely-different"), revises=rule_id),
            decided_by="emmanuel",
        )

        assert review.versions(rule_id)[1]["name"] == "completely-different"
        assert len(Catalogue(workspace).list()) == 1


class TestRejecting:
    def test_the_catalogue_is_untouched(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        """D-036: inconclusive, not wrong — so there is nothing to unwind."""
        register(workspace, tmp_path)
        review.reject(record(workspace, a_reading()), decided_by="emmanuel")

        assert Catalogue(workspace).list() == ()

    def test_no_version_is_baselined(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        review.reject(record(workspace, a_reading()), decided_by="emmanuel")

        count = workspace.execute(
            "SELECT COUNT(*) c FROM rule_version"
        ).fetchone()["c"]
        assert count == 0

    def test_it_is_recorded_as_rejected(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        proposal_id = record(workspace, a_reading())
        review.reject(proposal_id, decided_by="emmanuel", rationale="not yet")

        stored = RuleProposals(workspace).find(proposal_id)
        assert stored.decision == "rejected"
        assert stored.rationale == "not yet"

    def test_a_rejected_reading_can_still_be_accepted_later(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        """Rejection is inconclusive, so it must not be a dead end."""
        register(workspace, tmp_path)
        proposal_id = record(workspace, a_reading())
        review.reject(proposal_id, decided_by="emmanuel")

        result = review.accept(proposal_id, decided_by="emmanuel")
        assert result.created_rule
        assert RuleProposals(workspace).find(proposal_id).decision == "accepted"

    def test_an_unknown_reading_is_refused(self, review: Review):
        with pytest.raises(NotRegistered, match="no rule proposal"):
            review.reject(999, decided_by="emmanuel")


class TestHistoryIsDurable:
    def test_a_version_cannot_be_modified(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        review.accept(record(workspace, a_reading()), decided_by="emmanuel")

        with pytest.raises(sqlite3.DatabaseError, match="cannot be modified"):
            workspace.execute("UPDATE rule_version SET statement = 'rewritten'")

    def test_a_version_cannot_be_deleted(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        review.accept(record(workspace, a_reading()), decided_by="emmanuel")

        with pytest.raises(sqlite3.DatabaseError, match="cannot be deleted"):
            workspace.execute("DELETE FROM rule_version")

    def test_an_earlier_version_survives_a_later_acceptance(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        rule_id = review.accept(
            record(workspace, a_reading()), decided_by="emmanuel"
        ).rule_id
        review.accept(
            record(workspace, a_reading(name="renamed"), revises=rule_id),
            decided_by="emmanuel",
        )

        first = review.versions(rule_id)[0]
        assert first["name"] == "daily-limit"
        assert first["statement"].startswith("A transfer over the daily limit")


class TestAcceptedRulesMatchChanges:
    def test_an_accepted_rule_matches_its_anchored_path(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        """The point of the whole loop: an accepted rule is matched to future
        changes. A rule that never matches is inert (CON-40)."""
        register(workspace, tmp_path)
        review.accept(record(workspace, a_reading()), decided_by="emmanuel")

        hits = Catalogue(workspace).rules_matching("billing", ("rules.py",))
        assert "daily-limit" in hits

    def test_a_revision_changes_what_matches(
        self, workspace: Workspace, review: Review, tmp_path: Path
    ):
        register(workspace, tmp_path)
        rule_id = review.accept(
            record(workspace, a_reading()), decided_by="emmanuel"
        ).rule_id

        review.accept(
            record(workspace, a_reading(glob="other.py"), revises=rule_id),
            decided_by="emmanuel",
        )

        catalogue = Catalogue(workspace)
        assert catalogue.rules_matching("billing", ("rules.py",)) == {}
        assert catalogue.rules_matching("billing", ("other.py",))


class TestTheCommandLine:
    def _setup(self, tmp_path) -> str:
        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init"])
        clone = distinct_subject(tmp_path, "billing", "LIMIT = 250\n")
        main(["--workspace", ws, "repo", "add", str(clone), "--name", "billing"])
        main(["--workspace", ws, "ticket", "add", "622", "--no-provider"])

        with Workspace.open(ws) as workspace:
            submit_reply(
                workspace,
                "622",
                '{"rules":[{"name":"daily-limit","statement":"A transfer over the '
                'limit is refused.","behaviours":["Refuse"],"anchors":'
                '[{"path_glob":"rules.py","repository_alias":"billing"}]}]}',
            )
        return ws

    def test_accept_baselines_a_version(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "accept", "1", "--by", "e"]) == 0
        out = capsys.readouterr().out
        assert "rule 1 created" in out
        assert "version 1 baselined" in out

    def test_accept_requires_a_decider(self, tmp_path):
        """No automatic approvals: there is no default for who decided."""
        ws = self._setup(tmp_path)
        with pytest.raises(SystemExit) as exc:
            main(["--workspace", ws, "rule", "accept", "1"])
        assert exc.value.code == 2

    def test_reject_requires_a_decider(self, tmp_path):
        ws = self._setup(tmp_path)
        with pytest.raises(SystemExit) as exc:
            main(["--workspace", ws, "rule", "reject", "1"])
        assert exc.value.code == 2

    def test_reject_says_it_means_inconclusive(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "reject", "1", "--by", "e"]) == 0
        out = capsys.readouterr().out
        assert "inconclusive, not as wrong" in out
        assert "catalogue is unchanged" in out

    def test_history_shows_who_accepted_and_from_what(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        main(["--workspace", ws, "rule", "accept", "1", "--by", "emmanuel"])
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "history", "1"]) == 0
        out = capsys.readouterr().out
        assert "v1" in out
        assert "accepted by emmanuel" in out
        assert "rule proposal 1" in out

    def test_history_of_an_unaccepted_rule_says_so(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "rule", "history", "7"]) == 0
        assert "no accepted versions" in capsys.readouterr().out

    def test_accepting_an_unknown_reading_exits_four(self, tmp_path, capsys):
        ws = self._setup(tmp_path)
        capsys.readouterr()

        code = main(["--workspace", ws, "rule", "accept", "999", "--by", "e"])
        assert code == 4
        assert "no rule proposal" in capsys.readouterr().err
