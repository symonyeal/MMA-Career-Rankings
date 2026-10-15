"""Check the staged inputs and fitted artifacts required to rebuild a release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ratings.age import load_birth_dates
from ratings.rate_snapshot import _require_career_coverage
from ratings.scope import DEFAULT_PUBLISHED_SCOPE, SCOPE_ARTIFACT, scope_sources

# The snapshot behind README.md and RANKINGS.md. Every file in it is versioned,
# so any checkout can rebuild, re-score or refit the published boards.
PUBLISHED_SNAPSHOT = Path(__file__).resolve().parent / "data" / "snapshots" / "2026-10-14"


def check(snapshot: Path, *, scope: str = DEFAULT_PUBLISHED_SCOPE, inputs_only: bool = False) -> dict:
    """Report absent prerequisites; aggregate manifests cannot replace evidence."""
    snapshot = Path(snapshot)
    sources = scope_sources(scope)
    required = ["canonical_fights.parquet", "canonical_rounds.parquet", "canonical_fighters.parquet"]
    required.extend(SCOPE_ARTIFACT[s] for s in sources)
    if "majors" in sources:
        required.extend(["career_coverage.parquet", "sherdog_birth_dates.parquet"])
    if not inputs_only:
        required.extend(["rating_run.json", "combined_fights.parquet", "ratings_current.parquet",
                         "ratings_history_whr.parquet", "integrity_appearances.parquet",
                         "performance_appearances.parquet"])
        for name in ["completeness_gated_board", "prime_elite_board", "current_board"]:
            required.extend([f"{name}.parquet", f"{name}_women.parquet"])
    missing = [name for name in required if not (snapshot / name).is_file()]
    issues = []
    if "majors" in sources and (snapshot / "career_coverage.parquet").is_file():
        try:
            _require_career_coverage(snapshot, scope)
        except ValueError as e:
            issues.append(str(e))
    manifest = snapshot / "rating_run.json"
    if manifest.is_file():
        recorded = json.loads(manifest.read_text(encoding="utf-8")).get("birth_dates", 0)
        found = len(load_birth_dates(snapshot))
        # Before a fit, fewer dates than last time means an input went missing.
        # After it, any difference means the ratings were not fitted from these inputs.
        if found < recorded or (not inputs_only and found != recorded):
            issues.append(f"birth dates: found {found}, previous fit recorded {recorded}")
    return {"ready": not missing and not issues, "snapshot": str(snapshot), "scope": scope,
            "missing": missing, "issues": issues}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?", default=PUBLISHED_SNAPSHOT)
    parser.add_argument("--scope", default=DEFAULT_PUBLISHED_SCOPE)
    parser.add_argument("--inputs-only", action="store_true", help="Check prerequisites before fitting.")
    args = parser.parse_args()
    report = check(args.snapshot, scope=args.scope, inputs_only=args.inputs_only)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
