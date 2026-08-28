"""Computations behind ``analysis/investigations/top100_era_skew.ipynb``.

Why a module and not cells
--------------------------
Six hypotheses each need a WHR refit or a board rebuild, several need dozens,
and every one of them has to be re-runnable from a clean kernel. Putting the
work here keeps the notebook to "call, show, judge", makes the refits testable
outside Jupyter, and gives every expensive result one cache path under
``data/model_tuning/top100-era-skew/`` so the second run is instant.

Nothing here scores anything a second time. Every board is
``ratings.symon_score.career_skill_mass`` over a WHR history; the variants
change the *input* (which bouts, which drift rate) or the *bar*, never the
functional. Single-Entry is a property of the thing being investigated and the
investigation must not break it to look at it.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ratings.constants import WHR_W2_PER_DAY
from ratings import prequential as PQ
from ratings.symon_score import career_skill_mass
from ratings.whr import run_whr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT = PROJECT_ROOT / "data" / "snapshots" / "2026-08-13"
CACHE_DIR = PROJECT_ROOT / "data" / "model_tuning" / "top100-era-skew"

# The seven careers section 4 of the brief demands be carried through every
# hypothesis, plus the three controls the plan's own truncation test used.
CASES = [
    "Merab Dvalishvili",
    "Jon Jones",
    "Natalia Silva",
    "Randy Couture",
    "Robbie Lawler",
    "Jose Aldo",
    "Wanderlei Silva",
]
ZERO_MASS = [
    "Forrest Griffin",
    "Mauricio Rua",
    "Randy Couture",
    "Robbie Lawler",
    "Urijah Faber",
    "Vitor Belfort",
    "Wanderlei Silva",
]
TRUNCATION_CONTROLS = ["Tony Ferguson", "Anderson Silva", "BJ Penn"]


# ---------------------------------------------------------------------------
# Loading and caching


def load_fights(
    snapshot_dir: Path = DEFAULT_SNAPSHOT,
    *,
    scope: str = "ufc",
) -> pd.DataFrame:
    """Rated bouts through the production scope loader and dedupe guard."""
    return PQ.load_fight_table(Path(snapshot_dir), scope=scope)


def load_history(snapshot_dir: Path = DEFAULT_SNAPSHOT) -> pd.DataFrame:
    h = pd.read_parquet(Path(snapshot_dir) / "ratings_history_whr.parquet")
    h["event_date"] = pd.to_datetime(h["event_date"])
    return h


def load_current(snapshot_dir: Path = DEFAULT_SNAPSHOT) -> pd.DataFrame:
    return pd.read_parquet(Path(snapshot_dir) / "ratings_current.parquet")


def load_uncertainty(snapshot_dir: Path = DEFAULT_SNAPSHOT) -> pd.DataFrame:
    return pd.read_parquet(Path(snapshot_dir) / "career_mass_uncertainty.parquet")


def cached(name: str, build, *, force: bool = False) -> pd.DataFrame:
    """Read ``<cache>/<name>.parquet`` if present, else build it and write it.

    The notebook must run top-to-bottom from a clean kernel, which means every
    refit here is on the critical path the first time and must not be on it
    twice. ``force=True`` is the escape hatch for a deliberate rebuild.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path)
    frame = build()
    frame.to_parquet(path, index=False)
    return frame


def fights_fingerprint(fights: pd.DataFrame) -> str:
    """Short hash of the bout table, so a cache cannot outlive its input."""
    key = pd.util.hash_pandas_object(
        fights[["fighter_a", "fighter_b", "winner", "event_date"]], index=False
    ).values.tobytes()
    return hashlib.sha1(key).hexdigest()[:12]


# ---------------------------------------------------------------------------
# The board, and what it is made of


def annual_means(history: pd.DataFrame, mu_col: str = "mu_whr") -> pd.DataFrame:
    """One rating per fighter-year — the unit career mass is summed over."""
    h = history.copy()
    h["year"] = pd.to_datetime(h["event_date"]).dt.year
    annual = (
        h.groupby(["fighter", "year"], sort=False)[mu_col]
        .agg(annual_mean="mean", appearances="size")
        .reset_index()
    )
    annual["n_year"] = annual.groupby("year")["annual_mean"].transform("size")
    annual["place_in_year"] = (
        annual.groupby("year")["annual_mean"].rank(ascending=False, method="min").astype(int)
    )
    annual["pct_in_year"] = 1.0 - (annual["place_in_year"] - 1) / annual["n_year"]
    return annual


def board(history: pd.DataFrame, *, reference: str | float = 0.9) -> pd.DataFrame:
    """Career skill mass with its rank attached, highest first."""
    b = career_skill_mass(history, reference=reference)
    b["rank"] = np.arange(1, len(b) + 1)
    return b


def board_from_bar(annual: pd.DataFrame, bar_by_year: pd.Series, label: str) -> pd.DataFrame:
    """The same functional against an arbitrary per-year bar.

    ``career_skill_mass`` takes a quantile or the mean; the bar-composition
    hypothesis needs bars that are neither (a fixed count, a fixed-composition
    quantile), so the clip-and-sum is repeated here over a supplied bar rather
    than reimplemented differently.

    The ordering deliberately matches ``career_skill_mass``'s — score, then peak
    year excess, then name. Two thirds of the board sits tied at a mass of zero,
    so a different tiebreak would give the same fighter a different rank under
    an identical bar and invite a reader to attribute the difference to the bar.
    """
    a = annual.copy()
    a["bar"] = a["year"].map(bar_by_year)
    a["excess"] = (a["annual_mean"] - a["bar"]).clip(lower=0.0)
    g = a.groupby("fighter", sort=False)["excess"]
    out = pd.DataFrame({
        "score": g.sum(),
        "active_years": g.size().astype(int),
        "contributing_years": g.apply(lambda s: int((s > 0.0).sum())),
        "peak_year_excess": g.max(),
    })
    years = a.groupby("fighter", sort=False)["year"]
    out["first_year"] = years.min().astype(int)
    out["last_year"] = years.max().astype(int)
    out = out.reset_index()
    out["_key"] = out["fighter"].map(lambda f: f"{type(f).__name__}:{f!r}")
    out = out.sort_values(
        ["score", "peak_year_excess", "_key"], ascending=[False, False, True],
        kind="mergesort",
    ).drop(columns="_key").reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    out["variant"] = label
    return out


def composition(board_frame: pd.DataFrame, *, top_n: int = 100) -> dict:
    """The three numbers the whole investigation is about."""
    top = board_frame.head(top_n)
    return {
        "top_n": int(top_n),
        "active_2024_plus": int((top["last_year"] >= 2024).sum()),
        "debut_2009_or_earlier": int((top["first_year"] <= 2009).sum()),
        "median_debut_year": int(top["first_year"].median()),
        "zero_mass_fighters": int((board_frame["score"] <= 0.0).sum()),
    }


def case_rows(board_frame: pd.DataFrame, names=CASES) -> pd.DataFrame:
    """One row per carried case, in the brief's order, with a rank and a mass."""
    idx = board_frame.set_index("fighter")
    rows = []
    for name in names:
        if name not in idx.index:
            rows.append({"fighter": name, "rank": pd.NA, "score": pd.NA})
            continue
        r = idx.loc[name]
        rows.append({
            "fighter": name,
            "rank": int(r["rank"]),
            "score": float(r["score"]),
            "active_years": int(r["active_years"]),
            "contributing_years": int(r["contributing_years"]),
            "first_year": int(r["first_year"]),
            "last_year": int(r["last_year"]),
        })
    return pd.DataFrame(rows)


def career_shape(history: pd.DataFrame, *, min_bouts: int = 10) -> pd.DataFrame:
    """Per fighter: how far the trajectory travelled and whether it is a ramp.

    A strictly monotone trajectory is the visible signature of a smoother that
    can only explain "high then low" by tilting the whole career, so it is
    counted rather than assumed away.
    """
    h = history.sort_values(["fighter", "event_date", "event_name"])
    rows = []
    for fighter, grp in h.groupby("fighter", sort=False):
        mu = grp["mu_whr"].to_numpy(dtype=float)
        if len(mu) < min_bouts:
            continue
        d = np.diff(mu)
        rows.append({
            "fighter": fighter,
            "bouts": len(mu),
            "first": mu[0],
            "last": mu[-1],
            "peak": mu.max(),
            "range": float(mu.max() - mu.min()),
            "monotone_up": bool((d > 0).all()),
            "monotone_down": bool((d < 0).all()),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# A small OLS, because the question is "does this term survive that one"


def ols(y: np.ndarray, X: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Least squares with classical standard errors. Returns (terms, R²)."""
    design = np.column_stack([np.ones(len(y)), X.to_numpy(dtype=float)])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ beta
    n, k = design.shape
    xtx_inv = np.linalg.inv(design.T @ design)
    se = np.sqrt(np.diag((resid @ resid / (n - k)) * xtx_inv))
    terms = pd.DataFrame({
        "term": ["const", *X.columns],
        "coef": beta,
        "se": se,
        "t": beta / se,
    })
    r2 = 1.0 - (resid @ resid) / float(((y - y.mean()) ** 2).sum())
    return terms, float(r2)


# ---------------------------------------------------------------------------
# H1 — opponent-graph density


def graph_features(fights: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Per fighter: record depth, distinct opponents, opponent depth, 2-hop size.

    ``opp_mean_bouts`` is the one that matters. A fighter whose opponents are
    themselves thinly recorded is anchored by nothing, whichever decade they
    fought in — and in a UFC-only scope an early fighter's opponents are thin
    by construction, which is why this hypothesis and the scope one are not
    independent.
    """
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in zip(fights["fighter_a"], fights["fighter_b"]):
        adj[a].add(b)
        adj[b].add(a)
    bout_count = history.groupby("fighter").size().to_dict()

    rows = []
    for fighter, nbrs in adj.items():
        two_hop: set[str] = set()
        for n in nbrs:
            two_hop |= adj[n]
        two_hop -= nbrs
        two_hop.discard(fighter)
        rows.append({
            "fighter": fighter,
            "opponents": len(nbrs),
            "opp_mean_bouts": float(np.mean([bout_count.get(n, 0) for n in nbrs])),
            "two_hop": len(two_hop),
        })
    graph = pd.DataFrame(rows)

    per = history.groupby("fighter")
    base = pd.DataFrame({
        "peak": per["mu_whr"].max(),
        "debut_year": per["event_date"].min().dt.year,
        "bouts": per.size(),
    }).reset_index()
    return base.merge(graph, on="fighter", how="inner")


# ---------------------------------------------------------------------------
# H2 — the drift prior


def w2_sweep(
    fights: pd.DataFrame,
    multipliers=(0.25, 1.0, 4.0, 16.0, 64.0),
    *,
    reference: str | float = 0.9,
    force: bool = False,
) -> pd.DataFrame:
    """Refit at each multiple of ``WHR_W2_PER_DAY`` and rebuild the board.

    One row per (multiplier, fighter): the whole board is kept, not a summary,
    so every downstream question — the seven cases, the top-100 composition,
    the count of zeros — is answered from the same cached refit.
    """
    tag = fights_fingerprint(fights)

    def build() -> pd.DataFrame:
        frames = []
        for mult in multipliers:
            history = run_whr(fights, w2_per_day=WHR_W2_PER_DAY * float(mult))
            b = board(history, reference=reference)
            shape = career_shape(history)
            b = b.merge(shape[["fighter", "range"]], on="fighter", how="left")
            b["w2_multiplier"] = float(mult)
            b["w2"] = WHR_W2_PER_DAY * float(mult)
            frames.append(b)
        return pd.concat(frames, ignore_index=True)

    return cached(f"w2_sweep_{tag}", build, force=force)


def _decided(fights: pd.DataFrame) -> pd.DataFrame:
    f = fights.copy()
    for flag in ("is_draw", "is_nc"):
        if flag in f.columns:
            f = f[~f[flag].fillna(False).astype(bool)]
    f = f.dropna(subset=["winner", "fighter_a", "fighter_b", "event_date"])
    f = f[f["winner"].eq(f["fighter_a"]) | f["winner"].eq(f["fighter_b"])]
    f["y_a"] = (f["winner"] == f["fighter_a"]).astype(int)
    return f


def prequential_w2(
    fights: pd.DataFrame,
    w2_multipliers=(0.25, 1.0, 4.0, 16.0, 64.0),
    *,
    start: str = "2008-01-01",
    window_days: int = 182,
    min_prior_fights: int = 3,
    force: bool = False,
) -> pd.DataFrame:
    """Rolling-origin one-step-ahead scoring, blocked by half-year.

    The repo's own ``ratings.whr_backtest`` scores only the most recent handful
    of events, which cannot say whether a drift rate that rescues a 2004 career
    also predicts 2004. Here the origin walks the whole record: fit on every
    bout strictly before the origin, predict every decided bout in the
    following ``window_days``, and keep one row per scored bout so the paired
    interval can cluster on the event afterwards.

    A larger ``w2`` is charged honestly for staleness: a fighter's last rating
    is the prediction, and a fast-drifting rating goes stale faster. That is a
    real cost of the parameter, not an artifact of the blocking.
    """
    from ratings.whr import _ELO_PER_NAT

    tag = fights_fingerprint(fights)

    def build() -> pd.DataFrame:
        bouts = _decided(fights)
        appearances = pd.concat([
            bouts[["event_date", "fighter_a"]].rename(columns={"fighter_a": "fighter"}),
            bouts[["event_date", "fighter_b"]].rename(columns={"fighter_b": "fighter"}),
        ], ignore_index=True)
        origins = pd.date_range(start, bouts["event_date"].max(), freq=f"{window_days}D")

        rows = []
        for mult in w2_multipliers:
            w2 = WHR_W2_PER_DAY * float(mult)
            for origin in origins:
                train = bouts[bouts["event_date"] < origin]
                test = bouts[(bouts["event_date"] >= origin)
                             & (bouts["event_date"] < origin + pd.Timedelta(days=window_days))]
                if train.empty or test.empty:
                    continue
                history = run_whr(train, w2_per_day=w2)
                last = (history.sort_values(["fighter", "event_date"])
                        .groupby("fighter")["mu_whr"].last())
                prior = appearances[appearances["event_date"] < origin].groupby("fighter").size()
                for b in test.itertuples(index=False):
                    a, c = b.fighter_a, b.fighter_b
                    if a not in last.index or c not in last.index:
                        continue
                    if prior.get(a, 0) < min_prior_fights or prior.get(c, 0) < min_prior_fights:
                        continue
                    gap = (last[a] - last[c]) / _ELO_PER_NAT
                    p = float(np.clip(1.0 / (1.0 + np.exp(-gap)), 1e-6, 1 - 1e-6))
                    y = int(b.y_a)
                    rows.append({
                        "w2_multiplier": float(mult),
                        "origin": origin,
                        "event_name": b.event_name,
                        "event_date": b.event_date,
                        "p": p,
                        "y": y,
                        "log_loss": -(y * np.log(p) + (1 - y) * np.log(1 - p)),
                        "brier": (p - y) ** 2,
                    })
        return pd.DataFrame(rows)

    return cached(f"prequential_w2_{tag}", build, force=force)


def paired_event_bootstrap(
    predictions: pd.DataFrame,
    *,
    baseline_multiplier: float = 1.0,
    metric: str = "log_loss",
    replicates: int = 2000,
    seed: int = 0,
    lo: float = 0.025,
    hi: float = 0.975,
) -> pd.DataFrame:
    """Per-multiplier mean metric and its paired delta against the baseline.

    Bouts on one card share matchmaking and judging, so the resample unit is
    the event, and the delta is paired bout-by-bout before it is aggregated —
    the same bout scored two ways is one observation, not two.
    """
    wide = predictions.pivot_table(
        index=["event_name", "event_date", "origin"],
        columns="w2_multiplier",
        values=metric,
        aggfunc="mean",
    )
    counts = predictions.pivot_table(
        index=["event_name", "event_date", "origin"],
        columns="w2_multiplier",
        values="y",
        aggfunc="size",
    )
    wide = wide.dropna()
    counts = counts.loc[wide.index]
    n = counts[baseline_multiplier].to_numpy(dtype=float)

    rng = np.random.default_rng(seed)
    n_events = len(wide)
    draws = rng.integers(0, n_events, size=(replicates, n_events))

    rows = []
    base = wide[baseline_multiplier].to_numpy(dtype=float)
    for mult in wide.columns:
        values = wide[mult].to_numpy(dtype=float)
        mean = float((values * n).sum() / n.sum())
        delta = values - base
        delta_mean = float((delta * n).sum() / n.sum())
        boot = np.array([
            float((delta[idx] * n[idx]).sum() / n[idx].sum()) for idx in draws
        ])
        rows.append({
            "w2_multiplier": float(mult),
            "w2": WHR_W2_PER_DAY * float(mult),
            f"mean_{metric}": mean,
            "delta_vs_baseline": delta_mean,
            "delta_lo": float(np.quantile(boot, lo)),
            "delta_hi": float(np.quantile(boot, hi)),
            "events": n_events,
            "bouts": int(n.sum()),
        })
    out = pd.DataFrame(rows)
    out["separated"] = ~((out["delta_lo"] <= 0.0) & (out["delta_hi"] >= 0.0))
    return out.sort_values("w2_multiplier").reset_index(drop=True)


# ---------------------------------------------------------------------------
# H3 — peak deletion under a driftless prior


def unbeaten_cut(fights: pd.DataFrame, name: str) -> dict:
    """The end of a fighter's longest unbeaten run, and what follows it.

    The plan's truncation test used hand-picked cut dates. A rule is needed
    instead so the test extends past four fighters, and this is the rule those
    four dates were expressing: cut where the fighter stopped winning.
    """
    own = fights[(fights["fighter_a"] == name) | (fights["fighter_b"] == name)]
    own = own.sort_values(["event_date", "event_name"])
    if own.empty:
        return {"fighter": name, "cut_date": None, "run": 0, "dropped": 0}
    kept = (own["winner"].eq(name) | own["is_draw"].fillna(False)).to_numpy()
    best_len = best_end = -1
    run = 0
    for i, ok in enumerate(kept):
        run = run + 1 if ok else 0
        if run > best_len:
            best_len, best_end = run, i
    after = own.iloc[best_end + 1:]
    post_wins = int(after["winner"].eq(name).sum()) if len(after) else 0
    return {
        "fighter": name,
        "cut_date": own["event_date"].iloc[best_end],
        "run": int(best_len),
        "dropped": int(len(after)),
        "post_cut_wins": post_wins,
        "post_cut_win_rate": float(post_wins / len(after)) if len(after) else np.nan,
        "bouts": int(len(own)),
    }


def truncation_revisions(
    fights: pd.DataFrame,
    full_history: pd.DataFrame,
    names: list[str],
    *,
    min_dropped: int = 1,
    force: bool = False,
    cache_name: str | None = None,
) -> pd.DataFrame:
    """Refit with one fighter's post-peak suffix removed; read the revision.

    Only that fighter's own bouts are dropped — the rest of the graph is
    untouched — so the difference is what *their* later results did to *their*
    earlier rating, not a change of scale.

    Note the direction of the null: a truncated fit gives the fighter less
    evidence, and less evidence pulls a high rating *down* toward the anchor.
    A truncated peak that comes out higher than the full fit is therefore
    against the null, not with it.
    """
    tag = cache_name or f"truncation_{fights_fingerprint(fights)}_{len(names)}"

    def build() -> pd.DataFrame:
        rows = []
        for name in names:
            cut = unbeaten_cut(fights, name)
            if cut["cut_date"] is None or cut["dropped"] < min_dropped:
                rows.append({**cut, "truncated_peak": np.nan, "full_at_same_date": np.nan,
                             "revision": np.nan})
                continue
            own = (fights["fighter_a"] == name) | (fights["fighter_b"] == name)
            keep = ~(own & (fights["event_date"] > cut["cut_date"]))
            history = run_whr(fights[keep])
            mine = history[history["fighter"] == name]
            peak_at = mine.loc[mine["mu_whr"].idxmax(), "event_date"]
            truncated_peak = float(mine["mu_whr"].max())
            full = full_history[(full_history["fighter"] == name)
                                & (full_history["event_date"] == peak_at)]
            if full.empty:
                continue
            full_value = float(full["mu_whr"].iloc[0])
            rows.append({
                **cut,
                "peak_date": peak_at,
                "truncated_peak": truncated_peak,
                "full_at_same_date": full_value,
                "revision": full_value - truncated_peak,
            })
        return pd.DataFrame(rows)

    return cached(tag, build, force=force)


# ---------------------------------------------------------------------------
# H4 — what the bar is a quantile of


def bar_table(annual: pd.DataFrame, *, fixed_counts=(30, 60), min_bouts: int = 8,
              career_bouts: pd.Series | None = None) -> pd.DataFrame:
    """Every candidate bar, per year, with the years a fixed count cannot cover.

    A fixed count is the obvious repair for a quantile whose population grew
    from 28 to 625 — and it is undefined in exactly the years the repair is
    for. That is reported as ``NaN``, never silently filled with the worst
    fighter in a thin year, which would hand the early era a free floor.
    """
    by_year = annual.groupby("year")["annual_mean"]
    out = pd.DataFrame({
        "rated_fighter_years": by_year.size(),
        "q0.90": by_year.quantile(0.9),
        "mean": by_year.mean(),
    })
    for k in fixed_counts:
        out[f"top-{k}"] = by_year.apply(
            lambda s, k=k: float(np.sort(s.to_numpy())[::-1][k - 1]) if len(s) >= k else np.nan
        )
    if career_bouts is not None:
        deep = annual[annual["fighter"].map(career_bouts).ge(min_bouts)]
        out[f"q0.90 | >={min_bouts} bouts"] = deep.groupby("year")["annual_mean"].quantile(0.9)
    out["q0.90 is place"] = np.ceil(0.10 * out["rated_fighter_years"]).astype(int)
    return out.reset_index()


def case_year_placings(annual: pd.DataFrame, names=CASES) -> pd.DataFrame:
    """Where each carried case sat inside their own year's field.

    This is the measurement that decides H4: a fighter who never reached the
    top decile of any year is not being kept off the board by *which* decile
    the bar is, and no rank-consistent redefinition of the bar reaches them.
    """
    sub = annual[annual["fighter"].isin(names)]
    rows = []
    for name, grp in sub.groupby("fighter", sort=False):
        best = grp.loc[grp["pct_in_year"].idxmax()]
        rows.append({
            "fighter": name,
            "active_years": int(len(grp)),
            "best_year": int(best["year"]),
            "best_place": f"{int(best['place_in_year'])} of {int(best['n_year'])}",
            "best_percentile": round(100 * float(best["pct_in_year"]), 1),
            "years_in_top_decile": int((grp["pct_in_year"] >= 0.90).sum()),
            "median_percentile": round(100 * float(grp["pct_in_year"].median()), 1),
        })
    order = {n: i for i, n in enumerate(names)}
    return pd.DataFrame(rows).sort_values("fighter", key=lambda s: s.map(order)).reset_index(drop=True)


# ---------------------------------------------------------------------------
# H5 — scope


def joint_history(joint: pd.DataFrame, *, force: bool = False) -> pd.DataFrame:
    tag = f"joint_history_{fights_fingerprint(joint)}"
    return cached(tag, lambda: run_whr(joint), force=force)


def missing_career_fraction(
    fights: pd.DataFrame,
    fightmatrix_bouts: pd.DataFrame,
    names: list[str],
) -> pd.DataFrame:
    """How much of a career the engine's window never sees.

    FightMatrix is a *diagnostic* here and nothing else: it is used to count
    the bouts the rated scope is missing, never to move a rating. Its own
    coverage is a bounded cohort, so a zero in ``fm_bouts`` means "not in this
    cache", not "no such bouts".
    """
    fm = fightmatrix_bouts.copy()
    fm["event_date"] = pd.to_datetime(fm["event_date"], errors="coerce")
    window_opens = fights["event_date"].min()
    rows = []
    for name in names:
        own = fights[(fights["fighter_a"] == name) | (fights["fighter_b"] == name)]
        seen = fm[(fm["fighter"] == name) | (fm["opponent"] == name)]
        before = seen[seen["event_date"] < window_opens]
        rows.append({
            "fighter": name,
            "rated_bouts": int(len(own)),
            "rated_from": own["event_date"].min(),
            "fm_bouts": int(len(seen)),
            "fm_from": seen["event_date"].min() if len(seen) else pd.NaT,
            "fm_bouts_before_window": int(len(before)),
            "unseen_fraction": (round(1 - len(own) / len(seen), 3) if len(seen) else np.nan),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# H6 — is the activity penalty anywhere near the career functional


def activity_leak_check(history: pd.DataFrame, current: pd.DataFrame) -> dict:
    """Recompute the board from history alone and diff it against the snapshot.

    ``rate_snapshot`` computes career mass from ``ratings_history_whr`` and only
    then subtracts an inactivity penalty into separate ``*_activity_adjusted``
    columns of the current table. If that ordering ever changed, this diff
    would stop being zero.
    """
    recomputed = board(history)
    merged = recomputed.merge(
        current[["fighter", "symon_career_skill_mass", "activity_mu_penalty", "months_inactive"]],
        on="fighter", how="left",
    )
    diff = (merged["score"] - merged["symon_career_skill_mass"]).abs()
    penalised = merged[merged["activity_mu_penalty"] > 0]
    return {
        "fighters": int(len(merged)),
        "max_abs_diff_vs_snapshot": float(diff.max()),
        "board_is_exactly_reproducible_from_history": bool(diff.max() == 0.0),
        "fighters_with_penalty": int(len(penalised)),
        "max_penalty": float(merged["activity_mu_penalty"].max()),
        "penalised_fighters_with_any_mass_diff": int((diff[penalised.index] > 0).sum()),
        "history_columns": list(history.columns),
    }


# ---------------------------------------------------------------------------
# Re-bootstrapping a variant board


def bootstrap_board(
    fights: pd.DataFrame,
    *,
    replicates: int = 60,
    seed: int = 0,
    reference: str | float = 0.9,
    whr_kwargs: dict | None = None,
    cache_name: str,
    force: bool = False,
) -> pd.DataFrame:
    """Dirichlet event bootstrap of any variant board, cached by name.

    A variant that moves a point estimate has not obviously improved anything
    until its interval is beside it, so every board this notebook proposes
    gets one. Fewer replicates than the production 150: the question here is
    whether a rank *move* survives, not the exact endpoint.
    """
    from ratings.uncertainty import career_mass_bootstrap

    def build() -> pd.DataFrame:
        return career_mass_bootstrap(
            fights, replicates=replicates, seed=seed,
            whr_kwargs=dict(whr_kwargs or {}),
            mass_kwargs={"reference": reference},
        )

    return cached(cache_name, build, force=force)


@dataclass(frozen=True)
class Verdict:
    """One hypothesis' answer, in the three words the brief allows."""

    hypothesis: str
    claim: str
    verdict: str  # supported | refuted | unresolved
    because: str

    def as_markdown(self) -> str:
        icon = {"supported": "●", "refuted": "○", "unresolved": "◐"}[self.verdict]
        return (f"**{self.hypothesis} — {self.verdict.upper()}** {icon}\n\n"
                f"*Prediction:* {self.claim}\n\n*Measured:* {self.because}")


def blast_radius(before: pd.DataFrame, after: pd.DataFrame, *, top_n: int = 100) -> dict:
    """How much of the board a proposed change actually moves.

    A recommendation without this is a preference. Turnover counts the fighters
    who enter or leave the top N; the rank correlation says whether the rest of
    the board survived; the composition pair says whether the change touched
    the thing the investigation is about.
    """
    b = before.set_index("fighter")["rank"]
    a = after.set_index("fighter")["rank"]
    shared = b.index.intersection(a.index)
    top_before, top_after = set(before.head(top_n)["fighter"]), set(after.head(top_n)["fighter"])
    top50 = [f for f in before.head(50)["fighter"] if f in a.index]
    return {
        "top_n": int(top_n),
        "entered_top_n": int(len(top_after - top_before)),
        "left_top_n": int(len(top_before - top_after)),
        "spearman_all": float(b[shared].corr(a[shared], method="spearman")),
        "median_abs_rank_move_top50": float(np.median(np.abs(a[top50] - b[top50]))),
        "active_2024_before": composition(before, top_n=top_n)["active_2024_plus"],
        "active_2024_after": composition(after, top_n=top_n)["active_2024_plus"],
    }


def interval_widths(bootstrap: pd.DataFrame, *, top_n: int = 50) -> dict:
    """Median rank-interval width, so a 'better' board that got vaguer says so."""
    top = bootstrap.head(top_n)
    return {
        "top_n": int(top_n),
        "median_rank_width": float((top["rank_hi"] - top["rank_lo"]).median()),
        "median_mass_width": float((top["mass_hi"] - top["mass_lo"]).median()),
    }


def truncation_population(
    fights: pd.DataFrame,
    full_history: pd.DataFrame,
    *,
    min_bouts: int = 12,
    min_dropped: int = 3,
    force: bool = False,
) -> pd.DataFrame:
    """Run the peak-deletion test on every career long enough to have one.

    Four hand-picked fighters cannot separate "the smoother deleted the peak"
    from "those four declined". The population is every fighter with a record
    long enough to have a peak and a suffix, plus the carried cases and the
    plan's original controls so the notebook can quote both.
    """
    appearances = pd.concat([fights["fighter_a"], fights["fighter_b"]]).value_counts()
    cuts = pd.DataFrame([unbeaten_cut(fights, n) for n in appearances[appearances >= min_bouts].index])
    targets = cuts[cuts["dropped"] >= min_dropped]["fighter"].tolist()
    # CASES and ZERO_MASS overlap; a name refit twice is a duplicate row that
    # would double-weight those fighters in the population regression.
    seen = set(targets)
    for name in CASES + ZERO_MASS + TRUNCATION_CONTROLS:
        if name not in seen:
            seen.add(name)
            targets.append(name)
    return truncation_revisions(
        fights, full_history, targets,
        cache_name="truncation_population", force=force,
    )


def ordinal(n: float) -> str:
    """``3`` -> ``3rd``. Ordinals appear in prose that is generated, not typed,
    so the suffix has to be derived rather than hard-coded beside one number."""
    n = int(round(n))
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
