# Checking the published release

The release is the snapshot dated 2026-10-14. A fresh checkout can rebuild its
boards from committed inputs and fitted ratings without a crawl or a local
Sherdog page cache. Rebuilding a board uses the saved fit; it does not repeat
the fit or establish its predictive accuracy.

## How recent the sources are

Measured from `combined_fights.parquet` on 2026-10-20:

| Source corpus | Rows in the combined table | Latest recorded bout |
| --- | ---: | --- |
| UFC | 8,592 | 2026-10-10 |
| Sherdog major promotions and whole careers | 73,382 | 2026-08-30 |
| Fight Matrix profile additions | 781 | 2026-07-25 |
| UFC before the unified rules | 261 | 2000-09-22 |

These dates describe recorded bouts, not the dates each website was checked.
Duplicate resolution gives each retained row one source corpus, so the counts
are not the number of rows downloaded from each website. The published scope
is `majors,pre_unified`; the combined artifact also retains diagnostic rows.
The Fight Matrix profile summary records a fetch on 2026-10-14. It does not
make the Sherdog careers current through that date.

`refresh.py` refreshes UFC inputs and Fight Matrix profiles. It does not crawl
Sherdog careers. In particular, this release does not establish complete
non-UFC coverage after 2026-08-30. Source terms and the accepted redistribution
limits remain in the snapshot's `ATTRIBUTION.txt` and the source folders.

## Rebuild the boards from a fresh checkout

Install `requirements.txt` using the Python environment you intend to check.
Choose a persistent output directory outside the snapshot, then run:

```text
python check_release.py
python build_boards.py data/snapshots/2026-10-14 --scope majors,pre_unified --out-dir /path/to/persistent/rebuilt
python -m pytest -q
python -m ruff check .
python -m pip check
```

On 2026-10-20, a separate checkout containing only committed files rebuilt
the men's and women's All-time, Prime and Current parquet tables. Comparing
each complete table with `pandas.testing.assert_frame_equal(...,
check_exact=True)` found exact values, column types and row order in all six.
This check used revision `acf3128`; it did not re-score or refit the snapshot.
The solver, score weights and published rankings were unchanged.

To repeat the comparison, read each of `completeness_gated_board.parquet`,
`prime_elite_board.parquet` and `current_board.parquet`, and its `_women`
counterpart, from the snapshot and the new output directory. Pass each pair
to the assertion above. This catches changed rows and ordering as well as
changed totals.

## Predictive evidence has a separate scope

The earlier prediction results must not be read as a fresh evaluation of the
2026-10-14 fit. The published `whr` variant must be fitted using only bouts
before each held-out event; predictions from the full saved history would
allow later fights to influence the result.

The existing workflow can evaluate this configuration without modifying the
release:

```text
python build_prequential_evaluation.py data/snapshots/2026-10-14 --variants whr --events 40 --calibration-events 40 --scope majors,pre_unified --out-dir /path/to/persistent/evaluation --artifact-dir /path/to/persistent/evaluation
```

That run requires repeated full-history fits and was not completed during
the bounded reproduction check. No solver promotion, predictive improvement
or new calibration claim follows from the board comparison. The `canonical`
variant evaluates the causal Glicko baseline; it cannot certify the published
WHR model even when it reads the same snapshot and scope.

A bounded baseline run completed on 2026-10-20 using the published scope,
12 recent held-out events and 12 earlier calibration events. The held-out
events ran from 2026-08-08 through 2026-10-10; 92 distinct bouts remained
after requiring three earlier fights for each fighter. The causal Glicko
baseline's raw log loss was 0.728763, against 0.693147 for a constant 50%
forecast. Its temperature-calibrated log loss was 0.757909. Lower is better.
This sample is below the configured 200-bout floor for conclusions and
does not establish an advantage for either estimator. No WHR predictions
were computed in this run. [The saved evidence](release-evaluation-2026-10-20.json)
records the command, input fingerprint, scope, sample counts and all overall
metrics; the release snapshot was not modified.
