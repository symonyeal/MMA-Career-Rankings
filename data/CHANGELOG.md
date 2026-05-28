# Snapshot Changelog

## 2026-05-28 - Dual division concept + lens consolidation + Weight Classes section

Follow-up to the same-day title-anchor change. Walking through real careers
(GSP one MW cameo, Makhachev never lost LW before moving to WW, Topuria one
LW belt over a long FW career, Pereira majority LHW) showed one label is not
enough: divisional rankings should bucket by where the *career* happened, but
"where this fighter competes now" is its own useful answer.

- **Two divisional labels per fighter.** `ratings/division_resume.py`
  `primary_division_rows` now returns `career_division` (simple majority of
  effective fights, recency as tiebreak) **and** `current_division` (most
  recent UFC title-fight win, or the same as career when no belt was ever
  won). Old `primary_division` / `primary_division_reliability` columns are
  retired. Result: GSP is a career WW (one MW cameo doesn't relocate);
  Makhachev is a career LW (currently WW); Topuria is a career FW (currently
  LW); Pereira is now career LHW (more UFC fights than at MW).
- **Divisional bucketing uses career.** Every single-division view —
  leaderboard filter, `top_fighter_placement_scatter`,
  `top100_division_density_chart`, `division_strength_comparison_chart`,
  `sleeve_ranking_table` — now buckets by `career_division`, so a fighter
  surfaces under the class they made their name in regardless of a recent
  cameo. `current_division` is shown as a "Now competes" column where it
  differs.
- **Lens dropdown reduced to {Wins, Complete, Legacy}.** Finishes / Clean /
  Strength were thinly-different leaderboards: Complete already combines
  finish-quality + integrity + opponent-strength, and the PED list at the
  bottom of the notebook surfaces the integrity layer directly. Internal
  Clean/Strength labels stay in the audit ("What Moved a Fighter's Rating")
  cell because they describe the layers behind Complete.
- **Weight Classes section is one cohesive block.** Strength-over-time,
  single-year ranking, era heat map, top-100 share, and a division-leaders
  table all live in one cell with shared year-range and division controls.
  The old standalone "Era Check" section is gone — the heat map moved here.
- **Year range slider replaces single-year controls** on the strength
  timeline + era heat map; a separate snapshot-year slider drives the single-
  year ranking. Subsection of years is now a first-class control.
- **Single-year division ranking redesigned.** Replaces the aggregate
  one-bar-per-division chart with a per-class mini-leaderboard: top 5 actual
  fighter names in each selected weight class for the snapshot year. New
  helper: `analysis/viz.py:division_year_top_fighters_chart`.
- **Current-leaders table is per-division.** The old multi-division "current
  leaders" table is replaced with a single-division Dropdown → top 15 of
  that class (the user's "select a class, see the top 15"). The table also
  flags movers via a "Now competes" column.
- **Résumé vs Rating moved up + polished.** It now sits right after the
  Rankings (it's the natural sanity-check for them). Scatter labels the top
  six by name, ranks 1-10 keep their numbered chip, the long tail is a
  uniform small dot — no more "every dot fights for space" cluster. Top-100
  share moved into the Weight Classes block.
- **Win-streak overlay.** The streak section's fighter search now *overlays*
  the searched fighter's timeline on top of the picked-streak fighter rather
  than replacing it, so two runs can be compared head to head on the same
  axes. Primary line stays sky / secondary line goes violet.
- 155 passing (one new dual-division test for the GSP case; the
  notebook-dashboard test was updated for the moved era widget).

## 2026-05-28 - Title-anchored home division + cross-division pedigree carry-over

Acts on the observation that a fighter's home weight class was identified by
raw plurality of effective fights, which mislabeled Topuria (FW → LW),
McGregor (FW → LW), and Makhachev (LW → WW) — fighters who *vacated* a belt
and *won* the next division's title. Cameo fights up or down a class were also
pulling fighters' divisional placement around.

- **Home division now follows the belt.** `ratings/division_resume.py`
  `primary_division_rows` picks home as the division of the fighter's most
  recent UFC title-fight win (a title *loss* up or down a class —
  e.g. Volkanovski's lightweight title shots — does not relocate).
  Non-champions stay on the majority-of-career rule, with recency only as a
  tiebreak. Catch Weight / Open Weight / unparsed labels are no longer eligible
  as a home class.
- **Cross-division pedigree carry-over.** Per-division resume scores now shrink
  toward `pool_mean + bounded pedigree bump` rather than the pool mean alone.
  The bump is `min(0.30 × (fighter_best_other_division − pool), 40)` — a proven
  mover starts a little above the pool ("first fight bump") and converges
  toward their real in-division resume as the reliability shrinkage flattens.
  The cap keeps it a bump, never a full legacy loan: the no-legacy-loan
  regression test still passes (a thin two-fight cameo cannot top an
  established reign — GSP, Usman, Hughes still lead all-time Welterweight even
  with Makhachev now bucketed there).
- **`primary_division_share` → `primary_division_reliability`.** The old
  "share" was a fraction of effective fights and read misleadingly low for
  fresh title movers. The replacement is the home division's resume reliability
  in [0, 1] — how earned the home label is. Volkanovski FW ≈ 0.81,
  Makhachev WW ≈ 0.20.
- **Single-division views bucket by home.** `analysis/viz.py` divisional
  sleeve table, top-fighter placement, top-100 density, and division-strength
  comparison now prefer `primary_division` over `recent_division` (last bout),
  so a champion who moved up is listed under the division they actually
  belong to.
- New constants in `ratings/constants.py`: `DIVISION_CARRYOVER_FRAC`,
  `DIVISION_CARRYOVER_CAP`, `DIVISION_HOME_RECENCY_HALFLIFE_DAYS`. New
  `division_resume` columns: `division_last_fight_date`,
  `division_last_title_win_date`, `division_recency_weight`,
  `division_carryover_bump`.
- `pytest` 154 passing (including 5 new home-division scenario tests); snapshot
  `2026-05-13` + SQLite regenerated.

## 2026-05-14 - Active project cleanup

- Archived the redundant Greco scraper checkout; its six CSVs matched
  `data/raw/2026-05-13/` byte-for-byte. `refresh.py` and
  `loaders/ufcstats_loader.py` now default to `data/raw/<snapshot-date>` when
  those CSVs exist.
- Archived two unused UFC-DataLab CSVs (`stats_processed.csv`, `stats_raw.csv`);
  the four CSVs read by `loaders/datalab_loader.py` remain active.
- Removed regenerable local artifacts: `.test_tmp/`, empty Codex/agent
  scaffolds, empty `scripts/`, and all `__pycache__/` directories.
- Moved stale outer-folder `data/` and `analysis/` contents to
  `F U N/archive/symon-ufc-rank-engine-cleanup-2026-05-14/`.

## 2026-05-14 - WHR promoted to headline + title-bonus de-duplication

Acts on the consensus-validation finding (MODEL_ISSUES_AND_DIAGNOSIS.md
Issue 10): the windowed Glicko-2 period streams still mis-ranked relative to
consensus (Benson Henderson #8, Chris Weidman #11 on a 12-8 record, Cormier
above Jon Jones) while the WHR sidecar did not.

- **WHR is now the default headline ranking.** `rate_snapshot` leads its
  report with `sustained_peak_headline_mu_whr` / `five_year_peak_headline_mu_whr`
  (the `method_integrity_performance` stream is kept as a comparison print);
  `refresh.py`'s changelog top-10, `viz.sustained_peak_leaderboard_chart`, and
  the notebook fighter card all lead with WHR. Rationale: WHR is a smoother,
  so it is comparable across eras at the rating layer and does not carry the
  era-inflation / career-shape artifacts of the windowed streams.
- **Title bonuses de-duplicated in `ratings/peaks.py` `_context_adjustment`.**
  The title-win / champion-win / divisional-rank / P4P-rank win bonuses all
  describe the same fact ("you beat elite opposition") and were being SUMMED —
  a title win over a top-5 P4P-top-5 reigning champion stacked
  `55 + 35 + 25 + 25 = 140` mu on one fight, multiple-counting that floated
  title-reign-then-decline resumes. They are now DEDUPLICATED VIA `max` (the
  single strongest signal), matching `combined_opponent_quality_level` and the
  performance sleeve. Title-fight participation (`+8`, applies win or lose)
  stays a small separate additive term.
- `pytest` 119 passing; snapshot `2026-05-13`, SQLite, notebook regenerated.

## 2026-05-14 - Literature-grounded re-parameterization + WHR smoother sidecar

Replaces the hand-picked Phase-0 sensitivity constants with data-derived,
reliability-weighted quantities, and adds a Whole-History Rating smoother as a
sidecar stream. Literature basis: Berry, Reese & Larkey (1999) on era bridges;
Efron-Morris / James-Stein empirical Bayes; Coulom (2008) Whole-History Rating;
Dangauthier et al. (2007) TrueSkill Through Time.

**Phase 1 — `ratings/peaks.py` re-parameterization (all data-derived):**

- **Era / division normalization** is now empirical-Bayes. Each calendar
  year's mean shift is James-Stein shrunk by `tau2/(tau2+sampling_var)` (with
  `tau2` estimated from the data) and gated by the year's *bridge fraction* —
  the share of that year's fighters who also fought another year (BRL: era
  effects are only identifiable through fighters who span eras). Each
  division's mean/std is empirical-Bayes shrunk the same way. Net realized
  strength is `ERA_NORM_MAX_STRENGTH * eb_factor * bridge_factor` — strictly
  milder than the old flat 0.5 and mildest where data is thin/unbridged.
- **Opponent-quality weight** is now a logistic (Bradley-Terry-shaped) mapping
  of opponent quality to weight, replacing the ad-hoc power law.
- **Information-weighted results.** A win is weighted by opponent quality; a
  loss is weighted by opponent *weakness* on top of a real floor (losing to a
  weak opponent is more damning than losing to a champion).
- **Empirical-Bayes score shrinkage.** Each fighter's window score is
  James-Stein shrunk toward the pooled mean by its sampling reliability
  (`within_window_var / window_n`) — mild for well-sampled windows.

**Phase 2 — `ratings/whr.py` (new) Whole-History Rating smoother:**

- A Bayesian smoother (dynamic Bradley-Terry likelihood + Wiener-process
  prior, joint MAP over the whole history via per-fighter tridiagonal Newton
  steps). Unlike the Glicko-2 *filter*, it propagates information both
  directions, so ratings are comparable across eras at the rating layer.
- Runs as a sidecar `whr` stream: `ratings_history_whr.parquet`, `mu_whr` in
  `ratings_current`, plus `sustained_peak_*_whr` / `five_year_peak_*_whr`
  period columns. `WHR_W2_PER_DAY` should ultimately be tuned by predictive
  backtest (see RESEARCH_RECOMMENDATIONS.md).
- New `tests/test_whr.py` (5 tests). Suite at 119 passing.

## 2026-05-14 - Peak-score rework: era/division normalization + opponent-quality priority

Addresses the consensus-deviation diagnosis (MODEL_ISSUES_AND_DIAGNOSIS.md
Issue 10). All corrections live in `ratings/peaks.py` + `ratings/constants.py`
and are deliberately conservative (gentle blends, not hard overrides).

- **Era / division normalization of window mu.** Before scoring, each
  appearance's rating is de-trended for its calendar-year mean and rescaled by
  its division's depth (with `zeta = 1 - exp(-N/50)` shrinkage), self-calibrated
  to the snapshot's global mean/std. Blended only `ERA_NORM_STRENGTH = 0.5` of
  the way toward the normalized value so it nudges era inflation and
  division-depth bias out without large rank swings. Fixes pre-2010 legends
  being crushed and light-division / women's greats being suppressed.
- **Opponent quality is the first-priority signal.** Peak opponent weight is
  now mildly convex (`PEAK_OPP_WEIGHT_EXPONENT = 1.25`) and title bouts carry a
  `PERIOD_TITLE_FIGHT_WEIGHT_MULT = 1.25` weight multiplier — a window of
  title-fight wins over champions outweighs a window of finishes over mid-rank
  opponents. Method of victory stays a minor signal.
- **Loss leverage eased.** Losses now carry `PERIOD_LOSS_APPEARANCE_WEIGHT =
  0.50` base weight vs `0.25` for wins/draws (was effectively ~1/9 the leverage
  of a marquee win).
- **Activity bonus** raw fight-count term cut (`PERIOD_ACTIVITY_BONUS_PER_FIGHT`
  1.5 -> 0.5) so it no longer rewards padding or punishes efficient short
  careers.
- **5-Yr gate** lowered 9 -> 8 (injury-shortened greats stay visible); the
  10-year sustained gate stays at 13 UFC fights.
- The 2-year `career_peak` surface stays discarded. `replacement_framework.py`
  remains dead code, superseded by the above.
- Tests updated for the new gate; `pytest` 114 passed. Snapshot `2026-05-13`,
  SQLite, and notebook regenerated.

## 2026-05-14 - Consistency pass: single canonical snapshot + cleanup

- **Snapshot drift reconciled.** The repo held three conflicting snapshots:
  `2026-05-12` (had odds + DataLab + FightMatrix staged, but stale ratings and
  no `ratings_history.parquet`) and `2026-05-13` (fresh full ratings, but no
  odds/external artifacts). `2026-05-13` is now the single canonical snapshot:
  the staged `odds_lines.parquet`, `datalab_*`, and `fightmatrix_*` artifacts
  were copied in, then `rate_snapshot`, `build_database`, and the notebook were
  re-run end to end. Performance sleeve's odds sub-factor is now active
  (6,562 ok-quality odds rows). `2026-05-12` and `2026-05-12-pre-consolidation`
  were removed (regenerable / superseded).
- **Redundant data removed.** Deleted the 277 MB `UFC-DataLab` checkout down to
  the 4 CSV exports the loader actually reads (`stats_processed_all_bouts.csv`,
  `merged_stats_n_scorecards.csv`, `raw_fighter_details.csv`,
  `SCORECARDS.csv`); deleted 3 unused sibling API repos
  (`fightmatrix-api-jpgninja`, `fight-matrix-api-valish`, `mma-api-valish`);
  deleted the deprecated jasonchanhku odds CSV. Removed build-tool cruft
  (`.uv-cache/`, empty `uv.lock` stub) and regenerable temp dirs
  (`.test_tmp/`, `pytest-tmp/`, `probe700/`, `__pycache__/`). Project footprint
  dropped from ~1 GB to ~610 MB (450 MB of which is `.venv`).
- **Verified end to end:** `pytest` 114 passed; `rate_snapshot` exit 0;
  `build_database` 26 tables / 102 indexes; notebook rebuilt.
- **Evaluation finding (see MODEL_ISSUES_AND_DIAGNOSIS.md Issue 10).** The live
  period-score model in `ratings/peaks.py` still ranks Kamaru Usman (#7) and
  Chris Weidman (#9) inside the sustained-peak top 10, while GSP is #15 and
  Demetrious Johnson is outside the top 30. The more sophisticated
  `ratings/replacement_framework.py` (era-depth shrinkage, division-depth
  correction, championship-adequacy caps) is **not wired into the engine** —
  it is dead code. Documented, not yet fixed.

## 2026-05-13 - Principled peak windows + shared opponent quality

- Career Peak is now a 2-year rolling window scored from the top 3
  opponent-quality appearances, not a single all-time max `mu` point.
- Sustained Peak is now a 10-year rolling window that qualifies with at least
  13 UFC fights, then scores the top 13 opponent-quality appearances in that
  window. If the window has more than 13 fights, lower-quality opponents do
  not dilute the score.
- 5-Yr Peak remains a diagnostic, now using at least 9 UFC fights and the top
  9 opponent-quality appearances.
- Peak opponent quality uses actual bout opponents and the shared monotonic
  quality signal used by the performance sleeve: pre-fight canonical mu,
  divisional rank, championship context, and P4P context.
- The performance sleeve now replaces the dominance/finish-speed/five-round
  triplet with `perf_factor_decisiveness` and adds
  `perf_factor_activity_loss` for post-layoff losses; UFC debuts are neutral.

## 2026-05-13 - Performance sleeve rebuild: tanh smoothing + rank-gated upset

- **Saturation eliminated.** The hard `[0.80, 1.20]` clamp on the performance
  weight was firing on 13.7% of winner appearances (with overshoots up to
  +0.58 in the raw product). Replaced the multiplicative-product-and-clamp
  combination with a tanh-smoothed mapping of an additive log-signal:
      performance_weight_winner = 1 + 0.20 * tanh(S / PERF_TANH_SCALE)
      performance_weight_loser  = 1 - 0.20 * tanh(S / PERF_TANH_SCALE)
  Under the new formula no winner row hits the cap on the 2026-05-12 snapshot;
  99th-percentile winner weight is 1.173, the maximum is 1.196.
- **Opponent-quality factors deduplicated via max.** Opponent mu strength,
  division-rank context, championship context, and P4P context all measure
  "how elite was the opponent". They no longer triple-count: only the
  strongest single signal contributes to the per-fight log-signal `S`. The
  individual `perf_factor_*` columns are retained in
  `performance_appearances.parquet` for audit transparency.
- **Rank-gated upset factor added.** `perf_factor_upset` fires only when
  `winner_rank - opponent_rank >= 6` (champion = rank 0, unranked = rank 16).
  A #3-vs-#4 fight (gap 1) no longer triggers an upset; an unranked
  challenger beating the champion does. Moneyline odds can confirm the
  upset for fights with sparse rank data, but only when the rank gate is
  already open. Upset factor fires on 4.9% of winner rows (down from
  continuous firing on every plus-money winner).
- **Loser-side performance sleeve activated.** Losers now carry the symmetric
  mirror weight driven by the same per-fight `S`. The legacy "loser-stays-at-
  1.0" rule masked anchor events like GSP losing to Matt Serra at UFC 69.
  The weight-class-down-loss amplifier remains a structural override (loss
  detracts more) and is not composed with the tanh damp.
- **Anchor calibration confirmed on the 2026-05-12 snapshot:**
  - Matt Serra def. GSP (UFC 69, 2007-04-07) → Serra winner weight 1.192,
    GSP loser weight 0.808 (matches the user's 0.80 floor anchor).
  - Strickland def. Adesanya (UFC 293, 2023-09-09) → Strickland winner
    weight 1.164, Adesanya loser weight 0.836 (Strickland was canonical
    rank #7 so the structural signal is lower than Serra-GSP).
- **New audit columns** in `performance_appearances.parquet`:
  `perf_factor_upset`, `perf_upset_rank_gap`, `perf_signal_S`,
  `perf_winner_signal_S`.
- Constants `PERF_OPPONENT_QUALITY_AMPLITUDE`, `PERF_UPSET_AMPLITUDE`,
  `PERF_UPSET_RANK_GAP_THRESHOLD`, `PERF_UPSET_RANK_GAP_SCALE`,
  `PERF_TANH_SCALE` added to `ratings/constants.py`. Legacy per-factor
  amplitudes retained as audit-only.
- Rebuilt `ratings_current.parquet`, all sleeve histories,
  `performance_appearances.parquet`, `analysis/notebook.ipynb`, and
  `data/ufc_rank_engine.sqlite` from the 2026-05-12 snapshot. Suspect-
  fighter cap-hit shares dropped from 50-83% to 0% across the board.
- Updated `MODEL_ISSUES_AND_DIAGNOSIS.md` (new Issue 8 with full diagnosis)
  and `RESEARCH_RECOMMENDATIONS.md` (new sections 9-12 for state-space
  dynamic aging, continuous decisiveness scoring, heavy-tailed upset
  handling, and hierarchical priors for cross-org imports).
- Test suite green at 99 tests (was 94 in the prior pass) — added
  rank-gated upset firing/non-firing tests, tanh saturation envelope test,
  symmetric winner/loser weight test, and draw-weight test.

## 2026-05-13 - Rank/champ/P4P/weight-class context + true Sustained Peak

- Performance sleeve now includes three explicit context sub-factors:
  `perf_factor_rank_context`, `perf_factor_championship`, and
  `perf_factor_p4p`.
- Added `perf_factor_weight_class`: moving up and winning receives a modest
  winner-side boost, while moving down and losing receives a modest loser-side
  update increase so the loss detracts more.
- Context is derived from pre-fight model state only: top-15 divisional rank,
  top-15 pound-for-pound rank, and title lineage inferred from prior UFC title
  fights. Current FightMatrix rankings remain comparison data and are not
  backfilled into historical fights.
- `performance_appearances.parquet` now exposes the audit fields behind those
  factors, including opponent pre-fight division/P4P ranks and inferred
  champion/interim champion flags, plus previous/current division fields for
  weight-class movement.
- `sustained_peak_mu_<stream>` is now a true 10-year opponent-weighted rolling
  peak for every stream. `five_year_peak_mu_<stream>` remains the shorter
  `5-Yr Peak` diagnostic.
- Default engine reporting and notebook controls lead with all-sleeves career
  peak and Sustained Peak; current `mu` remains persisted as debug state.
- Added analysis audit helpers for transparent inspection:
  `performance_factor_audit_table`, `integrity_factor_audit_table`, and
  `sleeve_factor_summary_table`.
- Rebuilt `ratings_current.parquet`, all sleeve histories,
  `performance_appearances.parquet`, `analysis/notebook.ipynb`, and
  `data/ufc_rank_engine.sqlite` from the 2026-05-12 snapshot.

## 2026-05-13 - Sleeve consolidation + mdabbert odds + 5-stream architecture

Architecture rewrite. The engine now emits **five** rating streams instead of
the prior sixteen:

- `canonical` (pristine, never sleeved)
- `method` (method-bonus base)
- `method_integrity` (PED + DQ + missed-weight damp)
- `method_performance` (quality + market residual reward)
- `method_integrity_performance` (both)

All per-fight sleeve weights are clamped to the symmetric envelope
`[SLEEVE_FACTOR_MIN, SLEEVE_FACTOR_MAX] = [0.80, 1.20]`. Individual sub-factor
amplitudes never exceed 0.20.

Peak metrics renamed and re-defined for both canonical and method:
- `career_peak_mu_<stream>` — full-career maximum mu.
- `sustained_peak_mu_<stream>` — best 5-year (was 10y) window, min 5
  qualifying fights, opponent-weighted (`(opp_pre_mu - 1500) / 200`,
  clipped to `[0, 2]`).

Sleeve consolidation:
- **Integrity sleeve** (was: PED-flip): per-fight multiplicative damp,
  PED at -20% (floor), DQ wins at -8%, missed-weight wins at -12%.
  Compose multiplicatively, clamp to `[0.80, 1.0]`.
- **Performance sleeve** (merged quality + odds): six sub-factors
  multiplied (dominance, finish speed, five-round, opponent strength,
  opponent streak, market residual), clamped to `[0.80, 1.20]`. Losers
  and draws keep weight 1.0.

Source/code changes:
- Added `ratings/integrity_adjustment.py`, `ratings/performance_adjustment.py`,
  `ratings/peaks.py`, `loaders/integrity_flags.py`.
- Deleted `ratings/quality_adjustment.py`, `ratings/odds_adjustment.py`,
  `symon_ufc_rank_engine_batch.py`, `loaders/odds_ingest_jasonchanhku.py`.
- `ratings/rate_snapshot.py` rewritten end to end.
- Missed-weight detection moved into `loaders/integrity_flags.py` and
  draws from Greco `details_text` + optional mdabbert weight-vs-class
  divergence.
- Aliases: `data/external/aliases/fighter_aliases.csv` (vendored from
  tiger-millionaire, MIT) now consumed by `project_helpers.normalize_name_key`.

Odds source rotation:
- Replaced jasonchanhku odds (no license; ~13.6% coverage, 2013-2017)
  with mdabbert Ultimate UFC Dataset (Apache-2.0; ~78% coverage,
  2010-2026). Pair-and-date join, source-tagged
  `odds_source = "mdabbert-ultimate-v1"`.
- New module: `loaders/odds_ingest_mdabbert.py`.

Notebook:
- Section L composer reduced from three sleeve checkboxes to two
  (integrity + performance). The scoring dropdown locks sleeves to off
  whenever the user picks "canonical" — canonical stays pristine.
- Fighter detail card surfaces career + sustained peak for both
  canonical and method streams plus all three sleeve-stream mus.

Tests:
- New: `test_integrity_adjustment.py`, `test_performance_adjustment.py`,
  `test_peaks.py`, `test_integrity_flags.py`, `test_odds_ingest_mdabbert.py`,
  `test_aliases.py`.
- Replaced: `test_viz_smoke.py`, `test_database_builder.py`,
  `test_odds_engine.py`.
- Removed: `test_quality_adjustment.py`, `test_ped_adjustment.py`,
  `test_odds_adjustment.py`, `test_odds_ingest_jasonchanhku.py`.

Backup: pre-consolidation snapshot copied to
`data/snapshots/2026-05-12-pre-consolidation/` for rollback.

## 2026-05-12 - Phase D: real-odds ingest live (jasonchanhku UFC archive)
- New module `loaders/odds_ingest_jasonchanhku.py` downloads the public
  github CSV (no LICENSE, treat as local-use only), parses ~1,312 UFC
  bouts of decimal odds, and matches each to a canonical `fight_url`
  using a normalized unordered fighter-pair join. Rematches are
  resolved to the earliest-date matching bout (jch dataset has no
  date column). The CSV is cached locally at
  `data/external/odds/UFC-MMA-Predictor/UFC_Fights.csv` and never
  committed to this project.
- Loosened `_RAW_SUM_MIN` in the odds quality flag from 1.0 to 0.85:
  jch is a best-of-market aggregate, so raw implied sums cluster
  around 1.007 (vig competed away by competition between books),
  not the 1.04–1.08 a single sportsbook's vig'd line would show.
  Anything below 0.85 is still flagged as `negative_vig`.
- Production end-to-end run on the 2026-05-12 snapshot:
    - canonical fights:        8,346
    - odds_lines rows total:   1,135
    - odds-covered fights:     1,134 (13.6% coverage; era ~2013–2017)
    - ratings_current rows:    2,507
    - ratings_history_odds:   16,692
    - odds_adjustment_dist:    2,262 rows (positive + negative cohorts)
    - SQLite tables:               23 (was 20 pre-odds)
    - SQLite indexes:              82
    - delta_mu_odds_adjusted   median +4.2, min -0.3, max +55.3
- The favorite-loss damping is visible in the delta_mu distribution
  being skewed positive — long-tenured top fighters (who tend to be
  favored most of the time) gain a few points because their occasional
  upset losses are forgiven 15% while their many expected wins are
  amplified up to 20%.
- 7 new ingest tests (4 pure-helper + 3 network-integration that skip
  if the github URL is unreachable). Whole suite green at 87 tests.

## 2026-05-12 - Phase B math correction: linear empirical min-max normalization
- Replaced the sign-aware ECDF (percentile-rank) mapping with a
  **linear empirical min-max normalization** of the signed residual.
  Both sides amplifying upsets above 1.0 was the wrong shape; the
  intended semantics is:
      positive residual (underdog overperformance) -> weight ABOVE 1.0
      negative residual (favorite underperformance) -> weight BELOW 1.0
  with the empirical max-positive and max-negative residuals in the
  snapshot serving as the normalization anchors.
- Constants in `ratings/constants.py` renamed accordingly:
      ODDS_WEIGHT_FLOOR / CEILING_POSITIVE / CEILING_NEGATIVE / POWER
        ->  ODDS_WEIGHT_POSITIVE_AMPLITUDE (default 0.20)
        ->  ODDS_WEIGHT_NEGATIVE_AMPLITUDE (default 0.15)
  The 20% / 15% numbers are *target amplitudes* the linear normalization
  reaches at the empirical extremes; the actual fight-level weight
  depends on each residual's position on the empirical residual line.
- Semantic flip from the previous (rejected) design: under the new
  formula, the favorite who loses the biggest upset of all time has
  their rating drop DAMPED by 15% (partial forgiveness — a bad night
  doesn't disprove the market read), rather than amplified.
- Engine-layer code is unchanged. The weighted Glicko-2 update path
  still consumes whatever per-result weights the appearance frame
  supplies; only the math that decides those weights moved.
- 27 new Phase A unit tests covering linear normalization, asymmetric
  amplitude, proportional scaling at the cohort midpoint, clamp
  behavior beyond cohort max, and empty-cohort fallback. Suite green
  at 80 tests.
- `odds_adjustment_distribution.parquet` schema column renamed
  `percentile` -> `normalized` (linear normalization value in [0, 1])
  to reflect the new math.

## 2026-05-12 - Odds-adjusted rating stream, Phase C (notebook UX + DB)
- `analysis/viz.py` gains four odds-aware helpers — `odds_coverage_summary`,
  `odds_adjustment_distribution_chart`, `odds_impact_chart`,
  `favorite_underdog_performance_table` — each degrades to a clean
  "unavailable" message instead of erroring when the snapshot has no
  odds artifact.
- New sleeve composer: `RATING_STREAMS`, `PEAK_VIEWS`, and
  `select_rating_column(ratings_current, stream, peak)` map a (stream,
  peak) selection to a concrete column in `ratings_current.parquet`.
  Returns `None` rather than KeyError'ing when a column is absent in
  the current snapshot.
- `analysis/build_notebook.py` adds two new sections to the regenerated
  notebook:
    - **K. Odds / Market adjustment** — coverage banner, residual
      distribution, biggest deltas, favorite/underdog table; hidden
      gracefully when odds data is unavailable.
    - **L. Rating-stream / sleeve composer** — interactive dropdowns
      (canonical / method / PED-adjusted / odds-adjusted, crossed with
      current / instant-peak / sustained-peak) that re-draw the top-N
      table against the selected column.
- `build_database.py` learns three new optional tables — `odds_lines`,
  `odds_adjustment_distribution`, `ratings_history_odds_adjusted` —
  with composite indexes on `(event_date, event_name)`,
  `(fighter_a, fighter_b)`, `market_favorite`, `market_underdog`, and
  `(fighter, event_date)`. Source-gap entry flips between
  `odds_source_not_ingested / pending` and
  `odds_source_ingested / loaded` based on artifact presence.
- 10 new tests covering the viz helpers, sleeve composer, and a
  synthetic-odds DB build. Suite green at 77 tests.

## 2026-05-12 - Odds-adjusted rating stream, Phase B (engine wiring)
- Added `_rate_weighted` helper and `WeightedRatingEngine` class in
  `ratings/glicko2_engine.py`. The vendored `_glicko2.py` is untouched
  per its "do not edit" header; the weighted variant lives entirely in
  the engine wrapper and applies a per-result weight `w_i` to each term
  of the Glicko-2 variance and difference accumulators.
- Regression test confirms: with every weight set to 1.0,
  `_rate_weighted` reproduces `Glicko2.rate()` to fp tolerance, and
  `WeightedRatingEngine` reproduces `RatingEngine`'s `mu_canonical`
  trajectory exactly across multiple events.
- `ratings/rate_snapshot.py` now runs a third (optional) pass whenever
  `data/snapshots/<date>/odds_lines.parquet` exists: builds fighter
  appearances, sign-aware empirical distribution, per-result weights,
  then a weighted engine over the full canonical fight set (weight 1.0
  for uncovered bouts). Emits `ratings_history_odds_adjusted.parquet`,
  `odds_adjustment_distribution.parquet`, and merges
  `mu_odds_adjusted / phi_odds_adjusted / sigma_odds_adjusted /
  delta_mu_odds_adjusted / rank_odds_adjusted /
  instant_peak_mu_odds_adjusted / sustained_peak_mu_odds_adjusted /
  odds_adjusted_rating_periods / last_event_date_odds_adjusted` into
  `ratings_current.parquet`.
- When no `odds_lines.parquet` is present (the current production
  state), the odds-adjusted columns and parquet artifacts are NOT
  added — `ratings_current` schema is identical to its Phase A state.
- 11 new tests covering scalar regression, engine regression, upset
  amplification, snapshot integration, and propagation through
  opponent ratings. Suite green at 67 tests.

## 2026-05-12 - Odds-adjusted rating stream, Phase A (scaffolding)
- Added optional market-odds adjustment scaffolding: pure American/decimal
  conversions, no-vig pair removal, sign-aware empirical residual
  distributions, and per-result update-weight mapping live in
  `loaders/odds_loader.py` and `ratings/odds_adjustment.py`. Weight
  tunables centralized in `ratings/constants.py` (`ODDS_WEIGHT_FLOOR`,
  `ODDS_WEIGHT_CEILING_POSITIVE`, `ODDS_WEIGHT_CEILING_NEGATIVE`,
  `ODDS_WEIGHT_POWER`).
- Mapping is **asymmetric**: positive residuals (underdog
  overperformance) get amplified up to +20%, negative residuals
  (favorite collapses) up to +15%; the most-expected outcomes damp to
  the 0.85 floor. Empirical percentile is computed within each sign
  cohort separately so the worst favorite collapse and biggest underdog
  upset both anchor their cohort's ceiling.
- Phase A adds no engine wiring, no parquet artifacts, and no schema
  changes to `canonical_fights` or `ratings_current`. Existing rating
  streams (`mu_canonical`, `mu_method`, `mu_ped_adjusted`) are unchanged.
- 43 new unit tests covering odds math and weight-assignment semantics;
  whole suite still green (56 tests).
- Odds source audit: no historical moneyline/decimal data present in any
  local source (Greco raw, DataLab staged, FightMatrix HTML cache, or
  sibling api_sources). `open_odds_a/open_odds_b` from mmadecoded remain
  pending. Plan for real ingestion is to scrape BestFightOdds.com (using
  `wrcarpenter`'s event-URL seed list) with OddsPortal as cross-check;
  `jasonchanhku/UFC-MMA-Predictor` (1,312 bouts, 2013–2017) is a starter
  cross-check fixture but neither sibling repo carries a LICENSE so none
  of their CSVs are redistributed in this project. See `SOURCE_MATRIX.md`
  for the full ingestion plan.

## 2026-05-12 - Database and notebook v2 audit
- Added `build_database.py` and built `data/ufc_rank_engine.sqlite` from the
  `2026-05-12` snapshot.
- SQLite now includes canonical UFC tables, ratings/dominance outputs,
  PED/exclusion audit tables, staged UFC-DataLab/FightMatrix tables, and
  metadata tables (`source_manifest`, `snapshot_manifest`, `table_row_counts`,
  `source_gaps`).
- Consolidated sustained peak constants in `ratings/constants.py`.
- Expanded `analysis/viz.py` and regenerated `analysis/notebook.ipynb` with
  Glicko vs FightMatrix, rank deltas, source coverage, PED impact, sustained
  peak, division strength, and DataLab scorecard insights.
- Cross-org/pre-UFC bouts remain staged only and are still not integrated into
  the headline UFC-only Glicko stream.

## 2026-05-12 - Ratings and dominance run
- Ratings history/current parquet files produced from the initial Greco snapshot.
- Dominance parquet files produced from significant-strike, submission-attempt,
  and control-time differentials.
- Added fight-level PED confirmation audit columns and
  `ped_confirmed_bouts.csv`; `ratings_current.parquet` now includes
  `mu_ped_adjusted`, `rank_ped_adjusted`, and `delta_mu_ped_adjusted`.
- Added project-local UFC-DataLab and FightMatrix staging outputs:
  `datalab_*.parquet`, `fightmatrix_rankings.parquet`, and summary JSON files.
- Sustained peak switched from single-period max rating to 10-year rolling mean
  with a 5-fight minimum; instant peak retained for context.
- Current top 5 by mu_canonical: Jon Jones, Ilia Topuria, Islam Makhachev,
  Shavkat Rakhmonov, Khabib Nurmagomedov.

## 2026-05-12 — Initial snapshot
- First build of the canonical fight bundle from the local Greco1899 CSVs
  (last refreshed upstream 2026-05-10 11:04).
- Sources used in that first pass: Greco only; DataLab/FightMatrix were staged later.
- Filters applied: UFC 28+ (2000-11-17 cutoff). UFC 1–27 dropped.
- Excluded bouts persisted to `_excluded_bouts.csv`.

(future snapshots: list new events, new fighters, biggest rating movers)

## 2026-05-13 - Refresh run
- Canonical snapshot rebuilt from Greco CSVs: events=743, fights=8346, rounds=39886, excluded=342.
- Ratings and dominance produced: fighters_rated=2507, fighter_event_rows=16692, events_processed=738.
- Streams: canonical (pristine) + method + method_integrity + method_performance + method_integrity_performance.
- Performance sleeve includes quality, market, rank context, championship context, and P4P context.
- Period metrics: 10-year and 5-year windows, opponent-weighted, result-aware, with all qualifying fights counted.
- Top 10 by sustained_peak_headline_mu_method_integrity_performance: Anderson Silva 2472.3; Daniel Cormier 2404.5; Jon Jones 2390.5; Alexander Volkanovski 2369.8; Israel Adesanya 2365.8; Islam Makhachev 2343.8; Kamaru Usman 2340.9; Jose Aldo 2307.0; Chris Weidman 2299.0; Max Holloway 2290.8
- Movers vs 2026-05-12-pre-consolidation by mu_canonical:
  - Up: Julia Polastri +0.0; Anthony Johnson +0.0; Ian Loveland +0.0; Cristiano Marcello +0.0; Alexandre Dantas +0.0; Jessin Ayari +0.0; Mark Eddiva +0.0; Joe Jordan +0.0; Josh Quinlan +0.0; Reese Andy +0.0
  - Down: Uros Medic -0.0; Ben Saunders -0.0; Ramazan Emeev -0.0; Anthony Rocco Martin -0.0; Kyle Noke -0.0; Erik Silva -0.0; Alessio Sakara -0.0; Felipe Olivieri -0.0; Patrick Cote -0.0; Tim Means -0.0
