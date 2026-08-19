"""Performance sleeve: how impressive was this result vs expectation.

The performance sleeve operates on the **method** rating stream only. The
canonical stream is never performance-aware.

Architecture (2026-05-14 rewrite — see ``MODEL_ISSUES_AND_DIAGNOSIS.md``
Issue 8 for the saturation diagnosis that motivated this):

* Each sub-factor produces a multiplicative ``perf_factor_*`` column for
  audit transparency, but the per-fight signal ``S`` is computed via an
  additive deduplication that prevents the same opponent-quality information
  from triple-counting. Specifically, opponent-mu, division-rank context,
  championship context and P4P context all measure "how elite was the
  opponent"; only the strongest single signal contributes to ``S``.
* Upset is now **rank-gated**: it fires only when the winner is at least
  ``PERF_UPSET_RANK_GAP_THRESHOLD`` rank slots below the opponent (champion
  counts as rank 0, unranked as rank 16). A #3-vs-#4 fight is not an upset;
  an unranked challenger beating the champion is.
* The combination step is a **tanh saturation** rather than a hard clamp. The
  half-amplitude is ``_ENVELOPE_HALF = (SLEEVE_FACTOR_MAX-SLEEVE_FACTOR_MIN)/2``
  (0.10 since the 2026-06-25 +/-10% tightening):
  ``performance_weight_winner = 1 + 0.10·tanh(S/PERF_TANH_SCALE)`` and
  ``performance_weight_loser  = 1 - 0.10·tanh(S/PERF_TANH_SCALE)``. The same
  per-fight ``S`` therefore amplifies the winner's gain and damps the
  loser's hit symmetrically — when Strickland upset Adesanya (UFC 293) his
  weight lands near 1.097 and Adesanya's near 0.903. When Matt Serra TKO'd
  GSP (UFC 69) Serra lands near 1.097 and GSP near 0.903.

Audit columns:

* ``perf_factor_decisiveness``
* ``perf_factor_opponent_strength``, ``perf_factor_rank_context``,
  ``perf_factor_championship``, ``perf_factor_p4p``
* ``perf_factor_opponent_streak``
* ``perf_factor_weight_class``, ``perf_factor_activity_loss``

New columns:

* ``perf_factor_upset`` — the rank-gated upset multiplier (winner side).
* ``perf_signal_S`` — the additive log-signal that feeds the tanh mapping.
* ``perf_winner_signal_S`` — the winner-side ``S`` propagated to the loser
  row so audits can see why the loser's weight moved.

Draws stay at 1.0 on both sides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from project_helpers import normalize_name_key
from ratings.constants import (
    ACTIVITY_GAP_FULL_PENALTY,
    ACTIVITY_GAP_NORMAL,
    ACTIVITY_LOSS_AMPLITUDE,
    CHAMPIONSHIP_DEFENSE_SCORE_FLOOR,
    DOMINANCE_SCORE_AMPLITUDE,
    DOMINANCE_SCORE_SCALE,
    INTEGRITY_DQ_WIN_SCORE,
    INTEGRITY_MISSED_WEIGHT_WIN_SCORE,
    INTEGRITY_PED_WIN_SCORE,
    INTERIM_CHAMPIONSHIP_DEFENSE_SCORE_FLOOR,
    METHOD_SCORE_DOMINANT_5RD_UNANIMOUS,
    METHOD_SCORE_DQ,
    METHOD_SCORE_FINISH,
    METHOD_SCORE_NON_UNANIMOUS_DECISION,
    METHOD_SCORE_UNANIMOUS,
    PERF_DECISIVENESS_AMPLITUDE,
    PERF_OPPONENT_QUALITY_AMPLITUDE,
    PERF_OPPONENT_STREAK_AMPLITUDE,
    PERF_CHAMPIONSHIP_AMPLITUDE,
    PERF_P4P_AMPLITUDE,
    PERF_RANK_CONTEXT_AMPLITUDE,
    PERF_TANH_SCALE,
    PERF_UPSET_AMPLITUDE,
    PERF_UPSET_RANK_CHAMPION_VALUE,
    PERF_UPSET_RANK_GAP_SCALE,
    PERF_UPSET_RANK_GAP_THRESHOLD,
    PERF_UPSET_RANK_INTERIM_VALUE,
    PERF_UPSET_RANK_UNRANKED_VALUE,
    PERF_WEIGHT_CLASS_DOWN_LOSS_AMPLITUDE,
    PERF_WEIGHT_CLASS_UP_LOSS_DAMP,
    PERF_WEIGHT_CLASS_UP_WIN_AMPLITUDE,
    P4P_CONTEXT_TOP_N,
    RANK_CONTEXT_ACTIVE_DAYS,
    RANK_CONTEXT_TOP_N,
    SLEEVE_FACTOR_MAX,
    SLEEVE_FACTOR_MIN,
)
from ratings.opponent_quality import (
    championship_quality_factor,
    opponent_mu_quality_factor,
    p4p_quality_factor,
    rank_context_quality_factor,
)


# Symmetric envelope around 1.0 (the tanh saturation half-amplitude).
_ENVELOPE_HALF: float = (SLEEVE_FACTOR_MAX - SLEEVE_FACTOR_MIN) / 2.0  # = 0.20


_SCORE_RE = re.compile(r"\b(\d{2})\s*-\s*(\d{2})\b")
_ROUND_RE = re.compile(r"(\d+)\s*Rnd", re.IGNORECASE)


PERFORMANCE_APPEARANCE_COLUMNS = (
    "fight_url",
    "event_date",
    "event_name",
    "fighter",
    "opponent",
    "division",
    "is_draw",
    "is_winner",
    "actual_score",
    "quality_score_winner",
    "dominance_score_winner",
    "method_class",
    "scheduled_rounds",
    "end_round",
    "end_time_seconds",
    "bout_duration_seconds",
    "decisiveness_score",
    "performance_weight",
    "perf_factor_decisiveness",
    "perf_factor_opponent_strength",
    "perf_factor_opponent_streak",
    "perf_factor_rank_context",
    "perf_factor_championship",
    "perf_factor_p4p",
    "perf_factor_upset",
    "perf_factor_weight_class",
    "perf_factor_activity_loss",
    "perf_signal_S",
    "perf_winner_signal_S",
    "perf_upset_rank_gap",
    "activity_gap_days",
    "activity_layoff_level",
    "fighter_previous_division",
    "fighter_previous_weight_limit_lb",
    "fighter_current_weight_limit_lb",
    "fighter_weight_class_move",
    "fighter_weight_class_change_fight",
    "fighter_prefight_division_rank",
    "opponent_prefight_division_rank",
    "fighter_prefight_p4p_rank",
    "opponent_prefight_p4p_rank",
    "fighter_entered_as_champion",
    "opponent_entered_as_champion",
    "fighter_entered_as_interim_champion",
    "opponent_entered_as_interim_champion",
    "is_championship_bout",
    "is_interim_title_bout",
    "market_residual",
    "market_american_odds",
)


DIVISION_LABELS = (
    "Women's Strawweight",
    "Women's Flyweight",
    "Women's Bantamweight",
    "Women's Featherweight",
    "Light Heavyweight",
    "Heavyweight",
    "Middleweight",
    "Welterweight",
    "Lightweight",
    "Featherweight",
    "Bantamweight",
    "Flyweight",
    "Catch Weight",
    "Open Weight",
)

DIVISION_WEIGHT_LIMIT_LB = {
    "Women's Strawweight": 115,
    "Women's Flyweight": 125,
    "Women's Bantamweight": 135,
    "Women's Featherweight": 145,
    "Flyweight": 125,
    "Bantamweight": 135,
    "Featherweight": 145,
    "Lightweight": 155,
    "Welterweight": 170,
    "Middleweight": 185,
    "Light Heavyweight": 205,
    "Heavyweight": 265,
}


# ---------------------------------------------------------------------------
# Parsing helpers (pure, unit-testable)


def parse_judge_scores(details_text: object) -> list[tuple[int, int]]:
    """Extract ``(a_score, b_score)`` tuples from a Greco details string."""
    if not isinstance(details_text, str):
        return []
    return [(int(a), int(b)) for a, b in _SCORE_RE.findall(details_text)]


def scheduled_rounds(time_format: object) -> int:
    """Number of scheduled rounds. Defaults to 3 for safety."""
    if not isinstance(time_format, str):
        return 3
    match = _ROUND_RE.search(time_format)
    return max(1, int(match.group(1))) if match else 3


def normalize_division_label(weight_class: object) -> str | None:
    """Normalize UFCStats weight-class text to a stable division label."""
    if not isinstance(weight_class, str):
        return None
    text = " ".join(weight_class.split())
    cleaned = (
        text.replace("UFC ", "")
        .replace("Interim ", "")
        .replace(" Title Bout", "")
        .replace(" Bout", "")
        .strip()
    )
    for label in DIVISION_LABELS:
        if label.lower() in cleaned.lower():
            return label
    return cleaned or None


def is_real_ufc_title_bout(weight_class: object) -> bool:
    """True only for UFC undisputed/interim title bouts.

    UFCStats labels TUF and Road-to-UFC tournament finals as "Title Bout".
    Those are not divisional UFC championship fights and must not update title
    lineage, champion defenses, or title-ladder resume credit.
    """
    if not isinstance(weight_class, str):
        return False
    text = " ".join(weight_class.split()).lower()
    normalized = text.replace("titlebout", "title bout")
    if "title bout" not in normalized:
        return False
    if "ultimate fighter" in normalized or "road to ufc" in normalized:
        return False
    if "tuf nations" in normalized or "tournament" in normalized:
        return False
    return normalized.startswith("ufc ")


def is_championship_bout(row: pd.Series) -> bool:
    return is_real_ufc_title_bout(row.get("weight_class"))


def is_interim_title_bout(weight_class: object) -> bool:
    return is_real_ufc_title_bout(weight_class) and "interim" in str(weight_class).lower()


def fight_duration_seconds(row: pd.Series) -> float:
    end_round = pd.to_numeric(row.get("end_round"), errors="coerce")
    end_seconds = pd.to_numeric(row.get("end_time_seconds"), errors="coerce")
    if pd.isna(end_round) or pd.isna(end_seconds):
        return np.nan
    duration = (max(float(end_round), 1.0) - 1.0) * 300.0 + float(end_seconds)
    return duration if duration > 0 else np.nan


def decision_quality_score(row: pd.Series) -> float:
    """Map judge-scorecard dominance to the [0.85, 0.97] decision band.

    Returned as the bout's continuous winner score for the method /
    method_performance stream when method_class starts with "Decision".

    Tiers (chosen 2026-05-15):
      - Non-unanimous (Split or Majority): 0.90 flat. One judge disagreed,
        the result is structurally ambiguous regardless of average margin.
      - Unanimous, 5-round, every judge cards a full sweep (50-45) or
        near-sweep (49-46): 0.97. A dominant title-fight unanimous win.
      - Unanimous otherwise: 0.95.
    """
    method = row.get("method_class")
    if not isinstance(method, str):
        return METHOD_SCORE_UNANIMOUS
    if method.startswith("Decision - Split") or method.startswith("Decision - Majority"):
        return METHOD_SCORE_NON_UNANIMOUS_DECISION
    if not method.startswith("Decision - Unanimous"):
        return METHOD_SCORE_UNANIMOUS

    sched = scheduled_rounds(row.get("time_format"))
    scores = parse_judge_scores(row.get("details_text"))
    winner = row.get("winner")
    if not scores or sched < 5:
        return METHOD_SCORE_UNANIMOUS
    if winner == row.get("fighter_a"):
        margins = [a - b for a, b in scores]
    elif winner == row.get("fighter_b"):
        margins = [b - a for a, b in scores]
    else:
        return METHOD_SCORE_UNANIMOUS

    # Dominant 5-round unanimous: every judge cards a near-sweep, meaning the
    # winner lost at most one round on each card. On a 5-round bout this is a
    # points margin of at least 3 (50-45 = full sweep margin 5; 49-46 = lost
    # one round, margin 3). This is the "championship sweep" tier - strictly
    # above a normal unanimous decision (e.g. 48-47 across the board).
    if all(margin >= 3 for margin in margins):
        return METHOD_SCORE_DOMINANT_5RD_UNANIMOUS
    return METHOD_SCORE_UNANIMOUS


def _apply_integrity_score_damp(row: pd.Series, base_score: float) -> float:
    """Floor the winner score when the winner has an integrity flag on the bout.

    PED-confirmed win -> INTEGRITY_PED_WIN_SCORE (~0.55, barely above draw).
    Missed-weight win -> INTEGRITY_MISSED_WEIGHT_WIN_SCORE (0.70).
    DQ win            -> INTEGRITY_DQ_WIN_SCORE (0.75).
    Multiple flags take the harshest (lowest) floor.
    """
    winner = row.get("winner")
    if winner is None or pd.isna(winner):
        return float(base_score)
    score = float(base_score)
    if bool(row.get("ped_confirmed", False)) and row.get("ped_flagged_fighter") == winner:
        score = min(score, INTEGRITY_PED_WIN_SCORE)
    if bool(row.get("missed_weight", False)) and row.get("missed_weight_fighter") == winner:
        score = min(score, INTEGRITY_MISSED_WEIGHT_WIN_SCORE)
    if bool(row.get("is_dq", False)) and row.get("dq_winner") == winner:
        score = min(score, INTEGRITY_DQ_WIN_SCORE)
    return score


def quality_score_winner(row: pd.Series) -> float | None:
    """Continuous method-style winner score used by the method stream.

    Integrity penalty applies at this layer (2026-05-15): a PED-confirmed,
    DQ, or missed-weight win is downgraded to a structural floor score
    here, so the rating-level evidence is downgraded identically on both
    the Glicko-2 method stream and the WHR Bayesian smoother.
    """
    if bool(row.get("is_draw", False)):
        return None
    method = row.get("method_class")
    method = "" if method is None or pd.isna(method) else str(method)
    if method.startswith("Decision"):
        base_score = decision_quality_score(row)
    elif method == "KO/TKO" or method == "Submission":
        base_score = METHOD_SCORE_FINISH
    elif method == "DQ":
        base_score = METHOD_SCORE_DQ
    else:
        fallback = row.get("method_score_winner")
        base_score = METHOD_SCORE_FINISH if fallback is None or pd.isna(fallback) else float(fallback)
    return _apply_integrity_score_damp(row, base_score)


def _dominance_score_bonus(dominance_winner: pd.Series) -> pd.Series:
    """Positive-only dominance bonus for direct winner score S_j.

    The dominance term is intentionally not a sleeve factor. It modifies the
    continuous score fed into Glicko-2's ``S_j`` for decisions; finishes are
    already full-score wins.
    """
    dom = pd.to_numeric(dominance_winner, errors="coerce")
    level = 1.0 / (1.0 + np.exp(-dom.fillna(0.0) / max(DOMINANCE_SCORE_SCALE, 1e-9)))
    return DOMINANCE_SCORE_AMPLITUDE * (2.0 * level - 1.0).clip(lower=0.0, upper=1.0)


def _attach_dominance_score(
    fights: pd.DataFrame,
    fight_dominance: pd.DataFrame | None,
) -> pd.DataFrame:
    out = fights.copy()
    out["dominance_score_winner"] = pd.NA
    if fight_dominance is None or fight_dominance.empty or "dominance_a" not in fight_dominance.columns:
        return out
    dom = fight_dominance[["fight_url", "dominance_a"]].copy()
    out = out.merge(dom, on="fight_url", how="left")
    winner_is_a = out["winner"].eq(out["fighter_a"])
    winner_is_b = out["winner"].eq(out["fighter_b"])
    out["dominance_score_winner"] = np.select(
        [winner_is_a, winner_is_b],
        [
            pd.to_numeric(out["dominance_a"], errors="coerce"),
            -pd.to_numeric(out["dominance_a"], errors="coerce"),
        ],
        default=np.nan,
    )
    decision = out.get("method_class", pd.Series("", index=out.index)).astype(str).str.startswith("Decision")
    score = pd.to_numeric(out["quality_score_winner"], errors="coerce")
    bonus = _dominance_score_bonus(out["dominance_score_winner"])
    out.loc[decision & score.notna(), "quality_score_winner"] = (
        score.loc[decision & score.notna()] + bonus.loc[decision & score.notna()]
    ).clip(lower=0.975, upper=1.0)
    return out.drop(columns=["dominance_a"], errors="ignore")


def _apply_championship_defense_floor(fights: pd.DataFrame) -> pd.DataFrame:
    out = fights.copy()
    score = pd.to_numeric(out["quality_score_winner"], errors="coerce")
    title = out["is_championship_bout"].fillna(False).astype(bool)
    interim_title = out["is_interim_title_bout"].fillna(False).astype(bool)
    winner_a = out["winner"].eq(out["fighter_a"])
    winner_b = out["winner"].eq(out["fighter_b"])
    winner_entered_champ = (
        (winner_a & out["fighter_a_entered_as_champion"].fillna(False).astype(bool))
        | (winner_b & out["fighter_b_entered_as_champion"].fillna(False).astype(bool))
    )
    winner_entered_interim = (
        (winner_a & out["fighter_a_entered_as_interim_champion"].fillna(False).astype(bool))
        | (winner_b & out["fighter_b_entered_as_interim_champion"].fillna(False).astype(bool))
    )
    undisputed_defense = title & winner_entered_champ & score.notna()
    interim_defense = interim_title & winner_entered_interim & score.notna()
    out.loc[undisputed_defense, "quality_score_winner"] = np.maximum(
        score.loc[undisputed_defense],
        CHAMPIONSHIP_DEFENSE_SCORE_FLOOR,
    )
    out.loc[interim_defense, "quality_score_winner"] = np.maximum(
        pd.to_numeric(out.loc[interim_defense, "quality_score_winner"], errors="coerce"),
        INTERIM_CHAMPIONSHIP_DEFENSE_SCORE_FLOOR,
    )
    return out


# ---------------------------------------------------------------------------
# Pre-fight rating shifts (drives opponent-strength factor)


def prefight_ratings(history: pd.DataFrame) -> pd.DataFrame:
    """Per-(fighter, event) pre-event ``mu`` snapshot from ``ratings_history``."""
    if history is None or history.empty:
        return pd.DataFrame(columns=["fighter", "event_date", "event_name", "prefight_mu"])
    h = history[["fighter", "event_date", "event_name", "mu_canonical"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h = h.sort_values(["fighter", "event_date", "event_name"])
    h["prefight_mu"] = h.groupby("fighter")["mu_canonical"].shift(1).fillna(1500.0)
    return h[["fighter", "event_date", "event_name", "prefight_mu"]]


def pre_fight_win_streaks(fights: pd.DataFrame) -> pd.DataFrame:
    """Each fighter's UFC win streak entering each bout (no leak within event)."""
    if fights is None or fights.empty:
        return pd.DataFrame(columns=["fight_url", "streak_a", "streak_b"])
    f = fights[["fight_url", "event_date", "event_name", "fighter_a", "fighter_b", "winner", "is_draw"]].copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f = f.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    names = pd.unique(pd.concat([f["fighter_a"], f["fighter_b"]], ignore_index=True).dropna())
    fighter_id = {name: i for i, name in enumerate(names)}
    id_a = f["fighter_a"].map(fighter_id).fillna(-1).to_numpy(dtype=np.int64)
    id_b = f["fighter_b"].map(fighter_id).fillna(-1).to_numpy(dtype=np.int64)
    a_won = f["winner"].eq(f["fighter_a"]).to_numpy()
    b_won = f["winner"].eq(f["fighter_b"]).to_numpy()
    drawn = f["is_draw"].fillna(False).astype(bool).to_numpy() if "is_draw" in f.columns else np.zeros(len(f), dtype=bool)

    streaks = np.zeros(len(names) + 1, dtype=np.int64)  # index -1 parks unnamed sides
    streak_a = np.zeros(len(f), dtype=np.int64)
    streak_b = np.zeros(len(f), dtype=np.int64)

    # Streaks are read for the whole card before any of it is applied, so two
    # bouts on one event cannot leak into each other.
    for lo, hi in zip(*_group_bounds(f["event_date"], f["event_name"])):
        rows = slice(lo, hi)
        streak_a[rows] = streaks[id_a[rows]]
        streak_b[rows] = streaks[id_b[rows]]
        for k in range(lo, hi):
            a, b = id_a[k], id_b[k]
            if drawn[k]:
                streaks[a] = streaks[b] = 0
            elif a_won[k]:
                streaks[a] += 1
                streaks[b] = 0
            elif b_won[k]:
                streaks[b] += 1
                streaks[a] = 0
            else:
                streaks[a] = streaks[b] = 0

    return pd.DataFrame({
        "fight_url": f["fight_url"].to_numpy(),
        "streak_a": streak_a,
        "streak_b": streak_b,
    })


def _group_bounds(*keys: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Half-open row ranges of each run of equal key tuples in an already-sorted frame.

    The equivalent of ``groupby(sort=False)`` over a frame that is already
    ordered by those keys, without materializing a group object per event.
    """
    n = len(keys[0])
    if n == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    changed = np.zeros(n - 1, dtype=bool)
    for key in keys:
        values = key.to_numpy()
        changed |= values[1:] != values[:-1]
    boundary = np.flatnonzero(changed) + 1
    starts = np.concatenate(([0], boundary))
    stops = np.concatenate((boundary, [n]))
    return starts, stops


def _empty_prefight_context() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "fight_url",
        "division",
        "is_championship_bout",
        "is_interim_title_bout",
        "fighter_a_prefight_division_rank",
        "fighter_b_prefight_division_rank",
        "fighter_a_prefight_p4p_rank",
        "fighter_b_prefight_p4p_rank",
        "fighter_a_entered_as_champion",
        "fighter_b_entered_as_champion",
        "fighter_a_entered_as_interim_champion",
        "fighter_b_entered_as_interim_champion",
    ])


def prefight_ranking_context(canonical_fights: pd.DataFrame, ratings_history: pd.DataFrame) -> pd.DataFrame:
    """Pre-fight model rank, P4P, and title-lineage context per bout.

    This does not use current FightMatrix/UFC ranks for historical fights
    because that would leak future information. Until official date-stamped
    UFC ranking snapshots are loaded, the historical proxy is pre-event
    canonical rating rank: top-15 in the current division, top-15 P4P, plus
    championship holders inferred from prior UFC title fights.
    """
    if canonical_fights is None or canonical_fights.empty:
        return _empty_prefight_context()

    f = canonical_fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["division"] = f.get("weight_class", pd.Series(index=f.index)).map(normalize_division_label)
    weight_class = f.get("weight_class", pd.Series(index=f.index))
    f["is_championship_bout"] = weight_class.map(is_real_ufc_title_bout)
    f["is_interim_title_bout"] = weight_class.map(is_interim_title_bout)
    f = f.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    if ratings_history is None or ratings_history.empty or "mu_canonical" not in ratings_history.columns:
        neutral = f[["fight_url", "division", "is_championship_bout", "is_interim_title_bout"]].copy()
        for col in [
            "fighter_a_prefight_division_rank",
            "fighter_b_prefight_division_rank",
            "fighter_a_prefight_p4p_rank",
            "fighter_b_prefight_p4p_rank",
        ]:
            neutral[col] = pd.NA
        for col in [
            "fighter_a_entered_as_champion",
            "fighter_b_entered_as_champion",
            "fighter_a_entered_as_interim_champion",
            "fighter_b_entered_as_interim_champion",
        ]:
            neutral[col] = False
        return neutral

    # Post-event mu per bout side, joined once rather than rebuilt per event.
    # A fighter twice on one card keeps the later row, matching the dict-build
    # this replaces.
    h = ratings_history[["fighter", "event_date", "event_name", "mu_canonical"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h["mu_canonical"] = pd.to_numeric(h["mu_canonical"], errors="coerce")
    h = h.drop_duplicates(["fighter", "event_date", "event_name"], keep="last")
    for side in ("a", "b"):
        f = f.merge(
            h.rename(columns={"fighter": f"fighter_{side}", "mu_canonical": f"_post_mu_{side}"}),
            on=[f"fighter_{side}", "event_date", "event_name"],
            how="left",
        )

    # Fighter ids are assigned in sorted-name order, so the rank tie-break
    # ``(-mu, name)`` becomes a numeric lexsort on ``(-mu, id)``.
    names = pd.unique(pd.concat([f["fighter_a"], f["fighter_b"]], ignore_index=True).dropna())
    order_by_name = sorted(str(n) for n in names)
    fighter_id = {name: i for i, name in enumerate(order_by_name)}
    n_fighters = len(order_by_name)

    def _ids(series: pd.Series) -> np.ndarray:
        return series.map(fighter_id).fillna(-1).to_numpy(dtype=np.int64)

    id_a = _ids(f["fighter_a"])
    id_b = _ids(f["fighter_b"])
    divisions = f["division"].to_numpy()
    division_code, division_values = pd.factorize(f["division"], use_na_sentinel=True)
    is_title = f["is_championship_bout"].fillna(False).astype(bool).to_numpy()
    is_interim = f["is_interim_title_bout"].fillna(False).astype(bool).to_numpy()
    winner_id = _ids(f["winner"]) if "winner" in f.columns else np.full(len(f), -1, dtype=np.int64)
    # The row loop this replaces guarded with ``if not winner``, which skips
    # None and "" but NOT NaN — so a drawn title bout falls through and writes
    # a champion nobody matches, vacating the modeled lineage. That is why
    # Edgar does not enter UFC 136 flagged as champion. Preserved deliberately;
    # see the 2026-08-18 report for why it is a defect worth deciding on
    # separately rather than silently fixing inside a performance change.
    winner_values = (
        f["winner"].to_numpy() if "winner" in f.columns else np.full(len(f), None, dtype=object)
    )
    winner_falsy = np.array(
        [w is None or (isinstance(w, str) and not w) for w in winner_values], dtype=bool
    )
    post_mu_a = pd.to_numeric(f["_post_mu_a"], errors="coerce").to_numpy(dtype=float)
    post_mu_b = pd.to_numeric(f["_post_mu_b"], errors="coerce").to_numpy(dtype=float)
    event_days = (f["event_date"] - pd.Timestamp(0)).dt.days.to_numpy(dtype=np.int64)

    state_mu = np.full(n_fighters, np.nan)
    state_last_day = np.full(n_fighters, np.iinfo(np.int64).min, dtype=np.int64)
    state_division = np.full(n_fighters, -1, dtype=np.int64)
    # Champion lineage is per division and only ever touched by title bouts.
    champions: dict[int, int] = {}
    interim_champions: dict[int, int] = {}

    n = len(f)
    div_rank_a = np.full(n, np.nan)
    div_rank_b = np.full(n, np.nan)
    p4p_rank_a = np.full(n, np.nan)
    p4p_rank_b = np.full(n, np.nan)
    champ_a = np.zeros(n, dtype=bool)
    champ_b = np.zeros(n, dtype=bool)
    interim_champ_a = np.zeros(n, dtype=bool)
    interim_champ_b = np.zeros(n, dtype=bool)

    event_starts, event_stops = _group_bounds(f["event_date"], f["event_name"])
    for lo, hi in zip(event_starts, event_stops):
        cutoff_day = event_days[lo] - RANK_CONTEXT_ACTIVE_DAYS
        active = np.flatnonzero(state_last_day >= cutoff_day)
        if active.size:
            # Global P4P order, then division order read off the same sweep.
            order = active[np.lexsort((active, -state_mu[active]))]
            p4p = np.full(n_fighters, np.nan)
            p4p[order] = np.arange(1, order.size + 1, dtype=float)

            div_of_order = state_division[order]
            by_div = np.argsort(div_of_order, kind="stable")
            grouped = div_of_order[by_div]
            starts = np.flatnonzero(np.concatenate(([True], grouped[1:] != grouped[:-1])))
            sizes = np.diff(np.concatenate((starts, [grouped.size])))
            within = np.arange(grouped.size) - np.repeat(starts, sizes)
            div_rank = np.full(n_fighters, np.nan)
            div_rank[order[by_div]] = within + 1.0
            # A fighter whose recorded division is unknown is in no division board.
            div_rank[order[div_of_order < 0]] = np.nan
        else:
            p4p = np.full(n_fighters, np.nan)
            div_rank = np.full(n_fighters, np.nan)

        rows = slice(lo, hi)
        ra, rb = id_a[rows], id_b[rows]
        p4p_rank_a[rows] = np.where(ra >= 0, p4p[ra], np.nan)
        p4p_rank_b[rows] = np.where(rb >= 0, p4p[rb], np.nan)
        # A bout only carries a divisional rank when the bout's own division
        # matches the division the fighter is currently ranked in.
        same_div_a = (ra >= 0) & (state_division[ra] == division_code[rows]) & (division_code[rows] >= 0)
        same_div_b = (rb >= 0) & (state_division[rb] == division_code[rows]) & (division_code[rows] >= 0)
        div_rank_a[rows] = np.where(same_div_a, div_rank[ra], np.nan)
        div_rank_b[rows] = np.where(same_div_b, div_rank[rb], np.nan)

        for k in range(lo, hi):
            d = division_code[k]
            if d < 0:
                continue
            champ_a[k] = champions.get(d, -1) == id_a[k]
            champ_b[k] = champions.get(d, -1) == id_b[k]
            interim_champ_a[k] = interim_champions.get(d, -1) == id_a[k]
            interim_champ_b[k] = interim_champions.get(d, -1) == id_b[k]

        # Advance title lineage after all pre-fight context for the event is
        # captured, so same-card title bouts cannot leak into each other.
        for k in range(lo, hi):
            d = division_code[k]
            if winner_falsy[k] or d < 0 or not is_title[k]:
                continue
            # A NaN winner lands here as -1, which matches no fighter id — the
            # vacating behaviour described above.
            if is_interim[k]:
                interim_champions[d] = winner_id[k]
            else:
                champions[d] = winner_id[k]
                interim_champions.pop(d, None)

        # State advances in bout order, a then b, so a fighter twice on one
        # card carries the later bout's division — as the row loop did.
        seq_ids = np.empty(2 * (hi - lo), dtype=np.int64)
        seq_ids[0::2], seq_ids[1::2] = ra, rb
        seq_mu = np.empty(2 * (hi - lo))
        seq_mu[0::2], seq_mu[1::2] = post_mu_a[rows], post_mu_b[rows]
        seq_div = np.repeat(division_code[rows], 2)
        keep = (seq_ids >= 0) & ~np.isnan(seq_mu)
        if keep.any():
            state_mu[seq_ids[keep]] = seq_mu[keep]
            state_division[seq_ids[keep]] = seq_div[keep]
            state_last_day[seq_ids[keep]] = event_days[lo]

    return pd.DataFrame({
        "fight_url": f["fight_url"].to_numpy() if "fight_url" in f.columns else np.full(n, None),
        "division": divisions,
        "is_championship_bout": is_title,
        "is_interim_title_bout": is_interim,
        "fighter_a_prefight_division_rank": div_rank_a,
        "fighter_b_prefight_division_rank": div_rank_b,
        "fighter_a_prefight_p4p_rank": p4p_rank_a,
        "fighter_b_prefight_p4p_rank": p4p_rank_b,
        "fighter_a_entered_as_champion": champ_a,
        "fighter_b_entered_as_champion": champ_b,
        "fighter_a_entered_as_interim_champion": interim_champ_a,
        "fighter_b_entered_as_interim_champion": interim_champ_b,
    })


def _division_limit(division: object) -> float | None:
    if not isinstance(division, str):
        return None
    value = DIVISION_WEIGHT_LIMIT_LB.get(division)
    return float(value) if value is not None else None


def _movement_label(previous_limit: float | None, current_limit: float | None) -> str:
    if previous_limit is None or current_limit is None:
        return "unknown"
    if current_limit > previous_limit:
        return "up"
    if current_limit < previous_limit:
        return "down"
    return "same"


def prefight_weight_class_context(canonical_fights: pd.DataFrame) -> pd.DataFrame:
    """Previous UFC division and move direction entering each bout.

    A fighter's previous division is captured before the event is processed and
    updated only after the event, avoiding same-card leakage. Catchweight/open
    weight and unknown labels are neutral because they do not map cleanly to a
    standard UFC weight limit. Up/down moves only exist on the first fight
    after a standard-division change; once the fighter has appeared in the new
    division, following fights in that division are marked ``same``.
    """
    columns = [
        "fight_url",
        "fighter_a_previous_division",
        "fighter_b_previous_division",
        "fighter_a_previous_weight_limit_lb",
        "fighter_b_previous_weight_limit_lb",
        "fighter_current_weight_limit_lb",
        "fighter_a_weight_class_move",
        "fighter_b_weight_class_move",
        "fighter_a_weight_class_change_fight",
        "fighter_b_weight_class_change_fight",
    ]
    if canonical_fights is None or canonical_fights.empty:
        return pd.DataFrame(columns=columns)

    f = canonical_fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    if "division" not in f.columns:
        f["division"] = f.get("weight_class", pd.Series(index=f.index)).map(normalize_division_label)
    f["fighter_current_weight_limit_lb"] = f["division"].map(_division_limit)
    f = f.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    previous_division: dict[str, str | None] = {}
    rows: list[dict] = []
    for (_event_date, _event_name), group in f.groupby(["event_date", "event_name"], sort=False):
        for _, row in group.iterrows():
            current_limit = _division_limit(row.get("division"))
            a = row.get("fighter_a")
            b = row.get("fighter_b")
            a_prev = previous_division.get(a)
            b_prev = previous_division.get(b)
            a_prev_limit = _division_limit(a_prev)
            b_prev_limit = _division_limit(b_prev)
            a_move = _movement_label(a_prev_limit, current_limit)
            b_move = _movement_label(b_prev_limit, current_limit)
            rows.append({
                "fight_url": row.get("fight_url"),
                "fighter_a_previous_division": a_prev,
                "fighter_b_previous_division": b_prev,
                "fighter_a_previous_weight_limit_lb": a_prev_limit,
                "fighter_b_previous_weight_limit_lb": b_prev_limit,
                "fighter_current_weight_limit_lb": current_limit,
                "fighter_a_weight_class_move": a_move,
                "fighter_b_weight_class_move": b_move,
                "fighter_a_weight_class_change_fight": a_move in {"up", "down"},
                "fighter_b_weight_class_change_fight": b_move in {"up", "down"},
            })

        for _, row in group.iterrows():
            division = row.get("division")
            if not _division_limit(division):
                continue
            for side in ("fighter_a", "fighter_b"):
                fighter = row.get(side)
                if fighter:
                    previous_division[fighter] = division

    return pd.DataFrame(rows, columns=columns)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Sub-factor builders (each maps an underlying signal to a multiplicative factor)


def decisiveness_score(row: pd.Series) -> float:
    """Calibrated result decisiveness score in [0, 1]."""
    method = row.get("method_class")
    method = "" if method is None or pd.isna(method) else str(method)
    if method == "DQ":
        return 0.70
    if method in {"KO/TKO", "Submission"}:
        end_round = pd.to_numeric(row.get("end_round"), errors="coerce")
        return 1.00 if not pd.isna(end_round) and float(end_round) <= 1.0 else 0.95
    if method.startswith("Decision - Split"):
        return 0.78
    if method.startswith("Decision - Majority"):
        return 0.80
    if method.startswith("Decision - Unanimous"):
        scores = parse_judge_scores(row.get("details_text"))
        sched = scheduled_rounds(row.get("time_format"))
        winner = row.get("winner")
        if scores and sched >= 5:
            if winner == row.get("fighter_a"):
                margins = [a - b for a, b in scores]
            elif winner == row.get("fighter_b"):
                margins = [b - a for a, b in scores]
            else:
                margins = []
            if margins and all(m >= sched for m in margins):
                return 0.88
        return 0.83
    return 0.83


def _decisiveness_factor(score: pd.Series) -> pd.Series:
    level = pd.to_numeric(score, errors="coerce").fillna(0.83).clip(lower=0.0, upper=1.0)
    return 1.0 + PERF_DECISIVENESS_AMPLITUDE * level


def _opponent_strength_factor(fighter_mu: pd.Series, opponent_mu: pd.Series) -> pd.Series:
    """Audit-only multiplier for opponent mu strength.

    Captures **only** the "opponent is highly rated" signal. The legacy
    underdog/mismatch terms have moved to the rank-gated upset factor so the
    same opponent-quality information no longer double-counts when combined
    via ``max`` with rank/champ/P4P context.
    """
    return opponent_mu_quality_factor(opponent_mu)


def _opponent_streak_factor(opponent_streak: pd.Series, opponent_mu: pd.Series) -> pd.Series:
    """Bonus for ending a winning streak — only matters against rated opponents."""
    streak = pd.to_numeric(opponent_streak, errors="coerce").fillna(0.0)
    opp = pd.to_numeric(opponent_mu, errors="coerce").fillna(1500.0)
    opp_level = ((opp - 1500.0) / 650.0).clip(lower=0.0, upper=1.0)
    component = PERF_OPPONENT_STREAK_AMPLITUDE * (streak.clip(lower=0.0, upper=5.0) / 5.0) * (0.5 + 0.5 * opp_level)
    return 1.0 + component


def _american_from_decimal(decimal_odds: object) -> float | None:
    try:
        dec = float(decimal_odds)
    except (TypeError, ValueError):
        return None
    if np.isnan(dec) or dec <= 1.0:
        return None
    if dec >= 2.0:
        return (dec - 1.0) * 100.0
    return -100.0 / (dec - 1.0)


def _rank_context_factor(opponent_rank: pd.Series, opponent_champion: pd.Series, opponent_interim: pd.Series) -> pd.Series:
    """Bonus for beating a ranked opponent; unranked opponents are neutral."""
    return rank_context_quality_factor(opponent_rank, opponent_champion, opponent_interim)


def _championship_factor(
    is_title: pd.Series,
    is_interim_title: pd.Series,
    opponent_champion: pd.Series,
    opponent_interim: pd.Series,
) -> pd.Series:
    return championship_quality_factor(is_title, is_interim_title, opponent_champion, opponent_interim)


def _p4p_factor(opponent_p4p_rank: pd.Series) -> pd.Series:
    """Bonus for beating a pre-fight top-15 pound-for-pound opponent."""
    return p4p_quality_factor(opponent_p4p_rank)


def _weight_class_factor(
    move: pd.Series,
    change_fight: pd.Series,
    is_winner: pd.Series,
    is_draw: pd.Series,
) -> pd.Series:
    """Up+win boosts; down+loss amplifies losing update; up+loss damps it.

    The up+loss damp keeps an above-natural-class loss from punishing the
    fighter's main-division resume as harshly as a same-class loss.
    """
    move_text = move.fillna("unknown").astype(str).str.lower()
    first_after_change = change_fight.fillna(False).astype(bool)
    winners = is_winner.fillna(False).astype(bool)
    draws = is_draw.fillna(False).astype(bool)
    losses = ~winners & ~draws
    factor = pd.Series(1.0, index=move.index, dtype="float64")
    factor.loc[first_after_change & winners & move_text.eq("up")] = 1.0 + PERF_WEIGHT_CLASS_UP_WIN_AMPLITUDE
    factor.loc[first_after_change & losses & move_text.eq("down")] = 1.0 + PERF_WEIGHT_CLASS_DOWN_LOSS_AMPLITUDE
    factor.loc[first_after_change & losses & move_text.eq("up")] = 1.0 - PERF_WEIGHT_CLASS_UP_LOSS_DAMP
    return factor


def _attach_activity_gap_columns(out: pd.DataFrame) -> pd.DataFrame:
    """Add prior-UFC-gap columns per fighter appearance."""
    out = out.sort_values(["fighter", "event_date", "event_name", "fight_url"]).copy()
    prior_date = out.groupby("fighter")["event_date"].shift(1)
    gap = (out["event_date"] - prior_date).dt.days
    out["activity_gap_days"] = gap
    denom = max(ACTIVITY_GAP_FULL_PENALTY - ACTIVITY_GAP_NORMAL, 1)
    out["activity_layoff_level"] = (
        (pd.to_numeric(gap, errors="coerce") - ACTIVITY_GAP_NORMAL) / denom
    ).clip(lower=0.0, upper=1.0).fillna(0.0)
    return out.sort_index()


def _activity_loss_factor(layoff_level: pd.Series, is_winner: pd.Series, is_draw: pd.Series) -> pd.Series:
    winners = is_winner.fillna(False).astype(bool)
    draws = is_draw.fillna(False).astype(bool)
    losses = ~winners & ~draws
    level = pd.to_numeric(layoff_level, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    factor = pd.Series(1.0, index=level.index, dtype="float64")
    factor.loc[losses] = 1.0 + ACTIVITY_LOSS_AMPLITUDE * level.loc[losses]
    return factor


# ---------------------------------------------------------------------------
# Rank-gated upset signal
#
# An upset only fires when the winner is at least
# ``PERF_UPSET_RANK_GAP_THRESHOLD`` rank slots below the opponent. A #3 vs #4
# fight does not trigger; an unranked challenger beating the champion does.
# Champion → effective rank 0, interim champion → 1, unranked → 16. NaN ranks
# fall back to unranked (16).
#
# Magnitude scales linearly with the rank gap, anchored at the threshold and
# saturating at threshold + PERF_UPSET_RANK_GAP_SCALE. Moneyline odds can
# additionally confirm the upset for fights with sparse rank data, but the
# rank gate must already be open — otherwise a #3 favoured at -130 over a #4
# at +110 would erroneously read as an upset.


def _effective_rank(
    raw_rank: pd.Series,
    entered_as_champion: pd.Series,
    entered_as_interim: pd.Series,
) -> pd.Series:
    rank = pd.to_numeric(raw_rank, errors="coerce")
    champ = entered_as_champion.fillna(False).astype(bool)
    interim = entered_as_interim.fillna(False).astype(bool)
    effective = rank.where(~rank.isna(), PERF_UPSET_RANK_UNRANKED_VALUE).astype(float)
    effective = effective.clip(upper=PERF_UPSET_RANK_UNRANKED_VALUE)
    effective.loc[interim] = PERF_UPSET_RANK_INTERIM_VALUE
    effective.loc[champ] = PERF_UPSET_RANK_CHAMPION_VALUE
    return effective


def _upset_rank_gap(
    fighter_rank: pd.Series,
    opponent_rank: pd.Series,
    fighter_champion: pd.Series,
    fighter_interim: pd.Series,
    opponent_champion: pd.Series,
    opponent_interim: pd.Series,
) -> pd.Series:
    eff_fighter = _effective_rank(fighter_rank, fighter_champion, fighter_interim)
    eff_opp = _effective_rank(opponent_rank, opponent_champion, opponent_interim)
    return (eff_fighter - eff_opp).astype(float)


def _upset_factor(
    rank_gap: pd.Series,
    is_winner: pd.Series,
) -> pd.Series:
    """Rank-gated upset multiplier for winner-side rows.

    The output factor is in ``[1.0, 1 + PERF_UPSET_AMPLITUDE]``. The factor
    is computed for both winner and loser rows so the column is available for
    audit, but only the winner-side computation feeds ``S``. (Losers receive
    the symmetric tanh damp via ``S`` regardless.)

    The divisional rank gap is the whole gate. A closing-odds confirmation term
    used to sit alongside it; the 2026-08-18 audit measured it moving
    ``performance_weight`` on 35 of 16,958 appearance rows by at most 0.0077,
    for a paired effect on held-out log-loss of -1.4e-06 whose 95% interval
    spans zero, and it was removed.
    """
    gap = pd.to_numeric(rank_gap, errors="coerce").fillna(0.0)
    gate_open = gap >= PERF_UPSET_RANK_GAP_THRESHOLD
    level = ((gap - PERF_UPSET_RANK_GAP_THRESHOLD) / PERF_UPSET_RANK_GAP_SCALE).clip(
        lower=0.0, upper=1.0
    )
    level = level.where(gate_open, 0.0)
    # Only winners get the upset bonus surfaced into the per-factor column.
    level = level.where(is_winner.fillna(False).astype(bool), 0.0)
    return 1.0 + PERF_UPSET_AMPLITUDE * level


# ---------------------------------------------------------------------------
# Main builder


def build_performance_appearances(
    canonical_fights: pd.DataFrame,
    ratings_history: pd.DataFrame,
    odds_lines: pd.DataFrame | None = None,
    fight_dominance: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Per-(fight, fighter) performance weight, ready for the weighted engine.

    Outputs include the merged ``performance_weight`` plus each individual
    sub-factor for transparency and audit. Losers and draws emit weight 1.0.
    """
    if canonical_fights is None or canonical_fights.empty:
        return pd.DataFrame(columns=list(PERFORMANCE_APPEARANCE_COLUMNS))

    f = canonical_fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["scheduled_rounds"] = f["time_format"].apply(scheduled_rounds)
    f["scheduled_seconds"] = f["scheduled_rounds"] * 300.0
    f["bout_duration_seconds"] = f.apply(fight_duration_seconds, axis=1)
    f["is_finish"] = f.get("method_class", pd.Series("", index=f.index)).isin(["KO/TKO", "Submission"])
    f["quality_score_winner"] = f.apply(quality_score_winner, axis=1)
    f["decisiveness_score"] = f.apply(decisiveness_score, axis=1)
    f = _attach_dominance_score(f, fight_dominance)

    # Pre-fight rank/championship/P4P context, all derived without future leak.
    context = prefight_ranking_context(f, ratings_history)
    f = f.merge(context, on="fight_url", how="left")
    f = _apply_championship_defense_floor(f)
    weight_class_context = prefight_weight_class_context(f)
    f = f.merge(weight_class_context, on="fight_url", how="left")

    # Win streaks heading into each bout.
    f = f.merge(pre_fight_win_streaks(f), on="fight_url", how="left")

    # Opponent pre-fight mu (from canonical history).
    prior = prefight_ratings(ratings_history)
    prior_a = prior.rename(columns={"fighter": "fighter_a", "prefight_mu": "prefight_mu_a"})
    prior_b = prior.rename(columns={"fighter": "fighter_b", "prefight_mu": "prefight_mu_b"})
    f = f.merge(prior_a, on=["fighter_a", "event_date", "event_name"], how="left")
    f = f.merge(prior_b, on=["fighter_b", "event_date", "event_name"], how="left")
    for c in ("prefight_mu_a", "prefight_mu_b"):
        f[c] = pd.to_numeric(f[c], errors="coerce").fillna(1500.0)

    # Optional odds residual (joined per-side).
    have_odds = odds_lines is not None and not odds_lines.empty
    if have_odds:
        odds_cols = [
            "fight_url",
            "implied_prob_a_no_vig", "implied_prob_b_no_vig",
            "american_odds_a", "american_odds_b",
            "decimal_odds_a", "decimal_odds_b",
            "odds_data_quality",
        ]
        odds_use = odds_lines[[c for c in odds_cols if c in odds_lines.columns]].copy()
        ok = odds_use.get("odds_data_quality", pd.Series("missing", index=odds_use.index)).eq("ok")
        odds_use = odds_use[ok]
        f = f.merge(odds_use, on="fight_url", how="left")
    else:
        f["implied_prob_a_no_vig"] = pd.NA
        f["implied_prob_b_no_vig"] = pd.NA
        f["american_odds_a"] = pd.NA
        f["american_odds_b"] = pd.NA
        f["decimal_odds_a"] = pd.NA
        f["decimal_odds_b"] = pd.NA

    # Now explode into two appearance rows per fight.
    common = [
        "fight_url", "event_date", "event_name", "fighter_a", "fighter_b",
        "winner", "is_draw", "quality_score_winner", "method_class",
        "dominance_score_winner",
        "scheduled_rounds", "scheduled_seconds", "end_round", "end_time_seconds",
        "bout_duration_seconds", "decisiveness_score",
        "is_finish", "division", "is_championship_bout", "is_interim_title_bout",
        "fighter_current_weight_limit_lb",
    ]
    a = f[common + [
        "prefight_mu_a", "prefight_mu_b", "streak_b",
        "fighter_a_prefight_division_rank", "fighter_b_prefight_division_rank",
        "fighter_a_prefight_p4p_rank", "fighter_b_prefight_p4p_rank",
        "fighter_a_entered_as_champion", "fighter_b_entered_as_champion",
        "fighter_a_entered_as_interim_champion", "fighter_b_entered_as_interim_champion",
        "fighter_a_previous_division", "fighter_a_previous_weight_limit_lb",
        "fighter_a_weight_class_move", "fighter_a_weight_class_change_fight",
        "implied_prob_a_no_vig", "american_odds_a", "decimal_odds_a",
    ]].rename(columns={
        "fighter_a": "fighter",
        "fighter_b": "opponent",
        "prefight_mu_a": "prefight_mu",
        "prefight_mu_b": "opponent_prefight_mu",
        "streak_b": "opponent_streak",
        "fighter_a_prefight_division_rank": "fighter_prefight_division_rank",
        "fighter_b_prefight_division_rank": "opponent_prefight_division_rank",
        "fighter_a_prefight_p4p_rank": "fighter_prefight_p4p_rank",
        "fighter_b_prefight_p4p_rank": "opponent_prefight_p4p_rank",
        "fighter_a_entered_as_champion": "fighter_entered_as_champion",
        "fighter_b_entered_as_champion": "opponent_entered_as_champion",
        "fighter_a_entered_as_interim_champion": "fighter_entered_as_interim_champion",
        "fighter_b_entered_as_interim_champion": "opponent_entered_as_interim_champion",
        "fighter_a_previous_division": "fighter_previous_division",
        "fighter_a_previous_weight_limit_lb": "fighter_previous_weight_limit_lb",
        "fighter_a_weight_class_move": "fighter_weight_class_move",
        "fighter_a_weight_class_change_fight": "fighter_weight_class_change_fight",
        "implied_prob_a_no_vig": "market_prob",
        "american_odds_a": "market_american_odds",
        "decimal_odds_a": "market_decimal_odds",
    })
    b = f[common + [
        "prefight_mu_b", "prefight_mu_a", "streak_a",
        "fighter_b_prefight_division_rank", "fighter_a_prefight_division_rank",
        "fighter_b_prefight_p4p_rank", "fighter_a_prefight_p4p_rank",
        "fighter_b_entered_as_champion", "fighter_a_entered_as_champion",
        "fighter_b_entered_as_interim_champion", "fighter_a_entered_as_interim_champion",
        "fighter_b_previous_division", "fighter_b_previous_weight_limit_lb",
        "fighter_b_weight_class_move", "fighter_b_weight_class_change_fight",
        "implied_prob_b_no_vig", "american_odds_b", "decimal_odds_b",
    ]].rename(columns={
        "fighter_b": "fighter",
        "fighter_a": "opponent",
        "prefight_mu_b": "prefight_mu",
        "prefight_mu_a": "opponent_prefight_mu",
        "streak_a": "opponent_streak",
        "fighter_b_prefight_division_rank": "fighter_prefight_division_rank",
        "fighter_a_prefight_division_rank": "opponent_prefight_division_rank",
        "fighter_b_prefight_p4p_rank": "fighter_prefight_p4p_rank",
        "fighter_a_prefight_p4p_rank": "opponent_prefight_p4p_rank",
        "fighter_b_entered_as_champion": "fighter_entered_as_champion",
        "fighter_a_entered_as_champion": "opponent_entered_as_champion",
        "fighter_b_entered_as_interim_champion": "fighter_entered_as_interim_champion",
        "fighter_a_entered_as_interim_champion": "opponent_entered_as_interim_champion",
        "fighter_b_previous_division": "fighter_previous_division",
        "fighter_b_previous_weight_limit_lb": "fighter_previous_weight_limit_lb",
        "fighter_b_weight_class_move": "fighter_weight_class_move",
        "fighter_b_weight_class_change_fight": "fighter_weight_class_change_fight",
        "implied_prob_b_no_vig": "market_prob",
        "american_odds_b": "market_american_odds",
        "decimal_odds_b": "market_decimal_odds",
    })
    out = pd.concat([a, b], ignore_index=True, sort=False)
    out = _attach_activity_gap_columns(out)
    out["is_draw"] = out.get("is_draw", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    out["is_winner"] = out["winner"].eq(out["fighter"]) & ~out["is_draw"]
    out["actual_score"] = np.select(
        [out["is_draw"], out["is_winner"]],
        [0.5, 1.0],
        default=0.0,
    )
    out["market_residual"] = pd.to_numeric(out["actual_score"], errors="coerce") - pd.to_numeric(out["market_prob"], errors="coerce")
    missing_american = pd.to_numeric(out["market_american_odds"], errors="coerce").isna()
    if missing_american.any():
        derived_american = out.loc[missing_american, "market_decimal_odds"].map(_american_from_decimal)
        out.loc[missing_american, "market_american_odds"] = pd.to_numeric(derived_american, errors="coerce")
    # Per-factor audit columns. Each ``perf_factor_*`` reflects what that one
    # signal would say on its own; the per-fight combination below
    # deduplicates overlapping opponent-quality signals via ``max``.
    out["perf_factor_decisiveness"] = _decisiveness_factor(out["decisiveness_score"]).clip(
        lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)
    out["perf_factor_opponent_strength"] = _opponent_strength_factor(
        out["prefight_mu"], out["opponent_prefight_mu"]
    )
    out["perf_factor_opponent_streak"] = _opponent_streak_factor(
        out["opponent_streak"], out["opponent_prefight_mu"]
    ).clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)
    out["perf_factor_rank_context"] = _rank_context_factor(
        out["opponent_prefight_division_rank"],
        out["opponent_entered_as_champion"],
        out["opponent_entered_as_interim_champion"],
    ).clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)
    out["perf_factor_championship"] = _championship_factor(
        out["is_championship_bout"],
        out["is_interim_title_bout"],
        out["opponent_entered_as_champion"],
        out["opponent_entered_as_interim_champion"],
    ).clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)
    out["perf_factor_p4p"] = _p4p_factor(out["opponent_prefight_p4p_rank"]).clip(
        lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)
    out["perf_factor_weight_class"] = _weight_class_factor(
        out["fighter_weight_class_move"],
        out["fighter_weight_class_change_fight"],
        out["is_winner"],
        out["is_draw"],
    ).clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)
    out["perf_factor_activity_loss"] = _activity_loss_factor(
        out["activity_layoff_level"],
        out["is_winner"],
        out["is_draw"],
    ).clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)

    # Rank-gated upset: needs the winner-side rank gap (champion=0, unranked=16).
    out["perf_upset_rank_gap"] = _upset_rank_gap(
        out["fighter_prefight_division_rank"],
        out["opponent_prefight_division_rank"],
        out["fighter_entered_as_champion"],
        out["fighter_entered_as_interim_champion"],
        out["opponent_entered_as_champion"],
        out["opponent_entered_as_interim_champion"],
    )
    out["perf_factor_upset"] = _upset_factor(
        out["perf_upset_rank_gap"], out["is_winner"]
    ).clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)

    # ------------------------------------------------------------------
    # Additive log-signal ``S``. Built from the winner-side factors of each
    # bout; the same value is then applied symmetrically to the loser row so
    # the loss is damped by the same amount the win was amplified.
    method_log = np.log(out["perf_factor_decisiveness"].astype(float))

    # Deduplicate opponent-quality signals: ``max`` over the four overlapping
    # multipliers so a champion who is also top-15 division and top-15 P4P
    # does not triple-count. The legacy ``perf_factor_*`` columns remain in
    # the parquet for audit; only the strongest contributes here.
    opp_quality_max = pd.concat(
        [
            out["perf_factor_opponent_strength"].astype(float),
            out["perf_factor_rank_context"].astype(float),
            out["perf_factor_championship"].astype(float),
            out["perf_factor_p4p"].astype(float),
        ],
        axis=1,
    ).max(axis=1)
    opp_quality_log = np.log(opp_quality_max)

    upset_log = np.log(out["perf_factor_upset"].astype(float))
    streak_log = np.log(out["perf_factor_opponent_streak"].astype(float))
    weight_class_log = np.log(out["perf_factor_weight_class"].astype(float))

    winner_signal = method_log + opp_quality_log + upset_log + streak_log + weight_class_log

    # Each appearance row has its own winner_signal computation, but only the
    # WINNER row carries the signal that drives the fight's tanh mapping; the
    # loser row must inherit the winner's signal so the symmetric damp uses
    # the same per-fight ``S``. Use the winner-side row per fight_url to
    # propagate.
    winner_signal_by_fight = (
        out.loc[out["is_winner"].fillna(False).astype(bool), ["fight_url"]]
        .assign(perf_winner_signal_S=winner_signal.loc[out["is_winner"].fillna(False).astype(bool)].to_numpy())
        .drop_duplicates("fight_url")
    )
    out = out.merge(winner_signal_by_fight, on="fight_url", how="left")
    out["perf_winner_signal_S"] = out["perf_winner_signal_S"].fillna(0.0)

    # ``perf_signal_S`` is the row-local contribution (visible for audit), while
    # ``perf_winner_signal_S`` is the per-fight winner signal applied
    # symmetrically. Draws keep 1.0 weight on both sides.
    out["perf_signal_S"] = winner_signal.astype(float)

    tanh_term = np.tanh(out["perf_winner_signal_S"].astype(float) / PERF_TANH_SCALE)
    winner_weight = 1.0 + _ENVELOPE_HALF * tanh_term
    loser_weight = 1.0 - _ENVELOPE_HALF * tanh_term
    out["performance_weight"] = 1.0
    is_winner_mask = out["is_winner"].fillna(False).astype(bool)
    is_draw_mask = out["is_draw"].fillna(False).astype(bool)
    losers = (~is_winner_mask) & (~is_draw_mask)
    # Structural loser amplifiers are conceptually opposite to the tanh damp
    # (they AMPLIFY the loss), so they override the symmetric damp and compose
    # with each other before the final envelope clip.
    loser_down = (
        losers
        & out["fighter_weight_class_change_fight"].fillna(False).astype(bool)
        & out["fighter_weight_class_move"].fillna("").eq("down")
    )
    structural_loss_factor = pd.Series(1.0, index=out.index, dtype="float64")
    structural_loss_factor.loc[loser_down] *= out.loc[loser_down, "perf_factor_weight_class"].astype(float)
    activity_loss = losers & out["perf_factor_activity_loss"].astype(float).gt(1.0)
    structural_loss_factor.loc[activity_loss] *= out.loc[activity_loss, "perf_factor_activity_loss"].astype(float)
    structural_loss = losers & structural_loss_factor.gt(1.0)
    out.loc[is_winner_mask, "performance_weight"] = winner_weight.loc[is_winner_mask]
    out.loc[losers & ~structural_loss, "performance_weight"] = loser_weight.loc[losers & ~structural_loss]
    out.loc[structural_loss, "performance_weight"] = structural_loss_factor.loc[structural_loss]

    # Up-class loss damp: an above-natural-class loss further damps the loser
    # update so it detracts less from the main-division resume. Composes
    # multiplicatively with the symmetric tanh damp; the envelope clip below
    # bounds the result.
    loser_up = (
        losers
        & out["fighter_weight_class_change_fight"].fillna(False).astype(bool)
        & out["fighter_weight_class_move"].fillna("").eq("up")
    )
    if loser_up.any():
        up_loss_damp = pd.Series(1.0, index=out.index, dtype="float64")
        up_loss_damp.loc[loser_up] = out.loc[loser_up, "perf_factor_weight_class"].astype(float)
        out.loc[loser_up, "performance_weight"] = (
            out.loc[loser_up, "performance_weight"].astype(float) * up_loss_damp.loc[loser_up]
        )

    out["performance_weight"] = out["performance_weight"].clip(
        lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX
    )

    return out[list(PERFORMANCE_APPEARANCE_COLUMNS)].copy()
