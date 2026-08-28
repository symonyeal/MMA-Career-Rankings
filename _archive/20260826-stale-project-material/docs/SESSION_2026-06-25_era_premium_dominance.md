# Session 2026-06-25 — WHR modern-era premium + two-sided dominance

Implements the two APPROVED-NOT-YET-IMPLEMENTED items from the prior handover, then
evaluates the engine's era/dominance decisions and proposes upgrades (approval-gated).

## 1. What was implemented (done + unit-tested)

### (a) WHR modern-era premium  — `ratings/constants.py`, `ratings/rate_snapshot.py`
WHR re-anchors its global mean to 0 every coordinate-ascent pass (`ratings/whr.py`),
so it is **era-flat by construction**. Confirmed on the live snapshot: base `mu_whr`
per-fight mean was 1486.4 (≤2004) → 1516.3 (≥2022), a +29.9 / ~20yr ≈ **+1.4 mu/yr**
residual, vs the Glicko filter's empirical ~+4.7 mu/yr. So a Bayesian smoother cannot,
on its own, encode "the modern field is harder," and lowering `ERA_NORM_MAX_STRENGTH`
last session was correctly diagnosed as nearly inert.

Fix: add an explicit per-appearance premium to every WHR `mu` BEFORE peak windowing:
`mu += WHR_ERA_PREMIUM_PER_YEAR * (event_year − WHR_ERA_PREMIUM_REFERENCE_YEAR)`.
- New tunable constants: `WHR_ERA_PREMIUM_PER_YEAR = 4.5`, `WHR_ERA_PREMIUM_REFERENCE_YEAR = 2010`.
- New helper `_apply_whr_era_premium(history, mu_col)`; applied to the base `mu_whr`
  history and each sleeved WHR history, so it flows to the persisted history parquets,
  the current cols (via `.last()`), the peak windows, and `division_resume`.
- Reference year is **cosmetic**: a constant offset cancels out of within-snapshot
  ranks and of the affine rescale onto the Complete scale; only the per-year SLOPE
  moves fighters.

### (b) Two-sided, stronger dominance  — `ratings/constants.py`, `ratings/rate_snapshot.py`
Prior session's dominance reward only boosted the WINNER's WHR likelihood weight; a
smoother ranks by the whole record, so a winner-only boost could not lift dominant
finishers who also carry losses (Yoel Romero was Legacy #67 vs Complete #29).
- `_amplify_winner_dominance_weight` → `_amplify_dominance_weight`: now multiplies
  BOTH fighters' per-fight weight by `1 + amplitude * dom_level`. The winner is pushed
  up AND the blown-out loser pushed down harder, spreading dominant fighters from the
  field.
- `WHR_DOMINANCE_WEIGHT_AMPLITUDE` 0.20 → **0.30**.
- New `WHR_DOMINANCE_SCORE_SCALE = 1.25`, decoupling the Legacy dom_level sigmoid from
  the Glicko method-stream score scale `DOMINANCE_SCORE_SCALE = 2.0` (unchanged), so
  widening Legacy dominance does NOT perturb the Complete stream. Lower scale ⇒ more
  clear wins register as dominant (old shared 2.0: mean level ≈0.27, only ~21% cleared 0.5).

Unit tests updated (`tests/test_whr_dominance.py`): two-sided assertion + partial-level
case. Targeted suite (whr, whr_dominance, whr_backtest, peaks, performance_adjustment):
**59 passed**.

## 2. Before-baseline (men, Prime; current on-disk parquet = prior era=0.20 + one-sided dom=0.20)
Legacy = affine_match_scale(sustained_peak_headline_mu_whr_integrity_performance → Complete).

| cohort | fighter | Legacy # | Complete # |
|---|---|---|---|
| pioneers (expect DROP) | Randy Couture | 13 | 45 |
| | Matt Hughes | 15 | 55 |
| | Tim Sylvia | 28 | 56 |
| | Chuck Liddell | 30 | 50 |
| | Tito Ortiz | 31 | 74 |
| dominant finishers (expect RISE) | Yoel Romero | 67 | 29 |
| | Robert Whittaker | 52 | 28 |
| | Francis Ngannou | 33 | 30 |
| multi-era greats (expect HOLD) | Jon Jones | 1 | 2 |
| | Georges St-Pierre | 2 | 4 |
| | Demetrious Johnson | 3 | 23 |
| | Anderson Silva | 4 | 1 |

## 3. After-results (recompute 2026-06-23, exit 0)
Era slope diagnostic (base `mu_whr` per-fight mean): **+29.9 → +128.9** over 2004→2022
(≈ +1.4 → +6.1 mu/yr). The +4.5/yr × ~20 yr injection landed as designed.

Legacy rank (men, Prime), before → after:

| cohort | fighter | before | after | Δ | verdict |
|---|---|--:|--:|--:|---|
| pioneers (want DROP) | Randy Couture | 13 | 20 | −7 | ✓ |
| | Matt Hughes | 15 | 24 | −9 | ✓ |
| | Tim Sylvia | 28 | 41 | −13 | ✓ |
| | Chuck Liddell | 30 | 45 | −15 | ✓ |
| | Tito Ortiz | 31 | 49 | −18 | ✓ |
| dominant finishers (want RISE) | Robert Whittaker | 52 | 44 | +8 | ✓ |
| | Francis Ngannou | 33 | 31 | +2 | weak |
| | Yoel Romero | 67 | 65 | +2 | weak |
| multi-era greats (want HOLD) | Jon Jones | 1 | 1 | 0 | ✓ |
| | Georges St-Pierre | 2 | 2 | 0 | ✓ |
| | Demetrious Johnson | 3 | 5 | −2 | ✓ |
| | Anderson Silva | 4 | 8 | −4 | borderline |

**Reads.** Era premium works cleanly — every pioneer dropped, the top-10 is a
defensible modern-leaning all-time list (Jones, GSP, Makhachev, Volkanovski, DJ,
Pereira, Cormier, Silva, Usman, Adesanya). Two side-effects to weigh:
- **Recency over-reward.** Pure-2020s fighters leap *above* their Complete rank on
  premium alone: Merab Dvalishvili Legacy #16 vs Complete #49; Alexandre Pantoja #21
  vs #59; Petr Yan #27 vs #35. A *linear* premium maximally rewards the newest years,
  which is in tension with the "greatness = sustained across MULTIPLE eras" philosophy
  (a short all-2020s window is not multi-era yet ranks high). → Rec U3.
- **Dominant finishers barely moved** (Romero/Ngannou +2). The two-sided dominance
  helped the grinder (Whittaker +8) but not the quick-KO artists — because the
  dominance INDEX under-credits finishes (see Rec U2). The change is correct; the
  signal it amplifies is mis-shaped.
- **Silva #4→#8** is the magnitude question: 4.5/yr pulls 2006–2013-era greats just
  below pure-moderns. Tunable via `WHR_ERA_PREMIUM_PER_YEAR` if the user wants
  prior-era greats to sit higher.

## 4. Archiving audit — finding: nothing is safe to archive (and why that's the answer)
A thorough, evidence-based pass:
- **Working tree:** no junk. Every untracked file is live new work (`whr_backtest.py`,
  `loaders/ufcstats_scrape.py`, `analysis/CHART_PLAN.md`, the new tests).
- **Active snapshot `2026-06-23`:** no orphans — every file is current input (06-23
  ingest) or fresh output (06-25 recompute); the 3 known-legacy parquets the pipeline
  auto-deletes are already absent.
- **Root reporting scripts:** git-tracked + interconnected (`project_helpers.py`
  imported across the pipeline; `build_database.py` under test). Not stale.
- **`data/snapshots/2026-05-13` (looked stale → is LOAD-BEARING):** hardcoded by
  `tests/test_chart_additions.py:24`, `tests/test_database_builder.py:9`, and
  `build_rankings_sheets.py:13`. Archiving it would break the suite. **Left in place.**
- **Scratch (`.test_tmp/`, `__pycache__/`) + `.venv/`:** gitignored, reproducible.
  Zero-value to "archive"; `.venv` contradicts the single-Python policy but removing an
  env is a surfaced decision, not cleanup.
- Minor cosmetic: `missed_weight_bouts.csv` / `canonical_events.schema.json` write 0 B
  (empty audit / empty schema sidecar) — benign, regenerated each run, not corrupt.

Conclusion: I did not fabricate deletions. The one superficially-stale artifact is
live test infrastructure — which surfaces a real **fragility (Rec U6):** the test
suite depends on a gitignored 13 MB snapshot by hardcoded path.

## 5. Tests
Targeted suite (whr / dominance / backtest / peaks / performance): 59 passed.
Full suite incl. notebook exec: **178 passed** in 377 s (was 165 pre-session; +13 from
the two new dominance test cases and the prior session's untracked test files).

## 6. Evaluation of decisions + recommended upgrades (APPROVAL-GATED)

**Decisions assessed as SOUND:** two-lens Complete(filter)/Legacy(smoother) split;
WHR (Coulom 2008) as the era-comparable lens; the diagnosis that lowering
`ERA_NORM_MAX_STRENGTH` was inert (WHR re-anchors mean each pass → no trend to
de-trend); additive era premium as the structural fix; two-sided dominance as the fix
for a smoother ranking the whole record; dedup-via-max of overlapping opponent-quality
signals; tanh soft-saturation over hard clamps. Execution is clean and tested.

**Recommended upgrades:**
- **U1 (HIGH, correctness) — stop double-correcting the era trend.** The premium adds a
  year-slope to WHR mu; `peaks._era_division_normalized_mu` then removes ≤
  `ERA_NORM_MAX_STRENGTH` of that *same* slope (bridge-gated, so the realized premium
  varies by year in an uncontrolled way). Exempt `whr_*` streams from the era-de-trend
  half while keeping the division-depth rescale. Rationale: era-norm exists to patch the
  Glicko *filter* artifact; WHR has no such artifact and now carries an *intentional*
  era signal. Makes realized = nominal and fully tunable.
- **U2 (HIGH, serves stated goal) — fix the dominance index.** `ratings/dominance.py`
  is an un-normalized z-sum of *accumulated* sig-strikes / sub-attempts / control-
  seconds, with no per-time normalization and no finish floor; the score-path bonus only
  touches decisions. So long fights inflate dominance and a 60-second KO scores ~0 — the
  exact reason Romero/Ngannou barely moved. Fix: (a) floor dom_level high for finishes
  (a finish *is* dominance), (b) z-score per-minute rates not totals. Directly unlocks
  the user's "reward dominant finishers" intent that U-this-session only half-delivered.
- **U3 (MEDIUM) — concave / data-driven era premium.** Replace the linear +k·(yr−ref)
  with a curve derived from the Glicko per-fight-mean-by-year (the engine's own measured
  era-difficulty), monotonized — so Legacy inherits Complete's *measured* era shape,
  the newest years stop being over-rewarded, and spanning eras beats being newest.
- **U4 (MEDIUM) — systematic tuning.** Use the existing `whr_backtest.py` to sweep
  (`PER_YEAR`, `WHR_DOMINANCE_WEIGHT_AMPLITUDE`, `WHR_DOMINANCE_SCORE_SCALE`) against a
  predictive metric + the cohort table, replacing single-point hand-set guesses.
- **U5 (LOW) — center the premium reference at the data mean year** so WHR's global mean
  is snapshot-stable as data grows (cosmetic robustness).
- **U6 (LOW, process) — de-fragilize tests:** they pin a gitignored snapshot by hardcoded
  path; commit a tiny synthetic fixture or document the dependency.

## 7. Upgrades implemented this session (approved: U1 + U2 + U3 + scorecard gap)

User approved U1, U2, U3 and added a fourth request: *"fight dominance should consider
affine normalized round win gaps in decisions."* All four implemented together (one
recompute).

**U2 — dominance index rebuilt (`ratings/dominance.py`).**
- Per-minute exposure normalization: strikes / sub-attempts / control are divided by bout
  duration (`end_round`,`end_time_seconds`; 1-min floor) before A−B diff + z-score, so a
  60-second blow-out is no longer penalized for brevity and a 25-min grind is no longer
  flattered for length.
- Finish floor: a KO/TKO or Submission win floors the winner-perspective dominance at
  `DOMINANCE_FINISH_FLOOR_Z = 2.75` (→ Legacy dom_level ~0.8). Now returns one row per
  bout so finishes lacking round data still earn the floor.

**Scorecard round-win gap (user request) — decision dominance.** New
`_scorecard_margin_a` joins `datalab_scorecards.parquet` to the bout by normalized
`{name,name}`+date (38.7% of decisions carry a card; verified Merab 30-29-29 → +1.67).
The mean judge margin (50-45 sweep = +5, 48-47 = +1) is **affine-normalized (z-scored)
over carded decisions** and added as a fourth dominance component for decisions only —
so a one-sided decision reads dominant even when strike/control rates were close.
Decision dominance now spans p5 −2.3 … p95 +1.9 (finish floor +2.75 sits just above a
typical dominant decision; an exceptional sweep can still exceed a finish).

**U1 — WHR era-de-trend exemption (`ratings/peaks.py`).** `_era_division_normalized_mu`
gained `detrend_era`; `rolling_peak`/`five_year_peak`/`sustained_peak` thread it;
`rate_snapshot` passes `era_detrend = not base.startswith("whr")`. WHR/Legacy streams now
skip the year de-trend (which was re-flattening the very premium we inject) but keep the
division-depth rescale. Glicko streams are unchanged.

**U3 — data-driven concave era premium (`ratings/constants.py`,`rate_snapshot.py`).**
Replaced the linear `WHR_ERA_PREMIUM_PER_YEAR=4.5` with `WHR_ERA_PREMIUM_STRENGTH=1.0`.
`_build_era_premium_by_year` derives the premium from the Glicko canonical per-year mean
mu (the engine's own measured era-difficulty), drops init-transient thin years
(<40 fight-rows; year-2000 was exactly 1500 on 14 fights), 3-yr smooths, monotonizes
(cummax), centers on 2010, scales by STRENGTH. Resulting curve: 2001 −72 → 2010 0 →
2015 +3 → 2020 +31 → 2025 +50 (concave: steep early professionalization, modern plateau)
— span ~124, comparable magnitude to the prior linear run but a better shape, and with
U1 it lands at ~full nominal.

Tests: 5 new in `tests/test_dominance_upgrades.py` (finish floor, per-minute pace,
scorecard gap separation, era curve monotone+zeroed, detrend-flag), all green.

## 8. After-results (upgrades) — recompute clean (exit 0)

Legacy rank (men, Prime) across the three states — **bef** = pre-session,
**lin** = this session's first pass (linear premium + two-sided dom), **UPG** =
+U1/U2/U3/scorecard-gap. Era slope (base mu_whr) held at +131 (≈ the linear run's
+129; comparable magnitude, better shape).

| cohort | fighter | Complete | bef | lin | UPG | net |
|---|---|--:|--:|--:|--:|--:|
| pioneers | Randy Couture | 45 | 13 | 20 | 24 | −11 |
| | Matt Hughes | 55 | 15 | 24 | 30 | −15 |
| | Tito Ortiz | 74 | 31 | 49 | 56 | −25 |
| | Chuck Liddell | 50 | 30 | 45 | 47 | −17 |
| | Tim Sylvia | 56 | 28 | 41 | 46 | −18 |
| finishers | **Francis Ngannou** | 30 | 33 | 31 | **23** | **+10** |
| | Robert Whittaker | 28 | 52 | 44 | 44 | +8 |
| | Yoel Romero | 29 | 67 | 65 | 64 | +3 |
| multi-era | Jon Jones | 2 | 1 | 1 | 1 | 0 |
| | Georges St-Pierre | 4 | 2 | 2 | 2 | 0 |
| | Demetrious Johnson | 23 | 3 | 5 | 5 | −2 |
| | Anderson Silva | 1 | 4 | 8 | 8 | −4 |

**Reads.**
- **Finish floor (U2) is the headline win:** Ngannou #33→#23, now *above* his Complete
  rank — the pure KO artist whose quick finishes scored ~0 under the old accumulated-stats
  index is finally rewarded.
- **Whittaker/Romero rise only modestly and that is correct:** a smoother ranks the whole
  record, and two-sided dominance now makes their dominant *losses* (e.g. Whittaker KO'd by
  Adesanya) cost more. Dominance rewards *how you win*; it does not erase that you also
  lost. Both sit mid-board, consistent with multi-loss, no-title (Romero) resumes.
- **Era premium (U1+U3) is cleaner:** pioneers drop further and progressively as the
  concave curve's steeper early penalty lands at full nominal (no de-trend claw-back);
  greats who span eras hold the top (Jones/GSP unchanged, DJ/Silva top-8).
- **Residual tension (honest):** ultra-recent dominant champs still rank high
  (Merab Dvalishvili Legacy #16 vs Complete #49) because the Glicko data shows genuine
  continued modern inflation 2018-2025. Defensible under "modern is harder"; dial
  `WHR_ERA_PREMIUM_STRENGTH` (1.0 → ~0.7) if prior-era greats should sit higher.

Net: era-flatness corrected, the dominance signal is now correctly shaped (finishes and
sweeps count; being finished costs), and the knobs (`WHR_ERA_PREMIUM_STRENGTH`,
`DOMINANCE_FINISH_FLOOR_Z`, `WHR_DOMINANCE_*`) are all tunable for further iteration.

