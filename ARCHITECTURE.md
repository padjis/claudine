# Constat — Architecture

Version 0.1 · 2026-11-08 · **proposal, not yet implemented**

This document describes the *smallest* architecture that supports the MVP in
[PRODUCT_SPEC.md](PRODUCT_SPEC.md) § 6, and the shape to grow into afterwards. Keep the first
version deliberately boring: the goal is to validate the product workflow, not to demonstrate
infrastructure sophistication.

---

## 1. Technology choices

| Area | Start with | Why |
| --- | --- | --- |
| Language / interface | Python CLI | Fast to build, easy to test, suitable for Git analysis and structured data. |
| Git access | `git` command line via `subprocess` | Uses Git's mature capabilities; avoid implementing Git internals. |
| Data validation | Pydantic | Enforces a stable schema for evidence and proposals. |
| Persistence | SQLite | Simple local persistence without running a database service. |
| Reports | Markdown | Readable, portable, easy to commit to a repository. |
| Tests | pytest | Protects the evidence, approval and versioning rules. |
| AI | Provider interface; optional, later | Keep deterministic evidence collection separate from AI interpretation. Avoid recurring API costs in the first prototype. |

**Deferred:** web dashboard, multi-tenant SaaS, authentication, billing, Kubernetes, Kafka, graph
database, multi-agent workflows, automatic approval.

## 2. Layers

The central constraint: **deterministic evidence collection is independent of AI interpretation**,
and **nothing becomes official without a human decision**. The layering exists to make those two
rules structurally enforced rather than merely intended.

```
CLI  (click/argparse — thin: parse, validate, dispatch, render)
 │
 ├─ Git adapter          deterministic · read-only · subprocess
 ├─ Evidence engine      deterministic · bounded excerpts · source pointers
 ├─ Classification       deterministic · conservative · may return `unknown`
 ├─ Interpretation       OPTIONAL · AI provider interface · output is always `ai_interpretation`
 ├─ Proposal assembly    Pydantic models · every claim carries provenance
 ├─ Review / governance  human edit · approve · reject · rationale · reviewer · timestamp
 ├─ Baseline store       append-only · versioned · content-hashed · never mutated
 └─ Reporting            Markdown renderer · business view + technical evidence view
       │
       └─ SQLite (repositories, proposals, evidence refs, decisions, baselines)
```

### Dependency rule

Each layer may depend only on layers above it in that list. In particular:

- The Git adapter and evidence engine **never** import the interpretation layer. The evidence path
  must work with no AI provider configured.
- The interpretation layer **never** writes to the baseline store. Only a human decision produces a
  baseline.
- The reporting layer is a pure function of stored structure. Rendering must never discover new
  facts.

## 3. Proposed package layout

Created incrementally across sessions 02–20; not all of this exists at once.

```
constat/
  __init__.py
  cli.py              # entry point, command definitions
  config.py           # configuration + input validation (Session 03)
  git/
    adapter.py        # repository validation, revision resolution (Session 04)
    diff.py           # revision comparison, renames, deletions (Session 05)
  evidence/
    collector.py      # bounded evidence capture + source pointers (Session 06)
  models.py           # Pydantic: RevisionRange, Repository, Commit,
                      #   FileChange, EvidenceItem, Claim, ChangeProposal (Session 07)
  classify.py         # conservative categories, `unknown` allowed (Session 08)
  interpret/
    base.py           # AiProvider protocol (Session 10+)
    null.py           # default: produces no interpretations
  report/
    markdown.py       # renderer (Session 09, 10)
  store/
    schema.sql
    db.py             # SQLite persistence (Session 13)
    baselines.py      # immutable versioned baselines (Session 14)
  review.py           # edit / approve / reject (Session 12)
  github/
    metadata.py       # read-only repo metadata (Session 16)
    pulls.py          # PR linkage (Session 17)
tests/
  fixtures/           # generated throwaway Git repositories
```

## 4. Data model sketch

Subject to Session 07; recorded here so the shape is reviewable now.

- **Repository** — local path, resolved Git root, optional GitHub remote identity.
- **RevisionRange** — base revision, target revision, both resolved to full commit SHAs plus the
  symbolic name the user typed.
- **Commit** — SHA, author, committer, dates, message, parent SHAs (so merges are explicit).
- **FileChange** — path, previous path (renames), change type, line counts.
- **EvidenceItem** — provenance type, bounded excerpt, and a **source pointer** (`rev:path:lines`)
  that lets a reviewer re-derive the full original from Git.
- **Claim** — a single statement, its provenance type, and the evidence items supporting it. A claim
  with no supporting evidence must render as visibly uncertain.
- **ChangeProposal** — `schema_version`, stable identifier, repository, revision range, claims,
  classification, open questions for the reviewer, status (`proposed` / `approved` / `rejected`).
- **Decision** — reviewer identity (asserted, not authenticated), timestamp, action, rationale, the
  proposal content as decided.
- **Baseline** — append-only version row: proposal content at approval time, source revisions,
  content hash, previous baseline version. Never updated in place.

## 5. Integrity rules the tests must protect

These are the "key historical-integrity rules" in acceptance criterion 7. They are listed here so a
test exists for each.

1. Approving a proposal creates a **new** baseline version; no existing baseline row is modified or
   deleted.
2. Earlier baseline content remains byte-recoverable after any number of later approvals.
3. A rejection is persisted with its rationale and remains traceable; it does not vanish.
4. No proposal reaches `approved` without a recorded human decision.
5. Every claim in a stored proposal has exactly one provenance type.
6. With no AI provider configured, the pipeline still produces a valid report containing zero
   `ai_interpretation` claims.
7. Evidence source pointers resolve back to real Git objects.
8. Parallel release streams do not collapse: baselines are keyed such that two branches can each
   have their own approved history.

## 6. Security posture

- Read-only against Git and GitHub. No writes, no commits, no pushes, no PR comments in the MVP.
- Credentials come from the environment or an OS keychain — **never** from files in this repository.
  GitHub access starts with least-privilege, read-only scope on **one** repository.
- `.gitignore` must cover the local database, reports and any `.env`.
- No customer code, production secrets or personal data is sent to any tool or AI provider without
  checking applicable policies and permissions first.

## 7. After the MVP

Expand only when a pilot exposes a concrete need. The sensible future shape:

- **Connectors** — Git repositories, pull requests, issues, CI/test results, API specifications,
  schema registries.
- **Evidence and change engine** — deterministic extraction and normalisation, independent of the AI
  provider.
- **Product knowledge model** — capabilities, services, repositories, releases, change groups,
  traceability links.
- **Interpretation layer** — AI proposes impact and plain-language explanations, always tied to
  evidence and uncertainty.
- **Governance** — human review, approvals, rejection rationale, immutable baselines, audit history.
- **Interfaces** — CLI first; then GitHub integration, an API and possibly MCP; a dashboard only when
  users need one.
- **Deployment** — local-first for the prototype; evaluate hosted or self-hosted based on customer
  security needs.

### Expansion order

1. **Next:** GitHub App or GitHub Action, PR ingestion, multiple repositories, explicit change
   grouping.
2. **Then:** product capability model, service/API/event/schema relationships, release streams,
   richer traceability.
3. **Then:** team review workflows, roles, audit export, self-hosted deployment, organisation-level
   policies.
4. **Later:** hosted dashboard, integrations, advanced analytics, commercial plans, AI-provider
   options.
