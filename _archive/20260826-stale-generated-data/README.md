# Stale generated data archived 2026-08-26

No data was rebuilt. This archive removes obsolete outputs and caches from
current-looking paths while preserving them locally under the ignored
`generated-data/` tree.

| Original location | Reason archived |
|---|---|
| `data/ufc_rank_engine.sqlite` | Built 2026-08-14 with the retired schema and UFC-only-sized tables; it did not represent the current whole-sport snapshot. |
| `data/snapshots/2026-08-13/prequential_*` | Unkeyed exports predated prequential cache schema 6 and the age-through-inactivity projection. |
| `data/model_tuning/prequential/2026-08-13/` | Superseded keyed folds; current variant definitions resolve to different keys. |
| `data/model_tuning/top100-era-skew/` | Fixed-name fits belonging to the archived 2026-08-21 investigation. |
| `data/model_tuning/age-drift/` | Historical age-prior experiment run before the final inactivity projection; useful evidence, not a current evaluation. |
| `.test_tmp/`, `.ruff_cache/`, `__pycache__/` | Reproducible local test and interpreter caches. |

The raw UFC snapshots, Sherdog pages, FightMatrix profiles, current ranking
snapshot, current Top-100 audit, and finalized experimental evidence were not
moved. Restoring an item means moving it back to the recorded original path;
doing so does not make a stale result current.
