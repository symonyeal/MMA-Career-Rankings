# Data reclaimed — 2026-08-19

Removed as redundant. Everything here is regenerable; nothing unique was lost.
Kept untouched: `external/` (the 823 MB profile cache — 7.5 h of paced crawling
to refetch), `raw/`, `ufc_rank_engine.sqlite` (production), and every snapshot
directory.

## Duplicate staging artifacts — 185 MB

Each rated depth-one scope carried a full copy of **all five** model-bouts
policy variants plus `fightmatrix_model_eligible_bouts.parquet`, byte-identical
to the copies in
`snapshots/2026-08-14-fightmatrix-expanded-v3-working/`, which is the directory
those scopes were staged *from* and which `build_fightmatrix_expanded.py` reads.
A rated scope's actual model input is its own `crossorg_fights.parquet`; the
model-bouts files were pre-staging inputs it never reads again.

Removed 6 files from each of `-raw`, `-complete_edge`, `-reliability`. Verified
byte-identical (SHA-256) against the working copy before each deletion.

Regenerate: re-stage the scope with `build_fightmatrix_expanded.py`.

## Experimental databases — 422 MB

| File | Size | Why |
| --- | ---: | --- |
| `ufc_rank_engine_fightmatrix_depth_one.sqlite` | 310 MB | Experimental depth-one export |
| `ufc_rank_engine_fightmatrix_public.sqlite` | 112 MB | 302-seed bounded cohort, superseded by depth one |

Both are `.gitignore`d as "large/reproducible" and neither is read by any module
or test. The snapshots they were built from are still present, so either can be
rebuilt in one command:

```
python build_database.py --snapshot data/snapshots/<scope> \
    --db-path data/<name>.sqlite
```

`data/ufc_rank_engine.sqlite` — the production database — was **not** touched.

## Total: 607 MB
