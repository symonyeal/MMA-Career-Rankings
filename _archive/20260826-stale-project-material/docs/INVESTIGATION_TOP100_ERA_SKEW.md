# Investigation brief — why the top 100 is 70% active fighters and Randy Couture scores zero

**Status:** brief, not findings. Nothing here is a conclusion.
**Deliverable:** one Jupyter notebook committed to this repo — **not** a Claude artifact,
not a status report. See §6.
**Baseline:** `data/snapshots/2026-08-13`, career mass at `reference=0.9`
(`DEFAULT_CAREER_REFERENCE`, changed from `"mean"` on 2026-08-21).
**All figures below were measured on 2026-08-21 and are re-checkable.**

---

## 1. The problem in one table

The all-time board is supposed to rank careers. It currently ranks people who are
still having one.

| | |
|---|---|
| Top 100 still active in 2024+ | **70 of 100** |
| Top 100 who debuted ≤ 2009 | **18 of 100** (only 2 still active) |
| Median debut year, top 100 | **2015** |

And the tail of the board is worse than the head. These are not marginal figures —
they are fighters with **career skill mass of exactly zero**, meaning not one of
their active years cleared its own year's contender line:

| Fighter | Rank | Mass | Active years |
|---|---:|---:|---|
| Mauricio Rua | 1749 | **0** | 2007–2023 |
| Randy Couture | 2032 | **0** | 2000–2011 |
| Robbie Lawler | 2091 | **0** | 2002–2023 |
| Urijah Faber | 2427 | **0** | 2011–2019 |
| Vitor Belfort | 2461 | **0** | 2002–2018 |
| Wanderlei Silva | 2476 | **0** | 2007–2013 |
| Forrest Griffin | 945 | **0** | 2005–2012 |

Randy Couture is a three-time UFC heavyweight champion and a light-heavyweight
champion. Any board that scores him zero has a defect, and the defect is the
subject of this notebook.

Nearby, less extreme but same direction: José Aldo 33, Frankie Edgar 41,
Chuck Liddell 63, Rich Franklin 68, Matt Hughes 90, Dominick Cruz 98,
BJ Penn 124, Michael Bisping 128, Tito Ortiz 163.

---

## 2. What is already measured — do not re-derive, do check

### 2.1 The bar is almost flat across eras; the ratings are not

The bar a fighter-year must clear (0.9 quantile of that year's rated fighter-years):

| Year | Bar | Rated fighters |
|---|---:|---:|
| 2000 | 1628 | 28 |
| 2006 | 1618 | 174 |
| 2012 | 1656 | 382 |
| 2018 | 1669 | 565 |
| 2024 | **1700** | 625 |

The bar rises **72 points in 24 years**. Meanwhile:

| Fighter | Trajectory | Years clearing the bar |
|---|---|---:|
| Jon Jones | 1915 → 2036 | **14 of 14**, by 294–336 points |
| Merab Dvalishvili | 1701 → 1862 | **9 of 9** |
| Natalia Silva | 1836 → 1845 | **5 of 5**, by ~150 |
| Randy Couture | 1618 → 1551 | **0 of 12** — his best year is 10 points *below* the bar |
| Robbie Lawler | peak 1611 (2014) | **0 of 13** |
| Wanderlei Silva | 1480 → 1499 | **0 of 7**, ~160 points below throughout |

### 2.2 The obvious explanation is refuted

"Ratings inflate over time, so modern fighters clear a flat bar more easily" is
**not supported**. Among fighters with ≥8 UFC bouts, grouped by debut era:

| Debut | n | mean peak | **p90 peak** | mean bouts |
|---|---:|---:|---:|---:|
| 1993–2004 | 39 | 1556 | 1667 | 15.4 |
| 2005–2009 | 135 | 1548 | 1698 | 16.5 |
| 2010–2014 | 255 | 1562 | 1717 | 15.2 |
| 2015–2019 | 235 | 1562 | **1753** | 13.4 |
| 2020–2026 | 117 | 1588 | **1793** | 10.3 |

`corr(debut year, peak rating) = **0.068**` — essentially nothing.
`corr(bout count, peak rating) = **0.341**`.

**The mean is flat; only the upper tail rises.** Whatever is happening is happening
to the top of the distribution, not to the level. That is the central puzzle.

### 2.3 Trajectories move, but not much

Fighters with ≥10 bouts: within-career rating **range** is median **68** points
(p25 41, p75 108, max 372). Only **0.2%** of trajectories are strictly monotone, so
the smoother is not producing straight ramps — but a 68-point career range against a
336-point gap between Jones and the bar means **between-fighter spread dominates
within-career movement by roughly 5×**. Career mass is therefore close to
`(career level − bar) × active years`, which is worth stating explicitly because it
is not what the functional is documented to measure.

### 2.4 The three WHR parameters, none of them fitted

```
WHR_W2_PER_DAY  = 0.0004     # random-walk variance per day — NEVER FITTED
WHR_PRIOR_VAR   = 4.0        # anchor prior variance
WHR_VIRTUAL_GAMES = 2.0      # prior evidence per fighter
```

`WHR_W2_PER_DAY` governs how far a rating may travel per unit time. It is the prime
suspect for §2.3 and it has never been estimated from held-out prediction.

---

## 3. Hypotheses, each with a falsifiable test

Test them in this order; each is cheap and several are mutually exclusive.

**H1 — Graph density, not era.** Early fighters sit in a sparse, shallow opponent
graph, so the estimator cannot move them far from the anchor; modern fighters sit in
a dense one and can be pushed to extremes.
*Test:* for each fighter compute opponent-graph depth (bouts, distinct opponents,
mean opponent bout count, 2-hop neighbourhood size). Regress peak rating on those
plus debut year. **Prediction: graph terms carry the signal and debut year adds
nothing once they are in.** If debut year still matters, H1 is wrong.

**H2 — The drift rate is too small to express a peak.** With `w²` this low a career
is fitted as a near-constant, so a fighter is scored on career *average*, and anyone
with a long tail of losses (Couture, Lawler, Belfort) averages below the bar.
*Test:* refit at `w²` × {0.25, 1, 4, 16, 64}; for each, report within-career range,
held-out log loss, and where the seven zero-mass fighters land.
**Prediction: a larger `w²` raises within-career range and lifts fighters whose peak
and decline are far apart, at some cost in prediction.** If held-out loss degrades
monotonically from the current value, the current value is defensible and H2 is wrong.

**H3 — Peak deletion (the driftless prior).** A late decline is explained by lowering
the whole trajectory, so anyone who fought too long is scored on their ending.
*Test:* refit truncated before each fighter's decline and compare the same
appearance's rating in the full fit (the §3.9 protocol from the plan, previously run
for Ferguson/Silva/Penn/Jones). Extend it to Couture, Lawler, Belfort, W. Silva,
M. Rua, Faber.
**Prediction: the zero-mass group shows large negative revisions; Merab and Jones
show none.** Quantify how much of each fighter's zero is attributable.

**H4 — Survivorship in the bar itself.** The bar is a quantile over *rated*
fighter-years, and who is rated changes: 28 fighters in 2000 against 625 in 2024. The
0.9 quantile of 28 is the 3rd best fighter; of 625 it is the 63rd.
*Test:* recompute the bar as a fixed *count* (top-60 line) rather than a quantile, and
as a quantile over a fixed-composition subset (fighters with ≥8 bouts). Re-rank.
**Prediction: if the bar is the problem, the zero-mass group moves substantially.**
Note this is the one hypothesis that would change the §9.1 conclusion, so test it
properly rather than dismissing it.

**H5 — Scope truncation.** Legacy fighters lost the half of their careers the engine
cannot see. Couture's pre-UFC and post-UFC record, Wanderlei's PRIDE peak (he is 1480
in the UFC data — his PRIDE years are absent entirely), Faber's WEC years, Aldo's WEC
title reign.
*Test:* **the cross-org ingest is now complete** — 589 events, 6,199 bouts, 4,501
fighters, 1997–2026, including Bellator back to 2009-04-03. Join it (see §5) and
re-rank. **Prediction: Wanderlei, Faber, Aldo and Cro Cop move a great deal; Couture
and Lawler move less because their missing bouts are mostly outside the majors.**

**H6 — Activity, not skill.** 70/100 being active may partly be that inactive
fighters' ratings decay or that the activity penalty leaks into `mu_whr`.
*Test:* check whether `activity_mu_penalty` or `mu_whr_activity_adjusted` reaches the
career functional. It should not — career mass reads `ratings_history_whr`.
**Prediction: no leak, and H6 is a dead end.** Confirm it and move on.

---

## 4. The specific cases to carry through every section

Each of these must get a named verdict, not a table row:

| Fighter | The question |
|---|---|
| **Merab Dvalishvili** | 9 active years, all clearing the bar, rank 21. Is that a fair reading of a bantamweight champion, or is a long unbeaten run in a deep modern graph mechanically overpriced? |
| **Jon Jones** | Mass 4556 — **1.65×** the second-placed fighter, and the only rank with a tight interval [1,2]. Is that dominance the data supports, or the compounding of a 14-year career that never dipped? Both readings are defensible; say which and why. |
| **Natalia Silva** | Current #10 on 5 years and a flat 1836–1845. Ranked above fighters with far longer records. Is the estimator confident because she has been dominant, or because she has not yet been tested? Report her interval. |
| **Randy Couture** | Mass 0, rank 2032. Attribute the zero across H2/H3/H4/H5 with numbers. This is the acceptance case: an explanation that does not account for Couture has not explained the board. |
| **Robbie Lawler** | Mass 0 across a 13-year career with a welterweight title reign in the middle of it. The clearest peak-vs-average test in the set. |
| **José Aldo** | Rank 33; his board starts in 2011 because WEC is missing. How much does H5 alone recover? |
| **Wanderlei Silva** | Rated 1480–1499, 160 points below the bar, on UFC bouts alone. With PRIDE ingested, where does he land? |

---

## 5. Data available that was not available before

The cross-organisation ingest completed on 2026-08-21:

```
data/external/sherdog/majors_bouts.parquet        589 events / 6,199 bouts / 4,501 fighters
data/external/sherdog/crossorg_bouts.parquet      event cards + whole careers, merged
data/external/sherdog/majors_coverage.json        per-promotion, per-year counts
```

| Promotion | Events | Bouts | Span |
|---|---:|---:|---|
| PRIDE | 69 | 600 | 1997-10-11 → 2007-04-08 |
| WEC | 53 | 576 | 2001-06-30 → 2010-12-16 |
| Strikeforce | 64 | 657 | 1997-05-31 → 2013-01-12 |
| Affliction | 2 | 21 | 2008-07-19 → 2009-01-24 |
| Bellator | 316 | 3,498 | 2009-04-03 → 2024-09-14 |
| RIZIN | 85 | 847 | 2015-12-29 → 2026-12-31 |

Join it with `loaders.crossorg_identity`: `build_identity_map` →
`resolve_collisions` → `resolve_by_bout_evidence` → `apply_identity_map`. Do not
name-match by hand; the sibling and namesake traps are documented in that module.

Also available and unused by the career functional:
`ratings/field_depth.py` (division-year depth, contender line, scale-free
percentiles), `ratings/connectivity.py` (vertex-disjoint paths to the rated core),
`ratings/crossover.py` (Bradley-Terry transfer gaps).

---

## 6. The deliverable

**One notebook, committed to this repository. Not a Claude artifact, not a report in
`Claude Status Reports\`.**

```
analysis/investigations/top100_era_skew.ipynb
```

Requirements:

1. **Runs top-to-bottom from a clean kernel** against `data/snapshots/2026-08-13`
   with no manual steps. Any long refit is cached to
   `data/model_tuning/top100-era-skew/` and the notebook reads the cache when present.
2. **Committed with outputs cleared** — this repo already gitignores
   `analysis/notebook_with_output.ipynb`; follow the same convention and keep the
   committed `.ipynb` free of embedded output, so diffs stay readable.
3. **Every number in prose is computed in a cell above it.** No figure typed by hand.
4. **Structure follows §3**: one section per hypothesis, each opening with the
   falsifiable prediction and closing with a verdict of *supported*, *refuted*, or
   *unresolved* — and "unresolved" is a real answer, to be used whenever an interval
   crosses zero.
5. **Section 4's seven fighters appear in every hypothesis section**, so the reader
   can follow one career across all the explanations.
6. **Charts** follow the repo's existing `analysis/viz.py` conventions where one
   fits. Anything new must work in both light and dark and must not encode meaning
   in colour alone.
7. **Closing section: a ranked list of defects with a recommended fix and an
   estimated blast radius for each** — that is what makes the notebook actionable
   rather than descriptive.

---

## 7. Constraints that are not negotiable

- **Single-Entry.** Every fact posted once. If a fix involves adding opponent
  quality, title status or era to the score, it is wrong by construction — those
  live in the opponent's rating, the ledger, and the reference field respectively.
- **Never tune to an external list.** UFC official rankings, FightMatrix and any
  consensus board are diagnostics to be explained, never targets. A fix that moves
  Couture up because we expect him high is not a fix.
- **Evidence discipline.** Report "unresolved" when the interval crosses zero. Do
  not convert a rank change into a claim about a fighter without the interval beside
  it. Do not describe a refit as validated on one case.
- **Re-bootstrap anything that changes the board.** A change that improves a point
  estimate while widening intervals has not obviously improved anything, and must
  say so.

---

## 8. What "done" looks like

The notebook can answer, with numbers: *why does Randy Couture score zero, how much
of that is the drift rate, how much is peak deletion, how much is the bar's
composition, and how much is simply that half his career is not in the data* — and
then say which of those the project should fix first.

If the honest answer to some part is "the data cannot resolve this", the notebook
says so and names what evidence would.
