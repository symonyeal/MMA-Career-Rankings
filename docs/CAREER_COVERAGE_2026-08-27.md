# The top-100 oddities were a data problem, not a scoring one — 2026-08-27

**Dataset:** `data/snapshots/2026-08-13` · **Scope:** `majors,pre_unified`

Six fixes to the board shipped between 2026-08-20 and 2026-08-26. Every one of
them was applied *after* the ratings were calculated, and the same kind of
fighter kept coming back with a new name each time. This document records what
was actually wrong, what completing the data fixed, and what it did not.

## The problem

The `majors` dataset was built two ways at once. Fight cards were collected event
by event for seven promotions, which is complete *within* those promotions and
cuts off every career that ran wider than them. There is a second routine whose
whole job is to remove that truncation, and which states the principle itself:

> Rating a fighter on a subset of their record is the same bias that made the old
> cache unusable, only along a different axis. So once a fighter is in the graph
> at all, their whole record comes in.

That routine ran over the **4,501 fighters who had appeared on a PRIDE, WEC,
Strikeforce, Affliction, Bellator or RIZIN card** — and never over the UFC roster.
"Once a fighter is in the graph" quietly meant "once a fighter is in the *majors*
graph", so one dataset was carrying two different coverage rules.

Measured over the 1,825 fighters with three or more UFC fights:

| whole career read? | fighters | median pre-UFC fights recorded | median fights held |
|---|---:|---:|---:|
| yes | 547 (30.0%) | **13** | 37 |
| no | 1,278 | **1** | 10 |

Khabib Nurmagomedov was rated on 14 fights; his record is 29. Volkanovski,
Makhachev, Adesanya and Topuria each had 0 or 1 pre-UFC fights recorded. Usman
Nurmagomedov, Eblen, Izawa, Nemkov and McKee had all of theirs.

## Why missing fights turn into rating points

A fighter who rarely loses has no natural ceiling in this kind of model — every
extra win pushes the rating higher with nothing pulling back — so only the model's
prior stops the climb, and it settles near

    rating ≈ opponent level + 173.72 × ln(2k / v)

where `k` is **how many of that fighter's fights the dataset happens to hold**.
That is a property of how the data was collected, and the model reads it as skill.

Confirmed by refitting with one coverage rule for everybody (career-fill fights
dropped, so all seven promotions and nothing else) and comparing each fighter's
rating shift against what the formula predicts:

| fighters | n | correlation, predicted vs actual | median error |
|---|---:|---:|---:|
| loses ≤ 15% of fights | 95 | **+0.740** | 30 Elo |
| loses 15–35% | 888 | +0.263 | 61 Elo |
| loses > 35% | 1,020 | **−0.146** | 59 Elo |

It bites exactly where a record has no natural ceiling, and nowhere else.

## A separate, still-unfixed problem found on the way

This section records a measurement that the coverage gap does **not** explain. It
was found while diagnosing that gap, was assumed at first to be the same thing,
and the repair proved otherwise.

Testing on fights the model had not seen, across seven cut-off dates and scoring
only the 120 days after each one so no rating is stale, the ratings are accurate
**within** each pool of fighters and misplaced **between** them:

| group | n | predicted win rate | actual | gap |
|---|---:|---:|---:|---:|
| both fighters with no UFC record | 618 | 0.640 | 0.642 | +0.002 |
| both fighters UFC-tested (8+ fights) | 459 | 0.610 | 0.575 | −0.034 |
| favourite has no UFC record, opponent does | 172 | 0.649 | **0.523** | **−0.125** |
| favourite has a UFC record, opponent does not | 144 | 0.647 | **0.771** | **+0.124** |

**The near-symmetry is the proof.** If this were just noise, the favourite would
under-perform in *both* directions. Only a genuine level difference flips the sign.
Fitting a single offset on the UFC-experienced side gives **+101 Elo, 95% CI
[+57, +148]**, positive in 600 of 600 resamples, worth 0.036 of prediction error
on 316 fights across 166 events.

**Completing the data did not shrink it.** The identical test on the repaired
dataset:

| | before repair | after repair |
|---|---|---|
| favourite no UFC, opponent has | 0.649 → 0.523 (n=172) | 0.631 → 0.535 (n=174) |
| favourite has UFC, opponent none | 0.647 → 0.771 (n=144) | 0.676 → 0.821 (n=312) |
| fitted offset | **+101 Elo [+57, +148]** | **+110 Elo [+76, +151]** |

The intervals overlap almost entirely and the estimate moved the wrong way. The
theory that the coverage gap *caused* the pool difference is therefore
**disproved**, and this is an open problem in its own right. Both within-pool
groups stay accurate after the repair (−0.012 and +0.006), so it is specifically
the *relative level* of the two pools that is wrong, not either pool internally.

It does disprove a standing conclusion in
[Board and identification](../_archive/20260831-repository-consolidation/docs/BOARD_AND_IDENTIFICATION_2026-08-25.md),
which held that the pools are "connected to the tested core, so a promotion
discount cannot be measured". Connected is not the same as correctly placed, and
that conclusion came from looking at the network rather than from testing on
held-out fights. What it does **not** justify is applying the offset as a
promotion weight: this project's rule is that relative promotion strength is an
*output* of the fit, and an offset fitted on 486 crossover fights and then
subtracted would assert the answer. The right next step is to find why the fit
misplaces two connected pools — most likely because of who crosses over, and when.

## Three things that were not the cause

**The model being over-confident.** With staleness controlled, the fitted scale on
held-out fights is **0.936, 95% CI [0.776, 1.241]** — 1.0 sits inside it. A single
2023 test had suggested 1.6× over-confidence; that was stale ratings, and testing
across multiple cut-offs corrected it.

**Shrinking unreliable ratings.** The model is *least* certain about the
dominant fighters, not the questionable ones: Jon Jones 2.63, Usman Nurmagomedov
1.62, Khabib 1.59, against Donald Cerrone 10.55 and Robbie Lawler 9.61. The
correlation between board rank and certainty is +0.011. Shrinking by reliability
penalises dominance and separates nothing.

**The prior.** The automatic best-fit value for `WHR_PRIOR_VAR` is **0.58**
against the 4.0 that was set — the prior claims fighter skill varies by 347 Elo
where the fitted ratings vary by 141. That setting is genuinely wrong, but
correcting it compresses everything almost uniformly (top rating 2086 → 1837),
and an unbeaten record's sensitivity to fight count only falls from 0.87 to 0.70.

## The repair

`build_sherdog_careers.py` reads one whole-career page for every rated fighter
whose career is not already in the dataset, through the same cached, rate-limited
loader the project already uses, and merges the results under the existing
event-card precedence. 1,278 fighters needed it; 1,057 were already identifiable
and 221 needed a search, of which **77 could not be found and remain truncated**.

| | before | after |
|---|---:|---:|
| Sherdog fights held | 63,813 | **80,902** |
| fights used in the model | 67,920 | **80,697** |
| fighters rated | 28,867 | **33,692** |
| eligible roster with a whole career read | 547 (30.0%) | **1,744 (95.6%)** |

Fights recorded, before → after: Khabib 14 → 30, Adesanya 20 → 32, Volkanovski
19 → 32, Makhachev 19 → 30, Topuria 10 → 20, Whittaker 27 → 38, Jones 26 → 31 —
against Eblen 19 → 19, Izawa 18 → 18, Usman Nurmagomedov 22 → 24. That difference
is the repair.

Two guards stop it coming back:

- `loaders/career_coverage.py` states the property as a number.
  `stage_majors_scope` writes `career_coverage.parquet`, prints it and warns below
  the minimum; `rate_snapshot` publishes it in `rating_run.json`; `refresh.py`
  writes it into the changelog.
- `tests/test_career_coverage.py` fails on exactly the shape that broke the
  board — two fighters with identical UFC records, one with their pre-UFC
  regional record and one without.

**The risk was named, and measured on the wrong axis.** An earlier plan listed
"ragged data masquerading as coverage" as a risk, with per-promotion completeness
figures as the mitigation. Per-promotion completeness was built and it passes:
every promotion is complete within its own cards. The raggedness is **per
fighter**. Check completeness on the axis the model is actually sensitive to.

## What it fixed, and what it did not

Left the top 100: Yaroslav Amosov (2 UFC fights), Usman Nurmagomedov (0), Ben
Askren (3), A.J. McKee (0) — and also Alexandre Pantoja (18), Erin Blanchfield (9)
and Sergio Pettis (14). Entered: Beneil Dariush (26), Liz Carmouche (10), Alexa
Grasso (15), Wanderlei Silva (12), Demian Maia (33), Carla Esparza (16), Kayla
Harrison (3). Median UFC fights of those leaving is 9; of those entering, 15.
Careers with no UFC record in the top 100 went **7 → 5**; the top-10 watch list
stays empty; 93 of the old top 100 are still there, and agreement across the two
top 300s is +0.950.

**The underlying rating problem is untouched, and the repair made it symmetric
rather than removing it.** Seika Izawa is still rated **269 points above the best
fighter she has ever faced**, unchanged, and Khabib now sits **192** above his,
because completing his record lengthened an unbeaten run. Izawa, Johnny Eblen and
Vadim Nemkov are all still on the board, and Kayla Harrison enters at 100 on 3 UFC
fights — the same profile with a new name. Pantoja, a reigning UFC champion, fell
out of the top 100.

## Where this went

Everything this document called for was done, and the measurements now live in
the record that owns them rather than being restated here.

- The three model settings were refitted on the repaired data, the career score
  was made invariant to a rescaling of the ratings, and the UFC-versus-outside
  gap was measured and deliberately not applied as a promotion weight. All three
  are in
  [How the ratings and the score are built](RATING_LAYER_AND_LEDGER_2026-08-28.md),
  sections 2, 1 and 3, with the full tables and confidence intervals.
- Two changes shipped after this document was written, so every fight count and
  board position under "What it fixed" above predates them: the winner's credit
  now reflects how the fight ended, and the title résumé carries a measured
  promotion correction.
- The 77 fighters Sherdog's search could not resolve are still truncated. That
  and everything else still open is in [Open decisions](DECISIONS.md).

## Reproduce

```bash
python build_sherdog_careers.py --report-only      # per-fighter coverage, no network
python build_sherdog_careers.py --snapshot-dir "data/snapshots/2026-08-13"
python -c "from loaders.majors_scope import stage_majors_scope; stage_majors_scope('data/snapshots/2026-08-13')"
python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-08-13" --scope majors,pre_unified
python build_boards.py "data/snapshots/2026-08-13" --scope majors,pre_unified --write-readme
python build_top100_audit.py "data/snapshots/2026-08-13"
```

The one-off probes behind these measurements (`probe_corpus_censoring.py`,
`probe_symmetric_coverage.py`, `probe_lnk_law.py`, `probe_scale_calibration.py`,
`probe_information_content.py`, `probe_deviant_audit.py`) are kept outside this
repository, beside the working material for this project. The narrative report is
`Claude Status Reports/UFC Top 100 Root Cause Career Coverage 2026-08-27.md`.
