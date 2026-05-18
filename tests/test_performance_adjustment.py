"""Unit tests for the performance sleeve (tanh-smoothed, rank-gated upset)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from ratings.constants import (
    PERF_TANH_SCALE,
    PERF_UPSET_AMPLITUDE,
    PERF_UPSET_RANK_GAP_THRESHOLD,
    SLEEVE_FACTOR_MAX,
    SLEEVE_FACTOR_MIN,
)
from ratings.performance_adjustment import (
    build_performance_appearances,
    decision_quality_score,
    decisiveness_score,
    is_championship_bout,
    is_interim_title_bout,
    prefight_ranking_context,
    prefight_weight_class_context,
    parse_judge_scores,
    quality_score_winner,
    scheduled_rounds,
)
from ratings.opponent_quality import opponent_mu_quality_factor


def _bout_row(**overrides) -> pd.Series:
    base = {
        "fighter_a": "A",
        "fighter_b": "B",
        "winner": "A",
        "is_draw": False,
        "method_class": "Decision - Unanimous",
        "method_score_winner": 0.85,
        "time_format": "3 Rnd (5-5-5)",
        "end_round": 3,
        "end_time_seconds": 300,
        "details_text": "30-27 30-27 30-27",
    }
    base.update(overrides)
    return pd.Series(base)


def test_title_bout_parser_excludes_tournament_finals():
    assert is_championship_bout(pd.Series({
        "is_title_fight": True,
        "weight_class": "UFC Light Heavyweight Title Bout",
    }))
    assert is_interim_title_bout("UFC Interim Heavyweight Title Bout")
    assert not is_championship_bout(pd.Series({
        "is_title_fight": True,
        "weight_class": "Ultimate Fighter 33 Welterweight Tournament Title Bout",
    }))
    assert not is_championship_bout(pd.Series({
        "is_title_fight": True,
        "weight_class": "Road to UFC 3 Flyweight Tournament TitleBout",
    }))


def test_parse_judge_scores_extracts_tuples():
    assert parse_judge_scores("30-27 30-27 29-28") == [(30, 27), (30, 27), (29, 28)]
    assert parse_judge_scores(None) == []


def test_scheduled_rounds_extracts_count():
    assert scheduled_rounds("5 Rnd (5-5-5-5-5)") == 5
    assert scheduled_rounds("3 Rnd (5-5-5)") == 3
    assert scheduled_rounds(None) == 3


def test_decision_quality_score_3rd_unanimous_sits_at_unanimous_tier():
    # A 30-27 sweep on a 3-round bout is unanimous but not the
    # 5-round-dominant tier, so it lands at the plain Unanimous score.
    row = _bout_row(details_text="30-27 30-27 30-27")
    assert decision_quality_score(row) == pytest.approx(0.95)


def test_decision_quality_score_5rd_50_45_sweep_hits_dominant_tier():
    row = _bout_row(
        time_format="5 Rnd (5-5-5-5-5)",
        details_text="50-45 50-45 50-45",
    )
    assert decision_quality_score(row) == pytest.approx(0.97)


def test_decision_quality_score_5rd_49_46_still_dominant():
    # Every judge dropped at most one round - still the championship-sweep tier.
    row = _bout_row(
        time_format="5 Rnd (5-5-5-5-5)",
        details_text="49-46 49-46 49-46",
    )
    assert decision_quality_score(row) == pytest.approx(0.97)


def test_decision_quality_score_5rd_48_47_is_plain_unanimous():
    # Two rounds dropped on every card - not dominant, lands at Unanimous.
    row = _bout_row(
        time_format="5 Rnd (5-5-5-5-5)",
        details_text="48-47 48-47 48-47",
    )
    assert decision_quality_score(row) == pytest.approx(0.95)


def test_decision_quality_score_split_decision_drops_to_non_unanimous_tier():
    row = _bout_row(
        method_class="Decision - Split",
        details_text="29-28 29-28 28-29",
    )
    assert decision_quality_score(row) == pytest.approx(0.90)


def test_decision_quality_score_majority_decision_drops_to_non_unanimous_tier():
    row = _bout_row(
        method_class="Decision - Majority",
        details_text="29-28 29-28 29-29",
    )
    assert decision_quality_score(row) == pytest.approx(0.90)


def test_quality_score_winner_handles_finish_methods():
    ko = _bout_row(method_class="KO/TKO")
    sub = _bout_row(method_class="Submission")
    dq = _bout_row(method_class="DQ")
    draw = _bout_row(is_draw=True, method_class="Decision - Split")
    assert quality_score_winner(ko) == 1.0
    assert quality_score_winner(sub) == 1.0
    assert quality_score_winner(dq) == pytest.approx(0.85)
    assert quality_score_winner(draw) is None


def test_quality_score_winner_ped_win_is_floored_near_a_draw():
    """A PED-confirmed win drops the score to the integrity floor (~0.55),
    far below a clean finish (1.00) - the propagated rating-layer penalty."""
    ko = _bout_row(method_class="KO/TKO", ped_confirmed=True, ped_flagged_fighter="A")
    assert quality_score_winner(ko) == pytest.approx(0.55)


def test_quality_score_winner_missed_weight_win_is_floored():
    ko = _bout_row(method_class="KO/TKO", missed_weight=True, missed_weight_fighter="A")
    assert quality_score_winner(ko) == pytest.approx(0.70)


def test_quality_score_winner_ped_loss_is_untouched():
    """Damping a loss would soften it - the score damp only floors winners."""
    ko = _bout_row(method_class="KO/TKO", winner="A",
                   ped_confirmed=True, ped_flagged_fighter="B")
    assert quality_score_winner(ko) == 1.0


def test_decisiveness_score_ordering():
    first_round_finish = _bout_row(method_class="KO/TKO", end_round=1)
    later_finish = _bout_row(method_class="Submission", end_round=3)
    dominant_five_round = _bout_row(
        time_format="5 Rnd (5-5-5-5-5)",
        details_text="50-45 50-45 50-45",
    )
    narrow_ud = _bout_row(details_text="29-28 29-28 29-28")
    split = _bout_row(method_class="Decision - Split", details_text="29-28 28-29 29-28")
    dq = _bout_row(method_class="DQ")
    assert decisiveness_score(first_round_finish) == pytest.approx(1.00)
    assert decisiveness_score(later_finish) == pytest.approx(0.95)
    assert decisiveness_score(dominant_five_round) == pytest.approx(0.88)
    assert decisiveness_score(narrow_ud) == pytest.approx(0.83)
    assert decisiveness_score(split) == pytest.approx(0.78)
    assert decisiveness_score(dq) == pytest.approx(0.70)


def _minimal_history() -> pd.DataFrame:
    return pd.DataFrame([
        {"fighter": "Alice", "event_date": "2023-12-01", "event_name": "Prior",
         "mu_canonical": 1700.0},
        {"fighter": "Bob", "event_date": "2023-12-01", "event_name": "Prior",
         "mu_canonical": 1500.0},
    ])


def _minimal_fights() -> pd.DataFrame:
    return pd.DataFrame([
        {"fight_url": "u/1", "event_date": pd.Timestamp("2024-01-01"),
         "event_name": "E1", "fighter_a": "Alice", "fighter_b": "Bob",
         "winner": "Alice", "is_draw": False, "method_class": "KO/TKO",
         "method_score_winner": 1.0, "time_format": "5 Rnd (5-5-5-5-5)",
         "end_round": 1, "end_time_seconds": 60, "details_text": ""},
    ])


def test_performance_weight_within_envelope_and_loser_is_symmetric():
    """Tanh-smoothed combination: winner-side amplifies, loser-side damps by
    the same magnitude. The same per-fight signal feeds both sides."""
    out = build_performance_appearances(
        _minimal_fights(), _minimal_history(), odds_lines=None,
    )
    alice = out[out["fighter"] == "Alice"].iloc[0]
    bob = out[out["fighter"] == "Bob"].iloc[0]
    assert SLEEVE_FACTOR_MIN <= alice["performance_weight"] <= SLEEVE_FACTOR_MAX
    assert SLEEVE_FACTOR_MIN <= bob["performance_weight"] <= SLEEVE_FACTOR_MAX
    # Winner above 1.0, loser below 1.0, symmetric around 1.0.
    assert alice["performance_weight"] > 1.0
    assert bob["performance_weight"] < 1.0
    assert math.isclose(
        alice["performance_weight"] + bob["performance_weight"], 2.0, abs_tol=1e-9,
    )


def test_performance_individual_factors_within_envelope():
    out = build_performance_appearances(
        _minimal_fights(), _minimal_history(), odds_lines=None,
    )
    cols = [
        "perf_factor_decisiveness",
        "perf_factor_opponent_strength",
        "perf_factor_opponent_streak",
        "perf_factor_odds",
        "perf_factor_rank_context",
        "perf_factor_championship",
        "perf_factor_p4p",
        "perf_factor_weight_class",
        "perf_factor_activity_loss",
    ]
    for col in cols:
        vals = out[col].dropna()
        assert (vals >= SLEEVE_FACTOR_MIN).all()
        assert (vals <= SLEEVE_FACTOR_MAX).all()


def test_opponent_mu_quality_is_monotonic_across_elite_range():
    factors = opponent_mu_quality_factor(pd.Series([1500.0, 2150.0, 2300.0, 2400.0]))
    assert factors.iloc[0] == pytest.approx(1.0)
    assert factors.iloc[1] < factors.iloc[2] < factors.iloc[3]
    assert factors.iloc[3] <= 1.0 + 0.16


def test_performance_appearances_handles_empty_input():
    out = build_performance_appearances(pd.DataFrame(), _minimal_history(), odds_lines=None)
    assert out.empty


def test_rank_championship_p4p_context_uses_prefight_state():
    fights = pd.DataFrame([
        {"fight_url": "u/1", "event_date": pd.Timestamp("2023-01-01"),
         "event_name": "E1", "fighter_a": "Champion", "fighter_b": "Gatekeeper",
         "winner": "Champion", "is_draw": False, "method_class": "KO/TKO",
         "method_score_winner": 1.0, "time_format": "5 Rnd (5-5-5-5-5)",
         "end_round": 2, "end_time_seconds": 120, "details_text": "",
         "weight_class": "UFC Lightweight Title Bout", "is_title_fight": True},
        {"fight_url": "u/2", "event_date": pd.Timestamp("2023-02-01"),
         "event_name": "E2", "fighter_a": "Ranked", "fighter_b": "Other",
         "winner": "Ranked", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
         "weight_class": "UFC Lightweight Bout", "is_title_fight": False},
        {"fight_url": "u/3", "event_date": pd.Timestamp("2024-01-01"),
         "event_name": "E3", "fighter_a": "Challenger", "fighter_b": "Champion",
         "winner": "Challenger", "is_draw": False, "method_class": "Submission",
         "method_score_winner": 1.0, "time_format": "5 Rnd (5-5-5-5-5)",
         "end_round": 4, "end_time_seconds": 60, "details_text": "",
         "weight_class": "UFC Lightweight Title Bout", "is_title_fight": True},
    ])
    history = pd.DataFrame([
        {"fighter": "Champion", "event_date": "2023-01-01", "event_name": "E1", "mu_canonical": 1800.0},
        {"fighter": "Gatekeeper", "event_date": "2023-01-01", "event_name": "E1", "mu_canonical": 1400.0},
        {"fighter": "Ranked", "event_date": "2023-02-01", "event_name": "E2", "mu_canonical": 1700.0},
        {"fighter": "Other", "event_date": "2023-02-01", "event_name": "E2", "mu_canonical": 1450.0},
        {"fighter": "Challenger", "event_date": "2024-01-01", "event_name": "E3", "mu_canonical": 1750.0},
        {"fighter": "Champion", "event_date": "2024-01-01", "event_name": "E3", "mu_canonical": 1600.0},
    ])

    context = prefight_ranking_context(fights, history)
    title_context = context[context["fight_url"] == "u/3"].iloc[0]
    assert title_context["fighter_b_prefight_division_rank"] == 1
    assert title_context["fighter_b_prefight_p4p_rank"] == 1
    assert bool(title_context["fighter_b_entered_as_champion"]) is True

    out = build_performance_appearances(fights, history, odds_lines=None)
    challenger = out[(out["fight_url"] == "u/3") & (out["fighter"] == "Challenger")].iloc[0]
    assert challenger["opponent_prefight_division_rank"] == 1
    assert challenger["opponent_prefight_p4p_rank"] == 1
    assert bool(challenger["opponent_entered_as_champion"]) is True
    assert challenger["perf_factor_rank_context"] > 1.0
    assert challenger["perf_factor_championship"] > 1.0
    assert challenger["perf_factor_p4p"] > 1.0


def test_weight_class_move_up_win_boosts_and_down_loss_detracts():
    fights = pd.DataFrame([
        {"fight_url": "u/1", "event_date": pd.Timestamp("2023-01-01"),
         "event_name": "E1", "fighter_a": "Mover", "fighter_b": "BaseA",
         "winner": "Mover", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
         "weight_class": "UFC Lightweight Bout", "is_title_fight": False},
        {"fight_url": "u/2", "event_date": pd.Timestamp("2024-01-01"),
         "event_name": "E2", "fighter_a": "Mover", "fighter_b": "BaseB",
         "winner": "Mover", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
         "weight_class": "UFC Welterweight Bout", "is_title_fight": False},
        {"fight_url": "u/3", "event_date": pd.Timestamp("2025-01-01"),
         "event_name": "E3", "fighter_a": "Mover", "fighter_b": "BaseC",
         "winner": "BaseC", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "27-30 27-30 27-30",
         "weight_class": "UFC Lightweight Bout", "is_title_fight": False},
        {"fight_url": "u/4", "event_date": pd.Timestamp("2026-01-01"),
         "event_name": "E4", "fighter_a": "Mover", "fighter_b": "BaseD",
         "winner": "Mover", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
         "weight_class": "UFC Lightweight Bout", "is_title_fight": False},
    ])
    history = pd.DataFrame([
        {"fighter": f, "event_date": d, "event_name": e, "mu_canonical": 1500.0}
        for f, d, e in [
            ("Mover", "2023-01-01", "E1"), ("BaseA", "2023-01-01", "E1"),
            ("Mover", "2024-01-01", "E2"), ("BaseB", "2024-01-01", "E2"),
            ("Mover", "2025-01-01", "E3"), ("BaseC", "2025-01-01", "E3"),
            ("Mover", "2026-01-01", "E4"), ("BaseD", "2026-01-01", "E4"),
        ]
    ])

    context = prefight_weight_class_context(fights)
    assert context.loc[context["fight_url"] == "u/2", "fighter_a_weight_class_move"].iloc[0] == "up"
    assert bool(context.loc[context["fight_url"] == "u/2", "fighter_a_weight_class_change_fight"].iloc[0])
    assert context.loc[context["fight_url"] == "u/3", "fighter_a_weight_class_move"].iloc[0] == "down"
    assert bool(context.loc[context["fight_url"] == "u/3", "fighter_a_weight_class_change_fight"].iloc[0])
    assert context.loc[context["fight_url"] == "u/4", "fighter_a_weight_class_move"].iloc[0] == "same"
    assert not bool(context.loc[context["fight_url"] == "u/4", "fighter_a_weight_class_change_fight"].iloc[0])

    out = build_performance_appearances(fights, history, odds_lines=None)
    up_win = out[(out["fight_url"] == "u/2") & (out["fighter"] == "Mover")].iloc[0]
    down_loss = out[(out["fight_url"] == "u/3") & (out["fighter"] == "Mover")].iloc[0]
    same_division_after_move = out[(out["fight_url"] == "u/4") & (out["fighter"] == "Mover")].iloc[0]

    assert up_win["fighter_weight_class_move"] == "up"
    assert bool(up_win["fighter_weight_class_change_fight"])
    assert up_win["perf_factor_weight_class"] > 1.0
    assert up_win["performance_weight"] > 1.0
    assert down_loss["fighter_weight_class_move"] == "down"
    assert bool(down_loss["fighter_weight_class_change_fight"])
    assert down_loss["perf_factor_weight_class"] > 1.0
    assert down_loss["perf_factor_activity_loss"] > 1.0
    # The wc-down-loss amplifier OVERRIDES the symmetric tanh damp — it is a
    # structural amplification (loss detracts more), opposite in direction to
    # the "favorite forgiveness" tanh damp. The two must not compose.
    assert math.isclose(
        down_loss["performance_weight"],
        down_loss["perf_factor_weight_class"] * down_loss["perf_factor_activity_loss"],
        abs_tol=1e-9,
    )
    assert same_division_after_move["fighter_weight_class_move"] == "same"
    assert not bool(same_division_after_move["fighter_weight_class_change_fight"])
    assert same_division_after_move["perf_factor_weight_class"] == 1.0


def test_weight_class_move_up_loss_damps_loser_update():
    """An above-natural-class loss should detract LESS than a same-class loss.

    Volk-Islam motivation: a fighter who loses while moving up a class should
    not be punished as hard in their main-division resume.
    """
    fights = pd.DataFrame([
        {"fight_url": "u/1", "event_date": pd.Timestamp("2023-01-01"),
         "event_name": "E1", "fighter_a": "Volk", "fighter_b": "FW1",
         "winner": "Volk", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
         "weight_class": "UFC Featherweight Bout", "is_title_fight": False},
        # Move up: Volk -> Lightweight, loses
        {"fight_url": "u/2", "event_date": pd.Timestamp("2024-01-01"),
         "event_name": "E2", "fighter_a": "Volk", "fighter_b": "LWChamp",
         "winner": "LWChamp", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "5 Rnd (5-5-5-5-5)",
         "end_round": 5, "end_time_seconds": 300, "details_text": "27-30 27-30 27-30",
         "weight_class": "UFC Lightweight Bout", "is_title_fight": False},
    ])
    history = pd.DataFrame([
        {"fighter": f, "event_date": d, "event_name": e, "mu_canonical": mu}
        for f, d, e, mu in [
            ("Volk", "2023-01-01", "E1", 1800.0),
            ("FW1", "2023-01-01", "E1", 1500.0),
            ("Volk", "2024-01-01", "E2", 1750.0),
            ("LWChamp", "2024-01-01", "E2", 1900.0),
        ]
    ])

    out = build_performance_appearances(fights, history, odds_lines=None)
    up_loss = out[(out["fight_url"] == "u/2") & (out["fighter"] == "Volk")].iloc[0]
    assert up_loss["fighter_weight_class_move"] == "up"
    assert not bool(up_loss["is_winner"])
    # The weight-class factor for up+loss is < 1.0 (a damp).
    assert up_loss["perf_factor_weight_class"] < 1.0
    # The final performance_weight is damped (still loses, but less aggressively
    # than a same-class loss would be).
    assert up_loss["performance_weight"] < 1.0


def test_activity_loss_penalty_is_loser_only_and_debut_neutral():
    fights = pd.DataFrame([
        {"fight_url": "u/1", "event_date": pd.Timestamp("2020-01-01"),
         "event_name": "E1", "fighter_a": "Layoff", "fighter_b": "Opponent1",
         "winner": "Layoff", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "30-27 30-27 30-27"},
        {"fight_url": "u/2", "event_date": pd.Timestamp("2023-01-01"),
         "event_name": "E2", "fighter_a": "Layoff", "fighter_b": "Opponent2",
         "winner": "Opponent2", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "27-30 27-30 27-30"},
        {"fight_url": "u/3", "event_date": pd.Timestamp("2023-02-01"),
         "event_name": "E3", "fighter_a": "DebutLoser", "fighter_b": "Opponent3",
         "winner": "Opponent3", "is_draw": False, "method_class": "Decision - Unanimous",
         "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
         "end_round": 3, "end_time_seconds": 300, "details_text": "27-30 27-30 27-30"},
    ])
    history = pd.DataFrame([
        {"fighter": f, "event_date": d, "event_name": e, "mu_canonical": 1500.0}
        for f, d, e in [
            ("Layoff", "2020-01-01", "E1"),
            ("Opponent1", "2020-01-01", "E1"),
            ("Layoff", "2023-01-01", "E2"),
            ("Opponent2", "2023-01-01", "E2"),
            ("DebutLoser", "2023-02-01", "E3"),
            ("Opponent3", "2023-02-01", "E3"),
        ]
    ])
    out = build_performance_appearances(fights, history, odds_lines=None)
    layoff_loss = out[(out["fight_url"] == "u/2") & (out["fighter"] == "Layoff")].iloc[0]
    debut_loss = out[(out["fight_url"] == "u/3") & (out["fighter"] == "DebutLoser")].iloc[0]
    layoff_win = out[(out["fight_url"] == "u/1") & (out["fighter"] == "Layoff")].iloc[0]
    assert layoff_loss["activity_layoff_level"] == pytest.approx(1.0)
    assert layoff_loss["perf_factor_activity_loss"] > 1.0
    assert layoff_loss["performance_weight"] == pytest.approx(layoff_loss["perf_factor_activity_loss"])
    assert debut_loss["activity_layoff_level"] == pytest.approx(0.0)
    assert debut_loss["perf_factor_activity_loss"] == pytest.approx(1.0)
    assert layoff_win["perf_factor_activity_loss"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Rank-gated upset factor


def _upset_history(challenger_mu: float, champion_mu: float) -> pd.DataFrame:
    """History snapshot establishing champion + ten other ranked fighters so
    the challenger lands outside the top 6 but the champion lands at rank 1."""
    rows = [
        {"fighter": "Champ", "event_date": "2024-12-01", "event_name": "Prior",
         "mu_canonical": champion_mu},
        {"fighter": "Challenger", "event_date": "2024-12-01", "event_name": "Prior",
         "mu_canonical": challenger_mu},
    ]
    # Eight other rated fighters so the challenger sits well below them.
    for idx, mu in enumerate([1900.0, 1875.0, 1850.0, 1825.0, 1800.0,
                              1775.0, 1750.0, 1725.0]):
        rows.append({
            "fighter": f"Filler_{idx}", "event_date": "2024-12-01",
            "event_name": "Prior", "mu_canonical": mu,
        })
    return pd.DataFrame(rows)


def _title_bout(winner: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "fight_url": "u/title", "event_date": pd.Timestamp("2025-01-01"),
        "event_name": "Title", "fighter_a": "Challenger", "fighter_b": "Champ",
        "winner": winner, "is_draw": False, "method_class": "KO/TKO",
        "method_score_winner": 1.0, "time_format": "5 Rnd (5-5-5-5-5)",
        "end_round": 1, "end_time_seconds": 90, "details_text": "",
        "weight_class": "UFC Lightweight Title Bout", "is_title_fight": True,
    }])


def test_rank_gated_upset_fires_for_unranked_over_champion():
    fights = _title_bout(winner="Challenger")
    history = _upset_history(challenger_mu=1500.0, champion_mu=2000.0)
    # Champion lineage is built from prior title fights; for the title flag
    # alone we still want the champion factor active. Set is_championship_bout
    # via opp_entered_as_champion: we set the champion via a prior title bout.
    fights = pd.concat([
        pd.DataFrame([{
            "fight_url": "u/prior", "event_date": pd.Timestamp("2024-06-01"),
            "event_name": "Prior", "fighter_a": "Champ", "fighter_b": "Old",
            "winner": "Champ", "is_draw": False, "method_class": "KO/TKO",
            "method_score_winner": 1.0, "time_format": "5 Rnd (5-5-5-5-5)",
            "end_round": 1, "end_time_seconds": 60, "details_text": "",
            "weight_class": "UFC Lightweight Title Bout", "is_title_fight": True,
        }]),
        fights,
    ], ignore_index=True)
    history = pd.concat([
        history,
        pd.DataFrame([{"fighter": "Old", "event_date": "2024-06-01",
                       "event_name": "Prior", "mu_canonical": 1700.0}]),
    ], ignore_index=True)

    out = build_performance_appearances(fights, history, odds_lines=None)
    challenger = out[(out["fight_url"] == "u/title") & (out["fighter"] == "Challenger")].iloc[0]
    champ = out[(out["fight_url"] == "u/title") & (out["fighter"] == "Champ")].iloc[0]
    # Challenger is unranked (16) vs champion (0) → max upset gap = 16.
    assert challenger["perf_upset_rank_gap"] >= PERF_UPSET_RANK_GAP_THRESHOLD
    assert challenger["perf_factor_upset"] > 1.0 + 0.5 * PERF_UPSET_AMPLITUDE
    # Upset is a small nudge; the larger movement here comes from opponent
    # championship quality, not underdog status by itself.
    assert challenger["performance_weight"] > 1.0
    assert champ["performance_weight"] < 1.0


@pytest.mark.parametrize(
    "winner_rank, opponent_rank, expected_gap, should_fire",
    [
        # The user's specific counter-example: #3 vs #4 (gap 1).
        (4, 3, 1, False),
        # Other short gaps — none should fire. The rule is generic.
        (5, 2, 3, False),
        (10, 8, 2, False),
        (11, 6, 5, False),   # exactly at threshold-1; still no upset.
        (15, 11, 4, False),
        # At the rank-gap threshold (gap = 6) the linear scale yields level
        # = 0, so the factor stays at exactly 1.0 — the threshold is the
        # *opening* of the gate, not where the magnitude starts. The first
        # genuinely-firing gap is 7.
        (7, 1, 6, False),
        # The user's positive example: #11 over #3 (gap 8). Upset.
        (11, 3, 8, True),
        # Outside top 6 over champion (rank 0). User's primary positive
        # case: "someone outside top 6 beating the champion".
        (7, 0, 7, True),
        # Unranked (16) beating champion — maximum gap, full upset.
        (16, 0, 16, True),
    ],
)
def test_rank_gated_upset_rule_is_generic_not_hardcoded(
    winner_rank, opponent_rank, expected_gap, should_fire,
):
    """The rank-gap rule is parameterized by PERF_UPSET_RANK_GAP_THRESHOLD and
    applies generically — short gaps NEVER trigger an upset regardless of the
    specific ranks the fighters held. The 2026-05-13 user spec:

        'an upset is No 11 beating No 3 or something similar — it should not
         impact a fight between no 3 and no 4'

    This test directly exercises ``_upset_factor`` with synthetic rank inputs
    so the rule is verified end-to-end without relying on the engine's
    rank-derivation pipeline. The #3-vs-#4 example was just one illustration;
    the rule covers every short gap.
    """
    from ratings.performance_adjustment import _upset_factor, _upset_rank_gap

    fighter_rank = pd.Series([float(winner_rank)])
    opp_rank = pd.Series([float(opponent_rank)])
    # Translate "rank 0" into champion flag so the helper treats it as champ.
    fighter_champ = pd.Series([False])
    fighter_interim = pd.Series([False])
    opp_champ = pd.Series([opponent_rank == 0])
    opp_interim = pd.Series([False])

    gap = _upset_rank_gap(fighter_rank, opp_rank, fighter_champ, fighter_interim, opp_champ, opp_interim)
    assert gap.iloc[0] == expected_gap

    is_winner = pd.Series([True])
    odds_signal = pd.Series([0.0])
    factor = _upset_factor(gap, odds_signal, is_winner)
    if should_fire:
        assert factor.iloc[0] > 1.0
    else:
        assert math.isclose(factor.iloc[0], 1.0, abs_tol=1e-9)


def test_tanh_saturation_keeps_weights_inside_envelope():
    """No raw factor combination can take ``performance_weight`` past the
    envelope. With ten factors all at their maximum positive contribution
    (impossible in practice but worth verifying), the tanh mapping still
    asymptotes to the cap rather than crossing it."""
    # An extreme synthetic fight: unranked challenger KO's champion in
    # round 1 of a 5-round title fight as a huge plus-money underdog.
    fights = pd.DataFrame([{
        "fight_url": "u/x", "event_date": pd.Timestamp("2025-01-01"),
        "event_name": "Extreme", "fighter_a": "Underdog", "fighter_b": "King",
        "winner": "Underdog", "is_draw": False, "method_class": "KO/TKO",
        "method_score_winner": 1.0, "time_format": "5 Rnd (5-5-5-5-5)",
        "end_round": 1, "end_time_seconds": 15, "details_text": "",
        "weight_class": "UFC Heavyweight Title Bout", "is_title_fight": True,
    }])
    history = pd.DataFrame([
        {"fighter": "King", "event_date": "2024-12-01", "event_name": "Prior", "mu_canonical": 2300.0},
        {"fighter": "Underdog", "event_date": "2024-12-01", "event_name": "Prior", "mu_canonical": 1450.0},
    ])
    # Add a prior title fight so King is the reigning champion at the new bout.
    fights = pd.concat([
        pd.DataFrame([{
            "fight_url": "u/prior_x", "event_date": pd.Timestamp("2024-06-01"),
            "event_name": "Prior", "fighter_a": "King", "fighter_b": "OldGuy",
            "winner": "King", "is_draw": False, "method_class": "KO/TKO",
            "method_score_winner": 1.0, "time_format": "5 Rnd (5-5-5-5-5)",
            "end_round": 1, "end_time_seconds": 60, "details_text": "",
            "weight_class": "UFC Heavyweight Title Bout", "is_title_fight": True,
        }]),
        fights,
    ], ignore_index=True)
    history = pd.concat([
        history,
        pd.DataFrame([{"fighter": "OldGuy", "event_date": "2024-06-01",
                       "event_name": "Prior", "mu_canonical": 1500.0}]),
    ], ignore_index=True)

    out = build_performance_appearances(fights, history, odds_lines=None)
    underdog = out[(out["fight_url"] == "u/x") & (out["fighter"] == "Underdog")].iloc[0]
    king = out[(out["fight_url"] == "u/x") & (out["fighter"] == "King")].iloc[0]
    assert underdog["performance_weight"] <= SLEEVE_FACTOR_MAX
    assert king["performance_weight"] >= SLEEVE_FACTOR_MIN
    # Both must move toward (not past) the envelope edges.
    assert underdog["performance_weight"] > 1.0
    assert king["performance_weight"] < 1.0


def test_per_fight_signal_drives_symmetric_winner_and_loser_weights():
    """Loser-side weight is the mirror image of the winner-side weight
    around 1.0, driven by the same per-fight ``perf_winner_signal_S``."""
    out = build_performance_appearances(
        _minimal_fights(), _minimal_history(), odds_lines=None,
    )
    alice = out[out["fighter"] == "Alice"].iloc[0]
    bob = out[out["fighter"] == "Bob"].iloc[0]
    expected_winner = 1.0 + 0.20 * math.tanh(alice["perf_winner_signal_S"] / PERF_TANH_SCALE)
    expected_loser = 1.0 - 0.20 * math.tanh(alice["perf_winner_signal_S"] / PERF_TANH_SCALE)
    assert math.isclose(alice["performance_weight"], expected_winner, abs_tol=1e-9)
    assert math.isclose(bob["performance_weight"], expected_loser, abs_tol=1e-9)
    assert math.isclose(
        alice["perf_winner_signal_S"], bob["perf_winner_signal_S"], abs_tol=1e-9,
    )


def test_draws_keep_unit_weight_on_both_sides():
    fights = pd.DataFrame([{
        "fight_url": "u/draw", "event_date": pd.Timestamp("2025-01-01"),
        "event_name": "Draw", "fighter_a": "X", "fighter_b": "Y",
        "winner": None, "is_draw": True, "method_class": "Decision - Split",
        "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
        "end_round": 3, "end_time_seconds": 300, "details_text": "29-29 29-29 29-29",
    }])
    history = pd.DataFrame([
        {"fighter": "X", "event_date": "2024-12-01", "event_name": "Prior", "mu_canonical": 1500.0},
        {"fighter": "Y", "event_date": "2024-12-01", "event_name": "Prior", "mu_canonical": 1500.0},
    ])
    out = build_performance_appearances(fights, history, odds_lines=None)
    assert all(out["performance_weight"] == 1.0)
