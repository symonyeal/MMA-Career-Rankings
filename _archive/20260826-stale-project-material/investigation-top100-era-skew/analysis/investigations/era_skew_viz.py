"""Charts for the top-100 era-skew investigation.

Convention, inherited from ``analysis/viz.py``: every figure paints its own
opaque canvas from ``viz.THEME`` rather than inheriting the notebook host's.
That is what makes these readable in a light *and* a dark notebook — the figure
is a self-contained card either way, instead of light ink on whatever the host
happens to be.

Second rule, which ``viz.py`` predates: **no meaning in colour alone.** Every
series that means something different also carries a different dash pattern or
marker symbol and, wherever there is room, its own text label. A reader who
cannot separate the hues loses nothing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analysis.viz import CHART_COLORWAY, THEME, _apply_chart_layout

# Distinct dash patterns and marker symbols, in the order series are added, so a
# reader can tell two lines apart with the colour removed.
DASHES = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot", "5px,2px,1px,2px"]
SYMBOLS = ["circle", "square", "diamond", "triangle-up", "x", "cross", "star",
           "triangle-down", "pentagon", "hexagon"]


def _finish(fig: go.Figure, *, title: str, height: int = 460,
            xtitle: str = "", ytitle: str = "") -> go.Figure:
    fig.update_layout(title=title, xaxis_title=xtitle, yaxis_title=ytitle,
                      hovermode="closest")
    return _apply_chart_layout(fig, height=height)


def _zero_line(fig: go.Figure, *, y: float = 0.0, label: str = "", row=None, col=None) -> None:
    kwargs = dict(y=y, line=dict(color=THEME["text_muted"], width=1.5, dash="solid"),
                  annotation_text=label, annotation_position="top left",
                  annotation_font=dict(color=THEME["text_muted"], size=11))
    if row is not None:
        fig.add_hline(row=row, col=col, **kwargs)
    else:
        fig.add_hline(**kwargs)


def board_shape_chart(board: pd.DataFrame, *, top_n: int = 100) -> go.Figure:
    """Rank against debut year for the top N, split by whether they are done.

    The claim under test is visual: if the board ranked careers rather than
    current form, the points would not bunch on the right-hand side.
    """
    top = board.head(top_n).copy()
    top["still_active"] = top["last_year"] >= 2024
    fig = go.Figure()
    for active, name, symbol, colour in (
        (True, "still active (2024+)", "circle", CHART_COLORWAY[0]),
        (False, "career finished", "x", CHART_COLORWAY[1]),
    ):
        sub = top[top["still_active"] == active]
        fig.add_trace(go.Scatter(
            x=sub["first_year"], y=sub["rank"], mode="markers",
            name=f"{name} — {len(sub)}",
            marker=dict(symbol=symbol, size=10, color=colour,
                        line=dict(width=1, color=THEME["bg"])),
            text=sub["fighter"],
            hovertemplate="%{text}<br>rank %{y} · debut %{x}<extra></extra>",
        ))
    median = float(top["first_year"].median())
    fig.add_vline(x=median, line=dict(color=THEME["accent"], width=1.5, dash="dash"),
                  annotation_text=f"median debut {median:.0f}",
                  annotation_font=dict(color=THEME["accent"], size=11))
    fig.update_yaxes(autorange="reversed")
    return _finish(fig, title=f"Top {top_n} career skill mass — rank against debut year",
                   xtitle="First rated year", ytitle="Career-mass rank")


def field_shape_chart(bar_table: pd.DataFrame, annual: pd.DataFrame) -> go.Figure:
    """The bar, the middle of the field, and the top of it, year by year.

    The bar moves 72 points in 24 years. If the top of the field moved by the
    same amount there would be nothing to explain, so it is drawn beside it.
    """
    per_year = annual.groupby("year")["annual_mean"]
    frame = bar_table.set_index("year")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32],
                        vertical_spacing=0.07)
    series = [
        ("99th percentile", per_year.quantile(0.99), DASHES[1], SYMBOLS[2], CHART_COLORWAY[1]),
        ("the bar — 90th percentile", frame["q0.90"], DASHES[0], SYMBOLS[0], CHART_COLORWAY[0]),
        ("median", per_year.median(), DASHES[2], SYMBOLS[1], CHART_COLORWAY[2]),
    ]
    for name, values, dash, symbol, colour in series:
        fig.add_trace(go.Scatter(
            x=values.index, y=values.to_numpy(), mode="lines+markers", name=name,
            line=dict(color=colour, width=2.4, dash=dash),
            marker=dict(symbol=symbol, size=6, color=colour),
        ), row=1, col=1)
        last_year = int(values.index.max())
        fig.add_annotation(x=last_year, y=float(values.loc[last_year]), text=f" {name}",
                           showarrow=False, xanchor="left", row=1, col=1,
                           font=dict(color=colour, size=11))
    fig.add_trace(go.Bar(
        x=frame.index, y=frame["rated_fighter_years"], name="rated fighter-years",
        marker=dict(color=THEME["border_strong"]), showlegend=False,
    ), row=2, col=1)
    fig.update_yaxes(title_text="WHR rating", row=1, col=1)
    fig.update_yaxes(title_text="rated", row=2, col=1)
    fig.update_xaxes(title_text="Year", row=2, col=1, range=[1999.4, 2029])
    fig.update_layout(showlegend=False)
    return _finish(fig, title="The bar is nearly flat; the top of the field is not",
                   height=540)


def case_gap_chart(annual: pd.DataFrame, bar_by_year: pd.Series, cases: list[str]) -> go.Figure:
    """Each carried career's annual rating minus its own year's bar.

    Above the line contributes to career mass; below it contributes exactly
    nothing, however far below. One panel answers "who clears, and by how much"
    for every case at once.
    """
    fig = go.Figure()
    for i, name in enumerate(cases):
        sub = annual[annual["fighter"] == name].sort_values("year")
        if sub.empty:
            continue
        gap = sub["annual_mean"].to_numpy() - sub["year"].map(bar_by_year).to_numpy()
        colour = CHART_COLORWAY[i % len(CHART_COLORWAY)]
        fig.add_trace(go.Scatter(
            x=sub["year"], y=gap, mode="lines+markers", name=name,
            line=dict(color=colour, width=2.2, dash=DASHES[i % len(DASHES)]),
            marker=dict(symbol=SYMBOLS[i % len(SYMBOLS)], size=7, color=colour),
            hovertemplate=f"{name}<br>%{{x}} · %{{y:.0f}} vs bar<extra></extra>",
        ))
        fig.add_annotation(x=int(sub["year"].max()), y=float(gap[-1]), text=f" {name}",
                           showarrow=False, xanchor="left", font=dict(color=colour, size=11))
    _zero_line(fig, label="the bar")
    fig.update_layout(showlegend=False)
    fig.update_xaxes(range=[1999.4, 2031])
    return _finish(fig, title="Rating minus the year's bar — above the line is the only part that scores",
                   xtitle="Year", ytitle="Annual rating − year bar", height=500)


def forest_chart(models: dict[str, pd.DataFrame], *, title: str,
                 drop_const: bool = True) -> go.Figure:
    """Coefficients with 95% intervals, one row per term, grouped by model."""
    fig = go.Figure()
    terms = []
    for m in models.values():
        for t in m["term"]:
            if drop_const and t == "const":
                continue
            if t not in terms:
                terms.append(t)
    for i, (label, frame) in enumerate(models.items()):
        f = frame[frame["term"].isin(terms)]
        colour = CHART_COLORWAY[i % len(CHART_COLORWAY)]
        offset = (i - (len(models) - 1) / 2) * 0.22
        y = [terms.index(t) + offset for t in f["term"]]
        fig.add_trace(go.Scatter(
            x=f["coef"], y=y, mode="markers", name=label,
            error_x=dict(type="data", array=1.96 * f["se"], color=colour, thickness=1.6),
            marker=dict(symbol=SYMBOLS[i % len(SYMBOLS)], size=11, color=colour),
            hovertemplate="%{customdata}<br>coef %{x:.2f}<extra></extra>",
            customdata=f["term"],
        ))
    fig.add_vline(x=0, line=dict(color=THEME["text_muted"], width=1.5))
    fig.update_yaxes(tickmode="array", tickvals=list(range(len(terms))), ticktext=terms)
    return _finish(fig, title=title, xtitle="Coefficient on peak rating (95% CI)",
                   height=80 + 74 * len(terms))


def w2_chart(shape: pd.DataFrame, loss: pd.DataFrame) -> go.Figure:
    """What a larger drift prior buys in movement, and what it costs in prediction."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("Within-career rating range (median, ≥10 bouts)",
                                        "Held-out log loss vs the production value"))
    fig.add_trace(go.Scatter(
        x=shape["w2_multiplier"], y=shape["median_range"], mode="lines+markers+text",
        line=dict(color=CHART_COLORWAY[0], width=2.4, dash=DASHES[0]),
        marker=dict(symbol=SYMBOLS[0], size=10, color=CHART_COLORWAY[0]),
        text=[f"{v:.0f}" for v in shape["median_range"]], textposition="top center",
        textfont=dict(color=THEME["text_2"], size=11), showlegend=False,
    ), row=1, col=1)
    delta = loss.copy()
    worse = delta["delta_vs_baseline"] > 0
    fig.add_trace(go.Scatter(
        x=delta["w2_multiplier"], y=delta["delta_vs_baseline"], mode="markers",
        error_y=dict(type="data", symmetric=False,
                     array=delta["delta_hi"] - delta["delta_vs_baseline"],
                     arrayminus=delta["delta_vs_baseline"] - delta["delta_lo"],
                     color=THEME["text_muted"], thickness=1.6),
        marker=dict(size=13, color=np.where(worse, CHART_COLORWAY[4], CHART_COLORWAY[2]),
                    symbol=np.where(worse, "triangle-up", "triangle-down"),
                    line=dict(width=1, color=THEME["bg"])),
        showlegend=False,
        hovertemplate="×%{x}<br>Δ log loss %{y:.4f}<extra></extra>",
    ), row=2, col=1)
    _zero_line(fig, label="production w²", row=2, col=1)
    fig.update_xaxes(type="log", title_text="w² as a multiple of WHR_W2_PER_DAY",
                     row=2, col=1, tickvals=sorted(shape["w2_multiplier"]),
                     ticktext=[f"×{v:g}" for v in sorted(shape["w2_multiplier"])])
    fig.update_yaxes(title_text="rating points", row=1, col=1)
    fig.update_yaxes(title_text="Δ log loss (up = worse)", row=2, col=1)
    return _finish(fig, title="The drift prior: movement bought, accuracy paid", height=620)


def truncation_chart(truncation: pd.DataFrame, cases: list[str]) -> go.Figure:
    """Peak revision against how badly the deleted suffix went.

    Peak deletion predicts a slope: the worse the tail, the more the peak is
    revised down. A smoother that simply used more evidence would not care what
    the extra evidence said.
    """
    t = truncation.dropna(subset=["revision", "post_cut_win_rate"]).copy()
    is_case = t["fighter"].isin(cases)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t.loc[~is_case, "post_cut_win_rate"], y=t.loc[~is_case, "revision"],
        mode="markers", name=f"other long careers — {int((~is_case).sum())}",
        marker=dict(symbol="circle-open", size=7, color=THEME["text_muted"],
                    line=dict(width=1.2)),
        text=t.loc[~is_case, "fighter"],
        hovertemplate="%{text}<br>post-cut win rate %{x:.2f}<br>revision %{y:.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=t.loc[is_case, "post_cut_win_rate"], y=t.loc[is_case, "revision"],
        mode="markers+text", name="carried cases",
        marker=dict(symbol="diamond", size=13, color=CHART_COLORWAY[1],
                    line=dict(width=1, color=THEME["bg"])),
        text=t.loc[is_case, "fighter"], textposition="top center",
        textfont=dict(color=CHART_COLORWAY[1], size=10),
        hovertemplate="%{text}<br>revision %{y:.0f}<extra></extra>",
    ))
    if len(t) > 2:
        slope, intercept = np.polyfit(t["post_cut_win_rate"], t["revision"], 1)
        xs = np.linspace(0, 1, 20)
        fig.add_trace(go.Scatter(
            x=xs, y=intercept + slope * xs, mode="lines",
            name=f"fit: {slope:+.0f} pts per unit win rate",
            line=dict(color=CHART_COLORWAY[3], width=2, dash="dash"),
        ))
    _zero_line(fig, label="no revision")
    return _finish(fig, title="How much of a peak a later decline deletes",
                   xtitle="Win rate over the deleted suffix",
                   ytitle="Full-fit rating − truncated peak", height=520)


def bar_variants_chart(bar_table: pd.DataFrame) -> go.Figure:
    """Every candidate bar, and the place inside the year that 0.9 actually is."""
    frame = bar_table.set_index("year")
    cols = [c for c in frame.columns
            if c not in {"rated_fighter_years", "q0.90 is place"}]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.66, 0.34],
                        vertical_spacing=0.08,
                        subplot_titles=("Candidate bars", "What place in the year the 0.90 bar is"))
    for i, col in enumerate(cols):
        colour = CHART_COLORWAY[i % len(CHART_COLORWAY)]
        values = frame[col]
        fig.add_trace(go.Scatter(
            x=values.index, y=values.to_numpy(), mode="lines+markers", name=col,
            line=dict(color=colour, width=2.2, dash=DASHES[i % len(DASHES)]),
            marker=dict(symbol=SYMBOLS[i % len(SYMBOLS)], size=6, color=colour),
            connectgaps=False,
        ), row=1, col=1)
        defined = values.dropna()
        if len(defined):
            fig.add_annotation(x=int(defined.index.max()), y=float(defined.iloc[-1]),
                               text=f" {col}", showarrow=False, xanchor="left",
                               row=1, col=1, font=dict(color=colour, size=11))
    fig.add_trace(go.Scatter(
        x=frame.index, y=frame["q0.90 is place"], mode="lines+markers",
        line=dict(color=THEME["accent"], width=2.4, dash="solid", shape="hv"),
        marker=dict(symbol="square", size=6, color=THEME["accent"]),
        showlegend=False,
        hovertemplate="%{x}: the bar is the %{y}th best fighter-year<extra></extra>",
    ), row=2, col=1)
    fig.update_yaxes(title_text="WHR rating", row=1, col=1)
    fig.update_yaxes(title_text="place", row=2, col=1)
    fig.update_xaxes(title_text="Year", row=2, col=1, range=[1999.4, 2032])
    fig.update_layout(showlegend=False)
    return _finish(fig, title="A fixed count cannot repair a growing population — it is undefined where it is needed",
                   height=620)


def rank_move_chart(before: pd.DataFrame, after: pd.DataFrame, names: list[str],
                    *, before_label: str, after_label: str, title: str) -> go.Figure:
    """Dumbbell of one board's rank against another's, for named fighters."""
    b = before.set_index("fighter")["rank"]
    a = after.set_index("fighter")["rank"]
    rows = [(n, int(b[n]), int(a[n])) for n in names if n in b.index and n in a.index]
    rows.sort(key=lambda r: r[2])
    fig = go.Figure()
    for i, (name, r0, r1) in enumerate(rows):
        fig.add_trace(go.Scatter(
            x=[r0, r1], y=[i, i], mode="lines",
            line=dict(color=THEME["border_strong"], width=2), showlegend=False,
            hoverinfo="skip",
        ))
    fig.add_trace(go.Scatter(
        x=[r[1] for r in rows], y=list(range(len(rows))), mode="markers",
        name=before_label,
        marker=dict(symbol="circle-open", size=13, color=CHART_COLORWAY[4],
                    line=dict(width=2.2)),
        hovertemplate="%{customdata}<br>" + before_label + " rank %{x}<extra></extra>",
        customdata=[r[0] for r in rows],
    ))
    fig.add_trace(go.Scatter(
        x=[r[2] for r in rows], y=list(range(len(rows))), mode="markers",
        name=after_label,
        marker=dict(symbol="diamond", size=13, color=CHART_COLORWAY[2],
                    line=dict(width=1, color=THEME["bg"])),
        hovertemplate="%{customdata}<br>" + after_label + " rank %{x}<extra></extra>",
        customdata=[r[0] for r in rows],
    ))
    fig.update_yaxes(tickmode="array", tickvals=list(range(len(rows))),
                     ticktext=[r[0] for r in rows])
    fig.update_xaxes(type="log", title_text="Career-mass rank (log scale, left is better)")
    return _finish(fig, title=title, height=110 + 42 * len(rows))


def attribution_chart(rows: pd.DataFrame, *, fighter: str) -> go.Figure:
    """One bar per counterfactual: what that change alone does to a mass of zero."""
    r = rows.sort_values("score")
    colours = [CHART_COLORWAY[2] if v > 0 else THEME["text_muted"] for v in r["score"]]
    fig = go.Figure(go.Bar(
        x=r["score"], y=r["counterfactual"], orientation="h",
        marker=dict(color=colours, line=dict(width=1, color=THEME["bg"])),
        text=[f"  mass {v:,.0f} · rank {int(k):,}" for v, k in zip(r["score"], r["rank"])],
        textposition="outside", textfont=dict(color=THEME["text_2"], size=11),
        hovertemplate="%{y}<br>mass %{x:,.0f}<extra></extra>",
    ))
    fig.update_xaxes(range=[0, max(1.0, float(r["score"].max()) * 1.55)])
    return _finish(fig, title=f"{fighter}: what each change alone is worth",
                   xtitle="Career skill mass (rating-point-years)", height=110 + 46 * len(r))
