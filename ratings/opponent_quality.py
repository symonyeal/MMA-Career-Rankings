"""Shared opponent-quality signals for sleeves and peak windows."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import (
    P4P_CONTEXT_TOP_N,
    PEAK_OPP_WEIGHT_LOGISTIC_CENTER,
    PEAK_OPP_WEIGHT_LOGISTIC_TEMP,
    PERF_CHAMPIONSHIP_AMPLITUDE,
    PERF_OPPONENT_QUALITY_AMPLITUDE,
    PERF_OPPONENT_QUALITY_MU_SCALE,
    PERF_P4P_AMPLITUDE,
    PERF_RANK_CONTEXT_AMPLITUDE,
    RANK_CONTEXT_MIN_WINDOW,
    RANK_CONTEXT_TOP_N,
    RANK_CONTEXT_TOP_SHARE,
    SLEEVE_FACTOR_MAX,
    SLEEVE_FACTOR_MIN,
    SUSTAINED_PEAK_OPP_MAX_WEIGHT,
    SUSTAINED_PEAK_OPP_PIVOT,
)


def _as_float_series(values: object, index: pd.Index | None = None) -> pd.Series:
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce")
    if index is None:
        index = pd.RangeIndex(1)
    return pd.Series(values, index=index, dtype="float64")


def _as_bool_series(values: object, index: pd.Index) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.reindex(index).fillna(False).astype(bool)
    return pd.Series(bool(values), index=index, dtype=bool)


def opponent_mu_quality_level(opponent_mu: object) -> pd.Series:
    """Monotonic 0..1 strength level from opponent pre-fight canonical mu."""
    opp = _as_float_series(opponent_mu).fillna(SUSTAINED_PEAK_OPP_PIVOT)
    level = (opp - SUSTAINED_PEAK_OPP_PIVOT) / max(PERF_OPPONENT_QUALITY_MU_SCALE, 1.0)
    return level.clip(lower=0.0, upper=1.0)


def rank_context_quality_level(
    opponent_rank: object,
    opponent_champion: object | None = None,
    opponent_interim: object | None = None,
    opponent_pool: object | None = None,
) -> pd.Series:
    """0..1 divisional-rank/champion quality level.

    ``opponent_pool`` is the number of fighters that division's rank was read
    off. Given it, the ranked window is :data:`RANK_CONTEXT_TOP_SHARE` of the
    field rather than a fixed fifteen -- see the note above that constant.
    Omit it and the fixed window is used, which is the pre-2026-08-26 behaviour.
    """
    rank = _as_float_series(opponent_rank)
    index = rank.index
    if opponent_pool is None:
        window = pd.Series(float(RANK_CONTEXT_TOP_N), index=index, dtype="float64")
    else:
        pool = _as_float_series(opponent_pool).reindex(index)
        window = (RANK_CONTEXT_TOP_SHARE * pool).round()
        # A field too small to have a meaningful top share still has a top few,
        # and no window may exceed the fixed convention it replaces.
        window = window.clip(lower=float(RANK_CONTEXT_MIN_WINDOW), upper=float(RANK_CONTEXT_TOP_N))
        window = window.fillna(float(RANK_CONTEXT_TOP_N))
    ranked = (rank >= 1) & (rank <= window)
    rank_signal = pd.Series(0.0, index=index, dtype="float64")
    rank_signal.loc[ranked] = (
        (window.loc[ranked] + 1 - rank.loc[ranked]) / window.loc[ranked]
    ).clip(lower=0.0, upper=1.0)
    champ_signal = pd.Series(0.0, index=index, dtype="float64")
    if opponent_interim is not None:
        champ_signal.loc[_as_bool_series(opponent_interim, index)] = 0.85
    if opponent_champion is not None:
        champ_signal.loc[_as_bool_series(opponent_champion, index)] = 1.0
    return pd.Series(
        np.maximum(rank_signal.to_numpy(), champ_signal.to_numpy()),
        index=index,
        dtype="float64",
    )


def championship_quality_level(
    is_title: object,
    is_interim_title: object | None = None,
    opponent_champion: object | None = None,
    opponent_interim: object | None = None,
) -> pd.Series:
    """0..1 title-bout and reigning-titleholder quality level."""
    base = _as_bool_series(is_title, _as_float_series(0.0).index)
    if isinstance(is_title, pd.Series):
        index = is_title.index
        base = _as_bool_series(is_title, index)
    else:
        index = base.index
    signal = pd.Series(0.0, index=index, dtype="float64")
    signal.loc[base] = 0.65
    if is_interim_title is not None:
        signal.loc[_as_bool_series(is_interim_title, index)] = 0.55
    if opponent_interim is not None:
        signal.loc[_as_bool_series(opponent_interim, index)] = np.maximum(
            signal.loc[_as_bool_series(opponent_interim, index)],
            0.80,
        )
    if opponent_champion is not None:
        signal.loc[_as_bool_series(opponent_champion, index)] = 1.0
    return signal


def p4p_quality_level(opponent_p4p_rank: object) -> pd.Series:
    """0..1 pound-for-pound opponent quality level."""
    rank = _as_float_series(opponent_p4p_rank)
    ranked = rank.between(1, P4P_CONTEXT_TOP_N)
    signal = pd.Series(0.0, index=rank.index, dtype="float64")
    signal.loc[ranked] = ((P4P_CONTEXT_TOP_N + 1 - rank.loc[ranked]) / P4P_CONTEXT_TOP_N).clip(
        lower=0.0,
        upper=1.0,
    )
    return signal


def combined_opponent_quality_level(
    *,
    opponent_mu: object,
    opponent_rank: object | None = None,
    opponent_p4p_rank: object | None = None,
    opponent_champion: object | None = None,
    opponent_interim: object | None = None,
    is_title: object | None = None,
    is_interim_title: object | None = None,
) -> pd.Series:
    """Deduplicated 0..1 opponent-quality level shared by peaks and sleeves."""
    mu_level = opponent_mu_quality_level(opponent_mu)
    index = mu_level.index
    parts = [mu_level]
    if opponent_rank is not None:
        parts.append(rank_context_quality_level(opponent_rank, opponent_champion, opponent_interim).reindex(index).fillna(0.0))
    if opponent_p4p_rank is not None:
        parts.append(p4p_quality_level(opponent_p4p_rank).reindex(index).fillna(0.0))
    if is_title is not None:
        parts.append(
            championship_quality_level(
                is_title,
                is_interim_title=is_interim_title,
                opponent_champion=opponent_champion,
                opponent_interim=opponent_interim,
            ).reindex(index).fillna(0.0)
        )
    return pd.concat(parts, axis=1).max(axis=1).clip(lower=0.0, upper=1.0)


def opponent_mu_quality_factor(opponent_mu: object) -> pd.Series:
    factor = 1.0 + PERF_OPPONENT_QUALITY_AMPLITUDE * opponent_mu_quality_level(opponent_mu)
    return factor.clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)


def rank_context_quality_factor(
    opponent_rank: object,
    opponent_champion: object,
    opponent_interim: object,
    opponent_pool: object | None = None,
) -> pd.Series:
    return 1.0 + PERF_RANK_CONTEXT_AMPLITUDE * rank_context_quality_level(
        opponent_rank,
        opponent_champion,
        opponent_interim,
        opponent_pool,
    )


def championship_quality_factor(
    is_title: object,
    is_interim_title: object,
    opponent_champion: object,
    opponent_interim: object,
) -> pd.Series:
    return 1.0 + PERF_CHAMPIONSHIP_AMPLITUDE * championship_quality_level(
        is_title,
        is_interim_title=is_interim_title,
        opponent_champion=opponent_champion,
        opponent_interim=opponent_interim,
    )


def p4p_quality_factor(opponent_p4p_rank: object) -> pd.Series:
    return 1.0 + PERF_P4P_AMPLITUDE * p4p_quality_level(opponent_p4p_rank)


def peak_opponent_weight_from_level(level: object) -> pd.Series:
    """Logistic (Bradley-Terry-shaped) opponent-quality weight for peak windows.

    The quality level in ``[0, 1]`` is mapped through a logistic S-curve,
    rescaled so ``level = 0 -> weight 0`` and ``level = 1 -> MAX_WEIGHT``:

        weight = MAX_WEIGHT
                 * (logistic((level - CENTER)/TEMP) - logistic((0 - CENTER)/TEMP))
                 / (logistic((1 - CENTER)/TEMP) - logistic((0 - CENTER)/TEMP))

    This replaces the old ad-hoc power law with the Bradley-Terry logistic
    shape: weak opponents fade, mid-rank opponents weigh moderately, elite /
    champion opponents weigh near the maximum. Opponent quality is the
    first-priority signal. The title-bout multiplier is applied separately in
    ``ratings.appearance_context.peak_appearance_quality``.
    """
    quality = _as_float_series(level).fillna(0.0).clip(lower=0.0, upper=1.0)

    def _logistic(x: float | pd.Series):
        return 1.0 / (1.0 + np.exp(-(x - PEAK_OPP_WEIGHT_LOGISTIC_CENTER) / PEAK_OPP_WEIGHT_LOGISTIC_TEMP))

    lo = _logistic(0.0)
    hi = _logistic(1.0)
    normalized = (_logistic(quality) - lo) / (hi - lo)
    return normalized.clip(lower=0.0, upper=1.0) * SUSTAINED_PEAK_OPP_MAX_WEIGHT


# A "quality win" is over an opponent who was BOTH highly rated at the time and
# had a tested record of their own. Both halves are load-bearing, and both were
# measured before being adopted.
#
# Rating alone does not work: the top of the rating distribution is populated
# partly by fighters whose own records were built on thin circuits, so screening
# on it flatters exactly the careers it should catch (measured 2026-08-25 --
# Bader and Freire outscored Silva and Aldo "against elite opposition").
#
# Opponent strength with results ignored does not work either: it measures
# gatekeeping, not contention. A fighter who lost to ten elite opponents scores
# the same as one who beat them, and at a 1900 schedule bar Roy Nelson (0-10)
# outranked Khabib and St-Pierre while Jon Jones himself failed a 1950 bar.
# Counting *wins* is what separates a contender from a durable opponent.
MIN_OPPONENT_UFC_BOUTS = 8
# The contender line and the number of wins over it are stated policy, set by
# the project owner on 2026-08-31 after reading the qualifying names at several
# candidate lines. They are not fitted, and no accuracy measure selected them.
CONTENDER_LINE_MU = 1750.0
MIN_QUALITY_WINS = 5
QUALITY_WIN_COLUMNS = ["fighter", "quality_wins", "quality_bouts"]


def quality_win_record(
    appearances: pd.DataFrame,
    *,
    min_opponent_mu: float,
) -> pd.DataFrame:
    """Record in the supplied appearances above ``min_opponent_mu``.

    ``appearances`` must carry ``fighter``, ``is_winner`` and ``opponent_mu``,
    the opponent's rating as at that bout, and must ALREADY be screened to
    opponents with a tested record of their own -- see
    :data:`MIN_OPPONENT_UFC_BOUTS`. The screen is the caller's because it needs
    the corpus, not just the appearance rows.

    When ``fight_url`` is present, repeated ``(fighter, fight_url)`` rows are
    collapsed defensively. Upstream joins must still be validated; this guard
    prevents one physical bout from becoming several wins if a caller misses
    that invariant.

    Both columns are returned because they answer different questions:
    ``quality_wins`` gates the board, and ``quality_bouts`` shows how many times
    the fighter was in that company at all, so a 5-1 and a 5-9 are not printed
    as the same claim.
    """
    if appearances is None or appearances.empty or "fighter" not in appearances.columns:
        return pd.DataFrame(columns=QUALITY_WIN_COLUMNS)
    rated = appearances.dropna(subset=["opponent_mu"])
    if "fight_url" in rated.columns:
        rated = rated.drop_duplicates(["fighter", "fight_url"], keep="first")
    rated = rated[pd.to_numeric(rated["opponent_mu"], errors="coerce") >= float(min_opponent_mu)]
    if rated.empty:
        return pd.DataFrame(columns=QUALITY_WIN_COLUMNS)
    won = _as_bool_series(rated.get("is_winner", False), rated.index)
    out = (
        rated.assign(_won=won.astype(int))
        .groupby("fighter", as_index=False)
        .agg(quality_wins=("_won", "sum"), quality_bouts=("_won", "size"))
    )
    return out[QUALITY_WIN_COLUMNS].reset_index(drop=True)
