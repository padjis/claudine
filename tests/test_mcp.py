"""Tests for the MCP server (CON-50).

The most important test here asserts an **absence**: there is no tool that can
accept a rule proposal. A model that could accept would make "no proposal
becomes official without an explicit human decision" unenforceable, and the
hard prohibition in `CLAUDE.md` is that Constat must never mark a proposal
approved without a recorded human decision.

An absence is the easiest thing to lose. A later release adding one tool "for
convenience" would do it silently, so the tool list is asserted rather than
trusted.

The rest check that the gates hold through this door too — identity (D-040),
the credential refusal (D-047) and anchor grounding (D-052) — which they do by
construction, because every tool calls the same function the CLI does.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from constat.cli import main
from constat.store import Catalogue, Registry, RuleProposals, TicketStore, Workspace

from test_runs import distinct_subject
from test_scanning import AWS_KEY

pytest.importorskip("mcp", reason="the MCP server is an optional extra")

from constat.mcp import (  # noqa: E402  (after importorskip)
    EXPOSED_TOOLS,
    FORBIDDEN_TOOLS,
    build_server,
)


@pytest.fixture
def home(tmp_path: Path) -> str:
    """A workspace with one repository and ticket 622 pending."""
    ws = str(tmp_path / "ws")
    main(["--workspace", ws, "init"])
    clone = distinct_subject(tmp_path, "billing", "LIMIT = 250\n")
    main(["--workspace", ws, "repo", "add", str(clone), "--name", "billing"])
    main(["--workspace", ws, "ticket", "add", "622", "--no-provider"])
    return ws


@pytest.fixture
def leaky_home(tmp_path: Path) -> str:
    """A workspace whose evidence contains a credential."""
    ws = str(tmp_path / "ws")
    main(["--workspace", ws, "init"])
    clone = distinct_subject(tmp_path, "billing", f"K = '{AWS_KEY}'\n")
    main(["--workspace", ws, "repo", "add", str(clone), "--name", "billing"])
    main(["--workspace", ws, "ticket", "add", "622", "--no-provider"])
    return ws


def call(home: str, tool: str, **arguments):
    """Invoke one tool, as a client would, and return its text result."""
    server = build_server(home)
    result = asyncio.run(server.call_tool(tool, arguments))
    return result


def text_of(result) -> str:
    return result.content[0].text


def json_of(result):
    return json.loads(text_of(result))


class TestAcceptanceIsNotExposed:
    """The test this file exists for."""

    def test_the_tool_list_is_exactly_the_four(self, home: str):
        server = build_server(home)
        names = sorted(t.name for t in asyncio.run(server.list_tools()))
        assert names == sorted(EXPOSED_TOOLS)

    def test_no_tool_can_accept_or_reject(self, home: str):
        """Asserted on the live tool list, not on the source: a tool added by
        a decorator anywhere would show up here."""
        server = build_server(home)
        names = [t.name for t in asyncio.run(server.list_tools())]

        for forbidden in FORBIDDEN_TOOLS:
            assert not any(forbidden in name for name in names), (
                f"a tool matching {forbidden!r} is exposed; acceptance must "
                "stay a human act outside the agent's reach"
            )

    def test_the_instructions_say_nothing_is_accepted(self, home: str):
        """A model that does not know its output is provisional will present it
        as settled."""
        from constat.mcp import INSTRUCTIONS

        assert "Nothing you submit is accepted" in INSTRUCTIONS
        assert "no tool here that can make one" in INSTRUCTIONS

    def test_submitting_reports_that_nothing_was_accepted(self, home: str):
        reply = json.dumps(
            {
                "rules": [
                    {
                        "name": "daily-limit",
                        "statement": "A transfer over the limit is refused.",
                        "anchors": [
                            {"path_glob": "rules.py", "repository_alias": "billing"}
                        ],
                    }
                ]
            }
        )
        call(home, "gather_evidence", reference="622")
        result = json_of(call(home, "submit_rules", reference="622", reply=reply))

        assert result["accepted"] is False
        assert "no tool that can accept" in result["note"]

    def test_the_catalogue_stays_empty_however_much_is_submitted(self, home: str):
        reply = json.dumps(
            {
                "rules": [
                    {
                        "name": f"rule-{n}",
                        "statement": "Something holds.",
                        "anchors": [{"path_glob": "rules.py"}],
                    }
                    for n in range(3)
                ]
            }
        )
        call(home, "submit_rules", reference="622", reply=reply)

        with Workspace.open(home) as workspace:
            assert Catalogue(workspace).list() == ()
            assert len(RuleProposals(workspace).undecided("622")) == 3


class TestTheToolsWork:
    def test_gather_reports_every_repository(self, home: str):
        result = json_of(call(home, "gather_evidence", reference="622"))

        assert result["reference"] == "622"
        assert result["repositories_searched"] == 1
        assert result["repositories_contributing"] == 1
        assert result["run_id"] is not None

    def test_the_payload_carries_evidence_and_the_catalogue(self, home: str):
        payload = json_of(call(home, "get_payload", reference="622"))

        assert payload["reference"] == "622"
        assert sum(len(r["commits"]) for r in payload["repositories"]) == 1
        assert "catalogue" in payload

    def test_the_payload_carries_no_identity(self, home: str):
        """D-040 holds here because `get_payload` calls `export_payload`."""
        from test_ai import FIXTURE_EMAIL

        assert FIXTURE_EMAIL not in text_of(call(home, "get_payload", reference="622"))

    def test_submitting_stores_and_reports_discards(self, home: str):
        reply = json.dumps(
            {
                "rules": [
                    {
                        "name": "daily-limit",
                        "statement": "A transfer over the limit is refused.",
                        "anchors": [
                            {"path_glob": "rules.py", "repository_alias": "billing"}
                        ],
                    },
                    {
                        "name": "invented",
                        "statement": "Nothing supports this.",
                        "anchors": ["src/nope.py"],
                    },
                ]
            }
        )
        result = json_of(call(home, "submit_rules", reference="622", reply=reply))

        assert len(result["stored"]) == 1
        assert [d["name"] for d in result["discarded"]] == ["invented"]
        assert "grounded" in result["discarded"][0]["reason"]

    def test_the_queue_is_readable(self, home: str):
        reply = json.dumps(
            {
                "rules": [
                    {
                        "name": "daily-limit",
                        "statement": "A transfer over the limit is refused.",
                        "anchors": [{"path_glob": "rules.py"}],
                    }
                ]
            }
        )
        call(home, "submit_rules", reference="622", reply=reply, provider="claude")
        queue = json_of(call(home, "list_rule_proposals", reference="622"))

        assert len(queue) == 1
        assert queue[0]["name"] == "daily-limit"
        assert queue[0]["decision"] is None
        assert queue[0]["read_by"] == "claude"

    def test_the_queue_marks_the_model_as_self_reported(self, home: str):
        """D-045: nothing verifies what produced a reading, and a client
        reading this must not take it for an observed fact."""
        reply = json.dumps(
            {
                "rules": [
                    {
                        "name": "daily-limit",
                        "statement": "Something holds.",
                        "anchors": [{"path_glob": "rules.py"}],
                    }
                ]
            }
        )
        call(home, "submit_rules", reference="622", reply=reply, model="opus-5")
        queue = json_of(call(home, "list_rule_proposals", reference="622"))

        assert queue[0]["model"] == "opus-5"
        assert queue[0]["model_is_self_reported"] is True

    def test_an_empty_queue_is_an_empty_list(self, home: str):
        assert json_of(call(home, "list_rule_proposals", reference="622")) == []


class TestTheGatesHoldThroughThisDoor:
    """In-process a tool raises `ToolError`; a client receives `isError` with
    the same message. Both are checked — the second is the real contract."""

    def test_a_credential_refuses_the_payload(self, leaky_home: str):
        """D-047's gate fires here, because `get_payload` is `export_payload`.

        An MCP client is outside the process, so this is egress.
        """
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError) as exc:
            call(leaky_home, "get_payload", reference="622")

        message = str(exc.value)
        assert "refusing to send" in message
        assert "rules.py" in message  # where to look
        assert AWS_KEY not in message  # never the secret itself

    def test_gathering_still_works_with_a_credential_present(self, leaky_home: str):
        """Nothing is transmitted by gathering, so a false positive must not
        block it (D-044's asymmetry)."""
        result = json_of(call(leaky_home, "gather_evidence", reference="622"))
        assert result["credential_scan_findings"] == 1

    def test_an_unusable_reply_is_an_error_not_an_empty_result(self, home: str):
        """D-046 through MCP: a caller's bad JSON must not read as "no rules
        were identified"."""
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError, match="not valid JSON"):
            call(home, "submit_rules", reference="622", reply="I found none.")

    def test_an_unknown_ticket_is_an_error(self, home: str):
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError):
            call(home, "gather_evidence", reference="nope")

    def test_a_refusal_keeps_its_reason_rather_than_becoming_generic(
        self, leaky_home: str
    ):
        """The reason is the only part worth sending.

        These messages are the product's voice — "remove the credential and
        rotate it". A `ConstatError` left to escape is wrapped as an unexpected
        crash and the client sees only "Error executing tool get_payload",
        which a caller cannot act on.
        """
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError) as exc:
            call(leaky_home, "get_payload", reference="622")
        assert "rotate it" in str(exc.value)


class TestTheCommandLineEntryPoint:
    def test_the_mcp_subcommand_exists(self):
        from constat.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["mcp"])
        assert args.command == "mcp"

    def test_the_help_says_acceptance_is_not_exposed(self):
        from constat.cli import build_parser

        parser = build_parser()
        action = next(
            a for a in parser._actions if getattr(a, "choices", None) and "mcp" in a.choices
        )
        description = action.choices["mcp"].description
        assert "not exposed" in description
        assert "Nothing listens" in description

    def test_a_missing_dependency_is_reported_clearly(self, monkeypatch, capsys):
        """The extra is opt-in, so the failure has to name the fix."""
        import builtins

        real_import = builtins.__import__

        def fail_on_mcp(name, *args, **kwargs):
            if name == "mcp" or name.startswith("mcp."):
                raise ImportError("no mcp")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fail_on_mcp)
        monkeypatch.delitem(__import__("sys").modules, "constat.mcp", raising=False)

        code = main(["mcp"])
        assert code == 2
        assert "constat[mcp]" in capsys.readouterr().err


class TestThroughARealClient:
    """One end-to-end pass over stdio. Slower, and the only place the actual
    client contract is exercised rather than the in-process shortcut."""

    def _session(self, home: str):
        import shutil

        from mcp import StdioServerParameters

        constat = shutil.which("constat") or str(
            Path(__file__).resolve().parent.parent / ".venv" / "bin" / "constat"
        )
        return StdioServerParameters(
            command=constat, args=["--workspace", home, "mcp"]
        )

    def test_the_loop_runs_and_nothing_is_accepted(self, home: str):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        async def run():
            async with stdio_client(self._session(home)) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()

                    listed = await session.list_tools()
                    names = sorted(t.name for t in listed.tools)

                    await session.call_tool("gather_evidence", {"reference": "622"})
                    reply = json.dumps(
                        {
                            "rules": [
                                {
                                    "name": "daily-limit",
                                    "statement": "A transfer over the limit is refused.",
                                    "anchors": [{"path_glob": "rules.py"}],
                                }
                            ]
                        }
                    )
                    submitted = await session.call_tool(
                        "submit_rules", {"reference": "622", "reply": reply}
                    )
                    return names, json.loads(submitted.content[0].text)

        names, submitted = asyncio.run(run())

        assert names == sorted(EXPOSED_TOOLS)
        assert submitted["accepted"] is False
        assert len(submitted["stored"]) == 1

    def test_a_refusal_arrives_as_an_error_with_its_message(self, leaky_home: str):
        """The real contract: `isError`, and the reason intact."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        async def run():
            async with stdio_client(self._session(leaky_home)) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    return await session.call_tool(
                        "get_payload", {"reference": "622"}
                    )

        result = asyncio.run(run())

        assert result.is_error
        text = " ".join(c.text for c in result.content if hasattr(c, "text"))
        assert "refusing to send" in text
        assert AWS_KEY not in text


class TestMcpIsExemptFromTheProviderGate:
    """D-059 exempts this path, and the exemption is the design (D-045).

    On MCP the **host** supplies the model, so Constat having no provider is
    correct rather than a misconfiguration. If `gather_evidence` refused the
    way the CLI does, the entire intended workflow would stop working on a
    machine with no API key — which is the machine it was designed for.
    """

    def test_gathering_works_with_no_provider_configured(self, home, monkeypatch):
        monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
        result = json_of(call(home, "gather_evidence", reference="622"))

        assert result["repositories_searched"] >= 1

    def test_the_payload_is_readable_with_no_provider_configured(
        self, home, monkeypatch
    ):
        """The whole point of the MCP path: the evidence goes out, the host's
        model reads it, and Constat never needed a key."""
        monkeypatch.delenv("CONSTAT_AI_PROVIDER", raising=False)
        call(home, "gather_evidence", reference="622")
        payload = json_of(call(home, "get_payload", reference="622"))

        assert payload["reference"] == "622"

    def test_no_tool_mentions_the_provider_gate(self):
        """A `--no-provider` equivalent would be meaningless here, so there
        must not be one to pass."""
        from constat.mcp import EXPOSED_TOOLS

        assert "no_provider" not in " ".join(EXPOSED_TOOLS)
