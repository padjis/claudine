"""Tests for parsing a provider reply into proposals (CON-42, partial).

This is the trust boundary on AI output, and the tests are shaped by what a
model actually does wrong rather than by the happy path.

Three properties carry the weight:

1. **An unparseable reply is an error, never an empty result.** Returning no
   proposals for broken JSON would make the document read "no rules were
   identified" — a provider failure wearing the costume of a finding, which is
   what D-041 refused for a misconfigured provider.
2. **Anchors must be grounded in the evidence supplied.** A model will propose
   a rule anchored to a plausible-sounding path whether or not that path was in
   the payload. An ungrounded anchor is a fabrication, and a governance tool
   that stores it has invented its own evidence.
3. **Rejections are reported, not swallowed.** Eight proposals in, two kept,
   and a document that says nothing has misrepresented the pass.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from constat.ai import Interpretation, parse
from constat.ai.parsing import MAX_NAME, MAX_STATEMENT, ParseResult
from constat.ai.redaction import (
    CommitContext,
    FileChange,
    ProviderPayload,
    RepositoryContext,
)
from constat.errors import MalformedResponse
from constat.models import ProvenanceType, RegisteredRepository
from constat.operations import RepositoryFindings, gather, render
from constat.store import Registry, TicketStore, Workspace
from constat.tickets import TicketMatch, TicketStatus

from helpers import commit_file, git
from test_ai import FakeProvider

SHA = "a" * 40


def payload(
    paths: tuple[str, ...] = ("rules.py",),
    alias: str = "billing",
) -> ProviderPayload:
    """A payload with known paths, built directly.

    Constructed rather than gathered because these tests are about what the
    parser does with a *reply*; the grounding set is the only part of the
    payload that matters, and stating it plainly makes each assertion legible.
    """
    return ProviderPayload(
        reference="622",
        repositories=(
            RepositoryContext(
                alias=alias,
                default_branch="main",
                status="pending",
                commits=(
                    CommitContext(
                        sha=SHA,
                        subject="Raise the limit (#622)",
                        body="",
                        files=tuple(
                            FileChange(path=p, change_type="modified", diff="")
                            for p in paths
                        ),
                    ),
                ),
            ),
        ),
    )


def findings() -> tuple[RepositoryFindings, ...]:
    """One searched repository that contributed nothing.

    `render` returns early when no repository was searched at all, so the
    rendering tests need a real finding — otherwise they assert against the
    "nothing is registered" branch and pass for the wrong reason.
    """
    entry = RegisteredRepository(
        alias="billing",
        source="/tmp/billing",
        source_kind="local",
        identity="b" * 40,
        default_branch="main",
        added_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
    )
    return (
        RepositoryFindings(
            repository=entry,
            status=TicketStatus.NOT_FOUND,
            match=TicketMatch(repository_alias="billing", status=TicketStatus.NOT_FOUND),
        ),
    )


def reply(*rules: dict) -> str:
    return json.dumps({"rules": list(rules)})


def rule(**overrides) -> dict:
    """A well-formed proposal, grounded in `payload()`'s default path."""
    base = {
        "name": "daily-transfer-limit",
        "statement": "A transfer over the daily limit is refused.",
        "behaviours": ["Refuse and explain the limit"],
        "anchors": [{"path_glob": "rules.py", "repository_alias": "billing"}],
    }
    base.update(overrides)
    return base


class TestAReplyThatCannotBeUsed:
    """Each of these must raise, not return an empty result."""

    @pytest.mark.parametrize(
        "text,because",
        [
            ("", "empty"),
            ("   \n  ", "whitespace only"),
            ("I could not find any business rules.", "prose instead of JSON"),
            ("{not json at all", "truncated JSON"),
            ('{"rules": [}', "malformed array"),
            ('["a", "b"]', "a list at the top level, not an object"),
            ('{"proposals": []}', "no 'rules' key"),
            ('{"rules": {"name": "x"}}', "'rules' is not a list"),
            ('"just a string"', "a bare JSON string"),
            ("null", "JSON null"),
        ],
    )
    def test_it_is_refused(self, text, because):
        with pytest.raises(MalformedResponse):
            parse(text, payload())

    def test_the_refusal_explains_itself(self):
        with pytest.raises(MalformedResponse) as exc:
            parse("not json", payload())
        message = str(exc.value)
        assert "not valid JSON" in message
        assert "no rules" in message  # says why it is not reported as a finding

    def test_an_empty_reply_is_distinguished_from_a_broken_one(self):
        """Different causes, so different messages — a provider that returned
        nothing at all is not the same failure as one that returned garbage."""
        with pytest.raises(MalformedResponse) as empty:
            parse("", payload())
        with pytest.raises(MalformedResponse) as broken:
            parse("{{{", payload())
        assert "empty reply" in str(empty.value)
        assert "empty reply" not in str(broken.value)

    def test_a_missing_rules_key_names_the_reason(self):
        with pytest.raises(MalformedResponse) as exc:
            parse('{"findings": []}', payload())
        assert "'rules'" in str(exc.value)


class TestAcceptingAWellFormedReply:
    def test_a_grounded_proposal_is_kept(self):
        result = parse(reply(rule()), payload())
        assert len(result.proposals) == 1
        assert result.rejections == ()

        proposal = result.proposals[0]
        assert proposal.name == "daily-transfer-limit"
        assert proposal.provenance is ProvenanceType.AI_INTERPRETATION

    def test_behaviours_and_anchors_survive(self):
        proposal = parse(reply(rule()), payload()).proposals[0]
        assert [b.description for b in proposal.behaviours] == [
            "Refuse and explain the limit"
        ]
        assert proposal.anchors[0].path_glob == "rules.py"
        assert proposal.anchors[0].repository_alias == "billing"

    def test_a_fenced_reply_is_unwrapped(self):
        """Models wrap JSON in a code fence more often than not.

        Pragmatism, not laxity: the content inside still has to parse.
        """
        fenced = f"```json\n{reply(rule())}\n```"
        assert len(parse(fenced, payload()).proposals) == 1

    def test_an_unlabelled_fence_is_unwrapped(self):
        fenced = f"```\n{reply(rule())}\n```"
        assert len(parse(fenced, payload()).proposals) == 1

    def test_a_fence_containing_prose_is_still_refused(self):
        with pytest.raises(MalformedResponse):
            parse("```\nI found no rules.\n```", payload())

    def test_an_anchor_may_be_a_bare_string(self):
        """A model will write the short form regardless of the schema asked
        for. Accepting it costs nothing; the grounding check still applies."""
        result = parse(reply(rule(anchors=["rules.py"])), payload())
        assert result.proposals[0].anchors[0].repository_alias is None

    def test_an_anchor_glob_is_matched_not_compared(self):
        result = parse(reply(rule(anchors=["*.py"])), payload())
        assert len(result.proposals) == 1

    def test_whitespace_is_trimmed(self):
        result = parse(
            reply(rule(name="  spaced  ", statement="  A statement.  ")), payload()
        )
        proposal = result.proposals[0]
        assert proposal.name == "spaced"
        assert proposal.statement == "A statement."

    def test_an_empty_rules_list_is_not_an_error(self):
        """A provider that genuinely found nothing is a finding, not a fault."""
        result = parse('{"rules": []}', payload())
        assert result.proposals == ()
        assert result.rejections == ()
        assert "finding none" in result.note


class TestUngroundedAnchorsAreRejected:
    """The property that stops a model inventing its own evidence."""

    def test_an_anchor_naming_a_path_nobody_sent_is_rejected(self):
        bad = rule(anchors=[{"path_glob": "src/billing/limits.py"}])
        result = parse(reply(bad), payload())

        assert result.proposals == ()
        assert len(result.rejections) == 1
        assert "grounded" in result.rejections[0].reason

    def test_an_anchor_naming_an_unknown_repository_is_rejected(self):
        bad = rule(anchors=[{"path_glob": "rules.py", "repository_alias": "payments"}])
        result = parse(reply(bad), payload())
        assert result.proposals == ()
        assert result.rejections

    def test_a_proposal_with_no_anchors_at_all_is_rejected(self):
        """An unanchored rule can never be matched to a future change (CON-40),
        so it is inert rather than merely incomplete."""
        result = parse(reply(rule(anchors=[])), payload())
        assert result.proposals == ()
        assert "anchor" in result.rejections[0].reason

    def test_one_ungrounded_anchor_rejects_the_whole_proposal(self):
        """Keeping the grounded half would silently narrow a rule the model
        meant more broadly, which is a different claim."""
        half = rule(anchors=["rules.py", "does/not/exist.py"])
        result = parse(reply(half), payload())
        assert result.proposals == ()

    def test_grounding_spans_every_repository_in_the_payload(self):
        wide = ProviderPayload(
            reference="622",
            repositories=payload().repositories
            + payload(paths=("app.ts",), alias="web").repositories,
        )
        result = parse(
            reply(rule(anchors=[{"path_glob": "app.ts", "repository_alias": "web"}])),
            wide,
        )
        assert len(result.proposals) == 1

    def test_an_anchor_that_is_not_an_object_or_string_is_rejected(self):
        result = parse(reply(rule(anchors=[42])), payload())
        assert result.proposals == ()


class TestMalformedIndividualProposals:
    """One bad rule in eight must not discard the other seven — nor vanish."""

    @pytest.mark.parametrize(
        "overrides,reason",
        [
            ({"name": ""}, "no name"),
            ({"name": "   "}, "no name"),
            ({"name": None}, "no name"),
            ({"statement": ""}, "no statement"),
            ({"statement": None}, "no statement"),
            ({"name": "x" * (MAX_NAME + 1)}, "too long"),
            ({"statement": "y" * (MAX_STATEMENT + 1)}, "too long"),
        ],
    )
    def test_it_is_rejected_with_a_reason(self, overrides, reason):
        result = parse(reply(rule(**overrides)), payload())
        assert result.proposals == ()
        assert len(result.rejections) == 1
        assert reason in result.rejections[0].reason

    def test_a_non_object_entry_is_rejected(self):
        result = parse('{"rules": ["just a string"]}', payload())
        assert result.proposals == ()
        assert result.rejections[0].reason == "not an object"

    def test_a_duplicate_name_in_one_reply_is_rejected_once(self):
        result = parse(reply(rule(), rule()), payload())
        assert len(result.proposals) == 1
        assert len(result.rejections) == 1
        assert "duplicate" in result.rejections[0].reason

    def test_good_proposals_survive_alongside_bad_ones(self):
        result = parse(
            reply(
                rule(),
                rule(name="orphan", anchors=[]),
                rule(name="second", statement="Another rule."),
            ),
            payload(),
        )
        assert [p.name for p in result.proposals] == ["daily-transfer-limit", "second"]
        assert [r.name for r in result.rejections] == ["orphan"]

    def test_a_nameless_rejection_is_identified_by_position(self):
        """A reviewer needs to be able to count them even when the model gave
        nothing to name them by."""
        result = parse(reply(rule(name=None)), payload())
        assert result.rejections[0].name == "#1"

    def test_non_list_behaviours_are_dropped_not_fatal(self):
        """A malformed optional field loses the field, not the rule."""
        result = parse(reply(rule(behaviours="Refuse it")), payload())
        assert len(result.proposals) == 1
        assert result.proposals[0].behaviours == ()

    def test_blank_behaviours_are_discarded(self):
        result = parse(reply(rule(behaviours=["", "  ", "Real one"])), payload())
        assert [b.description for b in result.proposals[0].behaviours] == ["Real one"]


class TestARejectionCarriesNoUnvalidatedContent:
    def test_only_the_name_and_reason_are_kept(self):
        """A rejected proposal is unvalidated model output. Storing its text
        would put unattributable prose into a governance record."""
        bad = rule(
            name="orphan",
            statement="A sweeping claim nobody has checked.",
            anchors=[],
        )
        result = parse(reply(bad), payload())

        rejection = result.rejections[0]
        assert rejection.name == "orphan"
        assert "sweeping claim" not in repr(rejection)
        assert "sweeping claim" not in rejection.describe()


class TestTheNoteTheDocumentShows:
    def test_discards_are_announced(self):
        result = parse(reply(rule(), rule(name="orphan", anchors=[])), payload())
        assert "1 proposal(s) were discarded" in result.note

    def test_nothing_at_all_is_stated_as_the_provider_finding_none(self):
        note = ParseResult().note
        assert "finding none" in note
        assert "not a statement that none exist" in note

    def test_a_clean_pass_says_nothing_extra(self):
        """No rejections, no noise."""
        assert parse(reply(rule()), payload()).note == ""


class TestRejectionsReachTheDocument:
    """Parsing them correctly is useless if the document hides them."""

    def _interpretation(self, result: ParseResult) -> Interpretation:
        return Interpretation(
            provider="fake",
            model="fake-1",
            proposals=result.proposals,
            note=result.note,
            rejections=result.rejections,
        )

    def test_they_are_listed_when_some_proposals_survived(self):
        result = parse(reply(rule(), rule(name="orphan", anchors=[])), payload())
        body = render("622", findings(), self._interpretation(result))

        assert "discarded" in body
        assert "orphan" in body
        assert "grounded in the evidence" in body

    def test_they_are_listed_when_every_proposal_was_rejected(self):
        """The case most likely to be swallowed: nothing kept, so the rules
        section would otherwise read as a plain 'none identified'."""
        result = parse(reply(rule(name="orphan", anchors=[])), payload())
        interpretation = self._interpretation(result)
        assert not interpretation.identified_rules
        assert interpretation.has_output

        body = render("622", findings(), interpretation)
        assert "discarded" in body
        assert "orphan" in body

    def test_a_clean_pass_adds_no_rejection_section(self):
        body = render(
            "622", findings(), self._interpretation(parse(reply(rule()), payload()))
        )
        assert "discarded" not in body


class TestEndToEndThroughGather:
    """The parser is only useful if a provider's reply reaches the document."""

    @pytest.fixture
    def workspace(self, tmp_path: Path):
        with Workspace.create(tmp_path / "ws") as ws:
            yield ws

    def _subject(self, tmp_path: Path) -> Path:
        source = tmp_path / "src"
        source.mkdir()
        git(source, "init", "--initial-branch=main", "--quiet")
        commit_file(source, "rules.py", "LIMIT = 100\n", "Initial")

        clone = tmp_path / "billing"
        git(tmp_path, "clone", "--quiet", str(source), str(clone))
        git(clone, "checkout", "--quiet", "-b", "develop")
        commit_file(clone, "rules.py", "LIMIT = 250\n", "Raise the limit (#622)")
        git(clone, "checkout", "--quiet", "main")
        return clone

    def test_a_reply_parsed_against_the_real_payload_lands_in_the_document(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(str(self._subject(tmp_path)), alias="billing")
        TicketStore(workspace).add("622")

        # First run: capture the payload a provider would actually receive.
        probe = FakeProvider()
        gather(workspace, "622", provider=probe)
        real_payload = probe.seen[0]

        result = parse(reply(rule()), real_payload)
        assert len(result.proposals) == 1, result.rejections

        provider = FakeProvider(result.proposals)
        body = gather(workspace, "622", provider=provider).body
        assert "daily-transfer-limit" in body
        assert "ai_interpretation" in body

    def test_an_anchor_the_evidence_does_not_support_is_refused_on_real_data(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(str(self._subject(tmp_path)), alias="billing")
        TicketStore(workspace).add("622")

        probe = FakeProvider()
        gather(workspace, "622", provider=probe)

        invented = rule(anchors=[{"path_glob": "src/payments/gateway.py"}])
        result = parse(reply(invented), probe.seen[0])
        assert result.proposals == ()
        assert "grounded" in result.rejections[0].reason
