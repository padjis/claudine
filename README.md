# Constat

> Constat turns software changes into evidence-backed, human-approved knowledge about how a
> product behaves.

**Status: pre-MVP, 7 of 20 sessions done.** The CLI reads a local Git repository, resolves
revisions, and reports file changes, commits and bounded diff evidence. It does **not** yet
classify anything, produce a report, or support review and baselines — see
[BACKLOG.md](BACKLOG.md) for what exists and what does not.

## What problem this addresses

Software changes are scattered across commits, pull requests, tests, issues, APIs, schemas and
multiple repositories. Technical release notes rarely explain the *impact* in language that product
owners, business analysts and engineering leaders can all use. Documentation goes stale, and
AI-generated explanations can sound confident without being supported by evidence. Teams need a
reviewable record of proposed changes and a trustworthy history of what was actually approved.

## What makes Constat different

- **Product-level view** — connect changes across several repositories to one capability or business
  feature.
- **Evidence first** — distinguish code facts, test results, requirements, AI interpretations and
  human decisions.
- **Governed evolution** — approved baselines are immutable; new AI output is a *proposal* until a
  human reviews it.
- **Release awareness** — preserve parallel release streams and show how behaviour evolves over time.

## The MVP, in one sentence

A local Python CLI that compares two revisions of one Git repository, assembles inspectable
evidence, emits a structured change proposal, lets a human edit/approve/reject it, and stores the
approved result as an immutable versioned baseline.

The MVP workflow:

| Step | Name | What happens |
| ---- | ---- | ------------ |
| 1 | Select | Choose a local Git repository and either two revisions (what changed) or one (what it does now). |
| 2 | Analyse | Collect changed files, commits, diff evidence and references. |
| 3 | Propose | Produce a structured explanation of the possible behaviour change. |
| 4 | Review | A human edits, approves or rejects the proposal. |
| 5 | Baseline | Store the approved version without overwriting history. |
| 6 | Compare later | Show what changed since the previous approved baseline. |

## Explicitly out of scope for the MVP

Web dashboard, multi-tenant SaaS, authentication, billing, Kubernetes, Kafka, graph database,
multi-agent orchestration, automatic approval. These are added only when a validated user need
justifies them. See [ARCHITECTURE.md](ARCHITECTURE.md) § "After the MVP".

## Documents in this repository

| File | Purpose |
| ---- | ------- |
| [PRODUCT_SPEC.md](PRODUCT_SPEC.md) | What Constat is, the MVP scope, acceptance criteria, non-negotiable product rules, open questions. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The smallest architecture that supports the MVP, and the shape to grow into later. |
| [DECISIONS.md](DECISIONS.md) | Dated decision log. Why things are the way they are. |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Current state, the 20-session build roadmap, and the next single task. |
| [BACKLOG.md](BACKLOG.md) | Ticket register (`CON-NN`), including the non-code legal and validation work. |
| [CLAUDE.md](CLAUDE.md) | Working agreement for AI-assisted sessions. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute, and the required DCO sign-off. |
| [LICENSING_STRATEGY.md](LICENSING_STRATEGY.md) | Why Apache-2.0 + DCO, and what it means for a future sale. |
| [BRAND_NAME_REVIEW.md](BRAND_NAME_REVIEW.md) | Trademark, domain and positioning review of the working name. |

## Getting started

Requires Python 3.11 or newer. One runtime dependency, Pydantic, for schema validation of
persisted records (D-026).

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Then:

```bash
.venv/bin/constat --version
.venv/bin/constat                # prints help

# What changed between two revisions?
.venv/bin/constat analyse --repo /path/to/repo --base v1.0.0 --target v1.1.0

# What does this branch do now?
.venv/bin/constat snapshot --repo /path/to/repo --rev main
```

`analyse` reports file-level changes — added, modified, deleted, renamed with both paths. It
compares **from the merge base**, so work done only on `base` after the fork is excluded rather
than reported as a deletion (D-021), and the merge base is always stated so the result can be
verified. A range supplied backwards is refused rather than shown as "no changes".

`snapshot` lists the files present at a revision. It deliberately uses no change vocabulary: a
state description must not label everything `ADDED` (D-022).

Both commands collect evidence: commit metadata, and diff excerpts bounded at 400 lines per file
and 4000 per comparison (D-023). Every excerpt records its true size, any omission and the reason
for it, plus the exact `git` command that regenerates it in full — so bounding never makes Constat
the only copy of the evidence. The budget is shared fairly across files rather than spent in path
order, so a generated lockfile cannot starve a source file of its excerpt (D-024).

Add `--json` to either command for the structured proposal: a versioned, validated record carrying
the repository identity, the selection, commits, changes, evidence and a completeness statement.
Each run produces a new proposal ID, with a stable `selection_key` identifying the range — so
history stays append-only while lookup stays idempotent (D-025).

Nothing is classified yet. Every option is required: there are no defaults for inputs this
important, and `--repo` never falls back to the current directory.

Run the tests:

```bash
.venv/bin/python -m pytest
```

> **On NixOS** there is no system-wide `pip`. The `venv` above supplies one via `ensurepip`, so the
> commands work unchanged — just don't expect `pip install` to work outside the virtual environment.

Classification arrives in Session 08 and the first report in Session 09; see
[PROJECT_STATUS.md](PROJECT_STATUS.md) and [BACKLOG.md](BACKLOG.md).

## Naming

In French law a *constat* is a formal written statement of observed fact — a `constat d'huissier` is
admissible evidence. That is what this product emits: observed facts, formally recorded, attested by
a named person, kept distinguishable from inference.

The project was briefly called "Claudine"; it was renamed on 2026-11-08 over a trademark conflict
with Anthropic's registered CLAUDE mark, before any commit was published. The reasoning is in
[BRAND_NAME_REVIEW.md](BRAND_NAME_REVIEW.md) (decision D-013).

⚠️ **The name is chosen but not cleared.** No USPTO, EUIPO or INPI search has been performed, and no
primary domain has been acquired — `constat.com`, `.ai`, `.dev` and `.io` were all registered as of
2026-11-08. Both are tracked in [DECISIONS.md](DECISIONS.md) open items.

## Licence

[Apache License 2.0](LICENSE). Contributions require a Developer Certificate of Origin sign-off —
see [CONTRIBUTING.md](CONTRIBUTING.md).
