"""Weighted Glicko engine + 5-stream rate_snapshot snapshot integration.

Three layers:

1. Scalar regression — ``_rate_weighted`` with all weights = 1.0 reproduces
   the vendored ``Glicko2.rate()`` output (within fp tolerance).
2. Engine regression — ``WeightedRatingEngine`` with unit weights produces
   the same ``mu`` trajectory as ``RatingEngine``'s ``mu_canonical`` and
   ``mu_method``.
3. Snapshot smoke — ``ratings.rate_snapshot.run()`` produces the new
   5-stream column set; with ``odds_lines.parquet`` present the
   performance sleeve registers movement vs the plain method baseline.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ratings._glicko2 import Glicko2
from ratings.glicko2_engine import (
    DEFAULT_TAU,
    RatingEngine,
    WeightedRatingEngine,
    _rate_weighted,
)


# ---------------------------------------------------------------------------
# Scalar regression: unit weights == canonical Glicko2.rate()

def test_rate_weighted_unit_weights_equals_canonical():
    env = Glicko2(tau=DEFAULT_TAU)
    r0 = env.create_rating()
    opp1 = env.create_rating(mu=1600, phi=100)
    opp2 = env.create_rating(mu=1400, phi=200)

    canonical_series = [(1.0, opp1), (0.0, opp2)]
    weighted_series = [(1.0, opp1, 1.0), (0.0, opp2, 1.0)]

    expected = env.rate(r0, canonical_series)
    actual = _rate_weighted(env, r0, weighted_series)

    assert actual.mu == pytest.approx(expected.mu, abs=1e-9)
    assert actual.phi == pytest.approx(expected.phi, abs=1e-9)
    assert actual.sigma == pytest.approx(expected.sigma, abs=1e-9)


def test_rate_weighted_empty_series_matches_canonical_inactive_period():
    env = Glicko2(tau=DEFAULT_TAU)
    r0 = env.create_rating(mu=1500, phi=250)
    expected = env.rate(r0, [])
    actual = _rate_weighted(env, r0, [])
    assert actual.mu == pytest.approx(expected.mu, abs=1e-9)
    assert actual.phi == pytest.approx(expected.phi, abs=1e-9)
    assert actual.sigma == pytest.approx(expected.sigma, abs=1e-9)


def test_rate_weighted_zero_weights_acts_like_inactive_period():
    env = Glicko2(tau=DEFAULT_TAU)
    r0 = env.create_rating()
    opp = env.create_rating(mu=1700, phi=80)
    inactive = env.rate(r0, [])
    actual = _rate_weighted(env, r0, [(1.0, opp, 0.0)])
    assert actual.mu == pytest.approx(inactive.mu, abs=1e-9)
    assert actual.phi == pytest.approx(inactive.phi, abs=1e-9)


def test_rate_weighted_amplifies_underdog_win():
    env = Glicko2(tau=DEFAULT_TAU)
    r0 = env.create_rating()
    strong_opp = env.create_rating(mu=1800, phi=80)

    canonical_win = env.rate(r0, [(1.0, strong_opp)])
    amplified_win = _rate_weighted(env, r0, [(1.0, strong_opp, 1.20)])

    assert canonical_win.mu > 1500
    assert amplified_win.mu > canonical_win.mu


def test_rate_weighted_dampens_expected_outcome():
    env = Glicko2(tau=DEFAULT_TAU)
    r0 = env.create_rating()
    weak_opp = env.create_rating(mu=1200, phi=80)

    canonical_win = env.rate(r0, [(1.0, weak_opp)])
    damped_win = _rate_weighted(env, r0, [(1.0, weak_opp, 0.85)])

    assert canonical_win.mu > 1500
    assert 1500 < damped_win.mu < canonical_win.mu


# ---------------------------------------------------------------------------
# Engine regression: WeightedRatingEngine with unit weights matches canonical

def _three_event_bouts_canonical():
    return [
        (pd.Timestamp("2024-01-01"), "E1", [
            {"fighter_a": "Alice", "fighter_b": "Bob",
             "winner": "Alice", "is_draw": False, "method_score_winner": 1.00},
        ]),
        (pd.Timestamp("2024-02-01"), "E2", [
            {"fighter_a": "Alice", "fighter_b": "Carol",
             "winner": "Alice", "is_draw": False, "method_score_winner": 1.00},
        ]),
        (pd.Timestamp("2024-03-01"), "E3", [
            {"fighter_a": "Carol", "fighter_b": "Bob",
             "winner": "Carol", "is_draw": False, "method_score_winner": 0.85},
        ]),
    ]


def _three_event_bouts_weighted(weight: float = 1.0):
    out = []
    for event_date, event_name, bouts in _three_event_bouts_canonical():
        b_weighted = []
        for b in bouts:
            b_weighted.append({**b, "weight_a": weight, "weight_b": weight})
        out.append((event_date, event_name, b_weighted))
    return out


def test_weighted_engine_unit_weights_matches_canonical_engine():
    canon = RatingEngine(tau=DEFAULT_TAU)
    for ed, en, bouts in _three_event_bouts_canonical():
        canon.process_event(ed, en, bouts)

    weighted = WeightedRatingEngine(tau=DEFAULT_TAU)
    for ed, en, bouts in _three_event_bouts_weighted(weight=1.0):
        weighted.process_event(ed, en, bouts)

    c = canon.current_table().set_index("fighter")
    w = weighted.current_table().set_index("fighter")
    for f in ["Alice", "Bob", "Carol"]:
        assert w.loc[f, "mu"] == pytest.approx(c.loc[f, "mu_canonical"], abs=1e-9)
        assert w.loc[f, "phi"] == pytest.approx(c.loc[f, "phi_canonical"], abs=1e-9)
        assert w.loc[f, "sigma"] == pytest.approx(c.loc[f, "sigma_canonical"], abs=1e-9)


def test_weighted_engine_method_mode_matches_method_stream_with_unit_weights():
    method = RatingEngine(tau=DEFAULT_TAU)
    for ed, en, bouts in _three_event_bouts_canonical():
        method.process_event(ed, en, bouts)

    weighted = WeightedRatingEngine(tau=DEFAULT_TAU, score_mode="method")
    for ed, en, bouts in _three_event_bouts_weighted(weight=1.0):
        weighted.process_event(ed, en, bouts)

    m = method.current_table().set_index("fighter")
    w = weighted.current_table().set_index("fighter")
    for f in ["Alice", "Bob", "Carol"]:
        assert w.loc[f, "mu"] == pytest.approx(m.loc[f, "mu_method"], abs=1e-9)
        assert w.loc[f, "phi"] == pytest.approx(m.loc[f, "phi_method"], abs=1e-9)


def test_weighted_engine_amplifies_underdog_winner_rating_gain():
    canon = WeightedRatingEngine(tau=DEFAULT_TAU)
    canon.process_event(pd.Timestamp("2024-01-01"), "E", [
        {"fighter_a": "Underdog", "fighter_b": "Favorite",
         "winner": "Underdog", "is_draw": False,
         "weight_a": 1.0, "weight_b": 1.0},
    ])
    amped = WeightedRatingEngine(tau=DEFAULT_TAU)
    amped.process_event(pd.Timestamp("2024-01-01"), "E", [
        {"fighter_a": "Underdog", "fighter_b": "Favorite",
         "winner": "Underdog", "is_draw": False,
         "weight_a": 1.20, "weight_b": 1.0},
    ])
    canon_mu = canon.current_table().set_index("fighter").loc["Underdog", "mu"]
    amped_mu = amped.current_table().set_index("fighter").loc["Underdog", "mu"]
    assert amped_mu > canon_mu


def test_weighted_engine_history_records_total_weight():
    eng = WeightedRatingEngine(tau=DEFAULT_TAU)
    eng.process_event(pd.Timestamp("2024-01-01"), "E", [
        {"fighter_a": "A", "fighter_b": "B",
         "winner": "A", "is_draw": False, "weight_a": 1.15, "weight_b": 0.85},
    ])
    h = eng.history_df().set_index("fighter")
    assert h.loc["A", "total_weight"] == pytest.approx(1.15)
    assert h.loc["B", "total_weight"] == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# Snapshot integration: rate_snapshot.run() with the 5-stream architecture


def _build_synthetic_snapshot(snapshot_dir: Path) -> None:
    fights = pd.DataFrame([
        {"fight_url": "u/1", "event_url": "e/1", "event_name": "Synthetic 1",
         "event_date": pd.Timestamp("2024-01-01"), "event_location": "",
         "bout_string": "Alice vs. Bob", "fighter_a": "Alice", "fighter_b": "Bob",
         "fighter_a_outcome": "W", "fighter_b_outcome": "L",
         "winner": "Alice", "loser": "Bob",
         "is_draw": False, "is_nc": False, "is_excluded": False, "exclusion_reason": None,
         "weight_class": "Lightweight", "is_title_fight": False,
         "method_raw": "KO/TKO", "method_class": "KO/TKO", "method_score_winner": 1.0,
         "end_round": 1, "end_time_seconds": 60, "time_format": "3 Rnd (5-5-5)",
         "referee": "", "details_text": "",
         "ped_confirmed": False, "ped_flagged_fighter": None,
         "ped_confirmation_source": None, "ped_confirmation_detail": None},
        {"fight_url": "u/2", "event_url": "e/2", "event_name": "Synthetic 2",
         "event_date": pd.Timestamp("2024-02-01"), "event_location": "",
         "bout_string": "Alice vs. Carol", "fighter_a": "Alice", "fighter_b": "Carol",
         "fighter_a_outcome": "W", "fighter_b_outcome": "L",
         "winner": "Alice", "loser": "Carol",
         "is_draw": False, "is_nc": False, "is_excluded": False, "exclusion_reason": None,
         "weight_class": "Lightweight", "is_title_fight": False,
         "method_raw": "Decision - Unanimous", "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85,
         "end_round": 3, "end_time_seconds": 300, "time_format": "3 Rnd (5-5-5)",
         "referee": "", "details_text": "",
         "ped_confirmed": False, "ped_flagged_fighter": None,
         "ped_confirmation_source": None, "ped_confirmation_detail": None},
        {"fight_url": "u/3", "event_url": "e/3", "event_name": "Synthetic 3",
         "event_date": pd.Timestamp("2024-03-01"), "event_location": "",
         "bout_string": "Carol vs. Bob", "fighter_a": "Carol", "fighter_b": "Bob",
         "fighter_a_outcome": "W", "fighter_b_outcome": "L",
         "winner": "Carol", "loser": "Bob",
         "is_draw": False, "is_nc": False, "is_excluded": False, "exclusion_reason": None,
         "weight_class": "Lightweight", "is_title_fight": False,
         "method_raw": "Submission", "method_class": "Submission", "method_score_winner": 0.95,
         "end_round": 2, "end_time_seconds": 120, "time_format": "3 Rnd (5-5-5)",
         "referee": "", "details_text": "",
         "ped_confirmed": False, "ped_flagged_fighter": None,
         "ped_confirmation_source": None, "ped_confirmation_detail": None},
    ])
    rounds = pd.DataFrame(columns=[
        "fight_url", "event_name", "event_date", "bout_string",
        "round_num", "fighter", "kd",
        "sig_str_landed", "sub_att", "ctrl_seconds",
    ])
    fights.to_parquet(snapshot_dir / "canonical_fights.parquet", index=False)
    rounds.to_parquet(snapshot_dir / "canonical_rounds.parquet", index=False)


def _build_odds_artifact(snapshot_dir: Path) -> None:
    raw = pd.DataFrame([
        {"fight_url": "u/1", "event_date": "2024-01-01", "event_name": "Synthetic 1",
         "fighter_a": "Alice", "fighter_b": "Bob",
         "odds_source": "fixture",
         "odds_fighter_a": "Alice", "odds_fighter_b": "Bob",
         "american_odds_a": 400, "american_odds_b": -500,
         "decimal_odds_a": None, "decimal_odds_b": None},
        {"fight_url": "u/3", "event_date": "2024-03-01", "event_name": "Synthetic 3",
         "fighter_a": "Carol", "fighter_b": "Bob",
         "odds_source": "fixture",
         "odds_fighter_a": "Carol", "odds_fighter_b": "Bob",
         "american_odds_a": 350, "american_odds_b": -450,
         "decimal_odds_a": None, "decimal_odds_b": None},
    ])
    raw.to_parquet(snapshot_dir / "odds_lines.parquet", index=False)


_EXPECTED_STREAMS = (
    "canonical",
    "method",
    "method_integrity",
    "method_performance",
    "method_integrity_performance",
)


def test_rate_snapshot_produces_five_streams_without_odds(tmp_path: Path):
    from ratings.rate_snapshot import run as run_ratings

    snap = tmp_path / "snap"
    snap.mkdir()
    _build_synthetic_snapshot(snap)

    summary = run_ratings(snap, min_fights=1)
    current = pd.read_parquet(snap / "ratings_current.parquet")

    assert summary["odds_covered_fights"] == 0
    for stream in _EXPECTED_STREAMS:
        assert f"mu_{stream}" in current.columns
    assert "sustained_peak_mu_canonical" in current.columns
    assert "five_year_peak_mu_canonical" in current.columns
    assert "sustained_peak_mu_method_integrity_performance" in current.columns
    assert "five_year_peak_mu_method_integrity_performance" in current.columns
    # Legacy column names must not appear under the new architecture.
    for legacy in (
        "mu_ped_adjusted", "mu_odds_adjusted", "mu_quality_adjusted",
        "instant_peak_mu_canonical", "instant_peak_mu_method",
    ):
        assert legacy not in current.columns


def test_rate_snapshot_with_odds_lights_up_performance_sleeve(tmp_path: Path):
    from ratings.rate_snapshot import run as run_ratings

    snap = tmp_path / "snap"
    snap.mkdir()
    _build_synthetic_snapshot(snap)
    _build_odds_artifact(snap)

    summary = run_ratings(snap, min_fights=1)
    current = pd.read_parquet(snap / "ratings_current.parquet").set_index("fighter")

    assert summary["odds_covered_fights"] >= 2
    assert "sustained_peak_mu_method_integrity_performance" in current.columns
    assert "five_year_peak_mu_method_integrity_performance" in current.columns
    perf = pd.read_parquet(snap / "performance_appearances.parquet")
    for col in ["perf_factor_rank_context", "perf_factor_championship", "perf_factor_p4p", "perf_factor_weight_class"]:
        assert col in perf.columns
    # Performance sleeve produces a non-trivial delta for Alice (KO underdog winner)
    # relative to her plain method rating.
    assert abs(current.loc["Alice", "mu_method_performance"] - current.loc["Alice", "mu_method"]) > 0.5
    # Sleeve history files persist
    assert (snap / "ratings_history_method_integrity.parquet").exists()
    assert (snap / "ratings_history_method_performance.parquet").exists()
    assert (snap / "ratings_history_method_integrity_performance.parquet").exists()
