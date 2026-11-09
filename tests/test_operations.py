"""Tests for the gathering operation.

Done-when for CON-34 is "running an operation on a ticket produces a document
containing evidence from each repository where its work was found".

The sharper requirement is the negative one: a repository that was searched
and found nothing must still appear. Silence about a repository is
indistinguishable from "no changes there", and the two are different claims.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.errors import NotRegistered
from constat.evidence import ExcerptLimits
from constat.operations import gather
from constat.store import Registry, TicketStore, Workspace
from constat.tickets import TicketStatus

from helpers import commit_file, git


def make_subject(tmp_path: Path, name: str) -> Path:
    """A clone whose `develop` carries ticket 622's work, not yet in mainline."""
    source = tmp_path / f"{name}-src"
    source.mkdir()
    git(source, "init", "--initial-branch=main", "--quiet")
    commit_file(source, "rules.py", "LIMIT = 100\n", "Initial")

    clone = tmp_path / name
    git(tmp_path, "clone", "--quiet", str(source), str(clone))
    git(clone, "checkout", "--quiet", "-b", "develop")
    commit_file(clone, "rules.py", "LIMIT = 250\n", "Raise the limit (#622)")
    git(clone, "checkout", "--quiet", "main")
    return clone


def make_quiet_subject(tmp_path: Path, name: str) -> Path:
    """A clone with no reference to any ticket."""
    source = tmp_path / f"{name}-src"
    source.mkdir()
    git(source, "init", "--initial-branch=main", "--quiet")
    commit_file(source, "unrelated.py", "x = 1\n", "Something else")

    clone = tmp_path / name
    git(tmp_path, "clone", "--quiet", str(source), str(clone))
    return clone


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


class TestGathering:
    def test_evidence_is_gathered_from_a_contributing_repository(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        result = gather(workspace, "622")

        assert result.repositories_contributing == 1
        finding = result.findings[0]
        assert finding.status is TicketStatus.PENDING
        assert len(finding.commits) == 1
        assert finding.commits[0].bundle is not None
        assert finding.commits[0].bundle.excerpts

    def test_the_document_names_the_changed_files(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        body = gather(workspace, "622").body
        assert "rules.py" in body
        assert "billing" in body

    def test_a_searched_repository_that_found_nothing_still_appears(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The requirement that matters: silence is not a finding."""
        registry = Registry(workspace)
        registry.add(str(make_subject(tmp_path, "billing")), alias="billing")
        registry.add(str(make_quiet_subject(tmp_path, "quiet")), alias="quiet")
        TicketStore(workspace).add("622")

        result = gather(workspace, "622")
        body = result.body

        assert result.repositories_searched == 2
        assert result.repositories_contributing == 1
        assert "quiet" in body
        assert "not that the ticket changed nothing" in body

    def test_landed_work_is_distinguished_in_the_document(
        self, workspace: Workspace, tmp_path: Path
    ):
        clone = make_quiet_subject(tmp_path, "shipped")
        commit_file(clone, "done.py", "x\n", "Already shipped (#500)")

        Registry(workspace).add(str(clone), alias="shipped")
        TicketStore(workspace).add("500")

        body = gather(workspace, "500").body
        assert "Already in `main`" in body
        assert "not the same as finding nothing" in body

    def test_an_unknown_ticket_is_refused(self, workspace: Workspace):
        with pytest.raises(NotRegistered, match="no ticket"):
            gather(workspace, "never-opened")

    def test_no_registered_repositories_is_stated_not_implied(
        self, workspace: Workspace
    ):
        TicketStore(workspace).add("622")
        body = gather(workspace, "622").body

        assert "No repositories are registered" in body
        assert "not a statement that the ticket changed nothing" in body

    def test_evidence_is_per_commit_and_attributed(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A ticket's commits need not be contiguous, so each is collected
        separately and keeps its own attribution."""
        clone = make_subject(tmp_path, "billing")
        git(clone, "checkout", "--quiet", "develop")
        commit_file(clone, "second.py", "y = 2\n", "A second change (#622)")
        git(clone, "checkout", "--quiet", "main")

        Registry(workspace).add(str(clone), alias="billing")
        TicketStore(workspace).add("622")

        finding = gather(workspace, "622").findings[0]
        assert len(finding.commits) == 2
        assert all(c.attribution == "commit_message" for c in finding.commits)
        assert all(c.bundle is not None for c in finding.commits)

    def test_unrelated_commits_are_not_swept_in(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Diffing the first commit's parent against the last would include
        whatever landed between them. Per-commit collection does not."""
        clone = make_subject(tmp_path, "billing")
        git(clone, "checkout", "--quiet", "develop")
        commit_file(clone, "noise.py", "noise = True\n", "Unrelated tidy-up")
        commit_file(clone, "more.py", "z = 3\n", "More ticket work (#622)")
        git(clone, "checkout", "--quiet", "main")

        Registry(workspace).add(str(clone), alias="billing")
        TicketStore(workspace).add("622")

        body = gather(workspace, "622").body
        assert "more.py" in body
        assert "noise.py" not in body

    def test_excerpt_limits_are_respected(self, workspace: Workspace, tmp_path: Path):
        clone = make_subject(tmp_path, "billing")
        git(clone, "checkout", "--quiet", "develop")
        commit_file(
            clone, "big.py", "".join(f"x{n} = {n}\n" for n in range(500)), "Big (#622)"
        )
        git(clone, "checkout", "--quiet", "main")

        Registry(workspace).add(str(clone), alias="billing")
        TicketStore(workspace).add("622")

        result = gather(
            workspace, "622", ExcerptLimits(max_lines_per_file=10, max_lines_total=10)
        )
        bundles = [c.bundle for f in result.findings for c in f.commits if c.bundle]
        assert any(b.lines_omitted > 0 for b in bundles)
        assert "omitted" in result.body


class TestPersistence:
    def test_the_document_body_is_stored(self, workspace: Workspace, tmp_path: Path):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        tickets = TicketStore(workspace)
        tickets.add("622")

        assert tickets.document("622").is_empty is True
        gather(workspace, "622")
        assert tickets.document("622").is_empty is False

    def test_the_document_survives_a_restart(self, tmp_path: Path):
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            Registry(ws).add(str(make_subject(tmp_path, "billing")), alias="billing")
            TicketStore(ws).add("622")
            gather(ws, "622")

        with Workspace.open(home) as ws:
            assert "rules.py" in TicketStore(ws).document("622").body

    def test_each_run_records_an_operation_per_repository(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Without this the document is unattributable prose (D-029)."""
        registry = Registry(workspace)
        registry.add(str(make_subject(tmp_path, "billing")), alias="billing")
        registry.add(str(make_quiet_subject(tmp_path, "quiet")), alias="quiet")
        TicketStore(workspace).add("622")

        gather(workspace, "622")
        rows = workspace.execute(
            "SELECT kind, summary, repository_id FROM operation"
        ).fetchall()

        assert len(rows) == 2
        assert all(row["kind"] == "gather_evidence" for row in rows)
        assert all(row["repository_id"] is not None for row in rows)

    def test_operations_accumulate_across_runs(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Operations are a log of what ran, so re-running adds to it."""
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        gather(workspace, "622")
        gather(workspace, "622")

        count = workspace.execute("SELECT COUNT(*) c FROM operation").fetchone()["c"]
        assert count == 2

    def test_the_body_is_regenerated_not_duplicated(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Re-running must not append a second copy of the same findings."""
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        tickets = TicketStore(workspace)
        tickets.add("622")

        gather(workspace, "622")
        first = tickets.document("622").body
        gather(workspace, "622")
        second = tickets.document("622").body

        assert first == second
        assert second.count("# Ticket 622") == 1

    def test_the_timestamp_is_updated(self, workspace: Workspace, tmp_path: Path):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        tickets = TicketStore(workspace)
        tickets.add("622")
        before = tickets.document("622").updated_at

        gather(workspace, "622")
        assert tickets.document("622").updated_at >= before


class TestHonesty:
    def test_the_document_disclaims_authority(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A draft is not product knowledge until approved (product rule 4)."""
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        body = gather(workspace, "622").body
        assert "carries no authority" in body
        assert "approve" in body.lower()

    def test_the_document_claims_no_interpretation(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        body = gather(workspace, "622").body
        assert "Observed facts only" in body
        assert "Nothing here is classified, interpreted or approved" in body

    def test_completeness_is_stated_per_commit(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        body = gather(workspace, "622").body
        assert "captured" in body

    def test_the_attributing_ref_is_recorded(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Found on develop and found on an abandoned branch differ."""
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        assert "develop" in gather(workspace, "622").body
