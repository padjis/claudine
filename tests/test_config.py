"""Tests for input validation.

Every rejection path gets its own test, and each asserts on the *message* —
"fail clearly" is the acceptance criterion for Session 03, so a correct exit
code with an unhelpful message is a failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.config import (
    AnalysisRequest,
    SnapshotRequest,
    build_request,
    build_snapshot_request,
)
from constat.errors import ConstatError, InvalidInput


class TestAnalysisRequest:
    def test_valid_input_builds_a_request(self):
        request = build_request("/tmp/repo", "v1.0.0", "v1.1.0")
        assert request == AnalysisRequest(
            repo=Path("/tmp/repo"), base="v1.0.0", target="v1.1.0"
        )

    def test_request_is_immutable(self):
        """A validated request must not be mutated downstream."""
        request = build_request("/tmp/repo", "v1.0.0", "v1.1.0")
        with pytest.raises(Exception):
            request.base = "tampered"  # type: ignore[misc]

    @pytest.mark.parametrize("option", ["--repo", "--base", "--target"])
    def test_empty_value_is_rejected_and_names_the_option(self, option):
        args = {"repo": "/tmp/repo", "base": "v1.0.0", "target": "v1.1.0"}
        args[option.lstrip("-")] = ""

        with pytest.raises(InvalidInput) as exc:
            build_request(**args)
        assert option in str(exc.value)

    @pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
    def test_whitespace_only_counts_as_empty(self, blank):
        with pytest.raises(InvalidInput, match="must not be empty"):
            build_request(blank, "v1.0.0", "v1.1.0")

    def test_none_is_rejected(self):
        with pytest.raises(InvalidInput, match="must not be empty"):
            build_request(None, "v1.0.0", "v1.1.0")

    def test_surrounding_whitespace_is_reported_not_silently_stripped(self):
        """Trimming would be a silent default; the paste accident must surface."""
        with pytest.raises(InvalidInput) as exc:
            build_request("/tmp/repo", " v1.0.0 ", "v1.1.0")

        message = str(exc.value)
        assert "--base" in message
        assert "whitespace" in message
        assert repr(" v1.0.0 ") in message

    def test_identical_base_and_target_is_rejected(self):
        """Comparing a revision with itself yields nothing; say so up front."""
        with pytest.raises(InvalidInput, match="nothing to compare"):
            build_request("/tmp/repo", "main", "main")

    def test_identical_revisions_message_names_the_value(self):
        with pytest.raises(InvalidInput) as exc:
            build_request("/tmp/repo", "v2.3.1", "v2.3.1")
        assert "v2.3.1" in str(exc.value)

    def test_relative_revisions_are_accepted(self):
        """HEAD~5 and friends are Git's business to resolve, not ours."""
        request = build_request("/tmp/repo", "HEAD~5", "HEAD")
        assert request.base == "HEAD~5"
        assert request.target == "HEAD"

    def test_nonexistent_path_is_not_rejected_here(self):
        """Filesystem and Git validation is Session 04, deliberately not Session 03.

        Keeping the boundary means "you typed it wrong" and "your repository is
        broken" stay distinguishable failures.
        """
        request = build_request("/no/such/path/anywhere", "a", "b")
        assert request.repo == Path("/no/such/path/anywhere")

    def test_incompatible_tag_schemes_are_both_accepted(self):
        """Subject A uses build tags, Subject B uses semver (D-009).

        Validation must not assume a shared version space.
        """
        build_request("/tmp/subject-a", "v2601abcd", "v2601ef01")
        build_request("/tmp/subject-b", "v2.3.0", "v2.3.1")


class TestSnapshotRequest:
    def test_valid_input_builds_a_request(self):
        request = build_snapshot_request("/tmp/repo", "main")
        assert request == SnapshotRequest(repo=Path("/tmp/repo"), rev="main")

    @pytest.mark.parametrize("option", ["--repo", "--rev"])
    def test_empty_value_is_rejected_and_names_the_option(self, option):
        args = {"repo": "/tmp/repo", "rev": "main"}
        args[option.lstrip("-")] = ""

        with pytest.raises(InvalidInput) as exc:
            build_snapshot_request(**args)
        assert option in str(exc.value)

    def test_rev_has_no_default(self):
        """A snapshot may become an approved baseline, so the revision must be
        stated by the reviewer rather than inferred from the checked-out branch.
        """
        with pytest.raises(InvalidInput, match="--rev must not be empty"):
            build_snapshot_request("/tmp/repo", None)

    @pytest.mark.parametrize("rev", ["main", "master", "v2.3.1", "release/2.4", "abc1234"])
    def test_rev_is_not_restricted_to_a_branch_name(self, rev):
        """Release streams are distinct (product rule 6); not every stream has
        a branch called main."""
        assert build_snapshot_request("/tmp/repo", rev).rev == rev


def test_invalid_input_is_a_constat_error():
    """Callers can catch the base class without knowing every subtype."""
    assert issubclass(InvalidInput, ConstatError)
