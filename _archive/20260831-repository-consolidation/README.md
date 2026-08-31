# Archived 2026-08-31 — repository consolidation

This archive preserves superseded research code, historical decision records,
and stale generated outputs removed from the live project during the 2026-08-31
consistency pass. Nothing in this group is current operating guidance.

## Closed recursive FightMatrix expansion subsystem

Original paths:

- `analysis/fightmatrix_graph.py`
- `analysis/fightmatrix_validation.py`
- `analysis/fightmatrix_viz.py`
- `analysis/source_scope.py`
- `loaders/fightmatrix_expansion.py`
- `loaders/fightmatrix_identity.py`
- `tests/test_fightmatrix_expansion.py`
- `tests/test_source_scope.py`

These files formed one recursive depth-one public-profile research pipeline.
The only live callers were the two tests archived with it; active refresh and
rating paths use `loaders/fightmatrix_profiles.py` and the bounded ranked-cohort
artifacts instead. The finalized experimental snapshots remain in place as
immutable evidence and were not trimmed or rebuilt.

To restore the experiment, move the eight files back to their original paths as
one unit. Do not restore only a loader or only its tests.

## Historical and superseded records

Original paths:

- `docs/FIGHTMATRIX_PUBLIC_DATA_2026-08-14.md`
- `docs/FIGHTMATRIX_GRAPH_EXPANSION_2026-08-14.md`
- `docs/PLAN_WHOLE_SPORT_ENGINE_2026-08-21.md`
- `docs/PRINCIPLED_CORE_EVOLUTION_2026-08-20.md`
- `docs/PRIOR_MASS_AND_UNCERTAINTY_2026-08-20.md`
- `docs/BOARD_AND_IDENTIFICATION_2026-08-25.md`
- `data/RECLAIMED_2026-08-19.md`

Each record identified itself as historical or had been superseded by the
2026-08-27/28 coverage and rating-layer records. Current guidance remains in
`docs/CAREER_COVERAGE_2026-08-27.md`,
`docs/RATING_LAYER_AND_LEDGER_2026-08-28.md`, and
`docs/NEXT_2026-08-28.md`.

## Orphaned field-depth outputs

Original paths, preserved under
`generated-data/data/snapshots/2026-08-13/`:

- `field_depth.json`
- `field_depth.parquet`
- `field_percentiles.parquet`
- `opponent_quality_timeline.parquet`

The module, test, and driver that produced these files had already been
archived. No live code or document read them. Restoring the outputs alone does
not restore the feature; the archived module and driver are also required.

## Superseded top-100 audit

The prior contents of `data/model_tuning/top100-audit/` are preserved under
`generated-data/data/model_tuning/top100-audit/`. They were internally coherent
but predated the current `ratings_current.parquet`: for example, they recorded
Jon Jones at 2,940.8 while the current snapshot records 2,854.6. The live audit
was regenerated after the move.

`generated-data/` is intentionally ignored by Git. The archive README records
the recovery path while avoiding another committed copy of large generated
artifacts.

## Disposable verification caches

After the final test, lint, and compile checks, `.ruff_cache`, generated
`.test_tmp` contents, and live-tree `__pycache__` directories were moved under
`generated-data/cache-sweep/`. The tracked `.test_tmp/.gitkeep` remains at its
original path. These caches are not required for recovery and may be rebuilt by
the normal tools.

## Deliberately retained outside this archive

- Finalized 2026-08-14 FightMatrix experimental snapshots and their duplicate
  scope evidence remain where their manifests expect them.
- Older dated canonical/raw snapshots remain available for release comparison.
- `analysis/CHART_PLAN.md` remains live because current tests and chart code cite
  it as the retained visual contract.
- `majors_fights.parquet` remains a reproducible staging input even though an
  archived byte-identical copy exists; refresh may regenerate it.
