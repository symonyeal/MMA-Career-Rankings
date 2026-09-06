"""Generate the interactive rankings dashboard notebook.

The notebook is read-only over build-time artifacts in ``data/snapshots/<date>/``.
Its defining feature is a single **Control Room** at the top: a row of global
controls (ranking question, division, gender, top-N, and min-fights) that every
section subscribes to. Changing a control re-draws every
section that depends on it.

Reactivity is built on ``plotly.graph_objects.FigureWidget`` (charts are mutated
in place) and ``ipywidgets.HTML`` (tables get a new ``.value``). We deliberately
avoid the ``Output`` + ``fig.show()`` pattern, which fails to refresh reliably in
the VS Code notebook host and hangs under headless ``nbconvert``.
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
# Cell 1 — imports + snapshot load. Unchanged data contract from the prior
# notebook; this block is the single source of the in-memory frames.

DATA_LOAD = r"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from IPython.display import display, Markdown
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

from analysis.viz import (  # noqa: E402
    all_time_score_anatomy_chart,
    all_time_benchmark_chart,
    all_time_benchmark_table,
    DIV_SHORT,
    DIVISIONS,
    PUBLIC_RANKING_VIEWS,
    division_strength_timeline_chart,
    division_year_top_fighters_chart,
    era_heatmap_chart,
    favorite_underdog_performance_table,
    fighter_odds_history_chart,
    fighter_profile_chart,
    fighter_detail,
    fighter_search,
    load_project_data,
    public_history_key,
    public_rating_label,
    select_public_ranking_column,
    streak_timeline_chart,
    top100_division_density_chart,
    top_fighter_placement_scatter,
    trajectory_chart,
    win_streaks,
    win_streaks_table,
    yearly_rating_delta_scatter,
    # --- 2026-06-23 chart additions (see _archive/20260901-lean-pass/analysis/CHART_PLAN.md) ---
    division_entropy_chart,
    odds_coverage_summary,
    fighter_betting_line_chart,
    favorite_underdog_performance_chart,
    striking_profile_chart,
    dominance_leaderboard_chart,
    integrity_ledger_table,
    integrity_impact_chart,
    career_rank_interval_chart,
    career_shape_scatter,
    career_bar_ladder_chart,
    career_contribution_chart,
    evidence_vs_rating_chart,
    legacy_vs_prime_scatter,
    method_mix_timeline_chart,
    title_lineage_chart,
    heldout_scorecard_chart,
    ablation_forest_chart,
)
from ratings.symon_score import career_mass_family as _career_mass_family  # noqa: E402

SNAPSHOT_BASE = PROJECT_ROOT / "data" / "snapshots"
SNAPSHOT_CANDIDATES = [
    p for p in SNAPSHOT_BASE.iterdir()
    if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)
]
SNAPSHOT_DIR = sorted(SNAPSHOT_CANDIDATES, key=lambda p: p.name)[-1]
PREVIOUS_SNAPSHOT_DIR = (
    sorted([p for p in SNAPSHOT_CANDIDATES if p.name < SNAPSHOT_DIR.name], key=lambda p: p.name)[-1]
    if any(p.name < SNAPSHOT_DIR.name for p in SNAPSHOT_CANDIDATES)
    else None
)
DATABASE_PATH = PROJECT_ROOT / "data" / "ufc_rank_engine.sqlite"
SNAP = load_project_data(SNAPSHOT_DIR, DATABASE_PATH, prefer_database=False)
PREV = load_project_data(PREVIOUS_SNAPSHOT_DIR, DATABASE_PATH, prefer_database=False) if PREVIOUS_SNAPSHOT_DIR else {}

fights = SNAP["fights"]
fighters = SNAP["fighters"]
rc = SNAP["ratings_current"]
previous_rc = PREV.get("ratings_current", pd.DataFrame())
career_mass_uncertainty = SNAP.get("career_mass_uncertainty", pd.DataFrame())
division_resume = SNAP.get("division_resume", pd.DataFrame())
performance_appearances = SNAP.get("performance_appearances", pd.DataFrame())
integrity_appearances = SNAP.get("integrity_appearances", pd.DataFrame())
integrity_ledger = SNAP.get("integrity_ledger", pd.DataFrame())
integrity_discounted_board = SNAP.get("integrity_discounted_board", pd.DataFrame())
rounds = SNAP.get("rounds", pd.DataFrame())
division_entropy = SNAP.get("division_entropy", pd.DataFrame())
odds_lines = SNAP.get("odds_lines", pd.DataFrame())
prequential_predictions = SNAP.get("prequential_predictions", pd.DataFrame())
prequential_scores = SNAP.get("prequential_scores", pd.DataFrame())
prequential_paired = SNAP.get("prequential_paired", pd.DataFrame())
fightmatrix_all_time = SNAP.get("fightmatrix_all_time", pd.DataFrame())
ratings_history = SNAP.get("ratings_history", pd.DataFrame())
ratings_history_whr = SNAP.get("ratings_history_whr", pd.DataFrame())
ratings_histories = {
    "ratings_history_whr": ratings_history_whr,
}
# The same career functional recomputed at five bars. Cheap: it re-reads the
# fitted history, it does not refit the smoother.
CAREER_MASS_FAMILY = _career_mass_family(ratings_history_whr)
previous_fights = PREV.get("fights", pd.DataFrame())
previous_ratings_history = PREV.get("ratings_history", pd.DataFrame())
previous_ratings_history_whr = PREV.get("ratings_history_whr", pd.DataFrame())
previous_ratings_histories = {
    "ratings_history_whr": previous_ratings_history_whr,
}
fighter_dominance = SNAP.get("fighter_dominance", pd.DataFrame())
# The rated corpus is the authoritative combined table, not a re-concatenation
# of the UFC rows with whichever cross-org artifact happens to be staged. Those
# are different corpora: combined_fights is what the ratings on this page were
# actually fitted on, while the old concatenation pulled in the FightMatrix
# diagnostic scope even when the board was fitted on the Sherdog majors.
all_bouts = SNAP.get("combined_fights", pd.DataFrame())
if all_bouts.empty:
    all_bouts = fights
previous_all_bouts = PREV.get("combined_fights", pd.DataFrame())
if previous_all_bouts.empty:
    previous_all_bouts = previous_fights
non_ufc_bouts = (
    int((all_bouts["source_corpus"] != "ufc").sum())
    if "source_corpus" in all_bouts.columns else 0
)

display(Markdown(
    f"<div style='color:#cbd5e1;font-size:0.95em;"
    f"font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",system-ui,sans-serif'>"
    f"<b style='color:#f1f5f9'>Snapshot</b> <code>{SNAPSHOT_DIR.name}</code> &middot; "
    f"<b style='color:#f1f5f9'>{len(fights):,}</b> UFC bouts &middot; "
    f"<b style='color:#f1f5f9'>{non_ufc_bouts:,}</b> non-UFC bouts &middot; "
    f"<b style='color:#f1f5f9'>{len(rc):,}</b> fighters"
    f"</div>"
))
"""


# ---------------------------------------------------------------------------
# Cell 2 — shared runtime helpers: theme chrome, FigureWidget/HTML rendering,
# and the central subscribe/broadcast registry that wires the Control Room to
# every section.

RUNTIME = """
# Shared runtime helpers ----------------------------------------------------
# Visual identity (THEME + the "ufc_dark" Plotly template) lives in analysis.viz
# so chrome and charts share ONE source of truth. Importing viz already
# registered and defaulted the template; here we pull THEME in for HTML chrome
# and define the rendering + reactivity plumbing used by every section.
import os
import traceback

from analysis.viz import THEME

CHART_H = 460
_STRICT = bool(os.environ.get("NB_STRICT"))


def chart_widget(height=CHART_H):
    "A live FigureWidget pre-themed for the dark canvas; updated in place."
    fw = go.FigureWidget()
    fw.layout.template = "ufc_dark"
    fw.layout.height = height
    fw.layout.margin = dict(t=56, r=32, b=52, l=64)
    return fw


def show_fig(fw, fig):
    "Sync a freshly built go.Figure into a live FigureWidget (no re-display)."
    # Replace NaN/inf in customdata before pushing to the widget — jupyter_client
    # rejects non-finite floats during JSON serialization and emits a UserWarning.
    for _trace in (fig.data or []):
        _cd = getattr(_trace, "customdata", None)
        if _cd is not None:
            try:
                _arr = np.asarray(_cd, dtype=object)
                _mask = pd.isnull(_arr)
                if _mask.any():
                    _arr[_mask] = ""
                    _trace.customdata = _arr
            except Exception:
                pass
    with fw.batch_update():
        fw.data = ()
        if getattr(fig, "data", None):
            fw.add_traces(fig.data)
        fw.layout = fig.layout


def html_box(value=""):
    return widgets.HTML(value=value)


def table_html(obj):
    "Render a pandas Styler / DataFrame to an HTML string for a widgets.HTML."
    if obj is None:
        return ""
    if hasattr(obj, "to_html"):          # pandas Styler
        return obj.to_html()
    if isinstance(obj, pd.DataFrame):
        return "" if obj.empty else obj.to_html()
    return str(obj)


def note(text):
    "A muted caption that explains what a chart means."
    return (
        f"<div style='color:{THEME['text_caption']};font-family:{THEME['font']};"
        f"font-size:0.82em;line-height:1.5;margin:2px 0 4px'><i>{text}</i></div>"
    )


def msg(text):
    "An italic 'nothing to show' placeholder."
    return (
        f"<div style='color:{THEME['text_muted']};font-family:{THEME['font']};"
        f"font-style:italic;padding:6px 0'>{text}</div>"
    )


def heading(text):
    return (
        f"<div style='color:{THEME['text_2']};font-family:{THEME['font']};"
        f"font-size:0.78em;font-weight:600;text-transform:uppercase;"
        f"letter-spacing:0.08em;margin:12px 0 4px'>{text}</div>"
    )


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


_OUR_HANDLERS = {}   # id(widget) -> our last-registered callback


def _observe(widget, callback, names="value"):
    # Idempotent on re-run WITHOUT calling unobserve_all(): that would also strip
    # ipywidgets' internal options->_options_values observer, after which setting
    # .options silently stops updating the selectable values. So we only remove
    # the specific callback we registered previously for this widget.
    prev = _OUR_HANDLERS.get(id(widget))
    if prev is not None:
        try:
            widget.unobserve(prev, names=names)
        except Exception:
            pass
    _OUR_HANDLERS[id(widget)] = callback
    widget.observe(callback, names=names)


# --- Central reactivity registry ------------------------------------------
# Each section registers a draw function plus the set of global-control keys it
# depends on. The Control Room broadcasts a key when its widget changes; every
# subscriber interested in that key redraws.
SUBSCRIBERS = []     # list of (name, draw_fn, keys:set) — Control-Room key deps
SECTION_DRAWS = []   # list of (name, draw_fn) — every section, for full redraw


def register_section(name, fn):
    "Register a section's primary draw for an explicit full refresh."
    global SECTION_DRAWS
    SECTION_DRAWS = [s for s in SECTION_DRAWS if s[0] != name]
    SECTION_DRAWS.append((name, fn))


def subscribe(name, fn, keys):
    global SUBSCRIBERS
    SUBSCRIBERS = [s for s in SUBSCRIBERS if s[0] != name]
    SUBSCRIBERS.append((name, fn, set(keys)))
    register_section(name, fn)


def _run_draw(name, fn):
    try:
        fn()
    except Exception as exc:
        if _STRICT:
            raise
        print(f"[{name}] draw error: {exc}")
        traceback.print_exc()


def broadcast(key):
    for name, fn, keys in list(SUBSCRIBERS):
        if key in keys:
            _run_draw(name, fn)


def redraw_all():
    "Re-run every registered section draw."
    for name, fn in list(SECTION_DRAWS):
        _run_draw(name, fn)


# Canvas-wide CSS so markdown, tables, headings, and widgets share the dark
# canvas + typography. Scoped to rendered output, not the host IDE chrome.
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
  .jp-RenderedHTMLCommon h1, .jp-RenderedMarkdown h1 {{ font-size: 1.7em; margin-top: 1.2em; }}
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


# ---------------------------------------------------------------------------
# Cell 3 — the Control Room: global widgets, the rating-column resolver that
# turns those controls into a ratings_current column, and the wiring that makes
# every global control broadcast to its subscribers.

CONTROL_ROOM = r"""
# ---- Global controls -------------------------------------------------------
g_rank_view = widgets.Dropdown(
    options=list(PUBLIC_RANKING_VIEWS), value="all_time",
    description="Ranking:", style={"description_width": "70px"},
    layout=widgets.Layout(width="390px"))
g_division = widgets.Dropdown(
    options=[("All", "All divisions")] + [(DIV_SHORT.get(d, d), d) for d in DIVISIONS],
    value="All divisions",
    description="Weight class:", style={"description_width": "90px"},
    layout=widgets.Layout(width="240px"))
g_gender = widgets.ToggleButtons(
    options=[("Both", "both"), ("Men", "M"), ("Women", "F")], value="M",
    description="Roster:", style={"description_width": "70px"})
g_top_n = widgets.IntSlider(
    value=30, min=5, max=100, step=5, description="Show top:",
    continuous_update=False, style={"description_width": "80px"},
    layout=widgets.Layout(width="330px"))
g_min_fights = widgets.IntSlider(
    value=3, min=0, max=20, step=1, description="Min UFC bouts:",
    continuous_update=False, style={"description_width": "110px"},
    layout=widgets.Layout(width="350px"))
GLOBAL_WIDGETS = {
    "rank_view": g_rank_view, "division": g_division, "gender": g_gender,
    "top_n": g_top_n, "min_fights": g_min_fights,
}


def rating_label():
    label = public_rating_label(g_rank_view.value)
    primary = {
        "all_time": "public_legacy_score",
        "prime": "symon_prime_score",
        "current": "mu_whr",
    }[g_rank_view.value]
    resolved = select_public_ranking_column(rc, g_rank_view.value)
    return label if resolved == primary else f"{label} · legacy snapshot fallback"


def selected_rating_col():
    return select_public_ranking_column(rc, g_rank_view.value)


def selected_previous_rating_col():
    if previous_rc is None or previous_rc.empty:
        return None
    return select_public_ranking_column(previous_rc, g_rank_view.value)


def selected_history():
    history = ratings_histories.get(public_history_key(g_rank_view.value), pd.DataFrame())
    if history is not None and not history.empty and "mu_whr" in history.columns:
        return history
    return ratings_history


def selected_stream_col():
    history = selected_history()
    return "mu_whr" if "mu_whr" in history.columns else "mu_canonical"


# ---- Wire each global control to broadcast its key -------------------------
def _make_handler(key):
    def _h(_change):
        broadcast(key)
    return _h


for _k, _w in GLOBAL_WIDGETS.items():
    _observe(_w, _make_handler(_k))

# ---- Render the panel ------------------------------------------------------
_panel_css = (
    f"border:1px solid {THEME['border_strong']};border-radius:10px;"
    f"padding:14px 16px;background:{THEME['surface']};margin-bottom:6px"
)
display(Markdown(
    f"<div style='font-family:{THEME['font']};color:{THEME['text_muted']};"
    f"font-size:0.78em;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;"
    f"margin-bottom:6px'>Control Room &middot; drives every section below</div>"
))
display(widgets.VBox([
    widgets.HBox([g_rank_view, g_gender]),
    widgets.HBox([g_division, g_top_n, g_min_fights]),
], layout=widgets.Layout(border=f"1px solid {THEME['border_strong']}", padding="12px")))
display(Markdown(
    f"<div style='font-family:{THEME['font']};color:{THEME['text_caption']};"
    f"font-size:0.82em;line-height:1.6;margin-top:8px'>"
    f"<b style='color:{THEME['text_2']}'>Ranking</b> is one audited question: "
    f"<b>All-time</b> combines career skill, championship results, and schedule strength; "
    f"<b>Prime</b> is the best fixed 10-year window with at least 13 appearances; "
    f"<b>Current skill</b> is the latest latent WHR skill estimate. All three use the same "
    f"base, method-aware whole-history model; they are alternatives, not stackable bonuses. "
    f"<b style='color:{THEME['text_2']}'>Show top</b>, "
    f"<b>Min UFC bouts</b>, <b>Weight class</b>, and <b>Roster</b> filter the rankings. "
    f"Affected tables and charts refresh instantly.</div>"
))
"""


# ---------------------------------------------------------------------------
# Section cells.

LEADERBOARD = r"""
lb_html = html_box()
_spot_names = sorted(rc["fighter"].dropna().unique().tolist())
_default_spotlight = tuple([n for n in ["Georges St-Pierre", "Jon Jones", "Khabib Nurmagomedov"] if n in _spot_names])


def _build_top_view(df_subset, rating_col, n, min_fights_val, division_val):
    df = df_subset.copy()
    df["rating_periods"] = pd.to_numeric(df.get("rating_periods"), errors="coerce").fillna(0)
    df = df[df["rating_periods"] >= min_fights_val]
    if division_val and division_val != "All divisions":
        # Filter by career division: the class the fighter made their name in.
        # A long-tenured Lightweight who just won the Welterweight belt still
        # shows under Lightweight here. Fall back to recent_division for any
        # fighter whose career label is missing.
        career = df["career_division"] if "career_division" in df.columns else pd.Series(pd.NA, index=df.index)
        recent = df["recent_division"] if "recent_division" in df.columns else pd.Series(pd.NA, index=df.index)
        div_series = career.fillna(recent).fillna("")
        df = df[div_series.eq(division_val)]
    df = df.dropna(subset=[rating_col])
    df = df.sort_values(rating_col, ascending=False).head(n).reset_index(drop=True)
    if df.empty:
        return df
    rating_vals = pd.to_numeric(df[rating_col], errors="coerce")
    return pd.DataFrame({
        "#": [_rank_chip(i) for i in range(1, len(df) + 1)],
        "Fighter": df["fighter"],
        "Rating": rating_vals.round(1),
        "Div": (
            (df["career_division"] if "career_division" in df.columns else pd.Series(pd.NA, index=df.index))
            .fillna(df["recent_division"] if "recent_division" in df.columns else pd.Series("", index=df.index))
            .map(lambda v: DIV_SHORT.get(v, v) if isinstance(v, str) else "")
        ),
        "Last": pd.to_datetime(df["last_event_date"], errors="coerce").dt.date,
        "Fights": df["rating_periods"].astype(int),
    })


def _style_top(lean):
    if lean.empty:
        return None
    rmin, rmax = lean["Rating"].min(), lean["Rating"].max()
    return (
        lean.style.hide(axis="index")
        .bar(subset=["Rating"], color="rgba(56,189,248,0.28)", vmin=rmin, vmax=rmax)
        .format({"Rating": "{:.1f}"})
        .format(lambda s: s, subset=["#"], escape=None)
        .format(lambda s: s, subset=["Fighter"], escape=None)
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Last", "Fights"], **{"color": THEME["text_muted"], "font-size": "0.88em"})
        .set_properties(subset=["Div"], **{"color": THEME["text_2"]})
        .set_properties(subset=["#"], **{"text-align": "center", "padding-right": "4px"})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def draw_leaderboard():
    try:
        col = selected_rating_col()
    except ValueError as exc:
        lb_html.value = msg(f"Invalid selection: {exc}")
        return
    if col is None or col not in rc.columns:
        lb_html.value = msg("No matching rating column in this snapshot.")
        return
    has_gender = "gender" in rc.columns
    men = rc[rc["gender"].eq("M")].copy() if has_gender else rc.copy()
    women = rc[rc["gender"].eq("F")].copy() if has_gender else rc.iloc[0:0].copy()
    parts = [
        f"<div style='font-family:{THEME['font']};color:{THEME['text_2']};font-size:0.95em;margin-bottom:6px'>"
        f"<b style='color:{THEME['text']}'>{rating_label()}</b>"
        f" &middot; min {int(g_min_fights.value)} fights"
        f"{'' if g_division.value == 'All divisions' else ' &middot; ' + DIV_SHORT.get(g_division.value, g_division.value)}</div>"
    ]
    if g_gender.value in ("both", "M"):
        v = _build_top_view(men, col, g_top_n.value, g_min_fights.value, g_division.value)
        styled = _style_top(v)
        parts.append(heading("Men"))
        parts.append(table_html(styled) if styled is not None else msg("no fighters match the current filters"))
    if g_gender.value in ("both", "F"):
        v = _build_top_view(women, col, g_top_n.value, g_min_fights.value, g_division.value)
        styled = _style_top(v)
        parts.append(heading("Women"))
        parts.append(table_html(styled) if styled is not None else msg("no fighters match the current filters"))
    lb_html.value = "".join(parts)


display(lb_html)
draw_leaderboard()
subscribe("leaderboard", draw_leaderboard,
          {"rank_view", "gender", "division", "top_n", "min_fights"})
"""


RANKING_ANATOMY = r"""
anatomy_fw = chart_widget(height=650)


def draw_ranking_anatomy():
    show_fig(anatomy_fw, all_time_score_anatomy_chart(
        rc,
        n=min(20, int(g_top_n.value)),
        min_fights=int(g_min_fights.value),
        gender=g_gender.value,
        division=g_division.value,
    ))


display(anatomy_fw)
display(html_box(note(
    "Bar length is the published All-time total; colour shows the exact weighted contribution "
    "from championships, career skill, and wins over tested contenders. Hover exposes the raw "
    "evidence behind each component. Choose Men or Women because the two pools never fight."
)))
draw_ranking_anatomy()
subscribe("ranking_anatomy", draw_ranking_anatomy,
          {"gender", "division", "top_n", "min_fights"})
"""


EVIDENCE = r"""
evidence_scores_fw = chart_widget(height=520)
evidence_ablation_fw = chart_widget(height=560)


def draw_evidence():
    show_fig(evidence_scores_fw, heldout_scorecard_chart(
        prequential_scores, calibrated=True, segment_type="overall", min_n=200))
    show_fig(evidence_ablation_fw, ablation_forest_chart(
        prequential_paired, calibrated=True, metric="log_loss", min_n=200))


display(evidence_scores_fw)
display(html_box(note(
    "One-step-ahead scores on fights the model had not seen. Probabilities are temperature-calibrated "
    "on strictly earlier events. Row-level sample sizes stay visible because closing odds cover fewer fights.")))
display(evidence_ablation_fw)
display(html_box(note(
    "Each point is a paired challenger-minus-baseline comparison on the same bouts; whiskers are 95% "
    "bootstrap intervals. For log loss, left favors the challenger and right favors the baseline. "
    "Intervals crossing zero remain unresolved.")))
draw_evidence()
register_section("heldout_evidence", draw_evidence)
"""


BENCHMARK = r"""
benchmark_fw = chart_widget(height=720)
benchmark_html = html_box()


def draw_benchmark():
    col = selected_rating_col()
    n = max(15, int(g_top_n.value))
    if col is None or col not in rc.columns:
        show_fig(benchmark_fw, go.Figure())
        benchmark_html.value = msg("No matching rating column in this snapshot.")
        return
    fig = all_time_benchmark_chart(
        rc, fightmatrix_all_time, col,
        min_fights=int(g_min_fights.value), limit=n,
    )
    fig.update_layout(title=f"{rating_label()} vs FightMatrix all-time · engine top {n}")
    show_fig(benchmark_fw, fig)
    audit = all_time_benchmark_table(
        rc, fightmatrix_all_time, col,
        min_fights=int(g_min_fights.value), limit=n,
    )
    matched = int(audit["reference_rank"].notna().sum()) if not audit.empty else 0
    benchmark_html.value = (
        f"<div style='font-family:{THEME['font']};color:{THEME['text_2']};font-size:0.88em;"
        f"line-height:1.55;padding:10px 12px;border-left:3px solid {THEME['accent']};"
        f"background:{THEME['surface']}'>"
        f"Matched <b style='color:{THEME['text']}'>{matched} of {len(audit)}</b> engine leaders. "
        f"This is a <b>sanity check, not a target</b>: the published engine covers UFC, "
        f"PRIDE, WEC, Strikeforce, Affliction, Bellator and RIZIN careers, while "
        f"FightMatrix uses a different source boundary and ranking definition.</div>"
    )


display(benchmark_html)
display(benchmark_fw)
draw_benchmark()
subscribe("all_time_benchmark", draw_benchmark,
          {"rank_view", "top_n", "min_fights"})
"""


TRAJECTORY = r"""
spotlight = widgets.SelectMultiple(
    options=_spot_names, value=_default_spotlight, description="Fighters:",
    rows=7, layout=widgets.Layout(width="420px"), style={"description_width": "70px"})
traj_fw = chart_widget(height=520)
traj_cap = html_box(note("The line is each fighter's rating over time; the shaded band is how confident the "
                         "model is (wider = less certain, e.g. early career or after a layoff). Dots are fights, "
                         "colored by how they ended. Historical charts use the shared base WHR skill path."))


def draw_trajectory():
    names = list(spotlight.value or [])
    if not names:
        show_fig(traj_fw, go.Figure())
        return
    hist = selected_history()
    if hist is None or hist.empty:
        show_fig(traj_fw, go.Figure())
        return
    available = set(hist.get("fighter", pd.Series(dtype=str)))
    names = [n for n in names if n in available]
    if not names:
        show_fig(traj_fw, go.Figure())
        return
    stream_col = selected_stream_col()
    fig = trajectory_chart(hist, all_bouts, names, show_phi_band=True, show_method_markers=True,
                           rating_col=stream_col if stream_col in hist.columns else "mu_canonical")
    fig.update_layout(title="Career rating overlay", xaxis_title="Date", yaxis_title="Rating", height=520)
    show_fig(traj_fw, fig)


display(spotlight)
display(traj_fw)
display(traj_cap)
draw_trajectory()
_observe(spotlight, lambda *_: draw_trajectory())
subscribe("trajectory", draw_trajectory, {"rank_view"})
"""


MOVERS = r"""
_years_list = sorted(pd.to_datetime(all_bouts["event_date"], errors="coerce").dt.year.dropna().astype(int).unique().tolist(), reverse=True)
movers_year = widgets.Dropdown(
    options=_years_list,
    value=(_years_list[0] if _years_list else 2025),
    description="Year:",
    layout=widgets.Layout(width="180px"),
    style={"description_width": "50px"})
movers_fw = chart_widget(height=460)


def draw_movers():
    hist = selected_history()
    if hist is None or hist.empty:
        show_fig(movers_fw, go.Figure())
        return
    # Year-over-year moves are a per-fight story, so every board view uses the
    # same base WHR history rather than treating a career summary as a time path.
    stream_col = selected_stream_col()
    col = stream_col if (stream_col and stream_col in hist.columns) else "mu_canonical"
    if col not in hist.columns:
        show_fig(movers_fw, go.Figure())
        return
    fig = yearly_rating_delta_scatter(
        hist, all_bouts, rating_col=col, year=int(movers_year.value),
        n=max(8, g_top_n.value // 2))
    show_fig(movers_fw, fig)


display(movers_year)
display(movers_fw)
display(html_box(note(
    "The biggest rating movers of the selected year: green bars rose, red fell, "
    "ranked by how much. Driven by <b>Show top</b> (how many of each). Hover any "
    "bar for the individual fights — opponent, result, and per-fight change — "
    "behind the move."
)))
draw_movers()
_observe(movers_year, lambda *_: draw_movers())
subscribe("movers", draw_movers, {"rank_view", "top_n"})
"""


STREAKS = r"""
streak_sort = widgets.Dropdown(
    options=[("Longest", "length"), ("Toughest schedule", "quality"), ("Most title wins", "title_wins")],
    value="length", description="Sort:", style={"description_width": "70px"})
streak_min_len = widgets.IntSlider(value=5, min=2, max=15, step=1, description="Min wins:",
                                   style={"description_width": "70px"})
streak_pick = widgets.Dropdown(options=[], description="Timeline:",
                               layout=widgets.Layout(width="460px"), style={"description_width": "70px"})
streak_search = widgets.Text(value="", placeholder="…or type any fighter", description="Fighter:",
                             layout=widgets.Layout(width="360px"), style={"description_width": "70px"})
streak_html = html_box()
streak_fw = chart_widget(height=420)
_streak_state = {"rows": None}


def _style_streaks(df):
    if df is None or df.empty:
        return None
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


def draw_streak_timeline():
    # The picked streak (from the table dropdown) is the primary timeline. The
    # search box overlays a second fighter on the same axes so the two runs can
    # be compared head to head — picking from the table and typing a fighter
    # are no longer either/or.
    primary = None
    rows = _streak_state.get("rows")
    if rows is not None and not rows.empty and streak_pick.value is not None:
        r = rows.iloc[int(streak_pick.value)]
        primary = {
            "fighter": r["fighter"],
            "start": r["start_date"], "end": r["end_date"], "len": int(r["length"]),
        }

    overlay = None
    q = (streak_search.value or "").strip()
    if q:
        matches = fighter_search(rc, q, limit=1)
        if matches:
            name = matches[0]
            fr = win_streaks(fights, rc, min_len=1)
            fr = fr[fr["fighter"].eq(name)]
            ostart = oend = olen = None
            if not fr.empty:
                top = fr.sort_values("length", ascending=False).iloc[0]
                ostart, oend, olen = top["start_date"], top["end_date"], int(top["length"])
            overlay = {"fighter": name, "start": ostart, "end": oend, "len": olen}

    if primary is None and overlay is not None:
        # No picked row but a search match — promote the search to primary so
        # the chart is never blank when the user typed a fighter.
        primary, overlay = overlay, None

    if primary is None:
        show_fig(streak_fw, go.Figure())
        return

    show_fig(streak_fw, streak_timeline_chart(
        primary["fighter"], ratings_history, fights,
        highlight_start=primary["start"], highlight_end=primary["end"],
        streak_len=primary["len"],
        overlay_fighter=(overlay["fighter"] if overlay else None),
        overlay_highlight_start=(overlay["start"] if overlay else None),
        overlay_highlight_end=(overlay["end"] if overlay else None),
        overlay_streak_len=(overlay["len"] if overlay else None),
    ))


def draw_streaks():
    g = None if g_gender.value == "both" else g_gender.value
    div = None if g_division.value == "All divisions" else g_division.value
    t = win_streaks_table(fights, rc, min_len=streak_min_len.value, n=g_top_n.value,
                          division=div, gender=g, sort_by=streak_sort.value)
    t = t.reset_index(drop=True) if t is not None else None
    _streak_state["rows"] = t
    opts = []
    if t is not None and not t.empty:
        for i, r in t.iterrows():
            sy = pd.to_datetime(r["start_date"], errors="coerce")
            ey = pd.to_datetime(r["end_date"], errors="coerce")
            span = f"{'' if pd.isna(sy) else sy.year}–{'' if pd.isna(ey) else ey.year}"
            opts.append((f"{r['fighter']} — {int(r['length'])} wins ({span})", i))
    streak_pick.options = opts
    streak_pick.index = 0 if opts else None
    styled = _style_streaks(t)
    streak_html.value = table_html(styled) if styled is not None else msg("no streaks match the current filters")
    draw_streak_timeline()


display(widgets.HBox([streak_sort, streak_min_len]))
display(streak_html)
display(heading("Rating timeline — pick a streak or type a fighter"))
display(widgets.HBox([streak_pick, streak_search]))
display(streak_fw)
draw_streaks()
for _w in (streak_sort, streak_min_len):
    _observe(_w, lambda *_: draw_streaks())
_observe(streak_pick, lambda *_: draw_streak_timeline())
_observe(streak_search, lambda *_: draw_streak_timeline())
subscribe("streaks", draw_streaks, {"division", "gender", "top_n"})
"""


PLACEMENT = r"""
plc_scatter = chart_widget(height=560)


def _placement_col():
    try:
        return selected_rating_col() or ("mu_whr" if "mu_whr" in rc.columns else "mu_canonical")
    except ValueError:
        return "mu_whr" if "mu_whr" in rc.columns else "mu_canonical"


def draw_placement():
    col = _placement_col()
    fig = top_fighter_placement_scatter(rc, rating_col=col, n=g_top_n.value, min_fights=g_min_fights.value)
    fig.update_layout(title=f"Résumé vs Rating — {rating_label()} (top {g_top_n.value})")
    show_fig(plc_scatter, fig)


display(plc_scatter)
display(html_box(note("Each dot is a fighter — across is how many UFC bouts they've been rated on (résumé "
                     "depth), up is their rating. Top-right is the holy grail: an elite rating built over a "
                     "long, proven résumé, not a hot 3-fight start. Dots are colored by career division.")))
draw_placement()
subscribe("placement", draw_placement, {"rank_view", "top_n", "min_fights"})
"""


DIVISIONS_SECTION = r"""
# ---- Local controls --------------------------------------------------------
_default_divisions = tuple([d for d in ["Lightweight", "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight", "Featherweight", "Bantamweight", "Flyweight"] if d in DIVISIONS])
divx = widgets.SelectMultiple(
    options=[(DIV_SHORT.get(d, d), d) for d in DIVISIONS],
    value=_default_divisions[:6] if _default_divisions else tuple(list(DIVISIONS)[:6]),
    description="Divisions:", rows=9, layout=widgets.Layout(width="260px"),
    style={"description_width": "70px"})
_years = sorted(pd.to_datetime(all_bouts["event_date"], errors="coerce").dt.year.dropna().astype(int).unique().tolist())
_yr_min, _yr_max = (min(_years), max(_years)) if _years else (2000, 2026)
divx_year_range = widgets.IntRangeSlider(
    value=(max(_yr_min, _yr_max - 10), _yr_max), min=_yr_min, max=_yr_max, step=1,
    description="Years:", continuous_update=False,
    layout=widgets.Layout(width="420px"),
    style={"description_width": "60px"})
divx_index = widgets.ToggleButtons(
    options=[("Score", False), ("Index", True)], value=False, description="Scale:",
    style={"description_width": "60px"})
divx_year_snapshot = widgets.IntSlider(
    value=_yr_max, min=_yr_min, max=_yr_max, step=1, description="Snapshot year:",
    continuous_update=False,
    layout=widgets.Layout(width="380px"),
    style={"description_width": "110px"})

# ---- Output widgets --------------------------------------------------------
divx_timeline = chart_widget(height=540)
divx_snapshot = chart_widget(height=560)
divx_era = chart_widget(height=520)
divx_density = chart_widget(height=380)
divx_entropy = chart_widget(height=620)
divx_method = chart_widget(height=440)


def _divx_stream_col():
    hist = selected_history()
    stream_col = selected_stream_col()
    return stream_col if stream_col in hist.columns else "mu_canonical"


def draw_divx():
    hist = selected_history()
    col = _divx_stream_col()
    selected = list(divx.value or [])
    ymin, ymax = sorted([int(v) for v in divx_year_range.value])

    # ---- Strength over time (year-range, multi-division) -------------------
    if selected:
        fig_tl = division_strength_timeline_chart(
            hist, all_bouts, rating_col=col,
            top_n_per_division=g_top_n.value, divisions=selected,
            year_min=ymin, year_max=ymax, indexed=divx_index.value)
        fig_tl.update_layout(title=f"Base WHR skill — division strength {ymin}-{ymax}")
        show_fig(divx_timeline, fig_tl)
    else:
        show_fig(divx_timeline, go.Figure())

    # ---- Single-year ranking — actual top fighters per class --------------
    snap_year = max(ymin, min(ymax, int(divx_year_snapshot.value)))
    if selected:
        fig_snap = division_year_top_fighters_chart(
            hist, all_bouts, rating_col=col,
            year=snap_year, divisions=selected, top_n=5)
        show_fig(divx_snapshot, fig_snap)
    else:
        show_fig(divx_snapshot, go.Figure())

    # ---- Era heat map (shares the year range) ------------------------------
    era_divs = selected or list(DIVISIONS)
    fig_era = era_heatmap_chart(
        ratings_history, all_bouts, top_n=g_top_n.value,
        divisions=era_divs, year_min=ymin, year_max=ymax)
    fig_era.update_layout(
        title=f"Era strength index — {ymin}-{ymax}",
        coloraxis_colorbar=dict(
            title=dict(text="Strength index", font=dict(color="#cbd5e1")),
            tickfont=dict(color="#cbd5e1")))
    for tr in fig_era.data:
        if hasattr(tr, "colorbar"):
            tr.colorbar = dict(
                title=dict(text="Strength index", font=dict(color="#cbd5e1")),
                tickfont=dict(color="#cbd5e1"))
    show_fig(divx_era, fig_era)

    # ---- Top-100 split by career division ---------------------------------
    board_col = selected_rating_col() or col
    fig_den = top100_division_density_chart(rc, rating_col=board_col, n=100)
    show_fig(divx_density, fig_den)

    # ---- Division parity / crowdedness (entropy) --------------------------
    de = division_entropy.copy()
    if not de.empty and "year" in de.columns:
        de = de[(pd.to_numeric(de["year"], errors="coerce") >= ymin)
                & (pd.to_numeric(de["year"], errors="coerce") <= ymax)]
    show_fig(divx_entropy, division_entropy_chart(de, divisions=selected or list(DIVISIONS)))

    # ---- How fights end over time -----------------------------------------
    show_fig(divx_method, method_mix_timeline_chart(
        all_bouts, divisions=selected or None, year_min=ymin, year_max=ymax))


# ---- Layout ----------------------------------------------------------------
display(html_box(heading("Strength over time")))
display(widgets.HBox([divx, widgets.VBox([divx_year_range, divx_index])]))
display(divx_timeline)
display(html_box(note("Each selected weight class's top-tier strength over the chosen year range. "
                     "Flip to Index to compare how divisions rose and fell regardless of absolute level.")))

display(html_box(heading("Single-year ranking")))
display(divx_year_snapshot)
display(divx_snapshot)
display(html_box(note("Top fighters per class in the snapshot year — read each block as a mini-leaderboard.")))

display(html_box(heading("Era heat map")))
display(divx_era)
display(html_box(note("100 = the deepest division that year; shows which class ruled season by season.")))

display(html_box(heading("Top 100 by career division")))
display(divx_density)
display(html_box(note("How the current top 100 splits across weight classes (career division — where the "
                     "fighter built their résumé).")))

display(html_box(heading("Division parity")))
display(divx_entropy)
display(html_box(note("Crowdedness (top panel) = how bunched the elite of each class is: high means a deep, "
                     "competitive field; low means one fighter towers over a thin division. Bottom panel is "
                     "the class's top-10 average rating. Shares the weight-class and year-range pickers.")))

display(html_box(heading("How fights end")))
display(divx_method)
display(html_box(note("Share of bouts ending by KO/TKO, submission, or decision across the selected years and "
                     "weight classes — are fights finishing more or going to the cards?")))

draw_divx()
for _w in (divx, divx_year_range, divx_index, divx_year_snapshot):
    _observe(_w, lambda *_: draw_divx())
subscribe("divisions", draw_divx, {"rank_view", "top_n"})
"""


DIVISION_LEADERS = r"""
# Standalone: single-division top-15, fully decoupled from the multi-division
# charts above so selecting a class here doesn't trigger those redraws.
divx_leader_pick = widgets.Dropdown(
    options=[(DIV_SHORT.get(d, d), d) for d in DIVISIONS],
    value=("Lightweight" if "Lightweight" in DIVISIONS else (list(DIVISIONS)[0] if DIVISIONS else "Lightweight")),
    description="Division:",
    layout=widgets.Layout(width="210px"),
    style={"description_width": "75px"})
divx_leader_table = html_box()


def draw_division_leaders():
    div = divx_leader_pick.value
    if not div:
        divx_leader_table.value = msg("pick a division")
        return
    rank_col = selected_rating_col()
    if not rank_col or rank_col not in rc.columns:
        rank_col = "mu_canonical"
    d = rc.copy()
    d["_career"] = d.get("career_division", pd.Series(pd.NA, index=d.index))
    d = d[d["_career"].eq(div)].dropna(subset=[rank_col]).copy()
    d = d.sort_values(rank_col, ascending=False).head(15).reset_index(drop=True)
    div_s = DIV_SHORT.get(div, div)
    if d.empty:
        divx_leader_table.value = msg(f"no rated fighters in {div_s}")
    else:
        view = pd.DataFrame({
            "#": [_rank_chip(i) for i in range(1, len(d) + 1)],
            "Fighter": d["fighter"],
            "Rating": pd.to_numeric(d[rank_col], errors="coerce").round(1),
            "Fights": pd.to_numeric(d.get("rating_periods"), errors="coerce").fillna(0).astype(int),
            "Last": pd.to_datetime(d.get("last_event_date"), errors="coerce").dt.date,
            "Now in": d.get("current_division", pd.Series("—", index=d.index)).fillna("—").map(
                lambda v: DIV_SHORT.get(v, v) if isinstance(v, str) else "—"),
        })
        rmin, rmax = view["Rating"].min(), view["Rating"].max()
        styled = (
            view.style.hide(axis="index")
            .bar(subset=["Rating"], color="rgba(56,189,248,0.28)", vmin=rmin, vmax=rmax)
            .format({"Rating": "{:.1f}"})
            .format(lambda s: s, subset=["#"], escape=None)
            .format(lambda s: s, subset=["Fighter"], escape=None)
            .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
            .set_properties(subset=["Fights", "Last", "Now in"], **{"color": THEME["text_muted"]})
            .set_properties(subset=["#"], **{"text-align": "center"})
            .set_table_styles(_BASE_TABLE_STYLES)
        )
        divx_leader_table.value = heading(f"Top 15 — {div_s}") + table_html(styled)


display(divx_leader_pick)
display(divx_leader_table)
display(html_box(note(
    "'Now in' flags when a fighter currently competes in a different class than their career home — e.g. "
    "a title mover. Career home drives division rankings; current class is informational."
)))
draw_division_leaders()
_observe(divx_leader_pick, lambda *_: draw_division_leaders())
subscribe("division_leaders", draw_division_leaders, {"rank_view"})
"""


COMPARE = r"""
_fighter_names = sorted(rc["fighter"].dropna().unique().tolist())
cmp_a = widgets.Dropdown(options=_fighter_names,
                         value="Jon Jones" if "Jon Jones" in _fighter_names else _fighter_names[0],
                         description="Fighter A:", layout=widgets.Layout(width="360px"),
                         style={"description_width": "70px"})
cmp_b = widgets.Dropdown(options=_fighter_names,
                         value="Stipe Miocic" if "Stipe Miocic" in _fighter_names else _fighter_names[1],
                         description="Fighter B:", layout=widgets.Layout(width="360px"),
                         style={"description_width": "70px"})
cmp_html = html_box()
cmp_a_profile = chart_widget(height=300)
cmp_b_profile = chart_widget(height=300)
cmp_a_odds = chart_widget(height=300)
cmp_b_odds = chart_widget(height=300)
cmp_a_strike = chart_widget(height=300)
cmp_b_strike = chart_widget(height=300)
_FONT = '-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif'


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
    sp = ratings.get("prime_score")
    rec_str = f"{rec.get('wins',0)}–{rec.get('losses',0)}"
    if rec.get('draws', 0):
        rec_str += f"–{rec['draws']}"
    if rec.get('no_contests', 0):
        rec_str += f" ({rec['no_contests']} NC)"
    stance = tape.get("stance") or "—"
    reach = tape.get("reach_inches")
    height = tape.get("height_inches")
    return (
        f"<div style='border:1px solid #334155;border-radius:8px;padding:14px 16px;"
        f"background:#1e293b;color:#f1f5f9;font-family:{_FONT}'>"
        f"<div style='font-size:1.18em;font-weight:700;color:#f1f5f9'>{fighter_name}</div>"
        f"<div style='color:#94a3b8;font-size:0.88em;margin-bottom:8px'>{stance}"
        f"{f' &middot; {height}″' if height else ''}{f' &middot; reach {reach}″' if reach else ''}</div>"
        f"<div style='font-size:0.95em;margin:2px 0;color:#cbd5e1'><b style='color:#f1f5f9'>Record:</b> {rec_str}</div>"
        f"<div style='font-size:0.95em;margin:2px 0;color:#cbd5e1'><b style='color:#f1f5f9'>Rating:</b> {mu:.1f} "
        f"<span style='color:#64748b'>(±{phi:.1f}, range {lo:.0f}–{hi:.0f})</span></div>"
        + (f"<div style='font-size:0.95em;margin:2px 0;color:#cbd5e1'><b style='color:#f1f5f9'>Prime (10 yr):</b> {sp:.1f}</div>" if sp else "")
        + f"<div style='color:#64748b;font-size:0.85em;margin-top:6px'>Fights rated: {ratings.get('rating_periods', 0)}</div></div>"
    )


def draw_compare():
    a, b = (cmp_a.value or "").strip(), (cmp_b.value or "").strip()
    if not a or not b or a == b:
        cmp_html.value = msg("pick two different fighters")
        for fw in (cmp_a_profile, cmp_b_profile, cmp_a_odds, cmp_b_odds, cmp_a_strike, cmp_b_strike):
            show_fig(fw, go.Figure())
        return
    # Retrospective only — no head-to-head win probability (that would be a
    # prediction of what might happen). This is a side-by-side of two careers.
    cards = (
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:14px'>"
        f"<div>{_resume_block(a)}</div><div>{_resume_block(b)}</div></div>"
    )
    cmp_html.value = cards
    show_fig(cmp_a_profile, fighter_profile_chart(a, rc))
    show_fig(cmp_b_profile, fighter_profile_chart(b, rc))
    show_fig(cmp_a_odds, fighter_odds_history_chart(a, odds_lines, fights))
    show_fig(cmp_b_odds, fighter_odds_history_chart(b, odds_lines, fights))
    show_fig(cmp_a_strike, striking_profile_chart(rounds, a))
    show_fig(cmp_b_strike, striking_profile_chart(rounds, b))


display(widgets.HBox([cmp_a, cmp_b]))
display(cmp_html)
display(widgets.HBox([cmp_a_profile, cmp_b_profile]))
display(widgets.HBox([cmp_a_strike, cmp_b_strike]))
display(html_box(note("Striking fingerprint: where each fighter's significant strikes land (head/body/leg) and "
                     "from what position (distance/clinch/ground), across their whole career.")))
display(widgets.HBox([cmp_a_odds, cmp_b_odds]))
draw_compare()
_observe(cmp_a, lambda *_: draw_compare())
_observe(cmp_b, lambda *_: draw_compare())
register_section("compare", draw_compare)
"""


RATING_STORY = r"""
# ---- Local controls --------------------------------------------------------
_story_pool = (
    rc.dropna(subset=["symon_career_skill_mass"])
      .nlargest(60, "symon_career_skill_mass")["fighter"].tolist()
    if "symon_career_skill_mass" in rc.columns else sorted(rc["fighter"].dropna().unique())[:60]
)
story_fighter = widgets.Combobox(
    value=_story_pool[0] if _story_pool else "", options=_story_pool,
    description="Fighter:", ensure_option=False,
    layout=widgets.Layout(width="330px"), style={"description_width": "70px"})

story_fw = chart_widget(height=430)
shape_fw = chart_widget(height=560)


def draw_rating_story():
    show_fig(story_fw, career_contribution_chart(ratings_history_whr, story_fighter.value))
    show_fig(shape_fw, career_shape_scatter(rc, n=max(20, g_top_n.value)))


display(story_fighter)
display(story_fw)
display(html_box(note(
    "The score's own receipt. The dashed line is the bar that year — the average rated fighter. "
    "Each bar is what that season added to the career total, and a year below the line adds "
    "nothing rather than subtracting: this measures accumulated superiority, not decline.")))
display(shape_fw)
display(html_box(note(
    "Career mass is exactly <b>active years x mean yearly excess</b>, so every fighter sits on this "
    "plane and the dotted curves join equal scores. Up-and-left is a short, towering peak; "
    "down-and-right is a long stay above the field. Two very different careers can reach the same "
    "number — this is where you see which one you are looking at.")))
draw_rating_story()
_observe(story_fighter, lambda *_: draw_rating_story())
subscribe("career_story", draw_rating_story, {"top_n"})
"""


CONFIDENCE = r"""
unc_fw = chart_widget(height=760)
ladder_fw = chart_widget(height=560)
evidence_fw = chart_widget(height=460)


def draw_confidence():
    show_fig(unc_fw, career_rank_interval_chart(career_mass_uncertainty, n=g_top_n.value))
    show_fig(ladder_fw, career_bar_ladder_chart(CAREER_MASS_FAMILY, n=min(15, g_top_n.value)))
    show_fig(evidence_fw, evidence_vs_rating_chart(rc))


display(unc_fw)
display(html_box(note(
    "This is a Career Skill Mass diagnostic, not a Public Legacy interval. Each bar is where "
    "that diagnostic puts the fighter when the evidence is reweighted "
    "(Dirichlet-weighted events, refit end to end). Overlapping bars mean the gap between two "
    "fighters is not established — read those as a tie, not a ranking. If the chart is empty, "
    "run <code>python build_uncertainty.py data/snapshots/&lt;date&gt;</code>.")))
display(ladder_fw)
display(html_box(note(
    "The bar decides whether the board rewards height or duration. At the field mean almost every "
    "elite year clears it, so the score becomes years x excess; at the 95th percentile only genuinely "
    "dominant seasons count. Flat lines are fighters this choice does not decide.")))
display(evidence_fw)
display(html_box(note(
    "An undefeated record has no interior maximum-likelihood rating, so this chart is the engine's "
    "own audit: the prior carries a fixed number of virtual games per fighter, which is what keeps "
    "a 1-0 fighter from rating like a 20-0 fighter. Pink dots are the unbeaten.")))
draw_confidence()
subscribe("confidence", draw_confidence, {"top_n"})
"""


DOMINANCE = r"""
dom_fw = chart_widget(height=560)


def draw_dominance():
    show_fig(dom_fw, dominance_leaderboard_chart(
        fighter_dominance, rc, n=g_top_n.value, min_wins=max(3, g_min_fights.value)))


display(dom_fw)
display(html_box(note("Ranked by a dominance score — how lopsided their wins are (strike gap, control time, and "
                     "submission attempts, combined). Amber marks the most dominant. <b>Min UFC bouts</b> sets "
                     "the minimum wins.")))
draw_dominance()
subscribe("dominance", draw_dominance, {"top_n", "min_fights"})
"""


LEGACY_PRIME = r"""
lp_fw = chart_widget(height=600)


def draw_legacy_prime():
    show_fig(lp_fw, legacy_vs_prime_scatter(
        rc, n=max(20, g_top_n.value * 2), min_fights=max(8, g_min_fights.value)))


display(lp_fw)
display(html_box(note("Each dot is a fighter: across is their audited 10-year Prime score; up is Career Skill "
                     "Mass. The units differ, so read distance from the dashed trend — not the diagonal. "
                     "Above-trend fighters accumulated more career mass than their Prime predicts; below-trend "
                     "fighters concentrated more of their case in one decade.")))
draw_legacy_prime()
subscribe("legacy_prime", draw_legacy_prime, {"top_n", "min_fights"})
"""


TITLE_LINEAGE = r"""
tl_pick = widgets.Dropdown(
    options=[(DIV_SHORT.get(d, d), d) for d in DIVISIONS],
    value=("Lightweight" if "Lightweight" in DIVISIONS else (list(DIVISIONS)[0] if DIVISIONS else "Lightweight")),
    description="Division:", layout=widgets.Layout(width="220px"), style={"description_width": "75px"})
tl_interim = widgets.Checkbox(value=False, description="Include interim", indent=False)
tl_fw = chart_widget(height=460)


def draw_title_lineage():
    show_fig(tl_fw, title_lineage_chart(
        performance_appearances, division=tl_pick.value, include_interim=tl_interim.value))


display(widgets.HBox([tl_pick, tl_interim]))
display(tl_fw)
display(html_box(note("The belt itself, over time — one continuous track where each colored segment is a champion's "
                     "reign, from winning the title to losing it. The label shows the champion and their title "
                     "defenses (e.g. <b>3D</b>); hover for dates, who they beat, and reign length.")))
draw_title_lineage()
for _w in (tl_pick, tl_interim):
    _observe(_w, lambda *_: draw_title_lineage())
register_section("title_lineage", draw_title_lineage)
"""


MARKET = r"""
mkt_banner = html_box()
mkt_fav = chart_widget(height=400)
mkt_line = chart_widget(height=380)

# Fighters who actually have odds-priced fights, for the per-fighter line chart.
_mkt_resid = performance_appearances if performance_appearances is not None else pd.DataFrame()
if not _mkt_resid.empty and "market_residual" in _mkt_resid.columns:
    _mkt_priced = _mkt_resid.dropna(subset=["market_residual"])
    _mkt_counts = _mkt_priced.groupby("fighter").size().sort_values(ascending=False)
    _mkt_names = _mkt_counts[_mkt_counts >= 3].index.tolist()
else:
    _mkt_names = []
_mkt_default = next((n for n in ["Conor McGregor", "Max Holloway", "Dustin Poirier"] if n in _mkt_names),
                    (_mkt_names[0] if _mkt_names else None))
mkt_fighter = widgets.Dropdown(
    options=_mkt_names or ["(no odds-priced fighters)"],
    value=_mkt_default if _mkt_default else (_mkt_names[0] if _mkt_names else "(no odds-priced fighters)"),
    description="Fighter:", layout=widgets.Layout(width="320px"), style={"description_width": "60px"})


def draw_market():
    summary = odds_coverage_summary(rc, odds_lines, fights)
    if not summary.get("available"):
        mkt_banner.value = msg(summary.get("message", "No odds data in this snapshot."))
    else:
        mkt_banner.value = (
            f"<div style='font-family:{THEME['font']};color:{THEME['text_2']};font-size:0.95em;margin-bottom:6px'>"
            f"<b style='color:{THEME['text']}'>{summary['odds_covered_fights']:,}</b> of "
            f"{summary['total_fights']:,} bouts carry usable market odds "
            f"(<b style='color:{THEME['text']}'>{summary['odds_coverage_rate']:.0%}</b> coverage).</div>")
    show_fig(mkt_fav, favorite_underdog_performance_chart(
        favorite_underdog_performance_table(odds_lines, fights)))
    draw_market_line()


def draw_market_line():
    show_fig(mkt_line, fighter_betting_line_chart(performance_appearances, mkt_fighter.value))


display(mkt_banner)
display(mkt_fav)
display(html_box(note("An external calibration check: realized win rate against the market's no-vig expected "
                     "win rate, grouped by favorite/underdog bucket. Closing odds are not a ranking target.")))
display(mkt_fighter)
display(mkt_line)
display(html_box(note("Each bar is outcome (win = 1, draw = 0.5, loss = 0) minus the fighter's no-vig implied "
                     "probability. Green exceeded that probability; red fell short; amber is the sample average. "
                     "This is neither betting profit nor a rating adjustment.")))
draw_market()
_observe(mkt_fighter, lambda *_: draw_market_line())
register_section("market", draw_market)
"""


INTEGRITY_LEDGER = r"""
intg_fw = chart_widget(height=440)
intg_html = html_box()


def _style_integrity(df):
    if df is None or df.empty:
        return None
    view = df.rename(columns={
        "event_date": "Date", "fighter": "Fighter", "opponent": "Opponent",
        "reason": "Reason", "detail": "Detail", "integrity_weight": "Result weight",
        "discount_pct": "Discount"})
    show = [c for c in [
        "Date", "Fighter", "Opponent", "Reason", "Detail", "Result weight", "Discount"
    ] if c in view.columns]
    return (
        view[show].style.hide(axis="index")
        .format({"Result weight": "{:.2f}", "Discount": "{:.0f}%"}, na_rep="—")
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Reason"], **{"color": THEME["accent"]})
        .set_properties(subset=["Discount"], **{"color": THEME["negative"]})
        .set_properties(subset=["Detail"], **{"color": THEME["text_muted"], "font-size": "0.88em"})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def _integrity_rows(n=None):
    return integrity_ledger_table(
        integrity_appearances,
        integrity_ledger=integrity_ledger,
        n=n,
    )


def draw_integrity():
    all_rows = _integrity_rows(n=None)
    reason_counts = all_rows["reason"].value_counts() if "reason" in all_rows.columns else pd.Series(dtype=int)
    fighters_flagged = all_rows["fighter"].nunique() if "fighter" in all_rows.columns else 0
    modern_board = {"fighter", "integrity_cost"}.issubset(integrity_discounted_board.columns)
    source = (
        "explicit policy board on base WHR points"
        if modern_board
        else "legacy snapshot fallback · recorded result-weight flags only"
    )
    strip = (
        f"<div style='font-family:{THEME['font']};color:{THEME['text_2']};font-size:0.9em;line-height:1.6;margin-bottom:8px'>"
        f"<b style='color:{THEME['text']}'>{source}</b><br>"
        f"<b style='color:{THEME['accent']}'>{len(all_rows):,}</b> flagged policy entries across "
        f"<b style='color:{THEME['accent']}'>{fighters_flagged:,}</b> fighters · "
        f"PED {int(reason_counts.get('PED-confirmed win', 0)):,} · "
        f"DQ {int(reason_counts.get('Disqualification win', 0)):,} · "
        f"missed weight {int(reason_counts.get('Missed-weight win', 0)):,}.</div>"
    )
    show_fig(intg_fw, integrity_impact_chart(
        integrity_appearances,
        integrity_discounted_board=integrity_discounted_board,
        n=12,
    ))
    styled = _style_integrity(_integrity_rows(n=g_top_n.value))
    intg_html.value = strip + (
        (heading("Flagged results and stated discounts") + table_html(styled))
        if styled is not None
        else msg("no results are flagged by this policy in the snapshot")
    )


display(intg_fw)
display(intg_html)
display(html_box(note(
    "This is an explicit judgement policy, not evidence of better prediction. The modern board debits "
    "base WHR points only; Career Skill Mass and the default rankings above are unchanged. The ledger "
    "is the bout-level receipt. Older snapshots show their recorded result-weight flags without "
    "inferring a rating-point debit."
)))
draw_integrity()
subscribe("integrity_ledger", draw_integrity, {"top_n"})
"""


CELLS = [
    md("""
# Symon UFC Rank Engine — Interactive Dashboard

The **Control Room** picks one ranking question — All-time, Prime, or
Current skill — plus weight class and board depth. The opening board defaults
to **All-time**, the engine's career-accomplishment view. A score receipt then
explains the ranking, followed by held-out predictive scores and paired
intervals, including unresolved results.

> Run the cells top to bottom once, then drive everything from the top. View
> toggles update instantly; the public notebook is read-only over built artifacts.
"""),
    code(DATA_LOAD),
    code(RUNTIME),
    md("## 🎛️ Control Room"),
    code(CONTROL_ROOM),
    md("""
## The Rankings

The pound-for-pound board for the single **Ranking** selected above. **All-time**
is Public Legacy Score (career skill, championship results, and contender résumé);
**Prime** is the fixed 10-year/13-appearance window; **Current skill** is the
latest base WHR estimate.
Division, last fight, and rated-bout count keep short or stale résumés visible.
"""),
    code(LEADERBOARD),
    md("""
## Why the All-time leaders rank here

The leaderboard gives the order; this score receipt explains it. Every bar
reconstructs the published All-time total from the three stated terms, while
hover text keeps the underlying title, career-year, and contender-win evidence
visible. The chart follows the roster, division, depth, and evidence controls.
"""),
    code(RANKING_ANATOMY),
    md("""
## Does the rating model hold up?

The engine is judged one fight at a time before seeing the result. The first
chart compares held-out forecast quality; the second removes or swaps one
mechanism at a time on identical bouts. That separates measured support from a
good story: intervals crossing zero stay **unresolved**, and comparisons that
favor the alternative remain visible rather than being tuned away here.
"""),
    code(EVIDENCE),
    md("""
## Career Skill Mass stability (diagnostic)

These intervals apply to the Career Skill Mass diagnostic, not the published
Public Legacy ranking. Every fighter is re-ranked after whole events are
reweighted and the model is refit. The charts below show how sensitive that
diagnostic is to the evidence, the yearly bar, and the number of bouts.
"""),
    code(CONFIDENCE),
    md("""
## Career skill diagnostic receipt

Career skill mass is a sum of yearly excess over the field, so it decomposes
exactly into how long a fighter stayed above the field and how far above it they
were. Pick a fighter for their own receipt, then read the whole top of the board
on those two axes.
"""),
    code(RATING_STORY),
    md("""
## Résumé vs Rating

Who's the real deal vs the hot start. Each fighter plotted by résumé depth (UFC
bouts rated) against rating, colored by their career division. Top-right is the
holy grail — an elite rating built over a long, proven résumé. Driven by the
**Ranking** choice, **Show top**, and **Min UFC bouts**.
"""),
    code(PLACEMENT),
    md("""
## Most Dominant

Highest-rated isn't always most dominant. This ranks fighters by how thoroughly
they win — strike differential, control time, and submission attempts blended
into one per-fight dominance score. Driven by **Show top** and **Min UFC bouts**.
"""),
    code(DOMINANCE),
    md("""
## Career Skill Mass vs Prime

Career skill mass and best-decade skill answer different questions. Fighters
far from the trend line reveal longevity beyond their best decade, or a Prime
that outweighs the rest of the career. The line is a trend, not equal units.
"""),
    code(LEGACY_PRIME),
    md("""
## Career Arcs

Overlay any set of fighters and watch their ratings rise and fall fight by fight
— who peaked highest, who stayed at the top longest, who fell off. The line
always shows the shared base WHR skill path; summary rankings are not treated as
if they were per-fight time series.
"""),
    code(TRAJECTORY),
    md("""
## Risers & Fallers

Who moved — and by how much. Pick a year to see every fighter's cumulative
rating change for that season. Dot above zero = rose, below = fell. Hover
for the individual fights behind the move.
"""),
    code(MOVERS),
    md("""
## Win Streaks

The longest unbeaten runs in the books, filtered by **Weight class** / **Roster**
and ranked by your **Sort** (length, toughness of the schedule, or title wins).
Pick a run for the timeline — and *type any fighter* to overlay that fighter's
own streak on top, so you can compare two runs head to head on the same axes.
"""),
    code(STREAKS),
    md("""
## Weight Classes

Pick weight classes and a year range to drive the strength-over-time chart,
the single-year ranking, the era heat map, and the top-100 share. Historical
panels use base WHR skill; the current top-100 split uses the selected Ranking.
"""),
    code(DIVISIONS_SECTION),
    md("""
## Division Leaders

Pick a class to see its top 15 right now. **Now in** flags fighters whose
current weight class differs from their career home — title movers.
"""),
    code(DIVISION_LEADERS),
    md("""
## Title Lineage

Pick a division to trace its belt through time. The belt runs left to right as a
single track, each segment a champion's reign — so you can see the title pass
from hand to hand, who ruled longest, and how many times they defended it.
Toggle interim titles on or off.
"""),
    code(TITLE_LINEAGE),
    md("""
## Tale of the Tape

Pick two fighters for a side-by-side of their careers: résumés, rating profiles,
striking fingerprints, and how the betting market saw each of them over time.
This compares what each fighter *did* — it does not predict a hypothetical bout.
"""),
    code(COMPARE),
    md("""
## Integrity Policy View

This separate, explicit judgement view applies published fixed debits to base
WHR points for PED-confirmed, disqualification, and missed-weight wins. It does
not alter **Career Skill Mass** or the default rankings above, and it is not
presented as a predictive improvement. The ledger is the per-result receipt.
"""),
    code(INTEGRITY_LEDGER),
    md("""
## Results vs the Market

Closing odds are an external forecasting benchmark, not the definition of a
fighter's rank. This section shows coverage, whether favorites win as often as
their no-vig probabilities imply, and each fighter's realized result minus that
probability. The residual is not betting profit and is not a rating bonus.
"""),
    code(MARKET),
    md("""
## Appendix: Ranking Sanity Check

For an anomalous board, compare the selected engine ranking with FightMatrix's
all-time absolute list. Long connectors expose names worth investigating. This
does not force agreement: FightMatrix covers whole MMA careers while the
published whole-sport engine uses a different source boundary and ranking definition.
"""),
    code(BENCHMARK),
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


def write(target: Path | None = None) -> Path:
    """Write the notebook, and be the only thing that decides how.

    ``refresh.py`` used to hold its own copy of this line. Both spelled the
    encoding differently from whatever last wrote the checked-in file, so every
    rebuild rewrote 69 lines that had not changed -- em dashes escaped to
    ``\u2014`` and back. ``ensure_ascii=False`` keeps the UTF-8 the document is
    already written in, so a rebuild with no content change produces no diff.
    """
    target = Path(__file__).resolve().parent / "notebook.ipynb" if target is None else Path(target)
    target.write_text(
        json.dumps(build(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target


if __name__ == "__main__":
    written = write()
    print(f"wrote {written} ({written.stat().st_size} bytes)")
