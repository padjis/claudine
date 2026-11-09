"""Persistent local state.

The workspace holds registered repositories, tickets, documents and the
immutable record of approvals (D-027, D-029).
"""

from .schema import SCHEMA_VERSION
from .workspace import Workspace, database_path, utc_now, workspace_home

__all__ = [
    "SCHEMA_VERSION",
    "Workspace",
    "database_path",
    "utc_now",
    "workspace_home",
]
