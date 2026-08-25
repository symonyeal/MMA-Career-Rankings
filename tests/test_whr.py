"""Whole-History Rating smoother (ratings/whr.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ratings.whr import _build_appearances, _thomas, project_age_rating, run_whr


def _chain_fights(n_events: int = 15) -> pd.DataFrame:
    """A always beats B, B always beats C, repeated over many events."""
    base = pd.Timestamp("2015-01-01")
    rows = []
    for i in range(n_events):
        d = base + pd.Timedelta(days=120 * i)
        rows.append(dict(fighter_a="A", fighter_b="B", winner="A", is_draw=False,
                         event_date=d, event_name=f"E{i}a"))
        rows.append(dict(fighter_a="B", fighter_b="C", winner="B", is_draw=False,
                         event_date=d, event_name=f"E{i}b"))
    return pd.DataFrame(rows)


def test_thomas_solves_tridiagonal_system():
    # A symmetric tridiagonal system with a known solution.
    diag = np.array([2.0, 3.0, 2.0])
    off = np.array([1.0, 1.0])
    x_true = np.array([1.0, -1.0, 2.0])
    # rhs = A @ x_true
    rhs = np.array([
        diag[0] * x_true[0] + off[0] * x_true[1],
        off[0] * x_true[0] + diag[1] * x_true[1] + off[1] * x_true[2],
        off[1] * x_true[1] + diag[2] * x_true[2],
    ])
    x = _thomas(diag, off, rhs)
    assert np.allclose(x, x_true, atol=1e-9)


def test_whr_recovers_monotonic_ordering():
    hist = run_whr(_chain_fights(), iterations=60)
    last = hist.sort_values("event_date").groupby("fighter")["mu_whr"].last()
    assert last["A"] > last["B"] > last["C"]


def test_whr_history_shape_matches_rating_history_contract():
    hist = run_whr(_chain_fights())
    assert list(hist.columns) == ["fighter", "event_date", "event_name", "mu_whr"]
    # one row per fighter-appearance: 2 fighters per bout, 30 bouts.
    assert len(hist) == 60
    assert hist["mu_whr"].notna().all()


def test_whr_smoother_is_stable_across_late_career():
    """A dominant fighter's rating should plateau, not drift, once established."""
    hist = run_whr(_chain_fights(20), iterations=60)
    a_traj = hist[hist["fighter"] == "A"].sort_values("event_date")["mu_whr"].to_numpy()
    # last third of the career should be near-flat
    tail = a_traj[len(a_traj) // 3:]
    assert tail.std() < 5.0


def test_whr_empty_input_returns_empty_frame():
    out = run_whr(pd.DataFrame())
    assert list(out.columns) == ["fighter", "event_date", "event_name", "mu_whr"]
    assert out.empty


def test_quality_column_is_inert_unless_explicitly_selected():
    fights = _chain_fights(1)
    fights["quality_score_winner"] = 0.6

    implicit_scores = _build_appearances(fights)[3]
    explicit_scores = _build_appearances(
        fights, winner_score_col="quality_score_winner"
    )[3]

    assert implicit_scores.tolist() == [1.0, 0.0, 1.0, 0.0]
    assert explicit_scores.tolist() == pytest.approx([0.6, 0.4, 0.6, 0.4])


def test_whr_rejects_side_specific_likelihood_weights():
    fights = _chain_fights(1)
    fights["weight_a"] = 1.2
    fights["weight_b"] = 0.8

    with pytest.raises(ValueError, match="one shared likelihood weight"):
        run_whr(fights)


# ---------------------------------------------------------------------------
# Prior mass. An undefeated record has no interior maximum-likelihood rating,
# so what stops the climb decides the whole top of the board.


def _field(n_events: int = 30) -> list[dict]:
    """A churning mid-field that gives the scale something to be measured against."""
    base = pd.Timestamp("2012-01-01")
    rows = []
    for i in range(n_events):
        d = base + pd.Timedelta(days=90 * i)
        a, b = f"M{i % 6}", f"M{(i + 3) % 6}"
        rows.append(dict(fighter_a=a, fighter_b=b, winner=a if i % 2 else b,
                         is_draw=False, event_date=d, event_name=f"F{i}"))
    return rows


def _undefeated(name: str, wins: int) -> list[dict]:
    base = pd.Timestamp("2012-02-01")
    return [
        dict(fighter_a=name, fighter_b=f"M{i % 6}", winner=name, is_draw=False,
             event_date=base + pd.Timedelta(days=90 * i), event_name=f"U{name}{i}")
        for i in range(wins)
    ]


def test_undefeated_rating_grows_with_the_evidence_behind_it():
    """One win must not rate like ten.

    Before virtual games the prior was applied once per appearance, so its mass
    grew with career length exactly as fast as the likelihood and the stopping
    point was a constant. On the real database that put a fighter with a single
    UFC bout at the top of the entire ranking.
    """
    fights = pd.DataFrame(_field() + _undefeated("One", 1) + _undefeated("Ten", 10))
    hist = run_whr(fights, iterations=80)
    last = hist.sort_values("event_date").groupby("fighter")["mu_whr"].last()
    assert last["Ten"] > last["One"] + 50.0


def test_prior_mass_does_not_scale_with_career_length():
    """Doubling a fighter's undefeated record must move them, not stall them."""
    ladder = {}
    for wins in (2, 5, 12):
        fights = pd.DataFrame(_field() + _undefeated("X", wins))
        hist = run_whr(fights, iterations=80)
        ladder[wins] = float(
            hist[hist["fighter"].eq("X")].sort_values("event_date")["mu_whr"].iloc[-1]
        )
    assert ladder[2] < ladder[5] < ladder[12]


def test_virtual_games_pull_a_thin_record_toward_the_field():
    fights = pd.DataFrame(_field() + _undefeated("X", 1))
    strong = run_whr(fights, virtual_games=8.0, iterations=80)
    weak = run_whr(fights, virtual_games=0.0, iterations=80)
    x_strong = strong[strong["fighter"].eq("X")]["mu_whr"].iloc[-1]
    x_weak = weak[weak["fighter"].eq("X")]["mu_whr"].iloc[-1]
    assert x_strong < x_weak


def test_virtual_games_are_unbiased_for_a_balanced_record():
    """The prior must not push an even record up or down."""
    base = pd.Timestamp("2012-01-01")
    rows = [
        dict(fighter_a="Even", fighter_b=f"M{i % 6}", winner="Even" if i % 2 else f"M{i % 6}",
             is_draw=False, event_date=base + pd.Timedelta(days=90 * i), event_name=f"B{i}")
        for i in range(10)
    ]
    fights = pd.DataFrame(_field() + rows)
    with_prior = run_whr(fights, virtual_games=6.0, iterations=80)
    field_mean = with_prior["mu_whr"].mean()
    even = with_prior[with_prior["fighter"].eq("Even")]["mu_whr"].iloc[-1]
    assert abs(even - field_mean) < 60.0


def test_negative_virtual_games_are_rejected():
    with pytest.raises(ValueError):
        run_whr(_chain_fights(), virtual_games=-1.0)


def test_age_drift_is_explicit_and_auditable():
    fights = _chain_fights(12)
    with pytest.raises(ValueError, match="requires birth_dates"):
        run_whr(fights, age_drift=True)

    history = run_whr(
        fights,
        birth_dates={
            "A": pd.Timestamp("1994-01-01"),
            "B": pd.Timestamp("1984-01-01"),
            "C": pd.Timestamp("1974-01-01"),
        },
        age_drift=True,
    )

    assert {"age_years", "prior_drift_elo_per_year"} <= set(history.columns)
    assert history["age_years"].notna().all()
    # The under-24 bin is the identifying baseline, never a youth bonus.
    young = history[history["age_years"] < 24]
    assert np.allclose(young["prior_drift_elo_per_year"], 0.0)
    assert len(history.attrs["age_drift_elo_per_year"]) == 8


def test_age_projection_drops_score_across_inactivity_and_crosses_bins():
    rates = [0.0, -1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0]
    projected = project_age_rating(
        1800.0,
        last_date="2020-01-01",
        target_date="2024-01-01",
        birth_date="1984-01-01",  # age 36 -> 40, crossing the age-39 boundary
        drift_elo_per_year=rates,
    )
    assert projected < 1800.0
    assert projected == pytest.approx(1779.0, abs=0.1)


def test_age_projection_is_neutral_without_identified_dates():
    assert project_age_rating(
        1800.0,
        last_date="2020-01-01",
        target_date="2024-01-01",
        birth_date=None,
        drift_elo_per_year=[-10.0] * 8,
    ) == pytest.approx(1800.0)
