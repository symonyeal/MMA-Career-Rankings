"""Unit tests for the WHR drift-prior backtest harness (no heavy snapshot fit)."""
import numpy as np
import pandas as pd
import pytest

from ratings.whr_backtest import _decided_bouts, backtest_w2, elo_win_prob


def test_elo_win_prob_symmetry_and_monotonicity():
    assert elo_win_prob(1500, 1500) == pytest.approx(0.5)
    assert elo_win_prob(1700, 1500) > 0.5
    assert elo_win_prob(1300, 1500) < 0.5
    # symmetric: P(a) + P(b) == 1
    assert elo_win_prob(1700, 1500) + elo_win_prob(1500, 1700) == pytest.approx(1.0)


def test_variance_attenuation_shrinks_toward_coinflip():
    base = elo_win_prob(1700, 1500)
    # adding posterior variance with lambda>0 pulls the prediction toward 0.5
    shrunk = elo_win_prob(1700, 1500, var_a=2.0, var_b=2.0, var_lambda=1.0)
    assert 0.5 < shrunk < base
    # lambda=0 ignores variance entirely
    assert elo_win_prob(1700, 1500, var_a=9.0, var_b=9.0, var_lambda=0.0) == pytest.approx(base)


def test_whr_returns_variance_column():
    from ratings.whr import run_whr
    fights = _synthetic_history(6)
    hist = run_whr(fights, iterations=8, return_variance=True)
    assert "var_whr" in hist.columns
    assert (hist["var_whr"] > 0).all()


def test_decided_bouts_filters_and_labels():
    fights = pd.DataFrame({
        "event_date": ["2020-01-01", "2020-02-01", "2020-03-01"],
        "event_name": ["E1", "E2", "E3"],
        "fighter_a": ["A", "C", "E"],
        "fighter_b": ["B", "D", "F"],
        "winner": ["A", "C", None],          # E3 has no winner -> dropped
        "is_draw": [False, True, False],     # E2 is a draw -> dropped
        "is_excluded": [False, False, False],
    })
    out = _decided_bouts(fights)
    assert list(out["event_name"]) == ["E1"]
    assert int(out.iloc[0]["_y_a"]) == 1


def _synthetic_history(n_events=12):
    """A clear favorite (Ace) beats everyone; underdogs trade among themselves."""
    rng = np.random.default_rng(0)
    rows = []
    others = [f"U{i}" for i in range(6)]
    for e in range(n_events):
        date = pd.Timestamp("2018-01-01") + pd.Timedelta(days=60 * e)
        opp = others[e % len(others)]
        rows.append({"event_date": date, "event_name": f"E{e}",
                     "fighter_a": "Ace", "fighter_b": opp, "winner": "Ace",
                     "is_draw": False, "is_nc": False, "is_excluded": False})
        x, y = others[e % 6], others[(e + 3) % 6]
        rows.append({"event_date": date, "event_name": f"E{e}",
                     "fighter_a": x, "fighter_b": y, "winner": x,
                     "is_draw": False, "is_nc": False, "is_excluded": False})
    return pd.DataFrame(rows)


def test_backtest_w2_returns_scored_grid():
    fights = _synthetic_history()
    res = backtest_w2(
        fights, [0.0002, 0.0008], var_lambdas=[0.0, 1.0],
        n_eval_events=4, iterations=8, min_prior_fights=1,
    )
    assert set(res.columns) == {"w2", "var_lambda", "brier", "log_loss", "n"}
    assert len(res) == 4  # 2 w2 x 2 lambda
    assert res["n"].max() > 0
    # sorted best-first by log_loss
    assert res["log_loss"].is_monotonic_increasing
    # favorite is predicted to win -> Brier should be well below the 0.25 coin-flip floor
    assert res["brier"].min() < 0.25
