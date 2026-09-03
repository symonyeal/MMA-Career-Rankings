# Symon UFC Rank Engine

I wanted to know whether a sport this chaotic could be pinned down from first
principles. So I set out a small number of principles that do not contradict
each other, turned each one into arithmetic, and let the ranking fall wherever
it fell. The test was never whether the method was clever. It was whether the
list that came out the other end looked like the sport we actually watched.

Mostly it does. Jon Jones, Islam Makhachev, Georges St-Pierre, Daniel Cormier
and Alexander Volkanovski arrive at the top without being put there. The places
where the list argues with received opinion are the interesting part, and each
one traces back to a principle rather than to a thumb on the scale.

## The principles

Each of these does work none of the others do. Take one away and something in
the ranking stops being defensible.

1. **A fighter is only as good as the people they beat.** The only things that
   go in are who fought whom and what happened. Not reputation, not popularity,
   not highlights.
2. **A career is judged whole, not fight by fight.** What a win was worth is
   often unclear for years, so every fight in the sport is settled together, at
   once, rather than each result nudging a running total.
3. **Every fight counts exactly once.** The same bout turns up in several
   records. It is kept once, in its most reliable version, and the build stops
   if two copies survive.
4. **Half a record is a wrong record.** A fighter who rarely loses has no
   ceiling here: the fewer of their fights we hold, the more unbeatable they
   look. Their whole career comes in, or their number is wrong.
5. **How a fight ended counts, not only who won.** Finishing someone and
   squeaking a decision are not the same evidence.
6. **A win is worth what the opponent was worth that night.** Not what they
   were at their best, and not what they were before three years away.
7. **What you won and how good you were are different questions.** Titles and
   defences are an achievement. Beating strong people is a level. They are
   counted apart and never folded into a single idea.
8. **Only credit what can be seen.** Where a career can be identified only in
   part, it is pulled toward the ordinary rather than credited in full on thin
   evidence.
9. **No fact is ever counted twice.** Each fact enters in exactly one place. If
   time away has already lowered what a win is worth, it is not charged a
   second time on the board.
10. **When the evidence is not there, do not rank.** Leaving a fighter out is a
    refusal to judge them. It is not a last place.
11. **Men and women are ranked separately.** They never fight each other, so
    nothing links the two groups and a combined list would be guesswork.
12. **Say which numbers were measured and which were chosen.** Some come out of
    the fights. Some are my judgement. They are never dressed up as one another,
    and the chosen ones are listed in [Open decisions](docs/DECISIONS.md).

## What is published

| Ranking | The question it answers |
| --- | --- |
| All-time | What did the whole career add up to? |
| Prime | How good were they at their best, and how often did they prove it? |
| Current | How good are they now? |
| Integrity | How would the published conduct deductions change the order? |

These are three views of one fight history. They are not meant to be added
together, and Integrity is a separate audit that never touches the ratings.

Every table, including the women's boards, is in
[Published UFC Rankings](RANKINGS.md). Both documents are written by a single
run from one dataset, and every table is checked before either file is saved.

## Published rankings

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

What the whole career added up to: how good they were over time, what they won,
and how strong the opposition was. **Prime** is their level in their best ten
years, **Prime rank** is where that puts them on the next board (blank if they
did not qualify), and **Elite wins** counts the top opponents they beat in those
years.

Prime and Prime rank disagree on purpose. Prime is how high a fighter got. The
Prime board is about how often they proved it.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Prime | Prime rank | Elite wins |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | 3688.5 | 2210 | 1 | 12 |
| 2 | Islam Makhachev | 2415.7 | 2180 | 3 | 7 |
| 3 | Georges St-Pierre | 2105.4 | 2073 | 2 | 10 |
| 4 | Daniel Cormier | 2020.6 | 2080 | 5 | 8 |
| 5 | Alexander Volkanovski | 1946.6 | 2048 | 4 | 9 |
| 6 | Jose Aldo | 1895.6 | 1930 | 15 | 9 |
| 7 | Demetrious Johnson | 1871.1 | 1982 | 22 | 6 |
| 8 | Stipe Miocic | 1784.6 | 1994 | 20 | 6 |
| 9 | Anderson Silva | 1690.6 | 1922 | 17 | 9 |
| 10 | Francis Ngannou | 1603.9 | 2037 | 7 | 7 |
| 11 | Israel Adesanya | 1498.7 | 1935 | 14 | 9 |
| 12 | Dominick Cruz | 1472.8 | 1941 | 33 | 5 |
| 13 | Max Holloway | 1453.1 | 1963 | 8 | 9 |
| 14 | Ilia Topuria | 1441.8 | 2119 | 11 | 5 |
| 15 | Khabib Nurmagomedov | 1418.9 | 2172 |  | 4 |
| 16 | Merab Dvalishvili | 1406.8 | 1974 | 10 | 8 |
| 17 | Sean Strickland | 1324.6 | 1921 | 12 | 10 |
| 18 | Matt Hughes | 1223.2 | 1830 |  | 3 |
| 19 | Justin Gaethje | 1207.7 | 1994 | 21 | 6 |
| 20 | Lyoto Machida | 1204.0 | 1966 | 23 | 6 |
| 21 | Alex Pereira | 1176.2 | 1962 | 25 | 6 |
| 22 | Fedor Emelianenko | 1126.7 | 2014 | 24 | 5 |
| 23 | Kamaru Usman | 1101.2 | 1968 | 6 | 10 |
| 24 | Benson Henderson | 1087.4 | 1869 | 40 | 6 |
| 25 | Aljamain Sterling | 1085.4 | 1945 | 27 | 6 |
| 26 | Charles Oliveira | 1042.6 | 1978 | 18 | 7 |
| 27 | Dricus Du Plessis | 1010.6 | 2044 | 13 | 6 |
| 28 | Dustin Poirier | 972.3 | 1922 | 37 | 5 |
| 29 | Khamzat Chimaev | 952.8 | 2089 | 16 | 5 |
| 30 | Ciryl Gane | 952.3 | 2060 | 9 | 6 |
| 31 | Frankie Edgar | 914.2 | 1905 | 31 | 7 |
| 32 | Cain Velasquez | 897.5 | 1959 |  | 3 |
| 33 | Junior Dos Santos | 896.3 | 1914 |  | 4 |
| 34 | Patricio Freire | 851.0 | 1933 |  | 3 |
| 35 | Petr Yan | 850.3 | 1951 | 26 | 6 |
| 36 | Mauricio Rua | 830.0 | 1833 | 49 | 6 |
| 37 | Dan Henderson | 828.3 | 1869 | 48 | 5 |
| 38 | Anthony Pettis | 820.4 | 1759 | 62 | 6 |
| 39 | Chris Weidman | 816.7 | 1871 | 35 | 7 |
| 40 | Vadim Nemkov | 811.5 | 2067 | 19 | 5 |
| 41 | Henry Cejudo | 796.9 | 1873 |  | 4 |
| 42 | Ryan Bader | 776.1 | 1926 | 36 | 5 |
| 43 | Conor McGregor | 772.5 | 1840 |  | 4 |
| 44 | Randy Couture | 757.3 | 1763 |  | 4 |
| 45 | Tito Ortiz | 735.0 | 1786 |  | 4 |
| 46 | BJ Penn | 708.3 | 1793 | 57 | 5 |
| 47 | Robert Whittaker | 706.9 | 1893 | 32 | 7 |
| 48 | Movsar Evloev | 699.0 | 2103 |  | 4 |
| 49 | Wanderlei Silva | 694.3 | 1812 |  | 4 |
| 50 | Chuck Liddell | 676.1 | 1815 | 54 | 5 |
| 51 | Antonio Rodrigo Nogueira | 664.1 | 1889 |  | 4 |
| 52 | Eddie Alvarez | 661.5 | 1763 |  | 4 |
| 53 | Anthony Johnson | 654.4 | 1938 | 29 | 6 |
| 54 | Sean O'Malley | 652.0 | 1953 |  | 4 |
| 55 | Gegard Mousasi | 651.7 | 1919 |  | 4 |
| 56 | Alexander Volkov | 636.1 | 1906 | 30 | 7 |
| 57 | Jan Blachowicz | 626.0 | 1801 | 56 | 5 |
| 58 | Tom Aspinall | 625.2 | 1934 |  | 4 |
| 59 | Vitor Belfort | 623.7 | 1781 | 61 | 5 |
| 60 | Leon Edwards | 621.0 | 1888 |  | 4 |
| 61 | Luke Rockhold | 609.1 | 1863 | 44 | 6 |
| 62 | Rafael Dos Anjos | 607.6 | 1772 | 59 | 7 |
| 63 | Quinton Jackson | 607.0 | 1832 | 52 | 5 |
| 64 | Shavkat Rakhmonov | 600.6 | 2146 |  | 2 |
| 65 | Phil Davis | 589.6 | 1956 |  | 4 |
| 66 | Tyron Woodley | 563.6 | 1803 | 55 | 5 |
| 67 | Matt Serra | 559.8 | 1688 |  | 1 |
| 68 | Rashad Evans | 552.5 | 1814 |  | 4 |
| 69 | Derrick Lewis | 535.0 | 1771 |  | 4 |
| 70 | Beneil Dariush | 532.1 | 1850 | 46 | 6 |
| 71 | Fabricio Werdum | 529.6 | 1894 |  | 4 |
| 72 | Belal Muhammad | 529.2 | 1901 | 34 | 6 |
| 73 | Deiveson Figueiredo | 526.2 | 1828 | 53 | 5 |
| 74 | Curtis Blaydes | 525.7 | 1910 | 38 | 5 |
| 75 | Nassourdine Imavov | 518.1 | 1941 | 28 | 6 |
| 76 | Glover Teixeira | 509.7 | 1867 | 41 | 6 |
| 77 | TJ Dillashaw | 507.9 | 1849 |  | 3 |
| 78 | Arman Tsarukyan | 503.2 | 2014 |  | 4 |
| 79 | Joshua Van | 501.6 | 1944 |  | 3 |
| 80 | Jake Shields | 498.9 | 1820 | 51 | 6 |
| 81 | Mirko Filipovic | 497.2 | 1831 |  | 4 |
| 82 | Demian Maia | 485.2 | 1853 | 45 | 6 |
| 83 | Urijah Faber | 472.7 | 1800 |  | 3 |
| 84 | Umar Nurmagomedov | 472.2 | 2027 |  | 4 |
| 85 | Mark Coleman | 453.1 | 1722 |  | 2 |
| 86 | Sean Sherk | 444.6 | 1891 | 43 | 5 |
| 87 | Carlos Condit | 433.9 | 1721 |  | 4 |
| 88 | Alexandre Pantoja | 429.0 | 1869 | 47 | 5 |
| 89 | Matt Hamill | 426.9 | 1652 |  | 2 |
| 90 | Renan Barao | 426.8 | 1648 |  | 3 |
| 91 | Andrei Arlovski | 424.8 | 1780 |  | 4 |
| 92 | Magomed Ankalaev | 419.8 | 1968 |  | 2 |
| 93 | Robbie Lawler | 415.6 | 1705 |  | 3 |
| 94 | Michael Chandler | 414.1 | 1812 |  | 1 |
| 95 | Ian Machado Garry | 412.7 | 2071 |  | 4 |
| 96 | Alistair Overeem | 412.1 | 1810 |  | 4 |
| 97 | Yaroslav Amosov | 411.9 | 2047 |  | 2 |
| 98 | Joseph Benavidez | 411.4 | 1847 |  | 2 |
| 99 | Josh Barnett | 409.0 | 1903 |  | 2 |
| 100 | Yoel Romero | 407.0 | 1867 | 42 | 6 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

How good was a fighter at their best, counting only the peaks they actually
proved? To qualify they need **five wins over contenders inside one ten-year
stretch**, where a contender is an opponent rated 1,750 or better on the night
who also had a tested record of their own: at least eight UFC bouts.

The ten years chosen are the ones holding the most contender wins, not the
highest average. Picking by average rewards the years a fighter lost least — it
made Daniel Cormier's peak his undefeated Strikeforce run and left his UFC title
reign out of it. A peak is a peak because of who was beaten in it.

The order multiplies the two printed columns: how many contenders they beat, by
how far their level stood above the lowest on the board. A great peak proved
once and a good peak proved eleven times are not the same achievement. The wins
are never added to the level — they decide how much of it is credited — so
nothing is counted twice and there is no dial to tune.

65 men qualify, so this top 50 is full. Only 1 woman does. That is a statement
about how few women in the data have a long UFC record, not about the fighters.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Prime | Elite wins |
| ---: | --- | ---: | ---: |
| 1 | Jon Jones | 2210 | 12 |
| 2 | Georges St-Pierre | 2073 | 10 |
| 3 | Islam Makhachev | 2180 | 7 |
| 4 | Alexander Volkanovski | 2048 | 9 |
| 5 | Daniel Cormier | 2080 | 8 |
| 6 | Kamaru Usman | 1968 | 10 |
| 7 | Francis Ngannou | 2037 | 7 |
| 8 | Max Holloway | 1963 | 9 |
| 9 | Ciryl Gane | 2060 | 6 |
| 10 | Merab Dvalishvili | 1974 | 8 |
| 11 | Ilia Topuria | 2119 | 5 |
| 12 | Sean Strickland | 1921 | 10 |
| 13 | Dricus Du Plessis | 2044 | 6 |
| 14 | Israel Adesanya | 1935 | 9 |
| 15 | Jose Aldo | 1930 | 9 |
| 16 | Khamzat Chimaev | 2089 | 5 |
| 17 | Anderson Silva | 1922 | 9 |
| 18 | Charles Oliveira | 1978 | 7 |
| 19 | Vadim Nemkov | 2067 | 5 |
| 20 | Stipe Miocic | 1994 | 6 |
| 21 | Justin Gaethje | 1994 | 6 |
| 22 | Demetrious Johnson | 1982 | 6 |
| 23 | Lyoto Machida | 1966 | 6 |
| 24 | Fedor Emelianenko | 2014 | 5 |
| 25 | Alex Pereira | 1962 | 6 |
| 26 | Petr Yan | 1951 | 6 |
| 27 | Aljamain Sterling | 1945 | 6 |
| 28 | Nassourdine Imavov | 1941 | 6 |
| 29 | Anthony Johnson | 1938 | 6 |
| 30 | Alexander Volkov | 1906 | 7 |
| 31 | Frankie Edgar | 1905 | 7 |
| 32 | Robert Whittaker | 1893 | 7 |
| 33 | Dominick Cruz | 1941 | 5 |
| 34 | Belal Muhammad | 1901 | 6 |
| 35 | Chris Weidman | 1871 | 7 |
| 36 | Ryan Bader | 1926 | 5 |
| 37 | Dustin Poirier | 1922 | 5 |
| 38 | Curtis Blaydes | 1910 | 5 |
| 39 | Brendan Allen | 1908 | 5 |
| 40 | Benson Henderson | 1869 | 6 |
| 41 | Glover Teixeira | 1867 | 6 |
| 42 | Yoel Romero | 1867 | 6 |
| 43 | Sean Sherk | 1891 | 5 |
| 44 | Luke Rockhold | 1863 | 6 |
| 45 | Demian Maia | 1853 | 6 |
| 46 | Beneil Dariush | 1850 | 6 |
| 47 | Alexandre Pantoja | 1869 | 5 |
| 48 | Dan Henderson | 1869 | 5 |
| 49 | Mauricio Rua | 1833 | 6 |
| 50 | Donald Cerrone | 1849 | 5 |

<!-- BOARD:ELITEPRIME50:END -->

### Current — men, top 30

How good is the fighter now. Two screens decide who appears at all, both
borrowed from the boards above rather than invented for this one: they must have
**fought within the last 18 months**, and they must have **at least eight UFC
bouts**.

The recency bar is strict enough to withhold fighters who have not retired. Jon
Jones last fought on 2024-11-16 and Shavkat Rakhmonov on 2024-12-07, so both are
out. The bout count matters because nothing in this kind of model caps an
unbeaten record from above; without it the board seated six Bellator and PFL
fighters in the top thirty. That is not a verdict on those fighters. It is the
model saying it cannot place them, and saying so is more honest than ranking
them anyway.

Time away is charged where a win is priced, not here — that is principle 9 doing
its job. Do not read this board against the two above it: those are backward
looking and a career does not expire, while this one is a claim about today.

<!-- BOARD:CURRENT30:BEGIN -->

| # | Fighter | Rating | UFC bouts | Last bout |
| ---: | --- | ---: | ---: | ---: |
| 1 | Islam Makhachev | 2147 | 18 | 2025-11-15 |
| 2 | Ilia Topuria | 2050 | 10 | 2026-06-14 |
| 3 | Movsar Evloev | 2050 | 10 | 2026-03-21 |
| 4 | Ian Machado Garry | 2036 | 11 | 2025-11-22 |
| 5 | Ciryl Gane | 2036 | 13 | 2026-06-14 |
| 6 | Francis Ngannou | 2029 | 14 | 2026-05-16 |
| 7 | Khamzat Chimaev | 2018 | 10 | 2026-05-09 |
| 8 | Dricus Du Plessis | 2005 | 11 | 2026-07-18 |
| 9 | Arman Tsarukyan | 2003 | 12 | 2025-11-22 |
| 10 | Alexander Volkanovski | 1992 | 18 | 2026-01-31 |
| 11 | Umar Nurmagomedov | 1989 | 9 | 2026-01-24 |
| 12 | Justin Gaethje | 1985 | 16 | 2026-06-14 |
| 13 | Merab Dvalishvili | 1967 | 17 | 2025-12-06 |
| 14 | Carlos Ulberg | 1967 | 11 | 2026-04-11 |
| 15 | Charles Oliveira | 1961 | 36 | 2026-03-07 |
| 16 | Sean Strickland | 1945 | 25 | 2026-05-09 |
| 17 | Gabriel Bonfim | 1944 | 8 | 2026-06-06 |
| 18 | Nassourdine Imavov | 1939 | 11 | 2025-09-06 |
| 19 | Petr Yan | 1938 | 16 | 2025-12-06 |
| 20 | Magomed Ankalaev | 1936 | 16 | 2026-07-25 |
| 21 | Max Holloway | 1932 | 33 | 2026-07-11 |
| 22 | Sean O'Malley | 1932 | 15 | 2026-06-14 |
| 23 | Joshua Van | 1929 | 11 | 2026-05-09 |
| 24 | Corey Anderson | 1923 | 15 | 2025-10-03 |
| 25 | Mario Bautista | 1922 | 15 | 2026-07-11 |
| 26 | Sean Brady | 1920 | 11 | 2026-05-09 |
| 27 | Lerone Murphy | 1918 | 11 | 2026-03-21 |
| 28 | Sergei Pavlovich | 1917 | 12 | 2026-05-30 |
| 29 | Alex Pereira | 1916 | 13 | 2026-06-14 |
| 30 | Aljamain Sterling | 1915 | 23 | 2026-04-25 |

<!-- BOARD:CURRENT30:END -->

## What the numbers cannot do

- **The all-time score is backward looking.** An opponent is priced on
  everything now known about them, so it measures how good a win turned out to
  be, not how good it looked on the night.
- **The contender resume favours long careers**, though it counts at most one
  win per active year. Read it as context, not as a separate measure of skill.
- **How much of a career we can see is my judgement, not a finding.** It is a
  declared ranking of promotions. 64% of rated fights carry no promotion name,
  and those are left out rather than counted as small shows, because not knowing
  where a fight happened is not evidence that it was minor. A career
  identifiable from only a handful of fights is then pulled toward the average,
  so thin evidence is not credited at full confidence.
- **Time away is charged at a rate I chose, not one the data gave up.** It
  cannot be measured here: a fighter who returns badly often does not fight
  again, so the decline never becomes an observed change. The same survivorship
  makes the measured ageing curve claim a 42-year-old declines more slowly than
  a 37-year-old, which is not true.
- **A gap in the schedule is not proof of absence.** It is equally the shape of
  a fight the sources do not hold, which is why the charge is capped. Coverage
  is 99.8% complete for the fighters who can move a published board, and
  thinner outside them.
- **Weight class and fighter identity are partly inferred.** About 17% of
  filled weight classes are wrong for that particular fight, and four fighters
  cannot be told apart from namesakes at all, so only their UFC record is held.
- **No model can recover fights missing from every source.**

The full detail, and the changes already tested and refused, are in the
[decision register](docs/DECISIONS.md).

## Data

Three sources feed the published rankings: the UFC's own fight record, recovered
early UFC bouts that pre-date the unified rules, and major-promotion history
from Sherdog — PRIDE, Bellator, Strikeforce, WEC, RIZIN and Affliction. A
fourth, a limited FightMatrix sample, is kept for comparison and is never mixed
in unless it is asked for by name.

Every fight is stored once, with a note of which sources carried it, which is
what lets a narrower release be published without quietly dropping fights a
wider source also held. Whole-career records are now held for 1,821 of the 1,825
fighters this can affect.

Ownership, licensing and known gaps are in
[Source Matrix](data/SOURCE_MATRIX.md). Release history is in
[Data Changelog](data/CHANGELOG.md).

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
