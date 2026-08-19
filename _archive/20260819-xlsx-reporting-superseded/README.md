# RANKINGS_SUMMARY.xlsx reporting pipeline — archived 2026-08-19

Four scripts that built and repaired an Excel deliverable:

- `build_rankings_sheets.py` — wrote the sheets
- `build_rankings_charts.py` — added native charts to each sheet
- `build_top20_insights.py` — fixed rank direction and added Top-20 charts
- `fix_xlsx_calcchain.py` — repaired the workbook's calcChain after the rewrites

**Why archived:** the interactive notebook replaced the workbook as the reporting
surface. None of the four is imported by any module or test, and the workbook they
maintain is not produced by any current pipeline. `data/snapshots/2026-05-13`
stays in place — it is still hardcoded by `tests/test_chart_additions.py` and
`tests/test_database_builder.py`, which is why the 2026-06-25 audit left these
scripts alone at the time.

Restoring is a plain `git mv` back to the repo root.
