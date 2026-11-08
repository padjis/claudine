# Contributing to Constat

Constat is pre-MVP and currently built by a single founder. Contributions are welcome, but please
open an issue to discuss before writing code — the roadmap is deliberately narrow and an unsolicited
feature is likely to be out of scope.

## Licence

Constat is licensed under the [Apache License 2.0](LICENSE). Contributions are accepted under the
same licence.

## Developer Certificate of Origin — required

**Every commit must be signed off.** This project uses the Developer Certificate of Origin (DCO)
rather than a Contributor Licence Agreement. Sign off with:

```
git commit -s -m "your message"
```

which appends a line to your commit message:

```
Signed-off-by: Your Name <your.email@example.com>
```

Use your real name and a working email address. Commits without a sign-off cannot be merged.

### Why this project requires it

Two reasons, stated plainly:

1. **Provenance.** Constat's entire product thesis is that the origin of a claim should be
   traceable. A project about provenance that cannot establish the provenance of its own source
   would be hard to take seriously.
2. **Future licensing freedom.** Constat may later offer a commercially licensed edition.
   Relicensing is only possible while the copyright position is clear. Accepting contributions
   without a sign-off would permanently foreclose that option. The DCO keeps it open while staying
   far lighter than a CLA — no paperwork, no signing ceremony, just a trailer on the commit.

The full DCO text is in [DCO](DCO).

## Scope

Before proposing a change, read:

- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) § 6.2 — what is deliberately **out** of scope.
- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) § 7 — the eight product rules that must not be compromised.
- [PROJECT_STATUS.md](PROJECT_STATUS.md) — the current session and the next task.

A change that breaks a product rule will be rejected regardless of how well it is implemented.
A change that is simply *ahead* of the roadmap will usually be deferred, not rejected.

## Expectations for a change

- Tests for every meaningful behaviour change. The integrity rules in
  [ARCHITECTURE.md](ARCHITECTURE.md) § 5 each require their own test.
- A focused diff. No drive-by refactors, dependency upgrades or formatting churn.
- No new runtime dependency without a stated reason.
- Never add a credential, token or key to any file in this repository.
- Do not make the deterministic evidence path depend on an AI provider. The pipeline must work with
  no provider configured.

## AI-assisted contributions

AI assistance is fine — this project is built with it. The sign-off is a statement about *your*
right to submit the contribution, and it applies unchanged. You are responsible for what you submit:
review it, test it, and understand it before signing off.
