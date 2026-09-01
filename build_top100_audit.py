"""Audit the public top 100 against supplied public-perception anchors."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from build_boards import (
    gender_partition,
    public_legacy_eligibility_override,
    select_core_rating_col,
)
from ratings import prequential as PQ
from ratings.age import load_birth_dates
from ratings.connectivity import connectivity
from ratings.legacy_resume import public_legacy_score_rows
from ratings.scope import DEFAULT_PUBLISHED_SCOPE


def _key(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).casefold())


def _add_anchor(
    anchors: dict[str, list[dict[str, object]]],
    canonical: dict[str, str],
    fighter: str,
    source: str,
    rank: int,
) -> None:
    k = _key(fighter)
    canonical.setdefault(k, fighter)
    anchors.setdefault(k, []).append({"source": source, "rank": int(rank)})


def _build_public_anchors() -> tuple[dict[str, list[dict[str, object]]], dict[str, str]]:
    """Public anchors supplied by the 2026-08-24 discrepancy prompt."""
    anchors: dict[str, list[dict[str, object]]] = {}
    canonical: dict[str, str] = {}
    tapology = [
        "Georges St-Pierre",
        "Demetrious Johnson",
        "Islam Makhachev",
        "Jon Jones",
        "Alexander Volkanovski",
        "Daniel Cormier",
        "Khabib Nurmagomedov",
        "Anderson Silva",
        "Ilia Topuria",
        "Jose Aldo",
    ]
    espn = [
        "Jon Jones",
        "Georges St-Pierre",
        "Anderson Silva",
        "Demetrious Johnson",
        "Khabib Nurmagomedov",
        "Fedor Emelianenko",
        "Randy Couture",
        "Chuck Liddell",
        "BJ Penn",
        "Kamaru Usman",
    ]
    the100 = {
        "Anderson Silva": 3,
        "Stipe Miocic": 9,
        "Ilia Topuria": 10,
        "Alex Pereira": 11,
        "Israel Adesanya": 12,
        "Dricus Du Plessis": 15,
        "Kamaru Usman": 16,
        "Max Holloway": 17,
        "Leon Edwards": 25,
        "Henry Cejudo": 26,
        "Alexandre Pantoja": 29,
        "Randy Couture": 31,
        "Alistair Overeem": 33,
        "Charles Oliveira": 34,
        "Dustin Poirier": 35,
        "Conor McGregor": 36,
        "Frank Shamrock": 38,
        "Robert Whittaker": 45,
        "Petr Yan": 52,
        "Ken Shamrock": 53,
        "Bas Rutten": 54,
        "Glover Teixeira": 60,
        "Vadim Nemkov": 62,
        "Ryan Bader": 63,
        "Phil Davis": 64,
        "Frankie Edgar": 65,
        "TJ Dillashaw": 71,
        "Josh Barnett": 72,
        "BJ Penn": 80,
        "Tyron Woodley": 81,
        "Tony Ferguson": 95,
        "Benson Henderson": 97,
        "Robbie Lawler": 98,
        "Tom Aspinall": 100,
    }
    for rank, fighter in enumerate(tapology, start=1):
        _add_anchor(anchors, canonical, fighter, "Tapology fan top 10", rank)
    for rank, fighter in enumerate(espn, start=1):
        _add_anchor(anchors, canonical, fighter, "ESPN 21st-century men top 10", rank)
    for fighter, rank in the100.items():
        _add_anchor(anchors, canonical, fighter, "The 100 Greatest", rank)
    return anchors, canonical


PUBLIC_ANCHORS, PUBLIC_CANONICAL_NAMES = _build_public_anchors()

PUBLIC_QUALITATIVE_ANCHORS = {
    _key("Amanda Nunes"): "public women's GOAT tier from discrepancy prompt",
    _key("Cristiane Justino"): "public women's GOAT tier from discrepancy prompt",
    _key("Valentina Shevchenko"): "public women's all-time elite tier",
    _key("Patricio Freire"): "publicly strong Bellator all-time tier from discrepancy prompt",
    _key("Ronda Rousey"): "public impact and women's pioneer tier from discrepancy prompt",
}

PUBLIC_NON_ANCHORS = {
    _key(name)
    for name in [
        "Usman Nurmagomedov",
        "Yaroslav Amosov",
        "A.J. McKee",
        "Johnny Eblen",
        "Kyoji Horiguchi",
        "Sean Sherk",
        "Ben Askren",
        "Michael Page",
        "Rajabali Shaidullaev",
        "Seika Izawa",
        "Timur Khizriev",
        "Vladimir Matyushenko",
        "Paulo Filho",
        "Andrey Koreshkov",
        "Ramazan Kuramagomedov",
        "Renato Sobral",
        "Jon Fitch",
        "Gilbert Melendez",
        "Joseph Benavidez",
        "Archie Colgan",
        "Vitaly Minakov",
        "Pedro Rizzo",
        "Tim Sylvia",
        "Miguel Torres",
        "Shinya Aoki",
        "Diego Sanchez",
        "Vitor Ribeiro",
        "Vladyslav Rudniev",
        "Ricco Rodriguez",
        "Oleg Popov",
        "Patchy Mix",
    ]
}

WATCH_BELOW_40 = [
    "Anderson Silva",
    "Demetrious Johnson",
    "Jose Aldo",
    "Stipe Miocic",
    "Kamaru Usman",
    "Max Holloway",
    "Amanda Nunes",
    "Charles Oliveira",
    "Dustin Poirier",
]


def _anchors_for_snapshot(
    snapshot: Path,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, str]]:
    anchors = {k: [dict(row) for row in rows] for k, rows in PUBLIC_ANCHORS.items()}
    canonical = dict(PUBLIC_CANONICAL_NAMES)
    fightmatrix = snapshot / "fightmatrix_all_time.parquet"
    if fightmatrix.exists():
        all_time = pd.read_parquet(fightmatrix)
        for row in all_time[["fighter", "rank"]].dropna(subset=["fighter", "rank"]).itertuples(index=False):
            _add_anchor(
                anchors,
                canonical,
                str(row.fighter),
                "FightMatrix all-time local snapshot",
                int(row.rank),
            )
    return anchors, canonical


def _anchor_rows(
    fighter: object,
    anchors: dict[str, list[dict[str, object]]] | None = None,
) -> list[dict[str, object]]:
    active = PUBLIC_ANCHORS if anchors is None else anchors
    return active.get(_key(fighter), [])


def _anchor_rank(
    fighter: object,
    anchors: dict[str, list[dict[str, object]]] | None = None,
) -> int | None:
    rows = _anchor_rows(fighter, anchors)
    return min((int(row["rank"]) for row in rows), default=None)


def _has_public_anchor(
    fighter: object,
    anchors: dict[str, list[dict[str, object]]] | None = None,
) -> bool:
    return bool(_anchor_rows(fighter, anchors)) or _key(fighter) in PUBLIC_QUALITATIVE_ANCHORS


def _anchor_reason(
    fighter: object,
    anchors: dict[str, list[dict[str, object]]] | None = None,
) -> str:
    rows = _anchor_rows(fighter, anchors)
    if rows:
        return "; ".join(f"{row['source']}: {row['rank']}" for row in rows)
    qualitative = PUBLIC_QUALITATIVE_ANCHORS.get(_key(fighter))
    if qualitative:
        return qualitative
    if _key(fighter) in PUBLIC_NON_ANCHORS:
        return "not in supplied public top-100/top-10 anchors"
    return "no supplied public anchor"


def _current_with_legacy(snapshot: Path, scope: str) -> pd.DataFrame:
    current = pd.read_parquet(snapshot / "ratings_current.parquet")
    if "public_legacy_score" in current.columns:
        return current
    appearances = snapshot / "performance_appearances.parquet"
    if "symon_career_skill_mass" in current.columns:
        appearance_rows = pd.read_parquet(appearances) if appearances.exists() else pd.DataFrame()
        current = current.merge(
            public_legacy_score_rows(
                current,
                appearance_rows,
                source_fights=PQ.load_fight_table(snapshot, scope=scope),
            ),
            on="fighter",
            how="left",
        )
    return current


def _ranked(current: pd.DataFrame, rating_col: str) -> pd.DataFrame:
    out = current.copy()
    out["score"] = pd.to_numeric(out[rating_col], errors="coerce")
    periods = pd.to_numeric(out["rating_periods"], errors="coerce").fillna(0)
    eligible = periods.ge(13)
    if rating_col == "public_legacy_score":
        eligible = eligible | public_legacy_eligibility_override(out)
    out = out[eligible & (out["score"] > 0)].copy()
    out = out.sort_values(["score", "fighter"], ascending=[False, True]).reset_index(drop=True)
    out["model_rank"] = np.arange(1, len(out) + 1)
    return out


def _coverage(fights: pd.DataFrame) -> pd.DataFrame:
    sides = pd.concat(
        [
            fights[["fighter_a", "source"]].rename(columns={"fighter_a": "fighter"}),
            fights[["fighter_b", "source"]].rename(columns={"fighter_b": "fighter"}),
        ],
        ignore_index=True,
    )
    return (
        sides.assign(is_ufc=sides["source"].eq("ufc"))
        .groupby("fighter", sort=False)
        .agg(total_bouts=("source", "size"), ufc_bouts=("is_ufc", "sum"))
        .reset_index()
    )


def _fmt_num(value: object, digits: int = 0) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):,.{digits}f}"


def _model_reason(row: pd.Series, rating_col: str) -> str:
    title_wins = int(row.get("public_legacy_title_wins", 0) or 0)
    defenses = int(row.get("public_legacy_title_defenses", 0) or 0)
    divisions = int(row.get("public_legacy_title_win_divisions", 0) or 0)
    total_bouts = int(row.get("total_bouts", 0) or 0)
    ufc_bouts = int(row.get("ufc_bouts", 0) or 0)
    source = "external-only" if ufc_bouts == 0 else f"{ufc_bouts}/{total_bouts} UFC-rated"
    return (
        f"{rating_col} {_fmt_num(row.get('score'), 1)}; "
        f"skill mass {_fmt_num(row.get('symon_career_skill_mass'), 1)}; "
        f"evaluated skill {_fmt_num(row.get('public_legacy_skill_score'), 1)} "
        f"(exposure {_fmt_num(row.get('public_legacy_exposure_factor'), 2)}); "
        f"contender resume {_fmt_num(row.get('public_legacy_resume_score'), 1)} "
        f"({int(row.get('public_legacy_contender_wins', 0) or 0)} wins); "
        f"title ledger {title_wins} wins/{defenses} defenses/{divisions} divisions; "
        f"{source}"
    )


def _outlier_class(row: pd.Series) -> str:
    rank = int(row["model_rank"])
    public_rank = row.get("public_anchor_rank")
    if pd.isna(public_rank):
        if bool(row.get("has_public_anchor", False)):
            return "qualitative_anchor_no_rank"
        if bool(row.get("external_only", False)) and bool(row.get("active_2024_plus", False)):
            return "active_external_unanchored"
        if rank <= 25:
            return "unanchored_top25"
        return "unanchored"

    delta = int(row["delta"])
    if rank <= 25 and int(public_rank) >= 50:
        return "severe_overplacement"
    if delta <= -40:
        return "severe_overplacement"
    if delta <= -20:
        return "overplacement"
    if delta >= 40:
        return "severe_underplacement"
    if delta >= 20:
        return "underplacement"
    return "aligned_or_explainable"


def _recommendation(row: pd.Series) -> str:
    title_wins = int(row.get("public_legacy_title_wins", 0) or 0)
    if row["outlier_class"] == "qualitative_anchor_no_rank":
        return "No numeric delta available; keep the qualitative public-resume explanation visible."
    if bool(row.get("external_only", False)) and title_wins == 0 and int(row["model_rank"]) <= 25:
        return (
            "Do not defend as proven public greatness yet: non-UFC title lineage "
            "is missing from the title ledger, so this is a skill-mass/crossover claim."
        )
    if row["outlier_class"] in {"severe_underplacement", "underplacement"}:
        return "Audit prime-vs-twilight and impact/title context; current score still trails public anchor."
    if row["outlier_class"] in {"severe_overplacement", "overplacement"}:
        return "Audit whether WHR smoothing backfilled future skill into early years or a closed external graph."
    if row["outlier_class"].startswith("unanchored"):
        return "Keep only with a written plain-English schedule-strength explanation."
    return "No immediate model change; keep the decomposition visible."


def _attach_public_audit(
    top: pd.DataFrame,
    rating_col: str,
    anchors: dict[str, list[dict[str, object]]],
) -> pd.DataFrame:
    out = top.copy()
    out["public_anchor_rank"] = out["fighter"].map(lambda name: _anchor_rank(name, anchors))
    out["delta"] = out["model_rank"] - out["public_anchor_rank"]
    out["has_public_anchor"] = out["fighter"].map(lambda name: _has_public_anchor(name, anchors))
    out["public_reason"] = out["fighter"].map(lambda name: _anchor_reason(name, anchors))
    out["model_reason"] = out.apply(lambda row: _model_reason(row, rating_col), axis=1)
    out["outlier_class"] = out.apply(_outlier_class, axis=1)
    out["recommended_fix_or_explanation"] = out.apply(_recommendation, axis=1)
    return out


def _missing_public(
    top: pd.DataFrame,
    anchors: dict[str, list[dict[str, object]]],
    canonical: dict[str, str],
) -> pd.DataFrame:
    top_keys = {_key(name) for name in top["fighter"]}
    rows = []
    for k, anchor_rows in anchors.items():
        if k in top_keys:
            continue
        best = min(int(row["rank"]) for row in anchor_rows)
        name = canonical[k]
        rows.append(
            {
                "fighter": name,
                "public_anchor_rank": best,
                "public_reason": _anchor_reason(name, anchors),
                "recommended_fix_or_explanation": (
                    "Missing from model top 100; inspect title/resume signal, "
                    "late-career smoothing, and data coverage."
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["public_anchor_rank", "fighter"]).reset_index(drop=True)


def _names(rows: Iterable[object]) -> list[str]:
    return [str(x) for x in rows if pd.notna(x)]


def build(snapshot: Path, *, scope: str, out_dir: Path) -> dict[str, object]:
    snapshot = Path(snapshot)
    anchors, canonical_names = _anchors_for_snapshot(snapshot)
    current = _current_with_legacy(snapshot, scope)
    rating_col = select_core_rating_col(current)
    # Audit the population that is actually PUBLISHED. Since 2026-08-28 the
    # default board is the men's component, so auditing the mixed population
    # here would score a board nobody ships -- and would keep counting women as
    # "unanchored" against anchor lists that are men's lists.
    partition = gender_partition(current)
    audited = partition.get("M", current)
    published = _ranked(audited, rating_col)
    women = partition.get("F")
    published_women = (
        _ranked(women, rating_col)
        if women is not None and not women.empty
        else published.iloc[0:0]
    )
    skill = (
        _ranked(audited, "symon_career_skill_mass")[["fighter", "model_rank", "score"]]
        if "symon_career_skill_mass" in current.columns
        else pd.DataFrame(columns=["fighter", "model_rank", "score"])
    )
    comparison = published[["fighter", "model_rank", "score"]].merge(
        skill,
        on="fighter",
        how="outer",
        suffixes=("_public", "_skill_mass"),
    )
    comparison["rank_change_vs_skill_mass"] = (
        comparison["model_rank_skill_mass"] - comparison["model_rank_public"]
    )

    top = published.head(100).copy()
    appearances = (
        pd.read_parquet(snapshot / "ratings_history_whr.parquet")
        .groupby("fighter", sort=False)
        .agg(first_appearance=("event_date", "min"), last_appearance=("event_date", "max"))
        .reset_index()
    )
    fights = PQ.load_fight_table(snapshot, scope=scope)
    canonical = pd.read_parquet(snapshot / "canonical_fights.parquet")
    top = top.merge(appearances, on="fighter", how="left").merge(
        _coverage(fights), on="fighter", how="left"
    )
    core = set(canonical["fighter_a"]) | set(canonical["fighter_b"])
    core_counts = pd.concat([canonical["fighter_a"], canonical["fighter_b"]]).value_counts().to_dict()
    conn = connectivity(
        fights.rename(columns={"fighter_a": "fighter_a_id", "fighter_b": "fighter_b_id"}),
        core,
        core_bout_counts=core_counts,
        fighters=top["fighter"].tolist(),
    )[["fighter_id", "disjoint_paths", "rankable"]]
    top = top.merge(conn, left_on="fighter", right_on="fighter_id", how="left").drop(
        columns="fighter_id"
    )
    birth_dates = load_birth_dates(snapshot)
    top["birth_date_known"] = top["fighter"].isin(birth_dates)
    top["active_2024_plus"] = top["last_appearance"].dt.year.ge(2024)
    top["external_only"] = top["ufc_bouts"].fillna(0).eq(0)
    top = _attach_public_audit(top, rating_col, anchors)

    missing = _missing_public(top, anchors, canonical_names)
    top25 = top.head(25)
    top10 = top.head(10)
    below40 = []
    # The watch list spans both boards. A woman is not "missing" from the
    # published board -- she is ranked on the other one, and reporting her as
    # absent would manufacture a defect out of the gender separation.
    rank_by_key = {
        _key(row.fighter): (int(row.model_rank), board)
        for board, frame in (("men", published), ("women", published_women))
        for row in frame.itertuples()
    }
    for fighter in WATCH_BELOW_40:
        found = rank_by_key.get(_key(fighter))
        rank, board = found if found else (None, None)
        if rank is None or rank > 40:
            below40.append(
                {
                    "fighter": fighter,
                    "model_rank": rank,
                    "board": board,
                    "reason": _anchor_reason(fighter, anchors),
                }
            )

    summary: dict[str, object] = {
        "snapshot": snapshot.name,
        "scope": scope,
        "published_score": rating_col,
        "diagnostic_score": (
            "symon_career_skill_mass"
            if "symon_career_skill_mass" in current.columns
            else None
        ),
        "board": "men (the published default)",
        "ranked_fighters": int(len(published)),
        "ranked_fighters_women_board": int(len(published_women)),
        "top100_birth_date_coverage": round(float(top["birth_date_known"].mean()), 4),
        "top100_active_2024_plus": int(top["active_2024_plus"].sum()),
        "top100_external_only": int(top["external_only"].sum()),
        "top100_connectivity_rankable": int(top["rankable"].fillna(False).sum()),
        "external_only_names": _names(top.loc[top["external_only"], "fighter"]),
        "top100_debut_before_2000": int(top["first_appearance"].dt.year.lt(2000).sum()),
        "top100_debut_2015_plus": int(top["first_appearance"].dt.year.ge(2015).sum()),
        "top25_unanchored_count": int((~top25["has_public_anchor"]).sum()),
        "top25_unanchored_names": _names(top25.loc[~top25["has_public_anchor"], "fighter"]),
        "top10_active_external_unanchored": _names(
            top10.loc[
                top10["external_only"]
                & top10["active_2024_plus"]
                & ~top10["has_public_anchor"],
                "fighter",
            ]
        ),
        "watch_names_below_40_or_missing": below40,
        "missing_public_anchor_names": missing.to_dict("records"),
        "top10": top10[["model_rank", "fighter", "score", "model_reason"]].to_dict("records"),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    comparison.to_parquet(out_dir / "top100_score_comparison.parquet", index=False)
    top.to_parquet(out_dir / "top100_audit.parquet", index=False)
    top.to_csv(out_dir / "top100_audit.csv", index=False)
    missing.to_csv(out_dir / "public_anchor_missing_from_model_top100.csv", index=False)
    (out_dir / "top100_audit.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--scope", default=DEFAULT_PUBLISHED_SCOPE)
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/top100-audit"))
    args = ap.parse_args()
    print(json.dumps(build(args.snapshot_dir, scope=args.scope, out_dir=args.out_dir), indent=2))


if __name__ == "__main__":
    main()
