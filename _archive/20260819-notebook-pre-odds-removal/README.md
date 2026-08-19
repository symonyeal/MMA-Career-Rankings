# notebook.ipynb before the 2026-08-18/19 market-weighting removal

Copy of `analysis/notebook.ipynb` taken immediately before the odds-impact panel
was removed from it. The file carried uncommitted user edits at the time, so it
was archived rather than regenerated from `analysis/build_notebook.py`; only the
cells referencing the deleted `odds_impact_chart` / `mkt_impact` were changed.

Why the panel went: `perf_factor_odds` was computed, stored and plotted but was
never a term in the signal that produces `performance_weight`. The chart
described a market-value adjustment that did not exist. See
`docs/DIFFERENTIATOR_AUDIT_2026-08-18.md`.
