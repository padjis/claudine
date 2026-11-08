"""Read-only Git access.

Everything in this package shells out to the `git` binary rather than
reimplementing Git (D-002), and is strictly read-only (PRODUCT_SPEC.md rule 7).
"""

from .adapter import Repository, Revision, discover_repository, resolve_revision

__all__ = ["Repository", "Revision", "discover_repository", "resolve_revision"]
