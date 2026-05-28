"""Reusable Plotly chart builders for the notebook.

All functions are pure: they take dataframes + parameters, return a Plotly
Figure (or a simple DataFrame for tables). Widget binding lives in the
notebook cells so this module is testable in isolation.

VS Code Jupyter compatibility note: we use plain `plotly.graph_objects.Figure`
throughout (not FigureWidget) because the latter has had rendering issues
in VS Code's notebook host.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from project_helpers import date_range, normalize_name_key
from ratings.constants import (
    FIVE_YEAR_PEAK_MIN_FIGHTS,
    FIVE_YEAR_PEAK_WINDOW_DAYS,
    FIVE_YEAR_PEAK_WINDOW_LABEL,
    RATING_COLUMN_LABELS,
    SUSTAINED_PEAK_MIN_FIGHTS,
    SUSTAINED_PEAK_WINDOW_LABEL,
    rating_label,
    rename_rating_columns,
)
from ratings.glicko2_engine import predict_win_prob_from_ratings, matchup_quality_from_ratings

# ---------------------------------------------------------------------------
# Visual identity — single source of truth (ESPN-style dark analytics theme).
#
# Both this module's Plotly charts AND the notebook's HTML/markdown chrome read
# from THEME so the whole surface stays consistent. The notebook imports THEME
# from here (see analysis/build_notebook.py) rather than redefining it.

THEME = {
    # canvas
    "bg":            "#0b1220",  # deep broadcast navy (primary canvas)
    "surface":       "#161f33",  # cards, table rows
    "surface_alt":   "#111a2b",  # zebra striping (slightly darker)
    "hover":         "#243049",  # row / point hover
    # text
    "text":          "#f8fafc",  # primary
    "text_2":        "#cbd5e1",  # secondary
    "text_muted":    "#94a3b8",  # muted labels
    "text_caption":  "#64748b",  # captions / footnotes
    # lines
    "border":        "#2a3650",  # faint dividers / gridlines
    "border_strong": "#3b4a6b",  # axis lines, strong dividers
    # palette
    "primary":       "#38bdf8",  # sky — primary series / fighter A / bars
    "secondary":     "#a78bfa",  # violet — secondary series / fighter B
    "accent":        "#fbbf24",  # amber/gold — #1, champion, key highlight
    "accent_2":      "#f472b6",  # rose — secondary highlight / movement
    "positive":      "#34d399",  # emerald — gains / wins
    "negative":      "#f87171",  # red — losses / penalties
    "neutral":       "#94a3b8",  # zero / neutral
    # font stack
    "font":          '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
}

# Vibrant categorical colorway that reads cleanly on the dark canvas.
CHART_COLORWAY = [
    "#38bdf8",  # sky
    "#fbbf24",  # amber
    "#34d399",  # emerald
    "#a78bfa",  # violet
    "#fb7185",  # rose
    "#f97316",  # orange
    "#22d3ee",  # cyan
    "#a3e635",  # lime
    "#e879f9",  # fuchsia
    "#60a5fa",  # blue
]

# Named series colors used by specific charts (rating streams, market lines).
STREAM_PALETTE = {
    "canonical":        "#94a3b8",
    "method":           THEME["primary"],
    "integrity":        THEME["accent"],
    "performance":      THEME["positive"],
    "full_context":     THEME["accent_2"],
    "whr":              THEME["secondary"],
    "ped_adjusted":     THEME["accent"],
    "odds_adjusted":    THEME["secondary"],
    "quality_adjusted": THEME["positive"],
}

SIGN_COLORS = {
    "positive": THEME["positive"],
    "negative": THEME["negative"],
}

# Dark→bright sequential ramp for heatmaps (strength indices, densities).
HEATMAP_COLORSCALE = [
    [0.0, THEME["surface_alt"]],
    [0.45, "#1d4ed8"],
    [1.0, THEME["primary"]],
]

CHART_TEMPLATE = "ufc_dark"


def _register_plotly_template() -> None:
    """Register (once) and default the dark ESPN template for all charts."""
    import plotly.graph_objects as _go
    import plotly.io as _pio

    if "ufc_dark" not in _pio.templates:
        tpl = _go.layout.Template()
        axis = dict(
            gridcolor=THEME["border"],
            zerolinecolor=THEME["border_strong"],
            linecolor=THEME["border_strong"],
            tickcolor=THEME["border_strong"],
            tickfont=dict(color=THEME["text_2"], size=11),
            title=dict(font=dict(color=THEME["text_2"], size=12)),
        )
        tpl.layout = dict(
            paper_bgcolor=THEME["bg"],
            plot_bgcolor=THEME["bg"],
            font=dict(family=THEME["font"], color=THEME["text"], size=13),
            title=dict(font=dict(family=THEME["font"], color=THEME["text"], size=16)),
            colorway=CHART_COLORWAY,
            xaxis=axis,
            yaxis=axis,
            legend=dict(
                bgcolor="rgba(0,0,0,0)", bordercolor=THEME["border"], borderwidth=0,
                font=dict(color=THEME["text_2"], size=11),
            ),
            hoverlabel=dict(
                bgcolor=THEME["surface"], bordercolor=THEME["border_strong"],
                font=dict(family=THEME["font"], color=THEME["text"], size=12),
            ),
            margin=dict(t=56, r=36, b=48, l=56),
        )
        _pio.templates["ufc_dark"] = tpl
    _pio.templates.default = "ufc_dark"


_register_plotly_template()

EMPTY_FIGURE_LAYOUT = dict(
    template=CHART_TEMPLATE,
    height=360,
    margin=dict(t=56, r=36, b=48, l=56),
)

PERFORMANCE_FACTOR_LABELS = {
    "perf_factor_decisiveness": "Decisiveness",
    "perf_factor_opponent_strength": "Opponent strength",
    "perf_factor_opponent_streak": "Opponent streak",
    "perf_factor_odds": "Market odds",
    "perf_factor_rank_context": "Top-15 division context",
    "perf_factor_championship": "Championship context",
    "perf_factor_p4p": "P4P context",
    "perf_factor_upset": "Rank-gated upset",
    "perf_factor_weight_class": "Weight-class movement",
    "perf_factor_activity_loss": "Post-layoff loss",
}

INTEGRITY_FACTOR_LABELS = {
    "integrity_factor_ped": "PED-confirmed win",
    "integrity_factor_dq": "DQ win",
    "integrity_factor_missed_weight": "Missed-weight win",
}


def _empty_figure(message: str, *, title: str | None = None, height: int = 360) -> go.Figure:
    """Return a consistent empty-state chart instead of a blank figure."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        showarrow=False,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        font=dict(color="#64748b", size=14),
    )
    fig.update_layout(**{**EMPTY_FIGURE_LAYOUT, "title": title or "", "height": height})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _metric_label(column: str) -> str:
    """Human label for rating-like columns used in chart titles and hovers."""
    labels = {
        "mu_canonical": "Wins rating",
        "phi_canonical": "Rating uncertainty",
        "mu_method": "Finishes rating",
        "mu_method_integrity": "Clean rating",
        "mu_method_performance": "Strength rating",
        "mu_method_integrity_performance": "Complete rating",
        "mu_whr": "Legacy rating",
    }
    return labels.get(column, rating_label(column).replace("_", " "))


def _apply_chart_layout(fig: go.Figure, *, height: int | None = None) -> go.Figure:
    """Apply the shared visual system while leaving caller-specific layout intact."""
    layout = dict(
        template=CHART_TEMPLATE,
        colorway=CHART_COLORWAY,
        font=dict(family=THEME["font"], color=THEME["text"]),
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["bg"],
        margin=dict(t=64, r=36, b=56, l=64),
    )
    if height is not None:
        layout["height"] = height
    fig.update_layout(**layout)
    fig.update_xaxes(
        showgrid=True,
        gridcolor=THEME["border"],
        zerolinecolor=THEME["border_strong"],
        linecolor=THEME["border_strong"],
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=THEME["border"],
        zerolinecolor=THEME["border_strong"],
        linecolor=THEME["border_strong"],
    )
    return fig


# ---------------------------------------------------------------------------
# Loading

TABLE_KEY_MAP = [
    ("canonical_fights", "fights"),
    ("crossorg_fights", "crossorg_fights"),
    ("canonical_rounds", "rounds"),
    ("canonical_fighters", "fighters"),
    ("canonical_events", "events"),
    ("ratings_history", "ratings_history"),
    ("ratings_history_method_integrity", "ratings_history_method_integrity"),
    ("ratings_history_method_performance", "ratings_history_method_performance"),
    ("ratings_history_method_integrity_performance", "ratings_history_method_integrity_performance"),
    ("ratings_current", "ratings_current"),
    ("integrity_appearances", "integrity_appearances"),
    ("performance_appearances", "performance_appearances"),
    ("fight_dominance", "fight_dominance"),
    ("fighter_dominance", "fighter_dominance"),
    ("calibration_residuals", "calibration_residuals"),
    ("sleeve_attribution", "sleeve_attribution"),
    ("division_entropy", "division_entropy"),
    ("division_resume", "division_resume"),
    ("datalab_bouts_all", "datalab_bouts_all"),
    ("datalab_merged_stats_scorecards", "datalab_merged_stats_scorecards"),
    ("datalab_fighter_details", "datalab_fighter_details"),
    ("datalab_scorecards", "datalab_scorecards"),
    ("fightmatrix_rankings", "fightmatrix_rankings"),
    ("odds_lines", "odds_lines"),
]

CSV_KEY_MAP = [
    ("_excluded_bouts", "excluded_bouts"),
    ("ped_confirmed_bouts", "ped_confirmed_bouts"),
    ("missed_weight_bouts", "missed_weight_bouts"),
]

METADATA_TABLES = [
    "source_manifest",
    "snapshot_manifest",
    "table_row_counts",
    "source_gaps",
]


def load_snapshot(snapshot_dir: Path | str) -> dict[str, pd.DataFrame]:
    """Load every parquet in a snapshot directory into a dict of DataFrames.

    `odds_lines` is auto-enriched with implied/no-vig/favorite columns
    so downstream viz helpers can rely on a stable enriched schema.
    """
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"snapshot not found: {snapshot_dir}")
    out = {}
    for stem, key in TABLE_KEY_MAP:
        path = snapshot_dir / f"{stem}.parquet"
        if path.exists():
            out[key] = pd.read_parquet(path)
    for stem, key in CSV_KEY_MAP:
        path = snapshot_dir / f"{stem}.csv"
        if path.exists():
            out[key] = pd.read_csv(path)
    if "odds_lines" in out and not out["odds_lines"].empty:
        # Lazy import to avoid pulling odds_loader on every viz import path
        from loaders.odds_loader import compute_implied_probs
        out["odds_lines"] = compute_implied_probs(out["odds_lines"])
    return out


def load_database(db_path: Path | str) -> dict[str, pd.DataFrame]:
    """Load the SQLite database into the same dict shape as `load_snapshot`."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    out = {}
    with sqlite3.connect(db_path) as con:
        existing = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        for table_name, key in TABLE_KEY_MAP:
            if table_name in existing:
                out[key] = pd.read_sql_query(f'SELECT * FROM "{table_name}"', con)
        for table_name in METADATA_TABLES + ["excluded_bouts", "ped_confirmed_bouts", "missed_weight_bouts"]:
            if table_name in existing:
                out[table_name] = pd.read_sql_query(f'SELECT * FROM "{table_name}"', con)
    return out


def load_project_data(
    snapshot_dir: Path | str,
    database_path: Path | str | None = None,
    prefer_database: bool = False,
) -> dict[str, pd.DataFrame]:
    """Load either snapshot parquet files or the SQLite database.

    The notebook defaults to parquet snapshots, but this helper lets a user flip
    to database-backed loading without changing downstream visualization code.
    """
    if prefer_database and database_path is not None and Path(database_path).exists():
        return load_database(database_path)
    return load_snapshot(snapshot_dir)


# ---------------------------------------------------------------------------
# Helpers

DIVISIONS = [
    "Strawweight", "Flyweight", "Bantamweight", "Featherweight",
    "Lightweight", "Welterweight", "Middleweight", "Light Heavyweight",
    "Heavyweight", "Women's Strawweight", "Women's Flyweight",
    "Women's Bantamweight", "Women's Featherweight",
    "Catch Weight", "Open Weight",
]

DIV_SHORT: dict[str, str] = {
    "Strawweight":          "STW",
    "Flyweight":            "FLY",
    "Bantamweight":         "BW",
    "Featherweight":        "FW",
    "Lightweight":          "LW",
    "Welterweight":         "WW",
    "Middleweight":         "MW",
    "Light Heavyweight":    "LHW",
    "Heavyweight":          "HW",
    "Women's Strawweight":  "W.STW",
    "Women's Flyweight":    "W.FLY",
    "Women's Bantamweight": "W.BW",
    "Women's Featherweight":"W.FW",
    "Catch Weight":         "CW",
    "Open Weight":          "OW",
}

FIGHTMATRIX_DIVISION_MAP = {
    "heavyweight": "Heavyweight",
    "light-heavyweight": "Light Heavyweight",
    "middleweight": "Middleweight",
    "welterweight": "Welterweight",
    "lightweight": "Lightweight",
    "featherweight": "Featherweight",
    "bantamweight": "Bantamweight",
    "flyweight": "Flyweight",
    "womens-bantamweight": "Women's Bantamweight",
    "womens-flyweight": "Women's Flyweight",
    "womens-strawweight": "Women's Strawweight",
}


def _name_key(name: str | None) -> str | None:
    key = normalize_name_key(name, compact=True)
    return key or None


def _date_range(df: pd.DataFrame) -> tuple[str | None, str | None]:
    return date_range(df)


def normalize_division(weight_class: str | None) -> str | None:
    """Strip 'UFC ', ' Title Bout', ' Bout' to land at clean division names."""
    if not isinstance(weight_class, str):
        return None
    w = weight_class.replace("UFC ", "").replace(" Title Bout", "").replace(" Bout", "").strip()
    # Match more specific labels first so "Women's Flyweight" is not collapsed
    # to the generic "Flyweight" bucket.
    for d in sorted(DIVISIONS, key=len, reverse=True):
        if d.lower() in w.lower():
            return d
    return w  # Catch-all (Catch Weight, Open Weight, etc.)


def add_division_to_fights(fights: pd.DataFrame) -> pd.DataFrame:
    out = fights.copy()
    out["division"] = out["weight_class"].apply(normalize_division)
    return out


def recent_division_by_fighter(fights: pd.DataFrame) -> pd.DataFrame:
    """Return each fighter's most recent UFC division in the canonical snapshot."""
    f = add_division_to_fights(fights)
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    long = (
        f.sort_values("event_date")
         .melt(id_vars=["event_date", "division"], value_vars=["fighter_a", "fighter_b"],
               var_name="_side", value_name="fighter")
         .dropna(subset=["fighter"])
    )
    return (
        long.groupby("fighter", as_index=False)
        .last()[["fighter", "division"]]
    )


def fightmatrix_best_rankings(fightmatrix_rankings: pd.DataFrame) -> pd.DataFrame:
    """Collapse FightMatrix rows to one best ranking row per normalized fighter."""
    if fightmatrix_rankings is None or fightmatrix_rankings.empty:
        return pd.DataFrame(columns=[
            "fighter", "fightmatrix_division", "fightmatrix_rank", "fightmatrix_points", "_name_key",
        ])
    fm = fightmatrix_rankings.copy()
    fm["_name_key"] = fm["fighter"].apply(_name_key)
    fm["fightmatrix_rank"] = pd.to_numeric(fm["rank"], errors="coerce")
    fm["fightmatrix_points"] = pd.to_numeric(fm["points"], errors="coerce")
    fm["fightmatrix_division"] = fm["division"].map(FIGHTMATRIX_DIVISION_MAP).fillna(fm["division"])
    fm = fm.dropna(subset=["_name_key"])
    fm = fm.sort_values(["fightmatrix_points", "fightmatrix_rank"], ascending=[False, True])
    return fm.drop_duplicates("_name_key")[[
        "fighter", "fightmatrix_division", "fightmatrix_rank", "fightmatrix_points",
        "record", "profile_url", "_name_key",
    ]]


def _fighter_fight_rows(fights: pd.DataFrame) -> pd.DataFrame:
    """Return one row per fighter appearance in `fights`."""
    cols = ["fight_url", "event_date", "fighter_a", "fighter_b"]
    extra = [c for c in ["method_class", "winner", "is_draw"] if c in fights.columns]
    a = fights[cols + extra].rename(columns={"fighter_a": "fighter", "fighter_b": "opponent"})
    b = fights[cols + extra].rename(columns={"fighter_b": "fighter", "fighter_a": "opponent"})
    return pd.concat([a, b], ignore_index=True).dropna(subset=["fighter"])


def _fight_duration_seconds(fights: pd.DataFrame, default_round_seconds: int = 300) -> pd.Series:
    """Approximate completed fight duration from bout ending fields."""
    end_round = pd.to_numeric(fights["end_round"], errors="coerce")
    end_seconds = pd.to_numeric(fights["end_time_seconds"], errors="coerce")
    duration = ((end_round - 1).clip(lower=0) * default_round_seconds) + end_seconds
    return duration.where(duration.gt(0))


def fighter_career_record(fighter: str, fights: pd.DataFrame) -> dict:
    """Return W/L/D record + method breakdown for a fighter."""
    appeared_a = fights[fights["fighter_a"] == fighter]
    appeared_b = fights[fights["fighter_b"] == fighter]
    total = len(appeared_a) + len(appeared_b)
    wins = (fights["winner"] == fighter).sum()
    losses = (fights["loser"] == fighter).sum()
    draws = ((fights["is_draw"]) & ((fights["fighter_a"] == fighter) | (fights["fighter_b"] == fighter))).sum()

    # methods of victory
    method_breakdown = fights[fights["winner"] == fighter]["method_class"].value_counts().to_dict()
    return {
        "fights": int(total),
        "wins": int(wins),
        "losses": int(losses),
        "draws": int(draws),
        "method_breakdown_as_winner": method_breakdown,
    }


# ---------------------------------------------------------------------------
# A1. Live top-N table

def top_n_table(
    ratings_current: pd.DataFrame,
    fighters: pd.DataFrame,
    fights: pd.DataFrame,
    n: int = 25,
    min_fights: int = 3,
    division: str | None = None,
    active_within_days: int | None = None,
    rating_col: str = "mu_canonical",
) -> pd.DataFrame:
    """Return a sortable top-N table with derived columns for display."""
    df = ratings_current.copy()
    df = df[df["rating_periods"] >= min_fights]

    if active_within_days is not None and "last_event_date" in df.columns:
        cutoff = pd.Timestamp(fights["event_date"].max()) - pd.Timedelta(days=active_within_days)
        df = df[pd.to_datetime(df["last_event_date"]) >= cutoff]

    if division is not None:
        # Filter by most-recent division for each fighter
        f = add_division_to_fights(fights)
        recent_div = (
            f.sort_values("event_date")
             .melt(id_vars=["event_date", "division"],
                   value_vars=["fighter_a", "fighter_b"],
                   var_name="_", value_name="fighter")
             .dropna(subset=["fighter"])
             .groupby("fighter")["division"].last()
             .rename("division")
        )
        df = df.merge(recent_div, left_on="fighter", right_index=True, how="left")
        df = df[df["division"] == division]

    df = df.sort_values(rating_col, ascending=False).head(n).reset_index(drop=True)

    # Decorate with ToTT
    tott_cols = ["fighter", "height_inches", "weight_lb", "reach_inches", "stance"]
    tott = fighters[tott_cols].drop_duplicates(subset="fighter")
    df = df.merge(tott, on="fighter", how="left")

    df["rank"] = range(1, len(df) + 1)
    df["mu_canonical"] = df["mu_canonical"].round(1)
    df["phi_canonical"] = df["phi_canonical"].round(1)
    df["mu_method"] = df["mu_method"].round(1)
    for col in [
        "sustained_peak_headline_mu_whr", "five_year_peak_headline_mu_whr", "mu_whr",
        "sustained_peak_mu_canonical", "five_year_peak_mu_canonical",
        "sustained_peak_mu_method", "five_year_peak_mu_method",
        "sustained_peak_mu_method_integrity_performance",
        "five_year_peak_mu_method_integrity_performance",
        "mu_method_integrity", "delta_mu_method_integrity",
        "mu_method_performance", "delta_mu_method_performance",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(1)
    df["last_event_date"] = pd.to_datetime(df["last_event_date"]).dt.date

    display_cols = [
        "rank", "fighter", "mu_canonical", "phi_canonical",
        "gender", "career_division", "current_division", "recent_division",
        "sustained_peak_headline_mu_whr", "five_year_peak_headline_mu_whr",
        "sustained_peak_mu_method_integrity_performance",
        "five_year_peak_mu_method_integrity_performance",
        "sustained_peak_mu_canonical", "five_year_peak_mu_canonical",
        "rank_method_integrity", "mu_method_integrity", "delta_mu_method_integrity",
        "ped_confirmed_fights", "dq_wins", "missed_weight_wins",
        "mu_method", "rating_periods", "last_event_date",
        "height_inches", "weight_lb", "reach_inches", "stance",
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    return rename_rating_columns(df[display_cols])


# ---------------------------------------------------------------------------
# A2. Fighter detail card (returns a dict; notebook renders it)

def fighter_detail(
    fighter: str,
    fighters: pd.DataFrame,
    ratings_current: pd.DataFrame,
    fights: pd.DataFrame,
    fighter_dom: pd.DataFrame | None = None,
) -> dict:
    f = fighters[fighters["fighter"] == fighter]
    r = ratings_current[ratings_current["fighter"] == fighter]
    if f.empty and r.empty:
        return {"error": f"fighter not found: {fighter}"}

    rec = fighter_career_record(fighter, fights)
    out = {"fighter": fighter, "record": rec}

    if not f.empty:
        row = f.iloc[0]
        out["tale_of_the_tape"] = {
            "height_inches": row.get("height_inches"),
            "weight_lb":     row.get("weight_lb"),
            "reach_inches":  row.get("reach_inches"),
            "stance":        row.get("stance"),
            "dob":           row.get("dob"),
            "nickname":      row.get("nickname"),
        }
    if not r.empty:
        row = r.iloc[0]
        # 95% CI from phi: roughly mu ± 1.96 * phi
        def _opt_round(val, n=1):
            return None if val is None or pd.isna(val) else round(float(val), n)
        out["ratings"] = {
            "mu_canonical":                round(float(row["mu_canonical"]), 1),
            "phi_canonical":               round(float(row["phi_canonical"]), 1),
            "ci95_lower":                  round(float(row["mu_canonical"]) - 1.96 * float(row["phi_canonical"]), 1),
            "ci95_upper":                  round(float(row["mu_canonical"]) + 1.96 * float(row["phi_canonical"]), 1),
            "sustained_peak_mu_canonical": _opt_round(row.get("sustained_peak_mu_canonical")),
            "five_year_peak_mu_canonical": _opt_round(row.get("five_year_peak_mu_canonical")),
            "mu_method":                   round(float(row["mu_method"]), 1),
            "sustained_peak_mu_method":    _opt_round(row.get("sustained_peak_mu_method")),
            "five_year_peak_mu_method":    _opt_round(row.get("five_year_peak_mu_method")),
            "mu_method_integrity":         _opt_round(row.get("mu_method_integrity")),
            "mu_method_performance":       _opt_round(row.get("mu_method_performance")),
            "mu_method_integrity_performance": _opt_round(row.get("mu_method_integrity_performance")),
            "sustained_peak_mu_method_integrity_performance": _opt_round(row.get("sustained_peak_mu_method_integrity_performance")),
            "five_year_peak_mu_method_integrity_performance": _opt_round(row.get("five_year_peak_mu_method_integrity_performance")),
            "mu_whr":                      _opt_round(row.get("mu_whr")),
            "whr_rating":                  _opt_round(row.get("sustained_peak_headline_mu_whr")),
            "whr_rating_5yr":              _opt_round(row.get("five_year_peak_headline_mu_whr")),
            "ped_confirmed_fights":        int(row.get("ped_confirmed_fights", 0) or 0),
            "dq_wins":                     int(row.get("dq_wins", 0) or 0),
            "missed_weight_wins":          int(row.get("missed_weight_wins", 0) or 0),
            "rating_periods":              int(row["rating_periods"]),
            "last_event_date":             row.get("last_event_date"),
        }
    if fighter_dom is not None:
        d = fighter_dom[fighter_dom["fighter"] == fighter]
        if not d.empty:
            out["dominance"] = {
                "mean_dominance_in_wins": round(float(d.iloc[0]["mean_dominance"]), 2),
                "wins_with_dominance_calc": int(d.iloc[0]["wins"]),
            }
    return out


# ---------------------------------------------------------------------------
# B. Multi-fighter μ trajectory (with φ bands and optional method markers)

# Method colors for the markers (Tab B item #4)
METHOD_COLOR = {
    "KO/TKO":               "#fb7185",
    "Submission":           "#a78bfa",
    "Decision - Unanimous": "#34d399",
    "Decision - Majority":  "#22d3ee",
    "Decision - Split":     "#fbbf24",
    "DQ":                   "#94a3b8",
}

def trajectory_chart(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    fighters_to_plot: list[str],
    show_phi_band: bool = True,
    show_method_markers: bool = True,
    rating_col: str = "mu_canonical",
    phi_col: str = "phi_canonical",
) -> go.Figure:
    if ratings_history is None or ratings_history.empty:
        return _empty_figure("rating history unavailable", title="Rating trajectory")
    if rating_col not in ratings_history.columns:
        return _empty_figure(f"rating column not found: {rating_col}", title="Rating trajectory")

    fig = go.Figure()
    rating_name = _metric_label(rating_col)

    palette = CHART_COLORWAY

    fights_indexed = fights.copy() if fights is not None else pd.DataFrame()
    if not fights_indexed.empty and "event_date" in fights_indexed.columns:
        fights_indexed["event_date"] = pd.to_datetime(fights_indexed["event_date"], errors="coerce")
    appearances = (
        _fighter_fight_rows(fights_indexed)
        if show_method_markers and not fights_indexed.empty
        else pd.DataFrame(columns=["event_date", "fighter", "method_class"])
    )

    for i, fighter in enumerate(fighters_to_plot):
        h = ratings_history[ratings_history["fighter"] == fighter].copy()
        if h.empty:
            continue
        h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
        h = h.sort_values("event_date")
        color = palette[i % len(palette)]

        # phi band (1σ): mu ± phi
        if show_phi_band and phi_col in h.columns:
            upper = h[rating_col] + h[phi_col]
            lower = h[rating_col] - h[phi_col]
            fig.add_trace(go.Scatter(
                x=list(h["event_date"]) + list(h["event_date"])[::-1],
                y=list(upper) + list(lower)[::-1],
                fill="toself",
                fillcolor=_hex_to_rgba(color, 0.12),
                line=dict(color="rgba(0,0,0,0)"),
                hoverinfo="skip",
                showlegend=False,
                name=f"{fighter} uncertainty band",
            ))

        # μ line
        fig.add_trace(go.Scatter(
            x=h["event_date"], y=h[rating_col],
            mode="lines",
            name=fighter,
            line=dict(color=color, width=2),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{x|%Y-%m-%d}<br>"
                f"{rating_name}=%{{y:.1f}}<br>"
                "vs %{customdata[1]} opp(s) this event"
                "<extra></extra>"
            ),
            customdata=np.stack([
                [fighter] * len(h),
                h["opponents_this_event"].fillna(0).astype(int),
            ], axis=-1),
        ))

        # Method markers on the line (colored dots)
        if show_method_markers:
            # One marker per fighter-event rating row. If a fighter appears more than
            # once on a card, collapse the bout methods into a compact label.
            fighter_appearances = appearances[appearances["fighter"] == fighter]
            marker_events = (
                fighter_appearances.groupby(["event_date", "fighter"], as_index=False)
                .agg(method_class=("method_class", lambda s: ", ".join(s.dropna().astype(str).unique())))
            )
            marker_events["marker_method"] = marker_events["method_class"].str.split(", ").str[0]
            joined = h.merge(marker_events[["event_date", "fighter", "method_class", "marker_method"]],
                             on=["event_date", "fighter"], how="left")
            for method, dfm in joined.groupby("marker_method"):
                if pd.isna(method):
                    continue
                fig.add_trace(go.Scatter(
                    x=dfm["event_date"], y=dfm[rating_col],
                    mode="markers",
                    name=f"{fighter} – {method}",
                    marker=dict(size=8, color=METHOD_COLOR.get(method, "#000000"),
                                line=dict(color=color, width=1.5)),
                    showlegend=False,
                    customdata=dfm["method_class"],
                    hovertemplate=f"{fighter}<br>%{{customdata}}<br>%{{x|%Y-%m-%d}}<br>{rating_name}=%{{y:.1f}}<extra></extra>",
                ))

        # 5-Yr Peak annotation: simple visual guide; official peak columns
        # use opponent-quality top-N windows generated in ratings.peaks.
        peak_roll = h.set_index("event_date")[rating_col].rolling(
            f"{FIVE_YEAR_PEAK_WINDOW_DAYS}D",
            min_periods=FIVE_YEAR_PEAK_MIN_FIGHTS,
        ).mean()
        peak_idx = peak_roll.idxmax() if peak_roll.notna().any() else None
        if peak_idx is not None and not pd.isna(peak_idx):
            peak_row = h[h["event_date"] == peak_idx].iloc[-1]
            peak_value = float(peak_roll.loc[peak_idx])
            fig.add_annotation(
                x=peak_row["event_date"], y=peak_row[rating_col],
                text=f"{FIVE_YEAR_PEAK_WINDOW_LABEL} {peak_value:.0f}",
                showarrow=True, arrowhead=2, ax=0, ay=-30,
                font=dict(color=color, size=10),
            )

        end_row = h.iloc[-1]
        fig.add_annotation(
            x=end_row["event_date"],
            y=end_row[rating_col],
            text=fighter,
            showarrow=False,
            xanchor="left",
            xshift=8,
            font=dict(color=color, size=11),
        )

    if not fig.data:
        return _empty_figure("no selected fighters have rating history", title="Rating trajectory")

    _apply_chart_layout(fig, height=520)
    fig.update_layout(
        title=f"{rating_name} trajectory",
        xaxis_title="Event date",
        yaxis_title=rating_name,
        hovermode="closest",
        legend=dict(orientation="h", y=1.14, x=0, yanchor="bottom"),
        margin=dict(r=160),
    )
    return fig


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# C. Head-to-head prediction

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


# ---------------------------------------------------------------------------
# D. Weight-class strength of field over time

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
        yaxis_title="Mean canonical rating",
        hovermode="x unified",
    )
    return fig


def _division_strength_frame(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    rating_col: str,
    top_n_per_division: int = 15,
    divisions: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
) -> pd.DataFrame:
    if ratings_history is None or ratings_history.empty or fights is None or fights.empty:
        return pd.DataFrame(columns=["division", "year", "score", "fighters"])
    if rating_col not in ratings_history.columns:
        return pd.DataFrame(columns=["division", "year", "score", "fighters"])

    f = add_division_to_fights(fights)
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["year"] = f["event_date"].dt.year
    a = f[["year", "division", "fighter_a"]].rename(columns={"fighter_a": "fighter"})
    b = f[["year", "division", "fighter_b"]].rename(columns={"fighter_b": "fighter"})
    long = pd.concat([a, b], ignore_index=True).dropna(subset=["fighter", "division", "year"])
    if divisions:
        long = long[long["division"].isin(divisions)]
    if year_min is not None:
        long = long[long["year"] >= year_min]
    if year_max is not None:
        long = long[long["year"] <= year_max]
    if long.empty:
        return pd.DataFrame(columns=["division", "year", "score", "fighters"])

    rh = ratings_history.copy()
    rh["event_date"] = pd.to_datetime(rh["event_date"], errors="coerce")
    rh["year"] = rh["event_date"].dt.year
    rh[rating_col] = pd.to_numeric(rh[rating_col], errors="coerce")
    eoy = (
        rh.dropna(subset=[rating_col, "year"])
        .sort_values("event_date")
        .groupby(["fighter", "year"], as_index=False)
        .last()[["fighter", "year", rating_col]]
    )
    merged = long.merge(eoy, on=["fighter", "year"], how="inner").drop_duplicates(
        subset=["fighter", "year", "division"]
    )
    rows = []
    for (division, year), g in merged.groupby(["division", "year"], dropna=False):
        top = g.sort_values(rating_col, ascending=False).head(top_n_per_division)
        if len(top) < min(5, top_n_per_division):
            continue
        rows.append({
            "division": division,
            "year": int(year),
            "score": float(top[rating_col].mean()),
            "fighters": int(top["fighter"].nunique()),
        })
    return pd.DataFrame(rows).sort_values(["division", "year"]).reset_index(drop=True)


def division_strength_timeline_chart(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    rating_col: str,
    top_n_per_division: int = 15,
    divisions: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    indexed: bool = False,
) -> go.Figure:
    """Consulting-style comparison line chart for selected divisions over time."""
    plot_df = _division_strength_frame(
        ratings_history,
        fights,
        rating_col=rating_col,
        top_n_per_division=top_n_per_division,
        divisions=divisions,
        year_min=year_min,
        year_max=year_max,
    )
    if plot_df.empty:
        return _empty_figure("no selected divisions have enough rated fighters", title="Division strength")
    metric_label = _metric_label(rating_col)
    if indexed:
        plot_df = plot_df.copy()
        plot_df["score_raw"] = plot_df["score"]
        plot_df["score"] = plot_df.groupby("year")["score"].transform(
            lambda s: (s / s.max() * 100.0) if s.max() else s
        )
        y_title = "Strength index"
        title = f"Division strength index — top {top_n_per_division}"
        hover_score = "index=%{y:.1f}<br>rating=%{customdata[0]:.1f}"
    else:
        plot_df["score_raw"] = plot_df["score"]
        y_title = metric_label
        title = f"Division strength timeline — top {top_n_per_division}"
        hover_score = f"{metric_label}=%{{y:.1f}}"

    latest_year = int(plot_df["year"].max())
    latest = plot_df[plot_df["year"].eq(latest_year)].sort_values("score", ascending=False)
    subtitle = ""
    if not latest.empty:
        leader = latest.iloc[0]
        subtitle = f"Leader in {latest_year}: {leader['division']} ({leader['score']:.1f})"

    fig = go.Figure()
    for i, (division, dfd) in enumerate(plot_df.groupby("division", sort=False)):
        dfd = dfd.sort_values("year")
        fig.add_trace(go.Scatter(
            x=dfd["year"],
            y=dfd["score"],
            mode="lines+markers",
            name=str(division),
            line=dict(color=CHART_COLORWAY[i % len(CHART_COLORWAY)], width=2.5),
            marker=dict(size=7),
            customdata=np.stack([
                dfd["score_raw"].round(1).astype("string"),
                dfd["fighters"].astype(int).astype("string"),
            ], axis=-1),
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "year=%{x}<br>"
                f"{hover_score}<br>"
                "fighters=%{customdata[1]}<extra></extra>"
            ),
        ))
        end = dfd.iloc[-1]
        fig.add_annotation(
            x=end["year"],
            y=end["score"],
            text=str(division),
            showarrow=False,
            xanchor="left",
            xshift=8,
            font=dict(color=CHART_COLORWAY[i % len(CHART_COLORWAY)], size=11),
        )
    _apply_chart_layout(fig, height=560)
    fig.update_layout(
        title={"text": f"{title}<br><sup>{subtitle}</sup>" if subtitle else title},
        xaxis_title="Year",
        yaxis_title=y_title,
        hovermode="x unified",
        margin=dict(r=170),
        legend=dict(orientation="h", y=-0.22),
    )
    return fig


def division_year_top_fighters_chart(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    rating_col: str,
    year: int,
    divisions: list[str] | None = None,
    top_n: int = 5,
) -> go.Figure:
    """Single-year snapshot showing the actual top-N fighters per division.

    Replaces the old "one bar per division aggregate" view (which the user
    found unreadable) with a horizontal bar per *fighter*, grouped by division
    so each weight class reads as its own mini-leaderboard. Top of each block
    is the year's #1 in that class.
    """
    title = f"{year} division ranking — top {top_n} per class"
    if ratings_history is None or ratings_history.empty or fights is None or fights.empty:
        return _empty_figure("ratings unavailable", title=title)
    if rating_col not in ratings_history.columns:
        return _empty_figure(f"{rating_col!r} not in history", title=title)

    f = add_division_to_fights(fights)
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["year"] = f["event_date"].dt.year
    a = f[["year", "division", "fighter_a"]].rename(columns={"fighter_a": "fighter"})
    b = f[["year", "division", "fighter_b"]].rename(columns={"fighter_b": "fighter"})
    long = pd.concat([a, b], ignore_index=True).dropna(subset=["fighter", "division", "year"])
    long = long[long["year"].eq(year)]
    if divisions:
        long = long[long["division"].isin(divisions)]
    if long.empty:
        return _empty_figure(f"no fighters in the selected classes in {year}", title=title)

    rh = ratings_history.copy()
    rh["event_date"] = pd.to_datetime(rh["event_date"], errors="coerce")
    rh["year"] = rh["event_date"].dt.year
    rh[rating_col] = pd.to_numeric(rh[rating_col], errors="coerce")
    eoy = (
        rh.dropna(subset=[rating_col, "year"])
        .sort_values("event_date")
        .groupby(["fighter", "year"], as_index=False)
        .last()[["fighter", "year", rating_col]]
    )
    merged = long.merge(eoy, on=["fighter", "year"], how="inner").drop_duplicates(
        subset=["fighter", "year", "division"]
    )
    if merged.empty:
        return _empty_figure(f"no rated fighters in the selected classes in {year}", title=title)

    # Order divisions by their #1 fighter (strongest division on top); within a
    # division order by rating ascending so the top fighter appears at the top
    # of its block when the y-axis is reversed.
    top_per_div = (
        merged.sort_values(rating_col, ascending=False)
        .groupby("division", as_index=False)
        .head(top_n)
        .copy()
    )
    div_order = (
        top_per_div.groupby("division")[rating_col].max().sort_values(ascending=False).index.tolist()
    )
    if divisions:
        # Honor the caller's order when they pinned a selection (matches the
        # other division charts).
        div_order = [d for d in divisions if d in div_order] + [d for d in div_order if d not in divisions]

    fig = go.Figure()
    rating_name = _metric_label(rating_col)
    y_labels: list[str] = []
    for division in div_order:
        block = top_per_div[top_per_div["division"].eq(division)].sort_values(rating_col, ascending=False)
        if block.empty:
            continue
        div_short = DIV_SHORT.get(division, division)
        labels = [f"{i+1}. {fighter}  ·  {div_short}" for i, fighter in enumerate(block["fighter"].tolist())]
        fig.add_trace(go.Bar(
            x=block[rating_col].astype(float),
            y=labels,
            orientation="h",
            name=div_short,
            text=[f"{v:.0f}" for v in block[rating_col]],
            textposition="outside",
            hovertemplate=(
                f"<b>%{{y}}</b><br>{rating_name}=%{{x:.1f}}<extra></extra>"
            ),
        ))
        y_labels.extend(labels)
    # Reverse so the strongest division and #1 within it sit at the top.
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(y_labels)))
    height = max(380, 34 * len(y_labels) + 80)
    _apply_chart_layout(fig, height=height)
    fig.update_layout(
        title=title,
        xaxis_title=rating_name,
        yaxis_title="",
        barmode="stack",
        legend=dict(orientation="h", y=-0.18, font=dict(size=11)),
        margin=dict(l=220, r=80, t=70, b=80),
        showlegend=True,
    )
    fig.update_xaxes(range=[1300, 1700])
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


# ---------------------------------------------------------------------------
# E. Striker vs grappler scatter

def striker_grappler_scatter(
    rounds: pd.DataFrame,
    fights: pd.DataFrame,
    ratings_current: pd.DataFrame,
    fighters: pd.DataFrame,
    division: str | None = None,
    min_fights: int = 5,
) -> go.Figure:
    """For each fighter: SLpM vs TD/15min, sized by μ_canonical, colored by stance."""
    r = rounds.copy()
    f = add_division_to_fights(fights)
    if division is not None:
        f = f[f["division"] == division]
        valid_urls = set(f["fight_url"])
        r = r[r["fight_url"].isin(valid_urls)]

    # Sum per fighter
    agg = r.groupby("fighter").agg(
        sig_str_landed=("sig_str_landed", "sum"),
        td_landed=("td_landed", "sum"),
        sub_att=("sub_att", "sum"),
        ctrl_seconds=("ctrl_seconds", "sum"),
    ).reset_index()

    # Fight time comes from the bout ending fields. Count one duration per fighter
    # appearance so a 0:30 first-round finish is 0.5 minutes, not a full round.
    f_time = f.dropna(subset=["fight_url"]).copy()
    f_time["duration_seconds"] = _fight_duration_seconds(f_time)
    fight_time = (
        _fighter_fight_rows(f_time)
        .merge(f_time[["fight_url", "duration_seconds"]], on="fight_url", how="left")
        .groupby("fighter")["duration_seconds"].sum(min_count=1)
        .rename("seconds_fought")
        .reset_index()
    )
    fallback_time = (
        r.groupby("fighter").size().mul(300).rename("fallback_seconds").reset_index()
    )
    agg = agg.merge(fight_time, on="fighter", how="left")
    agg = agg.merge(fallback_time, on="fighter", how="left")
    agg["seconds_fought"] = agg["seconds_fought"].fillna(agg["fallback_seconds"])
    agg["minutes_fought"] = agg["seconds_fought"] / 60.0
    agg["slpm"] = agg["sig_str_landed"] / agg["minutes_fought"].replace(0, np.nan)
    agg["td_per_15"] = agg["td_landed"] / (agg["minutes_fought"] / 15.0).replace(0, np.nan)

    # Filter by min fights (approx: rounds >= min_fights * 1)
    fight_counts = (pd.concat([f[["fighter_a"]].rename(columns={"fighter_a": "fighter"}),
                               f[["fighter_b"]].rename(columns={"fighter_b": "fighter"})])
                      .groupby("fighter").size().rename("n_fights").reset_index())
    agg = agg.merge(fight_counts, on="fighter", how="left")
    agg = agg[agg["n_fights"] >= min_fights]

    # Join μ and stance
    agg = agg.merge(ratings_current[["fighter", "mu_canonical"]], on="fighter", how="inner")
    agg = agg.merge(fighters[["fighter", "stance"]], on="fighter", how="left")
    agg = agg.dropna(subset=["slpm", "td_per_15", "mu_canonical"])

    stance_colors = {
        "Orthodox": "#1f77b4", "Southpaw": "#d62728", "Switch": "#2ca02c",
        "Open Stance": "#9467bd", None: "#7f7f7f",
    }
    agg["color"] = agg["stance"].map(stance_colors).fillna("#7f7f7f")
    agg["size_norm"] = ((agg["mu_canonical"] - 1200) / 30).clip(lower=4, upper=40)

    fig = go.Figure()
    for stance, g in agg.groupby("stance", dropna=False):
        fig.add_trace(go.Scatter(
            x=g["slpm"], y=g["td_per_15"],
            mode="markers",
            name=str(stance) if not pd.isna(stance) else "Unknown",
            marker=dict(
                size=g["size_norm"],
                color=stance_colors.get(stance, "#7f7f7f"),
                opacity=0.6,
                line=dict(width=0.5, color="white"),
            ),
            customdata=np.stack([
                g["fighter"],
                g["mu_canonical"].round(0).astype(int).astype(str),
                g["n_fights"].astype("Int64").astype("string"),
            ], axis=-1),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "canonical rating=%{customdata[1]}<br>"
                "fights=%{customdata[2]}<br>"
                "SLpM=%{x:.2f}<br>"
                "TD/15=%{y:.2f}<extra></extra>"
            ),
        ))

    title_suffix = f" — {division}" if division else " — all divisions"
    _apply_chart_layout(fig, height=560)
    fig.update_layout(
        title=f"Striking pace vs wrestling volume{title_suffix}",
        xaxis_title="Significant strikes landed per minute (SLpM)",
        yaxis_title="Takedowns per 15 min (TD/15)",
    )
    return fig


# ---------------------------------------------------------------------------
# F. Calibration plot

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
        name="perfect calibration", showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=grouped["predicted_mid"], y=grouped["empirical"],
        mode="markers+lines",
        marker=dict(size=grouped["n"].clip(lower=8, upper=30), color="#1f77b4"),
        name="empirical",
        text=[f"n={int(n)}" for n in grouped["n"]],
        hovertemplate="predicted=%{x:.2f}<br>actual=%{y:.2f}<br>%{text}<extra></extra>",
    ))
    _apply_chart_layout(fig, height=520)
    fig.update_layout(
        title=f"Prediction calibration: Brier={brier:.4f}, bouts={len(df):,}",
        xaxis_title="Predicted P(A wins)",
        yaxis_title="Empirical win rate",
        xaxis=dict(range=[0, 1]),
        yaxis=dict(range=[0, 1]),
    )
    return fig


# ---------------------------------------------------------------------------
# V2. Cross-source and database-backed insight builders

def _current_rank_frame(ratings_current: pd.DataFrame, min_fights: int = 3) -> pd.DataFrame:
    rc = ratings_current.copy()
    rc["rating_periods"] = pd.to_numeric(rc.get("rating_periods"), errors="coerce")
    rc = rc[rc["rating_periods"] >= min_fights].copy()
    rc["glicko_rank"] = rc["mu_canonical"].rank(method="min", ascending=False).astype("Int64")
    rc["_name_key"] = rc["fighter"].apply(_name_key)
    return rc


def glicko_fightmatrix_scatter(
    ratings_current: pd.DataFrame,
    fightmatrix_rankings: pd.DataFrame,
    min_fights: int = 3,
    label_outliers: int = 12,
) -> go.Figure:
    """Current UFC Glicko mu vs FightMatrix points for matched fighters."""
    rc = _current_rank_frame(ratings_current, min_fights=min_fights)
    fm = fightmatrix_best_rankings(fightmatrix_rankings)
    merged = rc.merge(fm, on="_name_key", how="inner", suffixes=("_ufc", "_fm"))
    merged = merged.dropna(subset=["mu_canonical", "fightmatrix_points"])
    if merged.empty:
        return _empty_figure("no matched Glicko/FightMatrix fighters", title="Our ratings vs FightMatrix")

    x = pd.to_numeric(merged["mu_canonical"], errors="coerce")
    y = pd.to_numeric(merged["fightmatrix_points"], errors="coerce")
    if len(merged) >= 3 and x.nunique() > 1:
        slope, intercept = np.polyfit(x, y, 1)
        merged["fm_residual"] = y - (slope * x + intercept)
    else:
        merged["fm_residual"] = 0.0
    labeled = merged.reindex(merged["fm_residual"].abs().sort_values(ascending=False).head(label_outliers).index)

    fig = go.Figure()
    for division, g in merged.groupby("fightmatrix_division", dropna=False):
        fig.add_trace(go.Scatter(
            x=g["mu_canonical"],
            y=g["fightmatrix_points"],
            mode="markers",
            name=str(division),
            marker=dict(size=9, opacity=0.72),
            customdata=np.stack([
                g["fighter_ufc"],
                g["glicko_rank"].astype("string"),
                g["fightmatrix_rank"].astype("string"),
                g["record"].fillna(""),
            ], axis=-1),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Glicko mu=%{x:.1f} (rank %{customdata[1]})<br>"
                "FightMatrix points=%{y:.0f} (rank %{customdata[2]})<br>"
                "FM record=%{customdata[3]}<extra></extra>"
            ),
        ))
    if not labeled.empty:
        fig.add_trace(go.Scatter(
            x=labeled["mu_canonical"],
            y=labeled["fightmatrix_points"],
            mode="text",
            text=labeled["fighter_ufc"],
            textposition="top center",
            showlegend=False,
            hoverinfo="skip",
        ))
    _apply_chart_layout(fig, height=560)
    fig.update_layout(
        title="Our current rating vs FightMatrix points",
        xaxis_title="Canonical UFC rating",
        yaxis_title="FightMatrix points",
        legend=dict(orientation="h", y=-0.25),
    )
    return fig


def rank_delta_table(
    ratings_current: pd.DataFrame,
    fightmatrix_rankings: pd.DataFrame,
    min_fights: int = 3,
    limit: int = 50,
) -> pd.DataFrame:
    """Compare canonical Glicko rank, method-integrity rank, and FightMatrix rank."""
    rc = _current_rank_frame(ratings_current, min_fights=min_fights)
    fm = fightmatrix_best_rankings(fightmatrix_rankings)
    df = rc.merge(fm, on="_name_key", how="left", suffixes=("", "_fm"))
    df["rank_method_integrity"] = pd.to_numeric(df.get("rank_method_integrity"), errors="coerce")
    df["integrity_rank_delta"] = df["rank_method_integrity"] - df["glicko_rank"].astype(float)
    df["glicko_vs_fm_rank_delta"] = df["glicko_rank"].astype(float) - df["fightmatrix_rank"]
    df["abs_compare_delta"] = df[["integrity_rank_delta", "glicko_vs_fm_rank_delta"]].abs().max(axis=1)
    df = df.sort_values(["abs_compare_delta", "mu_canonical"], ascending=[False, False]).head(limit)
    cols = [
        "fighter", "glicko_rank", "mu_canonical", "rank_method_integrity",
        "delta_mu_method_integrity", "ped_confirmed_fights", "dq_wins",
        "missed_weight_wins", "fightmatrix_rank",
        "fightmatrix_points", "fightmatrix_division", "glicko_vs_fm_rank_delta",
        "integrity_rank_delta",
    ]
    cols = [c for c in cols if c in df.columns]
    out = df[cols].copy()
    for col in ["mu_canonical", "delta_mu_method_integrity", "fightmatrix_points",
                "glicko_vs_fm_rank_delta", "integrity_rank_delta"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(1)
    return out.reset_index(drop=True)


def source_coverage_summary(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Summarize source row counts, columns, date ranges, and fighter coverage."""
    table_labels = [
        ("events", "Greco canonical events"),
        ("fights", "Greco canonical fights"),
        ("rounds", "Greco canonical rounds"),
        ("fighters", "Greco canonical fighters"),
        ("ratings_current", "Current ratings"),
        ("datalab_bouts_all", "DataLab bouts all"),
        ("datalab_merged_stats_scorecards", "DataLab merged stats/scorecards"),
        ("datalab_fighter_details", "DataLab fighter details"),
        ("datalab_scorecards", "DataLab scorecards"),
        ("fightmatrix_rankings", "FightMatrix rankings"),
    ]
    rows = []
    for key, label in table_labels:
        df = data.get(key)
        if df is None or df.empty:
            rows.append({"key": key, "table": label, "rows": 0, "columns": 0})
            continue
        min_date, max_date = _date_range(df)
        fighter_count = None
        if "fighter" in df.columns:
            fighter_count = int(df["fighter"].dropna().nunique())
        elif "fighter_name" in df.columns:
            fighter_count = int(df["fighter_name"].dropna().nunique())
        elif {"fighter_a", "fighter_b"}.issubset(df.columns):
            fighter_count = int(pd.concat([df["fighter_a"], df["fighter_b"]]).dropna().nunique())
        elif {"red_fighter_name", "blue_fighter_name"}.issubset(df.columns):
            fighter_count = int(pd.concat([df["red_fighter_name"], df["blue_fighter_name"]]).dropna().nunique())
        rows.append({
            "key": key,
            "table": label,
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "unique_fighters": fighter_count,
            "min_date": min_date,
            "max_date": max_date,
        })
    return pd.DataFrame(rows)


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


def ped_impact_chart(ratings_current: pd.DataFrame, n: int = 15) -> go.Figure:
    """Top movers under the method-integrity sleeve vs the plain method baseline."""
    df = ratings_current.copy()
    if "delta_mu_method_integrity" not in df.columns:
        return _empty_figure("method-integrity columns not present", title="Integrity sleeve impact")
    df["delta_mu_method_integrity"] = pd.to_numeric(df["delta_mu_method_integrity"], errors="coerce")
    df = df.dropna(subset=["delta_mu_method_integrity"])
    df = df[df["delta_mu_method_integrity"].abs() > 0.01]
    if df.empty:
        return _empty_figure("no integrity-sleeve rating movement", title="Integrity sleeve impact")
    movers = pd.concat([
        df.sort_values("delta_mu_method_integrity", ascending=True).head(n),
        df.sort_values("delta_mu_method_integrity", ascending=False).head(n),
    ]).drop_duplicates("fighter")
    movers = movers.sort_values("delta_mu_method_integrity")
    colors = np.where(movers["delta_mu_method_integrity"] >= 0, SIGN_COLORS["positive"], SIGN_COLORS["negative"])
    fig = go.Figure(go.Bar(
        x=movers["delta_mu_method_integrity"],
        y=movers["fighter"],
        orientation="h",
        marker_color=colors,
        customdata=np.stack([
            movers.get("mu_method", pd.Series(index=movers.index)).round(1).astype("string"),
            movers.get("mu_method_integrity", pd.Series(index=movers.index)).round(1).astype("string"),
            movers.get("ped_confirmed_fights", pd.Series(index=movers.index)).astype("string"),
        ], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "delta=%{x:.1f}<br>"
            "method=%{customdata[0]}<br>"
            "method+integrity=%{customdata[1]}<br>"
            "confirmed PED fights=%{customdata[2]}<extra></extra>"
        ),
    ))
    _apply_chart_layout(fig, height=max(480, 24 * len(movers)))
    fig.update_layout(
        title="Largest integrity-sleeve rating impacts",
        xaxis_title="Rating movement vs method baseline",
        yaxis_title="Fighter",
    )
    return fig


def sustained_peak_leaderboard_chart(
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
            for col in (
                "sustained_peak_headline_mu_whr",
                "sustained_peak_mu_method_integrity_performance",
                "five_year_peak_mu_method_integrity_performance",
                "five_year_peak_mu_canonical",
            )
            if col in df.columns
        ),
        "five_year_peak_mu_canonical",
    )
    df = df[df["rating_periods"] >= min_fights].dropna(subset=[peak_col])
    df = df.sort_values(peak_col, ascending=False).head(n)
    if df.empty:
        return _empty_figure("no sustained peak data", title="Sustained peak leaderboard")
    five_col = next(
        (
            col
            for col in (
                "five_year_peak_headline_mu_whr",
                "five_year_peak_mu_method_integrity_performance",
                "five_year_peak_mu_canonical",
            )
            if col in df.columns
        ),
        "five_year_peak_mu_canonical",
    )
    fig = go.Figure(go.Bar(
        x=df[peak_col],
        y=df["fighter"],
        orientation="h",
        marker_color=STREAM_PALETTE["method"] if "method_integrity_performance" in peak_col else STREAM_PALETTE["canonical"],
        customdata=np.stack([
            df[five_col].round(1).astype("string"),
            df["rating_periods"].astype("Int64").astype("string"),
        ], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            f"{SUSTAINED_PEAK_WINDOW_LABEL}=%{{x:.1f}}<br>"
            f"{FIVE_YEAR_PEAK_WINDOW_LABEL}=%{{customdata[0]}}<br>"
            "rating periods=%{customdata[1]}<extra></extra>"
        ),
    ))
    _apply_chart_layout(fig, height=max(520, 24 * len(df)))
    fig.update_layout(
        title=f"Top {n} {SUSTAINED_PEAK_WINDOW_LABEL} ratings ({rating_label(peak_col)})",
        xaxis_title=rating_label(peak_col),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def division_strength_comparison_chart(
    ratings_current: pd.DataFrame,
    fights: pd.DataFrame,
    fightmatrix_rankings: pd.DataFrame,
    top_n: int = 15,
    min_fights: int = 3,
) -> go.Figure:
    rc = _current_rank_frame(ratings_current, min_fights=min_fights)
    recent_div = recent_division_by_fighter(fights).rename(columns={"division": "_recent_division"})
    ufc = rc.merge(recent_div, on="fighter", how="left")
    # Bucket by career division — where the bulk of the UFC career happened —
    # so fighters surface under the class they made their name in (Makhachev
    # under Lightweight, GSP under Welterweight) regardless of a recent
    # cameo. Fall back to recent division only when career isn't known.
    home = ufc["career_division"] if "career_division" in ufc.columns else pd.Series(pd.NA, index=ufc.index)
    ufc["division"] = home.fillna(ufc["_recent_division"])
    ufc = ufc.dropna(subset=["division"])
    ufc_rows = []
    for division, group in ufc.groupby("division"):
        top = group.sort_values("mu_canonical", ascending=False).head(top_n)
        if len(top) >= 3:
            ufc_rows.append({"division": division, "mean_top_mu": top["mu_canonical"].mean(), "ufc_count": len(top)})
    ufc_strength = pd.DataFrame(ufc_rows)

    fm = fightmatrix_rankings.copy()
    if not fm.empty:
        fm["division"] = fm["division"].map(FIGHTMATRIX_DIVISION_MAP)
        fm["points"] = pd.to_numeric(fm["points"], errors="coerce")
        fm["rank"] = pd.to_numeric(fm["rank"], errors="coerce")
        fm = fm.dropna(subset=["division", "points", "rank"])
        fm_rows = []
        for division, group in fm.groupby("division"):
            top = group.sort_values("rank").head(top_n)
            if len(top) >= 3:
                fm_rows.append({"division": division, "mean_fm_points": top["points"].mean(), "fm_count": len(top)})
        fm_strength = pd.DataFrame(fm_rows)
    else:
        fm_strength = pd.DataFrame(columns=["division", "mean_fm_points", "fm_count"])

    merged = ufc_strength.merge(fm_strength, on="division", how="outer").sort_values("division")
    if merged.empty:
        return _empty_figure("no division strength data", title="Division strength comparison")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=merged["division"],
            y=merged["mean_top_mu"],
            name=f"UFC Glicko top-{top_n} mean",
            marker_color=STREAM_PALETTE["canonical"],
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=merged["division"],
            y=merged["mean_fm_points"],
            name=f"FightMatrix top-{top_n} mean points",
            mode="lines+markers",
            line=dict(color=STREAM_PALETTE["ped_adjusted"], width=3),
        ),
        secondary_y=True,
    )
    _apply_chart_layout(fig, height=560)
    fig.update_layout(
        title="Division strength: UFC Glicko and FightMatrix",
        xaxis_title="Division",
        legend=dict(orientation="h", y=-0.22),
    )
    fig.update_yaxes(title_text="Mean UFC Glicko mu", secondary_y=False)
    fig.update_yaxes(title_text="Mean FightMatrix points", secondary_y=True)
    return fig


def top_fighter_placement_scatter(
    ratings_current: pd.DataFrame,
    *,
    rating_col: str = "sustained_peak_headline_mu_whr",
    n: int = 100,
    min_fights: int = 0,
) -> go.Figure:
    """Top-fighter placement: résumé depth vs rating, colored by career division.

    Top-right is the holy grail — an elite rating built over a long, proven
    résumé, not a hot 3-fight start. The top six fighters get their names on
    the chart; ranks #1–#10 get a numbered chip; everyone else is a sized dot
    you can hover for details.
    """
    if ratings_current is None or ratings_current.empty:
        return _empty_figure("ratings unavailable", title="Top fighter placement")
    df = ratings_current.copy()
    if rating_col not in df.columns:
        rating_col = "mu_canonical" if "mu_canonical" in df.columns else None
    if rating_col is None:
        return _empty_figure("no rating column available", title="Top fighter placement")
    df["rating_periods"] = pd.to_numeric(df.get("rating_periods"), errors="coerce").fillna(0)
    df = df[df["rating_periods"] >= min_fights].dropna(subset=[rating_col])
    df = df.sort_values(rating_col, ascending=False).head(n).reset_index(drop=True)
    if df.empty:
        return _empty_figure("no fighters match the current filters", title="Top fighter placement")
    df["division_display"] = df.get("career_division", df.get("recent_division", "")).fillna("Unknown")
    df["rank"] = np.arange(1, len(df) + 1)
    df["rating_display"] = pd.to_numeric(df[rating_col], errors="coerce")
    rating_name = _metric_label(rating_col)
    fig = go.Figure()
    # Stable color order = stable division legend across redraws. Sort by mean
    # rating so the strongest division leads the legend.
    division_order = (
        df.groupby("division_display")["rating_display"].mean().sort_values(ascending=False).index.tolist()
    )
    for division in division_order:
        g = df[df["division_display"].eq(division)]
        fig.add_trace(go.Scatter(
            x=g["rating_periods"],
            y=g["rating_display"],
            mode="markers",
            name=str(division),
            marker=dict(
                # Top-10 markers are bigger so they read at a glance; the long
                # tail is uniformly small to avoid the old "every dot fights for
                # space" cluster.
                size=np.where(g["rank"].le(10), 16, 9),
                opacity=0.82,
                line=dict(color="white", width=0.8),
            ),
            customdata=np.stack([
                g["rank"].astype(int).astype(str),
                g["fighter"],
                g["division_display"].astype(str),
                pd.to_datetime(g.get("last_event_date"), errors="coerce").dt.date.astype("string"),
            ], axis=-1),
            hovertemplate=(
                "<b>#%{customdata[0]} %{customdata[1]}</b><br>"
                "division=%{customdata[2]}<br>"
                "rated fights=%{x}<br>"
                f"{rating_name}=%{{y:.1f}}<br>"
                "last fight=%{customdata[3]}<extra></extra>"
            ),
        ))
    # Numbered chips for the top 10.
    for row in df.head(10).itertuples(index=False):
        is_leader = int(row.rank) == 1
        fig.add_annotation(
            x=row.rating_periods,
            y=row.rating_display,
            text=str(int(row.rank)),
            showarrow=False,
            font=dict(size=10, color=THEME["bg"] if is_leader else THEME["text"]),
            bgcolor=THEME["accent"] if is_leader else THEME["surface"],
            bordercolor=THEME["border_strong"],
            borderpad=2,
        )
    # Names for the top 6 (anchored to one side so labels don't collide with
    # each other or with the chip).
    for i, row in enumerate(df.head(6).itertuples(index=False)):
        fig.add_annotation(
            x=row.rating_periods,
            y=row.rating_display,
            text=str(row.fighter),
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            xshift=14,
            yshift=10 if i % 2 == 0 else -10,
            font=dict(size=11, color=THEME["text"]),
        )
    _apply_chart_layout(fig, height=560)
    fig.update_layout(
        title=f"Top {len(df)} placement — {rating_name}",
        xaxis_title="Rated bouts",
        yaxis_title=rating_name,
        legend=dict(orientation="h", y=-0.22, font=dict(size=11)),
        margin=dict(l=80, r=40, t=70, b=110),
    )
    fig.update_xaxes(rangemode="tozero")
    return fig


def top100_division_density_chart(
    ratings_current: pd.DataFrame,
    *,
    rating_col: str = "sustained_peak_headline_mu_whr",
    n: int = 100,
) -> go.Figure:
    """Share of the top-N occupied by each division."""
    if ratings_current is None or ratings_current.empty:
        return _empty_figure("ratings unavailable", title="Top-100 division density")
    df = ratings_current.copy()
    if rating_col not in df.columns:
        rating_col = "mu_canonical" if "mu_canonical" in df.columns else None
    if rating_col is None:
        return _empty_figure("no rating column available", title="Top-100 division density")
    df = df.dropna(subset=[rating_col]).sort_values(rating_col, ascending=False).head(n)
    if df.empty:
        return _empty_figure("no top-fighter rows available", title="Top-100 division density")
    df["division"] = df.get("career_division", df.get("recent_division", "")).fillna("Unknown")
    density = (
        df.groupby("division", as_index=False)
        .agg(fighters=("fighter", "nunique"), avg_score=(rating_col, "mean"))
        .sort_values(["fighters", "avg_score"], ascending=[True, True])
    )
    density["share_pct"] = (density["fighters"] / len(df) * 100).round(1)
    fig = go.Figure(go.Bar(
        x=density["share_pct"],
        y=density["division"],
        orientation="h",
        marker_color=STREAM_PALETTE["method"],
        text=density["share_pct"].map(lambda v: f"{v:.1f}%"),
        textposition="outside",
        customdata=np.stack([
            density["fighters"].astype(int).astype(str),
            density["avg_score"].round(1).astype("string"),
        ], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "%{customdata[0]} fighters in top group<br>"
            "%{x:.1f}% of top group<br>"
            "average score=%{customdata[1]}<extra></extra>"
        ),
    ))
    _apply_chart_layout(fig, height=max(420, 30 * len(density)))
    fig.update_layout(
        title=f"Division share inside top {len(df)}",
        xaxis_title="Share",
        yaxis_title="Division",
        showlegend=False,
    )
    fig.update_xaxes(ticksuffix="%")
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


def yearly_rating_delta_scatter(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    rating_col: str,
    year: int,
) -> go.Figure:
    """Per-fighter cumulative rating delta for all fights in a year.

    One dot per fighter sorted by total delta (fallers left, risers right).
    y = net rating change for the year, with a zero-line at center.
    Hover shows each individual fight with opponent, result, and per-fight Δ.
    """
    title = f"{year} — rating moves"
    if ratings_history is None or ratings_history.empty:
        return _empty_figure("rating history unavailable", title=title)
    if rating_col not in ratings_history.columns:
        return _empty_figure(f"{rating_col!r} not in history", title=title)

    rh = ratings_history.copy()
    rh["event_date"] = pd.to_datetime(rh["event_date"], errors="coerce")
    rh["_year"] = rh["event_date"].dt.year
    rh[rating_col] = pd.to_numeric(rh[rating_col], errors="coerce")

    year_rows = rh[rh["_year"] == year].dropna(subset=[rating_col]).copy()
    year_rows = year_rows.sort_values(["fighter", "event_date"])
    if year_rows.empty:
        return _empty_figure(f"no rating data for {year}", title=title)

    # Last rating each fighter had before the year starts (their baseline)
    before = (
        rh[rh["_year"] < year]
        .dropna(subset=[rating_col])
        .sort_values("event_date")
        .groupby("fighter", as_index=False)
        .last()[["fighter", rating_col]]
        .rename(columns={rating_col: "_mu_start"})
    )
    year_rows = year_rows.merge(before, on="fighter", how="left")
    # Per-fight previous rating: shift within fighter group, fall back to baseline
    year_rows["_mu_prev"] = year_rows.groupby("fighter")[rating_col].shift(1)
    year_rows["_mu_prev"] = year_rows["_mu_prev"].fillna(year_rows["_mu_start"])
    year_rows = year_rows.dropna(subset=["_mu_prev"])
    year_rows["_fight_delta"] = year_rows[rating_col] - year_rows["_mu_prev"]

    # Opponent and result from canonical fights
    if fights is not None and not fights.empty:
        fdf = fights.copy()
        fdf["event_date"] = pd.to_datetime(fdf["event_date"], errors="coerce")
        fdf = fdf[fdf["event_date"].dt.year == year]
        fa = fdf[["fight_url", "event_date", "fighter_a", "fighter_b", "winner"]].rename(
            columns={"fighter_a": "fighter", "fighter_b": "opponent"})
        fb = fdf[["fight_url", "event_date", "fighter_a", "fighter_b", "winner"]].rename(
            columns={"fighter_b": "fighter", "fighter_a": "opponent"})
        fl = pd.concat([fa, fb], ignore_index=True)
        fl["_result"] = np.where(fl["winner"].eq(fl["fighter"]), "W", "L")
        joined = year_rows.merge(
            fl[["fighter", "event_date", "opponent", "_result"]],
            on=["fighter", "event_date"], how="left"
        )
    else:
        joined = year_rows.copy()
        joined["opponent"] = pd.NA
        joined["_result"] = pd.NA

    # Aggregate per fighter
    rows = []
    for fighter, g in joined.groupby("fighter"):
        total = float(g["_fight_delta"].sum())
        lines = []
        for _, row in g.sort_values("event_date").iterrows():
            opp = str(row.get("opponent") or "?")
            res = str(row.get("_result") or "?")
            d = float(row["_fight_delta"])
            lines.append(f"vs {opp}  {res}  Δ{d:+.1f}")
        rows.append({
            "fighter": fighter,
            "total_delta": total,
            "n_fights": len(g),
            "hover_lines": "<br>".join(lines),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return _empty_figure(f"no qualified fighters in {year}", title=title)
    df = df.sort_values("total_delta").reset_index(drop=True)
    df["x_idx"] = np.arange(len(df))
    colors = np.where(df["total_delta"] >= 0, THEME["positive"], THEME["negative"])

    fig = go.Figure(go.Scatter(
        x=df["x_idx"],
        y=df["total_delta"],
        mode="markers",
        marker=dict(size=9, color=colors.tolist(), opacity=0.85, line=dict(color="white", width=0.6)),
        customdata=np.column_stack([
            df["fighter"].values,
            df["hover_lines"].values,
            df["n_fights"].astype(str).values,
        ]),
        hovertemplate=(
            "<b>%{customdata[0]}</b> (%{customdata[2]} fights)<br>"
            "%{customdata[1]}<br>"
            "<b>Total Δ%{y:+.1f}</b><extra></extra>"
        ),
        showlegend=False,
    ))

    # Label biggest risers and fallers (last-name only to save space)
    label_n = min(6, max(1, len(df) // 8))
    for row in pd.concat([df.tail(label_n), df.head(label_n)]).drop_duplicates("fighter").itertuples():
        name_short = str(row.fighter).split()[-1]
        fig.add_annotation(
            x=row.x_idx, y=row.total_delta,
            text=name_short,
            showarrow=False,
            yshift=13 if row.total_delta >= 0 else -13,
            font=dict(size=9, color=THEME["text_2"]),
        )

    fig.add_hline(y=0, line_color=THEME["border_strong"], line_width=1.5)
    _apply_chart_layout(fig, height=460)
    fig.update_layout(
        title=title,
        xaxis=dict(visible=False),
        yaxis_title=f"Δ {_metric_label(rating_col)}",
        hovermode="closest",
    )
    return fig


def era_heatmap_chart(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    top_n: int = 15,
    divisions: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
) -> go.Figure:
    """Heatmap of year x division mean mu_canonical among top-N fighters."""
    f = add_division_to_fights(fights)
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["year"] = f["event_date"].dt.year
    a = f[["event_date", "division", "fighter_a"]].rename(columns={"fighter_a": "fighter"})
    b = f[["event_date", "division", "fighter_b"]].rename(columns={"fighter_b": "fighter"})
    appearances = pd.concat([a, b], ignore_index=True).dropna()
    appearances["year"] = pd.to_datetime(appearances["event_date"], errors="coerce").dt.year
    if divisions:
        appearances = appearances[appearances["division"].isin(divisions)]
    if year_min is not None:
        appearances = appearances[appearances["year"] >= year_min]
    if year_max is not None:
        appearances = appearances[appearances["year"] <= year_max]
    rh = ratings_history.copy()
    rh["event_date"] = pd.to_datetime(rh["event_date"], errors="coerce")
    rh["year"] = rh["event_date"].dt.year
    eoy = (
        rh.sort_values("event_date")
        .groupby(["fighter", "year"], as_index=False)
        .last()[["fighter", "year", "mu_canonical"]]
    )
    merged = appearances.merge(eoy, on=["fighter", "year"], how="inner")
    rows = []
    for (year, division), group in merged.groupby(["year", "division"]):
        top = group.sort_values("mu_canonical", ascending=False).drop_duplicates("fighter").head(top_n)
        if len(top) >= 5:
            rows.append({"year": int(year), "division": division, "mean_top_mu": top["mu_canonical"].mean()})
    heat = pd.DataFrame(rows)
    if heat.empty:
        return _empty_figure("no era heatmap data", title="Division strength by era")
    matrix = heat.pivot(index="division", columns="year", values="mean_top_mu").sort_index()
    denom = matrix.max(axis=0).replace(0, np.nan)
    indexed = matrix.divide(denom, axis=1).mul(100)
    fig = go.Figure(go.Heatmap(
        z=indexed.values,
        x=matrix.columns.astype(str),
        y=matrix.index,
        customdata=matrix.values,
        colorscale=HEATMAP_COLORSCALE,
        zmin=max(80, float(np.nanmin(indexed.values)) if np.isfinite(indexed.values).any() else 0),
        zmax=100,
        colorbar_title="Strength index",
        hovertemplate=(
            "Year %{x}<br>%{y}<br>"
            "strength index=%{z:.1f}<br>"
            "avg top rating=%{customdata:.1f}<extra></extra>"
        ),
    ))
    _apply_chart_layout(fig, height=620)
    fig.update_layout(
        title=f"Top-end division strength by year (top {top_n})",
        xaxis_title="Year",
        yaxis_title="Division",
    )
    return fig


def _score_list(value) -> list[int]:
    if not isinstance(value, str):
        return []
    return [int(part) for part in value.replace("-", " ").split() if part.isdigit()]


def datalab_scorecard_decision_summary(scorecards: pd.DataFrame) -> pd.DataFrame:
    if scorecards is None or scorecards.empty:
        return pd.DataFrame(columns=["decision_type", "fights"])
    rows = []
    for _, row in scorecards.iterrows():
        red = _score_list(row.get("red_fighter_total_pts"))
        blue = _score_list(row.get("blue_fighter_total_pts"))
        if len(red) != len(blue) or len(red) < 2:
            continue
        red_votes = sum(r > b for r, b in zip(red, blue))
        blue_votes = sum(b > r for r, b in zip(red, blue))
        draw_votes = sum(r == b for r, b in zip(red, blue))
        if red_votes == len(red) or blue_votes == len(blue):
            decision_type = "unanimous"
        elif draw_votes and (red_votes or blue_votes):
            decision_type = "majority"
        elif red_votes and blue_votes:
            decision_type = "split"
        else:
            decision_type = "draw/other"
        rows.append({
            "decision_type": decision_type,
            "judge_count": len(red),
            "red_votes": red_votes,
            "blue_votes": blue_votes,
            "draw_votes": draw_votes,
            "total_margin": sum(red) - sum(blue),
            "abs_total_margin": abs(sum(red) - sum(blue)),
            "event_date": row.get("event_date"),
            "red_fighter_name": row.get("red_fighter_name"),
            "blue_fighter_name": row.get("blue_fighter_name"),
        })
    return pd.DataFrame(rows)


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


# ---------------------------------------------------------------------------
# Rating-stream sleeve composer (notebook UX)
#
# The 2026-05-13 consolidation collapsed the sleeve catalogue to two:
#   * integrity sleeve  -- PED + DQ + missed-weight (damps tainted results)
#   * performance sleeve -- quality of win + signed market line + rank,
#     championship, and P4P context (rewards impressive results vs expectation)
#
# Sleeves only apply to the method stream. Canonical is always pristine.
# Peak views resolve only against the two base streams (canonical / method).

RATING_STREAMS: tuple[tuple[str, str], ...] = (
    ("Wins", "canonical"),
    ("Finishes", "method"),
    ("Clean", "method_integrity"),
    ("Strength", "method_performance"),
    ("Complete", "method_integrity_performance"),
)

PEAK_VIEWS: tuple[tuple[str, str], ...] = (
    ("Prime", "sustained_peak"),
    ("Peak", "five_year_peak"),
    ("Now", "current"),
)

SCORING_METHODS: tuple[tuple[str, str], ...] = (
    ("Wins", "canonical"),
    ("Finishes", "method"),
)

PUBLIC_RATING_LENSES: tuple[tuple[str, str], ...] = (
    ("Wins", "wins"),
    ("Complete", "complete"),
    ("Legacy", "legacy"),
)

PUBLIC_TIME_VIEWS: tuple[tuple[str, str], ...] = (
    ("Now", "current"),
    ("Peak", "five_year_peak"),
    ("Prime", "sustained_peak"),
)

# Public lens -> internal stream:
#   * Wins (canonical Glicko-2) — just the W; no method, no integrity, no
#     opponent-quality sleeve.
#   * Complete (method + integrity + performance) — the full-context view:
#     finish quality, PED/DQ/missed-weight discounting, and opponent-strength
#     all baked in.
#   * Legacy (whole-history WHR smoother) — everything Complete carries plus
#     whole-career résumé bonuses; era-comparable.
# Finishes / Clean / Strength used to be exposed separately, but Complete
# already combines those signals and the PED list at the bottom of the
# notebook surfaces the integrity layer directly — exposing them as their own
# top-level lenses just multiplied near-identical leaderboards.
_PUBLIC_LENS_STREAM = {
    "wins": "canonical",
    "complete": "method_integrity_performance",
    "legacy": "whr",
}

_PUBLIC_LENS_HISTORY_KEY = {
    "wins": "ratings_history",
    "complete": "ratings_history_method_integrity_performance",
    "legacy": "ratings_history_whr",
}


def public_rating_label(lens: str, time_view: str) -> str:
    lens_label = dict(PUBLIC_RATING_LENSES).get(lens, lens)
    time_label = dict(PUBLIC_TIME_VIEWS).get(time_view, time_view)
    return f"{time_label} {lens_label}"


def public_rating_stream(lens: str) -> str:
    """Return the internal rating stream behind a public lens label."""
    stream = _PUBLIC_LENS_STREAM.get(lens)
    if stream is None:
        raise ValueError(f"unknown rating lens: {lens!r}")
    return stream


def select_public_rating_column(
    ratings_current: pd.DataFrame,
    lens: str,
    time_view: str,
) -> str | None:
    """Resolve public notebook controls to the backing ratings_current column."""
    stream = public_rating_stream(lens)
    return select_rating_column(ratings_current, stream, time_view)


def public_history_key(lens: str) -> str:
    """Return the SNAP key for the time-series table backing a public lens."""
    return _PUBLIC_LENS_HISTORY_KEY.get(lens, "ratings_history")


def prime_window_min_fights(years: int | float) -> int:
    """Minimum appearances for an adjustable Prime window.

    The fixed 10-year Prime view qualifies at 13 fights, so the adjustable
    control scales from that same density while keeping a practical floor.
    """
    import math

    return max(8, int(math.ceil(float(years) * 1.25)))


def prime_window_title_min_fights(
    years: int | float,
    min_fights: int | None = None,
) -> int:
    """Title-heavy effective minimum for an adjustable Prime window."""
    import math

    base = prime_window_min_fights(years) if min_fights is None else int(min_fights)
    return max(6, int(math.ceil(base * 0.75)))


def prime_window_column_names(
    stream: str,
    years: int | float,
    min_fights: int | None = None,
) -> tuple[str, str]:
    """Raw/headline column names for a notebook-calculated N-year Prime view."""
    y = int(years)
    suffix = f"prime_{y}yr"
    if min_fights is not None:
        suffix = f"{suffix}_{int(min_fights)}f"
    return f"{suffix}_mu_{stream}", f"{suffix}_headline_mu_{stream}"


def n_year_prime_scores(
    history: pd.DataFrame,
    canonical_history: pd.DataFrame,
    canonical_fights: pd.DataFrame,
    *,
    mu_col: str,
    stream: str,
    years: int | float,
    min_fights: int | None = None,
    appearance_quality: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Calculate an adjustable N-year Prime score for notebook controls.

    This uses the same period-scoring machinery as the persisted 5-year Peak
    and 10-year Prime columns; only the window length changes.
    """
    from ratings.peaks import rolling_peak

    min_fights = prime_window_min_fights(years) if min_fights is None else int(min_fights)
    raw_col, headline_col = prime_window_column_names(stream, years, min_fights)
    return rolling_peak(
        history,
        canonical_history,
        canonical_fights,
        mu_col=mu_col,
        out_col=raw_col,
        headline_col=headline_col,
        window_days=int(round(float(years) * 365.25)),
        min_fights=min_fights,
        title_effective_min_raw_fights=prime_window_title_min_fights(years, min_fights),
        appearance_quality=appearance_quality,
    )


def compose_rating_stream(
    scoring_method: str,
    *,
    use_integrity: bool = False,
    use_performance: bool = False,
) -> str:
    """Compose scoring-method + sleeve toggles into a ``ratings_current`` suffix.

    Sleeves can only be turned on when ``scoring_method == "method"``; using
    them with canonical raises ``ValueError`` so the UI can lock that.
    """
    if scoring_method not in {"canonical", "method"}:
        raise ValueError(f"unknown scoring method: {scoring_method!r}")
    if scoring_method == "canonical" and (use_integrity or use_performance):
        raise ValueError(
            "sleeves only apply to the method stream; canonical is always pristine"
        )
    if scoring_method == "canonical":
        return "canonical"
    parts = ["method"]
    if use_integrity:
        parts.append("integrity")
    if use_performance:
        parts.append("performance")
    return "_".join(parts)


def modular_rating_context(
    scoring_method: str,
    *,
    use_integrity: bool = False,
    use_performance: bool = False,
) -> dict[str, str]:
    """Human-readable labels + comparison baseline for a modular selection."""
    stream = compose_rating_stream(
        scoring_method,
        use_integrity=use_integrity,
        use_performance=use_performance,
    )
    if scoring_method == "canonical":
        scoring_label = "Wins"
        baseline_col, baseline_label = "mu_canonical", "Wins"
    else:
        scoring_label = "Finishes"
        baseline_col, baseline_label = "mu_method", "Finishes"
    sleeves = []
    if use_integrity:
        sleeves.append("Clean")
    if use_performance:
        sleeves.append("Strength")
    sleeve_label = " + ".join(sleeves) if sleeves else "No context"
    if use_integrity and use_performance:
        display_label = "Complete"
    elif use_integrity or use_performance:
        display_label = sleeve_label
    else:
        display_label = scoring_label
    return {
        "stream": stream,
        "label": display_label,
        "detail": f"{scoring_label} with {sleeve_label.lower()}",
        "baseline_col": baseline_col,
        "baseline_label": baseline_label,
    }


def select_rating_column(
    ratings_current: pd.DataFrame,
    stream: str,
    peak: str = "current",
) -> str | None:
    """Compose a (stream, peak) selection into the ``ratings_current`` column.

    Current is a debug state. Historical peak views resolve to the headline
    proven-resume-adjusted column when available, falling back to the raw
    per-stream peak column, then the matching base-stream peak column.
    """
    if peak == "current":
        col = f"mu_{stream}"
    elif peak == "sustained_peak":
        peak_base = "method" if stream.startswith("method") else "canonical"
        for candidate in (
            f"sustained_peak_headline_mu_{stream}",
            f"sustained_peak_mu_{stream}",
            f"sustained_peak_headline_mu_{peak_base}",
            f"sustained_peak_mu_{peak_base}",
            f"five_year_peak_headline_mu_{stream}",
            f"five_year_peak_mu_{stream}",
        ):
            if candidate in ratings_current.columns:
                return candidate
        return None
    elif peak == "five_year_peak":
        peak_base = "method" if stream.startswith("method") else "canonical"
        for candidate in (
            f"five_year_peak_headline_mu_{stream}",
            f"five_year_peak_mu_{stream}",
            f"five_year_peak_headline_mu_{peak_base}",
            f"five_year_peak_mu_{peak_base}",
        ):
            if candidate in ratings_current.columns:
                return candidate
        return None
    else:
        raise ValueError(f"unknown peak view: {peak!r}")
    return col if col in ratings_current.columns else None


def select_modular_rating_column(
    ratings_current: pd.DataFrame,
    scoring_method: str,
    *,
    use_integrity: bool = False,
    use_performance: bool = False,
    peak: str = "current",
) -> str | None:
    """Column lookup for the modular scoring-method x sleeve composer."""
    stream = compose_rating_stream(
        scoring_method,
        use_integrity=use_integrity,
        use_performance=use_performance,
    )
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


def style_sleeve_ranking_table(table: pd.DataFrame, query: str = ""):
    """Return a pandas Styler for the notebook's sleeve ranking table."""
    if table.empty:
        return table

    def delta_color(value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ""
        if v > 0:
            return "color: #15803d; font-weight: 600"
        if v < 0:
            return "color: #b91c1c; font-weight: 600"
        return "color: #475569"

    def row_highlight(row):
        if query and bool(row.get("query_match", False)):
            return ["background-color: #fef3c7"] * len(row)
        return [""] * len(row)

    display_table = table.drop(columns=["query_match"], errors="ignore")
    try:
        return (
            display_table.style
            .format({"current_rating": "{:.1f}", "baseline_rating": "{:.1f}", "delta_vs_baseline": "{:+.1f}"})
            .apply(lambda _row: row_highlight(table.loc[_row.name]), axis=1)
            .map(delta_color, subset=["delta_vs_baseline"])
            .set_properties(**{"text-align": "left"})
            .set_table_styles([
                {"selector": "th", "props": [("text-align", "left"), ("color", "#334155")]},
                {"selector": "td", "props": [("padding", "6px 10px")]},
            ])
        )
    except AttributeError:
        # Fallback when pandas' Styler requires jinja2. Return simple HTML
        # so the notebook can still render a readable table.
        from IPython.display import HTML

        fallback = display_table.copy()
        # Format numeric columns as strings with desired precision
        fallback["current_rating"] = fallback["current_rating"].apply(
            lambda v: f"{v:.1f}" if pd.notnull(v) else ""
        )
        fallback["baseline_rating"] = fallback["baseline_rating"].apply(
            lambda v: f"{v:.1f}" if pd.notnull(v) else ""
        )
        fallback["delta_vs_baseline"] = fallback["delta_vs_baseline"].apply(
            lambda v: f"{v:+.1f}" if pd.notnull(v) else ""
        )

        # If a query match exists in the original table, highlight the fighter cell
        if query and "query_match" in table.columns:
            def maybe_highlight(row):
                name = row["fighter"]
                if row.get("query_match", False):
                    return f"<span style=\"background-color: #fef3c7\">{name}</span>"
                return name

            highlighted = [maybe_highlight(r) for _, r in table.iterrows()]
            fallback["fighter"] = highlighted

        html = fallback.to_html(escape=False, index=False)
        return HTML(html)


# ---------------------------------------------------------------------------
# Odds / market-adjustment helpers
#
# All four functions degrade gracefully when their inputs are missing or
# empty (no odds artifact in the snapshot) so the notebook can render a
# clean "odds data unavailable" cell rather than KeyError'ing out.

def odds_coverage_summary(
    ratings_current: pd.DataFrame,
    odds_lines: pd.DataFrame | None,
    fights: pd.DataFrame,
) -> dict:
    """Compact dict describing odds coverage at the snapshot level."""
    if odds_lines is None or odds_lines.empty:
        return {
            "available": False,
            "total_fights": int(len(fights)) if fights is not None else 0,
            "odds_covered_fights": 0,
            "odds_coverage_rate": 0.0,
            "fighters_with_odds_adjustment": 0,
            "message": "No odds artifact present for this snapshot.",
        }
    total = int(len(fights)) if fights is not None else 0
    ok = odds_lines[odds_lines.get("odds_data_quality", "missing") == "ok"]
    covered_urls = set(ok["fight_url"]) & set(fights["fight_url"]) if total else set()
    covered = len(covered_urls)
    rate = covered / total if total else 0.0
    fighters_adjusted = 0
    if "delta_mu_method_performance" in ratings_current.columns:
        fighters_adjusted = int(
            ratings_current["delta_mu_method_performance"].abs().fillna(0).gt(0.01).sum()
        )
    return {
        "available": True,
        "total_fights": total,
        "odds_covered_fights": covered,
        "odds_coverage_rate": rate,
        "fighters_with_odds_adjustment": fighters_adjusted,
        "message": (
            f"{covered:,} of {total:,} canonical bouts have usable odds "
            f"({rate:.1%} coverage)."
        ),
    }


def odds_adjustment_distribution_chart(distribution: pd.DataFrame | None) -> go.Figure:
    """Plot positive and negative market-residual cohorts on one density axis.

    Accepts either the legacy ``odds_adjustment_distribution`` schema
    (cohort/abs_residual) or a ``performance_appearances`` frame and
    derives the cohorts on-the-fly. Empty input renders a placeholder.
    """
    if distribution is None or distribution.empty:
        return _empty_figure(
            "market residual distribution unavailable for this snapshot",
            title="Market residual distribution",
        )

    if "cohort" not in distribution.columns and "market_residual" in distribution.columns:
        r = pd.to_numeric(distribution["market_residual"], errors="coerce").dropna()
        derived = pd.DataFrame({
            "cohort": pd.Series(["positive"] * (r > 0).sum() + ["negative"] * (r < 0).sum()),
            "abs_residual": pd.concat([r[r > 0], (-r[r < 0])], ignore_index=True),
        })
        distribution = derived

    pos = distribution[distribution["cohort"] == "positive"]["abs_residual"]
    neg = distribution[distribution["cohort"] == "negative"]["abs_residual"]
    fig = go.Figure()
    if not pos.empty:
        fig.add_trace(go.Violin(
            x=pos,
            y=["positive"] * len(pos),
            name="positive",
            orientation="h",
            side="positive",
            width=0.9,
            line_color=SIGN_COLORS["positive"],
            fillcolor=_hex_to_rgba(SIGN_COLORS["positive"], 0.28),
            meanline_visible=True,
        ))
    if not neg.empty:
        fig.add_trace(go.Violin(
            x=neg,
            y=["negative"] * len(neg),
            name="negative",
            orientation="h",
            side="positive",
            width=0.9,
            line_color=SIGN_COLORS["negative"],
            fillcolor=_hex_to_rgba(SIGN_COLORS["negative"], 0.28),
            meanline_visible=True,
        ))
    _apply_chart_layout(fig, height=380)
    fig.update_layout(
        title="Market residual distribution by sign cohort",
        showlegend=False,
        violingap=0,
    )
    fig.update_xaxes(title_text="|actual - market_prob|")
    fig.update_yaxes(title_text="Cohort")
    return fig


def _fighter_odds_profile(odds_lines: pd.DataFrame | None) -> pd.DataFrame:
    if odds_lines is None or odds_lines.empty:
        return pd.DataFrame(columns=["fighter", "odds_covered_fights", "median_market_prob"])
    needed = {"fighter_a", "fighter_b", "implied_prob_a_no_vig", "implied_prob_b_no_vig", "odds_data_quality"}
    if not needed.issubset(odds_lines.columns):
        return pd.DataFrame(columns=["fighter", "odds_covered_fights", "median_market_prob"])
    ok = odds_lines[odds_lines["odds_data_quality"] == "ok"].copy()
    a = ok[["fighter_a", "implied_prob_a_no_vig"]].rename(
        columns={"fighter_a": "fighter", "implied_prob_a_no_vig": "market_prob"}
    )
    b = ok[["fighter_b", "implied_prob_b_no_vig"]].rename(
        columns={"fighter_b": "fighter", "implied_prob_b_no_vig": "market_prob"}
    )
    long = pd.concat([a, b], ignore_index=True).dropna(subset=["fighter", "market_prob"])
    if long.empty:
        return pd.DataFrame(columns=["fighter", "odds_covered_fights", "median_market_prob"])
    return (
        long.groupby("fighter", as_index=False)
        .agg(
            odds_covered_fights=("market_prob", "size"),
            median_market_prob=("market_prob", "median"),
        )
    )


def odds_impact_chart(
    ratings_current: pd.DataFrame,
    odds_lines: pd.DataFrame | None = None,
    n: int = 15,
) -> go.Figure:
    """Largest positive/negative ``delta_mu_method_performance`` movers."""
    if "delta_mu_method_performance" not in ratings_current.columns:
        return _empty_figure(
            "method-performance columns not present in ratings_current",
            title="Performance sleeve impact",
        )
    df = ratings_current.copy()
    df["delta_mu_method_performance"] = pd.to_numeric(df["delta_mu_method_performance"], errors="coerce")
    df = df.dropna(subset=["delta_mu_method_performance"])
    df = df[df["delta_mu_method_performance"].abs() > 0.01]
    if df.empty:
        return _empty_figure(
            "no measurable performance-sleeve rating movement",
            title="Performance sleeve impact",
        )
    movers = pd.concat([
        df.sort_values("delta_mu_method_performance", ascending=True).head(n),
        df.sort_values("delta_mu_method_performance", ascending=False).head(n),
    ]).drop_duplicates("fighter")
    movers = movers.sort_values("delta_mu_method_performance")
    profile = _fighter_odds_profile(odds_lines)
    movers = movers.merge(profile, on="fighter", how="left")
    colors = np.where(movers["delta_mu_method_performance"] >= 0, SIGN_COLORS["positive"], SIGN_COLORS["negative"])
    fig = go.Figure(go.Bar(
        x=movers["delta_mu_method_performance"],
        y=movers["fighter"],
        orientation="h",
        marker_color=colors,
        customdata=np.stack([
            movers.get("mu_method", pd.Series(index=movers.index)).round(1).astype("string"),
            movers.get("mu_method_performance", pd.Series(index=movers.index)).round(1).astype("string"),
            movers.get("odds_covered_fights", pd.Series(index=movers.index)).fillna(0).astype("Int64").astype("string"),
            movers.get("median_market_prob", pd.Series(index=movers.index)).round(3).astype("string"),
        ], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "delta=%{x:.1f}<br>"
            "method=%{customdata[0]}<br>"
            "method+performance=%{customdata[1]}<br>"
            "odds-covered fights=%{customdata[2]}<br>"
            "median market_prob=%{customdata[3]}<extra></extra>"
        ),
    ))
    _apply_chart_layout(fig, height=max(480, 24 * len(movers)))
    fig.update_layout(
        title="Largest performance-sleeve rating impacts",
        xaxis_title="Rating movement vs method baseline",
        yaxis_title="Fighter",
    )
    return fig


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


def _filter_fighter(df: pd.DataFrame, fighter: str | None) -> pd.DataFrame:
    if not fighter or "fighter" not in df.columns:
        return df
    key = normalize_name_key(fighter, compact=True)
    if not key:
        return df
    mask = df["fighter"].apply(lambda name: key in normalize_name_key(name, compact=True))
    return df[mask].copy()


def _appearance_outcome(df: pd.DataFrame) -> pd.Series:
    is_draw = df.get("is_draw", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    is_winner = df.get("is_winner", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    return pd.Series(
        np.select([is_draw, is_winner], ["draw", "win"], default="loss"),
        index=df.index,
    )


def performance_factor_audit_table(
    performance_appearances: pd.DataFrame,
    *,
    n: int = 100,
    fighter: str | None = None,
    factor: str | None = None,
    effect: str = "all",
    include_neutral: bool = False,
) -> pd.DataFrame:
    """Explode performance sleeve factors into one auditable row per effect.

    `effect` can be `all`, `boost`, `penalty`, or `neutral`. Most performance
    factors apply only to winner rows; the weight-class factor also applies to
    downward-loss penalties.
    """
    out_cols = [
        "event_date", "event_name", "fighter", "opponent", "outcome",
        "sleeve", "factor", "factor_col", "effect", "multiplier",
        "applied_to_update", "performance_weight", "division",
        "fighter_previous_division", "fighter_weight_class_move",
        "fighter_weight_class_change_fight",
        "opponent_prefight_division_rank", "opponent_prefight_p4p_rank",
        "opponent_entered_as_champion", "opponent_entered_as_interim_champion",
        "is_championship_bout", "market_american_odds",
    ]
    if performance_appearances is None or performance_appearances.empty:
        return pd.DataFrame(columns=out_cols)

    df = _filter_fighter(performance_appearances.copy(), fighter)
    factor_cols = [c for c in PERFORMANCE_FACTOR_LABELS if c in df.columns]
    if factor:
        factor_key = normalize_name_key(factor, compact=True)
        factor_cols = [
            c for c in factor_cols
            if factor_key in normalize_name_key(c, compact=True)
            or factor_key in normalize_name_key(PERFORMANCE_FACTOR_LABELS[c], compact=True)
        ]
    if not factor_cols:
        return pd.DataFrame(columns=out_cols)

    df["outcome"] = _appearance_outcome(df)
    is_winner = df.get("is_winner", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    is_draw = df.get("is_draw", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    is_loss = ~is_winner & ~is_draw
    move = df.get("fighter_weight_class_move", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    change_fight = df.get("fighter_weight_class_change_fight", pd.Series(False, index=df.index)).fillna(False).astype(bool)

    base_cols = [
        "event_date", "event_name", "fighter", "opponent", "outcome",
        "performance_weight", "division", "fighter_previous_division",
        "fighter_weight_class_move", "opponent_prefight_division_rank",
        "opponent_prefight_p4p_rank", "opponent_entered_as_champion",
        "opponent_entered_as_interim_champion", "is_championship_bout",
        "market_american_odds", "activity_gap_days", "activity_layoff_level",
    ]
    rows = []
    for col in factor_cols:
        sub = df[[c for c in base_cols if c in df.columns]].copy()
        sub["sleeve"] = "performance"
        sub["factor_col"] = col
        sub["factor"] = PERFORMANCE_FACTOR_LABELS[col]
        sub["multiplier"] = pd.to_numeric(df[col], errors="coerce").fillna(1.0)
        if col == "perf_factor_weight_class":
            applied = change_fight & ((is_winner & move.eq("up")) | (is_loss & move.eq("down")))
        elif col == "perf_factor_activity_loss":
            applied = is_loss
        else:
            applied = is_winner
        sub["applied_to_update"] = applied
        sub["effect"] = "neutral"
        active = applied & sub["multiplier"].ne(1.0)
        sub.loc[active & sub["multiplier"].gt(1.0), "effect"] = "boost"
        sub.loc[active & sub["multiplier"].lt(1.0), "effect"] = "penalty"
        if col == "perf_factor_weight_class":
            down_loss = active & change_fight & is_loss & move.eq("down")
            sub.loc[down_loss, "effect"] = "penalty"
        rows.append(sub)

    audit = pd.concat(rows, ignore_index=True, sort=False) if rows else pd.DataFrame(columns=out_cols)
    if not include_neutral:
        audit = audit[audit["effect"] != "neutral"]
    if effect != "all":
        audit = audit[audit["effect"] == effect]
    if audit.empty:
        return pd.DataFrame(columns=out_cols)
    audit["event_date"] = pd.to_datetime(audit.get("event_date"), errors="coerce").dt.date
    audit["_abs_delta"] = (pd.to_numeric(audit["multiplier"], errors="coerce") - 1.0).abs()
    audit = audit.sort_values(["_abs_delta", "event_date"], ascending=[False, False]).head(n)
    audit = audit.drop(columns=["_abs_delta"], errors="ignore")
    for col in ["multiplier", "performance_weight", "market_american_odds"]:
        if col in audit.columns:
            audit[col] = pd.to_numeric(audit[col], errors="coerce").round(3)
    return audit[[c for c in out_cols if c in audit.columns]].reset_index(drop=True)


def integrity_factor_audit_table(
    integrity_appearances: pd.DataFrame,
    performance_appearances: pd.DataFrame | None = None,
    *,
    n: int = 100,
    fighter: str | None = None,
    factor: str | None = None,
    effect: str = "all",
    include_neutral: bool = False,
) -> pd.DataFrame:
    """Explode integrity sleeve dampers into one readable row per penalty."""
    out_cols = [
        "event_date", "event_name", "fighter", "opponent", "outcome",
        "sleeve", "factor", "factor_col", "effect", "multiplier",
        "integrity_weight",
    ]
    if integrity_appearances is None or integrity_appearances.empty:
        return pd.DataFrame(columns=out_cols)

    df = integrity_appearances.copy()
    if performance_appearances is not None and not performance_appearances.empty:
        enrich_cols = [
            "fight_url", "fighter", "event_date", "event_name", "opponent",
            "is_winner", "is_draw",
        ]
        enrich = performance_appearances[[c for c in enrich_cols if c in performance_appearances.columns]].copy()
        df = df.merge(enrich, on=["fight_url", "fighter"], how="left")
    df = _filter_fighter(df, fighter)
    df["outcome"] = _appearance_outcome(df)

    factor_cols = [c for c in INTEGRITY_FACTOR_LABELS if c in df.columns]
    if factor:
        factor_key = normalize_name_key(factor, compact=True)
        factor_cols = [
            c for c in factor_cols
            if factor_key in normalize_name_key(c, compact=True)
            or factor_key in normalize_name_key(INTEGRITY_FACTOR_LABELS[c], compact=True)
        ]
    if not factor_cols:
        return pd.DataFrame(columns=out_cols)

    base_cols = ["event_date", "event_name", "fighter", "opponent", "outcome", "integrity_weight"]
    rows = []
    for col in factor_cols:
        sub = df[[c for c in base_cols if c in df.columns]].copy()
        sub["sleeve"] = "integrity"
        sub["factor_col"] = col
        sub["factor"] = INTEGRITY_FACTOR_LABELS[col]
        sub["multiplier"] = pd.to_numeric(df[col], errors="coerce").fillna(1.0)
        sub["effect"] = np.where(sub["multiplier"].lt(1.0), "penalty", "neutral")
        rows.append(sub)

    audit = pd.concat(rows, ignore_index=True, sort=False) if rows else pd.DataFrame(columns=out_cols)
    if not include_neutral:
        audit = audit[audit["effect"] != "neutral"]
    if effect != "all":
        audit = audit[audit["effect"] == effect]
    if audit.empty:
        return pd.DataFrame(columns=out_cols)
    audit["event_date"] = pd.to_datetime(audit.get("event_date"), errors="coerce").dt.date
    audit["_abs_delta"] = (pd.to_numeric(audit["multiplier"], errors="coerce") - 1.0).abs()
    audit = audit.sort_values(["_abs_delta", "event_date"], ascending=[False, False]).head(n)
    audit = audit.drop(columns=["_abs_delta"], errors="ignore")
    for col in ["multiplier", "integrity_weight"]:
        if col in audit.columns:
            audit[col] = pd.to_numeric(audit[col], errors="coerce").round(3)
    return audit[[c for c in out_cols if c in audit.columns]].reset_index(drop=True)


def sleeve_factor_summary_table(
    integrity_appearances: pd.DataFrame | None = None,
    performance_appearances: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Counts and normalized percent ranges for every non-neutral factor."""
    frames = []
    if performance_appearances is not None and not performance_appearances.empty:
        frames.append(performance_factor_audit_table(
            performance_appearances,
            n=len(performance_appearances) * max(1, len(PERFORMANCE_FACTOR_LABELS)),
        ))
    if integrity_appearances is not None and not integrity_appearances.empty:
        frames.append(integrity_factor_audit_table(
            integrity_appearances,
            performance_appearances,
            n=len(integrity_appearances) * max(1, len(INTEGRITY_FACTOR_LABELS)),
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
        "integrity": "Integrity penalties",
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
    integrity_appearances: pd.DataFrame | None = None,
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
    if integrity_appearances is not None and not integrity_appearances.empty:
        frames.append(integrity_factor_audit_table(
            integrity_appearances,
            performance_appearances,
            n=len(integrity_appearances) * max(1, len(INTEGRITY_FACTOR_LABELS)),
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


# ---------------------------------------------------------------------------
# Lean diagnostic dashboards backed by build-time artifacts

def calibration_residuals_chart(
    calibration_residuals: pd.DataFrame,
    *,
    segment_type: str = "division",
    min_n: int = 40,
) -> go.Figure:
    """Predicted win probability vs empirical outcomes by segment."""
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
        name="calibrated",
    ))
    for segment, g in df.groupby("segment_value", sort=False):
        fig.add_trace(go.Scatter(
            x=g["predicted_mean"],
            y=g["empirical_win_rate"],
            mode="markers+lines",
            name=str(segment),
            marker=dict(size=np.sqrt(g["n"]).clip(6, 22)),
            customdata=np.stack([
                g["residual"].round(3).astype("string"),
                g["n"].astype(int).astype("string"),
                g["brier"].round(4).astype("string"),
            ], axis=-1),
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "predicted=%{x:.3f}<br>"
                "empirical=%{y:.3f}<br>"
                "residual=%{customdata[0]}<br>"
                "n=%{customdata[1]}<br>"
                "brier=%{customdata[2]}<extra></extra>"
            ),
        ))
    _apply_chart_layout(fig, height=560)
    fig.update_layout(
        title=f"Calibration residuals by {segment_type}",
        xaxis_title="Mean predicted P(win)",
        yaxis_title="Empirical win rate",
        xaxis=dict(range=[0, 1]),
        yaxis=dict(range=[0, 1]),
        legend=dict(orientation="h", y=1.15, x=0),
    )
    return fig


def sleeve_attribution_waterfall(
    sleeve_attribution: pd.DataFrame,
    fighter: str,
) -> go.Figure:
    """Readable component chart for career rating movement by adjustment layer."""
    if sleeve_attribution is None or sleeve_attribution.empty or not fighter:
        return _empty_figure("sleeve attribution unavailable", title="Sleeve attribution")
    key = normalize_name_key(fighter, compact=True)
    df = sleeve_attribution[
        sleeve_attribution["fighter"].apply(lambda name: key in normalize_name_key(name, compact=True))
    ].copy()
    if df.empty:
        return _empty_figure(f"fighter not found: {fighter}", title="Sleeve attribution")
    actual = df["fighter"].iloc[0]
    components = [
        ("Base", "base_method_delta"),
        ("Clean", "integrity_delta"),
        ("Strength", "performance_delta"),
        ("Overlap", "interaction_delta"),
    ]
    rows = []
    for label, col in components:
        value = float(pd.to_numeric(df.get(col), errors="coerce").fillna(0.0).sum())
        rows.append({"component": label, "rating_points": value})
    plot = pd.DataFrame(rows)
    plot["abs_points"] = plot["rating_points"].abs()
    plot = plot.sort_values("abs_points", ascending=True)
    colors = np.where(plot["rating_points"].ge(0), SIGN_COLORS["positive"], SIGN_COLORS["negative"])
    total = float(plot["rating_points"].sum())
    fig = go.Figure(go.Bar(
        x=plot["rating_points"],
        y=plot["component"],
        orientation="h",
        marker_color=colors,
        text=plot["rating_points"].map(lambda v: f"{v:+.1f}"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:+.1f} rating points<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#94a3b8", line_width=1)
    fig.add_annotation(
        text=f"Net: {total:+.1f} rating points",
        x=1,
        y=1.08,
        xref="paper",
        yref="paper",
        showarrow=False,
        align="right",
        font=dict(size=13, color=THEME["text"]),
    )
    _apply_chart_layout(fig, height=460)
    fig.update_layout(
        title=f"{actual}: rating story",
        xaxis_title="Rating points",
        yaxis_title="",
        showlegend=False,
    )
    return fig


def sleeve_attribution_table(
    sleeve_attribution: pd.DataFrame,
    fighter: str,
    *,
    n: int = 25,
) -> pd.DataFrame:
    """Most recent exact per-event sleeve-attribution rows for a fighter."""
    cols = [
        "event_date", "event_name", "opponent", "base_method_delta",
        "integrity_delta", "performance_delta", "interaction_delta",
        "combined_delta", "integrity_weight", "performance_weight",
        "combined_weight",
    ]
    if sleeve_attribution is None or sleeve_attribution.empty or not fighter:
        return pd.DataFrame(columns=cols)
    key = normalize_name_key(fighter, compact=True)
    df = sleeve_attribution[
        sleeve_attribution["fighter"].apply(lambda name: key in normalize_name_key(name, compact=True))
    ].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df = df.sort_values("event_date", ascending=False).head(n)
    out = df[[c for c in cols if c in df.columns]].copy()
    out["event_date"] = out["event_date"].dt.date
    for col in [c for c in cols if c.endswith("_delta") or c.endswith("_weight")]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(3)
    return out.reset_index(drop=True)


def division_entropy_chart(
    division_entropy: pd.DataFrame,
    *,
    divisions: list[str] | None = None,
) -> go.Figure:
    """Top-10 divisional mu-density/entropy time-series."""
    if division_entropy is None or division_entropy.empty:
        return _empty_figure("division entropy unavailable", title="Division crowdedness")
    df = division_entropy.copy()
    if divisions:
        df = df[df["division"].isin(divisions)]
    if df.empty:
        return _empty_figure("no divisions selected", title="Division crowdedness")
    if not divisions:
        latest_year = pd.to_numeric(df["year"], errors="coerce").max()
        divisions = (
            df[df["year"].eq(latest_year)]
            .sort_values("top_mu_mean", ascending=False)
            .head(8)["division"].tolist()
        )
        df = df[df["division"].isin(divisions)]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Top-10 normalized entropy", "Top-10 mean mu"),
    )
    for division, g in df.sort_values(["division", "year"]).groupby("division"):
        fig.add_trace(
            go.Scatter(
                x=g["year"], y=g["entropy_normalized"],
                mode="lines+markers", name=str(division),
                hovertemplate="<b>%{fullData.name}</b><br>year=%{x}<br>entropy=%{y:.3f}<extra></extra>",
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=g["year"], y=g["top_mu_mean"],
                mode="lines", name=str(division), showlegend=False,
                hovertemplate="<b>%{fullData.name}</b><br>year=%{x}<br>top10 mean=%{y:.1f}<extra></extra>",
            ),
            row=2, col=1,
        )
    _apply_chart_layout(fig, height=720)
    fig.update_layout(title="Division crowdedness and top-end strength")
    fig.update_yaxes(range=[0, 1.02], row=1, col=1)
    fig.update_yaxes(title_text="Crowdedness (0-1)", row=1, col=1)
    fig.update_yaxes(title_text="Avg top-10 rating", row=2, col=1)
    fig.update_xaxes(title_text="Year", row=2, col=1)
    return fig


def favorite_underdog_performance_chart(performance: pd.DataFrame) -> go.Figure:
    """Grouped bars comparing actual and expected win rate by market bucket."""
    if performance is None or performance.empty:
        return _empty_figure(
            "favorite/underdog performance unavailable",
            title="Market calibration by favorite status",
        )
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=performance["bucket"],
        y=performance["win_rate"],
        name="Actual win rate",
        marker_color=STREAM_PALETTE["canonical"],
        text=(performance["win_rate"] * 100).round(1).astype(str) + "%",
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        x=performance["bucket"],
        y=performance["expected_win_rate"],
        name="Expected win rate",
        marker_color=STREAM_PALETTE["odds_adjusted"],
        text=(performance["expected_win_rate"] * 100).round(1).astype(str) + "%",
        textposition="outside",
    ))
    _apply_chart_layout(fig, height=380)
    fig.update_layout(
        title="Market calibration by favorite status",
        yaxis_title="Win rate",
        yaxis_tickformat=".0%",
        yaxis_range=[0, 1],
        barmode="group",
        legend=dict(orientation="h", y=1.12, x=0),
    )
    return fig


def fighter_profile_chart(
    fighter: str,
    ratings_current: pd.DataFrame,
) -> go.Figure:
    """Compact fighter profile bars for comparison cards."""
    if ratings_current is None or ratings_current.empty or not fighter:
        return _empty_figure("fighter profile unavailable", title="Fighter profile", height=300)
    row = ratings_current[ratings_current["fighter"].eq(fighter)]
    if row.empty:
        return _empty_figure(f"fighter not found: {fighter}", title="Fighter profile", height=300)
    r = row.iloc[0]
    metrics = [
        ("Current rating", r.get("mu_canonical")),
        ("10-year peak", r.get("sustained_peak_headline_mu_whr", r.get("sustained_peak_mu_canonical"))),
        ("5-year peak", r.get("five_year_peak_headline_mu_whr", r.get("five_year_peak_mu_canonical"))),
    ]
    plot = pd.DataFrame(metrics, columns=["metric", "value"]).dropna()
    if plot.empty:
        return _empty_figure("profile metrics unavailable", title=fighter, height=300)
    fig = go.Figure(go.Bar(
        x=pd.to_numeric(plot["value"], errors="coerce"),
        y=plot["metric"],
        orientation="h",
        marker_color=[STREAM_PALETTE["canonical"], STREAM_PALETTE["method"], STREAM_PALETTE["odds_adjusted"]][:len(plot)],
        text=pd.to_numeric(plot["value"], errors="coerce").round(1).astype(str),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:.1f} rating points<extra></extra>",
    ))
    _apply_chart_layout(fig, height=300)
    fig.update_layout(
        title=f"{fighter}: rating profile",
        xaxis_title="Rating points",
        yaxis_title="",
        showlegend=False,
        margin=dict(t=54, r=30, b=42, l=96),
    )
    fig.update_xaxes(rangemode="tozero")
    return fig


def fighter_odds_history_chart(
    fighter: str,
    odds_lines: pd.DataFrame | None,
    fights: pd.DataFrame,
) -> go.Figure:
    """Market-implied win probability over time for one fighter.

    Shows ALL canonical fights for the fighter. Where odds data is available
    the line plots the market win probability; fights without odds appear as
    diamond markers near the bottom so the complete fight history is visible
    even when the odds snapshot hasn't caught up yet.
    """
    title = f"{fighter}: market history"
    if fights is None or fights.empty:
        return _empty_figure("fight history unavailable", title=title, height=300)

    # All canonical fights for this fighter
    cols = ["fight_url", "event_date", "event_name", "fighter_a", "fighter_b", "winner", "is_draw"]
    fa = fights[fights["fighter_a"].eq(fighter)][[c for c in cols if c in fights.columns]].rename(
        columns={"fighter_b": "opponent"})
    fb = fights[fights["fighter_b"].eq(fighter)][[c for c in cols if c in fights.columns]].rename(
        columns={"fighter_a": "opponent"})
    all_fights = pd.concat([fa, fb], ignore_index=True)
    if all_fights.empty:
        return _empty_figure("no fights found", title=title, height=300)

    all_fights["event_date"] = pd.to_datetime(all_fights["event_date"], errors="coerce")
    result_colors = {"Win": SIGN_COLORS["positive"], "Loss": SIGN_COLORS["negative"], "Draw": THEME["neutral"]}
    all_fights["result"] = np.select(
        [
            all_fights.get("is_draw", pd.Series(False, index=all_fights.index)).fillna(False).astype(bool),
            all_fights["winner"].eq(fighter),
        ],
        ["Draw", "Win"],
        default="Loss",
    )

    # Merge odds where available
    all_fights["market_prob"] = np.nan
    if odds_lines is not None and not odds_lines.empty:
        needed = {"fight_url", "fighter_a", "fighter_b", "implied_prob_a_no_vig", "implied_prob_b_no_vig", "odds_data_quality"}
        if needed.issubset(odds_lines.columns):
            ok = odds_lines[odds_lines["odds_data_quality"].eq("ok")].copy()
            oa = ok[ok["fighter_a"].eq(fighter)][["fight_url", "implied_prob_a_no_vig"]].rename(
                columns={"implied_prob_a_no_vig": "market_prob_merge"})
            ob = ok[ok["fighter_b"].eq(fighter)][["fight_url", "implied_prob_b_no_vig"]].rename(
                columns={"implied_prob_b_no_vig": "market_prob_merge"})
            odds_long = pd.concat([oa, ob], ignore_index=True).dropna(subset=["market_prob_merge"])
            if not odds_long.empty:
                all_fights = all_fights.merge(odds_long, on="fight_url", how="left")
                all_fights["market_prob"] = all_fights.get("market_prob_merge", pd.Series(dtype=float))
                all_fights = all_fights.drop(columns=["market_prob_merge"], errors="ignore")

    all_fights = all_fights.sort_values("event_date")
    has_odds = all_fights.dropna(subset=["market_prob"])
    no_odds = all_fights[all_fights["market_prob"].isna()]

    fig = go.Figure()

    # Probability line + markers for fights with odds
    if not has_odds.empty:
        colors_odds = has_odds["result"].map(result_colors).fillna(THEME["text_muted"])
        fig.add_trace(go.Scatter(
            x=has_odds["event_date"],
            y=has_odds["market_prob"] * 100,
            mode="lines+markers",
            line=dict(color=STREAM_PALETTE["odds_adjusted"], width=2),
            marker=dict(size=9, color=colors_odds.tolist(), line=dict(color="white", width=0.8)),
            customdata=np.column_stack([
                has_odds["opponent"].fillna("").values,
                has_odds["result"].values,
                has_odds["event_name"].fillna("").values,
            ]),
            hovertemplate=(
                "<b>%{customdata[2]}</b><br>"
                "vs %{customdata[0]}: %{customdata[1]}<br>"
                "market win probability=%{y:.1f}%<extra></extra>"
            ),
            showlegend=False,
            name="odds",
        ))

    # Diamond markers at y=5 for fights without odds (preserves full history)
    if not no_odds.empty:
        colors_no = no_odds["result"].map(result_colors).fillna(THEME["text_muted"])
        fig.add_trace(go.Scatter(
            x=no_odds["event_date"],
            y=[5.0] * len(no_odds),
            mode="markers",
            marker=dict(size=10, color=colors_no.tolist(), symbol="diamond",
                        line=dict(color="white", width=0.8)),
            customdata=np.column_stack([
                no_odds["opponent"].fillna("").values,
                no_odds["result"].values,
                no_odds["event_name"].fillna("").values,
            ]),
            hovertemplate=(
                "<b>%{customdata[2]}</b><br>"
                "vs %{customdata[0]}: %{customdata[1]}<br>"
                "no odds data<extra></extra>"
            ),
            showlegend=False,
            name="no odds",
        ))

    if not fig.data:
        return _empty_figure("no fight data available", title=title, height=300)

    fig.add_hline(y=50, line_dash="dash", line_color="#94a3b8")
    _apply_chart_layout(fig, height=300)
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Market win probability",
        showlegend=False,
        margin=dict(t=54, r=30, b=42, l=64),
    )
    fig.update_yaxes(range=[0, 100], ticksuffix="%")
    return fig


def favorite_underdog_performance_table(
    odds_lines: pd.DataFrame | None,
    fights: pd.DataFrame,
) -> pd.DataFrame:
    """Win rates and outcome counts for market-favorites vs underdogs."""
    cols = ["bucket", "bouts", "wins", "draws", "win_rate", "expected_win_rate"]
    if odds_lines is None or odds_lines.empty or fights is None or fights.empty:
        return pd.DataFrame(columns=cols)

    needed = {"fight_url", "market_favorite", "market_underdog",
              "market_favorite_prob", "market_underdog_prob", "odds_data_quality"}
    if not needed.issubset(odds_lines.columns):
        return pd.DataFrame(columns=cols)

    ok = odds_lines[odds_lines["odds_data_quality"] == "ok"].copy()
    if ok.empty:
        return pd.DataFrame(columns=cols)

    join = ok.merge(
        fights[["fight_url", "winner", "is_draw"]],
        on="fight_url", how="inner",
    )

    def _agg(side: str) -> dict:
        fighter_col = "market_favorite" if side == "favorite" else "market_underdog"
        prob_col = "market_favorite_prob" if side == "favorite" else "market_underdog_prob"
        rows = join.dropna(subset=[fighter_col])
        if rows.empty:
            return {
                "bucket": side, "bouts": 0, "wins": 0, "draws": 0,
                "win_rate": float("nan"), "expected_win_rate": float("nan"),
            }
        wins = int((rows[fighter_col] == rows["winner"]).sum())
        draws = int(rows["is_draw"].fillna(False).astype(bool).sum())
        decided = len(rows) - draws
        return {
            "bucket": side,
            "bouts": int(len(rows)),
            "wins": wins,
            "draws": draws,
            "win_rate": wins / decided if decided else float("nan"),
            "expected_win_rate": float(rows[prob_col].mean()),
        }

    return pd.DataFrame([_agg("favorite"), _agg("underdog")], columns=cols)


# ---------------------------------------------------------------------------
# Win streaks — ranking + per-fighter rating timeline
#
# A win streak is a maximal run of consecutive wins in a fighter's
# chronological record. Draws and losses break a streak; no-contests and
# excluded bouts are skipped (they neither extend nor break it), matching how
# streaks are conventionally counted. Streaks are scored both by raw length
# and by the average strength of the opponents beaten, so the notebook can
# rank "longest" or "most impressive".

def _fighter_results_long(fights: pd.DataFrame) -> pd.DataFrame:
    """One row per fighter appearance with a clean win/loss/draw/nc outcome."""
    if fights is None or fights.empty:
        return pd.DataFrame(columns=[
            "fighter", "opponent", "event_date", "event_name", "division",
            "outcome", "is_title_fight", "method_class",
        ])
    f = add_division_to_fights(fights)
    if "is_excluded" in f.columns:
        f = f[~f["is_excluded"].fillna(False).astype(bool)]
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    keep = [
        "event_date", "event_name", "division", "winner", "loser",
        "is_draw", "is_nc", "is_title_fight", "method_class",
    ]
    keep = [c for c in keep if c in f.columns]
    frames = []
    for side, opp in (("fighter_a", "fighter_b"), ("fighter_b", "fighter_a")):
        sub = f[keep + [side, opp]].rename(columns={side: "fighter", opp: "opponent"})
        frames.append(sub)
    long = pd.concat(frames, ignore_index=True).dropna(subset=["fighter"])
    is_draw = long.get("is_draw", pd.Series(False, index=long.index)).fillna(False).astype(bool)
    is_nc = long.get("is_nc", pd.Series(False, index=long.index)).fillna(False).astype(bool)
    is_win = long["winner"].eq(long["fighter"]) if "winner" in long.columns else pd.Series(False, index=long.index)
    long["outcome"] = np.select(
        [is_nc, is_draw, is_win],
        ["nc", "draw", "win"],
        default="loss",
    )
    return long.sort_values(["fighter", "event_date"]).reset_index(drop=True)


def win_streaks(
    fights: pd.DataFrame,
    ratings_current: pd.DataFrame | None = None,
    *,
    min_len: int = 2,
) -> pd.DataFrame:
    """Return every win streak (>= ``min_len``) as one row, scored by quality.

    Columns: fighter, length, start_date, end_date, division (modal), divisions,
    opponents, title_wins, finishes, avg_opp_rating, ongoing, ended_by, gender.
    """
    cols = [
        "fighter", "length", "start_date", "end_date", "division", "divisions",
        "opponents", "title_wins", "finishes", "avg_opp_rating", "ongoing",
        "ended_by", "gender",
    ]
    long = _fighter_results_long(fights)
    if long.empty:
        return pd.DataFrame(columns=cols)

    opp_mu: dict[str, float] = {}
    gender_map: dict[str, str] = {}
    if ratings_current is not None and not ratings_current.empty:
        if "mu_canonical" in ratings_current.columns:
            opp_mu = dict(zip(ratings_current["fighter"], pd.to_numeric(
                ratings_current["mu_canonical"], errors="coerce")))
        if "gender" in ratings_current.columns:
            gender_map = dict(zip(ratings_current["fighter"], ratings_current["gender"]))

    finish_methods = {"KO/TKO", "Submission"}
    records: list[dict] = []

    def _emit(fighter: str, run: list, ended_by: str, ongoing: bool) -> None:
        if len(run) < min_len:
            return
        divisions = [r.division for r in run if isinstance(r.division, str)]
        modal_div = pd.Series(divisions).mode().iloc[0] if divisions else None
        opp_ratings = [opp_mu.get(r.opponent) for r in run]
        opp_ratings = [v for v in opp_ratings if v is not None and not pd.isna(v)]
        records.append({
            "fighter": fighter,
            "length": len(run),
            "start_date": run[0].event_date,
            "end_date": run[-1].event_date,
            "division": modal_div,
            "divisions": sorted(set(divisions)),
            "opponents": [r.opponent for r in run],
            "title_wins": int(sum(bool(getattr(r, "is_title_fight", False)) for r in run)),
            "finishes": int(sum(str(getattr(r, "method_class", "")) in finish_methods for r in run)),
            "avg_opp_rating": float(np.mean(opp_ratings)) if opp_ratings else float("nan"),
            "ongoing": ongoing,
            "ended_by": ended_by,
            "gender": gender_map.get(fighter),
        })

    for fighter, g in long.groupby("fighter", sort=False):
        run: list = []
        for row in g.itertuples(index=False):
            oc = row.outcome
            if oc == "win":
                run.append(row)
            elif oc == "nc":
                continue
            else:  # loss or draw breaks the streak
                verb = "Draw with" if oc == "draw" else "Loss to"
                _emit(fighter, run, f"{verb} {row.opponent}", ongoing=False)
                run = []
        _emit(fighter, run, "Active", ongoing=True)

    out = pd.DataFrame(records, columns=cols)
    if out.empty:
        return out
    return out.sort_values(
        ["length", "avg_opp_rating", "title_wins"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def win_streaks_table(
    fights: pd.DataFrame,
    ratings_current: pd.DataFrame | None = None,
    *,
    min_len: int = 3,
    n: int = 25,
    division: str | None = None,
    gender: str | None = None,
    sort_by: str = "length",
) -> pd.DataFrame:
    """Display-ready, filtered, ranked win-streak table."""
    streaks = win_streaks(fights, ratings_current, min_len=min_len)
    if streaks.empty:
        return streaks
    if division and division != "All":
        streaks = streaks[streaks["divisions"].apply(lambda ds: division in (ds or []))]
    if gender in ("M", "F"):
        streaks = streaks[streaks["gender"].eq(gender)]
    if streaks.empty:
        return streaks.iloc[0:0]
    if sort_by == "quality":
        streaks = streaks.sort_values(
            ["avg_opp_rating", "length", "title_wins"], ascending=False)
    elif sort_by == "title_wins":
        streaks = streaks.sort_values(
            ["title_wins", "length", "avg_opp_rating"], ascending=False)
    else:
        streaks = streaks.sort_values(
            ["length", "avg_opp_rating", "title_wins"], ascending=False)
    return streaks.head(n).reset_index(drop=True)


def _add_streak_traces(
    fig: go.Figure,
    fighter: str,
    history: pd.DataFrame,
    fights: pd.DataFrame,
    rating_col: str,
    *,
    line_color: str,
    marker_label_prefix: str = "",
    outcome_overrides: dict | None = None,
) -> None:
    """Add a fighter's rating line + outcome markers to an existing figure."""
    h = history[history["fighter"].eq(fighter)].copy()
    if h.empty:
        return
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h = h.sort_values("event_date")
    results = _fighter_results_long(fights)
    results = results[results["fighter"].eq(fighter)][["event_date", "opponent", "outcome"]]
    merged = h.merge(results, on="event_date", how="left")

    fig.add_trace(go.Scatter(
        x=h["event_date"], y=h[rating_col],
        mode="lines",
        line=dict(color=line_color, width=2.5, shape="spline", smoothing=0.4),
        name=f"{fighter} rating",
        hoverinfo="skip",
        showlegend=True,
    ))
    outcome_color = outcome_overrides or {
        "win": THEME["positive"], "loss": THEME["negative"],
        "draw": THEME["neutral"], "nc": THEME["text_caption"],
    }
    for outcome, label in (("win", "Win"), ("loss", "Loss"), ("draw", "Draw"), ("nc", "No contest")):
        seg = merged[merged["outcome"].eq(outcome)]
        if seg.empty:
            continue
        trace_label = f"{marker_label_prefix}{label}" if marker_label_prefix else label
        fig.add_trace(go.Scatter(
            x=seg["event_date"], y=seg[rating_col],
            mode="markers",
            name=trace_label,
            marker=dict(size=10, color=outcome_color[outcome],
                        line=dict(color=THEME["bg"], width=1.5)),
            customdata=seg["opponent"].fillna("").to_numpy()[:, None],
            hovertemplate=(
                f"<b>{fighter} — {label}</b> vs %{{customdata[0]}}<br>"
                "%{x|%b %d, %Y}<br>"
                f"{_metric_label(rating_col)}=%{{y:.1f}}<extra></extra>"
            ),
            showlegend=False,
        ))


def streak_timeline_chart(
    fighter: str,
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    rating_col: str = "mu_canonical",
    highlight_start=None,
    highlight_end=None,
    streak_len: int | None = None,
    overlay_fighter: str | None = None,
    overlay_highlight_start=None,
    overlay_highlight_end=None,
    overlay_streak_len: int | None = None,
) -> go.Figure:
    """Rating timeline for a fighter, with optional overlay of a second fighter.

    The primary fighter's streak window is shaded in the accent color so their
    rating arc over the run is obvious. When ``overlay_fighter`` is provided
    (the win-streak section's fighter search), that fighter's full rating
    timeline is drawn on the same axes in a contrasting color so the two runs
    can be compared head to head — outcome markers are kept separate per
    fighter, and a second streak window can be shaded.
    """
    title = f"{fighter}: rating timeline"
    if overlay_fighter and overlay_fighter != fighter:
        title = f"{fighter} vs {overlay_fighter}: rating timelines"
    if ratings_history is None or ratings_history.empty or not fighter:
        return _empty_figure("rating history unavailable", title=title, height=420)
    if rating_col not in ratings_history.columns:
        rating_col = "mu_canonical"
    if ratings_history[ratings_history["fighter"].eq(fighter)].empty:
        return _empty_figure(f"no rating history for {fighter}", title=title, height=420)

    fig = go.Figure()
    _add_streak_traces(
        fig, fighter, ratings_history, fights, rating_col,
        line_color=THEME["primary"],
    )

    # Shade the primary streak window.
    if highlight_start is not None and highlight_end is not None:
        hs = pd.to_datetime(highlight_start)
        he = pd.to_datetime(highlight_end)
        fig.add_vrect(
            x0=hs, x1=he,
            fillcolor=_hex_to_rgba(THEME["accent"], 0.14),
            line_width=0,
            layer="below",
        )
        label = "win streak" if streak_len is None else f"{streak_len}-fight win streak"
        fig.add_annotation(
            x=hs + (he - hs) / 2, y=1.0, yref="paper",
            text=f"{fighter}: {label}", showarrow=False, yanchor="bottom",
            font=dict(color=THEME["accent"], size=12),
        )

    # Overlay a second fighter — full timeline so the comparison is honest, not
    # just the streak window. Marker outcome colors stay the same so wins still
    # read green / losses red regardless of which fighter the marker belongs to.
    if overlay_fighter and overlay_fighter != fighter:
        if not ratings_history[ratings_history["fighter"].eq(overlay_fighter)].empty:
            _add_streak_traces(
                fig, overlay_fighter, ratings_history, fights, rating_col,
                line_color=THEME["secondary"],
                marker_label_prefix=f"{overlay_fighter} ",
            )
            if overlay_highlight_start is not None and overlay_highlight_end is not None:
                ohs = pd.to_datetime(overlay_highlight_start)
                ohe = pd.to_datetime(overlay_highlight_end)
                fig.add_vrect(
                    x0=ohs, x1=ohe,
                    fillcolor=_hex_to_rgba(THEME["secondary"], 0.10),
                    line_width=0, layer="below",
                )
                olabel = ("win streak" if overlay_streak_len is None
                          else f"{overlay_streak_len}-fight win streak")
                fig.add_annotation(
                    x=ohs + (ohe - ohs) / 2, y=0.96, yref="paper",
                    text=f"{overlay_fighter}: {olabel}", showarrow=False, yanchor="bottom",
                    font=dict(color=THEME["secondary"], size=11),
                )

    _apply_chart_layout(fig, height=460)
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title=_metric_label(rating_col),
        hovermode="closest",
        legend=dict(orientation="h", y=1.10, x=0, yanchor="bottom"),
    )
    return fig


# ---------------------------------------------------------------------------
# Convenience: list fighters with names that match a search prefix

def fighter_search(ratings_current: pd.DataFrame, prefix: str, limit: int = 20) -> list[str]:
    if not prefix:
        return ratings_current.sort_values("mu_canonical", ascending=False)["fighter"].head(limit).tolist()
    mask = ratings_current["fighter"].str.contains(prefix, case=False, na=False)
    matches = ratings_current[mask].sort_values("mu_canonical", ascending=False)
    return matches["fighter"].head(limit).tolist()
