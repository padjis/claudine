"""Tests for change and state summaries.

Done-when for CON-05 is "a deterministic change summary for two revisions", so
determinism and the awkward Git cases — renames, deletions, merges — are the
point rather than an afterthought.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.errors import BackwardsRange, NoCommonAncestor
from constat.git import (
    ChangeType,
    compare_revisions,
    discover_repository,
    find_merge_base,
    resolve_revision,
    summarise_state,
)

from helpers import commit_file, git


def summarise(repo: Path, base: str, target: str):
    found = discover_repository(repo)
    return compare_revisions(
        found, resolve_revision(found, base), resolve_revision(found, target)
    )


def paths_by_type(summary) -> dict[ChangeType, list[str]]:
    result: dict[ChangeType, list[str]] = {}
    for change in summary.changes:
        result.setdefault(change.change_type, []).append(change.path)
    return result


class TestChangeTypes:
    def test_added_file(self, repo: Path):
        commit_file(repo, "new.txt", "x\n", "Add new.txt")
        summary = summarise(repo, "v2.0.0", "main")

        assert [c.path for c in summary.of_type(ChangeType.ADDED)] == ["new.txt"]

    def test_modified_file(self, repo: Path):
        commit_file(repo, "README.md", "changed\n", "Edit README")
        summary = summarise(repo, "v2.0.0", "main")

        assert [c.path for c in summary.of_type(ChangeType.MODIFIED)] == ["README.md"]

    def test_deleted_file(self, repo: Path):
        """Deletions are reported explicitly, not as an absence."""
        commit_file(repo, "doomed.txt", "x\n", "Add doomed.txt")
        start = git(repo, "rev-parse", "HEAD")
        git(repo, "rm", "--quiet", "doomed.txt")
        git(repo, "commit", "-m", "Remove doomed.txt")

        summary = summarise(repo, start, "main")
        assert [c.path for c in summary.of_type(ChangeType.DELETED)] == ["doomed.txt"]

    def test_rename_keeps_both_paths(self, repo: Path):
        """A rename must not be reported as a delete plus an add.

        Doing so would misstate the change and break evidence anchored to the
        old path.
        """
        commit_file(repo, "old-name.txt", "stable content\n" * 20, "Add old-name.txt")
        start = git(repo, "rev-parse", "HEAD")
        git(repo, "mv", "old-name.txt", "new-name.txt")
        git(repo, "commit", "-m", "Rename old-name.txt")

        summary = summarise(repo, start, "main")

        renames = summary.of_type(ChangeType.RENAMED)
        assert len(renames) == 1
        assert renames[0].path == "new-name.txt"
        assert renames[0].previous_path == "old-name.txt"
        assert renames[0].is_rename is True
        assert renames[0].similarity == 100

        by_type = paths_by_type(summary)
        assert ChangeType.ADDED not in by_type
        assert ChangeType.DELETED not in by_type

    def test_rename_with_edits_reports_similarity_below_full(self, repo: Path):
        original = "".join(f"line {n}\n" for n in range(40))
        commit_file(repo, "a.txt", original, "Add a.txt")
        start = git(repo, "rev-parse", "HEAD")

        git(repo, "mv", "a.txt", "b.txt")
        (repo / "b.txt").write_text(original + "extra line\nanother\n")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-m", "Rename and edit")

        renames = summarise(repo, start, "main").of_type(ChangeType.RENAMED)
        assert len(renames) == 1
        assert renames[0].previous_path == "a.txt"
        assert renames[0].similarity is not None
        assert 0 < renames[0].similarity < 100

    def test_path_with_spaces_and_unicode(self, repo: Path):
        """-z parsing, rather than line parsing, is why this works."""
        name = "a file with spaces and é.txt"
        commit_file(repo, name, "x\n", "Add awkward name")

        summary = summarise(repo, "v2.0.0", "main")
        assert [c.path for c in summary.changes] == [name]

    def test_path_with_a_newline(self, repo: Path):
        """Line-based parsing would silently mangle this."""
        name = "line1\nline2.txt"
        (repo / name).write_text("x\n")
        git(repo, "add", "--", name)
        git(repo, "commit", "-m", "Add newline name")

        summary = summarise(repo, "v2.0.0", "main")
        assert [c.path for c in summary.changes] == [name]

    def test_unrecognised_status_becomes_unknown_not_a_guess(self):
        assert ChangeType.parse("Z") is ChangeType.UNKNOWN
        assert ChangeType.parse("") is ChangeType.UNKNOWN
        assert ChangeType.parse("R100") is ChangeType.RENAMED


class TestMergeBaseSemantics:
    def test_merge_base_is_recorded(self, repo: Path):
        commit_file(repo, "x.txt", "x\n", "Add x")
        summary = summarise(repo, "v1.0.0", "main")

        assert summary.merge_base == git(repo, "merge-base", "v1.0.0", "main")

    def test_linear_history_has_base_as_merge_base(self, repo: Path):
        commit_file(repo, "x.txt", "x\n", "Add x")
        summary = summarise(repo, "v2.0.0", "main")

        assert summary.base_is_merge_base is True

    def test_divergent_branches_exclude_changes_made_only_on_base(self, repo: Path):
        """The point of D-021.

        Work done on the base branch after the fork must not appear as part of
        what the target introduced. An endpoint diff would show it as a
        deletion, which would be a confidently wrong claim.
        """
        git(repo, "checkout", "--quiet", "-b", "target-branch")
        commit_file(repo, "from-target.txt", "t\n", "Target-only work")

        git(repo, "checkout", "--quiet", "main")
        commit_file(repo, "from-main.txt", "m\n", "Main-only work")

        summary = summarise(repo, "main", "target-branch")
        changed = [c.path for c in summary.changes]

        assert changed == ["from-target.txt"]
        assert "from-main.txt" not in changed
        assert summary.base_is_merge_base is False

    def test_endpoint_diff_would_have_differed(self, repo: Path):
        """Pins the difference between the two semantics, so a silent switch to
        `..` would fail loudly here rather than change reports quietly."""
        git(repo, "checkout", "--quiet", "-b", "target-branch")
        commit_file(repo, "from-target.txt", "t\n", "Target-only work")
        git(repo, "checkout", "--quiet", "main")
        commit_file(repo, "from-main.txt", "m\n", "Main-only work")

        endpoint = git(repo, "diff", "--name-status", "main", "target-branch")
        assert "from-main.txt" in endpoint  # the endpoint diff sees a deletion

        summary = summarise(repo, "main", "target-branch")
        assert "from-main.txt" not in [c.path for c in summary.changes]

    def test_merge_commit_in_range(self, repo: Path):
        """Merges must not break the summary (named explicitly in the roadmap)."""
        # Not "feature": the fixture already has refs/heads/feature/thing, and
        # a ref cannot be both a file and a directory.
        git(repo, "checkout", "--quiet", "-b", "merge-source")
        commit_file(repo, "feature.txt", "f\n", "Feature work")
        git(repo, "checkout", "--quiet", "main")
        commit_file(repo, "mainline.txt", "m\n", "Mainline work")
        git(repo, "merge", "--quiet", "--no-ff", "-m", "Merge work", "merge-source")

        summary = summarise(repo, "v2.0.0", "main")
        changed = [c.path for c in summary.changes]

        assert "feature.txt" in changed
        assert "mainline.txt" in changed

    def test_backwards_range_is_refused_not_reported_as_empty(self, repo: Path):
        """An ancestor target yields an empty merge-base diff.

        Reporting "no changes" would be a confidently wrong answer to a reversed
        argument order, so it is refused instead.
        """
        with pytest.raises(BackwardsRange, match="runs backwards"):
            summarise(repo, "main", "v1.0.0")

    def test_backwards_range_message_suggests_the_fix(self, repo: Path):
        with pytest.raises(BackwardsRange) as exc:
            summarise(repo, "main", "v1.0.0")

        message = str(exc.value)
        assert "--base" in message and "--target" in message

    def test_unrelated_histories_are_refused(self, repo: Path):
        """No common ancestor is not the same as "everything changed"."""
        git(repo, "checkout", "--quiet", "--orphan", "orphan-branch")
        git(repo, "rm", "--quiet", "-rf", ".")
        commit_file(repo, "alone.txt", "a\n", "Orphan root commit")

        found = discover_repository(repo)
        with pytest.raises(NoCommonAncestor, match="no common ancestor"):
            compare_revisions(
                found,
                resolve_revision(found, "main"),
                resolve_revision(found, "orphan-branch"),
            )

    def test_find_merge_base_matches_git(self, repo: Path):
        found = discover_repository(repo)
        base = resolve_revision(found, "v1.0.0")
        target = resolve_revision(found, "main")

        assert find_merge_base(found, base, target) == git(
            repo, "merge-base", "v1.0.0", "main"
        )


class TestDeterminism:
    def test_repeated_runs_produce_identical_summaries(self, repo: Path):
        commit_file(repo, "b.txt", "b\n", "Add b")
        commit_file(repo, "a.txt", "a\n", "Add a")

        first = summarise(repo, "v2.0.0", "main")
        second = summarise(repo, "v2.0.0", "main")
        assert first == second

    def test_changes_are_sorted_by_path(self, repo: Path):
        for name in ("zebra.txt", "apple.txt", "mango.txt"):
            commit_file(repo, name, "x\n", f"Add {name}")

        summary = summarise(repo, "v2.0.0", "main")
        paths = [c.path for c in summary.changes]
        assert paths == sorted(paths)

    def test_empty_range_is_empty_not_an_error(self, repo: Path):
        """Comparing a revision to a descendant with no changes is legitimate."""
        git(repo, "commit", "--quiet", "--allow-empty", "-m", "Empty commit")

        summary = summarise(repo, "v2.0.0", "main")
        assert summary.is_empty is True
        assert summary.changes == ()

    def test_summary_is_immutable(self, repo: Path):
        summary = summarise(repo, "v1.0.0", "main")
        with pytest.raises(Exception):
            summary.changes = ()  # type: ignore[misc]


class TestStateSummary:
    def test_lists_files_present_at_a_revision(self, repo: Path):
        commit_file(repo, "second.txt", "x\n", "Add second")

        found = discover_repository(repo)
        state = summarise_state(found, resolve_revision(found, "main"))

        assert set(state.paths) == {"README.md", "second.txt"}
        assert state.file_count == 2

    def test_state_uses_no_change_vocabulary(self, repo: Path):
        """A snapshot says what is present, not what was added (D-016).

        StateSummary carries plain paths rather than FileChange objects, so
        there is no ChangeType to misread as "all of this just appeared".
        """
        found = discover_repository(repo)
        state = summarise_state(found, resolve_revision(found, "main"))

        assert all(isinstance(path, str) for path in state.paths)
        assert not hasattr(state, "changes")

    def test_paths_are_sorted(self, repo: Path):
        for name in ("z.txt", "a.txt", "m.txt"):
            commit_file(repo, name, "x\n", f"Add {name}")

        found = discover_repository(repo)
        state = summarise_state(found, resolve_revision(found, "main"))
        assert list(state.paths) == sorted(state.paths)

    def test_state_at_an_older_revision_reflects_that_revision(self, repo: Path):
        commit_file(repo, "later.txt", "x\n", "Add later")

        found = discover_repository(repo)
        old = summarise_state(found, resolve_revision(found, "v1.0.0"))

        assert "later.txt" not in old.paths
        assert "README.md" in old.paths

    def test_nested_paths_are_listed_recursively(self, repo: Path):
        nested = repo / "src" / "deep"
        nested.mkdir(parents=True)
        (nested / "mod.py").write_text("x\n")
        git(repo, "add", "src/deep/mod.py")
        git(repo, "commit", "-m", "Add nested file")

        found = discover_repository(repo)
        state = summarise_state(found, resolve_revision(found, "main"))
        assert "src/deep/mod.py" in state.paths


class TestReadOnly:
    def test_summarising_does_not_change_the_repository(self, repo: Path):
        before = (
            git(repo, "status", "--porcelain"),
            git(repo, "rev-parse", "HEAD"),
            git(repo, "show-ref"),
        )

        found = discover_repository(repo)
        compare_revisions(
            found, resolve_revision(found, "v1.0.0"), resolve_revision(found, "main")
        )
        summarise_state(found, resolve_revision(found, "main"))

        after = (
            git(repo, "status", "--porcelain"),
            git(repo, "rev-parse", "HEAD"),
            git(repo, "show-ref"),
        )
        assert before == after

    def test_uncommitted_work_does_not_leak_into_the_summary(self, repo: Path):
        """The summary describes committed revisions, not the working tree."""
        (repo / "dirty.txt").write_text("uncommitted\n")
        (repo / "README.md").write_text("locally edited\n")

        summary = summarise(repo, "v1.0.0", "main")
        paths = [c.path for c in summary.changes]
        assert "dirty.txt" not in paths
