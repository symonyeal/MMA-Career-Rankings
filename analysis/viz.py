"""Frames used to build the published site; build_site.py is the only caller."""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from project_helpers import map_distinct, normalize_name_key
from ratings.divisions import DIV_SHORT, display_division_label
from ratings.constants import JULIAN_YEAR_DAYS


def _name_key(name: str | None) -> str | None:
    key = normalize_name_key(name, compact=True)
    return key or None


def add_division_to_fights(fights: pd.DataFrame) -> pd.DataFrame:
    out = fights.copy()
    out["division"] = map_distinct(out["weight_class"], display_division_label).to_numpy(dtype=object, na_value=None)
    return out


def _division_appearances(fights: pd.DataFrame) -> pd.DataFrame:
    f = add_division_to_fights(fights)
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["year"] = f["event_date"].dt.year
    a = f[["year", "division", "fighter_a"]].rename(columns={"fighter_a": "fighter"})
    b = f[["year", "division", "fighter_b"]].rename(columns={"fighter_b": "fighter"})
    long = pd.concat([a, b], ignore_index=True).dropna(subset=["fighter", "division", "year"])
    return long


def _annual_ratings(long: pd.DataFrame, ratings_history: pd.DataFrame, rating_col: str) -> pd.DataFrame:
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
    return merged


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

    long = _division_appearances(fights)
    if divisions:
        long = long[long["division"].isin(divisions)]
    if year_min is not None:
        long = long[long["year"] >= year_min]
    if year_max is not None:
        long = long[long["year"] <= year_max]
    if long.empty:
        return pd.DataFrame(columns=["division", "year", "score", "fighters"])

    merged = _annual_ratings(long, ratings_history, rating_col)
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


def division_year_top_fighters_frame(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    rating_col: str,
    year: int,
    divisions: list[str] | None = None,
    top_n: int = 5,
) -> pd.DataFrame:
    """Rows for the top fighters in each division at the end of a year.

    The output preserves the former chart trace order. Columns are division code,
    unrounded end-of-year rating, and the visible rank/name label.
    """
    cols = ["division", "rating", "label"]
    if ratings_history is None or ratings_history.empty or fights is None or fights.empty:
        return pd.DataFrame(columns=cols)
    if rating_col not in ratings_history.columns:
        return pd.DataFrame(columns=cols)

    long = _division_appearances(fights)
    long = long[long["year"].eq(year)]
    if divisions:
        long = long[long["division"].isin(divisions)]
    if long.empty:
        return pd.DataFrame(columns=cols)

    merged = _annual_ratings(long, ratings_history, rating_col)
    if merged.empty:
        return pd.DataFrame(columns=cols)

    top = merged.sort_values(rating_col, ascending=False).groupby("division", as_index=False).head(top_n)
    div_order = top.groupby("division")[rating_col].max().sort_values(ascending=False).index.tolist()
    if divisions:
        div_order = [d for d in divisions if d in div_order] + [d for d in div_order if d not in divisions]

    rows = []
    for division in div_order:
        code = DIV_SHORT.get(division, division)
        block = top[top["division"].eq(division)].sort_values(rating_col, ascending=False)
        for rank, (fighter, rating) in enumerate(block[["fighter", rating_col]].itertuples(index=False, name=None), 1):
            rows.append({"division": code, "rating": float(rating),
                         "label": f"{rank}. {fighter}  ·  {code}"})
    return pd.DataFrame(rows, columns=cols)

def all_time_benchmark_table(
    ratings_current: pd.DataFrame,
    fightmatrix_all_time: pd.DataFrame,
    rating_col: str,
    *,
    min_fights: int = 3,
    limit: int = 30,
) -> pd.DataFrame:
    """Compare a men's model board with FightMatrix's all-time absolute list.

    The reference includes whole MMA careers while the canonical engine is UFC
    only, so this is a diagnostic rather than training data. A positive gap
    means the model ranks the fighter lower than FightMatrix does.
    """
    columns = ["fighter", "model_rank", "reference_rank", "rank_gap", "model_rating", "reference_points"]
    if (
        ratings_current is None or ratings_current.empty
        or fightmatrix_all_time is None or fightmatrix_all_time.empty
        or rating_col not in ratings_current.columns
    ):
        return pd.DataFrame(columns=columns)

    rc = ratings_current.copy()
    rc["rating_periods"] = pd.to_numeric(rc.get("rating_periods"), errors="coerce").fillna(0)
    rc = rc[rc["rating_periods"].ge(min_fights)]
    if "gender" in rc.columns:
        rc = rc[rc["gender"].eq("M")]
    rc["model_rating"] = pd.to_numeric(rc[rating_col], errors="coerce")
    rc = rc.dropna(subset=["fighter", "model_rating"]).sort_values("model_rating", ascending=False)
    rc["model_rank"] = np.arange(1, len(rc) + 1)
    rc["_name_key"] = rc["fighter"].apply(_name_key)

    fm = fightmatrix_all_time.copy()
    fm["_name_key"] = fm["fighter"].apply(_name_key)
    fm["reference_rank"] = pd.to_numeric(fm["rank"], errors="coerce")
    fm["reference_points"] = pd.to_numeric(fm["points"], errors="coerce")
    fm = fm.dropna(subset=["_name_key", "reference_rank"]).sort_values("reference_rank")
    fm = fm.drop_duplicates("_name_key")

    out = rc.merge(
        fm[["_name_key", "reference_rank", "reference_points"]],
        on="_name_key", how="left",
    ).head(limit)
    out["rank_gap"] = out["model_rank"] - out["reference_rank"]
    return out[columns].reset_index(drop=True)


def yearly_rating_delta_frame(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    rating_col: str,
    year: int,
    n: int = 12,
) -> pd.DataFrame:
    """Ordered biggest rating moves with the per-fight hover lines used by the site."""
    cols = ["fighter", "total_delta", "hover_lines", "n_fights"]
    if ratings_history is None or ratings_history.empty or rating_col not in ratings_history.columns:
        return pd.DataFrame(columns=cols)

    rh = ratings_history.copy()
    rh["event_date"] = pd.to_datetime(rh["event_date"], errors="coerce")
    rh["_year"] = rh["event_date"].dt.year
    rh[rating_col] = pd.to_numeric(rh[rating_col], errors="coerce")
    year_rows = rh[rh["_year"] == year].dropna(subset=[rating_col]).copy()
    year_rows = year_rows.sort_values(["fighter", "event_date"])
    if year_rows.empty:
        return pd.DataFrame(columns=cols)

    before = (
        rh[rh["_year"] < year]
        .dropna(subset=[rating_col])
        .sort_values("event_date")
        .groupby("fighter", as_index=False)
        .last()[["fighter", rating_col]]
        .rename(columns={rating_col: "_mu_start"})
    )
    year_rows = year_rows.merge(before, on="fighter", how="left")
    year_rows["_mu_prev"] = year_rows.groupby("fighter")[rating_col].shift(1)
    year_rows["_mu_prev"] = year_rows["_mu_prev"].fillna(year_rows["_mu_start"])
    year_rows = year_rows.dropna(subset=["_mu_prev"])
    year_rows["_fight_delta"] = year_rows[rating_col] - year_rows["_mu_prev"]

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
        joined = year_rows.merge(fl[["fighter", "event_date", "opponent", "_result"]],
                                 on=["fighter", "event_date"], how="left")
    else:
        joined = year_rows.copy()
        joined["opponent"] = pd.NA
        joined["_result"] = pd.NA

    by_fighter = joined.groupby("fighter")
    # Series.sum preserves the figure builder's floating-point summation order.
    frame = pd.DataFrame([{"fighter": fighter, "total_delta": float(values.sum()), "n_fights": len(values)}
                          for fighter, values in by_fighter["_fight_delta"]])
    if frame.empty:
        return pd.DataFrame(columns=cols)
    frame = frame[frame["total_delta"].abs() > 0.05]
    if frame.empty:
        return pd.DataFrame(columns=cols)

    risers = frame.sort_values("total_delta", ascending=False).head(n)
    fallers = frame.sort_values("total_delta", ascending=True).head(n)
    keep = pd.concat([risers, fallers]).drop_duplicates("fighter").sort_values("total_delta").reset_index(drop=True)
    hover = []
    for fighter in keep["fighter"]:
        lines = []
        for _, row in by_fighter.get_group(fighter).sort_values("event_date").iterrows():
            opponent = str(row.get("opponent") or "?")
            result = str(row.get("_result") or "?")
            delta = float(row["_fight_delta"])
            lines.append(f"vs {opponent}  {result}  Δ{delta:+.1f}")
        hover.append("<br>".join(lines))
    keep["hover_lines"] = hover
    return keep[cols].reset_index(drop=True)

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
        modal_div = None
        if divisions:  # Series.mode() order: most frequent, ties to the smallest label
            tally = Counter(divisions)
            top = max(tally.values())
            modal_div = min(d for d, c in tally.items() if c == top)
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


def _integrity_long(integrity_appearances: pd.DataFrame) -> pd.DataFrame:
    """Rows where the integrity sleeve fired, tagged with a human reason."""
    cols = ["fight_url", "fighter", "reason", "integrity_factor", "integrity_weight"]
    if integrity_appearances is None or integrity_appearances.empty:
        return pd.DataFrame(columns=cols)
    df = integrity_appearances.copy()
    factor_map = {
        "integrity_factor_ped": "PED",
        "integrity_factor_dq": "DQ",
        "integrity_factor_missed_weight": "Missed weight",
    }
    rows = []
    for col, reason in factor_map.items():
        if col not in df.columns:
            continue
        fired = df[pd.to_numeric(df[col], errors="coerce").fillna(1.0) < 1.0]
        for _, r in fired.iterrows():
            rows.append({
                "fight_url": r.get("fight_url"), "fighter": r.get("fighter"),
                "reason": reason, "integrity_factor": float(r[col]),
                "integrity_weight": float(pd.to_numeric(r.get("integrity_weight"), errors="coerce")),
            })
    return pd.DataFrame(rows, columns=cols)


def integrity_ledger_table(
    integrity_appearances: pd.DataFrame | None = None,
    *,
    integrity_ledger: pd.DataFrame | None = None,
    n: int | None = 25,
) -> pd.DataFrame:
    """Return the auditable per-result policy ledger.

    New snapshots provide ``integrity_ledger`` as a finished artifact. For an
    older snapshot, the same view is reconstructed from ``integrity_appearances``
    and is limited to the result-weight discount that artifact actually records.
    A per-fight rating-point debit is deliberately never manufactured here.
    """
    cols = [
        "event_date", "fighter", "opponent", "reason", "detail",
        "integrity_weight", "discount_pct",
    ]
    reason_labels = {
        "ped": "PED-confirmed win",
        "ped-confirmed_win": "PED-confirmed win",
        "ped-confirmed win": "PED-confirmed win",
        "dq": "Disqualification win",
        "win_by_disqualification": "Disqualification win",
        "win by disqualification": "Disqualification win",
        "missed_weight": "Missed-weight win",
        "missed weight": "Missed-weight win",
        "won_after_missing_weight": "Missed-weight win",
        "won after missing weight": "Missed-weight win",
    }

    # Column presence distinguishes a real-but-empty ledger artifact from a
    # missing artifact, so a clean modern snapshot never falls back to stale
    # appearance rows.
    has_ledger_artifact = (
        integrity_ledger is not None
        and {"fighter", "reason"}.issubset(integrity_ledger.columns)
    )
    if has_ledger_artifact:
        out = integrity_ledger.copy()
    else:
        fired = _integrity_long(integrity_appearances)
        if fired.empty:
            return pd.DataFrame(columns=cols)
        out = fired.copy()
        out["event_date"] = pd.NaT
        out["opponent"] = pd.NA
        out["detail"] = pd.NA
        out["discount_pct"] = 100.0 * (
            1.0 - pd.to_numeric(out["integrity_factor"], errors="coerce")
        )

    for col in cols:
        if col not in out.columns:
            out[col] = pd.NA
    raw_reason = out["reason"].astype("string").str.strip()
    reason_key = raw_reason.str.lower().str.replace(" ", "_", regex=False)
    out["reason"] = reason_key.map(reason_labels).fillna(raw_reason)
    out["integrity_weight"] = pd.to_numeric(out["integrity_weight"], errors="coerce")
    out["discount_pct"] = pd.to_numeric(out["discount_pct"], errors="coerce")
    missing_discount = out["discount_pct"].isna() & out["integrity_weight"].notna()
    out.loc[missing_discount, "discount_pct"] = (
        100.0 * (1.0 - out.loc[missing_discount, "integrity_weight"])
    )
    out["_event_sort"] = pd.to_datetime(out["event_date"], errors="coerce")
    out = out.sort_values(
        ["discount_pct", "_event_sort", "fighter"],
        ascending=[False, False, True],
        na_position="last",
        kind="stable",
    )
    if n is not None:
        out = out.head(max(0, int(n)))
    out = out[cols].copy()
    out["event_date"] = pd.to_datetime(out["event_date"], errors="coerce").dt.date
    out["integrity_weight"] = out["integrity_weight"].round(3)
    out["discount_pct"] = out["discount_pct"].round(1)
    return out.reset_index(drop=True)


def title_lineage_frame(
    performance_appearances: pd.DataFrame,
    *,
    division: str,
    include_interim: bool = False,
) -> pd.DataFrame:
    """One row per title reign for a division, in chart order."""
    cols = ["fighter", "opponent", "start", "defences", "years", "bar_length", "label"]
    if performance_appearances is None or performance_appearances.empty or not division:
        return pd.DataFrame(columns=cols)
    df = performance_appearances
    if "is_championship_bout" not in df.columns:
        return pd.DataFrame(columns=cols)
    df = df[df["is_championship_bout"].fillna(False).astype(bool)]
    if not include_interim and "is_interim_title_bout" in df.columns:
        df = df[~df["is_interim_title_bout"].fillna(False).astype(bool)]
    if "division" in df.columns:
        in_division = map_distinct(
            df["division"], lambda value: isinstance(value, str) and display_division_label(value) == division
        )
        df = df[in_division.astype(bool)]
    df = df[df["is_winner"].fillna(False).astype(bool)].copy()
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df = df.dropna(subset=["event_date"]).sort_values("event_date").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=cols)

    reigns = []
    for _, row in df.iterrows():
        if reigns and reigns[-1]["fighter"] == row["fighter"]:
            reigns[-1]["defences"] += 1
            reigns[-1]["last_win"] = row["event_date"]
        else:
            reigns.append({"fighter": row["fighter"], "start": row["event_date"], "defences": 0,
                           "opponent": row.get("opponent")})
    frame = pd.DataFrame(reigns)
    frame["reign_end"] = frame["start"].shift(-1)
    frame["reign_end"] = frame["reign_end"].fillna(df["event_date"].max() + pd.Timedelta(days=150))
    days = (frame["reign_end"] - frame["start"]).dt.days.clip(lower=30)
    frame["years"] = (days / JULIAN_YEAR_DAYS).round(1)
    frame["bar_length"] = days * 86_400_000
    frame["start"] = frame["start"].dt.date
    frame["label"] = frame.apply(
        lambda row: f"{str(row['fighter']).split()[-1]} ({row['defences']}D)" if row["defences"]
        else str(row["fighter"]).split()[-1], axis=1)
    return frame[cols].reset_index(drop=True)
