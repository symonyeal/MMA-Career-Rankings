# Symon UFC Rank Engine

Rankings are arguments. This one makes its argument in code: start with recorded
fights, then state how divisions, promotions, titles and incomplete evidence are
treated. A disputed placement should lead to a fight or a declared rule, never
a hidden reputation bonus.

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

The fit includes early UFC and major-promotion careers, but gives no promotion a
bonus inside the fight rating; crossover results locate them. Promotion enters
only afterward as confidence in where the career was proved. The UFC is `1.00`,
PRIDE `0.95`, Affliction `0.90`, WEC and Strikeforce `0.88`, Bellator `0.65`, and
PFL, RIZIN, ONE and DREAM `0.60`. The exposure factor blends the career average
with its strongest quarter and pulls thin evidence toward the pooled average.
An unknown promotion is missing evidence, not a weak show.

### The result is not just win or loss

A knockout or submission scores `1.00`, a unanimous decision `0.95`, a split or
majority decision `0.90`, a disqualification `0.85`, and a draw `0.50` for each
fighter. These are fractional outcomes, not résumé bonuses. No-contests,
overturned results and bouts that could not continue are excluded.

### A later career can change the meaning of an earlier fight

The rating fits every career together, so later evidence can revalue an earlier
win. Scores are displayed around 1,500, and every fighter carries one neutral
virtual bout—half a win and half a loss—so 1–0 does not outrank 10–0 merely
because both are unbeaten. Skill can change with time and age; there is no
hand-written era bonus.

### One fight gets one entry, and one idea gets one payment

One authoritative row survives when sources repeat a bout, and publication
stops if a duplicate remains. Whole careers are required because missing losses
bias ratings upward; 1,821 of 1,825 eligible careers are merged. Opponent
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

Prime selects the ten-year stretch with the most qualifying contender wins,
breaking ties by average rating. Five wins are required. Ranking rewards both
the average level and the number of qualifying wins.

### Current: who can still be described now?

Current carries the latest rating through the age curve, then pulls thinly
established careers toward 1,750. A fighter needs 13 rated appearances, eight
UFC bouts and a fight within 18 months.

PED, disqualification and missed-weight deductions remain a separate Integrity
audit and never alter a published board.

## What is published

The full [Published UFC Rankings](RANKINGS.md) adds the three women's boards. One
build updates and validates both documents.

<!-- PUBLICATION:RELEASE:BEGIN -->

| Release fact | Value |
| --- | ---: |
| Dataset | 2026-08-13 |
| Data through | 2026-08-30 |
| Included records | UFC, early UFC and major-promotion careers |
| All-time basis | All-time career score |
| Rated fights | 81,281 |
| Rated fighters | 34,085 |
| Available fight records | 82,675 |
| Whole-career coverage | 1,821 of 1,825 eligible fighters (99.8%) |
| Prime contender threshold | 1,750 — reached by 19.5% of established fighters |
| Prime qualifiers | 65 men; 1 woman |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

**Prime** is the average level in the ten-year period with the most
contender wins, **Prime rank** is the position on the Prime board below and
**Elite wins** is the evidence behind that position; a blank rank means the
fighter did not qualify.

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

The table prints both inputs instead of the internal ordering index.

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

Only Current has an activity cutoff.

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

## Where the numbers stop

All-time is retrospective: later evidence changes an opponent's value. Elite-win
counts still reward opportunity, and the age curve underrepresents decline in
fighters who never returned.

Promotion labels are missing from 64% of rated fights. Held-out checks suggest
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

The supported runtime is the machine's system Python. These are the ordinary
entry points:

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
