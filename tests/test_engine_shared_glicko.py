"""Captured-output and exact parity checks for the shared Glicko update."""

import os
from pathlib import Path

import pandas as pd
import pytest

from ratings._glicko2 import Glicko2
from ratings.fights import iter_events
from ratings.glicko2_engine import RatingEngine, WeightedRatingEngine


@pytest.fixture(scope="module")
def native():
    try:
        import rating_rs
    except ImportError:
        if os.environ.get("RATING_RS_REQUIRED") == "1":
            pytest.fail("rating_rs is required in this environment")
        pytest.skip("rating_rs is not installed")
    return rating_rs


def test_engine_scalar_matches_captured_original_bits():
    env = Glicko2(tau=0.5, backend="python")
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


@pytest.mark.parametrize("center", [1500.0, 1375.0])
@pytest.mark.parametrize(
    "results",
    [
        [],
        [(1.0, 1600.0, 90.0, 0.0)],
        [(1.0, 1600.0, 90.0, 1.0)],
        [(1.0, 1600.0, 90.0, 0.7), (0.0, 1450.0, 120.0, 1.2),
         (0.5, 1525.0, 80.0, 0.9)],
    ],
)
def test_engine_rust_rate_matches_python_bits(native, center, results):
    python = Glicko2(mu=center, tau=0.37, epsilon=1e-6, backend="python")
    rust = Glicko2(mu=center, tau=0.37, epsilon=1e-6, backend="rust")
    rating = python.create_rating(center + 85.25, 123.5, 0.058)
    series_python = [(score, python.create_rating(mu, phi), weight) for score, mu, phi, weight in results]
    series_rust = [(score, rust.create_rating(mu, phi), weight) for score, mu, phi, weight in results]

    expected = python.rate_weighted(rating, series_python)
    actual = rust.rate_weighted(rating, series_rust)

    assert tuple(value.hex() for value in (actual.mu, actual.phi, actual.sigma)) == tuple(
        value.hex() for value in (expected.mu, expected.phi, expected.sigma)
    )


@pytest.mark.parametrize("weighted", [False, True])
def test_engine_rust_history_matches_python_on_snapshot(native, weighted):
    from ratings.fights import load_fight_table
    from ratings.scope import DEFAULT_PUBLISHED_SCOPE

    snapshot = Path(__file__).resolve().parents[1] / "data/snapshots/2026-10-24"
    fights = load_fight_table(snapshot, scope=DEFAULT_PUBLISHED_SCOPE)
    assert len(fights) > 0, "the backend comparison needs the published fight corpus"
    columns = ["fighter_a", "fighter_b", "winner", "is_draw", "method_score_winner"]
    if weighted:
        fights = fights.assign(weight_a=0.7, weight_b=1.1)
        columns += ["weight_a", "weight_b"]
        python = WeightedRatingEngine(score_mode="method", backend="python")
        rust = WeightedRatingEngine(score_mode="method", backend="rust")
    else:
        python, rust = RatingEngine(backend="python"), RatingEngine(backend="rust")
    for date, name, bouts in iter_events(fights, columns):
        python.process_event(date, name, bouts)
        rust.process_event(date, name, bouts)

    pd.testing.assert_frame_equal(python.history_df(), rust.history_df(), check_exact=True)
    expected = python.current_table().sort_values("fighter").reset_index(drop=True)
    actual = rust.current_table().sort_values("fighter").reset_index(drop=True)
    pd.testing.assert_frame_equal(expected, actual, check_exact=True)


@pytest.mark.parametrize("periods", [0, 1, 3, 120])
def test_engine_rust_inactivity_preserves_runtime_pow_bits(native, periods):
    python, rust = Glicko2(backend="python"), Glicko2(backend="rust")
    rating = python.create_rating(1414.237850143128, 286.7122785287158, 0.05999910436198874)
    expected, actual = python.inflate(rating, periods), rust.inflate(rating, periods)
    assert (actual.mu, actual.phi, actual.sigma) == (expected.mu, expected.phi, expected.sigma)
