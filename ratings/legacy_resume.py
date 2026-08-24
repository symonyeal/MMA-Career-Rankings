"""Public legacy scoring built from skill mass plus a resume ledger.

The latent rating estimates how strong a fighter looked from bout outcomes.
That is not the same public question as "greatest": title fights, title wins,
successful defenses, and belts in multiple divisions are resume achievements.
They belong in a transparent board-layer ledger, not inside the likelihood that
learns fighter strength.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from loaders.fightmatrix_organizations import normalize_organization
from ratings.performance_adjustment import is_real_ufc_title_bout, normalize_division_label


LEGACY_SCORE_COLUMNS = [
    "fighter",
    "public_legacy_score",
    "public_legacy_skill_mass",
    "public_legacy_skill_score",
    "public_legacy_exposure_factor",
    "public_legacy_title_score",
    "public_legacy_schedule_score",
    "public_legacy_title_appearances",
    "public_legacy_title_wins",
    "public_legacy_title_defenses",
    "public_legacy_title_win_divisions",
    "public_legacy_rank_context_win_mass",
    "public_legacy_multi_division_bonus",
    "public_legacy_ufc_bouts",
    "public_legacy_top_org_bouts",
    "public_legacy_unknown_org_bouts",
]

# Point values are in the same display units as Career Skill Mass
# (rating-point-years). They are deliberately small enough that the skill
# trajectory still matters, but large enough that a decade-long title reign is
# not ranked below a clean, lightly contextualized record.
TITLE_APPEARANCE_POINTS = 20.0
TITLE_WIN_POINTS = 45.0
TITLE_DEFENSE_POINTS = 60.0
MULTI_DIVISION_TITLE_POINTS = 600.0
RANK_CONTEXT_WIN_POINTS = 1200.0

ORG_FACTOR_BY_CANONICAL = {
    "UFC": 1.0,
    "PRIDE": 0.95,
    "Affliction": 0.90,
    "Strikeforce": 0.88,
    "WEC": 0.88,
    "Bellator": 0.65,
    "PFL": 0.60,
    "RIZIN": 0.60,
    "ONE": 0.60,
    "DREAM": 0.60,
}
ORG_FACTOR_BY_TIER = {
    1: 0.82,
    2: 0.60,
    3: 0.42,
    4: 0.20,
}


TITLE_COUNT_COLUMNS = [
    "fighter",
    "public_legacy_title_appearances",
    "public_legacy_title_wins",
    "public_legacy_title_defenses",
    "public_legacy_title_win_divisions",
]
TITLE_LEDGER_COLUMNS = [
    *TITLE_COUNT_COLUMNS,
    "public_legacy_source_title_score",
]

EXPOSURE_LEDGER_COLUMNS = [
    "fighter",
    "public_legacy_exposure_factor",
    "public_legacy_ufc_bouts",
    "public_legacy_top_org_bouts",
    "public_legacy_unknown_org_bouts",
]

COMBINED_TITLE_LEDGER_COLUMNS = [
    *TITLE_COUNT_COLUMNS,
    "public_legacy_rank_context_win_mass",
    "public_legacy_appearance_title_score",
    "public_legacy_source_title_score",
]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=LEGACY_SCORE_COLUMNS)


def _empty_title_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=TITLE_LEDGER_COLUMNS)


def _empty_exposure_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=EXPOSURE_LEDGER_COLUMNS)


def _title_points(
    appearances: pd.Series | np.ndarray | float,
    wins: pd.Series | np.ndarray | float,
    defenses: pd.Series | np.ndarray | float,
    divisions: pd.Series | np.ndarray | float,
) -> pd.Series | float:
    extra_divisions = np.maximum(0, divisions - 1)
    return (
        TITLE_APPEARANCE_POINTS * appearances
        + TITLE_WIN_POINTS * wins
        + TITLE_DEFENSE_POINTS * defenses
        + MULTI_DIVISION_TITLE_POINTS * extra_divisions
    )


def _organization_factor(canonical_organization: object, tier: object) -> float:
    org = str(canonical_organization or "Unknown")
    if org in ORG_FACTOR_BY_CANONICAL:
        return ORG_FACTOR_BY_CANONICAL[org]
    tier_num = pd.to_numeric(pd.Series([tier]), errors="coerce").iloc[0]
    if pd.isna(tier_num):
        return ORG_FACTOR_BY_TIER[4]
    return ORG_FACTOR_BY_TIER.get(int(tier_num), ORG_FACTOR_BY_TIER[4])


def _legacy_division_bucket(weight_class: object) -> str | None:
    """Normalize title divisions for cross-promotion public resume counts."""
    label = normalize_division_label(weight_class)
    if not isinstance(label, str):
        return None
    text = " ".join(label.split()).strip()
    for prefix in ("Women's ", "Womens ", "Female "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text or None


def _organization_context(fights: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "fight_url",
        "canonical_organization",
        "organization_tier",
        "public_legacy_org_factor",
    ]
    if fights is None or fights.empty or "fight_url" not in fights.columns:
        return pd.DataFrame(columns=columns)

    work = fights[["fight_url", "event_date"]].copy()
    work["source"] = fights.get("source", pd.Series("", index=fights.index))
    work["org"] = fights.get("org", pd.Series(pd.NA, index=fights.index))
    work["event_date"] = pd.to_datetime(work["event_date"], errors="coerce")
    work["_org_label"] = work["org"].fillna("Unknown").astype(str)
    ufc_source = work["source"].astype(str).eq("ufc") & work["org"].isna()
    work.loc[ufc_source, "_org_label"] = "UFC"
    work["_year"] = work["event_date"].dt.year.fillna(0).astype(int)

    keys = (
        work.groupby(["_org_label", "_year"], dropna=False, as_index=False)
        .agg(sample_date=("event_date", "median"))
    )
    records = []
    for org_label, year, sample_date in keys[
        ["_org_label", "_year", "sample_date"]
    ].itertuples(index=False, name=None):
        rec = normalize_organization(org_label, sample_date)
        records.append(
            {
                "_org_label": org_label,
                "_year": year,
                "canonical_organization": rec["canonical_organization"],
                "organization_tier": rec["organization_tier"],
                "public_legacy_org_factor": _organization_factor(
                    rec["canonical_organization"], rec["organization_tier"]
                ),
            }
        )
    mapped = work.merge(pd.DataFrame(records), on=["_org_label", "_year"], how="left")
    return mapped[columns].drop_duplicates("fight_url")


def organization_exposure_ledger(fights: pd.DataFrame) -> pd.DataFrame:
    """Evaluate how much of each career was proven in top organization context."""
    if fights is None or fights.empty or "fighter_a" not in fights.columns:
        return _empty_exposure_ledger()

    context = _organization_context(fights)
    sides = pd.concat(
        [
            fights[["fight_url", "fighter_a"]].rename(columns={"fighter_a": "fighter"}),
            fights[["fight_url", "fighter_b"]].rename(columns={"fighter_b": "fighter"}),
        ],
        ignore_index=True,
        sort=False,
    )
    sides = sides.merge(context, on="fight_url", how="left")
    sides["public_legacy_org_factor"] = pd.to_numeric(
        sides["public_legacy_org_factor"], errors="coerce"
    ).fillna(ORG_FACTOR_BY_TIER[4])
    sides["_is_ufc"] = sides["canonical_organization"].eq("UFC")
    sides["_is_top_org"] = sides["public_legacy_org_factor"].ge(0.82)
    sides["_is_unknown_org"] = sides["canonical_organization"].fillna("Unknown").eq("Unknown")

    def _top_quartile_mean(values: pd.Series) -> float:
        clean = pd.to_numeric(values, errors="coerce").dropna().sort_values(ascending=False)
        if clean.empty:
            return ORG_FACTOR_BY_TIER[4]
        return float(clean.head(max(1, int(np.ceil(len(clean) * 0.25)))).mean())

    grouped = sides.groupby("fighter", sort=False)
    out = grouped.agg(
        _mean_factor=("public_legacy_org_factor", "mean"),
        _top_quartile_factor=("public_legacy_org_factor", _top_quartile_mean),
        public_legacy_ufc_bouts=("_is_ufc", "sum"),
        public_legacy_top_org_bouts=("_is_top_org", "sum"),
        public_legacy_unknown_org_bouts=("_is_unknown_org", "sum"),
    ).reset_index()
    out["public_legacy_exposure_factor"] = (
        0.5 * pd.to_numeric(out["_mean_factor"], errors="coerce").fillna(ORG_FACTOR_BY_TIER[4])
        + 0.5 * pd.to_numeric(out["_top_quartile_factor"], errors="coerce").fillna(ORG_FACTOR_BY_TIER[4])
    ).clip(lower=ORG_FACTOR_BY_TIER[4], upper=1.0)
    for col in (
        "public_legacy_ufc_bouts",
        "public_legacy_top_org_bouts",
        "public_legacy_unknown_org_bouts",
    ):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    return out[EXPOSURE_LEDGER_COLUMNS]


def championship_resume_ledger(appearances: pd.DataFrame) -> pd.DataFrame:
    """Count public resume achievements from appearance context rows."""
    columns = [
        "fighter",
        "public_legacy_title_appearances",
        "public_legacy_title_wins",
        "public_legacy_title_defenses",
        "public_legacy_title_win_divisions",
        "public_legacy_rank_context_win_mass",
    ]
    if appearances is None or appearances.empty or "fighter" not in appearances.columns:
        return pd.DataFrame(columns=columns)

    app = appearances.copy()
    idx = app.index
    title = (
        app.get("is_championship_bout", pd.Series(False, index=idx)).fillna(False).astype(bool)
        | app.get("is_interim_title_bout", pd.Series(False, index=idx)).fillna(False).astype(bool)
    )
    won = pd.to_numeric(
        app.get("actual_score", pd.Series(0.0, index=idx)),
        errors="coerce",
    ).fillna(0.0).ge(1.0)
    entered_champ = (
        app.get("fighter_entered_as_champion", pd.Series(False, index=idx))
        .fillna(False)
        .astype(bool)
        | app.get("fighter_entered_as_interim_champion", pd.Series(False, index=idx))
        .fillna(False)
        .astype(bool)
    )
    app["_title"] = title
    app["_title_win"] = title & won
    app["_title_defense"] = title & won & entered_champ
    app["_rank_context_win_mass"] = np.where(
        won,
        (
            pd.to_numeric(
                app.get("perf_factor_rank_context", pd.Series(1.0, index=idx)),
                errors="coerce",
            )
            .fillna(1.0)
            .sub(1.0)
            .clip(lower=0.0)
        ),
        0.0,
    )

    grouped = app.groupby("fighter", sort=False)
    out = grouped.agg(
        public_legacy_title_appearances=("_title", "sum"),
        public_legacy_title_wins=("_title_win", "sum"),
        public_legacy_title_defenses=("_title_defense", "sum"),
        public_legacy_rank_context_win_mass=("_rank_context_win_mass", "sum"),
    ).reset_index()

    if "division" in app.columns:
        divisions = (
            app.loc[app["_title_win"]]
            .assign(_division_bucket=lambda x: x["division"].map(_legacy_division_bucket))
            .dropna(subset=["_division_bucket"])
            .groupby("fighter")["_division_bucket"]
            .nunique()
            .rename("public_legacy_title_win_divisions")
            .reset_index()
        )
        out = out.merge(divisions, on="fighter", how="left")
    else:
        out["public_legacy_title_win_divisions"] = 0

    for col in columns:
        if col == "fighter":
            continue
        if col == "public_legacy_rank_context_win_mass":
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    return out[columns]


def source_title_resume_ledger(fights: pd.DataFrame) -> pd.DataFrame:
    """Count title resume from source fight rows.

    ``performance_appearances`` deliberately narrows championship context to
    UFC divisional title bouts for its performance factor. The public legacy
    board needs the source title facts across the rated scope, including PRIDE,
    WEC, Strikeforce, Bellator, and RIZIN rows that already carry
    ``is_title_fight``.
    """
    if fights is None or fights.empty or "fighter_a" not in fights.columns:
        return _empty_title_ledger()

    f = fights.copy()
    f = f.merge(_organization_context(f), on="fight_url", how="left")
    idx = f.index
    raw_title = f.get("is_title_fight", pd.Series(False, index=idx)).fillna(False).astype(bool)
    ufc_org = f["canonical_organization"].eq("UFC")
    real_ufc_title = f.get("weight_class", pd.Series(pd.NA, index=idx)).map(
        is_real_ufc_title_bout
    )
    f["_is_title"] = np.where(ufc_org, real_ufc_title, raw_title)
    f = f[f["_is_title"]].copy()
    if f.empty:
        return _empty_title_ledger()

    f["event_date"] = pd.to_datetime(f.get("event_date", pd.Series(pd.NaT, index=f.index)), errors="coerce")
    f["_division"] = f.get("weight_class", pd.Series(pd.NA, index=f.index)).map(
        _legacy_division_bucket
    )
    f["_title_factor"] = pd.to_numeric(
        f["public_legacy_org_factor"], errors="coerce"
    ).fillna(ORG_FACTOR_BY_TIER[4])
    if "org" not in f.columns:
        f["org"] = ""
    f["_org_division"] = (
        f["canonical_organization"].fillna("Unknown").astype(str)
        + "::"
        + f["_division"].fillna("").astype(str)
    )
    f["_winner"] = f.get("winner", pd.Series(pd.NA, index=f.index))
    f["_is_draw"] = f.get("is_draw", pd.Series(False, index=f.index)).fillna(False).astype(bool)
    f = f.sort_values(["event_date", "event_name", "fight_url"], na_position="last")

    champions: dict[str, str] = {}
    defense_by_url_fighter: set[tuple[object, str]] = set()
    for fight_url, org_division, winner, is_draw in f[
        ["fight_url", "_org_division", "_winner", "_is_draw"]
    ].itertuples(index=False, name=None):
        org_division = str(org_division)
        if pd.isna(winner) or bool(is_draw):
            continue
        winner = str(winner)
        incumbent = champions.get(org_division)
        if incumbent == winner:
            defense_by_url_fighter.add((fight_url, winner))
        champions[org_division] = winner

    def _side(side: str) -> pd.DataFrame:
        other = "b" if side == "a" else "a"
        frame = f[
            [
                "fight_url",
                "event_date",
                "_division",
                f"fighter_{side}",
                f"fighter_{other}",
                "_winner",
                "_is_draw",
                "_title_factor",
                "canonical_organization",
            ]
        ].rename(
            columns={
                f"fighter_{side}": "fighter",
                f"fighter_{other}": "opponent",
                "_winner": "winner",
                "_is_draw": "is_draw",
            }
        )
        return frame

    app = pd.concat([_side("a"), _side("b")], ignore_index=True, sort=False)
    app["title_appearance"] = True
    app["title_win"] = app["winner"].eq(app["fighter"]) & ~app["is_draw"].fillna(False).astype(bool)
    app["title_defense"] = [
        (fight_url, fighter) in defense_by_url_fighter
        for fight_url, fighter in zip(app["fight_url"], app["fighter"])
    ]
    missing_division_wins = app["title_win"] & app["_division"].isna()
    if missing_division_wins.any():
        fallback = app.loc[missing_division_wins, [
            "fight_url",
            "fighter",
            "event_date",
            "canonical_organization",
        ]].copy()
        fallback["_win_number"] = (
            fallback.sort_values(["fighter", "canonical_organization", "event_date", "fight_url"])
            .groupby(["fighter", "canonical_organization"])
            .cumcount()
        )
        fallback_defenses = {
            (fight_url, fighter)
            for fight_url, fighter in fallback.loc[
                fallback["_win_number"].gt(0), ["fight_url", "fighter"]
            ].itertuples(index=False, name=None)
        }
        fallback_mask = pd.Series(
            [
                (fight_url, fighter) in fallback_defenses
                for fight_url, fighter in zip(app["fight_url"], app["fighter"])
            ],
            index=app.index,
        )
        app["title_defense"] = app["title_defense"] | fallback_mask

    grouped = app.groupby("fighter", sort=False)
    out = grouped.agg(
        public_legacy_title_appearances=("title_appearance", "sum"),
        public_legacy_title_wins=("title_win", "sum"),
        public_legacy_title_defenses=("title_defense", "sum"),
    ).reset_index()
    divisions = (
        app.loc[app["title_win"]]
        .dropna(subset=["_division"])
        .groupby("fighter")["_division"]
        .nunique()
        .rename("public_legacy_title_win_divisions")
        .reset_index()
    )
    out = out.merge(divisions, on="fighter", how="left")
    app["title_appearance_score"] = TITLE_APPEARANCE_POINTS * app["_title_factor"]
    app["title_win_score"] = np.where(
        app["title_win"], TITLE_WIN_POINTS * app["_title_factor"], 0.0
    )
    app["title_defense_score"] = np.where(
        app["title_defense"], TITLE_DEFENSE_POINTS * app["_title_factor"], 0.0
    )
    components = grouped.agg(
        _appearance_points=("title_appearance_score", "sum"),
        _win_points=("title_win_score", "sum"),
        _defense_points=("title_defense_score", "sum"),
    ).reset_index()
    out = out.merge(components, on="fighter", how="left")

    multi = []
    for fighter, group in app.loc[app["title_win"]].dropna(subset=["_division"]).groupby("fighter"):
        factors = (
            group.groupby("_division")["_title_factor"].max().sort_values(ascending=False).to_numpy()
        )
        bonus = MULTI_DIVISION_TITLE_POINTS * float(factors[1:].sum()) if len(factors) > 1 else 0.0
        multi.append({"fighter": fighter, "_multi_division_points": bonus})
    out = out.merge(pd.DataFrame(multi), on="fighter", how="left")
    out["public_legacy_source_title_score"] = (
        pd.to_numeric(out["_appearance_points"], errors="coerce").fillna(0.0)
        + pd.to_numeric(out["_win_points"], errors="coerce").fillna(0.0)
        + pd.to_numeric(out["_defense_points"], errors="coerce").fillna(0.0)
        + pd.to_numeric(out["_multi_division_points"], errors="coerce").fillna(0.0)
    )

    for col in TITLE_COUNT_COLUMNS:
        if col == "fighter":
            continue
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    out["public_legacy_source_title_score"] = pd.to_numeric(
        out["public_legacy_source_title_score"], errors="coerce"
    ).fillna(0.0)
    return out[TITLE_LEDGER_COLUMNS]


def _combine_title_ledgers(
    appearance_ledger: pd.DataFrame,
    source_ledger: pd.DataFrame,
) -> pd.DataFrame:
    app = appearance_ledger.copy() if appearance_ledger is not None else pd.DataFrame()
    source = source_ledger.copy() if source_ledger is not None else pd.DataFrame()
    if app.empty and source.empty:
        return pd.DataFrame(columns=COMBINED_TITLE_LEDGER_COLUMNS)
    if app.empty:
        app = pd.DataFrame(columns=[*TITLE_COUNT_COLUMNS, "public_legacy_rank_context_win_mass"])
    if source.empty:
        source = pd.DataFrame(columns=TITLE_LEDGER_COLUMNS)

    if not app.empty:
        app["public_legacy_appearance_title_score"] = _title_points(
            pd.to_numeric(app["public_legacy_title_appearances"], errors="coerce").fillna(0),
            pd.to_numeric(app["public_legacy_title_wins"], errors="coerce").fillna(0),
            pd.to_numeric(app["public_legacy_title_defenses"], errors="coerce").fillna(0),
            pd.to_numeric(app["public_legacy_title_win_divisions"], errors="coerce").fillna(0),
        )
    if "public_legacy_source_title_score" not in source.columns:
        source["public_legacy_source_title_score"] = 0.0

    out = app.merge(
        source,
        on="fighter",
        how="outer",
        suffixes=("_appearance", "_source"),
    )
    for col in TITLE_COUNT_COLUMNS:
        if col == "fighter":
            continue
        app_col = f"{col}_appearance"
        source_col = f"{col}_source"
        out[col] = np.maximum(
            pd.to_numeric(out.get(app_col), errors="coerce").fillna(0),
            pd.to_numeric(out.get(source_col), errors="coerce").fillna(0),
        ).astype(int)
    rank_context = "public_legacy_rank_context_win_mass"
    if rank_context not in out.columns:
        out[rank_context] = 0.0
    out[rank_context] = pd.to_numeric(out[rank_context], errors="coerce").fillna(0.0)

    if "public_legacy_appearance_title_score" not in out.columns:
        out["public_legacy_appearance_title_score"] = 0.0
    if "public_legacy_source_title_score" not in out.columns:
        out["public_legacy_source_title_score"] = 0.0
    for col in ("public_legacy_appearance_title_score", "public_legacy_source_title_score"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out[COMBINED_TITLE_LEDGER_COLUMNS]


def public_legacy_score_rows(
    current: pd.DataFrame,
    appearances: pd.DataFrame,
    *,
    skill_col: str = "symon_career_skill_mass",
    source_fights: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one public legacy score row per fighter.

    The score is:

    exposure-adjusted Career Skill Mass
    + title resume points, using UFC lineage when available and source-title
      rows discounted by evaluated organization context
    + exposure-adjusted pre-fight rank/champion context on wins.

    The resume ledgers are intentionally auditable and additive. They repair the
    product-label bug without mutating the latent rating model.
    """
    if current is None or current.empty or skill_col not in current.columns:
        return _empty()

    out = current[["fighter", skill_col]].copy()
    out = out.rename(columns={skill_col: "public_legacy_skill_mass"})
    ledger = _combine_title_ledgers(
        championship_resume_ledger(appearances),
        source_title_resume_ledger(source_fights) if source_fights is not None else _empty_title_ledger(),
    )
    out = out.merge(ledger, on="fighter", how="left")
    exposure = (
        organization_exposure_ledger(source_fights)
        if source_fights is not None
        else _empty_exposure_ledger()
    )
    out = out.merge(exposure, on="fighter", how="left")
    for col in (
        "public_legacy_title_appearances",
        "public_legacy_title_wins",
        "public_legacy_title_defenses",
        "public_legacy_title_win_divisions",
    ):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    if "public_legacy_rank_context_win_mass" not in out.columns:
        out["public_legacy_rank_context_win_mass"] = 0.0
    out["public_legacy_rank_context_win_mass"] = pd.to_numeric(
        out["public_legacy_rank_context_win_mass"], errors="coerce"
    ).fillna(0.0)
    out["public_legacy_exposure_factor"] = pd.to_numeric(
        out["public_legacy_exposure_factor"], errors="coerce"
    ).fillna(1.0)
    for col in (
        "public_legacy_ufc_bouts",
        "public_legacy_top_org_bouts",
        "public_legacy_unknown_org_bouts",
    ):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    for col in ("public_legacy_appearance_title_score", "public_legacy_source_title_score"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    extra_divisions = np.maximum(0, out["public_legacy_title_win_divisions"] - 1)
    out["public_legacy_multi_division_bonus"] = (
        MULTI_DIVISION_TITLE_POINTS * extra_divisions
    )
    out["public_legacy_title_score"] = np.maximum(
        out["public_legacy_appearance_title_score"],
        out["public_legacy_source_title_score"],
    )
    out["public_legacy_schedule_score"] = (
        RANK_CONTEXT_WIN_POINTS * out["public_legacy_rank_context_win_mass"]
        * out["public_legacy_exposure_factor"]
    )
    out["public_legacy_skill_score"] = (
        pd.to_numeric(out["public_legacy_skill_mass"], errors="coerce").fillna(0.0)
        * out["public_legacy_exposure_factor"]
    )
    out["public_legacy_score"] = (
        out["public_legacy_skill_score"]
        + out["public_legacy_title_score"]
        + out["public_legacy_schedule_score"]
    )
    return out[LEGACY_SCORE_COLUMNS]
