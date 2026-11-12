"""Storing rule proposals and the decisions on them.

A rule proposal is a **dated, attributed reading of the evidence one run
gathered** (D-046, D-048) — a rule in a pre-acceptance state, not a separate
kind of object. Three properties follow, and all three are enforced by the
database rather than by this module:

**A reading is never edited.** `rule_proposal` aborts `UPDATE` and `DELETE`. A
later run makes a new reading; "current" is derived, never stored. Editing one
would rewrite what a reviewer was shown, and deleting one would erase that it
was ever offered — the same loss D-046 refuses for discarded readings.

**A decision does not mutate the reading.** It goes in its own append-only
table, the shape `document_version` uses for documents (CON-31). `rejected`
means inconclusive rather than wrong (D-036), so a later reading of better
evidence is expected rather than precluded.

**`revises_rule_id` is a claim, not a key.** Anchors find candidates; the
interpretation pass decides which rule a reading revises (D-050). A wrong claim
is a rejectable interpretation, not a corrupted identity.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..errors import NotRegistered
from ..models import Anchor, Behaviour, RuleProposal
from .workspace import Workspace, utc_now


@dataclass(frozen=True)
class StoredRuleProposal:
    """A rule proposal as it was read back, with its decision if any."""

    id: int
    run_id: int
    proposal: RuleProposal
    provider: str
    model: str | None
    created_at: str
    model_attested: bool = False
    revises_rule_id: int | None = None
    decision: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    rationale: str | None = None

    @property
    def is_decided(self) -> bool:
        return self.decision is not None

    @property
    def claims_to_revise(self) -> bool:
        return self.revises_rule_id is not None

    @property
    def attribution(self) -> str:
        """Who read the evidence, and how firmly that is known (D-057).

        One property rather than a string built at each display site: the
        document and the CLI both show this, and the caveat is the part that
        would quietly go missing if they each assembled it. An unattested
        reading must never render like an attested one.
        """
        reader = self.provider + (f" ({self.model})" if self.model else "")
        return reader if self.model_attested else f"{reader}, self-reported"

    def describe(self) -> str:
        state = self.decision or "awaiting a decision"
        return f"`{self.proposal.name}` — {state}"


class RuleProposals:
    """Reading and writing rule proposals. Append-only by construction."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def record(
        self,
        run_id: int,
        proposal: RuleProposal,
        provider: str,
        model: str | None = None,
        revises_rule_id: int | None = None,
        model_attested: bool = False,
    ) -> int:
        """Store one reading and return its identity.

        `provider` and `model` are recorded because a reviewer cannot weigh a
        reading without knowing what made it.

        `model_attested` says which of two things the model id is. False — the
        default, and the only value on the `submit_reply` path — means the
        caller asserted it (D-045): provenance worth keeping, not an observed
        fact. True means Constat issued the request and read the id off the
        response (D-057). The default is the weaker claim, so a caller that
        forgets the argument understates rather than overstates.
        """
        with self._workspace.transaction() as ws:
            cursor = ws.execute(
                "INSERT INTO rule_proposal "
                "(run_id, name, statement, revises_rule_id, provider, model, "
                " model_attested, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    proposal.name,
                    proposal.statement,
                    revises_rule_id,
                    provider,
                    model,
                    int(model_attested),
                    utc_now(),
                ),
            )
            proposal_id = int(cursor.lastrowid)

            for behaviour in proposal.behaviours:
                ws.execute(
                    "INSERT INTO rule_proposal_behaviour "
                    "(rule_proposal_id, description) VALUES (?, ?)",
                    (proposal_id, behaviour.description),
                )
            for anchor in proposal.anchors:
                repository_id = None
                if anchor.repository_alias is not None:
                    row = ws.execute(
                        "SELECT id FROM repository WHERE alias = ?",
                        (anchor.repository_alias,),
                    ).fetchone()
                    # A reading can name a repository that has since been
                    # unregistered. Keeping the glob and losing the scope is
                    # better than losing the reading.
                    repository_id = row["id"] if row is not None else None
                ws.execute(
                    "INSERT INTO rule_proposal_anchor "
                    "(rule_proposal_id, repository_id, path_glob) VALUES (?, ?, ?)",
                    (proposal_id, repository_id, anchor.path_glob),
                )
            return proposal_id

    def decide(
        self,
        proposal_id: int,
        decision: str,
        decided_by: str,
        rationale: str | None = None,
    ) -> None:
        """Record a human's answer to one reading.

        Appends rather than updating. A second decision on the same reading is
        allowed and both remain visible: changing one's mind is part of the
        history, not a correction to be hidden.
        """
        if decision not in ("accepted", "rejected"):
            raise ValueError(
                f"decision must be 'accepted' or 'rejected', not {decision!r}"
            )
        if self.find(proposal_id) is None:
            raise NotRegistered(f"no rule proposal with id {proposal_id}")

        with self._workspace.transaction() as ws:
            ws.execute(
                "INSERT INTO rule_proposal_decision "
                "(rule_proposal_id, decision, decided_by, decided_at, rationale) "
                "VALUES (?, ?, ?, ?, ?)",
                (proposal_id, decision, decided_by, utc_now(), rationale),
            )

    def find(self, proposal_id: int) -> StoredRuleProposal | None:
        row = self._workspace.execute(
            "SELECT * FROM rule_proposal WHERE id = ?", (proposal_id,)
        ).fetchone()
        return None if row is None else self._hydrate(row)

    def for_run(self, run_id: int) -> tuple[StoredRuleProposal, ...]:
        rows = self._workspace.execute(
            "SELECT * FROM rule_proposal WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return tuple(self._hydrate(row) for row in rows)

    def for_ticket(self, reference: str) -> tuple[StoredRuleProposal, ...]:
        """Every reading made for a ticket, oldest first.

        Across runs on purpose: a reading survives the run that produced it and
        the regeneration of the document body, which is the whole reason this
        table exists.
        """
        rows = self._workspace.execute(
            "SELECT p.* FROM rule_proposal p "
            "JOIN run r ON r.id = p.run_id "
            "JOIN document d ON d.id = r.document_id "
            "JOIN ticket t ON t.id = d.ticket_id "
            "WHERE t.reference = ? ORDER BY p.id",
            (reference,),
        ).fetchall()
        return tuple(self._hydrate(row) for row in rows)

    def undecided(self, reference: str) -> tuple[StoredRuleProposal, ...]:
        """Readings a human has not answered yet — the review queue."""
        return tuple(p for p in self.for_ticket(reference) if not p.is_decided)

    def candidates_for(
        self, anchors: tuple[Anchor, ...]
    ) -> tuple[int, ...]:
        """Rules whose anchors overlap these, as *candidates* (D-050).

        Anchor overlap is the signal that finds a rule, never the proof that it
        is the same one — one file routinely implements several rules. Deciding
        is the interpretation pass's job, and a human's to accept.
        """
        if not anchors:
            return ()
        globs = {anchor.path_glob for anchor in anchors}
        placeholders = ", ".join("?" for _ in globs)
        rows = self._workspace.execute(
            f"SELECT DISTINCT rule_id FROM anchor WHERE path_glob IN ({placeholders}) "
            "ORDER BY rule_id",
            tuple(globs),
        ).fetchall()
        return tuple(row["rule_id"] for row in rows)

    def _hydrate(self, row: sqlite3.Row) -> StoredRuleProposal:
        behaviours = tuple(
            Behaviour(description=r["description"])
            for r in self._workspace.execute(
                "SELECT description FROM rule_proposal_behaviour "
                "WHERE rule_proposal_id = ? ORDER BY id",
                (row["id"],),
            ).fetchall()
        )
        anchors = tuple(
            Anchor(
                path_glob=r["path_glob"],
                repository_alias=r["alias"],
            )
            for r in self._workspace.execute(
                "SELECT a.path_glob, rep.alias FROM rule_proposal_anchor a "
                "LEFT JOIN repository rep ON rep.id = a.repository_id "
                "WHERE a.rule_proposal_id = ? ORDER BY a.id",
                (row["id"],),
            ).fetchall()
        )
        # The latest decision wins for display; earlier ones remain in the
        # table, because changing one's mind is history rather than a mistake.
        decision = self._workspace.execute(
            "SELECT decision, decided_by, decided_at, rationale "
            "FROM rule_proposal_decision WHERE rule_proposal_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()

        return StoredRuleProposal(
            id=row["id"],
            run_id=row["run_id"],
            proposal=RuleProposal(
                name=row["name"],
                statement=row["statement"],
                behaviours=behaviours,
                anchors=anchors,
            ),
            provider=row["provider"],
            model=row["model"],
            model_attested=bool(row["model_attested"]),
            created_at=row["created_at"],
            revises_rule_id=row["revises_rule_id"],
            decision=None if decision is None else decision["decision"],
            decided_by=None if decision is None else decision["decided_by"],
            decided_at=None if decision is None else decision["decided_at"],
            rationale=None if decision is None else decision["rationale"],
        )
