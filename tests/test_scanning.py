"""Tests for credential scanning at the provider boundary (CON-45).

Done-when is "a payload containing a credential is refused rather than sent".

The property that matters most is not detection — it is that **the scanner is
not itself a leak**. A finding, an error message, a document body and an
operation record all name where to look and never what was found. A scanner
that copies the credential into the workspace, and from there into every
frozen version of the document, would be worse than no scanner.

Second in importance is false-positive resistance. The ticket chose known
formats only (over entropy scoring) precisely because a refusal has to be
believable: one that fires on a lockfile hash teaches people to pass
`--accept-scan-findings` without reading it.

The credential-shaped strings below are published documentation examples
(AWS's own `AKIAIOSFODNN7EXAMPLE`) or obvious fabrications. None is real. A
side effect worth knowing: running Constat against *this* repository will
flag this file, which is the scanner working correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constat.ai import COMMIT_MESSAGE, redact, scan
from constat.ai.scanning import _is_credential_value, describe, refusal_message
from constat.errors import PayloadRefused
from constat.operations import gather
from constat.store import Registry, TicketStore, Workspace

from helpers import commit_file, git
from test_ai import FakeProvider

AWS_KEY = "AKIAIOSFODNN7EXAMPLE"


def make_subject(
    tmp_path: Path,
    name: str,
    content: str = "LIMIT = 250\n",
    message: str = "Raise the limit (#622)",
) -> Path:
    """A clone whose `develop` carries ticket 622's work, not yet in mainline."""
    source = tmp_path / f"{name}-src"
    source.mkdir()
    git(source, "init", "--initial-branch=main", "--quiet")
    commit_file(source, "rules.py", "LIMIT = 100\n", "Initial")

    clone = tmp_path / name
    git(tmp_path, "clone", "--quiet", str(source), str(clone))
    git(clone, "checkout", "--quiet", "-b", "develop")
    commit_file(clone, "rules.py", content, message)
    git(clone, "checkout", "--quiet", "main")
    return clone


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


def gathered_payload(workspace, tmp_path, **kwargs):
    Registry(workspace).add(str(make_subject(tmp_path, "billing", **kwargs)), alias="billing")
    TicketStore(workspace).add("622")
    return redact("622", gather(workspace, "622").findings)


class TestDetectors:
    """One case per format. Each string is shaped like the real thing."""

    @pytest.mark.parametrize(
        "detector,text",
        [
            ("aws_access_key_id", f"aws_key = '{AWS_KEY}'"),
            ("github_token", "ghp_" + "a" * 36),
            ("github_fine_grained_token", "github_pat_" + "A1b2" * 20),
            ("gitlab_token", "glpat-" + "xY3z" * 6),
            ("slack_token", "xoxb-123456789012-abcdefghijkl"),
            ("stripe_secret_key", "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"),
            ("google_api_key", "AIza" + "B" * 35),
            ("npm_token", "npm_" + "c" * 36),
            ("anthropic_api_key", "sk-ant-api03-" + "Zz9" * 10),
            ("openai_api_key", "sk-proj-" + "Q7w" * 20),
            ("private_key_block", "-----BEGIN RSA PRIVATE KEY-----"),
            ("private_key_block", "-----BEGIN PRIVATE KEY-----"),
            ("jwt", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92"),
            ("credentials_in_url", "postgres://svc:Hunter2Tr0ub4dor@db.internal:5432/app"),
        ],
    )
    def test_a_known_format_is_detected(self, detector, text):
        from constat.ai.scanning import _scan_line

        assert detector in _scan_line(text)

    def test_an_assigned_credential_is_detected(self):
        from constat.ai.scanning import _scan_line

        assert "assigned_credential" in _scan_line('API_KEY = "Xk7pQ2mZr9tLvB3nW8sY"')


class TestFalsePositiveResistance:
    """Every case here would make a refusal untrustworthy."""

    @pytest.mark.parametrize(
        "text",
        [
            'API_KEY = "your-api-key-here"',
            'API_KEY = "changeme"',
            'password = "xxxxxxxxxxxxxxxxxxxxxxxx"',
            'password = "placeholder-value-goes-here"',
            'SECRET = "${VAULT_SECRET_PATH_VALUE}"',
            'SECRET = "{{ secret_from_ansible_vault }}"',
            'api_key = os.environ["REAL_API_KEY_NAME"]',
            "apiKey: process.env.SOME_LONG_VARIABLE_NAME",
            'token = "<your-personal-access-token>"',
            'password = "aaaaaaaaaaaaaaaaaaaaaaaaaaa"',
            'password = "----------------------------"',
            # The ones that made entropy scoring unusable in this product.
            '"integrity": "sha512-abcdefghijklmnopqrstuvwxyz0123456789"',
            "git remote add origin ssh://git@github.com/padjis/constat.git",
            # Code, not data. A line of this shape — a `token`-named variable
            # assigned an expression — is what the scanner originally got
            # wrong on a real repository. Written synthetically here rather
            # than copied, so no private source lands in a public repository.
            "    const tokenAtPause = ++playbackTokenRef.current;",
            "    const token = someRef.current;",
            "    this.accessToken = response.data.accessToken;",
            "    const secret = computeSecretFromSeed(seed);",
            "    password = currentUser.credentials.password;",
            "    apiKey = config?.apiKey ?? defaultApiKeyValue;",
            "    const authToken = useMemo(() => buildToken(session), [session]);",
        ],
    )
    def test_a_non_credential_is_not_flagged(self, text):
        from constat.ai.scanning import _scan_line

        assert _scan_line(text) == set(), text

    def test_the_shape_that_forced_the_code_rule(self):
        """Regression guard for the false positive found on real evidence.

        Running the scanner over real commits before shipping flagged a
        `token`-named variable assigned an expression. One refusal like that
        teaches people to override by reflex, which is worse than the detector
        not existing. The line here is synthetic; the shape is the one that
        fired.
        """
        from constat.ai.scanning import _scan_line

        assert _scan_line("const tokenAtPause = ++playbackTokenRef.current;") == set()

    def test_an_unquoted_identifier_like_value_is_not_flagged(self):
        """`mySecretValue` and a real key are the same shape.

        Quoting is the only signal available that a value is a literal rather
        than a reference, so an unquoted value has to look more obviously
        random: three character classes instead of two.
        """
        from constat.ai.scanning import _scan_line

        assert _scan_line("const secret = mySecretValueHere;") == set()

    def test_an_unquoted_env_file_credential_is_still_flagged(self):
        """Quoting cannot simply be required — a `.env` file has none, and it
        is a prime leak vector."""
        from constat.ai.scanning import _scan_line

        assert "assigned_credential" in _scan_line("API_KEY=Xk7pQ2mZr9tLvB3nW8sY")

    def test_a_quoted_two_class_credential_is_flagged(self):
        """Quoted values are judged more leniently, by design."""
        from constat.ai.scanning import _scan_line

        assert "assigned_credential" in _scan_line('SECRET = "XkPqMzRtLvBnWsYdGhJk"')

    def test_a_long_hex_digest_assigned_to_a_secret_name_is_flagged(self):
        """Not a false positive: a 32+ hex value under a secret-ish name is a
        credential often enough that refusing is right."""
        from constat.ai.scanning import _scan_line

        assert "assigned_credential" in _scan_line(f'SECRET_TOKEN = "{"a1b2c3d4" * 5}"')

    def test_a_passphrase_of_one_character_class_is_missed_and_that_is_stated(self):
        """A documented limit, asserted so it cannot change silently.

        `correcthorsebatterystaple` is a real password and is not detected:
        one character class is indistinguishable from an English word. The
        ticket chose near-zero false positives and this is what it costs.
        """
        assert not _is_credential_value("correcthorsebatterystaple")


class TestScanningAPayload:
    def test_a_credential_in_a_diff_is_found_with_its_location(
        self, workspace: Workspace, tmp_path: Path
    ):
        payload = gathered_payload(
            workspace, tmp_path, content=f"LIMIT = 250\nAWS_KEY = '{AWS_KEY}'\n"
        )
        findings = scan(payload)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.repository_alias == "billing"
        assert finding.path == "rules.py"
        assert finding.detector == "aws_access_key_id"
        assert finding.line is not None

    def test_a_credential_in_a_commit_message_is_found(
        self, workspace: Workspace, tmp_path: Path
    ):
        """People paste tokens into commit messages while debugging."""
        payload = gathered_payload(
            workspace, tmp_path, message=f"Raise the limit (#622)\n\nused {AWS_KEY}\n"
        )
        findings = scan(payload)

        assert [f.path for f in findings] == [COMMIT_MESSAGE]
        assert findings[0].line is None

    def test_a_removed_credential_is_still_found(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A credential deleted by the change was still committed, is still in
        history, and would still be sent in the diff."""
        source = tmp_path / "src"
        source.mkdir()
        git(source, "init", "--initial-branch=main", "--quiet")
        commit_file(source, "rules.py", f"KEY = '{AWS_KEY}'\n", "Initial")

        clone = tmp_path / "billing"
        git(tmp_path, "clone", "--quiet", str(source), str(clone))
        git(clone, "checkout", "--quiet", "-b", "develop")
        commit_file(clone, "rules.py", "KEY = ''\n", "Remove the key (#622)")
        git(clone, "checkout", "--quiet", "main")

        Registry(workspace).add(str(clone), alias="billing")
        TicketStore(workspace).add("622")
        findings = scan(redact("622", gather(workspace, "622").findings))

        assert [f.detector for f in findings] == ["aws_access_key_id"]

    def test_a_clean_payload_produces_nothing(
        self, workspace: Workspace, tmp_path: Path
    ):
        assert scan(gathered_payload(workspace, tmp_path)) == ()

    def test_findings_are_deduplicated(self, workspace: Workspace, tmp_path: Path):
        """The same detector on the same line is one finding, not several."""
        payload = gathered_payload(
            workspace, tmp_path, content=f"A = '{AWS_KEY}'\nB = '{AWS_KEY}'\n"
        )
        findings = scan(payload)
        assert len(findings) == 2  # two lines, one finding each
        assert len({(f.path, f.line) for f in findings}) == 2


class TestTheScannerIsNotItselfALeak:
    """The property that matters most."""

    def test_a_finding_never_carries_the_matched_text(
        self, workspace: Workspace, tmp_path: Path
    ):
        payload = gathered_payload(
            workspace, tmp_path, content=f"AWS_KEY = '{AWS_KEY}'\n"
        )
        findings = scan(payload)
        assert AWS_KEY not in repr(findings)
        assert AWS_KEY not in findings[0].describe()

    def test_the_refusal_message_never_carries_the_matched_text(
        self, workspace: Workspace, tmp_path: Path
    ):
        payload = gathered_payload(
            workspace, tmp_path, content=f"AWS_KEY = '{AWS_KEY}'\n"
        )
        message = refusal_message(scan(payload))
        assert AWS_KEY not in message
        assert "rules.py" in message
        assert "--accept-scan-findings" in message

    def test_the_document_never_carries_the_matched_text(
        self, workspace: Workspace, tmp_path: Path
    ):
        """The decisive one.

        The body is persisted and will be frozen into approved versions, so a
        credential written here would outlive the repository it came from.
        """
        Registry(workspace).add(
            str(make_subject(tmp_path, "billing", content=f"K = '{AWS_KEY}'\n")),
            alias="billing",
        )
        TicketStore(workspace).add("622")

        result = gather(workspace, "622")
        assert AWS_KEY not in result.body
        assert "## Credential scan" in result.body
        assert "rules.py" in result.body

    def test_the_stored_override_record_never_carries_the_matched_text(
        self, workspace: Workspace, tmp_path: Path
    ):
        Registry(workspace).add(
            str(make_subject(tmp_path, "billing", content=f"K = '{AWS_KEY}'\n")),
            alias="billing",
        )
        TicketStore(workspace).add("622")
        gather(
            workspace, "622", provider=FakeProvider(), accept_scan_findings=True
        )

        rows = workspace.execute(
            "SELECT summary, payload FROM operation WHERE kind = 'scan_override'"
        ).fetchall()
        assert len(rows) == 1
        assert AWS_KEY not in (rows[0]["summary"] + (rows[0]["payload"] or ""))
        assert "rules.py" in rows[0]["payload"]


class TestTheGate:
    def _register(self, workspace, tmp_path, content):
        Registry(workspace).add(
            str(make_subject(tmp_path, "billing", content=content)), alias="billing"
        )
        TicketStore(workspace).add("622")

    def test_a_provider_run_is_refused(self, workspace: Workspace, tmp_path: Path):
        """The done-when."""
        self._register(workspace, tmp_path, f"K = '{AWS_KEY}'\n")

        with pytest.raises(PayloadRefused) as exc:
            gather(workspace, "622", provider=FakeProvider())
        assert "refusing to send" in str(exc.value)

    def test_the_refused_run_sends_nothing(self, workspace: Workspace, tmp_path: Path):
        """Refused *before* interpret, not after."""
        self._register(workspace, tmp_path, f"K = '{AWS_KEY}'\n")
        provider = FakeProvider()

        with pytest.raises(PayloadRefused):
            gather(workspace, "622", provider=provider)
        assert provider.seen == []

    def test_the_refused_run_leaves_the_document_untouched(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A partially written document would record evidence as if the run
        had succeeded."""
        self._register(workspace, tmp_path, f"K = '{AWS_KEY}'\n")

        with pytest.raises(PayloadRefused):
            gather(workspace, "622", provider=FakeProvider())
        assert TicketStore(workspace).document("622").is_empty

    def test_no_provider_means_no_refusal(self, workspace: Workspace, tmp_path: Path):
        """A false positive must not block a run that sends nothing.

        This is why scanning and refusing are separated: the scan still runs
        and still reports, but there is nothing to protect.
        """
        self._register(workspace, tmp_path, f"K = '{AWS_KEY}'\n")

        result = gather(workspace, "622")  # null provider
        assert result.scan_findings
        assert not result.scan_accepted
        assert "Nothing was sent" in result.body

    def test_the_scan_runs_even_with_no_provider(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Otherwise the scanner is dead code until CON-42 — the mistake D-040
        avoided by running redaction on the default path."""
        self._register(workspace, tmp_path, "LIMIT = 250\n")

        result = gather(workspace, "622")
        assert result.scan_findings == ()
        assert "## Credential scan" in result.body

    def test_a_clean_payload_reaches_the_provider(
        self, workspace: Workspace, tmp_path: Path
    ):
        self._register(workspace, tmp_path, "LIMIT = 250\n")
        provider = FakeProvider()

        gather(workspace, "622", provider=provider)
        assert len(provider.seen) == 1


class TestTheOverride:
    def _register(self, workspace, tmp_path):
        Registry(workspace).add(
            str(make_subject(tmp_path, "billing", content=f"K = '{AWS_KEY}'\n")),
            alias="billing",
        )
        TicketStore(workspace).add("622")

    def test_it_lets_the_payload_through(self, workspace: Workspace, tmp_path: Path):
        self._register(workspace, tmp_path)
        provider = FakeProvider()

        result = gather(
            workspace, "622", provider=provider, accept_scan_findings=True
        )
        assert len(provider.seen) == 1
        assert result.scan_accepted

    def test_it_is_recorded_in_the_document_as_a_human_decision(
        self, workspace: Workspace, tmp_path: Path
    ):
        """An override nobody can see afterwards is the same as no scan."""
        self._register(workspace, tmp_path)

        body = gather(
            workspace, "622", provider=FakeProvider(), accept_scan_findings=True
        ).body
        assert "accepted by a human" in body
        assert "human_decision" in body
        assert "--accept-scan-findings" in body

    def test_it_is_recorded_as_an_operation(self, workspace: Workspace, tmp_path: Path):
        self._register(workspace, tmp_path)
        gather(workspace, "622", provider=FakeProvider(), accept_scan_findings=True)

        rows = workspace.execute(
            "SELECT kind, summary FROM operation WHERE kind = 'scan_override'"
        ).fetchall()
        assert len(rows) == 1
        assert "1 credential-scan finding(s)" in rows[0]["summary"]

    def test_it_applies_to_one_run_only(self, workspace: Workspace, tmp_path: Path):
        """No stored state, so the next run is refused again."""
        self._register(workspace, tmp_path)
        gather(workspace, "622", provider=FakeProvider(), accept_scan_findings=True)

        with pytest.raises(PayloadRefused):
            gather(workspace, "622", provider=FakeProvider())

    def test_it_records_nothing_when_there_was_nothing_to_accept(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Passing the flag on a clean run must not fabricate a decision."""
        Registry(workspace).add(
            str(make_subject(tmp_path, "billing")), alias="billing"
        )
        TicketStore(workspace).add("622")

        result = gather(
            workspace, "622", provider=FakeProvider(), accept_scan_findings=True
        )
        assert not result.scan_accepted
        rows = workspace.execute(
            "SELECT id FROM operation WHERE kind = 'scan_override'"
        ).fetchall()
        assert rows == []


class TestTheRenderedSection:
    def test_a_clean_scan_says_what_it_does_not_cover(
        self, workspace: Workspace, tmp_path: Path
    ):
        """A silent pass would be read as proof, which it is not."""
        payload = gathered_payload(workspace, tmp_path)
        section = "\n".join(describe(payload, (), sent=False))

        assert "No credential-shaped strings were found" in section
        assert "known credential formats only" in section
        assert "not proof that none are present" in section
