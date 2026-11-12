"""Tests for the first real provider (CON-60, D-057).

**No network, no key, no cost.** The transport is injected, so `interpret` —
the real method, with the real `parse` behind it — runs against a function that
returns a canned reply. The real `anthropic` package is never imported; where
the SDK's own shape matters, `TestTheSdkTransport` substitutes a fake module.
A test that reached the API would bill on every run, and the suite is where
that would be hardest to notice.

Five properties:

1. **A reply becomes grounded rule proposals**, through the same parser the
   manual path uses — this provider adds a round trip and nothing else.
2. **A failed call raises.** Never an empty `Interpretation`, which would
   reach the document as "no rules were identified" (D-041).
3. **The recorded model is the one the response returned**, not the one that
   was requested, and it is marked attested.
4. **An attested model id loses the "self-reported" caveat, and only then.**
5. **The SDK call shape is asserted**, including that thinking blocks are
   skipped when reading the reply — the part an SDK upgrade would break
   quietly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from constat.ai.providers import anthropic as provider_module
from constat.ai.providers.anthropic import (
    DEFAULT_MODEL,
    MODEL_ENV,
    AnthropicProvider,
    build,
)
from constat.ai.redaction import redact
from constat.errors import MalformedResponse, ProviderFailed
from constat.operations import collect, gather
from constat.store import Registry, Review, RuleProposals, TicketStore, Workspace

from test_acceptance import a_reading, record
from test_runs import distinct_subject


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


def subject(workspace, tmp_path, alias: str = "billing"):
    Registry(workspace).add(
        str(distinct_subject(tmp_path, alias, "LIMIT = 250\n")), alias=alias
    )
    TicketStore(workspace).add("622")


A_REPLY = json.dumps(
    {
        "rules": [
            {
                "name": "daily-limit",
                "statement": "A transfer above the daily limit is refused.",
                "behaviours": ["Refuse the transfer"],
                "anchors": [{"path_glob": "rules.py", "repository_alias": "billing"}],
            }
        ]
    }
)


def transport(reply: str = A_REPLY, resolved: str = "claude-opus-5-20260114"):
    """A transport that records what it was asked and returns a canned reply."""
    seen: dict[str, str] = {}

    def send(model: str, payload_json: str) -> tuple[str, str]:
        seen["model"] = model
        seen["payload"] = payload_json
        return reply, resolved

    send.seen = seen  # type: ignore[attr-defined]
    return send


def payload_for(workspace, tmp_path):
    subject(workspace, tmp_path)
    return redact("622", collect(workspace, "622"))


class TestTheRoundTrip:
    def test_a_reply_becomes_proposals(self, workspace: Workspace, tmp_path: Path):
        payload = payload_for(workspace, tmp_path)
        result = AnthropicProvider("claude-opus-5", transport()).interpret(payload)

        assert [p.name for p in result.proposals] == ["daily-limit"]
        assert result.provider == "anthropic"

    def test_the_payload_is_what_crosses(self, workspace: Workspace, tmp_path: Path):
        """And nothing else. The provider has no access to the repository: what
        it sends is the redacted payload `gather` already scanned (D-040,
        D-047)."""
        payload = payload_for(workspace, tmp_path)
        send = transport()
        AnthropicProvider("claude-opus-5", send).interpret(payload)

        sent = json.loads(send.seen["payload"])
        assert sent["reference"] == "622"
        assert "rules.py" in send.seen["payload"]

    def test_identity_does_not_cross(self, workspace: Workspace, tmp_path: Path):
        """D-040 through the real provider rather than only the redactor.

        `distinct_subject` commits as a named author; none of it may appear in
        what the transport is handed."""
        payload = payload_for(workspace, tmp_path)
        send = transport()
        AnthropicProvider("claude-opus-5", send).interpret(payload)

        body = send.seen["payload"]
        # The identity `tests/helpers.py` commits with. Named concretely rather
        # than scanned for "@": diff hunk headers are full of `@@`, and an
        # assertion loose enough to pass that would not have failed on a real
        # leak either.
        assert "Test Fixture" not in body
        assert "fixture@example.invalid" not in body
        assert "author" not in body.lower()
        assert "committer" not in body.lower()
        # And the evidence did reach it, so the absence above means redaction
        # rather than an empty payload.
        assert "LIMIT = 250" in body

    def test_ungrounded_anchors_are_still_discarded(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The provider is not a way around the grounding check: it hands the
        reply to the same `parse`."""
        payload = payload_for(workspace, tmp_path)
        reply = json.dumps(
            {
                "rules": [
                    {
                        "name": "invented",
                        "statement": "A rule about a file nobody sent.",
                        "behaviours": ["x"],
                        "anchors": [
                            {
                                "path_glob": "nowhere/at/all.py",
                                "repository_alias": "billing",
                            }
                        ],
                    }
                ]
            }
        )
        result = AnthropicProvider("m", transport(reply)).interpret(payload)

        assert result.proposals == ()
        assert [r.name for r in result.rejections] == ["invented"]

    def test_an_unparseable_reply_raises(self, workspace: Workspace, tmp_path: Path):
        payload = payload_for(workspace, tmp_path)
        with pytest.raises(MalformedResponse):
            AnthropicProvider("m", transport("not json at all")).interpret(payload)


class TestAFailedCallIsNotAFinding:
    def test_a_transport_failure_raises(self, workspace: Workspace, tmp_path: Path):
        """The property D-041 exists for. An `Interpretation` with no proposals
        would render as "no rules were identified" — a network statement
        wearing the costume of a finding."""
        payload = payload_for(workspace, tmp_path)

        def broken(model: str, payload_json: str):
            raise ProviderFailed("connection refused")

        with pytest.raises(ProviderFailed):
            AnthropicProvider("m", broken).interpret(payload)

    def test_the_document_is_untouched_by_a_failed_run(
        self, workspace: Workspace, tmp_path: Path
    ):
        """`gather` must not leave a half-written document behind: a body
        recording the evidence as if the run succeeded is worse than none."""
        subject(workspace, tmp_path)
        before = gather(workspace, "622").body  # null provider, writes a body

        class Broken:
            name = "anthropic"
            model = "m"

            def interpret(self, payload):
                raise ProviderFailed("rate limited")

        with pytest.raises(ProviderFailed):
            gather(workspace, "622", provider=Broken())

        assert gather(workspace, "622").body == before
        assert RuleProposals(workspace).undecided("622") == ()

    def test_no_rules_found_is_not_an_error(self, workspace: Workspace, tmp_path: Path):
        """The other side of the same line: a model that read the evidence and
        identified nothing has made a finding, and it must survive."""
        payload = payload_for(workspace, tmp_path)
        result = AnthropicProvider("m", transport('{"rules": []}')).interpret(payload)

        assert result.proposals == ()
        assert result.model_attested is True
        # The note has to say a reading happened and found nothing, which is
        # the opposite of NO_PROVIDER_NOTE's "nobody looked".
        assert "identified no business rules" in result.note
        assert "not a statement that the code has no rules" in result.note
        assert "No AI provider is configured" not in result.note


class TestTheModelIdIsResolvedNotRequested:
    def test_the_response_model_is_what_is_recorded(
        self, workspace: Workspace, tmp_path: Path
    ):
        """`claude-opus-5` is an alias. A proposal recorded today must still
        name the model that read the evidence in a year (product rule 5)."""
        payload = payload_for(workspace, tmp_path)
        result = AnthropicProvider(
            "claude-opus-5", transport(resolved="claude-opus-5-20260114")
        ).interpret(payload)

        assert result.model == "claude-opus-5-20260114"
        assert result.model != "claude-opus-5"

    def test_the_requested_model_is_what_is_sent(
        self, workspace: Workspace, tmp_path: Path
    ):
        payload = payload_for(workspace, tmp_path)
        send = transport()
        AnthropicProvider("claude-haiku-4-5", send).interpret(payload)

        assert send.seen["model"] == "claude-haiku-4-5"

    def test_the_provider_path_is_attested(self, workspace: Workspace, tmp_path: Path):
        payload = payload_for(workspace, tmp_path)
        result = AnthropicProvider("m", transport()).interpret(payload)

        assert result.model_attested is True

    def test_the_model_comes_from_the_environment(self):
        assert build({}).model == DEFAULT_MODEL
        assert build({MODEL_ENV: "claude-haiku-4-5"}).model == "claude-haiku-4-5"
        assert build({MODEL_ENV: "   "}).model == DEFAULT_MODEL

    def test_the_credential_is_not_held_on_the_provider(self):
        """It is closed over by the transport and never stored as state, so a
        provider that somehow reached a log or a repr carries no key."""
        instance = build({"ANTHROPIC_API_KEY": "sk-secret-value"})

        assert "sk-secret-value" not in repr(instance)
        assert "sk-secret-value" not in str(vars(instance))


class TestAttestationReachesTheReader:
    def test_an_attested_reading_drops_the_caveat(
        self, workspace: Workspace, tmp_path: Path
    ):
        subject(workspace, tmp_path)
        gather(
            workspace, "622", provider=AnthropicProvider("claude-opus-5", transport())
        )
        item = RuleProposals(workspace).undecided("622")[0]

        assert item.model_attested is True
        assert item.attribution == "anthropic (claude-opus-5-20260114)"
        assert "self-reported" not in item.attribution

    def test_a_submitted_reading_keeps_it(self, workspace: Workspace, tmp_path: Path):
        subject(workspace, tmp_path)
        proposal_id = record(workspace, a_reading())
        item = RuleProposals(workspace).find(proposal_id)

        assert item.model_attested is False
        assert "self-reported" in item.attribution

    def test_the_document_shows_the_difference(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Both readings in one queue. A reviewer weighing them has to be able
        to tell which one Constat can vouch for."""
        subject(workspace, tmp_path)
        record(workspace, a_reading(name="submitted-rule"))
        body = gather(
            workspace, "622", provider=AnthropicProvider("claude-opus-5", transport())
        ).body

        assert "Read by anthropic (claude-opus-5-20260114).\n" in body
        assert "self-reported" in body

    def test_the_default_is_the_weaker_claim(self, workspace: Workspace, tmp_path: Path):
        """A caller that forgets the argument understates rather than
        overstates. The reverse default would silently promote every reading
        submitted from outside."""
        import inspect

        signature = inspect.signature(RuleProposals.record)
        assert signature.parameters["model_attested"].default is False

    def test_mcp_reports_attestation_rather_than_asserting_it(
        self, workspace: Workspace, tmp_path: Path
    ):
        """`model_is_self_reported` was hardcoded True. True by luck is not the
        same as true by construction, and it is now wrong for one path."""
        source = Path(provider_module.__file__).parent.parent.parent / "mcp.py"
        assert '"model_is_self_reported": True' not in source.read_text()


class TestTheSdkTransport:
    """The one part of this module shaped by the SDK, and so the one part the
    injected transport does not cover.

    A mutation check made the gap explicit: breaking the error handling inside
    `_sdk_transport` failed no test at all, because every other test here
    supplies its own transport. A fake `anthropic` module stands in — it
    asserts the call shape Constat relies on, which is the thing that would
    break silently on an SDK upgrade.
    """

    def fake_sdk(self, monkeypatch, *, blocks=None, model="resolved-id", raises=None):
        import sys
        import types

        calls: dict[str, object] = {}

        class FakeMessage:
            content = blocks or []

            def __init__(self, model):
                self.model = model

        class FakeStream:
            def __init__(self, model):
                self._model = model

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get_final_message(self):
                return FakeMessage(self._model)

        class FakeMessages:
            def stream(self, **kwargs):
                calls.update(kwargs)
                if raises is not None:
                    raise raises
                return FakeStream(model)

        class FakeAnthropic:
            def __init__(self, api_key):
                calls["api_key"] = api_key
                self.messages = FakeMessages()

        module = types.ModuleType("anthropic")
        module.Anthropic = FakeAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", module)
        return calls

    def block(self, kind: str, text: str = ""):
        import types

        return types.SimpleNamespace(type=kind, text=text)

    def test_the_reply_text_skips_thinking_blocks(self, monkeypatch):
        """Adaptive thinking puts thinking blocks ahead of the text, and
        `json.loads` on the whole response would fail on every call."""
        self.fake_sdk(
            monkeypatch,
            blocks=[
                self.block("thinking", "the diff raises a limit, so..."),
                self.block("text", '{"rules": []}'),
            ],
        )
        text, _ = provider_module._sdk_transport("key")("m", "{}")

        assert text == '{"rules": []}'

    def test_the_resolved_model_comes_off_the_response(self, monkeypatch):
        self.fake_sdk(monkeypatch, blocks=[self.block("text", "{}")], model="opus-5-dated")
        _, resolved = provider_module._sdk_transport("key")("claude-opus-5", "{}")

        assert resolved == "opus-5-dated"

    def test_the_request_carries_the_system_prompt_and_adaptive_thinking(
        self, monkeypatch
    ):
        calls = self.fake_sdk(monkeypatch, blocks=[self.block("text", "{}")])
        provider_module._sdk_transport("sk-key")("claude-opus-5", '{"reference": "622"}')

        assert calls["model"] == "claude-opus-5"
        assert calls["thinking"] == {"type": "adaptive"}
        assert calls["api_key"] == "sk-key"
        assert "business rules" in calls["system"]
        # The payload is the whole user turn: nothing else is sent.
        assert calls["messages"] == [
            {"role": "user", "content": '{"reference": "622"}'}
        ]

    def test_an_sdk_exception_becomes_ProviderFailed(self, monkeypatch):
        """Whatever the SDK raises, the caller sees one error type — and sees
        it raised, not returned as an empty reply (D-041)."""
        self.fake_sdk(monkeypatch, raises=RuntimeError("429 rate limited"))

        with pytest.raises(ProviderFailed) as exc:
            provider_module._sdk_transport("key")("m", "{}")

        assert "429 rate limited" in str(exc.value)
        assert "No rules were recorded for this run" in str(exc.value)

    def test_a_missing_sdk_says_which_extra_to_install(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def no_anthropic(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_anthropic)

        with pytest.raises(ProviderFailed) as exc:
            provider_module._sdk_transport("key")("m", "{}")

        assert "constat[ai]" in str(exc.value)
        assert "needs no provider at all" in str(exc.value)
