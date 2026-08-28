# Public Perception Repair - 2026-08-24

## What Was Happening

The old published board used raw `symon_career_skill_mass` as if it were a
public all-time greatness score. That was incoherent.

`symon_career_skill_mass` is a retrospective skill-mass functional over WHR.
It is useful, but it backfills whole-career evidence into earlier years. Clean
or low-loss careers in less-tested external circuits could accumulate many
above-bar years, then appear beside UFC/Pride title legends as if the public
resume question had been answered.

The data was mostly there. The problem was how it was evaluated:

- UFC title and rank context lived in `performance_appearances.parquet`.
- Source title flags for PRIDE, WEC, Strikeforce, Bellator, RIZIN, etc. lived
  in the guarded merged source fight table.
- Organization normalization and tier metadata already existed.
- FightMatrix all-time public anchors already existed in the snapshot.

The board was not using those pieces together.

## Model Repair

The published all-time board now uses `public_legacy_score`, not raw career
skill mass.

`public_legacy_score` keeps raw skill mass visible, but scores:

- exposure-adjusted career skill mass;
- championship resume points;
- source-title rows discounted by evaluated organization context;
- pre-fight rank/champion context on wins, also exposure-adjusted.

UFC is the top organization context. PRIDE/Affliction/Strikeforce/WEC/Bellator
and lower tiers receive explicit, auditable context factors through the existing
organization normalizer. This is a board-layer evaluation only; it does not
change the WHR/Glicko likelihood or add hidden organization weights to the fit.

The board eligibility gate also gained a narrow public-legacy override for
proven UFC title resumes: fighters with at least 8 rating periods, at least 8
UFC bouts, and a real title resume can rank before the generic 13-period floor.
That keeps Ilia Topuria and Dricus Du Plessis from being treated as missing
when the current data clearly has them.

## Current Sanity Results

Generated artifacts:

- `data/snapshots/2026-08-13/completeness_gated_board.parquet`
- `data/model_tuning/top100-audit/top100_audit.csv`
- `data/model_tuning/top100-audit/public_anchor_missing_from_model_top100.csv`
- `data/model_tuning/top100-audit/top100_audit.json`

Top-25 gate after repair:

- unanchored top-25 names: 0
- active external-only top-10 names: 0
- Usman Nurmagomedov: rank 60
- Yaroslav Amosov: rank 51
- Josh Barnett: rank 27
- Patricio Freire: rank 17
- Ilia Topuria: rank 22
- Cristiane Justino: rank 20, after collapsing women's featherweight and
  external featherweight title labels into one public legacy division bucket

The top 10 is now:

1. Jon Jones
2. Georges St-Pierre
3. Daniel Cormier
4. Islam Makhachev
5. Alexander Volkanovski
6. Anderson Silva
7. Amanda Nunes
8. Jose Aldo
9. Demetrious Johnson
10. Randy Couture

## Remaining Failures

The repair is not perfect, and the audit now names the misses.

Severe/clear overplacements still requiring explanation:

- Ryan Bader: model rank 19 vs The 100 Greatest rank 63.
- Josh Barnett: model rank 27 vs The 100 Greatest rank 72.

Public underplacements still requiring feature work:

- Charles Oliveira: model rank 52 vs The 100 Greatest 34 and FightMatrix 29.
- Dustin Poirier: model rank 79 vs The 100 Greatest 35 and FightMatrix 25.
- Israel Adesanya: model rank 33 vs public anchors 12/15.

Public anchor names still outside the model top 100 include Alistair Overeem,
Rafael dos Anjos, Robert Whittaker, Ken Shamrock, Bas Rutten, Glover Teixeira,
Tony Ferguson, and Tom Aspinall.

## Next Work Split

Data bugs:

- Fill missing `org`/`weight_class` labels in the Sherdog whole-career extension
  where existing FightMatrix/profile artifacts have the missing metadata.
- Improve early-era title lineage where source rows have `is_title_fight` but
  blank division.

Missing features:

- Add prime-impact credit for elite contender streaks and title eliminator runs.
  This is likely why Charles Oliveira and Dustin Poirier remain low.
- Add public impact/pioneer handling only if the product label claims
  "greatest" rather than "best career resume."

Scoring-functional changes:

- Recheck external-title organization factors after metadata backfill.
- Stress-test Ryan Bader and Josh Barnett as explicit overplacement cases.

Product-label changes:

- Keep raw `symon_career_skill_mass` as a skill diagnostic, not the public board.
- Publish `public_legacy_score` with its decomposition columns so each surprising
  rank has a plain-English explanation.
