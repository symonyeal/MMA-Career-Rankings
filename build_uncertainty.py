"""Bootstrap the Career Skill Mass diagnostic and persist its rank intervals.

Reruns the whole smoother under Dirichlet-reweighted events (see
``ratings/uncertainty.py``) and writes ``career_mass_uncertainty.parquet`` into
the snapshot, so the notebook can show every rank with the interval it deserves
instead of a bare integer.

These artifacts describe Career Skill Mass, not the published Public Legacy
Score. Intervals and tiers are ORDERING claims, so they are made inside ONE
bout-graph component. ``--gender`` picks it and defaults to the men's component;
``--gender F`` writes the ``*_women`` artifacts beside it. A mixed run would be
asking whether a woman is separated from a man, which no bout in the corpus can
answer -- see ``ratings/gender.py``.

Usage::

    python build_uncertainty.py data/snapshots/2026-08-13 --replicates 12
    python build_uncertainty.py data/snapshots/2026-08-13 --replicates 12 --gender F
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


from ratings.constants import SUSTAINED_PEAK_MIN_FIGHTS
from ratings.scope import DEFAULT_PUBLISHED_SCOPE
from ratings.gender import (
    DEFAULT_GENDER,
    GENDER_LABEL,
    GENDER_SUFFIX,
    GENDERS,
)
from ratings.symon_score import (
    DEFAULT_CAREER_REFERENCE,
    parse_reference,
)
from ratings.bootstrap import bootstrap_snapshot
from ratings.uncertainty import career_tiers, tier_summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument(
        "--replicates", type=int, default=12,
        help="12 is an exploratory check; budget 150 or more for a release board",
    )
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--quantiles", default="0.025,0.975",
                    help="interval endpoints as lo,hi")
    # Follows the production bar by default: the snapshot once carried a
    # parquet built at the mean bar beside a summary json claiming 0.9, and a
    # reader had no way to tell which board the intervals described.
    ap.add_argument("--reference", default=str(DEFAULT_CAREER_REFERENCE),
                    help="yearly bar: contender:N, count:N, mean, hybrid:L, or quantile")
    ap.add_argument("--scope", default=DEFAULT_PUBLISHED_SCOPE,
                    help="which bouts the board is built from; see ratings/scope.py")
    ap.add_argument("--tier-confidence", type=float, default=0.95,
                    help="share of replicates a tier leader must win to open a new tier")
    ap.add_argument("--min-rating-periods", type=int, default=SUSTAINED_PEAK_MIN_FIGHTS,
                    help="same completeness gate used by the published board")
    ap.add_argument(
        "--gender",
        choices=list(GENDERS),
        default=DEFAULT_GENDER,
        help=(
            "Bout-graph component to make interval and tier claims inside. "
            "Default M, the published board. Men and women never fight, so a "
            "mixed interval would be read off the prior."
        ),
    )
    ap.add_argument("--out", type=Path, default=None,
                    help="defaults to <snapshot>/career_mass_uncertainty.parquet")
    args = ap.parse_args()

    lo, hi = (float(x) for x in args.quantiles.split(","))
    reference = parse_reference(args.reference)
    print(f"[bootstrap] scope={args.scope} gender={args.gender} "
          f"({GENDER_LABEL[args.gender]}) {args.replicates} replicates")
    t0 = time.perf_counter()
    board, draws = bootstrap_snapshot(
        args.snapshot_dir, scope=args.scope, gender=args.gender,
        min_rating_periods=args.min_rating_periods, reference=reference,
        replicates=args.replicates, seed=args.seed, lo=lo, hi=hi, progress=True,
    )
    wall = time.perf_counter() - t0
    tiers = career_tiers(board, draws, confidence=args.tier_confidence)
    summary_tiers = tier_summary(tiers)

    suffix = GENDER_SUFFIX[args.gender]
    out_path = args.out or (
        args.snapshot_dir / f"career_mass_uncertainty{suffix}.parquet"
    )
    board.to_parquet(out_path, index=False)
    tiers.to_parquet(
        out_path.with_name(f"career_mass_tiers{suffix}.parquet"), index=False
    )
    ranked_tiers = tiers[tiers["tier"].notna()]
    summary = {
        "replicates": int(args.replicates),
        "seed": int(args.seed),
        "scope": args.scope,
        "score": "symon_career_skill_mass",
        "gender": args.gender,
        "gender_label": GENDER_LABEL[args.gender],
        "interval": [lo, hi],
        "reference": str(reference),
        "age_drift": True,
        "tier_confidence": float(args.tier_confidence),
        "min_rating_periods": int(args.min_rating_periods),
        "tiers": int(ranked_tiers["tier"].nunique()),
        "tiered_fighters": len(ranked_tiers),
        "unranked_at_floor": int(tiers["tier"].isna().sum()),
        "largest_tier": int(ranked_tiers.groupby("tier").size().max()) if len(ranked_tiers) else 0,
        "fighters": len(board),
        "wall_seconds": round(wall, 1),
        "median_rank_width_top50": float(
            (board.head(50)["rank_hi"] - board.head(50)["rank_lo"]).median()
        ),
    }
    (args.snapshot_dir / f"career_mass_uncertainty{suffix}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[bootstrap] wrote {out_path} in {wall:.0f}s")
    print(json.dumps(summary, indent=2))
    top = board.head(20)[["fighter", "mass", "rank", "rank_lo", "rank_hi", "mass_sd"]]
    print(top.round(1).to_string(index=False))
    print("\n=== tiers: nobody in a tier is separated from the fighter at its top ===")
    print(summary_tiers.head(15).round(1).to_string(index=False))
    print("\n=== the top three tiers, in full ===")
    show = tiers[tiers["tier"].le(3)] if len(ranked_tiers) else tiers.head(0)
    print(show[["tier", "fighter", "mass", "mass_lo", "mass_hi", "p_below_tier_leader"]]
          .round(2).to_string(index=False))


if __name__ == "__main__":
    main()
