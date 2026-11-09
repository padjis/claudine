"""Evidence collection.

Deterministic capture of what Git actually says, with every record traceable
back to the repository it came from.
"""

from .collector import (
    DEFAULT_LIMITS,
    Commit,
    DiffExcerpt,
    EvidenceBundle,
    ExcerptLimits,
    SourcePointer,
    collect_commits,
    collect_evidence,
    describe_commit,
)

__all__ = [
    "DEFAULT_LIMITS",
    "Commit",
    "DiffExcerpt",
    "EvidenceBundle",
    "ExcerptLimits",
    "SourcePointer",
    "collect_commits",
    "collect_evidence",
    "describe_commit",
]
