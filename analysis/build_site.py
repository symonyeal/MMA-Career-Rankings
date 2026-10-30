"""Build the static analysis site: ``site/data.js`` from one snapshot.

The site is the project's one presentation. Every frame below comes from ``viz.py`` or from the
rating code the published boards use; the page only filters, sorts and draws. Boards are the published ones
(``build_boards.py``), so the site and README cannot disagree.

Five certificates are checked before anything is written:
  1. the All-time score is reconstructed from its three normalised terms;
  2. the per-year career receipt sums to the published career skill mass;
  3. each integrity-policy rating is the base rating less its debit;
  4. the calibration table is symmetric: bin b and bin 9 − b are one bout seen from both corners;
  5. the forecast model and the betting market are scored on the same bouts.

Usage: python analysis/build_site.py [data/snapshots/<date>]
       python analysis/build_site.py [data/snapshots/<date>] --output <site-copy>
       python analysis/build_site.py --stamp     (re-stamp index.html after editing app.js or style.css)
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.viz import (
    DIV_SHORT, DIVISIONS, _division_strength_frame, add_division_to_fights, all_time_benchmark_table,
    division_year_top_fighters_frame, integrity_ledger_table, title_lineage_frame, win_streaks,
    yearly_rating_delta_frame,
)
from build_boards import _division_column
from ratings.age import load_birth_dates
from ratings.current_score import is_ufc_bout
from ratings.forecast import Y0 as FORECAST_Y0
from ratings.forecast import benchmark as forecast_benchmark
from ratings.constants import (
    FIVE_YEAR_PEAK_MIN_FIGHTS, FIVE_YEAR_PEAK_WINDOW_DAYS, FIVE_YEAR_PEAK_WINDOW_LABEL, SUSTAINED_PEAK_MIN_FIGHTS,
)
from ratings.era import ERA_COL, era_rated
from ratings.legacy_resume import (
    LEGACY_ACHIEVEMENT_WEIGHT, LEGACY_PART_POWER, LEGACY_QUALITY_SKILL_SHARE,
    PUBLIC_LEGACY_DISPLAY_SCALE, _scale, legacy_points,
)
from ratings.divisions import division_labels
from ratings.opponent_quality import CONTENDER_LINE_MU
from ratings.symon_score import (
    DEFAULT_CAREER_REFERENCE, DEFAULT_DIVISION_MIN_POPULATION, DEFAULT_DIVISION_REFERENCE,
    DEFAULT_HINGE_SPREAD_FRACTION, division_year_reference, positive_part,
    year_rating_spread, year_reference,
)

METHODS = ["KO/TKO", "Submission", "Decision - Unanimous", "Decision - Split", "Decision - Majority", "DQ", "Other"]
TOP_NS = (5, 10, 15, 25)
AGE_BANDS = ((0, 25, "under 25"), (25, 28, "25–27"), (28, 31, "28–30"), (31, 34, "31–33"), (34, 37, "34–36"),
             (37, 40, "37–39"), (40, 99, "40+"))  # whole years at the bout
LAYOFF_BANDS = ((0, 4, "under 4"), (4, 8, "4–8"), (8, 12, "8–12"), (12, 18, "12–18"), (18, 24, "18–24"),
                (24, 999, "24+"))  # months since the fighter's previous bout, any promotion
EPOCH = pd.Timestamp("1970-01-01")


def plain(o, nd=2):
    """JSON-native copy of o: arrays to lists, timestamps to ISO dates, NaN to null, floats to nd places."""
    if o is pd.NA or o is pd.NaT:
        return None
    if isinstance(o, dict):
        return {k: plain(v, nd) for k, v in o.items()}
    if isinstance(o, (list, tuple, np.ndarray, pd.Series, pd.Index)):
        return [plain(v, nd) for v in list(o)]
    if isinstance(o, (pd.Timestamp, np.datetime64)):
        return None if pd.isna(o) else pd.Timestamp(o).strftime("%Y-%m-%d")
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(o) else round(o) if nd == 0 else round(float(o), nd)
    return o


def year_top_rows(frame):
    """Browser rows grouped by division, preserving the former figure trace order."""
    return [[division, plain(g["rating"]), plain(g["label"])]
            for division, g in frame.groupby("division", sort=False)]


def mover_rows(frame):
    """Ordered rating changes and hover details used by the movers panel."""
    if frame.empty:
        return []
    return [plain(frame["total_delta"]), plain(frame["fighter"]),
            plain(frame[["hover_lines", "n_fights"]].astype(str).to_numpy().tolist())]


def lineage_rows(frame):
    """One row per reign: champion, challenger, dates, defences, duration and bar labels."""
    return plain(frame.to_numpy().tolist())


def days(s):
    return ((pd.to_datetime(s, errors="coerce") - EPOCH).dt.days).astype("Int64")


def board(snap, stem, cols):
    """Published men's and women's board rows concatenated; rank is null where the board withholds."""
    b = pd.concat([pd.read_parquet(snap / f"{stem}{s}.parquet") for s in ("", "_women")], ignore_index=True)
    b.loc[b["status"].ne("ranked"), "rank"] = np.nan
    return b.set_index("fighter")[cols]


def receipt(whr, rc):
    """Per-year career receipt: the annual frame of ratings.symon_score.career_skill_mass, kept.

    Same steps as the production call in rate_snapshot (division bar at contender:5, sport-wide
    contender:60 fallback, soft hinge at 0.175 of the year's spread); returns
    (fighter, year, annual_mean, field_mean, hinge, excess).
    """
    h = whr[["fighter", "event_date", "mu_whr"]].dropna().rename(columns={"mu_whr": "mu"})
    h["year"] = pd.to_datetime(h["event_date"]).dt.year
    a = h.groupby(["fighter", "year"], sort=False)["mu"].agg(annual_mean="mean").reset_index()
    a["division"] = a["fighter"].map(division_labels(rc))
    bar = year_reference(a, DEFAULT_CAREER_REFERENCE)
    g = float(year_reference(a.assign(year=0), DEFAULT_CAREER_REFERENCE).iloc[0])
    n = a.groupby("year", sort=False)["annual_mean"].transform("size")
    a["field_mean"] = a["year"].map(bar)
    a.loc[(n < 5) | a["field_mean"].isna(), "field_mean"] = g
    local = division_year_reference(a, DEFAULT_DIVISION_REFERENCE, min_population=DEFAULT_DIVISION_MIN_POPULATION)
    keys = pd.MultiIndex.from_arrays([a["division"], a["year"]])
    a["field_mean"] = pd.Series(local.reindex(keys).to_numpy(), index=a.index).fillna(a["field_mean"])
    a["hinge"] = a["year"].map(year_rating_spread(a)).fillna(0.0) * DEFAULT_HINGE_SPREAD_FRACTION
    a["excess"] = positive_part(a["annual_mean"] - a["field_mean"], a["hinge"])
    return a


def market(snap, bouts):
    """UFC bouts with betting odds, read against the result: the leak-free forecast benchmark
    (ratings.forecast), the biggest upsets, and win rate against price by age and by layoff.

    p_m: no-vig market P(a wins); y: 1 if a won. Benchmark rows are [label, ll, br, acc, ll gap to the
    market, 95% interval low, high]. Draws and no contests are dropped. Age and layoff rows are per
    fighter (both corners), with priced = mean market probability and se = standard error of
    mean(won − priced).
    """
    od = pd.read_parquet(snap / "odds_lines.parquet")
    od = od[od["odds_data_quality"].eq("ok")]
    b = bouts[~bouts["is_excluded"].fillna(False).astype(bool) & ~bouts["is_draw"].fillna(False).astype(bool)
              & ~bouts["is_nc"].fillna(False).astype(bool) & bouts["winner"].notna()]
    m = od.merge(b[["fight_url", "winner", "method_class", "is_title_fight", "weight_class"]], on="fight_url")
    m["y"], m["p_m"] = m["winner"].eq(m["fighter_a"]).astype(float), m["implied_prob_a_no_vig"]
    m = m[m["p_m"].between(0.001, 0.999)].reset_index(drop=True)

    E, bm = forecast_benchmark(snap)

    def cal(p, y):  # both corners, ten bins: [bin, mean forecast, win rate, n]
        P, Y = np.r_[p, 1 - p], np.r_[y, 1 - y]
        c = pd.DataFrame({"b": np.minimum((P * 10).astype(int), 9), "p": P, "y": Y}).groupby("b")
        c = c.agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
        return [[int(i), r.p, r.y, int(r.n)] for i, r in c.iterrows()]

    fav = np.where(m["p_m"] >= 0.5, m["y"], 1 - m["y"])
    lab = {"p_0": "Coin flip", "p_g": "Rating alone", "p_1": "Stats model", "p_m": "Betting market",
           "p_3": "Market + stats model"}
    vs = {"n": bm["n"], "events": bm["events"], "span": [bm["from"], bm["to"]], "first_test_year": FORECAST_Y0,
          "odds_bouts": len(m), "fav": float(fav.mean()),
          "years": [int(m["event_date"].dt.year.min()), int(m["event_date"].dt.year.max())],
          "rows": plain([[lab[c], *bm[c]] for c in lab], 4),
          "cal_market": plain(cal(E["p_m"].to_numpy(), E["y"].to_numpy()), 4),
          "cal_model": plain(cal(E["p_1"].to_numpy(), E["y"].to_numpy()), 4)}

    m["pw"] = np.where(m["y"].eq(1), m["p_m"], 1 - m["p_m"])
    m["loser"] = np.where(m["y"].eq(1), m["fighter_b"], m["fighter_a"])
    up = m.nsmallest(15, "pw").assign(event_date=lambda d: d["event_date"].dt.strftime("%Y-%m-%d"),
                                      is_title_fight=lambda d: d["is_title_fight"].fillna(False).astype(bool),
                                      weight_class=lambda d: d["weight_class"].str.replace(
                                          r"\b(UFC|Interim|Title|Bout)\b", "", regex=True).str.split().str.join(" "))
    upsets = plain(up[["event_date", "winner", "loser", "pw", "method_class", "is_title_fight", "weight_class"]]
                   .to_numpy().tolist(), 3)

    # one row per fighter per bout: their age, layoff, result and price
    dob = load_birth_dates(snap)
    seen = pd.concat([bouts[["fighter_a", "event_date"]].rename(columns={"fighter_a": "f"}),
                      bouts[["fighter_b", "event_date"]].rename(columns={"fighter_b": "f"})]).drop_duplicates()
    seen = seen.sort_values(["f", "event_date"])
    seen["lay"] = seen.groupby("f")["event_date"].diff().dt.days / (365.25 / 12)
    A = pd.concat([m.assign(f=m[f"fighter_{s}"], won=m["y"] if s == "a" else 1 - m["y"],
                            priced=m["p_m"] if s == "a" else 1 - m["p_m"]) for s in "ab"], ignore_index=True)
    A["age"] = (A["event_date"] - A["f"].map(dob)).dt.days / 365.25
    A = A.merge(seen.rename(columns={"event_date": "event_date"}), on=["f", "event_date"], how="left")

    def bands(col, B):
        out = []
        for lo, hi, lab in B:
            r = A[(A[col] >= lo) & (A[col] < hi)]
            e = r["won"] - r["priced"]
            out.append([lab, len(r), float(r["won"].mean()), float(r["priced"].mean()),
                        float(e.std() / math.sqrt(len(r)))])
        return plain(out, 4)

    return vs, upsets, bands("age", AGE_BANDS), bands("lay", LAYOFF_BANDS)


def build(snap):
    rd = lambda stem: pd.read_parquet(snap / f"{stem}.parquet")
    rc, whr, bouts, ufc, app = (rd(s) for s in (
        "ratings_current", "ratings_history_whr", "combined_fights", "canonical_fights", "performance_appearances"))
    run = json.loads((snap / "rating_run.json").read_text(encoding="utf-8"))

    # 1. All-time = 1000 (a T + (1-a)(s S + (1-s) R)), each term its part over the mean of its top 100,
    # raised to p (ratings.legacy_resume.legacy_points). The page re-weights T, S, R linearly.
    a, s = LEGACY_ACHIEVEMENT_WEIGHT, LEGACY_QUALITY_SKILL_SHARE
    parts = [rc[f"public_legacy_{c}_score"] for c in ("title", "skill", "resume")]
    T, S, R = (_scale(x) ** LEGACY_PART_POWER for x in parts)
    assert np.allclose(PUBLIC_LEGACY_DISPLAY_SCALE * (a * T + (1 - a) * (s * S + (1 - s) * R)),
                       rc["public_legacy_score"].fillna(0)), "All-time score does not reconstruct"
    assert np.allclose(sum(legacy_points(*parts)), rc["public_legacy_score"].fillna(0))

    E = rc[rc["rating_periods"] >= SUSTAINED_PEAK_MIN_FIGHTS].sort_values("public_legacy_score", ascending=False)
    names = E["fighter"].tolist()
    lookup = rc.set_index("fighter")
    at = board(snap, "completeness_gated_board", ["rank"])
    pr = board(snap, "prime_elite_board", ["rank", "elite_level", "tested_opponent_wins",
                                            "elite_window_start", "elite_window_end"])
    cu = board(snap, "current_board", ["rank", "current_board_score", "tested_opponent_wins"])
    dom = rd("fighter_dominance").set_index("fighter")
    peak = whr.groupby("fighter")[ERA_COL].max()
    x = E.set_index("fighter")
    yr = lambda c: pd.to_datetime(c, errors="coerce").dt.year
    F = {
        "name": names,
        "g": x["gender"],
        "div": _division_column(E["fighter"], lookup, "career_division"),
        "cdiv": _division_column(E["fighter"], lookup, "current_division"),
        "n": x["rating_periods"], "w": x["wins"], "l": x["losses"], "d": x["draws"],
        "last": x["whr_last_event_date"].map(lambda t: None if pd.isna(t) else pd.Timestamp(t).strftime("%Y-%m-%d")),
        "at": at["rank"].reindex(names), "score": x["public_legacy_score"],
        "T": T.set_axis(rc["fighter"]).reindex(names), "S": S.set_axis(rc["fighter"]).reindex(names),
        "R": R.set_axis(rc["fighter"]).reindex(names),
        "tw": x["public_legacy_qualifying_title_wins"], "cw": x["public_legacy_contender_wins"],
        "cy": x["symon_career_contributing_years"], "ay": x["symon_career_active_years"],
        "mass": x["symon_career_skill_mass"],
        "pr": pr["rank"].reindex(names), "plevel": pr["elite_level"].reindex(names),
        "pwins": pr["tested_opponent_wins"].reindex(names),
        "p0": yr(pr["elite_window_start"].reindex(names)), "p1": yr(pr["elite_window_end"].reindex(names)),
        "cr": cu["rank"].reindex(names), "cur": cu["current_board_score"].reindex(names),
        "ufc": cu["tested_opponent_wins"].reindex(names),
        "whr": x["mu_whr"], "peak": peak.reindex(names), "glicko": x["mu_canonical"],
        "dom": dom["mean_dominance"].reindex(names), "domw": dom["wins"].reindex(names),
    }
    F = {k: plain(pd.Series(list(v)) if not isinstance(v, list) else v, 3 if k in "TSR" else 1) for k, v in F.items()}

    # Class boards (ratings.division_legacy): components back on the scale of T, S, R above, so the page
    # re-weights a class exactly as it re-weights the All-time board; sum over classes = All-time.
    cb = rd("class_board")
    cb = cb[cb["fighter"].isin(set(names))]
    idx0 = {f: i for i, f in enumerate(names)}
    w = PUBLIC_LEGACY_DISPLAY_SCALE * np.array([a, (1 - a) * s, (1 - a) * (1 - s)])  # points per normalised unit
    cols = ["fighter", "division", "rank", "title", "skill", "resume"]
    classes = plain([[idx0[f], d, r, t / w[0], k / w[1], q / w[2]]
                     for f, d, r, t, k, q in cb[cols].itertuples(index=False)], 4)

    # 2. Trajectories: one point per WHR appearance, era-adjusted (ratings.era), joined to its bout by
    # (fighter, date, event, k).
    key = ["fighter", "event_date", "event_name"]
    h = whr[whr["fighter"].isin(set(names))].sort_values(key, kind="stable")
    p = app[app["fighter"].isin(set(names))].sort_values(key, kind="stable")
    h["k"], p["k"] = h.groupby(key).cumcount(), p.groupby(key).cumcount()
    t = h.merge(p[key + ["k", "opponent", "method_class", "is_winner", "is_draw"]], on=key + ["k"], how="left")
    N = names + sorted(set(t["opponent"].dropna()) - set(names))
    idx = {f: i for i, f in enumerate(N)}
    t["r"] = np.select([t["opponent"].isna(), t["is_draw"].fillna(False), t["is_winner"].fillna(False)],
                       ["N", "D", "W"], "L")
    t["m"] = t["method_class"].map({m: str(i) for i, m in enumerate(METHODS)}).fillna("-")
    t["day"], t["o"] = days(t["event_date"]), t["opponent"].map(idx).fillna(-1).astype(int)
    # Per fighter: [first day, day increments, rating, method codes, results W/L/D/N, opponent index].
    traj = {f: [int(g["day"].iloc[0]), plain(g["day"].diff().fillna(0).astype(int)), plain(g[ERA_COL].round()),
                "".join(g["m"]), "".join(g["r"]), plain(g["o"])]
            for f, g in t.groupby("fighter", sort=False)}

    # 3. Career receipt; certificate: per-fighter sum equals the published career skill mass.
    A = receipt(era_rated(whr), rc)
    mass = A.groupby("fighter")["excess"].sum()
    assert np.allclose(mass.reindex(names).fillna(0), x["symon_career_skill_mass"].reindex(names).fillna(0),
                       atol=1e-6), "career receipt does not sum to the published career skill mass"
    rec = {f: plain(g[["year", "annual_mean", "field_mean", "excess"]].round().to_numpy().tolist(), 0)
           for f, g in A[A["fighter"].isin(set(names))].groupby("fighter", sort=False)}

    # 4. Division frames, UFC bouts only: divisional views count the UFC, as the
    # class boards and Current do. Base WHR, end-of-year rating, top-N per class.
    U = bouts[is_ufc_bout(bouts)]
    years = sorted(y for y, c in pd.to_datetime(bouts["event_date"]).dt.year.value_counts().items() if c >= 100)
    uyears = sorted(y for y, c in pd.to_datetime(U["event_date"]).dt.year.value_counts().items() if c >= 30)
    strength = {k: plain(_division_strength_frame(whr, U, rating_col="mu_whr", top_n_per_division=k)
                         .to_numpy().tolist()) for k in TOP_NS}
    year_top = {y: year_top_rows(division_year_top_fighters_frame(whr, U, rating_col="mu_whr", year=y, top_n=5))
                for y in uyears}
    # Movers among the board population only; over all 34k fighters the list is regional debutants.
    whrE = whr[whr["fighter"].isin(set(names))]
    movers = {y: mover_rows(yearly_rating_delta_frame(whrE, bouts, rating_col="mu_whr", year=y, n=12))
              for y in years}
    f = add_division_to_fights(U[~U["is_excluded"].fillna(False).astype(bool)])
    f["year"] = pd.to_datetime(f["event_date"]).dt.year
    f["bucket"] = f["method_class"].map(
        lambda m: m if m in ("KO/TKO", "Submission") else "Decision" if str(m).startswith("Decision") else None)
    mix = f.dropna(subset=["bucket"]).groupby(["year", f["division"].fillna(""), "bucket"]).size()

    # 5. Title lineage per class, with and without interim belts.
    lineage = {d: [lineage_rows(title_lineage_frame(app, division=d, include_interim=i)) for i in (False, True)]
               for d in DIVISIONS[:13]}

    # 6. Streaks over UFC bouts, the external benchmark, integrity policy.
    st = win_streaks(ufc, rc, min_len=3)
    st = st.assign(start_date=days(st["start_date"]), end_date=days(st["end_date"]))[
        ["fighter", "length", "start_date", "end_date", "division", "divisions", "title_wins", "finishes",
         "avg_opp_rating", "ongoing", "ended_by", "gender"]]
    bench = all_time_benchmark_table(rc, rd("fightmatrix_all_time"), "public_legacy_score",
                                     min_fights=SUSTAINED_PEAK_MIN_FIGHTS, limit=100)
    # Integrity policy: rank on the base WHR list before and after the debits, highest-rated debited first.
    ib = rd("integrity_discounted_board")
    assert np.allclose(ib["mu_whr"] - ib["integrity_cost"], ib["integrity_discounted_rating"]), \
        "integrity rating is not base rating less debit"
    db = ib[ib["integrity_cost"] > 0].sort_values("mu_whr", ascending=False)
    ia, il = rd("integrity_appearances"), rd("integrity_ledger")
    integrity = {
        "n": len(db), "rated": len(ib), "cost": plain([db["integrity_cost"].min(), db["integrity_cost"].max()], 1),
        "debits": plain(db.head(25)[["fighter", "mu_whr", "undiscounted_rank", "rank", "integrity_cost",
                                     "ped_discounted_fights", "dq_discounted_fights",
                                     "missed_weight_discounted_fights"]].to_numpy().tolist(), 1),
        "ledger": plain(integrity_ledger_table(ia, integrity_ledger=il, n=None)
                        .replace("�", "—", regex=True).to_numpy().tolist()),  # source mis-decoded dash
    }

    # 7. Calibration of the pre-fight Glicko-2 forecast (ratings.diagnostics.calibration_residual_rows).
    cr = rd("calibration_residuals")
    o = cr[cr["segment_type"].eq("overall")].sort_values("prob_bin")
    assert np.allclose(o["predicted_mean"].to_numpy() + o["predicted_mean"].to_numpy()[::-1], 1), \
        "calibration table is not symmetric"
    big = cr[cr["segment_type"].eq("division") & cr["segment_value"].isin(DIVISIONS)]
    big = big[big.groupby("segment_value")["n"].transform("sum") >= 1000]
    calib = plain(pd.concat([o.assign(segment_value="All bouts"), big])[
        ["segment_value", "prob_bin", "predicted_mean", "empirical_win_rate", "n"]].to_numpy().tolist(), 4)

    # 8. Betting odds: the rating against the market on the same bouts, upsets, age and layoff against price.
    vs, upsets, age, layoff = market(snap, bouts)
    assert sum(r[3] for r in vs["cal_market"]) == sum(r[3] for r in vs["cal_model"]) == 2 * vs["n"], \
        "market and model forecasts are not scored on the same bouts"

    return {
        "meta": {
            "snapshot": snap.name, "through": pd.to_datetime(bouts["event_date"]).max().strftime("%Y-%m-%d"),
            "rated_bouts": run["rated_bouts"], "fighters": run["current_fighters"], "established": len(names),
            "min_periods": SUSTAINED_PEAK_MIN_FIGHTS, "contender": CONTENDER_LINE_MU,
            "a": a, "s": s, "scale": PUBLIC_LEGACY_DISPLAY_SCALE, "methods": METHODS,
            "peak": [FIVE_YEAR_PEAK_WINDOW_DAYS, FIVE_YEAR_PEAK_MIN_FIGHTS, FIVE_YEAR_PEAK_WINDOW_LABEL],
        },
        "divisions": DIVISIONS, "short": DIV_SHORT, "F": F, "classes": classes, "N": N, "traj": traj, "receipt": rec,
        "strength": strength, "year_top": year_top, "movers": movers, "mix": plain([[*k, v] for k, v in mix.items()]),
        "lineage": lineage, "streaks": plain(st.to_numpy().tolist(), 0),
        "bench": plain(bench.to_numpy().tolist(), 1), "integrity": integrity, "calib": calib,
        "market": vs, "upsets": upsets, "age": age, "layoff": layoff,
    }


ASSETS = ("style.css", "data.js", "app.js")


def version(path):
    """Content hash of an asset, line endings normalised so a Windows checkout and the deployed file agree."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:10]


def stamp(site=ROOT / "site"):
    """Point index.html at each asset by its content hash: a browser never pairs a new page with a cached old asset."""
    p = site / "index.html"
    h = p.read_text(encoding="utf-8")
    for a in ASSETS:
        h = re.sub(rf'"{re.escape(a)}(\?v=\w+)?"', f'"{a}?v={version(site / a)}"', h)
    p.write_text(h, encoding="utf-8", newline="\n")


def main(snap, site=ROOT / "site"):
    data = build(Path(snap))
    site = Path(site)
    site.mkdir(parents=True, exist_ok=True)
    if site.resolve() != (ROOT / "site").resolve():
        for asset in ("index.html", "style.css", "app.js"):
            shutil.copyfile(ROOT / "site" / asset, site / asset)
    out = site / "data.js"
    out.write_text("window.DATA = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n",
                   encoding="utf-8")
    stamp(site)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--stamp"]:
        stamp()
    elif "--output" in sys.argv:
        args = sys.argv[1:]
        i = args.index("--output")
        site = Path(args[i + 1])
        del args[i:i + 2]
        main(args[0] if args else max((ROOT / "data" / "snapshots").glob("20*")), site=site)
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else max((ROOT / "data" / "snapshots").glob("20*")))
