"""Unit tests for the WHR drift-prior backtest harness (no heavy snapshot fit)."""
import pandas as pd
import pytest

from ratings.whr import elo_win_prob
from ratings.whr_backtest import backtest_w2
from ratings.fights import decided_bouts


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
    out = decided_bouts(fights)
    assert list(out["event_name"]) == ["E1"]
    assert int(out.iloc[0]["_y_a"]) == 1


def _synthetic_history(n_events=12):
    """A clear favorite (Ace) beats everyone; underdogs trade among themselves."""
    rows = []
    others = [f"U{i}" for i in range(6)]
    for e in range(n_events):
        date = pd.Timestamp("2018-01-01") + pd.Timedelta(days=60 * e)
        opp = others[e % len(others)]
        rows.append({"event_date": date, "event_name": f"E{e}",
                     "fighter_a": "Ace", "fighter_b": opp, "winner": "Ace",
                     "is_draw": False, "is_nc": False, "is_excluded": False, "method_score_winner": 1.0})
        x, y = others[e % 6], others[(e + 3) % 6]
        rows.append({"event_date": date, "event_name": f"E{e}",
                     "fighter_a": x, "fighter_b": y, "winner": x,
                     "is_draw": False, "is_nc": False, "is_excluded": False, "method_score_winner": 1.0})
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


def _bout(date, winner="A", score=0.8, draw=False):
    return {"event_date": pd.Timestamp(date), "event_name": date,
            "fighter_a": "A", "fighter_b": "B", "winner": winner,
            "is_draw": draw, "is_nc": False, "is_excluded": False, "method_score_winner": score}


def test_backtest_default_fits_method_likelihood():
    fights = pd.DataFrame([_bout("2020-01-01", score=0.5), _bout("2021-01-01")])

    out = backtest_w2(fights, [0.0004], n_eval_events=1, iterations=20, min_prior_fights=1)

    assert out.loc[0, "n"] == 1
    assert out.loc[0, "brier"] == pytest.approx(0.25)


def test_backtest_trains_on_draws_and_counts_their_appearances():
    fights = pd.DataFrame([_bout("2020-01-01", winner=None, draw=True), _bout("2021-01-01")])

    out = backtest_w2(fights, [0.0004], n_eval_events=1, iterations=20, min_prior_fights=1)

    assert out.loc[0, "n"] == 1
    assert out.loc[0, "brier"] == pytest.approx(0.25)


def test_backtest_requires_production_score_column():
    fights = pd.DataFrame([_bout("2020-01-01"), _bout("2021-01-01")]).drop(columns="method_score_winner")

    with pytest.raises(ValueError, match="winner-score column"):
        backtest_w2(fights, [0.0004], n_eval_events=1, min_prior_fights=1)


def test_backtest_binary_model_requires_explicit_research_option():
    fights = pd.DataFrame([_bout("2020-01-01", score=0.5), _bout("2021-01-01")])

    out = backtest_w2(fights, [0.0004], binary_research=True,
                      n_eval_events=1, iterations=20, min_prior_fights=1)

    assert out.loc[0, "n"] == 1
    assert out.loc[0, "brier"] < 0.25


def test_backtest_projects_age_drift_to_forecast_date():
    train = [_bout("2017-01-01"), _bout("2018-01-01"),
             _bout("2019-01-01", winner="B"), _bout("2020-01-01", winner="B")]
    scores = []
    for date in ["2020-02-01", "2021-01-01"]:
        fights = pd.DataFrame([*train, _bout(date)])
        out = backtest_w2(fights, [0.0004], birth_dates={"A": pd.Timestamp("1983-01-01")},
                          n_eval_events=1, iterations=30, min_prior_fights=1)
        assert out.loc[0, "n"] == 1
        scores.append(out.loc[0, "brier"])

    # The same declining fighter becomes less likely to win after a longer gap.
    assert scores[1] > scores[0]
