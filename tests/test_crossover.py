"""Transfer failure is measured against each opponent, and abstains on thin records."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.crossover import (
    _implied_strength,
    aberrations,
    promotion_summary,
    transfer_test,
)


def _history(pairs: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame([
        {"fighter": name, "event_date": pd.Timestamp("2015-01-01"),
         "event_name": "E", "mu_whr": mu}
        for name, mu in pairs.items()
    ])


def _bouts(rows: list[tuple[str, str, str, str]], org: str | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["fighter_a", "fighter_b",
                                        "fighter_a_outcome", "event_date"])
    frame["fighter_b_outcome"] = frame["fighter_a_outcome"].map({"W": "L", "L": "W"})
    if org is not None:
        frame["org"] = org
    return frame


def test_implied_strength_recovers_a_known_level():
    """Beating a 1500 half the time implies a strength near 1500."""
    results = [(1500.0, 1.0), (1500.0, 0.0)] * 10
    theta, se = _implied_strength(results)
    assert abs(theta - 1500.0) < 5.0
    assert np.isfinite(se) and se > 0


def test_a_winless_record_is_shrunk_and_loosely_pinned_not_run_to_the_boundary():
    """Without the prior this had no interior maximum; with it, it is merely vague."""
    thin, thin_se = _implied_strength([(1600.0, 0.0), (1650.0, 0.0)])
    balanced, balanced_se = _implied_strength([(1600.0, 1.0), (1600.0, 0.0)] * 10)

    assert np.isfinite(thin) and np.isfinite(thin_se)
    assert thin < 1600.0                      # winless still reads as weaker
    assert thin > 1600.0 - 800.0              # but nowhere near the old clip
    assert thin_se > balanced_se * 2          # and it is far less pinned down


def test_the_prior_is_what_makes_every_gap_finite():
    """52% of real crossovers hit a boundary on one side; none may be dropped."""
    unregularized = _implied_strength([(1600.0, 0.0)], virtual_games=0.0)
    assert not np.isfinite(unregularized[1])
    regularized = _implied_strength([(1600.0, 0.0)])
    assert np.isfinite(regularized[1])


def test_transfer_gap_is_positive_when_outside_form_does_not_carry():
    history = _history({"Weak Opp": 1400.0, "Strong Opp": 1800.0})
    outside = _bouts([("Crosser", "Weak Opp", "W", "2018-01-01")] * 6, org="Bellator")
    inside = _bouts([("Crosser", "Weak Opp", "L", "2021-01-01")] * 6)

    result = transfer_test(outside, inside, history).set_index("fighter")
    assert result.loc["Crosser", "transfer_gap"] > 0
    assert result.loc["Crosser", "main_outside_org"] == "Bellator"


def test_losing_to_far_stronger_opposition_is_not_a_transfer_failure():
    """The whole point of conditioning on each opponent rather than averaging."""
    history = _history({"Even Opp": 1500.0, "Elite Opp": 2100.0})
    outside = _bouts([("Crosser", "Even Opp", "W", "2018-01-01"),
                      ("Crosser", "Even Opp", "L", "2018-06-01")] * 4, org="PRIDE")
    inside = _bouts([("Crosser", "Elite Opp", "L", "2021-01-01")] * 4)

    even = transfer_test(outside, inside, history).set_index("fighter")

    # Same fighter, same outside form, but the inside losses come to an opponent
    # at their own level: that IS a transfer failure and must score higher.
    history_weak = _history({"Even Opp": 1500.0, "Peer Opp": 1500.0})
    inside_peer = _bouts([("Crosser", "Peer Opp", "L", "2021-01-01")] * 4)
    peer = transfer_test(outside, inside_peer, history_weak).set_index("fighter")

    assert peer.loc["Crosser", "transfer_gap"] > even.loc["Crosser", "transfer_gap"]


def test_a_thin_record_never_reaches_the_aberration_screen():
    history = _history({"Opp": 1500.0})
    outside = _bouts([("Crosser", "Opp", "W", "2018-01-01")] * 8, org="Bellator")
    inside = _bouts([("Crosser", "Opp", "L", "2021-01-01"),
                     ("Crosser", "Opp", "W", "2021-06-01")])

    result = transfer_test(outside, inside, history)
    assert len(result) == 1
    assert aberrations(result).empty  # z on two inside bouts cannot clear 1.96


def test_unrated_opponents_are_skipped_rather_than_guessed():
    history = _history({"Rated Opp": 1500.0})
    outside = _bouts([("Crosser", "Unrated Guy", "W", "2018-01-01")] * 5, org="RIZIN")
    inside = _bouts([("Crosser", "Rated Opp", "W", "2021-01-01"),
                     ("Crosser", "Rated Opp", "L", "2021-06-01")])
    # Every outside opponent is unrated, so there is nothing to compare.
    assert transfer_test(outside, inside, history).empty


def test_promotion_summary_flags_only_intervals_that_exclude_zero():
    frame = pd.DataFrame({
        "fighter": [f"F{i}" for i in range(8)],
        "main_outside_org": ["Bellator"] * 4 + ["PRIDE"] * 4,
        "transfer_gap": [90.0, 95.0, 88.0, 92.0, 10.0, -120.0, 130.0, -20.0],
        "z": [2.0] * 8,
    })
    out = promotion_summary(frame)
    assert bool(out.loc["Bellator", "resolved"])
    assert not bool(out.loc["PRIDE", "resolved"])
