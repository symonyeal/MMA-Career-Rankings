# Symon UFC Rank Engine

The Symon UFC Rank Engine ranks fighters from their fight records. Every
number traces back to the bouts behind it, so any placement can be explained
and reproduced. The score's policy choices are named in
[Open decisions](docs/DECISIONS.md), not hidden in the arithmetic.

It answers three questions: what a fighter's career added up to, how good they
were at their peak, and how good they are today.

The all-time top 100 and the Prime 50 are below, under
[Published rankings](#published-rankings). Every table, including the women's
boards, is in [Published UFC Rankings](RANKINGS.md). Both documents print the
date and the data behind them beside every table, so a ranking is never shown
without the facts it came from.

## What is published

| Ranking | Question it answers | Measure |
| --- | --- | --- |
| All-time | What did the fighter's career add up to? | How good they were over time, what they won, and who they beat |
| Prime | How good were they at their best, and how often did they prove it? | Their rating in their best ten years, weighted by how many top opponents they beat in them |
| Current | How good are they now? | Their latest rating, adjusted for age and time out of competition |
| Integrity | How would the published conduct deductions change the order? | A line-by-line list of deductions, each with its reason |

These are three views of the same fight history. They are not meant to be added
together. Integrity is a separate audit and never changes the ratings.

## Published rankings

The two headline boards are here; the women's boards are in
[Published UFC Rankings](RANKINGS.md). Both documents are written by a single
run from one dataset, and every table is checked before either file is saved,
so a table can never fall out of step with the facts printed beside it.

<!-- PUBLICATION:RELEASE:BEGIN -->

| Release fact | Value |
| --- | ---: |
| Snapshot | 2026-08-13 |
| Published scope | majors,pre_unified |
| Published score | public_legacy_score |
| Rated bouts | 81,281 |
| Rated fighters | 34,085 |
| Maximum-coverage fight rows | 82,675 |
| Contender line | 1,750 — reached by 19.5% of established fighters |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

What the fighter's whole career added up to: how good they were over time,
what they won, and how strong their opposition was.

Three columns sit beside the score:

- **Prime** — their rating in their best ten years, on the same scale as the
  contender line in the release facts above. It shows what that line is worth
  in real names.
- **Prime rank** — where they sit on the Prime 50 board below. A blank means
  they did not qualify for that board.
- **Elite wins** — how many top opponents they beat in those ten years. A blank
  means none.

Prime and Prime rank will not always agree, and that is deliberate. Prime is how
high a fighter rated. The Prime board ranks how often they proved it. So a
fighter can rate higher than someone placed above them.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Prime | Prime rank | Elite wins |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | 4062.3 | 2210 | 1 | 12 |
| 2 | Islam Makhachev | 2493.4 | 2180 | 3 | 7 |
| 3 | Georges St-Pierre | 2202.7 | 2073 | 2 | 11 |
| 4 | Daniel Cormier | 2103.9 | 2080 | 5 | 8 |
| 5 | Jose Aldo | 1965.6 | 1930 | 16 | 9 |
| 6 | Alexander Volkanovski | 1946.0 | 2048 | 4 | 9 |
| 7 | Demetrious Johnson | 1899.8 | 1982 | 24 | 6 |
| 8 | Stipe Miocic | 1870.7 | 1994 | 22 | 6 |
| 9 | Francis Ngannou | 1730.1 | 2037 | 6 | 8 |
| 10 | Anderson Silva | 1705.0 | 1922 | 8 | 11 |
| 11 | Max Holloway | 1539.1 | 1963 | 9 | 9 |
| 12 | Ilia Topuria | 1477.8 | 2119 | 12 | 5 |
| 13 | Dominick Cruz | 1460.8 | 1941 | 34 | 5 |
| 14 | Israel Adesanya | 1437.4 | 1935 | 15 | 9 |
| 15 | Merab Dvalishvili | 1413.5 | 1974 | 11 | 8 |
| 16 | Khabib Nurmagomedov | 1383.3 | 2172 |  | 4 |
| 17 | Aljamain Sterling | 1319.2 | 1945 | 25 | 7 |
| 18 | Lyoto Machida | 1292.6 | 1976 | 19 | 7 |
| 19 | Alex Pereira | 1253.9 | 1962 | 21 | 7 |
| 20 | Sean Strickland | 1237.2 | 1921 | 13 | 10 |
| 21 | Justin Gaethje | 1236.8 | 1994 | 23 | 6 |
| 22 | Matt Hughes | 1146.1 | 1830 |  | 3 |
| 23 | Fedor Emelianenko | 1107.6 | 2014 | 27 | 5 |
| 24 | Charles Oliveira | 1060.2 | 1978 | 18 | 7 |
| 25 | Benson Henderson | 1055.7 | 1869 | 42 | 6 |
| 26 | Kamaru Usman | 1012.8 | 1968 | 7 | 10 |
| 27 | Dustin Poirier | 1010.9 | 1922 | 38 | 5 |
| 28 | Khamzat Chimaev | 1000.1 | 2089 | 17 | 5 |
| 29 | Cain Velasquez | 962.1 | 1964 |  | 4 |
| 30 | Ciryl Gane | 956.4 | 2060 | 10 | 6 |
| 31 | Junior Dos Santos | 941.2 | 1914 |  | 4 |
| 32 | Henry Cejudo | 934.8 | 1873 | 48 | 5 |
| 33 | Dricus Du Plessis | 912.7 | 2044 | 14 | 6 |
| 34 | Petr Yan | 875.6 | 1951 | 28 | 6 |
| 35 | Frankie Edgar | 872.6 | 1905 | 26 | 8 |
| 36 | Chris Weidman | 870.9 | 1871 | 33 | 8 |
| 37 | Mauricio Rua | 827.6 | 1833 | 52 | 6 |
| 38 | Anthony Pettis | 821.9 | 1759 | 69 | 6 |
| 39 | Conor McGregor | 816.7 | 1840 |  | 4 |
| 40 | Dan Henderson | 805.2 | 1869 | 50 | 5 |
| 41 | Vadim Nemkov | 768.3 | 2067 | 20 | 5 |
| 42 | Patricio Freire | 753.9 | 1933 |  | 3 |
| 43 | BJ Penn | 748.8 | 1793 | 63 | 5 |
| 44 | Movsar Evloev | 739.9 | 2103 |  | 4 |
| 45 | Chuck Liddell | 710.8 | 1820 | 54 | 6 |
| 46 | Ryan Bader | 703.1 | 1926 | 37 | 5 |
| 47 | Randy Couture | 686.2 | 1763 |  | 4 |
| 48 | Anthony Johnson | 681.7 | 1938 | 30 | 6 |
| 49 | Jan Blachowicz | 676.0 | 1801 | 62 | 5 |
| 50 | Fabricio Werdum | 670.6 | 1894 |  | 4 |
| 51 | Wanderlei Silva | 669.7 | 1812 |  | 4 |
| 52 | Robert Whittaker | 662.9 | 1893 | 32 | 7 |
| 53 | Antonio Rodrigo Nogueira | 661.6 | 1889 |  | 4 |
| 54 | Leon Edwards | 649.1 | 1888 |  | 4 |
| 55 | Tito Ortiz | 648.1 | 1786 |  | 4 |
| 56 | Sean O'Malley | 627.2 | 1953 |  | 4 |
| 57 | Rashad Evans | 624.5 | 1814 | 60 | 5 |
| 58 | Vitor Belfort | 617.9 | 1781 | 68 | 5 |
| 59 | Eddie Alvarez | 605.3 | 1763 |  | 4 |
| 60 | Matt Serra | 601.0 | 1688 |  | 1 |
| 61 | Luke Rockhold | 595.6 | 1863 | 45 | 6 |
| 62 | Shavkat Rakhmonov | 593.3 | 2146 |  | 2 |
| 63 | Gegard Mousasi | 589.5 | 1919 | 39 | 5 |
| 64 | Tom Aspinall | 588.3 | 1934 |  | 4 |
| 65 | Phil Davis | 588.0 | 1956 |  | 4 |
| 66 | Alexander Volkov | 586.2 | 1906 | 31 | 7 |
| 67 | Quinton Jackson | 567.8 | 1832 | 56 | 5 |
| 68 | Rafael Dos Anjos | 565.0 | 1772 | 66 | 7 |
| 69 | Derrick Lewis | 539.4 | 1818 | 59 | 5 |
| 70 | Tyron Woodley | 534.7 | 1803 | 61 | 5 |
| 71 | Mirko Filipovic | 533.6 | 1831 |  | 4 |
| 72 | Curtis Blaydes | 519.8 | 1910 | 40 | 5 |
| 73 | Belal Muhammad | 514.2 | 1901 | 35 | 6 |
| 74 | Beneil Dariush | 511.3 | 1850 | 47 | 6 |
| 75 | TJ Dillashaw | 500.7 | 1853 |  | 4 |
| 76 | Joshua Van | 491.0 | 1944 |  | 3 |
| 77 | Demian Maia | 480.5 | 1853 | 46 | 6 |
| 78 | Glover Teixeira | 478.3 | 1867 | 43 | 6 |
| 79 | Deiveson Figueiredo | 474.0 | 1828 | 58 | 5 |
| 80 | Mark Coleman | 464.4 | 1722 |  | 2 |
| 81 | Nassourdine Imavov | 459.1 | 1941 | 29 | 6 |
| 82 | Jake Shields | 449.0 | 1820 | 51 | 7 |
| 83 | Arman Tsarukyan | 440.1 | 2014 |  | 4 |
| 84 | Umar Nurmagomedov | 429.2 | 2027 |  | 4 |
| 85 | Frank Mir | 416.5 | 1737 |  | 3 |
| 86 | Alistair Overeem | 412.8 | 1810 |  | 4 |
| 87 | Sergio Pettis | 411.9 | 1830 |  | 3 |
| 88 | Matt Hamill | 411.4 | 1652 |  | 2 |
| 89 | Michael Chandler | 408.1 | 1812 |  | 1 |
| 90 | Joseph Benavidez | 407.6 | 1847 |  | 2 |
| 91 | Yoel Romero | 402.3 | 1867 | 44 | 6 |
| 92 | Magomed Ankalaev | 401.2 | 1968 |  | 2 |
| 93 | Robbie Lawler | 400.6 | 1705 |  | 3 |
| 94 | Ian Machado Garry | 395.7 | 2071 |  | 4 |
| 95 | Sean Sherk | 395.2 | 1894 | 36 | 6 |
| 96 | Renan Barao | 390.3 | 1648 |  | 3 |
| 97 | Jacare Souza | 387.9 | 1836 |  | 4 |
| 98 | Andrei Arlovski | 387.9 | 1780 |  | 4 |
| 99 | Donald Cerrone | 385.1 | 1849 | 53 | 5 |
| 100 | Carlos Ulberg | 383.7 | 1991 |  | 3 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

How good was the fighter at their best — counting only the peaks they actually
proved? To qualify, a fighter must have beaten **5 contenders within a single
ten-year stretch**. A contender means an opponent rated **1,750 or higher at the
time of the fight** who also had a tested record of their own: at least 8 UFC
bouts. Both figures come from the same ten years, so a win cannot prove a peak
it falls outside of.

**Which ten years.** We take the stretch with the most wins over contenders, not
the one with the highest average rating. Picking by rating rewards the years a
fighter lost least: it made Daniel Cormier's peak his undefeated Strikeforce run
and left his entire UFC title reign out of it, crediting 2 qualifying wins where
he has 8, and it credited Mirko Filipovic with none at all. A peak is a peak
because of who was beaten in it.

**How the order is decided.** Not by rating alone. A rating does not rise with
the number of hard fights behind it, so ranking on rating would put a fighter
who barely qualified above one who cleared the bar many times over. The order
multiplies the two printed columns: how many contenders they beat, by how far
their rating stood above the lowest on the board. A great peak proved once and a
good peak proved eleven times are not the same achievement. The wins are never
added to the rating — they decide how much of it is credited — so nothing is
counted twice, and there is no dial to tune.

The contender line and the five-win minimum are set as policy, not fitted to the
data. 70 men qualify, so this top 50 is full. Only 2 women do. That is a
statement about how few women in the data have a long UFC record, not about the
fighters — see [Published UFC Rankings](RANKINGS.md) for that board.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Prime | Elite wins |
| ---: | --- | ---: | ---: |
| 1 | Jon Jones | 2210 | 12 |
| 2 | Georges St-Pierre | 2073 | 11 |
| 3 | Islam Makhachev | 2180 | 7 |
| 4 | Alexander Volkanovski | 2048 | 9 |
| 5 | Daniel Cormier | 2080 | 8 |
| 6 | Francis Ngannou | 2037 | 8 |
| 7 | Kamaru Usman | 1968 | 10 |
| 8 | Anderson Silva | 1922 | 11 |
| 9 | Max Holloway | 1963 | 9 |
| 10 | Ciryl Gane | 2060 | 6 |
| 11 | Merab Dvalishvili | 1974 | 8 |
| 12 | Ilia Topuria | 2119 | 5 |
| 13 | Sean Strickland | 1921 | 10 |
| 14 | Dricus Du Plessis | 2044 | 6 |
| 15 | Israel Adesanya | 1935 | 9 |
| 16 | Jose Aldo | 1930 | 9 |
| 17 | Khamzat Chimaev | 2089 | 5 |
| 18 | Charles Oliveira | 1978 | 7 |
| 19 | Lyoto Machida | 1976 | 7 |
| 20 | Vadim Nemkov | 2067 | 5 |
| 21 | Alex Pereira | 1962 | 7 |
| 22 | Stipe Miocic | 1994 | 6 |
| 23 | Justin Gaethje | 1994 | 6 |
| 24 | Demetrious Johnson | 1982 | 6 |
| 25 | Aljamain Sterling | 1945 | 7 |
| 26 | Frankie Edgar | 1905 | 8 |
| 27 | Fedor Emelianenko | 2014 | 5 |
| 28 | Petr Yan | 1951 | 6 |
| 29 | Nassourdine Imavov | 1941 | 6 |
| 30 | Anthony Johnson | 1938 | 6 |
| 31 | Alexander Volkov | 1906 | 7 |
| 32 | Robert Whittaker | 1893 | 7 |
| 33 | Chris Weidman | 1871 | 8 |
| 34 | Dominick Cruz | 1941 | 5 |
| 35 | Belal Muhammad | 1901 | 6 |
| 36 | Sean Sherk | 1894 | 6 |
| 37 | Ryan Bader | 1926 | 5 |
| 38 | Dustin Poirier | 1922 | 5 |
| 39 | Gegard Mousasi | 1919 | 5 |
| 40 | Curtis Blaydes | 1910 | 5 |
| 41 | Brendan Allen | 1908 | 5 |
| 42 | Benson Henderson | 1869 | 6 |
| 43 | Glover Teixeira | 1867 | 6 |
| 44 | Yoel Romero | 1867 | 6 |
| 45 | Luke Rockhold | 1863 | 6 |
| 46 | Demian Maia | 1853 | 6 |
| 47 | Beneil Dariush | 1850 | 6 |
| 48 | Henry Cejudo | 1873 | 5 |
| 49 | Alexandre Pantoja | 1869 | 5 |
| 50 | Dan Henderson | 1869 | 5 |

<!-- BOARD:ELITEPRIME50:END -->

## How the ranking is governed

- **One fight table feeds everything.** A bout can appear in several sources. It
  is counted once, using the most reliable version, and we keep a record of which
  sources carried it. The build refuses to finish if any duplicate identity
  survives, which is how 99 duplicated fights were caught and removed on
  2026-09-01.
- **Ratings are fitted across a whole career at once**, not updated fight by
  fight, and how a fight ended counts, not only who won. Two simpler models are
  kept for comparison. The method is set out in
  [Rating Layer and Public Ledger](docs/RATING_LAYER_AND_LEDGER_2026-08-28.md).
- **A fighter's whole record comes in, or their rating is wrong.** A fighter who
  rarely loses has no natural ceiling in this kind of model, so the rating climbs
  with however many of their fights the dataset happens to hold. Khabib
  Nurmagomedov was rated on 14 fights when his record is 30, and that alone put
  him 206 points above the strongest opponent he had ever faced; with all 30
  fights in, the gap is 160. Whole-career records are now held for 1,821 of the
  1,825 fighters this can affect.
- **The all-time score is the published board.** The career-skill figure behind
  it is a diagnostic, and must not replace it without a fresh top-100 review: on
  its own it rates unbeaten records from weak circuits alongside title legends.
  Seika Izawa is the standing example — 320 points above the strongest opponent
  she has faced, on a record no one in the dataset has beaten.
- **Men and women are ranked separately.** They never fight each other, so no
  result connects the two groups and a combined list would be guesswork.
- **Fighters short of the evidence threshold are left out.** That is us declining
  to rank them. It is not a last place.
- **Every table and the facts beside it are checked before either document is
  saved**, so a release is never left half-updated.

## Data coverage

The published rankings draw on three sources: the UFC's own fight record,
recovered early UFC bouts that pre-date the unified rules, and major-promotion
history from Sherdog — PRIDE, Bellator, Strikeforce, WEC, RIZIN and Affliction.
A fourth source, a limited FightMatrix sample, is kept for comparison and is
never mixed in unless it is asked for by name.

Every fight is stored once, with a note of which sources carried it. Where two
sources describe the same fight we keep the more reliable version and record the
other source's claim on it. That is what lets a narrower release be published
without quietly dropping fights a wider source also had.

Source ownership, licensing and known gaps are listed in
[Source Matrix](data/SOURCE_MATRIX.md). Release history is in
[Data Changelog](data/CHANGELOG.md).

## Important limitations

- **The all-time score looks backwards.** An opponent is priced on everything now
  known about them, so it measures how good a win turned out to be, not how good
  it looked on the night.
- **The contender résumé favours long careers**, though it counts at most one win
  per active year. Read it as context, not as a separate measure of skill.
- **The exposure factor is a stated policy** — a declared ranking of promotions.
  It helps compare careers we can only see part of, but it is an assumption, not
  something the fight results prove. It also bites hardest where the data is
  thinnest: 64% of rated fights carry no promotion name, and every one of them is
  currently scored as the weakest tier. That costs Jiri Prochazka, 18 of whose 39
  fights are unnamed, an exposure factor of 0.73 against a top-100 median of 0.89.
- **A championship can be worth almost nothing.** Value comes from the opponent
  beaten, measured against their own division. Prochazka's win over Glover
  Teixeira for the UFC light-heavyweight title scores 0.073 because Teixeira
  rated barely above the line that year, while each of Prochazka's title *losses*
  is worth three times more than either of his wins — and losses are not counted.
  A minimum credit for winning a major title was measured and does not fix it;
  the numbers are in [Open decisions](docs/DECISIONS.md).
- **Weight class and fighter identity are partly inferred** where the sources are
  incomplete. About 17% of filled weight classes are wrong for that particular
  fight, and four fighters cannot be told apart from namesakes at all, so only
  their UFC record is held. Those inferences are audited, but they feed the
  rankings.
- **Same-night rematches.** UFC records identify them properly; other sources do
  not always, so an unclear same-day duplicate is treated as one fight. Three
  such pairs are known: Kazushi Sakuraba against Marcus Silveira at UFC Ultimate
  Japan is a genuine same-night tournament pair and is kept, and the other two
  are left as recorded because nothing in any source says which date is right.
- **No model can recover fights missing from every source.** Coverage gaps stay
  part of every release decision.

These limitations travel with every published board. The
[decision register](docs/DECISIONS.md) separates choices that still need a
decision, remaining data work, accepted limits, and changes already refused.

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
| `analysis/` | Charts and the generated interactive notebook |
| `tests/` | Behavioral, regression, consistency, and smoke tests |
| `data/snapshots/<date>/` | Immutable-style release inputs and generated artifacts |
| `data/external/<source>/` | Ingested source data, and one `pages.sqlite` holding that source's cached pages |
| `data/model_tuning/` | Held-out comparisons and top-100 audit evidence |
| `docs/` | Current methodology, coverage, and decision records |
| `_archive/` | Recoverable historical research, retired code, and stale generated material |

## Current technical records

Four documents, each answering one question.

- [How the ratings and the score are built](docs/RATING_LAYER_AND_LEDGER_2026-08-28.md)
  — the method: how a rating is fitted and what goes into the all-time score.
- [Open decisions](docs/DECISIONS.md) — unresolved model choices, remaining
  data work, accepted limitations, and changes already refused.
- [Career coverage](docs/CAREER_COVERAGE_2026-08-27.md) — how a gap in the data
  turned into rating points, and the rule that stops it returning.
- [Published UFC Rankings](RANKINGS.md) — every generated table.

Historical design notes and retired experiments are preserved under
[`_archive/`](_archive/) with restoration instructions. They are evidence of
past work, not current operating guidance.
