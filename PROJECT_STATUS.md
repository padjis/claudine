# Project status

**Last updated:** 2026-11-11
**Current phase:** Phase 3 — Meaning and reporting (reshaped by D-035 … D-039)
**Current session:** CON-42 — rule generation (CON-40, CON-41, CON-45 and CON-46 closed)

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
the document states that no rules were *identified* rather than implying none exist. Generation is
CON-42. No Markdown report is rendered yet: CON-09.

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

**CON-42 — rule generation.** An AI pass proposes rules, behaviours and anchors from a ticket's
evidence, all as `ai_interpretation`. The seam, the payload and the no-provider path exist; what is
missing is a provider in the registry and a prompt.

Before writing it, two things CON-41 measured should shape the design rather than surprise it:

1. **Payload size is a design constraint, not a detail.** 8 commits in *one* repository produced
   ~47,000 tokens. D-039 called the cost real; that is the number. The registered set is plural by
   construction (D-027), so this scales the wrong way.
2. **The safety gates are now in place.** Identity does not cross the boundary (D-040) and a
   credential-bearing payload is refused (D-044). CON-42 is no longer gated on either — what gates
   it is whether anyone wants the output.

And the standing reminder: validation is still at **zero discovery conversations** (CON-26). CON-42
is where this project starts paying a provider, with nobody yet asked whether they want the output.

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
