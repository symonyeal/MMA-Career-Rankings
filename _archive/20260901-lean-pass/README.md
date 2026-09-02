# The lean pass — 2026-09-01

The working copy was 2,070 MB. 1,347 MB of that could not be read by anything in
the project. This folder records what went and how to get it back.

No ranking moved. The published boards were checked against their artifacts
before and after: the top 100 and the elite Prime 50 match row for row, and the
release facts beside them are the same figures.

## What was removed, and why nothing could read it

### FightMatrix profile cache — 4,035 of 4,337 pages, 780 MB

`loaders/fightmatrix_profiles.py` follows only the profile links in the current
division and all-time ranking tables. That bounded crawl is 302 profiles, and
`fightmatrix_profiles.parquet` in the published snapshot names exactly those 302.
The other 4,035 pages were left behind by the depth-one recursive expansion,
which was measured and never promoted; its loader was archived on 2026-08-31.

`stale_profile_ids.txt` lists every removed profile id, and `sweep_manifest.json`
records the 302 that were kept. A re-crawl can be aimed at exactly the removed
set rather than starting over.

### Four expansion snapshots — 300 MB

- `data/snapshots/2026-08-14-fightmatrix-depth-one-raw`
- `data/snapshots/2026-08-14-fightmatrix-depth-one-reliability`
- `data/snapshots/2026-08-14-fightmatrix-depth-one-complete_edge`
- `data/snapshots/2026-08-14-fightmatrix-expanded-v3-working`
- `data/snapshots/2026-08-14-fightmatrix-validation`

Every table in these was written by `loaders/fightmatrix_expansion.py`, archived
on 2026-08-31 under `_archive/20260831-repository-consolidation/loaders/`. No
live module, test, or document referred to any of these directories by name.
Three of them were near-copies of one another.

### Generated data under four archive folders — 245 MB

`_archive/20260826-stale-generated-data/generated-data`,
`_archive/20260831-repository-consolidation/generated-data`,
`_archive/20260827-career-coverage-repair/generated-data`, and
`_archive/20260828-orphaned-and-stale/generated-data`. These held old SQLite
exports and pytest caches. `.gitignore` already declared them recoverable rather
than versioned; `build_database.py` rebuilds the export from a snapshot bundle.

### Backup parquets inside the published snapshot — 17 MB

`ratings_current.pre_dedup_20260901.parquet`,
`ratings_current.pre_resume_20260901.parquet`, and
`ratings_history_whr.pre_dedup_20260901.parquet` were sitting in
`data/snapshots/2026-08-13/`. Nothing read them, and a release directory that
also holds working backups stops being a statement of what was released. The
runs they came from are described in the changelog.

### Abandoned pytest temp directories and caches — 5.6 MB

`.test_tmp/pytest_ok`, `.test_tmp/repo_consistency_targeted`,
`.test_tmp/root_20260901_baseline`, `.test_tmp/root_duplicate_review`, plus
`__pycache__` and `.ruff_cache` trees. `--basetemp` recreates the first on every
run.

## Code retired in the same pass

`analysis/unwired_chart_builders.py` in this folder holds 19 chart and table
builders lifted out of `analysis/viz.py` — 796 lines, 16% of that file. None were
called by `analysis/build_notebook.py` or drawn in `analysis/notebook.ipynb`.
Four read `sleeve_attribution.parquet` and the `ratings_history_*_method_*`
streams, which no snapshot has produced since the 2026-08-20 core evolution, so
they could not have run against current data at all. `rank_movement_chart` and
`calibration_residuals_chart` had no caller of any kind, not even a test. To
restore one, paste it back into `analysis/viz.py`; the helpers it calls are still
there.

Three other removals live only in git history, because each was a duplicate of
something that stayed:

- `build_boards.py` carried a second README-writing path —
  `update_readme_block`, `update_readme_blocks`, `update_readme_board`,
  `update_readme_women_board`. The publisher calls `update_publication_files`,
  which validates every marker in every file before writing any of them. The
  four invariants the retired path's tests covered were repointed at the live
  publisher, so that coverage is now real rather than nominal.
- `loaders/sherdog_org_loader.py` defined its own `_session`, user agent and
  politeness delay. Both Sherdog readers fetch from one host and write into one
  cache directory, so it now imports them from `loaders/sherdog_loader.py`. The
  surviving delay is the longer of the two.
- `loaders/fightmatrix_organizations.py` kept `build_organization_map` and
  `annotate_organizations`, which produced
  `fightmatrix_organization_map.parquet` — an artifact only the removed
  expansion snapshots held.

## Caches became one file per source

Every reader had been writing one file per fetched page into its own directory,
in its own layout: plain HTML for FightMatrix profiles and Sherdog searches,
gzipped HTML for Sherdog fighters and events, a third scheme for ranking pages.
That was 6,972 files and 254 MB holding one kind of thing — the bytes a page
returned, kept so a parser can run again without asking the site again.

`loaders/page_cache.py` is now that one thing. A store is a single `pages.sqlite`
in the source's cache directory, holding gzipped page text under a kind and a
key. Every page was read back and compared against its loose file before that
file was removed; all 6,948 matched exactly.

| | before | after |
| --- | ---: | ---: |
| Sherdog | 6,654 files, 177.0 MB | 1 store, 172.2 MB |
| FightMatrix profiles | 302 files, 72.3 MB | 1 store, 9.4 MB |
| whole working copy | 7,493 files, 2,070 MB | 566 files, 634 MB |

FightMatrix shrank because those pages had never been compressed. Sherdog barely
moved because its pages already were — the win there is 6,654 files becoming one.

The 13 committed FightMatrix ranking pages under `data/external/fightmatrix/html/`
were deliberately left as loose files: they are in version control as readable
provenance, and a binary store would hide them from review.

## Documentation merged

`docs/NEXT_2026-08-28.md` and `docs/NEXT_2026-09-01.md` are here. They were two
registers of the same thing. They repeated six of their seven refusals word for
word, carried a rebuild command block each, and the later one had grown two
outcome sections and two separate "still open" lists. They are replaced by one
register, `docs/DECISIONS.md`. The merge itself carried every open item and every
refusal across. One open item — the title cliff, standing at 15 of the top 100
scoring zero for championships — was removed from the register by a later edit
the same day; the two refused repairs for it are still recorded there. The
analysis behind
them — the Hughes, Henderson and promotion-factor investigations, and the full
outcome write-ups — is only here, which is why these files are kept.

`analysis/CHART_PLAN.md` is here too. It was the plan the 2026-06 chart batch was
built from, already labelled historical, and kept live only because three code
comments cited it. Those comments now cite this copy.

`docs/CAREER_COVERAGE_2026-08-27.md` stayed live but lost the five findings it
restated from the methodology record, which holds them with the full tables and
confidence intervals the summary did not.

## Restoring

The expansion code is on the `fightmatrix-recursive-expansion-2026-08` branch
and in `_archive/20260831-repository-consolidation/`. Its data is not recoverable
from this repository: reproducing it means re-crawling the ids in
`stale_profile_ids.txt` and re-running that branch's loader.

Everything else here is rebuilt by a documented command — `build_database.py`
for the SQLite export, `refresh.py` for snapshot artifacts, `pytest` for the temp
trees.
