# Constat — Product Specification

Version 0.1 · 2026-11-08 · derived from *Constat Step-by-Step Product Roadmap v1.0*

---

## 1. Ambition

Help teams understand, verify and govern how software behaviour changes across repositories and
releases.

Constat should eventually become a product-level software evolution intelligence and governance
platform: it explains **what changed**, **why it matters**, **what evidence supports the
explanation**, and **whether the proposed behavioural documentation has been approved by a human**.

**Guiding principle:** build a small, trustworthy change-governance workflow first. Prove that teams
value it before investing in a hosted platform, complex AI orchestration or enterprise
infrastructure.

## 2. The problem

- Software changes are spread across commits, pull requests, tests, issues, APIs, events, schemas and
  multiple repositories.
- Technical release notes rarely explain impact in language that product owners, business analysts
  and engineering leaders can all use.
- Documentation becomes stale, while AI-generated explanations can sound confident without being
  supported by evidence.
- Teams need a reviewable record of proposed changes and a trustworthy history of what was actually
  approved.

## 3. The product promise

> Constat turns software changes into evidence-backed, human-approved knowledge about how a product
> behaves.

## 4. Differentiators

| Differentiator | Meaning |
| --- | --- |
| Product-level view | Connect changes across several repositories to one capability or business feature. |
| Evidence first | Distinguish code facts, test results, requirements, AI interpretations and human decisions. |
| Governed evolution | Keep approved baselines immutable; treat new AI output as a proposal until reviewed. |
| Release awareness | Preserve parallel release streams; show how behaviour evolves over time. |

## 5. Audiences

Constat must serve two audiences without conflating them:

- **Business audience** (product owners, business analysts, engineering leaders) — needs a
  plain-language explanation of behaviour change and its impact.
- **Technical audience** (developers, architects, reviewers) — needs the underlying evidence,
  inspectable and traceable to source.

A single report should offer both views, clearly separated.

---

## 6. MVP scope

The MVP works **locally**, against a **registered set** of Git repositories (D-027). A remote is
registered by URL and cloned into a local cache; everything is then read with the same read-only
Git layer.

It must: register repositories → open a ticket → run operations that gather evidence across the
set → accumulate that into one living document per ticket → let a person edit and approve it →
freeze an immutable, versioned baseline.

**Every comparison is against the repository's default branch** (D-028), resolved per repository
and never assumed to be `main`. Two shapes of question remain:

| Shape | Question answered |
| --- | --- |
| **Change** | What does this work add that mainline does not have? |
| **State** | What does this revision contain now? |

Both are needed. A delta alone cannot describe a product: the first baseline for a repository has
nothing to diff against, the product promise is present-tense, and drift detection presumes a
documented present state to measure against.

A **ticket** owns exactly one document (D-029). Operations expand or edit the draft; approval
freezes a version. The draft carries no authority — only a frozen version is product knowledge.

### 6.1 In scope

- Local Git repository analysis via the `git` command line.
- Comparison of two revisions (commits or tags), including renames and deletions.
- Description of the state of a single revision, typically `main` or `master`.
- Deterministic evidence collection: commit IDs, authors, dates, messages, file paths, bounded diff
  excerpts.
- Conservative change classification (feature, bug fix, refactor, configuration, API/schema change,
  test-only, unknown).
- A Markdown report separating facts from interpretation.
- Human review: edit, approve, reject — with reviewer, timestamp and rationale captured.
- SQLite persistence of repositories, proposals, evidence references and decisions.
- Immutable, versioned approved baselines.
- Comparison against the last approved baseline, including documentation-drift signals.
- Read-only GitHub metadata and pull-request linkage (Phase 5).
- Optional traceability links to issues, requirements, tests, APIs or schemas **when supplied**.

### 6.2 Out of scope for the MVP

Web dashboard · multi-tenant SaaS · authentication · billing · Kubernetes · Kafka · graph database ·
multi-agent workflows · automatic approval · writing to GitHub · any required AI API call.

AI is behind a provider interface and is **optional**. The first prototype must produce a useful
report with no AI provider configured at all, to avoid recurring API costs before the workflow is
validated.

### 6.3 MVP acceptance criteria

Taken verbatim from the roadmap; these are the MVP's definition of done.

1. A user can point Constat at a valid local Git repository.
2. ~~A user can compare two commits or tags~~ **Amended 2026-11-09 (D-028):** a user can see
   changed files and commit metadata for work measured against the repository's default branch.
   Release-to-release comparison is no longer in scope; a release tag is normally an ancestor of
   mainline, so it has no mainline framing.
3. The report links each important claim to inspectable evidence, or clearly labels it as an
   inference.
4. The proposal is structured and understandable to both a developer and a business stakeholder.
5. A human can edit, approve or reject a proposal.
6. An approved baseline is stored with its source revisions and decision metadata; later work does
   not silently rewrite it.
7. Automated tests cover the main workflow and the key historical-integrity rules.

---

## 7. Product rules that must not be compromised

These are invariants. A change that breaks one of them is a defect, not a trade-off.

1. **No unsupported certainty.** AI must not turn a guess into a fact. `unknown` is an acceptable
   result.
2. **Evidence is inspectable.** Important claims point to source commits, files, diffs, tests or
   supplied requirements.
3. **Keep provenance.** Distinguish implementation evidence, test evidence, requirements, AI
   interpretation and human approval.
4. **Approval is explicit.** Generated content is a proposal, not official product knowledge.
5. **History is durable.** Approved baselines and rejection decisions remain available and
   traceable.
6. **Release streams are distinct.** Do not assume every branch or release follows one linear
   timeline.
7. **Security by design.** Start read-only, minimise permissions, never store credentials in project
   files.
8. **Useful for both audiences.** Offer a business explanation and a technical evidence view without
   conflating them.

### 7.1 Provenance taxonomy

Every claim in a report carries exactly one provenance type:

| Type | Meaning | Source of truth |
| --- | --- | --- |
| `observed_fact` | Directly read from the repository. | Git |
| `test_evidence` | Observed test result or test-file change. | Test run / Git |
| `requirement_ref` | A requirement or issue supplied by a human or integration. | External, supplied |
| `ai_interpretation` | Generated explanation or impact assessment. | AI provider |
| `assumption` | Stated inference not backed by evidence. | Constat logic |
| `unknown` | Constat could not determine this. | — |
| `human_decision` | A reviewer's edit, approval or rejection. | Reviewer |

## 8. What to measure

| Signal | What to learn | Early success evidence |
| --- | --- | --- |
| Time saved | Does the report reduce time spent understanding a release? | A pilot user says it materially shortens an actual review task. |
| Accuracy and trust | Can users distinguish supported facts from inference? | Reviewers verify claims and identify uncertainty without being misled. |
| Cross-repo value | Does linking repositories reveal useful product behaviour? | A real feature is understood across at least two components. |
| Governance fit | Does the approval/baseline history solve a real control problem? | A team wants to retain and reuse approved records. |
| Willingness to pay | Is there an owner and budget for this problem? | At least two serious pilot discussions or commitments. |

## 9. Risks

| Risk | Mitigation |
| --- | --- |
| Building a generic AI documentation tool | Anchor in cross-repository, product-level change understanding plus human governance. |
| Overbuilding before validation | Keep the first MVP local and narrow; interview users while building; seek pilot commitments. |
| AI hallucinations damage trust | Separate facts and inference, show evidence, expose uncertainty, require human approval. |
| Diffs become too large or noisy | Bound evidence size, summarise by change unit, let reviewers drill into source details. |
| Multi-repo linking is ambiguous | Require explicit links or evidence; let humans confirm capability relationships. |
| Security blocks adoption | Start read-only/local; learn data residency, access and deployment requirements during discovery. |
| No clear buyer or budget | Interview budget owners and test willingness to pay before building enterprise features. |

## 10. Validation track (runs in parallel with building)

Product validation does not wait for the software to be finished.

**Weeks 1–2 — discovery.** Speak with 5–10 people who work across multiple repositories (architects,
engineering managers, platform leads, product owners, business analysts). Ask them to describe the
last time a feature changed across services and how they understood its impact; how they keep
behavioural documentation accurate and who approves it; what happens when documentation and
implementation disagree; what evidence, audit trail or approval workflow they would need before
trusting a generated explanation. Avoid pitching too early. Look for repeated, expensive problems
and existing workarounds.

**Weeks 3–5 — prototype validation.** Find one design partner with a safe, non-sensitive sample
repository. Demonstrate the same capability changing across more than one component. Ask what is
accurate, missing, misleading or valuable. Measure whether the report saves time versus their
current process. Record requests separately from the core product promise; do not implement every
suggestion.

**Weeks 6–8 — pilot commitment.** Offer a small, time-boxed pilot with clear scope, named users and
agreed success criteria. Seek **two** concrete pilot commitments before investing in a hosted
enterprise platform. Ask what budget owner would pay, what procurement/security checks apply, and
what must be true for renewal. If users like the idea but will not provide a repository, schedule a
pilot or introduce a buyer — revisit the problem and positioning.

---

## 11. Open questions and ambiguities

Recorded rather than guessed at. Each needs a decision before the session that depends on it.

| # | Question | Blocks | Current working assumption |
| --- | --- | --- | --- |
| ~~Q1~~ | ~~What is the unit of a proposal?~~ | Session 07 | **Resolved → D-025.** `(repository, selection)`, where a selection is a closed range, an open range, or a reserved commit set. Identity generated per run; `selection_key` derived. Cross-repository work is a group of proposals. |
| ~~Q2~~ | ~~Does "behaviour change" mean externally observable behaviour or any code change?~~ | Session 08 | **Resolved → D-010.** Business rule change. |
| Q3 | What exactly makes a baseline "immutable" — append-only rows, content hashing, or a signed chain? | Session 14 | Append-only versioned rows plus a content hash per baseline version. No cryptographic signing in the MVP. |
| ~~Q4~~ | ~~How is "documentation drift" defined and detected?~~ | Session 15 | **Resolved → D-012.** Per-claim evidence staleness: `current` / `unverified` / `orphaned`. A signal, never a verdict. |
| Q5 | Where do reviewer edits live — the Markdown report, a structured editor, or both? | Session 12 | Structured proposal is the system of record; Markdown is a rendered view. Review edits the structure. |
| Q6 | Who is the reviewer identity in a solo-founder MVP, and is it trusted input? | Session 12 | Reviewer identity comes from explicit CLI input / config, recorded as asserted (not authenticated). |
| Q7 | How are diff excerpts bounded without losing the evidence a reviewer needs? | Session 06 | Per-file and per-proposal byte/line caps, plus a stored pointer (`rev:path:line-range`) so the full original is always re-derivable from Git. |
| ~~Q8~~ | ~~Which sample repository is the primary test subject?~~ | Session 19 | **Resolved → D-009.** Two private repositories, aliased Subject A and Subject B. |
| Q9 | Is the report format stable enough to version, and do we promise compatibility? | Session 09 | Report schema is versioned from the start (`schema_version`); no compatibility promise before the MVP ships. |
| ~~Q10~~ | ~~What licence does this project use?~~ | Public release | **Resolved → D-011.** Apache-2.0, with a DCO sign-off on all contributions. |

All ten questions raised in Session 01 are now resolved. Resolved questions move to
[DECISIONS.md](DECISIONS.md); new ones are raised as `CON-` tickets in [BACKLOG.md](BACKLOG.md).
