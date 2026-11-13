# Constat

> Constat turns software changes into evidence-backed, human-approved knowledge about how a
> product behaves.

**Status: pre-MVP.** Phase 1 and 2 of the original roadmap are done; the project then moved to a workspace model (D-027 to D-030). The CLI reads a local Git repository, resolves
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
| [USAGE.md](USAGE.md) | How to run it: the loop, the MCP setup, exit codes, and what each refusal means. |
| [CLAUDE.md](CLAUDE.md) | Working agreement for AI-assisted sessions. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute, and the required DCO sign-off. |
| [LICENSING_STRATEGY.md](LICENSING_STRATEGY.md) | Why Apache-2.0 + DCO, and what it means for a future sale. |
| [BRAND_NAME_REVIEW.md](BRAND_NAME_REVIEW.md) | Trademark, domain and positioning review of the working name. |

## Getting started

Requires Python 3.11 or newer. One runtime dependency, Pydantic, for schema validation of
persisted records (D-026). Two optional extras: `mcp` for the agent surface, `ai` for a provider
Constat calls itself. Neither is needed for the evidence pipeline.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,mcp]"
.venv/bin/constat --version
```

Then the whole loop, with an agent doing the reading:

```bash
constat init
constat repo add ~/git/billing --name billing
constat ticket add 622            # gathers evidence across every registered repository
constat rule proposals 622        # what a reading proposed, awaiting your decision
constat rule accept 1 --by you    # the only thing that creates a rule
constat publish 622               # to the repository's wiki, through the credential gate
```

**[USAGE.md](USAGE.md) is the manual** — the three ways to have the evidence read, the MCP setup,
every exit code, and a table of what each refusal means. Start there.

Run the tests:

```bash
.venv/bin/python -m pytest
```

> **On NixOS** there is no system-wide `pip`. The `venv` above supplies one via `ensurepip`, so the
> commands work unchanged — just don't expect `pip install` to work outside the virtual environment.

`analyse` and `snapshot` also still exist. They predate the ticket workflow and are not part of it:
`analyse` reports file-level changes between two revisions from the merge base (D-021), `snapshot`
lists the files present at one revision using no change vocabulary (D-022). Both bound their diff
excerpts and state every omission with the `git` command that regenerates it in full (D-023, D-024).

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
