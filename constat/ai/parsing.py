"""Turning a provider's reply into proposals — or refusing it.

This is the trust boundary on AI output, and it exists before any real
provider does, because every property worth enforcing here is enforceable
without spending anything.

Three rules shape it.

**A reply that cannot be parsed is an error, never an empty result.** The
tempting implementation returns no proposals when the JSON is broken, and the
document then reads "no rules were identified" — a parse failure wearing the
costume of a finding. That is the same mistake D-041 refused for a
misconfigured provider, and it is refused again here.

**An anchor must be grounded in the evidence.** A model will cheerfully
propose a rule anchored to `src/billing/limits.py` whether or not that file
was in the payload. An anchor pointing at a path nobody sent is a fabrication,
and a governance tool that stores it has invented its own evidence. Anchors
are checked against the paths actually present, and ungrounded proposals are
dropped with a reason.

**Rejections are reported, not swallowed.** If a model returns eight rules and
six are discarded, a document showing two and saying nothing has misrepresented
what happened. Every rejection carries a reason and reaches the document.

A reply may also claim to **revise** an existing rule by naming its id
(D-050). That claim is checked the same way an anchor is: the rule has to have
been in the payload. A reading cannot have read a rule it was never shown, so
claiming a relationship to one is inventing it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..errors import MalformedResponse
from ..globs import matches_path
from ..models import Anchor, Behaviour, RuleProposal
from .redaction import ProviderPayload

FENCE = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL)
"""Models wrap JSON in a code fence more often than not. Unwrapping it is
pragmatism, not laxity: the content inside still has to parse, and anything
that is not JSON is still refused."""

MAX_NAME = 120
MAX_STATEMENT = 600
"""Bounds on generated text. An unbounded statement would let a model write a
page of prose into a field a reviewer has to read in a list."""


@dataclass(frozen=True)
class Rejection:
    """A proposal that was discarded, and why.

    Carries the proposed name only. The rest of a rejected proposal is not
    kept: it is unvalidated model output, and storing it would put
    unattributable text into a governance record.
    """

    name: str
    reason: str

    def describe(self) -> str:
        return f"`{self.name}` — {self.reason}"


@dataclass(frozen=True)
class ParseResult:
    proposals: tuple[RuleProposal, ...] = ()
    rejections: tuple[Rejection, ...] = ()

    @property
    def note(self) -> str:
        """What the document says about this pass.

        Never silent. Both halves matter: what was proposed, and what was
        thrown away.
        """
        if not self.proposals and not self.rejections:
            return (
                "The provider returned no rules. That is the provider finding "
                "none in this evidence, not a statement that none exist."
            )
        parts = []
        if self.rejections:
            parts.append(
                f"{len(self.rejections)} proposal(s) were discarded as "
                "ungrounded or malformed, listed below."
            )
        return " ".join(parts)


def _known_rules(payload: ProviderPayload) -> set[int]:
    """Rule ids the provider was actually shown.

    A `revises` claim naming a rule that was not in the payload is as
    ungrounded as an anchor naming a path nobody sent: the reading cannot have
    read it, so it is inventing a relationship rather than observing one.
    """
    return {rule.rule_id for rule in payload.catalogue}


def _known(payload: ProviderPayload) -> tuple[set[str], set[str]]:
    """The paths and repository aliases the provider was actually given."""
    aliases = {r.alias for r in payload.repositories}
    paths = {
        changed.path
        for r in payload.repositories
        for c in r.commits
        for changed in c.files
    }
    return paths, aliases


def _unwrap(text: str) -> str:
    match = FENCE.match(text)
    return match.group("body") if match else text


def _load(text: str) -> list[dict]:
    """Parse the reply, or raise. Never returns an empty list for bad input."""
    if not text.strip():
        raise MalformedResponse(
            "the provider returned an empty reply. Treated as an error rather "
            "than as 'no rules were identified', which would present a "
            "provider failure as a finding."
        )

    try:
        document = json.loads(_unwrap(text))
    except json.JSONDecodeError as exc:
        raise MalformedResponse(
            f"the provider's reply is not valid JSON ({exc.msg} at line "
            f"{exc.lineno}). Refused rather than reported as no rules found."
        ) from None

    if not isinstance(document, dict) or "rules" not in document:
        raise MalformedResponse(
            "the provider's reply is JSON but has no top-level 'rules' key, so "
            "it cannot be distinguished from a reply that found nothing."
        )

    rules = document["rules"]
    if not isinstance(rules, list):
        raise MalformedResponse("the 'rules' key is not a list.")
    return rules


def _behaviours(raw: object) -> tuple[Behaviour, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        Behaviour(description=item.strip())
        for item in raw
        if isinstance(item, str) and item.strip()
    )


def _anchors(raw: object, paths: set[str], aliases: set[str]) -> tuple[Anchor, ...]:
    """Grounded anchors only. An ungrounded one leaves the tuple empty, which
    the caller treats as a rejection."""
    if not isinstance(raw, list):
        return ()

    anchors = []
    for item in raw:
        if isinstance(item, str):
            item = {"path_glob": item}
        if not isinstance(item, dict):
            return ()

        glob = item.get("path_glob")
        if not isinstance(glob, str) or not glob.strip():
            return ()
        glob = glob.strip()

        alias = item.get("repository_alias")
        if alias is not None:
            if not isinstance(alias, str) or alias not in aliases:
                return ()

        if not any(matches_path(path, glob) for path in paths):
            return ()

        anchors.append(Anchor(path_glob=glob, repository_alias=alias))
    return tuple(anchors)


def parse(text: str, payload: ProviderPayload) -> ParseResult:
    """Parse a provider reply into grounded proposals.

    Raises `MalformedResponse` if the reply as a whole is unusable. Individual
    proposals that are malformed or ungrounded are rejected with a reason
    rather than failing the run: one bad rule in eight should not discard the
    other seven, but it must not vanish silently either.
    """
    paths, aliases = _known(payload)
    known_rules = _known_rules(payload)
    proposals: list[RuleProposal] = []
    rejections: list[Rejection] = []
    seen: set[str] = set()

    for index, raw in enumerate(_load(text), start=1):
        if not isinstance(raw, dict):
            rejections.append(Rejection(f"#{index}", "not an object"))
            continue

        name = raw.get("name")
        name = name.strip() if isinstance(name, str) else ""
        label = name or f"#{index}"

        statement = raw.get("statement")
        statement = statement.strip() if isinstance(statement, str) else ""

        if not name:
            rejections.append(Rejection(label, "no name"))
            continue
        if len(name) > MAX_NAME:
            rejections.append(Rejection(label[:MAX_NAME], "name is too long"))
            continue
        if not statement:
            rejections.append(Rejection(label, "no statement"))
            continue
        if len(statement) > MAX_STATEMENT:
            rejections.append(Rejection(label, "statement is too long"))
            continue
        if name in seen:
            rejections.append(Rejection(label, "duplicate name in one reply"))
            continue

        revises = raw.get("revises")
        if revises is not None:
            if not isinstance(revises, int) or isinstance(revises, bool):
                rejections.append(Rejection(label, "'revises' is not a rule id"))
                continue
            if revises not in known_rules:
                # Symmetric with an ungrounded anchor: the reading is claiming
                # a relationship to something it was never shown.
                rejections.append(
                    Rejection(
                        label,
                        f"claims to revise rule {revises}, which was not in "
                        "the evidence supplied",
                    )
                )
                continue

        anchors = _anchors(raw.get("anchors"), paths, aliases)
        if not anchors:
            # Deliberately fatal for the proposal. An unanchored rule can
            # never be matched to a future change (CON-40), and an anchor
            # naming a path nobody sent is the model inventing evidence.
            rejections.append(
                Rejection(label, "no anchor grounded in the evidence supplied")
            )
            continue

        seen.add(name)
        proposals.append(
            RuleProposal(
                name=name,
                statement=statement,
                behaviours=_behaviours(raw.get("behaviours")),
                anchors=anchors,
                revises_rule_id=revises,
            )
        )

    return ParseResult(proposals=tuple(proposals), rejections=tuple(rejections))
