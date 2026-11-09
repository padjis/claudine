"""Read-only access to a local Git repository.

Shells out to the `git` binary rather than reimplementing Git internals (D-002).
Every command issued here is read-only: this module never writes to a
repository, never mutates a working tree, and never takes a lock
(PRODUCT_SPEC.md rule 7).

Deliberately absent: anything that *chooses* a revision for the user. No
"latest tag", no default branch guess. One subject repository carries 777
generated build tags while the other uses 11 semver release tags (D-009), so any
convenience that picked a revision would pick the wrong one on at least one of
them. Revisions are always named by the caller.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..errors import (
    AmbiguousRevision,
    GitCommandFailed,
    GitUnavailable,
    NotARepository,
    PathNotFound,
    RevisionNotFound,
)

GIT = "git"


@dataclass(frozen=True)
class Repository:
    """A Git repository that has been confirmed to exist and be readable.

    ``given`` and ``root`` can differ: Git resolves a path inside a repository
    to its enclosing repository, so ``--repo some/subdir`` finds the whole
    repository. That is convenient but it widens scope silently, so both paths
    are kept and the CLI reports the root. A reviewer must be able to see which
    repository was actually read.
    """

    given: Path
    root: Path
    branch: str | None
    """The branch HEAD points at, or None when HEAD is detached.

    A bare repository still has a HEAD symref — its default branch — so this is
    populated for mirrors too. Read from HEAD and never inferred: Constat does
    not assume a repository's default branch is called `main`, because release
    streams are distinct (product rule 6)."""

    @property
    def is_detached(self) -> bool:
        return self.branch is None


@dataclass(frozen=True)
class Revision:
    """A revision resolved to a commit.

    Both forms are kept: ``sha`` gives integrity and is what evidence points at,
    ``symbolic`` is what the reviewer typed and recognises. A report that showed
    only the SHA would be correct and unreadable.
    """

    symbolic: str
    sha: str

    @property
    def short_sha(self) -> str:
        return self.sha[:12]


def _env() -> dict[str, str]:
    """Environment for every git call.

    ``GIT_OPTIONAL_LOCKS=0`` keeps reads from taking a lock, so Constat cannot
    interfere with work in progress. ``LC_ALL=C`` keeps git's own messages
    stable, so error handling does not depend on the caller's locale.
    """
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["LC_ALL"] = "C"
    return env


def run_git(args: Sequence[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the completed process without raising.

    Never uses a shell, so no argument can be interpreted as one.
    """
    try:
        return subprocess.run(
            [GIT, *args],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
            env=_env(),
        )
    except FileNotFoundError as exc:  # git not installed
        raise GitUnavailable(
            "the `git` command was not found. Constat shells out to git and "
            "cannot work without it."
        ) from exc


def discover_repository(path: Path | str) -> Repository:
    """Confirm `path` is a readable Git repository and describe it.

    Raises PathNotFound, NotARepository, or GitUnavailable. Each failure is
    distinct so the message can say what is actually wrong.
    """
    given = Path(path).expanduser()

    if not given.exists():
        raise PathNotFound(f"no such path: {given}")
    if not given.is_dir():
        raise NotARepository(f"not a directory: {given}")

    git_dir = run_git(["rev-parse", "--git-dir"], cwd=given)
    if git_dir.returncode != 0:
        raise NotARepository(
            f"{given} is a directory but not a Git repository "
            "(and is not inside one)."
        )

    root = _repository_root(given)
    return Repository(given=given, root=root, branch=_current_branch(given))


def _repository_root(path: Path) -> Path:
    """The work-tree root, or the git directory for a bare repository."""
    toplevel = run_git(["rev-parse", "--show-toplevel"], cwd=path)
    if toplevel.returncode == 0 and toplevel.stdout.strip():
        return Path(toplevel.stdout.strip())

    # Bare repositories have no work tree; the git directory is the repository.
    absolute = run_git(["rev-parse", "--absolute-git-dir"], cwd=path)
    if absolute.returncode == 0 and absolute.stdout.strip():
        return Path(absolute.stdout.strip())

    raise GitCommandFailed(
        f"could not determine the repository root for {path}: "
        f"{toplevel.stderr.strip() or absolute.stderr.strip()}"
    )


def _current_branch(path: Path) -> str | None:
    """The checked-out branch, or None when detached, bare, or unborn."""
    result = run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=path)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def root_commits(repo: Repository, revision: Revision) -> tuple[str, ...]:
    """The parentless commits in `revision`'s history, sorted.

    Used as the repository's durable identity (D-025). A filesystem path
    changes when a clone moves and a remote URL changes when a project
    migrates host; the root commit does not. Sorting makes the choice
    deterministic when a repository has several roots, which happens with
    orphan branches or grafted histories.
    """
    result = run_git(
        ["rev-list", "--max-parents=0", revision.sha], cwd=repo.root
    )
    if result.returncode != 0:
        raise GitCommandFailed(
            f"could not find the root commit(s) for {revision.symbolic} in "
            f"{repo.root}: {result.stderr.strip()}"
        )

    roots = tuple(sorted(line.strip() for line in result.stdout.split() if line.strip()))
    if not roots:
        raise GitCommandFailed(
            f"{revision.symbolic} in {repo.root} has no root commit, which "
            "should be impossible for a resolved revision."
        )
    return roots


def resolve_revision(repo: Repository, symbolic: str) -> Revision:
    """Resolve a symbolic revision to a commit SHA within `repo`.

    Accepts anything git accepts — branch, tag, SHA, ``HEAD~5``. Always resolves
    through ``^{commit}``: an annotated tag names a tag object, and resolving to
    that object rather than the commit it points at would quietly corrupt every
    later diff.

    An ambiguous reference is an error rather than something to resolve by git's
    precedence rules. Raises RevisionNotFound or AmbiguousRevision.
    """
    # --end-of-options stops a revision that begins with "-" being read as a
    # flag (git 2.24+). --quiet is deliberately NOT passed: it would suppress
    # the "refname is ambiguous" warning, which is the only signal git gives
    # that a name matched more than one ref.
    result = run_git(
        ["rev-parse", "--verify", "--end-of-options", f"{symbolic}^{{commit}}"],
        cwd=repo.root,
    )

    sha = result.stdout.strip()

    # Order matters. An unresolvable revision exits non-zero, and git's message
    # for it also contains the word "ambiguous" in some forms — so "not found"
    # must be decided before "ambiguous" is considered. A genuinely ambiguous
    # name exits zero and warns.
    if result.returncode != 0 or not sha:
        raise RevisionNotFound(
            f"{symbolic!r} does not resolve to a commit in {repo.root}."
        )

    if "ambiguous" in result.stderr.lower():
        raise AmbiguousRevision(
            f"{symbolic!r} matches more than one ref in {repo.root}. "
            "Qualify it, for example as refs/heads/… or refs/tags/…, so the "
            "revision being documented is unambiguous."
        )

    return Revision(symbolic=symbolic, sha=sha)
