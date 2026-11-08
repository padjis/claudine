"""Tests for the read-only Git adapter.

Covers valid, invalid and missing repositories and revisions — the done-when
criterion for CON-04.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.errors import (
    AmbiguousRevision,
    NotARepository,
    PathNotFound,
    RepositoryError,
    RevisionNotFound,
)
from constat.git import discover_repository, resolve_revision

from helpers import commit_file, git


class TestDiscoverRepository:
    def test_valid_repository_reports_root_and_branch(self, repo: Path):
        found = discover_repository(repo)
        assert found.root == repo.resolve()
        assert found.branch == "main"
        assert found.is_detached is False

    def test_missing_path_is_reported_as_missing(self, tmp_path: Path):
        with pytest.raises(PathNotFound, match="no such path"):
            discover_repository(tmp_path / "nope")

    def test_a_file_is_not_a_repository(self, tmp_path: Path):
        target = tmp_path / "a-file"
        target.write_text("x")
        with pytest.raises(NotARepository, match="not a directory"):
            discover_repository(target)

    def test_directory_that_is_not_a_repository(self, empty_dir: Path):
        with pytest.raises(NotARepository, match="not a Git repository"):
            discover_repository(empty_dir)

    def test_each_failure_mode_has_a_distinct_message(self, tmp_path: Path, empty_dir: Path):
        """"Missing", "not a directory" and "not a repository" are different
        problems and must not share one message."""
        messages = []
        for bad in (tmp_path / "nope", empty_dir):
            with pytest.raises(RepositoryError) as exc:
                discover_repository(bad)
            messages.append(str(exc.value))

        a_file = tmp_path / "f"
        a_file.write_text("x")
        with pytest.raises(RepositoryError) as exc:
            discover_repository(a_file)
        messages.append(str(exc.value))

        assert len(set(messages)) == 3

    def test_subdirectory_resolves_to_the_repository_root(self, repo: Path):
        """Git widens a subdirectory to its enclosing repository.

        Convenient, but it widens scope — so `given` and `root` are both kept
        and the CLI reports the root. A reviewer must be able to see which
        repository was actually read.
        """
        subdir = repo / "src" / "deep"
        subdir.mkdir(parents=True)

        found = discover_repository(subdir)
        assert found.root == repo.resolve()
        assert found.given == subdir
        assert found.given != found.root

    def test_detached_head_has_no_branch(self, repo: Path):
        git(repo, "checkout", "--quiet", "--detach", "HEAD")
        found = discover_repository(repo)
        assert found.branch is None
        assert found.is_detached is True

    def test_bare_repository_is_accepted(self, tmp_path: Path, repo: Path):
        """A mirror is a real repository, and its HEAD symref is its default branch.

        A bare repository has no work tree, but HEAD still points at a branch —
        so `branch` is populated rather than None. Verified against git
        directly rather than assumed.
        """
        bare = tmp_path / "mirror.git"
        git(tmp_path, "clone", "--bare", "--quiet", str(repo), str(bare))

        found = discover_repository(bare)
        assert found.root.name == "mirror.git"
        assert found.branch == git(bare, "symbolic-ref", "--short", "HEAD")
        assert found.branch == "main"

    def test_bare_repository_revisions_resolve(self, tmp_path: Path, repo: Path):
        """Reading history must not require a work tree."""
        bare = tmp_path / "mirror.git"
        git(tmp_path, "clone", "--bare", "--quiet", str(repo), str(bare))

        found = discover_repository(bare)
        assert resolve_revision(found, "main").sha == git(bare, "rev-parse", "main")

    def test_tilde_is_expanded(self, repo: Path, monkeypatch):
        monkeypatch.setenv("HOME", str(repo.parent))
        found = discover_repository(f"~/{repo.name}")
        assert found.root == repo.resolve()

    def test_repository_is_immutable(self, repo: Path):
        found = discover_repository(repo)
        with pytest.raises(Exception):
            found.branch = "tampered"  # type: ignore[misc]


class TestResolveRevision:
    def test_branch_resolves_to_a_full_sha(self, repo: Path):
        found = discover_repository(repo)
        revision = resolve_revision(found, "main")

        assert revision.symbolic == "main"
        assert len(revision.sha) == 40
        assert revision.sha == git(repo, "rev-parse", "main")

    def test_symbolic_name_is_preserved(self, repo: Path):
        """The SHA gives integrity; the symbolic name is what a reviewer reads."""
        found = discover_repository(repo)
        assert resolve_revision(found, "v1.0.0").symbolic == "v1.0.0"

    def test_lightweight_tag_resolves(self, repo: Path):
        found = discover_repository(repo)
        revision = resolve_revision(found, "v1.0.0")
        assert revision.sha == git(repo, "rev-parse", "v1.0.0^{commit}")

    def test_annotated_tag_resolves_to_the_commit_not_the_tag_object(self, repo: Path):
        """The bug the real repositories cannot catch.

        An annotated tag names a tag object. Resolving to that object instead of
        the commit it points at would corrupt every later diff, and neither
        237feed nor 237feed-app would reveal it: both use lightweight tags,
        where the two SHAs coincide.
        """
        found = discover_repository(repo)
        revision = resolve_revision(found, "v2.0.0")

        tag_object = git(repo, "rev-parse", "v2.0.0")
        commit = git(repo, "rev-parse", "v2.0.0^{commit}")

        assert tag_object != commit, "fixture must use an annotated tag"
        assert revision.sha == commit
        assert revision.sha != tag_object

    def test_full_sha_resolves_to_itself(self, repo: Path):
        found = discover_repository(repo)
        head = git(repo, "rev-parse", "HEAD")
        assert resolve_revision(found, head).sha == head

    def test_abbreviated_sha_resolves_to_the_full_sha(self, repo: Path):
        found = discover_repository(repo)
        head = git(repo, "rev-parse", "HEAD")
        assert resolve_revision(found, head[:8]).sha == head

    @pytest.mark.parametrize("rev", ["HEAD", "HEAD~1", "main^", "feature/thing"])
    def test_relative_and_slashed_revisions_resolve(self, repo: Path, rev: str):
        found = discover_repository(repo)
        assert len(resolve_revision(found, rev).sha) == 40

    def test_unknown_revision_is_reported_with_the_name(self, repo: Path):
        found = discover_repository(repo)
        with pytest.raises(RevisionNotFound) as exc:
            resolve_revision(found, "v99.0.0")

        message = str(exc.value)
        assert "v99.0.0" in message
        assert str(repo.resolve()) in message

    def test_revision_that_looks_like_a_flag_is_not_treated_as_one(self, repo: Path):
        """--end-of-options stops this being parsed as an option."""
        found = discover_repository(repo)
        with pytest.raises(RevisionNotFound):
            resolve_revision(found, "--all")

    def test_ambiguous_revision_is_an_error_rather_than_a_guess(self, repo: Path):
        """A tag and branch of the same name must not be silently disambiguated.

        Git would apply its precedence rules; picking one would risk documenting
        the wrong thing while looking confident.
        """
        git(repo, "branch", "collision")
        git(repo, "tag", "collision", "HEAD~1")

        found = discover_repository(repo)
        with pytest.raises(AmbiguousRevision, match="more than one ref"):
            resolve_revision(found, "collision")

    def test_fully_qualified_ref_disambiguates(self, repo: Path):
        git(repo, "branch", "collision")
        git(repo, "tag", "collision", "HEAD~1")
        found = discover_repository(repo)

        branch = resolve_revision(found, "refs/heads/collision")
        tag = resolve_revision(found, "refs/tags/collision")
        assert branch.sha != tag.sha

    def test_resolution_works_from_a_subdirectory_path(self, repo: Path):
        subdir = repo / "nested"
        subdir.mkdir()
        found = discover_repository(subdir)
        assert resolve_revision(found, "main").sha == git(repo, "rev-parse", "main")

    def test_unborn_head_in_a_fresh_repository(self, tmp_path: Path):
        """A repository with no commits is valid but has nothing to resolve."""
        fresh = tmp_path / "fresh"
        fresh.mkdir()
        git(fresh, "init", "--initial-branch=main", "--quiet")

        found = discover_repository(fresh)
        assert found.branch == "main"  # the branch exists; it is just unborn

        with pytest.raises(RevisionNotFound):
            resolve_revision(found, "HEAD")

    def test_short_sha_is_twelve_characters(self, repo: Path):
        found = discover_repository(repo)
        revision = resolve_revision(found, "main")
        assert revision.short_sha == revision.sha[:12]
        assert len(revision.short_sha) == 12


class TestReadOnly:
    def test_discovery_and_resolution_do_not_change_the_repository(self, repo: Path):
        """Constat is read-only (PRODUCT_SPEC.md rule 7). Prove it."""
        before_status = git(repo, "status", "--porcelain")
        before_head = git(repo, "rev-parse", "HEAD")
        before_refs = git(repo, "show-ref")

        found = discover_repository(repo)
        resolve_revision(found, "main")
        resolve_revision(found, "v2.0.0")

        assert git(repo, "status", "--porcelain") == before_status
        assert git(repo, "rev-parse", "HEAD") == before_head
        assert git(repo, "show-ref") == before_refs

    def test_uncommitted_work_is_left_alone(self, repo: Path):
        (repo / "README.md").write_text("dirty\n")
        (repo / "untracked.txt").write_text("new\n")

        found = discover_repository(repo)
        resolve_revision(found, "main")

        assert (repo / "README.md").read_text() == "dirty\n"
        assert (repo / "untracked.txt").exists()


def test_errors_share_a_catchable_base():
    for error in (PathNotFound, NotARepository, RevisionNotFound, AmbiguousRevision):
        assert issubclass(error, RepositoryError)


def test_commit_file_helper_returns_a_sha(repo: Path):
    """The fixture helper is used by other tests; verify it does what it says."""
    sha = commit_file(repo, "extra.txt", "x\n", "Add extra")
    assert sha == git(repo, "rev-parse", "HEAD")
