"""The Anthropic provider (CON-60, D-057).

The first provider that actually spends money, and the first that makes
`constat ticket add 622` fill the review queue on its own. Everything it does
after the reply arrives is the code the manual path already used: `parse`
checks the JSON, grounds every anchor against the payload, and discards what
it cannot ground. This module's only job is the round trip.

**What it sends.** A `ProviderPayload` and nothing else — the redacted
evidence for one ticket plus the rules already in the catalogue. No filesystem
access, no repository browsing. That is not a simplification: `gather` runs
`guard_release` before `interpret` is ever called, so the payload is the one
place a credential can be caught, and a provider that could read the working
tree would route around it (D-040, D-047).

**The transport is injected.** `interpret` takes a callable that performs the
request and returns the reply text with the model id the API resolved. The SDK
lives behind `_sdk_transport` and is imported inside it, so the dependency
exists only for someone who has configured this provider, and the tests
exercise the real `interpret` without a key, a network or a cost.

**A failed call raises.** Never an `Interpretation` with no proposals: that
reaches the document as "no rules were identified", and a timeout is not a
finding about the code (D-041, D-057).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from ...errors import ProviderFailed
from ..parsing import parse
from ..guidance import for_system_prompt
from ..provider import Interpretation
from ..redaction import ProviderPayload, as_dict

PROVIDER_NAME = "anthropic"

KEY_ENV = "ANTHROPIC_API_KEY"
"""Read from the environment on every call and never written anywhere."""

MODEL_ENV = "CONSTAT_AI_MODEL"
DEFAULT_MODEL = "claude-opus-5"

MAX_TOKENS = 16_000
"""Headroom for adaptive thinking plus the reply. The reply itself is small;
the thinking is not, and a truncated reply would arrive as invalid JSON."""

SYSTEM = for_system_prompt()
"""The provider's system message.

Shared with the MCP prompt through `ai.guidance`, so a rule proposed over MCP
and the same rule proposed here mean the same thing. Two prose blocks
maintained in parallel would drift, and the catalogue would become a record of
which path happened to be configured (CON-66).
"""


Transport = Callable[[str, str], tuple[str, str]]
"""`(model, payload_json) -> (reply_text, resolved_model)`.

The resolved model is returned separately because it is not the model that was
requested. `claude-opus-5` is an alias; what gets recorded is what the response
says answered, so a proposal read a year ago still names the model that read it
(D-057, product rule 5).
"""


def _sdk_transport(api_key: str) -> Transport:
    """The real round trip. The SDK is imported here and nowhere else."""

    def send(model: str, payload_json: str) -> tuple[str, str]:
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise ProviderFailed(
                "the 'anthropic' package is not installed. Constat does not "
                "depend on it; install the optional extra with "
                "`pip install 'constat[ai]'`. The evidence pipeline needs no "
                "provider at all."
            ) from exc

        client = Anthropic(api_key=api_key)
        try:
            # Streamed because the payload can run to tens of kilobytes and
            # adaptive thinking makes the wait long enough to risk a request
            # timeout on a large ticket.
            with client.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": payload_json}],
            ) as stream:
                message = stream.get_final_message()
        except Exception as exc:  # noqa: BLE001 - every failure is one failure
            # Deliberately broad. An API error, a connection error and a
            # timeout differ to a caller who can retry, and not at all to a
            # document: in every case Constat did not get a reading, and the
            # one thing that must not happen is reporting that as "no rules".
            raise ProviderFailed(
                f"the call to {PROVIDER_NAME} did not complete: {exc}. No "
                "rules were recorded for this run, and nothing was written to "
                "the document — refusing rather than reporting an empty "
                "result as a finding."
            ) from exc

        text = "".join(
            block.text for block in message.content if block.type == "text"
        )
        return text, message.model

    return send


class AnthropicProvider:
    """Reads a payload by asking Claude, and reports what the API answered."""

    name = PROVIDER_NAME

    def __init__(self, model: str, transport: Transport) -> None:
        self.model = model
        self._transport = transport

    def interpret(self, payload: ProviderPayload) -> Interpretation:
        """Send the payload, parse the reply, and report both halves.

        Raises `ProviderFailed` if the call did not complete and
        `MalformedResponse` if the reply cannot be parsed. Returns an empty
        interpretation only when the model genuinely returned no rules — which
        is a finding, and is why the two cases must not share a code path.
        """
        text, resolved = self._transport(
            self.model, json.dumps(as_dict(payload), default=str)
        )
        result = parse(text, payload)

        return Interpretation(
            provider=self.name,
            proposals=result.proposals,
            model=resolved,
            model_attested=True,
            rejections=result.rejections,
            note=_note(result.proposals, resolved),
        )


def _note(proposals: tuple, model: str) -> str:
    """The run's own line in the document. Scoped to this run (D-056)."""
    if proposals:
        return f"{len(proposals)} rule(s) proposed by {PROVIDER_NAME} ({model})."
    return (
        f"{PROVIDER_NAME} ({model}) read this ticket's evidence and identified "
        "no business rules. That is a reading of this change, not a statement "
        "that the code has no rules, and it carries no more authority than any "
        "other reading — nothing here is accepted."
    )


def build(env: Mapping[str, str]) -> AnthropicProvider:
    """Factory for the registry. The credential never leaves this call."""
    return AnthropicProvider(
        model=(env.get(MODEL_ENV) or "").strip() or DEFAULT_MODEL,
        transport=_sdk_transport(env.get(KEY_ENV, "")),
    )
