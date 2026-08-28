# Career coverage: the top-100 anomalies were a data defect — 2026-08-27

**Snapshot:** `data/snapshots/2026-08-13` · **Scope:** `majors,pre_unified`

Six board repairs shipped between 2026-08-20 and 2026-08-26 — the fixed-mass WHR
prior, the contender bar, the switch to `public_legacy_score`, per-opponent title
pricing, the division-scoped title bar, and the division career bar with a
softplus hinge. Every one was applied downstream of the rating, and the same
profile of fighter returned each time with a new cast. This document records what
was actually wrong, what completing the data fixed, and what it did not.

## The defect

`majors` is built two ways at once. Cards are enumerated by event for seven
promotions, which is roster-complete *within* those promotions and truncates
every career that ran wider. `sherdog_org_loader.parse_fighter_career` exists to
remove that truncation, and states the principle itself:

> Rating a fighter on a subset of their record is the same censoring bias that
> made the old fighter-seeded cache unusable, only applied along a different
> axis. So once a fighter is in the graph at all, their whole record comes in.

That expansion ran over the **4,501 fighters who had appeared on a PRIDE / WEC /
Strikeforce / Affliction / Bellator / RIZIN card**, and never over the UFCStats
roster. "Once a fighter is in the graph" quietly meant "once a fighter is in the
*majors* graph", so one corpus carried two coverage rules.

Measured over the 1,825 fighters with three or more UFC bouts:

| career page read | fighters | median recorded pre-UFC bouts | median corpus bouts |
|---|---:|---:|---:|
| yes | 547 (30.0%) | **13** | 37 |
| no | 1,278 | **1** | 10 |

Khabib Nurmagomedov was rated on 14 bouts; his record is 29. Volkanovski,
Makhachev, Adesanya and Topuria each had 0–1 recorded pre-UFC bouts. Usman
Nurmagomedov, Eblen, Izawa, Nemkov and McKee had all of theirs.

## Why coverage becomes rating points

A low-loss Bradley–Terry record has no interior maximum — the win gradient
`sum_j (1 - sigma(r - r_j))` is positive at every finite `r` — so the prior alone
stops the climb and the equilibrium sits near

    r* ≈ opponent_level + 173.72 · ln(2k / v)

`k` is *how many of the fighter's bouts the corpus happens to hold*. It is a
property of the crawl, and the model reads it as skill.

Confirmed against a coverage-symmetric refit (career-fill bouts dropped so all
seven promotions and nothing else, one rule for everybody), comparing each
fighter's rating shift against the predicted `173.72·ln(k_after/k_before)`:

| fighters | n | corr(predicted, observed) | median &#124;residual&#124; |
|---|---:|---:|---:|
| loss rate ≤ 15% | 95 | **+0.740** | 30 Elo |
| loss rate 15–35% | 888 | +0.263 | 61 Elo |
| loss rate > 35% | 1,020 | **−0.146** | 59 Elo |

It binds exactly where a record has no interior maximum, and nowhere else.

## A separate, unfixed defect found on the way: the pools are mis-located

This section records a measurement that is **not** explained by the coverage
asymmetry. It was found while diagnosing it, was initially assumed to be the same
defect, and the repair refuted that.

Held out over seven cutoffs, scoring only the 120 days after each so no rating is
stale, the ratings are calibrated **within** each pool and mis-located
**between** them:

| segment | n | predicted | actual | gap |
|---|---:|---:|---:|---:|
| both fighters 0 UFC bouts | 618 | 0.640 | 0.642 | +0.002 |
| both fighters UFC-tested (8+) | 459 | 0.610 | 0.575 | −0.034 |
| favourite 0 UFC, opponent 1+ | 172 | 0.649 | **0.523** | **−0.125** |
| favourite 1+ UFC, opponent 0 | 144 | 0.647 | **0.771** | **+0.124** |

The near-symmetry is the identification. Symmetric measurement error would make
the favourite under-perform in *both* directions; only a systematic level offset
flips the sign. A single fitted offset on the UFC-experienced side was **+101
Elo, event-bootstrap 95% CI [+57, +148]**, positive in 600 of 600 draws, worth
0.036 of held-out log loss on 316 bouts over 166 events.

**Completing the coverage did not shrink it.** Re-running the identical test on
the repaired corpus:

| | before repair | after repair |
|---|---|---|
| favourite 0 UFC, opponent 1+ | 0.649 → 0.523 (n=172) | 0.631 → 0.535 (n=174) |
| favourite 1+ UFC, opponent 0 | 0.647 → 0.771 (n=144) | 0.676 → 0.821 (n=312) |
| fitted offset | **+101 Elo [+57, +148]** | **+110 Elo [+76, +151]** |

The intervals overlap almost entirely and the point estimate moved the wrong way.
The hypothesis that the coverage asymmetry *caused* the pool-level offset is
therefore **refuted**, and this is an open defect in its own right. The two
within-pool segments stay calibrated after the repair (both-external −0.012,
both-UFC-tested +0.006), so it is specifically the *relative level* of the two
pools that is wrong, not either pool internally.

It still falsifies the standing conclusion in
[Board and identification](BOARD_AND_IDENTIFICATION_2026-08-25.md) that the pools
are "connected to the tested core, so an organisation discount is not
identified": connected is not the same as correctly located, and that conclusion
was drawn from graph connectivity rather than from a held-out test. What it does
**not** license is applying the offset as an organisation weight — the engine's
own rule is that relative promotion strength is an output of the joint fit, and
an offset fitted on 486 crossing bouts and then subtracted would assert the
answer. The right next step is to find why the joint fit mis-locates two
connected pools, most likely selection on who crosses and when.

## Three things that were not the cause

**Over-dispersion.** The fitted logistic scale on held-out bouts with staleness
controlled is **beta = 0.936, 95% CI [0.776, 1.241]** — 1.0 is inside it. A
single 2023 split suggested 1.6x over-dispersion; that was rating staleness, and
the multi-cutoff design corrected it.

**Reliability shrinkage.** Bradley–Terry Fisher information is *lowest* for the
dominant, not for the fake: Jon Jones 2.63, Usman Nurmagomedov 1.62, Khabib 1.59,
against Donald Cerrone 10.55 and Robbie Lawler 9.61.
`spearman(board rank, information) = +0.011`. Shrinking by reliability penalises
dominance and does not discriminate.

**The prior.** The Type-II maximum-likelihood fixed point for `WHR_PRIOR_VAR` is
**0.58** against the asserted 4.0 — the prior claims fighter skill has sd 347 Elo
where the fitted ratings have sd 141. That constant is genuinely wrong, but
correcting it is a near-uniform compression (max fitted rating 2086 → 1837), and
the analytic sensitivity of an unbeaten record to bout count only falls from 0.87
to 0.70 nats per log-bout.

## The repair

`build_sherdog_careers.py` reads one whole-career page for every rated fighter
whose career rows are not in the corpus, through the same polite cached loader
the project already uses, and merges them under the existing event-card
precedence. 1,278 targets; 1,057 Sherdog ids were already present in the corpus
and 221 needed a fightfinder search, of which **77 could not be resolved and stay
truncated**.

| | before | after |
|---|---:|---:|
| Sherdog corpus bouts | 63,813 | **80,902** |
| rated model bouts | 67,920 | **80,697** |
| rated fighters | 28,867 | **33,692** |
| eligible roster with a whole-career page | 547 (30.0%) | **1,744 (95.6%)** |

Recorded bouts, before → after: Khabib 14 → 30, Adesanya 20 → 32, Volkanovski
19 → 32, Makhachev 19 → 30, Topuria 10 → 20, Whittaker 27 → 38, Jones 26 → 31 —
against Eblen 19 → 19, Izawa 18 → 18, Usman Nurmagomedov 22 → 24. That
differential is the repair.

Two guards keep it from returning:

* `loaders/career_coverage.py` states the property as a number.
  `stage_majors_scope` writes `career_coverage.parquet`, prints it, and warns
  below `MIN_CAREER_PAGE_SHARE`; `rate_snapshot` publishes it in
  `rating_run.json`; `refresh.py` writes it into the changelog.
* `tests/test_career_coverage.py` fails on the corpus shape that broke the
  board — two fighters with identical UFC records, one with their pre-UFC
  regional record and one without.

**The risk was named and measured on the wrong axis.**
[Whole-sport engine](PLAN_WHOLE_SPORT_ENGINE_2026-08-21.md) §8 lists "*ragged
data masquerading as coverage… Mitigation: per-promotion completeness figures and
abstention*". Per-promotion completeness was built and it passes —
`majors_coverage.json` reports every promotion roster-complete inside its own
cards. The raggedness is **per fighter**. Check completeness on the axis the
estimator is sensitive to.

## What it fixed, and what it did not

Left the top 100: Yaroslav Amosov (2 UFC bouts), Usman Nurmagomedov (0), Ben
Askren (3), A.J. McKee (0) — and also Alexandre Pantoja (18), Erin Blanchfield
(9) and Sergio Pettis (14). Entered: Beneil Dariush (26), Liz Carmouche (10),
Alexa Grasso (15), Wanderlei Silva (12), Demian Maia (33), Carla Esparza (16),
Kayla Harrison (3). Median UFC bouts of those leaving is 9, of those entering 15.
External-only careers in the top 100 went **7 → 5**; `top10_active_external_
unanchored` remains empty; top-100 overlap with the old board is 93/100 and
Spearman over the union of the two top 300 is +0.950.

**The estimator defect underneath is untouched, and the repair made it symmetric
rather than removing it.** The deviant-fighter audit that motivated the
2026-08-20 prior repair still fires: Seika Izawa is rated **269 points above the
best fighter she has ever faced**, unchanged, and Khabib now sits **192** above
his because completing his record lengthened an unbeaten run. Izawa, Johnny Eblen
and Vadim Nemkov are still on the board, and Kayla Harrison enters it at 100 on
3 UFC bouts — the same profile with a new name. Pantoja, a reigning UFC champion,
fell out of the top 100.

## What has to happen next

1. **RESOLVED 2026-08-28 — the three WHR constants were fitted on the repaired
   published scope.** Fourteen rolling cutoffs; the coarse single-parameter
   sweep produced 8,435 paired held-out bouts across 1,467 events and the joint
   refinement that made the selection produced 7,641 across 1,355. Calibration for each cutoff used only earlier
   prediction windows. The selected joint configuration is
   `WHR_PRIOR_VAR=8`, `WHR_W2_PER_DAY=0.0004`, and `WHR_VIRTUAL_GAMES=1`:
   calibrated log-loss delta -0.00201, paired event-bootstrap 95% CI
   [-0.00349, -0.00060], and AUC 0.7041 -> 0.7067 versus the former 4/0.0004/2
   base. Prior variance 16 was worse, virtual mass 0.5 was unresolved, and
   `w2=0.0002` was unresolved. The incremental gain from prior variance 8 after
   setting virtual mass 1 was itself unresolved, so the two changes are not
   claimed to be independently identified. The empirical-Bayes fixed point
   0.58 answers in-sample marginal likelihood and was strongly worse for
   held-out prediction; it was not selected.
2. **RESOLVED 2026-08-27 — the career functional is scale-equivariant.** The
   published hinge scale is now 0.175 times each calendar year's population
   standard deviation of `annual_mean`, rather than a fixed 25 Elo. On the fitted
   history, rescaling every rating around 1500 by beta in {0.5, 0.7, 1.4, 2.0}
   produces an identical full rank vector, zero top-100 movement and scores equal
   to beta times baseline within 2.8e-12. The former board is still exactly
   reproducible by the named compatibility argument
   `hinge_scale=DEFAULT_HINGE_SCALE`. Evidence:
   `Claude Func Folder/py/ufc/out/career_scale_equivariance.csv`.
3. **RESOLVED 2026-08-28 — repaired-corpus held-out evidence was rebuilt, and
   so were the publication artifacts.** The constant sweep, the fight-information
   sweep and their strictly prior-fold calibrated, paired event-bootstrap
   analyses live under `Claude Func Folder/py/ufc/out/`. The snapshot was then
   re-rated end to end and the boards and README regenerated from it.
4. **77 fighters remain truncated** because Sherdog's fightfinder could not
   resolve their name. They are listed in the builder's report; resolving them is
   a name-matching problem, not a crawl problem.
5. **DIAGNOSED 2026-08-28, not applied as an organisation weight.** Under the
   fitted constants the complete-career label reproduces a +104 Elo offset
   [+67, +148] on 486 bouts. It is concentrated before selected fighters enter
   the UFC: future signees are +274 [+185, +389] against never-UFC opponents,
   rising to +463 [+290, +521] within one year of debut. A smaller +54
   [+10, +100] prior-UFC residual remains, while debutant-versus-incumbent is
   unresolved [-8, +98]. This supports selection on who crosses and when as the
   main mechanism, without claiming it explains every residual.

6. **NEW 2026-08-28 — two mechanisms shipped that this document predates.** The
   winner score now carries method of victory
   (`ratings.constants.WHR_WINNER_SCORE_COL`), and the title ledger carries a
   measured pool correction (`legacy_resume.UFC_POOL_OFFSET_ELO`). Every bout
   count and board position below the "What it fixed" heading was measured
   before both. See
   [Rating layer and ledger](RATING_LAYER_AND_LEDGER_2026-08-28.md) for the
   current board.

## Reproduce

```bash
python build_sherdog_careers.py --report-only      # per-fighter coverage, no network
python build_sherdog_careers.py --snapshot-dir "data/snapshots/2026-08-13"
python -c "from loaders.majors_scope import stage_majors_scope; stage_majors_scope('data/snapshots/2026-08-13')"
python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-08-13" --scope majors,pre_unified
python build_boards.py "data/snapshots/2026-08-13" --scope majors,pre_unified --write-readme
python build_top100_audit.py "data/snapshots/2026-08-13"
```

The one-off probes behind the measurements (`probe_corpus_censoring.py`,
`probe_symmetric_coverage.py`, `probe_lnk_law.py`, `probe_scale_calibration.py`,
`probe_information_content.py`, `probe_deviant_audit.py`) are kept outside this
repository beside the working material for this project. The narrative report is
`Claude Status Reports/UFC Top 100 Root Cause Career Coverage 2026-08-27.md`.
