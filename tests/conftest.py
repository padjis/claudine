"""Shared fixtures.

Repositories are built from scratch in a temporary directory. Tests must not
depend on the real subject repositories being present, or on anything about
the machine running them. The git helpers live in helpers.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import commit_file, git


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    """A directory that exists but is not a repository."""
    target = tmp_path / "not-a-repo"
    target.mkdir()
    return target


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository on `main` with two commits, a branch, and two kinds of tag.

    Contains both a lightweight and an annotated tag on purpose. The real
    subject repositories use only lightweight tags (D-009), where `rev-parse`
    and `rev-parse ^{commit}` happen to agree — so they cannot catch a resolver
    that forgets `^{commit}`. This fixture can.
    """
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "--initial-branch=main", "--quiet")

    first = commit_file(path, "README.md", "first\n", "First commit")
    git(path, "tag", "v1.0.0")  # lightweight

    commit_file(path, "README.md", "second\n", "Second commit")
    git(path, "tag", "-a", "v2.0.0", "-m", "Release 2.0.0")  # annotated

    git(path, "branch", "feature/thing", first)
    return path
