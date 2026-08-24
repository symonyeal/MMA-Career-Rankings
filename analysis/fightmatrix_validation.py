"""Multi-scope validation and per-bout anomaly traces for expansion experiments."""
from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from ratings.scope import SCOPE_ARTIFACT

from analysis.source_scope import resolve_score_column
from project_helpers import normalize_name_key


HISTORICAL_PANEL = [
    "Georges St-Pierre", "Jon Jones", "Anderson Silva", "Jose Aldo",
    "Demetrious Johnson", "Fedor Emelianenko", "Antonio Rodrigo Nogueira",
    "Wanderlei Silva", "Dan Henderson", "Urijah Faber", "Eddie Alvarez", "BJ Penn",
    "Matt Hughes", "Chuck Liddell", "Randy Couture", "Dominick Cruz", "Frankie Edgar",
    "Lyoto Machida", "Khabib Nurmagomedov", "Daniel Cormier",
]
ANOMALY_PANEL = [
    "Joseph Benavidez", "Raphael Assuncao", "Andrei Arlovski", "Forrest Griffin",
    "Mark Hunt", "Rich Franklin",
]


def _rank_table(snapshot: Path, score_column: str) -> pd.DataFrame:
    current = pd.read_parquet(Path(snapshot) / "ratings_current.parquet")
    if "gender" in current:
        current = current[current["gender"].eq("M")]
    current = current.dropna(subset=["fighter", score_column]).copy()
    current["rank"] = current[score_column].rank(method="min", ascending=False).astype(int)
    current["name_key"] = current["fighter"].map(lambda value: normalize_name_key(value, compact=True))
    return current[["fighter", "name_key", score_column, "rank", "rating_periods"]]


def _common_subset_metrics(
    ranked: pd.DataFrame, reference: pd.DataFrame, common_keys: set[str], score_column: str,
) -> dict:
    """Score one scope on the fighters every scope shares with the reference.

    Ranks are recomputed inside the shared subset, so a scope is not penalised
    for simply having a larger cohort.
    """
    if not common_keys:
        return {
            "common_subset_spearman": None, "common_subset_mean_absolute_rank_error": None,
            "common_subset_median_absolute_rank_error": None,
        }
    subset = ranked[ranked["name_key"].isin(common_keys)].merge(
        reference[reference["name_key"].isin(common_keys)], on="name_key", how="inner",
    )
    subset["subset_model_rank"] = subset[score_column].rank(method="min", ascending=False)
    subset["subset_reference_rank"] = subset["reference_rank"].rank(method="min")
    error = (subset["subset_model_rank"] - subset["subset_reference_rank"]).abs()
    return {
        "common_subset_spearman": float(
            subset["subset_model_rank"].corr(subset["subset_reference_rank"], method="spearman")
        ),
        "common_subset_mean_absolute_rank_error": float(error.mean()),
        "common_subset_median_absolute_rank_error": float(error.median()),
    }


def build_scope_validation(
    scopes: dict[str, Path],
    output_dir: Path,
    *,
    score_column: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Persist scope statistics and the required historical validation panel."""
    output_dir = Path(output_dir)
    base_name = "ufc_only" if "ufc_only" in scopes else next(iter(scopes))
    score_column = resolve_score_column(
        [pd.read_parquet(Path(path) / "ratings_current.parquet") for path in scopes.values()],
        score_column,
    )
    base = _rank_table(scopes[base_name], score_column)
    reference_path = Path(scopes[base_name]) / "fightmatrix_all_time.parquet"
    reference = pd.read_parquet(reference_path)[["fighter", "rank"]].copy()
    reference["name_key"] = reference["fighter"].map(lambda value: normalize_name_key(value, compact=True))
    reference = reference.rename(columns={"rank": "reference_rank"}).drop(columns="fighter")
    rows = []
    panel_rows = []
    movement_frames = []
    base_top30 = set(base.nsmallest(30, "rank")["name_key"])
    # Cohort size differs by scope, so a raw rank error is not comparable across
    # scopes. Every scope is additionally scored on the fighters that all scopes
    # and the public reference share, re-ranked inside that common subset.
    ranked_by_scope = {scope: _rank_table(path, score_column) for scope, path in scopes.items()}
    reference_keys = set(reference["name_key"])
    common_keys = set.intersection(*(
        set(frame["name_key"]) & reference_keys for frame in ranked_by_scope.values()
    )) if ranked_by_scope else set()
    for scope, path in scopes.items():
        ranked = ranked_by_scope[scope]
        matched = ranked.merge(reference, on="name_key", how="inner")
        compared = ranked.merge(base[["name_key", "rank"]], on="name_key", suffixes=("", "_base"))
        abs_error = (matched["rank"] - matched["reference_rank"]).abs()
        top30 = set(ranked.nsmallest(30, "rank")["name_key"])
        movement = ranked.merge(
            base[["name_key", "rank", score_column]].rename(columns={
                "rank": "ufc_only_rank", score_column: "ufc_only_score",
            }),
            on="name_key", how="left",
        ).merge(reference, on="name_key", how="left")
        movement["scope"] = scope
        movement["cohort_size"] = len(ranked)
        movement["model_percentile"] = movement["rank"] / len(ranked)
        movement["ufc_only_percentile"] = movement["ufc_only_rank"] / len(base)
        movement["percentile_delta_vs_ufc"] = movement["model_percentile"] - movement["ufc_only_percentile"]
        movement["rank_delta_vs_ufc"] = movement["rank"] - movement["ufc_only_rank"]
        movement["score_delta_vs_ufc"] = movement[score_column] - movement["ufc_only_score"]
        movement["absolute_reference_rank_error"] = (movement["rank"] - movement["reference_rank"]).abs()
        movement["top30"] = movement["rank"].le(30)
        movement_frames.append(movement.rename(columns={score_column: "model_score", "rank": "model_rank"}))
        graph_path = Path(path) / "fightmatrix_graph_metrics.parquet"
        graph = pd.read_parquet(graph_path).iloc[0].to_dict() if graph_path.exists() else {}
        headline_path = Path(path) / "fightmatrix_headline_eligibility.parquet"
        if headline_path.exists():
            headline = pd.read_parquet(headline_path)
            headline_count = int(headline.get(
                "uncertainty_headline_eligible", pd.Series(False, index=headline.index)
            ).fillna(False).sum())
        else:
            headline_count = int(ranked["rating_periods"].fillna(0).ge(3).sum())
        cross_path = Path(path) / SCOPE_ARTIFACT["fightmatrix"]
        cross = pd.read_parquet(cross_path) if cross_path.exists() else pd.DataFrame()
        canonical = pd.read_parquet(Path(path) / "canonical_fights.parquet")
        runtime_path = Path(path) / "fightmatrix_rating_runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.exists() else {}
        rows.append({
            "scope": scope,
            "profiles": graph.get("parsed_profiles", 0),
            "unique_fighters": int(len(ranked)),
            "bouts": int(len(canonical) + len(cross)),
            "model_ready_bouts": int(len(canonical) + ((~cross.get("is_excluded", pd.Series(False, index=cross.index))).sum() if not cross.empty else 0)),
            "connected_components": graph.get("connected_components"),
            "largest_component": graph.get("largest_connected_component_size"),
            "graph_closure": graph.get("graph_closure"),
            "weighted_edge_support": graph.get("weighted_edge_support"),
            "fighters_eligible_for_headline": headline_count,
            "rating_stability_spearman_vs_ufc": float(compared["rank"].corr(compared["rank_base"], method="spearman")),
            "reference_rank_spearman": float(matched["rank"].corr(matched["reference_rank"], method="spearman")),
            "mean_absolute_rank_error": float(abs_error.mean()),
            "median_absolute_rank_error": float(abs_error.median()),
            "top30_churn_vs_ufc": int(len(base_top30.symmetric_difference(top30)) // 2),
            "reference_matches": int(len(matched)),
            "common_reference_fighters": int(len(common_keys)),
            **_common_subset_metrics(ranked, reference, common_keys, score_column),
            "runtime_seconds": runtime.get("runtime_seconds"),
        })
        lookup = ranked.set_index("name_key")
        ref_lookup = reference.set_index("name_key")
        for fighter in HISTORICAL_PANEL + ANOMALY_PANEL:
            key = normalize_name_key(fighter, compact=True)
            panel_rows.append({
                "scope": scope, "fighter": fighter,
                "cohort_size": int(len(ranked)),
                "model_rank": int(lookup.loc[key, "rank"]) if key in lookup.index else None,
                "model_percentile": (
                    float(lookup.loc[key, "rank"]) / len(ranked) if key in lookup.index else None
                ),
                "model_score": float(lookup.loc[key, score_column]) if key in lookup.index else None,
                "rating_periods": int(lookup.loc[key, "rating_periods"]) if key in lookup.index else None,
                "reference_rank": int(ref_lookup.loc[key, "reference_rank"]) if key in ref_lookup.index else None,
                "panel": "unexpected_loss" if fighter in ANOMALY_PANEL else "historical",
            })
    comparison = pd.DataFrame(rows)
    panel = pd.DataFrame(panel_rows)
    movements = pd.concat(movement_frames, ignore_index=True, sort=False)
    comparison.to_parquet(output_dir / "fightmatrix_scope_validation.parquet", index=False)
    panel.to_parquet(output_dir / "fightmatrix_historical_panel.parquet", index=False)
    movements.to_parquet(output_dir / "fightmatrix_rank_movements.parquet", index=False)
    return comparison, panel


def build_anomaly_traces(
    snapshot: Path, output_dir: Path, *, scope_name: str = "expanded",
) -> pd.DataFrame:
    """Trace added-bout evidence and rating movement for required anomaly fighters."""
    snapshot = Path(snapshot)
    cross_path = snapshot / SCOPE_ARTIFACT["fightmatrix"]
    history_path = snapshot / "ratings_history_method_integrity_performance.parquet"
    completeness_path = snapshot / "fightmatrix_fighter_completeness.parquet"
    if not cross_path.exists() or not history_path.exists():
        out = pd.DataFrame()
        out.to_parquet(Path(output_dir) / "fightmatrix_anomaly_traces.parquet", index=False)
        return out
    bouts = pd.read_parquet(cross_path)
    history = pd.read_parquet(history_path).sort_values(["fighter", "event_date"])
    mu_col = next(column for column in history.columns if column.startswith("mu_"))
    history["rating_before"] = history.groupby("fighter")[mu_col].shift().fillna(1500.0)
    history["rating_change"] = history[mu_col] - history["rating_before"]
    completeness = pd.read_parquet(completeness_path) if completeness_path.exists() else pd.DataFrame()
    comp_by_name = {
        normalize_name_key(row.fighter, compact=True): row.profile_completeness_score
        for row in completeness.itertuples(index=False)
    } if not completeness.empty else {}
    histories = {name: group for name, group in history.groupby("fighter")}
    records = []
    targets = HISTORICAL_PANEL + ANOMALY_PANEL
    for fighter in targets:
        relevant = bouts[(bouts["fighter_a"].eq(fighter)) | (bouts["fighter_b"].eq(fighter))]
        for bout in relevant.itertuples(index=False):
            opponent = bout.fighter_b if bout.fighter_a == fighter else bout.fighter_a
            own_history = histories.get(fighter, pd.DataFrame())
            opponent_history = histories.get(opponent, pd.DataFrame())
            at_date = own_history[pd.to_datetime(own_history["event_date"]).eq(pd.Timestamp(bout.event_date))]
            opp_prior = opponent_history[pd.to_datetime(opponent_history["event_date"]).le(pd.Timestamp(bout.event_date))]
            opponent_rating = float(opp_prior.iloc[-1][mu_col]) if not opp_prior.empty else 1500.0
            change = float(at_date.iloc[-1]["rating_change"]) if not at_date.empty else None
            comp = float(comp_by_name.get(normalize_name_key(opponent, compact=True), 0.0))
            if comp < 0.8:
                cause = "missing_opponent_history_exposure"
            elif pd.isna(getattr(bout, "fighter_a_profile_id", None)):
                cause = "identity_uncertainty"
            else:
                cause = "new_fight_result_evidence"
            records.append({
                "scope": scope_name, "fighter": fighter, "opponent": opponent, "event_date": bout.event_date,
                "event_name": bout.event_name, "organization": getattr(bout, "org", None),
                "result": "win" if getattr(bout, "winner", None) == fighter else "loss" if getattr(bout, "loser", None) == fighter else "draw_or_nc",
                "opponent_rating_at_time": opponent_rating, "opponent_completeness": comp,
                "model_weight": float(getattr(bout, "org_weight", 1.0)),
                "fighter_rating_change": change,
                "rating_change_scope": "event_period_shared",
                "diagnostic_cause": cause,
            })
    out = pd.DataFrame(records)
    out.to_parquet(Path(output_dir) / "fightmatrix_anomaly_traces.parquet", index=False)
    return out


def build_anomaly_summary(
    panel: pd.DataFrame,
    traces: pd.DataFrame,
    output_dir: Path,
) -> pd.DataFrame:
    """Classify rank movement without treating reference proximity as proof."""
    base = panel[panel["scope"].eq("ufc_only")].set_index("fighter")
    rows = []
    for scope in [value for value in panel["scope"].unique() if value != "ufc_only"]:
        current = panel[panel["scope"].eq(scope)].set_index("fighter")
        for fighter in HISTORICAL_PANEL + ANOMALY_PANEL:
            if fighter not in current.index:
                continue
            current_row = current.loc[fighter]
            base_row = base.loc[fighter] if fighter in base.index else None
            fighter_traces = traces[
                traces["fighter"].eq(fighter)
                & (traces["scope"].eq(scope) if "scope" in traces else True)
            ] if not traces.empty else traces
            low_exposure = float(fighter_traces["opponent_completeness"].lt(.8).mean()) if len(fighter_traces) else 0.0
            rank_delta = (
                float(current_row["model_rank"] - base_row["model_rank"])
                if base_row is not None and pd.notna(base_row["model_rank"]) and pd.notna(current_row["model_rank"])
                else None
            )
            # A scope that rates more fighters lengthens the board, so a worse
            # integer rank is not by itself a worse rating. Percentile movement
            # separates cohort growth from real evidence.
            percentile_delta = (
                float(current_row["model_percentile"] - base_row["model_percentile"])
                if base_row is not None and pd.notna(base_row.get("model_percentile"))
                and pd.notna(current_row.get("model_percentile"))
                else None
            )
            if rank_delta is not None and rank_delta > 0 and percentile_delta is not None and percentile_delta < 0:
                cause = "cohort_growth_artifact"
            elif len(fighter_traces) == 0 and rank_delta not in (None, 0):
                cause = "cohort_dilution"
            elif low_exposure > .25:
                cause = "missing_opponent_history_exposure"
            else:
                cause = "new_fight_result_evidence"
            reference = current_row["reference_rank"]
            before_error = (
                abs(float(base_row["model_rank"] - reference))
                if base_row is not None and pd.notna(base_row["model_rank"]) and pd.notna(reference) else None
            )
            after_error = abs(float(current_row["model_rank"] - reference)) if pd.notna(current_row["model_rank"]) and pd.notna(reference) else None
            movement = (
                "closer_to_reference" if before_error is not None and after_error < before_error
                else "farther_from_reference" if before_error is not None and after_error > before_error
                else "unchanged_or_unmatched"
            )
            rows.append({
                "scope": scope, "fighter": fighter,
                "ufc_only_rank": base_row["model_rank"] if base_row is not None else None,
                "scope_rank": current_row["model_rank"], "rank_delta": rank_delta,
                "ufc_only_cohort_size": base_row["cohort_size"] if base_row is not None else None,
                "scope_cohort_size": current_row["cohort_size"],
                "ufc_only_percentile": base_row["model_percentile"] if base_row is not None else None,
                "scope_percentile": current_row["model_percentile"],
                "percentile_delta": percentile_delta,
                "reference_rank": reference, "reference_movement": movement,
                "added_bout_rows": int(len(fighter_traces)),
                "low_completeness_bout_share": low_exposure,
                "diagnostic_cause": cause,
                "evidence_note": "Reference movement is diagnostic only; causality is assigned from fight and completeness evidence.",
            })
    out = pd.DataFrame(rows)
    out.to_parquet(Path(output_dir) / "fightmatrix_anomaly_summary.parquet", index=False)
    return out
