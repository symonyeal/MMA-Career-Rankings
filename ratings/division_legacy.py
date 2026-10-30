"""The All-time score by weight class, counted over UFC bouts.

Let f be a fighter whose evidence items i -- title wins, contender wins, career years -- each
carry a class d(i), or none. An item has a class only if its bout is a UFC bout
(:func:`ratings.current_score.is_ufc_bout`, the predicate Current uses); every other item, like
open weight, counts toward the All-time score and toward no class. The All-time score is a sum of
three parts, each a power of a ledger total,

    S(f) = 1000 [a (T/n_T)^p + (1 - a)(s (K/n_K)^p + (1 - s)(R/n_R)^p)],

    T = title scale * sum of title-win weights,
    K = exposure * sum over years of skill excess,
    R = resume scale * exposure * sum over years of min(sum of contender-win weights, cap),

with n_T, n_K, n_R the board-wide normalisers (:func:`ratings.legacy_resume.legacy_norm`) and p
:data:`ratings.legacy_resume.LEGACY_PART_POWER`. The class score S_d(f) splits each part's points
by the share of that part's total earned in class d: with X in {T, K, R} and X_d its items in d,

    S_d(f) = sum_X 1000 w_X (X/n_X)^p X_d/X,    so    sum_d S_d(f) = S(f)    exactly;

items with no class, including every non-UFC item, sit under d = None. At p = 1 this is the same
expression over the items in d, as it was before 2026-10-16.

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
    RESUME_QUALITY_SCALE, RESUME_YEAR_CAP, TITLE_QUALITY_SCALE, contender_resume_rows,
    legacy_points, title_quality_rows, ufc_debut_dates_from,
)
from ratings.divisions import MEN_LIMIT_LB, division_labels
from ratings.current_score import is_ufc_bout
from ratings.divisions import normalize_division_label
from ratings.divisions import womens_division_label
from ratings.symon_score import (
    DEFAULT_CAREER_REFERENCE, DEFAULT_DIVISION_REFERENCE, DEFAULT_HINGE_SPREAD_FRACTION, career_skill_years,
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


def _lookup(s: pd.Series):
    """``s.get`` as a dict lookup: a ``Series.get`` per bout costs ~25 microseconds, a dict ~0.1."""
    return s.get if not s.index.is_unique or s.index.hasnans else s.to_dict().get


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
    gender = _lookup(current.set_index("fighter")["gender"])
    # .tolist(), not iteration: Arrow-backed string columns iterate ~10x slower
    ufc = set(source_fights.loc[is_ufc_bout(source_fights), "fight_url"].tolist())
    a = appearances[["fight_url", "fighter", "event_date", "division"]].copy()
    urls, fighters = a["fight_url"].tolist(), a["fighter"].tolist()
    a["division"] = classes = [weight_class(d, gender(f)) if u in ufc else None
                               for d, f, u in zip(a["division"].tolist(), fighters, urls)]
    a["year"] = pd.to_datetime(a["event_date"]).dt.year
    bout: dict[tuple, str | None] = {}  # first appearance of each (fight_url, fighter)
    for key, c in zip(zip(urls, fighters), classes):
        bout.setdefault(key, c)
    billed = _lookup(source_fights.drop_duplicates("fight_url").set_index("fight_url")["weight_class"])

    def of(x):  # a UFC bout's class: the appearance's, else the one the bout was billed at
        us, fs = x["fight_url"].tolist(), x["fighter"].tolist()
        return [None if u not in ufc else c if isinstance(c := bout.get((u, f)), str)
                else weight_class(billed(u), gender(f)) for u, f in zip(us, fs)]

    labels = division_labels(current)
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

    ``current`` carries the published per-fighter columns, which fix the exposure factor, the
    three part totals X and their normalisers.
    """
    c = current.drop_duplicates("fighter").set_index("fighter")
    e = c["public_legacy_exposure_factor"].fillna(1.0)
    X = {i: c[f"public_legacy_{i}_score"].fillna(0.0) for i in ("title", "skill", "resume")}
    unit = {"title": TITLE_QUALITY_SCALE, "skill": e, "resume": RESUME_QUALITY_SCALE * e}  # ledger -> score units
    x = ledger.copy()
    for (i, Xi), P in zip(X.items(), legacy_points(*X.values())):
        x[i] = x[i] * x["fighter"].map((P / Xi).where(Xi > 0, 0.0) * unit[i]).fillna(0.0)  # 1000 w (X/n)^p / X
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
