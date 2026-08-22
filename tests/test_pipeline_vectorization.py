"""The vectorized hot loops must agree with the row-loop logic they replaced.

The 2026-08-18 performance work rewrote four per-row/per-event Python loops as
array passes. Each was verified bit-exact against the committed 2026-08-13 and
depth-one snapshots, but those artifacts are gitignored, so the guarantee is
pinned here against reference implementations written the slow, obvious way.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ratings.division_resume import division_resume_rows
from ratings.appearance_context import (
    _context_adjustment,
    _result_adjustment,
)
from ratings.performance_adjustment import (
    _group_bounds,
    pre_fight_win_streaks,
    prefight_ranking_context,
)


def _rank_map(rows: list[tuple[str, float]]) -> dict[str, int]:
    """The rank ordering the vectorized lexsort has to reproduce: (-mu, name)."""
    ranked = sorted(rows, key=lambda item: (-float(item[1]), item[0]))
    return {fighter: rank for rank, (fighter, _mu) in enumerate(ranked, start=1)}


# ---------------------------------------------------------------------------
# Synthetic snapshot


def _synthetic_fights(n_events: int = 24, seed: int = 7) -> pd.DataFrame:
    """A fight table with the shapes the real loops have to survive.

    Deliberately includes: rematches, two bouts for one fighter on one card,
    title bouts, an interim title bout, a drawn title bout (no winner), a
    division change, and long layoffs.
    """
    rng = np.random.default_rng(seed)
    fighters = [f"F{i:02d}" for i in range(26)]
    divisions = ["Lightweight", "Welterweight", "Middleweight"]
    rows = []
    date = pd.Timestamp("2005-01-15")
    for e in range(n_events):
        date = date + pd.Timedelta(days=int(rng.integers(20, 400)))
        name = f"EV {e}"
        n_bouts = int(rng.integers(3, 7))
        pool = list(rng.permutation(fighters))
        for b in range(n_bouts):
            a, c = pool[2 * b], pool[2 * b + 1]
            div = divisions[int(rng.integers(0, len(divisions)))]
            title = (e % 5 == 0) and b == 0
            interim = (e % 11 == 0) and b == 1
            drawn = (e == 13) and b == 0
            winner = None if drawn else (a if rng.random() < 0.6 else c)
            label = div
            if title:
                label = f"UFC {div} Title Bout"
            elif interim:
                label = f"UFC Interim {div} Title Bout"
            rows.append({
                "fight_url": f"u{e}-{b}",
                "event_date": date,
                "event_name": name,
                "fighter_a": a,
                "fighter_b": c,
                "winner": winner if not drawn else np.nan,
                "is_draw": bool(drawn),
                "weight_class": label,
                "method_class": "Decision - Unanimous" if rng.random() < 0.5 else "KO/TKO",
                "method_score_winner": 0.9,
                "end_round": 3,
                "end_time_seconds": 300,
                "time_format": "3 Rnd (5-5-5)",
                "is_excluded": False,
            })
        # One fighter twice on the same card, exercising the last-row-wins rule.
        if e == 6:
            rows.append({**rows[-1], "fight_url": f"u{e}-x", "fighter_a": rows[-1]["fighter_a"],
                         "fighter_b": pool[-1], "winner": rows[-1]["fighter_a"],
                         "weight_class": "Welterweight", "is_draw": False})
    return pd.DataFrame(rows)


def _synthetic_history(fights: pd.DataFrame, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for _, r in fights.iterrows():
        for side in ("fighter_a", "fighter_b"):
            rows.append({
                "fighter": r[side],
                "event_date": r["event_date"],
                "event_name": r["event_name"],
                "mu_canonical": 1500.0 + rng.normal(0, 120),
                "phi_canonical": 200.0,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _group_bounds


def test_group_bounds_matches_groupby_on_a_sorted_frame():
    fights = _synthetic_fights().sort_values(["event_date", "event_name"]).reset_index(drop=True)
    starts, stops = _group_bounds(fights["event_date"], fights["event_name"])
    expected = [
        (int(g.index[0]), int(g.index[-1]) + 1)
        for _, g in fights.groupby(["event_date", "event_name"], sort=False)
    ]
    assert list(zip(starts.tolist(), stops.tolist())) == expected


def test_group_bounds_handles_empty_input():
    starts, stops = _group_bounds(pd.Series([], dtype="datetime64[ns]"), pd.Series([], dtype=str))
    assert len(starts) == 0 and len(stops) == 0


# ---------------------------------------------------------------------------
# prefight_ranking_context


def _reference_prefight_ranking_context(fights: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """The pre-2026-08-18 row-loop implementation, kept as the oracle."""
    from ratings.constants import RANK_CONTEXT_ACTIVE_DAYS
    from ratings.performance_adjustment import (
        is_interim_title_bout, is_real_ufc_title_bout, normalize_division_label,
    )

    f = fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["division"] = f["weight_class"].map(normalize_division_label)
    f["is_championship_bout"] = f["weight_class"].map(is_real_ufc_title_bout)
    f["is_interim_title_bout"] = f["weight_class"].map(is_interim_title_bout)
    f = f.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    h = history[["fighter", "event_date", "event_name", "mu_canonical"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    history_by_event = {k: g for k, g in h.groupby(["event_date", "event_name"], sort=False)}

    state_mu, state_division, state_last_date = {}, {}, {}
    champions, interim_champions = {}, {}
    rows = []
    for (event_date, event_name), group in f.groupby(["event_date", "event_name"], sort=False):
        event_date = pd.Timestamp(event_date)
        cutoff = event_date - pd.Timedelta(days=RANK_CONTEXT_ACTIVE_DAYS)
        active = [(fi, mu) for fi, mu in state_mu.items()
                  if state_last_date.get(fi, pd.Timestamp.min) >= cutoff]
        p4p_rank = _rank_map(active)
        by_division = {}
        for fi, mu in active:
            d = state_division.get(fi)
            if d:
                by_division.setdefault(d, []).append((fi, mu))
        division_ranks = {d: _rank_map(v) for d, v in by_division.items()}

        for _, row in group.iterrows():
            division = row.get("division")
            div_map = division_ranks.get(division, {}) if division else {}
            a, b = row.get("fighter_a"), row.get("fighter_b")
            rows.append({
                "fight_url": row.get("fight_url"),
                "division": division,
                "is_championship_bout": bool(row.get("is_championship_bout", False)),
                "is_interim_title_bout": bool(row.get("is_interim_title_bout", False)),
                "fighter_a_prefight_division_rank": div_map.get(a),
                "fighter_b_prefight_division_rank": div_map.get(b),
                "fighter_a_prefight_p4p_rank": p4p_rank.get(a),
                "fighter_b_prefight_p4p_rank": p4p_rank.get(b),
                "fighter_a_entered_as_champion": bool(division and champions.get(division) == a),
                "fighter_b_entered_as_champion": bool(division and champions.get(division) == b),
                "fighter_a_entered_as_interim_champion": bool(
                    division and interim_champions.get(division) == a),
                "fighter_b_entered_as_interim_champion": bool(
                    division and interim_champions.get(division) == b),
            })

        for _, row in group.iterrows():
            winner, division = row.get("winner"), row.get("division")
            if (pd.isna(winner) or not winner or not division
                    or not bool(row.get("is_championship_bout", False))):
                continue
            if bool(row.get("is_interim_title_bout", False)):
                interim_champions[division] = winner
            else:
                champions[division] = winner
                interim_champions.pop(division, None)

        post = history_by_event.get((event_date, event_name))
        if post is None:
            continue
        post_mu = dict(zip(post["fighter"], pd.to_numeric(post["mu_canonical"], errors="coerce")))
        for _, row in group.iterrows():
            division = row.get("division")
            for side in ("fighter_a", "fighter_b"):
                fighter = row.get(side)
                if not fighter or fighter not in post_mu or pd.isna(post_mu[fighter]):
                    continue
                state_mu[fighter] = float(post_mu[fighter])
                state_division[fighter] = division
                state_last_date[fighter] = event_date
    return pd.DataFrame(rows)


def test_prefight_ranking_context_matches_the_row_loop():
    fights = _synthetic_fights()
    history = _synthetic_history(fights)
    got = prefight_ranking_context(fights, history).sort_values("fight_url").reset_index(drop=True)
    ref = _reference_prefight_ranking_context(fights, history).sort_values(
        "fight_url").reset_index(drop=True)

    assert len(got) == len(ref)
    for col in ref.columns:
        a, b = ref[col], got[col]
        if pd.api.types.is_bool_dtype(b) or col.endswith("champion"):
            assert (a.fillna(False).astype(bool) == b.fillna(False).astype(bool)).all(), col
        elif col in {"division", "fight_url"}:
            assert ((a == b) | (a.isna() & b.isna())).all(), col
        else:
            av = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
            bv = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)
            assert ((av == bv) | (np.isnan(av) & np.isnan(bv))).all(), col


def test_drawn_title_bout_preserves_the_modelled_lineage():
    fights = pd.DataFrame([
        {
            "fight_url": "title-1", "event_date": "2020-01-01", "event_name": "E1",
            "fighter_a": "A", "fighter_b": "B", "winner": "A",
            "weight_class": "UFC Lightweight Title Bout", "is_draw": False,
        },
        {
            "fight_url": "title-draw", "event_date": "2020-06-01", "event_name": "E2",
            "fighter_a": "A", "fighter_b": "C", "winner": np.nan,
            "weight_class": "UFC Lightweight Title Bout", "is_draw": True,
        },
        {
            "fight_url": "after-draw", "event_date": "2020-12-01", "event_name": "E3",
            "fighter_a": "A", "fighter_b": "D", "winner": "D",
            "weight_class": "Lightweight", "is_draw": False,
        },
    ])
    history = _synthetic_history(fights)

    got = prefight_ranking_context(fights, history).set_index("fight_url")

    assert bool(got.loc["title-draw", "fighter_a_entered_as_champion"])
    assert bool(got.loc["after-draw", "fighter_a_entered_as_champion"])


# ---------------------------------------------------------------------------
# pre_fight_win_streaks


def test_pre_fight_win_streaks_matches_the_row_loop():
    fights = _synthetic_fights()
    got = pre_fight_win_streaks(fights).sort_values("fight_url").reset_index(drop=True)

    f = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    streaks: dict[str, int] = {}
    rows = []
    for (_d, _n), group in f.groupby(["event_date", "event_name"], sort=False):
        for _, row in group.iterrows():
            rows.append({"fight_url": row["fight_url"],
                         "streak_a": int(streaks.get(row["fighter_a"], 0)),
                         "streak_b": int(streaks.get(row["fighter_b"], 0))})
        for _, row in group.iterrows():
            a, b = row["fighter_a"], row["fighter_b"]
            if bool(row.get("is_draw", False)):
                streaks[a] = streaks[b] = 0
            elif row["winner"] == a:
                streaks[a] = streaks.get(a, 0) + 1
                streaks[b] = 0
            elif row["winner"] == b:
                streaks[b] = streaks.get(b, 0) + 1
                streaks[a] = 0
            else:
                streaks[a] = streaks[b] = 0
    ref = pd.DataFrame(rows).sort_values("fight_url").reset_index(drop=True)
    assert (got["streak_a"] == ref["streak_a"]).all()
    assert (got["streak_b"] == ref["streak_b"]).all()


# ---------------------------------------------------------------------------
# peaks window scan


def _reference_best_window(group: pd.DataFrame, *, mu_col: str, window_days: int,
                           min_fights: int, title_effective_min_raw_fights: int):
    """Recompute each window from the frame slice, the way the old scan did."""
    from ratings.constants import (
        PERIOD_ACTIVITY_BONUS_CAP, PERIOD_ACTIVITY_BONUS_PER_FIGHT,
        PERIOD_ACTIVITY_BONUS_PER_OPP_WEIGHT, PERIOD_DRAW_BASE_WEIGHT,
        PERIOD_EXTRA_TITLE_DIVISION_BONUS, PERIOD_LOSS_BASE_WEIGHT,
        PERIOD_LOSS_QUALITY_SCALE, PERIOD_WIN_BASE_WEIGHT,
    )
    g = group.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    dates = g["event_date"].to_numpy()
    best = None
    window_ns = np.timedelta64(window_days, "D")
    for j in range(len(g)):
        i = j
        while i > 0 and dates[i - 1] >= dates[j] - window_ns:
            i -= 1
        window = g.iloc[i:j + 1]
        if len(window) < min_fights:
            if len(window) < title_effective_min_raw_fights:
                continue
            if _title_effective_count(window) < float(min_fights):
                continue
        score_arr = pd.to_numeric(window["actual_score"], errors="coerce").fillna(0.0).to_numpy()
        opp_w = pd.to_numeric(window["opp_weight"], errors="coerce").fillna(0.0).to_numpy()
        level = pd.to_numeric(window["opponent_quality_level"], errors="coerce").fillna(
            0.0).clip(0.0, 1.0).to_numpy()
        is_win = score_arr >= 1.0
        is_draw = (score_arr > 0.0) & (score_arr < 1.0)
        weights = np.where(is_win, PERIOD_WIN_BASE_WEIGHT + opp_w,
                           np.where(is_draw, PERIOD_DRAW_BASE_WEIGHT + 0.5 * opp_w,
                                    PERIOD_LOSS_BASE_WEIGHT
                                    + PERIOD_LOSS_QUALITY_SCALE * (1.0 - level)))
        adjusted = (pd.to_numeric(window[mu_col], errors="coerce")
                    + _result_adjustment(window["actual_score"])
                    + _context_adjustment(window)).to_numpy(dtype=float)
        valid = (weights > 0) & ~np.isnan(adjusted)
        if not valid.any():
            continue
        w_sum = float(weights[valid].sum())
        if w_sum <= 0:
            continue
        w_mean = float((weights[valid] * adjusted[valid]).sum() / w_sum)
        opp_sum = float(opp_w.sum())
        score = w_mean + float(np.clip(
            PERIOD_ACTIVITY_BONUS_PER_FIGHT * max(0, len(window) - min_fights)
            + PERIOD_ACTIVITY_BONUS_PER_OPP_WEIGHT * opp_sum,
            0.0, PERIOD_ACTIVITY_BONUS_CAP))
        title_wins = window[window["is_championship_bout"].fillna(False).astype(bool)
                            & (score_arr >= 1.0)]
        n_div = title_wins["division"].dropna().nunique() if not title_wins.empty else 0
        score += float(max(0, n_div - 1) * PERIOD_EXTRA_TITLE_DIVISION_BONUS)
        candidate = (score, opp_sum, _title_ladder_mass(window), len(window))
        if best is None or candidate[0] > best[0]:
            best = candidate
    return best


def _appearance_frame(seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for f in range(6):
        date = pd.Timestamp("2008-03-01")
        for k in range(int(rng.integers(6, 20))):
            date = date + pd.Timedelta(days=int(rng.integers(60, 500)))
            rows.append({
                "fighter": f"F{f}",
                "event_date": date,
                "event_name": f"E{f}-{k}",
                "mu_period_normalized": 1500.0 + rng.normal(0, 90),
                "actual_score": float(rng.choice([0.0, 0.5, 1.0], p=[0.4, 0.05, 0.55])),
                "opp_weight": float(rng.random()),
                "opponent_quality_level": float(rng.random()),
                "division": rng.choice(["Lightweight", "Welterweight", None]),
                "is_championship_bout": bool(rng.random() < 0.2),
                "is_interim_title_bout": bool(rng.random() < 0.05),
                "fighter_entered_as_champion": bool(rng.random() < 0.15),
                "fighter_entered_as_interim_champion": False,
                "opponent_entered_as_champion": bool(rng.random() < 0.1),
                "opponent_entered_as_interim_champion": False,
                "opponent_prefight_division_rank": rng.choice([np.nan, 1, 4, 8, 12, 20]),
                "opponent_prefight_p4p_rank": rng.choice([np.nan, 2, 7, 14, 30]),
            })
    return pd.DataFrame(rows)


def test_division_resume_rows_scores_each_fighter_division_once():
    frame = _appearance_frame().dropna(subset=["division"])
    history = frame.rename(columns={"mu_period_normalized": "mu_whr"})[
        ["fighter", "event_date", "event_name", "mu_whr"]]
    out = division_resume_rows(history, frame)
    assert not out.empty
    assert not out.duplicated(["fighter", "division"]).any()
    counted = frame.groupby(["fighter", "division"]).size().rename("n").reset_index()
    merged = out.merge(counted, on=["fighter", "division"], how="left")
    assert (merged["division_fights"] == merged["n"]).all()
