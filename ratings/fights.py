"""Prepare scoped rating inputs and feed event-grained filters.

Production may discard staged organisation weights before preparation; research
keeps them. Neither path changes scope or deduplication policy here.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from loaders.combined_fights import load_combined_fights
from loaders.integrity_flags import INTEGRITY_COLUMNS, build_integrity_flags
from ratings.constants import METHOD_SCORES
from ratings.glicko2_engine import RatingEngine
from ratings.rules_era import RULES_ERA_WEIGHT, label_rules_era, rules_era_factor
from ratings.scope import UFC_ONLY
from project_helpers import group_bounds


def _ensure_integrity_columns(fights: pd.DataFrame) -> pd.DataFrame:
    out = fights.copy()
    for col in INTEGRITY_COLUMNS:
        if col == "fight_url":
            continue
        if col not in out.columns:
            out[col] = False if col in {"ped_confirmed", "is_dq", "missed_weight"} else None
    for col in ("ped_confirmed", "is_dq", "missed_weight"):
        out[col] = out[col].fillna(False).astype(bool)
    return out


def iter_events(fights: pd.DataFrame, columns: list[str]):
    """Yield ``(event_date, event_name, bouts)`` per event from column arrays.

    A ``groupby(...).to_dict("records")`` per event costs more than the Glicko
    arithmetic it feeds once the fight table carries tens of thousands of
    events, so the frame is converted to arrays once and sliced.
    """
    f = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    arrays = {c: f[c].to_numpy() for c in columns}
    dates = f["event_date"].to_numpy()
    names = f["event_name"].to_numpy()
    for lo, hi in zip(*group_bounds(f["event_date"], f["event_name"])):
        bouts = [{c: arrays[c][k] for c in columns} for k in range(lo, hi)]
        yield pd.Timestamp(dates[lo]), names[lo], bouts


def canonical_engine(fights: pd.DataFrame, tau: float) -> RatingEngine:
    engine = RatingEngine(tau=tau)
    columns = ["fighter_a", "fighter_b", "winner", "is_draw", "method_score_winner"]
    for event_date, event_name, bouts in iter_events(fights, columns):
        engine.process_event(event_date, event_name, bouts)
    return engine


def rated_rows(fights: pd.DataFrame) -> pd.DataFrame:
    if "is_excluded" in fights.columns:
        return fights[~fights["is_excluded"].fillna(False).astype(bool)].copy()
    return fights


def attach_bout_weights(
    fights: pd.DataFrame,
    *,
    rules_era_weight: float = RULES_ERA_WEIGHT,
) -> pd.DataFrame:
    """Set the one shared likelihood weight each bout contributes.

    Two factors, and both are the same number on both sides -- WHR needs a
    single bout likelihood, so a side-specific weight is not admissible here.

    ``org_weight``
        1.0 in production. The column is read rather than hard-coded so the
        research sweep can vary it without a second code path; see the
        org-weight note in :func:`ratings.rate_snapshot.run` for why production never does.
    ``rules_era``
        how far a UFC bout fought before the unified rules is allowed to move a
        rating. Defaults to 1.0 -- full admission -- and is a measured quantity,
        not an asserted one. See :mod:`ratings.rules_era`.
    """
    out = fights.copy()
    ow = pd.to_numeric(out.get("org_weight", 1.0), errors="coerce")
    ow = ow.fillna(1.0) if hasattr(ow, "fillna") else pd.Series(1.0, index=out.index)
    weight = ow * rules_era_factor(out, weight=rules_era_weight)
    out["weight_a"] = weight
    out["weight_b"] = weight
    return out


def prepare_fights(fights: pd.DataFrame, *, mdabbert_csv: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sort method-scored bouts, replace stale integrity flags, and return their audit."""
    fights = fights.copy()
    fights["rules_era"] = label_rules_era(fights)
    fights["event_date"] = pd.to_datetime(fights["event_date"])
    if "method_class" in fights.columns:
        recalculated = fights["method_class"].map(METHOD_SCORES)
        fights["method_score_winner"] = recalculated.combine_first(
            pd.to_numeric(fights.get("method_score_winner"), errors="coerce")
        )
    fights = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    integrity = build_integrity_flags(fights, mdabbert_csv=mdabbert_csv)
    fights = fights.drop(
        columns=[c for c in INTEGRITY_COLUMNS if c != "fight_url" and c in fights.columns], errors="ignore",
    ).merge(integrity, on="fight_url", how="left")
    return _ensure_integrity_columns(fights), integrity


def load_fight_table(snapshot_dir: Path, *, scope: str = UFC_ONLY) -> pd.DataFrame:
    """Read one named scope, rejecting unavailable corpora, and retain rated bouts."""
    fights, _ = load_combined_fights(Path(snapshot_dir), scope=scope, label="prequential")
    fights, _ = prepare_fights(fights)
    if "is_excluded" in fights.columns:
        fights = fights[~fights["is_excluded"]].copy()
    return fights.reset_index(drop=True)


def resume_fights(snapshot_dir: Path, scope: str) -> pd.DataFrame:
    fights, _ = load_combined_fights(snapshot_dir, scope=scope, label="resume")
    return rated_rows(fights)
