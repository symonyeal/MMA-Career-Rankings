"""The UFC pre-unified era: admitted, labelled, and priced by measurement.

``loaders/ufcstats_loader`` drops every UFC bout before UFC 28 (Tito Ortiz vs
Yuki Kondo, 2000-11-17) -- 253 bouts across 30 events, 1993-11-12 to
2000-09-22. They are scraped and parsed, then written to ``_excluded_bouts.csv``
with ``exclusion_reason = "pre_unified_rules"`` and never rated.

That is a defensible rule and nobody costed what it does to the board. It means
the engine structurally cannot rank the 1993-2000 generation, and it is most of
why Randy Couture scores zero: his rated record starts 2000-11-17, so roughly a
third of his career is outside the window by design. The board then printed him
at a rank anyway, which is the part that was not defensible.

The decision taken (2026-08-24) is to admit those bouts to the *rating* and
carry an explicit rules-era indicator, so the difference between the two rule
sets is estimated rather than assumed.

What the indicator can and cannot do
------------------------------------
``rules_era`` labels a bout ``ufc_pre_unified``, ``unified``, or ``non_ufc``.
Only the first carries a term. That is deliberate and it is a limitation worth
stating plainly rather than hiding: PRIDE never fought under unified rules
either, but its rules differed *per promotion* and this project has decided not
to assert promotion-level parameters -- promotion strength is an output of the
joint fit. A date-keyed rules indicator would quietly become an organisation
weight wearing a different label.

``RULES_ERA_WEIGHT`` scales the likelihood precision of a pre-unified bout: how
far a result under no weight classes, no time limits and no judges is allowed
to move a rating, relative to a modern one. It is a **measured** quantity, not
an asserted one -- see :mod:`build_rules_era_sweep`. It defaults to 1.0, full
admission, because that is what the evidence supports until a grid says
otherwise, and because a default below 1.0 would be exactly the kind of
unestimated constant this module exists to avoid.

Note what a level shift would *not* buy: a common additive era term cancels from
every within-era Bradley--Terry matchup, so it is identified only through the
fighters who crossed the boundary. There are few of them. The weight
formulation is at least measurable on held-out bouts; a level shift is not.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# UFC 28, the first event under unified rules. Bouts strictly before are the
# pre-unified era. Kept here as well as in the loader so the rating layer does
# not have to import a scraper to know where the boundary is.
UFC_28_DATE = pd.Timestamp("2000-11-17")

PRE_UNIFIED_REASON = "pre_unified_rules"
SNAPSHOT_ARTIFACT = "pre_unified_fights.parquet"
EXCLUDED_CSV = "_excluded_bouts.csv"

RULES_ERA_UNIFIED = "unified"
RULES_ERA_PRE = "ufc_pre_unified"
RULES_ERA_NON_UFC = "non_ufc"

# Likelihood-precision multiplier for a pre-unified UFC bout. 1.0 means "this
# result counts like any other". Change it only from a measured grid.
RULES_ERA_WEIGHT: float = 1.0


def label_rules_era(fights: pd.DataFrame) -> pd.Series:
    """Per-bout rules era, from the source and the date.

    A bout from a non-UFC corpus is ``non_ufc`` whatever its date: this project
    does not assert what rules a given promotion used in a given year, and
    guessing from the calendar would be an organisation weight by another name.
    """
    index = fights.index
    if fights.empty:
        return pd.Series(dtype=object, index=index)
    source = fights.get("source", pd.Series("ufc", index=index)).fillna("ufc").astype(str)
    dates = pd.to_datetime(fights["event_date"], errors="coerce")
    era = pd.Series(RULES_ERA_UNIFIED, index=index, dtype=object)
    era[source.ne("ufc")] = RULES_ERA_NON_UFC
    era[source.eq("ufc") & dates.lt(UFC_28_DATE)] = RULES_ERA_PRE
    return era


def rules_era_factor(fights: pd.DataFrame, *, weight: float = RULES_ERA_WEIGHT) -> pd.Series:
    """The per-bout likelihood multiplier the rules-era term implies."""
    if not 0.0 < float(weight) <= 1.0:
        raise ValueError("a rules-era weight must lie in (0, 1]")
    era = fights.get("rules_era")
    if era is None:
        era = label_rules_era(fights)
    return pd.Series(
        pd.Series(era, index=fights.index).eq(RULES_ERA_PRE).map(
            {True: float(weight), False: 1.0}),
        index=fights.index, dtype=float,
    )


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
            f"{PRE_UNIFIED_REASON!r} rows, so the run would silently rate the "
            "unified-era table and report it as a whole-history fit."
        )
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
    pre["rules_era"] = RULES_ERA_PRE
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
        "bouts": int(len(pre)),
        "rateable_bouts": int((~pre["is_excluded"]).sum()),
        "events": int(pre["event_name"].nunique()),
        "fighters": int(len(fighters)),
        # The boundary crossers. A rules-era level shift is identified only
        # through these fighters, which is why it is not attempted.
        "fighters_also_in_unified_era": int(len(fighters & unified_fighters)),
        "date_span": [str(pre["event_date"].min().date()), str(pre["event_date"].max().date())],
        "artifact": str(snapshot_dir / SNAPSHOT_ARTIFACT),
    }
