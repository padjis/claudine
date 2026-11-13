"""Accepting or rejecting a rule proposal (CON-44).

Acceptance is the only way a rule enters or changes in the catalogue (D-048),
and it is a human act — nothing here can be reached by a model.

**Accepting creates a version, never a mutation of history.** `rule` holds the
current state and `rule_version` the frozen record, the same split
`document`/`document_version` already uses (D-029). A later acceptance of a
reading that revises the rule appends version 2; version 1 stays readable
forever, pointing at the reading a human accepted to produce it.

**Rejecting changes nothing.** Under D-036 it means *inconclusive* — another
PR is expected — not "this rule is wrong" and not "never propose this again".
So it records a decision and leaves the catalogue alone.

**Which rule a reading revises is the reading's claim, not a key** (D-050). A
human accepting it is accepting that claim too, which is why acceptance is the
only place the claim takes effect.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidInput, NotRegistered
from .proposals import RuleProposals, StoredRuleProposal
from .workspace import Workspace, utc_now


@dataclass(frozen=True)
class Acceptance:
    """What accepting a rule proposal produced."""

    rule_id: int
    rule_version_id: int
    version_no: int
    created_rule: bool

    @property
    def is_revision(self) -> bool:
        return not self.created_rule


class Review:
    """A human's answers to rule proposals."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace
        self._proposals = RuleProposals(workspace)

    def accept(
        self,
        proposal_id: int,
        decided_by: str,
        rationale: str | None = None,
        attribution: str = "stated",
    ) -> Acceptance:
        """Accept a reading: record the decision and baseline a rule version."""
        stored = self._require(proposal_id)
        if stored.decision == "accepted":
            raise InvalidInput(
                f"rule proposal {proposal_id} is already accepted. Accepting "
                "it again would baseline a second identical version."
            )

        rule_id, created = self._target_rule(stored)
        version_id, version_no = self._baseline(rule_id, stored)
        self._proposals.decide(
            proposal_id, "accepted", decided_by, rationale, attribution
        )
        return Acceptance(
            rule_id=rule_id,
            rule_version_id=version_id,
            version_no=version_no,
            created_rule=created,
        )

    def reject(
        self,
        proposal_id: int,
        decided_by: str,
        rationale: str | None = None,
        attribution: str = "stated",
    ) -> None:
        """Reject a reading as inconclusive (D-036).

        Deliberately changes nothing in the catalogue. Rejection is not a
        statement that the rule is wrong, so there is nothing to unwind — and
        a later reading of better evidence is expected rather than precluded.
        """
        self._require(proposal_id)
        self._proposals.decide(
            proposal_id, "rejected", decided_by, rationale, attribution
        )

    # -- internals ---------------------------------------------------------

    def _require(self, proposal_id: int) -> StoredRuleProposal:
        stored = self._proposals.find(proposal_id)
        if stored is None:
            raise NotRegistered(f"no rule proposal with id {proposal_id}")
        return stored

    def _target_rule(self, stored: StoredRuleProposal) -> tuple[int, bool]:
        """The rule this reading becomes a version of, creating it if new."""
        if stored.revises_rule_id is not None:
            row = self._workspace.execute(
                "SELECT id FROM rule WHERE id = ?", (stored.revises_rule_id,)
            ).fetchone()
            if row is None:
                # The claim named a rule that is not there. Refused rather
                # than silently creating a new rule: the reviewer accepted a
                # revision, and quietly giving them a separate rule instead is
                # the duplicate CON-43 exists to prevent.
                raise NotRegistered(
                    f"rule proposal claims to revise rule "
                    f"{stored.revises_rule_id}, which does not exist."
                )
            return int(row["id"]), False

        cursor = self._workspace.execute(
            "INSERT INTO rule (name, statement, created_at) VALUES (?, ?, ?)",
            (stored.proposal.name, stored.proposal.statement, utc_now()),
        )
        return int(cursor.lastrowid), True

    def _baseline(
        self, rule_id: int, stored: StoredRuleProposal
    ) -> tuple[int, int]:
        """Freeze this reading as the rule's next version, and make it current."""
        previous = self._workspace.execute(
            "SELECT id, version_no FROM rule_version WHERE rule_id = ? "
            "ORDER BY version_no DESC LIMIT 1",
            (rule_id,),
        ).fetchone()
        version_no = 1 if previous is None else int(previous["version_no"]) + 1
        previous_id = None if previous is None else int(previous["id"])
        now = utc_now()

        with self._workspace.transaction() as ws:
            cursor = ws.execute(
                "INSERT INTO rule_version "
                "(rule_id, version_no, name, statement, from_rule_proposal_id, "
                " previous_version_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    rule_id,
                    version_no,
                    stored.proposal.name,
                    stored.proposal.statement,
                    stored.id,
                    previous_id,
                    now,
                ),
            )
            version_id = int(cursor.lastrowid)

            for behaviour in stored.proposal.behaviours:
                ws.execute(
                    "INSERT INTO rule_version_behaviour "
                    "(rule_version_id, description) VALUES (?, ?)",
                    (version_id, behaviour.description),
                )
            for anchor in stored.proposal.anchors:
                ws.execute(
                    "INSERT INTO rule_version_anchor "
                    "(rule_version_id, repository_id, path_glob) "
                    "VALUES (?, (SELECT id FROM repository WHERE alias = ?), ?)",
                    (version_id, anchor.repository_alias, anchor.path_glob),
                )

            # The current state follows the new version. `rule` is mutable for
            # the same reason `document` is: it is the working view, and the
            # durable record is the frozen version beside it.
            ws.execute(
                "UPDATE rule SET name = ?, statement = ? WHERE id = ?",
                (stored.proposal.name, stored.proposal.statement, rule_id),
            )
            ws.execute("DELETE FROM behaviour WHERE rule_id = ?", (rule_id,))
            ws.execute("DELETE FROM anchor WHERE rule_id = ?", (rule_id,))
            for behaviour in stored.proposal.behaviours:
                ws.execute(
                    "INSERT INTO behaviour (rule_id, description, created_at) "
                    "VALUES (?, ?, ?)",
                    (rule_id, behaviour.description, now),
                )
            for anchor in stored.proposal.anchors:
                ws.execute(
                    "INSERT INTO anchor "
                    "(rule_id, repository_id, path_glob, created_at) "
                    "VALUES (?, (SELECT id FROM repository WHERE alias = ?), ?, ?)",
                    (rule_id, anchor.repository_alias, anchor.path_glob, now),
                )

        return version_id, version_no

    # -- reading -----------------------------------------------------------

    def versions(self, rule_id: int) -> tuple[dict, ...]:
        """Every accepted version of a rule, oldest first.

        Returned as plain rows: this is the audit view, and a reviewer reading
        history wants what was recorded rather than a reconstructed object.
        """
        rows = self._workspace.execute(
            "SELECT v.id, v.version_no, v.name, v.statement, v.created_at, "
            "       v.from_rule_proposal_id, d.decided_by, d.attribution, "
            "       d.decided_at "
            "FROM rule_version v "
            "LEFT JOIN rule_proposal_decision d "
            "  ON d.rule_proposal_id = v.from_rule_proposal_id "
            " AND d.decision = 'accepted' "
            "WHERE v.rule_id = ? ORDER BY v.version_no",
            (rule_id,),
        ).fetchall()
        return tuple(dict(row) for row in rows)
