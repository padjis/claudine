"""Workspace settings: answers that belong to a setup, not to a run (D-060).

One table, one question so far. `reader` records who reads the evidence —
an agent over MCP, or Constat itself through a provider.

**Why this is stored rather than passed.** D-059 refuses a rule-generating
command when nothing can read the evidence, and at the command line these two
are indistinguishable: no provider because an agent is about to read this, and
no provider because you forgot to export the key. The flag `--no-provider` was
Constat asking that question on every ticket. It is not a per-ticket question:
nobody alternates between MCP and a provider from one ticket to the next. Ask
once, record it, and let the refusal protect the case it was built for.
"""

from __future__ import annotations

from ..errors import InvalidInput
from .workspace import Workspace, utc_now

READER = "reader"

READER_MCP = "mcp"
"""An agent reads the evidence through `constat mcp`. Constat holds no key and
calls nothing; no rule-generating command refuses for want of a provider."""

READER_PROVIDER = "provider"
"""Constat reads the evidence itself, through `CONSTAT_AI_PROVIDER`. A missing
or misconfigured provider is a fault and is refused (D-041, D-059)."""

READERS = (READER_MCP, READER_PROVIDER)

DEFAULT_READER = READER_PROVIDER
"""The strict one. A workspace that never said how it reads is treated as
expecting a provider, so the refusal D-059 added stays in force unless someone
turns it off deliberately — the safe direction for a default to lean."""


class Settings:
    """Read and write workspace settings."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self._workspace.execute(
            "SELECT value FROM setting WHERE key = ?", (key,)
        ).fetchone()
        return default if row is None else row["value"]

    def set(self, key: str, value: str) -> None:
        """Set a value, replacing any previous one.

        Settings are *not* append-only, unlike everything in the governance
        store. A setting is configuration — it says how this workspace is
        operated, never what anyone decided — and a history of configuration
        changes would imply it carried authority it does not have.
        """
        with self._workspace.transaction() as ws:
            ws.execute(
                "INSERT INTO setting (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, utc_now()),
            )

    @property
    def reader(self) -> str:
        return self.get(READER, DEFAULT_READER) or DEFAULT_READER

    def set_reader(self, value: str) -> None:
        if value not in READERS:
            raise InvalidInput(
                f"reader must be one of {', '.join(READERS)}, not {value!r}. "
                f"`{READER_MCP}` means an agent reads the evidence through the "
                f"MCP server; `{READER_PROVIDER}` means Constat reads it itself."
            )
        self.set(READER, value)
