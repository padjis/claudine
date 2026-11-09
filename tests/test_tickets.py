"""Tests for ticket attribution and the ticket store.

D-031 expects a ticket's work to be merged onto an integration branch but not
yet in mainline. The real subjects cannot exercise that case — every branch in
both is zero commits ahead of mainline — so the fixture here builds the
expected shape deliberately.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.errors import AlreadyRegistered, NotRegistered
from constat.git import discover_repository
from constat.models import Document, Ticket
from constat.store import TicketStore, Workspace
from constat.tickets import (
    Attribution,
    TicketStatus,
    branches_naming,
    find_ticket_commits,
    reference_pattern,
)

from helpers import commit_file, git


@pytest.fixture
def integrated(tmp_path: Path) -> Path:
    """A repository shaped the way D-031 expects.

    `main` is mainline. `develop` carries ticket 622's work, merged but not
    yet in mainline. Ticket 700 has a named branch. Ticket 500 has already
    landed in mainline.
    """
    path = tmp_path / "integrated"
    path.mkdir()
    git(path, "init", "--initial-branch=main", "--quiet")

    commit_file(path, "README.md", "start\n", "Initial commit")
    commit_file(path, "landed.txt", "x\n", "Fix the rounding rule (#500)")

    git(path, "checkout", "--quiet", "-b", "develop")
    commit_file(path, "pending.txt", "x\n", "Prune dead tokens (#622)")
    commit_file(path, "unrelated.txt", "x\n", "Tidy imports")

    git(path, "checkout", "--quiet", "-b", "feat/700-new-limit", "main")
    commit_file(path, "limit.txt", "x\n", "Raise the daily limit")

    git(path, "checkout", "--quiet", "main")
    return path


class TestReferenceMatching:
    @pytest.mark.parametrize(
        "text,matches",
        [
            ("Fix thing (#622)", True),
            ("Relates to 622 somehow", True),
            ("ticket-622: done", True),
            ("commit 6220 is unrelated", False),
            ("issue 1622 is different", False),
            ("no number here", False),
        ],
    )
    def test_a_bare_number_matches_only_as_a_whole_token(self, text, matches):
        """A plain `622` must not match `6220` or `1622`."""
        import re

        assert bool(re.search(reference_pattern("622"), text)) is matches

    def test_punctuated_references_match(self):
        import re

        assert re.search(reference_pattern("ABC-123"), "see ABC-123 for detail")
        assert re.search(reference_pattern("#617"), "fixes #617")

    def test_branches_are_matched_by_token_too(self, integrated: Path):
        repo = discover_repository(integrated)
        assert any("feat/700-new-limit" in b for b in branches_naming(repo, "700"))
        assert branches_naming(repo, "70") == ()


class TestFindingTicketCommits:
    def test_work_merged_outside_mainline_is_pending(self, integrated: Path):
        """The case D-031 expects."""
        match = find_ticket_commits(discover_repository(integrated), "622", "main")

        assert match.status is TicketStatus.PENDING
        assert match.commit_count == 1
        assert "Prune dead tokens" in match.commits[0].subject

    def test_a_pending_commit_records_where_it_was_found(self, integrated: Path):
        """The ref is evidence: develop and an abandoned branch differ."""
        match = find_ticket_commits(discover_repository(integrated), "622", "main")
        assert any("develop" in ref for ref in match.commits[0].found_on)

    def test_work_already_in_mainline_is_landed_not_missing(self, integrated: Path):
        """"Already shipped" and "no such reference" are different answers."""
        match = find_ticket_commits(discover_repository(integrated), "500", "main")

        assert match.status is TicketStatus.LANDED
        assert match.commit_count == 1

    def test_an_unknown_reference_is_not_found(self, integrated: Path):
        match = find_ticket_commits(discover_repository(integrated), "9999", "main")

        assert match.status is TicketStatus.NOT_FOUND
        assert match.commits == ()

    def test_the_three_statuses_are_distinct(self, integrated: Path):
        repo = discover_repository(integrated)
        statuses = {
            find_ticket_commits(repo, ref, "main").status
            for ref in ("622", "500", "9999")
        }
        assert statuses == {
            TicketStatus.PENDING,
            TicketStatus.LANDED,
            TicketStatus.NOT_FOUND,
        }

    def test_a_named_branch_attributes_its_commits(self, integrated: Path):
        """Branch-name attribution works without any commit-message reference.

        `Raise the daily limit` never mentions 700; the branch name does.
        """
        match = find_ticket_commits(discover_repository(integrated), "700", "main")

        assert match.status is TicketStatus.PENDING
        assert match.commits[0].attribution is Attribution.BRANCH_NAME
        assert "Raise the daily limit" in match.commits[0].subject
        assert any("feat/700-new-limit" in b for b in match.branches)

    def test_branch_attribution_takes_priority_over_message(self, integrated: Path):
        """D-030's ordering: the branch is the stronger signal."""
        git(integrated, "checkout", "--quiet", "-b", "feat/800-thing", "main")
        commit_file(integrated, "both.txt", "x\n", "Work on 800")
        git(integrated, "checkout", "--quiet", "main")

        match = find_ticket_commits(discover_repository(integrated), "800", "main")
        assert match.commits[0].attribution is Attribution.BRANCH_NAME

    def test_unrelated_commits_on_the_branch_are_not_attributed(self, integrated: Path):
        """Message attribution must not sweep in neighbouring work."""
        match = find_ticket_commits(discover_repository(integrated), "622", "main")
        subjects = [c.subject for c in match.commits]
        assert "Tidy imports" not in subjects

    def test_results_are_deterministic(self, integrated: Path):
        repo = discover_repository(integrated)
        assert find_ticket_commits(repo, "622", "main") == find_ticket_commits(
            repo, "622", "main"
        )

    def test_mainline_name_is_not_assumed(self, tmp_path: Path):
        """Product rule 6: the default branch may be called anything."""
        path = tmp_path / "trunkrepo"
        path.mkdir()
        git(path, "init", "--initial-branch=trunk", "--quiet")
        commit_file(path, "a.txt", "a\n", "Initial")
        git(path, "checkout", "--quiet", "-b", "staging")
        commit_file(path, "b.txt", "b\n", "Change the rule (#42)")
        git(path, "checkout", "--quiet", "trunk")

        match = find_ticket_commits(discover_repository(path), "42", "trunk")
        assert match.status is TicketStatus.PENDING


class TestTicketStore:
    @pytest.fixture
    def store(self, tmp_path: Path):
        with Workspace.create(tmp_path / "ws") as ws:
            yield TicketStore(ws)

    def test_opening_a_ticket_creates_its_document(self, store: TicketStore):
        """A ticket without a document is a state the model forbids (D-029)."""
        ticket = store.add("622")

        assert isinstance(ticket, Ticket)
        document = store.document("622")
        assert isinstance(document, Document)
        assert document.is_empty is True

    def test_a_ticket_cannot_be_opened_twice(self, store: TicketStore):
        store.add("622")
        with pytest.raises(AlreadyRegistered, match="already exists"):
            store.add("622")

    def test_the_duplicate_message_explains_why(self, store: TicketStore):
        store.add("622")
        with pytest.raises(AlreadyRegistered) as exc:
            store.add("622")
        assert "would not create a second one" in str(exc.value)

    def test_a_document_for_an_unknown_ticket_is_refused(self, store: TicketStore):
        with pytest.raises(NotRegistered, match="no ticket"):
            store.document("nope")

    def test_references_are_stored_verbatim(self, store: TicketStore):
        """The real subjects contain four reference shapes; constraining the
        format would exclude references that already exist."""
        for reference in ("622", "ADR-0019", "plans/0015", "repo#617"):
            assert store.add(reference).reference == reference

    def test_there_is_no_title_field(self, store: TicketStore):
        """Dropped in D-032: unverified free text has no place in a product
        whose provenance taxonomy has no category for it."""
        assert not hasattr(store.add("622"), "title")

    def test_listing_is_empty_initially(self, store: TicketStore):
        assert store.list() == ()


class TestPersistence:
    def test_tickets_and_documents_survive_a_restart(self, tmp_path: Path):
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            TicketStore(ws).add("622")

        with Workspace.open(home) as ws:
            store = TicketStore(ws)
            assert [t.reference for t in store.list()] == ["622"]
            assert store.document("622").is_empty

    def test_creation_is_atomic(self, tmp_path: Path):
        """If document creation failed, the ticket must not survive alone."""
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            store = TicketStore(ws)
            store.add("622")

            count = ws.execute(
                "SELECT COUNT(*) c FROM ticket t "
                "LEFT JOIN document d ON d.ticket_id = t.id "
                "WHERE d.id IS NULL"
            ).fetchone()["c"]
        assert count == 0, "no ticket may exist without its document"
