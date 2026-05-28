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
    division_strength_timeline_chart,
    division_year_snapshot_chart,
    division_year_top_fighters_chart,
    era_heatmap_chart,
    favorite_underdog_performance_table,
    fighter_odds_history_chart,
    fighter_profile_chart,
    fighter_detail,
    fighter_search,
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
SUBSCRIBERS = []     # list of (name, draw_fn, keys:set) — Control-Room key deps
SECTION_DRAWS = []   # list of (name, draw_fn) — every section, for full redraw


def register_section(name, fn):
    "Register a section's primary draw so a model recompute can refresh it."
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
    "Re-run every registered section draw (used after a model recompute)."
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
g_lens = widgets.Dropdown(
    options=list(PUBLIC_RATING_LENSES), value="complete",
    description="Rank by:", style={"description_width": "70px"},
    layout=widgets.Layout(width="230px"))
g_time = widgets.Dropdown(
    options=list(PUBLIC_TIME_VIEWS), value="current",
    description="Form:", style={"description_width": "70px"},
    layout=widgets.Layout(width="200px"))
g_division = widgets.Dropdown(
    options=["All divisions"] + list(DIVISIONS), value="All divisions",
    description="Weight class:", style={"description_width": "90px"},
    layout=widgets.Layout(width="320px"))
g_gender = widgets.ToggleButtons(
    options=[("Both", "both"), ("Men", "M"), ("Women", "F")], value="both",
    description="Roster:", style={"description_width": "70px"})
g_top_n = widgets.IntSlider(
    value=25, min=5, max=100, step=5, description="Show top:",
    continuous_update=False, style={"description_width": "80px"},
    layout=widgets.Layout(width="330px"))
g_min_fights = widgets.IntSlider(
    value=3, min=0, max=20, step=1, description="Min UFC bouts:",
    continuous_update=False, style={"description_width": "110px"},
    layout=widgets.Layout(width="350px"))
g_prime_years = widgets.IntSlider(
    value=10, min=6, max=15, step=1, description="Prime span (yrs):",
    continuous_update=False, style={"description_width": "120px"},
    layout=widgets.Layout(width="350px"))
g_prime_min = widgets.IntSlider(
    value=13, min=5, max=30, step=1, description="Min prime bouts:",
    continuous_update=False, style={"description_width": "120px"},
    layout=widgets.Layout(width="350px"))

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
    f"<b style='color:{THEME['text_2']}'>Rank by</b> picks how a win is scored — "
    f"<b>Wins</b> (just the W, no method or context), "
    f"<b>Complete</b> (the full picture: finish quality + integrity discounts for "
    f"PED/DQ/missed-weight + opponent strength), "
    f"<b>Legacy</b> (Complete plus a whole-career résumé bonus, era-comparable). "
    f"<b style='color:{THEME['text_2']}'>Form</b>: <b>Now</b> = where they sit today, "
    f"<b>Peak</b> = their best 5-year run, <b>Prime</b> = a sustained run you size with "
    f"the <b>Prime</b> sliders. <b style='color:{THEME['text_2']}'>Show top</b>, "
    f"<b>Min UFC bouts</b>, <b>Weight class</b>, and <b>Roster</b> filter the rankings. "
    f"Change anything and every section re-ranks instantly.</div>"
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
    baseline_vals = pd.to_numeric(df.get("mu_canonical"), errors="coerce")
    return pd.DataFrame({
        "#": [_rank_chip(i) for i in range(1, len(df) + 1)],
        "Fighter": df["fighter"],
        "Rating": rating_vals.round(1),
        "vs Wins": (rating_vals - baseline_vals).round(1),
        "Division": (
            (df["career_division"] if "career_division" in df.columns else pd.Series(pd.NA, index=df.index))
            .fillna(df["recent_division"] if "recent_division" in df.columns else pd.Series("", index=df.index))
        ),
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
traj_cap = html_box(note("The line is each fighter's rating over time; the shaded band is how confident the "
                         "model is (wider = less certain, e.g. early career or after a layoff). Dots are fights, "
                         "colored by how they ended. The rating follows the Scoring lens in the Control Room."))


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
        return selected_rating_col() or "sustained_peak_headline_mu_whr"
    except ValueError:
        return "sustained_peak_headline_mu_whr"


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
subscribe("placement", draw_placement, {"lens", "time", "prime_years", "prime_min", "top_n", "min_fights"})
"""


DIVISIONS_SECTION = r"""
# ---- Local controls --------------------------------------------------------
_default_divisions = tuple([d for d in ["Lightweight", "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight", "Featherweight", "Bantamweight", "Flyweight"] if d in DIVISIONS])
divx = widgets.SelectMultiple(
    options=list(DIVISIONS),
    value=_default_divisions[:6] if _default_divisions else tuple(list(DIVISIONS)[:6]),
    description="Divisions:", rows=9, layout=widgets.Layout(width="320px"),
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
divx_leader_pick = widgets.Dropdown(
    options=list(DIVISIONS),
    value=(_default_divisions[0] if _default_divisions
           else (list(DIVISIONS)[0] if DIVISIONS else "Lightweight")),
    description="Show top 15 of:",
    layout=widgets.Layout(width="320px"),
    style={"description_width": "120px"})

# ---- Output widgets --------------------------------------------------------
divx_timeline = chart_widget(height=540)
divx_snapshot = chart_widget(height=560)
divx_era = chart_widget(height=520)
divx_density = chart_widget(height=380)
divx_leader_table = html_box()


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
        fig_tl.update_layout(title=f"{rating_label()} — division strength {ymin}-{ymax}")
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
    fig_den = top100_division_density_chart(rc, rating_col=col, n=100)
    show_fig(divx_density, fig_den)

    # ---- Single-division leaders (top 15) ---------------------------------
    div = divx_leader_pick.value
    if not div:
        divx_leader_table.value = msg("pick a division for the leader board")
    else:
        rank_col = selected_rating_col()
        if not rank_col or rank_col not in rc.columns:
            rank_col = "mu_canonical"
        d = rc.copy()
        d["_career"] = d.get("career_division", pd.Series(pd.NA, index=d.index))
        d = d[d["_career"].eq(div)].dropna(subset=[rank_col]).copy()
        d = d.sort_values(rank_col, ascending=False).head(15).reset_index(drop=True)
        if d.empty:
            divx_leader_table.value = msg(f"no rated fighters in {div}")
        else:
            view = pd.DataFrame({
                "#": [_rank_chip(i) for i in range(1, len(d) + 1)],
                "Fighter": d["fighter"],
                "Rating": pd.to_numeric(d[rank_col], errors="coerce").round(1),
                "Fights": pd.to_numeric(d.get("rating_periods"), errors="coerce").fillna(0).astype(int),
                "Last": pd.to_datetime(d.get("last_event_date"), errors="coerce").dt.date,
                "Now competes": d.get("current_division", pd.Series("—", index=d.index)).fillna("—"),
            })
            rmin, rmax = view["Rating"].min(), view["Rating"].max()
            styled = (
                view.style.hide(axis="index")
                .bar(subset=["Rating"], color="rgba(56,189,248,0.28)", vmin=rmin, vmax=rmax)
                .format({"Rating": "{:.1f}"})
                .format(lambda s: s, subset=["#"], escape=None)
                .format(lambda s: s, subset=["Fighter"], escape=None)
                .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
                .set_properties(subset=["Fights", "Last", "Now competes"], **{"color": THEME["text_muted"]})
                .set_properties(subset=["#"], **{"text-align": "center"})
                .set_table_styles(_BASE_TABLE_STYLES)
            )
            divx_leader_table.value = (
                heading(f"Top 15 — {div} (career division)") + table_html(styled)
            )


# ---- Layout: one cohesive Weight Classes section ---------------------------
display(html_box(heading("Strength over time")))
display(widgets.HBox([divx, widgets.VBox([divx_year_range, divx_index])]))
display(divx_timeline)
display(html_box(note("Each selected weight class's top-tier strength over the chosen year range. "
                     "Flip to Index to compare how divisions rose and fell regardless of absolute level "
                     "— handy for 'was the 2010s lightweight era deeper than today's?'.")))

display(html_box(heading("Single-year ranking")))
display(divx_year_snapshot)
display(divx_snapshot)
display(html_box(note("The actual top fighters of the snapshot year in each selected class — not just an "
                     "aggregate. Read each block as a mini-leaderboard for that division that year.")))

display(html_box(heading("Era heat map")))
display(divx_era)
display(html_box(note("100 = the deepest weight class that year; lower = how far a division trailed the "
                     "era's best. Shows which division ruled the sport season by season.")))

display(html_box(heading("Top 100 by career division")))
display(divx_density)
display(html_box(note("How the current top 100 splits across the weight classes (by career division — where "
                     "the fighter built their résumé, not their most recent bout's class).")))

display(html_box(heading("Division leaders right now")))
display(divx_leader_pick)
display(divx_leader_table)
display(html_box(note("Top 15 of the picked class by the lens up top. 'Now competes' shows whether that "
                     "fighter currently fights in a different class than their career home — a flagged title "
                     "mover.")))

draw_divx()
for _w in (divx, divx_year_range, divx_index, divx_year_snapshot, divx_leader_pick):
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
register_section("compare", draw_compare)
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


def _signed_chip(label, value):
    if value is None or pd.isna(value):
        return ""
    color = THEME["positive"] if value > 0 else THEME["negative"] if value < 0 else THEME["text_muted"]
    return (f"<span style='display:inline-block;margin-right:16px;color:{THEME['text_muted']};"
            f"font-size:0.9em'>{label} <b style='color:{color}'>{value:+.1f}</b></span>")


def _style_attribution_rows(df):
    if df.empty:
        return None
    rename = {"event_date": "Date", "opponent": "Opponent",
              "integrity_delta": "Clean", "performance_delta": "Strength", "combined_delta": "Net"}
    out = df.rename(columns=rename)
    show = [c for c in ["Date", "Opponent", "Clean", "Strength", "Net"] if c in out.columns]
    out = out[show].copy()
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"], errors="coerce").dt.date
    def sign_color(v):
        if pd.isna(v) or v == 0:
            return f"color:{THEME['text_muted']}"
        return f"color:{THEME['positive']};font-weight:600" if v > 0 else f"color:{THEME['negative']};font-weight:600"
    sty = (
        out.style.hide(axis="index")
        .format({"Clean": "{:+.2f}", "Strength": "{:+.2f}", "Net": "{:+.2f}"}, na_rep="—")
        .set_properties(subset=["Opponent"], **{"font-weight": "600", "color": THEME["text"]})
        .set_table_styles(_BASE_TABLE_STYLES)
    )
    for c in ("Clean", "Strength", "Net"):
        if c in out.columns:
            sty = sty.map(sign_color, subset=[c])
    return sty


def draw_attribution():
    show_fig(attr_fw, sleeve_attribution_waterfall(sleeve_attribution, attr_fighter.value))
    rows = sleeve_attribution_table(sleeve_attribution, attr_fighter.value, n=attr_rows.value)
    if rows is None or rows.empty:
        attr_html.value = msg("no attribution rows for this fighter")
        return
    clean = pd.to_numeric(rows.get("integrity_delta"), errors="coerce").sum()
    strength = pd.to_numeric(rows.get("performance_delta"), errors="coerce").sum()
    net = pd.to_numeric(rows.get("combined_delta"), errors="coerce").sum()
    summary = (f"<div style='font-family:{THEME['font']};margin:2px 0 10px'>"
               f"<span style='color:{THEME['text_2']};font-size:0.82em;text-transform:uppercase;"
               f"letter-spacing:0.06em;margin-right:14px'>Across shown fights</span>"
               f"{_signed_chip('Clean', clean)}{_signed_chip('Strength', strength)}{_signed_chip('Net', net)}</div>")
    styled = _style_attribution_rows(rows)
    attr_html.value = summary + (table_html(styled) if styled is not None else "")


display(widgets.HBox([attr_fighter, attr_rows]))
display(attr_fw)
display(html_box(note("Bars to the right helped the rating, to the left hurt it. <b>Clean</b> is the integrity "
                     "layer (tainted-win discounts), <b>Strength</b> is the opponent-quality layer, and "
                     "<b>Net</b> is their combined effect on each fight.")))
display(attr_html)
draw_attribution()
_observe(attr_fighter, lambda *_: draw_attribution())
_observe(attr_rows, lambda *_: draw_attribution())
register_section("rating_story", draw_attribution)
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
    show = df[[c for c in ["group", "factor", "direction", "appearances", "median_effect_pct"]
               if c in df.columns]].copy()
    show = show.rename(columns={"group": "Layer", "factor": "Factor", "direction": "Direction",
                                "appearances": "Uses", "median_effect_pct": "Typical"})
    def dir_color(v):
        return (f"color:{THEME['positive']}" if v == "Boost"
                else f"color:{THEME['negative']}" if v == "Penalty" else f"color:{THEME['text_muted']}")
    sty = (
        show.style.hide(axis="index")
        .bar(subset=["Uses"], color="rgba(56,189,248,0.28)")
        .format({"Typical": "{:+.1f}%"})
        .set_properties(subset=["Factor"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Layer"], **{"color": THEME["text_2"]})
        .set_table_styles(_BASE_TABLE_STYLES)
    )
    if "Direction" in show.columns:
        sty = sty.map(dir_color, subset=["Direction"])
    return sty


def _style_audit_detail(df):
    if df.empty:
        return None
    show_cols = [c for c in ["event_date", "fighter", "opponent", "combined_effect_pct", "factors", "sleeves"]
                 if c in df.columns]
    out = df[show_cols].rename(columns={
        "event_date": "Date", "fighter": "Fighter", "opponent": "Opponent",
        "combined_effect_pct": "Net", "factors": "Why", "sleeves": "Layer"}).copy()
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"], errors="coerce").dt.date
    def net_color(v):
        if pd.isna(v) or v == 0:
            return f"color:{THEME['text_muted']}"
        return f"color:{THEME['positive']};font-weight:600" if v > 0 else f"color:{THEME['negative']};font-weight:600"
    sty = (
        out.style.hide(axis="index")
        .format({"Net": "{:+.1f}%"})
        .set_properties(subset=["Fighter"], **{"font-weight": "600", "color": THEME["text"]})
        .set_properties(subset=["Opponent", "Layer"], **{"color": THEME["text_2"]})
        .set_properties(subset=["Why"], **{"color": THEME["text_2"], "font-size": "0.9em"})
        .set_table_styles(_BASE_TABLE_STYLES)
    )
    if "Net" in out.columns:
        sty = sty.map(net_color, subset=["Net"])
    return sty


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
register_section("adjustments", draw_audit)
"""


# Era heat map was a standalone section; its chart now lives inside
# DIVISIONS_SECTION above (one cohesive Weight Classes block).


MODEL_TUNING = r'''
# ---- Model Tuning ----------------------------------------------------------
# Unlike the Control Room (which only changes the VIEW), these knobs change the
# MODEL. Applying them re-runs the full rating engine, so it takes a few
# minutes. The recompute writes into a throwaway local-temp snapshot, so the
# on-disk baseline is never modified; Reset restores the default model instantly.
import importlib
import shutil
import tempfile
import time as _time

import ratings.constants as _C
from ratings.glicko2_engine import DEFAULT_TAU as _TAU_DEFAULT

_ENGINE_MODULES = [
    "ratings.constants", "ratings.opponent_quality", "ratings.integrity_adjustment",
    "ratings.performance_adjustment", "ratings.division_resume", "ratings.whr",
    "ratings.peaks", "ratings.rate_snapshot",
]
for _mn in _ENGINE_MODULES:
    importlib.import_module(_mn)


def _set_const(name, value):
    # Engine modules do `from ratings.constants import X`, binding X in their own
    # namespace at import. Rebind X in every module that has it (no reload).
    for _mn in _ENGINE_MODULES:
        _mod = sys.modules.get(_mn)
        if _mod is not None and hasattr(_mod, name):
            setattr(_mod, name, value)


def _rebuild_method_scores():
    # The base method stream maps method_class through a precomputed METHOD_SCORES
    # dict (built once at loader import), so changing the tier constants needs an
    # explicit rebuild + rebind wherever that dict is referenced.
    import loaders.ufcstats_loader as _ufc
    import ratings.rate_snapshot as _rs
    ms = {
        "KO/TKO": _C.METHOD_SCORE_FINISH,
        "Submission": _C.METHOD_SCORE_FINISH,
        "Decision - Unanimous": _C.METHOD_SCORE_UNANIMOUS,
        "Decision - Majority": _C.METHOD_SCORE_NON_UNANIMOUS_DECISION,
        "Decision - Split": _C.METHOD_SCORE_NON_UNANIMOUS_DECISION,
        "DQ": _C.METHOD_SCORE_DQ,
    }
    _ufc.METHOD_SCORES = ms
    if hasattr(_rs, "METHOD_SCORES"):
        _rs.METHOD_SCORES = ms


# (const_name | "tau", label, min, max, step, group)
_KNOBS = [
    ("tau", "How fast ratings swing", 0.2, 1.2, 0.05, "Finish vs decision · volatility"),
    ("METHOD_SCORE_UNANIMOUS", "Credit for a unanimous-decision win", 0.80, 1.00, 0.01, "Finish vs decision · volatility"),
    ("METHOD_SCORE_NON_UNANIMOUS_DECISION", "Credit for a split/majority win", 0.70, 1.00, 0.01, "Finish vs decision · volatility"),
    ("INTEGRITY_PED_WIN_SCORE", "Credit for a PED-tainted win", 0.30, 1.00, 0.05, "Integrity (tainted wins)"),
    ("INTEGRITY_DQ_WIN_SCORE", "Credit for a win by DQ", 0.30, 1.00, 0.05, "Integrity (tainted wins)"),
    ("INTEGRITY_MISSED_WEIGHT_WIN_SCORE", "Credit for a win after missing weight", 0.30, 1.00, 0.05, "Integrity (tainted wins)"),
    ("PERF_OPPONENT_QUALITY_AMPLITUDE", "Reward for beating elite competition", 0.00, 0.20, 0.01, "Opposition & upsets"),
    ("PERF_UPSET_AMPLITUDE", "Reward for pulling an upset", 0.00, 0.10, 0.005, "Opposition & upsets"),
    ("SUSTAINED_PEAK_OPP_MAX_WEIGHT", "Reward for a title-level schedule", 1.0, 4.0, 0.1, "Prime / résumé weighting"),
    ("PERIOD_TITLE_FIGHT_WEIGHT_MULT", "How much title fights count", 1.0, 2.0, 0.05, "Prime / résumé weighting"),
    ("PERIOD_TITLE_WIN_BONUS", "Bonus for winning a title", 0.0, 120.0, 5.0, "Prime / résumé weighting"),
    ("PERIOD_LOSS_PENALTY", "Penalty for a loss", 0.0, 120.0, 5.0, "Prime / résumé weighting"),
]
_TUNE_DEFAULTS = {k: (float(_TAU_DEFAULT) if k == "tau" else float(getattr(_C, k))) for k, *_rest in _KNOBS}

# Snapshot the baseline frames once so Reset is instant (no recompute).
_FRAME_KEYS = ["rc", "ratings_history", "ratings_histories", "sleeve_attribution",
               "integrity_appearances", "performance_appearances", "fighter_dominance"]
if "_BASELINE_FRAMES" not in globals():
    _BASELINE_FRAMES = {k: globals().get(k) for k in _FRAME_KEYS}

# Persist widgets across cell re-runs so a Run-All does not wipe the user's tuning.
if "TUNE_WIDGETS" not in globals():
    TUNE_WIDGETS = {}
    for _name, _label, _lo, _hi, _step, _group in _KNOBS:
        TUNE_WIDGETS[_name] = widgets.FloatSlider(
            value=_TUNE_DEFAULTS[_name], min=_lo, max=_hi, step=_step,
            description=_label, continuous_update=False, readout_format=".3g",
            style={"description_width": "240px"}, layout=widgets.Layout(width="540px"))

tune_status = html_box()
tune_preview = html_box()
_apply_btn = widgets.Button(description="Apply & recompute", button_style="warning",
                            icon="bolt", layout=widgets.Layout(width="200px"))
_reset_btn = widgets.Button(description="Reset to defaults", layout=widgets.Layout(width="170px"))


def _ensure_scratch():
    global _SCRATCH
    sc = globals().get("_SCRATCH")
    if sc is None or not Path(sc).exists():
        sc = Path(tempfile.mkdtemp(prefix="ufc_tune_"))
        shutil.copytree(SNAPSHOT_DIR, sc, dirs_exist_ok=True)
        _SCRATCH = sc
    return Path(sc)


def _rebind_frames(snap_dir):
    snap = load_project_data(snap_dir, DATABASE_PATH, prefer_database=False)
    rh = snap.get("ratings_history", pd.DataFrame())
    whr_path = Path(snap_dir) / "ratings_history_whr.parquet"
    globals().update({
        "rc": snap["ratings_current"],
        "ratings_history": rh,
        "ratings_histories": {
            "ratings_history": rh,
            "ratings_history_method_integrity": snap.get("ratings_history_method_integrity", pd.DataFrame()),
            "ratings_history_method_performance": snap.get("ratings_history_method_performance", pd.DataFrame()),
            "ratings_history_method_integrity_performance": snap.get("ratings_history_method_integrity_performance", pd.DataFrame()),
            "ratings_history_whr": pd.read_parquet(whr_path) if whr_path.exists() else pd.DataFrame(),
        },
        "sleeve_attribution": snap.get("sleeve_attribution", pd.DataFrame()),
        "integrity_appearances": snap.get("integrity_appearances", pd.DataFrame()),
        "performance_appearances": snap.get("performance_appearances", pd.DataFrame()),
        "fighter_dominance": snap.get("fighter_dominance", pd.DataFrame()),
    })
    _prime_cache.clear()


def _current_tuning():
    return {name: TUNE_WIDGETS[name].value for name, *_rest in _KNOBS}


def _changed_vs_default(tuning):
    return [(label, _TUNE_DEFAULTS[name], tuning[name])
            for name, label, *_rest in _KNOBS
            if abs(float(tuning[name]) - _TUNE_DEFAULTS[name]) > 1e-9]


def _set_status(html, color=None):
    tune_status.value = (f"<div style='font-family:{THEME['font']};font-size:0.9em;"
                         f"color:{color or THEME['text_2']};padding:6px 0'>{html}</div>")


def _top5(rc_frame, label):
    col = ("mu_method_integrity_performance" if "mu_method_integrity_performance" in rc_frame.columns
           else "mu_canonical")
    men = rc_frame[rc_frame["gender"].eq("M")] if "gender" in rc_frame.columns else rc_frame
    top = men.dropna(subset=[col]).sort_values(col, ascending=False).head(5)
    names = " &middot; ".join(f"{i + 1}. {r.fighter}" for i, r in enumerate(top.itertuples()))
    return f"<b style='color:{THEME['text']}'>{label}</b> &nbsp;{names}"


def _recompute(_btn=None):
    tuning = _current_tuning()
    changed = _changed_vs_default(tuning)
    if not changed:
        _set_status("All knobs are at their defaults - move a slider, then Apply.", THEME["text_muted"])
        return
    before = _top5(rc, "Top 5 men before:")
    _apply_btn.disabled = _reset_btn.disabled = True
    _set_status("Recomputing the full model (5 rating streams + WHR + peaks). "
                "This takes a few minutes; every section refreshes when it finishes.", THEME["accent"])
    try:
        for name, *_rest in _KNOBS:
            if name != "tau":
                _set_const(name, float(tuning[name]))
        _rebuild_method_scores()
        from ratings.rate_snapshot import run as _run
        scratch = _ensure_scratch()
        t0 = _time.time()
        _run(scratch, tau=float(tuning["tau"]))
        dt = _time.time() - t0
        _rebind_frames(scratch)
        redraw_all()
        rows = "".join(
            f"<tr><td style='padding:1px 14px 1px 0;color:{THEME['text_2']}'>{lab}</td>"
            f"<td style='padding:1px 14px 1px 0;color:{THEME['text_muted']}'>{d:g}</td>"
            f"<td style='padding:1px 0;color:{THEME['accent']};font-weight:600'>{v:g}</td></tr>"
            for lab, d, v in changed)
        tune_preview.value = (
            f"<div style='font-family:{THEME['font']};font-size:0.85em'>"
            f"<table style='border-collapse:collapse;margin-bottom:8px'><thead><tr>"
            f"<th style='text-align:left;color:{THEME['text_muted']};font-size:0.85em;padding-right:14px'>Changed knob</th>"
            f"<th style='text-align:left;color:{THEME['text_muted']};font-size:0.85em;padding-right:14px'>Default</th>"
            f"<th style='text-align:left;color:{THEME['text_muted']};font-size:0.85em'>Applied</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            f"<div style='color:{THEME['text_caption']};line-height:1.6'>{before}<br>{_top5(rc, 'Top 5 men after:&nbsp;')}</div></div>")
        _set_status(f"Recomputed in {dt:.0f}s. Every section below now reflects the tuned model.",
                    THEME["positive"])
    except Exception as exc:
        traceback.print_exc()
        _set_status(f"Recompute failed: {exc}", THEME["negative"])
    finally:
        _apply_btn.disabled = _reset_btn.disabled = False


def _reset(_btn=None):
    for name, *_rest in _KNOBS:
        TUNE_WIDGETS[name].value = _TUNE_DEFAULTS[name]
        if name != "tau":
            _set_const(name, _TUNE_DEFAULTS[name])
    _rebuild_method_scores()
    globals().update(dict(_BASELINE_FRAMES))
    _prime_cache.clear()
    redraw_all()
    tune_preview.value = ""
    _set_status("Reset to the default model (instant - no recompute).", THEME["text_muted"])


_apply_btn.on_click(_recompute)
_reset_btn.on_click(_reset)

_groups = {}
for _name, _label, _lo, _hi, _step, _group in _KNOBS:
    _groups.setdefault(_group, []).append(TUNE_WIDGETS[_name])
_group_boxes = [
    widgets.VBox([widgets.HTML(heading(_g))] + _ws,
                 layout=widgets.Layout(border=f"1px solid {THEME['border']}",
                                       padding="6px 12px 10px", margin="0 10px 10px 0"))
    for _g, _ws in _groups.items()
]

display(Markdown(
    f"<div style='font-family:{THEME['font']};color:{THEME['text_caption']};font-size:0.82em;"
    f"line-height:1.6;margin-bottom:8px'>These change the <b>model</b>, not just the view. "
    f"Decision/integrity scores are on a 0-1 win scale (1 = a clean, decisive win); lower integrity "
    f"scores discount tainted wins. Adjust, then <b>Apply &amp; recompute</b> - the full engine reruns "
    f"(a few minutes) and every section updates. <b>Reset</b> restores defaults instantly.</div>"))
display(widgets.Box(_group_boxes, layout=widgets.Layout(display="flex", flex_flow="row wrap")))
display(widgets.HBox([_apply_btn, _reset_btn]))
display(tune_status)
display(tune_preview)
_set_status("Model is at defaults. Adjust a knob and Apply to recompute.", THEME["text_muted"])
'''


CELLS = [
    md("""
# Symon UFC Rank Engine — Interactive Dashboard

Two control layers sit at the top. The **Control Room** changes the *view* — how
wins are scored, current form vs prime, weight class, how many fighters — and
re-ranks every section instantly. **Model Tuning** changes the *model itself* —
how much a finish, a tainted win, a title fight or beating elite competition is
worth; hit **Apply & recompute** and the whole rating engine re-runs so every
board and chart reflects your version of the model. Each section also keeps a few
local controls (streak sort, the two fighters to compare).

> Run the cells top to bottom once, then drive everything from the top. View
> toggles update instantly; a model recompute takes a few minutes.
"""),
    code(DATA_LOAD),
    code(RUNTIME),
    md("## 🎛️ Control Room"),
    code(CONTROL_ROOM),
    md("""
## 🛠️ Model Tuning

The Control Room changes what you **look at**. This panel changes the **model
itself** — how wins, finishes, opponents, integrity and prime windows are
scored. Adjust the knobs and hit **Apply & recompute**: the full rating engine
re-runs and every table and chart below updates to the tuned model.
"""),
    code(MODEL_TUNING),
    md("""
## The Rankings

The pound-for-pound board for whatever you've set up top. **Rating** is the lens
you picked in **Rank by**; **vs Wins** shows how much the **Complete**
context layer moved a fighter off the raw win count — positive means context
helped their case. Reshape it with **Roster**, **Weight class**, **Show top**,
and **Min UFC bouts**.
"""),
    code(LEADERBOARD),
    md("""
## Résumé vs Rating

Who's the real deal vs the hot start. Each fighter plotted by résumé depth (UFC
bouts rated) against rating, colored by their career division. Top-right is the
holy grail — an elite rating built over a long, proven résumé. Driven by **Rank
by**, **Form**, **Show top**, and **Min UFC bouts**.
"""),
    code(PLACEMENT),
    md("""
## Career Arcs

Overlay any set of fighters and watch their ratings rise and fall fight by fight
— who peaked highest, who stayed at the top longest, who fell off. The line
follows whatever **Rank by** lens is selected up top.
"""),
    code(TRAJECTORY),
    md("""
## Risers & Fallers

Who's climbing and who's sliding since the previous snapshot, for the lens you've
selected. Needs a comparable prior snapshot for the same view.
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

All the division views in one place. Pick the weight classes and a year range
to drive the strength-over-time chart, the single-year ranking, the era heat
map, the top-100 share, and a single-division leaderboard (pick a class, see
its top 15 right now).
"""),
    code(DIVISIONS_SECTION),
    md("""
## Tale of the Tape

Pick two fighters for a head-to-head: the model's win probability, **closeness**
(1 = a coin-flip, 0 = a blowout on paper), side-by-side résumés, and each
fighter's rating profile and how the betting market saw them.
"""),
    code(COMPARE),
    md("""
## What Moved a Fighter's Rating

Pick a fighter and see which fights helped or hurt them. Bars to the right are
gains, to the left are hits — split into the **Clean** (tainted-win) and
**Strength** (quality-of-opposition) layers that combine into the **Complete** lens.
"""),
    code(RATING_STORY),
    md("""
## Under the Hood

Where the **Clean** and **Strength** adjustments actually fire, how often, and
how hard — with the biggest single-fight swings called out. This is the audit
trail behind the Model Tuning knobs.
"""),
    code(ADJUSTMENTS),
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
