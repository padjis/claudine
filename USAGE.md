# Using Constat

How to run it. For *why* it works this way see [DECISIONS.md](DECISIONS.md); for the shape of the
code see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Install

Python 3.11 or newer.

```bash
git clone https://github.com/padjis/constat && cd constat
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,mcp]"
```

Two optional extras, neither needed for the evidence pipeline:

| Extra | For | Install |
| --- | --- | --- |
| `mcp` | `constat mcp`, the agent surface | `pip install -e ".[mcp]"` |
| `ai` | Constat calling a model itself | `pip install -e ".[ai]"` |

`dev` deliberately omits `ai`, so the test suite cannot reach a real API.

**Put it on your PATH.** The commands below write `constat`; the venv must be activated
(`source .venv/bin/activate`) or you must spell out `.venv/bin/constat`. For an MCP config, always
use the absolute path — your client has neither your PATH nor an activated venv.

---

## 2. Decide who reads the evidence

Constat gathers evidence deterministically and never guesses what it means. Something has to
*read* that evidence to propose business rules, and there are three choices. Pick one before you
start, because a rule-generating command refuses if the answer is "nothing" (D-059).

| | Who calls the model | Cost | Model id recorded as |
| --- | --- | --- | --- |
| **MCP** — `constat mcp` driven by an agent | your client's host | none beyond your existing plan | self-reported |
| **Provider** — `CONSTAT_AI_PROVIDER=anthropic` | Constat | billed to your API account | attested |
| **By hand** — export, read, submit | you | whatever you use | self-reported |

> **Claude Pro does not include API credits.** They are separate products. If you have a Pro
> subscription and no credits, use the MCP path — that is what it exists for.

---

## 3. A workspace, and the repositories to read

```bash
constat init
constat repo add ~/git/billing --name billing
constat repo add ~/git/web     --name web
constat repo list
```

`init` creates one SQLite file: `--workspace PATH`, else `$CONSTAT_HOME`, else `~/.constat`. It
always prints which it used, and refuses to overwrite an existing one — the thing it would destroy
is the record of your decisions.

`repo add` resolves the default branch from `origin/HEAD` and **refuses if it cannot**, because
that branch becomes the reference point for every later comparison. Pass `--default-branch main`
if your clone has no `origin/HEAD`. Repository identity is the root commit, so the same repository
cloned twice is recognised as one.

---

## 4. The loop

### With MCP (recommended on a Pro subscription)

```bash
claude mcp add constat -- /absolute/path/to/.venv/bin/constat --workspace ~/.constat mcp
```

Then ask the agent in plain language:

> Use constat to gather evidence for ticket 622 and propose the business rules it changed.

It has four tools — `gather_evidence`, `get_payload`, `submit_rules`, `list_rule_proposals`.
**There is no accept tool and there will not be one** (D-055). The agent reads; you decide.

### With a provider

```bash
export CONSTAT_AI_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...      # read from the environment, never stored
constat ticket add 622                   # gathers, reads, fills the queue
```

`CONSTAT_AI_MODEL` overrides the default of `claude-opus-5`. What gets recorded is the model id the
API *returned*, not the alias you asked for, so a proposal still names the model that read it in a
year.

### By hand

```bash
constat ticket add 622 --no-provider          # evidence only
constat document 622 --payload > payload.json # redacted, credential-gated
#  …any model, anywhere, reads it…
constat rule submit 622 --from reply.json --provider claude --model opus-5
```

The reply is JSON:

```json
{"rules": [{
  "name": "daily-transfer-limit",
  "statement": "A transfer above the daily limit is refused.",
  "behaviours": ["Refuse the transfer and explain the limit"],
  "anchors": [{"path_glob": "rules.py", "repository_alias": "billing"}],
  "revises": 3
}]}
```

`revises` is optional — the payload includes your catalogue, so a reading can revise a rule it was
shown instead of duplicating it. Every anchor is checked against re-gathered evidence; anything
anchored to a path that is not there is discarded **with a reason**, never silently.

---

## 5. Review and decide

```bash
constat rule proposals 622          # the queue: undecided only
constat rule proposals 622 --all    # including decided ones
constat rule accept 1 --by emmanuel --rationale "matches the diff"
constat rule reject 2 --by emmanuel
constat rule history 1              # every version, back to the reading and its evidence
constat rule list                   # the catalogue
constat document 622 --show         # the document
```

Three things that are not accidents:

- **`--by` has no default.** A decision with no decider is not a decision.
- **`rejected` means inconclusive, not wrong** (D-036). A later reading of better evidence is
  expected, not precluded.
- **Accepting creates the rule.** Nothing else does — not gathering, not submitting, no MCP tool.
  It also freezes a version; rules are superseded, never deleted.

The queue tells you *which* kind of empty it is:

```
No undecided rule proposals for 622.

That is not a statement that this ticket has no rules —
nothing has read its evidence yet.
```

---

## 6. Publish it

```bash
constat publish 622                      # target derived from the repo's remote
constat publish 622 --target <git-url>   # or named explicitly
```

Writes `622.md` to a git-backed documentation repository — by default the wiki of the current
repository's remote. An unrecognised host **refuses** rather than guessing: a push to a guessed URL
is not undone by noticing afterwards.

This is the only command that writes outside the workspace. Gathering never publishes, accepting
never publishes, and publishing approves nothing.

> On GitHub and GitLab a wiki does not exist until you open it once in the browser. An existing but
> empty repository is fine — Constat makes the first commit.

---

## 7. Recomputing

`ticket add` refuses a second time; the ticket already exists. To re-read the same ticket:

```bash
constat document 622
```

It re-resolves the commits, re-reads the diffs, and proposes again. **Readings accumulate** — they
are append-only, so re-running three times leaves three entries in the queue, and accepting one
does not retire the others. Decide the queue before recomputing, or reject the stale duplicates.

To re-derive a rule you have already accepted, let the reading claim `revises: <rule id>`. That
appends version N+1 rather than duplicating the rule. You cannot erase version 1, by design.

---

## 8. Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 2 | Usage — bad arguments or malformed input |
| 3 | Repository — bad path, unresolvable revision, unknown default branch |
| 4 | Workspace — not initialised, unknown ticket, workspace already exists |
| 5 | Provider — misconfigured, unreachable, unparseable reply, or a credential in the evidence |
| 6 | Publish — target unknown, unreachable, or a credential in the document |

---

## 9. When it refuses

Constat refuses rather than guessing, so most of what you will see is deliberate. The message is
the documentation; this table is the short version.

| Message | What it means | What to do |
| --- | --- | --- |
| `CONSTAT_AI_PROVIDER is not set, so nothing would read this ticket's evidence` | A rule-generating command with nothing able to read (D-059) | Configure a provider, use MCP, or pass `--no-provider` for evidence only |
| `names a provider this version of Constat does not implement` | A typo, or a provider that is not built yet | `anthropic` is the only one today; Gemini is CON-62, ChatGPT CON-63 |
| `needs ANTHROPIC_API_KEY in the environment` | Provider named, credential absent | Export the key. It is never written to a file |
| `the 'anthropic' package is not installed` | The `ai` extra is missing | `pip install -e ".[ai]"` |
| `Your credit balance is too low` | The key works; the API account has no credit | Buy credits, **or use the MCP path** — Pro does not include API usage |
| `refusing to send evidence… possible credential(s) found` | A credential-shaped string in the evidence | Remove it from the code and **rotate it**. `--accept-scan-findings` overrides, on the record |
| `refusing to publish this document` | Same, on the page about to be published | A page cannot be recalled. Fix the evidence and re-gather |
| `no anchor grounded in the evidence supplied` | A reading anchored to a path nobody sent | Correct the anchor. Constat will not store an invented one |
| `could not determine the default branch` | `origin/HEAD` is not set | `git remote set-head origin -a`, or pass `--default-branch` |
| `whose documentation convention Constat does not know` | Publishing to an unrecognised host | Pass `--target` with the documentation repository URL |
| `a workspace already exists` | `init` on an existing workspace | Nothing was touched. Remove the file deliberately if you mean to start over |

Two that are *not* refusals, and matter:

- **`not_found` for a repository** is an answer, not a failure. Every registered repository is
  reported, including those that contributed nothing — silence about a repository is not the same
  as no changes in it.
- **"no rules were identified"** is a statement about configuration, never about your code.

---

## 10. What Constat will not do

Not limitations to work around — they are the product.

- **Accept anything by itself.** No command, flag, tool or provider can mark a rule proposal
  approved. Only `rule accept --by <who>`.
- **Send author or committer identity to a model.** The payload type has no field for it.
- **Write to a repository it reads.** Gathering cannot change what it is evidence of.
- **Report a failure as a finding.** A timeout, an unparseable reply or a missing provider is an
  error, never "no rules were identified".
- **Delete a rule, a decision, or an approved version.** Enforced by database trigger, not by
  convention.
