# Top-100 era-skew investigation archived 2026-08-26

This directory preserves the complete 2026-08-21 executable investigation:
the generated notebook, its builder, computation and visualization modules,
and its investigation-only tests.

The investigation correctly established that scope truncation caused the
modern-era skew. It is no longer a live tool because the published snapshot now
uses `majors,pre_unified`, while the notebook initialized UFC-only fights beside
whole-sport history and used fixed cache names from the earlier fit. Leaving it
under `analysis/` would make a historical result look safe to rerun against the
current data contract.

No conclusion or source evidence was deleted. The old computed parquet caches
are preserved in `_archive/20260826-stale-generated-data/generated-data/`.
The current score and scope contracts are the repository `README.md` and
`docs/BOARD_AND_IDENTIFICATION_2026-08-25.md`.
