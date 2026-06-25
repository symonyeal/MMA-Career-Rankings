"""Per-fight and per-fighter dominance index.

Components (user-specified ordering):
  1. Damage    — significant strikes landed differential.
  2. Submission — submission-attempt differential AND ground-control-time differential.
  3. Top control — Greco's CTRL column is total control time, which in
     practice is dominated by top-position time; we treat it as the proxy.

Per-fight scalar: the three components are normalized to PER-MINUTE rates
(strikes/min, sub-attempts/min, control-seconds/min) using the bout's actual
duration, then A−B diffs are z-scored across the snapshot and summed with equal
weights. Per-minute (not accumulated totals) means a 60-second blow-out is not
penalized for being short and a 25-minute grind is not flattered for being long.
Higher = more dominant performance by fighter_a over fighter_b. Negate for
fighter_b's perspective.

Finish floor: a KO/TKO or Submission win IS a dominant result, so the
winner-perspective dominance is floored at ``DOMINANCE_FINISH_FLOOR_Z`` — a flash
KO with few landed strikes no longer scores ~0. The floor is also why this
returns a row for EVERY bout (not only those with round-level stats): a finish
with no scraped round data still earns the floor.

Per-fighter aggregate: mean(dominance) across that fighter's bouts where
they were the winner (a positive aggregate means "wins decisively"; near
zero means "wins close").
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import DOMINANCE_FINISH_FLOOR_Z
from project_helpers import normalize_name_key

_FINISH_METHODS = ("KO/TKO", "Submission")


def _z(s: pd.Series) -> pd.Series:
    mu = s.mean()
    sd = s.std(ddof=0)
    if sd == 0 or pd.isna(sd):
        return pd.Series([0.0] * len(s), index=s.index)
    return (s - mu) / sd


def _fight_minutes(fights: pd.DataFrame) -> pd.Series:
    """Bout duration in minutes from ``end_round`` + ``end_time_seconds``.

    A completed round is 5:00; the final round ends at ``end_time_seconds``. A
    0.5-minute floor guards against dividing per-minute rates by ~0 on a flash
    finish (and against missing duration data).
    """
    end_round = pd.to_numeric(fights.get("end_round"), errors="coerce")
    end_secs = pd.to_numeric(fights.get("end_time_seconds"), errors="coerce")
    total_secs = (end_round - 1).clip(lower=0) * 300.0 + end_secs
    # 1-minute floor: a sub-minute finish must not divide into an explosive
    # per-minute rate that inflates the snapshot z-scale (finishes are floored by
    # DOMINANCE_FINISH_FLOOR_Z anyway, so their raw rate is not the signal).
    return (total_secs / 60.0).clip(lower=1.0)


def _parse_pts(value) -> float:
    """Mean of a judge-total string like ``"29 28 28"`` (one token per judge)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return float("nan")
    toks = [t for t in str(value).replace(",", " ").split() if t.lstrip("-").isdigit()]
    return float(np.mean([int(t) for t in toks])) if toks else float("nan")


def _scorecard_margin_a(fights: pd.DataFrame, scorecards: pd.DataFrame | None) -> pd.DataFrame:
    """``fight_url`` -> mean judge scorecard margin from fighter_a's perspective.

    Positive = fighter_a won by a wider card — the decision "round win gap" (a
    50-45 sweep is +5; a 48-47 squeaker +1). Joined to the canonical bout by the
    normalized ``{name, name}`` pair + event date so red/blue corner vs a/b
    ordering does not matter. Returns an empty frame if no scorecards are present.
    """
    cols = {"red_fighter_name", "blue_fighter_name", "event_date",
            "red_fighter_total_pts", "blue_fighter_total_pts"}
    if scorecards is None or scorecards.empty or not cols.issubset(scorecards.columns):
        return pd.DataFrame(columns=["fight_url", "scorecard_margin_a"])
    sc = scorecards.copy()
    sc["_red"] = sc["red_fighter_name"].map(normalize_name_key)
    sc["_blue"] = sc["blue_fighter_name"].map(normalize_name_key)
    sc["_date"] = pd.to_datetime(sc["event_date"], errors="coerce").dt.date
    sc["_margin"] = sc["red_fighter_total_pts"].map(_parse_pts) - sc["blue_fighter_total_pts"].map(_parse_pts)
    sc = sc.dropna(subset=["_red", "_blue", "_date", "_margin"])
    # red-perspective margin + which normalized name was the red corner, keyed by pair+date.
    red_by_key = {
        (frozenset((red, blue)), date): (red, margin)
        for red, blue, date, margin in zip(sc["_red"], sc["_blue"], sc["_date"], sc["_margin"])
    }

    f = fights[["fight_url", "fighter_a", "fighter_b", "event_date"]].copy()
    a_key = f["fighter_a"].map(normalize_name_key)
    b_key = f["fighter_b"].map(normalize_name_key)
    date = pd.to_datetime(f["event_date"], errors="coerce").dt.date

    margins = []
    for a, b, d in zip(a_key, b_key, date):
        rec = red_by_key.get((frozenset((a, b)), d))
        if rec is None:
            margins.append(float("nan"))
        else:
            red_norm, red_margin = rec
            margins.append(float(red_margin) if a == red_norm else float(-red_margin))
    f["scorecard_margin_a"] = margins
    return f.dropna(subset=["scorecard_margin_a"])[["fight_url", "scorecard_margin_a"]]


def per_fight_dominance(
    rounds: pd.DataFrame,
    fights: pd.DataFrame,
    scorecards: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one row per fight with the dominance scalar (a-perspective).

    Per-round stats are summed to bout level, divided by bout duration to get
    per-minute rates, then A−B diffs are z-scored across the snapshot and summed.
    For DECISIONS, the affine-normalized (z-scored) judge scorecard margin — the
    "round win gap", a 50-45 sweep vs a 48-47 squeaker — is added as a fourth
    component when ``scorecards`` is supplied, so a one-sided decision reads as
    dominant even when the strike/control rates were close. Finishes (KO/TKO,
    Submission) instead floor the winner-perspective dominance at
    ``DOMINANCE_FINISH_FLOOR_Z``. One row per bout in ``fights`` (finishes without
    round data still receive the floor).
    """
    agg_cols = ["sig_str_landed", "sub_att", "ctrl_seconds"]
    rate_cols = [f"{c}_diff" for c in agg_cols]  # kept names; now per-minute-rate diffs
    rounds = rounds.copy()
    for c in agg_cols:
        rounds[c] = pd.to_numeric(rounds[c], errors="coerce").fillna(0)
    bout = rounds.groupby(["fight_url", "fighter"], as_index=False)[agg_cols].sum()

    # Per-minute exposure normalization.
    minutes = pd.DataFrame({"fight_url": fights["fight_url"], "_minutes": _fight_minutes(fights)})
    bout = bout.merge(minutes, on="fight_url", how="left")
    for c in agg_cols:
        bout[c] = bout[c] / bout["_minutes"].where(bout["_minutes"] > 0, other=np.nan)

    fa = fights[["fight_url", "fighter_a", "fighter_b", "winner", "is_draw"]].copy()
    a = bout.merge(fa, left_on=["fight_url", "fighter"], right_on=["fight_url", "fighter_a"], how="inner")
    b = bout.merge(fa, left_on=["fight_url", "fighter"], right_on=["fight_url", "fighter_b"], how="inner")
    a_side = a[["fight_url"] + agg_cols].rename(columns={c: f"{c}_a" for c in agg_cols})
    b_side = b[["fight_url"] + agg_cols].rename(columns={c: f"{c}_b" for c in agg_cols})
    merged = a_side.merge(b_side, on="fight_url", how="inner")

    for c, rc in zip(agg_cols, rate_cols):
        merged[rc] = merged[f"{c}_a"] - merged[f"{c}_b"]

    merged["z_sig_str"] = _z(merged["sig_str_landed_diff"])
    merged["z_sub_att"] = _z(merged["sub_att_diff"])
    merged["z_ctrl"]    = _z(merged["ctrl_seconds_diff"])
    merged["dominance_a"] = merged["z_sig_str"] + merged["z_sub_att"] + merged["z_ctrl"]

    cols = ["fight_url", *rate_cols, "z_sig_str", "z_sub_att", "z_ctrl", "dominance_a"]
    # Expand to EVERY bout so finishes lacking round data still get the floor.
    base = fights[["fight_url", "fighter_a", "fighter_b", "winner", "method_class"]].copy()
    out = base.merge(merged[cols], on="fight_url", how="left")
    for c in rate_cols + ["z_sig_str", "z_sub_att", "z_ctrl", "dominance_a"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    # Decision round-win gap: add the affine-normalized (z-scored) judge scorecard
    # margin as a fourth dominance component, for decisions only. Normalized over
    # the decisions where a card exists, so it is commensurate with the per-minute
    # z-components above.
    margin = _scorecard_margin_a(fights, scorecards)
    if not margin.empty:
        out = out.merge(margin, on="fight_url", how="left")
        is_decision = out["method_class"].astype("string").str.startswith("Decision").fillna(False)
        gap = pd.to_numeric(out["scorecard_margin_a"], errors="coerce").where(is_decision)
        scored = gap.notna()
        if scored.any():
            out.loc[scored, "dominance_a"] = out.loc[scored, "dominance_a"] + _z(gap[scored])
        out = out.drop(columns=["scorecard_margin_a"], errors="ignore")

    # Finish floor: a KO/TKO or Submission win is a dominant result regardless of
    # accumulated stats. Floor the winner-perspective dominance (and keep a
    # higher raw value when the finish was also statistically one-sided).
    floor = float(DOMINANCE_FINISH_FLOOR_Z)
    if floor > 0:
        is_finish = out["method_class"].astype("string").isin(_FINISH_METHODS).fillna(False)
        win_a = out["winner"].eq(out["fighter_a"])
        win_b = out["winner"].eq(out["fighter_b"])
        out.loc[is_finish & win_a, "dominance_a"] = out.loc[is_finish & win_a, "dominance_a"].clip(lower=floor)
        out.loc[is_finish & win_b, "dominance_a"] = out.loc[is_finish & win_b, "dominance_a"].clip(upper=-floor)

    return out[cols].copy()


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
