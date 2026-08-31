# FightMatrix public-data incorporation — 2026-08-14

> **Historical experimental record.** This describes the bounded 302-profile
> run as delivered on 2026-08-14. Its SQLite export was reclaimed on 2026-08-19
> after the depth-one experiment superseded it; the snapshot and source cache
> remain preserved. It is not the current published scope.

## Delivered local data

- 302 public profiles linked from the persisted current-division and all-time
  ranking tables; no recursive opponent crawl.
- 72,295,776 bytes of cached HTML under
  `data/external/fightmatrix/profiles/` (ignored, reproducible, local only).
- 6,644 unique professional bouts with opponent, outcome, method, round,
  event/date/country, profile ids, and published pre-fight rank context.
- 4,023 post-2000-11-17 non-UFC bouts after pair/date deduplication against the
  canonical UFC snapshot, connecting 3,553 fighters.
- Zero failed profile requests in the completed run.

## Persisted artifacts

| Artifact | Role |
|---|---|
| `fightmatrix_profiles.parquet` | Public biography and career diagnostics. |
| `fightmatrix_bouts.parquet` | Deduplicated public profile histories. |
| `fightmatrix_crossorg_fights.parquet` | Source-specific canonical rating input. |
| `crossorg_fights.fightmatrix-public.parquet` | Optional combined input in the standard snapshot. |
| `fightmatrix_scope_comparison.parquet` | UFC-only vs bounded-cohort scores/ranks. |
| `2026-08-13-fightmatrix-public/` | Completed combined rating snapshot. |
| `ufc_rank_engine_fightmatrix_public.sqlite` | Historical combined-scope database, reclaimed 2026-08-19; the snapshot remains. |

## Provenance boundary

FightMatrix's proprietary database and CIRRS code were not copied. The cache
contains only pages publicly exposed for the bounded seed cohort. Published
FightMatrix rank, points, quality-performance percentage, 540 opponent metric,
combat age, and opponent historical rank are retained for diagnostics and do
not feed the engine. Optional ratings use only official-result-shaped fields:
fighter, opponent, outcome, method, round, event and date.

## Model result and decision

Adding 4,023 bouts expanded the rating graph from 2,554 to 5,492 fighters and
gave complete post-cutoff careers to the selected cohort. Examples: Aldo went
from 23 to 42 rating periods, GSP 22 to 28, Demetrious Johnson 18 to 30, Penn
27 to 32, and Hughes 23 to 31.

The bounded-cohort board is not promoted to default. It is a selection-biased
subgraph rather than FightMatrix's complete opponent universe, organization
names are not yet fully normalized, and non-UFC title lineage is absent. Those
gaps particularly understate Fedor, Nogueira, Henderson, Faber and Alvarez.
The standard snapshot therefore remains UFC-only while the combined run is
preserved as an explicit source-scope experiment.

## Next gates before promotion

1. Replace ranked-cohort sampling with a licensed complete professional-bout
   source or demonstrate graph-closure stability through recursive-depth
   ablations.
2. Normalize promotion identities and build promotion strength by date.
3. Add authoritative non-UFC division and title-lineage histories.
4. Re-run rank uncertainty and multi-reference agreement before changing the
   notebook default.
