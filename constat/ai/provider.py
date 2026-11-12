"""The provider seam.

D-003 isolated AI behind an interface and made it optional. D-039 changed what
that means: rules are *generated* by an interpretation pass, so with no
provider configured there are no rules — only evidence. The evidence path is
still completely provider-free, and the honest shape of the no-provider result
is a statement that no rules were **identified**, never that none **exist**.

That distinction is the whole reason this module is more than a `Protocol`.
An empty rule section and a missing provider look identical in output unless
something carries the reason, so `Interpretation` always carries a note and
the null provider's note says which situation the reader is in.

Nothing here performs a network call. The provider registry is empty in
CON-41: naming a provider that is not implemented is an error, not a quiet
fallback to nothing (`UnknownProvider`). Generation arrives with CON-42.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..models import RuleProposal
from .parsing import Rejection
from .redaction import ProviderPayload

NULL_PROVIDER_NAME = "none"

NO_PROVIDER_NOTE = (
    "No AI provider is configured, so no rules were identified. This is a "
    "statement about how Constat is configured, not about this code: rules "
    "may well exist here and go unlisted. Rule identification requires a "
    "provider (D-039); the evidence does not."
)


@dataclass(frozen=True)
class Interpretation:
    """What a provider returned, including nothing and why.

    `note` is not optional in practice. A caller rendering proposals without
    it would present an empty list as a finding, and "we found no rules" and
    "we did not look" are different claims (product rule 1).
    """

    provider: str
    proposals: tuple[RuleProposal, ...] = ()
    model: str | None = None
    model_attested: bool = False
    """Whether Constat established the model id itself or was told it.

    True only when Constat issued the request and read the id back off the
    response. A reading submitted from outside carries whatever the caller
    typed, which is provenance worth keeping and not a fact worth presenting
    as one (D-045, D-057)."""
    note: str = ""
    rejections: tuple[Rejection, ...] = ()
    """Proposals the provider returned that were discarded, with reasons. Part
    of the result rather than a log line: a document showing two rules when the
    provider offered eight has misrepresented the pass (product rule 3)."""

    @property
    def identified_rules(self) -> bool:
        return bool(self.proposals)

    @property
    def has_output(self) -> bool:
        """Whether the provider said anything at all, kept or discarded."""
        return bool(self.proposals or self.rejections)

    @property
    def ran(self) -> bool:
        """Whether an interpretation pass actually happened."""
        return self.provider != NULL_PROVIDER_NAME

    def describe(self) -> str:
        """The provider and model, for the document's provenance line."""
        if not self.ran:
            return "no provider"
        return f"{self.provider}" + (f" ({self.model})" if self.model else "")


@runtime_checkable
class Provider(Protocol):
    """An interpretation provider.

    Takes a redacted payload and returns proposals. It receives a
    `ProviderPayload` rather than evidence directly, so no implementation can
    reach identity even by accident — the type does not carry it (see
    `redaction`).
    """

    name: str
    model: str | None

    def interpret(self, payload: ProviderPayload) -> Interpretation:
        """Propose rules from the payload. Must never raise for empty input."""
        ...


class NullProvider:
    """The default. Returns no proposals and says why.

    It does not inspect the payload at all. That is the point: the pipeline
    must work, end to end, with nothing configured and nothing sent anywhere.
    """

    name = NULL_PROVIDER_NAME
    model: str | None = None

    def interpret(self, payload: ProviderPayload) -> Interpretation:
        return Interpretation(provider=self.name, note=NO_PROVIDER_NOTE)
