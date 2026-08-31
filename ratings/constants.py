"""Shared rating and reporting constants.

What these constants do and do not touch, after the 2026-08-20 core evolution:

* The **production WHR rating** uses the staged method score for decided bouts
  and symmetric draw evidence. ``WHR_WINNER_SCORE_COL = None`` restores binary
  W/L/D scoring. Its fit parameters are the WHR drift, prior-mass, and iteration
  constants below; the Glicko stream remains a causal comparison model.
* The **weighted-evidence factors** (``SLEEVE_*``, ``PERF_*``, ``INTEGRITY_*``)
  belong to audit layers and to the research variants in
  ``ratings.research_variants``. They are kept inside a symmetric [-10%, +10%]
  envelope so no single factor can dominate a bout, and they are not applied to
  the public board.
* The **period constants** (``PERIOD_*``, ``HEADLINE_*``) now serve only the
  division resume boards through ``ratings.appearance_context``. The rolling
  opponent-quality peak scores that used most of them were retired: the public
  period views are fixed windows over the WHR trajectory in
  ``ratings.symon_score``, and opponent quality is counted once, inside the
  rating itself.
* **Era normalisation is gone.** A common era offset cancels from every
  within-era Bradley--Terry comparison, so it was never identifiable from bout
  outcomes; the smoother is era-flat by construction.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Symmetric sleeve envelope.

SLEEVE_FACTOR_MIN: float = 0.90   # -10% floor — worst integrity penalty hits this.
SLEEVE_FACTOR_MAX: float = 1.10   # +10% roof — best performance bonus hits this.


# ---------------------------------------------------------------------------
# Period windows.

FIVE_YEAR_PEAK_WINDOW_DAYS: int = 1825  # 5 years
FIVE_YEAR_PEAK_WINDOW_LABEL: str = "5-Yr Period"
FIVE_YEAR_PEAK_MIN_FIGHTS: int = 8
SUSTAINED_PEAK_WINDOW_LABEL: str = "10-Yr Period"
SUSTAINED_PEAK_MIN_FIGHTS: int = 13


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
    "public_legacy_score":                                      "Public Legacy",
    "sustained_peak_headline_mu_canonical":                       "Prime Wins",
    "sustained_peak_headline_mu_method":                          "Prime Finishes",
    "sustained_peak_headline_mu_method_integrity":                "Prime Clean",
    "sustained_peak_headline_mu_method_performance":              "Prime Strength",
    "sustained_peak_headline_mu_method_integrity_performance":    "Prime Complete",
    "sustained_peak_headline_mu_whr":                             "Legacy",
    "sustained_peak_headline_mu_whr_integrity_performance":       "Legacy Complete",
}

# Reverse lookup: short label -> on-disk column.


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
# [0, 1], and mildest exactly where the data is thin or unbridged. Normalization
# is a no-op below ERA_NORM_MIN_POPULATION (keeps small synthetic fixtures on the
# raw scale).
#
# 2026-06-25: cap lowered 0.50 -> 0.20. The raw Glicko scale trends UP over time
# (per-fight mean mu ~1581 in 2002 -> ~1715 in 2025) because the modern field is
# deeper and more skilled — a real era-difficulty premium, not just scale drift.
# The old 0.50 cap erased half of it, dragging modern fighters down and lifting
# one-era pioneers toward parity. At 0.20 we keep ~80% of that premium (so modern
# stays harder, automatically and asymmetrically), and lean on the 10-year Prime
# WINDOW — not era-equalization — to reward greatness sustained across eras.

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
# Division identification (career + current) and cross-division carry-over.
#
# Two divisional labels per fighter, answering different questions:
#   * career_division — where the bulk of the UFC career happened (simple
#     majority of effective fights, recency as tiebreak). Drives single-
#     division leaderboards: when a user filters by Lightweight, a long-tenured
#     LW who just won the WW belt still shows up there. GSP is a career WW
#     despite a one-fight MW cameo; Makhachev is a career LW despite his recent
#     move up; Pereira is a career LHW once UFC fights outnumber MW ones.
#   * current_division — where the fighter competes now. Anchored by the most
#     recent UFC title-fight WIN (winning a belt is the permanent-move signal);
#     otherwise the division of their most recent UFC bout. Losing a title shot
#     up or down a class never relocates a fighter on either label.
# See ratings/division_resume.py:primary_division_rows.
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
INTEGRITY_PED_FACTOR: float = SLEEVE_FACTOR_MIN          # -10%, most severe
INTEGRITY_DQ_WIN_FACTOR: float = 0.96                    # -4%
INTEGRITY_MISSED_WEIGHT_WIN_FACTOR: float = 0.94         # -6%


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
# 4. The final weight is a tanh-smoothed mapping into the symmetric envelope
#    (the half-amplitude is derived from the SLEEVE bounds, now 0.10):
#       performance_weight_winner = 1 + 0.10 * tanh(S / PERF_TANH_SCALE)
#       performance_weight_loser  = 1 - 0.10 * tanh(S / PERF_TANH_SCALE)
#    Both extremes are now soft saturations, not hard clamps. The same
#    per-fight ``S`` therefore amplifies the winner's gain and damps the
#    loser's hit symmetrically — the "Strickland-Adesanya" anchor produces
#    ~1.10 on Strickland's side and ~0.90 on Adesanya's side.
#
# Anchor calibration (relative shape preserved after the 2026-06-25 halving;
# magnitudes are half of the old +/-20% snapshot values):
#   * Strickland def. Adesanya (UFC 293) — Strickland weight ≈ 1.097 (roof);
#     Adesanya weight ≈ 0.903.
#   * Matt Serra def. GSP (UFC 69) — Serra weight ≈ 1.097; GSP weight ≈ 0.903
#     (floor).
# Very few other fights reach either extreme by design.

PERF_DECISIVENESS_AMPLITUDE: float = 0.015

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

# Finish floor for the dominance index (ratings/dominance.py). A KO/TKO or
# Submission win IS a dominant result regardless of accumulated stats, so the
# winner-perspective dominance is floored at this value — in z-sum units, the
# scale of ``dominance_a = z_sig_str + z_sub_att + z_ctrl``. At
# ``WHR_DOMINANCE_SCORE_SCALE = 1.25`` a floor of 2.75 maps to a Legacy
# ``dom_level`` ~0.8. A long one-sided beat-down that also finishes keeps its
# higher raw value (``max(raw, floor)``); a flash KO with few landed strikes is
# lifted to the floor instead of scoring ~0 as it did under the old
# accumulated-totals index. 0 disables the floor.
DOMINANCE_FINISH_FLOOR_Z: float = 2.75

# WHR (Legacy) dominance reward — applied as a LIKELIHOOD WEIGHT, not a score.
# The score channel is capped (decisions clip to [0.975, 1.0], finishes are
# already 1.0), so it has no room to reward how lopsided a win was. WHR instead
# treats a dominant bout as stronger evidence in BOTH directions: each fighter's
# per-fight likelihood weight is multiplied by
# ``1 + WHR_DOMINANCE_WEIGHT_AMPLITUDE * dom_level`` (``dom_level`` in [0, 1]).
# The winner is pushed UP and the blown-out loser pushed DOWN harder, so dominant
# fighters separate from the field instead of the winner merely floating up.
# Ceiling-free (unlike the [0, 1] score), so it rewards dominant FINISHES too — a
# fighter who keeps steam-rolling people climbs the era-comparable Legacy board
# faster even with some losses on the record. 0 disables it.
#
# 2026-06-25 (two-sided rework): loser weight is now amplified too; amplitude
# 0.20 -> 0.30; and the dom_level sigmoid was given its own scale
# WHR_DOMINANCE_SCORE_SCALE, decoupled from the Glicko method-stream score scale
# DOMINANCE_SCORE_SCALE so widening Legacy dominance does not perturb Complete.
# Under the old shared scale 2.0, mean dom_level was ~0.27 and only ~21% of wins
# cleared level 0.5; a lower scale makes more clear wins register as dominant.
WHR_DOMINANCE_WEIGHT_AMPLITUDE: float = 0.30
WHR_DOMINANCE_SCORE_SCALE: float = 1.25

# Opponent-quality (deduplicated via max). Single amplitude across the four
# overlapping signals: opponent mu, division-rank context, championship
# context, P4P context. Each individual ``perf_factor_*`` column still
# captures what that one signal would say, but only the strongest contributes
# to the per-fight signal ``S``.
PERF_OPPONENT_QUALITY_AMPLITUDE: float = 0.08
PERF_OPPONENT_QUALITY_MU_SCALE: float = 900.0
PERF_OPPONENT_STREAK_AMPLITUDE: float = 0.025

# Rank-gated upset (new). The same column also covers a market-odds gate so
# the engine still reads moneyline information when ranking data is sparse,
# but the rank gate is the primary trigger.
PERF_UPSET_AMPLITUDE: float = 0.015
PERF_UPSET_RANK_GAP_THRESHOLD: int = 6
PERF_UPSET_RANK_GAP_SCALE: float = 10.0
PERF_UPSET_RANK_UNRANKED_VALUE: int = 16
PERF_UPSET_RANK_CHAMPION_VALUE: int = 0
PERF_UPSET_RANK_INTERIM_VALUE: int = 1
# Odds-confirmation thresholds — odds only contribute when the rank gate is
# already open. Largest plus-money winner anchors the upset roof.

# Tanh saturation scale, halved with the envelope (2026-06-25) so the saturation
# shape vs the (now halved) signal S is identical to the old +/-20% system.
# log_S ~= 0.20 maps to weight ~= 1.096; log_S ~= 0.30 maps to weight ~= 1.099.
# So only the truly extreme confluences (huge upset, dominant finish over the
# champion, etc.) approach the +/-10% envelope.
PERF_TANH_SCALE: float = 0.10

# Legacy/audit-only contextual amplitudes — retained for backward-compatible
# per-factor columns in ``performance_appearances.parquet``. They do NOT
# contribute additively to ``S``; the per-fight signal uses the deduplicated
# opponent-quality and rank-gated upset signals above.
RANK_CONTEXT_TOP_N: int = 15

# A rank is a position in a field, and this corpus pools every promotion into
# one division, so the fields are not the same size. Median active fighters per
# division, 2015-2025, against what a fixed top-15 window then means:
#
#     Women's Strawweight   37   top 15 = 40% of the field
#     Light Heavyweight     51   top 15 = 30%
#     Heavyweight           53   top 15 = 28%
#     Flyweight             62   top 15 = 24%
#     Middleweight          74   top 15 = 20%
#     Welterweight          78   top 15 = 19%
#     Bantamweight          85   top 15 = 18%
#     Lightweight           94   top 15 = 16%
#     Featherweight        119   top 15 = 13%
#
# Measured consequence on the schedule ledger: a win scored 0.0139 in women's
# strawweight against 0.0034 in featherweight, a factor of **4.1** for the same
# stated achievement, and 32.4% of strawweight wins counted as "ranked" against
# 8.3% of featherweight ones. Per fighter that is Zhang Weili at 0.057 a win and
# Katlyn Cerminara at 0.039 against Robert Whittaker's 0.018 and Sean
# Strickland's 0.0099 -- which is most of why a fighter with no title and no
# measured skill sat inside the published top 100 on schedule alone.
#
# The window is therefore a share of the field. 0.20 is the Middleweight value
# above, i.e. the share the fixed fifteen already implied at the median
# division, so the median division's numbers are left where they were and only
# the small and large fields move.
RANK_CONTEXT_TOP_SHARE: float = 0.20

# Never fewer than this many ranked slots: a genuinely tiny field still has a
# top few, and a share alone would round it to one or zero.
RANK_CONTEXT_MIN_WINDOW: int = 5
P4P_CONTEXT_TOP_N: int = 15
RANK_CONTEXT_ACTIVE_DAYS: int = 1095  # rankings ignore fighters inactive 3+ years
PERF_RANK_CONTEXT_AMPLITUDE: float = 0.08
PERF_CHAMPIONSHIP_AMPLITUDE: float = 0.08
PERF_P4P_AMPLITUDE: float = 0.07
PERF_WEIGHT_CLASS_UP_WIN_AMPLITUDE: float = 0.025
PERF_WEIGHT_CLASS_DOWN_LOSS_AMPLITUDE: float = 0.025
# Loss while moving up a weight class is damped — the fighter is fighting
# above their natural division so the loss should detract less from the
# main-division resume than a same-class loss would. The damp is applied
# as a winner-loss-side multiplier in [SLEEVE_FACTOR_MIN, 1.0].
PERF_WEIGHT_CLASS_UP_LOSS_DAMP: float = 0.05

# Activity-aware loss penalty. Debuts are neutral. Once a fighter has a prior
# UFC appearance, a long gap before a loss increases the losing update.
ACTIVITY_GAP_NORMAL: int = 270
ACTIVITY_GAP_FULL_PENALTY: int = 730
ACTIVITY_LOSS_AMPLITUDE: float = 0.06

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
#   rating scale. Controls how fast latent skill is allowed to drift. The
#   repaired-corpus predictive fit retained 0.0004; 0.0002 was unresolved.
# * WHR_PRIOR_VAR — weak Gaussian anchor prior variance; pins the global scale.
#   The repaired-corpus joint predictive fit selected 8.0 (details below).
# * WHR_ITERATIONS — coordinate-ascent passes over all fighters.
# * WHR_STEP_CLIP — per-pass Newton step clamp (natural units) for stability.
WHR_W2_PER_DAY: float = 0.0004
WHR_PRIOR_VAR: float = 8.0
WHR_ITERATIONS: int = 50
WHR_STEP_CLIP: float = 1.5

# * WHR_VIRTUAL_GAMES — prior evidence, in bouts, that every fighter carries
#   against an average opponent: half a win and half a loss per virtual game.
#
# Without it a fighter who has never lost has no interior maximum-likelihood
# rating: the Bradley--Terry gradient stays positive and only the prior stops
# the climb. When the prior is applied per appearance, its mass grows with
# career length at the same rate as the likelihood, so the stopping point is a
# constant that does not depend on how much evidence exists. Measured on the
# 2026-08-13 snapshot before this term existed: 56 fighters with a single UFC
# win averaged 1646, above the 98th percentile of the roster, and the highest
# rating in the database belonged to a fighter with one bout. Going from 1-0 to
# 10-0 moved the rating only 67 points.
#
# Virtual games are Coulom's remedy in the WHR paper. They are prior evidence of
# fixed size, so real bouts outweigh them as a career accumulates: a 20-0 record
# now rates far above a 1-0 record, which is the behaviour a rating must have.
# The original value 2.0 was selected on a small UFC-only test and was
# unresolved. Refit 2026-08-28 after whole-career corpus repair: 14 rolling
# cutoffs, 8,435 paired bouts / 1,467 events, with temperature learned only on
# earlier folds. The selected joint configuration (prior_var=8, virtual_games=1,
# w2_per_day=0.0004) improved calibrated log loss by 0.00201 versus the former
# 4/2/0.0004 base; paired event-bootstrap 95% CI [0.00060, 0.00349], and AUC
# 0.7041 -> 0.7067. Virtual mass 0.5 was unresolved and prior_var=16 was worse,
# bounding the selected grid. The incremental effect of prior_var=8 after
# virtual_games=1 was unresolved, so do not describe each component as
# independently identified.
WHR_VIRTUAL_GAMES: float = 1.0

# * WHR_WINNER_SCORE_COL — the fractional winner score every published WHR fit
#   uses. ``None`` restores the binary Bradley--Terry outcome.
#
# A finish is a less ambiguous observation of a skill gap than a split decision,
# so the winner is credited 1.00 for a KO/TKO or submission, 0.95 for a
# unanimous decision, 0.90 for a split or majority one and 0.85 for a DQ -- the
# ``method_score_winner`` column as staged, with no free parameter fitted here.
#
# This REVERSES the "method stays out" line in the 2026-08-21 whole-sport plan
# (§ "Explicit non-goal", and the ``Method / dominance`` row of its irredundancy
# matrix), which rested on an earlier research arm that "found no resolved
# benefit". Re-measured 2026-08-28 on the repaired corpus with a proper paired
# gate -- 7 cutoffs, 120-day scoring windows, 2,039 calibrated held-out bouts
# over 371 events, temperature learned only on earlier folds:
#
#   calibrated delta log loss  -0.00332, 95% event bootstrap [-0.00503, -0.00161]
#   AUC                        0.6967 -> 0.7006
#   monotone in the grading:   -0.00092 (quarter), -0.00179 (half), -0.00332
#
# The confound was tested and excluded. A CONSTANT winner score of 0.980 -- the
# same mean, with the method grading removed -- scores +0.00018 [-0.00033,
# +0.00065], i.e. nothing. The gain is method of victory, not uniform outcome
# shrinkage.
#
# What is deliberately NOT taken: sharpening the grading further keeps helping
# (-0.00456 at double spread, -0.00546 at quadruple, both resolved), and it is
# not adopted. That parameter would be fitted on the same held-out set that has
# to serve as the acceptance gate, whereas 1.00/0.95/0.90/0.85 is the staged
# column's own design point and was not chosen here.
#
# Note the sibling arm that FAILED, because it is the reason this is a score and
# not a precision: giving finishes a larger shared bout weight ``omega_b`` is
# significantly worse on decisions at every weight tried (+0.0010 to +0.0049,
# base favoured) while the score route is unresolved there. Method is partial
# credit on the outcome, not extra evidence about the bout.
WHR_WINNER_SCORE_COL: str | None = "method_score_winner"
