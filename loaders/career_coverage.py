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

import json
from pathlib import Path

import pandas as pd

from loaders.page_cache import open_cache

COVERAGE_COLUMNS = [
    "fighter",
    "ufc_bouts",
    "corpus_bouts",
    "pre_ufc_bouts",
    "sherdog_id",
    "whole_career_merged",
]

# Share of the eligible roster whose whole-career rows must have been merged
# before the corpus can be called coverage-symmetric. Not 1.0: a few fighters
# have no resolvable Sherdog identity at all, and abstaining on those is honest,
# whereas demanding perfection would make the gate unenforceable.
MIN_WHOLE_CAREER_SHARE = 0.95
INCORPORATED_PAGE_IDS_ARTIFACT = "career_pages_incorporated.json"

# Below this many UFC bouts a fighter cannot reach the board's completeness gate
# on UFC evidence, so their coverage does not decide a published rank.
DEFAULT_MIN_UFC_BOUTS = 3


def cached_page_ids(cache_dir: Path | str) -> set[str]:
    """Sherdog ids whose whole-career page is in the shared page store."""
    with open_cache(cache_dir) as cache:
        return set(cache.keys("fighters"))


def incorporated_page_ids(
    cache_dir: Path | str,
    bouts: pd.DataFrame | None = None,
) -> set[str]:
    """Sherdog ids whose parsed career rows reached the corpus.

    Most ids are recoverable from surviving ``fighter_page`` rows. A page whose
    every bout duplicated a better event-card row leaves no such provenance, so
    the builder records that successful incorporation separately.
    """
    ids: set[str] = set()
    if bouts is not None and not bouts.empty and "fighter_a_id" in bouts.columns:
        source = bouts.get("source", pd.Series("", index=bouts.index))
        ids.update(
            bouts.loc[source.eq("fighter_page"), "fighter_a_id"]
            .dropna()
            .astype(str)
        )

    path = Path(cache_dir) / INCORPORATED_PAGE_IDS_ARTIFACT
    if not path.exists():
        return ids
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        recorded = payload["fighter_ids"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"invalid incorporated-page audit at {path}") from exc
    ids.update(str(value) for value in recorded)
    return ids


def record_incorporated_page_ids(cache_dir: Path | str, fighter_ids: set[str]) -> None:
    """Atomically preserve page ids after their parsed rows are merged."""
    path = Path(cache_dir) / INCORPORATED_PAGE_IDS_ARTIFACT
    existing = incorporated_page_ids(cache_dir)
    payload = {
        "schema_version": 1,
        "fighter_ids": sorted(existing | {str(value) for value in fighter_ids}),
    }
    candidate = path.with_name(path.name + ".new")
    candidate.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    candidate.replace(path)


def coverage_rows(
    canonical_fights: pd.DataFrame,
    corpus_fights: pd.DataFrame,
    *,
    sherdog_ids: pd.Series | dict | None = None,
    merged_ids: set[str] | None = None,
) -> pd.DataFrame:
    """One row per UFC fighter: what the corpus holds of their career.

    ``corpus_fights`` is the staged, canonically-named fight table for the rated
    scope. ``sherdog_ids`` maps a canonical name to the Sherdog id the identity
    resolver assigned it, and ``merged_ids`` is the set of ids whose parsed
    whole-career rows were incorporated into ``corpus_fights``. Both are
    optional, so the shape can be audited before the extension exists.
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
    out["whole_career_merged"] = known.isin(merged_ids or set()) & known.ne("")
    return out[COVERAGE_COLUMNS]


def coverage_summary(
    rows: pd.DataFrame,
    *,
    min_ufc_bouts: int = DEFAULT_MIN_UFC_BOUTS,
) -> dict:
    """The asymmetry, as numbers a build can assert on.

    ``pre_ufc_bouts_gap`` is the statistic that failed before the repair: the
    difference in median recorded pre-UFC bouts between fighters whose parsed
    whole-career rows were merged and fighters whose rows were not. Under one
    coverage rule it has nothing to measure, because there is no second group.
    """
    empty = {"eligible": 0, "whole_career_share": 1.0, "pre_ufc_bouts_gap": 0.0}
    if rows is None or rows.empty:
        return empty
    if "whole_career_merged" not in rows.columns:
        raise ValueError(
            "career coverage predates the merged-row audit; restage the majors scope"
        )
    eligible = rows[rows["ufc_bouts"] >= int(min_ufc_bouts)]
    if eligible.empty:
        return empty
    merged = eligible[eligible["whole_career_merged"]]
    unmerged = eligible[~eligible["whole_career_merged"]]
    gap = (
        float(merged["pre_ufc_bouts"].median() - unmerged["pre_ufc_bouts"].median())
        if len(merged) and len(unmerged) else 0.0
    )
    return {
        "eligible": int(len(eligible)),
        "whole_career_merged": int(len(merged)),
        "whole_career_share": float(len(merged) / len(eligible)),
        "median_pre_ufc_bouts_merged":
            float(merged["pre_ufc_bouts"].median()) if len(merged) else float("nan"),
        "median_pre_ufc_bouts_unmerged":
            float(unmerged["pre_ufc_bouts"].median()) if len(unmerged) else float("nan"),
        "pre_ufc_bouts_gap": gap,
        "median_corpus_bouts_merged":
            float(merged["corpus_bouts"].median()) if len(merged) else float("nan"),
        "median_corpus_bouts_unmerged":
            float(unmerged["corpus_bouts"].median()) if len(unmerged) else float("nan"),
    }


def is_coverage_symmetric(
    summary: dict,
    *,
    min_share: float = MIN_WHOLE_CAREER_SHARE,
) -> bool:
    """Whether the corpus applies one coverage rule to the eligible roster."""
    if not summary or not summary.get("eligible"):
        return True
    return float(summary.get("whole_career_share", 0.0)) >= float(min_share)


def describe(summary: dict) -> str:
    if not summary.get("eligible"):
        return "career coverage: no eligible fighters"
    return (
        "career coverage: "
        f"{summary['whole_career_merged']:,}/{summary['eligible']:,} eligible fighters "
        f"({summary['whole_career_share']:.1%}) have whole-career rows merged; "
        f"median recorded pre-UFC bouts {summary['median_pre_ufc_bouts_merged']:.0f} merged "
        f"vs {summary['median_pre_ufc_bouts_unmerged']:.0f} unmerged "
        f"(gap {summary['pre_ufc_bouts_gap']:+.0f})"
    )
