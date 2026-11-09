"""Tests for the repository registry.

Done-when for CON-32 is "a registered repository survives a restart and can be
read with the existing Git layer", so persistence and round-tripping back into
`discover_repository` are tested directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.errors import (
    AlreadyRegistered,
    DefaultBranchUnknown,
    NotARepository,
    NotRegistered,
    PathNotFound,
)
from constat.git import discover_repository, local_branches, resolve_default_branch
from constat.store import Registry, Workspace

from helpers import git


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


@pytest.fixture
def registry(workspace: Workspace) -> Registry:
    return Registry(workspace)


@pytest.fixture
def cloned(tmp_path: Path, repo: Path) -> Path:
    """A clone, which is the only way origin/HEAD gets set.

    The fixture repository is created with `git init`, so it has no remote and
    no resolvable default branch — exactly the case the resolver refuses.
    """
    target = tmp_path / "cloned"
    git(tmp_path, "clone", "--quiet", str(repo), str(target))
    return target


class TestDefaultBranchResolution:
    def test_a_clone_resolves_from_origin_head(self, cloned: Path):
        assert resolve_default_branch(discover_repository(cloned)) == "main"

    def test_a_repository_without_origin_head_is_refused(self, repo: Path):
        """Never guessed from HEAD: registering while on a feature branch
        would make that branch the permanent reference point (D-028)."""
        with pytest.raises(DefaultBranchUnknown, match="could not determine"):
            resolve_default_branch(discover_repository(repo))

    def test_the_refusal_names_the_remedy_and_the_candidates(self, repo: Path):
        with pytest.raises(DefaultBranchUnknown) as exc:
            resolve_default_branch(discover_repository(repo))

        message = str(exc.value)
        assert "--default-branch" in message
        assert "git remote set-head" in message
        assert "main" in message  # listed as a candidate

    def test_a_checked_out_feature_branch_does_not_become_the_default(
        self, cloned: Path
    ):
        """The failure this guards against, made explicit."""
        git(cloned, "checkout", "--quiet", "-b", "feature/something")
        assert resolve_default_branch(discover_repository(cloned)) == "main"

    def test_local_branches_are_listed_sorted(self, repo: Path):
        branches = local_branches(discover_repository(repo))
        assert "main" in branches
        assert list(branches) == sorted(branches)


class TestAdd:
    def test_registering_stores_identity_and_default_branch(
        self, registry: Registry, cloned: Path
    ):
        entry = registry.add(str(cloned), alias="subject")

        assert entry.alias == "subject"
        assert entry.default_branch == "main"
        assert entry.identity == git(cloned, "rev-list", "--max-parents=0", "HEAD")
        assert entry.source_kind == "local"

    def test_alias_defaults_to_the_directory_name(self, registry: Registry, cloned: Path):
        assert registry.add(str(cloned)).alias == "cloned"

    def test_default_branch_can_be_stated_explicitly(self, registry: Registry, repo: Path):
        """The escape hatch for a repository with no resolvable default."""
        entry = registry.add(str(repo), alias="local-only", default_branch="main")
        assert entry.default_branch == "main"

    def test_an_unresolvable_default_branch_is_refused(
        self, registry: Registry, repo: Path
    ):
        with pytest.raises(DefaultBranchUnknown):
            registry.add(str(repo), alias="local-only")

    def test_a_missing_path_is_refused_with_the_usual_error(
        self, registry: Registry, tmp_path: Path
    ):
        """Registration reuses the Git layer's errors rather than inventing
        new ones, so "that is not a repository" reads the same everywhere."""
        with pytest.raises(PathNotFound):
            registry.add(str(tmp_path / "nope"), alias="x")

    def test_a_non_repository_is_refused(self, registry: Registry, empty_dir: Path):
        with pytest.raises(NotARepository):
            registry.add(str(empty_dir), alias="x")


class TestDuplicates:
    def test_the_same_repository_cannot_be_registered_twice(
        self, registry: Registry, cloned: Path
    ):
        registry.add(str(cloned), alias="first")
        with pytest.raises(AlreadyRegistered, match="already registered as 'first'"):
            registry.add(str(cloned), alias="second")

    def test_duplicates_are_detected_by_identity_not_path(
        self, registry: Registry, cloned: Path, tmp_path: Path
    ):
        """A second clone at a different path is still the same repository
        (D-025). Path-based detection would miss this."""
        registry.add(str(cloned), alias="first")

        elsewhere = tmp_path / "second-clone"
        git(tmp_path, "clone", "--quiet", str(cloned), str(elsewhere))

        with pytest.raises(AlreadyRegistered) as exc:
            registry.add(str(elsewhere), alias="second")
        assert "same repository" in str(exc.value)

    def test_an_alias_collision_with_a_different_repository_is_refused(
        self, registry: Registry, cloned: Path, tmp_path: Path
    ):
        registry.add(str(cloned), alias="taken")

        other = tmp_path / "other"
        other.mkdir()
        git(other, "init", "--initial-branch=main", "--quiet")
        git(other, "commit", "--quiet", "--allow-empty", "-m", "Root")
        unrelated = tmp_path / "other-clone"
        git(tmp_path, "clone", "--quiet", str(other), str(unrelated))

        with pytest.raises(AlreadyRegistered, match="unrelated repository"):
            registry.add(str(unrelated), alias="taken")

    def test_unrelated_repositories_can_both_be_registered(
        self, registry: Registry, cloned: Path, tmp_path: Path
    ):
        registry.add(str(cloned), alias="one")

        other = tmp_path / "other"
        other.mkdir()
        git(other, "init", "--initial-branch=main", "--quiet")
        git(other, "commit", "--quiet", "--allow-empty", "-m", "Root")
        clone2 = tmp_path / "other-clone"
        git(tmp_path, "clone", "--quiet", str(other), str(clone2))

        registry.add(str(clone2), alias="two")
        assert [e.alias for e in registry.list()] == ["one", "two"]


class TestListAndRemove:
    def test_an_empty_registry_lists_nothing(self, registry: Registry):
        assert registry.list() == ()

    def test_listing_is_sorted_by_alias(self, registry: Registry, cloned: Path, tmp_path: Path):
        registry.add(str(cloned), alias="zebra")

        other = tmp_path / "other"
        other.mkdir()
        git(other, "init", "--initial-branch=main", "--quiet")
        git(other, "commit", "--quiet", "--allow-empty", "-m", "Root")
        clone2 = tmp_path / "other-clone"
        git(tmp_path, "clone", "--quiet", str(other), str(clone2))
        registry.add(str(clone2), alias="apple")

        assert [e.alias for e in registry.list()] == ["apple", "zebra"]

    def test_remove_unregisters(self, registry: Registry, cloned: Path):
        registry.add(str(cloned), alias="subject")
        removed = registry.remove("subject")

        assert removed.alias == "subject"
        assert registry.list() == ()

    def test_remove_leaves_the_repository_on_disk(self, registry: Registry, cloned: Path):
        """Constat is read-only against repositories; unregistering is not a
        deletion."""
        registry.add(str(cloned), alias="subject")
        registry.remove("subject")

        assert cloned.exists()
        assert (cloned / ".git").exists()
        assert git(cloned, "rev-parse", "HEAD")

    def test_removing_an_unknown_alias_lists_what_is_known(self, registry: Registry, cloned: Path):
        registry.add(str(cloned), alias="subject")
        with pytest.raises(NotRegistered) as exc:
            registry.remove("typo")

        message = str(exc.value)
        assert "typo" in message
        assert "subject" in message  # tells you what you could have meant

    def test_removing_then_re_adding_works(self, registry: Registry, cloned: Path):
        registry.add(str(cloned), alias="subject")
        registry.remove("subject")
        assert registry.add(str(cloned), alias="subject").alias == "subject"


class TestPersistence:
    def test_a_registration_survives_a_restart(self, tmp_path: Path, cloned: Path):
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            Registry(ws).add(str(cloned), alias="subject")

        with Workspace.open(home) as ws:
            entries = Registry(ws).list()

        assert len(entries) == 1
        assert entries[0].alias == "subject"
        assert entries[0].default_branch == "main"

    def test_a_registered_repository_can_be_read_by_the_git_layer(
        self, tmp_path: Path, cloned: Path
    ):
        """The done-when: registration must produce something usable."""
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            Registry(ws).add(str(cloned), alias="subject")

        with Workspace.open(home) as ws:
            entry = Registry(ws).find("subject")

        assert entry is not None
        reopened = discover_repository(entry.source)
        assert reopened.root.exists()
        assert entry.default_branch in local_branches(reopened)

    def test_removal_survives_a_restart(self, tmp_path: Path, cloned: Path):
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            registry = Registry(ws)
            registry.add(str(cloned), alias="subject")
            registry.remove("subject")

        with Workspace.open(home) as ws:
            assert Registry(ws).list() == ()

    def test_timestamps_round_trip_as_datetimes(self, tmp_path: Path, cloned: Path):
        home = tmp_path / "ws"
        with Workspace.create(home) as ws:
            Registry(ws).add(str(cloned), alias="subject")

        with Workspace.open(home) as ws:
            entry = Registry(ws).find("subject")

        assert entry is not None
        assert entry.added_at.tzinfo is not None
        assert entry.last_fetched_at is None  # a local path is never stale
