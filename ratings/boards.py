"""The boards only this engine can ship.

Phase G of the 2026-08-18 differentiator audit. Everything here answers a
question a win-probability forecast cannot score, which is precisely why these
survive while the mechanisms that claimed an accuracy benefit did not:

* :func:`integrity_ledger` / :func:`integrity_discounted_board` — a ranking that
  refuses to credit a juiced win, with a per-fighter account of exactly which
  bouts were discounted, why, and what it cost them. "Should this result count"
  is a judgement, not a prediction, so it is labelled as one.
* :func:`completeness_gated_board` — a ranking that says "insufficient observed
  history to rank" instead of seating a fighter at a default rating. Refusing to
  answer is a product feature; a default seat is a silent lie.

These read finished snapshot artifacts and emit tables. They do not rate, and
they do not touch the notebook.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import (
    INTEGRITY_DQ_WIN_FACTOR,
    INTEGRITY_MISSED_WEIGHT_WIN_FACTOR,
    INTEGRITY_PED_FACTOR,
)

LEDGER_COLUMNS = (
    "fighter",
    "fight_url",
    "event_date",
    "event_name",
    "opponent",
    "reason",
    "detail",
    "integrity_weight",
    "discount_pct",
)

_REASON_LABEL = {
    "ped": "PED-confirmed win",
    "dq": "win by disqualification",
    "missed_weight": "won after missing weight",
}
_REASON_FACTOR = {
    "ped": INTEGRITY_PED_FACTOR,
    "dq": INTEGRITY_DQ_WIN_FACTOR,
    "missed_weight": INTEGRITY_MISSED_WEIGHT_WIN_FACTOR,
}


def integrity_ledger(
    integrity_appearances: pd.DataFrame,
    fights: pd.DataFrame,
) -> pd.DataFrame:
    """One row per discounted appearance: who, which bout, why, and how much.

    A board that quietly downweights results is not auditable. This is the
    receipt — every bout whose update was damped, the flag that damped it, and
    the resulting weight. A fighter with no flagged results has no rows.
    """
    if integrity_appearances is None or integrity_appearances.empty:
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))

    app = integrity_appearances.copy()
    factor_cols = {
        "ped": "integrity_factor_ped",
        "dq": "integrity_factor_dq",
        "missed_weight": "integrity_factor_missed_weight",
    }
    meta_cols = [
        "fight_url", "event_date", "event_name", "fighter_a", "fighter_b", "winner",
        "ped_confirmation_detail", "missed_weight_source", "weight_class",
    ]
    meta = fights[[c for c in meta_cols if c in fights.columns]].drop_duplicates("fight_url")
    app = app.merge(meta, on="fight_url", how="left")
    if {"fighter_a", "fighter_b"} <= set(app.columns):
        app["opponent"] = np.where(
            app["fighter"] == app["fighter_a"], app["fighter_b"], app["fighter_a"])
    else:
        app["opponent"] = pd.NA

    rows = []
    for reason, col in factor_cols.items():
        if col not in app.columns:
            continue
        flagged = app[pd.to_numeric(app[col], errors="coerce").fillna(1.0) < 1.0].copy()
        if flagged.empty:
            continue
        detail = pd.Series(_REASON_LABEL[reason], index=flagged.index, dtype=object)
        if reason == "ped" and "ped_confirmation_detail" in flagged.columns:
            extra = flagged["ped_confirmation_detail"].fillna("")
            detail = detail.str.cat(extra.where(extra.eq(""), " — " + extra), na_rep="")
        if reason == "missed_weight" and "weight_class" in flagged.columns:
            extra = flagged["weight_class"].fillna("")
            detail = detail.str.cat(extra.where(extra.eq(""), " (" + extra + ")"), na_rep="")
        flagged["reason"] = reason
        flagged["detail"] = detail
        flagged["discount_pct"] = 100.0 * (1.0 - float(_REASON_FACTOR[reason]))
        rows.append(flagged)

    if not rows:
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))
    out = pd.concat(rows, ignore_index=True, sort=False)
    for col in LEDGER_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[list(LEDGER_COLUMNS)].sort_values(
        ["fighter", "event_date", "reason"]).reset_index(drop=True)


# Mu points removed per discounted result, at the sleeve's own relative
# severity: PED -10%, missed weight -6%, DQ -4% of INTEGRITY_PENALTY_SCALE.
# This is a stated judgement, not an estimate — no prediction can score
# "should this win count", so no fit produced this number.
INTEGRITY_PENALTY_SCALE: float = 250.0


def integrity_discounted_board(
    current: pd.DataFrame,
    ledger: pd.DataFrame,
    *,
    rating_col: str = "sustained_peak_headline_mu_whr",
    min_rating_periods: int = 0,
    penalty_scale: float = INTEGRITY_PENALTY_SCALE,
    top: int | None = None,
) -> pd.DataFrame:
    """Board that debits a fighter for their own tainted wins, and shows the bill.

    The discount is applied **directly to the fighter being discounted**, as a
    stated mu penalty per flagged result, and to nobody else. That is a
    deliberate departure from the ``*_integrity`` rating streams: those damp the
    Bradley-Terry likelihood of 27 bouts, and because WHR re-anchors the global
    mean every pass, the perturbation propagates — measured on the 2026-08-13
    snapshot it *raised* 325 of 401 rated fighters and lowered only 76, with the
    largest rise (+24.1) exceeding the largest fall (-14.1). A sleeve advertised
    as "only penalises, never rewards" that lifts four fifths of the board is
    not a discount; it is noise with a moral label.

    This is a **judgement board, not an accuracy board**. The earlier predictive
    audit used a forecast helper and variant bundle that were later retired, so
    its numerical sleeve verdict is not repeated here. The policy survives for
    what it asserts, not as a claimed predictive improvement, and it is not the
    default headline.
    """
    if current is None or current.empty or rating_col not in current.columns:
        return pd.DataFrame(columns=["rank", "fighter", rating_col, "integrity_cost"])

    board = current[["fighter", rating_col]
                    + [c for c in ("rating_periods",) if c in current.columns]].copy()
    if "rating_periods" in board.columns and min_rating_periods:
        board = board[pd.to_numeric(board["rating_periods"], errors="coerce").fillna(0)
                      >= min_rating_periods]
    board = board.dropna(subset=[rating_col])

    penalty_per_reason = {
        reason: (1.0 - float(factor)) * penalty_scale
        for reason, factor in _REASON_FACTOR.items()
    }
    counts = (
        ledger.groupby(["fighter", "reason"]).size().unstack(fill_value=0)
        if ledger is not None and not ledger.empty
        else pd.DataFrame()
    )
    cost = pd.Series(0.0, index=board.index)
    for reason in ("ped", "dq", "missed_weight"):
        n = (board["fighter"].map(counts[reason]).fillna(0).astype(int)
             if reason in getattr(counts, "columns", []) else 0)
        board[f"{reason}_discounted_fights"] = n
        cost = cost + n * penalty_per_reason[reason]
    board["discounted_fights"] = board[
        [f"{r}_discounted_fights" for r in ("ped", "dq", "missed_weight")]
    ].sum(axis=1)
    board["integrity_cost"] = cost
    board["integrity_discounted_rating"] = (
        pd.to_numeric(board[rating_col], errors="coerce") - cost
    )

    # Both ranks are "min" ranks. They used to disagree: the reference was a min
    # rank and the post-discount rank was a positional arange, so two fighters
    # tied before and after the debit reported rank_change of 0 and +1 -- a place
    # lost to row order, not to any discount.
    board["undiscounted_rank"] = board[rating_col].rank(ascending=False, method="min")
    board = board.sort_values("integrity_discounted_rating", ascending=False).reset_index(drop=True)
    board["rank"] = board["integrity_discounted_rating"].rank(
        ascending=False, method="min").astype(int)
    # Positive = the discount cost them places.
    board["rank_change"] = board["rank"] - board["undiscounted_rank"]

    keep = ["rank", "fighter", "integrity_discounted_rating", rating_col,
            "undiscounted_rank", "rank_change", "integrity_cost", "discounted_fights",
            "ped_discounted_fights", "dq_discounted_fights", "missed_weight_discounted_fights"]
    keep = [c for c in keep if c in board.columns]
    out = board[keep]
    return out.head(top) if top else out


UNRANKED_AT_FLOOR_STATUS = "unranked (no year above the bar)"


def completeness_gated_board(
    current: pd.DataFrame,
    *,
    rating_col: str = "sustained_peak_headline_mu_whr",
    min_rating_periods: int = 5,
    eligibility_override: pd.Series | None = None,
    completeness: pd.Series | None = None,
    min_completeness: float = 0.8,
    tested_wins: pd.Series | None = None,
    min_tested_wins: int | None = None,
    unranked_at_or_below: float | None = None,
    top: int | None = None,
) -> pd.DataFrame:
    """Rank who can be ranked; say so plainly about everyone else.

    Fighters below the evidence floor are returned with ``rank`` as NA and a
    ``status`` explaining which floor they failed, rather than being seated at
    the 1500 default and appearing as a mid-table fighter they are not.

    Two changes stop this board from printing ordering as measurement:

    * ``rank`` is a ``method="min"`` rank, so genuinely tied fighters share one
      place. It used to be a positional ``arange`` over a sort, which turned the
      sort's own tie-break into a rank difference.
    * ``unranked_at_or_below`` withholds a rank from fighters sitting on the
      score's floor. Career Skill Mass has a floor at zero that means "no
      calendar year cleared the bar", and spreading the fighters sitting on it
      across consecutive printed ranks read as a measurement and was not one.
      Under the hard ``clip(lower=0)`` that motivated this, 2,366 of 2,554
      fighters sat on the floor with 285 of them past the evidence gate; under
      the softplus hinge shipped 2026-08-26 the floor is nearly empty -- 175 of
      33,692 rated fighters, 21 past the gate -- so this now guards an edge case
      rather than a third of the board. It still has to be here: the floor is a
      property of the functional, not of one snapshot's hinge scale. Leave it
      ``None`` for scores with no such floor (base WHR mu).

    ``min_tested_wins`` adds a second, independent floor on *proven* record: how
    many tested opponents above a stated rating line the fighter actually beat,
    per :func:`ratings.opponent_quality.quality_win_record`. Rating periods count
    appearances and say nothing about their difficulty, so without this a clean
    record against a soft field clears the same floor as one built against
    contenders.

    Two failure modes make both halves necessary, and each was measured. Judging
    a schedule by opponent strength alone promotes gatekeepers -- a fighter who
    lost to ten elite opponents scores the same as one who beat them, and at a
    1900 bar Roy Nelson (0-10) outranked Khabib and St-Pierre. Judging by wins
    alone promotes unbeaten records built on a thin circuit. The caller answers
    the first by counting wins and the second by admitting only opponents with a
    tested record of their own.

    It gates rather than scores. A fighter is on the board or not; where they
    land is still the rating. Folding opposition quality into the score would
    post it twice, since the rating is already estimated from those same
    opponents. A fighter with no measured value is withheld -- absent evidence
    is not a pass.
    """
    if current is None or current.empty or rating_col not in current.columns:
        return pd.DataFrame(columns=["rank", "fighter", rating_col, "status"])

    board = current[["fighter", rating_col]
                    + [c for c in ("rating_periods",) if c in current.columns]].copy()
    periods = pd.to_numeric(board.get("rating_periods", pd.Series(0, index=board.index)),
                            errors="coerce").fillna(0)
    rated = pd.to_numeric(board[rating_col], errors="coerce")

    status = pd.Series("ranked", index=board.index, dtype=object)
    eligible_periods = periods >= min_rating_periods
    if eligibility_override is not None:
        override = eligibility_override.reindex(board.index).fillna(False).astype(bool)
        eligible_periods = eligible_periods | override
        board["eligibility_override"] = override
    status[~eligible_periods] = (
        f"insufficient observed history to rank (< {min_rating_periods} rating periods)")
    status[rated.isna()] = "insufficient observed history to rank (no qualifying period score)"
    if completeness is not None:
        comp = pd.to_numeric(board["fighter"].map(completeness), errors="coerce")
        board["observed_completeness"] = comp
        thin = comp.notna() & (comp < min_completeness)
        status[thin & status.eq("ranked")] = (
            f"insufficient observed history to rank (completeness < {min_completeness:g})")
    if min_tested_wins is not None:
        wins = pd.to_numeric(
            board["fighter"].map(tested_wins) if tested_wins is not None else pd.NA,
            errors="coerce",
        )
        board["tested_opponent_wins"] = wins
        unproven = wins.isna() | (wins < int(min_tested_wins))
        status[unproven & status.eq("ranked")] = (
            "insufficient proven record to rank "
            f"(< {int(min_tested_wins)} wins over tested contenders)")
    if unranked_at_or_below is not None:
        at_floor = rated.notna() & (rated <= float(unranked_at_or_below))
        status[at_floor & status.eq("ranked")] = UNRANKED_AT_FLOOR_STATUS

    board["status"] = status
    ranked = board[board["status"].eq("ranked")].sort_values(rating_col, ascending=False)
    ranked = ranked.reset_index(drop=True)
    ranked["rank"] = ranked[rating_col].rank(ascending=False, method="min").astype(int)
    withheld = board[~board["status"].eq("ranked")].copy()
    withheld["rank"] = pd.NA

    out = pd.concat([ranked.head(top) if top else ranked, withheld], ignore_index=True, sort=False)
    cols = ["rank", "fighter", rating_col, "status"]
    cols += [c for c in ("rating_periods", "observed_completeness", "tested_opponent_wins")
             if c in out.columns]
    return out[cols]
