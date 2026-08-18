"""Notebook-ready Plotly views for FightMatrix expansion artifacts."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


COLORS = {"ufc_only": "#94a3b8", "raw": "#f59e0b", "controlled": "#22c55e"}


def expansion_funnel_chart(queue: pd.DataFrame) -> go.Figure:
    discovered = len(queue)
    fetched = int(queue["http_success"].fillna(False).sum())
    parsed = int(queue["parse_status"].eq("parsed").sum())
    complete = int(queue["completeness_classification"].eq("complete").sum())
    return go.Figure(go.Funnel(
        y=["Discovered", "Fetched", "Parsed", "Record reconciled"],
        x=[discovered, fetched, parsed, complete], marker_color="#38bdf8",
    )).update_layout(title="Opponent expansion funnel")


def closure_by_depth_chart(queue: pd.DataFrame) -> go.Figure:
    depth = queue.groupby("discovery_depth").agg(
        discovered=("profile_id", "size"),
        parsed=("parse_status", lambda values: values.eq("parsed").sum()),
    ).reset_index()
    depth["closure"] = depth["parsed"] / depth["discovered"]
    return go.Figure(go.Bar(
        x=depth["discovery_depth"], y=depth["closure"],
        customdata=depth[["parsed", "discovered"]],
        hovertemplate="Depth %{x}<br>%{customdata[0]} / %{customdata[1]}<extra></extra>",
        marker_color="#38bdf8",
    )).update_layout(title="Graph closure by discovery depth", yaxis_tickformat=".0%")


def component_sizes_chart(components: pd.DataFrame, limit: int = 30) -> go.Figure:
    view = components.nsmallest(limit, "component_rank")
    return go.Figure(go.Bar(
        x=view["component_rank"], y=view["component_size"], marker_color="#a78bfa",
    )).update_layout(title="Connected-component sizes", xaxis_title="Component rank")


def degree_distribution_chart(degree: pd.DataFrame) -> go.Figure:
    return go.Figure(go.Bar(
        x=degree["degree"], y=degree["fighter_count"], marker_color="#a78bfa",
    )).update_layout(title="Fighter degree distribution", xaxis_type="log", yaxis_type="log")


def incomplete_exposure_chart(fighters: pd.DataFrame, limit: int = 30) -> go.Figure:
    view = fighters.sort_values(
        ["weighted_opponent_coverage", "observed_edge_count"], ascending=[True, False]
    ).head(limit)
    return go.Figure(go.Bar(
        x=view["weighted_opponent_coverage"], y=view["fighter"], orientation="h",
        marker_color="#f59e0b",
    )).update_layout(
        title="Highest incomplete-history exposure", xaxis_tickformat=".0%",
        yaxis={"autorange": "reversed"},
    )


def rank_movement_chart(panel: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for scope, group in panel.groupby("scope", sort=False):
        color = COLORS["ufc_only"] if scope == "ufc_only" else (
            COLORS["raw"] if "raw" in scope else COLORS["controlled"]
        )
        fig.add_bar(name=scope, x=group["fighter"], y=group["model_rank"], marker_color=color)
    return fig.update_layout(
        title="Historical-panel rank by source scope", barmode="group",
        yaxis={"autorange": "reversed"},
    )


def reference_residual_chart(panel: pd.DataFrame) -> go.Figure:
    view = panel.dropna(subset=["model_rank", "reference_rank"]).copy()
    view["rank_residual"] = view["model_rank"] - view["reference_rank"]
    fig = go.Figure()
    for scope, group in view.groupby("scope", sort=False):
        fig.add_scatter(
            name=scope, x=group["fighter"], y=group["rank_residual"], mode="markers",
        )
    return fig.update_layout(title="Reference-rank residuals", yaxis_title="Model rank − reference rank")


def policy_sensitivity_chart(policies: pd.DataFrame) -> go.Figure:
    return go.Figure(go.Bar(
        x=policies["policy"], y=policies["eligible_weight_sum"],
        customdata=policies[["eligible_bouts", "mean_eligible_weight"]],
        hovertemplate="%{x}<br>weight sum %{y:.1f}<br>%{customdata[0]} bouts"
                      "<br>mean %{customdata[1]:.3f}<extra></extra>",
        marker_color="#22c55e",
    )).update_layout(title="Sensitivity to completeness policy")


def organization_coverage_chart(organization_map: pd.DataFrame, limit: int = 20) -> go.Figure:
    view = organization_map.groupby("canonical_organization", as_index=False)["bout_count"].sum()
    view = view.nlargest(limit, "bout_count")
    return go.Figure(go.Bar(
        x=view["canonical_organization"], y=view["bout_count"], marker_color="#38bdf8",
    )).update_layout(title="Organization coverage", xaxis_tickangle=-35)


def data_quality_chart(exceptions: pd.DataFrame) -> go.Figure:
    counts = exceptions["exception_type"].value_counts().reset_index()
    counts.columns = ["exception_type", "count"]
    return go.Figure(go.Bar(
        x=counts["exception_type"], y=counts["count"], marker_color="#ef4444",
    )).update_layout(title="Identity and data-quality exceptions", xaxis_tickangle=-35)


def weighted_edge_support_by_depth_chart(
    model_bouts: pd.DataFrame, completeness: pd.DataFrame, *, threshold: float = 0.8,
) -> go.Figure:
    """Share of each depth's edges whose two endpoints both clear ``threshold``."""
    depth_by_id = dict(zip(
        completeness["profile_id"].astype(str), completeness["discovery_depth"],
    ))
    work = model_bouts.copy()
    a_depth = work["fighter_a_profile_id"].astype(str).map(depth_by_id)
    b_depth = work["fighter_b_profile_id"].astype(str).map(depth_by_id)
    work["edge_depth"] = pd.concat([a_depth, b_depth], axis=1).max(axis=1)
    supported = work[["fighter_a_completeness", "fighter_b_completeness"]].min(axis=1).ge(threshold)
    work["supported_weight"] = work["final_model_weight"].where(supported, 0.0)
    grouped = work.groupby("edge_depth").agg(
        supported=("supported_weight", "sum"), total=("final_model_weight", "sum"),
    ).reset_index()
    grouped["support"] = grouped["supported"] / grouped["total"].replace(0.0, pd.NA)
    return go.Figure(go.Bar(
        x=grouped["edge_depth"], y=grouped["support"],
        customdata=grouped[["supported", "total"]], marker_color="#22c55e",
        hovertemplate="Depth %{x}<br>%{customdata[0]:.0f} / %{customdata[1]:.0f} weight<extra></extra>",
    )).update_layout(
        title="Weighted edge support by discovery depth",
        xaxis_title="Deepest endpoint depth", yaxis_tickformat=".0%",
    )


def organization_coverage_over_time_chart(
    organization_map: pd.DataFrame, *, limit: int = 8,
) -> go.Figure:
    """Bout counts per canonical organization per year, largest promotions only."""
    work = organization_map.copy()
    work["year"] = pd.to_datetime(work["first_event_date"], errors="coerce").dt.year
    top = work.groupby("canonical_organization")["bout_count"].sum().nlargest(limit).index
    fig = go.Figure()
    for organization in top:
        view = work[work["canonical_organization"].eq(organization)]
        view = view.groupby("year", as_index=False)["bout_count"].sum().sort_values("year")
        fig.add_scatter(name=str(organization), x=view["year"], y=view["bout_count"], mode="lines")
    return fig.update_layout(title="Organization coverage over time", xaxis_title="Year")


def score_movement_chart(movements: pd.DataFrame, *, limit: int = 25) -> go.Figure:
    """Largest score movements away from the UFC-only baseline, by scope."""
    view = movements.dropna(subset=["score_delta_vs_ufc"]).copy()
    order = view.groupby("fighter")["score_delta_vs_ufc"].apply(
        lambda values: values.abs().max()
    ).nlargest(limit).index
    view = view[view["fighter"].isin(order)]
    fig = go.Figure()
    for scope, group in view.groupby("scope", sort=False):
        color = COLORS["ufc_only"] if scope == "ufc_only" else (
            COLORS["raw"] if "raw" in scope else COLORS["controlled"]
        )
        fig.add_bar(name=scope, x=group["fighter"], y=group["score_delta_vs_ufc"], marker_color=color)
    return fig.update_layout(
        title="Score movement versus UFC-only", barmode="group", xaxis_tickangle=-35,
    )


def case_study_chart(traces: pd.DataFrame, fighter: str) -> go.Figure:
    """Per-bout evidence for one historical fighter: weight against opponent rating."""
    view = traces[traces["fighter"].eq(fighter)].sort_values("event_date")
    return go.Figure(go.Scatter(
        x=pd.to_datetime(view["event_date"]), y=view["opponent_rating_at_time"],
        mode="markers", marker={
            "size": 6 + 18 * view["model_weight"].fillna(0.0),
            "color": view["opponent_completeness"], "colorscale": "Viridis",
            "cmin": 0.0, "cmax": 1.0, "colorbar": {"title": "opponent<br>completeness"},
        },
        text=view["opponent"] + " · " + view["organization"].fillna("Unknown")
             + " · " + view["result"],
        hovertemplate="%{text}<br>%{x|%Y-%m-%d}<br>opponent rating %{y:.0f}<extra></extra>",
    )).update_layout(title=f"Added public evidence: {fighter}", yaxis_title="Opponent rating at bout")
