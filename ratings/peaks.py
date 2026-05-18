"""Five-year and ten-year historical period metrics.

Two rolling windows are emitted: a 5-year ``five_year_peak`` and a 10-year
``sustained_peak``. (The 2-year career-peak surface is intentionally
discarded — too easy to game with a short hot streak.) Every appearance in a
qualifying window counts: wins, losses, draws, elite opponents, weaker
opponents, and activity volume.

The score is an opponent-quality-weighted mean of post-fight rating with a
small result adjustment, plus a capped activity/resume bonus. The 2026-05-14
Phase-1 rework replaced hand-picked sensitivity constants with data-derived,
reliability-weighted quantities grounded in the rating literature:

* **Era / division normalization** (`_era_division_normalized_mu`). Raw Glicko
  mu inflates over calendar time and spreads differently by division depth.
  Each year's mean shift is shrunk by a James-Stein / empirical-Bayes factor
  and gated by the year's *bridge fraction* (Berry, Reese & Larkey 1999: era
  effects are only identifiable through fighters who span eras). Each
  division's mean/std is empirical-Bayes shrunk toward the global stats. The
  whole correction is capped by an explicit conservatism blend.

* **Opponent-quality weight** (`peak_opponent_weight_from_level`). A logistic
  (Bradley-Terry-shaped) mapping of opponent quality to weight replaces the
  old power law, with an extra multiplier for title bouts — a window of
  title-fight wins over champions outweighs a window of finishes over mid-rank
  opponents. Opponent quality is the first-priority signal.

* **Information-weighted results.** A win is weighted by opponent quality; a
  loss is weighted by opponent *weakness* on top of a real floor (losing to a
  weak opponent is more damning than losing to a champion).

* **Empirical-Bayes score shrinkage** (`_shrink_period_scores`). The final
  window score is James-Stein shrunk toward the pooled mean by its sampling
  reliability — mild for well-sampled windows, firmer for noisy ones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import (
    ERA_NORM_MAX_STRENGTH,
    ERA_NORM_MIN_POPULATION,
    ERA_NORM_STD_FLOOR_FRAC,
    FIVE_YEAR_PEAK_MIN_FIGHTS,
    FIVE_YEAR_PEAK_TITLE_EFFECTIVE_MIN_RAW_FIGHTS,
    FIVE_YEAR_PEAK_WINDOW_DAYS,
    HEADLINE_RESUME_BONUS_CAP,
    HEADLINE_RESUME_RATE,
    HEADLINE_TITLE_APPEARANCE_MASS,
    HEADLINE_TITLE_DEFENSE_MASS,
    HEADLINE_TITLE_WIN_MASS,
    PERIOD_ACTIVITY_BONUS_CAP,
    PERIOD_ACTIVITY_BONUS_PER_FIGHT,
    PERIOD_ACTIVITY_BONUS_PER_OPP_WEIGHT,
    PERIOD_CHAMPION_WIN_BONUS,
    PERIOD_DRAW_BASE_WEIGHT,
    PERIOD_DRAW_PENALTY,
    PERIOD_EXTRA_TITLE_DIVISION_BONUS,
    PERIOD_INTERIM_CHAMPION_WIN_BONUS,
    PERIOD_INTERIM_TITLE_WIN_BONUS,
    PERIOD_LOSS_BASE_WEIGHT,
    PERIOD_LOSS_PENALTY,
    PERIOD_LOSS_QUALITY_SCALE,
    PERIOD_P4P_TOP15_WIN_BONUS,
    PERIOD_P4P_TOP5_WIN_BONUS,
    PERIOD_SCORE_SHRINK_MIN_FIGHTERS,
    PERIOD_TITLE_FIGHT_BONUS,
    PERIOD_TITLE_FIGHT_WEIGHT_MULT,
    PERIOD_TITLE_WIN_BONUS,
    PERIOD_TITLE_EFFECTIVE_APPEARANCE_CREDIT,
    PERIOD_TITLE_EFFECTIVE_DEFENSE_CREDIT,
    PERIOD_TITLE_EFFECTIVE_WIN_CREDIT,
    PERIOD_TOP10_WIN_BONUS,
    PERIOD_TOP15_WIN_BONUS,
    PERIOD_TOP5_WIN_BONUS,
    PERIOD_WIN_BASE_WEIGHT,
    PERIOD_WIN_BONUS,
    SUSTAINED_PEAK_TITLE_EFFECTIVE_MIN_RAW_FIGHTS,
    SUSTAINED_PEAK_MIN_FIGHTS,
    SUSTAINED_PEAK_WINDOW_DAYS,
)
from ratings.opponent_quality import (
    combined_opponent_quality_level,
    peak_opponent_weight_from_level,
)
from ratings.performance_adjustment import (
    DIVISION_WEIGHT_LIMIT_LB,
    normalize_division_label,
    prefight_ranking_context,
)


PEAK_APPEARANCE_COLUMNS = [
    "fight_url",
    "event_date",
    "event_name",
    "fighter",
    "opponent",
    "opponent_prefight_mu",
    "opponent_quality_level",
    "opp_weight",
    "actual_score",
    "opponent_prefight_division_rank",
    "opponent_prefight_p4p_rank",
    "opponent_entered_as_champion",
    "opponent_entered_as_interim_champion",
    "fighter_entered_as_champion",
    "fighter_entered_as_interim_champion",
    "is_championship_bout",
    "is_interim_title_bout",
    "division",
    "division_weight_limit_lb",
]


def _prefight_mu_table(canonical_history: pd.DataFrame) -> pd.DataFrame:
    if canonical_history is None or canonical_history.empty:
        return pd.DataFrame(columns=["fighter", "event_date", "event_name", "prefight_mu"])
    h = canonical_history[["fighter", "event_date", "event_name", "mu_canonical"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h = h.sort_values(["fighter", "event_date", "event_name"]).reset_index(drop=True)
    h["prefight_mu"] = h.groupby("fighter")["mu_canonical"].shift(1).fillna(1500.0)
    return h[["fighter", "event_date", "event_name", "prefight_mu"]]


def peak_appearance_quality(
    canonical_fights: pd.DataFrame,
    canonical_history: pd.DataFrame,
) -> pd.DataFrame:
    """Return one opponent-quality row per actual fighter appearance."""
    if canonical_fights is None or canonical_fights.empty:
        return pd.DataFrame(columns=PEAK_APPEARANCE_COLUMNS)

    f = canonical_fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    context = prefight_ranking_context(f, canonical_history)
    f = f.merge(context, on="fight_url", how="left")
    f["division"] = f.get("weight_class", pd.Series(index=f.index)).map(normalize_division_label)
    f["division_weight_limit_lb"] = f["division"].map(DIVISION_WEIGHT_LIMIT_LB)

    prior = _prefight_mu_table(canonical_history)
    prior_a = prior.rename(columns={"fighter": "fighter_a", "prefight_mu": "prefight_mu_a"})
    prior_b = prior.rename(columns={"fighter": "fighter_b", "prefight_mu": "prefight_mu_b"})
    f = f.merge(prior_a, on=["fighter_a", "event_date", "event_name"], how="left")
    f = f.merge(prior_b, on=["fighter_b", "event_date", "event_name"], how="left")
    for col in ("prefight_mu_a", "prefight_mu_b"):
        f[col] = pd.to_numeric(f[col], errors="coerce").fillna(1500.0)

    common = [
        "fight_url",
        "event_date",
        "event_name",
        "fighter_a",
        "fighter_b",
        "winner",
        "is_draw",
        "is_championship_bout",
        "is_interim_title_bout",
        "division",
        "division_weight_limit_lb",
    ]
    a = f[common + [
        "prefight_mu_b",
        "fighter_b_prefight_division_rank",
        "fighter_b_prefight_p4p_rank",
        "fighter_b_entered_as_champion",
        "fighter_b_entered_as_interim_champion",
        "fighter_a_entered_as_champion",
        "fighter_a_entered_as_interim_champion",
    ]].rename(columns={
        "fighter_a": "fighter",
        "fighter_b": "opponent",
        "prefight_mu_b": "opponent_prefight_mu",
        "fighter_b_prefight_division_rank": "opponent_prefight_division_rank",
        "fighter_b_prefight_p4p_rank": "opponent_prefight_p4p_rank",
        "fighter_b_entered_as_champion": "opponent_entered_as_champion",
        "fighter_b_entered_as_interim_champion": "opponent_entered_as_interim_champion",
        "fighter_a_entered_as_champion": "fighter_entered_as_champion",
        "fighter_a_entered_as_interim_champion": "fighter_entered_as_interim_champion",
    })
    b = f[common + [
        "prefight_mu_a",
        "fighter_a_prefight_division_rank",
        "fighter_a_prefight_p4p_rank",
        "fighter_a_entered_as_champion",
        "fighter_a_entered_as_interim_champion",
        "fighter_b_entered_as_champion",
        "fighter_b_entered_as_interim_champion",
    ]].rename(columns={
        "fighter_b": "fighter",
        "fighter_a": "opponent",
        "prefight_mu_a": "opponent_prefight_mu",
        "fighter_a_prefight_division_rank": "opponent_prefight_division_rank",
        "fighter_a_prefight_p4p_rank": "opponent_prefight_p4p_rank",
        "fighter_a_entered_as_champion": "opponent_entered_as_champion",
        "fighter_a_entered_as_interim_champion": "opponent_entered_as_interim_champion",
        "fighter_b_entered_as_champion": "fighter_entered_as_champion",
        "fighter_b_entered_as_interim_champion": "fighter_entered_as_interim_champion",
    })
    out = pd.concat([a, b], ignore_index=True, sort=False)
    out["opponent_quality_level"] = combined_opponent_quality_level(
        opponent_mu=out["opponent_prefight_mu"],
        opponent_rank=out["opponent_prefight_division_rank"],
        opponent_p4p_rank=out["opponent_prefight_p4p_rank"],
        opponent_champion=out["opponent_entered_as_champion"],
        opponent_interim=out["opponent_entered_as_interim_champion"],
        is_title=out["is_championship_bout"],
        is_interim_title=out["is_interim_title_bout"],
    )
    out["opp_weight"] = peak_opponent_weight_from_level(out["opponent_quality_level"])
    # Title bouts weigh more in the window mean — win or lose. Opponent quality
    # is the first-priority signal and a title fight is the clearest marker of
    # it (a GSP title-fight decision outweighs a finish over a mid-ranker).
    title_bout = (
        out["is_championship_bout"].fillna(False).astype(bool)
        | out["is_interim_title_bout"].fillna(False).astype(bool)
    )
    out.loc[title_bout, "opp_weight"] = (
        out.loc[title_bout, "opp_weight"] * PERIOD_TITLE_FIGHT_WEIGHT_MULT
    )
    out["actual_score"] = np.select(
        [
            out["is_draw"].fillna(False).astype(bool),
            out["winner"].eq(out["fighter"]),
        ],
        [0.5, 1.0],
        default=0.0,
    )
    return out[PEAK_APPEARANCE_COLUMNS].copy()


def _result_adjustment(actual_score: pd.Series) -> pd.Series:
    score = pd.to_numeric(actual_score, errors="coerce").fillna(0.0)
    return pd.Series(
        np.select(
            [score >= 1.0, score == 0.5],
            [PERIOD_WIN_BONUS, -PERIOD_DRAW_PENALTY],
            default=-PERIOD_LOSS_PENALTY,
        ),
        index=score.index,
        dtype="float64",
    )


def _context_adjustment(window: pd.DataFrame) -> pd.Series:
    """Per-fight win-context bonus — the single strongest "who you beat" signal.

    The title-win, champion-win, divisional-rank and P4P-rank bonuses all
    describe the same underlying fact: *you won against elite opposition*.
    They are therefore DEDUPLICATED VIA ``max`` — only the strongest applicable
    bonus contributes, not their sum. Previously they were summed, so a title
    win over a top-5 / P4P-top-5 reigning champion stacked
    ``8 + 55 + 35 + 25 + 25 = 148`` mu of bonus on a single fight; that
    multiple-counting floated title-reign-then-decline resumes (Benson
    Henderson, Chris Weidman). The ``max`` matches how
    ``combined_opponent_quality_level`` and the performance sleeve already
    handle overlapping opponent-quality signals.

    Title-fight *participation* (``PERIOD_TITLE_FIGHT_BONUS``) stays a small
    separate additive term — it applies win OR lose, so it is not part of the
    win-context dedup group.
    """
    score = pd.to_numeric(window["actual_score"], errors="coerce").fillna(0.0)
    won = score >= 1.0
    title = window["is_championship_bout"].fillna(False).astype(bool)
    interim_title = window["is_interim_title_bout"].fillna(False).astype(bool)
    opp_champ = window["opponent_entered_as_champion"].fillna(False).astype(bool)
    opp_interim = window["opponent_entered_as_interim_champion"].fillna(False).astype(bool)
    opp_rank = pd.to_numeric(window["opponent_prefight_division_rank"], errors="coerce")
    opp_p4p = pd.to_numeric(window["opponent_prefight_p4p_rank"], errors="coerce")

    idx = window.index
    components: list[pd.Series] = []

    def _component(mask: pd.Series, value: float) -> None:
        s = pd.Series(0.0, index=idx, dtype="float64")
        s.loc[mask] = value
        components.append(s)

    _component(won & title, PERIOD_TITLE_WIN_BONUS)
    _component(won & interim_title, PERIOD_INTERIM_TITLE_WIN_BONUS)
    _component(won & opp_champ, PERIOD_CHAMPION_WIN_BONUS)
    _component(won & opp_interim, PERIOD_INTERIM_CHAMPION_WIN_BONUS)
    _component(won & opp_rank.between(1, 5), PERIOD_TOP5_WIN_BONUS)
    _component(won & opp_rank.between(6, 10), PERIOD_TOP10_WIN_BONUS)
    _component(won & opp_rank.between(11, 15), PERIOD_TOP15_WIN_BONUS)
    _component(won & opp_p4p.between(1, 5), PERIOD_P4P_TOP5_WIN_BONUS)
    _component(won & opp_p4p.between(6, 15), PERIOD_P4P_TOP15_WIN_BONUS)

    # Deduplicated: the single strongest applicable win-context bonus.
    win_context = (
        pd.concat(components, axis=1).max(axis=1)
        if components
        else pd.Series(0.0, index=idx, dtype="float64")
    )
    # Title-fight participation — small, separate, applies win or lose.
    participation = pd.Series(0.0, index=idx, dtype="float64")
    participation.loc[title] = PERIOD_TITLE_FIGHT_BONUS
    return win_context + participation


def _activity_bonus(window: pd.DataFrame, min_fights: int) -> float:
    appearances_over_min = max(0, len(window) - min_fights)
    opp_weight_sum = float(pd.to_numeric(window["opp_weight"], errors="coerce").fillna(0.0).sum())
    raw = (
        PERIOD_ACTIVITY_BONUS_PER_FIGHT * appearances_over_min
        + PERIOD_ACTIVITY_BONUS_PER_OPP_WEIGHT * opp_weight_sum
    )
    return float(np.clip(raw, 0.0, PERIOD_ACTIVITY_BONUS_CAP))


def _title_ladder_parts(window: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return title-appearance, title-win, and title-defense masks."""
    idx = window.index
    title = (
        window.get("is_championship_bout", pd.Series(False, index=idx)).fillna(False).astype(bool)
        | window.get("is_interim_title_bout", pd.Series(False, index=idx)).fillna(False).astype(bool)
    )
    won = pd.to_numeric(
        window.get("actual_score", pd.Series(0.0, index=idx)),
        errors="coerce",
    ).fillna(0.0).ge(1.0)
    entered_champ = (
        window.get("fighter_entered_as_champion", pd.Series(False, index=idx)).fillna(False).astype(bool)
        | window.get("fighter_entered_as_interim_champion", pd.Series(False, index=idx)).fillna(False).astype(bool)
    )
    defense = title & won & entered_champ
    return title, title & won, defense


def _title_effective_count(window: pd.DataFrame) -> float:
    """Raw fights plus effective championship-ladder work."""
    title, title_win, defense = _title_ladder_parts(window)
    return float(
        len(window)
        + PERIOD_TITLE_EFFECTIVE_APPEARANCE_CREDIT * int(title.sum())
        + PERIOD_TITLE_EFFECTIVE_WIN_CREDIT * int(title_win.sum())
        + PERIOD_TITLE_EFFECTIVE_DEFENSE_CREDIT * int(defense.sum())
    )


def _title_ladder_mass(window: pd.DataFrame) -> float:
    """Headline resume mass contributed by championship-ladder appearances."""
    title, title_win, defense = _title_ladder_parts(window)
    return float(
        HEADLINE_TITLE_APPEARANCE_MASS * int(title.sum())
        + HEADLINE_TITLE_WIN_MASS * int(title_win.sum())
        + HEADLINE_TITLE_DEFENSE_MASS * int(defense.sum())
    )


def _qualifies_window(window: pd.DataFrame, min_fights: int, title_effective_min_raw_fights: int) -> bool:
    if len(window) >= min_fights:
        return True
    if len(window) < title_effective_min_raw_fights:
        return False
    return _title_effective_count(window) >= float(min_fights)


def _multi_division_title_bonus(window: pd.DataFrame) -> float:
    title_wins = window[
        window["is_championship_bout"].fillna(False).astype(bool)
        & pd.to_numeric(window["actual_score"], errors="coerce").fillna(0.0).ge(1.0)
    ].copy()
    if title_wins.empty:
        return 0.0
    divisions = title_wins["division"].dropna().nunique()
    return float(max(0, divisions - 1) * PERIOD_EXTRA_TITLE_DIVISION_BONUS)


def _empirical_bayes_factor(
    cell_means: pd.Series,
    cell_sampling_var: pd.Series,
) -> tuple[float, float]:
    """Method-of-moments empirical-Bayes variance components.

    Given one row per cell (era/division) with the cell mean and the sampling
    variance of that mean, returns ``(tau2, _)`` where ``tau2`` is the
    estimated true between-cell variance: ``tau2 = max(0, var(means) -
    mean(sampling_var))``. The James-Stein shrinkage factor for a cell is then
    ``tau2 / (tau2 + sampling_var_cell)``.
    """
    means = pd.to_numeric(cell_means, errors="coerce").dropna()
    sv = pd.to_numeric(cell_sampling_var, errors="coerce").dropna()
    if len(means) < 2:
        return 0.0, 0.0
    tau2 = float(means.var(ddof=0)) - float(sv.mean()) if len(sv) else float(means.var(ddof=0))
    return max(0.0, tau2), 0.0


def _era_division_normalized_mu(merged: pd.DataFrame, mu_col: str) -> pd.Series:
    """Reliability-weighted era-de-trend + division-depth rescale of ``mu_col``.

    Raw Glicko mu drifts upward over calendar time (the rated pool inflates)
    and spreads differently by division depth. This returns a Series (aligned
    to ``merged.index``) correcting both, but the *strength* of every part of
    the correction is data-derived rather than a hand-picked constant:

    1. **Era de-trend.** Each calendar year's mean shift away from the global
       mean is shrunk by a James-Stein / empirical-Bayes factor
       ``tau2 / (tau2 + sampling_var)`` (``tau2`` = estimated true between-year
       variance), then gated by the year's *bridge fraction* — the share of
       that year's fighters who also fought in another year. Per Berry, Reese
       & Larkey (1999), era effects are only identifiable through fighters who
       span eras, so an unbridged year gets little era correction.
    2. **Division-depth rescale.** Each division's mean/std on the de-trended
       scale is shrunk toward the global mean/std by the same empirical-Bayes
       factor, so thin divisions are not over-corrected.

    The reference scale is the snapshot's own global mean/std (self-calibrated:
    an average-era / average-division fighter is unchanged). The whole
    correction is finally capped by blending at most ``ERA_NORM_MAX_STRENGTH``
    of the way toward the normalized value — the single explicit conservatism
    prior; every other factor above is estimated from the data. Below
    ``ERA_NORM_MIN_POPULATION`` rows the raw ``mu_col`` is returned untouched.
    """
    mu = pd.to_numeric(merged[mu_col], errors="coerce")
    if int(mu.notna().sum()) < ERA_NORM_MIN_POPULATION:
        return mu

    global_mean = float(mu.mean())
    global_var = float(mu.var(ddof=0))
    global_std = float(np.sqrt(global_var))
    if not np.isfinite(global_std) or global_std <= 0.0:
        return mu

    year = pd.to_datetime(merged["event_date"], errors="coerce").dt.year
    division = merged["division"] if "division" in merged.columns else None
    if division is None:
        division = pd.Series("unknown", index=merged.index)
    division = division.fillna("unknown").astype(str)
    fighter = (
        merged["fighter"]
        if "fighter" in merged.columns
        else pd.Series(range(len(merged)), index=merged.index)
    )
    work = pd.DataFrame(
        {"mu": mu, "year": year, "division": division, "fighter": fighter}
    )

    # --- 1. Era de-trend: empirical-Bayes shrunk, bridge-gated year shifts ---
    yr = work.groupby("year")["mu"]
    yr_n = yr.transform("count").clip(lower=1.0)
    yr_mean = yr.transform("mean")
    yr_var = yr.transform("var").fillna(global_var)
    raw_shift = yr_mean - global_mean
    se2_year = yr_var / yr_n                       # sampling variance of the year mean
    per_year = (
        work.assign(shift=raw_shift, se2=se2_year)
        .groupby("year")[["shift", "se2"]]
        .first()
    )
    tau2_year, _ = _empirical_bayes_factor(per_year["shift"], per_year["se2"])
    eb_year = (
        tau2_year / (tau2_year + se2_year)
        if tau2_year > 0.0
        else pd.Series(0.0, index=work.index)
    )
    # Bridge fraction: share of the year's fighters who also fought another year.
    fighter_years = work.groupby("fighter")["year"].transform("nunique")
    is_bridge = (fighter_years > 1).astype(float)
    bridge_frac = work.assign(_b=is_bridge).groupby("year")["_b"].transform("mean")
    work["mu_detr"] = work["mu"] - raw_shift * eb_year * bridge_frac

    # --- 2. Division-depth rescale: empirical-Bayes shrunk ---
    dv = work.groupby("division")["mu_detr"]
    dv_n = dv.transform("count").clip(lower=1.0)
    dv_mean = dv.transform("mean").fillna(global_mean)
    dv_var = dv.transform("var").fillna(global_var)
    dv_std = np.sqrt(dv_var)
    se2_div = dv_var / dv_n
    per_div = (
        work.assign(_se2=se2_div)
        .groupby("division")
        .agg(mean=("mu_detr", "mean"), se2=("_se2", "first"))
    )
    tau2_div, _ = _empirical_bayes_factor(per_div["mean"], per_div["se2"])
    eb_div = (
        tau2_div / (tau2_div + se2_div)
        if tau2_div > 0.0
        else pd.Series(0.0, index=work.index)
    )
    div_mean_eff = global_mean + (dv_mean - global_mean) * eb_div
    div_std_eff = (global_std + (dv_std - global_std) * eb_div).clip(
        lower=ERA_NORM_STD_FLOOR_FRAC * global_std
    )

    z = (work["mu_detr"] - div_mean_eff) / div_std_eff
    normalized = global_mean + global_std * z
    # Single explicit conservatism prior: blend at most ERA_NORM_MAX_STRENGTH
    # of the way toward the normalized value. Everything above is data-derived.
    blended = (1.0 - ERA_NORM_MAX_STRENGTH) * mu + ERA_NORM_MAX_STRENGTH * normalized
    return blended.where(mu.notna(), mu)


def _per_fighter_window_period(
    group: pd.DataFrame,
    *,
    mu_col: str,
    window_days: int,
    min_fights: int,
    title_effective_min_raw_fights: int,
    optimize_for_headline: bool = False,
) -> tuple[float, float, float, int, float, float]:
    """Best all-appearance opponent-quality period score for one fighter.

    Returns ``(score, window_opp_weight_sum, title_ladder_mass, window_n,
    effective_n, window_var)``:
    ``window_opp_weight_sum`` is the total opponent-quality weight in the best
    window and ``title_ladder_mass`` is the title-specific resume mass. These
    feed the headline proven-resume bonus. ``window_n`` is raw fight count,
    ``effective_n`` is title-effective count, and ``window_var`` is the
    weighted variance of adjusted mu inside it.
    """
    g = group.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    if g.empty:
        return float("nan"), float("nan"), float("nan"), 0, float("nan"), float("nan")

    dates = g["event_date"].to_numpy()
    best = float("nan")
    best_selection_score = float("nan")
    best_window_weight_sum = float("nan")
    best_title_ladder_mass = float("nan")
    best_window_n = 0
    best_effective_n = float("nan")
    best_window_var = float("nan")
    window_ns = np.timedelta64(window_days, "D")
    for j in range(len(g)):
        end_date = dates[j]
        start_date = end_date - window_ns
        i = j
        while i > 0 and dates[i - 1] >= start_date:
            i -= 1
        window = g.iloc[i : j + 1].copy()
        if not _qualifies_window(window, min_fights, title_effective_min_raw_fights):
            continue

        # Information-weighted appearance weights. A win is weighted by
        # opponent quality (beating elites matters); a draw is a muted win; a
        # loss is weighted by opponent *weakness* on top of a real floor —
        # losing to a weak opponent is more damning than losing to a champion.
        # Opponent quality is the first-priority signal.
        score_arr = (
            pd.to_numeric(window["actual_score"], errors="coerce").fillna(0.0).to_numpy()
        )
        opp_w = pd.to_numeric(window["opp_weight"], errors="coerce").fillna(0.0).to_numpy()
        level = (
            pd.to_numeric(window["opponent_quality_level"], errors="coerce")
            .fillna(0.0)
            .clip(0.0, 1.0)
            .to_numpy()
        )
        is_win = score_arr >= 1.0
        is_draw = (score_arr > 0.0) & (score_arr < 1.0)
        weights_arr = np.where(
            is_win,
            PERIOD_WIN_BASE_WEIGHT + opp_w,
            np.where(
                is_draw,
                PERIOD_DRAW_BASE_WEIGHT + 0.5 * opp_w,
                PERIOD_LOSS_BASE_WEIGHT + PERIOD_LOSS_QUALITY_SCALE * (1.0 - level),
            ),
        )
        weights = pd.Series(weights_arr, index=window.index)
        mu = pd.to_numeric(window[mu_col], errors="coerce")
        adjusted_mu = (
            mu
            + _result_adjustment(window["actual_score"])
            + _context_adjustment(window)
        )
        valid = weights.gt(0) & adjusted_mu.notna()
        w_sum = float(weights.loc[valid].sum())
        if w_sum <= 0:
            continue
        wv = weights.loc[valid]
        am = adjusted_mu.loc[valid]
        w_mean = float((wv * am).sum() / w_sum)
        score = w_mean
        score += _activity_bonus(window, min_fights)
        score += _multi_division_title_bonus(window)
        window_weights = pd.to_numeric(window["opp_weight"], errors="coerce").fillna(0.0)
        window_weight_sum = float(window_weights.sum())
        title_ladder_mass = _title_ladder_mass(window)
        selection_score = score
        if optimize_for_headline:
            selection_score += _resume_bonus(window_weight_sum, title_ladder_mass)
        if np.isnan(best_selection_score) or selection_score > best_selection_score:
            best = score
            best_selection_score = selection_score
            best_window_weight_sum = window_weight_sum
            best_title_ladder_mass = title_ladder_mass
            best_window_n = int(len(window))
            best_effective_n = _title_effective_count(window)
            # Weighted variance of adjusted mu — feeds the EB score shrinkage.
            best_window_var = float((wv * (am - w_mean) ** 2).sum() / w_sum)
    return best, best_window_weight_sum, best_title_ladder_mass, best_window_n, best_effective_n, best_window_var


def _resume_bonus(window_opp_weight_sum: float, title_ladder_mass: float = 0.0) -> float:
    """Headline proven-resume bonus with title-ladder mass, capped at cap."""
    if window_opp_weight_sum is None or np.isnan(window_opp_weight_sum):
        return float("nan")
    ladder = 0.0 if title_ladder_mass is None or np.isnan(title_ladder_mass) else float(title_ladder_mass)
    raw = HEADLINE_RESUME_RATE * (float(window_opp_weight_sum) + ladder)
    return float(np.clip(raw, 0.0, HEADLINE_RESUME_BONUS_CAP))


def _shrink_period_scores(
    scores: pd.Series,
    sizes: pd.Series,
    within_vars: pd.Series,
) -> pd.Series:
    """Empirical-Bayes (James-Stein) shrinkage of window scores to the pool mean.

    Each fighter's window score is shrunk toward the pooled mean of all
    qualifying fighters by ``w_i = tau2 / (tau2 + sigma2_i)``, where
    ``sigma2_i = within_window_var_i / window_n_i`` is the sampling variance
    of that fighter's window mean and ``tau2`` (true between-fighter variance)
    is estimated by method of moments. Because a 13+-fight window is mostly
    signal, ``w_i`` sits near 1.0 — the shrinkage is mild by construction and
    only meaningfully pulls in genuinely noisy small windows. No-op below
    ``PERIOD_SCORE_SHRINK_MIN_FIGHTERS`` qualifying fighters.
    """
    valid = scores.notna() & sizes.notna() & within_vars.notna() & (sizes > 0)
    if int(valid.sum()) < PERIOD_SCORE_SHRINK_MIN_FIGHTERS:
        return scores
    s = scores[valid].astype(float)
    n = sizes[valid].astype(float)
    wv = within_vars[valid].astype(float)
    pooled = float(s.mean())
    sigma2 = wv / n
    total_var = float(((s - pooled) ** 2).mean())
    tau2 = total_var - float(sigma2.mean())
    if not np.isfinite(tau2) or tau2 <= 0.0:
        return scores
    w = tau2 / (tau2 + sigma2)
    out = scores.copy()
    out.loc[valid] = pooled + (s - pooled) * w
    return out


def rolling_peak(
    history: pd.DataFrame,
    canonical_history: pd.DataFrame,
    canonical_fights: pd.DataFrame,
    *,
    mu_col: str,
    out_col: str,
    window_days: int,
    min_fights: int,
    title_effective_min_raw_fights: int,
    appearance_quality: pd.DataFrame | None = None,
    headline_col: str | None = None,
) -> pd.DataFrame:
    """Opponent-quality rolling period score for ``mu_col``.

    Emits the raw ``out_col`` and, when ``headline_col`` is supplied, a
    proven-resume-adjusted column ``out_col_headline`` = raw + bonus, where
    bonus = clip(rate * sum_opp_weight_in_best_window, 0, cap).
    """
    out_columns = ["fighter", out_col] + ([headline_col] if headline_col else [])
    if history is None or history.empty or mu_col not in history.columns:
        return pd.DataFrame(columns=out_columns)

    h = history[["fighter", "event_date", "event_name", mu_col]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h = h.dropna(subset=["fighter", "event_date", "event_name", mu_col])
    if h.empty:
        return pd.DataFrame(columns=out_columns)

    quality = (
        appearance_quality
        if appearance_quality is not None
        else peak_appearance_quality(canonical_fights, canonical_history)
    )
    merged = h.merge(
        quality[[
            "fighter",
            "event_date",
            "event_name",
            "opponent_prefight_mu",
            "opp_weight",
            "opponent_quality_level",
            "actual_score",
            "opponent_prefight_division_rank",
            "opponent_prefight_p4p_rank",
            "opponent_entered_as_champion",
            "opponent_entered_as_interim_champion",
            "fighter_entered_as_champion",
            "fighter_entered_as_interim_champion",
            "is_championship_bout",
            "is_interim_title_bout",
            "division",
            "division_weight_limit_lb",
        ]],
        on=["fighter", "event_date", "event_name"],
        how="left",
    )
    merged["opponent_prefight_mu"] = pd.to_numeric(
        merged["opponent_prefight_mu"], errors="coerce"
    ).fillna(1500.0)
    merged["opp_weight"] = pd.to_numeric(merged["opp_weight"], errors="coerce").fillna(0.0)
    merged["opponent_quality_level"] = pd.to_numeric(
        merged["opponent_quality_level"], errors="coerce"
    ).fillna(0.0)
    merged["actual_score"] = pd.to_numeric(merged["actual_score"], errors="coerce").fillna(0.0)

    # Era-de-trend + division-depth rescale before scoring, so windows are
    # comparable across eras and divisions.
    merged["mu_period_normalized"] = _era_division_normalized_mu(merged, mu_col)

    rows = []
    for fighter, group in merged.groupby("fighter", sort=False):
        (
            score,
            window_weight_sum,
            title_ladder_mass,
            window_n,
            effective_n,
            window_var,
        ) = _per_fighter_window_period(
            group,
            mu_col="mu_period_normalized",
            window_days=window_days,
            min_fights=min_fights,
            title_effective_min_raw_fights=title_effective_min_raw_fights,
            optimize_for_headline=headline_col is not None,
        )
        rows.append({
            "fighter": fighter,
            "_score": score,
            "_wsum": window_weight_sum,
            "_title_ladder_mass": title_ladder_mass,
            "_n": window_n,
            "_effective_n": effective_n,
            "_var": window_var,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=out_columns)

    # Empirical-Bayes shrinkage of the window score toward the pooled mean.
    df[out_col] = _shrink_period_scores(df["_score"], df["_n"], df["_var"])
    if headline_col:
        bonus = [
            _resume_bonus(wsum, ladder)
            for wsum, ladder in zip(df["_wsum"], df["_title_ladder_mass"])
        ]
        df[headline_col] = np.where(
            df[out_col].isna(), np.nan, df[out_col] + bonus
        )
    return df[out_columns]


def five_year_peak(
    history: pd.DataFrame,
    canonical_history: pd.DataFrame,
    canonical_fights: pd.DataFrame,
    *,
    mu_col: str,
    out_col: str,
    appearance_quality: pd.DataFrame | None = None,
    headline_col: str | None = None,
) -> pd.DataFrame:
    """Best 5-year opponent-quality rolling peak (min 7 UFC fights)."""
    return rolling_peak(
        history,
        canonical_history,
        canonical_fights,
        mu_col=mu_col,
        out_col=out_col,
        window_days=FIVE_YEAR_PEAK_WINDOW_DAYS,
        min_fights=FIVE_YEAR_PEAK_MIN_FIGHTS,
        title_effective_min_raw_fights=FIVE_YEAR_PEAK_TITLE_EFFECTIVE_MIN_RAW_FIGHTS,
        appearance_quality=appearance_quality,
        headline_col=headline_col,
    )


def sustained_peak(
    history: pd.DataFrame,
    canonical_history: pd.DataFrame,
    canonical_fights: pd.DataFrame,
    *,
    mu_col: str,
    out_col: str,
    appearance_quality: pd.DataFrame | None = None,
    headline_col: str | None = None,
) -> pd.DataFrame:
    """Best 10-year opponent-quality rolling peak (min 10 UFC fights)."""
    return rolling_peak(
        history,
        canonical_history,
        canonical_fights,
        mu_col=mu_col,
        out_col=out_col,
        window_days=SUSTAINED_PEAK_WINDOW_DAYS,
        min_fights=SUSTAINED_PEAK_MIN_FIGHTS,
        title_effective_min_raw_fights=SUSTAINED_PEAK_TITLE_EFFECTIVE_MIN_RAW_FIGHTS,
        appearance_quality=appearance_quality,
        headline_col=headline_col,
    )
