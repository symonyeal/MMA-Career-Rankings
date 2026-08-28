# Cohesive engine pass - 2026-08-25

> **CORRECTED LATER THE SAME DAY — read this first.**
>
> The board-selection change recorded below was a **regression** and has been
> reverted. This pass demoted `public_legacy_score` to a "sanity ledger" and
> promoted raw `symon_career_skill_mass` to the default core board. That undid
> the repair of 2026-08-24 (`PUBLIC_PERCEPTION_REPAIR_2026-08-24.md`) and put
> Usman Nurmagomedov 6th, Yaroslav Amosov 7th and Josh Barnett 8th all-time
> again — the exact failure that repair existed to fix.
>
> Measured on `data/snapshots/2026-08-13`, scope `majors,pre_unified`:
>
> | metric | this pass | after revert |
> |---|---:|---:|
> | top-25 unanchored names | 7 | **0** |
> | top-10 active external unanchored | Usman Nurmagomedov | **none** |
> | external-only in top 100 | 20 | **7** |
> | public anchors missing from top 100 | 23 | **8** |
>
> **Career Skill Mass is a skill diagnostic, not the public board.** See
> `build_boards.CORE_RATING_CANDIDATES` for the standing comment.
>
> The rest of this pass was kept: `loaders/combined_fights.py` (one deduped
> model-input table) and the removal of the duplicated `symon_peak_score` are
> genuine consolidations and remain in production.

## Current contract

The production model now has one combined model-input table and two public
score surfaces:

| Surface | Artifact/column | Role |
|---|---|---|
| Combined fights | `combined_fights.parquet` + `combined_fights_summary.json` | One deduped model table for the selected scope, preserving the union of source columns. |
| All-time | `public_legacy_score` | The default core board, restored after the revert described above. |
| Prime | `symon_prime_score` | Fixed 10-year WHR period score. |
| Skill diagnostic | `symon_career_skill_mass` | The retrospective career functional. It is the skill input to the board, never the board. |

`symon_peak_score` is no longer produced by `ratings.rate_snapshot.run()`,
offered in the public notebook selector, or exposed as a named helper. The
generic `symon_period_score()` remains for research windows.

## Combined table result

On `data/snapshots/2026-08-13` with scope `majors,pre_unified`:

| Metric | Value |
|---|---:|
| rows | 68,415 |
| model bouts | 67,920 |
| duplicate fingerprints | 0 |
| date range | 1980-04-25 to 2026-08-23 |
| source corpora | majors 59,684; UFC 8,479; pre_unified 252 |

The scope guard dropped 4,127 repeated/overlapping rows from `majors` and one
repeated row from `pre_unified` before the table was written.

## Org-weight audit

Production remains unit-weighted: every admitted bout has `org_weight = 1.0`.
The old FightMatrix participant-caliber weights still count as research only
because they use eventual UFC-career information.

`build_org_strength_audit.py` now refits Career Skill Mass under explicit
candidate families:

| Model | Top-25 unanchored | Top-100 external-only | Severe over | Severe under | Verdict |
|---|---:|---:|---:|---:|---|
| `unit` | 8 | 20 | 3 | 4 | production baseline |
| `constant_non_ufc_0.75` | 8 | 16 | 3 | 6 | reduces external-only count but worsens underplacement |
| `bridge_floor_0.5_prior_60` | 8 | 21 | 3 | 5 | bridge support is high, so weights stay near unit |
| `bridge_floor_0.35_prior_60` | 7 | 21 | 3 | 5 | one fewer top-25 unanchored, but no broad repair |

The bridge-reliability formula is:

`floor + (1 - floor) * n_eff / (n_eff + prior)`,
where `n_eff = sqrt(crossover_fighters * crossover_bouts)`.

That is an evidence-support weight, not a prestige ladder. On this snapshot it
does not justify replacing the unit model. The main remaining outliers are not
fixed by a simple organization scalar; they point to the career-vs-public-resume
gap and to non-UFC title/resume context that should stay visible as sanity
diagnostics.

## Rebuilt artifacts

Generated or refreshed locally:

- `data/snapshots/2026-08-13/combined_fights.parquet`
- `data/snapshots/2026-08-13/combined_fights_summary.json`
- `data/snapshots/2026-08-13/completeness_gated_board.parquet`
- `data/model_tuning/top100-audit/*`
- `data/model_tuning/org-strength/2026-08-13/*`

Full test suite after the pass: **388 passed**.
