# Decision log

Append-only. Newest first. Never rewrite a decision — supersede it with a new entry that references
the old one.

Format: `## D-NNN · YYYY-MM-DD · Title` → **Decision**, **Context**, **Consequences**, and
**Status** (`accepted` / `superseded by D-NNN`).

---

## D-024 · 2026-11-09 · Excerpt budget is shared fairly, not spent first-come

**Decision.** The total line budget is allocated across changed files *before* any text is kept,
smallest need first: each file is offered an equal share of what remains, takes only what it needs,
and the surplus is redistributed. Files are never served in path order.

**Context.** The first implementation spent the budget as it walked the sorted change list. Run
against a Subject B release range it produced the obvious failure: a generated lockfile sorts
early, took its full 400-line allowance out of a 4000-line budget, and files later in the alphabet
received **nothing**. Which evidence a reviewer saw depended on filename ordering.

For a governance tool that is indefensible. A file named `zzz_pricing_rules.java` would be silently
excerpt-free while a generated lockfile was quoted at length — and the report would look equally
confident either way.

**Consequences.**

- Measured on the same real range after the change: **49 of 50 files captured whole**, with only
  the lockfile truncated (393 of 3835 lines). The generated file absorbs the loss instead of
  imposing it on source files.
- Allocation requires reading every diff before keeping any of it, so the whole range is held in
  memory briefly. Acceptable at this scale (7442 lines is well under a megabyte); revisit if a range
  ever approaches repository size.
- Ties break on path, so allocation is deterministic and does not depend on dictionary ordering.
- A test asserts that two equally-sized files get shares within one line of each other, and another
  asserts a small file survives alongside a 2000-line sibling. Both would fail under first-come.
- This is **not** classification. Constat is not deciding that lockfiles matter less — it has no
  opinion about any file. Fair sharing simply removes an arbitrary bias. Treating generated files
  differently on purpose would be CON-08's business, and would need evidence.

**Status.** accepted

---

## D-023 · 2026-11-09 · Evidence is bounded by measured limits, and every omission is stated

**Decision.** Diff excerpts are capped at **400 lines per file** and **4000 lines per comparison**.
Every excerpt records its true total line count, whether it was truncated, how many lines were
omitted and why. Every excerpt — including a fully omitted one — carries a source pointer and the
exact `git` command that regenerates it in full.

**Context.** D-005 required bounded evidence but named no numbers. These were measured against the
subject repositories on 2026-11-08 rather than invented:

| Range | Files | Diff lines | Largest file |
| --- | --- | --- | --- |
| Subject A, a build-tag range | 29 | 2255 | 345 |
| Subject B, a release range | 50 | 7442 | 3835 (a generated lockfile) |

A 400-line per-file cap captures essentially all genuine source changes in both ranges while
containing the generated lockfile. The per-file and total caps are separate precisely because one
pathological file should not be able to consume a whole range's budget.

**Consequences.**

- **Truncation is only safe because the original stays reachable.** The recorded command is tested
  by actually running it and confirming it returns content the excerpt does not contain. Without
  that, bounding would violate "evidence is inspectable" (product rule 2).
- **A file is never dropped from the record.** Running out of budget removes an excerpt's *text*,
  never its entry — omitting the file would under-report the change itself.
- `EvidenceBundle.is_complete` and `completeness_note()` exist so a report can never imply
  completeness it does not have. CON-09 must surface the note.
- Binary files are recorded as binary with no excerpt and a zero line count, rather than being given
  a fabricated textual diff.
- Author and committer are both captured and never collapsed: a rebase or cherry-pick rewrites the
  committer while preserving the author, so merging them would misattribute work.
- **Privacy note for later:** evidence includes author and committer email addresses. That is fine
  locally, but when the optional AI provider arrives (D-003), sending commit metadata to a third
  party means sending personal data. PRODUCT_SPEC.md rule 7 applies and the question must be
  settled before any provider is wired up, not after.

**Status.** accepted

---

## D-022 · 2026-11-08 · State is read with `ls-tree`, not as a diff against the empty tree

**Decision.** `summarise_state` lists the files present at a revision using `ls-tree -r`, and
returns a `StateSummary` carrying plain paths. It does **not** diff against Git's empty tree, and it
shares no return type with `compare_revisions`.

**Context.** Diffing against the empty tree is the idiomatic trick for "everything at this
revision", and it was the plan recorded in CON-05's notes. It is wrong here: every file comes back
labelled `ADDED`. That is change vocabulary answering a state question, and D-016 exists precisely to
keep the two apart. A snapshot asserts "this is what is present", not "this was all just added" —
and a reviewer skimming a report full of `ADDED` would reasonably conclude the latter.

`ls-tree` also avoids needing the empty-tree hash, which differs between SHA-1 and SHA-256
repositories.

**Consequences.**

- `StateSummary` has `paths: tuple[str, ...]`, not `changes`. There is no `ChangeType` present to
  misread. A test asserts the absence of a `changes` attribute, so a future refactor cannot quietly
  merge the two shapes.
- The two renderers stay separate at CON-09, as that ticket's note already requires.
- Sharing the *evidence collector* between state and change at CON-06 is still fine; it is the
  vocabulary and the output type that must not be shared.

**Status.** accepted

---

## D-021 · 2026-11-08 · Comparison runs from the merge base, not between endpoints

**Decision.** `compare_revisions` computes `merge-base(base, target)` and diffs from there to
`target` — equivalent to `git diff base...target`. The merge base is stored on the summary and
always stated in output.

**Context.** `git diff base..target` compares two endpoints; the merge base asks what `target`
introduced since it diverged. The second is the question Constat exists to answer: a report
documenting a change should describe what the change *added*, not how two trees happen to differ.
Under endpoint comparison, work done only on `base` after the fork appears as a **deletion** in
`target` — a claim that is simply false, and one that would look exactly as confident as a true one.

**Consequences.**

- **The merge base must be reported.** The comparison does not necessarily start at `base`, and a
  reviewer cannot verify the summary without knowing where it did start. `base_is_merge_base`
  distinguishes the simple ancestor case from the diverged one, and the CLI says which applies.
- **A backwards range had to become an error** (`BackwardsRange`). If `target` is an ancestor of
  `base`, the merge base *is* `target`, so the diff is empty — "no changes" in answer to reversed
  arguments. That is the confidently-wrong-empty-report failure, so it is refused with a message
  naming the fix. This fired immediately on real data: a Subject A build-tag pair supplied in the
  wrong order was caught rather than reported as unchanged.
- `git log A..B` already has merge-base semantics for commit listing, so commit enumeration in
  CON-06 will agree with this without special handling. Note the asymmetry: `A...B` means
  merge-base-to-B for `diff` but *symmetric difference* for `log`. Use the explicit merge base
  rather than three-dot notation, so the two can never be confused.

**Evidence, stated precisely.** The semantics provably differ — a constructed test
(`test_endpoint_diff_would_have_differed`) shows the endpoint diff reporting a base-only file as a
deletion while the merge-base diff excludes it. On real data the difference has **not yet been
observed to change a report**: two adjacent Subject B release tags are on divergent lines (the
merge base is neither tag), yet both semantics yield identical results — 50 changed files with one
deletion either way. The decision rests on correctness of the question being asked, not on an
observed discrepancy in this repository.

**Status.** accepted

---

## D-020 · 2026-11-08 · An ambiguous revision is an error, not a precedence decision

**Decision.** When a revision name matches more than one ref — a branch and a tag of the same name —
Constat raises `AmbiguousRevision` rather than letting Git's precedence rules pick one. The caller
must qualify the name (`refs/heads/…`, `refs/tags/…`).

**Context.** Git resolves `collision` to the branch and prints a warning. Accepting that would mean
documenting one revision while the reviewer may have meant the other, and the report would look
exactly as confident either way. That is the failure product rule 1 exists to prevent, arriving on
the input path where it is cheapest to stop.

**Consequences.**

- `rev-parse` must **not** be passed `--quiet`: that flag suppresses the ambiguity warning, which is
  the only signal Git gives. Verified empirically — with `--quiet` the call exits 0 with empty
  stderr and the ambiguity is invisible.
- Detection depends on Git's warning text, so `LC_ALL=C` is set for every Git call to keep the
  message stable regardless of the user's locale.
- Not-found must be decided *before* ambiguity: Git's message for an unresolvable revision can also
  contain the word "ambiguous". A genuinely ambiguous name exits 0; an unknown one exits non-zero.
- A test pins this behaviour, so a future Git changing its wording fails loudly rather than silently
  disabling the check.

**Status.** accepted

---

## D-019 · 2026-11-08 · Revisions always resolve through `^{commit}`

**Decision.** Every revision is resolved with `rev-parse --verify --end-of-options <rev>^{commit}`,
and both the symbolic name and the full 40-character SHA are retained.

**Context.** An annotated tag names a *tag object*, not a commit. Resolving `v2.0.0` without
`^{commit}` yields the tag object's SHA, which would corrupt every later diff and every piece of
evidence anchored to it.

This is a bug the real subject repositories **cannot** catch: Subjects A and B both use lightweight
tags, where `rev-parse <tag>` and `rev-parse <tag>^{commit}` return the same SHA (verified
2026-11-08). The test fixture therefore creates one annotated and one lightweight tag on
purpose, and asserts the two SHAs differ before asserting which one is used.

**Consequences.**

- Keeping both forms is load-bearing, not redundant: the SHA is what evidence points at and what
  integrity depends on; the symbolic name is what a reviewer recognises. A report showing only SHAs
  would be correct and unreadable.
- `--end-of-options` (Git 2.24+) prevents a revision beginning with `-` being parsed as a flag.
- Test fixtures must not mirror only the subject repositories' conventions, or they inherit their
  blind spots.

**Status.** accepted

---

## D-018 · 2026-11-08 · `document` initialises a proposal; `review` stays the governance verb

**Decision.** The ticket-scoped command is **`constat document <ref>`**. The word **`review`** is
reserved for the human approval step (CON-12) and will not be used for anything else.

**Context.** The natural phrasing for "start documenting this ticket's changes" is *review the
ticket*, but `review` already carries a precise meaning here: a person examining a proposal and
approving, editing or rejecting it. Two meanings of *review* in one CLI is exactly the conflation
this product exists to prevent — and it would land on the governance surface, where clarity matters
most.

**Consequences.**

- `document` is the verb for initialising a proposal from a reference; `review` is the verb for
  deciding on one. A reader can tell which stage of the workflow a command belongs to from the verb
  alone.
- CON-12 keeps `review`, so no ticket needs renaming.
- The vocabulary is now a fixed, small set worth protecting: `snapshot` (state), `analyse` (change
  between revisions), `document` (change for a reference), `review` (human decision). A new command
  should reuse one of these or justify a genuinely new concept.

**Status.** accepted

---

## D-017 · 2026-11-08 · Work is tracked as `CON-NN` tickets in an in-repo backlog

**Decision.** Work is tracked in [BACKLOG.md](BACKLOG.md) as `CON-NN` tickets, versioned alongside
the code rather than in an external tracker. Sessions 01–20 are `CON-01`–`CON-20`, so session *N* is
always `CON-NN`. `CON-21` onwards is non-session work. Commits reference the ticket in the subject
and close it in a `Closes:` trailer.

**Context.** Correlating changes needed stable identifiers. GitHub Issues was the alternative and
would have given automatic cross-referencing plus a dogfooding story for CON-17/CON-18 — but an
in-repo register is versioned with the code, works offline, needs no credentials, and is readable in
a clone. For a project whose premise is durable, inspectable records, keeping the register in the
repository is the more consistent choice.

**Consequences.**

- **Tickets are not decisions.** A ticket is work that gets closed; a `D-NNN` entry is an immutable
  record of why. Closing a ticket never deletes or supersedes a decision. Both are referenced from
  the same commit when a ticket forces one.
- The register must be updated in the same commit as the work, or it drifts. Added to the
  end-of-session checklist in `CLAUDE.md`.
- No automatic cross-referencing: a reader must grep for `CON-NN` rather than following a link. An
  acceptable cost at this size; revisit if collaborators arrive.
- `CON-21`–`CON-28` capture the legal, commercial and validation work that no session forces. Two
  are already overdue — the domain is unregistered and no discovery conversations have been held.
  Making them tickets is the point: they are the items most easily avoided in favour of code.

**Status.** accepted

---

## D-016 · 2026-11-08 · Constat documents state as well as change

**Decision.** Constat produces two kinds of document, via two commands:

| Command | Question | Unit |
| --- | --- | --- |
| `analyse --repo --base --target` | What changed between two revisions? | closed range |
| `snapshot --repo --rev` | What does this revision do now? | open range |

This supersedes the implicit assumption in D-001 and PRODUCT_SPEC.md section 6 that the MVP only
ever compares two revisions.

**Context.** The specified MVP produced deltas only, which left a real hole:

- **The first baseline had nothing to diff against.** With delta-only analysis, the earliest
  approved record for a repository would describe a *change* rather than a *behaviour*, which is not
  what "approved product knowledge" should mean.
- **The product promise is present-tense** — "knowledge about how a product behaves" — and the two
  stated audiences ask what the system *does*, not only what moved last week.
- **Drift (D-012) presumes a documented present state** to measure approved claims against.

**Consequences.**

- **Q1 is generalised rather than ratified.** The unit of a change proposal is
  `(repository, revision_range)`, where a range is either *closed* (`base` → `target`) or *open* (a
  single revision). The earlier working assumption of `(repo, base_rev, target_rev)` was too narrow;
  it is good that it was never ratified. Q1 remains open pending Session 07.
- Reports must distinguish the two. A state description and a change description carry different
  claims, and conflating them would blur provenance — "this is how it behaves" is a different
  assertion from "this is what moved".
- `--rev` is required rather than defaulting to HEAD. A snapshot can become an approved baseline, so
  the revision must be stated by the reviewer, not inferred from whichever branch is checked out.
- `--rev` is not restricted to a branch name: a tag or SHA is equally valid, and not every release
  stream has a branch called `main` (product rule 6).
- Snapshot plumbing can share the evidence collector with analyse — in Git terms a snapshot is a
  diff against the empty tree — but the *reports* must stay separate documents. Sharing the renderer
  would be a false economy.
- PRODUCT_SPEC.md section 6 is updated accordingly. ARCHITECTURE.md section 4's data model needs the
  open-range case at Session 07.

**Status.** accepted

---

## D-015 · 2026-11-08 · argparse, and zero runtime dependencies for now

**Decision.** The CLI uses stdlib `argparse` rather than `click`. The package declares **no runtime
dependencies**; `pytest` is the only dev dependency. Build backend is setuptools, version derived
from `constat.__version__` so metadata cannot drift.

**Context.** ARCHITECTURE.md section 1 left the choice open ("click/argparse"). The roadmap says to
keep the first version deliberately boring, and CLAUDE.md forbids a new runtime dependency without
a stated reason. For `--version` and `--help`, argparse is entirely adequate, and argparse handles
subcommands fine when Session 03 needs them.

Pydantic is still the intended choice for data validation (D-002) and will be added in Session 07
when there are models to validate — not before.

**Consequences.**

- `pip install constat` pulls nothing else, which keeps the security-review surface minimal for an
  enterprise pilot. That matters more for this product than CLI ergonomics do.
- The deterministic evidence path demonstrably cannot depend on an AI provider (D-003), because
  there is nothing in `dependencies` at all.
- Revisit if Session 03's revision/option handling becomes unwieldy. Switching to click later is a
  contained change, because `cli.py` is thin by design and `build_parser()` is isolated from
  `main()`.
- Development on NixOS has no system pip; a venv with `ensurepip` supplies one. Recorded in the
  README so a new contributor is not stuck.

**Status.** accepted

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
  Subject A's commit volume, drift without these flags fires on everything and the feature becomes
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

| Signal | Where it lives in Subject A | Why it is rule-bearing |
| --- | --- | --- |
| Liquibase migrations | numbered changelog directories in the backend module (74 tracked, ordered, named) | A schema/data migration is almost always a rule or constraint change, and the directory name states the intent. |
| Feature flags | config registered as flags per the project's own ADR-0001 | A flag *is* a business rule toggle. |
| Bean validation | `javax.validation` / hibernate-validator annotations in the model module | Declarative constraints: `@NotNull`, `@Size`, `@Pattern` are rules in machine-readable form. |

Classification (Session 08) targets these three first. Everything else is `unknown` until a human
says otherwise. This is a narrower and more defensible MVP than "explain the diff".

**Status.** accepted

---

## D-009 · 2026-11-08 · Sample subjects are two private repositories, aliased A and B

**Decision.** The primary test subjects are two private repositories belonging to the author,
referred to throughout as:

| Alias | What it is | Scale | Tagging |
| --- | --- | --- | --- |
| **Subject A** | Java/Gradle backend, four modules | 1130 commits, 777 tags | machine-generated build tags, one per build |
| **Subject B** | Mobile application | 444 commits, 11 tags | semver release tags |

The Session 19 cross-repo scenario uses this pair. They are **private**, so they are named only in
a gitignored `SUBJECTS.local.md`; this public repository carries the measurements and properties
the decisions rest on, but not the identities.

**Context.** Resolves open question Q8. The roadmap asks for a small project we own and can safely
analyse. These are owned, local, actively developed, and — critically — the owner knows them well
enough to judge whether Constat's output is *accurate*, which is what prototype validation
requires.

**Consequences.**

- **The two repos version incompatibly.** Subject A uses machine-generated build tags (date plus
  hash, one per build); Subject B uses semver release tags.
  There is no shared version space. This is a gift rather than a problem: it forces product rule 6
  ("release streams are distinct") to be honoured from the start instead of being discovered late.
- **Constat must distinguish release tags from build tags** or drown in 777 of them. Tag selection
  needs to be a deliberate feature, not an afterthought — revisit at Session 04 (revision
  resolution).
- Subject A carries an in-repo architecture decision log. That is a real source for the
  `requirement_ref` provenance type, which anchors Session 18 traceability in something that already
  exists rather than something hypothetical.
- Analysis must respect `.gitignore`: Subject A's build-output directories contain generated
  artefacts and are correctly untracked. Evidence collection reads tracked files only.

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
- **Release tag vs build tag discrimination** — surfaced by D-009: Subject A carries 777
  machine-generated build tags. Revision resolution must not treat them as release points. Needed
  by Session 04.
- **Copyright holder: individual or company** — see D-011 consequences.
