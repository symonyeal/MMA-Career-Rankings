# How the ratings and the score are built — 2026-08-28

**Status: current.** Where an older document disagrees with this one about the
settings, about method of victory, or about whether a promotion discount can be
measured, this document is right. Dataset `2026-08-13`, published scope
`majors,pre_unified`.

Five changes were made, in this order, because each one changes the scale the
next is measured on.

| # | Change | Result |
|---|---|---|
| 1 | Career score no longer shifts when the ratings are rescaled | **shipped** — provably no change under rescaling |
| 2 | Three model settings refitted on the repaired dataset | **shipped** — `prior_var 4 → 8`, `virtual_games 2 → 1` |
| 3 | The gap between UFC and non-UFC ratings traced to its cause | **not added to the model** — the cause is who the UFC signs |
| 4 | Judge the fight, not only the opponent | extra weight for big fights **rejected**; partial credit for how a fight ended **shipped**; the score gets a measured promotion correction |
| 5 | Separate boards for men and women | **shipped** |

## How to read the numbers in this document

- **Log loss** measures prediction error on fights the model had not seen. Lower
  is better. A **negative** change means the new version predicts better.
- Every result carries a **95% confidence interval**. If that interval includes
  zero, the test **did not resolve** — the data cannot tell the two versions
  apart, and we say so rather than claiming a win.
- Tests are run by holding out later fights, fitting on earlier ones only, and
  resampling whole events rather than individual bouts. Nothing that scores a
  version is allowed to have been used to tune it.
- **The result tables below are the evidence.** Each measurement was produced by
  a one-off research script writing to a local working folder; those raw files
  are working material and are not part of the repository, so they are not cited
  here. Where a finding is also enforced in code, the test that enforces it is
  named, and running it is the way to check the claim.

---

## 1. The career score no longer moves when the ratings are rescaled

**The problem.** The softness of the bar a fighter's rating is measured against
was a fixed 25 Elo, while the bar itself was calculated from the ratings.
Multiply every rating by a constant — adding no new information whatsoever — and
the board reordered.

**The fix.** Softness is now `DEFAULT_HINGE_SPREAD_FRACTION = 0.175` of how
spread out the ratings are in that calendar year. Because spread scales with the
ratings, the bar, the margin over it and the softness now all move together, and
the career score moves with them. The 0.175 was chosen to reproduce the old
setting, not to introduce a new one: the typical yearly spread in this dataset is
142.0 Elo, giving a softness of 24.9 Elo against the old fixed 25.

**Checked on the real fitted history, not a toy example.** The property is held
in place by
`tests/test_symon_score.py::test_relative_hinge_is_scale_equivariant_for_the_full_rank_vector`:

| rating multiplier | same order? | fighters moved | largest score error |
|---|---|---:|---:|
| 0.5 | yes | 0 | 2.7e-12 |
| 0.7 | yes | 0 | 1.4e-12 |
| 1.4 | yes | 0 | 1.4e-12 |
| 2.0 | yes | 0 | 5.7e-13 |

95,412 fighter-years, and the top 100 is identical at every multiplier. The old
behaviour is still available exactly: setting `hinge_scale=DEFAULT_HINGE_SCALE`
reproduced all **33,692** stored scores of that build with **zero** differences,
which
`tests/test_symon_score.py::test_fixed_hinge_compatibility_mode_reproduces_the_prior_published_call`
checks on every run. The two modes cannot both be set; asking for both raises an
error.

**What this means for the rest of this document.** An older archived experiment
concluded that raising the model's prior weight promoted journeymen — "Travis
Fulton is #1 at `virtual_games=24`". Part of that was an artefact of the old
fixed softness. That conclusion has been **re-derived below, not quoted**.

---

## 2. Three model settings, refitted on the repaired dataset

Fourteen cut-off dates, scoring the next 180 days each time, requiring both
fighters to have at least three earlier fights in the dataset. A coarse sweep of
one setting at a time first, then a joint refinement that also probed every
direction the coarse grid left open. Final test set: 7,641 held-out fights across
1,355 events.

### Chosen

`WHR_PRIOR_VAR = 8.0` · `WHR_VIRTUAL_GAMES = 1.0` · `WHR_W2_PER_DAY = 0.0004`

against the previous `4.0 / 2.0 / 0.0004`:

| version tested | change in log loss | 95% CI | result |
|---|---:|---|---|
| **pv8, vg1 (chosen)** | **−0.00201** | **[−0.00349, −0.00060]** | better |
| pv16, vg1 | −0.00186 | [−0.00374, −0.00005] | better, but worse than pv8 |
| pv8, vg0.5 | −0.00172 | [−0.00383, +0.00032] | did not resolve |
| vg1 alone | −0.00161 | [−0.00243, −0.00081] | better |
| pv32, vg1 | −0.00159 | [−0.00371, +0.00045] | did not resolve |
| pv8 alone | −0.00099 | [−0.00148, −0.00053] | better |
| pv8, vg1, w2=0.0002 | −0.00061 | [−0.00285, +0.00151] | did not resolve |

Ranking accuracy (AUC) 0.7041 → 0.7067.

### What has to be said about it

- **The two settings cannot be separated at this sample size.** Adding
  `prior_var=8` on top of `virtual_games=1` does **not** resolve on its own
  ([−0.00107, +0.00023]). The pair together beats the old pair. Do not describe
  either one as independently proven.
- **`WHR_W2_PER_DAY` did not resolve and was left at 0.0004.** How fast a
  fighter's true level drifts was measured, and the measurement was inconclusive.
  The open item this was meant to close is therefore **still open**.
- **The textbook automatic answer of 0.58 is wrong here.** It optimises an
  in-sample criterion and predicted markedly worse out of sample. The setting
  moved in the **opposite** direction — from 4 up to 8, not down to 0.58.
- **`WHR_VIRTUAL_GAMES` moved down, not up**, which confirms the archived
  experiment's direction on a repaired dataset and a fixed career formula.
  Raising it stays rejected.

---

## 3. The UFC-versus-outside gap: measured, explained, deliberately not applied

Out of sample, the ratings are well calibrated **within** each pool of fighters
and misplaced **between** them. Re-measured under the new settings, over seven cut-offs, 120-day windows and
600 resamples:

| group | n | gap (Elo) | 95% CI | resamples positive |
|---|---:|---:|---|---:|
| ever fought in the UFC vs never | 486 | **+104** | [+67, +148] | 600/600 |
| **future UFC signing, before their debut** | 156 | **+274** | [+185, +389] | 600/600 |
| — within 1 year of the debut | 58 | +463 | [+290, +521] | 600/600 |
| — 1 to 3 years before | 69 | +259 | [+132, +463] | 600/600 |
| — more than 3 years before | 29 | +154 | [+42, +341] | 598/600 |
| **already UFC-tested, fighting elsewhere** | 328 | **+54** | [+10, +100] | 596/600 |
| UFC newcomer vs UFC regular | 169 | +48 | [−8, +98] | 573/600 |

**The cause is who gets signed, and the timing is the proof.** A fighter about to
be signed already beats their own rating by 274 Elo **before the UFC has anything
to do with them**, and the size of that gap tracks how soon the signing comes:
+463 within a year, +259 at one to three years, +154 beyond three. That is the
UFC spotting fighters the model has priced too low — not evidence that the UFC
makes fighters better. Consistently, the gap between UFC newcomers and UFC
regulars **does not resolve**.

**No promotion weight was added to the model.** Fitting a level difference on 486
crossover fights and subtracting it would assert the very answer the joint fit
exists to estimate.

**What it does justify.** The leftover +54 Elo — a fighter who has already been
UFC-tested, fighting outside — is a standing difference between the two pools
that remains after the crossover has happened. That number is used, and only in
the résumé score, never in the ratings. See §4.3.

---

## 4. Judge the fight, not only the opponent

Seven cut-offs, 120-day scoring windows, 18 variants, a full model refit for each
variant at each cut-off. 2,039 held-out fights across 371 events.

### 4.1 REJECTED — "a title fight tells us more" is simply false

Giving a class of fight more weight in the model:

| version tested | change in log loss | 95% CI | result |
|---|---:|---|---|
| `ufc_title_w=1.25` | +0.00021 | [−0.00007, +0.00051] | no resolution, wrong direction |
| `ufc_title_w=1.5` | +0.00041 | [−0.00012, +0.00098] | no resolution, wrong direction |
| `ufc_title_w=2.0` | +0.00079 | [−0.00017, +0.00182] | no resolution, wrong direction |
| `external_title_w=1.25` | +0.00011 | [−0.00012, +0.00034] | no resolution, wrong direction |
| `five_round_w=1.5` | +0.00078 | [−0.00002, +0.00162] | no resolution, wrong direction |

Not one improved anything, and on the title fights themselves the UFC-title
version is worse still (+0.0069 to +0.0265). The testable version of
"championship fights are more informative" was tested and it failed. It does not
ship, and the proposal for a championship weighting is now **answered, not
pending**.

The finish-weighting versions fail in an instructive way: they help on fights
that ended in a finish and are **clearly worse on decisions** at every weight
(+0.0010 to +0.0049). That is moving weight around, not adding information.

### 4.2 SHIPPED — finishes count for more than decisions

`WHR_WINNER_SCORE_COL = "method_score_winner"`. The winner is credited 1.00 for a
knockout or submission, 0.95 for a unanimous decision, 0.90 for a split or
majority decision, and 0.85 for a disqualification. Nothing here was fitted.

| version tested | change in log loss | 95% CI | result |
|---|---:|---|---|
| quarter grading | −0.00092 | [−0.00134, −0.00050] | better |
| half grading | −0.00179 | [−0.00264, −0.00094] | better |
| **full grading (shipped)** | **−0.00332** | **[−0.00503, −0.00161]** | **better** |
| double grading | −0.00456 | [−0.00718, −0.00197] | better, not adopted |
| quadruple grading | −0.00546 | [−0.00897, −0.00203] | better, not adopted |

Ranking accuracy 0.6967 → 0.7006.

**The obvious alternative explanation was tested and ruled out.** Giving every
winner a flat 0.980 — the same average, with the grading removed — is worth
nothing: +0.00018 [−0.00033, +0.00065]. At 0.990, +0.00008 [−0.00018, +0.00033].
The gain comes from *how* the fight ended, not from shrinking every result.

**Why the grading stops where it does.** Sharpening it keeps helping, but that
sharpening would then be tuned on the same held-out fights that have to judge it.
1.00 / 0.95 / 0.90 / 0.85 is the data column's own design and was not chosen here.

**This reverses a previously written rule.** An archived plan
(`../_archive/20260831-repository-consolidation/docs/PLAN_WHOLE_SPORT_ENGINE_2026-08-21.md`)
listed method of victory as an explicit non-goal, on the strength of an earlier
experiment that found no benefit. Measured properly, the benefit is real. Note
the shape of the correction: method of victory is **partial credit on the
result**, not extra evidence about the fight — the extra-weight route failed and
the partial-credit route passed. Nothing is counted twice, because "how
decisively it ended" is recorded once, in the result itself.

**One setting, one place.** `ratings.whr.production_score_kwargs` is the only
place the constant is named, and the main fit, the accuracy gate and both
resampling entry points all go through it. If the data column is missing it
**raises an error** rather than quietly reverting to win/lose.
`tests/test_published_whr_fit.py` locks this in. While fixing it, two resampling
callers were found still using the **old** career formula, so the published
uncertainty figures described a board nobody publishes. Both now use the current
one.

### 4.3 The résumé score gets a promotion correction that is measured, not typed

The complaint that started this: Patricio Freire 13th on ten non-UFC title wins,
against Charles Oliveira 33rd and Alexandre Pantoja outside the top 100.

`UFC_POOL_OFFSET_ELO = 54.0` is added to a fighter's rating **in the résumé score
only**, and only when they had already fought in the UFC before the fight being
priced. It is added to **both** the opponent being priced and the yearly averages
the contender bar is read from, so the comparison stays on one scale.

This restores a promotion effect on the title path that was removed on
2026-08-25, and it is worth being precise about why that removal was wrong. It
rested on two figures calculated **from these same ratings**: the chance a random
Bellator title opponent rates above a random UFC one, 0.477, and a head-to-head
transfer gap of +4 [−4, +28]. A pool-level gap is exactly what a figure taken
from inside the model cannot see, because the model has no pool setting and each
fighter's own rating absorbs the gap. Only an out-of-sample measurement can see
it.

**Measured effect** on the rebuilt ratings with everything else held fixed.
Title résumé value:

| fighter | no offset | offset 54 | change |
|---|---:|---:|---:|
| Georges St-Pierre | 1.184 | 1.598 | +35% |
| Charles Oliveira | 0.276 | 0.365 | +32% |
| Demetrious Johnson | 1.454 | 1.785 | +23% |
| Khabib Nurmagomedov | 0.707 | 0.872 | +23% |
| Jon Jones | 2.406 | 2.800 | +16% |
| Alexandre Pantoja | 0.207 | 0.211 | +2% |
| **Patricio Freire** | **1.040** | **0.847** | **−19%** |
| Usman Nurmagomedov | 0.230 | 0.188 | −18% |

Roughly a 50% swing between UFC and non-UFC title résumés, from a number nobody
typed in. Pantoja barely moves, and that is the correction working properly: his
division is already UFC-tested, so his opponents and the bar they are measured
against rise together.

**What the outside check says, honestly.** A score that never predicts a fight
cannot be judged on prediction error, so this project's fallback is agreement
with published all-time lists. That check **does not resolve**:

| list | n | agreement, 0 → 54 | change | 95% CI | resolves? |
|---|---:|---|---:|---|---|
| ESPN 21st-century men | 10 | 0.8424 → 0.8667 | +0.024 | [0.000, +0.190] | no |
| Tapology fan top 10 | 10 | 0.6727 → 0.5758 | −0.097 | [−0.403, 0.000] | no |
| The 100 Greatest | 34 | 0.4930 → 0.4747 | −0.018 | [−0.068, +0.022] | no |

One up, two down, and **not one interval excludes zero**. Ten to thirty-four
hand-picked names cannot settle a 54-Elo correction. The one thing that does move
consistently is where the listed fighters sit overall: their median board rank
goes from 48.5 to 46.0 on the largest list. Recognised greats move up while
unlisted regional résumés move down, which is the right direction — but the order
*among* the listed names is not settled either way. **The change is carried by the
out-of-sample measurement, not by the lists**, and the list result is recorded
here as the non-confirmation it is. Setting `pool_offset_elo=0.0` restores the
2026-08-27 behaviour exactly.

**How far it addresses the complaint**, on the rebuilt men's board:

| fighter | before this pass | now |
|---|---:|---:|
| Patricio Freire | 13 | **22** |
| Charles Oliveira | 33 | **26** |
| Alexandre Pantoja | outside the top 100 | **99** |
| Usman Nurmagomedov | 113 | 95 (men-only board) |
| Yaroslav Amosov | — | 119 |
| A.J. McKee | — | 116 |
| Johnny Eblen | 89 | 85 |
| Vadim Nemkov | 56 | 52 |

The published top 25 now reads Jones, St-Pierre, Cormier, Makhachev, Aldo,
Johnson, Volkanovski, Miocic, Silva, Holloway, Khabib, Couture, Ngannou,
Sterling, Topuria, Velasquez, Cruz, Adesanya, Hughes, Liddell, Edgar, Freire,
Dvalishvili, Gaethje, Penn. The count of top-25 fighters absent from all three
published lists falls from 4 to **3** — Ngannou, Sterling and Dvalishvili, all
UFC champions the lists happen to omit, not regional outliers.

The Freire half of the complaint is addressed. **The Pantoja half is not.** 99th
is on the board but nowhere near the 29th an outside list gives him, and the
reason is not the promotion question. The résumé raises each title win to the
fourth power before adding them up, so five wins over opponents sitting near their
own division's bar cannot catch ten wins over opponents the model rates well
above theirs. What is left is the open rating problem in §6 — lightly-tested
careers rated too high — amplified by that fourth power. A promotion term does
not fix it, and was never claimed to.

**One assumption, stated.** The 54 was measured on the fight-by-fight model and
is applied to the whole-career model. Both share one fit and one weak bridge
between pools, so the same limitation applies to both — but that the *size*
carries across is not something we measured.

---

## 5. Men and women are ranked on separate boards

Men's and women's fights form **two completely separate networks** — 0 of the
81,281 rated fights and 0 shared opponents connect them, re-checked after the
2026-09-02 corpus completion — so adding a constant to every
women's rating changes no predicted fight outcome at all. The gap between the two
levels is set by an assumption, not by evidence. It is not small: on 2026-08-25,
sliding that assumption from −200 to +200 Elo moved total women's career mass
from 0 to 45,382, and Zhang Weili from 30th with nothing to 13th with 886. A
combined board publishes that assumption as if it were a rank.

**The first attempt at this was incomplete, which is worth recording.** Splitting
the two published board files left every other ranking surface mixed: the
headline printouts, the uncertainty intervals and tiers, and the notebook's
top-N helper all still ranked men against women. Prime was the worst affected,
because it reads the raw rating with no exposure factor and no résumé to damp the
assumption. The rule now lives in **one** place, `ratings/gender.py`, and every
surface goes through it.

- `completeness_gated_board.parquet` is the **men's** board, and "all-time" or
  "Prime" without a gender means the men's one.
- `completeness_gated_board_women.parquet` is the women's board, ranked within
  its own network.
- All four tables in `RANKINGS.md` are written by the same
  `build_boards.py --write-readme` run. Every marker is checked before a single
  file is written, and the explanatory note travels with each women's table.
- A fighter whose gender could not be determined stays on the default board
  rather than being asserted into the women's one. A dataset with no gender
  information gets one mixed board rather than a false claim to have separated
  anything.
- `build_top100_audit.py` audits the **published** population. It had been
  scoring the mixed board, which counted Zhang Weili and Rose Namajunas as
  "missing from the lists" against three lists that only contain men. Its watch
  list now covers both boards and says which one a name was found on.
- `build_uncertainty.py --gender` picks which group the uncertainty intervals are
  claimed inside, defaulting to men's. A mixed version was asking whether Zhang
  Weili can be separated from Jon Jones, which no fight in the dataset can
  answer.
- `ratings.rate_snapshot._print_top` prints one table per group with the reason
  underneath, instead of one mixed table.
- `analysis.viz.top_n_table` defaults to the published group; a mixed view now
  has to be asked for explicitly.
- Three stale **mixed** interval files from 2026-08-24 were sitting under what
  are now the men's filenames. They were archived, because leaving them would
  hand a reader a stale mixed board under the men's name.

Result: 3,481 men ranked and 271 women. The women's top ten is Nunes,
Shevchenko, Zhang, Namajunas, Rousey, Justino, Andrade, Jedrzejczyk, Suarez,
Izawa. Twelve women had held top-100 places on the mixed board, so twelve men
move up. Nothing about either ranking's internal order changed.

---

## 5b. The schedule component was measuring UFC tenure, not schedule

Found by asking why **Fedor Emelianenko sat 44th** on a board whose own ESPN
reference list has him 6th. The answer was not a judgement about Fedor. Two of
the three components rated him correctly — his **skill** score of 1023.7 was
fourth among all heavyweights, behind only Jones, Cormier and Ngannou and ahead
of Miocic (859) and Velasquez (644), and his **title** score of 605 is a fair
reading of five title wins. His **schedule** score was **75.5**, against Miocic
468, Couture 790, Velasquez 484, Werdum 428.

**The cause.** "Wins over ranked opposition" needs a weight class to rank inside,
and the code took the weight class from one data field. That field is filled in
on **100%** of UFC rows and **6%** of the Sherdog rows, so 94% of non-UFC fights
had no weight class and could not enter any ranked field at all. A pre-fight
ranking was computable on 73.8% of UFC appearances against **2.2%** of the
others. Every PRIDE-era name carries the same signature: Cro Cop 0.0, Kharitonov
0.0, Coleman 6.7, Nogueira 59.1, Fedor 75.5.

The component was therefore reading **which promotion a fighter was in, not who
they fought** — exactly what the project forbids — and it was a third of the
published score. Across the top 150 it correlated **+0.53** with a fighter's
UFC fight count, against **−0.25** for skill and **+0.01** for title.

**The fix.** `fill_division_from_career` lets an unlabelled fight borrow the
weight class of that fighter's **nearest labelled fight in time**. A fight keeps
its own label wherever it has one. Tested by hiding one label at a time across
20,640 labelled records, nearest-in-time predicted the true weight class **83.0%**
of the time, against 80.1% for using the fighter's most common weight class.
Coverage goes from 16.2% to **90.8%**; a fighter the data never weighed keeps no
weight class and stays out of every ranked field, which is the honest answer.

It is not free: about **17%** of the filled labels will be wrong for that
particular fight — a fighter moving up or down, or a catchweight. Fedor resolves
to heavyweight on 44 of 47 fights; Wanderlei Silva keeps a genuine 33/14/2 split
across light heavy, middle and heavy.

**What it affects.** Only the score, not the ratings. The published rating fit
does not read this table at all, so ratings, Prime and career skill are
unchanged.

**Effect.** Fedor **44 → 23**. Cro Cop 206 → 59, Nogueira 103 → 46, Barnett
83 → 39, Coleman 153 → 81, Hunt 245 → 181. The UFC-tenure correlation falls from
+0.53 to **+0.48**.

**And the remaining bias is now located.** Breaking it down: the raw ranked-win
figure correlates **+0.327** with UFC fight count, while the **exposure factor**
correlates **+0.699**. What is left is dominated by `ORG_FACTOR_BY_CANONICAL`, a
hand-typed table of promotion strengths, whose average runs 0.560 for fighters
with no UFC fights against 0.877 for those with fifteen or more.

Removing it was measured and **not adopted**: it cuts the correlation to +0.345,
but it doubles the number of fighters with no UFC record in the top 100 (5 → 9)
and returns Patricio Freire to 14th, undoing the promotion-corrected title work.
The listed fighters in the top 100 number 37 under all three versions, so the
outside check cannot separate them. The typed table therefore stays — unjustified
but load-bearing — and its size is recorded here rather than left to be
rediscovered.

## 5c. The accuracy check exists again, on the published data

The dataset carried no accuracy artefact at handoff, so the acceptance rule had
nothing to run against. It does now, and it runs on the **published** data rather
than the UFC-only subset the harness used to default to silently.

24 held-out events, 40 calibration events, 218 scored fights per version, both
fighters with at least three earlier fights. 9,569 CPU-seconds:

| version | log loss | Brier | accuracy | AUC | calibration error |
|---|---:|---:|---:|---:|---:|
| **published model** | **0.6255** | 0.2180 | 0.6560 | **0.7032** | 0.0733 |
| standard Glicko | 0.6699 | 0.2389 | 0.5459 | 0.6169 | 0.0880 |
| coin flip | 0.6931 | 0.2500 | 0.5642 | 0.5000 | 0.0642 |
| betting market | 0.5487 | 0.1846 | 0.7059 | 0.7917 | 0.1283 |

Two warnings about that table. **The market row is only 17 fights** and nobody
should draw a conclusion from it; it appears because the harness reports it. And
**218 fights is small** — the run's own minimum for drawing conclusions is 200,
so the overall row barely clears it and several breakdowns come back flagged as
too small. Treat it as a standing regression check, not as fresh evidence for
choosing anything.

What it does support: the whole-career model beats both the fight-by-fight model
and the coin flip on the published data, and its AUC of 0.7032 lands where the
settings refit put it independently (0.7067 on 7,641 fights). Two different
harnesses agreeing on the same model.

## 6. Open work

This document owns the implemented method and the evidence behind it. The live
list of unresolved model choices, data work and accepted limitations is kept once,
in [Open decisions](DECISIONS.md).
