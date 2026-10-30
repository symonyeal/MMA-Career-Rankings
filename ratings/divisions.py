"""Canonical division labels and the career pools used by every score."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd


DIVISION_LABELS = (
    "Women's Strawweight",
    "Women's Flyweight",
    "Women's Bantamweight",
    "Women's Featherweight",
    "Light Heavyweight",
    "Heavyweight",
    "Middleweight",
    "Welterweight",
    "Lightweight",
    "Featherweight",
    "Bantamweight",
    "Flyweight",
    "Catch Weight",
    "Open Weight",
)

DIVISION_WEIGHT_LIMIT_LB = {
    "Women's Strawweight": 115,
    "Women's Flyweight": 125,
    "Women's Bantamweight": 135,
    "Women's Featherweight": 145,
    "Flyweight": 125,
    "Bantamweight": 135,
    "Featherweight": 145,
    "Lightweight": 155,
    "Welterweight": 170,
    "Middleweight": 185,
    "Light Heavyweight": 205,
    "Heavyweight": 265,
}


def normalize_division_label(weight_class: object) -> str | None:
    """Normalize UFCStats weight-class text to a stable division label."""
    if not isinstance(weight_class, str):
        return None
    text = " ".join(weight_class.split())
    cleaned = (
        text.replace("UFC ", "")
        .replace("Interim ", "")
        .replace(" Title Bout", "")
        .replace(" Bout", "")
        .strip()
    )
    for label in DIVISION_LABELS:
        if label.lower() in cleaned.lower():
            return label
    return cleaned or None


# One women's division is billed three ways in this corpus -- "Women's
# Flyweight" from UFCStats, a bare "Flyweight" from the Sherdog majors rows, and
# "125lb Catchweight" -- and each spelling becomes its own contender pool.
# Measured on the 2026-08-13 snapshot, the pool spelled "Flyweight" carried a
# contender line 91 rating points BELOW the pool spelled "Women's Flyweight" for
# the same division and the same eleven years, so a woman's career score
# depended on which source billed her bouts. Folding the spellings is the
# division half of that repair; the gender half is in
# ``rate_snapshot._attach_recent_division_gender``.
MEN_LIMIT_LB = (("Strawweight", 115),) + tuple(
    (label, limit) for label, limit in DIVISION_WEIGHT_LIMIT_LB.items() if not label.startswith("Women's")
)
_WOMENS_LIMIT_LB = ((105, "Women's Atomweight"),) + tuple(
    (limit, label) for label, limit in DIVISION_WEIGHT_LIMIT_LB.items() if label.startswith("Women's")
)
_WOMENS_BY_UNPREFIXED = {label.removeprefix("Women's "): label for _, label in _WOMENS_LIMIT_LB}
_CATCHWEIGHT_LB = re.compile(r"(\d{2,3})\s*lb", re.IGNORECASE)


def womens_division_label(division: object) -> str | None:
    """Fold any billing a woman's bout carries onto one women's division.

    Returns ``None`` for a label this cannot place, so the caller can keep its
    own fallback rather than inventing a pool.
    """
    if not isinstance(division, str) or not division.strip():
        return None
    text = " ".join(division.split())
    if text.startswith("Women's"):
        return text
    if text in _WOMENS_BY_UNPREFIXED:
        return _WOMENS_BY_UNPREFIXED[text]
    match = _CATCHWEIGHT_LB.search(text)
    if match:
        pounds = int(match.group(1))
        for limit, label in _WOMENS_LIMIT_LB:
            if pounds <= limit:
                return label
        return "Women's Openweight"
    # RIZIN bills its women's openweight bouts as Heavyweight and Light
    # Heavyweight; those are eight fighters on this snapshot, not a men's pool.
    if text in {"Heavyweight", "Light Heavyweight", "Middleweight", "Welterweight",
                "Lightweight", "Open Weight", "Openweight", "Catch Weight", "Catchweight"}:
        return "Women's Openweight"
    return None


def division_labels(current: pd.DataFrame) -> pd.Series | None:
    """Fighter -> division label, women's classes kept separate from men's.

    A woman's ``career_division`` is folded onto one canonical women's division
    first. Without that fold the same division splits into as many pools as the
    corpus has spellings for it -- "Women's Flyweight" from UFCStats and a bare
    "Flyweight" from the Sherdog majors rows -- and each pool strikes its own
    contender line. Measured on 2026-08-13 those two lines sat 91 rating points
    apart over the same eleven years, so which one a career was scored against
    was decided by its source, not by its division.

    The ``"W " + div`` prefix is kept as the fallback for a label the fold
    cannot place, so a fighter is never silently pooled with the men.
    """
    if current is None or "career_division" not in current.columns:
        return None
    div = current["career_division"].astype(str)
    gender = current.get("gender", pd.Series("", index=current.index)).astype(str)
    female = gender.str.upper().str.startswith("F")
    folded = div.map(womens_division_label)
    return pd.Series(
        np.where(female, folded.fillna("W " + div), div), index=current["fighter"]
    ).groupby(level=0).first()


DIV_SHORT: dict[str, str] = {
    "Strawweight":          "STW",
    "Flyweight":            "FLY",
    "Bantamweight":         "BW",
    "Featherweight":        "FW",
    "Lightweight":          "LW",
    "Welterweight":         "WW",
    "Middleweight":         "MW",
    "Light Heavyweight":    "LHW",
    "Heavyweight":          "HW",
    "Women's Strawweight":  "W.STW",
    "Women's Flyweight":    "W.FLY",
    "Women's Bantamweight": "W.BW",
    "Women's Featherweight":"W.FW",
    "Catch Weight":         "CW",
    "Open Weight":          "OW",
}
DISPLAY_DIVISIONS = list(DIV_SHORT)


def display_division_label(weight_class: str | None) -> str | None:
    """Strip 'UFC ', ' Title Bout', ' Bout' to land at clean division names."""
    if not isinstance(weight_class, str):
        return None
    w = weight_class.replace("UFC ", "").replace(" Title Bout", "").replace(" Bout", "").strip()
    # Match more specific labels first so "Women's Flyweight" is not collapsed
    # to the generic "Flyweight" bucket.
    for d in sorted(DISPLAY_DIVISIONS, key=len, reverse=True):
        if d.lower() in w.lower():
            return d
    return w  # Catch-all (Catch Weight, Open Weight, etc.)


def division_column(fighters: pd.Series, lookup: object, column: str) -> list[str]:
    """Each fighter's division, blank where the corpus never weighed them."""
    if column not in getattr(lookup, "columns", []):
        return ["" for _ in fighters]
    d = fighters.map(lookup[column])
    g = fighters.map(lookup["gender"]) if "gender" in getattr(lookup, "columns", []) else ""
    f = pd.Series(g, index=fighters.index).astype(str).str.upper().str.startswith("F")
    d.loc[f] = d.loc[f].map(womens_division_label).fillna("W " + d.loc[f].astype(str))
    return ["" if pd.isna(value) else str(value) for value in d]
