"""The Current score: who is best now, counted the way All-time counts a career.

Owner decisions of 2026-10-14, after the published Current board ranked a
rating alone and put an unbeaten featherweight 2nd while the flyweight champion
with two defenses sat 19th:

* **Titles count, like the rest of it.** Current uses the All-time formula and
  its exact parts -- title, skill, résumé at 30% / 17.5% / 52.5%, each divided by
  the mean of its own top hundred and raised to the same power
  (:func:`ratings.legacy_resume.legacy_points`) -- but the title and résumé ledgers
  sum only wins inside the window. A win is still priced against everything known
  about the opponent (:func:`ratings.legacy_resume.contender_resume_ledger`,
  ``since``). Current reads the unadjusted ratings, not the era-adjusted ones
  All-time reads (:mod:`ratings.era`): every fighter on it is a contemporary, so an
  era shift would only move the 1,750 line by the reading for an unfinished season.
* **A UFC bout inside the window is required.** "Current" means current in the
  UFC: any UFC bout counts, of any outcome, from UFCStats or labelled as UFC by
  Sherdog. The window is the 18 months the board already used.
* **An unbeaten record's rating is capped at the best opponent it beat.** In a
  Bradley-Terry fit a win is evidence that the winner is above the loser, so
  wins bound a rating from below and only losses bound it from above. A fighter
  who has never lost rises with every win however weak the opponent, and the
  part of the rating above the strongest opponent ever beaten is carried by the
  absence of losses, not by any win. The skill part therefore reads the aged
  level capped at that opponent's rating going in. It needs no constant: the
  cap is the fighter's own best win. Measured on the 2026-10-14 snapshot, it
  binds hardest on exactly the records the owner named -- Movsar Evloev 152
  points above his best win, Lerone Murphy 142, Gabriel Bonfim 130, Sean Brady
  125 -- while a champion who beat the division (Justin Gaethje, Sean
  Strickland) sits below his best win and is untouched.

The rating itself is not changed. This is a board rule, argued from mechanism;
see "Rules that bind every change" in ``docs/DECISIONS.md``.
"""
from __future__ import annotations

import pandas as pd

from ratings.history import opponent_ratings
from ratings.boards import exposure_shrunk_level
from ratings.legacy_resume import (
    RESUME_QUALITY_SCALE, TITLE_QUALITY_SCALE, contender_resume_ledger, legacy_points,
    title_quality_ledger, ufc_debut_dates_from,
)
from ratings.divisions import division_labels
from ratings.opponent_quality import CONTENDER_LINE_MU

CURRENT_WINDOW_MONTHS = 18.0
DAYS_PER_MONTH = 30.4375
UFC_CORPORA = frozenset({"ufc", "pre_unified"})
UFC_ORG_LABELS = frozenset({"UFC", "UFC (pre-unified)", "Ultimate Fighting Championship (UFC)"})
AGED_LEVEL_COL = "mu_whr_age_activity_adjusted"

CURRENT_SCORE_COLUMNS = [
    "fighter",
    "current_title_score",
    "current_title_wins",
    "current_resume_score",
    "current_contender_wins",
    "current_best_win_mu",
    "current_skill_level",
    "current_skill_score",
    "current_score",
    "last_ufc_event_date",
    "months_since_ufc",
]


def _sides(fights: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(fights["event_date"], errors="coerce")
    return pd.concat(
        [
            pd.DataFrame({"fighter": fights[a], "opponent": fights[b], "event_date": dates,
                          "winner": fights.get("winner")})
            for a, b in (("fighter_a", "fighter_b"), ("fighter_b", "fighter_a"))
        ],
        ignore_index=True,
    ).dropna(subset=["fighter", "event_date"])


def best_win_ratings(fights: pd.DataFrame, history: pd.DataFrame) -> pd.Series:
    """Fighter -> rating, going in, of the strongest opponent they ever beat."""
    sides = _sides(fights)
    wins = sides[sides["winner"].eq(sides["fighter"])].dropna(subset=["opponent"])
    if wins.empty:
        return pd.Series(dtype="float64")
    h = history[["fighter", "event_date", "mu_whr"]].copy()
    h = h.assign(event_date=pd.to_datetime(h["event_date"], errors="coerce")).dropna()
    priced = opponent_ratings(wins.sort_values("event_date"), h.sort_values("event_date")).dropna(
        subset=["opponent_mu"]
    )
    return priced.groupby("fighter")["opponent_mu"].max()


def capped_level(level: pd.Series, best_win: pd.Series) -> pd.Series:
    """The level no higher than the best win; unknown where nothing was beaten."""
    best = pd.to_numeric(best_win.reindex(level.index), errors="coerce")
    return pd.to_numeric(level, errors="coerce").where(best.isna() | (level <= best), best).where(
        best.notna()
    )


def is_ufc_bout(fights: pd.DataFrame) -> pd.Series:
    corpus = fights.get("source_corpus", pd.Series(pd.NA, index=fights.index))
    org = fights.get("org", pd.Series(pd.NA, index=fights.index))
    return corpus.isin(UFC_CORPORA) | org.isin(UFC_ORG_LABELS)


def last_ufc_dates(recorded_fights: pd.DataFrame) -> pd.Series:
    """Fighter -> latest UFC bout of any outcome, rated or not."""
    ufc = recorded_fights[is_ufc_bout(recorded_fights)]
    if ufc.empty:
        return pd.Series(dtype="datetime64[ns]")
    return _sides(ufc).groupby("fighter")["event_date"].max()


def _title_win_counts(fights: pd.DataFrame, since: pd.Timestamp) -> pd.Series:
    idx = fights.index
    keep = fights.get("is_title_fight", pd.Series(False, index=idx)).fillna(False).astype(bool)
    for flag in ("is_excluded", "is_draw", "is_nc"):
        keep &= ~fights.get(flag, pd.Series(False, index=idx)).fillna(False).astype(bool)
    keep &= pd.to_datetime(fights["event_date"], errors="coerce") >= since
    return fights.loc[keep, "winner"].dropna().value_counts()


def current_score_rows(
    current: pd.DataFrame,
    *,
    rated_fights: pd.DataFrame,
    recorded_fights: pd.DataFrame,
    history: pd.DataFrame,
    reference_date: pd.Timestamp,
    window_months: float = CURRENT_WINDOW_MONTHS,
) -> pd.DataFrame:
    """One Current score row per fighter in ``current``.

    ``rated_fights`` prices the wins; ``recorded_fights`` also holds the no
    contests and unrated rows, and decides only the last UFC bout.
    ``reference_date`` is the snapshot's last rated bout, the same date the
    inactivity clock measures from.
    """
    reference = pd.Timestamp(reference_date)
    since = reference - pd.Timedelta(days=float(window_months) * DAYS_PER_MONTH)
    out = current[["fighter"]].copy()
    exposure = pd.to_numeric(
        current.get("public_legacy_exposure_factor", pd.Series(1.0, index=current.index)),
        errors="coerce",
    ).fillna(1.0)

    title = title_quality_ledger(
        rated_fights,
        history,
        divisions=division_labels(current),
        ufc_debut_dates=ufc_debut_dates_from(rated_fights),
        since=since,
    ).set_index("fighter")["public_legacy_title_quality"]
    resume = contender_resume_ledger(rated_fights, history, since=since).set_index("fighter")
    out["current_title_score"] = TITLE_QUALITY_SCALE * out["fighter"].map(title).fillna(0.0)
    out["current_title_wins"] = (
        out["fighter"].map(_title_win_counts(rated_fights, since)).fillna(0).astype(int)
    )
    out["current_resume_score"] = (
        RESUME_QUALITY_SCALE
        * out["fighter"].map(resume["public_legacy_resume_quality"]).fillna(0.0)
        * exposure.to_numpy()
    )
    out["current_contender_wins"] = (
        out["fighter"].map(resume["public_legacy_contender_wins"]).fillna(0).astype(int)
    )

    best = best_win_ratings(rated_fights, history)
    out["current_best_win_mu"] = out["fighter"].map(best)
    aged = pd.to_numeric(
        current.get(AGED_LEVEL_COL, pd.Series(pd.NA, index=current.index)), errors="coerce"
    )
    level = capped_level(
        pd.Series(aged.to_numpy(), index=out["fighter"]),
        pd.Series(out["current_best_win_mu"].to_numpy(), index=out["fighter"]),
    )
    shrunk = exposure_shrunk_level(
        level, pd.Series(exposure.to_numpy(), index=out["fighter"]), anchor=CONTENDER_LINE_MU
    )
    out["current_skill_level"] = shrunk.to_numpy()
    out["current_skill_score"] = (
        (out["current_skill_level"] - CONTENDER_LINE_MU).clip(lower=0.0).fillna(0.0)
    )

    out["current_score"] = sum(legacy_points(
        out["current_title_score"], out["current_skill_score"], out["current_resume_score"]))

    last = out["fighter"].map(last_ufc_dates(recorded_fights))
    out["last_ufc_event_date"] = pd.to_datetime(last)
    out["months_since_ufc"] = (
        ((reference - out["last_ufc_event_date"]).dt.days / DAYS_PER_MONTH).clip(lower=0.0).round(2)
    )
    return out[CURRENT_SCORE_COLUMNS]
