"""Tests for the interpretation layer (CON-41).

Done-when is "a provider can be configured; absent one, Constat reports
evidence and states that no rules were identified".

Three properties carry the weight here, and none of them is "a provider can
be called":

1. **Identity does not cross the boundary.** The payload is built from real
   gathered evidence whose commits carry a known address, and that address
   must appear nowhere in it — including inside commit trailers and diff text,
   which are the two places a field-by-field copy would miss.
2. **A misconfiguration is never reported as a finding.** Naming a provider
   that does not exist must fail loudly. Falling back to the null provider
   would emit "no rules were identified" to someone who configured one.
3. **"None identified" is never written as "none exist".** The wording is the
   deliverable, so it is asserted rather than assumed.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic import ValidationError

from constat.ai import (
    NO_PROVIDER_NOTE,
    Interpretation,
    NullProvider,
    Provider,
    ProviderPayload,
    redact,
    resolve,
    scrub_diff,
    scrub_message,
)
from constat.ai import settings
from constat.errors import ProviderNotConfigured, UnknownProvider
from constat.models import Anchor, Behaviour, ProvenanceType, Rule, RuleProposal
from constat.operations import gather
from constat.store import Registry, TicketStore, Workspace

from helpers import commit_file, git

FIXTURE_EMAIL = "fixture@example.invalid"
"""The address `helpers.IDENTITY` commits under. If this diverges from
helpers.py the leak tests stop testing anything, so it is asserted below."""


class FakeProvider:
    """A provider that returns whatever the test gives it, and records input.

    Exists so the configuration path can be exercised with no network, no
    credential and no cost — which is also how CON-42's provider will be
    tested.
    """

    name = "fake"
    model = "fake-1"

    def __init__(self, proposals=(), note: str = "") -> None:
        self.proposals = tuple(proposals)
        self.note = note
        self.seen: list[ProviderPayload] = []

    def interpret(self, payload: ProviderPayload) -> Interpretation:
        self.seen.append(payload)
        return Interpretation(
            provider=self.name,
            model=self.model,
            proposals=self.proposals,
            note=self.note,
        )


def make_subject(tmp_path: Path, name: str, message: str = "Raise the limit (#622)") -> Path:
    """A clone whose `develop` carries ticket 622's work, not yet in mainline."""
    source = tmp_path / f"{name}-src"
    source.mkdir()
    git(source, "init", "--initial-branch=main", "--quiet")
    commit_file(source, "rules.py", "LIMIT = 100\n", "Initial")

    clone = tmp_path / name
    git(tmp_path, "clone", "--quiet", str(source), str(clone))
    git(clone, "checkout", "--quiet", "-b", "develop")
    commit_file(clone, "rules.py", "LIMIT = 250\n", message)
    git(clone, "checkout", "--quiet", "main")
    return clone


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


@pytest.fixture
def gathered(workspace: Workspace, tmp_path: Path):
    """Real findings for ticket 622 in one contributing repository."""
    Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
    TicketStore(workspace).add("622")
    return gather(workspace, "622").findings


def flatten(payload: ProviderPayload) -> str:
    """Every string in the payload, for leak hunting.

    Searching the whole structure rather than named fields is deliberate: a
    leak that a test only looks for in the places it expects is a leak that
    ships.
    """
    return str(asdict(payload))


class TestTheFixtureItself:
    def test_the_fixture_commits_under_the_address_the_leak_tests_hunt_for(
        self, gathered
    ):
        """Guard the guard.

        Every privacy test below asserts an address is absent. If the fixture
        stopped committing under that address they would all pass while
        testing nothing, so this asserts the address is genuinely in the
        collected evidence before redaction removes it.
        """
        from helpers import IDENTITY

        assert FIXTURE_EMAIL in " ".join(IDENTITY)

        commits = [c for f in gathered for c in f.commits]
        assert commits
        records = [r for c in commits if c.bundle for r in c.bundle.commits]
        assert records
        assert any(r.author_email == FIXTURE_EMAIL for r in records)


class TestRedaction:
    def test_no_author_address_survives_into_the_payload(self, gathered):
        """The D-023 settlement, on the real path."""
        payload = redact("622", gathered)
        assert FIXTURE_EMAIL not in flatten(payload)

    def test_the_payload_has_nowhere_to_put_identity(self, gathered):
        """Structural, not behavioural.

        The strongest guarantee is not that identity is stripped but that the
        type cannot carry it: a future field-copying change cannot reintroduce
        an author without first adding the attribute.
        """
        payload = redact("622", gathered)
        commit = payload.repositories[0].commits[0]
        for forbidden in (
            "author_name",
            "author_email",
            "authored_at",
            "committer_name",
            "committer_email",
            "committed_at",
        ):
            assert not hasattr(commit, forbidden)

    def test_the_commit_sha_is_kept(self, gathered):
        """Identity goes; traceability stays.

        A sha identifies a commit, not a person, and without it a proposal
        could not be checked against the evidence that produced it (product
        rule 2).
        """
        payload = redact("622", gathered)
        original = gathered[0].commits[0].sha
        assert payload.repositories[0].commits[0].sha == original

    def test_what_changed_still_reaches_the_provider(self, gathered):
        """Redaction must not strip the thing rule generation needs."""
        payload = redact("622", gathered)
        files = payload.repositories[0].commits[0].files
        assert [f.path for f in files] == ["rules.py"]
        assert "LIMIT = 250" in files[0].diff

    def test_a_repository_that_contributed_nothing_is_still_present(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Same reason as the document: absence and silence differ."""
        registry = Registry(workspace)
        registry.add(str(make_subject(tmp_path, "billing")), alias="billing")

        quiet_src = tmp_path / "quiet-src"
        quiet_src.mkdir()
        git(quiet_src, "init", "--initial-branch=main", "--quiet")
        commit_file(quiet_src, "other.py", "x = 1\n", "Unrelated")
        git(tmp_path, "clone", "--quiet", str(quiet_src), str(tmp_path / "quiet"))
        registry.add(str(tmp_path / "quiet"), alias="quiet")

        TicketStore(workspace).add("622")
        payload = redact("622", gather(workspace, "622").findings)

        assert [r.alias for r in payload.repositories] == ["billing", "quiet"]
        assert payload.repositories[1].commits == ()
        assert payload.repositories[1].status == "not_found"

    def test_the_default_branch_reaches_the_provider(self, gathered):
        payload = redact("622", gathered)
        assert payload.repositories[0].default_branch == "main"

    def test_an_empty_payload_reports_itself_empty(self):
        payload = redact("622", ())
        assert payload.is_empty
        assert payload.commit_count == 0

    def test_commit_count_spans_repositories(self, gathered):
        payload = redact("622", gathered)
        assert payload.commit_count == 1
        assert not payload.is_empty


class TestScrubbingFreeText:
    """Messages and diffs are where a field-by-field redactor leaks."""

    def test_identity_trailers_are_removed_from_a_message(self):
        body = (
            "Raise the daily limit.\n"
            "\n"
            "Signed-off-by: Someone Real <someone@example.com>\n"
            "Co-Authored-By: Another Person <another@example.com>\n"
        )
        scrubbed = scrub_message(body)
        assert "Raise the daily limit." in scrubbed
        assert "Someone Real" not in scrubbed
        assert "Another Person" not in scrubbed
        assert "example.com" not in scrubbed

    def test_trailers_are_matched_case_insensitively_and_with_indentation(self):
        scrubbed = scrub_message("Fix\n\n  co-authored-by: X <x@example.com>\n")
        assert "x@example.com" not in scrubbed
        assert scrubbed.startswith("Fix")

    def test_a_bare_address_in_prose_is_masked(self):
        """Not every disclosure is a well-formed trailer."""
        scrubbed = scrub_message("Reported by alice@example.com during review")
        assert "alice@example.com" not in scrubbed
        assert "[redacted]" in scrubbed
        assert "during review" in scrubbed

    def test_the_message_text_itself_survives(self):
        scrubbed = scrub_message("Refuse a transfer over the daily limit")
        assert scrubbed == "Refuse a transfer over the daily limit"

    def test_an_address_in_diff_text_is_masked(self):
        """A changed AUTHORS file puts addresses in the evidence itself."""
        diff = "+Alice Example <alice@example.com>\n"
        assert "alice@example.com" not in scrub_diff(diff)

    def test_masking_a_diff_never_drops_a_line(self):
        """A diff is evidence. Removing a line would misstate the change.

        This is why messages and diffs are scrubbed by different functions:
        dropping a trailer line from a message is correct, and dropping a line
        from a diff is a different kind of dishonesty.
        """
        diff = (
            "@@ -1,3 +1,3 @@\n"
            "-Signed-off-by: Old <old@example.com>\n"
            "+Signed-off-by: New <new@example.com>\n"
            " unchanged\n"
        )
        scrubbed = scrub_diff(diff)
        assert scrubbed.count("\n") == diff.count("\n")
        assert "old@example.com" not in scrubbed
        assert "new@example.com" not in scrubbed
        assert scrubbed.startswith("@@ -1,3 +1,3 @@")

    def test_a_trailer_in_a_real_commit_body_does_not_reach_the_payload(
        self, workspace: Workspace, tmp_path: Path
    ):
        """End to end, through gather, with a trailer a real commit would carry."""
        clone = make_subject(
            tmp_path,
            "billing",
            message="Raise the limit (#622)\n\nSigned-off-by: Someone <leak@example.test>\n",
        )
        Registry(workspace).add(str(clone), alias="billing")
        TicketStore(workspace).add("622")

        payload = redact("622", gather(workspace, "622").findings)
        flat = flatten(payload)
        assert "leak@example.test" not in flat
        assert "Signed-off-by" not in flat
        assert "#622" in flat  # the message's substance is untouched


class TestNullProvider:
    def test_it_proposes_nothing(self):
        result = NullProvider().interpret(redact("622", ()))
        assert result.proposals == ()
        assert not result.identified_rules

    def test_it_says_no_rules_were_identified_not_that_none_exist(self):
        """The product rule 1 wording, asserted rather than trusted."""
        note = NullProvider().interpret(redact("622", ())).note
        assert note == NO_PROVIDER_NOTE
        assert "no rules were identified" in note
        assert "may well exist" in note

    def test_it_reports_that_no_pass_ran(self):
        result = NullProvider().interpret(redact("622", ()))
        assert not result.ran
        assert result.describe() == "no provider"

    def test_it_satisfies_the_provider_protocol(self):
        assert isinstance(NullProvider(), Provider)

    def test_a_real_provider_describes_itself_for_provenance(self):
        """A reviewer cannot weigh a proposal without knowing what produced it."""
        result = FakeProvider().interpret(redact("622", ()))
        assert result.ran
        assert result.describe() == "fake (fake-1)"


class TestResolvingAProvider:
    def test_nothing_configured_gives_the_null_provider(self):
        assert isinstance(resolve(env={}), NullProvider)

    def test_the_name_none_gives_the_null_provider(self):
        assert isinstance(resolve(env={"CONSTAT_AI_PROVIDER": "none"}), NullProvider)

    def test_whitespace_is_not_a_provider_name(self):
        assert isinstance(resolve(env={"CONSTAT_AI_PROVIDER": "  "}), NullProvider)

    def test_a_configured_provider_is_returned(self):
        """"A provider can be configured" — the done-when, without a network."""
        fake = FakeProvider()
        resolved = resolve(
            env={"CONSTAT_AI_PROVIDER": "fake"},
            providers={"fake": lambda env: fake},
        )
        assert resolved is fake

    def test_the_factory_receives_the_environment(self):
        """Credentials come from the environment, so the factory needs it."""
        seen: list[object] = []
        env = {"CONSTAT_AI_PROVIDER": "fake", "FAKE_API_KEY": "k"}
        resolve(
            env=env,
            providers={"fake": lambda e: seen.append(e) or FakeProvider()},
        )
        assert seen == [env]

    def test_an_unimplemented_provider_is_refused_not_nulled(self):
        """The safety property. A silent fallback would be a lie by omission."""
        with pytest.raises(UnknownProvider) as exc:
            resolve(env={"CONSTAT_AI_PROVIDER": "openai"})
        message = str(exc.value)
        assert "openai" in message
        assert "no rules were identified" in message

    def test_the_refusal_names_what_is_available(self):
        with pytest.raises(UnknownProvider) as exc:
            resolve(
                env={"CONSTAT_AI_PROVIDER": "nope"},
                providers={"fake": lambda env: FakeProvider()},
            )
        assert "available: fake" in str(exc.value)

    def test_every_registered_provider_declares_its_credential(self):
        """This replaced an assertion that the registry ships empty, which was
        true until CON-60 implemented one. The property worth keeping is not
        the emptiness: it is that a registered name cannot be resolved without
        its credential being checked, which only happens if `CREDENTIAL_ENV`
        knows about it. A provider in one dict and not the other would resolve
        with no key and fail at the network instead."""
        assert settings.PROVIDERS
        for name in settings.PROVIDERS:
            assert name in settings.CREDENTIAL_ENV

    def test_registering_a_provider_imports_no_sdk(self):
        """D-003 as an import-time property, not a promise in a docstring.

        `PROVIDERS` holds factories whose SDK imports sit inside them, so a
        user who installed neither extra can still run the evidence pipeline.
        Moving `import anthropic` to module scope in the provider would pass
        every other test in this file and break that."""
        import subprocess
        import sys

        probe = (
            "import sys, constat.ai, constat.cli;"
            " from constat.ai.settings import resolve;"
            " resolve({'CONSTAT_AI_PROVIDER': 'anthropic',"
            "          'ANTHROPIC_API_KEY': 'not-a-real-key'});"
            " assert 'anthropic' not in sys.modules, sorted(sys.modules)"
        )
        # A subprocess because this test module has already imported half of
        # Constat; `sys.modules` here says nothing about a cold start.
        done = subprocess.run([sys.executable, "-c", probe], capture_output=True)
        assert done.returncode == 0, done.stderr.decode()

    def test_a_missing_credential_is_refused(self, monkeypatch):
        monkeypatch.setitem(settings.CREDENTIAL_ENV, "fake", "FAKE_API_KEY")
        with pytest.raises(ProviderNotConfigured) as exc:
            resolve(
                env={"CONSTAT_AI_PROVIDER": "fake"},
                providers={"fake": lambda env: FakeProvider()},
            )
        assert "FAKE_API_KEY" in str(exc.value)

    def test_a_blank_credential_counts_as_missing(self, monkeypatch):
        monkeypatch.setitem(settings.CREDENTIAL_ENV, "fake", "FAKE_API_KEY")
        with pytest.raises(ProviderNotConfigured):
            resolve(
                env={"CONSTAT_AI_PROVIDER": "fake", "FAKE_API_KEY": "   "},
                providers={"fake": lambda env: FakeProvider()},
            )

    def test_a_present_credential_resolves(self, monkeypatch):
        monkeypatch.setitem(settings.CREDENTIAL_ENV, "fake", "FAKE_API_KEY")
        resolved = resolve(
            env={"CONSTAT_AI_PROVIDER": "fake", "FAKE_API_KEY": "secret"},
            providers={"fake": lambda env: FakeProvider()},
        )
        assert isinstance(resolved, FakeProvider)


class TestTheDocumentWithNoProvider:
    def test_the_rules_section_always_appears(self, workspace: Workspace, tmp_path: Path):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        body = gather(workspace, "622").body
        assert "## Business rules" in body

    def test_it_states_that_no_rules_were_identified(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        body = gather(workspace, "622").body
        assert "no rules were identified" in body
        assert "may well exist" in body

    def test_the_evidence_is_still_complete(self, workspace: Workspace, tmp_path: Path):
        """D-003's guarantee survives D-039: no provider, full evidence."""
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        result = gather(workspace, "622")
        assert result.repositories_contributing == 1
        assert "rules.py" in result.body
        assert not result.interpretation.ran

    def test_nothing_is_claimed_to_be_interpreted(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        body = gather(workspace, "622").body
        assert "Observed facts only" in body


class TestTheDocumentWithAProvider:
    @pytest.fixture
    def proposal(self):
        return RuleProposal(
            name="daily-transfer-limit",
            statement="A transfer over the daily limit is refused.",
            behaviours=(Behaviour(description="Refuse and explain the limit"),),
            anchors=(Anchor(path_glob="rules.py", repository_alias="billing"),),
        )

    def _gathered(self, workspace, tmp_path, provider):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")
        return gather(workspace, "622", provider=provider)

    def test_a_proposal_appears_in_the_document(
        self, workspace: Workspace, tmp_path: Path, proposal
    ):
        result = self._gathered(workspace, tmp_path, FakeProvider([proposal]))
        assert "daily-transfer-limit" in result.body
        assert "A transfer over the daily limit is refused." in result.body

    def test_a_proposal_is_labelled_as_interpretation(
        self, workspace: Workspace, tmp_path: Path, proposal
    ):
        """Product rule 3: evidence and interpretation stay distinguishable."""
        body = self._gathered(workspace, tmp_path, FakeProvider([proposal])).body
        assert "ai_interpretation" in body
        assert "Observed facts only" not in body
        assert "observed fact" in body

    def test_a_proposal_carries_no_authority(
        self, workspace: Workspace, tmp_path: Path, proposal
    ):
        """Product rule 4, and the no-automatic-approvals prohibition."""
        body = self._gathered(workspace, tmp_path, FakeProvider([proposal])).body
        assert "no authority until a human" in body
        assert "not a finding" in body

    def test_the_provider_is_named_for_provenance(
        self, workspace: Workspace, tmp_path: Path, proposal
    ):
        body = self._gathered(workspace, tmp_path, FakeProvider([proposal])).body
        assert "fake (fake-1)" in body

    def test_behaviours_and_anchors_are_rendered(
        self, workspace: Workspace, tmp_path: Path, proposal
    ):
        body = self._gathered(workspace, tmp_path, FakeProvider([proposal])).body
        assert "Refuse and explain the limit" in body
        assert "billing:rules.py" in body

    def test_a_proposal_with_no_anchors_says_it_can_never_be_matched(
        self, workspace: Workspace, tmp_path: Path
    ):
        """CON-40's lesson: an unanchored rule is invisible to every future change."""
        bare = RuleProposal(name="orphan", statement="Something is true.")
        body = self._gathered(workspace, tmp_path, FakeProvider([bare])).body
        assert "can never be matched" in body

    def test_a_provider_that_found_nothing_is_distinguished_from_no_provider(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Two different empty results, and the document must not conflate them."""
        provider = FakeProvider(note="No rules were identified in this evidence.")
        result = self._gathered(workspace, tmp_path, provider)
        assert result.interpretation.ran
        assert "No rules were identified in this evidence." in result.body
        assert NO_PROVIDER_NOTE not in result.body

    def test_the_provider_receives_a_redacted_payload(
        self, workspace: Workspace, tmp_path: Path
    ):
        """What a provider is handed is the payload, never the evidence."""
        provider = FakeProvider()
        self._gathered(workspace, tmp_path, provider)

        assert len(provider.seen) == 1
        payload = provider.seen[0]
        assert isinstance(payload, ProviderPayload)
        assert payload.reference == "622"
        assert FIXTURE_EMAIL not in flatten(payload)

    def test_the_payload_is_built_even_with_no_provider(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Redaction runs on the default path too.

        A privacy boundary only exercised once a real provider exists is a
        boundary first tested against a live API.
        """
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        payload = redact("622", gather(workspace, "622").findings)
        assert payload.commit_count == 1


class TestFailingBeforeTheExpensivePart:
    def test_a_misconfigured_provider_fails_before_any_repository_is_read(
        self, workspace: Workspace, tmp_path: Path, monkeypatch
    ):
        """Resolving the provider last would read every repository and collect
        all the evidence before refusing.

        Asserting on the document alone would not catch that — it is written
        at the end either way — so this watches the collector itself.
        """
        import constat.operations as operations

        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")

        calls: list[str] = []
        real = operations._collect_repository
        monkeypatch.setattr(
            operations,
            "_collect_repository",
            lambda entry, ref, limits: calls.append(entry.alias) or real(
                entry, ref, limits
            ),
        )
        monkeypatch.setenv("CONSTAT_AI_PROVIDER", "openai")

        with pytest.raises(UnknownProvider):
            gather(workspace, "622")

        assert calls == []

    def test_the_document_is_left_untouched_by_a_refusal(
        self, workspace: Workspace, tmp_path: Path, monkeypatch
    ):
        Registry(workspace).add(str(make_subject(tmp_path, "billing")), alias="billing")
        TicketStore(workspace).add("622")
        monkeypatch.setenv("CONSTAT_AI_PROVIDER", "openai")

        with pytest.raises(UnknownProvider):
            gather(workspace, "622")

        assert TicketStore(workspace).document("622").is_empty


class TestTheProposalType:
    def test_a_proposal_is_not_a_rule(self):
        """Distinct types, so a proposal cannot be stored by mistake."""
        assert not issubclass(RuleProposal, Rule)
        assert "created_at" not in RuleProposal.model_fields

    def test_provenance_is_pinned_to_interpretation(self):
        proposal = RuleProposal(name="x", statement="y")
        assert proposal.provenance is ProvenanceType.AI_INTERPRETATION

    def test_provenance_cannot_be_relabelled(self):
        """Machine inference must not be dressed up as a supplied requirement."""
        with pytest.raises(ValidationError):
            RuleProposal(
                name="x",
                statement="y",
                provenance=ProvenanceType.REQUIREMENT_REF,
            )

    def test_a_proposal_is_immutable(self):
        proposal = RuleProposal(name="x", statement="y")
        with pytest.raises(ValidationError):
            proposal.statement = "z"


class TestARuleGeneratingCommandRefusesWithoutAProvider:
    """D-059. The one misconfiguration that used to succeed.

    D-041 made a *misconfigured* provider fail loudly, and it does: an
    unimplemented name and a missing credential both exit 5. Nothing
    configured at all still wrote a document saying "no rules were
    identified" — accurate, and useless to someone who ran the command to
    get rules.

    The refusal is at the command boundary on purpose. `operations.gather`
    still runs with the null provider, because the evidence path must not
    need a key and because the MCP server depends on it.
    """

    @pytest.fixture
    def registered(self, tmp_path: Path):
        from constat.cli import main

        home = tmp_path / "ws"
        main(["--workspace", str(home), "init"])
        main([
            "--workspace", str(home), "repo", "add",
            str(make_subject(tmp_path, "billing")), "--name", "billing",
        ])
        return home

    def test_ticket_add_refuses(self, registered, monkeypatch, capsys):
        from constat.cli import EXIT_PROVIDER, main

        monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
        code = main(["--workspace", str(registered), "ticket", "add", "622"])

        assert code == EXIT_PROVIDER
        assert "CONSTAT_AI_PROVIDER is not set" in capsys.readouterr().err

    def test_the_refusal_leaves_no_ticket_behind(self, registered, monkeypatch):
        """Otherwise `ticket add` refuses to open it again, and the user is
        stuck with an empty document they cannot regenerate."""
        from constat.cli import main
        from constat.store import TicketStore, Workspace

        monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
        main(["--workspace", str(registered), "ticket", "add", "622"])

        with Workspace.open(str(registered)) as ws:
            assert TicketStore(ws).list() == ()

    def test_document_refuses(self, registered, monkeypatch, capsys):
        from constat.cli import EXIT_PROVIDER, main

        monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
        main(["--workspace", str(registered), "ticket", "add", "622",
              "--no-provider"])
        code = main(["--workspace", str(registered), "document", "622"])

        assert code == EXIT_PROVIDER

    def test_the_refusal_names_every_way_forward(
        self, registered, monkeypatch, capsys
    ):
        """An objection that does not say what to do instead is a dead end,
        and there are three different right answers here."""
        from constat.cli import main

        monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
        main(["--workspace", str(registered), "ticket", "add", "622"])
        err = capsys.readouterr().err

        assert "CONSTAT_AI_PROVIDER=anthropic" in err   # let Constat read it
        assert "rule submit" in err                     # read it yourself
        assert "--no-provider" in err                   # evidence only

    def test_no_provider_gathers_the_evidence(self, registered, monkeypatch):
        from constat.cli import EXIT_OK, main

        monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
        code = main(["--workspace", str(registered), "ticket", "add", "622",
                     "--no-provider"])
        assert code == EXIT_OK

    def test_a_configured_provider_is_not_refused(self, registered, monkeypatch):
        """The gate asks whether anything *can* read, not whether a flag was
        passed."""
        from constat.cli import EXIT_OK, main

        monkeypatch.setenv("CONSTAT_AI_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
        # The provider resolves, so the gate lets it through. The call itself
        # then fails at the transport, which is a different error entirely —
        # and proves the gate is not what stopped it.
        code = main(["--workspace", str(registered), "ticket", "add", "622"])
        assert code != EXIT_OK  # the network, not the gate
        assert code == 5

    def test_a_misconfigured_provider_still_fails_differently(
        self, registered, monkeypatch, capsys
    ):
        """D-041's case must keep its own message rather than being absorbed
        into the new one."""
        from constat.cli import main

        monkeypatch.setenv("CONSTAT_AI_PROVIDER", "openai")
        main(["--workspace", str(registered), "ticket", "add", "622"])
        err = capsys.readouterr().err

        assert "does not implement" in err
        assert "CONSTAT_AI_PROVIDER is not set" not in err

    def test_gather_itself_does_not_refuse(self, registered, monkeypatch):
        """The library keeps the guarantee. Moving the refusal into `gather`
        would make Constat unusable without a key and break the MCP server,
        where having no provider is correct rather than a misconfiguration
        (D-045)."""
        from constat.cli import main
        from constat.operations import gather
        from constat.store import Workspace

        monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
        main(["--workspace", str(registered), "ticket", "add", "622",
              "--no-provider"])

        with Workspace.open(str(registered)) as ws:
            result = gather(ws, "622")  # no provider, no flag, no refusal

        assert result.reference == "622"
        assert result.interpretation.provider == "none"
