"""Tests for rendering the document from stored state (CON-56).

The bug this closes was a lie rather than a gap. `constat document 622 --show`
printed *"no rules were identified"* while the catalogue held a rule with three
versions and that ticket had rule proposals waiting — because the body rendered
from the current run's `Interpretation` instead of from the workspace. A
statement about configuration, presented as a statement about the code, which
is product rule 1's failure mode exactly.

Three properties:

1. **Stored state reaches the document.** Impacted rules, unclaimed paths and
   the review queue all come from the workspace, so a run with no provider
   still shows them.
2. **The business half and the evidence half stay separate** (product rule 8),
   and the run's own note is scoped to *this run*.
3. **The document works as a pull-request body**, including when it is too long
   — GitHub truncates silently, and D-023's rule is that truncation is always
   stated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.operations import (
    EVIDENCE_HEADING,
    PR_BODY_LIMIT,
    bound_for_pr,
    catalogue_view,
    collect,
    gather,
)
from constat.store import Catalogue, Registry, Review, RuleProposals, TicketStore, Workspace

from test_acceptance import a_reading, record
from test_ai import FakeProvider
from test_runs import distinct_subject


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


def register(workspace, tmp_path, alias: str = "billing"):
    Registry(workspace).add(
        str(distinct_subject(tmp_path, alias, "LIMIT = 250\n")), alias=alias
    )
    TicketStore(workspace).add("622")


def accepted_rule(workspace, tmp_path, glob: str = "rules.py") -> int:
    register(workspace, tmp_path)
    return Review(workspace).accept(
        record(workspace, a_reading(glob=glob)), decided_by="emmanuel"
    ).rule_id


class TestTheCatalogueReachesTheDocument:
    def test_an_impacted_rule_is_named(self, workspace: Workspace, tmp_path: Path):
        accepted_rule(workspace, tmp_path)
        body = gather(workspace, "622").body

        assert "daily-limit" in body
        assert "anchors in what this ticket changed" in body

    def test_it_reports_code_touched_not_meaning_changed(
        self, workspace: Workspace, tmp_path: Path
    ):
        """D-035: anchors say where a rule lives, never what it now does."""
        accepted_rule(workspace, tmp_path)
        body = gather(workspace, "622").body

        assert "whether their behaviour changed is for a reviewer to say" in body

    def test_a_catalogue_with_no_match_says_so(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Distinct from an empty catalogue: the rules exist, none applies."""
        accepted_rule(workspace, tmp_path, glob="elsewhere.py")
        body = gather(workspace, "622").body

        assert "None of the 1 rule(s) in the catalogue" in body

    def test_unclaimed_paths_stay_prominent(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The catalogue's failure mode has to be visible (D-038, D-039)."""
        register(workspace, tmp_path)
        body = gather(workspace, "622").body

        assert "claimed by no rule" in body
        assert "rules.py" in body

    def test_the_review_queue_appears(self, workspace: Workspace, tmp_path: Path):
        register(workspace, tmp_path)
        gather(workspace, "622", provider=FakeProvider([a_reading()]))

        body = gather(workspace, "622").body  # null provider on the second run
        assert "await a human decision" in body
        assert "daily-limit" in body

    def test_the_queue_states_it_carries_no_authority(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        body = gather(workspace, "622", provider=FakeProvider([a_reading()])).body
        assert "carries any authority until accepted" in body

    def test_the_queue_marks_the_reader_as_self_reported(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        body = gather(workspace, "622", provider=FakeProvider([a_reading()])).body
        assert "self-reported" in body

    def test_an_accepted_proposal_leaves_the_queue(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        result = gather(workspace, "622", provider=FakeProvider([a_reading()]))
        proposal_id = RuleProposals(workspace).undecided("622")[0].id
        Review(workspace).accept(proposal_id, decided_by="emmanuel")

        body = gather(workspace, "622").body
        assert "await a human decision" not in body
        assert "daily-limit" in body  # now an impacted rule instead

    def test_an_empty_workspace_claims_nothing(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        body = gather(workspace, "622").body

        assert "rule(s) in the catalogue have anchors" not in body
        assert "await a human decision" not in body


class TestTheRunsNoteIsScoped:
    def test_the_no_rules_note_is_labelled_as_this_run(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The lie this ticket closes.

        Unscoped, the note read as a statement about the ticket while the
        catalogue beside it held rules.
        """
        accepted_rule(workspace, tmp_path)
        body = gather(workspace, "622").body

        assert "**This run:** No AI provider is configured" in body
        # and the catalogue is right there contradicting a bare reading of it
        assert "daily-limit" in body

    def test_a_productive_run_is_also_scoped(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        body = gather(workspace, "622", provider=FakeProvider([a_reading()])).body
        assert "**This run:** 1 rule(s) proposed by" in body

    def test_the_note_no_longer_claims_the_evidence_is_above_it(
        self, workspace: Workspace, tmp_path: Path
    ):
        """It now renders before the evidence, so the old wording was wrong."""
        register(workspace, tmp_path)
        body = gather(workspace, "622").body
        assert "the evidence above does not" not in body


class TestTheTwoHalvesStaySeparate:
    def test_business_comes_before_evidence(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Product rule 8: a reviewer decides from the first half."""
        accepted_rule(workspace, tmp_path)
        body = gather(workspace, "622").body

        assert body.index("## Business rules") < body.index(EVIDENCE_HEADING)

    def test_the_evidence_has_its_own_heading(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        body = gather(workspace, "622").body

        assert EVIDENCE_HEADING in body
        assert "### billing" in body  # nested under it, not a sibling

    def test_the_evidence_still_carries_its_completeness_note(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Restructuring must not drop what D-023 requires."""
        register(workspace, tmp_path)
        body = gather(workspace, "622").body
        assert "diff content" in body


class TestItWorksAsAPullRequestBody:
    def test_the_queue_renders_as_a_task_list(
        self, workspace: Workspace, tmp_path: Path
    ):
        """GitHub task-list syntax, so the same document is usable as a PR
        body. Reading ticks back is CON-58's unverified channel."""
        register(workspace, tmp_path)
        body = gather(workspace, "622", provider=FakeProvider([a_reading()])).body

        assert "- [ ] `#" in body

    def test_a_tick_is_declared_inert(self, workspace: Workspace, tmp_path: Path):
        """A checkbox that looks actionable and does nothing is worse than no
        checkbox. It says so."""
        register(workspace, tmp_path)
        body = gather(workspace, "622", provider=FakeProvider([a_reading()])).body

        assert "records nothing yet" in body
        assert "constat rule accept" in body

    def test_the_document_is_plain_markdown(
        self, workspace: Workspace, tmp_path: Path
    ):
        """No raw HTML: the same document has to render in Confluence and
        GitBook later, where `<details>` would not (CON-59)."""
        accepted_rule(workspace, tmp_path)
        body = gather(workspace, "622", provider=FakeProvider([a_reading()])).body

        for tag in ("<details>", "<summary>", "<br", "<div"):
            assert tag not in body

    def test_a_short_document_passes_through_untouched(self):
        assert bound_for_pr("# Ticket 1\n\nshort", "1") == "# Ticket 1\n\nshort"

    def test_a_long_document_is_bounded(self):
        body = "# Ticket 1\n\nbusiness\n\n" + EVIDENCE_HEADING + "\n\n" + "x" * 90_000
        bounded = bound_for_pr(body, "1")

        assert len(bounded) <= PR_BODY_LIMIT

    def test_the_omission_is_stated_not_silent(self):
        """D-023 one level up: GitHub would cut it mid-sentence instead."""
        body = "# Ticket 1\n\nbusiness\n\n" + EVIDENCE_HEADING + "\n\n" + "x" * 90_000
        bounded = bound_for_pr(body, "622")

        assert "Omitted here" in bounded
        assert "truncated silently" in bounded
        assert "constat document 622 --show" in bounded  # how to see it all

    def test_the_business_half_is_never_trimmed(self):
        """It is the half a reviewer decides from."""
        body = (
            "# Ticket 1\n\n"
            "IMPACTED RULE MARKER\n\n" + EVIDENCE_HEADING + "\n\n" + "x" * 90_000
        )
        bounded = bound_for_pr(body, "1")

        assert "IMPACTED RULE MARKER" in bounded
        assert "not trimmed" in bounded

    def test_a_business_half_that_alone_overflows_says_so(self):
        """Rather than returning something a forge will cut mid-sentence."""
        body = "# Ticket 1\n\n" + "b" * 90_000 + "\n\n" + EVIDENCE_HEADING + "\n\nx"
        bounded = bound_for_pr(body, "622")

        assert len(bounded) <= PR_BODY_LIMIT
        assert "does not fit a pull-request body" in bounded
        assert "constat document 622 --show" in bounded

    def test_a_real_document_fits_comfortably(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Measured, not assumed: a 30-commit document is about 21 KB."""
        accepted_rule(workspace, tmp_path)
        body = gather(workspace, "622", provider=FakeProvider([a_reading()])).body

        assert len(body) < PR_BODY_LIMIT
        assert bound_for_pr(body, "622") == body


class TestTheViewIsReadOnly:
    def test_rendering_discovers_nothing(self, workspace: Workspace, tmp_path: Path):
        """ARCHITECTURE.md § 2: rendering is a pure function of stored
        structure. The view is passed in rather than fetched, so `render`
        cannot reach a workspace at all."""
        import inspect

        from constat.operations import render

        assert "workspace" not in inspect.signature(render).parameters

    def test_the_view_reads_what_the_store_holds(
        self, workspace: Workspace, tmp_path: Path
    ):
        rule_id = accepted_rule(workspace, tmp_path)
        findings = collect(workspace, "622")
        view = catalogue_view(workspace, "622", findings)

        assert view.rule_count == 1
        assert "daily-limit" in view.impacted
        assert view.queue == ()
        assert Catalogue(workspace).list()[0].name == "daily-limit"
        assert rule_id == 1
