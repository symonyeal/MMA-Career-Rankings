"""Generate the interactive rankings dashboard notebook.

The notebook is read-only over build-time artifacts in ``data/snapshots/<date>/``.
Its defining feature is a single **Control Room** at the top: a row of global
controls (scoring method, time window, prime window, division, gender, top-N,
min-fights) that every section subscribes to. Changing a control re-draws every
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

import pandas as pd
import plotly.graph_objects as go
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
    PUBLIC_RATING_LENSES,
    PUBLIC_TIME_VIEWS,
    SCORING_METHODS,
    calibration_residuals_chart,
    division_entropy_chart,
    division_strength_timeline_chart,
    division_year_snapshot_chart,
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
    prime_window_column_names,
    n_year_prime_scores,
    performance_factor_audit_table,
    public_history_key,
    public_rating_label,
    public_rating_stream,
    rank_movement_chart,
    rank_delta_table,
    recent_division_by_fighter,
    select_modular_rating_column,
    select_public_rating_column,
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
calibration_residuals = SNAP.get("calibration_residuals", pd.DataFrame())
sleeve_attribution = SNAP.get("sleeve_attribution", pd.DataFrame())
division_entropy = SNAP.get("division_entropy", pd.DataFrame())
division_resume = SNAP.get("division_resume", pd.DataFrame())
performance_appearances = SNAP.get("performance_appearances", pd.DataFrame())
integrity_appearances = SNAP.get("integrity_appearances", pd.DataFrame())
fightmatrix_rankings = SNAP.get("fightmatrix_rankings", pd.DataFrame())
odds_lines = SNAP.get("odds_lines", pd.DataFrame())
ratings_history = SNAP.get("ratings_history", pd.DataFrame())
ratings_histories = {
    "ratings_history": ratings_history,
    "ratings_history_method_integrity": SNAP.get("ratings_history_method_integrity", pd.DataFrame()),
    "ratings_history_method_performance": SNAP.get("ratings_history_method_performance", pd.DataFrame()),
    "ratings_history_method_integrity_performance": SNAP.get("ratings_history_method_integrity_performance", pd.DataFrame()),
}
previous_fights = PREV.get("fights", pd.DataFrame())
previous_ratings_history = PREV.get("ratings_history", pd.DataFrame())
previous_ratings_histories = {
    "ratings_history": previous_ratings_history,
    "ratings_history_method_integrity": PREV.get("ratings_history_method_integrity", pd.DataFrame()),
    "ratings_history_method_performance": PREV.get("ratings_history_method_performance", pd.DataFrame()),
    "ratings_history_method_integrity_performance": PREV.get("ratings_history_method_integrity_performance", pd.DataFrame()),
}
fighter_dominance = SNAP.get("fighter_dominance", pd.DataFrame())
ped_confirmed_bouts = SNAP.get("ped_confirmed_bouts", pd.DataFrame())
crossorg_fights = SNAP.get("crossorg_fights", pd.DataFrame())
previous_crossorg_fights = PREV.get("crossorg_fights", pd.DataFrame())

_whr_path = SNAPSHOT_DIR / "ratings_history_whr.parquet"
ratings_history_whr = pd.read_parquet(_whr_path) if _whr_path.exists() else pd.DataFrame()
ratings_histories["ratings_history_whr"] = ratings_history_whr
all_bouts = pd.concat([fights, crossorg_fights], ignore_index=True, sort=False) if not crossorg_fights.empty else fights
previous_all_bouts = (
    pd.concat([previous_fights, previous_crossorg_fights], ignore_index=True, sort=False)
    if not previous_crossorg_fights.empty
    else previous_fights
)

_prev_whr_path = PREVIOUS_SNAPSHOT_DIR / "ratings_history_whr.parquet" if PREVIOUS_SNAPSHOT_DIR else None
previous_ratings_history_whr = (
    pd.read_parquet(_prev_whr_path)
    if _prev_whr_path is not None and _prev_whr_path.exists()
    else pd.DataFrame()
)
previous_ratings_histories["ratings_history_whr"] = previous_ratings_history_whr

display(Markdown(
    f"<div style='color:#cbd5e1;font-size:0.95em;"
    f"font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",system-ui,sans-serif'>"
    f"<b style='color:#f1f5f9'>Snapshot</b> <code>{SNAPSHOT_DIR.name}</code> &middot; "
    f"<b style='color:#f1f5f9'>{len(fights):,}</b> UFC bouts &middot; "
    f"<b style='color:#f1f5f9'>{len(crossorg_fights):,}</b> cross-org bouts &middot; "
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
SUBSCRIBERS = []   # list of (name, draw_fn, keys:set)


def subscribe(name, fn, keys):
    global SUBSCRIBERS
    SUBSCRIBERS = [s for s in SUBSCRIBERS if s[0] != name]
    SUBSCRIBERS.append((name, fn, set(keys)))


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
g_lens = widgets.Dropdown(
    options=list(PUBLIC_RATING_LENSES), value="complete",
    description="Scoring:", style={"description_width": "70px"},
    layout=widgets.Layout(width="220px"))
g_time = widgets.Dropdown(
    options=list(PUBLIC_TIME_VIEWS), value="current",
    description="Window:", style={"description_width": "70px"},
    layout=widgets.Layout(width="200px"))
g_division = widgets.Dropdown(
    options=["All divisions"] + list(DIVISIONS), value="All divisions",
    description="Division:", style={"description_width": "70px"},
    layout=widgets.Layout(width="300px"))
g_gender = widgets.ToggleButtons(
    options=[("Both", "both"), ("Men", "M"), ("Women", "F")], value="both",
    description="Gender:", style={"description_width": "70px"})
g_top_n = widgets.IntSlider(
    value=25, min=5, max=100, step=5, description="Top N:",
    continuous_update=False, style={"description_width": "70px"},
    layout=widgets.Layout(width="320px"))
g_min_fights = widgets.IntSlider(
    value=3, min=0, max=20, step=1, description="Min fights:",
    continuous_update=False, style={"description_width": "80px"},
    layout=widgets.Layout(width="320px"))
g_prime_years = widgets.IntSlider(
    value=10, min=6, max=15, step=1, description="Prime yrs:",
    continuous_update=False, style={"description_width": "80px"},
    layout=widgets.Layout(width="320px"))
g_prime_min = widgets.IntSlider(
    value=13, min=5, max=30, step=1, description="Prime min:",
    continuous_update=False, style={"description_width": "80px"},
    layout=widgets.Layout(width="320px"))

GLOBAL_WIDGETS = {
    "lens": g_lens, "time": g_time, "division": g_division, "gender": g_gender,
    "top_n": g_top_n, "min_fights": g_min_fights,
    "prime_years": g_prime_years, "prime_min": g_prime_min,
}

_prime_cache = {}


def _prime_mu_col(stream):
    return f"mu_{stream}"


def rating_label():
    lens_label = dict(PUBLIC_RATING_LENSES).get(g_lens.value, g_lens.value)
    if g_time.value == "sustained_peak":
        return f"{int(g_prime_years.value)}-Yr Prime {lens_label}"
    if g_time.value == "five_year_peak":
        return f"5-Yr Peak {lens_label}"
    return public_rating_label(g_lens.value, g_time.value)


def _ensure_prime_column(frame, histories, canonical_history, bout_frame, *, cache_label):
    years = int(g_prime_years.value)
    min_req = int(g_prime_min.value)
    stream = public_rating_stream(g_lens.value)
    raw_col, headline_col = prime_window_column_names(stream, years, min_req)
    if headline_col in frame.columns:
        return headline_col
    if raw_col in frame.columns:
        return raw_col
    hist = histories.get(public_history_key(g_lens.value), pd.DataFrame())
    mu_col = _prime_mu_col(stream)
    if (
        frame is None or frame.empty
        or hist is None or hist.empty
        or canonical_history is None or canonical_history.empty
        or bout_frame is None or bout_frame.empty
        or mu_col not in hist.columns
    ):
        return None
    key = (cache_label, g_lens.value, years, min_req)
    if key not in _prime_cache:
        _prime_cache[key] = n_year_prime_scores(
            hist, canonical_history, bout_frame,
            mu_col=mu_col, stream=stream, years=years, min_fights=min_req)
    scores = _prime_cache[key]
    if scores is None or scores.empty:
        return None
    mapped = scores.set_index("fighter")
    for col in (raw_col, headline_col):
        if col in mapped.columns:
            frame[col] = frame["fighter"].map(mapped[col])
    return headline_col if headline_col in frame.columns else raw_col if raw_col in frame.columns else None


def selected_rating_col():
    if (
        g_time.value == "sustained_peak"
        and (int(g_prime_years.value) != 10 or int(g_prime_min.value) != 13)
    ):
        return _ensure_prime_column(rc, ratings_histories, ratings_history, all_bouts, cache_label="current")
    return select_public_rating_column(rc, g_lens.value, g_time.value)


def selected_previous_rating_col():
    if previous_rc is None or previous_rc.empty:
        return None
    if (
        g_time.value == "sustained_peak"
        and (int(g_prime_years.value) != 10 or int(g_prime_min.value) != 13)
    ):
        return _ensure_prime_column(previous_rc, previous_ratings_histories,
                                    previous_ratings_history, previous_all_bouts, cache_label="previous")
    return select_public_rating_column(previous_rc, g_lens.value, g_time.value)


def selected_history():
    return ratings_histories.get(public_history_key(g_lens.value), ratings_history)


def selected_stream_col():
    col = selected_rating_col()
    if col and "_mu_" in col and (col.startswith("sustained_peak") or col.startswith("five_year_peak") or col.startswith("prime_")):
        return "mu_" + col.split("_mu_", 1)[1]
    return col


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
    widgets.HBox([g_lens, g_time, g_gender]),
    widgets.HBox([g_division, g_top_n, g_min_fights]),
    widgets.HBox([g_prime_years, g_prime_min]),
], layout=widgets.Layout(border=f"1px solid {THEME['border_strong']}", padding="12px")))
display(Markdown(
    f"<div style='font-family:{THEME['font']};color:{THEME['text_caption']};"
    f"font-size:0.82em;line-height:1.6;margin-top:8px'>"
    f"<b style='color:{THEME['text_2']}'>Scoring</b> picks the ranking lens — "
    f"<b>Wins</b> (result only), <b>Finishes</b> (how it ended), <b>Clean</b> "
    f"(de-weights tainted wins), <b>Strength</b> (opponent + market context), "
    f"<b>Complete</b> (all context), <b>Legacy</b> (whole-history WHR). "
    f"<b style='color:{THEME['text_2']}'>Window</b>: <b>Now</b> = current form, "
    f"<b>Peak</b> = best fixed 5-year burst, <b>Prime</b> = a sustained N-year run "
    f"set by the <b>Prime</b> sliders. <b style='color:{THEME['text_2']}'>Top N</b>, "
    f"<b>Min fights</b>, <b>Division</b>, and <b>Gender</b> filter the leaderboards "
    f"and placement views. Change anything and the dependent sections refresh.</div>"
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
        "vs Wins": (rating_vals - baseline_vals).round(1),
        "Division": df.get("recent_division").fillna(df.get("primary_division", "")),
        "Last": pd.to_datetime(df["last_event_date"], errors="coerce").dt.date,
        "Fights": df["rating_periods"].astype(int),
    })


def _style_top(lean):
    if lean.empty:
        return None
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
        lean.style.hide(axis="index")
        .bar(subset=["Rating"], color="rgba(56,189,248,0.28)", vmin=rmin, vmax=rmax)
        .map(delta_color, subset=["vs Wins"])
        .format({"Rating": "{:.1f}", "vs Wins": "{:+.1f}"})
        .format(lambda s: s, subset=["#"], escape=None)
        .format(lambda s: s, subset=["Fighter"], escape=None)
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Last", "Fights"], **{"color": THEME["text_muted"], "font-size": "0.88em"})
        .set_properties(subset=["Division"], **{"color": THEME["text_2"]})
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
        f"{'' if g_division.value == 'All divisions' else ' &middot; ' + g_division.value}</div>"
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
          {"lens", "time", "prime_years", "prime_min", "gender", "division", "top_n", "min_fights"})
"""


TRAJECTORY = r"""
spotlight = widgets.SelectMultiple(
    options=_spot_names, value=_default_spotlight, description="Fighters:",
    rows=7, layout=widgets.Layout(width="420px"), style={"description_width": "70px"})
traj_fw = chart_widget(height=520)
traj_cap = html_box(note("Shaded band = 1σ rating uncertainty (±φ); dots colored by finish method. "
                         "The rating stream follows the Scoring lens in the Control Room."))


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
subscribe("trajectory", draw_trajectory, {"lens", "time", "prime_years", "prime_min"})
"""


MOVERS = r"""
mov_html = html_box()
mov_fw = chart_widget(height=460)


def draw_movers():
    try:
        col = selected_rating_col()
    except ValueError as exc:
        mov_html.value = msg(f"Invalid selection: {exc}")
        show_fig(mov_fw, go.Figure())
        return
    if not col:
        mov_html.value = msg("no matching rating view")
        show_fig(mov_fw, go.Figure())
        return
    prev_col = selected_previous_rating_col()
    if not prev_col or prev_col != col:
        mov_html.value = msg("no matching prior-snapshot view for this selection")
        show_fig(mov_fw, go.Figure())
        return
    mov_html.value = ""
    fig = rank_movement_chart(previous_rc, rc, rating_col=col, top_k=50,
                              n=g_top_n.value, min_fights=g_min_fights.value)
    fig.update_layout(title=f"Biggest movers — {rating_label()}")
    show_fig(mov_fw, fig)


display(mov_html)
display(mov_fw)
draw_movers()
subscribe("movers", draw_movers, {"lens", "time", "prime_years", "prime_min", "min_fights", "top_n"})
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
    q = (streak_search.value or "").strip()
    if q:
        matches = fighter_search(rc, q, limit=1)
        if not matches:
            show_fig(streak_fw, go.Figure())
            return
        name = matches[0]
        fr = win_streaks(fights, rc, min_len=1)
        fr = fr[fr["fighter"].eq(name)]
        hs = he = ln = None
        if not fr.empty:
            top = fr.sort_values("length", ascending=False).iloc[0]
            hs, he, ln = top["start_date"], top["end_date"], int(top["length"])
        show_fig(streak_fw, streak_timeline_chart(name, ratings_history, fights,
                 highlight_start=hs, highlight_end=he, streak_len=ln))
        return
    rows = _streak_state.get("rows")
    if rows is None or rows.empty or streak_pick.value is None:
        show_fig(streak_fw, go.Figure())
        return
    r = rows.iloc[int(streak_pick.value)]
    show_fig(streak_fw, streak_timeline_chart(r["fighter"], ratings_history, fights,
             highlight_start=r["start_date"], highlight_end=r["end_date"], streak_len=int(r["length"])))


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
plc_scatter = chart_widget(height=520)
plc_density = chart_widget(height=360)


def _placement_col():
    try:
        return selected_rating_col() or "sustained_peak_headline_mu_whr"
    except ValueError:
        return "sustained_peak_headline_mu_whr"


def draw_placement():
    col = _placement_col()
    fig1 = top_fighter_placement_scatter(rc, rating_col=col, n=g_top_n.value, min_fights=g_min_fights.value)
    fig1.update_layout(title=f"Placement — {rating_label()} (top {g_top_n.value})")
    show_fig(plc_scatter, fig1)
    fig2 = top100_division_density_chart(rc, rating_col=col, n=100)
    show_fig(plc_density, fig2)


display(plc_scatter)
display(html_box(note("Each point is a ranked fighter: x = number of rated fights, y = rating. "
                     "Larger, higher points are the strongest deep-resume fighters.")))
display(plc_density)
display(html_box(note("Share of the current top-100 occupied by each division.")))
draw_placement()
subscribe("placement", draw_placement, {"lens", "time", "prime_years", "prime_min", "top_n", "min_fights"})
"""


DIVISIONS_SECTION = r"""
_default_divisions = tuple([d for d in ["Lightweight", "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight", "Featherweight", "Bantamweight", "Flyweight"] if d in DIVISIONS])
divx = widgets.SelectMultiple(
    options=list(DIVISIONS),
    value=_default_divisions[:6] if _default_divisions else tuple(list(DIVISIONS)[:6]),
    description="Divisions:", rows=9, layout=widgets.Layout(width="340px"),
    style={"description_width": "70px"})
divx_index = widgets.ToggleButtons(options=[("Score", False), ("Index", True)], value=False, description="Scale:",
                                   style={"description_width": "60px"})
_years = sorted(pd.to_datetime(all_bouts["event_date"], errors="coerce").dt.year.dropna().astype(int).unique().tolist())
divx_year = (widgets.IntSlider(value=max(_years), min=min(_years), max=max(_years), step=1, description="Year:",
                               continuous_update=False, style={"description_width": "60px"})
             if _years else widgets.IntSlider(value=2026, min=2000, max=2026, description="Year:"))
divx_timeline = chart_widget(height=460)
divx_snapshot = chart_widget(height=440)
divx_table = html_box()
divx_entropy = chart_widget(height=360)


def _divx_stream_col():
    hist = selected_history()
    stream_col = selected_stream_col()
    return stream_col if stream_col in hist.columns else "mu_canonical"


def draw_divx():
    hist = selected_history()
    col = _divx_stream_col()
    selected = list(divx.value or [])
    if not selected:
        divx_table.value = msg("select at least one division")
        show_fig(divx_timeline, go.Figure())
        show_fig(divx_snapshot, go.Figure())
        show_fig(divx_entropy, go.Figure())
        return
    fig_tl = division_strength_timeline_chart(hist, all_bouts, rating_col=col,
             top_n_per_division=g_top_n.value, divisions=selected,
             year_min=divx_year.min, year_max=divx_year.max, indexed=divx_index.value)
    fig_tl.update_layout(title=f"{rating_label()} — division strength over time")
    show_fig(divx_timeline, fig_tl)
    fig_snap = division_year_snapshot_chart(hist, all_bouts, rating_col=col,
               year=divx_year.value, top_n_per_division=g_top_n.value, divisions=selected)
    fig_snap.update_layout(title=f"Division ranking — {divx_year.value}")
    show_fig(divx_snapshot, fig_snap)

    recent = recent_division_by_fighter(fights)
    d = rc.merge(recent, on="fighter", how="left")
    d["division"] = d["division"].fillna(d.get("primary_division"))
    d = d[d["division"].isin(selected)]
    rank_col = selected_rating_col()
    if rank_col not in d.columns:
        rank_col = "mu_canonical"
    d = d.dropna(subset=[rank_col]).sort_values(["division", rank_col], ascending=[True, False])
    d = d.groupby("division", as_index=False).head(8).reset_index(drop=True)
    if d.empty:
        divx_table.value = msg("no rated fighters in the selected divisions")
    else:
        view = pd.DataFrame({
            "#": d.groupby("division").cumcount().add(1).map(_rank_chip),
            "Division": d["division"],
            "Fighter": d["fighter"],
            "Rating": pd.to_numeric(d[rank_col], errors="coerce").round(1),
            "Fights": pd.to_numeric(d.get("rating_periods"), errors="coerce").fillna(0).astype(int),
            "Last": pd.to_datetime(d.get("last_event_date"), errors="coerce").dt.date,
        })
        rmin, rmax = view["Rating"].min(), view["Rating"].max()
        styled = (
            view.style.hide(axis="index")
            .bar(subset=["Rating"], color="rgba(56,189,248,0.28)", vmin=rmin, vmax=rmax)
            .format({"Rating": "{:.1f}"})
            .format(lambda s: s, subset=["#"], escape=None)
            .format(lambda s: s, subset=["Fighter"], escape=None)
            .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
            .set_properties(subset=["Division"], **{"color": THEME["text_2"]})
            .set_properties(subset=["Fights", "Last"], **{"color": THEME["text_muted"]})
            .set_properties(subset=["#"], **{"text-align": "center"})
            .set_table_styles(_BASE_TABLE_STYLES)
        )
        divx_table.value = heading("Current leaders by selected division") + table_html(styled)
    if division_entropy is not None and not division_entropy.empty:
        show_fig(divx_entropy, division_entropy_chart(division_entropy, divisions=selected))
    else:
        show_fig(divx_entropy, go.Figure())


display(widgets.HBox([divx, widgets.VBox([divx_year, divx_index])]))
display(divx_timeline)
display(html_box(note("Top-N average rating per division over time. Switch Scale to Index to compare shapes "
                     "rather than absolute level.")))
display(divx_snapshot)
display(divx_table)
display(divx_entropy)
display(html_box(note("Crowdedness: how tightly packed the top of each division is (higher = more contenders "
                     "bunched together).")))
draw_divx()
for _w in (divx, divx_year, divx_index):
    _observe(_w, lambda *_: draw_divx())
subscribe("divisions", draw_divx, {"lens", "time", "prime_years", "prime_min", "top_n"})
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
    sp = ratings.get("sustained_peak_mu_canonical")
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
        + (f"<div style='font-size:0.95em;margin:2px 0;color:#cbd5e1'><b style='color:#f1f5f9'>Career peak:</b> {sp:.1f}</div>" if sp else "")
        + f"<div style='color:#64748b;font-size:0.85em;margin-top:6px'>Fights rated: {ratings.get('rating_periods', 0)}</div></div>"
    )


def draw_compare():
    a, b = (cmp_a.value or "").strip(), (cmp_b.value or "").strip()
    if not a or not b or a == b:
        cmp_html.value = msg("pick two different fighters")
        for fw in (cmp_a_profile, cmp_b_profile, cmp_a_odds, cmp_b_odds):
            show_fig(fw, go.Figure())
        return
    pred = h2h_prediction(a, b, rc)
    if pred.get("error"):
        cmp_html.value = msg(pred["error"])
        return
    pa = pred["p_a_wins"] * 100
    pb = pred["p_b_wins"] * 100
    qual = pred["matchup_quality_0_to_1"]
    prob_bar = (
        f"<div style='margin:8px 0 14px;font-family:{_FONT}'>"
        f"<div style='display:flex;font-size:0.95em;color:#cbd5e1;margin-bottom:4px'>"
        f"<div style='flex:1'><b style='color:#38bdf8'>{a}</b> &mdash; {pa:.1f}%</div>"
        f"<div style='text-align:right'>{pb:.1f}% &mdash; <b style='color:#a78bfa'>{b}</b></div></div>"
        f"<div style='height:22px;border-radius:11px;overflow:hidden;background:#1e293b;display:flex;border:1px solid #334155'>"
        f"<div style='width:{pa:.1f}%;background:#38bdf8'></div>"
        f"<div style='width:{pb:.1f}%;background:#a78bfa'></div></div>"
        f"<div style='color:#94a3b8;font-size:0.88em;margin-top:6px'>"
        f"Closeness: <b style='color:#f1f5f9'>{qual:.2f}</b> "
        f"<span style='color:#64748b'>(1 = coin-flip, 0 = lopsided)</span></div></div>"
    )
    cards = (
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:14px'>"
        f"<div>{_resume_block(a)}</div><div>{_resume_block(b)}</div></div>"
    )
    cmp_html.value = prob_bar + cards
    show_fig(cmp_a_profile, fighter_profile_chart(a, rc))
    show_fig(cmp_b_profile, fighter_profile_chart(b, rc))
    show_fig(cmp_a_odds, fighter_odds_history_chart(a, odds_lines, fights))
    show_fig(cmp_b_odds, fighter_odds_history_chart(b, odds_lines, fights))


display(widgets.HBox([cmp_a, cmp_b]))
display(cmp_html)
display(widgets.HBox([cmp_a_profile, cmp_b_profile]))
display(widgets.HBox([cmp_a_odds, cmp_b_odds]))
draw_compare()
_observe(cmp_a, lambda *_: draw_compare())
_observe(cmp_b, lambda *_: draw_compare())
"""


RATING_STORY = r"""
attr_fighter = widgets.Dropdown(
    options=_fighter_names,
    value="Georges St-Pierre" if "Georges St-Pierre" in _fighter_names else _fighter_names[0],
    description="Fighter:", layout=widgets.Layout(width="420px"), style={"description_width": "70px"})
attr_rows = widgets.IntSlider(value=20, min=5, max=60, step=5, description="Rows:",
                              style={"description_width": "60px"})
attr_fw = chart_widget(height=420)
attr_html = html_box()


def _style_attribution_rows(df):
    if df.empty:
        return None
    rename = {
        "event_date": "Date", "opponent": "Opponent", "base_method_delta": "Base",
        "integrity_delta": "Clean", "performance_delta": "Strength",
        "interaction_delta": "Overlap", "combined_delta": "Net", "combined_weight": "Weight",
    }
    out = df.rename(columns=rename)
    show = [c for c in ["Date", "Opponent", "Base", "Clean", "Strength", "Overlap", "Net", "Weight"] if c in out.columns]
    out = out[show]
    return (
        out.style.hide(axis="index")
        .format({"Base": "{:+.2f}", "Clean": "{:+.2f}", "Strength": "{:+.2f}",
                 "Overlap": "{:+.2f}", "Net": "{:+.2f}", "Weight": "{:.2f}"}, na_rep="")
        .set_properties(subset=["Opponent"], **{"font-weight": "600", "color": THEME["text"]})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def draw_attribution():
    show_fig(attr_fw, sleeve_attribution_waterfall(sleeve_attribution, attr_fighter.value))
    rows = sleeve_attribution_table(sleeve_attribution, attr_fighter.value, n=attr_rows.value)
    styled = _style_attribution_rows(rows)
    attr_html.value = table_html(styled) if styled is not None else msg("no attribution rows")


display(widgets.HBox([attr_fighter, attr_rows]))
display(attr_fw)
display(html_box(note("Right = adjustment helped the rating, left = it hurt. Base is the raw method result; "
                     "Clean and Strength are the integrity/opponent-context layers.")))
display(attr_html)
draw_attribution()
_observe(attr_fighter, lambda *_: draw_attribution())
_observe(attr_rows, lambda *_: draw_attribution())
"""


ADJUSTMENTS = r"""
audit_sleeve = widgets.Dropdown(options=[("All", "all"), ("Clean", "integrity"), ("Strength", "performance")],
                                value="all", description="Layer:", style={"description_width": "60px"})
audit_effect = widgets.Dropdown(options=[("Boost + penalty", "all"), ("Boost only", "boost"), ("Penalty only", "penalty")],
                                value="all", description="Effect:", style={"description_width": "60px"})
audit_fighter = widgets.Dropdown(options=[("(all fighters)", "")] + [(n, n) for n in _fighter_names], value="",
                                 description="Fighter:", layout=widgets.Layout(width="340px"),
                                 style={"description_width": "70px"})
audit_n = widgets.IntSlider(value=25, min=5, max=100, step=5, description="Rows:", style={"description_width": "60px"})
audit_html = html_box()


def _style_audit_summary(df):
    if df.empty:
        return None
    show = df[[c for c in ["group", "factor", "direction", "appearances",
                           "median_effect_pct", "min_effect_pct", "max_effect_pct"] if c in df.columns]].copy()
    show = show.rename(columns={"group": "Group", "factor": "Factor", "direction": "Direction",
                                "appearances": "Uses", "median_effect_pct": "Typical",
                                "min_effect_pct": "Low", "max_effect_pct": "High"})
    return (
        show.style.hide(axis="index")
        .bar(subset=["Uses"], color="rgba(56,189,248,0.28)")
        .format({"Typical": "{:+.1f}%", "Low": "{:+.1f}%", "High": "{:+.1f}%"})
        .set_properties(subset=["Factor"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Group", "Direction"], **{"color": THEME["text_2"]})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def _style_audit_detail(df):
    if df.empty:
        return None
    show_cols = [c for c in ["event_date", "fighter", "opponent", "outcome", "direction",
                             "combined_effect_pct", "factors", "sleeves", "division"] if c in df.columns]
    out = df[show_cols].rename(columns={
        "event_date": "Date", "fighter": "Fighter", "opponent": "Opponent", "outcome": "Result",
        "direction": "Direction", "combined_effect_pct": "Net", "factors": "Factors",
        "sleeves": "Layer", "division": "Division"}).copy()
    def effect_color(v):
        if v == "Boost":
            return f"color:{THEME['positive']};font-weight:600"
        if v == "Penalty":
            return f"color:{THEME['negative']};font-weight:600"
        return f"color:{THEME['text_muted']}"
    return (
        out.style.hide(axis="index")
        .map(effect_color, subset=["Direction"])
        .format({"Net": "{:+.1f}%"})
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Opponent", "Division", "Layer"], **{"color": THEME["text_2"]})
        .set_properties(subset=["Factors"], **{"color": THEME["text_2"], "font-size": "0.9em"})
        .set_table_styles(_BASE_TABLE_STYLES)
    )


def draw_audit():
    parts = []
    summary = sleeve_factor_summary_table(integrity_appearances, performance_appearances)
    if audit_sleeve.value != "all":
        summary = summary[summary["sleeve"].eq(audit_sleeve.value)]
    styled = _style_audit_summary(summary)
    if styled is None:
        parts.append(msg("no sleeve activity in this snapshot"))
    else:
        parts.append(heading("Factors") + table_html(styled))
    fighter_filter = (audit_fighter.value or "").strip() or None
    detail = sleeve_effects_by_fight_table(
        integrity_appearances if audit_sleeve.value in ("all", "integrity") else pd.DataFrame(),
        performance_appearances if audit_sleeve.value in ("all", "performance") else pd.DataFrame(),
        n=audit_n.value, fighter=fighter_filter, effect=audit_effect.value)
    styled_d = _style_audit_detail(detail)
    if styled_d is None:
        parts.append(msg("no factor effects match the current filters"))
    else:
        parts.append(heading("Biggest fights") + table_html(styled_d))
    audit_html.value = "".join(parts)


display(widgets.VBox([widgets.HBox([audit_sleeve, audit_effect]), widgets.HBox([audit_fighter, audit_n])]))
display(audit_html)
draw_audit()
for _w in (audit_sleeve, audit_effect, audit_fighter, audit_n):
    _observe(_w, lambda *_: draw_audit())
"""


FIGHTMATRIX = r"""
gfm_fw = chart_widget(height=520)
gfm_html = html_box()


def _style_rank_delta(df):
    if df.empty:
        return None
    rename = {"fighter": "Fighter", "glicko_rank": "Our rank", "mu_canonical": "Our rating",
              "fightmatrix_rank": "FightMatrix rank", "fightmatrix_points": "FightMatrix points",
              "fightmatrix_division": "Division", "glicko_vs_fm_rank_delta": "Rank gap",
              "delta_mu_method_integrity": "Integrity adj.", "ped_confirmed_fights": "PED",
              "dq_wins": "DQ", "missed_weight_wins": "MW"}
    show_cols = [c for c in ["fighter", "glicko_rank", "fightmatrix_rank", "glicko_vs_fm_rank_delta",
                             "mu_canonical", "fightmatrix_points", "fightmatrix_division",
                             "delta_mu_method_integrity", "ped_confirmed_fights", "dq_wins", "missed_weight_wins"]
                 if c in df.columns]
    out = df[show_cols].rename(columns=rename).copy()
    def delta_color(v):
        if pd.isna(v):
            return ""
        if v > 0:
            return f"color:{THEME['negative']};font-weight:600"
        if v < 0:
            return f"color:{THEME['positive']};font-weight:600"
        return f"color:{THEME['text_muted']}"
    fmt = {}
    if "Our rating" in out.columns: fmt["Our rating"] = "{:.1f}"
    if "FightMatrix points" in out.columns: fmt["FightMatrix points"] = "{:.0f}"
    if "Integrity adj." in out.columns: fmt["Integrity adj."] = "{:+.1f}"
    if "Rank gap" in out.columns: fmt["Rank gap"] = "{:+.0f}"
    styled = (
        out.style.hide(axis="index").format(fmt, na_rep="—")
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_table_styles(_BASE_TABLE_STYLES)
    )
    if "Rank gap" in out.columns:
        styled = styled.map(delta_color, subset=["Rank gap"])
    return styled


def draw_gfm():
    if fightmatrix_rankings is None or fightmatrix_rankings.empty:
        gfm_html.value = msg("no FightMatrix data in this snapshot")
        show_fig(gfm_fw, go.Figure())
        return
    fig = glicko_fightmatrix_scatter(rc, fightmatrix_rankings, min_fights=g_min_fights.value, label_outliers=0)
    fig.update_layout(title="Our rating vs FightMatrix points", xaxis_title="Our rating", yaxis_title="FightMatrix points")
    show_fig(gfm_fw, fig)
    deltas = rank_delta_table(rc, fightmatrix_rankings, min_fights=g_min_fights.value, limit=g_top_n.value)
    styled = _style_rank_delta(deltas)
    gfm_html.value = (heading("Biggest rank disagreements") + table_html(styled)) if styled is not None else msg("no rank-disagreement rows available")


display(gfm_fw)
display(html_box(note("Each dot is a fighter both systems rate. Dots far from the cloud are the biggest "
                     "disagreements; the table lists them. Min-fights and Top N come from the Control Room.")))
display(gfm_html)
draw_gfm()
subscribe("fightmatrix", draw_gfm, {"min_fights", "top_n"})
"""


ERA = r"""
era_divisions = widgets.SelectMultiple(options=list(DIVISIONS), value=tuple(list(DIVISIONS)[:8]),
                                       description="Divisions:", rows=8, layout=widgets.Layout(width="340px"),
                                       style={"description_width": "70px"})
era_year_min = widgets.IntSlider(value=min(_years), min=min(_years), max=max(_years), step=1, description="From:",
                                 continuous_update=False, style={"description_width": "60px"})
era_year_max = widgets.IntSlider(value=max(_years), min=min(_years), max=max(_years), step=1, description="To:",
                                 continuous_update=False, style={"description_width": "60px"})
era_fw = chart_widget(height=460)


def draw_era():
    if ratings_history is None or ratings_history.empty:
        show_fig(era_fw, go.Figure())
        return
    ymin, ymax = sorted([era_year_min.value, era_year_max.value])
    fig = era_heatmap_chart(ratings_history, all_bouts, top_n=g_top_n.value,
                            divisions=list(era_divisions.value or []), year_min=ymin, year_max=ymax)
    fig.update_layout(title=f"Top-end division strength index (top {g_top_n.value})",
                      coloraxis_colorbar=dict(title=dict(text="Strength index", font=dict(color="#cbd5e1")),
                                              tickfont=dict(color="#cbd5e1")))
    for tr in fig.data:
        if hasattr(tr, "colorbar"):
            tr.colorbar = dict(title=dict(text="Strength index", font=dict(color="#cbd5e1")),
                               tickfont=dict(color="#cbd5e1"))
    show_fig(era_fw, fig)


display(widgets.HBox([era_divisions, widgets.VBox([era_year_min, era_year_max])]))
display(era_fw)
display(html_box(note("Color is normalized within each year: 100 = strongest division that year; lower = how far "
                     "behind that year's leader. Top N comes from the Control Room.")))
draw_era()
for _w in (era_divisions, era_year_min, era_year_max):
    _observe(_w, lambda *_: draw_era())
subscribe("era", draw_era, {"top_n"})
"""


CELLS = [
    md("""
# Symon UFC Rank Engine — Interactive Dashboard

One **Control Room** at the top drives every section. Pick a **scoring method**,
a **time window**, a **division**, **Top N**, and minimum fights, and the
leaderboards, movers, placement, division and era views all refresh together.
Each section keeps a few local controls for things that only make sense there
(streak sort, fighters to compare, attribution rows).

> Charts are live `FigureWidget`s and tables are HTML widgets, so toggles update
> in place. Run the cells top to bottom once, then drive it from the controls.
"""),
    code(DATA_LOAD),
    code(RUNTIME),
    md("## 🎛️ Control Room"),
    code(CONTROL_ROOM),
    md("""
## Leaderboard

The ranked board for the current Control-Room selection. **Rating** is the
selected scoring lens; **vs Wins** shows how far context (Clean/Strength) moved a
fighter off the raw win-based number. Use **Gender**, **Division**, **Top N**, and
**Min fights** above to reshape it.
"""),
    code(LEADERBOARD),
    md("""
## Career Overlay

Pick any set of fighters to overlay their rating arcs. The line follows whatever
**Scoring** lens is selected in the Control Room.
"""),
    code(TRAJECTORY),
    md("""
## Movers

The largest rank changes versus the previous snapshot, for the selected scoring
view. Needs a comparable prior snapshot for the same view.
"""),
    code(MOVERS),
    md("""
## Win Streaks

The longest unbeaten runs, filtered by the Control-Room **Division**/**Gender** and
ranked by your chosen **Sort**. Pick a row — or type any fighter — to see that
fighter's rating arc with the streak window shaded gold.
"""),
    code(STREAKS),
    md("""
## Placement

Resume depth vs rating for the top group, plus how the top-100 splits across
divisions. Driven by **Scoring**, **Window**, **Top N**, and **Min fights**.
"""),
    code(PLACEMENT),
    md("""
## Divisions

Compare divisions like a dashboard: choose the divisions and a year, switch
between absolute **Score** and shape-only **Index**, and the timeline, the
single-year ranking, the current leaders table, and crowdedness all update.
"""),
    code(DIVISIONS_SECTION),
    md("""
## Compare Fighters

Pick two fighters for a head-to-head: predicted win probability, **closeness**
(1 = coin-flip, 0 = lopsided), side-by-side resumes, and each fighter's rating
profile and market history.
"""),
    code(COMPARE),
    md("""
## Rating Story

For one fighter, which adjustments helped or hurt over their career. Right is
positive, left is negative.
"""),
    code(RATING_STORY),
    md("""
## Adjustments

Where the Clean and Strength layers fire, how often, and how large the effects
are — with the biggest individual fights called out.
"""),
    code(ADJUSTMENTS),
    md("""
## FightMatrix Check

A sanity check against an outside ranking. Far-from-the-cloud dots are the
biggest disagreements; the table lists them explicitly.
"""),
    code(FIGHTMATRIX),
    md("""
## Top-End Strength by Era

Year × division heatmap of top-end strength, normalized within each year so you
can read which division led the sport season by season.
"""),
    code(ERA),
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
