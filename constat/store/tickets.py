"""Tickets and their documents (CON-33, D-029).

Creating a ticket creates its document in the same transaction. A ticket
without a document is a state the model does not allow, so it must not be
reachable even briefly.
"""

from __future__ import annotations

from datetime import datetime

from ..errors import AlreadyRegistered, NotRegistered
from ..models import Document, Ticket
from .workspace import Workspace, utc_now


def _ticket(row) -> Ticket:
    return Ticket(
        reference=row["reference"],
        title=row["title"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _document(row, reference: str) -> Document:
    return Document(
        ticket_reference=reference,
        body=row["body"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class TicketStore:
    """Tickets known to a workspace, each with its document."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def add(self, reference: str, title: str | None = None) -> Ticket:
        """Open a ticket and its document atomically."""
        if self.find(reference) is not None:
            raise AlreadyRegistered(
                f"ticket {reference!r} already exists. Its document is where "
                "further operations accumulate; opening it again would not "
                "create a second one."
            )

        now = utc_now()
        with self._workspace.transaction() as ws:
            cursor = ws.execute(
                "INSERT INTO ticket (reference, title, created_at) VALUES (?, ?, ?)",
                (reference, title, now),
            )
            ws.execute(
                "INSERT INTO document (ticket_id, created_at, updated_at, body) "
                "VALUES (?, ?, ?, '')",
                (int(cursor.lastrowid), now, now),
            )

        found = self.find(reference)
        assert found is not None  # just inserted
        return found

    def find(self, reference: str) -> Ticket | None:
        row = self._workspace.execute(
            "SELECT * FROM ticket WHERE reference = ?", (reference,)
        ).fetchone()
        return _ticket(row) if row else None

    def list(self) -> tuple[Ticket, ...]:
        rows = self._workspace.execute(
            "SELECT * FROM ticket ORDER BY created_at, reference"
        ).fetchall()
        return tuple(_ticket(row) for row in rows)

    def document(self, reference: str) -> Document:
        row = self._workspace.execute(
            "SELECT d.* FROM document d "
            "JOIN ticket t ON t.id = d.ticket_id WHERE t.reference = ?",
            (reference,),
        ).fetchone()
        if row is None:
            raise NotRegistered(
                f"no ticket {reference!r}. Open one with `ticket add`."
            )
        return _document(row, reference)
