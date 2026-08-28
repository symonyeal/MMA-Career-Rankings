"""Does the corpus apply one coverage rule to every fighter, or two?

The engine's scopes are built two ways at once. Cards are enumerated by event
for seven promotions (UFC, UFC 1-27, PRIDE, WEC, Strikeforce, Affliction,
Bellator, RIZIN), which is roster-complete *within* those promotions and
truncates every career that ran wider. ``sherdog_org_loader.parse_fighter_career``
exists to remove that truncation by reading one page per fighter, and its own
docstring gives the reason:

    Rating a fighter on a subset of their record is the same censoring bias that
    made the old fighter-seeded cache unusable, only applied along a different
    axis. So once a fighter is in the graph at all, their whole record comes in.

That expansion was run over the fighters who appeared on a card of the six
non-UFC promotions, and not over the UFCStats roster, so "once a fighter is in
the graph" quietly meant "once a fighter is in the *majors* graph". The result
is one corpus carrying two coverage rules.

The difference is not cosmetic. A low-loss Bradley--Terry record has no interior
maximum -- the win gradient ``sum_j (1 - sigma(r - r_j))`` is positive at every
finite ``r`` -- so the prior alone stops the climb and the equilibrium sits near
``opponent_level + 173.72 * ln(2k/v)``. ``k`` is *how many of the fighter's
bouts the corpus happens to hold*. Two equally dominant fighters with different
coverage get different ratings for that reason alone, and a career functional
that integrates the rating over years multiplies the gap by career length.

Measured on ``data/snapshots/2026-08-13`` before the repair, over the 1,825
fighters with three or more UFC bouts: median recorded pre-UFC bouts was 12
where the career page had been read and 1 where it had not.

This module states the property as a number, so a build can check it.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

COVERAGE_COLUMNS = [
    "fighter",
    "ufc_bouts",
    "corpus_bouts",
    "pre_ufc_bouts",
    "sherdog_id",
    "career_page_read",
]

# Share of the eligible roster whose whole-career page must have been read
# before the corpus can be called coverage-symmetric. Not 1.0: a few fighters
# have no resolvable Sherdog identity at all, and abstaining on those is honest,
# whereas demanding perfection would make the gate unenforceable.
MIN_CAREER_PAGE_SHARE = 0.95

# Below this many UFC bouts a fighter cannot reach the board's completeness gate
# on UFC evidence, so their coverage does not decide a published rank.
DEFAULT_MIN_UFC_BOUTS = 3


def cached_page_ids(cache_dir: Path | str) -> set[str]:
    """Sherdog ids whose whole-career page is on disk."""
    return {
        path.name.split(".", 1)[0]
        for path in Path(cache_dir).glob("*.html.gz")
    }


def coverage_rows(
    canonical_fights: pd.DataFrame,
    corpus_fights: pd.DataFrame,
    *,
    sherdog_ids: pd.Series | dict | None = None,
    read_ids: set[str] | None = None,
) -> pd.DataFrame:
    """One row per UFC fighter: what the corpus holds of their career.

    ``corpus_fights`` is the staged, canonically-named fight table for the rated
    scope. ``sherdog_ids`` maps a canonical name to the Sherdog id the identity
    resolver assigned it, and ``read_ids`` is the set of ids whose career page
    has been read; both are optional, so the shape can be audited without the
    HTML cache present.
    """
    if canonical_fights is None or canonical_fights.empty:
        return pd.DataFrame(columns=COVERAGE_COLUMNS)

    ufc = (
        pd.concat([canonical_fights["fighter_a"], canonical_fights["fighter_b"]])
        .value_counts()
        .rename("ufc_bouts")
    )
    debut = (
        pd.concat([
            canonical_fights[["fighter_a", "event_date"]].rename(
                columns={"fighter_a": "fighter"}),
            canonical_fights[["fighter_b", "event_date"]].rename(
                columns={"fighter_b": "fighter"}),
        ])
        .assign(event_date=lambda d: pd.to_datetime(d["event_date"], errors="coerce"))
        .groupby("fighter")["event_date"].min()
    )

    sides = pd.concat([
        corpus_fights[["fighter_a", "event_date"]].rename(columns={"fighter_a": "fighter"}),
        corpus_fights[["fighter_b", "event_date"]].rename(columns={"fighter_b": "fighter"}),
    ], ignore_index=True)
    sides["event_date"] = pd.to_datetime(sides["event_date"], errors="coerce")
    corpus_bouts = sides.groupby("fighter").size().rename("corpus_bouts")
    sides["_debut"] = sides["fighter"].map(debut)
    pre = (
        sides[sides["event_date"] < sides["_debut"]]
        .groupby("fighter").size().rename("pre_ufc_bouts")
    )

    out = ufc.to_frame().reset_index(names="fighter")
    out["corpus_bouts"] = out["fighter"].map(corpus_bouts).fillna(0).astype(int)
    out["pre_ufc_bouts"] = out["fighter"].map(pre).fillna(0).astype(int)
    ids = pd.Series(sherdog_ids, dtype=object) if sherdog_ids is not None else pd.Series(dtype=object)
    out["sherdog_id"] = out["fighter"].map(ids) if len(ids) else None
    known = out["sherdog_id"].astype("string").fillna("")
    out["career_page_read"] = known.isin(read_ids or set()) & known.ne("")
    return out[COVERAGE_COLUMNS]


def coverage_summary(
    rows: pd.DataFrame,
    *,
    min_ufc_bouts: int = DEFAULT_MIN_UFC_BOUTS,
) -> dict:
    """The asymmetry, as numbers a build can assert on.

    ``pre_ufc_bouts_gap`` is the statistic that failed before the repair: the
    difference in median recorded pre-UFC bouts between the fighters whose
    career page was read and the fighters whose page was not. Under one coverage
    rule it has nothing to measure, because there is no second group.
    """
    empty = {"eligible": 0, "career_page_share": 1.0, "pre_ufc_bouts_gap": 0.0}
    if rows is None or rows.empty:
        return empty
    eligible = rows[rows["ufc_bouts"] >= int(min_ufc_bouts)]
    if eligible.empty:
        return empty
    read = eligible[eligible["career_page_read"]]
    unread = eligible[~eligible["career_page_read"]]
    gap = (
        float(read["pre_ufc_bouts"].median() - unread["pre_ufc_bouts"].median())
        if len(read) and len(unread) else 0.0
    )
    return {
        "eligible": int(len(eligible)),
        "career_page_read": int(len(read)),
        "career_page_share": float(len(read) / len(eligible)),
        "median_pre_ufc_bouts_read":
            float(read["pre_ufc_bouts"].median()) if len(read) else float("nan"),
        "median_pre_ufc_bouts_unread":
            float(unread["pre_ufc_bouts"].median()) if len(unread) else float("nan"),
        "pre_ufc_bouts_gap": gap,
        "median_corpus_bouts_read":
            float(read["corpus_bouts"].median()) if len(read) else float("nan"),
        "median_corpus_bouts_unread":
            float(unread["corpus_bouts"].median()) if len(unread) else float("nan"),
    }


def is_coverage_symmetric(
    summary: dict,
    *,
    min_share: float = MIN_CAREER_PAGE_SHARE,
) -> bool:
    """Whether the corpus applies one coverage rule to the eligible roster."""
    if not summary or not summary.get("eligible"):
        return True
    return float(summary.get("career_page_share", 0.0)) >= float(min_share)


def describe(summary: dict) -> str:
    if not summary.get("eligible"):
        return "career coverage: no eligible fighters"
    return (
        "career coverage: "
        f"{summary['career_page_read']:,}/{summary['eligible']:,} eligible fighters "
        f"({summary['career_page_share']:.1%}) have a whole-career page; "
        f"median recorded pre-UFC bouts {summary['median_pre_ufc_bouts_read']:.0f} read "
        f"vs {summary['median_pre_ufc_bouts_unread']:.0f} unread "
        f"(gap {summary['pre_ufc_bouts_gap']:+.0f})"
    )
