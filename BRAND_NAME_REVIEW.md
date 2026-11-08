# Brand name review

Version 0.2 · research conducted 2026-11-08 · **not legal advice; not a cleared trademark search**

**Outcome: the working name "Claudine" was rejected and the product renamed to _Constat_ on
2026-11-08, before the initial commit. Recorded as D-013.**

This document is kept as the reasoning behind that decision, not as an open question. It covers why
"Claudine" was abandoned (§ 1–6), the alternatives considered (§ 7–8), and what clearance work
remains on the chosen name (§ 9).

The roadmap flagged on page 1 that "the name is provisional; domain, company-name and trademark
clearance have not been performed." This review performed a preliminary version of that check. The
result was worse than "unclear" — there was a specific, documented conflict with an actively
enforced mark.

---

## 1. The trademark problem

### 1.1 CLAUDE is a registered mark in this exact category

Anthropic, PBC holds US registration **#7645254** for **CLAUDE** (serial 97790228), filed
2023-02-10, registered 2025-01-07, in the category of **computer and software services**. That is
the same class Claudine would occupy.

### 1.2 Anthropic's published brand rules exclude this

Anthropic's guidelines permit saying a product *runs on* Claude in plain text, but prohibit using
the Claude or Anthropic names as part of a product, feature or company name. Community analysis of
the rules places **sound-alike names** on the not-allowed side, citing enforcement.

### 1.3 There is a live enforcement precedent against a *weaker* conflict

On **2026-01-27**, Anthropic's legal team sent a trademark notice to the creator of **Clawdbot**,
on the basis that "Clawd" sounded too similar to "Claude". The project renamed to Moltbot within
days, then to OpenClaw by 2026-01-30. The creator complied rather than contest it.

This is the finding that moves "Claudine" from theoretical risk to likely problem:

| | Clawdbot | Claudine |
| --- | --- | --- |
| Relationship to CLAUDE | Phonetic only — a deliberate misspelling | Contains the literal string `Claud`; reads as *Claude* + the French diminutive `-ine` |
| Category | AI developer tool | AI-adjacent developer tool |
| Outcome | Demand letter, renamed in 4 days | — |

In trademark terms, adding a suffix to a registered mark within the same class is a textbook
**formative mark** and a standard likelihood-of-confusion finding. Claudine is a *stronger* conflict
than the one Anthropic already acted on, not a weaker one.

### 1.4 The aggravating factor

Claudine is a developer tool, built with Claude Code, in the AI tooling space. Likelihood of
confusion is assessed on exactly this: similar mark, related goods, overlapping channels, same
buyers. Every factor points the wrong way. A reasonable developer encountering "Claudine" in this
category would plausibly assume an Anthropic affiliation — which is precisely the harm trademark law
addresses.

## 2. Why this matters more than it would for most projects

Under Apache-2.0 the **trademark is the primary defensible asset** — see
[LICENSING_STRATEGY.md](LICENSING_STRATEGY.md) § 4. The code can be forked; the name cannot. Building
on a name that may have to be surrendered inverts the whole strategy.

Two concrete failure modes:

1. Two years of brand equity, pilot decks, documentation and search presence are rebuilt under
   duress on someone else's timetable.
2. An acquirer discounts the deal or carves out the name, because the one non-copyable asset has no
   clean title.

## 3. Domains

Checked by DNS/NS lookup on 2026-11-08. NS records present indicates the domain is registered,
whether or not a site is served.

| Domain | Status |
| --- | --- |
| `claudine.com` | **Registered** (resolves) |
| `claudine.ai` | **Registered** — the one an AI product would want |
| `claudine.io` | **Registered** |
| `claudine.dev` | **Registered** |
| `claudine.app` | **Registered** |
| `claudine.sh` | Appears unregistered |
| `getclaudine.com`, `useclaudine.com` | Appear unregistered |

Every primary domain is gone. What remains are the prefix-and-fallback patterns that signal a
project which could not get its own name.

## 4. Non-legal brand problems

Independently of trademark, the name works against the product:

- **It reads as an assistant persona, not institutional software.** Claudine is a French feminine
  given name. The buyer here is an engineering leader, architect or compliance stakeholder choosing
  a *governance and audit* tool. That audience responds to institutional, evidential naming. A
  first-name persona actively miscues the category — and worse, it implies a chatty AI assistant,
  which is the exact perception the product's "no unsupported certainty" positioning fights against.
- **Strong pre-existing cultural associations.** The *Claudine* novels by Colette (four books,
  1900–1904) are a well-known, semi-autobiographical and somewhat risqué coming-of-age series.
  There is also the 1974 American film *Claudine*. Both outrank a new developer tool in search and
  in recall.
- **Unfortunate etymology.** Claudine derives from the Roman family name *Claudius*, from Latin
  *claudus*, meaning "lame" or "limping". Few people know this, but it is a poor root for a product
  whose entire promise is trustworthiness, and it is the kind of detail that surfaces in a
  competitor's pitch.

## 5. Cost of renaming, now versus later

| When | Cost |
| --- | --- |
| **Now** | Effectively zero. No users, no commits pushed, no SEO, no customers. Eleven uncommitted files and a `git mv`. |
| After the first pilots | Re-issue decks, docs and URLs; explain the change to the people whose trust you are trying to win. |
| After a community forms | Package names, imports, integrations, stars, inbound links — plus a credibility cost. |
| Under a demand letter | All of the above, on someone else's deadline, while mid-sales-cycle. |

The asymmetry is extreme and it only gets worse. This is the cheapest it will ever be.

## 6. Criteria for a replacement

1. **No derivation from any AI vendor's marks** — not Claude, GPT, Gemini or their phonetic
   neighbours. The product outlives whichever model backs it, and D-003 already keeps AI optional.
2. **Institutional, not persona.** The category is governance and audit.
3. **Connotes evidence, provenance, record or continuity** — the actual product thesis.
4. **`.com` or `.ai` obtainable**, with a matching GitHub org.
5. **Clears a preliminary USPTO/EUIPO search** in Nice classes 9 and 42.
6. **Pronounceable and spellable** by a non-native English speaker on a call.

## 7. Candidate names — French, grouped by concept

None of these are cleared. Each needs the search that "Claudine" just failed. Domain status was
checked by NS lookup on 2026-11-08: **TAKEN** means a nameserver exists (often registrar parking, so
possibly purchasable), **free?** means no nameserver was found — suggestive of availability, not
proof of it.

The organising idea: French has a precise, institutional vocabulary for *the official record of an
observed fact* that English lacks. That vocabulary is this product's thesis. Where English offers
only "report" or "record", French distinguishes a `constat` from a `procès-verbal` from a `scellé` —
each a different legal weight of evidence. That is an unusually good naming well for a governance
tool.

### Family A — the official record and its custody

The strongest family, because it maps directly onto immutable approved baselines.

| Name | Meaning and reasoning | Domains |
| --- | --- | --- |
| **Constat** ✅ **chosen** | In French law, a *constat* is a formal written statement of observed fact — a `constat d'huissier` is admissible evidence. This is *exactly* what the product produces: observed facts, formally recorded, attested by a person. The single best semantic fit on the list. Risk: anglophones may stress it "CON-stat" rather than "kon-STAH". | `.com/.ai/.dev/.io` all taken |
| **Greffe** | The court registry — where official records are deposited and preserved unaltered. The *greffier* is the clerk who keeps them. An immutable baseline store is, literally, a greffe. Risk: *greffe* also means a medical graft, and the "gr-" opening is hard for anglophones. | `.dev` free?; **`Greffia` free on `.com`/`.ai`/`.dev`** |
| **Scellé** | Evidence placed under seal in legal custody — `mise sous scellés`. Carries immutability, chain of custody and tamper-evidence in one word. The accent is a liability in a domain name; `Scelle` loses the pronunciation. | `.dev` free? |
| **Liasse** | A bundle of documents filed together as one record. Quietly accurate for a change proposal: many evidence items, one filed unit. Pleasant to say ("lee-ASS"), distinctive, no English collision. | **`.ai` and `.dev` free?** |
| **Paraphe** | The initials placed on every page of a contract to validate it. It *is* human approval, rendered as a single word. Memorable and unusual. Risk: obscure even to many French speakers. | all taken |

### Family B — evidence

| Name | Meaning and reasoning | Domains |
| --- | --- | --- |
| **Faisceau** | From `faisceau d'indices` — "body of circumstantial evidence", the standard French legal phrase for multiple weak signals combining into something persuasive. This is precisely the product's classification model: individual signals, none conclusive alone. Also means a beam or bundle, so it reads as convergence. Strong concept, slightly long. | **`.ai` free?** |
| **Indice** | A single clue or evidence item. Clean and short, but "indice" also means index/subscript in maths and finance, so it is crowded. | `.dev` free? |
| **Empreinte** | An imprint or fingerprint — the mark left behind. Evidential and evocative, but long and hard to spell on a call. | all taken |
| **Preuvia** | Coined from `preuve` (proof). Reads as a product name rather than a word, which makes it a stronger trademark. Slightly generic-SaaS in flavour. | **`.ai` and `.dev` free?** |

### Family C — the thread across repositories

This family captures the actual differentiator: connecting changes in several repositories to one
capability.

| Name | Meaning and reasoning | Domains |
| --- | --- | --- |
| **Fil Rouge** | The French idiom for the connecting thread running through something — the exact equivalent of "throughline", and the single clearest statement of what the product does across repositories. Two words is a drawback; `filrouge` as one word is slightly opaque. | `filrouge.dev` free? |
| **Maillon** | A link in a chain. Each repository's change is a *maillon*; the capability is the chain. Short, clean, pronounceable ("my-YON"). | all taken |
| **Filiation** | Descent and lineage — how one version descends from another. Accurate for baseline versioning, but it is a legal term for parentage, which may mislead. | **`.ai`/`.dev`/`.io` free?** |
| **Sillage** | The wake a ship leaves — the visible trace of something's passage. The most evocative name here and the hardest to pronounce ("see-YAHZH"). Probably disqualifying for an anglophone market. | `.io` free? |

### Family D — the reference point

| Name | Meaning and reasoning | Domains |
| --- | --- | --- |
| **Repère** | A reference point or benchmark — `point de repère`. This is the French word for *baseline*, the product's own core noun. Semantically ideal; the accent is a problem, and `repere` unaccented looks like a typo. | `.io` free?; **`Reperis` `.ai`/`.dev` free?** |
| **Jalon** | A milestone or survey marker. Clean, short, easy to say. Less evidential than the Family A names. | all taken |
| **Socle** | The base or plinth on which something rests — `socle commun` means a shared foundation. Good for "approved baseline". Awkward final consonant cluster in English. | all taken |
| **Ancrage** | Anchoring. Conveys fixity, which suits immutability, but it is abstract. | `.dev` free? |

### Family E — approval

| Name | Meaning and reasoning | Domains |
| --- | --- | --- |
| **Aval** | `Donner son aval` means to give one's approval or endorsement. It *also* means downstream. Both meanings are load-bearing here: human approval, and changes flowing downstream through repositories. Four letters, trivially pronounceable in both languages. The best short name on the list. Risk: an English reader may see "a-VAL" or misread it toward "Avalon". | `.io` free? |
| **Attesta** | From attestation — evidence formally confirmed by a person. Reads as institutional software. | **`.com` free?** |

---

## 8. Recommendation among the alternatives

If forced to pick three to take into a real clearance search:

1. **Aval** — shortest, bilingual, and the double meaning (approval + downstream) is genuinely
   on-thesis rather than a stretch. Best balance of brandability and meaning.
2. **Constat** — the strongest semantic match to the product. Worth paying for a parked domain.
3. **Faisceau** or **Liasse** — both have clean `.ai` availability, which matters, and both carry
   real evidentiary meaning. Liasse is easier to say; Faisceau has the better concept.

`Greffia` deserves a mention for a practical reason: it appeared free on `.com`, `.ai` **and**
`.dev`, which no other candidate managed. A coined word built on `greffe` (the court registry) keeps
the governance meaning while being far more registrable than a dictionary word.

### A trademark point worth raising with counsel

A common French noun occupies **different trademark positions in different jurisdictions**. In
France and before the EUIPO, a word like `constat` or `preuve` applied to evidence software is
suggestive of the goods and therefore a *weaker* mark, possibly facing a descriptiveness objection.
In the US and UK the same word is arbitrary to the average consumer and therefore a *stronger*,
more readily registrable mark.

This cuts both ways depending on where the first customers are. A coined form — `Greffia`,
`Reperis`, `Preuvia`, `Attesta` — sidesteps the problem in every jurisdiction at the cost of some
immediate meaning. Worth one question to a trademark attorney before the shortlist is finalised.

### What has *not* been done

A web search found no obvious software or SaaS trademark conflicts for the leading candidates, but
absence of search results is not clearance. None of these names has been checked against the USPTO
or EUIPO registers, against French company registrations, or for availability as a GitHub
organisation.

## 9. Outcome, and what clearance work remains

**Decided 2026-11-08: the product is _Constat_.** Recorded as D-013. The rename was completed before
the initial commit, so it cost nothing — the GitHub repository, the local working copy, the remote
URL and every document were updated with no public history to rewrite.

### Done

- GitHub repository renamed to `padjis/constat`; remote URL updated.
- All project documents, the Python package name in `ARCHITECTURE.md` § 3, `LICENSE` and `NOTICE`
  updated.
- The trademark conflict that forced the decision is resolved: *Constat* has no relationship to any
  AI vendor's marks, which was criterion 1 in § 6.

### Still outstanding — do not treat the name as cleared

| # | Task | When |
| --- | --- | --- |
| 1 | Preliminary USPTO and EUIPO knockout search in Nice classes 9 and 42. | Before the first pilot conversation |
| 2 | Trademark attorney review of the finalist, including the FR/EU descriptiveness question in § 8. | Before the first pilot conversation |
| 3 | French company-register (INPI / RCS) check. | With task 2 |
| 4 | **Register `tryconstat.com`** — chosen in D-014, confirmed unregistered, not yet bought. `constat.ai` is listed for sale on GoDaddy and remains the upgrade path once validated. | Now |
| 5 | GitHub organisation name, if one is wanted later. | Not urgent |

### The known weakness of this choice

Two caveats were accepted knowingly rather than overlooked:

1. **No primary domain was available.** Every obvious TLD was taken: `constat.com` sits with a
   legacy owner, `.dev` and `.fr` are live, and `.ai` and `.io` are held on aftermarket
   nameservers — `constat.ai` redirects to a GoDaddy for-sale page. Resolved by taking
   **`tryconstat.com`** (D-014), with `constat.ai` as the paid upgrade path once the workflow is
   validated. This was the one criterion from § 6 that *Constat* failed, and it was traded against
   the strength of the semantic fit.
2. **In France and before the EUIPO, `constat` applied to evidence software is suggestive of the
   goods** and is therefore a weaker mark than it would be in the US or UK, where it is arbitrary.
   See § 8. If the first customers are French or EU, raise this with counsel early — it may argue
   for a distinctive composite (`Constat` plus a wordmark or a qualifier) rather than the bare noun.

Neither is a reason to revisit the decision now. Both are reasons to involve a trademark attorney
before spending money on a brand.

---

## Sources

- [CLAUDE Trademark (USPTO Serial 97790228)](https://www.trademarkelite.com/trademark/trademark-detail/97790228/CLAUDE)
- [Trademark registration record, CLAUDE](https://www.trademarkia.com/claude-97790228)
- [Claude Code — Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- [What Anthropic's brand and trademark rules allow in a third-party app's name and icon](https://github.com/Jbmanllr/accroster/issues/27)
- [Clawdbot Rebrands to Moltbot After Trademark Request From Anthropic — Laravel News](https://laravel-news.com/clawdbot-rebrands-to-moltbot-after-trademark-request-from-anthropic)
- [Viral AI Sidekick 'Clawdbot' Changes Name To 'Moltbot' — Forbes](https://www.forbes.com/sites/ronschmelzer/2026/01/27/viral-ai-sidekick-clawdbot-changes-name-to-moltbot-and-sheds-its-old-skin/)
- [OpenClaw name history: Clawdbot, Moltbot, and OpenClaw](https://eastondev.com/blog/en/posts/ai/20260204-openclaw-rename-history/)
- [Anthropic raised trademark concerns, so Clawdbot renamed — Hacker News](https://news.ycombinator.com/item?id=46778307)
- [Claudine (book series) — Wikipedia](https://en.wikipedia.org/wiki/Claudine_(book_series))
- [Meaning of the name Claudine](https://www.wisdomlib.org/names/claudine)
- [Claudine: Name Meaning and Origin — SheKnows](https://www.sheknows.com/baby-names/name/claudine/)
