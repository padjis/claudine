# Decision log

Append-only. Newest first. Never rewrite a decision — supersede it with a new entry that references
the old one.

Format: `## D-NNN · YYYY-MM-DD · Title` → **Decision**, **Context**, **Consequences**, and
**Status** (`accepted` / `superseded by D-NNN`).

---

## D-014 · 2026-11-08 · The project website is tryconstat.com

**Decision.** The web presence is **`tryconstat.com`**. Confirmed unregistered on 2026-11-08
(NXDOMAIN on both NS and SOA lookups).

**Context.** Closes the domain open item from D-013. Every primary TLD for the bare name was gone:
`constat.com` sits with a legacy Network Solutions owner, `constat.dev` and `constat.fr` are live,
and `constat.ai` and `constat.io` are held on aftermarket nameservers — `constat.ai` redirects to a
GoDaddy for-sale page, so it is purchasable at an unknown price. Paying aftermarket rates before any
user validation would contradict the roadmap's own guiding principle.

**Consequences.**

- **`constat.ai` remains the upgrade path.** It is listed for sale rather than in use. If validation
  succeeds and a brand budget exists, it is the domain to buy. Worth re-checking periodically; a
  listed domain can be withdrawn or bought by someone else.
- A `try<name>.com` form reads as a product landing page, which suits the pilot-recruitment phase
  the roadmap schedules for weeks 3–8. It reads less well as a long-term corporate identity.
- `getconstat.com` and `constathq.com` are already taken, so the two next-most-obvious prefix
  patterns are unavailable. If `tryconstat.com` is ever abandoned, the fallback is a different TLD,
  not a different prefix.
- Nothing is deployed to it yet, and nothing should be: there is no product to show. Registering it
  now is about securing the name, not launching.

**Status.** accepted

---

## D-013 · 2026-11-08 · The product is named Constat

**Decision.** The working name "Claudine" was rejected and the product is renamed **Constat**. The
GitHub repository is `padjis/constat`. Done before the initial commit, so no public history or
external reference needed rewriting.

**Context.** Resolves the escalated name blocker. Preliminary research found that "Claudine"
conflicted with Anthropic's registered CLAUDE mark (US #7645254) in the same class of goods and
services, with an enforcement precedent from 2026-01-27 against *Clawdbot* — a weaker, merely
phonetic resemblance. "Claudine" contains the literal string `Claud` and parses as *Claude* plus the
French diminutive `-ine`, which is a textbook formative mark. Full analysis in
[BRAND_NAME_REVIEW.md](BRAND_NAME_REVIEW.md).

Under D-011 the trademark is the primary defensible asset, because Apache-2.0 makes the code
forkable. Building that asset on a name that might have to be surrendered inverted the whole
strategy.

**Why Constat specifically.** In French law a *constat* is a formal written statement of observed
fact; a `constat d'huissier` is admissible evidence. That is precisely what this product emits —
observed facts, formally recorded, attested by a named person, distinguishable from inference. The
name states the product thesis rather than gesturing at it, and it is institutional rather than
persona-flavoured, which suits a governance and audit buyer.

**Consequences.**

- **The name is not cleared.** No USPTO, EUIPO or INPI search has been run. See
  BRAND_NAME_REVIEW.md § 9 for the outstanding list. Do not print it on anything expensive yet.
- **No primary domain is available.** `constat.com`, `.ai`, `.dev` and `.io` were all registered as
  of 2026-11-08. A domain must be acquired before outbound discovery work. This is the one naming
  criterion the choice knowingly fails, traded against the strength of the semantic fit.
- **Jurisdictional asymmetry.** In France and before the EUIPO, `constat` applied to evidence
  software is suggestive of the goods and therefore a weaker mark; in the US and UK it is arbitrary
  and stronger. If the first customers are French or EU, this may argue for a distinctive composite
  rather than the bare noun. A question for counsel, not a reason to revisit now.
- The Python package is `constat/`; the CLI command name is settled at Session 02.

**Status.** accepted

---

## D-012 · 2026-11-08 · Drift is per-claim evidence staleness, not a correctness verdict

**Decision.** Resolves open question Q4. Documentation drift is defined as **"the evidence
supporting this claim has moved"**, evaluated per claim rather than per document, using the
evidence source pointers established in D-005. Three states:

| State | Meaning | How it is determined |
| --- | --- | --- |
| `current` | No commit since the baseline's target revision touched the cited evidence. | Deterministic |
| `unverified` | The cited evidence changed. The claim **may or may not** still hold. | Deterministic |
| `orphaned` | The cited path no longer exists. | Deterministic |

**Context.** The tempting definition — "the documentation is now wrong" — is one Constat cannot
support. Detecting that an approved description no longer matches current behaviour requires
semantic understanding, i.e. AI inference, which would make the headline governance feature the
least trustworthy thing in the product and break product rule 1 on exactly the surface where trust
matters most.

**Consequences.**

- **Drift is a signal, never a verdict.** Reports say "this claim's evidence has changed;
  re-verify", never "this claim is false". Non-negotiable; it is the difference between a reviewer
  trusting the tool and dismissing it.
- Fully deterministic, so it works with no AI provider configured and `unverified` counts are
  directly testable.
- It aggregates into a sentence a reviewer can act on: *"7 of 23 approved claims are unverified
  since baseline v4."*
- **Noise suppression is required, not optional.** Rename-following (`--follow`) and
  whitespace-insensitive comparison (`-w`) must be in from the start. Against a repository with
  237feed's commit volume, drift without these flags fires on everything and the feature becomes
  noise.
- **Known weakness, must be documented at Session 20:** a business rule changed in a file the
  baseline never cited produces *no* drift signal. Constat under-reports rather than over-reports.
  That is the correct direction to fail, but a pilot will find it and it must be disclosed rather
  than discovered.

**Status.** accepted

---

## D-011 · 2026-11-08 · Apache-2.0, with a DCO on all contributions

**Decision.** Resolves open question Q10. Constat is licensed under Apache License 2.0
(`LICENSE`, `NOTICE`). All contributions require a Developer Certificate of Origin sign-off
(`git commit -s`), documented in `CONTRIBUTING.md` with the DCO 1.1 text in `DCO`.

**Context.** Three factors decided it:

1. *Procurement survivability.* The roadmap has us asking pilot customers in weeks 6–8 what
   procurement and security checks apply. Apache-2.0 is on effectively every enterprise allowlist;
   AGPL is on many deny lists, and for a tool pointed at a customer's private source code an AGPL
   licence invites a legal discussion unrelated to the product.
2. *The patent grant.* MIT offers none. Apache-2.0's explicit grant is what an enterprise reviewer
   looks for and costs nothing to give.
3. *BUSL is premature.* Source-available non-compete licensing is the right tool when there is
   revenue to protect. At zero users it signals paranoia and still fails some allowlists. The real
   risk is obscurity, not cloning.

**Consequences.**

- **Relicensing freedom depends on the copyright position staying clear.** A future commercially
  licensed edition is only possible while contributions are traceable. Accepting a single outside
  pull request without a sign-off would permanently foreclose that option — hence the DCO is in
  place *before* the repository attracts contributors, not after.
- The DCO was chosen over a CLA deliberately: it preserves the same optionality with no paperwork
  and no signing ceremony, which is appropriate for a project with one contributor.
- The copyright holder is recorded as "Emmanuel Padjinou" in `LICENSE` and `NOTICE`. If the work
  should be held by a company rather than an individual, both files need updating before any
  outside contribution is accepted.

**Status.** accepted

---

## D-010 · 2026-11-08 · "Behaviour change" means business rule change

**Decision.** Constat's subject is **business rule change** — not any code change, and not all
externally observable behaviour. Refactors, dependency bumps, build changes, formatting and
infrastructure edits are reported as context but are not the thing Constat claims to explain.

**Context.** Resolves open question Q2. "Any code change" makes Constat a diff viewer; "externally
observable behaviour" still includes performance, UX and operational change that Constat has no
evidence for. Business rules are what product owners, business analysts and engineering leaders
actually argue about, which matches the stated audiences.

**Consequences — the hard part.** Business rules are *not* reliably detectable from a diff. A rule
living in a service-layer `if` statement is invisible to deterministic analysis. Inferring it would
violate product rule 1 (no unsupported certainty). So the MVP needs a deterministic spine of
rule-bearing evidence and must return `unknown` elsewhere.

In the chosen sample repository (D-009) that spine exists and is strong:

| Signal | Location in 237feed | Why it is rule-bearing |
| --- | --- | --- |
| Liquibase migrations | `backend/src/main/resources/db/NNNN_*/changelog.yml` (74 tracked, ordered, named) | A schema/data migration is almost always a rule or constraint change, and the directory name states the intent. |
| Feature flags | config registered as flags per the project's own ADR-0001 | A flag *is* a business rule toggle. |
| Bean validation | `javax.validation` / hibernate-validator annotations in `models` | Declarative constraints: `@NotNull`, `@Size`, `@Pattern` are rules in machine-readable form. |

Classification (Session 08) targets these three first. Everything else is `unknown` until a human
says otherwise. This is a narrower and more defensible MVP than "explain the diff".

**Status.** accepted

---

## D-009 · 2026-11-08 · Sample subject is the local 237feed repository family

**Decision.** The primary test subjects are the local `237feed` repositories, principally
`237feed` (Java/Gradle backend: `api`, `backend`, `commons`, `models` — 1130 commits, 777 tags) and
`237feed-app` (444 commits, 11 tags). The Session 19 cross-repo scenario uses this pair.

**Context.** Resolves open question Q8. The roadmap asks for a small project we own and can safely
analyse. These are owned, local, actively developed, and — critically — the owner knows them well
enough to judge whether Constat's output is *accurate*, which is what prototype validation
requires.

**Consequences.**

- **The two repos version incompatibly.** `237feed` uses machine-generated build tags
  (`v26113ec4` — date plus hash, one per build); `237feed-app` uses semver release tags (`v2.3.1`).
  There is no shared version space. This is a gift rather than a problem: it forces product rule 6
  ("release streams are distinct") to be honoured from the start instead of being discovered late.
- **Constat must distinguish release tags from build tags** or drown in 777 of them. Tag selection
  needs to be a deliberate feature, not an afterthought — revisit at Session 04 (revision
  resolution).
- `237feed` carries an ADR log at `docs/adr/`. That is a real, in-repo source for the
  `requirement_ref` provenance type, which anchors Session 18 traceability in something that already
  exists rather than something hypothetical.
- Analysis must respect `.gitignore`: `api/build/` and `backend/build/` contain generated artefacts
  and are correctly untracked. Evidence collection reads tracked files only.

**Status.** accepted

---

## D-008 · 2026-11-08 · Report and proposal schemas are versioned from day one

**Decision.** Every stored proposal and rendered report carries a `schema_version`. No backward
compatibility is promised before the MVP ships.

**Context.** Governance data is meant to survive; a stored baseline is useless if we cannot tell
which schema produced it. Versioning is cheap now and expensive to retrofit.

**Consequences.** One extra field everywhere. Migration logic is deferred until a real schema break
occurs.

**Status.** accepted

---

## D-007 · 2026-11-08 · Reviewer identity is asserted, not authenticated

**Decision.** The reviewer recorded on a decision comes from explicit CLI input or configuration, and
is stored as an *asserted* identity. No authentication in the MVP.

**Context.** Authentication is explicitly deferred. A solo-founder prototype has no identity
provider, but "approval is explicit" still requires knowing *who* approved.

**Consequences.** The audit trail is honest about its own weakness: it records a claim of identity,
not proof. This must be stated in the README limitations section (Session 20), because an enterprise
pilot will ask.

**Status.** accepted

---

## D-006 · 2026-11-08 · Baselines are append-only rows with a content hash, not a signed chain

**Decision.** Immutability is implemented as append-only versioned rows plus a content hash per
baseline version, linked to the previous version. No cryptographic signing.

**Context.** Resolves open question Q3. The product rule is "history is durable and traceable", not
"history is tamper-proof against a hostile local user". Signing solves a threat the MVP does not
have.

**Consequences.** A user with direct SQLite access could still edit history. Acceptable locally;
revisit if a pilot raises an audit requirement.

**Status.** accepted

---

## D-005 · 2026-11-08 · Evidence is bounded, but always re-derivable from Git

**Decision.** Diff excerpts are capped per file and per proposal. Every excerpt stores a source
pointer (`rev:path:line-range`) so the complete original can be re-read from Git on demand.

**Context.** Resolves open question Q7. "Diffs become too large or noisy" is a named risk, but
truncating evidence would violate "evidence is inspectable".

**Consequences.** Constat never becomes the sole copy of the evidence. Requires the repository to
remain available at review time — an accepted local-first constraint.

**Status.** accepted

---

## D-004 · 2026-11-08 · The structured proposal is the system of record; Markdown is a view

**Decision.** Reviewer edits apply to the structured proposal. The Markdown report is a rendered
projection and is never parsed back into the model.

**Context.** Resolves open question Q5. Round-tripping Markdown into structured data would lose
provenance, which is the one thing Constat cannot afford to lose.

**Consequences.** The review experience must be good enough to edit structure directly. Rendering is
a pure function and therefore easy to test.

**Status.** accepted

---

## D-003 · 2026-11-08 · AI is optional and isolated behind a provider interface

**Decision.** The deterministic evidence pipeline has no dependency on any AI provider. A null
provider is the default. All AI output is labelled `ai_interpretation`.

**Context.** Avoids recurring API costs before the workflow is validated, keeps the "no unsupported
certainty" rule structurally enforceable, and means the prototype works offline.

**Consequences.** A test asserts the full pipeline produces a valid report with zero
`ai_interpretation` claims when no provider is configured.

**Status.** accepted

---

## D-002 · 2026-11-08 · Python CLI, Git subprocess, Pydantic, SQLite, Markdown, pytest

**Decision.** Adopt the roadmap's technology table unchanged for the first version.

**Context.** The goal is to validate the product workflow, not the infrastructure. These choices are
fast to build, easy to test and need no running services.

**Consequences.** Shelling out to `git` means depending on a `git` binary and parsing its output —
accepted, because reimplementing Git internals is strictly worse. No web UI, so the first users must
be comfortable with a terminal.

**Status.** accepted

---

## D-001 · 2026-11-08 · Local-first, single-repository MVP; defer the platform

**Decision.** The first release proves one complete workflow end to end — select, analyse, propose,
review, baseline, compare — locally, against one Git repository. Dashboard, SaaS, auth, billing,
Kubernetes, Kafka, graph database, multi-agent orchestration and automatic approval are all
deferred.

**Context.** The roadmap's guiding principle: build a small, trustworthy change-governance workflow
first and prove teams value it before investing in a platform. "Overbuilding before validation" is a
named top risk.

**Consequences.** Cross-repository value — the actual differentiator — is only demonstrated at
Session 19, via a scenario spanning two repositories or simulated linked PRs. That demo is therefore
a milestone, not an afterthought.

**Status.** accepted

---

## Open items (not yet decided)

- **Trademark clearance for "Constat"** — the name is chosen (D-013) but **not cleared**. No USPTO,
  EUIPO or INPI search has been run. Needed before the first pilot conversation. See
  [BRAND_NAME_REVIEW.md](BRAND_NAME_REVIEW.md) § 9.
- **Register `tryconstat.com`** — chosen in D-014 and confirmed unregistered on 2026-11-08, but
  **not yet actually registered**. Do this before it is discussed publicly.
- **Unit of a change proposal** (spec Q1) — has a working assumption (one proposal per
  `(repository, base_rev, target_rev)`) but no ratifying decision. Needed by Session 07.
- **Release tag vs build tag discrimination** — surfaced by D-009: `237feed` carries 777
  machine-generated build tags. Revision resolution must not treat them as release points. Needed
  by Session 04.
- **Copyright holder: individual or company** — see D-011 consequences.
