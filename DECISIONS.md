# Decision log

Append-only. Newest first. Never rewrite a decision — supersede it with a new entry that references
the old one.

Format: `## D-NNN · YYYY-MM-DD · Title` → **Decision**, **Context**, **Consequences**, and
**Status** (`accepted` / `superseded by D-NNN`).

---

## D-055 · 2026-11-12 · The MCP server exposes four tools, and acceptance is not one of them

**Implements D-045.** `constat mcp` runs an MCP server on **stdio**.

**Decision.** Four tools: `gather_evidence`, `get_payload`, `submit_rules`,
`list_rule_proposals`. **There is no `accept` or `reject` tool**, and the tool list is asserted in
a test so the absence cannot be lost quietly.

The `mcp` SDK is an **optional extra** (`pip install constat[mcp]`), not a runtime dependency.

**Context.** `CLAUDE.md` prohibits marking a proposal approved without a recorded human decision,
and product rule 4 makes generated content a proposal rather than knowledge. A model that could
call `accept` would make both unenforceable — not by malice, but because the tool would be there.
Acceptance therefore stays a human act at the CLI, outside the agent's reach.

**Consequences.**

- **An absence is the easiest property to lose**, so it is tested on the *live* tool list rather
  than by reading the source. A tool added by a decorator anywhere shows up there.
- **Stdio, not HTTP.** The client spawns Constat as a subprocess and nothing listens on a port,
  which is what keeps this a local tool rather than the hosted service `PRODUCT_SPEC.md` § 6.2
  defers — and means no authentication layer, which § 6.2 also defers.
- **No tool reimplements an operation.** Every one calls the same function the CLI does, so the
  gates hold by construction: identity never crosses (D-040), the credential gate fires on
  `get_payload` because that *is* `export_payload` (D-047), and a submitted reading is grounded
  against re-gathered evidence (D-052). Tested through a real client, not only in process.
- **Constat's errors become `ToolError`, deliberately.** That is the SDK's "a failure you
  anticipated", and it keeps the message. Letting a `ConstatError` escape gets it wrapped as an
  unexpected crash and the client sees only "Error executing tool get_payload" — losing "remove
  the credential and rotate it", which is the only part worth sending.
- **The optional extra keeps the promise in D-003**: the evidence pipeline runs with nothing but
  pydantic installed, and a CLI user carries no protocol library they never run.
- **The server tells the model its output is provisional.** The instructions say nothing submitted
  is accepted and that no tool here can accept — a model that believes otherwise will present a
  reading as settled.
- The workspace is opened per call rather than held for the session: a session outlives any one
  operation, and a long-lived connection to a governance store is a lock waiting to be contended.

**Status.** accepted

---

## D-054 · 2026-11-12 · A reading may claim to revise a rule it was shown

**Closes the finding half of CON-43.**

**Decision.** The payload carries the catalogue — each rule's id, name, statement and anchors. A
reply may name `revises: <rule_id>`, and that claim is validated the way an anchor is: the rule
must have been in the payload. For readings that claim to be new, anchor overlap is computed and
**reported as a candidate**, never applied.

**Context.** A reading had never been shown what exists, so every reading claimed to be new and the
second reading of a rule created a duplicate — CON-43's failure arriving by a different route. The
missing piece was an input, not logic.

**Consequences.**

- **An invented `revises` is rejected like an invented anchor.** A reading cannot have read a rule
  it was never shown, so claiming a relationship to one is inventing it rather than observing it.
  The symmetry is deliberate: both are the model asserting something the evidence does not support.
- **A booleans check is not pedantry.** `True` is an `int` in Python and would otherwise pass as
  rule id 1.
- **Overlap warns and never decides** (D-050). A reading that claims to be new is stored as new,
  and the reviewer is told what it overlaps. Rewriting the claim would be exactly the structural
  key D-050 refused — and accepting a second rule on the same file is often correct, since one file
  routinely implements several rules.
- **A claimed revision is not flagged.** It already decided; warning about it would be noise.
- **An honest limit, asserted in a test.** Overlap is *identical glob string*, not glob
  intersection. A rule anchored to `rules.py` and a reading anchored to `**/*.py` overlap in
  reality and are not flagged. Widening it means comparing globs for intersection, which has no
  exact answer in general, and a warning that fired on every broad glob would be noise.
- The catalogue in the payload carries no identity, so D-040 is unaffected — it is the user's own
  rules, not evidence about people.

**Status.** accepted

---

## D-053 · 2026-11-11 · Accepting a rule proposal baselines a version; rejecting changes nothing

**Closes CON-44, and most of CON-43.** Schema 6.

**Decision.** `rule_version` is a frozen snapshot of a rule at the moment a human accepted a
reading of it, append-only by trigger. `rule` remains the current state — the same split
`document`/`document_version` already uses (D-029). Accepting a reading that claims to revise a
rule appends the next version; accepting one that claims to be new creates the rule at version 1.

**Rejecting changes nothing in the catalogue.** Under D-036 it means *inconclusive*, so there is
nothing to unwind, and a rejected reading can still be accepted later.

**Context.** Rule proposals could be stored but never acted on. D-037 required acceptance to be
per-rule and human; this is that act, and it is the only way a rule enters or changes (D-048).

**Consequences.**

- **Every rule version names the reading it came from** (`from_rule_proposal_id`), and that
  reading names the run whose evidence it read (D-049). A rule is therefore traceable to a diff
  without storing the diff.
- **A revision is a version, not a duplicate** — CON-43's done-when. It works because
  `revises_rule_id` is the reading's claim and a human accepting the reading accepts the claim
  (D-050). Acceptance is the only place the claim takes effect.
- **A name may change between versions** and the rule stays one rule, which is what D-050's
  surrogate identity was for.
- **`rule` is mutable and that is deliberate**, for the same reason `document.body` is: it is the
  working view, and the durable record is the frozen version beside it. Behaviours and anchors are
  replaced on acceptance; their history lives in `rule_version_behaviour` / `_anchor`.
- **Accepting twice is refused** — it would baseline a second identical version.
- **A claim to revise a rule that does not exist cannot even be recorded**: the foreign key refuses
  it. `Review._target_rule` refuses it again at acceptance, unreachable while the key holds and
  kept because the alternative — silently creating a *new* rule when the reviewer accepted a
  revision — is exactly the duplicate CON-43 exists to prevent.
- **`--by` has no default.** There is no way to accept without naming who decided, which is the
  no-automatic-approvals prohibition expressed in the argument parser.
- Rules that predate acceptance keep no version. They were never accepted, and inventing one would
  fabricate an approval.

**Status.** accepted

---

## D-052 · 2026-11-11 · A submitted reply is grounded against re-gathered evidence

**Decision.** `constat rule submit <REF>` takes a reply produced outside Constat and stores the
rule proposals that survive grounding. Three rules shape it:

1. **The evidence is re-gathered, never taken from the caller.** Grounding is checked against what
   Constat can see now.
2. **No credential gate.** The payload is rebuilt locally and never transmitted, so there is
   nothing to refuse. The gate belongs on egress (D-047).
3. **Nothing is accepted.** Submitting fills the review queue; the catalogue is untouched.

**Context.** D-045 made the host supply the model, so Constat needs an inbound path. `parse` takes
`(text, payload)` and does not care where the text came from (D-046), so everything after the reply
is the provider path's machinery unchanged.

**Consequences.**

- **A caller cannot widen its own grounding set.** If the payload came from the caller, a reply
  could ship a payload that makes any anchor look grounded — the check would verify the reply
  against itself.
- **Parsing happens before the run is opened**, so an unusable reply leaves no empty event behind.
- `provider` and `model` are self-reported and recorded as such (D-045). Nothing verifies them.
- **Discards are printed before the kept count.** A reader shown only what was stored has been told
  a shorter truth than what happened (D-046).
- **One matcher, shared.** Grounding and catalogue matching now both use `constat/globs.py`. Two
  matchers that disagreed would accept a rule proposal at submit time and then never match it to a
  change, or the reverse.
- **`**/x.py` also matches at the root.** Plain `fnmatch` requires a directory after `**/`, so a
  model writing the most natural "this file anywhere" glob would have been rejected as ungrounded.
  A false rejection here is the same failure as a false credential positive: it teaches people to
  stop reading the rejections.
- The document body still reflects the run that wrote it, so a submitted reading is stored but not
  rendered there. `rule proposals <REF>` shows the queue; rendering from stored readings belongs
  with the display work.

**Status.** accepted

---

## D-051 · 2026-11-11 · A rule proposal is stored append-only; its decision is a separate record

**Implements D-048 and D-050.** Schema 5.

**Decision.** `rule_proposal` stores each reading with its run, its self-reported reader
(`provider`, `model`) and its claim about which rule it revises. `rule_proposal_decision` stores a
human's answer separately. Both abort `UPDATE` and `DELETE` by trigger; so does `rule`.

**Context.** A rule proposal previously lived for one `gather()` call and was rendered into a
document body that the next run regenerates — so a reading could not survive long enough for
anyone to accept it. D-037 makes acceptance per-rule and human, which requires durable
pre-acceptance state.

**Consequences.**

- **A decision does not mutate the reading**, the shape `document_version` uses (CON-31).
  Accepting leaves the reading exactly as the reviewer saw it.
- **Changing one's mind appends.** Both decisions stay visible; the latest is what displays.
  History rather than a correction to be hidden (product rule 5).
- **`revises_rule_id` is nullable and is a claim, not a key** (D-050). Null means the reading
  claims to be new.
- **An anchor naming an unregistered repository keeps its glob and loses its scope.** Losing the
  reading would be worse than losing the scope.
- **`rule.name` lost `UNIQUE`,** which needed rebuilding `rule` plus its two cascading children —
  dropping the parent alone would have taken the catalogue with it. Verified: a real v4 workspace
  migrated with its rows intact.
- **One half has not moved.** `Catalogue` is still name-keyed: `add_rule` keeps an
  application-level duplicate guard and `find` looks up by name, so two rules cannot yet share a
  name through the API even though the schema allows it. That guard is a leftover of the pre-D-050
  model and goes when the catalogue becomes id-keyed and versioned (CON-43). Recorded rather than
  quietly left.
- Acceptance does not yet write into the catalogue — that needs the versioned rule table, and
  lands with the acceptance flow (CON-44).

**Status.** accepted

---

## D-050 · 2026-11-11 · Anchors match a rule; they do not identify it

**Decision.** A rule has a **stable surrogate identity** that survives renames, restatements and
anchor drift. Anchors are the **candidate matcher**: overlapping anchors mean "this rule proposal
may revise that rule". Whether it actually does is an **AI judgment carried as
`ai_interpretation`**, accepted or rejected by a human like any other interpretation — not a
database key.

`rule.name` loses its `UNIQUE` constraint. A name is a label that may change between versions, not
an identity.

**Context.** Identity had to come from somewhere, and the name is the wrong place: AI-generated
names drift between runs, so a `UNIQUE` name would fork one rule into two whenever the wording
changed. Anchors are the better signal — a rule is identified by where it lives rather than what it
is called.

But anchors cannot be the key. **One file routinely implements several business rules** — a
`limits.py` can hold both a daily transfer limit and a per-merchant cap — so an anchor-set key
would collapse distinct rules into one, failing in the opposite direction from duplicates. Path
globs are too coarse to be unique per rule, and making anchors finer (symbol or line level) would
be a change to the evidence layer for a benefit a judgment call already provides.

**Consequences.**

- **CON-43 becomes a proposal, not a lookup.** "Evidence contradicting a baselined rule proposes an
  update rather than a duplicate" is now: find candidates by anchor overlap, let the interpretation
  pass say which rule is revised, and let a human accept that. The hardest part of D-039 stays hard,
  but it stays *reviewable*, which a key would not have been.
- **A wrong match is recoverable.** It is a rejectable interpretation rather than a corrupted
  identity, so the failure mode is a bad suggestion instead of a merged pair of unrelated rules.
- **The match itself must be reported.** "This was treated as a revision of rule X" is a claim a
  reviewer has to see, for the same reason discarded rule proposals are listed (D-046). A silent
  match would hide the one judgment most likely to be wrong.
- A rule proposal records which rule it claims to revise; null means it claims to be new.
- The versioned rule table (CON-51, merged with CON-43 per D-048) hangs off the surrogate id, so
  supersession is independent of both the name and the anchor set.
- Several rules sharing an anchor is normal and expected, not a conflict to resolve.

**Status.** accepted

---

## D-049 · 2026-11-11 · A run has an identity; operations belong to one

**Decision.** Schema 4 adds a `run` table — one row per invocation that touched a document, with
its kind and start time — and `operation.run_id`. A gather opens one run regardless of how many
repositories it reads.

**Context.** A gather writes one `operation` row *per repository*, so no operation row can answer
"which run produced this". A rule proposal is a reading of the evidence one run gathered (D-046),
so it needs a single thing to reference. Nothing existed to reference.

**Consequences.**

- **Rows written before schema 4 keep `run_id` NULL.** Back-filling a run for them would
  fabricate provenance — they were written when runs did not exist, and saying so is the honest
  record. Verified on a real workspace: 7 pre-migration rows stayed NULL across the migration.
- **An export opens a run only when it accepted scan findings.** An export that found nothing made
  no decision, and recording it would put an empty event in the audit trail.
- A scan override joins the run whose evidence it let through — the override and the payload are
  one event, not two.
- `run_id` is on the result objects, so a caller does not have to re-query and guess which row is
  its own.
- This unblocks CON-51: a rule proposal can now say which run it read.

**Status.** accepted

---

## D-048 · 2026-11-11 · Rules are only AI-generated, and the catalogue is append-only

**Supersedes D-039's manual-command carve-out**, which kept `rule add` / `behaviour` / `anchor` as
a bootstrap and test path.

**Decision.** Two halves of one simplification:

1. **A rule enters the catalogue only as an accepted rule proposal.** There is no human-authored
   path. The `rule add`, `rule behaviour` and `rule anchor` commands go.
2. **A rule cannot be removed.** `rule remove` goes, `Catalogue.remove_rule` goes, and a
   `BEFORE DELETE ON rule` trigger aborts the operation — enforced by the database, not by the
   absence of a command.

`rule list` and `rule show` stay; they are read-only. `Catalogue.add_rule` and friends stay as the
*storage* API the interpretation path writes accepted rule proposals through — what is removed is
the human-facing surface, not the ability to store.

**Context.** D-039 already made AI the author and kept the manual commands only as scaffolding.
Keeping them meant two authorship paths, two provenance stories, and a question — "who wrote this
rule?" — that the taxonomy had to answer twice. Removing them deletes the question.

Removal went for a different reason. The project's own pattern is that integrity lives where it
cannot be bypassed: `document_version` aborts `UPDATE` and `DELETE` by trigger precisely so a
future bug cannot rewrite an approval by forgetting to call the right helper (CON-31). A catalogue
that can be emptied by a `DELETE` is protected by convention only.

**Consequences.**

- **Supersession replaces removal, and this is the load-bearing consequence.** CON-43 already
  requires that evidence contradicting a baselined rule *propose an update rather than a
  duplicate*. With no deletes, that update is a **new version**, not a mutation. A wrongly
  accepted rule is therefore permanent as *history* and replaceable as *current* — which is
  product rule 5 working as intended rather than a trap.
- **The rule catalogue needs the versioned shape `document_version` already has.** That makes
  CON-43 and CON-51 the same schema change: append-only versioned rules, written only by accepted
  rule proposals. Schema v4, with a migration.
- **A bootstrap gap, stated rather than discovered.** With the provider registry still empty
  (CON-41), nothing can put a rule in the catalogue, so `unmatched_paths` coverage is unreachable
  from the CLI until the interpretation path completes. Tests exercise it through the storage API
  directly. This is a real loss of a manual smoke path, accepted deliberately.
- 8 CLI tests covering the removed commands go with them; the 24 catalogue tests call the storage
  API and are unaffected.
- **"Rule proposal", never bare "proposal."** A rule proposal is a rule in a pre-acceptance state,
  not a separate kind of object — and after this decision it is the *only* way a rule comes into
  being, which makes the naming load-bearing rather than stylistic.

**Status.** accepted

---

## D-047 · 2026-11-11 · Every path where the payload leaves goes through one gate

**Decision.** `guard_release(payload, accepted=…)` is the single chokepoint for any path where the
payload leaves the process. It scans and raises `PayloadRefused` unless a human accepted the
findings for that run. `constat document <ref> --payload` is the first caller besides `gather`.

**An export refuses unconditionally**, where `gather` with no provider scans, reports and
continues. That asymmetry is the decision: a local run that transmits nothing can tolerate a false
positive, and an export cannot, because by the time it has printed it has left.

**Context.** D-044 gated the provider path, keyed on `provider.name != NULL_PROVIDER_NAME`. D-045
then created a second front door — the host supplies the model, so the payload has to be handed
out — and that door bypassed both D-040 and D-044 entirely. A gate covering one of two doors is
decoration.

**Consequences.**

- **It raises rather than returning a flag.** A caller that forgets to check a boolean still sends
  the payload; a caller that forgets to catch an exception does not.
- **Export writes nothing** except an override record. A reader that mutated the governance record
  would make the document depend on who looked at it.
- **An export override is recorded under its own kind** (`scan_override_export`), distinct from a
  send override. Two different disclosures; collapsing them loses which one a reviewer is seeing.
- **`collect()` is shared** by both paths, so a reviewer and a model cannot be looking at different
  evidence for the same ticket. A test asserts the two payloads are identical.
- **Any future egress path inherits this obligation** — a submit command that echoes the payload,
  an MCP resource, a debug dump. The gate exists so the answer is "call `guard_release`" rather
  than "remember D-040 and D-044".
- Verified on real data: Subject B exports cleanly with no identity field present; Subject A is
  **refused with zero bytes on stdout**, having real credentials in the window. Without this the
  export would have handed them to a third-party model.

**Status.** accepted

---

## D-046 · 2026-11-11 · A provider reply is parsed, grounded and refused — never silently emptied

**Decision.** `constat/ai/parsing.py` converts a provider reply into `RuleProposal`s under three
rules:

1. **A reply that cannot be parsed raises `MalformedResponse`** (exit 5), never returns zero
   proposals. Empty, prose, broken JSON, JSON with no `rules` key, and `rules` that is not a list
   are all errors.
2. **Every anchor must match a path actually present in the payload**, and any
   `repository_alias` must name a repository that was searched. An ungrounded proposal is
   rejected whole, with a reason.
3. **Rejections are reported** — in the `ParseResult`, on the `Interpretation`, in the document,
   and in the CLI summary.

**Context.** Rule 1 is D-041's principle applied one layer in: a parse failure that returns
nothing makes the document read "no rules were identified", which is a provider failure wearing
the costume of a finding.

Rule 2 is the one with teeth. A model will propose a rule anchored to a plausible-sounding path
whether or not that path was in the payload; storing it would mean the tool had **invented its own
evidence**, which is the exact inverse of product rule 2. Grounding is checkable for free, so it
is checked.

**Consequences.**

- **A rejected proposal keeps only its name and the reason.** The rest is unvalidated model
  output, and storing its text would put unattributable prose into a governance record.
- **One ungrounded anchor rejects the whole proposal**, rather than keeping the grounded half.
  Silently narrowing a rule the model meant more broadly is a different claim, not a smaller one.
- **An unanchored proposal is rejected**, because a rule with no anchors can never be matched to a
  future change (CON-40) — inert rather than merely incomplete.
- Code fences are unwrapped and bare-string anchors accepted. Pragmatism about how models
  actually reply; the content inside still has to parse and still has to ground.
- `name` and `statement` are length-bounded. An unbounded statement lets a model write a page of
  prose into a field a reviewer reads in a list.
- **This module is provider-agnostic on purpose.** It takes `(text, payload)` and does not care
  whether the text came from an HTTP response or from an agent in the same terminal — which is
  what makes D-045 cheap.
- Verified on both real subjects (30 and 72 grounding paths): a grounded reply is kept, an
  invented anchor is rejected, a prose reply is refused.

**Status.** accepted

---

## D-045 · 2026-11-11 · The agent-facing surface is an MCP server, not a skill

**Decision.** Constat's agent-facing surface will be an **MCP server**. A Claude skill is not the
target. The interpretation pass may therefore be driven by a *host-supplied* model rather than by
a provider Constat calls itself, and the `Provider` protocol (D-003, CON-41) is not the seam that
gets used in that mode.

**Context.** Two separate forces, and the second corrected an earlier recommendation of mine.

**Cost.** `CLAUDE.md` postpones the finished product's API calls until the workflow is validated,
and validation stands at zero discovery conversations (CON-26). If the host supplies the model,
the subscription is the inference and CON-42's HTTP client may never need to exist.

**Portability.** A skill is an *instruction-packaging format*, portable only to runtimes that
implement it — several surfaces, one vendor. **MCP is a protocol**, and is the mechanism that
actually crosses implementations. "Works across AI implementations" is an MCP question; a skill
was the wrong answer to it.

**Consequences.**

- **The prerequisite work is identical either way**, so the surface choice costs nothing to defer:
  a submit command that runs D-046's parser, a payload-export command, and provenance handling.
  The server is a thin shell over those.
- **A hole this opens, and a prerequisite.** Redaction (D-040) and credential refusal (D-044)
  currently gate on `provider.name != NULL_PROVIDER_NAME`. An export or submit front door would
  bypass both — the same gate must apply there, or D-040 and D-044 are decorative.
- **Provenance degrades, and must be recorded as degraded.** With a host-supplied model, the
  model's identity is *self-reported* by the client. That is nearer `assumption` than
  `observed_fact` and must never be stored as the latter.
- **Control inverts.** Constat stops orchestrating and becomes a service: it cannot guarantee an
  interpretation pass happened, only validate what it is handed. Acceptable, because it never
  trusted that output — grounding is checked (D-046) and acceptance is still human (D-036).
- **Approval is never exposed as a tool.** A model that can call `approve` would make the
  no-automatic-approvals prohibition unenforceable. Acceptance stays a human act outside the
  agent's reach.
- MCP over stdio is a local process, so this is not the hosted service `PRODUCT_SPEC.md` § 6.2
  defers — but it is new infrastructure, and the ticket needs agreeing before it is built.
- The portability *floor* remains the CLI: any agent can be told to run a command. A skill would
  only ever have been a convenience wrapper.

**Status.** accepted

---

## D-044 · 2026-11-11 · Credentials are detected by format; a refusal is overridable on the record

**Completes D-040**, which stopped identity crossing the provider boundary and stated plainly that
credentials in messages and diffs were not solved.

**Decision.** The payload is scanned for credentials before it is sent. Detection is by **known
format only** — issuer-specified prefixes and lengths, PEM headers, JWT structure, passwords in
connection strings, and credential-named assignments whose value survives a placeholder, code and
character-variety test. Entropy scoring is not used.

A payload with findings is **refused** (`PayloadRefused`, exit 5). The refusal is overridable with
`--accept-scan-findings`, which applies to one run only and is recorded in the document as a
`human_decision` and as a `scan_override` operation.

**Scanning runs on every run; refusal applies only when a provider would actually receive the
payload.** Those are deliberately separate.

**Context.** Entropy scoring catches more and is the wrong trade here. It fires on minified
JavaScript, lockfile integrity hashes and base64 assets, all abundant in the subjects. In a
governance tool a false refusal blocks real work until someone overrides it, and the second time
that happens the override stops being read. A detector that is nearly always right is worth more
than one that catches more.

**Consequences.**

- **The scanner must not become the leak.** A finding records repository, commit, path, line and
  detector — never the matched text. Anything else would copy the credential into the workspace and
  from there into every frozen version of the document, outliving the repository it came from. Four
  tests assert the secret is absent from the finding, the error message, the document body and the
  stored override record.
- **Separating scan from refusal keeps two things true.** A false positive cannot block a local run
  that sends nothing, and the scanner is not dead code until a provider exists — the mistake D-040
  avoided by running redaction on the default path.
- **An override with no record is the same as no scan**, so it is written to the document and to
  the operation log. It is per-run by construction: there is no stored state to make it sticky.
- **Refusal happens before `interpret` and before the document is written.** A partially written
  document would record evidence as if the run had succeeded.
- **Stated misses, in exchange for believable refusals.** A passphrase of one character class is
  not detected; nor is a base64 credential beginning with `+`; nor any credential with no
  recognisable shape. `scan` returning nothing is **not** a statement that the payload is clean,
  and the document says so rather than implying a clean bill of health.
- **Validated on real evidence, which changed the implementation.** A first pass over real commits
  produced a false positive — a `token`-named variable assigned an expression — and a second over a
  wider sample produced true positives. The code-expression rule exists because of the first; the
  second is why the feature exists. Per the repository owner's instruction, nothing identifying
  what was found is recorded in this repository: findings belong in a workspace, not in a public
  decision log.
- A "bare identifier" rejection rule was tried and removed: a real credential and a variable name
  are the same shape. Character-class variety does that work instead, with a stricter threshold for
  unquoted values, since quoting is the only available signal that a value is a literal — and it
  cannot be required, because a `.env` file has none.

**Status.** accepted

---

## D-043 · 2026-11-10 · The document is written only by AI; humans comment, validate or reject

**Amends D-029's authorship of the draft**, which had humans editing the document body directly.

**Decision.** The document body is machine-written, always. A human never edits it. Human input
takes exactly three forms:

| Action | Effect |
| --- | --- |
| **Comment** | Free text attached to the document or to one of its parts. Never becomes document content; it is input to the next regeneration. |
| **Validate a business rule** | Per-rule acceptance (D-037). The rule migrates into the baseline. |
| **Reject an implementation** | Inconclusive, not wrong (D-036). Another PR is expected. |

Amendments are requested by commenting, not by typing into the body. The AI rewrites; the human
directs and decides.

**Context.** Two problems dissolve at once.

The first is **CON-39**, raised as a hazard at CON-34 and recorded as blocking CON-12: the body is
regenerated on every run, which destroys anything a reviewer wrote into it. If nobody writes into
it, there is nothing to destroy. The hazard was a consequence of mixed authorship, not a flaw in
regeneration.

The second is **provenance**. A document that is part machine-derived and part hand-edited has no
way to say which sentence is which, and product rule 3 requires exactly that. Single authorship
makes every sentence in the body attributable by construction, and human intent stays in comments
and decisions where it carries its own category.

**Consequences.**

- **CON-39 is not withdrawn; it is transformed.** The residual problem is real and is the same
  class: a comment is anchored to something, and regeneration rewrites the thing it is anchored to.
  A comment attached to a rule survives if it is anchored to the rule's identity; a comment
  attached to a line of rendered prose does not survive the next run. **Comment anchors must be
  durable identities, not positions in text.** This is now CON-39's actual content, and it still
  gates CON-12 and CON-44.
- **Free text gets a home without contradicting D-032.** D-032 dropped the ticket title because
  unverified human free text had no category in the taxonomy. A comment is not a counter-example:
  it is never a claim *in* the document, so it asserts nothing. It can only influence what the AI
  writes next, and whatever the AI then writes is still `ai_interpretation` requiring acceptance.
  A comment carries no authority and makes no assertion about the product.
- **The "no automatic approvals" prohibition gets easier to hold.** The body cannot contain an
  approval, because the body is machine-written and machine output is a proposal by definition
  (product rule 4). Authority lives only in validated rules and frozen versions.
- **Rejection does not edit anything either.** It records that the implementation is inconclusive
  and expects another PR (D-036). It does not mark the write-up wrong.
- The `Document` docstring in `models.py` said "humans edit it". Corrected.
- New scope: comments must be stored, attributed and durable — **CON-47** — and must reach the
  interpretation pass so that commenting actually changes the next draft — **CON-48**. Without
  CON-48 commenting is a suggestion box.

**Status.** accepted

---

## D-042 · 2026-11-10 · Packages are discovered, never listed

**Decision.** `pyproject.toml` configures `[tool.setuptools.packages.find]` with
`include = ["constat*"]` and `namespaces = false`. An explicit `packages = [...]` list is not used.
A test asserts the configuration is a `find` directive, that every package directory on disk
matches an include pattern, and that a wheel built from a staged copy of the source contains every
module and imports on its own.

**Context.** The explicit list said `packages = ["constat"]`, which setuptools took literally: from
CON-04 onwards every subpackage — `git`, `store`, `evidence`, `ai` — was dropped from the wheel. No
test noticed for five tickets, because the development install is editable and imports from the
working tree. A built wheel would have failed at the first `from .store import …`. Found while
verifying an unrelated claim about dependencies (CON-46).

The deeper point is the failure *shape*: forgetting to extend a list produces a silently broken
artefact rather than an error. Discovery cannot forget.

**Consequences.**

- A new subpackage is shipped without anyone remembering anything.
- `namespaces = false` stays, or any directory — including `__pycache__` — becomes a package.
- **Two testing traps are recorded here because both produced a false pass**, and both would
  silently return if the test were rewritten:
  - setuptools stages into `build/` and never cleans it, so an in-tree build includes modules left
    by earlier builds. With the defect restored, building in place still produced a complete wheel.
    The test builds from a staged copy.
  - The editable install registers a meta path finder through a `.pth` file that claims `constat.*`
    from the working tree, ahead of `sys.path`. The import probe loaded `cli` from the wheel and
    `store` from the repository, passing against a wheel containing no `store`. The probe runs with
    `-S` so `.pth` files are skipped.
- CON-20 ("package the MVP") rests on this. It was not going to be discoverable at that point
  without it, since nothing before CON-20 builds an artefact.

**Status.** accepted

---

## D-041 · 2026-11-10 · A provider misconfiguration is refused, never reported as a finding

**Decision.** If `CONSTAT_AI_PROVIDER` names a provider that is not implemented, or an implemented
provider's credential is absent from the environment, Constat **fails** — exit code **5**, distinct
from 2 (input), 3 (repository) and 4 (workspace). It never falls back to the null provider.

Credentials are read from the environment only. The workspace may record *which* provider and model
produced a proposal, because a reviewer needs that provenance; it never records the key.

**Context.** The tempting behaviour is to degrade gracefully: if anything about the provider is
wrong, use the null provider, and nothing ever breaks. What that actually produces is a document
reading "no rules were identified" for a user who believed they had configured a provider — a
configuration fault wearing the costume of a finding. That is product rule 1's failure mode exactly,
and it is worse here than a crash, because the output looks like an answer.

**Consequences.**

- The provider registry ships **empty** in CON-41. No provider is implemented until CON-42, and an
  empty registry is the honest way to say so — unlike an entry that exists and fails when used. The
  error names what is available, which is currently `none`.
- A fifth exit code is a cost. It is paid because the alternative is telling a user to check their
  repository or their workspace when both are fine.
- **The provider is resolved before any repository is read.** Resolving it last would mean reading
  every repository and collecting all the evidence before refusing. A test watches the collector
  rather than the document, because the document is written at the end either way and would not
  catch the regression.
- `ticket add` gathers too, so it carries the same exit code. A provider fault there leaves the
  ticket open with an empty document, which is recoverable by re-running `constat document` once the
  environment is fixed — a living document (D-029), not a lost one.

**Status.** accepted

---

## D-040 · 2026-11-10 · Identity does not cross the provider boundary

**Settles the question deferred by D-023** and required by it to be settled *before* a provider is
wired up, not after.

**Decision.** Nothing that identifies a person is sent to an AI provider. No author name, no
committer name, no email address, no authored or committed timestamp. The payload carries the
ticket reference, repository aliases, default branches, per-repository status, commit SHAs, commit
subjects and bodies, changed paths and diff text — and has **no field** in which identity could be
placed.

Two further rules follow, because stripping declared fields is the easy half:

- **Identity trailers are removed from commit messages.** `Signed-off-by`, `Co-Authored-By`,
  `Reviewed-by` and the rest are entirely a person, so the line goes. Any remaining address-shaped
  string in the prose is masked.
- **Addresses in diff text are masked, but no diff line is ever dropped.** A changed `AUTHORS`,
  mailmap or contributor list puts addresses in the evidence itself. Masking the address is correct;
  removing the line would misstate the change, and this boundary must not trade one dishonesty for
  another.

**Context.** Product rule 7 (least privilege) decides it once the question is put properly: rule
generation needs to know *what* changed and never *who* changed it. Identity therefore has no
purpose on the far side of the boundary, and sending it would be a personal-data disclosure with
nothing bought for it. Pseudonymisation was considered and rejected as the worst of both — still
personal data in the regulatory sense, for a grouping capability nothing asks for.

**Consequences.**

- **Redaction is not a flag.** An option to disable it would be disabled in the run that matters.
  The payload types are constructible only by going through `redact`.
- **Redaction runs on the default path**, with no provider configured, so the boundary is exercised
  by the ordinary workflow rather than first tested against a live API.
- **SHAs stay.** A sha identifies a commit, not a person, and without it a proposal could not be
  checked against the evidence that produced it (product rule 2).
- The guarantee is partly structural rather than behavioural, which is the stronger form: a future
  field-copying change cannot reintroduce an author without first adding the attribute to the type.
- **An honest limit on the real-data evidence.** Verified against 8 real commits in Subject B: zero
  address-shaped strings survive into the payload. But that range needed **no masking at all** —
  identity was absent structurally, and the trailer and diff-masking paths were exercised only by
  fixtures. Those paths rest on anticipating the case, not on having observed it here.
- **Commit messages and diffs still leave the machine.** That is the product, not an oversight, and
  it is what a prospective user must be told before a provider is enabled. Secret-scanning the
  payload is *not* solved by this decision and is not claimed to be.

**Status.** accepted

---

## D-039 · 2026-11-10 · Rules are generated and maintained by AI, stored in the catalogue

**Supersedes D-038's authorship.** The catalogue stays; people do not write it.

**Decision.** Business rules, their behaviours and their anchors are **generated and maintained by
an AI interpretation pass** over collected evidence. The catalogue is where they are stored and
versioned. Humans do not author rules; they **accept or reject** them (D-036), and accepted rules
migrate into the baseline (D-037).

**Context.** D-038 chose a human-declared catalogue to avoid recurring API cost before validation.
That is reversed deliberately: a catalogue only ever contains the rules someone remembered to
declare, and the drift between a hand-maintained catalogue and the code is the disease this
product exists to treat. Having Constat suffer from it would be self-defeating.

**Consequences.**

- **Provenance is corrected.** D-038 reasoned that a human-written statement is `requirement_ref`.
  Generated rules are **`ai_interpretation`** — proposals, visibly uncertain, carrying no
  authority until accepted. The governance model already enforces this; the taxonomy entry simply
  changes.
- **AI stops being optional for the core output.** D-003 keeps the provider interface and keeps
  the *evidence* path provider-free, so Constat still runs without a key — but with no provider
  there are no rules, only evidence, and it must say so rather than imply none exist.
- **This is now the roadmap's top risk made concrete.** The plan says to postpone AI API calls
  until the workflow is validated, and validation stands at zero discovery conversations
  (CON-26). The cost is real: evidence is already 2000–4000 diff lines per range per repository.
  Proceeding is a deliberate choice, not an oversight.
- **"Maintained" means rules change as the code does.** A later ticket whose evidence contradicts
  a baselined rule must propose an update to that rule, not silently create a second one. That is
  harder than generation and is the part most likely to go wrong.
- The catalogue's coverage reporting matters more, not less. An AI pass will miss rules too, so
  changed files claimed by no rule must stay prominent.
- Manual `rule` commands are kept as a bootstrap and test path, not as the model. They are how the
  catalogue is exercised without a provider configured.

  > **Withdrawn by D-048** on 2026-11-11. There is no human-authored path into the catalogue, and
  > no removal either. Two authorship paths meant answering "who wrote this rule?" twice; the
  > bootstrap convenience was not worth it.

**Status.** accepted

---

## D-038 · 2026-11-10 · Rules come from a catalogue, not from code signals

**Supersedes the "deterministic spine" of D-010.** Feature flags went at D-034; SQL migrations go
now; nothing replaces them.

**Decision.** Business rules live in a **catalogue** held in the workspace. Each rule carries its
behaviours and a set of **anchors** — the paths in registered repositories whose code is
understood to implement it. Rules are never inferred from code *signals* such as migrations or
annotations.

> **Authorship superseded by D-039.** This entry originally had people declaring the rules. They
> are generated and maintained by AI; the catalogue structure below is unchanged.

**Context.** D-035 settled that a rule is a business statement and a behaviour is a way the
application handles a business case. Neither can be read out of a migration or an annotation, so
the spine was never going to produce rules — only evidence. Migrations are irrelevant for the same
reason flags were: a schema change is a technical artefact that may accompany a rule change, or
may not, and treating it as one would report on the machinery again.

The alternative was an AI pass, deferred here on cost grounds and **chosen the same day in
D-039**. The cost concern stands and is recorded there rather than dismissed.

**Consequences.**

- **It works in any language.** Subject B is TypeScript with no migrations and no bean validation;
  under the catalogue it is served exactly as well as Subject A, which no code-derived signal
  could have managed.
- ~~Rule statements become authoritative rather than proposed.~~ **Corrected by D-039:** generated
  rules are `ai_interpretation` — proposals carrying no authority until accepted.
- **Status is computed at the level of evidence, never meaning.** Constat can say "the code
  anchored to this behaviour changed in this ticket"; it cannot say what the behaviour now *is*.
  The reviewer supplies that. This is D-012's drift reasoning applied to rules: a signal, never a
  verdict.
- **Changes covered by no rule must be reported prominently.** This is the catalogue's failure
  mode: it only knows the rules someone declared, so a ticket touching ten files where only two
  are anchored must say so loudly. A document listing two impacted rules while silently ignoring
  eight unanchored files would be exactly the confident under-report this product exists to
  prevent.
- The catalogue drifts from the code — the disease Constat treats. This is the specific weakness
  that D-039 reverses authorship to address: a hand-maintained catalogue would have drifted by
  construction.
- `NEW` and `REMOVED` behaviours come from review, not detection: the reviewer adds a behaviour
  the implementation introduced, or marks one whose anchor has gone.

**Status.** accepted

---

## D-037 · 2026-11-10 · Accepted rules migrate into the baseline

**Decision.** When a reviewer accepts a rule change, that rule is **migrated into the main
baseline** — the approved description of how mainline behaves. A later gather compares the
ticket's rules against the baseline, not against a fresh reading of mainline.

**Context.** Answers the question CON-39 raised: what happens to accepted rules when a document is
re-gathered. Nothing is re-litigated, because an accepted rule is no longer part of the proposal —
it has become approved product knowledge.

**Consequences.**

- This unifies three things that were separate tickets. The baseline (CON-14) *is* the accepted
  rule set; comparing against the last approved baseline (CON-15) *is* how NEW / CHANGED /
  UNCHANGED / REMOVED are computed; and drift (D-012) is a baseline rule whose supporting evidence
  has since moved.
- **`NEW` and `CHANGED` are relative to the baseline, not to mainline.** A rule absent from the
  baseline is new even if it has existed in code for years but was never documented. That is the
  correct meaning for a governance record: it tracks what has been *approved*, not what exists.
- Baseline versions stay immutable and append-only (D-029, enforced by trigger). Migrating a rule
  creates a new baseline version; it never edits the previous one.
- A rule accepted on one ticket and then changed by another will show as `CHANGED` against the
  baseline, which is exactly right.

**Status.** accepted

---

## D-036 · 2026-11-10 · Rejection means inconclusive, not wrong

**Decision.** Rejecting a document marks the attempt **inconclusive**: the implementation is
missing something and another pull request is expected. It is not a statement that Constat
described the change badly, and it is not a permanent verdict on the work.

A rejection carries **commentary** explaining what is missing. Comments are first-class, not a
single free-text rationale field.

**Context.** The schema's `decision` column allows `approved` and `rejected`, but "rejected" was
ambiguous between two very different signals: *the write-up is wrong* and *the change should not
ship*. The intended meaning is neither — it is "not done yet, iterate".

**Consequences.**

- The stored decision must say which it is, or a later reader cannot tell why work stopped. The
  vocabulary needs to carry "inconclusive — another PR expected" distinctly.
- Comments need their own storage, not a single `rationale` column: there may be several, attached
  to specific rules rather than only to the document as a whole.
- **Multi-person commenting is out of MVP scope.** Reviewer identity is asserted rather than
  authenticated (D-007), so "people commented" is a claim Constat cannot verify. One reviewer's
  comments are recorded as asserted; a real multi-user flow needs identity first.
- A rejected document is not closed. The ticket stays open, the next gather picks up the follow-up
  commits, and the rejection and its comments remain in history.

**Status.** accepted

---

## D-035 · 2026-11-10 · A rule is business-oriented; a behaviour is a way the app handles it

**Decision.**

- A **rule** is purely business-oriented and determines how the application behaves. Not a
  migration, not an annotation — those are *evidence for* a rule, never the rule itself.
- A **behaviour** is any distinct way the application handles a business case under that rule.

So "a transfer over the daily limit is refused" is a behaviour of the rule "daily transfer limit".
`@Size(max=250)` is evidence that such a rule exists, but is not itself either.

**Context.** This is the definition that makes the product its stated promise rather than a diff
viewer, and it settles what D-010's spine was for: migrations and validation constraints are
**evidence**, not rules.

**Consequences — one of them forces a decision deferred since D-003.**

- **Rules cannot be derived deterministically.** No amount of reading migrations or annotations
  produces "a transfer over the daily limit is refused". That sentence requires either
  interpretation or a human. The deterministic spine supports rules; it cannot generate them.
- Behaviours are branches of business logic, which are semantic rather than syntactic. Same
  conclusion.
- Combined with the requirement that the MVP work across more than one repository — Subject B is
  TypeScript, with no migrations and no bean validation — a deterministic-only extractor is ruled
  out on both counts.
- This is the roadmap's own "interpretation layer" arriving: *AI proposes impact and plain-language
  explanations, always tied to evidence and uncertainty*. It is consistent with the plan, provided
  output stays a proposal, carries `ai_interpretation` provenance, and is human-approved — all of
  which the governance model already enforces.
- What it does change is **D-003's "optional"**. Without a provider there can be no rules, only
  evidence. The honest shape is that Constat still runs and still reports evidence, but states
  plainly that no rules were identified — rather than implying none exist.

**Status.** accepted

---

## D-034 · 2026-11-10 · Feature flags are not a business rule source

**Amends D-010**, which listed feature flags as one of three deterministic rule-bearing signals.

**Decision.** Feature flags are removed from the rule model entirely. Constat will not derive
rules, behaviours or statuses from flag declarations, defaults or descriptions.

**Context.** A flag is a *control over* behaviour, not a statement of it. "This behaviour can be
switched off" is a delivery and rollout mechanism that any change might use; it says nothing about
what the rule is. Including it would have made Constat report on the machinery of shipping rather
than on the rules themselves — a generic property of software change, which is precisely what the
product is meant to rise above.

Two further reasons, both visible in Subject A:

- Many registered flags are plainly not rules. `padjis.app.version` with default `2.3.0` is
  configuration; so is an AI prompt template. A rule extractor that emitted those as "business
  rules" would bury real findings in noise.
- **The live value is not in the repository.** Flags are seeded into Redis via `setIfAbsent` and
  edited by operators at runtime (ADR-0001), so a changed default need not change behaviour at
  all. Constat could only ever have reported "the declared default moved", and reporting that as a
  behaviour change would have been unsupported certainty on the product's most sensitive surface.

The second point alone would have forced heavy caveating; the first makes the signal low-value;
the principle makes it wrong in kind. Removing it is cheaper than qualifying it.

**Consequences.**

- **The deterministic spine narrows to two signals**: schema/data migrations, and declarative
  validation constraints. That is thinner and should be stated plainly rather than implied away.
- **Coverage in a non-Java repository is now close to zero.** Subject B is TypeScript with no
  Liquibase migrations and no bean validation, so a rule extractor built on this spine will find
  nothing there. The document must say "no rule-bearing signals found" rather than "no rules
  changed" — the two are different claims.
- Nothing is removed from the code: CON-08 had not been built, so this changes a plan rather than
  an implementation. Caught before it cost anything.

**Status.** accepted

---

## D-033 · 2026-11-10 · Evidence is collected per commit, and `ticket add` fills the document

**Decision.** Two things, both about CON-34.

**Evidence is collected per commit, not as one cumulative diff.** For each commit attributable to
a ticket, Constat diffs it against its first parent and collects bounded evidence for that commit
alone.

**`ticket add` runs the gathering operation immediately.** Opening a ticket writes its document in
the same invocation; there is no intermediate state where a ticket exists with an empty document
that says nothing.

**Context — per commit.** A ticket's commits need not be contiguous. Diffing the first commit's
parent against the last would sweep in whatever else landed between them, attributing other
people's work to the ticket. There is no single revision range that means "this ticket's effect",
so there should not be a single diff pretending to be one.

The cost is duplication: a file touched by three commits produces three excerpts. That is accepted
because each hunk stays attributable to the commit that made it, which is the point of provenance
(product rule 3). A test builds exactly the trap — ticket work, an unrelated commit, more ticket
work — and asserts the unrelated file never appears.

First parent rather than merge base, for a merge commit: that yields what the merge brought in,
which is what the merge contributed.

**Context — filling on add.** The earlier shape ran the same search at `ticket add`, printed it,
and discarded it: `operation` stayed empty and the document stayed blank. Two implementations of
one idea, one of which persisted nothing. The ephemeral version is deleted.

**Consequences.**

- `constat document <ref>` remains, for re-gathering after new commits and for `--show`. It is a
  refresh, not a required first step.
- **`ticket show` reports stored state only** and no longer re-searches. A `show` that searched
  afresh could disagree with the document it was describing.
- The document body is **regenerated** on each run rather than appended to, so re-running does not
  duplicate findings. That is safe only while the body is entirely machine-derived. Once human
  editing exists (CON-12), regeneration would destroy edits — recorded as **CON-39**, and it must
  be solved before review ships.
- Excerpt limits apply per commit, so a ticket with many commits can capture more in total than a
  single range would. Every bundle states its own completeness, so nothing is hidden, but a
  document-wide budget may be wanted later.
- A commit with no parent (a root commit) has nothing to diff against. The reason is recorded on
  the commit rather than dropping it, since dropping would under-report silently.

**Status.** accepted

---

## D-032 · 2026-11-10 · A ticket has no title

**Decision.** A ticket is a reference and a creation time. There is no title field, and no
`--title` option. Schema bumped to version 2 with a migration dropping the column.

**Context.** The title was added for readability — `ticket list` showing bare `622`, `ADR-0019`,
`plans/0015` is hard to scan. But it is **unverified free text**, and the provenance taxonomy
(PRODUCT_SPEC.md section 7.1) has no category for one. The nearest, `human_decision`, is wrong: a
decision is an approval, not a note. A title appearing in a document could be read as established
when nobody checked it against anything — in a product whose entire discipline is separating what
is supported from what is asserted.

Two alternatives were considered and rejected: marking it as an unverified label (which keeps the
hazard and adds ceremony), and deriving it from evidence such as a branch name or the first
attributed commit subject (defensible, but it adds a field nothing needs yet; a derived label can
be rendered on demand without being stored).

**Consequences.**

- `ticket list` shows bare references. If that proves unreadable in practice, the fix is to render
  a label derived from attributed evidence at display time, not to store free text.
- **The first schema migration exists because of this**, which is the useful part. A governance
  tool that discarded stored decisions whenever its schema changed would contradict product
  rule 5 on exactly the surface where it matters most. Version bumps carry migrations; only a
  version with no migration path is refused.
- `executescript()` is not used for migrations: it implicitly commits, which would silently defeat
  the surrounding transaction and could leave a workspace half-migrated. Statements are listed and
  executed individually. Found by a test that failed with "cannot commit - no transaction is
  active".
- Tests build a real version-1 workspace, migrate it, and assert the row survives while the column
  does not. Asserting the version number alone would not have shown that data was preserved.

**Status.** accepted

---

## D-031 · 2026-11-10 · A ticket is expected to be merged, but not yet into mainline

**Refines D-030.** The commit set is not searched across all of history; it is searched in the
window between mainline and everything else.

**Decision.** Constat expects a ticket's work to be **already implemented and merged** — onto an
integration or release branch — but **not yet in mainline**. The commit set for ticket `T` is
therefore:

```
commits reachable from any ref, excluding those reachable from mainline,
that are attributable to T
```

In Git terms, `git log --all --not <mainline>`, filtered by the attribution rules in D-030.

**Why this formulation rather than a configured integration branch.** Naming one integration
branch per repository would need configuration, and would be wrong the moment work sits on a
release branch instead of `develop`. "Reachable from anything, but not from mainline" describes
the same window without naming it, and covers `develop`, `release/*` and a still-open ticket
branch identically. Subject A has `develop` *and* seven release branches; Subject B has release
branches and no `develop` at all, so no single configured name would have served both.

**Consequences.**

- **The search space is bounded and small.** Not "all 1130 commits" but "whatever is staged ahead
  of mainline", which is the set a reviewer actually cares about.
- **Three outcomes, which must not be conflated.** `unknown` is an acceptable result (product
  rule 1), and so is "already landed":

  | Outcome | Meaning |
  | --- | --- |
  | Commits found outside mainline | Documentable. This is the expected case. |
  | Commits found, but only in mainline | Already landed. Not nothing — a different answer. |
  | No commits anywhere | The reference matched nothing. Not "this ticket changed nothing". |

- **`ticket add` warns rather than refuses** when the expected case does not hold. A ticket may
  legitimately be registered before its repositories are, or before the attribution pattern is
  tuned. Refusing would make a tuning problem look like a missing ticket.
- **The ref a commit was found on is evidence and must be recorded.** "Found on
  `refs/heads/develop`" and "found on an abandoned branch" are different provenance (product
  rule 3), and only the first should carry weight.
- Searching `--all` includes remote-tracking and stale refs, so an abandoned branch can
  contribute. Recording the ref is what makes that visible rather than silently misleading.
- This is the assumption that makes mainline-only (D-028) coherent: there is divergence to measure
  precisely because the work has not reached mainline yet. Documenting *after* a mainline merge
  falls back to the attribution rules alone.

**Status.** accepted

---

## D-030 · 2026-11-09 · A ticket resolves to a commit set; mainline stays the reference

**Resolves CON-37.**

**Decision.** The *reference point* is always mainline (D-028 stands). The *target* is a **commit
set** attributable to a ticket, not a branch tip. A ticket's commits are resolved from, in order:

1. **A branch whose name encodes the ticket** — `feat/622-prune-dead-fcm-tokens` names ticket 622.
   Unambiguous while the branch exists.
2. **Commit-message references** — the configurable pattern from CON-29.
3. **An explicit commit list**, supplied by a human.

The effect of that set is expressed against the mainline tree.

**Context.** An integration-branch workflow was proposed as the answer, and in principle it works:
work on `develop` diverges from mainline, so there is something to measure. Checked against the
real subjects on 2026-11-09, it does not hold:

| Branch | Ahead of mainline | Behind |
| --- | --- | --- |
| Subject A `develop` | **0** | 1119 |
| Subject A `feat/622-…` | **0** | 10 |
| Subject A `release/…` | **0** | 362 |
| Subject B `release/1.2.0` | **0** | 182 |

Every branch is zero ahead; Subject B has no integration branch at all. Ticket 622's commit is
already in mainline, `merge-base(main, feat/622) == tip of feat/622`, and the diff between them is
**0 files**. Under branch-divergence alone, documenting ticket 622 would produce an empty
document while the work sits plainly in history.

Both teams also rebase rather than merge — 3 merge commits in Subject A's last 200, zero in
Subject B's — so a ticket's commits do not survive as a distinguishable merge group.

**Consequences.**

- This is the `commit_set` selection reserved in D-025, now required rather than speculative.
- **Already-merged work becomes documentable**, which matters because all of both subjects is
  already merged. Branch divergence alone would have made Constat unable to document its own
  primary test data — a failure that would otherwise have surfaced at CON-34.
- Branch-name resolution is a genuinely better signal than commit messages where it exists:
  unambiguous, and it does not depend on commit discipline. Only ~5% of Subject A's commits carry
  any reference at all.
- Resolution order matters and must be reported. A document has to state *how* its commit set was
  determined, because "the branch said so" and "a human listed them" are different provenance
  (product rule 3).
- A commit set may be **empty**, and that is a legitimate answer meaning "no commits reference this
  ticket" — not "this ticket changed nothing". The two must not be rendered alike.
- Prospective documentation still works and is still better: a ticket documented before it merges
  has a live branch, and approval freezes the version (D-029) so it survives the merge.

**Status.** accepted

---

## D-029 · 2026-11-09 · A ticket owns one living document, frozen on approval

**Supersedes D-025's proposal-per-run model.** D-025's identity reasoning survives; its top-level
object does not.

**Decision.** A **ticket** owns exactly one **document**. Operations expand or edit that document
rather than creating new top-level records. Approval freezes an immutable, versioned snapshot;
later operations continue editing the draft, and every approved version stays recoverable.

| Artefact | Mutable? | Lifetime |
| --- | --- | --- |
| Document (draft) | yes — operations append, humans edit | one per ticket, ongoing |
| Document version | **no** — frozen at approval | one per approval, forever |

> **Authorship amended by D-043.** The draft is written by operations only. Humans comment,
> validate a rule or reject an implementation; they do not edit the body. The lifetimes above are
> unchanged.

**Context.** The user's model, and it is better than mine for a reason I had already logged
without recognising: CON-30 ("re-running `analyse` fills the store with near-duplicate proposals")
was not a storage problem, it was evidence that proposal-per-run was the wrong unit. Ten runs
against one ticket should deepen one document, not create ten.

It also promotes CON-29 from a peripheral idea to the primary workflow.

**Consequences.**

- **CON-30 is withdrawn**, not deferred. The problem does not exist in this model.
- Product rules 4 and 5 are satisfied by the split, not by the draft: the draft is working
  material and carries no authority; the frozen version is the governance record. "Edit the doc"
  and "immutable baselines" only contradict each other if there is one artefact.
- From D-025, kept: identity is generated rather than derived, and repository identity is the root
  commit. A document version gets a fresh ID per approval for exactly the reason a proposal did.
- From D-025, dropped: one top-level record per analysis run.
- Persistence moves much earlier. A registry and an accumulating document both need storage before
  any of this works, so CON-13's SQLite is now a prerequisite rather than a Phase 4 task.
- An operation needs to be a first-class, recorded thing — what ran, against which repository, when,
  and what it contributed. Otherwise a document becomes unattributable prose, which is the failure
  this product exists to prevent.

**Status.** accepted

---

## D-028 · 2026-11-09 · Mainline is the only reference point

**Supersedes the closed-range half of D-016.** `snapshot` survives; arbitrary `--base`/`--target`
does not.

**Decision.** Every comparison is against the repository's **default branch**, resolved per
repository and never assumed to be literally `main` (product rule 6, and D-009 found both subjects
use `main` only by coincidence). Explicit base/target range selection is removed.

**Context.** Chosen deliberately for a sharper model: the question Constat answers becomes "what
does this work add that mainline does not have", which is the question a ticket actually poses.
Merge-base semantics (D-021) already implement exactly this, with base = mainline.

**Consequences — including one that is a real loss.**

- **MVP acceptance criterion 2 is amended.** It read "a user can compare two commits or tags".
  Release-to-release documentation is no longer possible: a release tag is normally an *ancestor*
  of mainline, so `compare(mainline, v2.3.1)` is a backwards range and is refused by design
  (D-021). PRODUCT_SPEC.md section 6.3 is updated to say comparison is against mainline.
  Recorded rather than quietly dropped — this was flagged before the choice was made and accepted
  with the cost understood.
- The default branch must be **resolved** from each repository and stored in the registry. Hardcoding
  `main` would break product rule 6 and any repository still on `master`.
- `--base` and `--target` leave the CLI. The machinery behind them stays: `compare_revisions` is
  unchanged, it simply always receives mainline as base.
- Open and needing a decision during implementation: **what happens once a ticket's work is merged
  into mainline.** At that point there is no divergence left, and "what does this add to mainline"
  answers "nothing". The document must describe the commits' effect rather than the branch's
  divergence, or every merged ticket goes blank. This is the one unresolved piece of the model.

**Status.** accepted

---

## D-027 · 2026-11-09 · Constat holds a workspace of registered repositories

**Amends D-001**, which kept the MVP to one repository per run. Local-first is unchanged;
single-repository is not.

**Decision.** Constat maintains persistent state: a **workspace** holding registered repositories.
Repositories are added and removed at setup or at any later point. A remote is registered by URL
and **cloned into a local cache**, then read with the existing read-only Git layer.

**Context.** Operating on a set is the point of the product — "connect changes across several
repositories to one capability" is the first stated differentiator, and `--repo` once per
invocation never served it. The cross-repository demo was parked at CON-19, which made the
differentiator the last thing to be proven.

**Consequences.**

- **Everything in `constat/git/` and `constat/evidence/` keeps working unchanged.** A cached clone
  is an ordinary local repository, which is why clone-and-cache was chosen over API access: one
  code path, not two, and the security posture of D-001 is preserved.
- Fetching is a **write to the cache but never to the source**. Read-only against the user's
  repositories still holds; the cache is Constat's own.
- Credentials for private remotes are needed and must never be stored in the workspace
  (product rule 7). Defer to the system Git credential helper rather than handling tokens.
- A registered repository stores: alias, source (path or URL), cache location, root-commit identity
  (D-025), and resolved default branch (D-028).
- Staleness becomes a real concern. A cached clone is a point-in-time copy, so every document must
  record **when the cache was last fetched**, or evidence silently ages. Unstated staleness in a
  governance tool is the same class of failure as unstated truncation (D-023).

**Status.** accepted

---

## D-026 · 2026-11-09 · Pydantic bounds the published schema; internals stay dataclasses

**Decision.** Pydantic becomes the project's first runtime dependency, applied **only** to the
models that are persisted, serialised or reported — those in `constat/models.py`. The Git adapter,
diff and evidence types stay frozen dataclasses, with an explicit mapping layer between them.

**Context.** D-002 chose Pydantic; D-015 deferred it until there was something to validate. There
now is. The open question was how far it should reach, and the worst outcome would have been
ending up with two conventions by accident rather than by choice.

The boundary follows the layering in ARCHITECTURE.md section 2. The Git layer is deterministic
plumbing over `subprocess` whose "validation" is whether Git succeeded; schema enforcement there
would be ceremony. The proposal is the opposite: it is the stable contract that gets written to
SQLite (CON-13), rendered (CON-09) and frozen into baselines (CON-14), and a malformed one is a
governance failure rather than a bug.

**Consequences.**

- `pip install constat` now pulls one package. The security-review surface argument in D-015 still
  holds: one well-known dependency, and the deterministic evidence path remains free of any AI
  provider (D-003).
- A mapping layer is required, and is where the two worlds meet. It is deliberately one-directional:
  adapters build models, models never reach back into Git.
- `schema_version` lives on the proposal (D-008) and is asserted in tests, so a future format change
  cannot go unnoticed.
- Rejecting Pydantic in the Git layer means `Repository`, `Revision`, `ChangeSummary`,
  `EvidenceBundle` and friends stay dependency-free and trivially constructible in tests — which is
  why the existing 143 tests needed no changes.

**Status.** accepted

---

## D-025 · 2026-11-09 · The unit of a proposal, and how one is identified

**Decision.** Closes Q1 and CON-24, the last of the original ten open questions.

A proposal is **`(repository, selection)`**, where a selection is one of:

| Kind | Question | Status |
| --- | --- | --- |
| `change` | What changed between two revisions? | implemented (CON-05) |
| `state` | What does this revision contain now? | implemented (CON-05) |
| `commit_set` | What changed for this reference? | reserved for CON-29 |

**A proposal belongs to exactly one repository.** Cross-repository work is a *group* referencing
several proposals, never one proposal spanning repositories. Forced by D-009: the two subjects have
no shared version space, so a single range cannot be meaningful in both. This also satisfies
product rule 6 structurally rather than by convention.

**Identity is generated, not derived.** Each run produces a new proposal with a fresh UUID, and
additionally carries a deterministic `selection_key` — a hash of the repository identity, the
selection kind and the resolved SHAs.

**Context.** The tempting choice is a derived identity: hash the inputs, so re-analysing a range
yields "the same" proposal. It breaks on the governance model. An approved baseline and a later
re-analysis of the same range are *different things* — one is a human decision, the other a fresh
machine output — and giving them one identity would force the re-analysis either to collide with
the approved record or to silently overwrite it. History must be durable (product rule 5), which
means append-only, which means new identity per run.

The `selection_key` recovers what derivation was for: "show me every proposal for this range" and
"has this been documented before?" remain single lookups. Append-only history and idempotent lookup
are not actually in tension; they just need two fields rather than one.

**Repository identity is the root commit, not the path.** A filesystem path changes when a clone
moves, and a remote URL changes when a project migrates host — this project changed both its name
and its forge inside two days. The SHA of the earliest root commit does not. Where a repository has
several root commits (orphan branches), all are recorded and the lexicographically smallest is used
as the key, so the choice is deterministic.

**Consequences.**

- CON-13 gets its stable identifier, and CON-14's baselines can reference a proposal UUID that will
  never be reused.
- CON-15 compares against the last approved baseline *for the same `selection_key`*, which is what
  "since the last approved state" has to mean.
- Re-running `analyse` ten times produces ten proposals. That is correct but needs surfacing in the
  UI eventually, or the store fills with near-duplicates; worth a ticket when CON-13 lands.
- Computing repository identity costs one extra `git rev-list --max-parents=0` per run. Cheap, and
  it buys identity that survives moving, renaming and re-cloning.
- `commit_set` is reserved in the schema now so adding CON-29 later is additive rather than a
  schema break.

**Status.** accepted

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

  > **Settled by D-040** on 2026-11-10, with the provider interface and before any provider exists.
  > Identity does not cross the boundary at all. This entry is unchanged; the obligation it
  > recorded is discharged.

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

> **This table is withdrawn.** It listed three code signals — feature flags, SQL migrations and
> bean validation — as deterministic sources of business rules. Flags were removed by D-034,
> migrations and the remainder by **D-038**. None of them are rules: under D-035 a rule is a
> business statement, and a migration or an annotation is at most *evidence* that one exists.
> Rules now come from a human-declared catalogue.

Classification (Session 08) targets these three first. Everything else is `unknown` until a human
says otherwise. This is a narrower and more defensible MVP than "explain the diff".

**Status.** accepted; the rule-source table withdrawn by D-038

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
