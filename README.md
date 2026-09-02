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

**Two careers, and why the board separates them.** Demetrious Johnson is 6th and
Fedor Emelianenko 23rd, and the first thing to notice is that Fedor rates *higher*
at his peak — 2,014 against Johnson's 1,982. The board is not saying Johnson was
the better fighter at his best. It is saying he achieved more with it, and three
numbers carry that. **What they won:** Johnson has 12 title wins and 11 defenses
against Fedor's 5 and 2, which scores 2,248 against 804 — by far the largest gap
between them, and the achievement term is 30% of the whole score. **Who they
beat:** almost level, 6 contender wins to 5, scoring 1,170 against 1,000. **How
much of the career we can see:** Fedor never fought in the UFC, so 4 of his rated
fights carry no promotion name at all and his exposure factor is 0.828 against
Johnson's 0.921 — which takes his skill figure from 1,339 down to 1,109, a cut of
230 points where Johnson loses 130.

That last one is a stated policy, not a fact the results prove, and it is the
part of Fedor's placement most open to argument — it is listed under
[Important limitations](#important-limitations) for exactly that reason. The
first two are not: a fighter who defended a world title eleven times did
something a fighter who defended twice did not, and the score is built to say so.


<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Prime | Prime rank | Elite wins |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | 3962.6 | 2210 | 1 | 12 |
| 2 | Islam Makhachev | 2352.7 | 2180 | 3 | 7 |
| 3 | Georges St-Pierre | 2223.3 | 2073 | 2 | 11 |
| 4 | Daniel Cormier | 2016.7 | 2080 | 5 | 8 |
| 5 | Jose Aldo | 1936.0 | 1930 | 16 | 9 |
| 6 | Demetrious Johnson | 1879.6 | 1982 | 24 | 6 |
| 7 | Alexander Volkanovski | 1855.6 | 2048 | 4 | 9 |
| 8 | Stipe Miocic | 1765.0 | 1994 | 22 | 6 |
| 9 | Anderson Silva | 1720.2 | 1922 | 8 | 11 |
| 10 | Francis Ngannou | 1644.5 | 2037 | 6 | 8 |
| 11 | Max Holloway | 1508.4 | 1963 | 9 | 9 |
| 12 | Israel Adesanya | 1462.6 | 1935 | 15 | 9 |
| 13 | Dominick Cruz | 1388.1 | 1941 | 34 | 5 |
| 14 | Ilia Topuria | 1387.0 | 2119 | 12 | 5 |
| 15 | Merab Dvalishvili | 1353.0 | 1974 | 11 | 8 |
| 16 | Khabib Nurmagomedov | 1338.2 | 2172 |  | 4 |
| 17 | Lyoto Machida | 1282.2 | 1976 | 19 | 7 |
| 18 | Alex Pereira | 1266.4 | 1962 | 21 | 7 |
| 19 | Aljamain Sterling | 1261.8 | 1945 | 25 | 7 |
| 20 | Sean Strickland | 1208.3 | 1921 | 13 | 10 |
| 21 | Justin Gaethje | 1181.9 | 1994 | 23 | 6 |
| 22 | Matt Hughes | 1151.3 | 1830 |  | 3 |
| 23 | Fedor Emelianenko | 1119.8 | 2014 | 27 | 5 |
| 24 | Kamaru Usman | 1069.2 | 1968 | 7 | 10 |
| 25 | Benson Henderson | 1065.3 | 1869 | 42 | 6 |
| 26 | Charles Oliveira | 1047.2 | 1978 | 18 | 7 |
| 27 | Khamzat Chimaev | 975.1 | 2089 | 17 | 5 |
| 28 | Dustin Poirier | 972.9 | 1922 | 38 | 5 |
| 29 | Ciryl Gane | 962.9 | 2060 | 10 | 6 |
| 30 | Cain Velasquez | 933.6 | 1964 |  | 4 |
| 31 | Dricus Du Plessis | 915.0 | 2044 | 14 | 6 |
| 32 | Junior Dos Santos | 912.0 | 1914 |  | 4 |
| 33 | Henry Cejudo | 899.2 | 1873 | 48 | 5 |
| 34 | Frankie Edgar | 898.9 | 1905 | 26 | 8 |
| 35 | Chris Weidman | 874.6 | 1871 | 33 | 8 |
| 36 | Dan Henderson | 852.2 | 1869 | 50 | 5 |
| 37 | Petr Yan | 851.3 | 1951 | 28 | 6 |
| 38 | Patricio Freire | 825.4 | 1933 |  | 3 |
| 39 | Mauricio Rua | 813.0 | 1833 | 52 | 6 |
| 40 | Anthony Pettis | 805.3 | 1759 | 69 | 6 |
| 41 | Vadim Nemkov | 795.3 | 2067 | 20 | 5 |
| 42 | Ryan Bader | 791.3 | 1926 | 37 | 5 |
| 43 | Randy Couture | 783.7 | 1763 |  | 4 |
| 44 | Conor McGregor | 770.1 | 1840 |  | 4 |
| 45 | Chuck Liddell | 768.1 | 1820 | 54 | 6 |
| 46 | BJ Penn | 753.9 | 1793 | 63 | 5 |
| 47 | Movsar Evloev | 739.9 | 2103 |  | 4 |
| 48 | Tito Ortiz | 735.3 | 1786 |  | 4 |
| 49 | Wanderlei Silva | 720.3 | 1812 |  | 4 |
| 50 | Anthony Johnson | 681.7 | 1938 | 30 | 6 |
| 51 | Robert Whittaker | 675.4 | 1893 | 32 | 7 |
| 52 | Antonio Rodrigo Nogueira | 674.6 | 1889 |  | 4 |
| 53 | Jan Blachowicz | 670.3 | 1801 | 62 | 5 |
| 54 | Gegard Mousasi | 649.7 | 1919 | 39 | 5 |
| 55 | Rashad Evans | 649.1 | 1814 | 60 | 5 |
| 56 | Fabricio Werdum | 648.1 | 1894 |  | 4 |
| 57 | Leon Edwards | 636.6 | 1888 |  | 4 |
| 58 | Vitor Belfort | 626.5 | 1781 | 68 | 5 |
| 59 | Luke Rockhold | 620.2 | 1863 | 45 | 6 |
| 60 | Sean O'Malley | 619.5 | 1953 |  | 4 |
| 61 | Alexander Volkov | 604.8 | 1906 | 31 | 7 |
| 62 | Eddie Alvarez | 600.8 | 1763 |  | 4 |
| 63 | Phil Davis | 596.4 | 1956 |  | 4 |
| 64 | Shavkat Rakhmonov | 593.3 | 2146 |  | 2 |
| 65 | Tom Aspinall | 571.5 | 1934 |  | 4 |
| 66 | Rafael Dos Anjos | 571.2 | 1772 | 66 | 7 |
| 67 | Quinton Jackson | 569.6 | 1832 | 56 | 5 |
| 68 | Tyron Woodley | 561.3 | 1803 | 61 | 5 |
| 69 | TJ Dillashaw | 554.9 | 1853 |  | 4 |
| 70 | Matt Serra | 549.8 | 1688 |  | 1 |
| 71 | Derrick Lewis | 539.4 | 1818 | 59 | 5 |
| 72 | Mirko Filipovic | 523.1 | 1831 |  | 4 |
| 73 | Curtis Blaydes | 519.8 | 1910 | 40 | 5 |
| 74 | Belal Muhammad | 519.1 | 1901 | 35 | 6 |
| 75 | Beneil Dariush | 511.3 | 1850 | 47 | 6 |
| 76 | Deiveson Figueiredo | 505.3 | 1828 | 58 | 5 |
| 77 | Glover Teixeira | 488.0 | 1867 | 43 | 6 |
| 78 | Demian Maia | 480.5 | 1853 | 46 | 6 |
| 79 | Joshua Van | 471.0 | 1944 |  | 3 |
| 80 | Nassourdine Imavov | 459.1 | 1941 | 29 | 6 |
| 81 | Mark Coleman | 450.9 | 1722 |  | 2 |
| 82 | Jake Shields | 449.7 | 1820 | 51 | 7 |
| 83 | Arman Tsarukyan | 440.1 | 2014 |  | 4 |
| 84 | Urijah Faber | 433.3 | 1800 |  | 3 |
| 85 | Alistair Overeem | 431.3 | 1810 |  | 4 |
| 86 | Andrei Arlovski | 430.5 | 1780 |  | 4 |
| 87 | Michael Chandler | 429.5 | 1812 |  | 1 |
| 88 | Umar Nurmagomedov | 429.2 | 2027 |  | 4 |
| 89 | Robbie Lawler | 422.5 | 1705 |  | 3 |
| 90 | Matt Hamill | 411.4 | 1652 |  | 2 |
| 91 | Sean Sherk | 411.4 | 1894 | 36 | 6 |
| 92 | Alexandre Pantoja | 409.3 | 1869 | 49 | 5 |
| 93 | Joseph Benavidez | 407.6 | 1847 |  | 2 |
| 94 | Renan Barao | 405.4 | 1648 |  | 3 |
| 95 | Frank Mir | 404.5 | 1737 |  | 3 |
| 96 | Sergio Pettis | 403.3 | 1830 |  | 3 |
| 97 | Yoel Romero | 402.3 | 1867 | 44 | 6 |
| 98 | Carlos Condit | 400.6 | 1721 |  | 4 |
| 99 | Magomed Ankalaev | 396.3 | 1968 |  | 2 |
| 100 | Ian Machado Garry | 395.7 | 2071 |  | 4 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

How good was the fighter at their best — counting only the peaks they actually
proved? To qualify, a fighter must have beaten **5 contenders within a single
ten-year stretch**. A contender means an opponent rated **1,750 or higher at the
time of the fight** who also had a tested record of their own: at least 8 UFC
bouts. That number is easier to read as names than as a figure. On the top-100
table above, Anthony Pettis peaked at 1,759 and Randy Couture at 1,763, both just
over the line; Frank Mir at 1,737 and Mark Coleman at 1,722 sit just under it.
So a contender is not a title challenger — it is a fighter of roughly that
standing, and the work is done by needing to beat five of them, not by the height
of the line. Both figures come from the same ten years, so a win cannot prove a
peak it falls outside of.

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
