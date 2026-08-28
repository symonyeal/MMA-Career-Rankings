# Data reclaimed — 2026-08-19

> **Historical reclamation record.** Driver paths below now resolve through
> `_archive/20260825-superseded-research-drivers/`. The database called
> “production” here was later found stale and archived on 2026-08-26; no data
> was rebuilt during that cleanup.

Removed as redundant. Everything here is regenerable; nothing unique was lost.
At the time, the cleanup kept untouched: `external/` (the 823 MB profile cache
— 7.5 h of paced crawling to refetch), `raw/`, `ufc_rank_engine.sqlite`, and
every snapshot directory. The stale SQLite export was subsequently archived on
2026-08-26 without a rebuild.

## Duplicate staging artifacts — 185 MB

Each rated depth-one scope carried a full copy of **all five** model-bouts
policy variants plus `fightmatrix_model_eligible_bouts.parquet`, byte-identical
to the copies in
`snapshots/2026-08-14-fightmatrix-expanded-v3-working/`, which is the directory
those scopes were staged *from* and which the archived
`build_fightmatrix_expanded.py` reads.
A rated scope's actual model input is its own `crossorg_fights.parquet`; the
model-bouts files were pre-staging inputs it never reads again.

Removed 6 files from each of `-raw`, `-complete_edge`, `-reliability`. Verified
byte-identical (SHA-256) against the working copy before each deletion.

Historical regeneration driver:
`_archive/20260825-superseded-research-drivers/build_fightmatrix_expanded.py`.

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

## Post-reclamation manifest repair — 2026-08-26

The three rated depth-one manifests still listed the six files removed above,
so a verifier correctly reported six missing artifacts in each finalized
scope. Their `artifacts` maps now describe files that remain in each directory,
and a `post_reclamation` object records the removed names, reason, dates, and
authoritative working-directory location. Existing parquet bytes and hashes
were not changed.

An exact-duplicate scan also found 51 groups totaling about 110 MB across the
finalized experimental snapshots. Those copies are intentionally retained:
they are scope-local research evidence, and removing more of them would weaken
snapshot immutability unless the archive format itself were redesigned. They
are redundant bytes, not an active ranking input or disposable cache.
