"""Helpers for building throwaway repositories in tests.

Kept out of conftest.py so they can be imported explicitly rather than arriving
as fixtures. Tests must not depend on `237feed` being present, or on anything
about the machine running them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Committing requires an identity, and the machine's own config must not leak
# into fixtures. Passed per-invocation rather than written to a config file.
IDENTITY = [
    "-c",
    "user.name=Test Fixture",
    "-c",
    "user.email=fixture@example.invalid",
    "-c",
    "commit.gpgsign=false",
]


def git(repo: Path, *args: str) -> str:
    """Run git in `repo` and return stdout, raising on failure."""
    result = subprocess.run(
        ["git", *IDENTITY, *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def commit_file(repo: Path, name: str, content: str, message: str) -> str:
    """Write a file, commit it, and return the commit SHA."""
    (repo / name).write_text(content)
    git(repo, "add", name)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")
