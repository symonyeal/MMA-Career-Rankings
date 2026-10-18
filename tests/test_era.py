"""Era-adjusted ratings (ratings.era) and the powered score parts (legacy_resume.legacy_points)."""
import numpy as np
import pandas as pd
import pytest

from ratings.era import ERA_COL, era_shift, with_era
from ratings.legacy_resume import (
    LEGACY_ACHIEVEMENT_WEIGHT as a, LEGACY_QUALITY_SKILL_SHARE as s, PUBLIC_LEGACY_DISPLAY_SCALE as k, _scale,
    legacy_points,
)

YEARS = range(2000, 2012)


def _history(rng, n=200, prefix="m", drift=None):
    """n fighters at fixed levels r_f, one bout a year, observed on a scale drifting by drift(y)."""
    r = rng.normal(1500.0, 150.0, n)
    drift = drift or (lambda y: 0.0)
    return pd.DataFrame([{"fighter": f"{prefix}{i}", "event_date": pd.Timestamp(f"{y}-06-01"),
                          "mu_whr": r[i] + drift(y)} for y in YEARS for i in range(n)])


def test_a_planted_drift_is_removed_up_to_a_constant():
    """Certificate: levels fixed, scale drifting 9 points a year plus noise; mu_era recovers the levels."""
    rng = np.random.default_rng(0)
    c = dict(zip(YEARS, 9.0 * np.arange(len(YEARS)) + rng.normal(0, 20, len(YEARS))))
    h0, h = _history(np.random.default_rng(1)), _history(np.random.default_rng(1), drift=c.get)
    gender = pd.Series("M", index=h["fighter"].unique())
    gap = with_era(h, gender)[ERA_COL] - with_era(h0, gender)[ERA_COL]
    assert gap.max() - gap.min() == pytest.approx(0.0, abs=1e-9)


def test_the_shift_averages_zero_over_fighter_years():
    rng = np.random.default_rng(2)
    h = _history(rng, drift=lambda y: 5.0 * (y - 2000) ** 1.5)
    d = era_shift(h, pd.Series("M", index=h["fighter"].unique()))
    assert d.groupby([h["fighter"], h["event_date"].dt.year]).first().mean() == pytest.approx(0.0, abs=1e-9)


def test_one_gender_cannot_move_the_other():
    rng = np.random.default_rng(3)
    men, women = _history(rng), _history(rng, n=80, prefix="w")
    gender = pd.Series({**{f: "M" for f in men["fighter"]}, **{f: "F" for f in women["fighter"]}})
    base = with_era(pd.concat([men, women], ignore_index=True), gender)
    moved = women.assign(mu_whr=women["mu_whr"] + 30.0 * (women["event_date"].dt.year - 2000))
    shifted = with_era(pd.concat([men, moved], ignore_index=True), gender)
    m = base["fighter"].str.startswith("m")
    assert np.allclose(base.loc[m, ERA_COL], shifted.loc[m, ERA_COL])


def test_power_one_is_the_linear_score_and_a_typical_part_is_worth_its_weight_at_any_power():
    rng = np.random.default_rng(4)
    T, K, R = (pd.Series(rng.gamma(2.0, 1.0, 150)) for _ in range(3))
    linear = k * (a * _scale(T) + (1 - a) * (s * _scale(K) + (1 - s) * _scale(R)))
    assert np.allclose(sum(legacy_points(T, K, R, p=1.0)), linear)
    one = pd.Series([1.0] * 100 + [0.0])
    for p in (0.5, 1.0):
        assert legacy_points(one, one, one, p=p)[0][0] == pytest.approx(k * a)
