"""Chart and table builders retired from ``analysis/viz.py`` on 2026-09-01.

None of these were called by ``analysis/build_notebook.py`` or drawn in
``analysis/notebook.ipynb``. Four of them (the ``sleeve_*`` builders and the
modular column selectors) read ``sleeve_attribution.parquet`` and the
``ratings_history_*_method_*`` streams, which no snapshot has produced since the
2026-08-20 core evolution, so they could not run against current data at all.
``rank_movement_chart`` and ``calibration_residuals_chart`` had no caller of any
kind, not even a test.

The code is kept verbatim as evidence of past work. To restore one, paste it back
into ``analysis/viz.py`` and re-add its smoke-test case; the helpers it calls are
still there.
"""
from __future__ import annotations

from plotly.subplots import make_subplots
from project_helpers import date_range, normalize_name_key
from ratings.constants import FIVE_YEAR_PEAK_MIN_FIGHTS, FIVE_YEAR_PEAK_WINDOW_DAYS, FIVE_YEAR_PEAK_WINDOW_LABEL, SUSTAINED_PEAK_MIN_FIGHTS, SUSTAINED_PEAK_WINDOW_LABEL, rating_label, rename_rating_columns
from ratings.glicko2_engine import predict_win_prob_from_ratings, matchup_quality_from_ratings
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from analysis.viz import (  # noqa: F401
    CHART_COLORWAY,
    PERFORMANCE_FACTOR_LABELS,
    SIGN_COLORS,
    STREAM_PALETTE,
    THEME,
    _apply_chart_layout,
    _division_strength_frame,
    _empty_figure,
    _metric_label,
    _normalize_public_view,
    add_division_to_fights,
    compose_rating_stream,
    datalab_scorecard_decision_summary,
    performance_factor_audit_table,
    recent_division_by_fighter,
    select_public_ranking_column,
    select_rating_column,
    source_coverage_summary,
)


def h2h_prediction(
    fighter_a: str, fighter_b: str,
    ratings_current: pd.DataFrame,
    phi_b_override: float | None = None,
) -> dict:
    ra = ratings_current[ratings_current["fighter"] == fighter_a]
    rb = ratings_current[ratings_current["fighter"] == fighter_b]
    if ra.empty:
        return {"error": f"unknown fighter: {fighter_a}"}
    if rb.empty:
        return {"error": f"unknown fighter: {fighter_b}"}

    mu_a, phi_a = float(ra.iloc[0]["mu_canonical"]), float(ra.iloc[0]["phi_canonical"])
    mu_b, phi_b = float(rb.iloc[0]["mu_canonical"]), float(rb.iloc[0]["phi_canonical"])
    if phi_b_override is not None:
        phi_b = float(phi_b_override)

    p_a = predict_win_prob_from_ratings(mu_a, phi_a, mu_b, phi_b)
    quality = matchup_quality_from_ratings(mu_a, phi_a, mu_b, phi_b)
    return {
        "fighter_a": fighter_a,
        "fighter_b": fighter_b,
        "mu_a": round(mu_a, 1), "phi_a": round(phi_a, 1),
        "mu_b": round(mu_b, 1), "phi_b": round(phi_b, 1),
        "p_a_wins": round(p_a, 4),
        "p_b_wins": round(1 - p_a, 4),
        "matchup_quality_0_to_1": round(quality, 4),
    }


def weight_class_strength_chart(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    top_n_per_division: int = 15,
    divisions: list[str] | None = None,
) -> go.Figure:
    """For each (division, year), mean μ_canonical of the top-N fighters
    active in that division that year."""
    if ratings_history is None or ratings_history.empty or fights is None or fights.empty:
        return _empty_figure("rating history or fights unavailable", title="Division strength over time")

    f = add_division_to_fights(fights)
    f["event_date"] = pd.to_datetime(f["event_date"])
    f["year"] = f["event_date"].dt.year

    # Long table of (fighter, year, division) participations
    a = f[["year", "division", "fighter_a"]].rename(columns={"fighter_a": "fighter"})
    b = f[["year", "division", "fighter_b"]].rename(columns={"fighter_b": "fighter"})
    long = pd.concat([a, b], ignore_index=True).dropna(subset=["fighter", "division"])

    # Bring in μ_canonical (use the rating AS-OF that year — the last rating row before year-end)
    rh = ratings_history.copy()
    rh["event_date"] = pd.to_datetime(rh["event_date"])
    rh["year"] = rh["event_date"].dt.year
    eoy = (rh.sort_values("event_date")
             .groupby(["fighter", "year"], as_index=False).last()
             [["fighter", "year", "mu_canonical"]])

    merged = long.merge(eoy, on=["fighter", "year"], how="inner").drop_duplicates(
        subset=["fighter", "year", "division"]
    )

    rows = []
    for (division, year), g in merged.groupby(["division", "year"], dropna=False):
        if pd.isna(division):
            continue
        top = g.sort_values("mu_canonical", ascending=False).head(top_n_per_division)
        if len(top) < 5:
            continue
        rows.append({"division": division, "year": year, "mean_top_mu": top["mu_canonical"].mean()})

    plot_df = pd.DataFrame(rows)
    if plot_df.empty:
        return _empty_figure(
            "no division/year has enough rated fighters for this view",
            title="Division strength over time",
        )
    if divisions is not None:
        plot_df = plot_df[plot_df["division"].isin(divisions)]
    if plot_df.empty:
        return _empty_figure(
            "no selected divisions have enough rated fighters for this view",
            title="Division strength over time",
        )

    fig = go.Figure()
    for i, (div, dfd) in enumerate(plot_df.groupby("division")):
        dfd = dfd.sort_values("year")
        fig.add_trace(go.Scatter(
            x=dfd["year"], y=dfd["mean_top_mu"],
            mode="lines+markers",
            name=div,
            line=dict(color=CHART_COLORWAY[i % len(CHART_COLORWAY)], width=2),
            hovertemplate="<b>%{fullData.name}</b><br>year=%{x}<br>mean top rating=%{y:.1f}<extra></extra>",
        ))
    _apply_chart_layout(fig, height=520)
    fig.update_layout(
        title=f"Division strength over time: top-{top_n_per_division} mean rating",
        xaxis_title="Year",
        yaxis_title="Average rating",
        hovermode="x unified",
    )
    return fig


def division_year_snapshot_chart(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    rating_col: str,
    year: int,
    top_n_per_division: int = 15,
    divisions: list[str] | None = None,
) -> go.Figure:
    """Selected-year division ranking for bar-chart comparison."""
    plot_df = _division_strength_frame(
        ratings_history,
        fights,
        rating_col=rating_col,
        top_n_per_division=top_n_per_division,
        divisions=divisions,
        year_min=year,
        year_max=year,
    )
    if plot_df.empty:
        return _empty_figure("no division data for selected year", title=f"{year} division strength")
    plot_df = plot_df.sort_values("score", ascending=True)
    fig = go.Figure(go.Bar(
        x=plot_df["score"],
        y=plot_df["division"],
        orientation="h",
        marker_color=STREAM_PALETTE["full_context"],
        text=plot_df["score"].map(lambda v: f"{v:.0f}"),
        textposition="outside",
        customdata=plot_df["fighters"].astype(int),
        hovertemplate="<b>%{y}</b><br>score=%{x:.1f}<br>fighters=%{customdata}<extra></extra>",
    ))
    _apply_chart_layout(fig, height=max(420, 34 * len(plot_df)))
    fig.update_layout(
        title=f"{year} division strength — top {top_n_per_division}",
        xaxis_title=_metric_label(rating_col),
        yaxis_title="",
        showlegend=False,
    )
    return fig


def calibration_plot(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    n_bins: int = 10,
) -> go.Figure:
    """For each completed fight, find the predicted win probability (using
    each fighter's μ_canonical at the previous rating event) and bin against
    actual outcomes.
    """
    fights = fights[~fights["is_excluded"]].copy()
    fights = fights[~fights["is_draw"]].copy()
    fights["event_date"] = pd.to_datetime(fights["event_date"])
    fights = fights.dropna(subset=["winner"])

    # For each fighter, build a sorted history list
    rh = ratings_history.copy()
    rh["event_date"] = pd.to_datetime(rh["event_date"])
    rh = rh.sort_values(["fighter", "event_date"])

    # Build per-fighter lookup: get rating just BEFORE a given event_date
    by_fighter: dict[str, pd.DataFrame] = {f: g for f, g in rh.groupby("fighter")}

    def rating_before(fighter: str, evt: pd.Timestamp) -> tuple[float, float, int] | None:
        g = by_fighter.get(fighter)
        if g is None:
            return None
        prior = g[g["event_date"] < evt]
        if prior.empty:
            return (1500.0, 350.0, 0)  # Glicko-2 prior
        last = prior.iloc[-1]
        return (float(last["mu_canonical"]), float(last["phi_canonical"]), len(prior))

    preds = []
    for _, row in fights.iterrows():
        a, b = row["fighter_a"], row["fighter_b"]
        evt = row["event_date"]
        ra = rating_before(a, evt)
        rb = rating_before(b, evt)
        if ra is None or rb is None:
            continue
        if ra[2] < 3 or rb[2] < 3 or ra[1] >= 350 or rb[1] >= 350:
            continue
        p_a = predict_win_prob_from_ratings(ra[0], ra[1], rb[0], rb[1])
        actual_a = 1 if row["winner"] == a else 0
        preds.append({"p_a": p_a, "actual": actual_a})

    df = pd.DataFrame(preds)
    if df.empty:
        return _empty_figure("no rated bouts", title="Prediction calibration")

    # Bin
    bins = np.linspace(0, 1, n_bins + 1)
    df["bin"] = pd.cut(df["p_a"], bins=bins, include_lowest=True, labels=False)
    grouped = df.groupby("bin").agg(
        predicted_mid=("p_a", "mean"),
        empirical=("actual", "mean"),
        n=("actual", "size"),
    ).reset_index().dropna()

    # Compute Brier score (per-bout MSE) for the title
    brier = ((df["p_a"] - df["actual"]) ** 2).mean()

    fig = go.Figure()
    # diagonal "perfect calibration" line
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1],
        mode="lines", line=dict(dash="dash", color="grey"),
        name="perfectly accurate", showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=grouped["predicted_mid"], y=grouped["empirical"],
        mode="markers+lines",
        marker=dict(size=grouped["n"].clip(lower=8, upper=30), color="#1f77b4"),
        name="actual results",
        text=[f"{int(n)} bouts" for n in grouped["n"]],
        hovertemplate="Model said %{x:.0%}<br>Actually won %{y:.0%}<br>%{text}<extra></extra>",
    ))
    _apply_chart_layout(fig, height=520)
    fig.update_layout(
        title=f"How accurate are the win predictions? Error score {brier:.3f} (lower is better) · {len(df):,} bouts",
        xaxis_title="Model's predicted win chance",
        yaxis_title="How often they actually won",
        xaxis=dict(range=[0, 1], tickformat=".0%"),
        yaxis=dict(range=[0, 1], tickformat=".0%"),
    )
    return fig


def external_source_coverage_dashboard(data: dict[str, pd.DataFrame]) -> go.Figure:
    summary = source_coverage_summary(data)
    display_summary = summary.copy()
    display_summary["date_range"] = display_summary.apply(
        lambda r: "" if pd.isna(r.get("min_date")) else f"{r.get('min_date')} to {r.get('max_date')}",
        axis=1,
    )
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "bar"}, {"type": "table"}]],
        column_widths=[0.42, 0.58],
        horizontal_spacing=0.04,
    )
    fig.add_trace(
        go.Bar(
            x=display_summary["rows"],
            y=display_summary["table"],
            orientation="h",
            marker_color=STREAM_PALETTE["canonical"],
            hovertemplate="%{y}<br>rows=%{x:,}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Table(
            header=dict(values=["Table", "Rows", "Cols", "Fighters", "Date range"]),
            cells=dict(values=[
                display_summary["table"],
                display_summary["rows"].map(lambda v: f"{int(v):,}"),
                display_summary["columns"].map(lambda v: f"{int(v):,}"),
                display_summary["unique_fighters"].map(lambda v: "" if pd.isna(v) else f"{int(v):,}"),
                display_summary["date_range"],
            ]),
        ),
        row=1,
        col=2,
    )
    _apply_chart_layout(fig, height=600)
    fig.update_layout(title="Source coverage: rows, fighters, and dates", showlegend=False)
    fig.update_xaxes(title_text="Rows", row=1, col=1)
    return fig


def period_leaderboard_chart(
    ratings_current: pd.DataFrame,
    n: int = 25,
    min_fights: int = SUSTAINED_PEAK_MIN_FIGHTS,
) -> go.Figure:
    df = ratings_current.copy()
    df["rating_periods"] = pd.to_numeric(df.get("rating_periods"), errors="coerce")
    # WHR (Whole-History Rating smoother) is the default headline surface — it
    # is comparable across eras at the rating layer. Fall back to the windowed
    # Glicko-2 streams only when the WHR columns are absent (older snapshots).
    peak_col = next(
        (
            col
            for col in ("symon_prime_score", "mu_whr")
            if col in df.columns
        ),
        "mu_whr",
    )
    df = df[df["rating_periods"] >= min_fights].dropna(subset=[peak_col])
    df = df.sort_values(peak_col, ascending=False).head(n)
    if df.empty:
        return _empty_figure("no sustained peak data", title="Sustained peak leaderboard")
    fig = go.Figure(go.Bar(
        x=df[peak_col],
        y=df["fighter"],
        orientation="h",
        marker_color=STREAM_PALETTE["method"] if "method_performance" in peak_col else STREAM_PALETTE["canonical"],
        customdata=np.stack([
            df["rating_periods"].astype("Int64").astype("string"),
        ], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            f"{SUSTAINED_PEAK_WINDOW_LABEL}=%{{x:.1f}}<br>"
            "fights rated=%{customdata[0]}<extra></extra>"
        ),
    ))
    _apply_chart_layout(fig, height=max(520, 24 * len(df)))
    fig.update_layout(
        title=f"Top {n} {SUSTAINED_PEAK_WINDOW_LABEL} ratings ({rating_label(peak_col)})",
        xaxis_title=rating_label(peak_col),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def rank_movement_chart(
    previous: pd.DataFrame,
    current: pd.DataFrame,
    *,
    rating_col: str,
    top_k: int = 50,
    n: int = 20,
    min_fights: int = 3,
) -> go.Figure:
    """Largest rank moves between two snapshots for one public rating view."""
    if previous is None or previous.empty or current is None or current.empty:
        return _empty_figure("previous snapshot unavailable", title="Movers")
    if rating_col not in previous.columns or rating_col not in current.columns:
        return _empty_figure("rating view unavailable in both snapshots", title="Movers")

    def _rank(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["rating_periods"] = pd.to_numeric(out.get("rating_periods"), errors="coerce").fillna(0)
        out = out[out["rating_periods"] >= min_fights].dropna(subset=[rating_col])
        out = out.sort_values(rating_col, ascending=False).head(top_k).reset_index(drop=True)
        out["rank"] = np.arange(1, len(out) + 1)
        return out[["fighter", "rank", rating_col]]

    old = _rank(previous)
    new = _rank(current)
    if old.empty or new.empty:
        return _empty_figure("no ranked fighters to compare", title="Movers")

    merged = old.merge(new, on="fighter", how="outer", suffixes=("_old", "_new"))
    outside = top_k + 1
    merged["rank_old_filled"] = merged["rank_old"].fillna(outside)
    merged["rank_new_filled"] = merged["rank_new"].fillna(outside)
    merged["move"] = merged["rank_old_filled"] - merged["rank_new_filled"]
    merged = merged[merged["move"].ne(0)].copy()
    if merged.empty:
        return _empty_figure("top group did not move", title="Movers")
    merged["abs_move"] = merged["move"].abs()
    merged["status"] = np.select(
        [merged["rank_old"].isna(), merged["rank_new"].isna(), merged["move"].gt(0)],
        ["Entered", "Left", "Up"],
        default="Down",
    )
    plot = merged.sort_values(["abs_move", "rank_new_filled"], ascending=[False, True]).head(n)
    plot = plot.sort_values("move")
    colors = np.where(plot["move"].ge(0), THEME["positive"], THEME["negative"])
    labels = [
        f"{fighter} ({status})" if status in {"Entered", "Left"} else fighter
        for fighter, status in zip(plot["fighter"], plot["status"])
    ]
    fig = go.Figure(go.Bar(
        x=plot["move"],
        y=labels,
        orientation="h",
        marker_color=colors,
        text=plot["move"].map(lambda v: f"{v:+.0f}"),
        textposition="outside",
        customdata=np.stack([
            plot["rank_old"].fillna(0).astype(int).astype(str),
            plot["rank_new"].fillna(0).astype(int).astype(str),
            pd.to_numeric(plot.get(f"{rating_col}_new"), errors="coerce").round(1).astype("string"),
        ], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "move=%{x:+.0f}<br>"
            "old rank=%{customdata[0]}<br>"
            "new rank=%{customdata[1]}<br>"
            "new score=%{customdata[2]}<extra></extra>"
        ),
    ))
    fig.add_vline(x=0, line_color=THEME["border_strong"], line_width=1)
    _apply_chart_layout(fig, height=max(430, 26 * len(plot)))
    fig.update_layout(
        title=f"Top-{top_k} movers — {_metric_label(rating_col)}",
        xaxis_title="Rank move",
        yaxis_title="",
        showlegend=False,
    )
    return fig


def datalab_scorecard_insight_chart(scorecards: pd.DataFrame) -> go.Figure:
    decisions = datalab_scorecard_decision_summary(scorecards)
    if decisions.empty:
        return _empty_figure("no usable DataLab scorecard totals", title="Scorecard insight")
    counts = decisions["decision_type"].value_counts().reindex(
        ["unanimous", "split", "majority", "draw/other"],
        fill_value=0,
    )
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "bar"}, {"type": "histogram"}]],
        subplot_titles=("Decision types", "Judge-score total margin"),
    )
    fig.add_trace(
        go.Bar(x=counts.index, y=counts.values,
               marker_color=[THEME["primary"], THEME["negative"], THEME["accent"], THEME["neutral"]]),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Histogram(x=decisions["abs_total_margin"], nbinsx=20, marker_color=THEME["positive"]),
        row=1,
        col=2,
    )
    _apply_chart_layout(fig, height=480)
    fig.update_layout(title="Judge scorecard texture", showlegend=False)
    fig.update_yaxes(title_text="Fights", row=1, col=1)
    fig.update_xaxes(title_text="Decision type", row=1, col=1)
    fig.update_xaxes(title_text="Absolute total margin across judges", row=1, col=2)
    return fig


def public_rating_stream(view: str) -> str:
    """Compatibility helper: every new public view uses the base WHR stream."""
    _normalize_public_view(view)
    return "whr"


def select_public_rating_column(
    ratings_current: pd.DataFrame,
    view: str,
    time_view: str | None = None,
) -> str | None:
    """Compatibility wrapper for the retired lens×form public API."""
    return select_public_ranking_column(
        ratings_current, _normalize_public_view(view, time_view))


def select_modular_rating_column(
    ratings_current: pd.DataFrame,
    scoring_method: str,
    *,
    use_performance: bool = False,
    peak: str = "current",
) -> str | None:
    """Column lookup for the modular scoring-method x sleeve composer."""
    stream = compose_rating_stream(scoring_method, use_performance=use_performance)
    return select_rating_column(ratings_current, stream, peak)


def sleeve_ranking_table(
    ratings_current: pd.DataFrame,
    rating_col: str,
    n: int = 25,
    min_fights: int = 3,
    division: str | None = None,
    active_within_days: int | None = None,
    fights: pd.DataFrame | None = None,
    query: str = "",
    baseline_col: str = "mu_canonical",
) -> pd.DataFrame:
    """Build the compact table rendered by the notebook sleeve composer."""
    df = ratings_current.dropna(subset=[rating_col]).copy()
    df["rating_periods"] = pd.to_numeric(df.get("rating_periods"), errors="coerce")
    df = df[df["rating_periods"].fillna(0) >= min_fights]
    if fights is not None and active_within_days is not None and "last_event_date" in df.columns:
        cutoff = pd.Timestamp(fights["event_date"].max()) - pd.Timedelta(days=active_within_days)
        df = df[pd.to_datetime(df["last_event_date"], errors="coerce") >= cutoff]
    if division is not None:
        # Bucket by career division: where the bulk of the UFC career happened.
        # A long-tenured Lightweight who just won the Welterweight belt still
        # surfaces under Lightweight in the divisional leaderboard, because that
        # is the class the resume was built in. Fall back to most-recent
        # division only when career isn't known.
        if "career_division" in df.columns:
            home = df["career_division"]
        else:
            home = pd.Series(pd.NA, index=df.index)
        if fights is not None:
            recent_div = recent_division_by_fighter(fights).rename(
                columns={"division": "_recent_division"}
            )
            df = df.merge(recent_div, on="fighter", how="left")
            home = home.fillna(df["_recent_division"])
        df["division"] = home
        df = df[df["division"] == division]
    df = df.sort_values(rating_col, ascending=False).head(n).reset_index(drop=True)
    out = pd.DataFrame({
        "rank": range(1, len(df) + 1),
        "fighter": df["fighter"],
        "current_rating": pd.to_numeric(df[rating_col], errors="coerce").round(1),
        "baseline_rating": pd.to_numeric(df[baseline_col], errors="coerce").round(1),
        "delta_vs_baseline": (
            pd.to_numeric(df[rating_col], errors="coerce") - pd.to_numeric(df[baseline_col], errors="coerce")
        ).round(1),
        "last_event_date": pd.to_datetime(df.get("last_event_date"), errors="coerce").dt.date,
    })
    if query:
        key = normalize_name_key(query)
        out["query_match"] = out["fighter"].apply(lambda name: key in normalize_name_key(name))
    return out


def ranking_context_impact_table(performance_appearances: pd.DataFrame, n: int = 25) -> pd.DataFrame:
    """Largest winner-side rank/championship/P4P context boosts."""
    cols = [
        "event_date", "fighter", "opponent", "division",
        "context_multiplier", "perf_factor_rank_context",
        "perf_factor_championship", "perf_factor_p4p",
        "opponent_prefight_division_rank", "opponent_prefight_p4p_rank",
        "opponent_entered_as_champion", "opponent_entered_as_interim_champion",
        "is_championship_bout", "is_interim_title_bout", "performance_weight",
    ]
    if performance_appearances is None or performance_appearances.empty:
        return pd.DataFrame(columns=cols)
    needed = {"is_winner", "perf_factor_rank_context", "perf_factor_championship", "perf_factor_p4p"}
    if not needed.issubset(performance_appearances.columns):
        return pd.DataFrame(columns=cols)
    df = performance_appearances[performance_appearances["is_winner"].fillna(False).astype(bool)].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)
    for col in ["perf_factor_rank_context", "perf_factor_championship", "perf_factor_p4p", "performance_weight"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df["context_multiplier"] = (
        df["perf_factor_rank_context"].fillna(1.0)
        * df["perf_factor_championship"].fillna(1.0)
        * df["perf_factor_p4p"].fillna(1.0)
    )
    df = df[df["context_multiplier"] > 1.0001]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce").dt.date
    out = df.sort_values("context_multiplier", ascending=False).head(n)
    out = out[[c for c in cols if c in out.columns]].copy()
    for col in ["context_multiplier", "perf_factor_rank_context", "perf_factor_championship", "perf_factor_p4p", "performance_weight"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(3)
    return out.reset_index(drop=True)


def weight_class_context_impact_table(performance_appearances: pd.DataFrame, n: int = 25) -> pd.DataFrame:
    """Largest weight-class movement effects in the performance sleeve."""
    cols = [
        "event_date", "fighter", "opponent", "division",
        "fighter_previous_division", "fighter_weight_class_move",
        "fighter_weight_class_change_fight", "activity_gap_days",
        "activity_layoff_level",
        "is_winner", "perf_factor_weight_class", "performance_weight",
    ]
    if performance_appearances is None or performance_appearances.empty:
        return pd.DataFrame(columns=cols)
    needed = {"fighter_weight_class_move", "perf_factor_weight_class", "performance_weight"}
    if not needed.issubset(performance_appearances.columns):
        return pd.DataFrame(columns=cols)
    df = performance_appearances.copy()
    df["perf_factor_weight_class"] = pd.to_numeric(df["perf_factor_weight_class"], errors="coerce")
    df = df[df["perf_factor_weight_class"].fillna(1.0).gt(1.0001)]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce").dt.date
    df["movement_effect"] = np.where(
        df["is_winner"].fillna(False).astype(bool),
        "upward win boost",
        "downward loss penalty",
    )
    cols_with_effect = cols[:6] + ["movement_effect"] + cols[6:]
    out = df.sort_values(["perf_factor_weight_class", "event_date"], ascending=[False, False]).head(n)
    out = out[[c for c in cols_with_effect if c in out.columns]].copy()
    for col in ["perf_factor_weight_class", "performance_weight"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(3)
    return out.reset_index(drop=True)


def sleeve_factor_summary_table(
    performance_appearances: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Counts and normalized percent ranges for every non-neutral factor."""
    frames = []
    if performance_appearances is not None and not performance_appearances.empty:
        frames.append(performance_factor_audit_table(
            performance_appearances,
            n=len(performance_appearances) * max(1, len(PERFORMANCE_FACTOR_LABELS)),
        ))
    if not frames:
        return pd.DataFrame(columns=[
            "sleeve", "factor", "effect", "appearances", "min_multiplier",
            "median_multiplier", "max_multiplier",
        ])
    audit = pd.concat(frames, ignore_index=True, sort=False)
    if audit.empty:
        return pd.DataFrame(columns=[
            "sleeve", "factor", "effect", "appearances", "min_multiplier",
            "median_multiplier", "max_multiplier",
        ])
    grouped = (
        audit.groupby(["sleeve", "factor", "effect"], as_index=False)
        .agg(
            appearances=("multiplier", "size"),
            min_multiplier=("multiplier", "min"),
            median_multiplier=("multiplier", "median"),
            max_multiplier=("multiplier", "max"),
        )
    )
    for col in ["min_multiplier", "median_multiplier", "max_multiplier"]:
        grouped[col] = pd.to_numeric(grouped[col], errors="coerce").round(3)
    grouped["group"] = grouped["sleeve"].map({
        "performance": "Performance context",
    }).fillna(grouped["sleeve"])
    grouped["direction"] = grouped["effect"].map({
        "boost": "Boost",
        "penalty": "Penalty",
        "neutral": "Neutral",
    }).fillna(grouped["effect"])
    for src, dst in [
        ("min_multiplier", "min_effect_pct"),
        ("median_multiplier", "median_effect_pct"),
        ("max_multiplier", "max_effect_pct"),
    ]:
        grouped[dst] = ((pd.to_numeric(grouped[src], errors="coerce") - 1.0) * 100).round(1)
    return grouped.sort_values(
        ["group", "direction", "appearances"],
        ascending=[True, True, False],
    ).reset_index(drop=True)


def sleeve_effects_by_fight_table(
    performance_appearances: pd.DataFrame | None = None,
    *,
    n: int = 25,
    fighter: str | None = None,
    effect: str = "all",
) -> pd.DataFrame:
    """Aggregate all non-neutral sleeve factors to one row per fighter-fight."""
    frames = []
    if performance_appearances is not None and not performance_appearances.empty:
        frames.append(performance_factor_audit_table(
            performance_appearances,
            n=len(performance_appearances) * max(1, len(PERFORMANCE_FACTOR_LABELS)),
            fighter=fighter,
            effect=effect,
        ))
    cols = [
        "event_date", "fighter", "opponent", "outcome", "direction",
        "combined_effect_pct", "factors", "sleeves", "division",
    ]
    if not frames:
        return pd.DataFrame(columns=cols)
    audit = pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True, sort=False)
    if audit.empty:
        return pd.DataFrame(columns=cols)
    audit["event_date"] = pd.to_datetime(audit.get("event_date"), errors="coerce").dt.date
    audit["multiplier"] = pd.to_numeric(audit["multiplier"], errors="coerce").fillna(1.0)
    keys = [c for c in ["event_date", "event_name", "fighter", "opponent", "outcome", "division"] if c in audit.columns]
    grouped = (
        audit.groupby(keys, dropna=False)
        .agg(
            combined_multiplier=("multiplier", "prod"),
            factors=("factor", lambda s: ", ".join(pd.Series(s).dropna().astype(str).drop_duplicates())),
            sleeves=("sleeve", lambda s: " + ".join(pd.Series(s).dropna().astype(str).drop_duplicates())),
        )
        .reset_index()
    )
    grouped["combined_effect_pct"] = ((grouped["combined_multiplier"] - 1.0) * 100).round(1)
    grouped["direction"] = np.select(
        [grouped["combined_effect_pct"].gt(0), grouped["combined_effect_pct"].lt(0)],
        ["Boost", "Penalty"],
        default="Neutral",
    )
    grouped = grouped[grouped["combined_effect_pct"].abs() > 0.01]
    if grouped.empty:
        return pd.DataFrame(columns=cols)
    grouped = grouped.sort_values("combined_effect_pct", key=lambda s: s.abs(), ascending=False).head(n)
    return grouped[[c for c in cols if c in grouped.columns]].reset_index(drop=True)


def calibration_residuals_chart(
    calibration_residuals: pd.DataFrame,
    *,
    segment_type: str = "division",
    min_n: int = 40,
) -> go.Figure:
    """Predicted win probability vs empirical outcomes by segment."""
    # Not called by build_notebook.py. Kept because rate_snapshot still writes
    # calibration_residuals.parquet and build_database still exports it: the
    # artifact is live and this is its reader, available from a notebook cell.
    if calibration_residuals is None or calibration_residuals.empty:
        return _empty_figure("calibration residuals unavailable", title="Calibration by segment")
    df = calibration_residuals[calibration_residuals["segment_type"].eq(segment_type)].copy()
    df["n"] = pd.to_numeric(df.get("n"), errors="coerce").fillna(0)
    df = df[df["n"] >= min_n]
    if df.empty:
        return _empty_figure("no calibration segment has enough bouts", title="Calibration by segment")
    df["abs_residual"] = pd.to_numeric(df["residual"], errors="coerce").abs()
    top_segments = (
        df.groupby("segment_value")["abs_residual"].mean()
        .sort_values(ascending=False)
        .head(8)
        .index
    )
    df = df[df["segment_value"].isin(top_segments)].sort_values(["segment_value", "prob_bin"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1],
        mode="lines",
        line=dict(color="#94a3b8", dash="dash"),
        name="perfectly accurate",
    ))
    for segment, g in df.groupby("segment_value", sort=False):
        fig.add_trace(go.Scatter(
            x=g["predicted_mean"],
            y=g["empirical_win_rate"],
            mode="markers+lines",
            name=str(segment),
            marker=dict(size=np.sqrt(g["n"]).clip(6, 22)),
            customdata=np.stack([
                (g["residual"] * 100).round(1).astype("string"),
                g["n"].astype(int).astype("string"),
            ], axis=-1),
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Model said %{x:.0%}<br>"
                "Actually won %{y:.0%}<br>"
                "off by %{customdata[0]} pts<br>"
                "%{customdata[1]} bouts<extra></extra>"
            ),
        ))
    _apply_chart_layout(fig, height=560)
    fig.update_layout(
        title=f"Prediction accuracy by {segment_type}",
        xaxis_title="Model's predicted win chance",
        yaxis_title="How often they actually won",
        xaxis=dict(range=[0, 1], tickformat=".0%"),
        yaxis=dict(range=[0, 1], tickformat=".0%"),
        legend=dict(orientation="h", y=1.15, x=0),
    )
    return fig


def snapshot_movers_chart(
    ratings_current: pd.DataFrame,
    previous_ratings_current: pd.DataFrame | None,
    *,
    rating_col: str = "mu_canonical",
    n: int = 12,
) -> go.Figure:
    """Biggest rating risers/fallers since the previous snapshot.

    Diverging horizontal bars on the rating column the Control Room selects;
    the natural landing chart after a data refresh.
    """
    title = "Movers since last snapshot"
    if (previous_ratings_current is None or previous_ratings_current.empty
            or ratings_current is None or ratings_current.empty):
        return _empty_figure("no previous snapshot to compare", title=title)
    col = rating_col if rating_col in ratings_current.columns else "mu_canonical"
    if col not in previous_ratings_current.columns:
        return _empty_figure("rating column missing in previous snapshot", title=title)
    cur = ratings_current[["fighter", col]].rename(columns={col: "now"})
    prev = previous_ratings_current[["fighter", col]].rename(columns={col: "before"})
    m = cur.merge(prev, on="fighter", how="inner").dropna(subset=["now", "before"])
    m["delta"] = pd.to_numeric(m["now"], errors="coerce") - pd.to_numeric(m["before"], errors="coerce")
    m = m[m["delta"].abs() > 0.05]
    if m.empty:
        return _empty_figure("no fighters moved since the last snapshot", title=title)
    movers = pd.concat([
        m.sort_values("delta", ascending=False).head(n),
        m.sort_values("delta", ascending=True).head(n),
    ]).drop_duplicates("fighter").sort_values("delta")
    colors = np.where(movers["delta"] >= 0, SIGN_COLORS["positive"], SIGN_COLORS["negative"])
    fig = go.Figure(go.Bar(
        x=movers["delta"], y=movers["fighter"], orientation="h",
        marker_color=colors,
        text=movers["delta"].round(1).map(lambda v: f"{v:+.1f}"), textposition="outside",
        customdata=np.stack([
            pd.to_numeric(movers["before"], errors="coerce").round(1).astype("string"),
            pd.to_numeric(movers["now"], errors="coerce").round(1).astype("string"),
        ], axis=-1),
        hovertemplate="<b>%{y}</b><br>%{customdata[0]} → %{customdata[1]} (%{x:+.1f})<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=THEME["border_strong"], line_width=1)
    _apply_chart_layout(fig, height=max(440, 24 * len(movers)))
    fig.update_layout(title=title, xaxis_title="Rating change vs previous snapshot", yaxis_title="",
                      showlegend=False)
    return fig


def inactivity_table(ratings_current: pd.DataFrame, *, n: int = 20, min_rating: float = 1650.0,
                     min_months: float = 12.0, max_months: float = 96.0) -> pd.DataFrame:
    """Highly-rated fighters fading on the clock — the ring-rust ledger.

    Bounded to a recent window (`max_months`, default 8 years) so it surfaces
    meaningful recent layoffs rather than fighters who retired decades ago.
    """
    cols = ["fighter", "months_inactive", "mu_canonical", "activity_mu_penalty",
            "mu_canonical_activity_adjusted", "last_event_date"]
    if ratings_current is None or ratings_current.empty:
        return pd.DataFrame(columns=cols)
    if "months_inactive" not in ratings_current.columns:
        return pd.DataFrame(columns=cols)
    df = ratings_current.copy()
    df["months_inactive"] = pd.to_numeric(df["months_inactive"], errors="coerce")
    df["mu_canonical"] = pd.to_numeric(df["mu_canonical"], errors="coerce")
    df = df[(df["months_inactive"] >= min_months) & (df["months_inactive"] <= max_months)
            & (df["mu_canonical"] >= min_rating)]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df.sort_values("months_inactive", ascending=False).head(n)
    out = df[[c for c in cols if c in df.columns]].copy()
    if "last_event_date" in out.columns:
        out["last_event_date"] = pd.to_datetime(out["last_event_date"], errors="coerce").dt.date
    for c in ("months_inactive", "mu_canonical", "activity_mu_penalty", "mu_canonical_activity_adjusted"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(1)
    return out.reset_index(drop=True)
