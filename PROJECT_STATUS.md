# Project status

**Last updated:** 2026-11-08
**Current phase:** Phase 1 — Foundation
**Current session:** 01 — Create the repository and working agreement

---

## Where things stand

The repository exists and is public at `https://github.com/padjis/constat`. The remote is currently
empty — the documents below are the intended initial commit and have **not** been committed or
pushed.

No product code exists. This is intentional: Session 01 is scope and documentation only.

### Session 01 — done when: *a documented empty project with clear scope and rules*

| Item | Status |
| --- | --- |
| Git repository | ✅ initialised locally on `main`, `origin` configured |
| `README.md` | ✅ written |
| `CLAUDE.md` | ✅ written |
| `PRODUCT_SPEC.md` | ✅ written, including 10 open questions |
| `ARCHITECTURE.md` | ✅ written — proposal, nothing implemented |
| `DECISIONS.md` | ✅ written — D-001 … D-008 |
| `PROJECT_STATUS.md` | ✅ this file |
| `.gitignore` | ✅ written |
| `LICENSE` / `NOTICE` | ✅ Apache-2.0 — D-011 |
| `CONTRIBUTING.md` / `DCO` | ✅ DCO sign-off required — D-011 |
| Initial commit pushed | ⬜ **not done — awaiting explicit authorisation** |

### Tests run

None. There is no code yet, so there is nothing to test. This is the expected state at the end of
Session 01.

### Known issues / open items

- **Push is blocked on credentials.** The repository is public so it can be read anonymously, but
  pushing needs authentication. There is no `gh` CLI on this machine; the HTTPS remote prompts for a
  username and the SSH key at `~/.ssh/id_rsa` was rejected (`Permission denied (publickey)`). Either
  add that key to the GitHub account, install and authenticate `gh`, or configure a credential
  helper.
- **Name chosen but not cleared.** Renamed from "Claudine" to **Constat** on 2026-11-08 (D-013),
  before any commit was published. No USPTO/EUIPO/INPI search has been run. See
  `BRAND_NAME_REVIEW.md` § 9.
- **Website is `tryconstat.com`** (D-014) — chosen and confirmed unregistered, but **not yet
  registered**. `constat.ai` is listed for sale and is the upgrade path post-validation.
- **Q1 (unit of a change proposal) has a working assumption but no ratifying decision** — the last
  of the original ten still open. Needed by Session 07.
- **Tag selection is a known design problem**: `237feed` has 777 machine-generated build tags
  (`v26113ec4`), while `237feed-app` uses semver (`v2.3.1`). Revision resolution must distinguish
  release tags from build tags. Needed by Session 04.
- **Copyright holder** recorded as an individual in `LICENSE`/`NOTICE`; change before accepting any
  outside contribution if it should be a company.
- Q2, Q4, Q8 and Q10 are now resolved (D-010, D-012, D-009, D-011); the product name is resolved
  by D-013.

---

## Next single task

**Authorise the initial commit.** The name blocker is resolved (D-013), so nothing else stands in
the way of closing Session 01. Pushing still requires working credentials — see known issues.

Then begin **Session 02 — Create the Python project skeleton**.

Session 02 scope: package, CLI entry point, virtual environment, dependency management, pytest, and
a simple `version`/`--help` command.
**Done when:** the CLI installs and runs locally; tests execute.

Nothing beyond that. No Git reading, no configuration schema — those are Sessions 03 and 04.

---

## Build roadmap — 20 focused work sessions

At 1–2 hours per day, one independently testable outcome per session. This is a working sequence,
**not a deadline promise** — take longer when a milestone needs it.

### Phase 1 — Foundation (sessions 1–4)

| # | Session | Done when | Status |
| --- | --- | --- | --- |
| 01 | Create the repository and working agreement | A documented empty project with clear scope and rules. | 🟡 docs written, commit pending |
| 02 | Create the Python project skeleton | The CLI installs and runs locally; tests execute. | ⬜ |
| 03 | Add configuration and input validation | Helpful errors; no silent defaults for important inputs. | ⬜ |
| 04 | Read a local Git repository | Tests cover valid, invalid and missing repositories/revisions. | ⬜ |

### Phase 2 — Evidence engine (sessions 5–7)

| # | Session | Done when | Status |
| --- | --- | --- | --- |
| 05 | Compare two revisions | A deterministic change summary for two revisions. | ⬜ |
| 06 | Collect inspectable evidence | Evidence records can be traced back to Git. | ⬜ |
| 07 | Define the change data model | Stable, tested structured output. | ⬜ |

### Phase 3 — Meaning and reporting (sessions 8–11)

| # | Session | Done when | Status |
| --- | --- | --- | --- |
| 08 | Classify changes conservatively | Classification never pretends to know business intent from a filename alone. | ⬜ |
| 09 | Generate the first report | A developer can understand the report without reading raw command output. | ⬜ |
| 10 | Separate facts from interpretation | Every claim has a provenance type; unsupported claims are visibly uncertain. | ⬜ |
| 11 | Strengthen quality with tests | The report remains safe and useful across realistic Git cases. | ⬜ |

### Phase 4 — Human governance and history (sessions 12–15)

| # | Session | Done when | Status |
| --- | --- | --- | --- |
| 12 | Implement review decisions | No proposal becomes official without an explicit human decision. | ⬜ |
| 13 | Persist proposals and decisions | A restart does not lose review history. | ⬜ |
| 14 | Create immutable approved baselines | A later approval creates a new version; previous content remains recoverable. | ⬜ |
| 15 | Compare against the last approved baseline | A reviewer can see what is new since the last approved state. | ⬜ |

### Phase 5 — GitHub and realistic demonstration (sessions 16–20)

| # | Session | Done when | Status |
| --- | --- | --- | --- |
| 16 | Read GitHub repository metadata | Constat can identify the GitHub repository and map it to its local clone. | ⬜ |
| 17 | Link pull requests to change proposals | A proposal can be traced to its originating PR. | ⬜ |
| 18 | Add traceability references | A reviewer can navigate from a proposal to its supporting artefacts. | ⬜ |
| 19 | Run a realistic multi-change scenario | A repeatable demo shows the product-level value, not just a Git diff. | ⬜ |
| 20 | Package the MVP and document limits | A new person can run the demo and understand what Constat does and does not do. | ⬜ |

---

## First seven days

| Day | Task | Status |
| --- | --- | --- |
| 1 | Create an empty Git repository named `constat`. | ✅ |
| 2 | Add the project charter, product specification and working agreement. | ✅ |
| 3 | Have Claude Code review the documents, identify ambiguities and propose a small architecture. **Do not implement.** | ✅ 10 ambiguities recorded in `PRODUCT_SPEC.md` § 11; architecture proposed in `ARCHITECTURE.md` |
| 4 | Choose the first sample Git repository. Prefer a small project you own and can safely analyse. | ✅ local `237feed` + `237feed-app` — D-009 |
| 5 | Agree on the first CLI command and its acceptance criteria. | ⬜ **next decision needed** |
| 6 | Implement the CLI skeleton and tests. | ⬜ (= Session 02) |
| 7 | Review the result, update project status, conduct the first two discovery conversations. | ⬜ |

## Validation track

Running in parallel with building — see `PRODUCT_SPEC.md` § 10.

| Window | Goal | Status |
| --- | --- | --- |
| Weeks 1–2 | 5–10 discovery conversations | ⬜ 0 of 5–10 held |
| Weeks 3–5 | One design partner, prototype validation | ⬜ |
| Weeks 6–8 | Two pilot commitments | ⬜ |

**Reminder from the roadmap:** do not wait until the software is finished to discover whether anyone
needs it. The Day 7 task includes the first two discovery conversations — that is the real deadline
for starting this track.

---

## The first milestone

Not "build the platform". It is:

> Show one team a trustworthy, evidence-backed explanation of a real software change, let them
> approve it, and prove that the approved knowledge can be carried forward without losing history.
