# Stale project material archived 2026-08-26

This directory preserves superseded documentation, a redundant historical
archive that previously lived under `docs/archive/`, and the closed top-100
era-skew investigation. Nothing was deleted. Stale generated outputs and
disposable caches are recorded separately in
`../20260826-stale-generated-data/`.

The current operating contract is the repository `README.md`, with
`docs/BOARD_AND_IDENTIFICATION_2026-08-25.md` as the latest scoring decision
record.

## Superseded documents

The files in `docs/` were removed from the live documentation surface for the
following reasons:

| File | Why it is archived | Current replacement |
|---|---|---|
| `BLOCKERS_2026-08-24.md` | Mixed an investigation brief with later closure notes while retaining obsolete open-blocker labels. | `docs/BOARD_AND_IDENTIFICATION_2026-08-25.md` and the repository `README.md` |
| `COHESIVE_ENGINE_PASS_2026-08-25.md` | Recorded a same-day board regression that promoted raw Career Skill Mass and then had to be reverted. Its valid combined-input result is now part of the README contract. | Repository `README.md`; `docs/BOARD_AND_IDENTIFICATION_2026-08-25.md` |
| `DASHBOARD_CHARTS_AND_EXPANSION.md` | Described the retired multi-knob dashboard and chart architecture rather than the generated notebook now in production. | `analysis/build_notebook.py`, `analysis/notebook.ipynb`, and the repository `README.md` |
| `DIFFERENTIATOR_AUDIT_2026-08-18.md` | Historical audit of mechanisms and a UFC-only state that subsequent passes retired or replaced. | `docs/PRINCIPLED_CORE_EVOLUTION_2026-08-20.md` and the repository `README.md` |
| `INVESTIGATION_TOP100_ERA_SKEW.md` | Was explicitly a pre-investigation brief, not findings. The closed executable investigation is preserved beside it. | `investigation-top100-era-skew/`; `docs/BOARD_AND_IDENTIFICATION_2026-08-25.md` |
| `NEXT_2026-08-25.md` | Explicitly marked superseded and included a same-day change that was later reverted. | `docs/BOARD_AND_IDENTIFICATION_2026-08-25.md` |
| `OUTCOME_2026-08-24.md` | Published an obsolete score contract and ranking table replaced the following day. | Repository `README.md`; `docs/BOARD_AND_IDENTIFICATION_2026-08-25.md` |
| `PUBLIC_PERCEPTION_DISCREPANCY_PROMPT_2026-08-24.md` | Repair prompt whose work was completed. Its example rankings are no longer the live board. | `docs/BOARD_AND_IDENTIFICATION_2026-08-25.md` |
| `PUBLIC_PERCEPTION_REPAIR_2026-08-24.md` | Described the former flat title-resume and organisation-factor path replaced by per-opponent title pricing. | `docs/BOARD_AND_IDENTIFICATION_2026-08-25.md`; `ratings/legacy_resume.py` |
| `SESSION_2026-06-25_era_premium_dominance.md` | Session narrative for era-premium and dominance machinery subsequently refuted and retired. | `docs/PRINCIPLED_CORE_EVOLUTION_2026-08-20.md` |
| `STRATEGIC_AUDIT_2026-08-13.md` | Described an older UFC-only, era-premium, multi-control system. | Repository `README.md` |

## Consolidated historical archive

`legacy-docs-archive/` is the former `docs/archive/` directory, moved intact so
its files, including the historical workbook, remain recoverable together.
This removes the redundant second archive location without rewriting its
historical contents.

## Closed executable investigation

`investigation-top100-era-skew/` preserves the notebook, its builder and helper
modules, its visualization code, and its investigation-only tests. The cached
fits are in the generated-data archive. They were removed from the live surface
because they were built against the former UFC-only baseline and fixed cache
names; running them against the current whole-sport snapshot would mix scopes.

## Intentionally retained

- `analysis/CHART_PLAN.md` is explicitly labelled historical and is cited by
  live chart code and tests.
- Source, provenance, and FightMatrix documentation remain live because they
  describe inputs rather than a superseded scoring decision.
- Build drivers remain live because the README and reproducibility notes still
  invoke them.
- Expensive raw UFC, Sherdog, and FightMatrix source caches remain untouched.
