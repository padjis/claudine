"""Read-only Git access.

Everything in this package shells out to the `git` binary rather than
reimplementing Git (D-002), and is strictly read-only (PRODUCT_SPEC.md rule 7).
"""

from .adapter import (
    Repository,
    Revision,
    discover_repository,
    local_branches,
    resolve_default_branch,
    resolve_revision,
    root_commits,
)
from .diff import (
    ChangeSummary,
    ChangeType,
    FileChange,
    StateSummary,
    compare_revisions,
    find_merge_base,
    summarise_state,
)

__all__ = [
    "ChangeSummary",
    "ChangeType",
    "FileChange",
    "Repository",
    "Revision",
    "StateSummary",
    "compare_revisions",
    "discover_repository",
    "local_branches",
    "resolve_default_branch",
    "root_commits",
    "find_merge_base",
    "resolve_revision",
    "summarise_state",
]
