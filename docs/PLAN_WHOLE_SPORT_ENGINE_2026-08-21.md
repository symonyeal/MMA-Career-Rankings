# Whole-sport scope, evidence weighting, and era depth — design plan

**Date:** 2026-08-21
**Status:** plan. Nothing here is implemented. Every number below was measured on
`data/snapshots/2026-08-13` on 2026-08-21 and is cited so it can be re-checked.
**Predecessors:** [Principled Core Evolution](PRINCIPLED_CORE_EVOLUTION_2026-08-20.md),
[Prior Mass and Uncertainty](PRIOR_MASS_AND_UNCERTAINTY_2026-08-20.md).

---

## 0. What this document is for

The engine currently rates **UFC bouts only**. That is not a scope decision, it
is an unfinished one: it means the platform cannot answer where Fedor
Emelianenko, Wanderlei Silva, Antonio Rodrigo Nogueira, Mirko Cro Cop or a
WEC-era José Aldo belong, and it silently truncates the careers of everyone who
built a résumé elsewhere before arriving.

At the same time the last pass stripped out a large amount of machinery —
opponent-quality weights, title bonuses, activity bonuses, era premiums —
because it was double-counting. That was right *in the form it took*, and it
left a question unanswered: **round count, title status and opponent calibre
obviously matter, so where do they legitimately live?**

This plan answers both, under one principle, and states what would falsify it.

---

## 1. The guiding principle

> ### Single-Entry
> **Every fact about a fight is posted exactly once, in the one layer where it
> is the answer rather than a decoration.**
>
> | Question the fact answers | Where it is posted | Example |
> |---|---|---|
> | *What happened?* | the bout likelihood | win / loss / draw |
> | *How much does this bout tell us?* | the likelihood **precision** `ω_b` | scheduled rounds, duration, data quality |
> | *Who did they fight?* | the **opponent's own latent rating** | never a separate "beat a top-5" bonus |
> | *Where did it sit in the sport?* | the **achievement ledger** | title, defence, lineage |
> | *How sure are we?* | **refit intervals** | never a hand-set constant |
> | *Compared to whom?* | the **declared reference field** | division-year contender line |

The name is deliberate. Double-entry bookkeeping posts each transaction twice
because it is checking itself. A rating system that posts a fact twice is not
checking itself — it is **counting it twice**, and the second posting is
invisible in the final number.

### Why this is not what anyone else does

| System | Structure | Where a fact gets posted more than once |
|---|---|---|
| **UFC official rankings** | media panel ballots, aggregated | Not a model. Voters weigh title status, recency, name value and skill simultaneously and inseparably; there is no estimand, no uncertainty, and no way to ask *why*. |
| **FightMatrix** | Elo-family points with quality-of-opposition and title/activity adjustments | Beating a strong opponent is posted once as the Elo update **and again** as a quality bonus; title fights add points **on top of** the skill they already evidence. |
| **Generic Elo / Glicko trackers** | single points number | Achievement and skill are fused into one figure, so "who is better" and "who accomplished more" cannot be asked separately. |
| **This engine (target)** | one likelihood, one precision, separate ledgers | By construction: a redundant posting is a **bug with a test**, not a tuning choice. |

Two further commitments follow, and neither is present in the systems above:

1. **The platform publishes what it cannot distinguish.** Rank intervals and
   explicit tie-groups. The current board's honest reading is *Jon Jones, then a
   large tied group* — median rank-interval width across the top 50 is 102
   places (150-replicate bootstrap, 2026-08-20).
2. **Estimands are separated and never blended into one headline number.**
   *Skill* (latent, era-comparable), *achievement* (factual, dated), *standing*
   (uncertainty-aware ordering). A reader may combine them; the engine will not
   do it silently on their behalf.

---

## 2. What is already right — preserve, do not revisit

| Asset | Why it survives |
|---|---|
| One binary W/L/D likelihood, one shared weight per bout | Side-specific weights are not the gradient of any joint likelihood. Enforced in `run_whr`. |
| Filter (Glicko-2) and smoother (WHR) over the same evidence | Different questions — "what do we know at time *t*" vs "what does the whole career say" — not competing models. |
| Prior mass fixed per fighter (anchor + virtual games) | Without it an undefeated record has no interior MLE; a 1-0 fighter held the highest rating in the database. |
| Career functional with one contribution per active year | Blocks fight-volume padding. |
| Fixed Prime/Peak windows | Blocks window-shopping until a favourite wins. |
| Bootstrap rank intervals | The only honest source of "how sure". |
| Integrity as ledger + debit, never propagated through the graph | A policy judgement, kept visibly separate from skill. |
| Completeness abstention | Unranked beats a plausible-looking default seat. |
| Cross-org quarantine **until the weights are fixed** | The current weights leak future information (§3.2). |

---

## 3. Gap register

Severity: **S1** blocks a headline claim · **S2** distorts published output ·
**S3** limits reach or trust.

### 3.1 (S1) The scope gap — the fighters the engine cannot see

Non-UFC bouts are staged in `crossorg_fights.fightmatrix-public.parquet` but
never rated. Measured coverage for the fighters this plan is meant to serve
(non-UFC bouts in cache / distinct opponents / opponents who are UFC-rated —
the bridge that anchors them to the main scale):

| Fighter | non-UFC bouts | opponents | **UFC-rated opponents** | median UFC bouts of those bridges |
|---|---|---|---|---|
| Fedor Emelianenko | 45 | 40 | **24** | 11 |
| Urijah Faber | 28 | 26 | 10 | 10 |
| Wanderlei Silva | 25 | 17 | 7 | 13 |
| Antonio Rodrigo Nogueira | 25 | 21 | 8 | 8 |
| Dan Henderson | 22 | 19 | 12 | 4 |
| José Aldo | 19 | 19 | 4 | 12 |
| Dominick Cruz | 18 | 17 | 6 | 9 |
| Eddie Alvarez | 32 | 30 | 8 | 7 |
| Gegard Mousasi | 3 | 3 | 1 | 24 |
| **Mirko Cro Cop** | **0** | 0 | **0** | — |
| **Ben Askren** | **0** | 0 | **0** | — |
| **Ronaldo Souza** | **0** | 0 | **0** | — |
| Alistair Overeem | 1 | 1 | 1 | 20 |

Two facts, both decisive:

- **Fedor is highly connectable.** 24 of his 40 non-UFC opponents are UFC-rated
  fighters with real UFC careers behind them. He is not a floating island; the
  bridge is strong enough to place him on the main scale with a defensible
  interval.
- **The cache is ragged, not merely partial.** Cro Cop, Askren and Jacaré have
  *zero* bouts and Overeem has one, despite long non-UFC careers. This is the
  fingerprint of a bounded seed crawl (302 profiles, depth-one expansion), not
  of a data source. Rating on this cache as-is would produce confident-looking
  numbers for some legends and nothing at all for others — which is worse than
  the current honest silence, and is the mechanism behind the earlier
  "Fedor reference #4 → model #105" artifact.

**Blocks:** any all-time claim, the entire pre-2010 heavyweight and
lightweight picture, WEC-era Aldo/Cruz/Faber, and the credibility of the phrase
"all-time" on the board.

### 3.2 (S2) Organisation strength and data reliability are conflated — and leak

`loaders/sherdog_loader.compute_fight_weights` derives a non-UFC bout's weight
from *"the percentile of their established UFC rating"* — the participants'
**eventual** UFC careers, with one inference hop across the completed graph.

Three separate defects in one function:

1. **Temporal leakage.** A 2004 PRIDE bout is weighted by what those fighters
   did in the UFC years later. No rolling-origin evaluation over this is honest,
   because the weight already knows the future.
2. **Conceptual conflation.** "This promotion's fighters were weaker" (a
   *location* fact about a population) and "this record is less reliably
   documented" (a *precision* fact about an observation) are different things
   being expressed by one number.
3. **Structural bias toward the UFC.** Weighting a bout by its participants'
   UFC caliber guarantees that a fighter who never entered the UFC cannot
   accumulate full-weight evidence — the answer is assumed before it is
   estimated. This is precisely the question Fedor exists to test.

### 3.3 (S2) Era depth is neither measured nor reported — and the naive measure is confounded

The retired era premium was a **monotone** ladder (a running maximum over
year-means). Your own counterexample refutes monotonicity directly: heavyweight
today is not deeper than heavyweight in 2013. Measured — mean rating of the top
five active fighters in that division-year:

| year | Heavyweight | Lightweight | Welterweight |
|---|---|---|---|
| 2013 | 1746 | 1756 | 1724 |
| 2016 | 1760 | 1851 | 1772 |
| 2019 | 1804 | 1847 | 1765 |
| 2023 | 1831 | 1855 | 1815 |
| **2025** | **1716** | **1866** | 1856 |
| 2026 | 1779 | 1818 | 1771 |

Heavyweight in 2025 sits **150 points below** lightweight in the same year,
having been level with it in 2013. Your Aspinall observation is visible in the
data. A monotone era ladder would have erased it, which is a second, independent
reason the premium deserved to die.

**But the naive reading is unsafe.** Every division drifts upward (~1700 → ~1830)
and WHR re-anchors the global mean over *all* appearances each pass. As the
roster grows and adds low-rated fighters, the top pulls away from the mean for
reasons that have nothing to do with difficulty. **Absolute rating levels are
not comparable across eras without an explicit bridge argument.** Any era claim
must be made in a scale-free form (percentile within the contemporaneous field)
or supported by cross-era bridging fighters.

Worked example — your Jon Jones claim, tested both ways:

| period | mean opponent rating | mean opponent **percentile in their division-year** |
|---|---|---|
| 2008–13 | 1575 | 0.692 |
| 2014–15 (Teixeira, Cormier) | 1766 | **0.943** |
| 2016–19 (OSP, Gustafsson II, Smith, Santos) | 1559 | **0.762** |
| 2020–26 (Reyes, Gane, Miocic) | 1751 | 0.902 |

The claim is **directionally right but mis-located**. Jones's weak stretch is
the 2016–19 light-heavyweight title run at the 76th percentile, not his most
recent bouts, which are back at the 90th. And note how differently the two
columns read: raw ratings make 2016–19 (1559) look comparable to 2008–13 (1575),
while the scale-free measure shows 2008–13 was an *ascent* through the division
and 2016–19 was a *decline* in opposition from a peak. The engine currently
publishes neither column.

### 3.4 (S2) All evidence is weighted equally

`ω_b = 1` for every bout. A 25-minute five-round championship fight and a
three-round preliminary count identically. The likelihood already *has* the
precision term — it is simply pinned at one. Measured availability of the
inputs: 7,659 three-round bouts, 773 five-round bouts, plus `end_round`,
`end_time_seconds`, `method_class` and `time_format` on both the UFC and
cross-org tables.

### 3.5 (S1) The board is not identified beyond first place

150-replicate bootstrap, field-mean bar: median rank-interval width of 102
places across the top 50; **no pair inside the top twenty is separated**. The
higher bar makes this worse, not better (top-25 median width 64 → 101 at the
90th percentile), because raising the bar discards contributing years.

This is the most under-appreciated gap in the project: **more precision in the
rating layer will not fix it if the career functional itself is noisy.** Adding
non-UFC data will help (more evidence per fighter); adding bonuses would not.

### 3.6 (S3) Achievement has no first-class surface

Titles, defences, lineage and ranked wins were correctly evicted from the skill
score — and then not given a home. The result reads as though the engine
considers them worthless, which is not the claim. The claim is that they are a
**different estimand**, and a platform that says so should *publish* them.

### 3.7 (S3) Data hygiene in the cross-org cache

934 distinct `org` labels for 4,023 bouts, including mojibake duplicates
(`1º Round Combat` appearing under several manglings). Promotion identity is
currently unusable as a grouping key. Name matching across sources is a known
trap in this project (hyphens, ring names, date drift) and cross-org ingestion
multiplies its blast radius.

### 3.8 (S3) The evaluation harness is under-powered for the questions being asked

The virtual-game comparison was unresolved on 406 decided bouts — every paired
interval crossed zero. Any new precision term will face the same wall unless the
harness grows: more held-out events, and **segment-specific tests** on the bouts
where a term is supposed to bite (thin records, five-round fights, cross-org
bouts) rather than diluting the signal across all bouts.

### 3.9 (S1) The model has no notion of age — and its prior is misspecified because of it

WHR's Wiener prior is **driftless**: `theta(t+D) - theta(t) ~ N(0, w^2 D)`. It
asserts that a 24-year-old and a 41-year-old are, before seeing results, equally
likely to improve as to decline. The data disagrees, strongly and monotonically.

Population aging curve, measured 2026-08-21 (14,225 appearances with a known date
of birth — 84% of history rows; `dob` is present for 3,749 of 4,516 fighters):

| age at bout | raw rating change / yr | **field-relative change / yr** (percentile pts) | 95% CI | n |
|---|---|---|---|---|
| <24 | -0.5 | -0.69 | +/-0.42 | 553 |
| 24-27 | -2.9 | -1.19 | +/-0.22 | 1,973 |
| 27-30 | -4.2 | -1.62 | +/-0.16 | 3,669 |
| 30-33 | -6.0 | -1.98 | +/-0.15 | 3,887 |
| 33-36 | -7.7 | -2.48 | +/-0.18 | 2,556 |
| 36-39 | -8.8 | -2.78 | +/-0.26 | 1,159 |
| 39-42 | -9.5 | -3.21 | +/-0.49 | 324 |
| 42+ | -10.3 | -2.67 | +/-0.87 | 102 |

Median peak age is **28.9** (IQR 26.6-31.8, fighters with 8+ bouts). The
field-relative column removes the population-drift confound of section 3.3; the
**differences between buckets are the aging signal**, and every interval excludes
zero. The common negative offset present even in the youngest bucket is *not* yet
attributed — debut opposition quality, roster churn and smoother back-propagation
are all candidates — so only the differences should be relied on.

#### What the misspecification costs: a late collapse retroactively deletes the peak

Refitting the smoother on data truncated before each fighter's decline, and
comparing the same appearance's rating in the full-career fit:

| fighter | peak rating, truncated fit | same date, full fit | **revision** |
|---|---|---|---|
| Tony Ferguson (cut 2020) | 1881 | 1600 | **-281** |
| Anderson Silva (cut 2013) | 1976 | 1766 | **-210** |
| BJ Penn (cut 2011) | 1704 | 1580 | **-124** |
| Jon Jones (cut 2013) | 1860 | 1967 | **+107** |

A smoother *should* revise the past — that is its job, and some of these fighters
were genuinely declining before the losses arrived. But the mechanism producing
these magnitudes is the driftless prior: with `E[dtheta] = 0` at every age, the
only way to explain "high, then very low" is to **split the difference across the
whole trajectory**, pulling the peak down and the trough up. The model has no way
to say *"a 36-year-old losing four straight is what aging looks like."*

So Tony Ferguson's 2019 peak is scored 281 points lower because of 2020-2023,
while Jon Jones, who never collapsed, is revised *upward*. As it stands the
engine quietly rewards fighters for retiring on time.

**This is the same parameter family as the cross-era problem in E2.** Both are
governed by how the prior treats rating change over time, and both are currently
answered by an unfitted constant.

---

## 4. The design

### E1 — Evidence precision: the legitimate home for rounds, duration and stakes

**This is the reconciliation.** The retired machinery was wrong because of its
*form*, not its subject matter:

```
retired (bonus form):     θ_i  ←  θ_i + title_bonus + rank_bonus + activity_bonus
proposed (precision form): ℓ_b  =  ω_b · [ y_b log σ(θ_i−θ_j) + (1−y_b) log σ(θ_j−θ_i) ]
```

A bonus adds points to a *score*. A precision changes how strongly a *single
observation* moves both fighters. The differences are not cosmetic:

- **It cannot inflate anyone.** A high-precision loss hurts exactly as much as a
  high-precision win helps. There is no direction to game.
- **It is symmetric by construction**, so it stays a valid joint likelihood —
  the WHR contract already rejects side-specific weights.
- **It is falsifiable.** A precision term either improves held-out prediction on
  the bouts it applies to, or it does not ship.
- **It cannot double-count opponent quality**, because opponent quality is not
  in `ω_b` — it is in `θ_j`, where it already was.

Proposed terms, each with one parameter:

| Term | Form | Rationale | Identification |
|---|---|---|---|
| Scheduled rounds | `ω ∝ (R/3)^α`, α ∈ [0,1] | 25 scheduled minutes sample the skill difference more thoroughly than 15; a flash knockout is a coin-flip in either. | Non-title five-round main events (post-2012) break the collinearity with title status. |
| Realised duration | `ω ∝ (t/t_ref)^β` | A decision after 25 minutes is more evidence than a 30-second finish — *about relative skill*, not about dominance. | Present on both tables (`end_round`, `end_time_seconds`). |
| Championship bout | indicator, one coefficient | **Tested, not assumed.** Plausibly lower-variance (full camps, no short notice); plausibly nothing once ratings are controlled. | Ratings are controlled automatically by the harness. |
| Source reliability | per-source constant | A bout reconstructed from a thin record is a noisier observation than a fully documented one. **This is the only legitimate use of promotion identity in the rating layer.** | Cross-org vs UFCStats. |

**Explicit non-goal:** dominance and method stay *out* of `ω_b`. A one-sided
decision and a knockout are the same evidence about who is better; the earlier
research arm found no resolved benefit, and dominance already has a home as a
published diagnostic.

**On "beating high-quality ranked opponents is valuable":** this is already
exact in the model and needs no new term. The gradient of the likelihood is
`ω_b(y_b − σ(θ_i − θ_j))`, so beating a higher-rated opponent produces a larger
update *precisely in proportion to how unexpected it was*. Adding a rank bonus
on top would be the double posting the principle forbids. Official rankings stay
out of the rating layer for a second reason too: they are media ballots
correlated with the outcomes being predicted, so feeding them in would launder
consensus into "evidence".

### E2 — Whole-sport joint fit, with **no organisation weight at all**

The current design asks "how much is a PRIDE bout worth relative to a UFC
bout?" — and answers it with a number derived from the future. **The question is
malformed.** Fit every bout on one scale in one joint estimation, and org
strength stops being a parameter: it emerges from the fighters who crossed
between promotions. Relative promotion strength is *output*, not input.

What replaces the weight:

1. **One joint fit** over UFC + non-UFC bouts. No org term. Bridge fighters
   (Hendo, Werdum, Big Nog, Barnett, Overeem, Sylvia, Arlovski …) determine the
   relative scale, exactly as they should.
2. **Source reliability only** in `ω_b` (E1), reflecting documentation quality —
   never promotion prestige.
3. **Connectivity as an uncertainty statement, not a discount.** A weakly
   bridged fighter does not get their rating shrunk toward the UFC; they get a
   **wide interval**, and below a stated floor they are published as *unranked —
   insufficiently connected*. This is the completeness abstention rule, applied
   to graph structure.

**What actually sets the relative scale.** Not any single crossover, and not a
promotion parameter — there is none. The current cache already contains **615
bridge fighters carrying 5,565 UFC bouts** (239 with 10+ UFC bouts, 54 with
20+). That ensemble constrains where the populations sit relative to each other,
and non-crossover fighters are anchored through multi-hop paths: Fedor never
entered the UFC, but 24 of his opponents did.

Note that a bridge fighter's rating is not *transplanted* across promotions.
Every one of their bouts, in either promotion, is a term in the same likelihood;
their trajectory is whatever explains all of it at once.

**Threat to validity — crossover timing is selected, not random.** Fighters
change promotions at a particular point in their careers, and often a late one:
much of the PRIDE roster reached the UFC after the 2007 buyout, past peak. A
*static* rating fit to this would conclude PRIDE was weak when it was in fact
measuring aging.

The architecture survives this only because WHR is time-varying: a fighter's
2004 rating and 2008 rating are separate points on one trajectory linked by a
random walk, so decline is modelled as decline rather than charged to the
promotion. This is the strongest single argument for the smoother, and it makes
`WHR_W2_PER_DAY` — the permitted drift rate — the **load-bearing parameter of
the whole cross-org design**. Too rigid and UFC-era losses drag down the
PRIDE-era peak; too loose and nothing is tethered.

`WHR_W2_PER_DAY` has never been fitted; it ships at a plausible prior. That is a
minor sin at UFC-only scope and an unacceptable one here. **Fitting it by
held-out prediction is a prerequisite of Phase 3, not an optimisation** — and it
should be checked for stability across eras, since a drift rate estimated mostly
from the modern UFC may not describe 2003.

A second, smaller effect in the same place: rules and environment differ across
promotions (ring versus cage, soccer kicks, ten-minute opening rounds). Where a
fighter is genuinely better or worse under different rules, that is a real change
in their trajectory rather than measurement error, and the time-varying model
will absorb it as such. It is only a problem if someone later tries to read a
single career-average number as "their true level".

Per-fighter connectivity should be reported explicitly: number of distinct
bridge opponents, number of edge-disjoint paths to the UFC core, and the depth
of those bridges' own records. Fedor at 24 bridged opponents (median 11 UFC
bouts each) would clear any sane floor; Cro Cop at zero would abstain — and
abstention would correctly say *"we have no data"* rather than *"he was not
good"*.

**Leakage rule, absolute:** no quantity derived from a fighter's post-cutoff
record may enter any weight, at any point. The prequential harness must rebuild
everything it uses inside each fold, and `CACHE_SCHEMA_VERSION` must be bumped
when this lands.

### E3 — Field depth: measured, non-monotone, and used for reporting first

Define, per division-year, on the joint fit:

```
D(d, a)  =  mean rating of the top-K active fighters in division d, year a
C(d, a)  =  the contender line: the K-th highest active rating
```

Properties this must have, all of which the retired premium lacked: it is
**per-division** (heavyweight 2025 ≠ lightweight 2025), it is **non-monotone**
(2014 and 2025 heavyweight dips survive), and it is **measured, not assumed**.

Three uses, in increasing order of how much argument they need:

1. **Reporting (ship first, no model change).** Publish opponent quality as a
   percentile within the division-year field — the column that relocated the
   Jones dip from "recent" to 2016–19. This alone answers most era questions and
   risks nothing.
2. **Context for the achievement ledger.** A title reign is annotated with the
   depth of the field it was won in. Aspinall's heavyweight run and Khabib's
   lightweight run stop looking identical on paper.
3. **Optionally, the career functional's reference field** (§E5) — the one that
   needs a decision, not just an implementation.

**Caveat that must travel with every one of these:** absolute level differences
across eras are only trustworthy to the extent that fighters bridge those eras.
Report the bridge density alongside any era claim, and prefer scale-free
percentiles wherever they will do.

### E4 — The achievement ledger, and the standing view

A separate, factual artifact — no estimation, no bonuses, no blending:

- title fights, wins, defences, lineage, interim status, undisputed unifications
- ranked-opponent wins, by the *engine's own* contemporaneous ranking and by the
  official one, reported side by side
- the field depth each of those happened in (E3)
- longest runs at the top of a division, with dates

This honours "title fights are valuable" **without** contaminating the skill
estimate: it publishes the achievement as a fact, dated and contextualised,
rather than converting it into rating points at an exchange rate nobody can
justify. A "standing" view may then present skill and achievement **side by
side** — two columns, never one silently blended number, so a reader who weighs
titles heavily and one who weighs skill heavily can both use the same page and
see exactly where they diverge.

### E5 — The one open decision: what the career functional measures against

Career mass is `Σ_a [ θ̄_ia − bar_a ]₊`. Whole-sport scope forces the
`bar` question to be settled, because the reference population is about to
change underneath it.

| Option | Reads as | Aspinall case | Cost |
|---|---|---|---|
| **A. Relative** — bar is the contemporaneous field | "how far above his peers" | Dominating a thin heavyweight era yields a *large* gap → **more** credit | Rewards lapping a weak field; the effect you flagged |
| **B. Absolute** — bar is a fixed level on the joint scale | "how high he actually was" | A thin era holds his rating down (he beat lower-rated opponents), so he earns **less** | Depends entirely on cross-era bridging being real |
| **C. Hybrid** — relative bar, contribution capped by field depth | "dominance, discounted when the field is thin" | Explicitly discounts the thin era | Adds a parameter; must be measured, not asserted |

**Your Aspinall argument is an argument for B or C, not A** — and the engine
currently runs A. That is the single most consequential choice in this document,
and it is a product judgement about what "all-time great" should mean, not a
question the data can settle on its own. What the data *can* say, and should be
made to say before you decide: whichever option is chosen must be run through
the bootstrap, because we already know identification is fragile and the current
evidence is that a stricter bar costs precision.

### E6 — Age: the prior expects decline, the ledger records who beat it

Two changes, deliberately in two different layers, because age answers two
different questions.

#### E6a (skill layer) — an age-dependent drift in the Wiener prior

```
current:   theta(t+D) - theta(t)  ~  N( 0,            w^2 D )
proposed:  theta(t+D) - theta(t)  ~  N( mu(age) * D,  w^2 D )
```

`mu(age)` is the population aging curve of section 3.9 — **estimated from the
data, not assumed**, and re-estimated with the model rather than hard-coded. This
is not a bonus and does not violate Single-Entry: it is a prior expectation,
which the likelihood is free to overrule. It is the same kind of object as the
virtual games already in the model.

What it buys, precisely:

- **A late collapse is explained by aging instead of by lowering the peak.** This
  is the direct fix for the Ferguson / Silva / Penn revisions above, and it is
  what makes Prime and Peak trustworthy for fighters who fought too long.
- **Late-career excellence becomes measurable as excess over expectation**
  rather than being invisible.
- **Thin late-career records stop being treated as though nothing changed.** A
  38-year-old returning from two years out is expected to be worse, which is the
  honest prior.

**The risk, stated plainly:** an age prior *assumes* decline, so for a fighter
with very few late bouts the prior can dominate the evidence and push them down
for no reason but their birthday. It must be tested on the segment where it bites
— bouts involving fighters over 35 — and shipped only if it earns its place
there, under the same unresolved-means-unresolved rule that governed the
virtual-game mass.

#### E6b (achievement layer) — the aging residual

Age changes how *remarkable* a performance is; it does not change how *good* the
fighter is. Skill stays in the rating; remarkability goes in the ledger.

The naive metric — percentile among same-age fighters — is measurable today and
supports the Glover/Prochazka reading, but by a narrower margin than expected:

| fighter | year | age | rating | percentile among same-age fighters | peers |
|---|---|---|---|---|---|
| Glover Teixeira | 2021 | 42.0 | 1646 | **0.956** | 45 |
| Jiri Prochazka | 2022 | 29.7 | 1714 | 0.932 | 1,580 |
| Randy Couture | 2007 | 44.2 | 1580 | 0.850 | 20 |
| Daniel Cormier | 2018 | 39.6 | 1801 | 0.993 | 138 |

**That metric understates the case, for a structural reason.** The pool of active
42-year-olds is 45 fighters and is *already* a survivor-selected elite; the
29-year-old pool is 1,580 and contains everyone. Sitting at the 96th percentile
of 45 survivors is a much higher bar than the 93rd of 1,580 all-comers, and a
cross-sectional percentile cannot see the difference.

The measure that can:

```
aging residual = actual rating at age A
                 - rating predicted by applying mu(age) to that fighter's
                   own earlier trajectory
```

Per-fighter, anchored to their own baseline, it answers "how much better did he
age than the population says he should have?" — which is exactly the Glover
claim, and it is not survivorship-confounded the way a cross-sectional percentile
is. If that proves insufficient, the stricter object is a **cohort transition**
measure: of fighters at level X at age 30, what share are still at level Y at 42.

Ledger entries this enables, all factual and dated: age at first title, age at
last title defence, aging residual at peak and at each title win, and a career
shape classification (early peak / plateau / late bloomer / cliff) read off the
trajectory.

#### E6c — opportunity, not skill: the Askren case

A fighter who arrives at 34 has fewer years in which to accumulate anything.
Career Skill Mass is a **sum over years**, so it necessarily reflects that — by
definition, not by defect. Two honest responses, both already partly built:

1. **Publish the rate alongside the total.** `symon_career_mean_year_excess`
   already exists and is the vertical axis of the years-vs-height chart, where a
   short, high career sits up-and-left. Surface it as a first-class companion
   column so "great but brief" is legible beside "great and long".
2. **Fix the actual truncation.** Askren's short window is largely a *UFC-scope
   artifact*: his Bellator and ONE years exist and are simply not rated (section
   3.1, where his cached non-UFC bout count is currently **zero**). Whole-sport
   scope, not an age adjustment, is the real repair.

---

## 5. Irredundancy matrix

The audit table. **A signal appearing in two rows is a bug, not a design
choice**, and each row should acquire a test that fails if it moves.

| Signal | Single home | Explicitly NOT in |
|---|---|---|
| Win / loss / draw | bout likelihood | anywhere else |
| Opponent quality | opponent's latent `θ_j` | no rank bonus, no résumé bonus, no quality multiplier |
| Scheduled rounds / duration | `ω_b` precision | not a score bonus |
| Championship status | `ω_b` **only if it survives a held-out test**; otherwise ledger only | not a rating bonus, ever |
| Official rankings | achievement ledger + external validation | never a rating input |
| Promotion identity | `ω_b` **as documentation reliability only** | not a strength discount — strength comes from bridges |
| Era / field depth | reporting, ledger context, and (pending E5) the reference bar | not an additive rating premium |
| Method / dominance | published diagnostic | not `ω_b`, not the score |
| Activity / layoff | display-time attenuation, clearly labelled | not career mass |
| Age | prior **drift** `mu(age)` in the skill layer; **aging residual** in the ledger | never a bonus or penalty applied to a finished score |
| Integrity (PED/DQ) | ledger + explicit debit board | not propagated through the opponent graph |
| Data completeness | abstention gate | not a low rating |
| Uncertainty | refit intervals | never a hand-set constant |

---

## 6. Validation protocol

Nothing ships on plausibility. Each expansion must clear all four gates.

**Gate 1 — Metamorphic tests.** Properties that must hold by construction:
reciprocal forecasts sum to one; a shared precision keeps winner and loser
gradients opposite; doubling `ω` on a bout moves both fighters more; adding a
disconnected promotion changes no existing rating; removing all of a fighter's
bridges widens their interval rather than moving their point estimate.

**Gate 2 — Held-out prediction, on the segment where the term bites.** Overall
log loss will dilute a term that applies to 9% of bouts (five-rounders). Report
the targeted segment *and* overall, with paired event-level intervals, and
**declare "unresolved" when the interval crosses zero** — as was done for the
virtual-game mass rather than claiming a win.

**Gate 3 — The case panel.** These fighters are the reason for the work, and
each carries a specific question. Their placements are *diagnostics to be
explained*, never targets to be hit — the project rule against tuning to an
external list applies with full force here:

| Fighter | The question they test |
|---|---|
| Fedor Emelianenko | Can a strong non-UFC career be placed at all, with a defensible interval? |
| Mirko Cro Cop | Does a data hole abstain loudly instead of scoring low? |
| Wanderlei Silva / Big Nogueira | Do PRIDE-era careers land coherently relative to their UFC-era opponents? |
| José Aldo, Cruz, Faber | Does WEC history join the UFC record without a seam? |
| Tom Aspinall | Does a thin-era champion read differently from a deep-era one? |
| Jon Jones | Does the 2016–19 dip appear where the percentile analysis says it is? |
| Alexander Volkanovski / Makhachev | Do existing top placements survive the scope change, or move for a *stated* reason? |
| Tony Ferguson, Anderson Silva, BJ Penn | Does a long decline stop deleting the peak? Their Prime and Peak scores should rise; their *current* rating should not. |
| Glover Teixeira vs Jiri Prochazka | Does a title won at 42 read as more remarkable than one won at 29, in the ledger rather than in the rating? |
| Ben Askren, Michael Chandler | Does a late arrival stop being punished for years the UFC never gave them? |

**Gate 4 — Uncertainty.** Every change is re-bootstrapped. A change that
improves a point estimate while widening intervals has not obviously improved
anything, and must say so.

---

## 7. Sequenced roadmap

Each phase has an exit criterion. **No phase begins before the previous one
exits**, because every later phase's evidence is contaminated by an unfixed
earlier one.

### Phase 0 — Reporting-only era work *(no model change; lowest risk, immediate value)*
- Division-year field depth `D(d,a)` and contender line `C(d,a)` as an artifact.
- Opponent-quality percentile column and a per-fighter "quality of opposition
  over time" chart (the Jones diagnostic, generalised).
- **Exit:** the Aspinall and Jones questions answerable from the notebook without
  any new rating term.

### Phase 1 — Evidence precision `ω_b`
- Implement rounds/duration/reliability precision; keep championship status as a
  tested candidate.
- Grow the harness: more held-out events, segment-specific scoring.
- **Exit:** each term either shows a resolved held-out gain on its own segment,
  or is dropped and recorded as unresolved. No term ships on plausibility.

### Phase 1b — Age-aware drift *(prerequisite for trustworthy Prime/Peak)*
- Estimate the population aging curve `mu(age)` jointly with the model.
- Fit `WHR_W2_PER_DAY` at the same time — drift rate and drift mean are not
  separately meaningful, and neither has ever been fitted.
- Re-run the truncation test of section 3.9: the Ferguson / Silva / Penn peak
  revisions must shrink materially, and Jon Jones's upward revision must not
  become a downward one.
- **Exit:** held-out prediction on over-35 bouts is not worse, the peak
  revisions shrink, and the aging curve is stable across eras (a curve fitted
  mostly on the modern UFC must not be assumed to describe 2003).

### Phase 2 — Data foundation for whole-sport scope
- Replace the bounded seed crawl with **roster-complete ingestion** for a small
  number of promotions that matter historically: PRIDE, WEC, Strikeforce,
  Affliction, Bellator, RIZIN. Completeness *per promotion* beats breadth across
  934 labels.
- Canonical promotion identity (kill the mojibake duplicates); extend the name
  matching audit to cross-org rosters.
- Publish a coverage matrix: per promotion, per year, bouts ingested vs known.
- **Exit:** Cro Cop, Askren, Jacaré and Overeem have their real records, and
  every included promotion has a stated completeness figure.

### Phase 3 — Joint fit and connectivity
- **Fit `WHR_W2_PER_DAY` by held-out prediction first** — it governs whether a
  cross-era peak survives a later decline, and is currently an unfitted prior.
- Remove `compute_fight_weights` entirely; one joint estimation, no org term.
- Connectivity metrics, abstention floor, connectivity-aware intervals.
- Bump the prequential cache schema; verify no weight touches post-cutoff data.
- **Exit:** the case panel is explicable, and the UFC-only board either survives
  or moves for reasons that can be named fighter by fighter.

### Phase 4 — Achievement ledger and the standing view
- Titles, defences, lineage, ranked wins, field-depth context.
- Side-by-side skill and achievement presentation.
- **Exit:** "title fights are valuable" is visibly honoured with zero rating
  points transferred.

### Phase 5 — Settle the reference bar (E5)
- Implement A/B/C behind the existing `reference=` parameter, bootstrap each.
- **Exit:** a decision recorded *with* its identification cost, not a silent
  default.

---

## 8. Risks and non-goals

**Risks**

- *Ragged data masquerading as coverage.* The failure mode that produced Fedor
  at #105. Mitigation: per-promotion completeness figures and abstention.
- *Cohort growth faking regression.* A longer leaderboard worsens integer ranks
  without any fighter declining. Mitigation: compare percentiles and common
  subsets — already in `analysis/fightmatrix_validation.py`.
- *Name collisions at scale.* Mitigation: extend the existing audit before
  ingestion, not after.
- *Precision terms quietly becoming bonuses.* Mitigation: the irredundancy
  matrix, with tests.
- *Identification getting worse, not better.* More fighters and a wider scale can
  widen intervals. This is honest, and must be reported rather than hidden by
  quoting point estimates.
- *Selected crossover timing mistaken for promotion strength.* The central
  threat. Mitigation: the time-varying smoother, a fitted `WHR_W2_PER_DAY`, and
  a direct check — compare bridge fighters' pre-move and post-move trajectories
  against their age curve. If the model is charging aging to the promotion, the
  bridges will show a systematic step change at the move date that a
  fitted drift rate should have absorbed.

- *An age prior becoming an age penalty.* `mu(age)` assumes decline, and for a
  fighter with few late bouts the prior can outweigh the evidence. This is the
  one proposed change that can systematically move a group of fighters for a
  reason that is not a result. Mitigation: segment-specific held-out testing on
  over-35 bouts, and a metamorphic test that a fighter who keeps winning at 40
  is not dragged down.
- *Survivorship mistaken for late-career greatness.* The pool of active
  42-year-olds is 45 fighters and already elite. Any age-conditional statistic
  must say what it is conditioning on, which is why the aging residual is
  preferred to a cross-sectional percentile.

**Non-goals**

- Matching FightMatrix, the official rankings, or any external list. They are
  benchmarks and sanity checks; agreement is evidence of nothing in particular
  and was never a target.
- A single blended "greatness" number. The separation of estimands is the
  product.
- Predicting fights better than the market. The market is a benchmark; the
  engine's purpose is a defensible retrospective account of skill and
  achievement.

---

## 9. Decisions needed from you

1. **§E5 — the reference bar.** A (relative), B (absolute), or C (hybrid)? Your
   Aspinall argument implies B or C; the engine currently runs A.


   ---Should use C, determine best use case of hybrid. 


2. **Promotion list for Phase 2.** Is PRIDE / WEC / Strikeforce / Affliction /
   Bellator / RIZIN the right historical set, and does regional coverage matter
   or only the majors?

   ---Only the majors is sufficient. 

3. **Abstention floor.** How connected must a fighter be before the board ranks
   them at all? (Fedor: 24 bridges. A floor of, say, 3 bridged opponents with
   real records would include him comfortably and still exclude the truly
   isolated.)

   --Use technical understanding, check against hypothesis by searching famous fighters of each promotion
   and whether the rank makes sense given public chatter.

4. **Decline and the career total.** Career Skill Mass currently clips negative
   years to zero, so hanging around too long is free — it never subtracts. Given
   your Penn / Silva / Ferguson point, is that the behaviour you want (the peak
   is protected, the decline is ignored), or should a "career shape" view show
   the decline explicitly beside the total?

---There should be some impact, but fighters are also just trying to get paid. 
So losses w top opponents or quality opponents count, like Yoel Romero lost 6 fights but all to quality opponents,
but Tony lost to everybody and kept going down, assess best decision here. 

5. **Championship precision.** If a title indicator shows *no* resolved
   predictive effect, is ledger-only treatment acceptable — or do you want it in
   the rating on normative grounds, clearly labelled as such?
---sure. as long as whole thing is principally consistent. 