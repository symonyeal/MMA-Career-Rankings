# Superseded research drivers — archived 2026-08-25

Every file here is a **one-off research driver whose question is closed and
whose answer is already recorded** in `docs/` and in the shared memory base.
None of them is imported by `refresh.py`, by `tests/`, by `analysis/`, or named
in `README.md`. Archiving them does not change any published number: the full
suite is **388 passed** before and after.

They are kept rather than deleted because each one is the reproduction script
for a finding that is still load-bearing. If a finding is ever challenged, the
harness that produced it is here.

| File | Question it answered | Where the answer lives now |
|---|---|---|
| `build_age_drift_evaluation.py` | Does an empirical age-bucket WHR prior beat a driftless one? | **Yes, shipped.** `age_drift=True` is production; evidence in `data/model_tuning/age-drift/`; memory `ufc-aging-and-peak-deletion` |
| `build_cross_era_bridge.py` | Is the whole-career graph wide enough to compare eras? | **Yes** — B8 closed; narrowest adjacent-year bridge since 2000 is 340. Residual +5.20 pts/year remains named as unresolved |
| `build_crossorg.py` | Stage a cross-org snapshot | Superseded by `ratings/scope.py` + `loaders/combined_fights.py` |
| `build_crossorg_careers.py` | Whole-career ingestion for cross-org fighters | Superseded by `build_sherdog_majors.py` + `loaders/majors_scope.py` |
| `build_crossorg_weight_sweep.py` | Should a non-UFC bout carry a weight < 1? | **No.** Production is unit-weighted; the current form of this question is `build_org_strength_audit.py`; memory `ufc-crossorg-weight-and-scope` |
| `build_field_depth.py` | Persist division-year field depth | One-off persister; `ratings/field_depth.py` is still live and imported |
| `build_fightmatrix_expanded.py` | Does a bounded recursive FightMatrix crawl help? | Crawl complete, **never promoted**; memory `ufc-fightmatrix-depth-one-expansion` |
| `build_fightmatrix_public.py` | Build a local ranked-cohort FightMatrix copy | 36 lines; `loaders/fightmatrix_profiles.py` is still live via `refresh.py` |
| `build_fightmatrix_validation.py` | Compare experimental scopes to the UFC baseline | Superseded by `build_scope_prequential_comparison.py`, which is **kept** |
| `build_source_scope_comparison.py` | UFC-only vs FightMatrix-public source scope | 23 lines; same successor as above |
| `build_whr_prior_sweep.py` | Re-select `WHR_VIRTUAL_GAMES` on a gate containing the failure mode | **Not the fix.** See below |

## Why `build_whr_prior_sweep.py` is here

It was written on 2026-08-25 while diagnosing the top-100 board, on the theory
that the undefeated-thin-graph intruders (Usman Nurmagomedov 6th, Rajabali
Shaidullaev 30th, Vladyslav Rudniev 85th) were caused by `WHR_VIRTUAL_GAMES = 2`
being too weak to bound an unbounded likelihood.

The diagnosis of the *mechanism* was right and is recorded in
`Claude Status Reports/UFC_Top100_Who_Doesnt_Belong_2026-08-25.md`. **The
proposed fix was wrong**, for two reasons:

1. `v` was already selected by backtest on 2026-08-20 over {0,1,2,4,6,10}
   (`docs/PRIOR_MASS_AND_UNCERTAINTY_2026-08-20.md`). Every paired interval
   crossed zero; `v = 2` shipped on the stated tie-break *smallest prior mass
   that wins the point estimate*.
2. The real defect was never in the rating at all. It was that the **published
   board had been switched to raw `symon_career_skill_mass`**, a retrospective
   skill diagnostic, instead of `public_legacy_score`. Restoring the board
   selection fixed it outright: top-25 unanchored went 7 → **0**.

The driver does contain one genuinely new idea worth keeping: an
`unbeaten_entrant` prequential segment that isolates bouts where a side arrives
unbeaten over ≥8 wins — the only population the prior actually governs, and one
a UFC-only held-out set structurally cannot contain. If the prior is ever
revisited, start from that segment.

## What was deliberately NOT archived

- `build_top100_audit.py` — **essential.** It is the check that catches exactly
  the regression repaired on 2026-08-25. Run it after any board change and read
  `top25_unanchored_count`.
- `build_scope_prequential_comparison.py` — the live way to justify admitting a
  corpus, referenced by `docs/NEXT_2026-08-25.md`.
- `build_rules_era_sweep.py`, `build_uncertainty.py`, `build_sherdog_majors.py`,
  `build_prequential_evaluation.py`, `build_database.py`, `build_boards.py`,
  `build_org_strength_audit.py` — all referenced by `tests/`, `analysis/`,
  `refresh.py`, or `README.md`.
- Everything in `ratings/` and `loaders/`. An import-graph scan found only
  `loaders/crossorg_identity_audit.py` and `loaders/ufcstats_scrape.py` without
  a production importer, and both have tests or are the live scraper. **The
  library is not full of dead code**; the redundancy was in the drivers and in
  the board-selection regression.
