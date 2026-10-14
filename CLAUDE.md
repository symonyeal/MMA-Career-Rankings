# Working contract

Read this before changing anything. [README](README.md) explains what the rankings say and how
they are built; [the decision register](docs/DECISIONS.md) records what was decided, what was
tried and refused, and what is still open. This file states the rules a change must not break.

Codex reads the same file through [AGENTS.md](AGENTS.md).

## Always on

| Rule | Reason |
| --- | --- |
| Quote no number you did not just produce. | A figure in a document is a claim about a run. If the run is not in front of you, the figure is a memory of one. |
| Say "did not resolve" when a test did not resolve. | A confidence interval that crosses zero is not a negative result, and reporting it as one invents a finding. |
| Count each fact once. | Career length already has a home. Anything else that grows with career length charges for the same thing twice. See the decision register. |
| A rating change passes a held-out prediction test. A score change cannot. | The score never predicts a fight, so it is argued from mechanism and checked against outside lists — and the check reports how much it can actually detect. |
| Check "Tested and refused" before proposing a model change. | Fifteen changes have already been measured and rejected there. Re-proposing one costs a day and ends the same way. |
| An external data source arrives with its licence and an `ATTRIBUTION.txt`. | These sources are redistributed inside this repository. A source whose licence is not beside it cannot be shown to be redistributable. |
| Everything a published board reads is committed: the snapshot folder whole, plus the Sherdog extracts beside the page store. Local caches hold nothing a rebuild needs. | Until 2026-10-14 the fit's inputs and the fitted ratings were gitignored. A second machine had to re-crawl the sources, came back with 43 fewer birth dates and no odds rows, and nothing failed. `tests/test_release_committed.py` now fails on a fresh clone, which is how CI runs. |
| A solver change ships only as a setting that defaults to the published behaviour. | The 2026-10-09 WHR repair replaced the solver outright, then the boards were refitted with it before any held-out test on production inputs. Every tuned constant had been set against the old solver, so the published boards changed and none of those constants had been re-checked. It is now `WHR_CENTER_EACH_PASS`; flip it after the test resolves, not before. |

## Re-score before you publish

`build_boards.py` publishes the `public_legacy_*` columns already stored in
`ratings_current.parquet`. It does not recompute them. A score or board change must re-score the
snapshot first, or the boards publish the old scores while the audit — which does recompute —
publishes the new ones, and the two disagree without saying so.

The full sequence is in [Rebuild and verify](docs/DECISIONS.md#rebuild-and-verify). The short
form, which every change ends with:

```text
python -m pytest -q
python -m ruff check .
python -m pip check
```

All three must be clean. They are also run by [CI](.github/workflows/ci.yml) on every push, because
between 2026-09-01 and 2026-09-22 the lint gate was documented but never enforced and drifted to
364 findings without anyone noticing.

## Prose register

Every markdown file here is plain business English — README, RANKINGS and everything in `docs/`,
not only the reader-facing pages. Explain a term once rather than assuming it. Never soften a
limitation while simplifying it: "that is us declining to rank them, not ranking them last" is
plainer than "an abstention", and just as firm. Nothing is dropped in the name of plainness —
every number, interval, named fighter and file path survives.

## Things that are not defects

- **`analysis/notebook.ipynb` is generated** by `analysis/build_notebook.py` and is excluded from
  linting. Edit the builder, not the artifact.
- **The blind `except Exception` in `loaders/`** is deliberate and carries a `noqa` saying why. A
  multi-day crawl must survive one bad page.
- **`date.today()` in the snapshot-label arguments** is a local calendar date, not an instant. It
  is not a missing time zone.
