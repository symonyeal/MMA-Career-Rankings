# Career-coverage repair, and the one authoritative fight table — 2026-08-27

Two changes moved material here. Both are recoverable: the binaries live under
`generated-data/`, which is deliberately git-ignored, and every one of them is
regenerable from the sources that remain in the repo.

## 1. The corpus carried two coverage rules

`majors` was built by enumerating seven promotions' cards by event and then
reading one Sherdog whole-career page per fighter — but that second pass ran
only over the 4,501 fighters who had appeared on a PRIDE / WEC / Strikeforce /
Affliction / Bellator / RIZIN card. The UFCStats roster was never expanded, so a
fighter who reached the UFC through one of those promotions had their whole
regional record in the model and a fighter who did not had almost none of it.
Measured over the 1,825 fighters with three or more UFC bouts: only 547 (30.0%)
had a whole-career page, and median recorded pre-UFC bouts was **13** for those
against **1** for the other 1,278.

That is a rating defect rather than a reporting one. A low-loss Bradley–Terry
record has no interior maximum, so the equilibrium sits near
`opponent_level + 173.72 * ln(2k/v)` and `k` — how many of a fighter's bouts the
corpus happens to hold — becomes rating points. `build_sherdog_careers.py` now
completes the coverage, `loaders/career_coverage.py` states the property as a
number, and `tests/test_career_coverage.py` fails on the shape that broke the
board.

**Everything under `generated-data/model-tuning/` was fitted on the corpus with
the asymmetry live.** Their conclusions are conditioned on the defect and must
not be cited as current:

| directory | what it measured | why it is archived |
|---|---|---|
| `virtual-games/` | the `WHR_VIRTUAL_GAMES` ladder | the sweep's failure mode was partly the coverage term it could not see |
| `whr-prior/` | prior-mass ladder and backtest | selected on the pre-repair corpus |
| `core-ablation/` | paired estimator ablation | same |
| `causal-career/` | causal-filter career comparison | same |
| `cross-era-bridge/` | cross-era bridge fits | same |
| `rules_era/` | the `RULES_ERA_WEIGHT` sweep | same; `build_rules_era_sweep.py` regenerates it |
| `org-strength/` | candidate organisation weights | same; `build_org_strength_audit.py` regenerates it |
| `prequential/` | scope-comparison folds | predates the repair and the current cache schema |

Re-run the builder named beside each one against a repaired snapshot before
using any of these numbers again.

## 2. One authoritative fight table

`combined_fights.parquet` is now written once at **maximum coverage** — every
corpus the snapshot staged — and a named scope is a row filter on its
`source_corpus` column rather than a second merge of the same sources. Verified
on `data/snapshots/2026-08-13`: selecting `majors,pre_unified` out of the
maximum-coverage table returns exactly the same 67,920 model bouts as merging
that scope directly, zero rows different on either side.
`tests/test_combined_fights.py` pins that equality, the shared-bout precedence,
and the guard that stops a later build from narrowing the artifact once its
inputs are archived.

Moved here as a result:

| file | why |
|---|---|
| `generated-data/snapshots/2026-08-13/crossorg_fights.fightmatrix-public.parquet` | byte-identical to `fightmatrix_crossorg_fights.parquet` (same MD5), a straight duplicate |
| `generated-data/snapshots/2026-08-13/majors_fights.parquet` | staged build input; every row is in `combined_fights.parquet` |
| `generated-data/snapshots/2026-08-13/pre_unified_fights.parquet` | staged build input; every row is in `combined_fights.parquet` |
| `generated-data/snapshots/2026-08-13/fightmatrix_crossorg_fights.parquet` | staged build input; every row is in `combined_fights.parquet` |

The three staged parquets are **inputs, not outputs**. A full
`refresh.py` re-stages them from the sources that remain in the repo
(`data/external/sherdog/crossorg_bouts.parquet`, the snapshot's own
`_excluded_bouts.csv`, and `data/external/fightmatrix/`), so archiving them here
removes a duplicated copy from the published snapshot, not the ability to
rebuild. `write_combined_fights` refuses to overwrite the authoritative table
with a narrower one, so a rating run against this snapshot keeps the whole-sport
corpus even though the staged pieces are no longer beside it.

## Restoring

Copy any file back to the path named in the table and re-run the builder that
consumes it. Nothing here is required by the current pipeline.
