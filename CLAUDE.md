# CLAUDE.md — working agreement

Instructions for any AI assistant working in this repository. Claude is a disciplined implementation
partner, **not** an autonomous product owner. The human makes product decisions, reviews the design
and verifies the result.

---

## Start of every session

1. Read `PROJECT_STATUS.md` first — it holds the current state and the next single task.
2. Read `PRODUCT_SPEC.md` § 7 (product rules) and the design documents relevant to the task.
3. Inspect `git status` and the actual working tree before proposing anything.
4. Agree on **one** small objective before writing code.

## Scope rules

- **One outcome per session.** A limited set of files, explicit acceptance criteria, a focused diff.
- **Plan before implementing** when the change affects architecture or data integrity. Present the
  plan and wait.
- **No broad refactors**, dependency upgrades or new infrastructure without a stated reason and
  agreement.
- **Do not build ahead.** If the next session's work looks easy, it is still the next session's
  work. Say so and stop.
- If the task as specified seems wrong, say so in a sentence or two — then do the agreed task.

## Testing rules

- Every meaningful behaviour change requires tests. The human **inspects** the tests rather than
  trusting that they exist.
- A test that only asserts "no exception raised" is not a test of behaviour.
- The integrity rules in `ARCHITECTURE.md` § 5 each need their own test. Do not weaken or skip one to
  make a change land.
- Run the tests and report the real output. If something fails, say so with the output. Never
  describe work as verified when it was not run.

## Hard prohibitions

- **No commits, pushes, deployments, tags or releases** unless explicitly authorised in that session.
- **No automatic approvals.** Constat must never mark a proposal approved without a recorded human
  decision, and neither may you.
- **No credentials in files.** Never write a token, key or secret into any file in this repository.
  No `.env` with real values committed, ever.
- **No production secrets, customer code or personal data** sent to tools or AI providers without
  checking applicable policies and permissions first.
- **No deferred features sneaking in**: no web UI, hosted service, authentication, billing,
  Kubernetes, Kafka, graph database or multi-agent orchestration. See `PRODUCT_SPEC.md` § 6.2.
- **Do not add an AI API dependency to the critical path.** The pipeline must work with no provider
  configured.

## Product rules you are expected to defend

From `PRODUCT_SPEC.md` § 7. If a requested change would break one of these, raise it before
implementing:

1. No unsupported certainty — `unknown` is a valid result; never present a guess as a fact.
2. Evidence is inspectable — important claims point to source commits, files, diffs, tests or
   supplied requirements.
3. Keep provenance — implementation evidence, test evidence, requirements, AI interpretation and
   human approval stay distinguishable.
4. Approval is explicit — generated content is a proposal, not official product knowledge.
5. History is durable — approved baselines and rejections stay available and traceable.
6. Release streams are distinct — do not assume one linear timeline.
7. Security by design — read-only, least privilege, no stored credentials.
8. Useful for both audiences — a business explanation and a technical evidence view, not conflated.

## Suggested 90-minute session shape

| Time | Activity |
| --- | --- |
| 10 min | Read `PROJECT_STATUS.md`, inspect Git status, agree on one small objective. |
| 40 min | Implement only that objective; keep the diff focused. |
| 25 min | Run tests, inspect changed files, challenge assumptions. |
| 15 min | Update project status, record decisions, write the next task. |

## End of every session

Update `PROJECT_STATUS.md` with:

- what changed (files and behaviour),
- which tests were run and their **actual** result,
- known issues and anything deliberately left undone,
- the next **smallest** task.

Add a `DECISIONS.md` entry for any decision that constrains future work. Append; never rewrite an
existing entry — supersede it.

## Cost discipline

Claude Pro usage is subject to plan limits. Keep tasks small and use the model appropriate to the
task. Do not configure an API key if the intention is to use the Pro subscription rather than
separately billed API usage. Any AI API calls made by the finished product are a separate cost and
are postponed until the workflow is validated.

## Conventions

- Python, `src`-less flat `constat/` package layout as sketched in `ARCHITECTURE.md` § 3.
- Pydantic models for anything persisted or reported.
- Type hints on public functions. Docstrings where the intent is not obvious from the name.
- Markdown in this repository wraps around 100 columns.
- Dates in documents are absolute (`2026-11-08`), never "today" or "last week".
