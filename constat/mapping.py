"""Translate Git-layer dataclasses into published models.

One direction only (D-026): adapters build models; models never reach back
into Git. That keeps the published schema free of subprocess concerns, and
keeps the Git layer free of a Pydantic dependency.
"""

from __future__ import annotations

from .evidence.collector import EvidenceBundle
from .git.adapter import Repository, Revision, root_commits
from .git.diff import ChangeSummary, StateSummary
from .models import (
    ChangeSelection,
    CommitRecord,
    Completeness,
    EvidenceRecord,
    FileChangeRecord,
    Proposal,
    RepositoryRef,
    RevisionRef,
    StateSelection,
)


def revision_ref(revision: Revision) -> RevisionRef:
    return RevisionRef(symbolic=revision.symbolic, sha=revision.sha)


def repository_ref(repo: Repository, revision: Revision) -> RepositoryRef:
    """Build a repository reference, computing its durable identity.

    Costs one `git rev-list --max-parents=0`. Worth it: the result survives
    the repository being moved, renamed or re-cloned (D-025).
    """
    return RepositoryRef(
        root_commits=root_commits(repo, revision),
        local_path=str(repo.root),
        branch=repo.branch,
    )


def _evidence_records(bundle: EvidenceBundle) -> tuple[EvidenceRecord, ...]:
    return tuple(
        EvidenceRecord(
            path=excerpt.path,
            previous_path=excerpt.previous_path,
            change_type=excerpt.change_type.name,
            revision=excerpt.pointer.revision,
            reproduce=excerpt.pointer.reproduce,
            text=excerpt.text,
            total_lines=excerpt.total_lines,
            truncated=excerpt.truncated,
            omitted_lines=excerpt.omitted_lines,
            is_binary=excerpt.is_binary,
            omitted_reason=excerpt.omitted_reason,
        )
        for excerpt in bundle.excerpts
    )


def _commit_records(bundle: EvidenceBundle) -> tuple[CommitRecord, ...]:
    return tuple(
        CommitRecord(
            sha=commit.sha,
            author_name=commit.author_name,
            author_email=commit.author_email,
            authored_at=commit.authored_at,
            committer_name=commit.committer_name,
            committer_email=commit.committer_email,
            committed_at=commit.committed_at,
            subject=commit.subject,
            body=commit.body,
            parent_shas=commit.parent_shas,
            is_merge=commit.is_merge,
        )
        for commit in bundle.commits
    )


def change_proposal(
    repo: Repository, summary: ChangeSummary, bundle: EvidenceBundle
) -> Proposal:
    """Build a proposal describing what a range introduced."""
    return Proposal(
        repository=repository_ref(repo, summary.target),
        selection=ChangeSelection(
            base=revision_ref(summary.base),
            target=revision_ref(summary.target),
            merge_base=summary.merge_base,
        ),
        commits=_commit_records(bundle),
        changes=tuple(
            FileChangeRecord(
                change_type=change.change_type.name,
                path=change.path,
                previous_path=change.previous_path,
                similarity=change.similarity,
            )
            for change in summary.changes
        ),
        evidence=_evidence_records(bundle),
        completeness=Completeness(
            lines_captured=bundle.lines_captured,
            lines_omitted=bundle.lines_omitted,
            files_without_excerpt=bundle.files_without_excerpt,
            max_lines_per_file=bundle.limits.max_lines_per_file,
            max_lines_total=bundle.limits.max_lines_total,
        ),
    )


def state_proposal(
    repo: Repository, state: StateSummary, commit: CommitRecord
) -> Proposal:
    """Build a proposal describing what a revision contains.

    Carries no `changes` and no evidence excerpts: a state description must
    not borrow change vocabulary (D-022). The file inventory is expressed as
    the revision's contents, not as a list of additions.
    """
    return Proposal(
        repository=repository_ref(repo, state.revision),
        selection=StateSelection(revision=revision_ref(state.revision)),
        commits=(commit,),
    )


def commit_record(commit) -> CommitRecord:
    """Map a single collected commit, for the state path."""
    return CommitRecord(
        sha=commit.sha,
        author_name=commit.author_name,
        author_email=commit.author_email,
        authored_at=commit.authored_at,
        committer_name=commit.committer_name,
        committer_email=commit.committer_email,
        committed_at=commit.committed_at,
        subject=commit.subject,
        body=commit.body,
        parent_shas=commit.parent_shas,
        is_merge=commit.is_merge,
    )
