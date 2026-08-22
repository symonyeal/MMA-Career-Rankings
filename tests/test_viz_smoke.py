from pathlib import Path

import pandas as pd
import pytest

from analysis.viz import (
    PEAK_VIEWS,
    PUBLIC_RANKING_VIEWS,
    RATING_STREAMS,
    compose_rating_stream,
    _fight_duration_seconds,
    calibration_plot,
    datalab_scorecard_decision_summary,
    datalab_scorecard_insight_chart,
    division_strength_comparison_chart,
    division_strength_timeline_chart,
    division_year_snapshot_chart,
    external_source_coverage_dashboard,
    favorite_underdog_performance_table,
    favorite_underdog_performance_chart,
    fighter_detail,
    era_heatmap_chart,
    glicko_fightmatrix_scatter,
    h2h_prediction,
    load_snapshot,
    odds_adjustment_distribution_chart,
    odds_coverage_summary,
    integrity_impact_chart,
    rank_delta_table,
    ranking_context_impact_table,
    performance_factor_audit_table,
    sleeve_factor_summary_table,
    sleeve_effects_by_fight_table,
    weight_class_context_impact_table,
    normalize_division,
    public_history_key,
    public_rating_label,
    public_rating_stream,
    select_modular_rating_column,
    select_public_ranking_column,
    select_public_rating_column,
    select_rating_column,
    sleeve_ranking_table,
    striker_grappler_scatter,
    period_leaderboard_chart,
    fighter_odds_history_chart,
    fighter_profile_chart,
    top_n_table,
    top100_division_density_chart,
    top_fighter_placement_scatter,
    trajectory_chart,
    weight_class_strength_chart,
)


SNAPSHOT_DIR = Path("data/snapshots/2026-05-13")


@pytest.fixture(scope="module")
def snapshot():
    if not SNAPSHOT_DIR.exists():
        pytest.skip(f"snapshot not present: {SNAPSHOT_DIR}")
    return load_snapshot(SNAPSHOT_DIR)


def test_viz_builders_smoke(snapshot):
    rc = snapshot["ratings_current"]
    fighters = snapshot["fighters"]
    fights = snapshot["fights"]
    rounds = snapshot["rounds"]
    rh = snapshot["ratings_history"]

    table = top_n_table(rc, fighters, fights, n=5)
    assert len(table) == 5
    assert "fighter" in table.columns

    detail = fighter_detail("Jon Jones", fighters, rc, fights, snapshot.get("fighter_dominance"))
    assert "ratings" in detail

    h2h = h2h_prediction("Jon Jones", "Khabib Nurmagomedov", rc)
    assert 0 <= h2h["p_a_wins"] <= 1

    figures = [
        trajectory_chart(rh, fights, ["Jon Jones", "Anderson Silva"]),
        weight_class_strength_chart(rh, fights, divisions=["Lightweight"]),
        division_strength_timeline_chart(rh, fights, rating_col="mu_canonical", divisions=["Lightweight"]),
        division_year_snapshot_chart(rh, fights, rating_col="mu_canonical", year=2024, divisions=["Lightweight"]),
        striker_grappler_scatter(rounds, fights, rc, fighters),
        calibration_plot(rh, fights),
        glicko_fightmatrix_scatter(rc, snapshot["fightmatrix_rankings"]),
        external_source_coverage_dashboard(snapshot),
        integrity_impact_chart(
            snapshot.get("integrity_appearances", pd.DataFrame()),
            snapshot.get("sleeve_attribution", pd.DataFrame()),
        ),
        period_leaderboard_chart(rc),
        division_strength_comparison_chart(rc, fights, snapshot["fightmatrix_rankings"]),
        datalab_scorecard_insight_chart(snapshot["datalab_scorecards"]),
        top_fighter_placement_scatter(rc, n=50),
        top100_division_density_chart(rc, n=50),
        fighter_profile_chart("Jon Jones", rc),
        fighter_odds_history_chart("Jon Jones", snapshot.get("odds_lines"), fights),
    ]
    assert all(len(fig.data) > 0 or hasattr(fig, "layout") for fig in figures)

    deltas = rank_delta_table(rc, snapshot["fightmatrix_rankings"], limit=10)
    assert len(deltas) == 10
    assert "glicko_rank" in deltas.columns

    scorecards = datalab_scorecard_decision_summary(snapshot["datalab_scorecards"])
    assert not scorecards.empty
    assert "decision_type" in scorecards.columns


def test_fight_duration_uses_actual_finish_time():
    fights = pd.DataFrame(
        {
            "end_round": [1, 3, 5],
            "end_time_seconds": [30, 300, 92],
        }
    )
    assert _fight_duration_seconds(fights).tolist() == [30, 900, 1292]


def test_weight_class_strength_chart_handles_no_qualifying_rows():
    ratings_history = pd.DataFrame(
        {
            "fighter": ["A", "B"],
            "event_date": ["2024-01-01", "2024-01-01"],
            "mu_canonical": [1510.0, 1490.0],
        }
    )
    fights = pd.DataFrame(
        {
            "event_date": ["2024-01-01"],
            "weight_class": ["UFC Lightweight Bout"],
            "fighter_a": ["A"],
            "fighter_b": ["B"],
        }
    )
    fig = weight_class_strength_chart(
        ratings_history,
        fights,
        top_n_per_division=15,
        divisions=["Lightweight"],
    )
    assert hasattr(fig, "layout")
    assert fig.layout.annotations


# ---------------------------------------------------------------------------
# Odds helpers + sleeve composer should degrade cleanly

def test_odds_coverage_summary_present_or_absent(snapshot):
    odds_lines = snapshot.get("odds_lines")
    summary = odds_coverage_summary(
        snapshot["ratings_current"],
        odds_lines,
        snapshot["fights"],
    )
    assert "available" in summary
    assert "message" in summary
    assert isinstance(summary["total_fights"], int)
    if odds_lines is None or odds_lines.empty:
        assert summary["available"] is False
    else:
        assert summary["available"] is True
        assert summary["odds_covered_fights"] > 0


def test_odds_coverage_summary_no_artifact_branch(snapshot):
    summary = odds_coverage_summary(
        snapshot["ratings_current"], pd.DataFrame(), snapshot["fights"]
    )
    assert summary["available"] is False
    assert summary["odds_covered_fights"] == 0
    assert "No odds artifact" in summary["message"]


def test_odds_adjustment_distribution_chart_returns_figure_when_empty():
    fig = odds_adjustment_distribution_chart(pd.DataFrame())
    assert hasattr(fig, "layout")


def test_favorite_underdog_performance_table_handles_no_odds(snapshot):
    out = favorite_underdog_performance_table(
        snapshot.get("odds_lines"),
        snapshot["fights"],
    )
    assert "bucket" in out.columns


def test_select_rating_column_resolves_canonical_current(snapshot):
    col = select_rating_column(snapshot["ratings_current"], "canonical", "current")
    assert col == "mu_canonical"


def test_period_views_resolve_to_the_published_period_scores():
    """Both period aliases land on the Symon window scores, for any stream asked.

    The per-stream rolling peak columns were retired, so a period view is no
    longer a function of the stream: there is one Prime and one Peak. A snapshot
    built before they existed resolves to nothing rather than to a retired
    column.
    """
    modern = pd.DataFrame({
        "fighter": ["A"], "mu_canonical": [1500.0], "mu_whr": [1520.0],
        "symon_prime_score": [1700.0], "symon_peak_score": [1750.0],
    })
    for stream in ("canonical", "whr"):
        for alias in ("five_year_peak", "peak"):
            assert select_rating_column(modern, stream, alias) == "symon_peak_score"
        for alias in ("sustained_peak", "prime"):
            assert select_rating_column(modern, stream, alias) == "symon_prime_score"
    assert select_rating_column(modern, "canonical", "current") == "mu_canonical"

    legacy = pd.DataFrame({
        "fighter": ["A"], "mu_canonical": [1500.0],
        "sustained_peak_mu_canonical": [1600.0],
    })
    assert select_rating_column(legacy, "canonical", "prime") is None


def test_select_rating_column_returns_none_when_missing():
    bare = pd.DataFrame({"fighter": ["A"], "mu_canonical": [1500.0]})
    assert select_rating_column(bare, "method_integrity", "current") is None
    assert select_rating_column(bare, "method_performance", "five_year_peak") is None


def test_select_rating_column_rejects_unknown_peak(snapshot):
    with pytest.raises(ValueError):
        select_rating_column(snapshot["ratings_current"], "canonical", "made_up")


def test_normalize_division_preserves_womens_labels():
    assert normalize_division("UFC Women's Flyweight Bout") == "Women's Flyweight"
    assert normalize_division("UFC Women's Strawweight Title Bout") == "Women's Strawweight"
    assert normalize_division("UFC Flyweight Bout") == "Flyweight"


def test_rating_streams_and_peak_views_are_aligned():
    stream_keys = [v for _, v in RATING_STREAMS]
    peak_keys = [v for _, v in PEAK_VIEWS]
    # The weighted "Strength" stream is retired: it gave one bout different
    # winner and loser weights, which is not one joint likelihood.
    assert set(stream_keys) == {"canonical", "method"}
    # Period views are published scores now, not per-stream rolling columns.
    assert set(peak_keys) == {"current", "prime", "peak"}


def test_compose_rating_stream_locks_canonical():
    """Canonical is always pristine; the performance sleeve only applies to method."""
    assert compose_rating_stream("canonical") == "canonical"
    assert compose_rating_stream("method") == "method"
    assert compose_rating_stream("method", use_performance=True) == "method_performance"
    with pytest.raises(ValueError):
        compose_rating_stream("canonical", use_performance=True)


def test_modular_lookup_resolves_to_method_streams(snapshot):
    rc = snapshot["ratings_current"]
    assert select_modular_rating_column(rc, "canonical") == "mu_canonical"
    if "mu_method_integrity_performance" in rc.columns:
        assert select_modular_rating_column(rc, "method", use_performance=True) == "mu_method_performance"


def test_public_ranking_views_resolve_new_columns_only():
    rc = pd.DataFrame({
        "symon_career_skill_mass": [10.0],
        "symon_prime_score": [1600.0],
        "symon_peak_score": [1650.0],
        "mu_whr": [1550.0],
        # Retired columns must never win public resolution, even when present.
        "mu_method_integrity_performance": [9999.0],
        "mu_whr_integrity_performance": [9999.0],
    })
    expected = {
        "all_time": "symon_career_skill_mass",
        "prime": "symon_prime_score",
        "peak": "symon_peak_score",
        "current": "mu_whr",
    }
    assert dict(PUBLIC_RANKING_VIEWS).keys() == {
        "All-time", "Prime · best 10 years / 13+ bouts",
        "Peak · best 5 years / 8+ bouts", "Current skill",
    }
    for view, column in expected.items():
        assert select_public_ranking_column(rc, view) == column
        assert public_history_key(view) == "ratings_history_whr"
        assert public_rating_stream(view) == "whr"
        assert "integrity_performance" not in select_public_ranking_column(rc, view)
    assert public_rating_label("all_time") == "All-time"
    retired_only = rc[["mu_method_integrity_performance", "mu_whr_integrity_performance"]]
    assert all(select_public_ranking_column(retired_only, view) is None for view in expected)


def test_public_ranking_views_fall_back_to_base_old_snapshot_columns():
    # A snapshot built before the Symon scores existed, still carrying retired
    # weighted columns: every view must land on base WHR, never on a retired
    # sleeve or on the withdrawn opponent-quality period columns.
    old = pd.DataFrame({
        "mu_whr": [1550.0],
        "mu_canonical": [1500.0],
        "sustained_peak_headline_mu_whr": [1600.0],
        "five_year_peak_headline_mu_whr": [1650.0],
        "mu_method_integrity_performance": [9999.0],
        "mu_whr_integrity_performance": [9999.0],
    })
    assert select_public_ranking_column(old, "all_time") == "mu_whr"
    assert select_public_ranking_column(old, "prime") == "mu_whr"
    assert select_public_ranking_column(old, "peak") == "mu_whr"
    assert select_public_ranking_column(old, "current") == "mu_whr"
    # Retired two-argument callers normalize onto the same base-only mapping.
    assert select_public_rating_column(old, "complete", "current") == "mu_whr"


def test_sleeve_ranking_table_filters_and_delta(snapshot):
    table = sleeve_ranking_table(
        snapshot["ratings_current"],
        "mu_canonical",
        n=5,
        min_fights=3,
        fights=snapshot["fights"],
        query="Jones",
    )
    assert list(table.columns) == [
        "rank", "fighter", "current_rating", "baseline_rating",
        "delta_vs_baseline", "last_event_date", "query_match",
    ]
    assert len(table) == 5
    assert table["delta_vs_baseline"].eq(0).all()


def test_new_market_and_era_charts_smoke(snapshot):
    market = favorite_underdog_performance_table(snapshot.get("odds_lines"), snapshot["fights"])
    context = ranking_context_impact_table(snapshot.get("performance_appearances", pd.DataFrame()), n=5)
    weight_context = weight_class_context_impact_table(snapshot.get("performance_appearances", pd.DataFrame()), n=5)
    perf_audit = performance_factor_audit_table(snapshot.get("performance_appearances", pd.DataFrame()), n=10)
    summary = sleeve_factor_summary_table(
        snapshot.get("performance_appearances", pd.DataFrame()),
    )
    effects = sleeve_effects_by_fight_table(
        snapshot.get("performance_appearances", pd.DataFrame()),
        n=5,
    )
    figures = [
        favorite_underdog_performance_chart(market),
        era_heatmap_chart(snapshot["ratings_history"], snapshot["fights"], top_n=10),
    ]
    assert all(hasattr(fig, "layout") for fig in figures)
    assert "context_multiplier" in context.columns
    assert "perf_factor_weight_class" in weight_context.columns
    assert {"factor", "effect", "multiplier"}.issubset(perf_audit.columns)
    assert {"sleeve", "factor", "appearances", "median_effect_pct"}.issubset(summary.columns)
    assert {"fighter", "combined_effect_pct", "factors"}.issubset(effects.columns)
