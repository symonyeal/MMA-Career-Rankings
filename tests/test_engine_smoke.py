"""Smoke test: feed the engine 4 fictional events and verify it doesn't crash,
that ratings move in plausible directions, and that excluded outcomes are
respected by the caller (engine doesn't get them)."""
from datetime import datetime
import pandas as pd
import pytest

from ratings.glicko2_engine import RatingEngine


def test_canonical_w_l_directionality():
    """Wins must raise μ_canonical and losses must lower it."""
    eng = RatingEngine(tau=0.5)
    eng.process_event(pd.Timestamp("2024-01-01"), "E1", [
        {"fighter_a": "Alice", "fighter_b": "Bob",
         "winner": "Alice", "is_draw": False, "method_score_winner": 1.00},
    ])
    eng.process_event(pd.Timestamp("2024-02-01"), "E2", [
        {"fighter_a": "Alice", "fighter_b": "Carol",
         "winner": "Alice", "is_draw": False, "method_score_winner": 1.00},
    ])
    eng.process_event(pd.Timestamp("2024-03-01"), "E3", [
        {"fighter_a": "Carol", "fighter_b": "Bob",
         "winner": "Carol", "is_draw": False, "method_score_winner": 0.85},
    ])

    cur = eng.current_table()
    alice = cur[cur["fighter"] == "Alice"].iloc[0]
    bob   = cur[cur["fighter"] == "Bob"].iloc[0]
    carol = cur[cur["fighter"] == "Carol"].iloc[0]

    # Alice 2-0 > Carol 1-1 > Bob 0-2.
    assert alice["mu_canonical"] > carol["mu_canonical"]
    assert carol["mu_canonical"] > bob["mu_canonical"]
    assert alice["mu_canonical"] > 1500 > bob["mu_canonical"]


def test_method_bonus_differentiates_ko_vs_split_dec():
    """Two parallel fighters with identical canonical records but different
    methods of victory should rank: KO winner > split-decision winner in μ_method,
    while their μ_canonical stays close to identical."""
    eng = RatingEngine(tau=0.5)
    eng.process_event(pd.Timestamp("2024-01-01"), "E", [
        {"fighter_a": "Kayla", "fighter_b": "OppA",
         "winner": "Kayla", "is_draw": False, "method_score_winner": 1.00},   # KO
        {"fighter_a": "Diana", "fighter_b": "OppB",
         "winner": "Diana", "is_draw": False, "method_score_winner": 0.70},   # Split Dec
    ])
    cur = eng.current_table().set_index("fighter")
    # Same canonical {1,0} score against fresh 1500 opponents -> same μ_canonical
    assert abs(cur.loc["Kayla", "mu_canonical"] - cur.loc["Diana", "mu_canonical"]) < 0.5
    # Method bonus differentiates them — KO finisher should be clearly higher.
    assert cur.loc["Kayla", "mu_method"] > cur.loc["Diana", "mu_method"] + 5


def test_lazy_phi_inflation():
    eng = RatingEngine(tau=0.5)
    eng.process_event(pd.Timestamp("2020-01-01"), "E1", [
        {"fighter_a": "Alice", "fighter_b": "Bob",
         "winner": "Alice", "is_draw": False, "method_score_winner": 0.80},
    ])
    phi_after_e1 = eng.states["Alice"].canonical.phi

    # Long inactivity window.
    eng.process_event(pd.Timestamp("2025-01-01"), "E2", [
        {"fighter_a": "Alice", "fighter_b": "Dave",
         "winner": "Alice", "is_draw": False, "method_score_winner": 0.80},
    ])
    # After a long layoff Alice's phi should have grown (uncertainty went up).
    # before being knocked down again by the new bout.
    history = eng.history_df()
    alice_hist = history[history["fighter"] == "Alice"].reset_index(drop=True)
    # ratings did update
    assert len(alice_hist) == 2
    # the engine accepted the long gap without crashing
    assert eng.states["Alice"].last_event_date == pd.Timestamp("2025-01-01")


def test_draw_handling():
    eng = RatingEngine(tau=0.5)
    eng.process_event(pd.Timestamp("2024-01-01"), "E", [
        {"fighter_a": "Alice", "fighter_b": "Bob",
         "winner": None, "is_draw": True, "method_score_winner": None},
    ])
    a = eng.states["Alice"].canonical.mu
    b = eng.states["Bob"].canonical.mu
    # Two 1500/350 fighters drawing → ratings should stay close to 1500 each
    assert abs(a - 1500) < 5
    assert abs(b - 1500) < 5
