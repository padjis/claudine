# Licensing strategy

Version 0.1 · 2026-11-08 · companion to [DECISIONS.md](DECISIONS.md) D-011

**Not legal advice.** This records the commercial reasoning behind the licence choice so that future
decisions stay consistent with it. Before any actual transaction, have a software IP lawyer review
the position.

---

## 1. The question this answers

The product may be sold, or may grow a commercial edition. Does licensing it under Apache-2.0
damage that? Short answer: **no — but unclear ownership would, and the name might.**

## 2. What an acquirer actually buys

An acquirer is not buying exclusivity over the source code. Under Apache-2.0 they cannot have it,
and they know that going in. What transfers:

| Asset | Affected by Apache-2.0? |
| --- | --- |
| Copyright ownership | **No.** The licence grants use; it does not transfer title. You still own the work. |
| Trademark | **No.** Apache-2.0 § 6 explicitly withholds trademark rights. The name remains exclusively yours. |
| Customer contracts, pilots, pipeline | No |
| Hosted service, operations, accumulated data | No |
| Right to license *future* versions differently | **Only if** you own all copyright |
| Exclusivity over *already published* code | **Yes — permanently forfeited** |

The last row is the whole trade-off and it is irreversible. Every version published under
Apache-2.0 stays Apache-2.0 for ever. Future versions can be licensed differently; released ones
cannot be recalled.

## 3. What actually kills software acquisitions

Diligence rarely fails because a project was open source. It fails on **chain of title** — the
buyer's lawyers cannot prove the seller owns what is being sold. The usual causes:

- Contributions merged with no CLA or DCO, so the copyright position on that code is unknown.
- Code written while employed elsewhere, under an employment IP-assignment clause.
- Copied code under an incompatible licence (GPL contamination being the classic).
- Contractor work with no written assignment.

**This is why the DCO matters more to an exit than the licence choice does.** It is the cheapest
insurance available, and it only works if it is in place *before* the first outside contribution —
which, as of D-011, it is.

## 4. The value asymmetry, and why it suits this product

Apache-2.0 caps what anyone will pay for *the code*, because a competitor can fork it. Value
therefore migrates to what a fork cannot take: the trademark, the customer relationships, the hosted
service, the accumulated approved-baseline data, and the founder.

For Constat this works out better than it first appears. The product is a **governance** tool.
Governance buyers purchase trust, audit trails, and a vendor who will answer the phone during a
compliance review. Nobody adopts a forked governance tool from an unknown maintainer. The moat was
never going to be the source code — so little is given up by publishing it, and a great deal of
procurement friction is avoided.

## 5. Paths to more exclusivity, all still open

The DCO preserves every one of these. None are available if unsigned contributions are accepted.

| Path | What it means | When it fits |
| --- | --- | --- |
| **Open core** | CLI stays Apache-2.0; governance server, SSO, audit export and multi-tenancy ship proprietary. | Fits the roadmap's expansion order almost exactly — those are all post-MVP anyway. |
| **Relicense future versions to BUSL-1.1** | Source-available, non-compete, auto-converting to Apache after ~4 years. | Only once there is revenue to protect. Do it *before* a community forms; backlash scales with how many people built on the original promise. |
| **Dual licence** | Apache for the community; commercial terms with indemnification for enterprises. | Enterprises routinely pay for exactly this. |

## 6. Why not the alternatives

| Option | Why not |
| --- | --- |
| **MIT** | No patent grant. Costs nothing to give one, and enterprise reviewers look for it. |
| **AGPL-3.0** | On many enterprise deny-lists. For a tool pointed at a customer's private source code it invites a legal discussion unrelated to the product, during exactly the pilot conversations the roadmap schedules for weeks 6–8. |
| **BUSL-1.1 now** | Premature at zero users. Signals paranoia, still fails some procurement allowlists, and the real risk is obscurity rather than cloning. Remains available later. |
| **Proprietary / all rights reserved** | Maximum control, minimum adoption. Wrong trade for a product whose first job is to earn trust. |

## 7. The trademark, and why the name was changed

Because Apache-2.0 makes the trademark the **primary defensible asset**, the product name carries
more strategic weight here than it would for a closed-source product. The code is forkable by
design; the name is not.

That reasoning is what drove the rename. Research on 2026-11-08 found that the original working
name, "Claudine", carried a high and concrete conflict risk with Anthropic's registered CLAUDE mark
in the same class of goods and services, with a documented enforcement precedent against a weaker
sound-alike. A name that might have to be abandoned is the worst possible foundation for the one
asset the licence leaves exclusively ours — so it was replaced with **Constat** before the initial
commit (D-013). Full analysis: **[BRAND_NAME_REVIEW.md](BRAND_NAME_REVIEW.md)**.

**Two items remain open and both bear on the licensing strategy**, because an unclearable or
unobtainable name would undermine the asset this licence depends on:

1. No USPTO, EUIPO or INPI search has been run on *Constat*. Needed before the first pilot
   conversation.
2. No primary domain has been acquired. Needed before outbound discovery.

There is also a jurisdictional wrinkle worth raising with counsel: a common French noun applied to
software in this field is *suggestive* before the EUIPO and INPI — a weaker mark — while being
*arbitrary*, and therefore stronger, in the US and UK. If the first customers are French or EU, that
may argue for a distinctive composite rather than the bare noun.

## 8. Practical hygiene

1. Sign off **your own** commits too (`git commit -s`), not just outside contributions — a
   consistent record, not a partial one.
2. If employed, check the employment contract's IP-assignment clause **now**. This is the most
   common way founders discover they do not own their side project.
3. Decide whether copyright sits with an individual or a company. Transfer later is possible but
   adds a diligence step. Tracked as an open item in [DECISIONS.md](DECISIONS.md).
4. Track third-party dependency licences from the first `pyproject.toml`. One GPL dependency in a
   distributed product is a real problem; finding it in year three is worse.
5. Keep `NOTICE` accurate as contributors are added.
