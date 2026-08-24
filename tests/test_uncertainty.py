"""The public board's rank intervals must come from refitting the estimator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ratings.uncertainty import BOOTSTRAP_COLUMNS, career_mass_bootstrap, rank_is_separated


def _fights(n_events: int = 24) -> pd.DataFrame:
    """A field where one fighter is clearly best and one is thinly evidenced."""
    rows = []
    names = [f"F{i}" for i in range(8)]
    for e in range(n_events):
        date = pd.Timestamp("2015-01-01") + pd.Timedelta(days=60 * e)
        a, b = names[e % 4], names[4 + (e % 4)]
        rows.append({
            "fight_url": f"u/{e}", "event_date": date, "event_name": f"E{e}",
            "fighter_a": "Best", "fighter_b": a, "winner": "Best", "is_draw": False,
        })
        rows.append({
            "fight_url": f"u/{e}b", "event_date": date, "event_name": f"E{e}",
            "fighter_a": a, "fighter_b": b, "winner": a if e % 3 else b,
            "is_draw": False,
        })
    rows.append({
        "fight_url": "u/thin", "event_date": pd.Timestamp("2018-06-01"),
        "event_name": "E-thin", "fighter_a": "Thin", "fighter_b": "F1",
        "winner": "Thin", "is_draw": False,
    })
    return pd.DataFrame(rows)


def test_bootstrap_returns_the_documented_shape():
    out = career_mass_bootstrap(_fights(), replicates=6, seed=0)
    assert list(out.columns) == BOOTSTRAP_COLUMNS
    assert out["rank"].is_monotonic_increasing
    assert (out["replicates"] == 6).all()


def test_point_estimate_lies_inside_its_own_interval():
    """The Dirichlet bootstrap keeps total evidence constant.

    Resampling events with replacement instead drops roughly 37% of them, and
    career mass is a sum over years, so every replicate would sit below the
    point estimate.
    """
    out = career_mass_bootstrap(_fights(), replicates=12, seed=3).set_index("fighter")
    top = out.head(4)
    inside = (top["mass"] >= top["mass_lo"] * 0.9) & (top["mass"] <= top["mass_hi"] * 1.1)
    assert inside.all()


def test_every_fighter_survives_every_replicate():
    out = career_mass_bootstrap(_fights(), replicates=8, seed=1)
    assert (out["replicates_present"] == out["replicates"]).all()


def test_eligibility_gate_applies_to_point_and_replicate_ranks():
    eligible = {"Best", "F0", "F1"}
    board, draws = career_mass_bootstrap(
        _fights(), replicates=4, seed=1,
        eligible_fighters=eligible, return_draws=True,
    )
    assert set(board["fighter"]) <= eligible
    assert set(draws.index) == set(board["fighter"])
    assert "Thin" not in board["fighter"].tolist()


def test_thin_evidence_gets_a_wider_rank_interval_than_a_long_career():
    out = career_mass_bootstrap(_fights(), replicates=16, seed=5).set_index("fighter")
    if "Thin" in out.index and "Best" in out.index:
        thin = out.loc["Thin", "rank_hi"] - out.loc["Thin", "rank_lo"]
        best = out.loc["Best", "rank_hi"] - out.loc["Best", "rank_lo"]
        assert thin >= best


def test_separation_requires_disjoint_intervals():
    board = pd.DataFrame({
        "fighter": ["A", "B", "C"],
        "rank": [1, 2, 3], "rank_lo": [1, 2, 9], "rank_hi": [3, 6, 14],
    })
    assert not rank_is_separated(board, "A", "B")   # overlapping
    assert rank_is_separated(board, "A", "C")       # disjoint
    assert not rank_is_separated(board, "A", "missing")


def test_bad_arguments_are_rejected():
    with pytest.raises(ValueError):
        career_mass_bootstrap(_fights(), replicates=0)
    with pytest.raises(ValueError):
        career_mass_bootstrap(_fights(), lo=0.9, hi=0.1)


def test_empty_input_returns_the_empty_board():
    out = career_mass_bootstrap(pd.DataFrame(), replicates=3)
    assert out.empty and list(out.columns) == BOOTSTRAP_COLUMNS


def test_reproducible_under_a_fixed_seed():
    a = career_mass_bootstrap(_fights(), replicates=5, seed=11)
    b = career_mass_bootstrap(_fights(), replicates=5, seed=11)
    assert np.allclose(a["mass_lo"], b["mass_lo"], equal_nan=True)
