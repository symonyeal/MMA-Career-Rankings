"""Per-appearance opponent context feeding the division resume boards.

The rolling five- and ten-year period scores this module used to test were
retired on 2026-08-20; their replacement is covered in ``test_symon_score.py``.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ratings.appearance_context import peak_appearance_quality


def test_peak_opponent_quality_uses_actual_opponent_not_same_card_elite():
    prior_date = pd.Timestamp("2023-01-01")
    event_date = pd.Timestamp("2024-01-01")
    hist = pd.DataFrame([
        {"fighter": "LowOpp", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 1500.0},
        {"fighter": "Elite", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 2300.0},
        {"fighter": "Other", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 1500.0},
        {"fighter": "X", "event_date": event_date, "event_name": "Card", "mu_canonical": 1700.0},
        {"fighter": "LowOpp", "event_date": event_date, "event_name": "Card", "mu_canonical": 1450.0},
        {"fighter": "Elite", "event_date": event_date, "event_name": "Card", "mu_canonical": 2310.0},
        {"fighter": "Other", "event_date": event_date, "event_name": "Card", "mu_canonical": 1490.0},
    ])
    fights = pd.DataFrame([
        {
            "fight_url": "u/1", "event_date": event_date, "event_name": "Card",
            "fighter_a": "X", "fighter_b": "LowOpp", "winner": "X",
            "is_draw": False, "method_class": "Decision - Unanimous",
            "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
            "end_round": 3, "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
            "weight_class": "UFC Lightweight Bout", "is_title_fight": False,
        },
        {
            "fight_url": "u/2", "event_date": event_date, "event_name": "Card",
            "fighter_a": "Elite", "fighter_b": "Other", "winner": "Elite",
            "is_draw": False, "method_class": "KO/TKO",
            "method_score_winner": 1.0, "time_format": "3 Rnd (5-5-5)",
            "end_round": 1, "end_time_seconds": 60, "details_text": "",
            "weight_class": "UFC Lightweight Bout", "is_title_fight": False,
        },
    ])
    quality = peak_appearance_quality(fights, hist)
    x = quality[quality["fighter"] == "X"].iloc[0]
    assert x["opponent"] == "LowOpp"
    assert x["opponent_prefight_mu"] == pytest.approx(1500.0)
    assert x["opp_weight"] == pytest.approx(0.0)


def test_peak_appearances_do_not_fan_out_same_event_tournament_rows():
    prior_date = pd.Timestamp("2023-01-01")
    event_date = pd.Timestamp("2024-01-01")
    history = pd.DataFrame([
        {"fighter": "A", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 1700.0},
        {"fighter": "B", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 1500.0},
        {"fighter": "C", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 1600.0},
        {"fighter": "A", "event_date": event_date, "event_name": "Tournament", "mu_canonical": 1720.0},
        {"fighter": "B", "event_date": event_date, "event_name": "Tournament", "mu_canonical": 1480.0},
        {"fighter": "A", "event_date": event_date, "event_name": "Tournament", "mu_canonical": 1740.0},
        {"fighter": "C", "event_date": event_date, "event_name": "Tournament", "mu_canonical": 1580.0},
    ])
    fights = pd.DataFrame([
        {
            "fight_url": f"t/{number}", "event_date": event_date,
            "event_name": "Tournament", "fighter_a": "A", "fighter_b": opponent,
            "winner": "A", "is_draw": False,
            "method_class": "Decision - Unanimous", "method_score_winner": 0.85,
            "time_format": "3 Rnd (5-5-5)", "end_round": 3,
            "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
            "weight_class": "UFC Lightweight Bout", "is_title_fight": False,
        }
        for number, opponent in enumerate(["B", "C"], start=1)
    ])

    out = peak_appearance_quality(fights, history)

    assert len(out) == 2 * len(fights)
    assert not out.duplicated(["fight_url", "fighter"]).any()


def test_peak_appearances_fail_loudly_on_duplicate_fight_fighter_output():
    event_date = pd.Timestamp("2024-01-01")
    fights = pd.DataFrame([{
        "fight_url": "self/1", "event_date": event_date, "event_name": "Bad",
        "fighter_a": "A", "fighter_b": "A", "winner": "A", "is_draw": False,
        "method_class": "Decision - Unanimous", "method_score_winner": 0.85,
        "time_format": "3 Rnd (5-5-5)", "end_round": 3,
        "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
        "weight_class": "UFC Lightweight Bout", "is_title_fight": False,
    }])
    history = pd.DataFrame([{
        "fighter": "A", "event_date": event_date, "event_name": "Bad",
        "mu_canonical": 1500.0,
    }])

    with pytest.raises(ValueError, match=r"unique per \(fight_url, fighter\)"):
        peak_appearance_quality(fights, history)
