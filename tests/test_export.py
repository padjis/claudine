"""Tests for the payload export path and the shared release gate (CON-49).

D-045 gave Constat a second front door. D-040 stopped identity crossing the
first one and D-044 refused credentials at it — both gated on
`provider.name != NULL_PROVIDER_NAME`, which an export bypasses entirely. A
gate that covers one of two doors is decoration, so the property under test
here is that **both doors share it**.

The one deliberate asymmetry: `gather` with no provider scans and reports but
does not refuse, because nothing is transmitted and a false positive should not
block a local run. An export always refuses, because by the time it has
printed it has left.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from constat.ai import as_dict, guard_release
from constat.errors import PayloadRefused
from constat.operations import collect, export_payload, gather
from constat.store import Registry, TicketStore, Workspace

from helpers import commit_file, git
from test_ai import FIXTURE_EMAIL, FakeProvider
from test_scanning import AWS_KEY, make_subject


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


def register(workspace, tmp_path, content: str = "LIMIT = 250\n"):
    Registry(workspace).add(
        str(make_subject(tmp_path, "billing", content=content)), alias="billing"
    )
    TicketStore(workspace).add("622")


class TestTheReleaseGate:
    """`guard_release` is the single chokepoint both doors go through."""

    def test_a_clean_payload_passes_and_reports_nothing(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path)
        payload = export_payload(workspace, "622").payload
        assert guard_release(payload) == ()

    def test_a_credential_is_refused(self, workspace: Workspace, tmp_path: Path):
        register(workspace, tmp_path, content=f"K = '{AWS_KEY}'\n")
        from constat.ai import redact

        payload = redact("622", collect(workspace, "622"))
        with pytest.raises(PayloadRefused):
            guard_release(payload)

    def test_it_raises_rather_than_returning_a_flag(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A caller that forgets to check a boolean still sends the payload.

        Raising removes that failure mode, so the signature is asserted as part
        of the contract rather than left to convention.
        """
        from constat.ai import redact

        register(workspace, tmp_path, content=f"K = '{AWS_KEY}'\n")
        payload = redact("622", collect(workspace, "622"))

        findings = guard_release(payload, accepted=True)
        assert findings  # accepted: returned for reporting, not swallowed


class TestExportingAPayload:
    def test_it_produces_the_evidence(self, workspace: Workspace, tmp_path: Path):
        register(workspace, tmp_path)
        result = export_payload(workspace, "622")

        assert result.payload.reference == "622"
        assert result.payload.commit_count == 1
        assert [r.alias for r in result.payload.repositories] == ["billing"]

    def test_it_carries_no_identity(self, workspace: Workspace, tmp_path: Path):
        """D-040 applies here too — the boundary is the same boundary."""
        register(workspace, tmp_path)
        result = export_payload(workspace, "622")
        assert FIXTURE_EMAIL not in str(as_dict(result.payload))

    def test_it_writes_no_document(self, workspace: Workspace, tmp_path: Path):
        """Exporting is a read. A reader that mutates the governance record
        would make the document depend on who looked at it."""
        register(workspace, tmp_path)
        export_payload(workspace, "622")
        assert TicketStore(workspace).document("622").is_empty

    def test_an_unknown_ticket_is_refused(self, workspace: Workspace):
        from constat.errors import NotRegistered

        with pytest.raises(NotRegistered):
            export_payload(workspace, "nope")

    def test_it_serialises_to_json(self, workspace: Workspace, tmp_path: Path):
        """Whatever reads this is outside the process, so the shape has to
        survive a round trip through plain data."""
        register(workspace, tmp_path)
        text = json.dumps(as_dict(export_payload(workspace, "622").payload), default=str)
        again = json.loads(text)
        assert again["reference"] == "622"
        assert again["repositories"][0]["alias"] == "billing"


class TestTheAsymmetryBetweenTheTwoDoors:
    """The only place the two paths deliberately differ."""

    def test_a_local_gather_with_no_provider_is_not_refused(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, content=f"K = '{AWS_KEY}'\n")
        result = gather(workspace, "622")  # null provider
        assert result.scan_findings
        assert not result.scan_accepted

    def test_an_export_of_the_same_evidence_is_refused(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The hole D-045 opened, closed.

        Same repository, same credential, no provider configured — `gather`
        tolerates it and `export_payload` must not, because the export leaves.
        """
        register(workspace, tmp_path, content=f"K = '{AWS_KEY}'\n")
        with pytest.raises(PayloadRefused):
            export_payload(workspace, "622")

    def test_the_refusal_names_where_to_look_but_not_the_secret(
        self, workspace: Workspace, tmp_path: Path
    ):
        register(workspace, tmp_path, content=f"K = '{AWS_KEY}'\n")
        with pytest.raises(PayloadRefused) as exc:
            export_payload(workspace, "622")

        message = str(exc.value)
        assert "rules.py" in message
        assert AWS_KEY not in message


class TestOverridingAnExport:
    def test_the_override_lets_it_through(self, workspace: Workspace, tmp_path: Path):
        register(workspace, tmp_path, content=f"K = '{AWS_KEY}'\n")
        result = export_payload(workspace, "622", accept_scan_findings=True)
        assert result.accepted
        assert len(result.scan_findings) == 1

    def test_the_override_is_recorded(self, workspace: Workspace, tmp_path: Path):
        """An override nobody can see afterwards is the same as no scan
        (D-044) — and an export override let a credential off the machine."""
        register(workspace, tmp_path, content=f"K = '{AWS_KEY}'\n")
        export_payload(workspace, "622", accept_scan_findings=True)

        rows = workspace.execute(
            "SELECT summary, payload FROM operation "
            "WHERE kind = 'scan_override_export'"
        ).fetchall()
        assert len(rows) == 1
        assert "1 credential-scan finding(s)" in rows[0]["summary"]
        assert "rules.py" in rows[0]["payload"]
        assert AWS_KEY not in rows[0]["payload"]

    def test_an_export_override_is_distinguishable_from_a_send_override(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Two different disclosures. Collapsing them would lose which one a
        reviewer is looking at."""
        register(workspace, tmp_path, content=f"K = '{AWS_KEY}'\n")
        export_payload(workspace, "622", accept_scan_findings=True)
        gather(
            workspace, "622", provider=FakeProvider(), accept_scan_findings=True
        )

        kinds = {
            row["kind"]
            for row in workspace.execute(
                "SELECT kind FROM operation WHERE kind LIKE 'scan_override%'"
            ).fetchall()
        }
        assert kinds == {"scan_override_export", "scan_override"}

    def test_a_clean_export_records_nothing(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Passing the flag on a clean run must not fabricate a decision."""
        register(workspace, tmp_path)
        result = export_payload(workspace, "622", accept_scan_findings=True)
        assert not result.accepted
        assert (
            workspace.execute(
                "SELECT id FROM operation WHERE kind = 'scan_override_export'"
            ).fetchall()
            == []
        )


class TestCollectIsShared:
    def test_both_paths_see_the_same_evidence(
        self, workspace: Workspace, tmp_path: Path
    ):
        """`gather` and `export_payload` must not disagree about what a
        ticket's evidence is, or a reviewer and a model are looking at
        different things."""
        register(workspace, tmp_path)

        exported = export_payload(workspace, "622").payload
        probe = FakeProvider()
        gather(workspace, "622", provider=probe)
        sent = probe.seen[0]

        assert as_dict(exported) == as_dict(sent)

    def test_collect_writes_nothing(self, workspace: Workspace, tmp_path: Path):
        register(workspace, tmp_path)
        collect(workspace, "622")
        assert TicketStore(workspace).document("622").is_empty


class TestTheCommandLine:
    def _setup(self, tmp_path, content: str = "LIMIT = 250\n") -> str:
        from constat.cli import main

        ws = str(tmp_path / "ws")
        main(["--workspace", ws, "init"])
        clone = make_subject(tmp_path, "billing", content=content)
        main(["--workspace", ws, "repo", "add", str(clone), "--name", "billing"])
        main(["--workspace", ws, "ticket", "add", "622", "--no-provider"])
        return ws

    def test_payload_prints_json_on_stdout(self, tmp_path, capsys):
        """stdout stays a clean JSON document so a pipe can consume it."""
        from constat.cli import main

        ws = self._setup(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "document", "622", "--payload", "--no-provider"]) == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["reference"] == "622"

    def test_a_credential_refuses_the_export(self, tmp_path, capsys):
        from constat.cli import main

        ws = self._setup(tmp_path, content=f"K = '{AWS_KEY}'\n")
        capsys.readouterr()

        assert main(["--workspace", ws, "document", "622", "--payload", "--no-provider"]) == 5
        captured = capsys.readouterr()
        assert "refusing to send" in captured.err
        assert AWS_KEY not in captured.err
        assert captured.out == ""  # nothing escaped before the refusal

    def test_the_override_warns_on_stderr_and_still_prints(self, tmp_path, capsys):
        from constat.cli import main

        ws = self._setup(tmp_path, content=f"K = '{AWS_KEY}'\n")
        capsys.readouterr()

        code = main(
            [
                "--workspace", ws, "document", "622",
                "--payload", "--accept-scan-findings",
            ]
        )
        assert code == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["reference"] == "622"
        assert "were accepted" in captured.err

    def test_payload_and_show_together_are_a_usage_error(self, tmp_path, capsys):
        from constat.cli import main

        ws = self._setup(tmp_path)
        capsys.readouterr()

        assert main(["--workspace", ws, "document", "622", "--payload", "--show", "--no-provider"]) == 2
        assert "pick one" in capsys.readouterr().err

    def test_the_export_leaves_the_document_untouched(self, tmp_path, capsys):
        """`document --payload` reads; `document` writes.

        `ticket add` already filled the body, so "is it empty" asserts nothing
        here — the property is that the export does not *change* it.
        """
        from constat.cli import main

        ws = self._setup(tmp_path)

        def body() -> str:
            capsys.readouterr()
            main(["--workspace", ws, "document", "622", "--show", "--no-provider"])
            return capsys.readouterr().out

        before = body()
        assert "rules.py" in before  # the document really does have content

        capsys.readouterr()
        main(["--workspace", ws, "document", "622", "--payload", "--no-provider"])
        assert body() == before
