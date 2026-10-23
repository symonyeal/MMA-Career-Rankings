"""Exact parity of the list-based ``prefight_weight_class_context`` and count-based ``prefight_ranking_context``.

Legend: wc = weight-class frame, h = ratings history, mu = post-event rating, pool = fighters in a division board.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import RANK_CONTEXT_ACTIVE_DAYS
from ratings.performance_adjustment import (
    _division_limit,
    _movement_label,
    normalize_division_label,
    prefight_ranking_context,
    prefight_weight_class_context,
)

_WC = ["UFC Lightweight Title Bout", "Lightweight Bout", "Welterweight Bout", "Catch Weight Bout",
       "Women's Strawweight Bout", None]


def _fights(seed: int, n_ev: int = 60, n_fighters: int = 14, classes=_WC) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    names = [f"F{i:02d}" for i in range(n_fighters)]
    rows, hist = [], []
    for e in range(n_ev):
        date = pd.Timestamp("2010-01-01") + pd.Timedelta(days=int(e * rng.integers(20, 200)))
        for b in range(int(rng.integers(1, 5))):
            a, c = rng.choice(names, 2, replace=False)
            rows.append({"fight_url": f"u{e}-{b}", "event_date": date, "event_name": f"E{e}", "fighter_a": a,
                         "fighter_b": c, "winner": rng.choice([a, c]), "weight_class": rng.choice(classes)})
            for s in (a, c):
                # Small integer mu forces ties, which the (-mu, name) tie-break must resolve.
                hist.append({"fighter": s, "event_date": date, "event_name": f"E{e}",
                             "mu_canonical": float(rng.integers(1490, 1496))})
    return pd.DataFrame(rows), pd.DataFrame(hist)


def _reference_ranks(f: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    """Sort the whole active field per card, the way the first vectorised version did."""
    f = f.copy()
    f["division"] = f["weight_class"].map(normalize_division_label)
    f = f.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    post = {(r.fighter, r.event_date, r.event_name): r.mu_canonical for r in h.itertuples()}
    state: dict[str, tuple[float, object, pd.Timestamp]] = {}
    out = []
    for (date, name), g in f.groupby(["event_date", "event_name"], sort=False):
        cutoff = date - pd.Timedelta(days=RANK_CONTEXT_ACTIVE_DAYS)
        act = sorted(((mu, d, x) for x, (mu, d, last) in state.items() if last >= cutoff), key=lambda t: (-t[0], t[2]))
        p4p = {x: i + 1.0 for i, (_, _, x) in enumerate(act)}
        board: dict[str, dict[str, float]] = {}
        for _, d, x in act:
            if isinstance(d, str):
                board.setdefault(d, {})[x] = len(board.get(d, {})) + 1.0
        for r in g.itertuples():
            d = r.division
            row = {"fight_url": r.fight_url}
            for s, x in (("a", r.fighter_a), ("b", r.fighter_b)):
                same = isinstance(d, str) and x in state and state[x][1] == d and x in p4p
                row[f"fighter_{s}_prefight_p4p_rank"] = p4p.get(x, np.nan)
                row[f"fighter_{s}_prefight_division_rank"] = board[d][x] if same else np.nan
                row[f"fighter_{s}_prefight_division_pool"] = float(len(board[d])) if same else np.nan
            out.append(row)
        for r in g.itertuples():
            for x in (r.fighter_a, r.fighter_b):
                state[x] = (post[(x, date, name)], r.division, date)
    return pd.DataFrame(out)


def test_ranking_context_ranks_and_pools_match_a_full_sort():
    for seed in range(5):
        # No missing classes: the reference does not model the career-vote division fill.
        f, h = _fights(seed, classes=[w for w in _WC if w])
        got = prefight_ranking_context(f, h)
        ref = _reference_ranks(f, h)
        assert got["fight_url"].tolist() == ref["fight_url"].tolist()
        for col in ref.columns.drop("fight_url"):
            assert np.array_equal(got[col].to_numpy(), ref[col].to_numpy(), equal_nan=True), (seed, col)


def _reference_weight_class_context(fights: pd.DataFrame) -> pd.DataFrame:
    """The iterrows implementation this replaced."""
    f = fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["division"] = f["weight_class"].map(normalize_division_label)
    f = f.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    prev: dict = {}
    rows = []
    for _, group in f.groupby(["event_date", "event_name"], sort=False):
        for _, row in group.iterrows():
            cur = _division_limit(row.get("division"))
            a, b = row.get("fighter_a"), row.get("fighter_b")
            a_prev, b_prev = prev.get(a), prev.get(b)
            a_move = _movement_label(_division_limit(a_prev), cur)
            b_move = _movement_label(_division_limit(b_prev), cur)
            rows.append({
                "fight_url": row.get("fight_url"),
                "fighter_a_previous_division": a_prev, "fighter_b_previous_division": b_prev,
                "fighter_a_previous_weight_limit_lb": _division_limit(a_prev),
                "fighter_b_previous_weight_limit_lb": _division_limit(b_prev),
                "fighter_current_weight_limit_lb": cur,
                "fighter_a_weight_class_move": a_move, "fighter_b_weight_class_move": b_move,
                "fighter_a_weight_class_change_fight": a_move in {"up", "down"},
                "fighter_b_weight_class_change_fight": b_move in {"up", "down"},
            })
        for _, row in group.iterrows():
            if not _division_limit(row.get("division")):
                continue
            for side in ("fighter_a", "fighter_b"):
                if row.get(side):
                    prev[row.get(side)] = row.get("division")
    return pd.DataFrame(rows, columns=list(rows[0]) if rows else None)


def test_weight_class_context_matches_the_iterrows_loop_bit_for_bit():
    for seed in range(5):
        f, _ = _fights(seed)
        got = prefight_weight_class_context(f.assign(division=f["weight_class"].map(normalize_division_label)))
        ref = _reference_weight_class_context(f)
        assert list(got.columns) == list(ref.columns)
        assert (got.dtypes == ref.dtypes).all()
        assert got.equals(ref) and got.index.equals(ref.index)


def test_weight_class_context_drops_null_event_keys_like_groupby():
    f, _ = _fights(0, n_ev=10)
    f.loc[3, "event_name"] = np.nan
    f.loc[5, "event_date"] = pd.NaT
    got = prefight_weight_class_context(f.assign(division=f["weight_class"].map(normalize_division_label)))
    ref = _reference_weight_class_context(f)
    assert len(got) == len(f) - 2 and got.equals(ref)
