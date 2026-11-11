"""Credential scanning at the provider boundary (CON-45).

D-040 stopped identity crossing the boundary, and said plainly what it did not
solve: commit messages and diffs still leave the machine, so a credential
committed by mistake would be sent as readily as anything else. This is that
gap.

**Known formats only.** Every detector here recognises a credential by its
*shape* — an `AKIA` prefix, a PEM header, a `ghp_` token. Entropy scoring was
considered and rejected: it fires on minified JavaScript, lockfile integrity
hashes and base64-embedded assets, all of which are abundant in both subject
repositories. In a governance tool a false refusal blocks real work until
someone overrides it, and that is how people learn to override by reflex. A
detector that is nearly always right is worth more than one that catches more.

The cost of that choice is stated rather than hidden: **a credential with no
recognisable shape is not detected.** `scan` returning nothing is not a
statement that the payload is clean, and `describe` says so in the document.

**Findings never carry the secret.** A finding names the repository, commit,
path, line and detector. Recording the matched text would copy the credential
into the workspace and then into every frozen version of the document — the
scanner would become the leak.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .redaction import ProviderPayload

COMMIT_MESSAGE = "(commit message)"
"""Stands in for a path when the finding is in a subject or body rather than a
diff. A sentinel rather than None so a reviewer reading the document sees where
to look without needing to know the data model."""


DETECTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Prefix-and-length formats. Each is specified by its issuer, so a match is
    # a credential rather than a string that resembles one.
    ("aws_access_key_id", re.compile(r"\b(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("github_fine_grained_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{70,}")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("stripe_secret_key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("anthropic_api_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{40,}")),
    # A PEM header is unambiguous, and the body does not need matching: the
    # header alone means a private key is in the diff.
    ("private_key_block", re.compile(r"-----BEGIN (?:[A-Z][A-Z ]* )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
)

CREDENTIALS_IN_URL = re.compile(
    r"\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:(?P<password>[^\s/:@]+)@"
)
"""A password embedded in a connection string. `ssh://git@host` does not match
— there is no colon before the `@` — which keeps ordinary Git remotes clean."""

ASSIGNMENT = re.compile(
    r"(?i)\b(?P<key>[a-z0-9_.\-]*"
    r"(?:api[_\-]?key|secret|passwd|password|pwd|token|access[_\-]?key|credentials?)"
    r"[a-z0-9_.\-]*)\s*[:=]\s*(?P<quote>[\"']?)(?P<value>[^\s\"';,)\]}]{20,})(?P=quote)"
)
"""The only detector keyed on a *name* rather than a format, and the only one
that can be wrong. Everything it matches goes through `_is_credential_value`."""

PLACEHOLDER = re.compile(
    r"(?i)^(?:"
    r"x{3,}|\*{3,}|\.{3,}|-{3,}|_{3,}"
    r"|change[_\-]?me|replace[_\-]?me|insert[_\-].*|your[_\-].*|my[_\-].*"
    r"|example.*|sample.*|dummy.*|fake.*|placeholder.*|redacted.*|todo|tbd"
    r"|secret|password|passwd|token|api[_\-]?key|credentials?"
    r"|none|null|nil|true|false|undefined|empty"
    r"|test|testing|foo.*|bar.*|baz.*|abc123.*"
    r")$"
)

INTERPOLATION = re.compile(r"\$\{|\{\{|%\(|%s|<[a-zA-Z]|os\.environ|process\.env|getenv")
"""A value read from the environment is the *correct* pattern, not a leak."""

CODE_EXPRESSION = re.compile(
    r"^(?:\+\+|--|new\s|await\s|typeof\s|[+\-!~&*^|])"  # opens with an operator
    r"|[(\[{]"  # a call or a literal
    r"|=>|\|\||&&|\?\?|\?\."  # operators no credential contains
    r"|^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+$"  # a.b.c — a reference
)
"""Rejects values that are *code* rather than data.

Added after the scanner fired on real source: a `token`-named variable
assigned an expression, such as `const tokenAtPause = ++someRef.current;`.
That is the single most common shape in real code that the name-keyed
detector gets wrong, and one such refusal is enough to teach someone to pass
`--accept-scan-findings` without reading it.

A "bare identifier" rule was tried here and removed: `mySecretValue` and
`Xk7pQ2mZr9tLvB3nW8sY` are the same shape, so it rejected real credentials
too. That distinction is made by character-class variety instead, below.

The cost: a base64 credential beginning with `+` is missed. Accepted, and
cheaper than a detector nobody believes."""

HEX = re.compile(r"^[0-9a-f]{32,}$", re.IGNORECASE)


def _is_credential_value(value: str, *, quoted: bool = True) -> bool:
    """Whether an assigned value looks like a real credential.

    Conservative on purpose: every rejection here is a credential this scanner
    will miss, and every acceptance is a refusal someone has to deal with. The
    ticket chose near-zero false positives, so ambiguity resolves to "not a
    credential".

    `quoted` is the strongest signal available that a value is a literal
    rather than a reference, so an unquoted value must look more obviously
    random. It cannot simply be required: a `.env` file writes
    `API_KEY=…` with no quotes at all, and that is a prime leak vector.
    """
    if PLACEHOLDER.match(value) or INTERPOLATION.search(value):
        return False
    if CODE_EXPRESSION.search(value):
        return False
    if len(set(value)) < 5:
        # `aaaaaaaaaaaaaaaaaaaaaa`, `0000...`, `---...`.
        return False
    if HEX.match(value):
        return True

    classes = sum(
        (
            any(c.islower() for c in value),
            any(c.isupper() for c in value),
            any(c.isdigit() for c in value),
            any(not c.isalnum() for c in value),
        )
    )
    # One character class is a word or a decimal, so a passphrase is missed —
    # accepted and stated. An unquoted value needs three, which is what
    # separates `Xk7pQ2mZr9tLvB3nW8sY` from `mySecretValue`.
    return classes >= (2 if quoted else 3)


@dataclass(frozen=True)
class SecretFinding:
    """Where to look, and what kind of thing to look for. Never the secret."""

    repository_alias: str
    commit_sha: str
    path: str
    detector: str
    line: int | None = None

    def describe(self) -> str:
        where = f"`{self.repository_alias}` `{self.commit_sha[:12]}` `{self.path}`"
        if self.line is not None:
            where += f" line {self.line}"
        return f"{where} — {self.detector}"


def _scan_line(text: str) -> set[str]:
    """Detector names matching one line."""
    hits = {name for name, pattern in DETECTORS if pattern.search(text)}

    url = CREDENTIALS_IN_URL.search(text)
    if url and _is_credential_value(url.group("password")):
        hits.add("credentials_in_url")

    for match in ASSIGNMENT.finditer(text):
        if _is_credential_value(
            match.group("value"), quoted=bool(match.group("quote"))
        ):
            hits.add("assigned_credential")
            break

    return hits


def scan(payload: ProviderPayload) -> tuple[SecretFinding, ...]:
    """Every credential-shaped string in the payload, deduplicated and ordered.

    Removed diff lines are scanned too. A credential deleted in the change was
    still committed, is still in history, and would still be sent.
    """
    findings: list[SecretFinding] = []
    seen: set[tuple[str, str, str, str, int | None]] = set()

    def record(alias: str, sha: str, path: str, detector: str, line: int | None) -> None:
        key = (alias, sha, path, detector, line)
        if key not in seen:
            seen.add(key)
            findings.append(SecretFinding(alias, sha, path, detector, line))

    for repository in payload.repositories:
        for commit in repository.commits:
            message = f"{commit.subject}\n{commit.body}"
            for detector in sorted(_scan_line(message)):
                record(repository.alias, commit.sha, COMMIT_MESSAGE, detector, None)

            for changed in commit.files:
                for number, line in enumerate(changed.diff.splitlines(), start=1):
                    for detector in sorted(_scan_line(line)):
                        record(
                            repository.alias, commit.sha, changed.path, detector, number
                        )

    return tuple(findings)


def describe(
    payload: ProviderPayload,
    findings: tuple[SecretFinding, ...],
    *,
    sent: bool,
    accepted: bool = False,
    accepted_at: str | None = None,
) -> list[str]:
    """Render the credential-scan section, which always appears.

    A scan nobody can see is not a control. The clean case is stated too,
    including what the scan does not cover — a silent pass would be read as
    proof, which it is not.
    """
    examined = sum(len(c.files) for r in payload.repositories for c in r.commits)
    messages = payload.commit_count
    lines = ["## Credential scan", ""]

    if not findings:
        lines += [
            f"No credential-shaped strings were found in {examined} file diff(s) and "
            f"{messages} commit message(s). The scan recognises known credential "
            "formats only, so this is not proof that none are present.",
            "",
        ]
        return lines

    if accepted:
        when = f" on {accepted_at}" if accepted_at else ""
        lines += [
            f"{len(findings)} possible credential(s) found, and **accepted by a "
            f"human**{when} via `--accept-scan-findings`. The payload was sent with "
            "them present. Provenance: `human_decision`.",
            "",
        ]
    elif sent:  # pragma: no cover - the gate refuses before this is reachable
        lines += [f"{len(findings)} possible credential(s) found.", ""]
    else:
        lines += [
            f"{len(findings)} possible credential(s) found. Nothing was sent — no AI "
            "provider is configured — so none of this left the machine.",
            "",
        ]

    lines += ["The matched text is deliberately not recorded. Where to look:", ""]
    lines += [f"- {finding.describe()}" for finding in findings]
    lines.append("")
    return lines


def refusal_message(findings: tuple[SecretFinding, ...]) -> str:
    """The error text when a payload is refused."""
    locations = "\n".join(f"  - {finding.describe()}" for finding in findings)
    return (
        f"refusing to send evidence to an AI provider: {len(findings)} possible "
        f"credential(s) found.\n{locations}\n"
        "The matched text is not recorded, on purpose. Remove the credential and "
        "rotate it, or re-run with --accept-scan-findings to send anyway — which is "
        "recorded in the document as a human decision."
    )
