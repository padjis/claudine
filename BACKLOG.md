# Backlog

Ticket register. The single source of truth for *what work exists*; the single source of truth for
*what was decided* is [DECISIONS.md](DECISIONS.md), and for *where things stand* it is
[PROJECT_STATUS.md](PROJECT_STATUS.md).

## Conventions

- **ID format:** `CON-NN`. Stable and never reused, including for abandoned tickets.
- **`CON-01` … `CON-20` are the twenty roadmap sessions**, in order. Session *N* is always
  `CON-NN`, so no mapping table is needed.
- **`CON-21` onwards** is everything that is not a session: commercial, legal and validation work.
- **Commit messages** reference the ticket in the subject and close it in a trailer:

  ```
  Session 04: read a local Git repository (CON-04)

  ...body...

  Closes: CON-04
  Signed-off-by: ...
  ```

  Use `Refs: CON-04` for partial work and `Closes:` only when the done-when criterion is actually
  met.
- **Tickets are not decisions.** A ticket is work that gets closed; a `D-NNN` entry is an immutable
  record of why. A ticket may produce a decision, and the commit should mention both — but closing
  a ticket never deletes or supersedes anything.

**Status:** ✅ done · 🟡 in progress · ⬜ not started · 🔴 blocked

---

## Phase 1 — Foundation

| ID | Title | Done when | Status |
| --- | --- | --- | --- |
| CON-01 | Create the repository and working agreement | A documented empty project with clear scope and rules. | ✅ `b092b62` |
| CON-02 | Create the Python project skeleton | The CLI installs and runs locally; tests execute. | ✅ `68d2ffb` |
| CON-03 | Add configuration and input validation | Helpful errors; no silent defaults for important inputs. | ✅ `7458423` |
| CON-04 | Read a local Git repository | Tests cover valid, invalid and missing repositories/revisions. | ✅ `184fa0b` |

## Phase 2 — Evidence engine

| ID | Title | Done when | Status |
| --- | --- | --- | --- |
| CON-05 | Compare two revisions | A deterministic change summary for two revisions. | ✅ `6e3b07d` |
| CON-06 | Collect inspectable evidence | Evidence records can be traced back to Git. | ✅ `eb957b6` |
| CON-07 | Define the change data model | Stable, tested structured output. | ✅ `24d3746` — top-level object revised by D-029 |

## Phase 3 — Meaning and reporting

| ID | Title | Done when | Status |
| --- | --- | --- | --- |
| CON-08 | Classify changes conservatively | Classification never pretends to know business intent from a filename alone. | ⬜ unchanged, but now follows CON-31..34 |
| CON-09 | Generate the first report | A developer can understand the report without reading raw command output. | ⬜ |
| CON-10 | Separate facts from interpretation | Every claim has a provenance type; unsupported claims are visibly uncertain. | ⬜ |
| CON-11 | Strengthen quality with tests | The report remains safe and useful across realistic Git cases. | ⬜ |

## Phase 4 — Human governance and history

| ID | Title | Done when | Status |
| --- | --- | --- | --- |
| CON-12 | Implement review decisions | No proposal becomes official without an explicit human decision. | ⬜ |
| CON-13 | Persist proposals and decisions | A restart does not lose review history. | 🔁 **superseded by CON-31** — persistence is now a prerequisite, not Phase 4 |
| CON-14 | Create immutable approved baselines | A later approval creates a new version; previous content remains recoverable. | ⬜ |
| CON-15 | Compare against the last approved baseline | A reviewer can see what is new since the last approved state. | ⬜ |

## Phase 5 — GitHub and realistic demonstration

| ID | Title | Done when | Status |
| --- | --- | --- | --- |
| CON-16 | Read GitHub repository metadata | Constat can identify the GitHub repository and map it to its local clone. | ⬜ |
| CON-17 | Link pull requests to change proposals | A proposal can be traced to its originating PR. | ⬜ |
| CON-18 | Add traceability references | A reviewer can navigate from a proposal to its supporting artefacts. | ⬜ |
| CON-19 | Run a realistic multi-change scenario | A repeatable demo shows the product-level value, not just a Git diff. | ⬜ no longer the *first* cross-repo work — CON-32 makes the set primary |
| CON-20 | Package the MVP and document limits | A new person can run the demo and understand what Constat does and does not do. | ⬜ |

---

## Non-session work

Not optional, and not code. These are the items most likely to be skipped because no session
forces them.

| ID | Title | Done when | Status |
| --- | --- | --- | --- |
| CON-21 | Register `tryconstat.com` | The domain is owned. | 🔴 **not done** — chosen in D-014 and confirmed free, but unregistered and now named publicly. |
| CON-22 | Trademark knockout search on "Constat" | USPTO and EUIPO searched in Nice classes 9 and 42, plus an INPI/RCS check. | ⬜ before the first pilot conversation |
| CON-23 | Trademark attorney review | A finalist cleared, including the FR/EU descriptiveness question. | ⬜ before the first pilot conversation |
| CON-24 | Ratify the proposal unit (Q1) | A `D-NNN` entry fixes the unit of a proposal. | ✅ D-025 |
| CON-25 | Decide the copyright holder | `LICENSE` and `NOTICE` name the intended holder. | ⬜ before accepting any outside contribution |
| CON-26 | Hold 5–10 discovery conversations | Notes from 5–10 people who work across multiple repositories. | 🔴 **0 held** — the roadmap puts the first two on Day 7 |
| CON-27 | Secure one design partner | A safe, non-sensitive sample repository from someone other than us. | ⬜ weeks 3–5 |
| CON-28 | Obtain two pilot commitments | Two time-boxed pilots with named users and agreed success criteria. | ⬜ weeks 6–8 |

## New scope

| ID | Title | Done when | Status |
| --- | --- | --- | --- |
| CON-29 | Ticket-scoped documentation (`constat document <ref>`) | A proposal can be initialised from a reference found in commit messages, across one or more repositories. | 🔁 **promoted** — now the primary workflow, delivered by CON-33/34 |
| CON-30 | ~~Surface near-duplicate proposals~~ | — | ❌ **withdrawn.** The problem was an artefact of proposal-per-run; D-029's one-document-per-ticket model does not have it. |

## Workspace model (D-027, D-028, D-029)

Added 2026-11-09 after a direction change. These replace the single-repository, one-shot shape the
first seven sessions assumed. The Git and evidence layers are unaffected.

| ID | Title | Done when | Status |
| --- | --- | --- | --- |
| CON-31 | Workspace storage | A SQLite workspace persists across runs; schema versioned. | ✅ |
| CON-32 | Repository registry | Repositories can be added, listed and removed; local paths and remote URLs both work. | ✅ local paths; remote URLs are CON-35 |
| CON-33 | Tickets and documents | A ticket can be opened and owns exactly one living document. | ✅ |
| CON-34 | Operations against the set | An operation gathers evidence for a ticket across every registered repository, measured against mainline, and expands the document. | ⬜ **next** |
| CON-35 | Remote clone-and-cache | A remote URL is cloned into a local cache and read like any local repository; fetch time is recorded. | ⬜ |
| CON-36 | Default-branch resolution | Each repository's default branch is resolved and stored, never assumed to be `main`. | ✅ delivered with CON-32 |
| CON-37 | Merged-ticket semantics | A ticket whose work is already merged still produces a document rather than an empty one. | ✅ resolved by D-030; implementation lands with CON-34 |
| CON-38 | Cache staleness disclosure | Every document states when each repository's cache was last fetched. | ⬜ |

---

## Notes on specific tickets

### CON-37 — resolved by measurement, not by argument (D-030)

An integration-branch workflow was proposed as the answer. Checked against the real subjects it
did not hold: **every branch is zero commits ahead of mainline.** Subject A's `develop` is 0 ahead
and 1119 behind; its `feat/622-…` ticket branch is 0 ahead and 10 behind; Subject B has no
integration branch at all. Ticket 622's work is already in mainline, and the diff between
`merge-base(main, feat/622)` and the branch tip is **0 files**.

So branch divergence alone would have produced an empty document for a ticket whose work sits
plainly in history — and Constat would have been unable to document its own primary test data.

Resolved as D-030: mainline stays the reference point, but the target is a **commit set**
attributable to the ticket, resolved from a branch name encoding it, commit-message references, or
an explicit list. The branch-name signal (`feat/622-…`) is the better one where it exists:
unambiguous, and independent of commit-message discipline, which only ~5% of Subject A's commits
exercise.

### CON-33 — the expected window, and the three answers

D-031 narrowed the search: a ticket's work is expected to be **merged onto an integration or
release branch but not yet in mainline**. That makes the search space `--all --not <mainline>` —
bounded, and exactly the set a reviewer cares about — without needing an integration branch to be
configured. Neither subject could have shared one name anyway: Subject A has `develop` plus seven
release branches, Subject B has release branches and no `develop`.

Three outcomes, deliberately not collapsed into "found / not found":

| Status | Meaning |
| --- | --- |
| `pending` | Commits ahead of mainline. The expected case. |
| `landed` | Already in mainline. Not nothing — a different answer. |
| `not_found` | The reference matched no commits. Also not "changed nothing". |

**The real subjects cannot exercise `pending`** — every branch in both is zero ahead of mainline —
so the fixture builds that shape deliberately. Running `ticket add 622` against Subject A
correctly reports `landed`, which is honest rather than convenient.

Branch-name attribution proved its worth: ticket 700's commit in the fixture never mentions 700,
only the branch does. And token-boundary matching found a genuine body reference on real data —
`(#622)` inside a commit whose subject says nothing about the ticket — while refusing `6220` and
`1622`.

### CON-32 — two refusals worth keeping

**The default branch is resolved from `refs/remotes/origin/HEAD` or not at all.** It never falls
back to HEAD's symref, because HEAD is whichever branch is checked out *right now*: registering
while on a feature branch would make that branch the permanent reference point for every
comparison (D-028), wrong in a way nobody would notice. A repository created with `git init` has
no `origin/HEAD` — this one does not — so `--default-branch` must be stated. Verified: both
subjects resolve to `main` automatically; this repository is refused.

**Duplicates are detected by identity, not path.** The same project cloned to two directories is
one repository (D-025), and path comparison would miss it. The error names the existing alias and
the shared root commit.

### CON-31 — immutability is enforced by the database

Append-only history is a database trigger, not an application convention. `document_version`
rejects `UPDATE` and `DELETE` outright, so a future bug cannot quietly rewrite an approval by
forgetting to call the right helper. Tests assert the triggers actually fire — a trigger that does
not is worse than none, because it looks like protection.

Also enforced in schema rather than code: one document per ticket (`UNIQUE` on `ticket_id`), only
`approved`/`rejected` as decisions, and foreign keys on — SQLite leaves those off by default, so
referential integrity has to be requested on every connection.

### CON-31 — why persistence moved

It was CON-13, in Phase 4. A registry (CON-32) and an accumulating document (CON-33) both need
storage to exist at all, so it became a prerequisite. The integrity rules in ARCHITECTURE.md
section 5 apply from here on rather than later.

### CON-04 — done, and the tag problem turned out not to be due here

**Corrected during implementation.** This ticket was expected to force the build-tag-versus-release-
tag problem from D-009. It did not, and the reason matters: **nothing in Constat selects a revision
for the user.** Every option is required with no default (D-016), so there is no code path that
could pick a build tag. The problem arrives only when something auto-selects — "latest tag",
"default branch", "since last release".

So the obligation at this stage was *negative*: do not add that convenience. The adapter module
says so explicitly, and Subject A's 777 build tags and Subject B's 11 semver tags both resolve
correctly because the caller names them.

The tag classification question moves to whichever ticket first wants to auto-select. It is not
abandoned, just not yet real.

**What was actually hard here:**

- **Annotated tags** (D-019). Resolution must go through `^{commit}`, and neither subject repository
  can catch a resolver that forgets to, because both use lightweight tags where the two SHAs
  coincide. The fixture adds an annotated tag specifically to cover this.
- **Ambiguous refs** (D-020). `--quiet` hides the only warning Git gives, so it must not be passed.
- **Subdirectory widening.** `--repo some/subdir` resolves to the enclosing repository. Accepted for
  convenience, but both paths are kept and the CLI states which repository was actually read —
  otherwise scope widens silently, which is how a confidently wrong report happens.
- `branch` is read from HEAD's symref and never inferred. A bare mirror has one too (verified), and
  `main` is never assumed to be the default branch (product rule 6).

### CON-06 — done; the budget had an ordering bug worth remembering

Bounding evidence turned out to be the easy half. The hard half was *who gets the budget*: spending
it first-come let a generated lockfile take 400 of 4000 lines and starve every file later in the
alphabet. Evidence selection depending on filename ordering is not a performance detail, it is a
correctness problem for a governance tool (D-024).

Also surfaced here and deferred deliberately:

- **Privacy.** Evidence carries author and committer email addresses. Harmless locally; a disclosure
  the moment an AI provider is wired up (D-003). Must be settled before, not after — see D-023.
- **Copy detection stays off.** `-M` rename detection only; `-C` is more expensive and more
  ambiguous. Stated rather than defaulted into.
- **One `git diff` per file** rather than splitting a combined diff on `diff --git` boundaries.
  Slower, but a filename containing that string cannot corrupt the split.

### CON-07 — done; identity was the real question

The models were straightforward. The decision that mattered was **generated versus derived
identity** (D-025), and it is not obvious until you ask what happens on a re-run: a derived
identity would make a fresh re-analysis collide with an approved baseline for the same range.
Append-only history (product rule 5) requires a new identity per run, and a separate
`selection_key` recovers the idempotent lookup that derivation was wanted for.

Repository identity is the **root commit**, not the path or the remote. This project changed both
its name and its forge within two days of starting, which is as good an argument as any.

**New ticket arising:** re-running `analyse` ten times produces ten proposals. Correct, but the
store will fill with near-duplicates — needs surfacing once CON-13 lands. See CON-30.

### CON-09 — must not collapse state and change

A snapshot asserts "this is how it behaves"; an analysis asserts "this is what moved" (D-016).
Sharing the evidence collector is fine; sharing the renderer would blur provenance.

**Corrected at CON-05.** This note used to say a snapshot is "a diff against the empty tree". It is
not, and that framing was the problem: the empty-tree diff labels every file `ADDED`, which is
change vocabulary answering a state question. State is now read with `ls-tree` and returns plain
paths with no `ChangeType` at all (D-022).

### CON-19 — the differentiator, demonstrated late

Cross-repository value is the actual product thesis but is only shown here, at ticket 19 of 20
(D-001). Treat it as a milestone rather than a trailing task. Uses Subjects A and B, whose
incompatible version schemes force product rule 6 to be honoured properly.

### CON-29 — a third selector shape, and the cross-repo mechanism

Initialise a proposal from a reference appearing in commit messages, rather than from a revision
range. This is a genuinely different shape from the other two selectors:

| Selector | Question | Unit |
| --- | --- | --- |
| `analyse --base --target` | What changed between two revisions? | closed range |
| `snapshot --rev` | What does this revision do now? | state |
| `document <ref>` | What changed for this piece of work? | **commit set** — possibly non-contiguous, possibly spanning repositories |

**Why this matters more than it appears.** An explicit reference in a commit message is
*human-authored evidence of grouping*. That answers the risk recorded in PRODUCT_SPEC.md section 9
— "multi-repo linking is ambiguous → require explicit links or evidence" — with actual evidence
rather than inference from timestamps or filenames. It is the mechanism CON-19 was otherwise
missing.

It also probably settles Q1 / CON-24: the proposal unit is `(repository, selection)` where a
selection is a range, a state, or a commit set.

**The command is `document`, not `review`** (D-018). `review` is reserved for the human approval
step (CON-12); two meanings of *review* in one CLI is precisely the conflation this product cannot
afford.

**Measured on Subject A, 2026-11-08, across all 1130 commits:**

| Pattern | Count |
| --- | --- |
| `ADR-NNNN` | 21 |
| `plans/NNNN` | 13 |
| bare `#N` | 12 |
| JIRA-style `ABC-1` | 8 |
| `repo#issue` (cross-repo) | 3 |

Roughly **5% of commits carry any reference**, in four coexisting schemes. Two hard consequences:

1. **The pattern must be configurable.** Hardcoding `CON-NN` would make the feature work only on
   repositories that adopted our own convention, and fail on the primary test subject.
2. **It cannot be the primary entry point.** For comparison, 94 commits touch tracked migrations —
   the business-rule spine from D-010. Reference density is far below evidence density, so this is
   a precision tool for well-tracked work, not a replacement for range selection. A report built
   from it must say what fraction of the range it accounts for, or it will quietly under-report.

The three `repo#issue` references are real cross-repository links already present in history,
which gives CON-19 genuine evidence to work from rather than a simulated link.

### CON-26 — the one most likely to slip

The roadmap is explicit: *"Do not wait until the software is finished to discover whether anyone
needs it."* Every other ticket here is more comfortable to work on than this one. That is the
reason it has a ticket.
