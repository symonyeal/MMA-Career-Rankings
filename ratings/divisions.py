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
_WOMENS_LIMIT_LB = (
    (105, "Women's Atomweight"),
    (115, "Women's Strawweight"),
    (125, "Women's Flyweight"),
    (135, "Women's Bantamweight"),
    (145, "Women's Featherweight"),
)
_WOMENS_BY_UNPREFIXED = {
    "Atomweight": "Women's Atomweight",
    "Strawweight": "Women's Strawweight",
    "Flyweight": "Women's Flyweight",
    "Bantamweight": "Women's Bantamweight",
    "Featherweight": "Women's Featherweight",
}
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
