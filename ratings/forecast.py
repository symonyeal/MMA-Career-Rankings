"""Leak-free pre-fight forecasts for UFC bouts, scored against the no-vig betting price.

The question is whether a forecast built only from what was known before the fight beats the market. Each calendar
year Y is forecast by models fitted on bouts dated before 1 January Y, and every feature reads only earlier dates.

Why the history is narrower than the rating corpus
--------------------------------------------------
``build_sherdog_careers.py`` crawled whole careers, regional bouts included, only for fighters who had three or more
UFC bouts when it ran. A deep pre-UFC record therefore foretells UFC survival. That is right for the rankings, and
it is a leak for a forecast test: on the repository history the market-plus-features model showed a +10.5% betting
return that vanished once the leak was removed. Forecast features here read only bouts from promotions the corpus
enumerates card by card (``ROSTER``), so a fighter's recorded past does not depend on their future. Glicko-2 is
re-run on that history with the production ``RatingEngine``, unchanged.

The data lists the winner first in 62% of bouts, so every model is antisymmetric in the corners:
P(a beats b) + P(b beats a) = 1, and the corner order carries no signal.

Legend
------
a, b     the two corners; d_x is x_a − x_b
y        1 if a won
p_g      Glicko-2 predictive probability (Glickman 2012), unchanged
p_m      market: no-vig implied probability
p_1      model: L2 logistic regression with no intercept on the d_x features (Bradley–Terry form)
p_3      market + model: p_1's design with logit(p_m) added, fitted only on bouts that have odds
w        logistic weights; C the inverse L2 penalty, as in scikit-learn's LogisticRegression
k        rating periods before the bout
s        seconds fought
m15      prior weight of the shrunk UFC rates: 15 minutes at the pre-``Y0`` population rate
ll, br   log loss and Brier score
"""
from __future__ import annotations

import bisect
from pathlib import Path

import numpy as np
import pandas as pd

from .age import load_birth_dates
from .constants import JULIAN_YEAR_DAYS
from .evaluation import EPS, losses
from .fights import canonical_engine
from .glicko2_engine import DEFAULT_TAU, predict_win_prob_from_ratings

ROSTER = frozenset({"UFC", "UFC (pre-unified)", "Ultimate Fighting Championship (UFC)", "PRIDE", "WEC",
                    "Strikeforce", "Affliction", "Bellator", "RIZIN"})
Y0 = 2012  # first test year; earlier bouts only train
C = 1.0
SEED, B = 20261027, 2000
UFC_RATES = ("slpm", "sapm", "sacc", "sdef", "td15", "tdacc", "tddef", "sub15", "ctrl", "kd15", "kda15")


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def fit(A: np.ndarray, y: np.ndarray, iters: int = 50) -> np.ndarray:
    """w minimising C·Σ log loss + ½‖w‖² on rows A and their mirror −A (Newton steps)."""
    A, y = np.vstack([A, -A]), np.r_[y, 1 - y]
    w = np.zeros(A.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-A @ w))
        g = C * A.T @ (p - y) + w
        H = C * (A * (p * (1 - p))[:, None]).T @ A + np.eye(len(w))
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-10:
            break
    return w


def prob(A: np.ndarray, w: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-A @ w))


def _flag(s: pd.Series) -> pd.Series:
    return s.fillna(False).astype(bool)


def _record(cb: pd.DataFrame) -> pd.DataFrame:
    """Per fighter and date, from strictly earlier dates: bouts, wins, streak, layoff days, KO losses in 730 days."""
    L = pd.concat([pd.DataFrame({"f": cb[x], "event_date": cb["event_date"],
                                 "w": np.where(cb["is_draw"], .5, (cb["winner"] == cb[x]).astype(float)),
                                 "kol": ((cb["loser"] == cb[x]) & (cb["method_class"] == "KO/TKO")).astype(float)})
                   for x in ("fighter_a", "fighter_b")]).dropna(subset=["f"])
    D = L.groupby(["f", "event_date"], sort=True).agg(n=("w", "size"), w=("w", "sum"), kol=("kol", "sum"),
                                                     wl=("w", "min")).reset_index()
    rows = []
    for f, g in D.groupby("f", sort=False):
        n = w = 0.0
        st, prev, kd = 0, None, []
        for t, dn, dw, dk, wl in zip(g["event_date"], g["n"], g["w"], g["kol"], g["wl"]):
            i = bisect.bisect_left(kd, t - pd.Timedelta(days=730))
            rows.append((f, t, n, w, st, (t - prev).days if prev is not None else np.nan, len(kd) - i))
            n, w, prev = n + dn, w + dw, t
            st = (st + 1 if st >= 0 else 1) if wl == 1 else ((st - 1 if st <= 0 else -1) if wl == 0 else 0)
            kd += [t] * int(dk)
    return pd.DataFrame(rows, columns=["f", "event_date", "npro", "wpro", "streak", "lay", "ko2"])


def _ufc_rates(rd: pd.DataFrame, cf: pd.DataFrame) -> pd.DataFrame:
    """Per fighter and date, UFC in-fight rates from strictly earlier bouts, shrunk toward the pre-Y0 rate."""
    q = {"sl": "sig_str_landed", "sa": "sig_str_attempted", "tl": "td_landed", "ta": "td_attempted",
         "sub": "sub_att", "ctrl": "ctrl_seconds", "kd": "kd"}
    g = rd.groupby(["fight_url", "fighter"])[list(q.values())].sum().rename(columns={v: k for k, v in q.items()})
    g = g.reset_index()
    g = g.merge(g.rename(columns={"fighter": "opp", **{k: "o" + k for k in q}}), on="fight_url")
    g = g[g["fighter"] != g["opp"]].merge(cf[["fight_url", "event_date", "s"]], on="fight_url").dropna(subset=["s"])
    sc = list(q) + ["o" + k for k in q] + ["s"]
    g = g.groupby(["fighter", "event_date"])[sc].sum().reset_index().sort_values(["fighter", "event_date"])
    g["nufc"] = 1.0
    U = pd.concat([g[["fighter", "event_date"]].rename(columns={"fighter": "f"}),
                   g.groupby("fighter")[sc + ["nufc"]].cumsum() - g[sc + ["nufc"]]], axis=1)
    pre = g[g["event_date"] < f"{Y0}-01-01"][sc].sum()
    m15 = 900.0

    def rate(num, den, w):
        return (U[num] + pre[num] / pre[den] * w) / (U[den] + w)

    wsa, wta, wosa, wota = (pre[c] / pre["s"] * m15 for c in ("sa", "ta", "osa", "ota"))
    U["slpm"], U["sapm"] = rate("sl", "s", m15) * 60, rate("osl", "s", m15) * 60
    U["sacc"], U["sdef"] = rate("sl", "sa", wsa), 1 - rate("osl", "osa", wosa)
    U["td15"], U["tdacc"] = rate("tl", "s", m15) * 900, rate("tl", "ta", wta)
    U["tddef"], U["sub15"] = 1 - rate("otl", "ota", wota), rate("sub", "s", m15) * 900
    U["ctrl"], U["kd15"], U["kda15"] = rate("ctrl", "s", m15), rate("kd", "s", m15) * 900, rate("okd", "s", m15) * 900
    return U[["f", "event_date", *UFC_RATES, "nufc"]]


def _glicko(cb: pd.DataFrame) -> pd.DataFrame:
    eng = canonical_engine(cb.dropna(subset=["event_date", "event_name"]), tau=DEFAULT_TAU)
    h = eng.history_df().sort_values(["fighter", "event_date"], kind="stable")
    h["k"] = h.groupby("fighter").cumcount()
    h = h.drop_duplicates(["fighter", "event_date"])
    return h.rename(columns={"fighter": "f", "pre_mu_canonical": "mu", "pre_phi_canonical": "phi"})[
        ["f", "event_date", "mu", "phi", "k"]]


def bout_frame(snap: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(X, F): one row per decided UFC bout with forecasts' inputs, and the d_x feature matrix."""
    snap = Path(snap)
    cf = pd.read_parquet(snap / "canonical_fights.parquet")
    cf["s"] = (cf["end_round"].astype(float) - 1) * 300 + cf["end_time_seconds"]
    X = cf[~_flag(cf["is_excluded"]) & ~_flag(cf["is_draw"]) & ~_flag(cf["is_nc"]) & cf["winner"].notna()]
    X = X[["fight_url", "event_name", "event_date", "fighter_a", "fighter_b", "winner"]].reset_index(drop=True)
    X["y"] = X["winner"].eq(X["fighter_a"]).astype(float)

    cb = pd.read_parquet(snap / "combined_fights.parquet")
    cb = cb[cb["is_model_bout"].astype(bool) & ~_flag(cb["is_nc"])]
    cb = cb[(cb["source"] == "ufc") | cb["org"].isin(ROSTER)]
    U = _ufc_rates(pd.read_parquet(snap / "canonical_rounds.parquet"), cf)
    dob = load_birth_dates(snap)
    fi = pd.read_parquet(snap / "canonical_fighters.parquet").drop_duplicates("fighter").set_index("fighter")
    for frame in (_record(cb), U, _glicko(cb)):
        cols = [c for c in frame.columns if c not in ("f", "event_date")]
        for s in "ab":
            X = X.merge(frame.rename(columns={"f": f"fighter_{s}", **{c: f"{c}_{s}" for c in cols}}),
                        on=[f"fighter_{s}", "event_date"], how="left")
    debut = U.loc[U["nufc"] == 0, list(UFC_RATES)].mean()
    for s in "ab":
        X[f"age_{s}"] = (X["event_date"] - X[f"fighter_{s}"].map(dob)).dt.days / JULIAN_YEAR_DAYS
        X[f"ht_{s}"] = X[f"fighter_{s}"].map(fi["height_inches"])
        X[f"rch_{s}"] = X[f"fighter_{s}"].map(fi["reach_inches"])
        X = X.fillna({f"mu_{s}": 1500.0, f"phi_{s}": 350.0, f"k_{s}": 0, f"nufc_{s}": 0, f"npro_{s}": 0,
                      f"wpro_{s}": 0, f"streak_{s}": 0, f"ko2_{s}": 0, **{f"{c}_{s}": debut[c] for c in UFC_RATES}})
    X["p_g"] = [predict_win_prob_from_ratings(*r) for r in
                X[["mu_a", "phi_a", "mu_b", "phi_b"]].astype(float).itertuples(index=False)]

    def d(c, fn=lambda v: v):
        return (fn(X[c + "_a"].astype(float)) - fn(X[c + "_b"].astype(float))).fillna(0.0)

    wr = lambda s: (X[f"wpro_{s}"] + 2) / (X[f"npro_{s}"] + 4)
    F = pd.DataFrame({
        "g_logit": logit(X["p_g"]), "d_phi": d("phi"),
        "d_age": d("age"), "d_age32": d("age", lambda v: np.maximum(v - 32, 0)),
        "d_ht": d("ht"), "d_rch": d("rch"),
        "d_lay": d("lay", lambda v: np.log1p(v.fillna(0))), "d_lay365": d("lay", lambda v: (v > 365).astype(float)),
        "d_npro": d("npro", np.log1p), "d_wr": (wr("a") - wr("b")).astype(float),
        "d_streak": d("streak"), "d_ko2": d("ko2"), "d_nufc": d("nufc", np.log1p),
        **{f"d_{c}": d(c) for c in UFC_RATES},
    }).astype(float)

    od = pd.read_parquet(snap / "odds_lines.parquet")
    od = od[od["odds_data_quality"].eq("ok") & od["implied_prob_a_no_vig"].between(.001, .999)]
    X = X.merge(od[["fight_url", "fighter_a", "implied_prob_a_no_vig"]].rename(columns={"fighter_a": "od_a"}),
                on="fight_url", how="left")
    assert X["od_a"].isna().sum() + X["od_a"].eq(X["fighter_a"]).sum() == len(X), "odds corner order differs"
    X["p_m"] = X["implied_prob_a_no_vig"]
    F["m_logit"] = logit(X["p_m"].fillna(.5))
    return X, F


def walk_forward(X: pd.DataFrame, F: pd.DataFrame) -> pd.DataFrame:
    """Adds p_1 and p_3: each test year forecast by fits on bouts dated before that year."""
    X = X.copy()
    yr = X["event_date"].dt.year
    c1 = [c for c in F.columns if c != "m_logit"]
    c3 = ["m_logit", *c1]
    X["p_1"] = X["p_3"] = np.nan
    for Y in range(Y0, int(yr.max()) + 1):
        tr, te = (yr < Y).to_numpy(), (yr == Y).to_numpy()
        for out, cols, rows in (("p_1", c1, tr), ("p_3", c3, tr & X["p_m"].notna().to_numpy())):
            A = F.loc[rows, cols].to_numpy()
            sd = np.r_[A, -A].std(0) + 1e-12  # scaled, never centred: centring would break antisymmetry
            w = fit(A / sd, X.loc[rows, "y"].to_numpy())
            X.loc[te, out] = prob(F.loc[te, cols].to_numpy() / sd, w)
    return X


def score(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per bout: log loss, Brier, winner picked (a coin's 0.5 counts as half)."""
    p = np.clip(p, EPS, 1 - EPS)
    ll, br = losses(p, y)
    return np.c_[ll, br,
                 np.where(p == .5, .5, (p > .5) == (y == 1))]


def interval(v: np.ndarray, cluster: np.ndarray, rng: np.random.Generator) -> list[float]:
    """95% cluster-bootstrap interval of mean(v), resampling whole events."""
    k = pd.factorize(cluster)[0]
    sv, sn = np.bincount(k, v), np.bincount(k)
    ix = rng.integers(0, len(sv), (B, len(sv)))
    mm = sv[ix].sum(1) / sn[ix].sum(1)
    return [float(np.percentile(mm, 2.5)), float(np.percentile(mm, 97.5))]


def benchmark(snap: Path) -> tuple[pd.DataFrame, dict]:
    """Test bouts with odds from Y0 on, and per forecast: [ll, br, acc] plus the ll gap to the market."""
    X = walk_forward(*bout_frame(snap))
    E = X[(X["event_date"].dt.year >= Y0) & X["p_m"].notna()].reset_index(drop=True)
    E["p_0"] = .5
    y, ev, rng = E["y"].to_numpy(), E["event_name"].to_numpy(), np.random.default_rng(SEED)
    S = {c: score(E[c].to_numpy(), y) for c in ("p_0", "p_g", "p_1", "p_m", "p_3")}
    out = {"n": len(E), "events": int(E["event_name"].nunique()),
           "from": str(E["event_date"].min().date()), "to": str(E["event_date"].max().date())}
    for c, s in S.items():
        gap = s[:, 0] - S["p_m"][:, 0]
        out[c] = [*s.mean(0).tolist(), float(gap.mean()), *(interval(gap, ev, rng) if c != "p_m" else [0.0, 0.0])]
    return E, out


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(benchmark(Path(sys.argv[1]))[1], indent=1))
