from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analysis.fightmatrix_graph import (
    PolicyConfig,
    _name_tokens,
    _names_compatible,
    load_name_aliases,
    assert_no_reference_leakage,
    build_model_input,
    finalize_snapshot,
    reconcile_bouts,
)
from analysis.fightmatrix_validation import build_scope_validation
from analysis.source_scope import DEFAULT_SCORE_COLUMN
from analysis.fightmatrix_viz import (
    closure_by_depth_chart,
    component_sizes_chart,
    data_quality_chart,
    degree_distribution_chart,
    expansion_funnel_chart,
    incomplete_exposure_chart,
    case_study_chart,
    organization_coverage_chart,
    organization_coverage_over_time_chart,
    policy_sensitivity_chart,
    rank_movement_chart,
    reference_residual_chart,
    score_movement_chart,
    weighted_edge_support_by_depth_chart,
)
from loaders.fightmatrix_expansion import (
    ExpansionConfig,
    classify_profile,
    initialize_queue,
    run_expansion,
)
from loaders.fightmatrix_identity import build_identity_artifacts, identity_name_key
from loaders.fightmatrix_organizations import normalize_organization


def _html(name: str, record: str, opponent: str, opponent_id: str, result: str = "W") -> str:
    inverse = {"W": "win", "L": "loss", "D": "draw", "NC": "nc"}
    assert result in inverse
    return f"""
    <h1>{name}</h1>
    <table class="tblRank"><tr><td>
      Pro Debut Date: 2020-01-01 Pro Record: {record}
    </td></tr></table>
    <table class="tblRank">
      <tr><td>Result</td><td>Opponent</td><td>Outcome</td></tr>
      <tr><td>{result}</td><td><a href="/fighter-profile/{opponent.replace(' ', '%20')}/{opponent_id}/">{opponent}</a></td>
          <td>Decision (Unanimous) Round 3</td></tr>
      <tr><td colspan="3"><a href="/event/Test/99/">UFC Test</a>
          <em>Saturday, January 1st 2022</em></td></tr>
    </table>
    """


def _raw_bout(
    fighter="Alpha One", fighter_id="1", opponent="Beta Two", opponent_id="2",
    result="win", event_id="99", date="2022-01-01", key="fightmatrix::99::alphaone::betatwo",
):
    return {
        "fight_key": key, "event_id": event_id, "event_url": "https://www.fightmatrix.com/event/Test/99/",
        "event_name": "UFC Test", "event_date": pd.Timestamp(date), "event_country_code": "US",
        "fighter": fighter, "fighter_profile_id": fighter_id, "opponent": opponent,
        "opponent_profile_id": opponent_id,
        "opponent_profile_url": f"https://www.fightmatrix.com/fighter-profile/{opponent.replace(' ', '%20')}/{opponent_id}/",
        "result": result, "opponent_prefight_rank": None, "opponent_prefight_division": None,
        "method_raw": "Decision (Unanimous)", "method_class": "Decision - Unanimous",
        "end_round": 3, "end_time_seconds": None, "org": "UFC", "is_title_fight": False,
        "source": "fightmatrix_public", "source_profile_url": f"https://www.fightmatrix.com/fighter-profile/x/{fighter_id}/",
    }


def _base_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "base"
    cache = tmp_path / "cache"
    base.mkdir()
    cache.mkdir()
    seed_url = "https://www.fightmatrix.com/fighter-profile/Alpha%20One/1/"
    pd.DataFrame([{
        "profile_id": "1", "fighter": "Alpha One", "profile_url": seed_url,
        "pro_record": "1-0-0", "profile_bout_count": 1,
    }]).to_parquet(base / "fightmatrix_profiles.parquet", index=False)
    pd.DataFrame([_raw_bout()]).to_parquet(base / "fightmatrix_bouts.parquet", index=False)
    (cache / "1.html").write_text(_html("Alpha One", "1-0-0", "Beta Two", "2"), encoding="utf-8")
    (cache / "2.html").write_text(_html("Beta Two", "0-1-0", "Alpha One", "1", "L"), encoding="utf-8")
    return base, cache


def test_completeness_reconciles_unreported_no_contest():
    profile = {"fighter": "A", "pro_record": "1-0-0"}
    bouts = pd.DataFrame({"result": ["win", "nc"]})
    state = classify_profile(profile, bouts)
    assert state["completeness_classification"] == "complete"
    assert state["stated_professional_total"] == 1
    assert state["parsed_history_count"] == 2


def test_completeness_detects_partial_and_malformed_profiles():
    partial = classify_profile({"fighter": "A", "pro_record": "2-0-0"}, pd.DataFrame({"result": ["win"]}))
    malformed = classify_profile({"fighter": None, "pro_record": None}, pd.DataFrame())
    assert partial["completeness_classification"] == "partial"
    assert malformed["completeness_classification"] == "failed"


def test_queue_discovers_stable_opponent_ids_and_enforces_depth(tmp_path: Path):
    base, cache = _base_snapshot(tmp_path)
    queue = initialize_queue(base, tmp_path / "queue.parquet", cache)
    assert queue.set_index("profile_id").loc["1", "discovery_depth"] == 0
    assert queue.set_index("profile_id").loc["2", "discovery_depth"] == 1
    assert queue.set_index("profile_id").loc["2", "referring_profile_id"] == "1"


def test_cached_run_resumes_with_zero_request_budget(tmp_path: Path):
    base, cache = _base_snapshot(tmp_path)
    out = tmp_path / "out"
    result = run_expansion(
        base, out, cache_dir=cache,
        config=ExpansionConfig(max_depth=1, max_new_profiles_per_run=1, request_budget=0, sleep_seconds=0),
        progress=False,
    )
    queue = pd.read_parquet(out / "fightmatrix_profile_queue.parquet").set_index("profile_id")
    assert result["new_profiles_this_run"] == 1
    assert result["live_requests_this_run"] == 0
    assert queue.loc["2", "parse_status"] == "parsed"
    assert queue.loc["2", "expansion_stop_reason"] == "maximum_depth"
    resumed = run_expansion(
        base, out, cache_dir=cache,
        config=ExpansionConfig(max_depth=1, max_new_profiles_per_run=1, request_budget=0, sleep_seconds=0),
        progress=False,
    )
    assert resumed["new_profiles_this_run"] == 0
    provenance = pd.read_parquet(out / "fightmatrix_profile_provenance.parquet")
    assert {"public_url", "fetch_timestamp", "http_status", "content_sha256", "parser_version",
            "snapshot_date", "profile_id", "discovery_depth", "raw_cache_path",
            "tls_verification", "cache_hit"}.issubset(provenance.columns)
    assert provenance["content_sha256"].str.len().eq(64).all()


def test_request_budget_preserves_uncached_queue(tmp_path: Path):
    base, cache = _base_snapshot(tmp_path)
    (cache / "2.html").unlink()
    out = tmp_path / "out"
    result = run_expansion(
        base, out, cache_dir=cache,
        config=ExpansionConfig(max_depth=1, request_budget=0, sleep_seconds=0), progress=False,
    )
    queue = pd.read_parquet(out / "fightmatrix_profile_queue.parquet").set_index("profile_id")
    assert result["stop_reason"] == "request_budget"
    assert queue.loc["2", "fetch_status"] == "pending"


def test_depth_boundary_is_discovered_but_not_fetched(tmp_path: Path):
    base, cache = _base_snapshot(tmp_path)
    (cache / "2.html").write_text(_html("Beta Two", "1-0-0", "Gamma Three", "3"), encoding="utf-8")
    out = tmp_path / "boundary"
    run_expansion(
        base, out, cache_dir=cache,
        config=ExpansionConfig(max_depth=1, max_new_profiles_per_run=1, request_budget=0, sleep_seconds=0),
        progress=False,
    )
    queue = pd.read_parquet(out / "fightmatrix_profile_queue.parquet").set_index("profile_id")
    assert queue.loc["3", "discovery_depth"] == 2
    assert queue.loc["3", "fetch_status"] == "not_eligible"
    assert queue.loc["3", "expansion_stop_reason"] == "maximum_depth"


def test_retry_limit_records_failure_without_losing_queue(tmp_path: Path, monkeypatch):
    base, cache = _base_snapshot(tmp_path)
    (cache / "2.html").unlink()
    import loaders.fightmatrix_expansion as expansion
    monkeypatch.setattr(expansion, "_fetch", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("malformed")))
    out = tmp_path / "failed"
    run_expansion(
        base, out, cache_dir=cache,
        config=ExpansionConfig(max_depth=1, request_budget=1, max_retries=1, sleep_seconds=0),
        progress=False,
    )
    row = pd.read_parquet(out / "fightmatrix_profile_queue.parquet").set_index("profile_id").loc["2"]
    assert row["fetch_status"] == "failed"
    assert row["parse_status"] == "failed"
    assert row["expansion_stop_reason"] == "retry_limit"
    assert "malformed" in row["last_error"]


@pytest.mark.parametrize("name_a,name_b", [
    ("José Aldo", "Jose Aldo"),
    ("Conor O’Malley", "Conor O'Malley"),
    ("Jean-Luc Picard", "Jean Luc Picard"),
    ('Quinton "Rampage" Jackson', "Quinton Jackson"),
    ("John Junior", "John Jr."),
])
def test_identity_normalization_regressions(name_a: str, name_b: str):
    assert identity_name_key(name_a) == identity_name_key(name_b)


def test_identity_uses_profile_ids_and_does_not_merge_ambiguous_names(tmp_path: Path):
    profiles = pd.DataFrame([
        {"profile_id": "1", "fighter": "Alex Lee"},
        {"profile_id": "2", "fighter": "Alex Lee"},
    ])
    identity, exceptions = build_identity_artifacts(
        profiles, pd.DataFrame(), pd.DataFrame({"fighter": ["Alex Lee"]}),
        overrides_path=tmp_path / "missing.csv",
    )
    assert identity["internal_fighter_id"].nunique() == 2
    assert identity["ufc_fighter"].isna().all()
    assert "duplicate_normalized_name" in set(exceptions["exception_type"])


def test_organization_normalization_is_time_aware_and_unknowns_survive():
    assert normalize_organization("PRIDE 33", "2007-02-24")["canonical_organization"] == "PRIDE"
    assert normalize_organization("Pancrase 1995", "1995-01-01")["organization_tier"] == 2
    assert normalize_organization("Pancrase 350", "2024-01-01")["organization_tier"] == 3
    unknown = normalize_organization("Basement Combat 7", "2020-01-01")
    assert unknown["canonical_organization"] == "Unknown"
    assert unknown["organization_confidence"] == 0.0


def test_reconciliation_classifies_reciprocal_and_inverts_result():
    rows = [_raw_bout(), _raw_bout("Beta Two", "2", "Alpha One", "1", "loss")]
    resolved, audit = reconcile_bouts(pd.DataFrame(rows))
    assert len(resolved) == 1
    assert set(audit["deduplication_classification"]) == {"reciprocal_profile_records"}
    assert audit["deduplication_decision"].eq("selected").sum() == 1


def test_reconciliation_preserves_conflicts_without_selecting_one():
    rows = [_raw_bout(), _raw_bout("Beta Two", "2", "Alpha One", "1", "win")]
    resolved, audit = reconcile_bouts(pd.DataFrame(rows))
    assert resolved.empty
    assert set(audit["deduplication_classification"]) == {"conflicting_records"}


def test_reconciliation_excludes_ufc_overlap():
    ufc = pd.DataFrame([{"fighter_a": "Alpha One", "fighter_b": "Beta Two", "event_date": pd.Timestamp("2022-01-01")}])
    resolved, audit = reconcile_bouts(pd.DataFrame([_raw_bout()]), ufc)
    assert resolved.empty
    assert audit.iloc[0]["deduplication_classification"] == "ufc_source_overlap"


def test_reconciliation_excludes_ufc_overlap_across_the_date_line():
    """A public profile may date an Asian card one day after the UFC source."""
    ufc = pd.DataFrame([{
        "fighter_a": "Alpha One", "fighter_b": "Beta Two",
        "event_date": pd.Timestamp("2021-12-31"),
    }])
    resolved, audit = reconcile_bouts(pd.DataFrame([_raw_bout()]), ufc)
    assert resolved.empty
    assert audit.iloc[0]["deduplication_classification"] == "ufc_source_overlap"


@pytest.mark.parametrize("ufc_name", ["Alph One", "One", "Alpha Robert One"])
def test_reconciliation_matches_ufc_name_variants(ufc_name: str):
    """Shortened, lengthened and prefix first-name variants are the same bout."""
    ufc = pd.DataFrame([{
        "fighter_a": ufc_name, "fighter_b": "Beta Two",
        "event_date": pd.Timestamp("2022-01-01"),
    }])
    resolved, audit = reconcile_bouts(pd.DataFrame([_raw_bout()]), ufc)
    assert resolved.empty
    assert audit.iloc[0]["deduplication_classification"] == "ufc_source_overlap"


def test_reconciliation_matches_nickname_first_name_beside_an_exact_opponent():
    """``Tank Abbott`` versus ``David Abbott`` is the same bout when the other
    fighter matches exactly on the same event day."""
    ufc = pd.DataFrame([{
        "fighter_a": "Zenon One", "fighter_b": "Beta Two",
        "event_date": pd.Timestamp("2022-01-01"),
    }])
    resolved, audit = reconcile_bouts(pd.DataFrame([_raw_bout()]), ufc)
    assert resolved.empty
    assert audit.iloc[0]["deduplication_classification"] == "ufc_source_overlap"


def test_reconciliation_requires_one_exact_side_before_merging_variants():
    """Two loose family-name matches on one day are not enough to merge."""
    ufc = pd.DataFrame([{
        "fighter_a": "Zenon One", "fighter_b": "Yuri Two",
        "event_date": pd.Timestamp("2022-01-01"),
    }])
    resolved, audit = reconcile_bouts(pd.DataFrame([_raw_bout()]), ufc)
    assert len(resolved) == 1
    assert audit.iloc[0]["deduplication_classification"] != "ufc_source_overlap"


def test_reconciliation_does_not_merge_a_different_opponent():
    ufc = pd.DataFrame([{
        "fighter_a": "Alpha One", "fighter_b": "Gamma Three",
        "event_date": pd.Timestamp("2022-01-01"),
    }])
    resolved, audit = reconcile_bouts(pd.DataFrame([_raw_bout()]), ufc)
    assert len(resolved) == 1
    assert audit.iloc[0]["deduplication_classification"] != "ufc_source_overlap"


def test_reconciliation_marks_one_day_event_alias_as_likely_duplicate():
    first = _raw_bout(event_id=None, date="2022-01-01", key="a")
    second = _raw_bout(event_id=None, date="2022-01-02", key="b")
    second["event_name"] = "Ultimate Fighting Championship Test"
    resolved, audit = reconcile_bouts(pd.DataFrame([first, second]))
    assert len(resolved) == 1
    assert set(audit["deduplication_classification"]) == {"likely_duplicate"}


def test_reconciliation_is_deterministic():
    rows = pd.DataFrame([_raw_bout(), _raw_bout("Beta Two", "2", "Alpha One", "1", "loss")])
    first, first_audit = reconcile_bouts(rows)
    second, second_audit = reconcile_bouts(rows.sample(frac=1, random_state=7).reset_index(drop=True))
    assert first.iloc[0]["deduplication_key"] == second.iloc[0]["deduplication_key"]
    assert set(first_audit["deduplication_classification"]) == set(second_audit["deduplication_classification"])


def _policy_inputs(tmp_path: Path):
    base = tmp_path / "base_policy"
    base.mkdir()
    pd.DataFrame([
        {"fighter": "Alpha One", "mu_canonical": 1600.0, "rating_periods": 5, "recent_division": "Lightweight"},
        {"fighter": "Beta Two", "mu_canonical": 1500.0, "rating_periods": 5, "recent_division": "Lightweight"},
    ]).to_parquet(base / "ratings_current.parquet", index=False)
    profiles = pd.DataFrame([
        {"profile_id": "1", "fighter": "Alpha One", "completeness_classification": "complete", "stated_professional_total": 1, "parsed_history_count": 1},
        {"profile_id": "2", "fighter": "Beta Two", "completeness_classification": "partial", "stated_professional_total": 4, "parsed_history_count": 1},
    ])
    identity = pd.DataFrame([
        {"canonical_display_name": "Alpha One", "ufc_fighter": "Alpha One"},
        {"canonical_display_name": "Beta Two", "ufc_fighter": "Beta Two"},
    ])
    resolved = pd.DataFrame([_raw_bout(event_id="199", key="fightmatrix::199::alphaone::betatwo")])
    resolved["event_name"] = "PRIDE 1"
    resolved["org"] = "PRIDE"
    resolved["source_bout_identifier"] = resolved["fight_key"]
    resolved["deduplication_key"] = "event:199::1::2"
    resolved["deduplication_decision"] = "unique"
    return base, profiles, identity, resolved


def test_complete_edge_and_reliability_policies(tmp_path: Path):
    base, profiles, identity, resolved = _policy_inputs(tmp_path)
    strict = build_model_input(resolved, profiles, identity, base, config=PolicyConfig(policy="complete_edge", minimum_completeness=.8))
    weighted = build_model_input(resolved, profiles, identity, base, config=PolicyConfig(policy="reliability"))
    boundary = build_model_input(resolved, profiles, identity, base, config=PolicyConfig(policy="boundary"))
    assert strict.iloc[0]["is_excluded"]
    assert not weighted.iloc[0]["is_excluded"]
    assert 0 < weighted.iloc[0]["final_model_weight"] < 1
    assert weighted.iloc[0]["initial_uncertainty_multiplier"] > 1
    assert not boundary.iloc[0]["is_excluded"]
    assert boundary.iloc[0]["final_model_weight"] > 0
    assert boundary.iloc[0]["initial_uncertainty_multiplier"] > 1


def test_reference_field_leakage_fails_closed():
    with pytest.raises(ValueError, match="reference fields"):
        assert_no_reference_leakage(pd.DataFrame({"fighter_a": ["A"], "rating_points": [99]}))


def test_snapshot_finalization_is_immutable(tmp_path: Path):
    (tmp_path / "fightmatrix_expansion_manifest.json").write_text("{}", encoding="utf-8")
    marker = finalize_snapshot(tmp_path)
    assert marker.exists()
    with pytest.raises(FileExistsError):
        finalize_snapshot(tmp_path)


def test_scope_comparison_report_generation(tmp_path: Path):
    scopes = {}
    for scope, scores in (("ufc_only", [1600.0, 1500.0]), ("expanded", [1550.0, 1650.0])):
        path = tmp_path / scope
        path.mkdir()
        pd.DataFrame({
            "fighter": ["Jon Jones", "Georges St-Pierre"],
            DEFAULT_SCORE_COLUMN: scores, "rating_periods": [10, 10], "gender": ["M", "M"],
        }).to_parquet(path / "ratings_current.parquet", index=False)
        pd.DataFrame([{"fight_url": "x"}]).to_parquet(path / "canonical_fights.parquet", index=False)
        scopes[scope] = path
    pd.DataFrame({
        "fighter": ["Jon Jones", "Georges St. Pierre"], "rank": [2, 1],
    }).to_parquet(scopes["ufc_only"] / "fightmatrix_all_time.parquet", index=False)
    comparison, panel = build_scope_validation(scopes, tmp_path)
    assert set(comparison["scope"]) == {"ufc_only", "expanded"}
    assert {"reference_rank_spearman", "mean_absolute_rank_error", "top30_churn_vs_ufc"}.issubset(comparison.columns)
    assert set(panel["panel"]) == {"historical", "unexpected_loss"}
    assert (tmp_path / "fightmatrix_scope_validation.parquet").exists()
    assert {"common_subset_spearman", "common_reference_fighters"}.issubset(comparison.columns)


def test_notebook_ready_visualizations_smoke():
    queue = pd.DataFrame({
        "profile_id": ["1", "2"], "discovery_depth": [0, 1],
        "http_success": [True, False], "parse_status": ["parsed", "pending"],
        "completeness_classification": ["complete", "unresolved"],
    })
    fighters = pd.DataFrame({
        "fighter": ["A"], "weighted_opponent_coverage": [.5], "observed_edge_count": [3],
    })
    panel = pd.DataFrame({
        "scope": ["ufc_only", "raw_expanded"], "fighter": ["A", "A"],
        "model_rank": [2, 1], "reference_rank": [1, 1],
    })
    figures = [
        expansion_funnel_chart(queue), closure_by_depth_chart(queue),
        component_sizes_chart(pd.DataFrame({"component_rank": [1], "component_size": [2]})),
        degree_distribution_chart(pd.DataFrame({"degree": [1], "fighter_count": [2]})),
        incomplete_exposure_chart(fighters), rank_movement_chart(panel),
        reference_residual_chart(panel),
        policy_sensitivity_chart(pd.DataFrame({
            "policy": ["raw"], "eligible_weight_sum": [1.0], "eligible_bouts": [1],
            "mean_eligible_weight": [1.0],
        })),
        organization_coverage_chart(pd.DataFrame({"canonical_organization": ["UFC"], "bout_count": [1]})),
        data_quality_chart(pd.DataFrame({"exception_type": ["unmatched"]})),
    ]
    assert all(len(figure.data) > 0 for figure in figures)


def test_depth_and_case_study_visualizations_smoke():
    model_bouts = pd.DataFrame({
        "fighter_a_profile_id": ["1", "1"], "fighter_b_profile_id": ["2", "3"],
        "fighter_a_completeness": [1.0, 1.0], "fighter_b_completeness": [1.0, .2],
        "final_model_weight": [.9, .4],
    })
    completeness = pd.DataFrame({
        "profile_id": ["1", "2", "3"], "discovery_depth": [0, 1, 2],
    })
    support = weighted_edge_support_by_depth_chart(model_bouts, completeness)
    organizations = pd.DataFrame({
        "canonical_organization": ["PRIDE", "PRIDE"], "bout_count": [4, 6],
        "first_event_date": pd.to_datetime(["2000-01-01", "2003-01-01"]),
    })
    movements = pd.DataFrame({
        "scope": ["depth_one_raw"], "fighter": ["A"], "score_delta_vs_ufc": [-12.5],
    })
    traces = pd.DataFrame({
        "fighter": ["A"], "opponent": ["B"], "event_date": pd.to_datetime(["2005-01-01"]),
        "opponent_rating_at_time": [1600.0], "opponent_completeness": [.9],
        "model_weight": [.8], "organization": ["PRIDE"], "result": ["win"],
    })
    figures = [
        support, organization_coverage_over_time_chart(organizations),
        score_movement_chart(movements), case_study_chart(traces, "A"),
    ]
    assert all(len(figure.data) > 0 for figure in figures)
    assert support.data[0].y[0] == pytest.approx(1.0)


@pytest.mark.parametrize("public, ufc", [
    ("Jingliang Li", "Li Jingliang"),
    ("Weili Zhang", "Zhang Weili"),
    ("Nuerdanbieke Shayilan", "Shayilan Nuerdanbieke"),
])
def test_name_order_permutation_is_the_same_fighter(public: str, ufc: str):
    """Public sources render Chinese names given-name-first; the UFC source
    renders them family-name-first."""
    assert _names_compatible(_name_tokens(public), _name_tokens(ufc))


@pytest.mark.parametrize("public, ufc", [
    ("Khalil Rountree", "Khalil Rountree Jr."),
    ("Marvin Vettori Sr", "Marvin Vettori"),
])
def test_generational_suffix_is_ignored(public: str, ufc: str):
    assert _names_compatible(_name_tokens(public), _name_tokens(ufc))


@pytest.mark.parametrize("public, ufc", [
    ("Renato Carneiro", "Renato Moicano"),
    ("Rony Mariano Bezerra", "Rony Jason"),
    ("Mizuki Inoue", "Mizuki"),
    ("Patricio Freire", "Patricio Pitbull"),
])
def test_committed_ring_name_aliases_resolve(public: str, ufc: str):
    """A ring name that replaces the family name cannot be derived from the
    strings, so it is carried in the committed alias table."""
    assert _names_compatible(_name_tokens(public), _name_tokens(ufc))


def test_alias_table_never_merges_unrelated_fighters():
    assert not _names_compatible(_name_tokens("Jon Jones"), _name_tokens("Jon Fitch"))
    assert not _names_compatible(_name_tokens("Renato Carneiro"), _name_tokens("Renato Sobral"))


def test_alias_table_is_loadable_and_documented():
    aliases = load_name_aliases()
    assert aliases
    assert all(key != value for key, value in aliases.items())


@pytest.mark.parametrize("public, ufc", [
    ("Georges St. Pierre", "Georges St-Pierre"),
    ("Marc Andre Barriault", "Marc-Andre Barriault"),
])
def test_hyphen_is_punctuation_not_a_name_boundary(public: str, ufc: str):
    """The public source writes a period and a space where the UFC source
    writes a hyphen; both are the same family name."""
    assert _names_compatible(_name_tokens(public), _name_tokens(ufc))
