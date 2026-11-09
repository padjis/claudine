"""Input definition and validation.

This module validates the *shape* of what the user typed and nothing more.
Whether the path is a real Git repository, and whether the revisions resolve to
real commits, is Session 04's work. Holding that boundary means an
invalid-input error can never be reported as a repository problem, and vice
versa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import InvalidInput

# A plain dataclass rather than a Pydantic model: Pydantic arrives in Session 07
# when there are persisted models to validate (D-002, D-015).


@dataclass(frozen=True)
class AnalysisRequest:
    """One unit of analysis: a repository, and a revision range within it.

    ``base`` is the already-known state; ``target`` is the new state being
    proposed for documentation. Both are the symbolic references the user
    supplied — a tag, branch, SHA or relative ref such as ``HEAD~5``. Session 04
    resolves them to full commit SHAs and keeps both forms: the SHA for
    integrity, the symbolic name because that is what a reviewer recognises.

    ``base`` is deliberately *not* "the last approved baseline". That is a
    separate comparison on a different axis (Session 15): base-to-target asks
    what changed in the code, baseline-to-proposal asks what changed in our
    documented understanding. Conflating them would let a re-analysis of an
    already-approved range mean something it does not.

    Revisions are meaningful only within ``repo``. Two repositories need not
    share a version space — one subject repository uses generated build tags
    while the other uses semver (D-009) — so an analysis spanning repositories
    is several of these requests, never one request with a shared range.
    """

    repo: Path
    base: str
    target: str


@dataclass(frozen=True)
class SnapshotRequest:
    """One unit of analysis: the state of a single revision.

    Answers "what does this branch do now?" rather than "what changed?". This
    is the open-ended counterpart to AnalysisRequest, and it exists because a
    delta alone cannot describe a product:

    * The first baseline for a repository has nothing to diff against. Without
      a snapshot, the earliest approved record would describe a change rather
      than a behaviour.
    * Drift (D-012) asks whether approved claims still hold *now*, which
      presumes a documented present state to compare against.

    ``rev`` is typically ``main`` or ``master``, but is not restricted to a
    branch — a tag or SHA is equally valid, and a release stream may not have a
    branch named ``main`` at all (product rule 6).
    """

    repo: Path
    rev: str


def _require_text(value: str | None, option: str) -> str:
    """Reject anything that is not a usable, unambiguous value.

    Whitespace is reported rather than stripped. Silently trimming would be a
    silent default, and the surrounding whitespace is almost always a paste
    accident worth surfacing (PRODUCT_SPEC.md section 7).
    """
    if value is None or not value.strip():
        raise InvalidInput(f"{option} must not be empty.")
    if value != value.strip():
        raise InvalidInput(
            f"{option} has surrounding whitespace: {value!r}. "
            "Remove it, or quote the value if the whitespace is deliberate."
        )
    return value


def build_request(repo: str | None, base: str | None, target: str | None) -> AnalysisRequest:
    """Validate raw CLI strings and return a request, or raise InvalidInput.

    Every important input is required; there are no defaults. In particular
    ``repo`` does not fall back to the current directory — a governance tool
    that silently analyses whichever directory you happen to be standing in is
    how a confidently wrong report gets produced.
    """
    repo_text = _require_text(repo, "--repo")
    base_text = _require_text(base, "--base")
    target_text = _require_text(target, "--target")

    if base_text == target_text:
        raise InvalidInput(
            f"--base and --target are both {base_text!r}; there would be nothing "
            "to compare."
        )

    return AnalysisRequest(repo=Path(repo_text), base=base_text, target=target_text)


def build_snapshot_request(repo: str | None, rev: str | None) -> SnapshotRequest:
    """Validate raw CLI strings for a state snapshot, or raise InvalidInput.

    ``rev`` is required rather than defaulting to the repository's current HEAD.
    A snapshot is a candidate for an approved baseline, so the revision it
    describes must be something the reviewer stated, not something Constat
    inferred from whichever branch happened to be checked out.
    """
    repo_text = _require_text(repo, "--repo")
    rev_text = _require_text(rev, "--rev")

    return SnapshotRequest(repo=Path(repo_text), rev=rev_text)
