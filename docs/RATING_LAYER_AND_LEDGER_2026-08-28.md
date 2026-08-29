# Rating layer and ledger — 2026-08-28

**Status: current.** Supersedes the constants, the method-of-victory non-goal and
the "an organisation discount is not identified" line wherever earlier documents
state them. Snapshot `2026-08-13`, published scope `majors,pre_unified`.

Five things were done, in the order they had to be done in, because each one
changes the rating scale the next one is measured on.

| # | Change | Verdict |
|---|---|---|
| 1 | Career functional made scale-equivariant | **shipped**, exact no-op under rescale |
| 2 | The three WHR constants refit on the repaired corpus | **shipped**, `prior_var 4 → 8`, `virtual_games 2 → 1` |
| 3 | The pool offset chased to its mechanism | **not applied to the likelihood**; mechanism identified as selection |
| 4 | Rank the fight, not just the opponent | precision arms **rejected**; the method **score** shipped; the ledger gets a measured pool correction |
| 5 | Boards separated by gender | **shipped** |

Everything below was measured with the §2.8 acceptance rule: paired, event-level
bootstrap, calibration temperature learned **only on strictly earlier folds**,
and unresolved reported as unresolved.

---

## 1. The career functional is now scale-equivariant

**The defect.** `DEFAULT_HINGE_SCALE` was a fixed 25 Elo while the bar it softens
is a statistic *of the ratings*. Apply `mu' = 1500 + beta*(mu - 1500)` — no new
information at all — and the board reordered.

**The repair.** Softness is now `DEFAULT_HINGE_SPREAD_FRACTION = 0.175` times the
population standard deviation of `annual_mean` **inside each calendar year**.
Standard deviation is affine-equivariant, so under any positive rescale the bar,
the excess and the softness all multiply by the same factor and the career score
multiplies with them. 0.175 was set to reproduce the old setting's intent, not a
new one: the median annual spread on this corpus is 142.0 Elo, giving a typical
softness of 24.9 Elo against the old 25.

**Verified on the fitted history, not on a toy** (`out/career_scale_equivariance.csv`):

| beta | rank vector identical | fighters moved | max score error |
|---|---|---:|---:|
| 0.5 | yes | 0 | 2.7e-12 |
| 0.7 | yes | 0 | 1.4e-12 |
| 1.4 | yes | 0 | 1.4e-12 |
| 2.0 | yes | 0 | 5.7e-13 |

95,412 fighter-years, 100/100 top-100 overlap at every beta. The former
behaviour is still reachable exactly: `hinge_scale=DEFAULT_HINGE_SCALE`
reproduces all **33,692** persisted scores with **0** nonzero differences
(`out/career_fixed_hinge_compatibility.csv`). The two modes are mutually
exclusive and passing both raises.

**Consequence for everything else in this document.** The archived
`WHR_VIRTUAL_GAMES` sweep partly measured the functional rather than the prior —
"Travis Fulton is #1 at `virtual_games=24`" is in part a fixed-hinge artifact.
That conclusion has been **re-derived below, not cited**.

---

## 2. The three WHR constants, refit on the repaired corpus

Rolling origin, **14 cutoffs**, 180-day scoring windows, both fighters with at
least three prior corpus bouts. A coarse single-parameter sweep first, then a
joint refinement that also probed the boundary in every direction the coarse
grid left open. Final artifact: 7,641 paired held-out bouts over 1,355 events.

### Selected

`WHR_PRIOR_VAR = 8.0` · `WHR_VIRTUAL_GAMES = 1.0` · `WHR_W2_PER_DAY = 0.0004`

versus the former `4.0 / 2.0 / 0.0004`:

| challenger | delta log loss | 95% CI | verdict |
|---|---:|---|---|
| **pv8, vg1 (selected)** | **-0.00201** | **[-0.00349, -0.00060]** | challenger |
| pv16, vg1 | -0.00186 | [-0.00374, -0.00005] | challenger, but worse than pv8 |
| pv8, vg0.5 | -0.00172 | [-0.00383, +0.00032] | unresolved |
| vg1 alone | -0.00161 | [-0.00243, -0.00081] | challenger |
| pv32, vg1 | -0.00159 | [-0.00371, +0.00045] | unresolved |
| pv8 alone | -0.00099 | [-0.00148, -0.00053] | challenger |
| pv8, vg1, w2=0.0002 | -0.00061 | [-0.00285, +0.00151] | unresolved |

AUC 0.7041 → 0.7067.

### What must be said about it

* **The two terms are not separately identified at this resolution.** Adding
  `prior_var=8` on top of `virtual_games=1` is itself **unresolved**
  ([-0.00107, +0.00023]). The *configuration* clears the gate against the
  shipped base; do not describe each component as independently proven.
* **`WHR_W2_PER_DAY` is unresolved and was left at 0.0004.** The whole-sport
  plan's "fitted `WHR_W2_PER_DAY`" mitigation is therefore **still open**: the
  drift rate was measured, and the measurement did not resolve.
* **The empirical-Bayes fixed point 0.58 is not the answer.** It is the Type-II
  ML solution to an in-sample marginal-likelihood question and it was strongly
  worse predictively. The prior variance moved in the **opposite** direction to
  the EB fit — from 4 up to 8, not down to 0.58.
* **`WHR_VIRTUAL_GAMES` moved down, not up.** This re-derives the archived
  sweep's direction on a repaired corpus and a scale-equivariant functional.
  Raising virtual mass remains refuted.

---

## 3. The pool offset: measured, decomposed, and deliberately not applied

Held out, the ratings are calibrated **within** each pool and mis-located
**between** them. Reproduced under the new constants
(`out/pool_selection_offsets.csv`, seven cutoffs, 120-day windows, 600-draw
event bootstrap):

| segment | n | offset (Elo) | 95% CI | draws positive |
|---|---:|---:|---|---:|
| ever-UFC vs never-UFC (the original) | 486 | **+104** | [+67, +148] | 600/600 |
| **future UFC signee, pre-debut** | 156 | **+274** | [+185, +389] | 600/600 |
| — within 1 year of debut | 58 | +463 | [+290, +521] | 600/600 |
| — 1 to 3 years before debut | 69 | +259 | [+132, +463] | 600/600 |
| — more than 3 years before | 29 | +154 | [+42, +341] | 598/600 |
| **prior UFC experience, fighting outside** | 328 | **+54** | [+10, +100] | 596/600 |
| UFC debutant vs incumbent | 169 | +48 | [-8, +98] | 573/600 |

**The mechanism is selection, and the timing gradient is the evidence.** A
fighter about to be signed already out-performs their rating by +274 Elo
*before* the UFC has anything to do with them, and the excess is monotone in how
soon the signing comes: +463 within a year, +259 at one to three, +154 beyond
three. That is non-ignorable selection on the latent variable — the UFC signs
fighters whose record the model has priced too low — not a promotion strength
term. Consistently, the offset between UFC incumbents and UFC debutants is
**unresolved**.

**No organisation weight was added to the likelihood.** §2.4 stands. Fitting a
level offset on 486 crossing bouts and subtracting it would assert the answer the
joint fit exists to estimate.

**What it does license.** The residual +54 Elo term — a fighter who has already
been UFC-tested, fighting outside — is a standing difference between the two
pools that survives after the crossing has happened. That is used, and only on
the ledger path: see §4.3.

---

## 4. Rank the fight, not just the opponent

Seven cutoffs, 120-day scoring windows, 18 arms, one full WHR refit per arm per
cutoff. 2,039 calibrated held-out bouts over 371 events
(`out/fight_information_scores.csv`,
`out/fight_information_paired_event_bootstrap.csv`).

### 4.1 The precision route is REJECTED — "a title fight tells us more" is false

Giving a bout class a larger shared likelihood weight `omega_b`:

| arm | overall delta | 95% CI | verdict |
|---|---:|---|---|
| `ufc_title_w=1.25` | +0.00021 | [-0.00007, +0.00051] | unresolved, wrong sign |
| `ufc_title_w=1.5` | +0.00041 | [-0.00012, +0.00098] | unresolved, wrong sign |
| `ufc_title_w=2.0` | +0.00079 | [-0.00017, +0.00182] | unresolved, wrong sign |
| `external_title_w=1.25` | +0.00011 | [-0.00012, +0.00034] | unresolved, wrong sign |
| `five_round_w=1.5` | +0.00078 | [-0.00002, +0.00162] | unresolved, wrong sign |

Not one is negative, and on the title bouts *themselves* the UFC-title arm is
worse still (+0.0069 to +0.0265). The falsifiable version of "championship bouts
are lower-variance observations" was tested and it failed. It does not ship, and
the whole-sport plan's proposed `Championship bout` precision term is now
**answered, not pending**.

The `finish_w` precision arms fail differently and instructively: they help on
bouts that ended in a finish and are **significantly worse on decisions** at
every weight (+0.0010 to +0.0049, base favoured). That is reweighting, not
information.

### 4.2 The score route SHIPS — finishes over decisions

`WHR_WINNER_SCORE_COL = "method_score_winner"`: the winner is credited 1.00 for
a KO/TKO or submission, 0.95 for a unanimous decision, 0.90 for a split or
majority one, 0.85 for a DQ. No free parameter was fitted.

| arm | overall delta | 95% CI | verdict |
|---|---:|---|---|
| quarter grading | -0.00092 | [-0.00134, -0.00050] | challenger |
| half grading | -0.00179 | [-0.00264, -0.00094] | challenger |
| **full grading (shipped)** | **-0.00332** | **[-0.00503, -0.00161]** | **challenger** |
| double grading | -0.00456 | [-0.00718, -0.00197] | challenger, not adopted |
| quadruple grading | -0.00546 | [-0.00897, -0.00203] | challenger, not adopted |

AUC 0.6967 → 0.7006.

**The confound was tested and excluded.** A *constant* winner score of 0.980 —
the same mean, with the method grading removed — is worth nothing:
+0.00018 [-0.00033, +0.00065]. At 0.990, +0.00008 [-0.00018, +0.00033]. The gain
is method of victory, not uniform outcome shrinkage.

**Why the grading stops at the staged column.** Sharpening it keeps helping, and
that parameter would be fitted on the same held-out set that has to serve as the
acceptance gate. 1.00/0.95/0.90/0.85 is the column's own design point and was not
chosen here. It is also the reading of "not too much, but enough that they
accumulate".

**This reverses a written non-goal.** `PLAN_WHOLE_SPORT_ENGINE_2026-08-21.md` put
method out of the model in its "Explicit non-goal" and in the `Method /
dominance` row of the irredundancy matrix, on an earlier research arm that
"found no resolved benefit". Re-measured properly, the benefit resolves. Note
the shape of the correction: method is **partial credit on the outcome**, not
extra evidence about the bout — the precision route failed, the score route
passed. Single-Entry is intact, because the fact "how decisively it ended" is
posted once, in `y_b`.

**One model, three call sites.** `ratings.whr.production_score_kwargs` is the
only place that names the constant, and the snapshot fit, the prequential gate
and both bootstrap entry points all go through it. It **raises** rather than
falling back to binary when the column is missing.
`tests/test_published_whr_fit.py` pins this. While fixing it, two bootstrap
callers were found refitting the *old* career functional — sport-wide bar, hard
hinge — so the published intervals described a board nobody publishes. Both now
pass the division bar and the spread-relative hinge.

### 4.3 The ledger: an organisation correction that is measured, not typed

The complaint was Patricio Freire 13th on ten non-UFC title wins against Charles
Oliveira 33rd and Alexandre Pantoja outside the top 100.

`UFC_POOL_OFFSET_ELO = 54.0` is added to a fighter's rating on the **ledger path
only**, when they had already fought in the UFC before the bout being priced. It
is applied to **both** the opponent being priced and the annual means the
contender line is read from, so `q` compares two numbers on one scale.

This reinstates an organisation effect on the title path that was removed on
2026-08-25 — and it is worth being precise about why that removal was wrong. It
rested on two statistics computed **from these same ratings**: P(a random
Bellator title opponent rates above a random UFC one) = 0.477, and a
Bradley-Terry transfer gap of +4 [-4, +28]. A pool offset is exactly what a
within-model statistic cannot see: the smoother has no pool parameter, and free
per-fighter thetas absorb the offset in sample. The out-of-sample measurement is
the one that can see it.

**Measured effect**, on the rebuilt ratings with everything else held fixed
(`out/pool_priced_title_quality.parquet`). Title resume value:

| fighter | offset 0 | offset 54 | change |
|---|---:|---:|---:|
| Georges St-Pierre | 1.184 | 1.598 | +35% |
| Charles Oliveira | 0.276 | 0.365 | +32% |
| Demetrious Johnson | 1.454 | 1.785 | +23% |
| Khabib Nurmagomedov | 0.707 | 0.872 | +23% |
| Jon Jones | 2.406 | 2.800 | +16% |
| Alexandre Pantoja | 0.207 | 0.211 | +2% |
| **Patricio Freire** | **1.040** | **0.847** | **-19%** |
| Usman Nurmagomedov | 0.230 | 0.188 | -18% |

A roughly 50% relative swing between UFC and non-UFC title resumes, from a
number nobody typed. Note Pantoja barely moves and that is the correction
behaving properly: his division's pool is already UFC-tested, so his opponents
and their contender line rise together.

**What the external check says, honestly.** A board-only ledger cannot be
validated by held-out log loss (§2.8), so this repo's protocol is agreement with
external all-time references. It **does not resolve**
(`out/pool_offset_anchor_agreement.csv`, paired bootstrap over anchor names):

| list | n | spearman at 0 -> 54 | delta | 95% CI | resolves |
|---|---:|---|---:|---|---|
| ESPN 21st-century men | 10 | 0.8424 -> 0.8667 | +0.024 | [0.000, +0.190] | no |
| Tapology fan top 10 | 10 | 0.6727 -> 0.5758 | -0.097 | [-0.403, 0.000] | no |
| The 100 Greatest | 34 | 0.4930 -> 0.4747 | -0.018 | [-0.068, +0.022] | no |

One up, two down, **and not one interval excludes zero** — ten to thirty-four
hand-picked names cannot adjudicate a 54-Elo correction. The one thing that does
move consistently is where the anchored fighters sit: median board rank 48.5 ->
46.0 on the largest list. The recognised greats move up while unanchored
regional resumes move down, which is the direction, but the ordering *among* the
anchors is not resolved either way. **The change is carried on the out-of-sample
measurement, not on the anchor lists**, and the anchor result is recorded here as
the non-confirmation it is. `pool_offset_elo=0.0` restores the 2026-08-27
ledger exactly.

**How far it gets the complaint**, on the rebuilt board and after the gender
split (`completeness_gated_board.parquet`, men's):

| fighter | before this pass | now |
|---|---:|---:|
| Patricio Freire | 13 | **22** |
| Charles Oliveira | 33 | **26** |
| Alexandre Pantoja | outside the top 100 | **99** |
| Usman Nurmagomedov | 113 | 95 (of a men-only board) |
| Yaroslav Amosov | — | 119 |
| A.J. McKee | — | 116 |
| Johnny Eblen | 89 | 85 |
| Vadim Nemkov | 56 | 52 |

The published top 25 now reads Jones, St-Pierre, Cormier, Makhachev, Aldo,
Johnson, Volkanovski, Miocic, Silva, Holloway, Khabib, Couture, Ngannou,
Sterling, Topuria, Velasquez, Cruz, Adesanya, Hughes, Liddell, Edgar, Freire,
Dvalishvili, Gaethje, Penn, and `top25_unanchored_count` falls from 4 to **3** —
Ngannou, Sterling and Dvalishvili, all UFC champions absent from the three
supplied lists rather than regional outliers.

The Freire half of the complaint is addressed. The Pantoja half is **not**: 99th
is inside the board but nowhere near the 29th his external anchor gives him, and
the reason is not the organisation question. The ledger sums `q**4` over title
wins, and five wins over opponents sitting near their own division's contender
line cannot reach ten wins over opponents the model rates well above theirs.
What is left is the open estimator defect in §6 — `mu_whr` over-rating
lightly-tested careers — read through a convex weight. It is not repaired by an
organisation term and was not claimed to be.

**The transfer is an assumption, stated.** The offset was fitted on the
prospective filter state and is applied to the retrospective smoother. Both share
one likelihood and one weak pool bridge, so the same identification failure
applies to both; that the *magnitude* carries across is not measured.

---

## 5. The boards are separated by gender

Men's and women's bouts are **disjoint components of the bout graph** — 0 of
80,697 rated bouts and 0 shared opponents join them — so adding a constant to
every rating in the women's component changes no modelled bout probability. The
offset between the two levels is set by the prior. It is not small: 2026-08-25
measured total female career mass running from 0 at -200 Elo to 45,382 at +200,
moving Zhang Weili from rank 30 with zero mass to rank 13 with 886. A mixed board
publishes that unidentified gauge as a rank.

**The first attempt at this was incomplete, and that is worth recording.**
Separating the two published *board artifacts* left every other ranking surface
mixed: the snapshot's headline Career Skill Mass / **Prime** / Public Legacy
prints, the bootstrap rank intervals and tiers, and the notebook's top-N helper
all still ordered men against women. Prime was the worst of them, because Prime
reads `mu_whr` directly with no exposure factor and no resume ledger, so nothing
downstream damps the gauge -- it is exactly the board the handoff predicted would
"move a lot". The rule now lives in **one** module, `ratings/gender.py`, and
every surface goes through it.

* `completeness_gated_board.parquet` is now the **men's** board, and "all-time"
  or "Prime" without a gender means men's.
* `completeness_gated_board_women.parquet` is the women's board, ranked within
  its own component.
* Both README blocks are written by the same `build_boards.py --write-readme`
  run, so they cannot drift, and `GENDER_GAUGE_NOTE` travels with the women's
  block so the board cannot be published without the reason beside it.
* A fighter the gender inference could not label stays on the default board
  rather than being asserted into the women's one. A snapshot with no `gender`
  column gets one mixed board rather than a false claim to have separated
  anything.
* `build_top100_audit.py` audits the **published** population. It was scoring
  the mixed board, which counted Zhang Weili and Rose Namajunas as "unanchored"
  against three anchor lists that are men's lists. Its watch list now spans both
  boards and labels which one a name was found on, so a woman is never reported
  as missing from the men's board.

* `build_uncertainty.py --gender` picks the component the intervals and tiers
  are claimed inside, defaulting to men's, and writes `*_women` artifacts for
  the other. A mixed bootstrap was asking whether Zhang Weili is separated from
  Jon Jones, which no bout in the corpus can answer.
* `ratings.rate_snapshot._print_top` prints one board per component with the
  reason underneath, instead of one mixed table.
* `analysis.viz.top_n_table` defaults to the published component; a mixed view
  now has to be asked for explicitly by passing `gender=None`.
* Three stale **mixed-population** interval artifacts from 2026-08-24 were
  sitting at what are now the men's filenames. Archived, because leaving them
  there would hand a reader a stale mixed board under the men's name.

Published result: 3,481 men ranked and 271 women. The women's top ten is Nunes,
Shevchenko, Zhang, Namajunas, Rousey, Justino, Andrade, Jedrzejczyk, Suarez,
Izawa. Twelve women previously occupied top-100 places on the mixed board, so
twelve men move up; nothing about either ranking's internal order changed.

---

## 5b. The schedule component was measuring UFC tenure

Found by asking why **Fedor Emelianenko sat 44th** on a board whose own ESPN
anchor list has him 6th. The answer was not a judgement about Fedor. Two of the
three components rated him correctly -- his **skill** score of 1023.7 was fourth
among all heavyweights, behind only Jones, Cormier and Ngannou and ahead of
Miocic (859) and Velasquez (644); his **title** score of 605 is a fair reading
of five title wins. His **schedule** score was **75.5**, against Miocic 468,
Couture 790, Velasquez 484, Werdum 428.

**The mechanism.** "Wins over ranked opposition" needs a division to rank
inside, and `performance_adjustment` derived that division from `weight_class`
alone. That column is present on **100%** of UFC rows and **6%** of the Sherdog
majors rows, so 94% of non-UFC bouts had no division and could not enter any
ranked field. A pre-fight division rank was computable on 73.8% of UFC
appearances against **2.2%** of majors ones. Every PRIDE-era name carries the
same signature: Cro Cop 0.0, Kharitonov 0.0, Coleman 6.7, Nogueira 59.1,
Fedor 75.5.

The component was therefore reading **promotion, not schedule** -- exactly what
the contract forbids -- and it is a third of the published score. Measured
across the published top 150, it correlated **+0.53** with a fighter's UFC bout
count, against **-0.25** for skill and **+0.01** for title.

**The repair.** `fill_division_from_career` lets an unlabelled bout borrow the
division of that fighter's **nearest labelled bout in time**. A bout keeps its
own label wherever it has one. On a leave-one-out check over 20,640 labelled
sides, nearest-in-time predicted the true division **83.0%** of the time against
80.1% for the career-modal alternative. Bout-level coverage goes from 16.2% to
**90.8%**; a fighter the corpus never weighed keeps no division and stays out of
every ranked field, which is the honest answer.

It is not free: about **17%** of the filled labels will be the wrong division
for that particular bout -- a fighter moving weight, or a catchweight. Fedor
resolves to Heavyweight on 44 of 47 bouts, Wanderlei Silva keeps a genuine
33/14/2 light-heavy/middle/heavy split.

**Blast radius is the ledger only.** `perf_factor_rank_context` is read by
`legacy_resume` and the dashboard; the published WHR fit reads
`_attach_org_only_weights(rated_fights)`, not the appearance table. Ratings,
Prime and Career Skill Mass are unchanged.

**Effect.** Fedor **44 -> 23**. Cro Cop 206 -> 59, Nogueira 103 -> 46, Barnett
83 -> 39, Coleman 153 -> 81, Hunt 245 -> 181. The UFC-tenure correlation falls
from +0.53 to **+0.48**.

**And the residual is now located.** Decomposing it: the raw rank-context win
mass correlates **+0.327** with UFC bout count, while the *exposure factor*
correlates **+0.699**. The remaining bias is dominated by
`ORG_FACTOR_BY_CANONICAL`, a hand-typed promotion table, whose mean runs 0.560
for fighters with no UFC bouts against 0.877 for those with fifteen or more.

Neutralising it was measured and **not adopted**: it cuts the correlation to
+0.345 but doubles zero-UFC fighters in the top 100 (5 -> 9) and returns
Patricio Freire to 14th, undoing the pool-priced title work. Anchors in the top
100 are 37 under all three arms, so the external check does not discriminate.
The typed table therefore stays, unjustified but load-bearing, and its size is
recorded here rather than left to be rediscovered.

## 5c. The held-out artifact exists again, on the published scope

The snapshot carried no prequential artifact at handoff, so §2.8's acceptance
rule had nothing to run against. It does now, and it runs on the **published**
scope rather than the UFC-only one the harness silently defaulted to before the
`--scope` flag was added (see the defect list above).

24 held-out events, 40 calibration events, 218 scored bouts per variant, both
fighters with at least three prior bouts. 9,569 CPU-seconds:

| variant | log loss | Brier | accuracy | AUC | calibration error |
|---|---:|---:|---:|---:|---:|
| **whr** (published) | **0.6255** | 0.2180 | 0.6560 | **0.7032** | 0.0733 |
| canonical Glicko | 0.6699 | 0.2389 | 0.5459 | 0.6169 | 0.0880 |
| naive 50/50 | 0.6931 | 0.2500 | 0.5642 | 0.5000 | 0.0642 |
| market benchmark | 0.5487 | 0.1846 | 0.7059 | 0.7917 | 0.1283 |

Two things must be said about that table. **The market row is n=17** and is not a
comparison anyone should draw a conclusion from; it is there because the harness
reports it. And **218 bouts is small** — the run's own
`min_n_for_conclusions` is 200, so the overall row barely clears it and several
segments come back flagged `n_sufficient: False`. It is a standing regression
check, not a fresh basis for selecting anything.

What it does support: the retrospective smoother beats the causal filter and the
naive baseline on the published corpus, and its AUC of 0.7032 sits where the
constant refit put it independently (0.7067 on 7,641 paired bouts). Those are two
different harnesses agreeing on the same model.

## 6. What is still open

* **`WHR_W2_PER_DAY` is still asserted.** It was measured and did not resolve.
  The whole-sport plan's central-threat mitigation is not discharged.
* **The estimator defect is untouched, and re-measuring it after this pass says
  so plainly.** Seika Izawa is now **+319** above the best fighter she has ever
  faced (it was +269 before the coverage repair) and Khabib **+206** (+192). The
  ledger correction moved the *board*; it did not touch the rating that produces
  those gaps. The two contender lines in `symon_score` and `legacy_resume` are
  still different statistics, and the 2026-08-26 note's condition — "fix the
  rating, then unify this line" — is still unmet, so they stay different.
* **77 fighters remain truncated** because Sherdog's fightfinder could not
  resolve their name. A name-matching problem, not a crawl problem.
* **The pre-debut +274 Elo selection term is not modelled.** It is knowable only
  retrospectively and pricing an achievement by who was later signed would be a
  look-ahead dressed as a resume.
* **The exposure path still uses the typed `ORG_FACTOR_BY_CANONICAL` table.**
  The measured pool correction was applied to the **title** path, which is where
  the defect was demonstrated; the schedule/exposure component still multiplies
  by hand-set promotion factors. It already produces the right ordering on its
  own (Oliveira 565 against Freire 322 before this pass), so nothing was shown
  to be wrong with it, but "measured, not typed" is only half done. Extending
  the offset there is a separate change needing its own measurement.
* **The stated ordering is delivered in the aggregate, not term by term.** "UFC
  title > top UFC opposition > top outside opposition > regular UFC > regular
  outside" now falls out of the title and schedule components together. No term
  encodes that ordering directly, and none should -- a typed ladder is exactly
  the hand-set exchange rate the value-normalised score exists to avoid.
* **The anchor protocol is underpowered** for anything smaller than a large
  reordering. Ten to thirty-four names cannot resolve a ledger term. A ledger
  change that needs external validation needs a bigger external reference than
  this repo currently has.
