"""Build-time diagnostic tables for the notebook.

The notebook should be a read-only diagnostic surface. These helpers compute
the heavy evidence tables during snapshot generation so visual cells only
load and plot stable artifacts.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ratings.glicko2_engine import predict_win_prob_from_ratings
from ratings.performance_adjustment import normalize_division_label


def _prefight_history(history: pd.DataFrame, mu_col: str, phi_col: str | None = None) -> pd.DataFrame:
    cols = ["fighter", "event_date", "event_name", mu_col]
    if phi_col and phi_col in history.columns:
        cols.append(phi_col)
    h = history[cols].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h = h.sort_values(["fighter", "event_date", "event_name"]).reset_index(drop=True)
    h[f"prefight_{mu_col}"] = h.groupby("fighter")[mu_col].shift(1).fillna(1500.0)
    if phi_col and phi_col in h.columns:
        h[f"prefight_{phi_col}"] = h.groupby("fighter")[phi_col].shift(1).fillna(350.0)
        h["prefight_periods"] = h.groupby("fighter").cumcount()
    return h


def _stance_lookup(fighters: pd.DataFrame | None) -> pd.DataFrame:
    if fighters is None or fighters.empty or "stance" not in fighters.columns:
        return pd.DataFrame(columns=["fighter", "stance"])
    out = fighters[["fighter", "stance"]].drop_duplicates("fighter").copy()
    out["stance"] = out["stance"].fillna("Unknown").replace({"": "Unknown"})
    return out


def calibration_residual_rows(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    fighters: pd.DataFrame | None = None,
    *,
    n_bins: int = 10,
    min_prefight_periods: int = 3,
) -> pd.DataFrame:
    """Predicted-vs-empirical rows segmented by division and stance.

    One non-draw bout contributes two appearance rows: fighter A with
    ``p_win = P(A beats B)`` and fighter B with ``1 - p_win``. The segment
    summaries are therefore symmetric and can be sliced by stance.
    """
    out_cols = [
        "segment_type", "segment_value", "prob_bin", "predicted_mean",
        "empirical_win_rate", "residual", "brier", "n",
    ]
    if ratings_history is None or ratings_history.empty or fights is None or fights.empty:
        return pd.DataFrame(columns=out_cols)

    f = fights.copy()
    if "is_excluded" in f.columns:
        f = f[~f["is_excluded"].fillna(False).astype(bool)]
    f = f[~f.get("is_draw", pd.Series(False, index=f.index)).fillna(False).astype(bool)].copy()
    f = f.dropna(subset=["winner", "fighter_a", "fighter_b"])
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["division"] = f.get("weight_class", pd.Series(index=f.index)).map(normalize_division_label)

    pref = _prefight_history(ratings_history, "mu_canonical", "phi_canonical")
    a = pref.rename(columns={
        "fighter": "fighter_a",
        "prefight_mu_canonical": "mu_a",
        "prefight_phi_canonical": "phi_a",
        "prefight_periods": "periods_a",
    })[["fighter_a", "event_date", "event_name", "mu_a", "phi_a", "periods_a"]]
    b = pref.rename(columns={
        "fighter": "fighter_b",
        "prefight_mu_canonical": "mu_b",
        "prefight_phi_canonical": "phi_b",
        "prefight_periods": "periods_b",
    })[["fighter_b", "event_date", "event_name", "mu_b", "phi_b", "periods_b"]]
    f = f.merge(a, on=["fighter_a", "event_date", "event_name"], how="left")
    f = f.merge(b, on=["fighter_b", "event_date", "event_name"], how="left")
    for col, default in (("mu_a", 1500.0), ("mu_b", 1500.0), ("phi_a", 350.0), ("phi_b", 350.0)):
        f[col] = pd.to_numeric(f[col], errors="coerce").fillna(default)
    for col in ("periods_a", "periods_b"):
        f[col] = pd.to_numeric(f[col], errors="coerce").fillna(0)
    f = f[(f["periods_a"] >= min_prefight_periods) & (f["periods_b"] >= min_prefight_periods)]
    if f.empty:
        return pd.DataFrame(columns=out_cols)

    f["p_a"] = [
        predict_win_prob_from_ratings(mu_a, phi_a, mu_b, phi_b)
        for mu_a, phi_a, mu_b, phi_b in zip(f["mu_a"], f["phi_a"], f["mu_b"], f["phi_b"])
    ]
    f["actual_a"] = f["winner"].eq(f["fighter_a"]).astype(float)

    stance = _stance_lookup(fighters)
    left = f[["fight_url", "division", "fighter_a", "p_a", "actual_a"]].rename(
        columns={"fighter_a": "fighter", "p_a": "p_win", "actual_a": "actual"}
    )
    right = f[["fight_url", "division", "fighter_b", "p_a", "actual_a"]].rename(
        columns={"fighter_b": "fighter"}
    )
    right["p_win"] = 1.0 - right["p_a"]
    right["actual"] = 1.0 - right["actual_a"]
    right = right.drop(columns=["p_a", "actual_a"])
    apps = pd.concat([left, right], ignore_index=True, sort=False)
    apps = apps.merge(stance, on="fighter", how="left")
    apps["stance"] = apps["stance"].fillna("Unknown")

    bins = np.linspace(0.0, 1.0, n_bins + 1)

    def _summarize(frame: pd.DataFrame, segment_type: str, segment_value: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=out_cols)
        work = frame.copy()
        work["prob_bin"] = pd.cut(work["p_win"], bins=bins, include_lowest=True, labels=False)
        grouped = (
            work.groupby("prob_bin", as_index=False)
            .agg(
                predicted_mean=("p_win", "mean"),
                empirical_win_rate=("actual", "mean"),
                brier_pair=("p_win", lambda s: float(np.nan)),
                n=("actual", "size"),
            )
            .dropna(subset=["prob_bin"])
        )
        if grouped.empty:
            return pd.DataFrame(columns=out_cols)
        # Brier must use the paired actual values, so compute it separately.
        brier = work.groupby("prob_bin").apply(
            lambda g: float(((g["p_win"] - g["actual"]) ** 2).mean()),
            include_groups=False,
        )
        grouped["brier"] = grouped["prob_bin"].map(brier)
        grouped["segment_type"] = segment_type
        grouped["segment_value"] = segment_value
        grouped["residual"] = grouped["empirical_win_rate"] - grouped["predicted_mean"]
        return grouped[out_cols]

    frames = [_summarize(apps, "overall", "all")]
    for division, g in apps.groupby("division", dropna=False):
        frames.append(_summarize(g, "division", str(division or "Unknown")))
    for stance_value, g in apps.groupby("stance", dropna=False):
        frames.append(_summarize(g, "stance", str(stance_value or "Unknown")))
    out = pd.concat(frames, ignore_index=True, sort=False)
    out["prob_bin"] = out["prob_bin"].astype(int)
    out["n"] = out["n"].astype(int)
    return out


def sleeve_attribution_rows(
    method_history: pd.DataFrame,
    sleeve_histories: dict[str, pd.DataFrame],
    integrity_appearances: pd.DataFrame,
    performance_appearances: pd.DataFrame,
) -> pd.DataFrame:
    """Per-fighter event deltas decomposed into base, sleeves, and interaction."""
    out_cols = [
        "fighter", "event_date", "event_name", "fight_url", "opponent",
        "base_method_delta", "integrity_delta", "performance_delta",
        "interaction_delta", "combined_delta", "integrity_weight",
        "performance_weight", "combined_weight",
    ]
    if method_history is None or method_history.empty:
        return pd.DataFrame(columns=out_cols)

    def _deltas(hist: pd.DataFrame, mu_col: str, out_col: str) -> pd.DataFrame:
        h = hist[["fighter", "event_date", "event_name", mu_col]].copy()
        h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
        h = h.sort_values(["fighter", "event_date", "event_name"]).reset_index(drop=True)
        h[f"prev_{mu_col}"] = h.groupby("fighter")[mu_col].shift(1).fillna(1500.0)
        h[out_col] = pd.to_numeric(h[mu_col], errors="coerce") - pd.to_numeric(h[f"prev_{mu_col}"], errors="coerce")
        return h[["fighter", "event_date", "event_name", out_col]]

    base = _deltas(method_history, "mu_method", "base_method_delta")
    integ = _deltas(
        sleeve_histories.get("method_integrity", pd.DataFrame()),
        "mu",
        "method_integrity_delta",
    ) if "method_integrity" in sleeve_histories else pd.DataFrame()
    perf = _deltas(
        sleeve_histories.get("method_performance", pd.DataFrame()),
        "mu",
        "method_performance_delta",
    ) if "method_performance" in sleeve_histories else pd.DataFrame()
    both = _deltas(
        sleeve_histories.get("method_integrity_performance", pd.DataFrame()),
        "mu",
        "combined_delta",
    ) if "method_integrity_performance" in sleeve_histories else pd.DataFrame()

    out = base.copy()
    for frame in (integ, perf, both):
        if not frame.empty:
            out = out.merge(frame, on=["fighter", "event_date", "event_name"], how="left")
    out["method_integrity_delta"] = out.get("method_integrity_delta", pd.Series(index=out.index)).fillna(out["base_method_delta"])
    out["method_performance_delta"] = out.get("method_performance_delta", pd.Series(index=out.index)).fillna(out["base_method_delta"])
    out["combined_delta"] = out.get("combined_delta", pd.Series(index=out.index)).fillna(out["base_method_delta"])
    out["integrity_delta"] = out["method_integrity_delta"] - out["base_method_delta"]
    out["performance_delta"] = out["method_performance_delta"] - out["base_method_delta"]
    out["interaction_delta"] = (
        out["combined_delta"]
        - out["base_method_delta"]
        - out["integrity_delta"]
        - out["performance_delta"]
    )

    if performance_appearances is not None and not performance_appearances.empty:
        enrich = performance_appearances[[
            "fight_url", "fighter", "event_date", "event_name", "opponent", "performance_weight",
        ]].copy()
        enrich["event_date"] = pd.to_datetime(enrich["event_date"], errors="coerce")
        out = out.merge(enrich, on=["fighter", "event_date", "event_name"], how="left")
    else:
        out["fight_url"] = pd.NA
        out["opponent"] = pd.NA
        out["performance_weight"] = 1.0
    if integrity_appearances is not None and not integrity_appearances.empty and "fight_url" in out.columns:
        iw = integrity_appearances[["fight_url", "fighter", "integrity_weight"]].copy()
        out = out.merge(iw, on=["fight_url", "fighter"], how="left")
    else:
        out["integrity_weight"] = 1.0
    out["integrity_weight"] = pd.to_numeric(out["integrity_weight"], errors="coerce").fillna(1.0)
    out["performance_weight"] = pd.to_numeric(out["performance_weight"], errors="coerce").fillna(1.0)
    out["combined_weight"] = (out["integrity_weight"] * out["performance_weight"]).clip(0.80, 1.20)
    return out[out_cols].copy()


def division_entropy_rows(
    ratings_history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    top_n: int = 10,
    temperature: float = 100.0,
) -> pd.DataFrame:
    """Top-N divisional rating density by calendar year.

    High normalized entropy means the top of the division is dense and
    competitive; low entropy means one or two fighters dominate the mass.
    """
    out_cols = [
        "year", "division", "fighters_in_division", "top_n", "top_mu_mean",
        "top_mu_std", "top_mu_range", "density_per_100_mu",
        "entropy_normalized",
    ]
    if ratings_history is None or ratings_history.empty or fights is None or fights.empty:
        return pd.DataFrame(columns=out_cols)

    f = fights.copy()
    if "is_excluded" in f.columns:
        f = f[~f["is_excluded"].fillna(False).astype(bool)]
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["division"] = f.get("weight_class", pd.Series(index=f.index)).map(normalize_division_label)
    a = f[["event_date", "event_name", "division", "fighter_a"]].rename(columns={"fighter_a": "fighter"})
    b = f[["event_date", "event_name", "division", "fighter_b"]].rename(columns={"fighter_b": "fighter"})
    apps = pd.concat([a, b], ignore_index=True, sort=False).dropna(subset=["fighter", "division"])

    h = ratings_history[["fighter", "event_date", "event_name", "mu_canonical"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    merged = apps.merge(h, on=["fighter", "event_date", "event_name"], how="inner")
    if merged.empty:
        return pd.DataFrame(columns=out_cols)
    merged["year"] = merged["event_date"].dt.year
    latest = (
        merged.sort_values(["year", "division", "fighter", "event_date", "event_name"])
        .groupby(["year", "division", "fighter"], as_index=False)
        .last()
    )

    rows: list[dict] = []
    for (year, division), group in latest.groupby(["year", "division"], sort=True):
        g = group.dropna(subset=["mu_canonical"]).sort_values("mu_canonical", ascending=False)
        if g.empty:
            continue
        top = g.head(top_n)
        mu = pd.to_numeric(top["mu_canonical"], errors="coerce").dropna().to_numpy(dtype=float)
        if mu.size == 0:
            continue
        centered = mu - float(mu.max())
        weights = np.exp(centered / max(float(temperature), 1.0))
        probs = weights / weights.sum()
        entropy = -float(np.sum(probs * np.log(probs))) / math.log(len(probs)) if len(probs) > 1 else 0.0
        mu_range = float(mu.max() - mu.min()) if len(mu) > 1 else 0.0
        rows.append({
            "year": int(year),
            "division": division,
            "fighters_in_division": int(g["fighter"].nunique()),
            "top_n": int(len(mu)),
            "top_mu_mean": float(mu.mean()),
            "top_mu_std": float(mu.std(ddof=0)),
            "top_mu_range": mu_range,
            "density_per_100_mu": float(len(mu) / max(mu_range / 100.0, 1.0)),
            "entropy_normalized": entropy,
        })
    return pd.DataFrame(rows, columns=out_cols)
