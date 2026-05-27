# Symon UFC Rank Engine

An MMA ranking lab for all-time, current, and division-level UFC analysis.

The project builds a local ranked snapshot from UFCStats/Greco, enriches it
with odds and comparison sources, adds Sherdog-derived PRIDE/Strikeforce/WEC
bouts, and presents the results in a Plotly/Jupyter notebook with short,
audience-friendly labels.

## Open This First

Run the interactive notebook:

```bash
.venv/bin/jupyter lab analysis/notebook.ipynb
```

Or rebuild it after code changes:

```bash
.venv/bin/python analysis/build_notebook.py
```

The notebook auto-loads the newest snapshot under `data/snapshots/`.

## Rating Labels

| Label | Use it for | What it means |
|---|---|---|
| Now | Current form | Latest rating after the fighter's most recent bout. |
| Peak | Best 5 years | A fighter's strongest five-year run. |
| Prime | Best 10 years | A fighter's strongest proven decade. |
| Wins | Simple results | Win, loss, draw only. |
| Finishes | Result plus method | Rewards how the fight ended. |
| Clean | Integrity checked | Adjusts PED, DQ, and missed-weight wins. |
| Strength | Context checked | Adds opponent, odds, rank, title, and weight-class context. |
| Complete | Best default | Clean + Strength together. |
| Legacy | Broad all-time | Whole-history smoother for era-spanning lists. |

Recommended audience defaults:

- **Now + Complete** for current rankings.
- **Prime + Complete** for all-time debate.
- **Peak + Complete** for short-run dominance.
- **Legacy** when comparing old eras to modern eras.

This matters for cases like Israel Adesanya: his recent losses pull down
**Now**, while his title-run resume still keeps him high in **Prime**.

## Notebook Views

The notebook is built to work like a dashboard:

- Select **Now**, **Peak**, **Prime**, or **Legacy**.
- Select **Wins**, **Finishes**, **Clean**, **Strength**, or **Complete**.
- Filter leaderboards by division.
- Compare rank movement before and after cross-organization enrichment.
- Trace a fighter's career line against the selected rating view.
- Switch division charts by year, top-N depth, and selected divisions.
- View division strength over time for comparative performance.

Charts follow a consulting-style presentation pattern: clear title, short
labels, focused color, direct takeaway, and minimal chart noise.

## Current Snapshot

Production snapshot: `data/snapshots/2026-05-27`

Included in the latest run:

- 743 UFC events.
- 8,346 rated UFC fights.
- 1,002 PRIDE/Strikeforce/WEC cross-organization bouts from Sherdog.
- Cross-org method, round/time, title flag, inferred UFC division, and
  per-fight caliber weight.
- 2,884 rated fighters.
- Local SQLite export at `data/ufc_rank_engine.sqlite`.

Cross-org weighting is per fight, not a blanket promotion discount. Elite
vs elite bouts outside the UFC count heavily; bouts involving unproven
fighters count less.

## Rebuild Commands

Use these from the project root.

Build the cross-org snapshot:

```bash
.venv/bin/python build_crossorg.py --base "data/snapshots/2026-05-13" --out "data/snapshots/2026-05-27"
```

Run the ratings:

```bash
.venv/bin/python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-05-27"
```

Build SQLite:

```bash
.venv/bin/python build_database.py --snapshot-dir "data/snapshots/2026-05-27"
```

Run tests:

```bash
.venv/bin/python -m pytest -q
```

## Project Layout

```text
analysis/              Notebook builder and Plotly charts
build_crossorg.py      Sherdog PRIDE/Strikeforce/WEC enrichment builder
build_database.py      SQLite export builder
data/SOURCE_MATRIX.md  Source and field audit
docs/archive/          Older audits, logs, and reports
loaders/               Source loaders and identity helpers
ratings/               Rating engine, adjustments, peaks, and WHR
tests/                 Loader, engine, database, and visualization tests
```

## Source Notes

Primary UFC fight data comes from the Greco UFCStats CSV snapshot. External
comparison and context sources include UFC-DataLab, FightMatrix, mdabbert odds,
and Sherdog fighter histories for PRIDE/Strikeforce/WEC bouts.

Raw snapshots, large caches, and generated SQLite files are intentionally
ignored by Git. The code and notebook can regenerate the local outputs.

Detailed source lineage lives in `data/SOURCE_MATRIX.md`.

## Archived Material

Older audit notes, ranking exports, and development handoff logs were moved to
`docs/archive/` so the root stays presentable while preserving the project
history.
