"""Stage the UFC pre-unified era (UFC 1 to UFC 27) as its own corpus.

``loaders/ufcstats_loader`` drops every UFC bout before UFC 28 (2000-11-17) into
``_excluded_bouts.csv``. Its upstream table starts at UFC 2, so the official
eight-bout UFC 1 card is committed separately (``data/external/ufc``) and joined
here. The bouts are rated like any other (decision of 2026-08-24, recorded in
docs/DECISIONS.md); the ``rules_era`` label is kept on the rows for audit.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from project_helpers import bout_fingerprint

PRE_UNIFIED_REASON = "pre_unified_rules"
SNAPSHOT_ARTIFACT = "pre_unified_fights.parquet"
EXCLUDED_CSV = "_excluded_bouts.csv"
# P1 : committed official UFC 1 backfill
P1 = Path(__file__).resolve().parent.parent / "data" / "external" / "ufc" / "ufc1_fights.csv"


def load_pre_unified_fights(snapshot_dir: Path) -> pd.DataFrame:
    """The dropped UFC 1-27 bouts, back in the canonical fight-table shape.

    They are read from ``_excluded_bouts.csv``, which is where the loader puts
    them, so no re-scrape is needed and the rows are the loader's own parse --
    not a second, differently-parsed copy from a scraped fighter page.
    """
    snapshot_dir = Path(snapshot_dir)
    path = snapshot_dir / EXCLUDED_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"scope 'pre_unified' requested but {path} does not exist, so the "
            "pre-unified bouts cannot be recovered. Rebuild the snapshot."
        )
    excluded = pd.read_csv(path)
    pre = excluded[excluded["exclusion_reason"].astype(str).eq(PRE_UNIFIED_REASON)].copy()
    if pre.empty:
        raise ValueError(
            f"scope 'pre_unified' requested but {path} holds no "
            f"{PRE_UNIFIED_REASON!r} rows, so the run would silently rate a partial era"
        )
    if not P1.exists():
        raise FileNotFoundError(f"UFC 1 backfill is missing: {P1}")
    u1 = pd.read_csv(P1)
    if len(u1) != 8 or u1["event_name"].nunique() != 1:
        raise ValueError(f"UFC 1 backfill must hold the complete eight-bout event: {P1}")
    held = set(bout_fingerprint(pre))
    u1 = u1[~bout_fingerprint(u1).isin(held)]
    pre = pd.concat([pre, u1], ignore_index=True, sort=False)
    pre["event_date"] = pd.to_datetime(pre["event_date"], errors="coerce")
    # They were excluded for being pre-unified and for nothing else. A bout in
    # here that ALSO ended in a no-contest or an overturned result stays
    # excluded -- the era decision does not re-admit an unrateable result.
    for col in ("is_draw", "is_nc"):
        if col in pre.columns:
            pre[col] = pre[col].fillna(False).astype(bool)
    unrateable = pre.get("method_class", pd.Series("", index=pre.index)).astype(str).isin(
        {"Overturned", "Could Not Continue"}) | pre.get("is_nc", False)
    pre["is_excluded"] = unrateable
    pre["exclusion_reason"] = pre["exclusion_reason"].where(unrateable, None)
    pre["source"] = "ufc"
    pre["org"] = "UFC (pre-unified)"
    pre["org_weight"] = 1.0
    pre["rules_era"] = "ufc_pre_unified"
    return pre.dropna(subset=["event_date", "fighter_a", "fighter_b"]).reset_index(drop=True)


def stage_pre_unified_scope(snapshot_dir: Path) -> dict:
    """Write ``pre_unified_fights.parquet`` beside the snapshot."""
    snapshot_dir = Path(snapshot_dir)
    pre = load_pre_unified_fights(snapshot_dir)
    pre.to_parquet(snapshot_dir / SNAPSHOT_ARTIFACT, index=False)
    fighters = set(pre["fighter_a"]) | set(pre["fighter_b"])
    canonical = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    unified_fighters = set(canonical["fighter_a"]) | set(canonical["fighter_b"])
    return {
        "bouts": len(pre),
        "rateable_bouts": int((~pre["is_excluded"]).sum()),
        "events": int(pre["event_name"].nunique()),
        "fighters": len(fighters),
        # The boundary crossers: a rules-era level shift would be identified
        # only through these fighters, which is why none is attempted.
        "fighters_also_in_unified_era": len(fighters & unified_fighters),
        "date_span": [str(pre["event_date"].min().date()), str(pre["event_date"].max().date())],
        "artifact": str(snapshot_dir / SNAPSHOT_ARTIFACT),
    }
