"""Helpers for building throwaway repositories and catalogue state in tests.

Kept out of conftest.py so they can be imported explicitly rather than arriving
as fixtures. Tests must not depend on the real subject repositories being
present, or on anything about the machine running them.

**Why the catalogue seeding lives here.** `Catalogue` used to carry
`add_rule`, `add_behaviour` and `add_anchor`. No CLI or MCP path ever reached
them — a rule is created only by `Review.accept` (D-048) — so they were a
writable door into the governance store that production could not use and
nothing guarded. They now live here, where a writable door is harmless, and
`Catalogue` is read-only.

Seeding writes rows directly, on purpose. A test about `rules_matching` or
`unmatched_paths` does not care how the rule got there, and routing every
fixture through a rule proposal and an acceptance would make those tests
slower and about something else. Tests that *are* about how a rule comes to
exist use `Review.accept`, which is the real path.
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


# -- catalogue seeding --------------------------------------------------------


def seed_rule(
    workspace,
    name: str,
    statement: str = "A seeded business rule.",
    behaviours: tuple[str, ...] = (),
    anchors: tuple = (),
) -> int:
    """Put a rule in the catalogue directly, and return its id.

    `anchors` takes either a glob or a `(glob, repository_alias)` pair. An
    unknown alias is stored as an unscoped anchor rather than refused: this is
    a fixture, and validating a test's own input is not its job.
    """
    cursor = workspace.execute(
        "INSERT INTO rule (name, statement, created_at) VALUES (?, ?, ?)",
        (name, statement, _now()),
    )
    rule_id = int(cursor.lastrowid)

    for description in behaviours:
        seed_behaviour(workspace, name, description)
    for anchor in anchors:
        if isinstance(anchor, str):
            seed_anchor(workspace, name, anchor)
        else:
            seed_anchor(workspace, name, *anchor)
    return rule_id


def seed_behaviour(workspace, rule_name: str, description: str) -> None:
    """Add one behaviour to a seeded rule."""
    workspace.execute(
        "INSERT INTO behaviour (rule_id, description, created_at) VALUES (?, ?, ?)",
        (_rule_id(workspace, rule_name), description, _now()),
    )


def seed_anchor(
    workspace, rule_name: str, path_glob: str, repository_alias: str | None = None
) -> None:
    """Add one anchor to a seeded rule, optionally scoped to a repository."""
    repository_id = None
    if repository_alias is not None:
        row = workspace.execute(
            "SELECT id FROM repository WHERE alias = ?", (repository_alias,)
        ).fetchone()
        repository_id = int(row["id"]) if row is not None else None
    workspace.execute(
        "INSERT INTO anchor (rule_id, repository_id, path_glob, created_at) "
        "VALUES (?, ?, ?, ?)",
        (_rule_id(workspace, rule_name), repository_id, path_glob, _now()),
    )


def _rule_id(workspace, name: str) -> int:
    row = workspace.execute(
        "SELECT id FROM rule WHERE name = ? ORDER BY id DESC LIMIT 1", (name,)
    ).fetchone()
    if row is None:
        raise AssertionError(f"test fixture error: no seeded rule named {name!r}")
    return int(row["id"])


def _now() -> str:
    from constat.store.workspace import utc_now

    return utc_now()
