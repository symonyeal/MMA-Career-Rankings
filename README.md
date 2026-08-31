# Symon UFC Rank Engine

The Symon UFC Rank Engine turns fight history into explainable rankings for
three business questions: the value of a fighter's full career, the strength of
their best period, and their current competitive level. It is designed for
analysts, editors, and product teams that need a reproducible ranking with a
clear evidence trail—not a list assembled by opinion alone.

The latest generated tables are in [Published UFC Rankings](RANKINGS.md). That
publication records its snapshot, scope, score, and row counts beside the tables
so the release cannot be separated from its source facts.

## Business outputs

| Output | Business question | Measure |
| --- | --- | --- |
| All-time | What did the fighter's completed body of work amount to? | Public Legacy Score: career skill, championship results, and schedule strength |
| Prime | How strong was the fighter at their best? | Best fixed ten-year WHR window with at least 13 rated appearances |
| Prime (elite-tested) | Which of those peaks were actually proven? | The Prime score, restricted to fighters with at least 5 career wins over rated contenders who were themselves UFC-tested |
| Current skill | How strong is the fighter now? | Latest WHR skill estimate, with age and inactivity projection where used |
| Integrity board | How would stated policy discounts change the order? | A separate debit ledger on base rating points |
| Career Skill Mass | How much sustained skill sat above the field over time? | A diagnostic underneath the public score, not the public ranking |

All-time, Prime, and Current are alternative views of the same fight history.
They should not be added together. Integrity, dominance, market odds, and
opponent-context outputs are audits and explanations; they do not silently
alter the published rating likelihood.

## How the ranking is governed

- One authoritative fight table supplies every model path. A bout may be
  available from several corpora, but it is rated once using the preferred
  parse while retaining its source membership.
- The published skill trajectory uses method-aware Whole-History Rating (WHR).
  A causal Glicko-2 stream and binary WHR remain comparison models.
- Public Legacy Score is the public All-time board. Career Skill Mass remains a
  skill diagnostic and must not be promoted as the public board without a new
  top-100 audit.
- Men and women are ranked separately. No fight evidence connects the two
  populations, so a combined order would be determined by the prior rather
  than observed competition.
- Fighters below the evidence threshold are withheld. An abstention is not a
  low score and is never converted into an arbitrary rank.
- The elite-tested Prime board applies a second threshold, on proven record
  rather than volume: wins over opponents who were above the contender line and
  had a tested record of their own. The line and the win minimum are stated
  policy, not fitted values. The threshold gates who appears; it never changes
  the order, which stays the rating.
- Generated release facts and all four public tables are validated before the
  publication file is changed, preventing half-refreshed releases.

## Data coverage

The current published scope combines canonical UFCStats history, recovered
pre-unified UFC bouts, and staged major-promotion history from Sherdog. The
bounded FightMatrix profile cohort is retained as diagnostic evidence and can
be selected explicitly; it is not silently merged into the published scope.

`combined_fights.parquet` is the maximum-coverage evidence table. Its
`source_corpus` field identifies the preferred parse and
`available_in_corpora` records every corpus in which the bout was found. A
named run scope selects by membership, which prevents a shared bout from
disappearing merely because a higher-priority source supplied its final row.

Source ownership, licensing notes, and known coverage gaps are maintained in
[Source Matrix](data/SOURCE_MATRIX.md). Release history is maintained in
[Data Changelog](data/CHANGELOG.md).

## Important limitations

- Public Legacy is retrospective. Historical title-win quality can use a
  fighter's whole-history WHR trajectory, so it answers an all-time résumé
  question rather than “what was known on that date?”
- The schedule component is correlated with the number of credited ranked wins
  and currently has no annual cap. It should be read as résumé context, not an
  independent fourth skill model.
- The exposure factor is a declared organization mapping. It helps compare
  partially observed careers but remains a policy assumption, not a quantity
  identified solely by bout outcomes.
- Division and identity fields are partly inferred where source records are
  incomplete. Those inferences are audited, but they can affect division-based
  résumé context.
- Existing bootstrap intervals and tiers describe Career Skill Mass. They are
  not uncertainty intervals for Public Legacy Score and are labelled as a
  diagnostic in the notebook.
- Canonical UFC fight URLs distinguish legitimate same-night rematches.
  Non-UFC sources do not always provide an equivalent stable bout key, so an
  ambiguous same-day duplicate is conservatively collapsed.
- No model can recover fights absent from every admitted source. Coverage and
  identity exceptions therefore remain part of every release decision.

These are current boundaries, not invitations to repeat closed tuning loops.
The decision register in [Next Decisions](docs/NEXT_2026-08-28.md) records
options already tested or rejected.

## Use the project

Install the pinned Python dependencies with the machine's system Python:

```text
C:\Python314\python.exe -m pip install -r requirements.txt
```

Run the verification suite:

```text
C:\Python314\python.exe -m pytest -q
C:\Python314\python.exe -m ruff check .
```

Rebuild the generated public ranking publication from the current snapshot:

```text
C:\Python314\python.exe build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
```

Build the local query database safely. The builder assembles a sibling file and
promotes it only after all required tables and indexes succeed, preserving the
last known-good database if a rebuild fails.

```text
C:\Python314\python.exe build_database.py --snapshot-dir data/snapshots/2026-08-13
```

Regenerate the interactive notebook after source changes:

```text
C:\Python314\python.exe analysis/build_notebook.py
```

The full `refresh.py` workflow rebuilds source data, ratings, boards, release
notes, and the notebook. Review its source and scope arguments before use;
external retrieval and a new release build are deliberate operations.

## Project map

| Path | Purpose |
| --- | --- |
| `ratings/` | Rating engines, public score, board policy, uncertainty diagnostics |
| `loaders/` | Source ingestion, identity handling, and authoritative fight-table construction |
| `analysis/` | Business-facing charts and generated interactive notebook |
| `tests/` | Behavioral, regression, consistency, and smoke tests |
| `data/snapshots/<date>/` | Immutable-style release inputs and generated artifacts |
| `data/model_tuning/` | Held-out comparisons and top-100 audit evidence |
| `docs/` | Current methodology, coverage, and decision records |
| `_archive/` | Recoverable historical research, retired code, and stale generated material |

## Current technical records

- [Rating Layer and Public Ledger](docs/RATING_LAYER_AND_LEDGER_2026-08-28.md)
  explains the production skill layer, Public Legacy components, and audit
  separation.
- [Career Coverage](docs/CAREER_COVERAGE_2026-08-27.md) documents source
  completeness and the authoritative whole-career coverage rule.
- [Next Decisions](docs/NEXT_2026-08-28.md) is the active handoff and decision
  register, including closed options that should not be re-run without new
  evidence.
- [Published UFC Rankings](RANKINGS.md) is the generated business publication.

Historical design notes and retired experiments are preserved under
[`_archive/`](_archive/) with restoration instructions. They are evidence of
past work, not current operating guidance.
