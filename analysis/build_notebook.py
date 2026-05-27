"""Generate the lean diagnostic notebook.

The notebook is intentionally read-only: build-time artifacts in
``data/snapshots/<date>/`` carry the expensive calculations.
"""
from __future__ import annotations

import json
from pathlib import Path


def code(src: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": _split(src),
    }


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _split(src)}


def _split(src: str) -> list[str]:
    src = src.lstrip("\n")
    lines = src.splitlines(keepends=True)
    return lines if lines else [""]


# ---------------------------------------------------------------------------
# Shared notebook-runtime helpers, emitted once near the top of the notebook.

SHARED_HELPERS = """
# Shared styling helpers ----------------------------------------------------
# Visual identity (THEME tokens + the dark "ufc_dark" Plotly template) lives in
# analysis.viz so the notebook chrome and every chart share ONE source of
# truth. Importing viz (done in the cell above) already registers and defaults
# the Plotly template; here we just pull THEME in for the HTML/CSS chrome.

from analysis.viz import THEME


def _rank_chip(n):
    # Accent (amber) reserved for #1 only; #2/#3 use muted neutrals.
    if n == 1:
        bg, fg = THEME["accent"], "#1f1300"
    elif n == 2:
        bg, fg = "#475569", THEME["text"]
    elif n == 3:
        bg, fg = "#3f3650", THEME["text_2"]
    else:
        bg, fg = "#1e293b", THEME["text_muted"]
    return (
        f'<span style="display:inline-block;min-width:1.6em;padding:1px 7px;'
        f'border-radius:9px;background:{bg};color:{fg};'
        f'font-family:{THEME["font"]};'
        f'font-weight:600;text-align:center;font-size:0.85em">{n}</span>'
    )


_BASE_TABLE_STYLES = [
    {"selector": "", "props": f"font-family: {THEME['font']}; "
                              f"background-color: {THEME['bg']}; "
                              f"color: {THEME['text']}; "
                              f"border-collapse: collapse; width: 100%"},
    {"selector": "thead th", "props": f"background-color: {THEME['bg']}; "
                                       f"color: {THEME['text_muted']}; "
                                       f"text-align: left; padding: 8px 14px; "
                                       f"font-size: 0.74em; font-weight: 600; "
                                       f"text-transform: uppercase; letter-spacing: 0.08em; "
                                       f"border-bottom: 1px solid {THEME['border_strong']}"},
    {"selector": "tbody td", "props": f"padding: 7px 14px; font-size: 0.92em; "
                                       f"color: {THEME['text']}; "
                                       f"background-color: {THEME['surface']}; "
                                       f"border-bottom: 1px solid {THEME['border']}"},
    {"selector": "tbody tr:nth-child(odd) td", "props": f"background-color: {THEME['surface_alt']}"},
    {"selector": "tbody tr:hover td", "props": f"background-color: {THEME['hover']}"},
]


class _DrawGuard:
    \"\"\"Re-entrancy guard for widget callbacks.

    Some draw_* functions mutate other observed widget values (e.g. locking
    sleeves when scoring=canonical). Those mutations trigger more callbacks,
    which would otherwise stack duplicate output. Use as a context manager:

        with _draw_guard(\"top\") as ok:
            if not ok:
                return
            ...
    \"\"\"
    def __init__(self, name):
        self.name = name
    def __enter__(self):
        flag = f"_drawing_{self.name}"
        if globals().get(flag):
            return False
        globals()[flag] = True
        return True
    def __exit__(self, *exc):
        globals()[f"_drawing_{self.name}"] = False


def _draw_guard(name):
    return _DrawGuard(name)


def _debug_caption(text):
    return Markdown(
        f"<div style='color:{THEME[\"text_caption\"]};font-size:0.8em;"
        f"font-family:{THEME[\"font\"]};margin-top:-4px'>"
        f"<i>{text}</i></div>"
    )


def _clear_output(out, wait=True):
    # VS Code's notebook host is more reliable when the clear happens inside
    # the Output context. Calling out.clear_output(wait=True) can append
    # repeated callback renders instead of replacing them.
    with out:
        clear_output(wait=wait)


def _observe_once(widget, callback, names="value"):
    # Re-running a notebook cell can register the same callback again on a
    # live widget. Best-effort unobserve keeps each redraw to one render.
    try:
        widget.unobserve(callback, names=names)
    except (ValueError, TypeError):
        pass
    widget.observe(callback, names=names)


# Canvas-wide CSS so markdown cells, plain DataFrame outputs, headings, and
# code-output regions all sit on the dark canvas with consistent typography.
# Scoped to the rendered output area so we don't touch the host IDE chrome.
_THEME_CSS = f\"\"\"
<style>
  .jp-RenderedHTMLCommon, .jp-RenderedMarkdown,
  .jp-OutputArea-output, .cell-output-ipywidget-background,
  .vsc-output-ipy, .output_html, .output_area, .output_text {{
    background-color: {THEME['bg']} !important;
    color: {THEME['text']};
    font-family: {THEME['font']};
  }}
  .jp-RenderedHTMLCommon h1, .jp-RenderedMarkdown h1,
  .jp-RenderedHTMLCommon h2, .jp-RenderedMarkdown h2,
  .jp-RenderedHTMLCommon h3, .jp-RenderedMarkdown h3,
  .jp-RenderedHTMLCommon h4, .jp-RenderedMarkdown h4 {{
    color: {THEME['text']};
    font-family: {THEME['font']};
    font-weight: 600;
    letter-spacing: -0.01em;
    border: none;
  }}
  .jp-RenderedHTMLCommon h1, .jp-RenderedMarkdown h1 {{ font-size: 1.7em; margin-top: 1.4em; }}
  .jp-RenderedHTMLCommon h2, .jp-RenderedMarkdown h2 {{ font-size: 1.35em; margin-top: 1.2em; color: {THEME['text']}; }}
  .jp-RenderedHTMLCommon h3, .jp-RenderedMarkdown h3 {{ font-size: 1.12em; color: {THEME['text_2']}; }}
  .jp-RenderedHTMLCommon h4, .jp-RenderedMarkdown h4 {{ font-size: 0.95em; color: {THEME['text_muted']}; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }}
  .jp-RenderedHTMLCommon p, .jp-RenderedMarkdown p {{ color: {THEME['text_2']}; font-size: 0.95em; line-height: 1.55; }}
  .jp-RenderedHTMLCommon code, .jp-RenderedMarkdown code {{
    background-color: {THEME['surface']}; color: {THEME['primary']};
    padding: 1px 6px; border-radius: 4px; font-size: 0.88em;
  }}
  .jp-RenderedHTMLCommon hr, .jp-RenderedMarkdown hr {{
    border: none; border-top: 1px solid {THEME['border']}; margin: 1.4em 0;
  }}
  .widget-label, .widget-readout {{ color: {THEME['text_2']} !important; font-family: {THEME['font']} !important; }}
  .widget-dropdown > select, .widget-text input, .widget-int-text input {{
    background-color: {THEME['surface']} !important; color: {THEME['text']} !important;
    border: 1px solid {THEME['border_strong']} !important;
  }}
  .widget-slider .noUi-connect {{ background: {THEME['primary']} !important; }}
  .widget-checkbox label, .widget-toggle-buttons label {{ color: {THEME['text_2']} !important; }}
</style>
\"\"\"
display(Markdown(_THEME_CSS))
"""


CELLS = [
    md("""
# Symon UFC Rank Engine

A read-only diagnostic view of the latest ratings snapshot. Each section
answers one question; controls live right above the output they drive.
"""),
    code(r"""
import re
import sys
from pathlib import Path

import pandas as pd
from IPython.display import clear_output, display, Markdown
import ipywidgets as widgets

pd.set_option("display.max_rows", 120)
pd.set_option("display.max_colwidth", 200)


def find_project_root(start: Path) -> Path:
    p = start.resolve()
    for _ in range(8):
        if (p / "data" / "snapshots").exists():
            return p
        p = p.parent
    raise RuntimeError("cannot locate project root")


PROJECT_ROOT = find_project_root(Path.cwd())
sys.path.insert(0, str(PROJECT_ROOT))

from analysis.viz import (
    DIVISIONS,
    PEAK_VIEWS,
    SCORING_METHODS,
    calibration_residuals_chart,
    division_entropy_chart,
    era_heatmap_chart,
    favorite_underdog_performance_table,
    fighter_odds_history_chart,
    fighter_profile_chart,
    fighter_detail,
    fighter_search,
    glicko_fightmatrix_scatter,
    h2h_prediction,
    integrity_factor_audit_table,
    load_project_data,
    modular_rating_context,
    performance_factor_audit_table,
    rank_delta_table,
    recent_division_by_fighter,
    select_modular_rating_column,
    sleeve_attribution_table,
    sleeve_attribution_waterfall,
    sleeve_effects_by_fight_table,
    sleeve_factor_summary_table,
    streak_timeline_chart,
    top100_division_density_chart,
    top_fighter_placement_scatter,
    trajectory_chart,
    weight_class_strength_chart,
    win_streaks,
    win_streaks_table,
)

SNAPSHOT_BASE = PROJECT_ROOT / "data" / "snapshots"
SNAPSHOT_CANDIDATES = [
    p for p in SNAPSHOT_BASE.iterdir()
    if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)
]
SNAPSHOT_DIR = sorted(SNAPSHOT_CANDIDATES, key=lambda p: p.name)[-1]
DATABASE_PATH = PROJECT_ROOT / "data" / "ufc_rank_engine.sqlite"
SNAP = load_project_data(SNAPSHOT_DIR, DATABASE_PATH, prefer_database=False)

fights = SNAP["fights"]
fighters = SNAP["fighters"]
rc = SNAP["ratings_current"]
calibration_residuals = SNAP.get("calibration_residuals", pd.DataFrame())
sleeve_attribution = SNAP.get("sleeve_attribution", pd.DataFrame())
division_entropy = SNAP.get("division_entropy", pd.DataFrame())
division_resume = SNAP.get("division_resume", pd.DataFrame())
performance_appearances = SNAP.get("performance_appearances", pd.DataFrame())
integrity_appearances = SNAP.get("integrity_appearances", pd.DataFrame())
fightmatrix_rankings = SNAP.get("fightmatrix_rankings", pd.DataFrame())
odds_lines = SNAP.get("odds_lines", pd.DataFrame())
ratings_history = SNAP.get("ratings_history", pd.DataFrame())
fighter_dominance = SNAP.get("fighter_dominance", pd.DataFrame())
ped_confirmed_bouts = SNAP.get("ped_confirmed_bouts", pd.DataFrame())

_whr_path = SNAPSHOT_DIR / "ratings_history_whr.parquet"
ratings_history_whr = pd.read_parquet(_whr_path) if _whr_path.exists() else pd.DataFrame()

display(Markdown(
    f"<div style='color:#cbd5e1;font-size:0.95em;"
    f"font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",system-ui,sans-serif'>"
    f"<b style='color:#f1f5f9'>Snapshot:</b> <code>{SNAPSHOT_DIR.name}</code> &middot; "
    f"<b style='color:#f1f5f9'>{len(fights):,}</b> fights &middot; "
    f"<b style='color:#f1f5f9'>{len(rc):,}</b> rated fighters"
    f"</div>"
))
"""),
    code(SHARED_HELPERS),
    md("""
## Top 30 Leaderboard

The headline ranking. **Scoring** picks how ratings are computed (plain Glicko-2
versus method-bonus, which rewards finishes over decisions). The two sleeve
toggles add adjustments on top: the **integrity sleeve** dampens
PED-confirmed wins, DQ wins, and missed-weight wins; the **performance sleeve**
adds quality-of-opponent, market-upset, and rank-context bonuses. **Window**
picks current rating vs a peak from a specific career window. Use
**Spotlight overlay** to compare multiple career curves below the table.
"""),
    code("""
scoring = widgets.Dropdown(
    options=list(SCORING_METHODS),
    value="method",
    description="Scoring:",
    layout=widgets.Layout(width="320px"),
)
peak = widgets.Dropdown(
    options=list(PEAK_VIEWS),
    value="sustained_peak",
    description="Window:",
    layout=widgets.Layout(width="320px"),
)
integrity = widgets.Checkbox(value=True, description="Integrity sleeve (PED/DQ/missed-weight)")
performance = widgets.Checkbox(value=True, description="Performance sleeve (quality/market/rank)")
gender = widgets.ToggleButtons(
    options=[("Both", "both"), ("Men", "M"), ("Women", "F")],
    value="both",
    description="Gender:",
)
division_filter = widgets.Dropdown(
    options=["All divisions"] + list(DIVISIONS),
    value="All divisions",
    description="Division:",
    layout=widgets.Layout(width="320px"),
)
n_men = widgets.IntSlider(value=30, min=5, max=100, step=5, description="Top N (M):")
n_women = widgets.IntSlider(value=15, min=5, max=100, step=5, description="Top N (F):")
min_fights = widgets.IntSlider(value=0, min=0, max=20, step=1, description="Min fights:")
_top_names = sorted(rc["fighter"].dropna().unique().tolist())
_default_spotlight = tuple([n for n in ["Georges St-Pierre", "Jon Jones", "Khabib Nurmagomedov"] if n in _top_names])
spotlight = widgets.SelectMultiple(
    options=_top_names,
    value=_default_spotlight,
    description="Spotlight:",
    rows=8,
    layout=widgets.Layout(width="420px"),
    style={"description_width": "80px"},
)

out_top = widgets.Output()
out_spot = widgets.Output()


def _build_top_view(df_subset, rating_col, n, min_fights_val, division_val="All divisions"):
    df = df_subset.copy()
    df["rating_periods"] = pd.to_numeric(df.get("rating_periods"), errors="coerce").fillna(0)
    df = df[df["rating_periods"] >= min_fights_val]
    if division_val and division_val != "All divisions":
        div_series = df.get("recent_division")
        if div_series is None:
            div_series = pd.Series(index=df.index, dtype=object)
        div_series = div_series.fillna(df.get("primary_division", ""))
        df = df[div_series.eq(division_val)]
    df = df.dropna(subset=[rating_col])
    df = df.sort_values(rating_col, ascending=False).head(n).reset_index(drop=True)
    if df.empty:
        return df
    rating_vals = pd.to_numeric(df[rating_col], errors="coerce")
    baseline_vals = pd.to_numeric(df.get("mu_canonical"), errors="coerce")
    return pd.DataFrame({
        "#": [_rank_chip(i) for i in range(1, len(df) + 1)],
        "Fighter": df["fighter"],
        "Rating": rating_vals.round(1),
        "vs plain Glicko": (rating_vals - baseline_vals).round(1),
        "Division": df.get("recent_division").fillna(df.get("primary_division", "")),
        "Last fight": pd.to_datetime(df["last_event_date"], errors="coerce").dt.date,
        "Fights": df["rating_periods"].astype(int),
    })


def _style_top(lean):
    if lean.empty:
        return lean
    rmin, rmax = lean["Rating"].min(), lean["Rating"].max()
    def delta_color(v):
        if pd.isna(v):
            return ""
        if v > 0:
            return f"color: {THEME['positive']}; font-weight: 600"
        if v < 0:
            return f"color: {THEME['negative']}; font-weight: 600"
        return f"color: {THEME['text_muted']}"
    return (
        lean.style
        .hide(axis="index")
        .bar(subset=["Rating"], color="rgba(56,189,248,0.28)", vmin=rmin, vmax=rmax)
        .map(delta_color, subset=["vs plain Glicko"])
        .format({"Rating": "{:.1f}", "vs plain Glicko": "{:+.1f}"})
        .format(lambda s: s, subset=["#"], escape=None)
        .format(lambda s: s, subset=["Fighter"], escape=None)
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Last fight", "Fights"], **{"color": THEME["text_muted"], "font-size": "0.88em"})
        .set_properties(subset=["Division"], **{"color": THEME["text_2"]})
        .set_properties(subset=["#"], **{"text-align": "center", "padding-right": "4px"})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def draw_top(*_):
    with _draw_guard("top") as ok:
        if not ok:
            return
        # Lock sleeves to canonical without retriggering self
        if scoring.value == "canonical":
            if integrity.value:
                integrity.value = False
            if performance.value:
                performance.value = False
            integrity.disabled = True
            performance.disabled = True
        else:
            integrity.disabled = False
            performance.disabled = False

        _clear_output(out_top)
        with out_top:
            try:
                col = select_modular_rating_column(
                    rc, scoring.value,
                    use_integrity=integrity.value,
                    use_performance=performance.value,
                    peak=peak.value,
                )
            except ValueError as exc:
                display(Markdown(f"**Invalid selection:** {exc}"))
                return
            if col is None or col not in rc.columns:
                display(Markdown("**No matching rating column in this snapshot.**"))
                return

            ctx = modular_rating_context(
                scoring.value,
                use_integrity=integrity.value,
                use_performance=performance.value,
            )
            window_label = dict(PEAK_VIEWS).get(peak.value, peak.value)
            display(Markdown(
                f"<div style='color:{THEME[\"text_2\"]};font-size:0.95em;"
                f"font-family:{THEME[\"font\"]};margin-bottom:6px'>"
                f"<b style='color:{THEME[\"text\"]}'>{window_label}</b> &middot; {ctx['label']}"
                f"</div>"
            ))
            display(_debug_caption(f"sorted by column <code>{col}</code>"))

            has_gender = "gender" in rc.columns
            men = rc[rc["gender"].eq("M")].copy() if has_gender else rc.copy()
            women = rc[rc["gender"].eq("F")].copy() if has_gender else rc.iloc[0:0].copy()

            if gender.value in ("both", "M"):
                display(Markdown("#### Men"))
                v = _build_top_view(men, col, n_men.value, min_fights.value, division_filter.value)
                display(_style_top(v) if not v.empty else Markdown("_no fighters match the current filters_"))
            if gender.value in ("both", "F"):
                display(Markdown("#### Women"))
                v = _build_top_view(women, col, n_women.value, min_fights.value, division_filter.value)
                display(_style_top(v) if not v.empty else Markdown("_no fighters match the current filters_"))


def draw_spotlight(*_):
    _clear_output(out_spot)
    with out_spot:
        names = list(spotlight.value or [])
        if not names:
            return
        if ratings_history is None or ratings_history.empty:
            display(Markdown("_no rating history available_"))
            return
        available = set(ratings_history.get("fighter", pd.Series(dtype=str)))
        names = [name for name in names if name in available]
        if not names:
            display(Markdown("_no selected fighters have rating history_"))
            return
        fig = trajectory_chart(ratings_history, fights, names,
                              show_phi_band=True, show_method_markers=True)
        fig.update_layout(
            title="Career rating overlay",
            xaxis_title="Date",
            yaxis_title="Rating",
            height=520,
            margin=dict(t=40, b=40, l=50, r=10),
        )
        fig.show()
        display(_debug_caption(
            "shaded band = 1σ rating uncertainty (±φ); dots colored by finish method"
        ))


controls = widgets.VBox([
    widgets.HBox([scoring, peak]),
    widgets.HBox([integrity, performance]),
    widgets.HBox([gender, division_filter]),
    widgets.HBox([n_men, n_women, min_fights]),
])
display(controls)
display(out_top)
display(Markdown("---"))
display(Markdown("#### Fighter Spotlight Overlay"))
display(spotlight)
display(out_spot)

draw_top()
draw_spotlight()

for w in (scoring, peak, integrity, performance, gender, division_filter, n_men, n_women, min_fights):
    _observe_once(w, draw_top, names="value")
_observe_once(spotlight, draw_spotlight, names="value")
"""),
    md("""
## Win Streaks

The longest unbeaten runs in the database, rank-ordered. **Sort** switches
between raw streak length, the average quality of the opponents beaten, and the
number of title wins inside the run. Filter by division and gender. Then pick
any streak below — or type a fighter — to see that fighter's rating climb and
fall on the timeline, with the streak window shaded gold.
"""),
    code(r"""
streak_div = widgets.Dropdown(
    options=["All divisions"] + list(DIVISIONS), value="All divisions",
    description="Division:", layout=widgets.Layout(width="320px"))
streak_gender = widgets.ToggleButtons(
    options=[("Both", "both"), ("Men", "M"), ("Women", "F")], value="both", description="Gender:")
streak_sort = widgets.Dropdown(
    options=[("Longest", "length"), ("Toughest schedule", "quality"), ("Most title wins", "title_wins")],
    value="length", description="Sort:")
streak_min_len = widgets.IntSlider(value=5, min=2, max=15, step=1, description="Min wins:")
streak_n = widgets.IntSlider(value=20, min=5, max=60, step=5, description="Rows:")
streak_pick = widgets.Dropdown(options=[], description="Timeline:",
                               layout=widgets.Layout(width="460px"), style={"description_width": "80px"})
streak_search = widgets.Text(value="", placeholder="…or type any fighter", description="Fighter:",
                             layout=widgets.Layout(width="360px"), style={"description_width": "80px"})
out_streaks = widgets.Output()
out_streak_tl = widgets.Output()
_streak_state = {"rows": None}


def _style_streaks(df):
    if df is None or df.empty:
        return Markdown("_no streaks match the current filters_")
    rows = df.reset_index(drop=True)
    def _yr(d):
        d = pd.to_datetime(d, errors="coerce")
        return "" if pd.isna(d) else d.strftime("%Y")
    view = pd.DataFrame({
        "#": [_rank_chip(i) for i in range(1, len(rows) + 1)],
        "Fighter": rows["fighter"],
        "Streak": rows["length"].astype(int),
        "Division": rows["division"].fillna("—"),
        "Span": [f"{_yr(s)}–{_yr(e)}" for s, e in zip(rows["start_date"], rows["end_date"])],
        "Avg opp": pd.to_numeric(rows["avg_opp_rating"], errors="coerce"),
        "Titles": rows["title_wins"].astype(int),
        "Finishes": rows["finishes"].astype(int),
        "Status": [("Active" if og else eb) for og, eb in zip(rows["ongoing"], rows["ended_by"])],
    })
    def status_color(v):
        return (f"color:{THEME['positive']};font-weight:600" if v == "Active"
                else f"color:{THEME['text_muted']}")
    smax = max(int(view["Streak"].max()), 1)
    return (
        view.style.hide(axis="index")
        .bar(subset=["Streak"], color="rgba(251,191,36,0.32)", vmin=0, vmax=smax)
        .map(status_color, subset=["Status"])
        .format({"Avg opp": "{:.0f}"}, na_rep="—")
        .format(lambda s: s, subset=["#"], escape=None)
        .format(lambda s: s, subset=["Fighter"], escape=None)
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Streak"], **{"font-weight": "700", "color": THEME["accent"]})
        .set_properties(subset=["Division", "Span", "Status"], **{"color": THEME["text_2"]})
        .set_properties(subset=["Avg opp", "Titles", "Finishes"], **{"color": THEME["text_muted"]})
        .set_properties(subset=["#"], **{"text-align": "center"})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def draw_streak_timeline(*_):
    _clear_output(out_streak_tl)
    with out_streak_tl:
        q = (streak_search.value or "").strip()
        if q:
            matches = fighter_search(rc, q, limit=1)
            if not matches:
                display(Markdown(f"_no fighter matches_ **{q}**"))
                return
            name = matches[0]
            fr = win_streaks(fights, rc, min_len=1)
            fr = fr[fr["fighter"].eq(name)]
            hs = he = None
            ln = None
            if not fr.empty:
                top = fr.sort_values("length", ascending=False).iloc[0]
                hs, he, ln = top["start_date"], top["end_date"], int(top["length"])
            streak_timeline_chart(name, ratings_history, fights,
                                  highlight_start=hs, highlight_end=he, streak_len=ln).show()
            return
        rows = _streak_state.get("rows")
        if rows is None or rows.empty or streak_pick.value is None:
            display(Markdown("_pick a streak above, or type a fighter_"))
            return
        r = rows.iloc[int(streak_pick.value)]
        streak_timeline_chart(r["fighter"], ratings_history, fights,
                              highlight_start=r["start_date"], highlight_end=r["end_date"],
                              streak_len=int(r["length"])).show()


def draw_streaks(*_):
    with _draw_guard("streaks") as ok:
        if not ok:
            return
        g = None if streak_gender.value == "both" else streak_gender.value
        t = win_streaks_table(fights, rc, min_len=streak_min_len.value, n=streak_n.value,
                              division=streak_div.value, gender=g, sort_by=streak_sort.value)
        t = t.reset_index(drop=True) if t is not None else None
        _streak_state["rows"] = t
        opts = []
        if t is not None and not t.empty:
            for i, r in t.iterrows():
                sy = pd.to_datetime(r["start_date"], errors="coerce")
                ey = pd.to_datetime(r["end_date"], errors="coerce")
                span = f"{'' if pd.isna(sy) else sy.year}–{'' if pd.isna(ey) else ey.year}"
                opts.append((f"{r['fighter']} — {int(r['length'])} wins ({span})", i))
        streak_pick.unobserve_all()
        streak_pick.options = opts
        if opts:
            streak_pick.value = opts[0][1]
        _observe_once(streak_pick, draw_streak_timeline, names="value")
        _clear_output(out_streaks)
        with out_streaks:
            display(_style_streaks(t))
        draw_streak_timeline()


display(widgets.VBox([
    widgets.HBox([streak_div, streak_gender]),
    widgets.HBox([streak_sort, streak_min_len, streak_n]),
]))
display(out_streaks)
display(Markdown("#### Rating timeline"))
display(widgets.HBox([streak_pick, streak_search]))
display(out_streak_tl)

draw_streaks()
for w in (streak_div, streak_gender, streak_sort, streak_min_len, streak_n):
    _observe_once(w, draw_streaks, names="value")
_observe_once(streak_search, draw_streak_timeline, names="value")
"""),
    md("""
## Top Fighter Placement

A placement view for the top fighters: rating score vertically, UFC sample
size horizontally, color by division. This is meant to show *where* a fighter
sits, not just their row number. The density chart below shows which divisions
actually occupy the top 100.
"""),
    code("""
placement_n = widgets.IntSlider(value=100, min=25, max=200, step=25, description="Top N:")
placement_min_fights = widgets.IntSlider(value=0, min=0, max=20, step=1, description="Min fights:")
out_placement = widgets.Output()


def _placement_col():
    try:
        return select_modular_rating_column(
            rc, scoring.value,
            use_integrity=integrity.value,
            use_performance=performance.value,
            peak=peak.value,
        ) or "sustained_peak_headline_mu_whr"
    except ValueError:
        return "sustained_peak_headline_mu_whr"


def draw_placement(*_):
    with _draw_guard("placement") as ok:
        if not ok:
            return
        _clear_output(out_placement)
        with out_placement:
            col = _placement_col()
            fig = top_fighter_placement_scatter(
                rc,
                rating_col=col,
                n=placement_n.value,
                min_fights=placement_min_fights.value,
            )
            fig.show()
            top100_division_density_chart(rc, rating_col=col, n=100).show()


display(widgets.HBox([placement_n, placement_min_fights]))
display(out_placement)
draw_placement()
for w in (placement_n, placement_min_fights, scoring, peak, integrity, performance):
    _observe_once(w, draw_placement, names="value")
"""),
    md("""
## Division Explorer

Drill into a single division: its current top of the rankings, how its top-end
strength has moved year over year, and how crowded the top has become. Switch
divisions to navigate the whole roster one weight class at a time.
"""),
    code(r"""
divx = widgets.Dropdown(
    options=list(DIVISIONS),
    value="Lightweight" if "Lightweight" in DIVISIONS else list(DIVISIONS)[0],
    description="Division:", layout=widgets.Layout(width="340px"))
divx_n = widgets.IntSlider(value=15, min=5, max=40, step=5, description="Top N:")
out_divx = widgets.Output()


def _divx_col():
    for c in ("sustained_peak_headline_mu_whr",
              "sustained_peak_mu_method_integrity_performance", "mu_canonical"):
        if c in rc.columns:
            return c
    return "mu_canonical"


def draw_divx(*_):
    with _draw_guard("divx") as ok:
        if not ok:
            return
        _clear_output(out_divx)
        with out_divx:
            col = _divx_col()
            recent = recent_division_by_fighter(fights)
            d = rc.merge(recent, on="fighter", how="left")
            d["division"] = d["division"].fillna(d.get("primary_division"))
            d = d[d["division"].eq(divx.value)].dropna(subset=[col])
            d = d.sort_values(col, ascending=False).head(divx_n.value).reset_index(drop=True)
            if d.empty:
                display(Markdown("_no rated fighters in this division_"))
            else:
                view = pd.DataFrame({
                    "#": [_rank_chip(i) for i in range(1, len(d) + 1)],
                    "Fighter": d["fighter"],
                    "Rating": pd.to_numeric(d[col], errors="coerce").round(1),
                    "Fights": pd.to_numeric(d.get("rating_periods"), errors="coerce").fillna(0).astype(int),
                    "Last fight": pd.to_datetime(d.get("last_event_date"), errors="coerce").dt.date,
                })
                rmin, rmax = view["Rating"].min(), view["Rating"].max()
                styled = (
                    view.style.hide(axis="index")
                    .bar(subset=["Rating"], color="rgba(56,189,248,0.28)", vmin=rmin, vmax=rmax)
                    .format({"Rating": "{:.1f}"})
                    .format(lambda s: s, subset=["#"], escape=None)
                    .format(lambda s: s, subset=["Fighter"], escape=None)
                    .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
                    .set_properties(subset=["Fights", "Last fight"], **{"color": THEME["text_muted"]})
                    .set_properties(subset=["#"], **{"text-align": "center"})
                    .set_table_styles(_BASE_TABLE_STYLES)
                )
                display(Markdown(f"#### Top {len(d)} — {divx.value}"))
                display(styled)
            try:
                weight_class_strength_chart(ratings_history, fights, divisions=[divx.value]).show()
            except Exception as exc:
                display(_debug_caption(f"strength chart unavailable: {exc}"))
            if division_entropy is not None and not division_entropy.empty:
                division_entropy_chart(division_entropy, divisions=[divx.value]).show()


display(widgets.HBox([divx, divx_n]))
display(out_divx)
draw_divx()
for w in (divx, divx_n):
    _observe_once(w, draw_divx, names="value")
"""),
    md("""
## Compare Fighters

Pick two fighters. The bar shows the model's predicted win probability for
that matchup. **Closeness** runs 0 to 1 — 1 means the fight is a coin-flip
on paper, 0 means a lopsided mismatch. Below that, side-by-side career cards
and, when the market data is available, each fighter's history as a
favorite vs underdog.
"""),
    code("""
_fighter_names = sorted(rc["fighter"].dropna().unique().tolist())
cmp_a = widgets.Dropdown(options=_fighter_names,
                         value="Jon Jones" if "Jon Jones" in _fighter_names else _fighter_names[0],
                         description="Fighter A:",
                         layout=widgets.Layout(width="380px"))
cmp_b = widgets.Dropdown(options=_fighter_names,
                         value="Stipe Miocic" if "Stipe Miocic" in _fighter_names else _fighter_names[1],
                         description="Fighter B:",
                         layout=widgets.Layout(width="380px"))
out_cmp = widgets.Output()


def _resume_block(fighter_name):
    detail = fighter_detail(fighter_name, fighters, rc, fights, fighter_dominance)
    if detail.get("error"):
        return f"<div style='color:#f87171;background:#1e293b;padding:10px 14px;border-radius:6px;border:1px solid #334155'>{detail['error']}</div>"
    rec = detail.get("record", {}) or {}
    ratings = detail.get("ratings", {}) or {}
    tape = detail.get("tale_of_the_tape", {}) or {}
    mu = ratings.get("mu_canonical")
    phi = ratings.get("phi_canonical")
    lo = ratings.get("ci95_lower")
    hi = ratings.get("ci95_upper")
    sp = ratings.get("sustained_peak_mu_canonical")
    rec_str = f"{rec.get('wins',0)}–{rec.get('losses',0)}"
    if rec.get('draws', 0):
        rec_str += f"–{rec['draws']}"
    if rec.get('no_contests', 0):
        rec_str += f" ({rec['no_contests']} NC)"
    stance = tape.get("stance") or "—"
    reach = tape.get("reach_inches")
    height = tape.get("height_inches")
    font = '-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif'
    return (
        f"<div style='border:1px solid #334155;border-radius:8px;padding:14px 16px;"
        f"background:#1e293b;color:#f1f5f9;font-family:{font}'>"
        f"<div style='font-size:1.18em;font-weight:700;color:#f1f5f9'>{fighter_name}</div>"
        f"<div style='color:#94a3b8;font-size:0.88em;margin-bottom:8px'>{stance}"
        f"{f' &middot; {height}″' if height else ''}"
        f"{f' &middot; reach {reach}″' if reach else ''}"
        f"</div>"
        f"<div style='font-size:0.95em;margin:2px 0;color:#cbd5e1'><b style='color:#f1f5f9'>Record:</b> {rec_str}</div>"
        f"<div style='font-size:0.95em;margin:2px 0;color:#cbd5e1'><b style='color:#f1f5f9'>Rating:</b> {mu:.1f} "
        f"<span style='color:#64748b'>(confidence ±{phi:.1f}, range {lo:.0f}–{hi:.0f})</span></div>"
        + (f"<div style='font-size:0.95em;margin:2px 0;color:#cbd5e1'><b style='color:#f1f5f9'>Career peak:</b> {sp:.1f}</div>" if sp else "")
        + f"<div style='color:#64748b;font-size:0.85em;margin-top:6px'>Fights rated: {ratings.get('rating_periods', 0)}</div>"
        f"</div>"
    )


def _market_history_row(fighter_name):
    if odds_lines is None or odds_lines.empty:
        return None
    needed = {"fight_url", "fighter_a", "fighter_b",
              "implied_prob_a_no_vig", "implied_prob_b_no_vig", "odds_data_quality"}
    if not needed.issubset(odds_lines.columns):
        return None
    ok = odds_lines[odds_lines["odds_data_quality"] == "ok"].copy()
    if ok.empty or fights is None or fights.empty:
        return None
    a = ok[ok["fighter_a"] == fighter_name][["fight_url", "implied_prob_a_no_vig"]].rename(
        columns={"implied_prob_a_no_vig": "market_prob"}
    )
    b = ok[ok["fighter_b"] == fighter_name][["fight_url", "implied_prob_b_no_vig"]].rename(
        columns={"implied_prob_b_no_vig": "market_prob"}
    )
    long = pd.concat([a, b], ignore_index=True)
    if long.empty:
        return None
    j = long.merge(fights[["fight_url", "winner", "is_draw"]], on="fight_url", how="inner")
    if j.empty:
        return None
    fav = j[j["market_prob"] >= 0.5]
    dog = j[j["market_prob"] < 0.5]
    def _wr(sub):
        decided = sub[~sub["is_draw"].fillna(False).astype(bool)]
        if decided.empty:
            return None
        # winner == fighter_name means they won
        wins = int((decided.merge(
            ok[["fight_url"]].assign(_=1), on="fight_url", how="left"
        )["winner"] == fighter_name).sum() if False else 0)
        # Simpler: count wins by checking fights.winner directly
        wins = int((decided["winner"] == fighter_name).sum())
        return wins, len(decided), wins / len(decided)
    fav_res = _wr(fav)
    dog_res = _wr(dog)
    return {"as_favorite": fav_res, "as_underdog": dog_res, "total": len(j)}


def _market_card(fighter_name):
    mh = _market_history_row(fighter_name)
    if not mh:
        return None
    font = '-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif'
    def _fmt(side, res):
        if not res:
            return f"<div style='color:#64748b;font-size:0.9em'>{side}: no fights in this bucket</div>"
        wins, total, rate = res
        return (
            f"<div style='font-size:0.93em;margin:2px 0;color:#cbd5e1'>"
            f"<b style='color:#f1f5f9'>{side}:</b> {wins}–{total - wins} "
            f"<span style='color:#94a3b8'>({rate*100:.0f}% win)</span></div>"
        )
    return (
        f"<div style='border:1px solid #334155;border-radius:8px;padding:12px 14px;"
        f"background:#1e293b;margin-top:10px;font-family:{font}'>"
        f"<div style='color:#94a3b8;font-size:0.74em;text-transform:uppercase;letter-spacing:0.08em;font-weight:600;margin-bottom:6px'>"
        f"Market history</div>"
        f"{_fmt('As favorite', mh['as_favorite'])}"
        f"{_fmt('As underdog', mh['as_underdog'])}"
        f"<div style='color:#64748b;font-size:0.8em;margin-top:6px'>"
        f"Market data covers {mh['total']} of this fighter's bouts</div>"
        f"</div>"
    )


def draw_compare(*_):
    with _draw_guard("compare") as ok:
        if not ok:
            return
        _clear_output(out_cmp)
        with out_cmp:
            a, b = (cmp_a.value or "").strip(), (cmp_b.value or "").strip()
            if not a or not b:
                display(Markdown("_pick two fighters_"))
                return
            if a == b:
                display(Markdown("_pick two different fighters_"))
                return
            pred = h2h_prediction(a, b, rc)
            if pred.get("error"):
                display(Markdown(f"**{pred['error']}**"))
                return
            pa = pred["p_a_wins"] * 100
            pb = pred["p_b_wins"] * 100
            qual = pred["matchup_quality_0_to_1"]
            font = '-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif'
            prob_bar = (
                f"<div style='margin:14px 0;font-family:{font}'>"
                f"<div style='display:flex;font-size:0.95em;color:#cbd5e1;margin-bottom:4px'>"
                f"<div style='flex:1'><b style='color:#38bdf8'>{a}</b> &mdash; {pa:.1f}%</div>"
                f"<div style='text-align:right'>{pb:.1f}% &mdash; <b style='color:#a78bfa'>{b}</b></div>"
                f"</div>"
                f"<div style='height:22px;border-radius:11px;overflow:hidden;background:#1e293b;display:flex;border:1px solid #334155'>"
                f"<div style='width:{pa:.1f}%;background:#38bdf8'></div>"
                f"<div style='width:{pb:.1f}%;background:#a78bfa'></div>"
                f"</div>"
                f"<div style='color:#94a3b8;font-size:0.88em;margin-top:6px'>"
                f"Closeness: <b style='color:#f1f5f9'>{qual:.2f}</b> "
                f"<span style='color:#64748b'>(1 = coin-flip, 0 = lopsided)</span>"
                f"</div>"
                f"</div>"
            )
            display(Markdown(prob_bar))
            cards = (
                f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:14px'>"
                f"<div>{_resume_block(a)}{_market_card(a) or ''}</div>"
                f"<div>{_resume_block(b)}{_market_card(b) or ''}</div>"
                f"</div>"
            )
            display(Markdown(cards))
            left = widgets.Output()
            right = widgets.Output()
            with left:
                fighter_profile_chart(a, rc).show()
                fighter_odds_history_chart(a, odds_lines, fights).show()
            with right:
                fighter_profile_chart(b, rc).show()
                fighter_odds_history_chart(b, odds_lines, fights).show()
            display(widgets.HBox([left, right]))


display(widgets.HBox([cmp_a, cmp_b]))
display(out_cmp)
draw_compare()
_observe_once(cmp_a, draw_compare, names="value")
_observe_once(cmp_b, draw_compare, names="value")
"""),
    md("""
## Why a Fighter is Where They Are

Pick a fighter. The waterfall below breaks down each sleeve adjustment that
moved their rating away from the plain method baseline — PED damp, DQ
penalty, quality-of-win bonus, market-upset bonus, championship context,
and so on. Bars to the right are boosts; bars to the left are penalties.
"""),
    code("""
attr_fighter = widgets.Dropdown(
    options=_fighter_names,
    value="Georges St-Pierre" if "Georges St-Pierre" in _fighter_names else _fighter_names[0],
    description="Fighter:",
    layout=widgets.Layout(width="420px"),
)
attr_rows = widgets.IntSlider(value=20, min=5, max=60, step=5, description="Rows:")
out_attr = widgets.Output()


def _style_attribution_rows(df):
    if df.empty:
        return df
    rename = {
        "event_date": "Date",
        "event_name": "Event",
        "opponent": "Opponent",
        "base_method_delta": "Result/method",
        "integrity_delta": "Integrity",
        "performance_delta": "Performance",
        "interaction_delta": "Overlap",
        "combined_delta": "Net movement",
        "integrity_weight": "Integrity weight",
        "performance_weight": "Performance weight",
        "combined_weight": "Final weight",
    }
    out = df.rename(columns=rename)
    show = [c for c in [
        "Date", "Opponent", "Result/method", "Integrity", "Performance",
        "Overlap", "Net movement", "Final weight",
    ] if c in out.columns]
    out = out[show]
    return (
        out.style
        .hide(axis="index")
        .format({
            "Result/method": "{:+.2f}",
            "Integrity": "{:+.2f}",
            "Performance": "{:+.2f}",
            "Overlap": "{:+.2f}",
            "Net movement": "{:+.2f}",
            "Final weight": "{:.2f}",
        }, na_rep="")
        .set_properties(subset=["Opponent"], **{"font-weight": "600", "color": THEME["text"]})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def draw_attribution(*_):
    with _draw_guard("attribution") as ok:
        if not ok:
            return
        _clear_output(out_attr)
        with out_attr:
            sleeve_attribution_waterfall(sleeve_attribution, attr_fighter.value).show()
            rows = sleeve_attribution_table(sleeve_attribution, attr_fighter.value, n=attr_rows.value)
            display(_style_attribution_rows(rows) if not rows.empty else Markdown("_no attribution rows_"))


display(widgets.HBox([attr_fighter, attr_rows]))
display(out_attr)
draw_attribution()
_observe_once(attr_fighter, draw_attribution, names="value")
_observe_once(attr_rows, draw_attribution, names="value")
"""),
    md("""
## Sleeve Adjustments — Where They Fire

Every adjustment factor in the model — PED, DQ, missed-weight on the integrity
side; quality of win, market upset, rank context, championship context, P4P,
weight-class movement, post-layoff loss on the performance side — and how
often each one actually fires. The summary shows appearance counts and the
multiplier range; the detail table shows the largest individual effects.
"""),
    code("""
audit_sleeve = widgets.Dropdown(
    options=[("All", "all"), ("Integrity", "integrity"), ("Performance", "performance")],
    value="all", description="Sleeve:",
)
audit_effect = widgets.Dropdown(
    options=[("Boost + penalty", "all"), ("Boost only", "boost"), ("Penalty only", "penalty")],
    value="all", description="Effect:",
)
audit_fighter = widgets.Dropdown(options=[("(all fighters)", "")] + [(n, n) for n in _fighter_names], value="",
                                 description="Fighter:",
                                 layout=widgets.Layout(width="360px"))
audit_n = widgets.IntSlider(value=25, min=5, max=100, step=5, description="Rows:")
out_audit = widgets.Output()


def _style_audit_summary(df):
    if df.empty:
        return df
    show = df[[c for c in [
        "group", "factor", "direction", "appearances",
        "median_effect_pct", "min_effect_pct", "max_effect_pct",
    ] if c in df.columns]].copy()
    show = show.rename(columns={
        "group": "Group",
        "factor": "Factor",
        "direction": "Direction",
        "appearances": "Uses",
        "median_effect_pct": "Typical",
        "min_effect_pct": "Low",
        "max_effect_pct": "High",
    })
    return (
        show.style
        .hide(axis="index")
        .bar(subset=["Uses"], color="rgba(56,189,248,0.28)")
        .format({"Typical": "{:+.1f}%", "Low": "{:+.1f}%", "High": "{:+.1f}%"})
        .set_properties(subset=["Factor"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Group", "Direction"], **{"color": THEME["text_2"]})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def _style_audit_detail(df):
    if df.empty:
        return df
    show_cols = [c for c in [
        "event_date", "fighter", "opponent", "outcome", "direction",
        "combined_effect_pct", "factors", "sleeves", "division",
    ] if c in df.columns]
    out = df[show_cols].rename(columns={
        "event_date": "Date",
        "fighter": "Fighter",
        "opponent": "Opponent",
        "outcome": "Result",
        "direction": "Direction",
        "combined_effect_pct": "Net effect",
        "factors": "Factors",
        "sleeves": "Sleeves",
        "division": "Division",
    }).copy()
    def effect_color(v):
        if v == "Boost":
            return f"color:{THEME['positive']};font-weight:600"
        if v == "Penalty":
            return f"color:{THEME['negative']};font-weight:600"
        return f"color:{THEME['text_muted']}"
    return (
        out.style
        .hide(axis="index")
        .map(effect_color, subset=["Direction"])
        .format({"Net effect": "{:+.1f}%"})
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Opponent", "Division", "Sleeves"], **{"color": THEME["text_2"]})
        .set_properties(subset=["Factors"], **{"color": THEME["text_2"], "font-size": "0.9em"})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def draw_audit(*_):
    with _draw_guard("audit") as ok:
        if not ok:
            return
        _clear_output(out_audit)
        with out_audit:
            summary = sleeve_factor_summary_table(integrity_appearances, performance_appearances)
            if audit_sleeve.value != "all":
                summary = summary[summary["sleeve"].eq(audit_sleeve.value)]
            if summary.empty:
                display(Markdown("_no sleeve activity in this snapshot_"))
            else:
                display(Markdown("#### Factor summary"))
                display(_style_audit_summary(summary))

            fighter_filter = (audit_fighter.value or "").strip() or None
            detail = sleeve_effects_by_fight_table(
                integrity_appearances if audit_sleeve.value in ("all", "integrity") else pd.DataFrame(),
                performance_appearances if audit_sleeve.value in ("all", "performance") else pd.DataFrame(),
                n=audit_n.value,
                fighter=fighter_filter,
                effect=audit_effect.value,
            )
            if not detail.empty:
                display(Markdown("#### Largest fight-level effects"))
                display(_style_audit_detail(detail))
            else:
                display(Markdown("_no factor effects match the current filters_"))


display(widgets.VBox([
    widgets.HBox([audit_sleeve, audit_effect]),
    widgets.HBox([audit_fighter, audit_n]),
]))
display(out_audit)
draw_audit()
for w in (audit_sleeve, audit_effect, audit_fighter, audit_n):
    _observe_once(w, draw_audit, names="value")
"""),
    md("""
## Our Rankings vs FightMatrix

A sanity check against an outside ranking. Each dot is a fighter both systems
rate; hover over a dot to see the fighter, both rankings, and the rating
numbers. The further a dot is from the cloud, the more the two systems
disagree — the table lists the biggest disagreements explicitly.
"""),
    code("""
gfm_min_fights = widgets.IntSlider(value=3, min=0, max=15, step=1, description="Min fights:")
gfm_table_n = widgets.IntSlider(value=20, min=5, max=60, step=5, description="Table rows:")
out_gfm = widgets.Output()


def _style_rank_delta(df):
    if df.empty:
        return df
    rename = {
        "fighter": "Fighter", "glicko_rank": "Our rank",
        "mu_canonical": "Our rating",
        "fightmatrix_rank": "FightMatrix rank",
        "fightmatrix_points": "FightMatrix points",
        "fightmatrix_division": "Division",
        "glicko_vs_fm_rank_delta": "Rank gap",
        "delta_mu_method_integrity": "Integrity adj.",
        "ped_confirmed_fights": "PED",
        "dq_wins": "DQ", "missed_weight_wins": "MW",
    }
    show_cols = [c for c in [
        "fighter", "glicko_rank", "fightmatrix_rank", "glicko_vs_fm_rank_delta",
        "mu_canonical", "fightmatrix_points", "fightmatrix_division",
        "delta_mu_method_integrity", "ped_confirmed_fights", "dq_wins", "missed_weight_wins",
    ] if c in df.columns]
    out = df[show_cols].rename(columns=rename).copy()
    def delta_color(v):
        if pd.isna(v):
            return ""
        # rank gap: positive = we rank LOWER than FightMatrix => use negative-style red
        if v > 0:
            return f"color:{THEME['negative']};font-weight:600"
        if v < 0:
            return f"color:{THEME['positive']};font-weight:600"
        return f"color:{THEME['text_muted']}"
    fmt = {}
    if "Our rating" in out.columns:
        fmt["Our rating"] = "{:.1f}"
    if "FightMatrix points" in out.columns:
        fmt["FightMatrix points"] = "{:.0f}"
    if "Integrity adj." in out.columns:
        fmt["Integrity adj."] = "{:+.1f}"
    if "Rank gap" in out.columns:
        fmt["Rank gap"] = "{:+.0f}"
    styled = (
        out.style
        .hide(axis="index")
        .format(fmt, na_rep="—")
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_table_styles(_BASE_TABLE_STYLES)
    )
    if "Rank gap" in out.columns:
        styled = styled.map(delta_color, subset=["Rank gap"])
    return styled


def draw_gfm(*_):
    with _draw_guard("gfm") as ok:
        if not ok:
            return
        _clear_output(out_gfm)
        with out_gfm:
            if fightmatrix_rankings is None or fightmatrix_rankings.empty:
                display(Markdown("_no FightMatrix data in this snapshot_"))
                return
            fig = glicko_fightmatrix_scatter(
                rc, fightmatrix_rankings,
                min_fights=gfm_min_fights.value,
                label_outliers=0,
            )
            fig.update_layout(
                title="Our rating vs FightMatrix points",
                xaxis_title="Our rating",
                yaxis_title="FightMatrix points",
            )
            fig.show()
            deltas = rank_delta_table(rc, fightmatrix_rankings,
                                      min_fights=gfm_min_fights.value,
                                      limit=gfm_table_n.value)
            if deltas.empty:
                display(Markdown("_no rank-disagreement rows available_"))
            else:
                display(Markdown("#### Biggest rank disagreements"))
                display(_style_rank_delta(deltas))


display(widgets.HBox([gfm_min_fights, gfm_table_n]))
display(out_gfm)
draw_gfm()
for w in (gfm_min_fights, gfm_table_n):
    _observe_once(w, draw_gfm, names="value")
"""),
    md("""
## Top-End Strength by Era

Each row is a division; each column is a year. The color is normalized inside
each year: 100 means the strongest division that year, lower values show how
far a division sat behind that year's leader.
"""),
    code("""
era_top_n = widgets.IntSlider(value=15, min=5, max=30, step=5, description="Top N:")
out_era = widgets.Output()


def draw_era(*_):
    with _draw_guard("era") as ok:
        if not ok:
            return
        _clear_output(out_era)
        with out_era:
            if ratings_history is None or ratings_history.empty:
                display(Markdown("_no ratings history in this snapshot_"))
                return
            fig = era_heatmap_chart(ratings_history, fights, top_n=era_top_n.value)
            fig.update_layout(
                title=f"Top-end division strength index (top {era_top_n.value})",
                coloraxis_colorbar=dict(
                    title=dict(text="Strength index", font=dict(color="#cbd5e1")),
                    tickfont=dict(color="#cbd5e1"),
                ),
            )
            for tr in fig.data:
                if hasattr(tr, "colorbar"):
                    tr.colorbar = dict(
                        title=dict(text="Strength index", font=dict(color="#cbd5e1")),
                        tickfont=dict(color="#cbd5e1"),
                    )
            fig.show()
            display(_debug_caption(
                "100 = strongest division in that year; hover still shows the underlying average rating"
            ))


display(era_top_n)
display(out_era)
draw_era()
_observe_once(era_top_n, draw_era, names="value")
"""),
    md("""
## PED Curation Gap

**Diagnostic, not for general audiences.** The integrity sleeve can only damp
PED-confirmed wins for bouts curated in `ped_confirmed_bouts.csv`. This cell
shows what's currently curated and a candidate set of fighters publicly
associated with PEDs who don't yet have rows. No data is written here —
this is a visibility-only queue.
"""),
    code("""
out_ped = widgets.Output()


def _style_curated(df):
    return (
        df.style
        .hide(axis="index")
        .set_properties(subset=["fighter_a", "fighter_b", "winner"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["ped_confirmation_detail"], **{"color": THEME["text_2"], "font-size": "0.88em"})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


with out_ped:
    if ped_confirmed_bouts is None or ped_confirmed_bouts.empty:
        display(Markdown("**No `ped_confirmed_bouts.csv` in this snapshot.**"))
    else:
        n_rows = len(ped_confirmed_bouts)
        curated_fighters = set(ped_confirmed_bouts["ped_flagged_fighter"].dropna().unique())
        display(Markdown(
            f"<div style='color:#cbd5e1;font-size:0.95em;"
            f"font-family:-apple-system,BlinkMacSystemFont,\\\"Segoe UI\\\",system-ui,sans-serif'>"
            f"<b style='color:#f1f5f9'>{n_rows}</b> PED-confirmed bouts currently curated, "
            f"covering <b style='color:#f1f5f9'>{len(curated_fighters)}</b> distinct fighters."
            f"</div>"
        ))
        show = ped_confirmed_bouts[[
            "event_date", "event_name", "fighter_a", "fighter_b", "winner",
            "ped_flagged_fighter", "ped_confirmation_detail",
        ]].copy()
        show["event_date"] = pd.to_datetime(show["event_date"], errors="coerce").dt.date
        display(Markdown("#### Currently curated"))
        display(_style_curated(show))

        if "ped_confirmed_fights" in rc.columns:
            rc_with_ped = rc[pd.to_numeric(rc["ped_confirmed_fights"], errors="coerce").fillna(0) > 0]
            uncovered = sorted(set(rc_with_ped["fighter"]) - curated_fighters)
            display(Markdown("#### Candidates not yet in CSV"))
            known_candidates = [
                "Jon Jones", "Anderson Silva", "Brock Lesnar", "Chael Sonnen",
                "Alistair Overeem", "Frank Mir", "Josh Barnett", "Stephan Bonnar",
                "Cris Cyborg", "Lyoto Machida", "Yoel Romero", "Tim Means",
                "Hector Lombard", "Thiago Silva", "Cung Le",
            ]
            rc_names = set(rc["fighter"].dropna().unique())
            rows = []
            for name in uncovered:
                rows.append({"source": "rc flag (no CSV row)", "fighter": name})
            for name in known_candidates:
                if name not in curated_fighters and name in rc_names:
                    rows.append({"source": "public-reporting candidate", "fighter": name})
            queue = pd.DataFrame(rows).drop_duplicates(subset=["fighter"]).reset_index(drop=True)
            if queue.empty:
                display(Markdown("_no candidates surface from current heuristics_"))
            else:
                display(queue.style.hide(axis="index").set_table_styles(_BASE_TABLE_STYLES))
                display(Markdown(
                    f"<div style='color:#94a3b8;font-size:0.85em;margin-top:6px;"
                    f"font-family:-apple-system,BlinkMacSystemFont,\\\"Segoe UI\\\",system-ui,sans-serif'>"
                    f"Curation queue ({len(queue)} fighters). Add a row per "
                    f"<code>fight_url</code> to <code>data/snapshots/&lt;date&gt;/ped_confirmed_bouts.csv</code> "
                    f"and rebuild ratings to apply the integrity damper."
                    f"</div>"
                ))


display(out_ped)
"""),
]


def build() -> dict:
    return {
        "cells": CELLS,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3 (ipykernel)",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.14.3",
                "mimetype": "text/x-python",
                "codemirror_mode": {"name": "ipython", "version": 3},
                "pygments_lexer": "ipython3",
                "nbconvert_exporter": "python",
                "file_extension": ".py",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "notebook.ipynb"
    target.write_text(json.dumps(build(), indent=1), encoding="utf-8")
    print(f"wrote {target} ({target.stat().st_size} bytes)")
