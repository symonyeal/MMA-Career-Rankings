# Symon UFC Rank Engine

The Symon UFC Rank Engine turns fight history into explainable rankings for
three business questions: the value of a fighter's full career, the strength of
their best period, and their current competitive level. It is designed for
analysts, editors, and product teams that need a reproducible ranking with a
clear evidence trail—not a list assembled by opinion alone.

The all-time top 100 and the elite-tested Prime 50 are published below under
[Published rankings](#published-rankings). Every generated table, including the
women's boards, is in [Published UFC Rankings](RANKINGS.md). Both documents
record the snapshot, scope, score, and row counts beside the tables so a release
cannot be separated from its source facts.

## Business outputs

| Output | Business question | Measure |
| --- | --- | --- |
| All-time | What did the fighter's completed body of work amount to? | Public Legacy Score: career skill, championship results, and schedule strength |
| Prime | How strong was the fighter at their best? | Their strongest ten-year stretch, which must contain at least 13 rated bouts |
| Prime (elite-tested) | Which of those peaks were actually proven? | The Prime score, restricted to fighters who beat at least 5 rated contenders *during that same ten-year stretch* |
| Current skill | How strong is the fighter now? | Their latest estimated level, adjusted for age and for time out of competition |
| Integrity board | How would stated policy discounts change the order? | A separate, itemised deduction against a fighter's rating, shown with the reason for each |
| Career Skill Mass | How much sustained skill sat above the field over time? | A diagnostic underneath the public score, not the public ranking |

All-time, Prime, and Current are alternative views of the same fight history.
They should not be added together. Integrity, dominance, market odds, and
opponent-context outputs are audits and explanations; they do not silently
alter the published rating likelihood.

## Published rankings

The two headline boards are published here. The full release — the women's
boards and the ungated Prime top 100 — is in
[Published UFC Rankings](RANKINGS.md). Both documents are written by the same
`build_boards.py` run from one snapshot, so the tables below cannot drift from
the publication or from the release facts they were built with.

<!-- PUBLICATION:RELEASE:BEGIN -->

| Release fact | Value |
| --- | ---: |
| Snapshot | 2026-08-13 |
| Published scope | majors,pre_unified |
| Published score | public_legacy_score |
| Rated bouts | 80,697 |
| Rated fighters | 33,692 |
| Maximum-coverage fight rows | 82,171 |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

What did the fighter's completed body of work amount to? Public Legacy Score
combines sustained career skill, championship results, and schedule strength.
The component columns are the business explanation of the total: they are
contributions to one score, not separate rankings.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Skill | Title | Schedule |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | 2854.6 | 1000.0 | 1000.0 | 854.6 |
| 2 | Georges St-Pierre | 2207.8 | 637.1 | 570.7 | 1000.0 |
| 3 | Demetrious Johnson | 1840.6 | 391.7 | 637.4 | 811.5 |
| 4 | Jose Aldo | 1609.1 | 397.9 | 593.6 | 617.6 |
| 5 | Daniel Cormier | 1589.0 | 477.8 | 553.3 | 557.8 |
| 6 | Islam Makhachev | 1576.6 | 648.6 | 642.4 | 285.5 |
| 7 | Alexander Volkanovski | 1311.3 | 262.7 | 587.6 | 460.9 |
| 8 | Anderson Silva | 1297.7 | 205.3 | 489.6 | 602.8 |
| 9 | Matt Hughes | 1237.9 | 165.1 | 410.5 | 662.3 |
| 10 | Stipe Miocic | 1210.3 | 258.0 | 547.9 | 404.4 |
| 11 | Max Holloway | 1186.3 | 80.6 | 310.8 | 795.0 |
| 12 | Dominick Cruz | 1134.6 | 239.5 | 445.7 | 449.5 |
| 13 | Khabib Nurmagomedov | 1126.4 | 586.6 | 311.3 | 228.5 |
| 14 | Randy Couture | 1044.0 | 22.7 | 196.7 | 824.6 |
| 15 | Francis Ngannou | 992.8 | 336.4 | 306.8 | 349.7 |
| 16 | Lyoto Machida | 975.9 | 260.2 | 123.1 | 592.6 |
| 17 | Aljamain Sterling | 971.3 | 144.4 | 325.9 | 501.0 |
| 18 | Chuck Liddell | 960.4 | 247.9 | 100.4 | 612.2 |
| 19 | Ilia Topuria | 954.4 | 342.2 | 379.3 | 232.9 |
| 20 | Cain Velasquez | 930.0 | 193.5 | 258.9 | 477.7 |
| 21 | Israel Adesanya | 911.0 | 176.1 | 326.7 | 408.2 |
| 22 | Fedor Emelianenko | 900.8 | 307.4 | 216.2 | 377.2 |
| 23 | Dan Henderson | 886.6 | 302.4 | 30.6 | 553.6 |
| 24 | Patricio Freire | 874.2 | 227.3 | 302.3 | 344.6 |
| 25 | BJ Penn | 827.0 | 58.7 | 225.5 | 542.9 |
| 26 | Merab Dvalishvili | 824.2 | 68.9 | 332.4 | 423.0 |
| 27 | Alex Pereira | 790.4 | 60.0 | 262.8 | 467.6 |
| 28 | Justin Gaethje | 778.5 | 142.3 | 276.4 | 359.8 |
| 29 | Joseph Benavidez | 754.5 | 288.7 | 0.0 | 465.7 |
| 30 | Henry Cejudo | 750.5 | 99.8 | 269.4 | 381.4 |
| 31 | Quinton Jackson | 722.8 | 62.7 | 92.6 | 567.6 |
| 32 | Benson Henderson | 709.1 | 75.2 | 250.8 | 383.1 |
| 33 | Ryan Bader | 705.2 | 79.7 | 70.9 | 554.7 |
| 34 | Frankie Edgar | 700.0 | 95.5 | 80.9 | 523.7 |
| 35 | Petr Yan | 684.5 | 115.8 | 202.2 | 366.4 |
| 36 | Vitor Belfort | 684.1 | 128.9 | 30.9 | 524.2 |
| 37 | Josh Barnett | 680.1 | 216.5 | 21.2 | 442.4 |
| 38 | Junior Dos Santos | 678.5 | 112.8 | 165.6 | 400.1 |
| 39 | Fabricio Werdum | 676.4 | 64.8 | 153.9 | 457.7 |
| 40 | Kamaru Usman | 670.2 | 52.6 | 200.5 | 417.1 |
| 41 | Khamzat Chimaev | 667.2 | 360.6 | 108.6 | 198.0 |
| 42 | Chris Weidman | 660.9 | 83.4 | 183.8 | 393.6 |
| 43 | Charles Oliveira | 655.2 | 60.2 | 130.4 | 464.6 |
| 44 | Tyron Woodley | 615.5 | 34.2 | 126.6 | 454.7 |
| 45 | Antonio Rodrigo Nogueira | 611.9 | 204.8 | 16.3 | 390.9 |
| 46 | TJ Dillashaw | 602.2 | 37.3 | 103.8 | 461.1 |
| 47 | Dricus Du Plessis | 592.2 | 189.7 | 138.3 | 264.2 |
| 48 | Mauricio Rua | 590.9 | 88.6 | 130.8 | 371.5 |
| 49 | Eddie Alvarez | 554.0 | 51.1 | 156.0 | 346.9 |
| 50 | Rashad Evans | 545.3 | 94.0 | 35.6 | 415.7 |
| 51 | Deiveson Figueiredo | 538.0 | 127.5 | 66.8 | 343.7 |
| 52 | Conor McGregor | 521.7 | 21.0 | 264.0 | 236.7 |
| 53 | Mirko Filipovic | 508.6 | 44.3 | 73.5 | 390.8 |
| 54 | Luke Rockhold | 507.8 | 44.6 | 84.9 | 378.3 |
| 55 | Robbie Lawler | 498.0 | 10.0 | 92.6 | 395.4 |
| 56 | Ciryl Gane | 497.9 | 303.9 | 77.5 | 116.5 |
| 57 | Vadim Nemkov | 495.4 | 169.8 | 172.3 | 153.3 |
| 58 | Tito Ortiz | 487.5 | 162.4 | 75.4 | 249.6 |
| 59 | Wanderlei Silva | 487.1 | 249.7 | 67.5 | 169.9 |
| 60 | Michael Chandler | 475.0 | 64.9 | 188.2 | 221.9 |
| 61 | Rich Franklin | 472.5 | 173.5 | 35.0 | 264.0 |
| 62 | Sean Strickland | 471.6 | 66.0 | 177.4 | 228.2 |
| 63 | Movsar Evloev | 465.5 | 289.2 | 0.0 | 176.3 |
| 64 | Yoel Romero | 454.2 | 44.3 | 0.0 | 410.0 |
| 65 | Leon Edwards | 453.9 | 6.9 | 172.8 | 274.3 |
| 66 | Frank Mir | 445.5 | 1.1 | 130.6 | 313.8 |
| 67 | Brandon Moreno | 444.2 | 3.5 | 117.3 | 323.4 |
| 68 | Dustin Poirier | 436.5 | 44.0 | 137.9 | 254.5 |
| 69 | Alistair Overeem | 428.1 | 6.4 | 2.8 | 418.8 |
| 70 | Rafael Dos Anjos | 428.1 | 1.5 | 77.6 | 348.9 |
| 71 | Urijah Faber | 424.5 | 130.3 | 6.9 | 287.3 |
| 72 | Anthony Pettis | 423.4 | 15.3 | 199.1 | 208.9 |
| 73 | Takanori Gomi | 415.6 | 135.6 | 0.0 | 280.0 |
| 74 | Jussier Formiga | 408.8 | 66.4 | 0.0 | 342.4 |
| 75 | Robert Whittaker | 386.9 | 32.3 | 66.6 | 288.0 |
| 76 | Renan Barao | 382.4 | 44.2 | 149.2 | 189.0 |
| 77 | Matt Serra | 382.3 | 20.7 | 218.2 | 143.4 |
| 78 | Mark Coleman | 378.0 | 14.1 | 174.6 | 189.3 |
| 79 | Kyoji Horiguchi | 376.9 | 165.4 | 30.9 | 180.6 |
| 80 | Sean Sherk | 374.2 | 141.3 | 54.6 | 178.3 |
| 81 | Gegard Mousasi | 373.1 | 81.1 | 94.6 | 197.5 |
| 82 | Joshua Van | 369.8 | 78.4 | 152.0 | 139.4 |
| 83 | Shavkat Rakhmonov | 367.8 | 301.9 | 0.0 | 65.9 |
| 84 | Phil Davis | 361.7 | 126.5 | 27.1 | 208.1 |
| 85 | Anthony Johnson | 361.4 | 41.6 | 0.0 | 319.7 |
| 86 | Sean O'Malley | 361.0 | 80.3 | 107.3 | 173.4 |
| 87 | Chael Sonnen | 360.3 | 18.4 | 0.0 | 341.9 |
| 88 | Tim Sylvia | 358.5 | 16.3 | 115.3 | 226.8 |
| 89 | Demian Maia | 357.4 | 121.1 | 0.0 | 236.3 |
| 90 | Sergio Pettis | 349.2 | 6.5 | 116.5 | 226.2 |
| 91 | Donald Cerrone | 336.5 | 35.7 | 0.0 | 300.8 |
| 92 | Hayato Sakurai | 334.4 | 68.4 | 0.0 | 266.0 |
| 93 | Beneil Dariush | 327.4 | 7.1 | 0.0 | 320.3 |
| 94 | Ricardo Arona | 318.6 | 114.2 | 0.0 | 204.4 |
| 95 | Jacare Souza | 318.6 | 76.8 | 0.0 | 241.7 |
| 96 | Johnny Eblen | 313.3 | 173.9 | 71.0 | 68.4 |
| 97 | Michael Bisping | 313.1 | 34.0 | 55.0 | 224.1 |
| 98 | Jake Shields | 311.9 | 23.5 | 46.1 | 242.3 |
| 99 | Ben Askren | 310.6 | 127.5 | 90.9 | 92.2 |
| 100 | Jiri Prochazka | 310.1 | 49.2 | 22.0 | 239.0 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

How strong was the fighter at their best, counting only peaks that were
actually proven? Prime is the best fixed ten-year rating window with at least
13 rated appearances. The elite-tested board adds one requirement about **who
the fighter beat, and when**: at least **5 wins over contenders inside that
same ten-year stretch**, where a contender was rated **1750 or higher** at the
time of the bout *and* had a tested record of its own — at least 8 UFC bouts.
Wins after the stretch ends do not count towards it; a later victory cannot
prove an earlier peak.

The line and the win minimum are stated policy, not fitted values. The
threshold gates who appears; it never changes the order, which stays the
rating. 78 men qualify, so this top 50 fills. Only 2 women qualify, which is a
fact about corpus depth rather than about the fighters — see
[Published UFC Rankings](RANKINGS.md) for that board and the reasoning behind
both halves of the opponent test.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Score | Elite wins |
| ---: | --- | ---: | ---: |
| 1 | Jon Jones | 2207.8 | 12 |
| 2 | Islam Makhachev | 2171.4 | 9 |
| 3 | Ilia Topuria | 2111.7 | 5 |
| 4 | Georges St-Pierre | 2073.3 | 11 |
| 5 | Alexander Volkanovski | 2047.2 | 9 |
| 6 | Francis Ngannou | 2041.5 | 7 |
| 7 | Vadim Nemkov | 2027.5 | 5 |
| 8 | Stipe Miocic | 2003.4 | 6 |
| 9 | Dricus Du Plessis | 2000.9 | 6 |
| 10 | Kamaru Usman | 1980.9 | 6 |
| 11 | Jose Aldo | 1977.0 | 7 |
| 12 | Demetrious Johnson | 1974.0 | 6 |
| 13 | Max Holloway | 1961.7 | 9 |
| 14 | Alex Pereira | 1961.1 | 7 |
| 15 | Chris Weidman | 1957.0 | 7 |
| 16 | Charles Oliveira | 1949.9 | 7 |
| 17 | Dominick Cruz | 1949.5 | 5 |
| 18 | Anthony Johnson | 1938.7 | 6 |
| 19 | Aljamain Sterling | 1929.7 | 7 |
| 20 | Dustin Poirier | 1927.5 | 5 |
| 21 | Yoel Romero | 1925.4 | 5 |
| 22 | Anderson Silva | 1925.1 | 11 |
| 23 | Sean Strickland | 1917.6 | 9 |
| 24 | Merab Dvalishvili | 1911.6 | 8 |
| 25 | Robert Whittaker | 1899.0 | 8 |
| 26 | Alexander Volkov | 1897.6 | 7 |
| 27 | Alexandre Pantoja | 1867.4 | 5 |
| 28 | Nassourdine Imavov | 1846.5 | 6 |
| 29 | Jake Shields | 1844.7 | 6 |
| 30 | Quinton Jackson | 1830.8 | 5 |
| 31 | Rafael Dos Anjos | 1801.7 | 6 |
| 32 | Neil Magny | 1798.9 | 6 |
| 33 | Jan Blachowicz | 1797.9 | 6 |
| 34 | Thiago Santos | 1784.6 | 5 |

<!-- BOARD:ELITEPRIME50:END -->

## How the ranking is governed

- One authoritative fight table supplies every model path. A bout may be
  available from several corpora, but it is rated once using the preferred
  parse while retaining its source membership.
- A fighter's level over time is estimated from their entire record at once,
  rather than updated fight by fight, and how a bout ended counts towards the
  result rather than only who won. Two simpler models are kept alongside as
  comparisons. The method is documented in
  [Rating Layer and Public Ledger](docs/RATING_LAYER_AND_LEDGER_2026-08-28.md).
- Public Legacy Score is the public All-time board. Career Skill Mass remains a
  skill diagnostic and must not be promoted as the public board without a new
  top-100 audit.
- Men and women are ranked separately. No fight evidence connects the two
  populations, so a combined order would be determined by the prior rather
  than observed competition.
- Fighters below the evidence threshold are withheld. An abstention is not a
  low score and is never converted into an arbitrary rank.
- Every published table and the release facts beside it are checked before
  either document is rewritten, so a release is never left half-updated.

## Data coverage

The current published scope combines canonical UFCStats history, recovered
pre-unified UFC bouts, and staged major-promotion history from Sherdog. The
bounded FightMatrix profile cohort is retained as diagnostic evidence and can
be selected explicitly; it is not silently merged into the published scope.

Every admitted bout is held once, in a single evidence table, together with a
record of which sources supplied it. Where two sources describe the same bout
the more authoritative one is used, but the other source's claim on it is kept.
That is what lets a narrower release be selected without silently losing bouts a
broader source also carried. Field-level detail is in the source matrix below.

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

Rebuild the generated public ranking publication from the current snapshot.
One run refreshes `RANKINGS.md` and the headline boards in this README
together, and every marked block is validated before either file is written:

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
