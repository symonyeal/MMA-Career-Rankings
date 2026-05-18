"""Per-fight and per-fighter dominance index.

Components (user-specified ordering):
  1. Damage    — significant strikes landed differential.
  2. Submission — submission-attempt differential AND ground-control-time differential.
  3. Top control — Greco's CTRL column is total control time, which in
     practice is dominated by top-position time; we treat it as the proxy.

Per-fight scalar: z-score each diff across the snapshot's fight set, sum
with equal weights. Higher = more dominant performance by fighter_a over
fighter_b. Negate to get fighter_b's perspective.

Per-fighter aggregate: mean(dominance) across that fighter's bouts where
they were the winner (a positive aggregate means "wins decisively"; near
zero means "wins close").
"""
from __future__ import annotations

import pandas as pd


def _z(s: pd.Series) -> pd.Series:
    mu = s.mean()
    sd = s.std(ddof=0)
    if sd == 0 or pd.isna(sd):
        return pd.Series([0.0] * len(s), index=s.index)
    return (s - mu) / sd


def per_fight_dominance(rounds: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    """Return one row per fight with the dominance scalar (a-perspective).

    Sums per-round stats up to fight level, then computes A−B diffs and
    z-scores them across the snapshot.
    """
    agg_cols = ["sig_str_landed", "sub_att", "ctrl_seconds"]
    rounds = rounds.copy()
    for c in agg_cols:
        rounds[c] = pd.to_numeric(rounds[c], errors="coerce").fillna(0)
    bout = rounds.groupby(["fight_url", "fighter"], as_index=False)[agg_cols].sum()

    fa = fights[["fight_url", "fighter_a", "fighter_b", "winner", "is_draw"]].copy()
    a = bout.merge(fa, left_on=["fight_url", "fighter"], right_on=["fight_url", "fighter_a"], how="inner")
    b = bout.merge(fa, left_on=["fight_url", "fighter"], right_on=["fight_url", "fighter_b"], how="inner")
    a_side = a[["fight_url"] + agg_cols].rename(columns={c: f"{c}_a" for c in agg_cols})
    b_side = b[["fight_url"] + agg_cols].rename(columns={c: f"{c}_b" for c in agg_cols})
    merged = a_side.merge(b_side, on="fight_url", how="inner")

    for c in agg_cols:
        merged[f"{c}_diff"] = merged[f"{c}_a"] - merged[f"{c}_b"]

    merged["z_sig_str"] = _z(merged["sig_str_landed_diff"])
    merged["z_sub_att"] = _z(merged["sub_att_diff"])
    merged["z_ctrl"]    = _z(merged["ctrl_seconds_diff"])
    merged["dominance_a"] = merged["z_sig_str"] + merged["z_sub_att"] + merged["z_ctrl"]

    out = merged[["fight_url", "sig_str_landed_diff", "sub_att_diff",
                  "ctrl_seconds_diff", "z_sig_str", "z_sub_att", "z_ctrl",
                  "dominance_a"]].copy()
    return out


def per_fighter_dominance(fight_dom: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    """Mean dominance (from the winner's perspective) per fighter."""
    f = fights[["fight_url", "winner", "fighter_a", "fighter_b"]].merge(
        fight_dom[["fight_url", "dominance_a"]], on="fight_url", how="inner"
    )
    # dominance from the winner's perspective
    f["dominance_winner"] = f.apply(
        lambda r: r["dominance_a"] if r["winner"] == r["fighter_a"]
        else (-r["dominance_a"] if r["winner"] == r["fighter_b"] else None),
        axis=1,
    )
    f = f.dropna(subset=["winner", "dominance_winner"])
    agg = f.groupby("winner", as_index=False).agg(
        wins=("fight_url", "count"),
        mean_dominance=("dominance_winner", "mean"),
    ).rename(columns={"winner": "fighter"})
    return agg.sort_values("mean_dominance", ascending=False).reset_index(drop=True)
