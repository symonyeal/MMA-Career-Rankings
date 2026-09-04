# Symon UFC Rank Engine

Rankings are arguments. This one argues in code: every placement traces to
recorded fights and a declared rule, never a hidden reputation bonus.

## A ranking is a set of decisions

### Weight classes are different competitive worlds

Most divisions rarely meet, so raw rating gaps between them are not reliable
pound-for-pound evidence. Career division is where most effective appearances
occurred; recency only breaks a tie. Current division changes after a UFC title
win, not after a cameo or title loss. Each active year is judged against its
division's top ten percent, capped at roughly the fifth-best fighter once the
class matures; divisions with fewer than 30 fighter-years use the sport-wide
line. Men's and women's boards stay separate because no results connect them.

### The UFC is the anchor, not the whole sport

The fit includes early UFC and major-promotion careers and gives no promotion a
bonus inside the rating -- crossover results locate them, and promotion enters
afterward only as confidence in where a career was proved. The UFC is `1.00`,
PRIDE `0.95`, Affliction `0.90`, WEC and Strikeforce `0.88`, Bellator `0.65`, and
PFL, RIZIN, ONE and DREAM `0.60`. The exposure factor blends the career average
with its strongest quarter and pulls thin evidence toward the pooled average.
An unknown promotion is missing evidence, not a weak show.

### The result is not just win or loss

A knockout or submission scores `1.00`, a unanimous decision `0.95`, a split or
majority decision `0.90`, a disqualification `0.85`, and a draw `0.50` for each
fighter. No-contests, overturned results and bouts that could not continue are
excluded.

### A later career can change the meaning of an earlier fight

The rating fits every career together, so later evidence can revalue an earlier
win. Scores are displayed around 1,500, and every fighter carries one neutral
virtual bout—half a win and half a loss—so 1–0 does not outrank 10–0 merely
because both are unbeaten. Skill can change with time and age; there is no
hand-written era bonus.

### One fight gets one entry, and one idea gets one payment

One authoritative row survives when sources repeat a bout, and publication
stops if a duplicate remains. Whole careers are required because missing losses
bias ratings upward. Opponent
strength is paid in the rating, each active year enters career skill once, and
the contender résumé is capped once per year. Titles are priced through the
opponent beaten, not a flat belt or multi-division bonus.

## Three questions, three boards

### All-time: what did the career add up to?

```text
All-time = 30% championships + 17.5% career skill + 52.5% contender résumé
```

Each component is divided by the mean of its own top 100 before combining.
Career skill sums each active year above its division-year line. The résumé
prices wins over opponents rated at least 1,750 before the bout and tested by at
least eight UFC fights, capped at one contribution per year. Returning opponents
lose 90 points per excess era-normalized turnaround, capped at four. Title wins
are priced against the opponent; recognized major titles carry a `0.05` floor.

### Prime: how high was the proven peak?

Prime selects the ten-year stretch with the most qualifying contender wins, ties
broken by average rating, then ranks on both that average and the count. Five
wins are required.

### Current: who can still be described now?

Current carries the latest rating through the age curve, then pulls thinly
established careers toward 1,750. A fighter needs 13 rated appearances, eight
UFC bouts and a fight within 18 months.

PED, disqualification and missed-weight deductions remain a separate Integrity
audit and never alter a published board.

## What is published

The full [Published UFC Rankings](RANKINGS.md) adds the three women's boards.

<!-- PUBLICATION:RELEASE:BEGIN -->

| Release fact | Value |
| --- | ---: |
| Dataset | 2026-08-13 |
| Data through | 2026-08-30 |
| Included records | UFC, early UFC and major-promotion careers |
| All-time basis | All-time career score |
| Rated fights | 81,479 |
| Rated fighters | 34,108 |
| Available fight records | 82,961 |
| Whole-career coverage | 1,821 of 1,825 eligible fighters (99.8%) |
| Prime contender threshold | 1,750 — reached by 19.5% of established fighters |
| Prime qualifiers | 66 men; 1 woman |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

**Prime** is the average level in the ten-year period with the most
contender wins, **Prime rank** is the position on the Prime board below and
**Elite wins** is the evidence behind that position; a blank rank means the
fighter did not qualify.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Prime | Prime rank | Elite wins |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | 3723.4 | 2211 | 1 | 12 |
| 2 | Islam Makhachev | 2892.2 | 2198 | 2 | 9 |
| 3 | Georges St-Pierre | 2109.6 | 2074 | 3 | 10 |
| 4 | Demetrious Johnson | 2056.2 | 1982 | 22 | 6 |
| 5 | Daniel Cormier | 2041.3 | 2080 | 5 | 8 |
| 6 | Jose Aldo | 1933.1 | 1930 | 15 | 9 |
| 7 | Alexander Volkanovski | 1902.0 | 2051 | 4 | 9 |
| 8 | Stipe Miocic | 1767.3 | 1994 | 21 | 6 |
| 9 | Anderson Silva | 1627.4 | 1922 | 17 | 9 |
| 10 | Francis Ngannou | 1573.1 | 2037 | 7 | 7 |
| 11 | Dominick Cruz | 1512.3 | 1941 | 34 | 5 |
| 12 | Israel Adesanya | 1484.6 | 1935 | 14 | 9 |
| 13 | Max Holloway | 1473.3 | 1963 | 8 | 9 |
| 14 | Ilia Topuria | 1435.8 | 2120 | 12 | 5 |
| 15 | Khabib Nurmagomedov | 1410.6 | 2172 |  | 4 |
| 16 | Merab Dvalishvili | 1393.7 | 1974 | 10 | 8 |
| 17 | Sean Strickland | 1319.2 | 1921 | 11 | 10 |
| 18 | Lyoto Machida | 1213.2 | 1966 | 23 | 6 |
| 19 | Alex Pereira | 1155.4 | 1964 | 25 | 6 |
| 20 | Matt Hughes | 1148.3 | 1831 |  | 3 |
| 21 | Justin Gaethje | 1130.8 | 1995 | 20 | 6 |
| 22 | Fedor Emelianenko | 1108.8 | 2014 | 24 | 5 |
| 23 | Kamaru Usman | 1083.2 | 1968 | 6 | 10 |
| 24 | Charles Oliveira | 1078.8 | 1980 | 18 | 7 |
| 25 | Aljamain Sterling | 1073.9 | 1945 | 27 | 6 |
| 26 | Benson Henderson | 1069.7 | 1869 | 39 | 6 |
| 27 | Dricus Du Plessis | 1003.6 | 2044 | 13 | 6 |
| 28 | Dustin Poirier | 973.2 | 1927 | 32 | 6 |
| 29 | Ciryl Gane | 947.0 | 2059 | 9 | 6 |
| 30 | Frankie Edgar | 930.9 | 1906 | 30 | 7 |
| 31 | Khamzat Chimaev | 925.1 | 2089 | 16 | 5 |
| 32 | Cain Velasquez | 889.5 | 1959 |  | 3 |
| 33 | Petr Yan | 887.9 | 1952 | 26 | 6 |
| 34 | Junior Dos Santos | 869.3 | 1913 |  | 4 |
| 35 | Dan Henderson | 859.8 | 1868 | 48 | 5 |
| 36 | Anthony Pettis | 825.2 | 1759 | 63 | 6 |
| 37 | Chris Weidman | 817.8 | 1871 | 35 | 7 |
| 38 | Patricio Freire | 813.8 | 1927 |  | 3 |
| 39 | Henry Cejudo | 806.2 | 1873 |  | 4 |
| 40 | Mauricio Rua | 804.4 | 1833 | 49 | 6 |
| 41 | Ryan Bader | 778.1 | 1926 | 36 | 5 |
| 42 | Randy Couture | 776.1 | 1767 | 62 | 5 |
| 43 | Conor McGregor | 771.8 | 1838 |  | 4 |
| 44 | Vadim Nemkov | 762.6 | 2066 | 19 | 5 |
| 45 | Movsar Evloev | 726.9 | 2104 |  | 4 |
| 46 | Robert Whittaker | 713.1 | 1893 | 33 | 7 |
| 47 | BJ Penn | 710.0 | 1793 | 58 | 5 |
| 48 | Tito Ortiz | 692.0 | 1787 |  | 4 |
| 49 | Gegard Mousasi | 668.3 | 1920 |  | 4 |
| 50 | Antonio Rodrigo Nogueira | 664.0 | 1890 |  | 4 |
| 51 | Sean O'Malley | 649.3 | 1954 |  | 4 |
| 52 | Anthony Johnson | 647.4 | 1941 | 28 | 6 |
| 53 | Chuck Liddell | 646.5 | 1815 | 54 | 5 |
| 54 | Vitor Belfort | 641.1 | 1781 | 61 | 5 |
| 55 | Alexander Volkov | 636.5 | 1905 | 31 | 7 |
| 56 | Eddie Alvarez | 632.4 | 1763 |  | 4 |
| 57 | Leon Edwards | 627.0 | 1887 |  | 4 |
| 58 | Luke Rockhold | 620.5 | 1863 | 43 | 6 |
| 59 | Rafael Dos Anjos | 618.7 | 1771 | 59 | 7 |
| 60 | Wanderlei Silva | 608.1 | 1812 |  | 4 |
| 61 | Tom Aspinall | 605.7 | 1933 |  | 4 |
| 62 | Jan Blachowicz | 587.1 | 1801 | 56 | 5 |
| 63 | Phil Davis | 585.2 | 1956 |  | 4 |
| 64 | Tyron Woodley | 573.0 | 1802 | 55 | 5 |
| 65 | Shavkat Rakhmonov | 572.2 | 2140 |  | 2 |
| 66 | Deiveson Figueiredo | 562.9 | 1830 | 53 | 5 |
| 67 | Beneil Dariush | 551.9 | 1850 | 46 | 6 |
| 68 | Quinton Jackson | 545.1 | 1832 | 52 | 5 |
| 69 | Rashad Evans | 540.9 | 1814 |  | 4 |
| 70 | Derrick Lewis | 539.0 | 1771 |  | 4 |
| 71 | TJ Dillashaw | 535.7 | 1850 |  | 3 |
| 72 | Joshua Van | 531.3 | 1963 |  | 3 |
| 73 | Curtis Blaydes | 526.2 | 1909 | 37 | 5 |
| 74 | Fabricio Werdum | 526.0 | 1892 |  | 4 |
| 75 | Belal Muhammad | 517.3 | 1898 | 40 | 5 |
| 76 | Nassourdine Imavov | 513.8 | 1940 | 29 | 6 |
| 77 | Matt Serra | 511.6 | 1689 |  | 1 |
| 78 | Mirko Filipovic | 502.9 | 1831 |  | 4 |
| 79 | Glover Teixeira | 496.0 | 1868 | 41 | 6 |
| 80 | Demian Maia | 487.5 | 1853 | 45 | 6 |
| 81 | Umar Nurmagomedov | 477.8 | 2027 |  | 4 |
| 82 | Arman Tsarukyan | 475.8 | 2012 |  | 4 |
| 83 | Usman Nurmagomedov | 470.2 |  |  |  |
| 84 | Jake Shields | 465.2 | 1820 | 51 | 6 |
| 85 | Alexandre Pantoja | 464.6 | 1873 | 47 | 5 |
| 86 | Joseph Benavidez | 464.3 | 1848 |  | 2 |
| 87 | Michael Chandler | 453.3 | 1811 |  | 1 |
| 88 | Mark Coleman | 442.5 | 1722 |  | 2 |
| 89 | Urijah Faber | 438.6 | 1800 |  | 3 |
| 90 | Robbie Lawler | 437.8 | 1705 |  | 3 |
| 91 | Sean Sherk | 433.4 | 1891 | 44 | 5 |
| 92 | Brandon Moreno | 430.2 | 1775 |  | 3 |
| 93 | Magomed Ankalaev | 427.3 | 1969 |  | 2 |
| 94 | Renan Barao | 424.8 | 1648 |  | 3 |
| 95 | Andrei Arlovski | 423.2 | 1781 |  | 4 |
| 96 | Carlos Condit | 421.9 | 1720 |  | 4 |
| 97 | Rich Franklin | 420.5 | 1801 |  | 2 |
| 98 | Matt Hamill | 419.0 | 1651 |  | 2 |
| 99 | Donald Cerrone | 409.3 | 1849 | 50 | 5 |
| 100 | Raphael Assuncao | 408.0 | 1724 | 65 | 5 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

The table prints both inputs instead of the internal ordering index.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Prime | Elite wins |
| ---: | --- | ---: | ---: |
| 1 | Jon Jones | 2211 | 12 |
| 2 | Islam Makhachev | 2198 | 9 |
| 3 | Georges St-Pierre | 2074 | 10 |
| 4 | Alexander Volkanovski | 2051 | 9 |
| 5 | Daniel Cormier | 2080 | 8 |
| 6 | Kamaru Usman | 1968 | 10 |
| 7 | Francis Ngannou | 2037 | 7 |
| 8 | Max Holloway | 1963 | 9 |
| 9 | Ciryl Gane | 2059 | 6 |
| 10 | Merab Dvalishvili | 1974 | 8 |
| 11 | Sean Strickland | 1921 | 10 |
| 12 | Ilia Topuria | 2120 | 5 |
| 13 | Dricus Du Plessis | 2044 | 6 |
| 14 | Israel Adesanya | 1935 | 9 |
| 15 | Jose Aldo | 1930 | 9 |
| 16 | Khamzat Chimaev | 2089 | 5 |
| 17 | Anderson Silva | 1922 | 9 |
| 18 | Charles Oliveira | 1980 | 7 |
| 19 | Vadim Nemkov | 2066 | 5 |
| 20 | Justin Gaethje | 1995 | 6 |
| 21 | Stipe Miocic | 1994 | 6 |
| 22 | Demetrious Johnson | 1982 | 6 |
| 23 | Lyoto Machida | 1966 | 6 |
| 24 | Fedor Emelianenko | 2014 | 5 |
| 25 | Alex Pereira | 1964 | 6 |
| 26 | Petr Yan | 1952 | 6 |
| 27 | Aljamain Sterling | 1945 | 6 |
| 28 | Anthony Johnson | 1941 | 6 |
| 29 | Nassourdine Imavov | 1940 | 6 |
| 30 | Frankie Edgar | 1906 | 7 |
| 31 | Alexander Volkov | 1905 | 7 |
| 32 | Dustin Poirier | 1927 | 6 |
| 33 | Robert Whittaker | 1893 | 7 |
| 34 | Dominick Cruz | 1941 | 5 |
| 35 | Chris Weidman | 1871 | 7 |
| 36 | Ryan Bader | 1926 | 5 |
| 37 | Curtis Blaydes | 1909 | 5 |
| 38 | Brendan Allen | 1908 | 5 |
| 39 | Benson Henderson | 1869 | 6 |
| 40 | Belal Muhammad | 1898 | 5 |
| 41 | Glover Teixeira | 1868 | 6 |
| 42 | Yoel Romero | 1867 | 6 |
| 43 | Luke Rockhold | 1863 | 6 |
| 44 | Sean Sherk | 1891 | 5 |
| 45 | Demian Maia | 1853 | 6 |
| 46 | Beneil Dariush | 1850 | 6 |
| 47 | Alexandre Pantoja | 1873 | 5 |
| 48 | Dan Henderson | 1868 | 5 |
| 49 | Mauricio Rua | 1833 | 6 |
| 50 | Donald Cerrone | 1849 | 5 |

<!-- BOARD:ELITEPRIME50:END -->

### Current — men, top 30

<!-- BOARD:CURRENT30:BEGIN -->

| # | Fighter | Rating | UFC bouts | Last bout |
| ---: | --- | ---: | ---: | ---: |
| 1 | Islam Makhachev | 2156 | 18 | 2026-08-15 |
| 2 | Movsar Evloev | 2041 | 10 | 2026-03-21 |
| 3 | Ilia Topuria | 2034 | 10 | 2026-06-14 |
| 4 | Ciryl Gane | 2025 | 13 | 2026-06-14 |
| 5 | Francis Ngannou | 2019 | 14 | 2026-05-16 |
| 6 | Khamzat Chimaev | 2001 | 10 | 2026-05-09 |
| 7 | Ian Machado Garry | 1991 | 11 | 2026-08-15 |
| 8 | Arman Tsarukyan | 1990 | 12 | 2025-11-22 |
| 9 | Dricus Du Plessis | 1986 | 11 | 2026-07-18 |
| 10 | Alexander Volkanovski | 1981 | 18 | 2026-01-31 |
| 11 | Umar Nurmagomedov | 1978 | 9 | 2026-01-24 |
| 12 | Justin Gaethje | 1962 | 16 | 2026-06-14 |
| 13 | Merab Dvalishvili | 1958 | 17 | 2025-12-06 |
| 14 | Carlos Ulberg | 1958 | 11 | 2026-04-11 |
| 15 | Charles Oliveira | 1956 | 36 | 2026-03-07 |
| 16 | Sean Strickland | 1938 | 25 | 2026-05-09 |
| 17 | Joshua Van | 1931 | 11 | 2026-05-09 |
| 18 | Nassourdine Imavov | 1931 | 11 | 2025-09-06 |
| 19 | Gabriel Bonfim | 1929 | 8 | 2026-06-06 |
| 20 | Max Holloway | 1929 | 33 | 2026-07-11 |
| 21 | Magomed Ankalaev | 1928 | 16 | 2026-07-25 |
| 22 | Sean O'Malley | 1925 | 15 | 2026-06-14 |
| 23 | Petr Yan | 1923 | 16 | 2025-12-06 |
| 24 | Corey Anderson | 1919 | 15 | 2025-10-03 |
| 25 | Lerone Murphy | 1915 | 11 | 2026-03-21 |
| 26 | Mario Bautista | 1915 | 15 | 2026-07-11 |
| 27 | Alex Pereira | 1911 | 13 | 2026-06-14 |
| 28 | Aljamain Sterling | 1908 | 23 | 2026-04-25 |
| 29 | Sean Brady | 1906 | 11 | 2026-05-09 |
| 30 | Sergei Pavlovich | 1905 | 12 | 2026-05-30 |

<!-- BOARD:CURRENT30:END -->

## Where the numbers stop

All-time is retrospective: later evidence changes an opponent's value. Elite-win
counts still reward opportunity, and the age curve underrepresents decline in
fighters who never returned.

Promotion labels are missing from 57% of rated fights. Held-out checks suggest
11% of filled weight classes are wrong, and four eligible careers cannot be
matched uniquely. Missing data is shrunk or excluded, never guessed at full
confidence. See the [decision register](docs/DECISIONS.md) for evidence and
rejected changes.

## Project map

| Path | Use it for |
| --- | --- |
| [`RANKINGS.md`](RANKINGS.md) | The complete men's and women's All-time, Prime and Current release |
| `ratings/` | Ratings, divisions, résumés and board policy |
| `loaders/` | Source ingestion, identity and fight-table construction |
| `data/snapshots/<date>/` | Release inputs, outputs and manifests |
| [`data/SOURCE_MATRIX.md`](data/SOURCE_MATRIX.md) and [`data/CHANGELOG.md`](data/CHANGELOG.md) | Source coverage and release history |
| [`docs/`](docs/) | Method, coverage and decision records |
| `analysis/` | Charts and notebook |
| `tests/` | Verification |
| `_archive/` | Retired work |

The supported runtime is the machine's system Python:

```text
C:\Python314\python.exe -m pip install -r requirements.txt
C:\Python314\python.exe -m pytest -q
C:\Python314\python.exe -m ruff check .
C:\Python314\python.exe build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
C:\Python314\python.exe build_database.py --snapshot-dir data/snapshots/2026-08-13
C:\Python314\python.exe analysis/build_notebook.py
```

`refresh.py` runs the complete source-to-publication workflow. Never hand-edit a
generated table; `build_boards.py` updates both publications.
