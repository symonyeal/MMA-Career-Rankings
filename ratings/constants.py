"""Shared rating/reporting constants.

Convention after the 2026-05-13 consolidation:

* All per-result multiplicative factors fall inside a symmetric [-20%, +20%]
  envelope; ``SLEEVE_FACTOR_MIN`` and ``SLEEVE_FACTOR_MAX`` are the canonical
  floor / roof. Every sleeve sub-factor amplitude is ``<= 0.20`` so it cannot
  by itself exceed the envelope, and the final per-fight sleeve weight is
  clamped back to ``[SLEEVE_FACTOR_MIN, SLEEVE_FACTOR_MAX]`` after the
  factors are combined.
* Canonical rating is never sleeved. Sleeves only attach to the method
  stream. Streams that exist in ``ratings_current.parquet``:
  ``canonical``, ``method``, ``method_integrity``, ``method_performance``,
  ``method_integrity_performance``.
* Period scores are emitted for every stream. ``sustained_peak`` is a
  10-year rolling window and ``five_year_peak`` is a 5-year rolling window.
  The 2-year career peak surface is intentionally discarded. Period scores
  use all appearances in the window, with opponent quality, result, and
  activity all contributing.
* Window mu is era/division normalized before scoring (see
  ``ratings/peaks.py``): each appearance's rating is de-trended for the
  calendar-year inflation of the Glicko scale and rescaled for the depth of
  its division, so a 2005 welterweight and a 2024 flyweight are comparable.
  Normalization is self-calibrated to the snapshot's global mean/std, so an
  average-era / average-division fighter is unchanged.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Symmetric sleeve envelope.

SLEEVE_FACTOR_MIN: float = 0.80   # -20% floor — worst integrity penalty hits this.
SLEEVE_FACTOR_MAX: float = 1.20   # +20% roof — best performance bonus hits this.


# ---------------------------------------------------------------------------
# Period windows.

FIVE_YEAR_PEAK_WINDOW_DAYS: int = 1825  # 5 years
FIVE_YEAR_PEAK_WINDOW_LABEL: str = "5-Yr Period"
FIVE_YEAR_PEAK_MIN_FIGHTS: int = 8
FIVE_YEAR_PEAK_TITLE_EFFECTIVE_MIN_RAW_FIGHTS: int = 6
SUSTAINED_PEAK_WINDOW_DAYS: int = 3650  # 10 years
SUSTAINED_PEAK_WINDOW_LABEL: str = "10-Yr Period"
SUSTAINED_PEAK_MIN_FIGHTS: int = 13
SUSTAINED_PEAK_TITLE_EFFECTIVE_MIN_RAW_FIGHTS: int = 10


# ---------------------------------------------------------------------------
# Display labels for the nine 10-year-peak rating columns.
#
# On disk the columns keep their explicit `sustained_peak_headline_mu_<stream>`
# names so downstream code can resolve any (engine x sleeves) combo from the
# parquet directly. For anything a human reads — notebook, charts, sheets,
# print blocks, chat output — the rendering layer maps the long names through
# RATING_COLUMN_LABELS so the visible header is short.
#
# Internal parquet columns keep the exact stream names. Public labels use
# sentence-case product names so reports and notebooks do not leak model jargon.

RATING_COLUMN_LABELS: dict[str, str] = {
    "sustained_peak_headline_mu_canonical":                       "Prime Wins",
    "sustained_peak_headline_mu_method":                          "Prime Finishes",
    "sustained_peak_headline_mu_method_integrity":                "Prime Clean",
    "sustained_peak_headline_mu_method_performance":              "Prime Strength",
    "sustained_peak_headline_mu_method_integrity_performance":    "Prime Complete",
    "sustained_peak_headline_mu_whr":                             "Legacy",
    "sustained_peak_headline_mu_whr_integrity":                   "Legacy Clean",
    "sustained_peak_headline_mu_whr_performance":                 "Legacy Strength",
    "sustained_peak_headline_mu_whr_integrity_performance":       "Legacy Complete",
}

# Reverse lookup: short label -> on-disk column.
RATING_COLUMN_LOOKUP: dict[str, str] = {v: k for k, v in RATING_COLUMN_LABELS.items()}


def rating_label(column: str) -> str:
    """Return the short human label for a rating column, or the column itself."""
    return RATING_COLUMN_LABELS.get(column, column)


def rename_rating_columns(df):
    """Return ``df`` with rating columns renamed to short labels for display.

    Only renames columns that exist in the input frame; all other columns are
    untouched. The on-disk parquet is not modified — this is purely for the
    rendering layer.
    """
    overlap = {k: v for k, v in RATING_COLUMN_LABELS.items() if k in df.columns}
    return df.rename(columns=overlap) if overlap else df

# Era / division normalization of window mu (see ratings/peaks.py).
#
# Phase-1 rework (2026-05-14) — replaces the hand-picked flat blend with
# data-derived, reliability-weighted shrinkage. Literature basis:
#   * Berry, Reese & Larkey (1999), "Bridging Different Eras in Sports" —
#     era effects are only identifiable through "bridges" (fighters whose
#     careers span eras), so the era shift is gated by the bridge fraction.
#   * Efron-Morris / James-Stein empirical Bayes — the era shift and the
#     division rescale are each shrunk toward "no correction" by
#     ``tau2 / (tau2 + sampling_var)``, where ``tau2`` (true between-cell
#     variance) is estimated from the data, not guessed.
#
# Net effect: the realized per-cell normalization strength is
# ``ERA_NORM_MAX_STRENGTH * eb_factor * bridge_factor`` with both factors in
# [0, 1] — strictly milder than the old flat 0.5, and mildest exactly where
# the data is thin or unbridged. Normalization is a no-op below
# ERA_NORM_MIN_POPULATION (keeps small synthetic fixtures on the raw scale).
ERA_NORM_MIN_POPULATION: int = 200
ERA_NORM_MAX_STRENGTH: float = 0.50      # cap on realized normalization; EB+bridges scale within it
ERA_NORM_STD_FLOOR_FRAC: float = 0.5     # effective division std >= frac * global std

# Peak opponent-quality weight — opponent quality is the single most important
# signal in the engine. A title-heavy schedule against elite opponents must
# outrank a higher-volume schedule against mid-tier opponents, and a few PED
# or integrity violations against elites must not erase that.
#
#     opp_weight_i = SUSTAINED_PEAK_OPP_MAX_WEIGHT
#                    * logistic((quality_level_i - CENTER) / TEMP)
#                    * (PERIOD_TITLE_FIGHT_WEIGHT_MULT if title bout else 1.0)
#
# Windows qualify by UFC fight count (>= *_MIN_FIGHTS). Once a window
# qualifies, every appearance in it is scored, win or loss. Wins are weighted
# by opponent quality (beating elites matters); losses are weighted by
# opponent *weakness* on top of a real floor (losing to a weak opponent is
# more damning than losing to a champion).
#
# 2026-05-15 tuning: SUSTAINED_PEAK_OPP_MAX_WEIGHT 2.0 -> 2.6 and
# PERIOD_TITLE_FIGHT_WEIGHT_MULT 1.25 -> 1.40. Together these push the
# per-fight weight of an elite/title bout well above a mid-tier bout, so a
# GSP-style title-only resume scores above a Silva/Jones-style mixed resume.
SUSTAINED_PEAK_OPP_PIVOT: float = 1500.0
SUSTAINED_PEAK_OPP_MAX_WEIGHT: float = 2.6
PEAK_OPP_WEIGHT_LOGISTIC_CENTER: float = 0.5   # quality level at half-max weight
PEAK_OPP_WEIGHT_LOGISTIC_TEMP: float = 0.22    # gentle S-curve steepness
PERIOD_TITLE_FIGHT_WEIGHT_MULT: float = 1.40   # title bouts weigh more, win or lose
# Information-weighted per-appearance base weights.
PERIOD_WIN_BASE_WEIGHT: float = 0.25     # win weight = WIN_BASE + opp_weight
PERIOD_LOSS_BASE_WEIGHT: float = 0.50    # real floor — every loss counts
PERIOD_LOSS_QUALITY_SCALE: float = 1.0   # extra loss weight = SCALE * (1 - quality_level)
PERIOD_DRAW_BASE_WEIGHT: float = 0.25    # draw treated as a muted win
PERIOD_WIN_BONUS: float = 10.0
PERIOD_DRAW_PENALTY: float = 5.0
PERIOD_LOSS_PENALTY: float = 55.0
# Empirical-Bayes shrinkage of the final window score toward the pooled mean
# of all qualifying fighters, by window sample size (James-Stein). Small-sample
# windows regress to the centre; the shrink constant K is EB-estimated from the
# data. No-op below PERIOD_SCORE_SHRINK_MIN_FIGHTERS qualifying fighters.
PERIOD_SCORE_SHRINK_MIN_FIGHTERS: int = 30
# Raw fight-count activity bonus reduced (it rewarded padding and punished
# efficient short careers like Khabib) but not removed. Resume depth is also
# rewarded through PERIOD_ACTIVITY_BONUS_PER_OPP_WEIGHT (quality of schedule)
# and the headline proven-resume bonus.
PERIOD_ACTIVITY_BONUS_PER_FIGHT: float = 0.5
PERIOD_ACTIVITY_BONUS_PER_OPP_WEIGHT: float = 1.0
PERIOD_ACTIVITY_BONUS_CAP: float = 50.0
PERIOD_TITLE_FIGHT_BONUS: float = 8.0
PERIOD_TITLE_WIN_BONUS: float = 55.0
PERIOD_INTERIM_TITLE_WIN_BONUS: float = 35.0
PERIOD_CHAMPION_WIN_BONUS: float = 35.0
PERIOD_INTERIM_CHAMPION_WIN_BONUS: float = 20.0
PERIOD_TOP5_WIN_BONUS: float = 25.0
PERIOD_TOP10_WIN_BONUS: float = 15.0
PERIOD_TOP15_WIN_BONUS: float = 8.0
PERIOD_P4P_TOP5_WIN_BONUS: float = 25.0
PERIOD_P4P_TOP15_WIN_BONUS: float = 10.0
PERIOD_EXTRA_TITLE_DIVISION_BONUS: float = 30.0

# Title-effective eligibility for all-time windows.
#
# Raw UFC fight count remains the main qualification rule. A title-dense
# career can also qualify once it has a real raw floor and enough effective
# title-ladder work:
#
#   n_eff = n + a*T + b*W_T + c*D_T
#
# where T is title appearances, W_T is title wins, and D_T is successful
# defenses by a fighter who entered the bout as champion/interim champion.
# This admits cases like Alex Pereira's title-dense UFC resume without letting
# two-fight title cameos masquerade as sustained all-time careers.
PERIOD_TITLE_EFFECTIVE_APPEARANCE_CREDIT: float = 0.75
PERIOD_TITLE_EFFECTIVE_WIN_CREDIT: float = 1.00
PERIOD_TITLE_EFFECTIVE_DEFENSE_CREDIT: float = 0.75


# ---------------------------------------------------------------------------
# Division home-class identification and cross-division carry-over.
#
# A fighter's "home" division is where the bulk of their career happened, but a
# permanent move overrides that. The permanence signal is the belt: winning a
# UFC title in a new division (which requires vacating/relinquishing the old
# one) makes the move permanent regardless of how many fights remain on the old
# record. Losing a title challenge up or down a class does NOT relocate a
# fighter. See ratings/division_resume.py:primary_division_rows.
#
# For the divisional resume score, a proven champion who moves up should not
# arrive at the bottom of the new division's pool: their first fight gets a
# small pedigree "bump" carried from their established division, and the score
# then flattens toward their actual in-division performance as they accumulate
# fights (the reliability shrinkage already supplies the flattening curve). The
# carry-over is a bounded fraction of how far the fighter's best-division resume
# sits above the new division's pool mean, so it is a bump — never a full
# legacy loan across weight classes.
DIVISION_CARRYOVER_FRAC: float = 0.30        # share of cross-division pedigree used as prior
DIVISION_CARRYOVER_CAP: float = 40.0         # max mu of carry-over bump into a new division
DIVISION_HOME_RECENCY_HALFLIFE_DAYS: float = 1095.0   # 3-yr half-life for non-champion home pick


# ---------------------------------------------------------------------------
# Integrity penalties (PED, DQ, missed-weight).
#
# 2026-05-15: integrity penalties now apply at the SCORE layer (S_j), not just
# as a per-fight update-weight damp. A PED-confirmed win is treated as a
# barely-above-draw score (~0.55) on both the Glicko-2 method stream and the
# WHR Bayesian smoother — propagated identically through both rating layers
# rather than as a post-hoc shrink. This makes a tainted win a structural,
# rating-level penalty rather than a soft update-magnitude tweak.
#
# The legacy weight-side factors are retained for the audit-only
# integrity_appearances table; the rating arithmetic is driven by the score.
#
# Score floors (applied when the integrity-flagged fighter is the WINNER):
INTEGRITY_PED_WIN_SCORE: float = 0.55       # PED win ~ barely above draw
INTEGRITY_DQ_WIN_SCORE: float = 0.75        # DQ win clearly compromised
INTEGRITY_MISSED_WEIGHT_WIN_SCORE: float = 0.70   # missed weight, won — harsh

# Legacy weight-side factors (audit table only — not the path of penalty
# anymore). Kept so historical comparisons against earlier snapshots still
# parse the same parquet columns. The PED/MW values now match the score-side
# penalties so the audit weight column tells the same directional story.
INTEGRITY_PED_FACTOR: float = SLEEVE_FACTOR_MIN          # -20%, most severe
INTEGRITY_DQ_WIN_FACTOR: float = 0.92                    # -8%
INTEGRITY_MISSED_WEIGHT_WIN_FACTOR: float = 0.88         # -12%


# ---------------------------------------------------------------------------
# Performance sleeve (combined method/dominance + opponent quality + upset +
# streak + weight-class movement).
#
# Architecture (2026-05-14 rewrite):
#
# 1. Each sub-factor contributes a SIGNED log-delta capped at its amplitude.
# 2. Per-fight signal ``S`` is the SUM of contributing log-deltas. Opponent-
#    quality contributors (mu-strength, division-rank context, championship
#    context, P4P context) are deduplicated via ``max`` so a champion who is
#    also top-15 division and top-15 P4P does not triple-count.
# 3. Upset is rank-gated, not continuous: it fires only when
#    ``winner_rank - opponent_rank >= PERF_UPSET_RANK_GAP_THRESHOLD``
#    (champion = rank 0; unranked = rank PERF_UPSET_RANK_UNRANKED_VALUE).
#    A #3 vs #4 matchup does not trigger an upset; an unranked fighter beating
#    the champion does.
# 4. The final weight is a tanh-smoothed mapping into the symmetric envelope:
#       performance_weight_winner = 1 + 0.20 * tanh(S / PERF_TANH_SCALE)
#       performance_weight_loser  = 1 - 0.20 * tanh(S / PERF_TANH_SCALE)
#    Both extremes are now soft saturations, not hard clamps. The same
#    per-fight ``S`` therefore amplifies the winner's gain and damps the
#    loser's hit symmetrically — the "Strickland-Adesanya" anchor produces
#    ~1.20 on Strickland's side and ~0.80 on Adesanya's side.
#
# Anchor calibration (data-confirmed on the 2026-05-13 snapshot):
#   * Strickland def. Adesanya (UFC 293) — Strickland weight ≈ 1.19 (roof);
#     Adesanya weight ≈ 0.81.
#   * Matt Serra def. GSP (UFC 69) — Serra weight ≈ 1.19; GSP weight ≈ 0.81
#     (floor).
# Very few other fights reach either extreme by design.

PERF_DECISIVENESS_AMPLITUDE: float = 0.03

# Method-of-victory tiers used by both METHOD_SCORES (loader) and
# decision_quality_score (performance_adjustment). 2026-05-15 widening:
# decisions now spread 0.85 - 0.97 so split/majority is clearly weaker than
# unanimous, and a 5-round one-sided unanimous decision sits just below a
# finish. The Finish -> Unanimous gap stays modest so opponent quality
# remains the dominant signal.
METHOD_SCORE_FINISH: float = 1.00
METHOD_SCORE_DOMINANT_5RD_UNANIMOUS: float = 0.97   # every judge 50-45 or 49-46
METHOD_SCORE_UNANIMOUS: float = 0.95
METHOD_SCORE_NON_UNANIMOUS_DECISION: float = 0.90   # Majority or Split (3-judge ambiguity)
METHOD_SCORE_DQ: float = 0.85

# Championship-defense outcome floor for the quality-method stream.
#
# Strict canonical Glicko-2 never punishes a win: with S_j = 1 and E_j < 1,
# the score residual is non-negative. The paradox appears only after the
# method/dominance stream replaces S_j with a continuous score below 1.0; a
# narrow title defense can then have S_j < E_j. A successful champion defense
# is therefore floored high enough to keep the direct outcome signal from
# treating "defended the title narrowly" as worse than expected non-performance.
CHAMPIONSHIP_DEFENSE_SCORE_FLOOR: float = 0.990
INTERIM_CHAMPIONSHIP_DEFENSE_SCORE_FLOOR: float = 0.985

# Direct dominance modifier for the quality-method winner score. This is not a
# sleeve weight; it modifies the Glicko score S_j itself before the weighted
# engine update. Only decisions move because finishes already sit at 1.0.
DOMINANCE_SCORE_AMPLITUDE: float = 0.010
DOMINANCE_SCORE_SCALE: float = 2.0

# Opponent-quality (deduplicated via max). Single amplitude across the four
# overlapping signals: opponent mu, division-rank context, championship
# context, P4P context. Each individual ``perf_factor_*`` column still
# captures what that one signal would say, but only the strongest contributes
# to the per-fight signal ``S``.
PERF_OPPONENT_QUALITY_AMPLITUDE: float = 0.16
PERF_OPPONENT_QUALITY_MU_SCALE: float = 900.0
PERF_OPPONENT_STREAK_AMPLITUDE: float = 0.05

# Rank-gated upset (new). The same column also covers a market-odds gate so
# the engine still reads moneyline information when ranking data is sparse,
# but the rank gate is the primary trigger.
PERF_UPSET_AMPLITUDE: float = 0.03
PERF_UPSET_RANK_GAP_THRESHOLD: int = 6
PERF_UPSET_RANK_GAP_SCALE: float = 10.0
PERF_UPSET_RANK_UNRANKED_VALUE: int = 16
PERF_UPSET_RANK_CHAMPION_VALUE: int = 0
PERF_UPSET_RANK_INTERIM_VALUE: int = 1
# Odds-confirmation thresholds — odds only contribute when the rank gate is
# already open. Largest plus-money winner anchors the upset roof.
PERF_UPSET_ODDS_PLUS_MONEY_FLOOR: float = 250.0  # +250 minimum to count
PERF_UPSET_ODDS_PLUS_MONEY_FULL: float = 700.0   # +700 anchors full upset

# Tanh saturation scale. log_S ~= 0.40 maps to weight ~= 1.193; log_S ~= 0.60
# maps to weight ~= 1.199. So only the truly extreme confluences (huge upset,
# dominant finish over the champion, etc.) approach the envelope.
PERF_TANH_SCALE: float = 0.20

# Legacy/audit-only contextual amplitudes — retained for backward-compatible
# per-factor columns in ``performance_appearances.parquet``. They do NOT
# contribute additively to ``S``; the per-fight signal uses the deduplicated
# opponent-quality and rank-gated upset signals above.
RANK_CONTEXT_TOP_N: int = 15
P4P_CONTEXT_TOP_N: int = 15
RANK_CONTEXT_ACTIVE_DAYS: int = 1095  # rankings ignore fighters inactive 3+ years
PERF_RANK_CONTEXT_AMPLITUDE: float = 0.16
PERF_CHAMPIONSHIP_AMPLITUDE: float = 0.16
PERF_P4P_AMPLITUDE: float = 0.14
PERF_WEIGHT_CLASS_UP_WIN_AMPLITUDE: float = 0.05
PERF_WEIGHT_CLASS_DOWN_LOSS_AMPLITUDE: float = 0.05
# Loss while moving up a weight class is damped — the fighter is fighting
# above their natural division so the loss should detract less from the
# main-division resume than a same-class loss would. The damp is applied
# as a winner-loss-side multiplier in [SLEEVE_FACTOR_MIN, 1.0].
PERF_WEIGHT_CLASS_UP_LOSS_DAMP: float = 0.10
PERF_ODDS_POSITIVE_AMPLITUDE: float = 0.15   # audit-only column
PERF_ODDS_NEGATIVE_AMPLITUDE: float = 0.10   # audit-only column

# Activity-aware loss penalty. Debuts are neutral. Once a fighter has a prior
# UFC appearance, a long gap before a loss increases the losing update.
ACTIVITY_GAP_NORMAL: int = 270
ACTIVITY_GAP_FULL_PENALTY: int = 730
ACTIVITY_LOSS_AMPLITUDE: float = 0.12

# Current-ranking inactivity penalty. This is a post-rating current-view
# column, not a mutation of the historical Glicko state. It exists for active
# P4P/rank-camping diagnostics; all-time/period greatness should keep using
# the unpenalized peak surfaces.
ACTIVITY_MU_PENALTY_START_MONTHS: float = 15.0
ACTIVITY_MU_PENALTY_FULL_MONTHS: float = 30.0
ACTIVITY_MU_PENALTY_CAP: float = 75.0


# ---------------------------------------------------------------------------
# Headline proven-resume adjustment.
#
# Raw peak columns are pristine top-N opp-quality means. The headline columns
# add a small bonus per quality-weighted fight inside the best window:
#
#     bonus = clip(HEADLINE_RESUME_RATE * sum(opp_weight in window), 0,
#                  HEADLINE_RESUME_BONUS_CAP)
#     headline_peak = raw_peak + bonus
#
# ``opp_weight`` is in ``[0, 2]`` (sub-prior opponents contribute 0). A long,
# proven, top-of-division resume can lift the headline by up to +50 mu over the
# raw peak; a short or thin resume of just the minimum quality fights lifts by
# very little. Cap keeps the column interpretable as a rating.
HEADLINE_RESUME_RATE: float = 2.0
HEADLINE_RESUME_BONUS_CAP: float = 180.0
HEADLINE_TITLE_APPEARANCE_MASS: float = 2.0
HEADLINE_TITLE_WIN_MASS: float = 3.0
HEADLINE_TITLE_DEFENSE_MASS: float = 2.5


# ---------------------------------------------------------------------------
# Whole-History Rating (WHR) sidecar — see ratings/whr.py.
#
# WHR is a Bayesian *smoother* (Coulom 2008): it estimates every fighter's
# whole rating history jointly, propagating information both directions, so
# ratings are comparable across eras at the rating layer (not as a post-hoc
# patch). It runs as a sidecar stream alongside the Glicko-2 filter.
#
# * WHR_W2_PER_DAY — Wiener-process variance per day on the natural/logistic
#   rating scale. Controls how fast latent skill is allowed to drift. Should
#   ultimately be chosen by predictive backtest (Brier / log-loss); the default
#   is a reasonable MMA prior (~70 Elo of drift std per year).
# * WHR_PRIOR_VAR — weak Gaussian anchor prior variance; pins the global scale.
# * WHR_ITERATIONS — coordinate-ascent passes over all fighters.
# * WHR_STEP_CLIP — per-pass Newton step clamp (natural units) for stability.
WHR_W2_PER_DAY: float = 0.0004
WHR_PRIOR_VAR: float = 4.0
WHR_ITERATIONS: int = 50
WHR_STEP_CLIP: float = 1.5


# ---------------------------------------------------------------------------
# Stream catalogue. Single source of truth for the engine, viz, and database.

CANONICAL_STREAM: str = "canonical"
METHOD_STREAM: str = "method"
METHOD_SLEEVE_STREAMS: tuple[str, ...] = (
    "method_integrity",
    "method_performance",
    "method_integrity_performance",
)
ALL_STREAMS: tuple[str, ...] = (CANONICAL_STREAM, METHOD_STREAM, *METHOD_SLEEVE_STREAMS)
# WHR is a Bayesian smoother stream. The base stream uses binary win/loss
# with no sleeves. Sleeved variants reweight each fight's Bradley-Terry
# likelihood contribution by the sleeve factor — priors are unweighted.
WHR_STREAM: str = "whr"
WHR_INTEGRITY_STREAM: str = "whr_integrity"
WHR_PERFORMANCE_STREAM: str = "whr_performance"
WHR_INTEGRITY_PERFORMANCE_STREAM: str = "whr_integrity_performance"
WHR_SLEEVE_STREAMS: tuple[str, ...] = (
    WHR_INTEGRITY_STREAM,
    WHR_PERFORMANCE_STREAM,
    WHR_INTEGRITY_PERFORMANCE_STREAM,
)
