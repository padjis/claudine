"""Tests for the published schema.

Done-when for CON-07 is "stable, tested structured output", so serialisation
round-trips and key stability are the point, not an afterthought.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from constat.evidence import collect_evidence, describe_commit
from constat.git import compare_revisions, discover_repository, resolve_revision, summarise_state
from constat.mapping import change_proposal, commit_record, state_proposal
from constat.models import (
    SCHEMA_VERSION,
    ChangeSelection,
    Proposal,
    ProvenanceType,
    RepositoryRef,
    RevisionRef,
    SelectionKind,
    StateSelection,
)

from helpers import commit_file, git

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def a_repo_ref(**overrides) -> RepositoryRef:
    defaults = dict(root_commits=(SHA_C,), local_path="/somewhere/repo", branch="main")
    return RepositoryRef(**{**defaults, **overrides})


def a_change_selection(**overrides) -> ChangeSelection:
    defaults = dict(
        base=RevisionRef(symbolic="v1", sha=SHA_A),
        target=RevisionRef(symbolic="v2", sha=SHA_B),
        merge_base=SHA_A,
    )
    return ChangeSelection(**{**defaults, **overrides})


def build_proposal(repo: Path, base: str, target: str) -> Proposal:
    found = discover_repository(repo)
    summary = compare_revisions(
        found, resolve_revision(found, base), resolve_revision(found, target)
    )
    return change_proposal(found, summary, collect_evidence(found, summary))


class TestValidation:
    def test_a_sha_must_look_like_a_sha(self):
        with pytest.raises(ValidationError):
            RevisionRef(symbolic="main", sha="not-a-sha")

    def test_an_uppercase_sha_is_rejected(self):
        """Git emits lowercase; accepting both would make keys non-comparable."""
        with pytest.raises(ValidationError):
            RevisionRef(symbolic="main", sha="A" * 40)

    def test_an_abbreviated_sha_is_rejected_in_the_schema(self):
        """Resolution produces full SHAs; a short one here means a bug upstream."""
        with pytest.raises(ValidationError):
            RevisionRef(symbolic="main", sha="abc1234")

    def test_unknown_fields_are_refused(self):
        """A typo'd key must not vanish silently from a governance record."""
        with pytest.raises(ValidationError):
            RepositoryRef(
                root_commits=(SHA_C,), local_path="/x", branhc="main"  # typo
            )

    def test_a_repository_needs_at_least_one_root_commit(self):
        with pytest.raises(ValidationError):
            RepositoryRef(root_commits=(), local_path="/x")

    def test_similarity_must_be_a_percentage(self):
        from constat.models import FileChangeRecord

        with pytest.raises(ValidationError):
            FileChangeRecord(change_type="RENAMED", path="a", similarity=101)

    def test_models_are_immutable(self):
        ref = RevisionRef(symbolic="main", sha=SHA_A)
        with pytest.raises(ValidationError):
            ref.sha = SHA_B  # type: ignore[misc]

    def test_proposal_is_immutable(self):
        proposal = Proposal(repository=a_repo_ref(), selection=a_change_selection())
        with pytest.raises(ValidationError):
            proposal.commits = ()  # type: ignore[misc]


class TestIdentity:
    def test_each_proposal_gets_a_fresh_id(self):
        """Generated, not derived (D-025): re-analysis must not collide with an
        approved baseline for the same range."""
        first = Proposal(repository=a_repo_ref(), selection=a_change_selection())
        second = Proposal(repository=a_repo_ref(), selection=a_change_selection())

        assert first.proposal_id != second.proposal_id
        assert isinstance(first.proposal_id, UUID)

    def test_selection_key_is_stable_across_runs(self):
        """What derivation was for: find every proposal covering this range."""
        first = Proposal(repository=a_repo_ref(), selection=a_change_selection())
        second = Proposal(repository=a_repo_ref(), selection=a_change_selection())

        assert first.selection_key == second.selection_key

    def test_selection_key_ignores_the_local_path(self):
        """Identity must survive the repository being moved or re-cloned."""
        here = Proposal(
            repository=a_repo_ref(local_path="/home/a/repo"),
            selection=a_change_selection(),
        )
        there = Proposal(
            repository=a_repo_ref(local_path="/mnt/elsewhere/repo"),
            selection=a_change_selection(),
        )
        assert here.selection_key == there.selection_key

    def test_selection_key_ignores_the_checked_out_branch(self):
        a = Proposal(repository=a_repo_ref(branch="main"), selection=a_change_selection())
        b = Proposal(repository=a_repo_ref(branch="release/2"), selection=a_change_selection())
        assert a.selection_key == b.selection_key

    def test_different_ranges_get_different_keys(self):
        first = Proposal(repository=a_repo_ref(), selection=a_change_selection())
        other = Proposal(
            repository=a_repo_ref(),
            selection=a_change_selection(target=RevisionRef(symbolic="v3", sha=SHA_C)),
        )
        assert first.selection_key != other.selection_key

    def test_different_repositories_get_different_keys(self):
        first = Proposal(
            repository=a_repo_ref(root_commits=(SHA_A,)), selection=a_change_selection()
        )
        other = Proposal(
            repository=a_repo_ref(root_commits=(SHA_B,)), selection=a_change_selection()
        )
        assert first.selection_key != other.selection_key

    def test_state_and_change_on_one_revision_differ(self):
        """"What changed" and "what is here" are different questions (D-016)."""
        change = Proposal(repository=a_repo_ref(), selection=a_change_selection())
        state = Proposal(
            repository=a_repo_ref(),
            selection=StateSelection(revision=RevisionRef(symbolic="v2", sha=SHA_B)),
        )
        assert change.selection_key != state.selection_key

    def test_repository_identity_is_the_smallest_root_commit(self):
        """Deterministic when a repository has several roots."""
        ref = a_repo_ref(root_commits=(SHA_C, SHA_A, SHA_B))
        assert ref.identity == SHA_A


class TestSerialisation:
    def test_proposal_round_trips_through_json(self):
        original = Proposal(repository=a_repo_ref(), selection=a_change_selection())
        restored = Proposal.model_validate_json(original.model_dump_json())

        assert restored == original
        assert restored.selection_key == original.selection_key

    def test_schema_version_is_present_and_serialised(self):
        proposal = Proposal(repository=a_repo_ref(), selection=a_change_selection())
        payload = json.loads(proposal.model_dump_json())

        assert payload["schema_version"] == SCHEMA_VERSION
        assert SCHEMA_VERSION == 1

    def test_selection_discriminator_survives_a_round_trip(self):
        """A state proposal must not come back as a change proposal."""
        state = Proposal(
            repository=a_repo_ref(),
            selection=StateSelection(revision=RevisionRef(symbolic="main", sha=SHA_A)),
        )
        restored = Proposal.model_validate_json(state.model_dump_json())

        assert restored.selection.kind is SelectionKind.STATE
        assert isinstance(restored.selection, StateSelection)
        assert restored.is_change is False

    def test_timestamps_round_trip_with_timezone(self):
        proposal = Proposal(
            repository=a_repo_ref(),
            selection=a_change_selection(),
            created_at=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
        )
        restored = Proposal.model_validate_json(proposal.model_dump_json())
        assert restored.created_at.tzinfo is not None
        assert restored.created_at == proposal.created_at

    def test_serialisation_is_deterministic_for_equal_input(self):
        fixed = dict(
            proposal_id=UUID(int=1),
            created_at=datetime(2026, 11, 9, tzinfo=timezone.utc),
            repository=a_repo_ref(),
            selection=a_change_selection(),
        )
        assert Proposal(**fixed).model_dump_json() == Proposal(**fixed).model_dump_json()

    def test_commit_set_is_reserved_in_the_schema(self):
        """Declared now so CON-29 is additive rather than a schema break."""
        assert SelectionKind.COMMIT_SET.value == "commit_set"


class TestProvenance:
    def test_evidence_defaults_to_observed_fact(self):
        """Everything emitted today is read straight from Git."""
        from constat.models import EvidenceRecord

        record = EvidenceRecord(
            path="a.py", change_type="MODIFIED", revision=SHA_A, reproduce="git diff"
        )
        assert record.provenance is ProvenanceType.OBSERVED_FACT

    def test_the_full_taxonomy_is_declared(self):
        """PRODUCT_SPEC.md section 7.1 — CON-10 extends this, not invents it."""
        assert {p.value for p in ProvenanceType} == {
            "observed_fact",
            "test_evidence",
            "requirement_ref",
            "ai_interpretation",
            "assumption",
            "unknown",
            "human_decision",
        }


class TestMappingFromRealRepositories:
    def test_change_proposal_carries_commits_changes_and_evidence(self, repo: Path):
        commit_file(repo, "new.txt", "x\n", "Add new.txt")
        proposal = build_proposal(repo, "v2.0.0", "main")

        assert proposal.is_change is True
        assert len(proposal.commits) == 1
        assert [c.path for c in proposal.changes] == ["new.txt"]
        assert len(proposal.evidence) == 1
        assert proposal.evidence[0].reproduce.startswith("git -C")

    def test_repository_identity_comes_from_the_root_commit(self, repo: Path):
        proposal = build_proposal(repo, "v1.0.0", "main")
        expected = git(repo, "rev-list", "--max-parents=0", "HEAD").split()

        assert set(proposal.repository.root_commits) == set(expected)
        assert proposal.repository.identity == min(expected)

    def test_identity_survives_the_repository_being_moved(self, repo: Path, tmp_path: Path):
        """The reason identity is not the path (D-025)."""
        before = build_proposal(repo, "v1.0.0", "main")

        moved = tmp_path / "relocated"
        repo.rename(moved)
        after = build_proposal(moved, "v1.0.0", "main")

        assert after.repository.identity == before.repository.identity
        assert after.selection_key == before.selection_key
        assert after.repository.local_path != before.repository.local_path

    def test_a_clone_shares_the_identity_of_its_origin(self, repo: Path, tmp_path: Path):
        clone = tmp_path / "clone"
        git(tmp_path, "clone", "--quiet", str(repo), str(clone))

        assert (
            build_proposal(clone, "v1.0.0", "main").repository.identity
            == build_proposal(repo, "v1.0.0", "main").repository.identity
        )

    def test_real_proposal_round_trips(self, repo: Path):
        commit_file(repo, "a.txt", "a\n", "Add a")
        original = build_proposal(repo, "v2.0.0", "main")
        restored = Proposal.model_validate_json(original.model_dump_json())

        assert restored == original

    def test_completeness_is_recorded(self, repo: Path):
        commit_file(repo, "a.txt", "a\n", "Add a")
        proposal = build_proposal(repo, "v2.0.0", "main")

        assert proposal.completeness is not None
        assert proposal.completeness.is_complete is True
        assert proposal.completeness.max_lines_per_file == 400

    def test_state_proposal_has_no_changes_or_evidence(self, repo: Path):
        """A state description must not borrow change vocabulary (D-022)."""
        found = discover_repository(repo)
        revision = resolve_revision(found, "main")
        state = summarise_state(found, revision)
        proposal = state_proposal(
            found, state, commit_record(describe_commit(found, revision))
        )

        assert proposal.is_change is False
        assert proposal.changes == ()
        assert proposal.evidence == ()
        assert len(proposal.commits) == 1

    def test_rename_keeps_both_paths_in_the_model(self, repo: Path):
        commit_file(repo, "old.txt", "content\n" * 30, "Add old.txt")
        start = git(repo, "rev-parse", "HEAD")
        git(repo, "mv", "old.txt", "new.txt")
        git(repo, "commit", "-m", "Rename")

        proposal = build_proposal(repo, start, "main")
        rename = next(c for c in proposal.changes if c.path == "new.txt")

        assert rename.previous_path == "old.txt"
        assert rename.change_type == "RENAMED"
        assert rename.similarity == 100
