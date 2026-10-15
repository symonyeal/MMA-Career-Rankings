"""The All-time score by weight class.

Let f be a fighter whose evidence items i -- title wins, contender wins, career years -- each
carry a class d(i), or none. The All-time score is linear in three ledger totals,

    S(f) = 1000 [a T(f)/n_T + (1 - a)(s K(f)/n_K + (1 - s) R(f)/n_R)],

    T = title scale * sum of title-win weights,
    K = exposure * sum over years of skill excess,
    R = resume scale * exposure * sum over years of min(sum of contender-win weights, cap),

with n_T, n_K, n_R the board-wide normalisers (:func:`ratings.legacy_resume.legacy_norm`). The
class score S_d(f) is the same expression over the items in class d with the same n's, so

    sum_d S_d(f) = S(f)    exactly; items with no class sit under d = None.

Two totals are not plain sums over items, so each needs a stated allocation rule:
    resume   a capped year is split pro rata, w -> w min(1, cap / sum of that year's w);
    career   a year's excess is split by the share of that year's bouts in each class.

Each year is still measured against the bar of the fighter's career class, as the published
score does; that is recorded as open in docs/DECISIONS.md, not changed here.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ratings.legacy_resume import (
    LEGACY_ACHIEVEMENT_WEIGHT, LEGACY_QUALITY_SKILL_SHARE, PUBLIC_LEGACY_DISPLAY_SCALE, RESUME_QUALITY_SCALE,
    RESUME_YEAR_CAP, TITLE_QUALITY_SCALE, _division_labels, contender_resume_rows, legacy_norm, title_quality_rows,
    ufc_debut_dates_from,
)
from ratings.performance_adjustment import normalize_division_label, womens_division_label
from ratings.symon_score import (
    DEFAULT_CAREER_REFERENCE, DEFAULT_DIVISION_REFERENCE, DEFAULT_HINGE_SPREAD_FRACTION, career_skill_years,
)

MEN_LIMIT_LB = (
    ("Strawweight", 115), ("Flyweight", 125), ("Bantamweight", 135), ("Featherweight", 145),
    ("Lightweight", 155), ("Welterweight", 170), ("Middleweight", 185), ("Light Heavyweight", 205),
    ("Heavyweight", 265),
)
MEN = {c for c, _ in MEN_LIMIT_LB}
_LB = re.compile(r"(\d{2,3})\s*lb", re.IGNORECASE)
CLASS_COLUMNS = ["fighter", "division", "title", "skill", "resume", "score"]


def weight_class(division: object, gender: object) -> str | None:
    """The class a bout counts toward, or None.

    Women's billings fold onto one women's class (:func:`womens_division_label`); a men's
    catchweight goes to the lightest class whose limit holds it; open weight and an unknown
    billing count toward no class.
    """
    if gender == "F":
        d = womens_division_label(division)
        return None if d in (None, "Women's Openweight") else d
    d = normalize_division_label(division)
    if d in MEN:
        return d
    m = _LB.search(division) if isinstance(division, str) else None
    return next((c for c, lb in MEN_LIMIT_LB if int(m.group(1)) <= lb), None) if m else None


def pro_rata(rows: pd.DataFrame, cap: float) -> pd.Series:
    """w min(1, cap / W), W the (fighter, _year) total: each year's allocations sum to min(W, cap)."""
    W = rows.groupby(["fighter", "_year"])["weight"].transform("sum")
    return rows["weight"] * np.minimum(1.0, cap / W)


def class_ledger(
    current: pd.DataFrame,
    appearances: pd.DataFrame,
    *,
    source_fights: pd.DataFrame,
    history: pd.DataFrame,
    reference: str | float = DEFAULT_CAREER_REFERENCE,
    year_cap: float = RESUME_YEAR_CAP,
) -> pd.DataFrame:
    """(fighter, division, title, skill, resume) in ledger units: the three totals split by class.

    The inputs are those of :func:`ratings.legacy_resume.public_legacy_score_rows`, so the
    per-fighter sums over division reproduce its title quality, career skill mass and resume quality.
    """
    gender = current.set_index("fighter")["gender"]
    a = appearances[["fight_url", "fighter", "event_date", "division"]].copy()
    a["division"] = [weight_class(d, gender.get(f)) for d, f in zip(a["division"], a["fighter"])]
    a["year"] = pd.to_datetime(a["event_date"]).dt.year
    bout = a.drop_duplicates(["fight_url", "fighter"]).set_index(["fight_url", "fighter"])["division"]
    billed = source_fights.drop_duplicates("fight_url").set_index("fight_url")["weight_class"]

    def of(x):  # the appearance's class, else the class the bout itself was billed at
        d = bout.reindex(pd.MultiIndex.from_arrays([x["fight_url"], x["fighter"]])).to_numpy()
        return [c if isinstance(c, str) else weight_class(billed.get(u), gender.get(f))
                for c, u, f in zip(d, x["fight_url"], x["fighter"])]

    labels = _division_labels(current)
    T = title_quality_rows(source_fights, history, reference=reference, divisions=labels,
                           ufc_debut_dates=ufc_debut_dates_from(source_fights))
    T = T.assign(division=of(T), title=T["weight"])
    R = contender_resume_rows(source_fights, history)
    R = R.assign(division=of(R), resume=pro_rata(R, year_cap))
    Y = career_skill_years(history, reference=reference, divisions=labels,
                           division_reference=DEFAULT_DIVISION_REFERENCE,
                           hinge_spread_fraction=DEFAULT_HINGE_SPREAD_FRACTION)
    share = (a.groupby(["fighter", "year"])["division"].value_counts(normalize=True, dropna=False)
             .rename("share").reset_index())
    K = Y.merge(share, on=["fighter", "year"], how="left")
    K = K.assign(skill=K["excess"] * K["share"].fillna(1.0))  # a year with no bout row keeps its excess unclassed

    parts = [T[["fighter", "division", "title"]], K[["fighter", "division", "skill"]],
             R[["fighter", "division", "resume"]]]
    out = pd.concat(parts, ignore_index=True).groupby(["fighter", "division"], dropna=False, sort=False)
    return out[["title", "skill", "resume"]].sum().reset_index()


def class_scores(current: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    """(fighter, division, title, skill, resume, score) in All-time points; sum over division = score.

    ``current`` carries the published per-fighter columns, which fix the exposure factor and the
    three normalisers.
    """
    a, s, k = LEGACY_ACHIEVEMENT_WEIGHT, LEGACY_QUALITY_SKILL_SHARE, PUBLIC_LEGACY_DISPLAY_SCALE
    n = {c: legacy_norm(current[f"public_legacy_{c}_score"]) for c in ("title", "skill", "resume")}
    x = ledger.merge(current[["fighter", "public_legacy_exposure_factor"]], on="fighter", how="left")
    e = x["public_legacy_exposure_factor"].fillna(1.0)
    x["title"] = k * a * TITLE_QUALITY_SCALE * x["title"] / n["title"]
    x["skill"] = k * (1 - a) * s * e * x["skill"] / n["skill"]
    x["resume"] = k * (1 - a) * (1 - s) * RESUME_QUALITY_SCALE * e * x["resume"] / n["resume"]
    x["score"] = x["title"] + x["skill"] + x["resume"]
    return x[CLASS_COLUMNS]


def class_board(scores: pd.DataFrame, current: pd.DataFrame, eligible: pd.Series) -> pd.DataFrame:
    """Rank each class among the All-time-eligible fighters who earned credit in it.

    Adds ``gender``, ``rank`` (within gender and class) and ``share`` (the class score over the
    fighter's All-time score).
    """
    b = scores[scores["division"].notna() & scores["fighter"].isin(set(eligible)) & (scores["score"] > 0)].copy()
    c = current.set_index("fighter")
    b["gender"] = b["fighter"].map(c["gender"])
    b["share"] = b["score"] / b["fighter"].map(c["public_legacy_score"])
    b["rank"] = b.groupby(["gender", "division"])["score"].rank(ascending=False, method="first").astype(int)
    return b.sort_values(["gender", "division", "rank"]).reset_index(drop=True)
