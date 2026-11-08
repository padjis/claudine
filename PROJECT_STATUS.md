# Project status

**Last updated:** 2026-11-08
**Current phase:** Phase 1 — Foundation
**Current session:** 05 — Compare two revisions

---

## Where things stand

The repository is public at `https://github.com/padjis/constat`. Session 01 was committed and
pushed as `b092b62`.

`analyse` produces a deterministic file-level change summary; `snapshot` lists the files present at
a revision. No evidence is collected and nothing is classified — that is Sessions 06 and 08.

### Session 05 — done when: *a deterministic change summary for two revisions* ✅

| Item | Status |
| --- | --- |
| `constat/git/diff.py` — `compare_revisions`, `summarise_state` | ✅ |
| Merge-base comparison, merge base recorded and always stated (D-021) | ✅ |
| Renames keep both paths and the similarity score | ✅ |
| Deletions reported explicitly | ✅ |
| `ChangeType.UNKNOWN` for unrecognised status letters, never a guess | ✅ |
| `-z` parsing — paths with spaces, unicode and newlines survive | ✅ |
| Backwards range refused rather than reported as empty (`BackwardsRange`) | ✅ |
| Unrelated histories refused (`NoCommonAncestor`) | ✅ |
| Deterministic: explicit sort, identical output across runs | ✅ |
| State read with `ls-tree`, no change vocabulary (D-022) | ✅ |

### Tests run

```
.venv/bin/python -m pytest  →  114 passed
```

28 new tests. Merges, renames-with-edits, orphan branches, empty commits, awkward filenames and
read-only guarantees are all covered.

### Verified against real repositories

- `237feed` `v2611f845` → `v26113ec4`: 29 changed files, base is an ancestor of target.
- `237feed-app` `v2.3.0` → `v2.3.1`: 50 changed files, and the two tags have **diverged** — the
  merge base is neither tag.
- `237feed` `snapshot --rev main`: 628 files present.
- **The `BackwardsRange` guard fired on real data.** A `237feed` build-tag pair supplied in the
  wrong order was refused. Without it the output would have read "No file changes in this range",
  which is the confidently-wrong-empty-report failure this product exists to avoid.

### An honest limit on the D-021 evidence

The two diff semantics provably differ — a constructed test shows the endpoint diff reporting a
base-only file as a deletion. But on real data the difference has **not** yet been observed to
change a report: for `237feed-app` `v2.3.0`→`v2.3.1`, despite genuine divergence, both semantics
give identical results (50 files, 1 deletion). D-021 rests on asking the right question, not on an
observed discrepancy here.

### Session 04 — done when: *tests cover valid, invalid and missing repositories/revisions* ✅

| Item | Status |
| --- | --- |
| `constat/git/adapter.py` — read-only, shells out to `git` (D-002) | ✅ |
| `discover_repository()` — path, repository and branch | ✅ |
| `resolve_revision()` — symbolic name + full SHA retained (D-019) | ✅ |
| Distinct error types, separate from `InvalidInput` | ✅ `RepositoryError` and five subtypes |
| Repository failures exit **3**, malformed input still exits 2 | ✅ |
| Throwaway-repository fixtures; no dependency on `237feed` | ✅ `tests/conftest.py`, `tests/helpers.py` |
| Annotated tags resolve to the commit, not the tag object (D-019) | ✅ |
| Ambiguous revisions refused rather than guessed (D-020) | ✅ |
| Bare repositories, detached HEAD, unborn HEAD, subdirectories | ✅ |
| Read-only proven, not asserted | ✅ tests compare `status`/`HEAD`/`show-ref` before and after |

### Tests run

```
.venv/bin/python -m pytest  →  86 passed in 2.36s
```

38 new tests. Verified against both real repositories, including their incompatible tag schemes:
`237feed` build tags (`v26113ec4`) and `237feed-app` semver (`v2.3.1`) both resolve.

### Correction to an earlier claim

I had said the 777-build-tag problem would come due at Session 04. It did not. Nothing in Constat
selects a revision for the user — every option is required with no default — so no code path can
pick a build tag. The obligation here was *negative*: do not add "latest tag" convenience. Tag
classification moves to whichever ticket first wants to auto-select. See `BACKLOG.md`, CON-04.

### Session 03 — done when: *helpful errors; no silent defaults for important inputs* ✅

| Item | Status |
| --- | --- |
| `analyse --repo --base --target`, all required | ✅ |
| `snapshot --repo --rev`, all required (D-016) | ✅ |
| `constat/config.py` — `AnalysisRequest`, `SnapshotRequest`, frozen dataclasses | ✅ |
| `constat/errors.py` — `ConstatError`, `InvalidInput` | ✅ |
| No default for `--repo` — never analyses the current directory implicitly | ✅ |
| No default for `--rev` — a baseline's revision must be stated, not inferred | ✅ |
| Whitespace reported rather than silently stripped | ✅ |
| Self-comparison (`--base` == `--target`) rejected with the value named | ✅ |
| Invalid input exits 2 with a message on stderr and nothing on stdout | ✅ |

**Scope boundary held:** Session 03 validates the *shape* of input only. Whether the path exists, is
a Git repository, or the revisions resolve, is Session 04. A test asserts a nonexistent path is
*not* rejected here, so "you typed it wrong" and "your repository is broken" stay distinguishable.

### Tests run

```
.venv/bin/python -m pytest  →  48 passed in 0.30s
```

26 new tests across `tests/test_config.py` and `tests/test_cli.py`. Every rejection path asserts on
the **message**, not just the exit code — "fail clearly" is the acceptance criterion, so a correct
code with an unhelpful message would be a failure.

### Verified by hand

```
$ constat snapshot --repo ~/git/237feed --rev main        → input accepted, nothing read
$ constat analyse --repo ~/git/237feed \
    --base v26113ec4 --target v2611f845                   → input accepted, nothing read
$ constat analyse --base a --target b                     → error: --repo required  (exit 2)
$ constat analyse --repo ~/git/237feed \
    --base main --target main                             → error: nothing to compare (exit 2)
```

---

### Session 02 — done when: *the CLI installs and runs locally; tests execute* ✅

| Item | Status |
| --- | --- |
| `pyproject.toml` — setuptools, Python ≥ 3.11, Apache-2.0 metadata | ✅ |
| `constat/` package with `__version__` as single source of truth | ✅ |
| `constat/cli.py` — argparse, `--version` / `--help` (D-015) | ✅ |
| `constat/__main__.py` — `python -m constat` works pre-install | ✅ |
| `constat` console script entry point | ✅ verified running from the venv |
| Virtual environment + dependency management | ✅ `.venv`, editable install with `[dev]` extra |
| pytest configured and running | ✅ 8 tests, all passing |
| Zero runtime dependencies | ✅ `dependencies = []` |

### Tests run

```
.venv/bin/python -m pytest  →  8 passed in 0.21s
```

Covered: `--version` exit code and output; `--help`; bare invocation printing help rather than
failing silently; unknown flag exiting 2 with a usage error; parser constructible in isolation;
`python -m constat`; and the installed console script actually executing.

The version-drift test was **mutation-checked** — setting `__version__` to a wrong value was
confirmed to fail it, so it is not passing trivially.

### Verified by hand

```
$ constat --version        → constat 0.0.1
$ constat                  → usage + description + "no analysis commands exist yet"
$ python -m constat --version → constat 0.0.1
$ constat --nope           → error: unrecognized arguments: --nope   (exit 2)
```

---

### Session 01 — done when: *a documented empty project with clear scope and rules* ✅

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
| Initial commit pushed | ✅ `b092b62`, signed off, pushed to `origin/main` |

---

### Known issues / open items

- **`.venv/` is gitignored and must be recreated per clone** — see the README. On NixOS there is no
  system pip; `python3 -m venv` supplies one via `ensurepip`.
- **SSH to GitHub does not work from this machine.** The key at `~/.ssh/id_rsa` is 2048-bit RSA,
  which GitHub now rejects as too short. Pushing uses HTTPS with a stored credential instead. If SSH
  is ever wanted, generate an ed25519 key.
- **Name chosen but not cleared.** Renamed from "Claudine" to **Constat** on 2026-11-08 (D-013),
  before any commit was published. No USPTO/EUIPO/INPI search has been run. See
  `BRAND_NAME_REVIEW.md` § 9.
- **Website is `tryconstat.com`** (D-014) — chosen and confirmed unregistered, but **not yet
  registered**. `constat.ai` is listed for sale and is the upgrade path post-validation.
- **Q1 (unit of a proposal) was widened by D-016 and remains open.** The unit is
  `(repository, revision_range)` where a range is closed (`base`→`target`) or open (single
  revision). The earlier `(repo, base_rev, target_rev)` assumption was too narrow. Needed by
  Session 07.
- **Reports must keep state and change distinct** (D-016). A snapshot asserts "this is how it
  behaves"; an analysis asserts "this is what moved". Session 09 must not collapse them into one
  renderer.
- **Tag selection is deferred, not solved.** `237feed` has 777 build tags (`v26113ec4`) against
  `237feed-app`'s 11 semver tags. This only matters once something *auto-selects* a revision; today
  nothing does, because every option is required. Due at whichever ticket first adds "latest tag",
  "default branch" or "since last release".
- **Copyright holder** recorded as an individual in `LICENSE`/`NOTICE`; change before accepting any
  outside contribution if it should be a company.
- Q2, Q4, Q8 and Q10 are now resolved (D-010, D-012, D-009, D-011); the product name is resolved
  by D-013.

---

## Next single task

**Session 06 — Collect inspectable evidence (CON-06).**

Capture commit IDs, authors, dates, messages, file paths and bounded diff excerpts. Preserve source
references so a reviewer can inspect the original.
**Done when:** evidence records can be traced back to Git.

Scope for that session:

- Commit enumeration with `git log <merge-base>..<target>`, which already has merge-base semantics
  and so agrees with D-021 without special handling.
- Bounded diff excerpts per file, with per-file and per-proposal caps (D-005).
- A source pointer (`rev:path:line-range`) on every excerpt, so the full original is always
  re-derivable from Git and Constat never becomes the only copy of the evidence.
- Evidence for `snapshot` too, not only `analyse` — and without borrowing change vocabulary (D-022).

Two things to settle while implementing it:

- **What the caps actually are.** D-005 requires bounds but names no numbers. `237feed` has merges
  and a 628-file tree, so a 50-file range with full diffs is already a large document. Pick numbers
  and record them, rather than leaving a magic constant.
- **Whether `-M` rename detection should become `-C` (copy detection) as well.** Copies are more
  expensive to detect and more ambiguous; currently off. Leaving it off is the conservative choice
  and should be stated rather than defaulted into.

Explicitly **not** in Session 06: classification or interpretation. That is CON-08.

---

## Build roadmap — 20 focused work sessions

At 1–2 hours per day, one independently testable outcome per session. This is a working sequence,
**not a deadline promise** — take longer when a milestone needs it.

Session *N* is ticket `CON-NN` in [BACKLOG.md](BACKLOG.md), which also carries the non-session
legal and validation work (`CON-21` onwards) and the per-ticket design notes.

### Phase 1 — Foundation (sessions 1–4)

| # | Session | Done when | Status |
| --- | --- | --- | --- |
| 01 | Create the repository and working agreement | A documented empty project with clear scope and rules. | ✅ `b092b62` |
| 02 | Create the Python project skeleton | The CLI installs and runs locally; tests execute. | ✅ |
| 03 | Add configuration and input validation | Helpful errors; no silent defaults for important inputs. | ✅ |
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
| 6 | Implement the CLI skeleton and tests. | ✅ Session 02 |
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
