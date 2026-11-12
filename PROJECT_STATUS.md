# Project status

**Last updated:** 2026-11-12
**Current phase:** Phase 3 — Meaning and reporting (reshaped by D-035 … D-039)
**Current session:** CON-57 — a publishing port (CON-09, CON-56 closed)

---

## Where things stand

The repository is public at `https://github.com/padjis/constat`. Session 01 was committed and
pushed as `b092b62`.

A workspace now persists repositories, tickets, living documents and a rule catalogue. A ticket
reference gathers evidence across every registered repository (CON-34) and the catalogue reports
which changed paths no rule claims (CON-40).

**No rules are produced yet, and nothing deterministic can produce them** — D-035 settled that a
rule is a business statement no code signal yields, and D-039 made generation an AI pass. CON-41
built the seam for it: the provider registry is deliberately empty, nothing leaves the machine, and
the document states that no rules were *identified* rather than implying none exist.

CON-42 is in progress. The trust boundary on AI output exists — a reply is parsed, every anchor is
checked against the evidence actually supplied, and an unusable reply is refused rather than
silently emptied (D-046). What does not exist is something to produce the reply, and **D-045
changed what that will be**: the agent surface is an MCP server, so the host supplies the model and
the next step is stored rule proposals (CON-51) and a submit path (CON-52) rather than an HTTP
client. CON-09 is closed by CON-56: the document renders from stored state.

**Q1 is closed.** All ten original open questions from Session 01 are now resolved.

### Session 07 — done when: *stable, tested structured output* ✅

| Item | Status |
| --- | --- |
| `constat/models.py` — Pydantic schema, frozen, `extra="forbid"` | ✅ |
| `constat/mapping.py` — one-directional adapter→model layer (D-026) | ✅ |
| `schema_version` on every proposal (D-008) | ✅ asserted in tests |
| Generated `proposal_id`, deterministic `selection_key` (D-025) | ✅ |
| Repository identity from the root commit, not the path | ✅ survives move and re-clone |
| Discriminated `change` / `state` selections; `commit_set` reserved | ✅ |
| Full provenance taxonomy declared; evidence defaults to `observed_fact` | ✅ |
| JSON round-trip, including the selection discriminator | ✅ |
| `--json` on both commands | ✅ |
| Pydantic added as the first runtime dependency, with a stated reason | ✅ D-026 |

### Tests run

```
.venv/bin/python -m pytest  →  179 passed
```

36 new tests. The existing 143 needed **no changes**, which is the point of the D-026 boundary:
the Git layer stayed dependency-free dataclasses.

### Verified against a real repository

Subject A, a build-tag range, via `--json`: schema_version 1, 7 commits, 29 changes, 29 evidence
records all `observed_fact`, completeness 2223 captured / 32 omitted, and a repository identity
derived from the root commit rather than the path.

### The decision that actually mattered

Not the models — **identity**. A derived proposal ID (hash the inputs) is the tempting choice and
breaks the governance model: a fresh re-analysis would collide with an approved baseline for the
same range. History must be append-only (product rule 5), so identity is generated per run, and a
separate `selection_key` recovers the idempotent lookup derivation was wanted for. The two are not
in tension; they just need two fields.

### Session 06 — done when: *evidence records can be traced back to Git* ✅

| Item | Status |
| --- | --- |
| `constat/evidence/collector.py` — commits, excerpts, source pointers | ✅ |
| Commit metadata: sha, author, committer, both dates, subject, body, parents | ✅ |
| Author and committer never collapsed (a rebase rewrites one, not the other) | ✅ |
| Merge commits included and flagged, not filtered out | ✅ |
| Bounded excerpts, 400 lines/file and 4000/comparison (D-023) | ✅ measured, not invented |
| Fair-share allocation rather than first-come (D-024) | ✅ |
| Every excerpt records a reproduce command — **tested by running it** | ✅ |
| Truncation always stated: total lines, omitted count, reason | ✅ |
| Binary files recorded as binary, never given a fabricated diff | ✅ |
| A file is never dropped from the record, only its text | ✅ |

### Tests run

```
.venv/bin/python -m pytest  →  143 passed
```

29 new tests. The central one actually executes the recorded `git` command and asserts it returns
content the truncated excerpt does not contain — traceability proven rather than asserted.

### Verified against real repositories

- Subject A, a build-tag range: 7 commits, 29 files, 2223 lines captured, 1 file truncated.
- Subject B, a release range: 18 commits, 50 files, **49 captured whole**; only a generated
  lockfile truncated, at 393 of 3835 lines.

### A bug caught before shipping

The first implementation spent the excerpt budget first-come down the sorted file list. On the real
Subject B range that meant a generated lockfile took 400 of 4000 lines and files later in the
alphabet got **nothing** — evidence selection determined by filename ordering. Fixed by allocating
fairly before keeping any text (D-024); the real range went from starving later files to capturing
49 of 50 whole.

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

- Subject A, a build-tag range: 29 changed files, base is an ancestor of target.
- Subject B, a release range: 50 changed files, and the two tags have **diverged** — the merge
  base is neither tag.
- Subject A, `snapshot --rev main`: 628 files present.
- **The `BackwardsRange` guard fired on real data.** A Subject A build-tag pair supplied in the
  wrong order was refused. Without it the output would have read "No file changes in this range",
  which is the confidently-wrong-empty-report failure this product exists to avoid.

### An honest limit on the D-021 evidence

The two diff semantics provably differ — a constructed test shows the endpoint diff reporting a
base-only file as a deletion. But on real data the difference has **not** yet been observed to
change a report: for a Subject B release range, despite genuine divergence, both semantics
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
| Throwaway-repository fixtures; no dependency on the real subjects | ✅ `tests/conftest.py`, `tests/helpers.py` |
| Annotated tags resolve to the commit, not the tag object (D-019) | ✅ |
| Ambiguous revisions refused rather than guessed (D-020) | ✅ |
| Bare repositories, detached HEAD, unborn HEAD, subdirectories | ✅ |
| Read-only proven, not asserted | ✅ tests compare `status`/`HEAD`/`show-ref` before and after |

### Tests run

```
.venv/bin/python -m pytest  →  86 passed in 2.36s
```

38 new tests. Verified against both real repositories, including their incompatible tag schemes:
Subject A's build tags and Subject B's semver tags both resolve.

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
$ constat snapshot --repo <subject-a> --rev main   → input accepted, nothing read
$ constat analyse --repo <subject-a> \
    --base <tag-1> --target <tag-2>                → input accepted, nothing read
$ constat analyse --base a --target b              → error: --repo required  (exit 2)
$ constat analyse --repo <subject-a> \
    --base main --target main                      → error: nothing to compare (exit 2)
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

- **Personal data in evidence: settled (D-040).** Identity does not cross the provider boundary at
  all — no names, no addresses, no timestamps, and the payload type has no field for them. The
  obligation D-023 recorded is discharged, before any provider exists.
- **A built wheel was broken, and is fixed (CON-46, D-042).** `packages = ["constat"]` dropped every
  subpackage from the wheel from CON-04 onwards, unnoticed because the development install is
  editable. Now discovered rather than listed, with `tests/test_packaging.py` building a wheel and
  importing from it.
- **Secret scanning is in place (CON-45, D-044), with stated misses.** Known formats only, so a
  passphrase of one character class or any credential with no recognisable shape is not detected.
  An empty scan is not a clean bill of health, and the document says so rather than implying one.
- **The AI cost is now a measured number, not an estimate.** 8 commits in one repository produce a
  ~47,000-token payload. The registered set is plural by construction, so this scales the wrong
  way, and CON-42 must treat payload size as a design constraint.
- **CON-39 blocks review, now in a narrower form (D-043).** The document body is machine-written
  only — a human comments, validates a rule or rejects an implementation, and never edits — so
  regeneration destroys no prose. What remains is that a comment is anchored to something the next
  run rewrites: **anchors must be durable identities, not positions in text.** Still gates CON-12
  and CON-44, and now also CON-47.
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
- **Tag selection is deferred, not solved.** Subject A has 777 build tags against Subject B's 11
  semver tags. This only matters once something *auto-selects* a revision; today
  nothing does, because every option is required. Due at whichever ticket first adds "latest tag",
  "default branch" or "since last release".
- **Copyright holder** recorded as an individual in `LICENSE`/`NOTICE`; change before accepting any
  outside contribution if it should be a company.
- Q2, Q4, Q8 and Q10 are now resolved (D-010, D-012, D-009, D-011); the product name is resolved
  by D-013.

---

## Next single task

**CON-57 — a publishing port and the default target.** The document is now worth publishing; the
place to put it is not built.

From the approved plan: a `Target` protocol (`publish`, `read_decisions`), default detection from
the repository's remote (`github.com` → GitHub pages, `gitlab.*` → GitLab wiki) refusing rather
than guessing, publishing gated by `guard_release` because it is egress, and credentials from the
environment only. `constat/git/adapter.py` needs a small read-only `remote_url`.

`PRODUCT_SPEC.md` § 6.2 defers "writing to GitHub" and needs amending first, with the reason
stated — an amendment note, as D-028 has in § 6.3.

Then **CON-58** (read decisions back, with channel and verification recorded) and **CON-59** (the
other backends).

Still standing: validation is at **zero discovery conversations** (CON-26), and `tryconstat.com`
is unregistered (CON-21).

---

## CON-56 — done when: *the document shows the catalogue and the queue, not just the run* ✅

Closing **CON-09**'s core.

| Item | Status |
| --- | --- |
| `CatalogueView` + `catalogue_view()` — impacted rules, unclaimed paths, queue | ✅ D-056 |
| Business section first; evidence under `## Evidence` | ✅ product rule 8 |
| The run's own result labelled **"This run:"** | ✅ closes the lie |
| Rendering takes no workspace — a pure function of stored structure | ✅ asserted on the signature |
| Rule proposals stored *before* the body is rendered | ✅ the queue no longer lags a run |
| Plain Markdown; usable as a PR body; queue as a task list | ✅ |
| `bound_for_pr` — business half never trimmed, omission stated | ✅ D-023's rule, one level up |
| Unclaimed paths one per line, never abbreviated | ✅ D-038, D-039 |

### Tests run

```
.venv/bin/python -m pytest  →  723 passed in 83.16s
```

26 new tests. One existing test was rewritten — see below.

### Mutation-checked

| Regression | Result |
| --- | --- |
| Render from the run instead of stored state | **11 tests failed** |
| Unscope the run's note | **1 test failed** |
| Truncate silently instead of stating the omission | **3 tests failed** |

The third needed a second attempt: my first edit produced an `IndentationError`, so the run reported
zero failures because the module would not import. A mutation that does not compile proves nothing,
and `grep -c FAILED` does not distinguish that from a passing suite.

### The bug was a lie, not a gap

`constat document 622 --show` printed *"no rules were identified"* while the catalogue held rule 1
at version 3 and that ticket had rule proposals waiting. The body rendered from the current run's
`Interpretation`, so a run with no provider reported on the ticket as though nothing were known.
That is product rule 1's failure mode appearing in the product's own output.

### Two defects found while building it

- **The queue lagged a run behind.** Rule proposals were stored *after* the document was rendered,
  so a reader saw "1 rule proposed" and an empty queue in the same document. `gather` now stores
  before rendering.
- **The note said "the evidence above".** The evidence moved below it in the restructure.

### Verified on both real subjects

| Subject | Document | Fits a PR body | Business signals |
| --- | --- | --- | --- |
| B, 8 commits | 5,095 chars | yes | impacted rule named, 29 unclaimed paths listed |
| A, 30 commits | 21,218 chars | yes | coverage reported |

Subject B surfaced the readability problem: 29 unclaimed paths comma-joined into one paragraph is
unreadable in a document and worse in a pull request. One per line now, and never abbreviated —
"and N more" would hide exactly the coverage gap D-038 requires to stay visible.

---

## CON-50 — done when: *an MCP client can drive the loop; acceptance is never exposed* ✅

| Item | Status |
| --- | --- |
| `constat/mcp.py`, `constat mcp` — stdio transport | ✅ D-055 |
| Four tools: gather, payload, submit, list queue | ✅ |
| **No `accept` or `reject` tool**, asserted on the live tool list | ✅ the point of the ticket |
| The `mcp` SDK is an optional extra | ✅ D-003's promise holds |
| No tool reimplements an operation | ✅ gates hold by construction |
| Constat's errors keep their message through `ToolError` | ✅ |
| Instructions tell the model nothing it submits is accepted | ✅ |
| Verified through a real client over stdio | ✅ not only in process |

### Tests run

```
.venv/bin/python -m pytest  →  697 passed in 69.30s
```

22 new tests. The existing 675 needed no changes.

### Mutation-checked

| Regression | Result |
| --- | --- |
| Expose an `accept_rule_proposal` tool "for convenience" | **3 tests failed** |
| Let a `ConstatError` escape instead of becoming a `ToolError` | **4 tests failed** |

### The test that matters asserts an absence

A model that could call `accept` would make "no proposal becomes official without an explicit human
decision" unenforceable — not by malice, but because the tool would be there. An absence is the
easiest property to lose, so the tool list is checked against the **live server** rather than by
reading the source: a tool added by a decorator anywhere shows up.

### A wrapper that lost the reason

Letting a `ConstatError` escape gets it wrapped as an unexpected crash, and a client sees "Error
executing tool get_payload" with the refusal gone. `ToolError` — the SDK's "a failure you
anticipated" — keeps the message, which for this product is the part worth sending: *remove the
credential and rotate it*.

### Two things the SDK taught me rather than my memory

`mcp` 2.x renamed `FastMCP` to `MCPServer`, and the client-side `CallToolResult` field is
`is_error`, not `isError`. Both found by running it against a real client — which is the argument
for that end-to-end test existing rather than trusting the in-process shortcut.

---

## CON-55 — done when: *a reading can claim to revise a rule rather than duplicate it* ✅

| Item | Status |
| --- | --- |
| The payload carries the catalogue — id, name, statement, anchors | ✅ D-054, the missing input |
| A reply may name `revises: <rule_id>` | ✅ |
| An invented claim is rejected like an invented anchor | ✅ symmetric on purpose |
| A boolean is not a rule id | ✅ `True` is an `int` in Python |
| Overlap is reported as a candidate, never applied | ✅ D-050 |
| A claimed revision is not also flagged | ✅ it already decided |
| The catalogue in the payload carries no identity | ✅ D-040 unaffected |

### Tests run

```
.venv/bin/python -m pytest  →  675 passed
```

20 new tests. The existing 655 needed no changes.

### Mutation-checked

| Regression | Result |
| --- | --- |
| Ignore the `revises` claim entirely | **8 tests failed** |
| The payload stops carrying the catalogue | **4 tests failed** |
| Auto-pick the overlapping candidate | **3 tests failed** |

### The missing piece was an input, not logic

A reading had never been shown what exists, so every reading claimed to be new and the second
reading of a rule created a duplicate — CON-43's failure arriving by a different route. Adding the
catalogue to the payload is most of the fix; validating the claim is the rest.

### An honest limit, and how it surfaced

Overlap is **identical glob string**, not glob intersection. A rule anchored to `rules.py` and a
reading anchored to `**/*.py` overlap in reality and are not flagged. Widening it means comparing
globs for intersection, which has no exact answer in general, and a warning that fired on every
broad glob would be noise.

It surfaced because a test I wrote had an `or` escape hatch — `assert candidates == {} or
possible_duplicates == 1` — which could not fail. Replacing it with the real expectation is what
exposed the narrowness. An assertion with an alternative branch is usually a sign the expected
behaviour was not actually understood.

---

## CON-44 — done when: *a reviewer accepts or rejects rule changes individually* ✅

Closing most of **CON-43** with it.

| Item | Status |
| --- | --- |
| `rule_version` + behaviours and anchors; schema 6 with a migration | ✅ D-053 |
| `rule accept` / `rule reject` / `rule history` | ✅ |
| Accepting baselines a frozen version pointing at the reading accepted | ✅ traceable to a diff |
| A revision adds version N+1 rather than duplicating the rule | ✅ CON-43's done-when |
| A name may change between versions; the rule stays one rule | ✅ D-050 |
| Rejecting changes nothing and is not a dead end | ✅ D-036 |
| `rule_version` append-only by trigger | ✅ |
| `--by` has no default | ✅ no automatic approvals, in the parser |

### Tests run

```
.venv/bin/python -m pytest  →  655 passed in 54.62s
```

30 new tests. The existing 625 needed no changes.

### Mutation-checked

| Regression | Result |
| --- | --- |
| Ignore the revision claim — every acceptance creates a new rule | **6 tests failed** |
| Rejecting baselines a version anyway | **2 tests failed** |
| `rule_version` loses its append-only triggers | **2 tests failed** |

### Why a revision is a version and not a duplicate

`revises_rule_id` is the reading's *claim* (D-050), and a human accepting the reading accepts the
claim with it. Acceptance is therefore the only place the claim takes effect — which is what makes
a wrong claim a rejectable interpretation rather than a corrupted identity.

### A guard the database made unreachable

A claim to revise a nonexistent rule cannot even be recorded: the foreign key refuses it at write
time. The acceptance-time guard stays anyway, and the test says why — if the key were ever
relaxed, the alternative is silently creating a *new* rule when the reviewer accepted a revision.

### Verified on the real workspace

Migrated v5 → v6 with its 8 operations intact, then the reading stored from Subject B's evidence
was accepted into rule 1, version 1 — with `rule history` showing the chain back to the rule
proposal and the run.

### What is left of CON-43

The *finding* half. `candidates_for` locates rules by anchor overlap, but nothing calls it, so
every submitted reading still claims to be new. CON-55.

---

## CON-52 — done when: *a reply produced anywhere becomes grounded, stored rule proposals* ✅

| Item | Status |
| --- | --- |
| `submit_reply`, `rule submit`, `rule proposals` | ✅ D-052 |
| Evidence **re-gathered**, never taken from the caller | ✅ the load-bearing part |
| An unusable reply is an error, not an empty result | ✅ exit 5 |
| Parsing happens before the run opens — no empty events | ✅ |
| `provider` / `model` recorded as self-reported | ✅ D-045 |
| Discards reported **before** the kept count | ✅ D-046 |
| Nothing accepted; the catalogue is untouched | ✅ asserted |
| The document body is not rewritten | ✅ `document` writes it, submit does not |

### Tests run

```
.venv/bin/python -m pytest  →  625 passed in 57.13s
```

31 new tests. The existing 594 needed no changes.

### Mutation-checked

| Regression | Result |
| --- | --- |
| Trust a caller-supplied payload instead of re-gathering | **13 tests failed** |
| Auto-accept submitted readings into the catalogue | **2 tests failed** |
| Let the two glob matchers diverge again | **4 tests failed** |

### Why re-gathering is the load-bearing part

If the payload came from the caller, a reply could ship a payload that makes any anchor look
grounded — the check would be verifying the reply against itself. Grounding only means something
when it is checked against evidence Constat can see.

### A false rejection, caught by a test rather than in use

`**/rules.py` is the most natural way to write "this file anywhere", and plain `fnmatch` never
matches it against a root-level file — so a correct anchor was being discarded as ungrounded.
Grounding and catalogue matching now share `constat/globs.py`; two matchers that disagreed would
accept a rule proposal at submit time and then never match it to a change.

This is the same failure as a false credential positive, one layer up: a rejection that is wrong
teaches people to stop reading rejections.

### Verified end to end on a real subject

Subject B: a 195 KB payload exported, a reply submitted naming one real path and one invented one.
The grounded reading was stored, the invented anchor discarded with its reason, and the catalogue
was still empty afterwards.

---

## CON-51 — done when: *a rule proposal survives the run that produced it* ✅

With CON-53 (withdraw the manual rule commands) landing alongside it.

| Item | Status |
| --- | --- |
| `rule_proposal` + behaviours, anchors, decisions; schema 5 with a migration | ✅ D-051 |
| Append-only: `UPDATE` and `DELETE` abort by trigger | ✅ readings and decisions both |
| A decision does not mutate the reading | ✅ separate table, as `document_version` |
| Changing one's mind appends; both stay visible | ✅ latest displays |
| Self-reported reader recorded (`provider`, `model`) | ✅ D-045 — a claim, not a fact |
| `revises_rule_id` nullable — a claim, not a key | ✅ D-050 |
| `gather` persists what the provider returned | ✅ survives the next regeneration |
| `rule` cannot be deleted | ✅ trigger (D-048) |
| `rule add` / `behaviour` / `anchor` / `remove` gone | ✅ CON-53 |
| `rule.name` lost `UNIQUE` | ✅ in the schema — see the honest limit below |

### Tests run

```
.venv/bin/python -m pytest  →  594 passed in 44.13s
```

30 new tests. Eight CLI tests covering the removed commands went with them, and two catalogue
withdrawal tests became "removal is now impossible".

### Mutation-checked

| Regression | Result |
| --- | --- |
| The append-only triggers removed | **5 tests failed** |
| `gather` stops persisting what the provider returned | **3 tests failed** |
| The migration forgets to copy `behaviour` rows | **1 test failed** |

### The riskiest migration so far

Dropping `rule.name`'s `UNIQUE` needs a table rebuild, and `rule` is the parent of `behaviour` and
`anchor` with `ON DELETE CASCADE` — so dropping the parent alone would have silently emptied the
catalogue. All three are rebuilt, children dropped first, renames last so the new children's
foreign keys are rewritten to match.

Verified on a real v4 workspace: migrated to 5 with its **8 operations and 1 run** intact, and the
four `rule_proposal*` tables usable afterwards rather than merely present.

### An honest limit: half the change landed

`Catalogue` is still **name-keyed**. `add_rule` keeps an application-level duplicate guard and
`find` looks up by name, so two rules cannot share a name *through the API* even though the schema
now allows it. That guard is a leftover of the pre-D-050 model and goes when the catalogue becomes
id-keyed and versioned (CON-43, with CON-44). The test asserts the schema rather than the API, and
says why — rather than asserting a behaviour that does not exist yet.

---

## CON-54 — done when: *one run per invocation, with its operations attached* ✅

| Item | Status |
| --- | --- |
| `run` table and `operation.run_id`; schema 4 with a migration | ✅ D-049 |
| One run per gather, whatever the repository count | ✅ asserted with three |
| Every operation a run writes belongs to it — no orphans | ✅ |
| A scan override joins the run whose evidence it let through | ✅ one event, not two |
| An export opens a run **only** when it accepted findings | ✅ no empty events |
| Pre-schema-4 rows keep `run_id` NULL | ✅ no fabricated provenance |

### Tests run

```
.venv/bin/python -m pytest  →  561 passed in 37.65s
```

19 new tests. The existing 542 needed one change: the migration test asserted `schema_version == 3`
as a literal, and now asserts against `SCHEMA_VERSION` so a future bump that forgets its migration
fails there rather than quietly rewriting the expectation.

### Mutation-checked

| Regression | Result |
| --- | --- |
| A run opened per repository instead of per invocation | **5 tests failed** |
| The migration creates `run` but forgets `operation.run_id` | **4 tests failed** |

### Verified on a real workspace

A workspace built at schema 3 by the previous commit: opened, migrated to 4, kept its **7**
pre-run operation rows NULL, and a fresh gather opened run 1 with its operation attached.

### A fixture of mine tripped a real guard

Registering three repositories failed as a duplicate. `make_subject` seeds byte-identical history,
and identical content committed in the same second yields the same root commit — so D-025's
identity check refused the second one. The guard was right and the fixture was lazy; the helper
now varies each root. Worth noting because it is the third time this session a test problem has
been my assumption about a fixture rather than a fault in the code.

---

## CON-49 — done when: *the payload can be handed out, and only through the gate* ✅

| Item | Status |
| --- | --- |
| `guard_release` — one chokepoint for every egress path | ✅ D-047 |
| `constat document <ref> --payload` — redacted payload as JSON on stdout | ✅ |
| Export refuses **unconditionally**; `gather` with no provider still only reports | ✅ the asymmetry |
| `collect()` shared, so both paths see identical evidence | ✅ asserted equal |
| Export writes nothing but an override record | ✅ |
| Override recorded under its own kind, distinct from a send override | ✅ `scan_override_export` |
| `--payload` with `--show` is a usage error | ✅ exit 2 |

### Tests run

```
.venv/bin/python -m pytest  →  542 passed in 33.63s
```

22 new tests. The existing 520 needed no changes.

### The hole this closed, on real data

| Subject | Result |
| --- | --- |
| B, 8 commits, 33 files | Exports cleanly — ~195 KB, and no identity field on the commit type at all |
| A, 30 commits | **Refused, exit 5, zero bytes on stdout** — it has real credentials in the window |

Before this, `--payload` would have handed Subject A's credentials to a third-party model. The
gate was keyed on a provider being configured, and an export has no provider.

**Mutation-checked:** reverting the export to the provider-only gate fails 3 tests, including the
one asserting stdout stayed empty.

### Why it raises instead of returning a flag

A caller that forgets to check a boolean still sends the payload. A caller that forgets to catch
an exception does not. Any future egress path — a submit echo, an MCP resource, a debug dump —
inherits the obligation, and the answer is "call `guard_release`" rather than "remember D-040 and
D-044".

### A test that asserted nothing, again

The CLI test for "the export does not fill the document" originally checked the body was empty.
`ticket add` already fills it (CON-34), so the assertion was vacuous. Rewritten to compare the
body before and after — the property is that the export does not *change* it. Second time this
session an assertion has been hollow rather than wrong; both times the fixture had more state than
I assumed.

---

## CON-42 — in progress: the trust boundary landed, the provider did not 🟡

| Item | Status |
| --- | --- |
| `constat/ai/parsing.py` — `parse`, `ParseResult`, `Rejection` | ✅ D-046 |
| An unusable reply raises `MalformedResponse`, never returns empty | ✅ exit 5 |
| Every anchor checked against paths actually in the payload | ✅ the property with teeth |
| An ungrounded or unanchored proposal is rejected whole, with a reason | ✅ |
| Rejections reach the `Interpretation`, the document and the CLI | ✅ |
| A rejection carries only the name and reason, never the model's prose | ✅ |
| Code fences unwrapped; bare-string anchors accepted | ✅ pragmatism about real replies |
| A provider in the registry, and a prompt | ⬜ reshaped by D-045 into CON-49 / CON-50 |

### Tests run

```
.venv/bin/python -m pytest  →  520 passed in 30.26s
```

50 new tests. The existing 470 needed no changes.

### Mutation-checked

| Regression | Result |
| --- | --- |
| A bad reply swallowed as "no rules found" | **14 tests failed** |
| The anchor-grounding check removed | **3 tests failed** |
| Rejections never rendered into the document | **2 tests failed** |

### Anchor grounding is the part worth keeping

A model will propose a rule anchored to a plausible-sounding path whether or not that path was in
the payload. Storing it would mean Constat had **invented its own evidence** — the inverse of
product rule 2. The check costs nothing, so it is made, and it is deliberately fatal to the whole
proposal: keeping the grounded half of a two-anchor rule would silently narrow a claim the model
meant more broadly, which is a different claim rather than a smaller one.

### Verified on both real subjects

| | Grounding paths | Grounded reply | Invented anchor | Prose reply |
| --- | --- | --- | --- | --- |
| Subject B, 8 commits | 30 | kept | rejected | refused |
| Subject A, 30 commits | 72 | kept | rejected | refused |

### One test that was passing for the wrong reason

The first version of the rejection-rendering tests called `render` with an empty findings tuple.
`render` returns early when nothing was searched, so both assertions ran against the "no
repositories are registered" branch and told me nothing. Caught because the assertion failed, not
because I checked — worth remembering that an early return makes a downstream assertion vacuous
rather than false.

---

## CON-45 — done when: *a payload containing a credential is refused rather than sent* ✅

| Item | Status |
| --- | --- |
| `constat/ai/scanning.py` — detectors, `scan`, rendered section, refusal message | ✅ |
| Known formats only; entropy scoring rejected with a reason | ✅ D-044 |
| `PayloadRefused` in the `ProviderError` family, exit 5 | ✅ |
| Refusal before `interpret` **and** before the document is written | ✅ asserted |
| Scan runs on every run; refusal only where a provider would receive it | ✅ |
| `--accept-scan-findings`, one run only, recorded as `human_decision` | ✅ on `document` and `ticket add` |
| Override recorded as a `scan_override` operation | ✅ |
| A finding never carries the matched text | ✅ four tests |
| An empty scan is not presented as proof of cleanliness | ✅ asserted on the wording |

### Tests run

```
.venv/bin/python -m pytest  →  470 passed in 51.61s
```

67 new tests. The existing 403 needed no changes.

### Mutation-checked

| Regression | Result |
| --- | --- |
| The refusal gate made unreachable | **4 tests failed** |
| `SecretFinding` made to carry the matched text | **4 tests failed** — including the persisted-document one |
| Scanning restricted to the provider path | **1 test failed** |

The second matters most. A scanner that records what it found would copy the credential into the
workspace and from there into every frozen version of the document, outliving the repository it
came from.

### Real evidence changed the implementation twice

| Pass | Result | Consequence |
| --- | --- | --- |
| First, 8 commits, ~3,100 diff lines | One **false positive** — a `token`-named variable assigned an expression | The code-expression rule exists because of it |
| Second, 30 commits, a different stack | **True positives** | The feature justified itself before it had a provider to protect |

After the fix, the first sample scans clean. A "bare identifier" rejection rule was tried in
between and removed — a real credential and a variable name are the same shape — so character-class
variety does that work, with a stricter threshold for unquoted values.

**Nothing identifying what was found is recorded in this repository**, by the owner's instruction.
Findings belong in a workspace document, not in public project files; the test fixtures use
synthetic lines and published documentation examples for the same reason.

### The honest part

A passphrase of one character class, a base64 credential beginning with `+`, and anything with no
recognisable shape all go undetected. That is the price of refusals being believable: the second
time a false refusal happens, the override stops being read.

---

## CON-46 — done when: *a built wheel contains the package and imports* ✅

| Item | Status |
| --- | --- |
| `pyproject.toml` — discovery instead of an explicit `packages` list | ✅ D-042 |
| `tests/test_packaging.py` — configuration, wheel contents, wheel import | ✅ 6 tests |
| Every package directory on disk is asserted to match an include pattern | ✅ walks the tree, no hardcoded list |

Found while verifying CON-41's "no new dependency" claim, not while looking for it. From CON-04
onwards the wheel contained nine modules and no subpackages at all; a wheel install would have
failed at the first `from .store import …`. Invisible for five tickets because the development
install is editable and imports from the working tree.

### The test was harder than the fix, and twice gave a false pass

The fix is one line. Making it *provable* took two attempts, and both failures made a broken wheel
look fine — which is why they are written down in D-042 rather than left in a commit message:

| False pass | Why |
| --- | --- |
| In-tree build | setuptools stages into `build/` and never cleans it, so earlier builds' modules are included regardless of configuration. With the defect restored, an in-tree build still produced a **complete** wheel. |
| Import probe | The editable install's `.pth` meta path finder claims `constat.*` from the working tree, ahead of `sys.path`. The probe loaded `cli` from the wheel and `store` from the repository, passing against a wheel with no `store` in it. |

Now the wheel is built from a staged copy of the source, and the probe runs with `-S` so `.pth`
files are skipped and the unpacked wheel is the only `constat` available.

**Mutation-checked:** with the explicit list restored, 5 of the 6 tests fail.

### Tests run

```
.venv/bin/python -m pytest  →  403 passed in 41.85s
```

---

## CON-41 — done when: *a provider can be configured; absent one, no rules were identified* ✅

| Item | Status |
| --- | --- |
| `constat/ai/provider.py` — `Provider` protocol, `Interpretation`, `NullProvider` | ✅ |
| `constat/ai/redaction.py` — the privacy boundary (D-040) | ✅ |
| `constat/ai/settings.py` — provider resolved from the environment, registry empty | ✅ |
| `RuleProposal` in `models.py`, provenance pinned to `ai_interpretation` | ✅ cannot be relabelled |
| The document's rules section, always present | ✅ `## Business rules` |
| "No rules were identified" never written as "none exist" | ✅ asserted on the wording |
| Credentials from the environment only, never stored | ✅ workspace records provider, not key |
| A misconfigured provider is refused, not nulled (D-041) | ✅ exit code 5 |
| The provider resolves **before** any repository is read | ✅ test watches the collector |
| `ticket add` reports the rules state too | ✅ it gathers, so it must say |
| No new dependency, no HTTP, no API call | ✅ `dependencies` unchanged |

### Tests run

```
.venv/bin/python -m pytest  →  397 passed in 37.94s
```

57 new tests. The existing 340 needed no changes.

### Mutation-checked, because a privacy test that cannot fail is worthless

Two deliberate regressions were introduced and the suite re-run:

| Regression | Result |
| --- | --- |
| `scrub_message` and `scrub_diff` turned into identity functions | **6 tests failed** |
| Provider resolution moved after evidence collection | **1 test failed** |

The second one is the reason that test watches `_collect_repository` rather than the document: the
document is written at the end either way, so asserting on it would have passed while the
regression shipped.

### Verified against the real subjects

Both subjects registered; `ticket add 622` and `ADR-0019` report `landed` / `not_found` with the
rules section present and honest. `CONSTAT_AI_PROVIDER=anthropic` exits **5** and names what is
available, rather than quietly producing an empty rule section.

For a payload with real content, Subject B was cloned and its last 8 commits made pending ahead of
mainline:

| Measure | Value |
| --- | --- |
| Commits in the payload | 8 |
| Files | 33 |
| Payload size | 186,636 chars (~47,000 tokens) |
| Address-shaped strings surviving | **0** |
| Author/committer fields on the payload type | **none exist** |

### Two honest limits

**The masking paths were not exercised by real data.** That range needed zero redactions —
identity was absent *structurally*, because the type has nowhere to put it. The trailer-stripping
and diff-masking code was exercised only by fixtures. It rests on anticipating the case, the same
way D-021 rests on asking the right question rather than on an observed discrepancy.

**Secret scanning is not solved and is not claimed to be.** Commit messages and diffs do leave the
machine — that is the product — but a payload containing a leaked credential would be sent as
readily as anything else. Raised as **CON-45**, to land with or before CON-42.

### A wrinkle left behind

`ticket add` gathers, so a provider fault there leaves the ticket open with an empty document. It
is recoverable — `constat document <ref>` once the environment is fixed — and consistent with the
living-document model (D-029), but it is not transactional in the way CON-33's ticket-and-document
creation is.

---

## CON-40 — done when: *rules, behaviours and anchors persist and report coverage* ✅

Committed as `b576795`.

| Item | Status |
| --- | --- |
| `constat/store/catalogue.py` — `Catalogue` | ✅ |
| `rule` / `behaviour` / `anchor` tables; schema v3 with a v2→v3 migration | ✅ |
| `Rule`, `Behaviour`, `Anchor` in `constat/models.py` | ✅ |
| `constat rule add / behaviour / anchor / list / show / remove` | ✅ |
| Rules matched to changed paths by anchor glob | ✅ `rules_matching` |
| Paths claimed by **no** rule reported explicitly | ✅ `unmatched_paths` |
| A rule with no anchors says so — it can never be matched | ✅ stated in `rule show` |
| Generated rules carry `ai_interpretation`, not `requirement_ref` | ✅ corrected by D-039 |

### Tests run

```
.venv/bin/python -m pytest  →  340 passed in 16.42s
```

30 new tests (24 catalogue, 6 CLI), plus the v2→v3 migration covered in `tests/test_workspace.py`.

### The rule model settled here, over six decisions in one day

This was the session where the rule model stopped being a code problem. The sequence matters:

- **D-035** — a rule is a *business statement*; a behaviour is *a way the app handles a business
  case*. Neither can be read out of code. That is what made every code-signal approach a dead end,
  not an implementation difficulty.
- **D-034** — feature flags removed. A flag is a *control over* behaviour, not a statement of it,
  and its live value is not even in the repository.
- **D-038** — SQL migrations removed for the same reason, dissolving D-010's "deterministic spine"
  entirely. A migration is at most *evidence that* a rule exists.
- **D-036** — rejection means **inconclusive** (another PR is expected), not "the write-up is
  wrong" and not "this must never ship".
- **D-037** — accepted rules migrate into the baseline. This unifies CON-14, CON-15 and drift:
  `NEW` and `CHANGED` are relative to what has been *approved*, not to what exists.
- **D-039** — rules are generated and maintained by AI, reversing D-038's authorship the same day
  it was taken.

### The reversal is the entry worth re-reading

D-038 chose a hand-declared catalogue to avoid API cost before validation. D-039 reversed it
hours later, and the reason is not convenience: a hand-maintained catalogue contains only the
rules someone remembered to declare, and drifts from the code **by construction** — the exact
disease this product treats. The `rule` CLI commands survive as a bootstrap and test path, which
is how the catalogue is exercised with no provider configured. They are not the intended way to
author rules, and the command help says so.

### What this costs, stated rather than discovered later

D-039 is the roadmap's top risk made concrete. The plan says postpone AI API calls until the
workflow is validated, and validation stands at **zero discovery conversations** (CON-26).
Evidence is already 2000–4000 diff lines per range per repository. Proceeding is a deliberate
choice.

### The functions that matter most

`unmatched_paths`. A catalogue only knows the rules it holds, and an AI pass will miss rules too,
so changed files claimed by no rule must stay prominent rather than being quietly absent. Coverage
reporting is the thing that keeps an incomplete catalogue honest.

---

## CON-34 — done when: *an operation produces a document with evidence from each repository* ✅

| Item | Status |
| --- | --- |
| `constat document <ref>` gathers across the registered set | ✅ |
| `ticket add` fills the document immediately (D-033) | ✅ |
| Evidence collected per commit, not as one cumulative diff (D-033) | ✅ |
| Repositories searched but contributing nothing still appear | ✅ |
| `landed` / `not_found` / `pending` distinguished in the body | ✅ |
| Each run records an operation per repository | ✅ |
| `ticket show` reports stored state, never a fresh search | ✅ |

### Tests run

```
.venv/bin/python -m pytest  →  308 passed
```

### The trap the tests build

A ticket's commits need not be contiguous. Diffing the first commit's parent against the last
would attribute whatever else landed between them to the ticket, so a test constructs exactly
that — ticket work, an unrelated commit, more ticket work — and asserts the unrelated file never
appears.

### Hazard left behind: CON-39

The body is regenerated on every run. That is safe only while it is entirely machine-derived; the
moment a reviewer can edit it (CON-12), regeneration destroys their work. Must be solved before
review ships.

---

## CON-33 — done when: *a ticket owns exactly one living document* ✅

| Item | Status |
| --- | --- |
| `constat ticket add / list / show` | ✅ |
| Ticket and document created in one transaction | ✅ asserted no orphan is reachable |
| A second document for one ticket is impossible | ✅ schema `UNIQUE` |
| References stored verbatim — four shapes exist in the subjects | ✅ |
| No ticket title; schema v2 migration drops the column (D-032) | ✅ |
| Attribution by branch name and by commit message (D-030) | ✅ |
| Search window is everything ahead of mainline (D-031) | ✅ |
| `pending` / `landed` / `not_found` kept distinct | ✅ |
| The ref a commit was found on is recorded as evidence | ✅ |

### Tests run

```
.venv/bin/python -m pytest  →  286 passed
```

38 new tests, including five that migrate a real version-1 workspace.

### On the real subjects

`ticket add 622` against Subject A reports **`landed`** — correctly, since every branch there is
zero commits ahead of mainline. That is the honest answer rather than the convenient one, and it
is why the fixture builds the `pending` shape itself.

Token-boundary matching earned its place on real data: ticket 622 matched a commit whose *subject*
never mentions it, because its body contains `(#622)`. The same pattern correctly refuses `6220`
and `1622`.

---

## CON-32 — done when: *a registered repository survives a restart and is readable* ✅

| Item | Status |
| --- | --- |
| `constat repo add / list / remove` | ✅ |
| Identity and default branch resolved and stored at registration | ✅ |
| Default branch from `origin/HEAD`, never from the checked-out branch | ✅ CON-36 delivered here |
| Duplicate detection by identity, not path | ✅ |
| Registration reuses the Git layer's errors | ✅ |
| `remove` leaves the repository on disk untouched | ✅ asserted |
| Exit 3 for repository problems, 4 for workspace problems | ✅ |

### Tests run

```
.venv/bin/python -m pytest  →  248 passed
```

33 new tests. The clone fixture matters: `origin/HEAD` only exists in a clone, so a `git init`
repository exercises the refusal path and a clone exercises the resolution path.

### The two refusals

**No default-branch guessing.** Falling back to HEAD's symref would let `repo add` run from a
feature branch and silently make that branch the baseline for every future comparison. Verified
against reality: both subjects resolve automatically; this repository, created with `git init`,
is refused and told to pass `--default-branch` or run `git remote set-head`.

**No duplicate by identity.** A second clone at another path is the same repository (D-025). The
error names the existing alias and the shared root commit rather than just saying "duplicate".

---

## CON-31 — done when: *a restart does not lose repositories, tickets or documents* ✅

| Item | Status |
| --- | --- |
| `constat/store/` — SQLite workspace, versioned schema | ✅ |
| `constat init`, reporting the workspace it used | ✅ |
| Refuses to overwrite an existing workspace | ✅ exit 4 |
| Refuses a newer *or* older schema rather than guessing | ✅ |
| Append-only `document_version`, enforced by triggers | ✅ UPDATE and DELETE both abort |
| One document per ticket, enforced by `UNIQUE` | ✅ |
| Foreign keys on (SQLite defaults them off) | ✅ |
| Operations recorded against documents | ✅ table in place |
| Exit code 4 for workspace errors, distinct from 2 and 3 | ✅ |

### Tests run

```
.venv/bin/python -m pytest  →  215 passed
```

36 new tests. The append-only ones assert the triggers actually fire: a trigger that does not is
worse than no trigger, because it looks like protection.

### One bug the tests caught

Opening a non-database file leaked a raw `sqlite3.DatabaseError` traceback instead of a Constat
error. Fixed in the connection wrapper — "fail clearly" is the standard the project set itself,
and a stack trace does not meet it.

### Design note

Immutability is enforced **by the database**, not by application code. `document_version` rejects
`UPDATE` and `DELETE` outright, so a future bug cannot rewrite an approval by forgetting to call
the right helper. Same reasoning for one-document-per-ticket, the decision `CHECK`, and foreign
keys: ARCHITECTURE.md section 5 rules belong where they cannot be bypassed.

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
| 04 | Read a local Git repository | Tests cover valid, invalid and missing repositories/revisions. | ✅ `184fa0b` |

### Phase 2 — Evidence engine (sessions 5–7)

| # | Session | Done when | Status |
| --- | --- | --- | --- |
| 05 | Compare two revisions | A deterministic change summary for two revisions. | ✅ `6e3b07d` |
| 06 | Collect inspectable evidence | Evidence records can be traced back to Git. | ✅ `eb957b6` |
| 07 | Define the change data model | Stable, tested structured output. | ✅ `24d3746` — top-level object revised by D-029 |

### Phase 3 — Meaning and reporting (sessions 8–11)

| # | Session | Done when | Status |
| --- | --- | --- | --- |
| 08 | ~~Classify changes conservatively~~ | — | 🔁 **superseded by CON-40…43.** Classification by code signal was dissolved: D-034 removed flags, D-038 removed migrations, D-035 established that a rule is a business statement no signal can produce. |
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
| 4 | Choose the first sample Git repository. Prefer a small project you own and can safely analyse. | ✅ Subjects A and B — D-009 |
| 5 | Agree on the first CLI command and its acceptance criteria. | ✅ Session 03 — every command has stated acceptance criteria |
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
