"""Tests for evidence collection.

Done-when for CON-06 is "evidence records can be traced back to Git", so the
central tests actually run the recorded reproduce command and check it returns
the original.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from constat.evidence import (
    DEFAULT_LIMITS,
    ExcerptLimits,
    collect_commits,
    collect_evidence,
    describe_commit,
)
from constat.git import compare_revisions, discover_repository, resolve_revision

from helpers import commit_file, git


def evidence_for(repo: Path, base: str, target: str, limits: ExcerptLimits | None = None):
    found = discover_repository(repo)
    summary = compare_revisions(
        found, resolve_revision(found, base), resolve_revision(found, target)
    )
    return found, summary, collect_evidence(found, summary, limits or DEFAULT_LIMITS)


class TestCommits:
    def test_commits_in_range_are_captured(self, repo: Path):
        commit_file(repo, "a.txt", "a\n", "Add a")
        commit_file(repo, "b.txt", "b\n", "Add b")

        _, _, bundle = evidence_for(repo, "v2.0.0", "main")
        subjects = [c.subject for c in bundle.commits]
        assert subjects == ["Add b", "Add a"]  # newest first

    def test_author_and_committer_are_both_kept(self, repo: Path):
        """A rebase rewrites the committer but preserves the author.

        Collapsing them would misattribute the work.
        """
        commit_file(repo, "a.txt", "a\n", "Add a")
        _, _, bundle = evidence_for(repo, "v2.0.0", "main")
        commit = bundle.commits[0]

        assert commit.author_name == "Test Fixture"
        assert commit.committer_name == "Test Fixture"
        assert hasattr(commit, "authored_at") and hasattr(commit, "committed_at")

    def test_dates_are_timezone_aware(self, repo: Path):
        commit_file(repo, "a.txt", "a\n", "Add a")
        _, _, bundle = evidence_for(repo, "v2.0.0", "main")

        assert bundle.commits[0].authored_at.tzinfo is not None

    def test_multiline_body_survives(self, repo: Path):
        """Commit messages contain newlines, which is why records are separated
        by control characters rather than by line."""
        (repo / "a.txt").write_text("a\n")
        git(repo, "add", "a.txt")
        git(repo, "commit", "-m", "Subject line", "-m", "Body line one\nBody line two")

        _, _, bundle = evidence_for(repo, "v2.0.0", "main")
        commit = bundle.commits[0]

        assert commit.subject == "Subject line"
        assert "Body line one" in commit.body
        assert "Body line two" in commit.body

    def test_commit_sha_matches_git(self, repo: Path):
        commit_file(repo, "a.txt", "a\n", "Add a")
        _, _, bundle = evidence_for(repo, "v2.0.0", "main")

        assert bundle.commits[0].sha == git(repo, "rev-parse", "HEAD")

    def test_merge_commits_are_included_and_flagged(self, repo: Path):
        """Dropping merges would make the commit list disagree with the files."""
        git(repo, "checkout", "--quiet", "-b", "side")
        commit_file(repo, "side.txt", "s\n", "Side work")
        git(repo, "checkout", "--quiet", "main")
        commit_file(repo, "mainline.txt", "m\n", "Mainline work")
        git(repo, "merge", "--quiet", "--no-ff", "-m", "Merge side", "side")

        _, _, bundle = evidence_for(repo, "v2.0.0", "main")

        merges = bundle.merge_commits
        assert len(merges) == 1
        assert merges[0].subject == "Merge side"
        assert len(merges[0].parent_shas) == 2
        assert bundle.commit_count == 3

    def test_commit_range_matches_git_log(self, repo: Path):
        """git log A..B uses the same boundary as the merge-base diff (D-021)."""
        git(repo, "checkout", "--quiet", "-b", "target-branch")
        commit_file(repo, "t.txt", "t\n", "Target work")
        git(repo, "checkout", "--quiet", "main")
        commit_file(repo, "m.txt", "m\n", "Main work")

        found, summary, bundle = evidence_for(repo, "main", "target-branch")
        expected = git(
            repo, "log", "--format=%H", f"{summary.merge_base}..{summary.target.sha}"
        ).split()

        assert [c.sha for c in bundle.commits] == expected
        assert "Main work" not in [c.subject for c in bundle.commits]

    def test_describe_commit_reads_a_single_revision(self, repo: Path):
        """A snapshot has a revision but no range."""
        found = discover_repository(repo)
        commit = describe_commit(found, resolve_revision(found, "main"))

        assert commit.sha == git(repo, "rev-parse", "main")
        assert commit.subject == "Second commit"

    def test_empty_range_has_no_commits(self, repo: Path):
        found = discover_repository(repo)
        assert collect_commits(found, "v2.0.0", "v2.0.0") == ()


class TestTraceability:
    def test_reproduce_command_returns_the_original_diff(self, repo: Path):
        """The core promise of CON-06: evidence traces back to Git.

        Run the recorded command and confirm it yields the real diff.
        """
        commit_file(repo, "tracked.txt", "one\ntwo\nthree\n", "Add tracked.txt")
        _, _, bundle = evidence_for(repo, "v2.0.0", "main")

        excerpt = next(e for e in bundle.excerpts if e.path == "tracked.txt")
        result = subprocess.run(
            excerpt.pointer.reproduce,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        )

        assert "tracked.txt" in result.stdout
        assert "+one" in result.stdout

    def test_reproduce_command_works_for_a_truncated_excerpt(self, repo: Path):
        """Truncation is only safe because the full original stays reachable."""
        big = "".join(f"line {n}\n" for n in range(300))
        commit_file(repo, "big.txt", big, "Add big.txt")

        _, _, bundle = evidence_for(
            repo, "v2.0.0", "main", ExcerptLimits(max_lines_per_file=10, max_lines_total=10)
        )
        excerpt = next(e for e in bundle.excerpts if e.path == "big.txt")
        assert excerpt.truncated is True

        result = subprocess.run(
            excerpt.pointer.reproduce, shell=True, capture_output=True, text=True, check=True
        )
        assert len(result.stdout.splitlines()) > len(excerpt.text.splitlines())
        assert "line 299" in result.stdout

    def test_pointer_identifies_revision_and_path(self, repo: Path):
        commit_file(repo, "x.txt", "x\n", "Add x")
        found, summary, bundle = evidence_for(repo, "v2.0.0", "main")

        excerpt = next(e for e in bundle.excerpts if e.path == "x.txt")
        assert excerpt.pointer.revision == summary.target.sha
        assert excerpt.pointer.path == "x.txt"
        assert excerpt.pointer.repository_root == found.root
        assert str(excerpt.pointer).startswith(summary.target.sha[:12])


class TestBounding:
    def test_small_range_is_captured_whole(self, repo: Path):
        commit_file(repo, "small.txt", "a\nb\n", "Add small.txt")
        _, _, bundle = evidence_for(repo, "v2.0.0", "main")

        assert bundle.is_complete is True
        assert bundle.lines_omitted == 0
        assert "captured" in bundle.completeness_note()

    def test_per_file_cap_truncates_and_says_so(self, repo: Path):
        big = "".join(f"line {n}\n" for n in range(500))
        commit_file(repo, "big.txt", big, "Add big.txt")

        _, _, bundle = evidence_for(
            repo, "v2.0.0", "main", ExcerptLimits(max_lines_per_file=50, max_lines_total=4000)
        )
        excerpt = next(e for e in bundle.excerpts if e.path == "big.txt")

        assert excerpt.truncated is True
        assert excerpt.omitted_lines > 0
        assert len(excerpt.text.splitlines()) == 50
        assert excerpt.total_lines > 50
        assert excerpt.omitted_reason is not None
        assert bundle.is_complete is False

    def test_tight_budget_is_shared_rather_than_taken_first_come(self, repo: Path):
        """Allocation must not depend on filename order.

        First-come spending let a file that happens to sort early consume the
        budget and starve later ones — so which evidence a reviewer saw would
        depend on alphabetisation. Observed on 237feed-app, where
        package-lock.json is 3835 of 7442 diff lines in one range.
        """
        for name in ("a.txt", "b.txt", "c.txt"):
            commit_file(repo, name, "".join(f"{name} {n}\n" for n in range(100)), f"Add {name}")

        _, summary, bundle = evidence_for(
            repo, "v2.0.0", "main", ExcerptLimits(max_lines_per_file=90, max_lines_total=60)
        )

        # Every changed file still has a record.
        assert len(bundle.excerpts) == len(summary.changes)

        shares = {e.path: len(e.text.splitlines()) for e in bundle.excerpts}
        for name in ("a.txt", "b.txt", "c.txt"):
            assert shares[name] > 0, f"{name} was starved"

        # Comparable need, so comparable share — not winner-takes-all.
        assert max(shares.values()) - min(shares.values()) <= 1
        assert sum(shares.values()) <= 60

    def test_a_small_file_is_captured_whole_despite_a_huge_sibling(self, repo: Path):
        """The lockfile case: a large generated file must not crowd out a
        small, potentially business-relevant one."""
        commit_file(repo, "lockfile.json", "".join(f"dep {n}\n" for n in range(2000)), "Add lockfile")
        commit_file(repo, "rule.java", "if (amount > limit) reject();\n", "Add a rule")

        _, _, bundle = evidence_for(
            repo, "v2.0.0", "main", ExcerptLimits(max_lines_per_file=400, max_lines_total=500)
        )

        rule = next(e for e in bundle.excerpts if e.path == "rule.java")
        lockfile = next(e for e in bundle.excerpts if e.path == "lockfile.json")

        assert rule.truncated is False
        assert "if (amount > limit) reject();" in rule.text
        assert lockfile.truncated is True

    def test_allocation_is_independent_of_path_ordering(self, repo: Path):
        """Renaming a file must not change how much evidence other files get."""
        commit_file(repo, "zzz.txt", "".join(f"z {n}\n" for n in range(80)), "Add zzz")
        commit_file(repo, "aaa.txt", "".join(f"a {n}\n" for n in range(80)), "Add aaa")

        _, _, bundle = evidence_for(
            repo, "v2.0.0", "main", ExcerptLimits(max_lines_per_file=400, max_lines_total=100)
        )
        shares = {e.path: len(e.text.splitlines()) for e in bundle.excerpts}

        assert abs(shares["aaa.txt"] - shares["zzz.txt"]) <= 1

    def test_budget_starvation_still_keeps_the_file_on_record(self, repo: Path):
        """With a budget too small to share, files still appear with pointers."""
        for name in ("a.txt", "b.txt", "c.txt"):
            commit_file(repo, name, "".join(f"{name} {n}\n" for n in range(100)), f"Add {name}")

        _, summary, bundle = evidence_for(
            repo, "v2.0.0", "main", ExcerptLimits(max_lines_per_file=10, max_lines_total=1)
        )

        assert len(bundle.excerpts) == len(summary.changes)
        starved = [e for e in bundle.excerpts if not e.text and not e.is_binary]
        assert starved
        assert all(e.omitted_reason for e in starved)
        assert all(e.pointer.reproduce for e in starved)
        assert all(e.total_lines > 0 for e in starved)

    def test_omissions_are_counted(self, repo: Path):
        big = "".join(f"line {n}\n" for n in range(200))
        commit_file(repo, "big.txt", big, "Add big.txt")

        _, _, bundle = evidence_for(
            repo, "v2.0.0", "main", ExcerptLimits(max_lines_per_file=10, max_lines_total=10)
        )
        assert bundle.lines_omitted > 0
        assert str(bundle.lines_omitted) in bundle.completeness_note()

    def test_completeness_note_never_implies_completeness_when_truncated(self, repo: Path):
        big = "".join(f"line {n}\n" for n in range(200))
        commit_file(repo, "big.txt", big, "Add big.txt")

        _, _, bundle = evidence_for(
            repo, "v2.0.0", "main", ExcerptLimits(max_lines_per_file=5, max_lines_total=5)
        )
        note = bundle.completeness_note()

        assert "omitted" in note
        assert "remains available from Git" in note

    def test_defaults_are_the_measured_values(self):
        assert DEFAULT_LIMITS.max_lines_per_file == 400
        assert DEFAULT_LIMITS.max_lines_total == 4000


class TestAwkwardCases:
    def test_binary_file_is_recorded_without_a_fabricated_diff(self, repo: Path):
        (repo / "logo.bin").write_bytes(bytes(range(256)) * 4)
        git(repo, "add", "logo.bin")
        git(repo, "commit", "-m", "Add binary")

        _, _, bundle = evidence_for(repo, "v2.0.0", "main")
        excerpt = next(e for e in bundle.excerpts if e.path == "logo.bin")

        assert excerpt.is_binary is True
        assert excerpt.text == ""
        assert excerpt.total_lines == 0
        assert "binary" in (excerpt.omitted_reason or "")
        assert excerpt.pointer.reproduce

    def test_rename_excerpt_records_both_paths(self, repo: Path):
        commit_file(repo, "before.txt", "content\n" * 30, "Add before.txt")
        start = git(repo, "rev-parse", "HEAD")
        git(repo, "mv", "before.txt", "after.txt")
        git(repo, "commit", "-m", "Rename")

        _, _, bundle = evidence_for(repo, start, "main")
        excerpt = next(e for e in bundle.excerpts if e.path == "after.txt")

        assert excerpt.previous_path == "before.txt"
        assert "before.txt" in excerpt.pointer.reproduce
        assert "after.txt" in excerpt.pointer.reproduce

    def test_deleted_file_still_produces_evidence(self, repo: Path):
        commit_file(repo, "gone.txt", "bye\n", "Add gone.txt")
        start = git(repo, "rev-parse", "HEAD")
        git(repo, "rm", "--quiet", "gone.txt")
        git(repo, "commit", "-m", "Delete gone.txt")

        _, _, bundle = evidence_for(repo, start, "main")
        excerpt = next(e for e in bundle.excerpts if e.path == "gone.txt")
        assert "-bye" in excerpt.text

    def test_path_with_spaces_is_handled(self, repo: Path):
        name = "a file with spaces.txt"
        commit_file(repo, name, "x\n", "Add spaced name")

        _, _, bundle = evidence_for(repo, "v2.0.0", "main")
        excerpt = next(e for e in bundle.excerpts if e.path == name)
        assert excerpt.has_text

    def test_empty_range_yields_empty_bundle(self, repo: Path):
        git(repo, "commit", "--quiet", "--allow-empty", "-m", "Nothing")
        _, _, bundle = evidence_for(repo, "v2.0.0", "main")

        assert bundle.excerpts == ()
        assert bundle.commit_count == 1
        assert bundle.is_complete is True


class TestDeterminismAndReadOnly:
    def test_repeated_collection_is_identical(self, repo: Path):
        commit_file(repo, "a.txt", "a\n", "Add a")
        commit_file(repo, "b.txt", "b\n", "Add b")

        _, _, first = evidence_for(repo, "v2.0.0", "main")
        _, _, second = evidence_for(repo, "v2.0.0", "main")
        assert first == second

    def test_collection_does_not_change_the_repository(self, repo: Path):
        commit_file(repo, "a.txt", "a\n", "Add a")
        before = (
            git(repo, "status", "--porcelain"),
            git(repo, "rev-parse", "HEAD"),
            git(repo, "show-ref"),
        )

        evidence_for(repo, "v2.0.0", "main")

        after = (
            git(repo, "status", "--porcelain"),
            git(repo, "rev-parse", "HEAD"),
            git(repo, "show-ref"),
        )
        assert before == after

    def test_bundle_is_immutable(self, repo: Path):
        _, _, bundle = evidence_for(repo, "v1.0.0", "main")
        with pytest.raises(Exception):
            bundle.commits = ()  # type: ignore[misc]
