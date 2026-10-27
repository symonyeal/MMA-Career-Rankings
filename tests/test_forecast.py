import numpy as np
import pandas as pd

from ratings import forecast


def test_fit_is_antisymmetric_and_optimal():
    rng = np.random.default_rng(0)
    A = rng.normal(size=(400, 3))
    y = (A @ [1.0, -0.5, 0.0] + rng.logistic(size=400) > 0).astype(float)
    w = forecast.fit(A, y)
    np.testing.assert_allclose(forecast.prob(A, w) + forecast.prob(-A, w), 1, atol=1e-12)
    # zero gradient of C·Σ log loss + ½‖w‖² over the rows and their mirror
    M, z = np.vstack([A, -A]), np.r_[y, 1 - y]
    np.testing.assert_allclose(forecast.C * M.T @ (forecast.prob(M, w) - z) + w, 0, atol=1e-8)


def test_record_reads_only_earlier_dates():
    d = pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01"])
    cb = pd.DataFrame({"fighter_a": ["x", "x", "x"], "fighter_b": ["p", "q", "r"], "event_date": d,
                       "winner": ["x", "q", "x"], "loser": ["p", "x", "r"], "is_draw": False,
                       "method_class": ["Decision - Unanimous", "KO/TKO", "Submission"]})
    r = forecast._record(cb).query("f == 'x'").set_index("event_date")
    assert r["npro"].tolist() == [0, 1, 2]
    assert r["wpro"].tolist() == [0, 1, 1]
    assert r["streak"].tolist() == [0, 1, -1]
    assert r["ko2"].tolist() == [0, 0, 1]
    assert np.isnan(r["lay"].iloc[0]) and r["lay"].iloc[1] == 152


def test_forecast_history_leaves_out_promotions_recorded_by_career_page():
    assert {"UFC", "PRIDE", "WEC", "Strikeforce", "Affliction", "Bellator", "RIZIN"} <= forecast.ROSTER
    assert not {"Deep", "Pancrase", "KOTC", "Shooto"} & forecast.ROSTER
