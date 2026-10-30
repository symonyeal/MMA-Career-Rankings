"""Captured-output and event consistency checks for the shared Glicko update."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ratings._glicko2 import Glicko2
from ratings.glicko2_engine import RatingEngine, WeightedRatingEngine

CAPTURE = json.loads((Path(__file__).parent / "fixtures/rating_results.json").read_text())


def test_engine_scalar_matches_captured_original_bits():
    env = Glicko2(tau=0.5)
    rating = env.create_rating(1700, 80, 0.06)
    opponent = env.create_rating(1450, 120, 0.07)

    result = env.rate(rating, [(1.0, opponent), (0.5, env.create_rating())])

    assert tuple(value.hex() for value in (result.mu, result.phi, result.sigma)) == (
        "0x1.a9a05e7650b2fp+10",
        "0x1.3aa98085cea95p+6",
        "0x1.eb7ec93a19525p-5",
    )


def test_engine_unit_weights_preserve_event_history_bits():
    bouts = [
        {"fighter_a": "A", "fighter_b": "B", "winner": "A", "is_draw": False},
        {"fighter_a": "B", "fighter_b": "C", "winner": None, "is_draw": True},
    ]
    regular = RatingEngine(tau=0.5)
    weighted = WeightedRatingEngine(tau=0.5)
    regular.process_event(pd.Timestamp("2020-01-01"), "E", bouts)
    weighted.process_event(
        pd.Timestamp("2020-01-01"),
        "E",
        [{**bout, "weight_a": 1.0, "weight_b": 1.0} for bout in bouts],
    )

    for fighter in regular.states:
        a = regular.states[fighter].canonical
        b = weighted.states[fighter].rating
        assert tuple(value.hex() for value in (a.mu, a.phi, a.sigma)) == tuple(
            value.hex() for value in (b.mu, b.phi, b.sigma)
        )


def test_engine_zero_weight_remains_inactive_period():
    env = Glicko2(tau=0.5)
    rating = env.create_rating(1600, 90, 0.06)
    opponent = env.create_rating(1450, 120, 0.07)

    inactive = env.rate(rating, [])
    zero_weight = env.rate_weighted(rating, [(1.0, opponent, 0.0)])

    assert tuple(value.hex() for value in (inactive.mu, inactive.phi, inactive.sigma)) == tuple(
        value.hex() for value in (zero_weight.mu, zero_weight.phi, zero_weight.sigma)
    )


@pytest.mark.parametrize("case", CAPTURE["glicko"])
def test_engine_matches_captured_results(case):
    center = case["center"]
    env = Glicko2(mu=center, tau=0.37)
    rating = env.create_rating(center + 85.25, 123.5, 0.058)
    series = [(s, env.create_rating(mu, phi), w) for s, mu, phi, w in case["series"]]
    actual = env.rate_weighted(rating, series)
    np.testing.assert_allclose([actual.mu, actual.phi, actual.sigma], case["expected"], rtol=1e-14)


@pytest.mark.parametrize("case", CAPTURE["inactivity"])
def test_engine_inactivity_matches_captured_results(case):
    env = Glicko2()
    rating = env.create_rating(1414.237850143128, 286.7122785287158, 0.05999910436198874)
    actual = env.inflate(rating, case["periods"])
    np.testing.assert_allclose([actual.mu, actual.phi, actual.sigma], case["expected"], rtol=1e-14)
