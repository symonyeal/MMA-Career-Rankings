# Symon UFC Rank Engine

Every all-time list is an argument. This one makes its argument in code, so if
you do not like where somebody landed you can point at a fight or a rule and say
why. There is no reputation bonus buried in here.

## A ranking is a set of decisions

### Weight classes are different competitive worlds

Fighters from different divisions almost never meet, so there is no chain of
results tying a flyweight's rating to a heavyweight's. A fighter's division is
wherever they did most of their real work, and recency only breaks a tie. Moving
up counts once they have won a UFC title at the new weight, not when they take a
one-off fight upstairs or lose the belt. Each year of a career is measured
against the top ten percent of its own division that year, about the fifth-best
fighter once a class has filled out; divisions with fewer than 30 fighter-years
on record borrow the sport-wide line. Men and women get separate boards, because
nothing in the results connects the two.

### The UFC is the anchor, not the whole sport

The rating does not care which banner you fought under, and it is the crossover
fights that put PRIDE or Bellator on the same scale as the UFC. Promotion shows
up only afterwards, as a read on how well tested a career was: the UFC is
`1.00`, PRIDE `0.95`, Affliction `0.90`, WEC and Strikeforce `0.88`, Bellator
`0.65`, and PFL, RIZIN, ONE and DREAM `0.60`. That number blends a fighter's
career average with their strongest stretch and pulls thin records toward the
middle. When we do not know who ran the show, that is missing information, not
proof it was a small one.

### The result is not just win or loss

A knockout or submission scores `1.00`, a unanimous decision `0.95`, a split or
majority decision `0.90`, a disqualification `0.85`, and a draw `0.50` for each
fighter. No-contests, overturned wins and fights stopped by something nobody
controls do not count at all.

### A later career can change the meaning of an earlier fight

Every career is fitted together at once, so what a win was worth can change
years later: beat someone who turns out to be an all-timer and that win grows.
Ratings are displayed around 1,500, and everybody carries one neutral virtual
bout—half a win and half a loss—which is why a 1–0 fighter does not leapfrog a
10–0 fighter just because neither has lost yet. Fighters get better and then
worse with age, and none of that comes from a hand-typed era bonus.

### One fight gets one entry, and one idea gets one payment

When two sources carry the same fight, one row survives, and the build refuses
to publish if a duplicate slips through. We need whole careers rather than just
the UFC run, because a fighter whose losses are missing looks better than they
were. How good the opponent was already lives in that opponent's rating, each
active year counts once toward career skill, the contender résumé takes one win
per year, and a title is priced by who you actually beat for it, not by a flat
bonus for holding one.

## Three questions, three boards

### All-time: what did the career add up to?

```text
All-time = 30% championships + 17.5% career skill + 52.5% contender résumé
```

Each piece is divided by the average of its own top 100 first, so those
percentages mean what they say. Career skill adds up every year a fighter spent
above their division's line. The résumé counts wins over opponents rated at least
1,750 going in and tested by at least eight UFC fights, one win per year, and
opponents coming back off a layoff lose 90 points per excess turnaround, capped
at four. Title wins are priced by the opponent you beat for the belt, though the
recognized major titles carry a `0.05` floor.

### Prime: how high was the proven peak?

Prime looks for the ten-year stretch with the most qualifying contender wins and
ranks on both that count and the average rating behind it. Five wins are
required.

### Current: who can still be described now?

Current takes the last rating we have, ages it forward, and pulls thin records
back toward 1,750. To make this board a fighter needs 13 rated appearances,
eight UFC bouts and a fight within 18 months.

PED, disqualification and missed-weight deductions sit in a separate Integrity
audit. They never move a published board.

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

**Prime** and **Prime rank** come from the Prime board below, and **Elite
wins** is the evidence behind that rank. A blank rank means the fighter did not
qualify, not that they placed last.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Division | Score | Prime | Prime rank | Elite wins |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 3723.4 | 2211 | 1 | 12 |
| 2 | Islam Makhachev | Lightweight | 2892.2 | 2198 | 2 | 9 |
| 3 | Georges St-Pierre | Welterweight | 2109.6 | 2074 | 3 | 10 |
| 4 | Demetrious Johnson | Flyweight | 2056.2 | 1982 | 22 | 6 |
| 5 | Daniel Cormier | Light Heavyweight | 2041.3 | 2080 | 5 | 8 |
| 6 | Jose Aldo | Featherweight | 1933.1 | 1930 | 15 | 9 |
| 7 | Alexander Volkanovski | Featherweight | 1902.0 | 2051 | 4 | 9 |
| 8 | Stipe Miocic | Heavyweight | 1767.3 | 1994 | 21 | 6 |
| 9 | Anderson Silva | Middleweight | 1627.4 | 1922 | 17 | 9 |
| 10 | Francis Ngannou | Heavyweight | 1573.1 | 2037 | 7 | 7 |
| 11 | Dominick Cruz | Bantamweight | 1512.3 | 1941 | 34 | 5 |
| 12 | Israel Adesanya | Middleweight | 1484.6 | 1935 | 14 | 9 |
| 13 | Max Holloway | Featherweight | 1473.3 | 1963 | 8 | 9 |
| 14 | Ilia Topuria | Featherweight | 1435.8 | 2120 | 12 | 5 |
| 15 | Khabib Nurmagomedov | Lightweight | 1410.6 | 2172 |  | 4 |
| 16 | Merab Dvalishvili | Bantamweight | 1393.7 | 1974 | 10 | 8 |
| 17 | Sean Strickland | Middleweight | 1319.2 | 1921 | 11 | 10 |
| 18 | Lyoto Machida | Light Heavyweight | 1213.2 | 1966 | 23 | 6 |
| 19 | Alex Pereira | Light Heavyweight | 1155.4 | 1964 | 25 | 6 |
| 20 | Matt Hughes | Welterweight | 1148.3 | 1831 |  | 3 |
| 21 | Justin Gaethje | Lightweight | 1130.8 | 1995 | 20 | 6 |
| 22 | Fedor Emelianenko | Heavyweight | 1108.8 | 2014 | 24 | 5 |
| 23 | Kamaru Usman | Welterweight | 1083.2 | 1968 | 6 | 10 |
| 24 | Charles Oliveira | Lightweight | 1078.8 | 1980 | 18 | 7 |
| 25 | Aljamain Sterling | Bantamweight | 1073.9 | 1945 | 27 | 6 |
| 26 | Benson Henderson | Lightweight | 1069.7 | 1869 | 39 | 6 |
| 27 | Dricus Du Plessis | Middleweight | 1003.6 | 2044 | 13 | 6 |
| 28 | Dustin Poirier | Lightweight | 973.2 | 1927 | 32 | 6 |
| 29 | Ciryl Gane | Heavyweight | 947.0 | 2059 | 9 | 6 |
| 30 | Frankie Edgar | Lightweight | 930.9 | 1906 | 30 | 7 |
| 31 | Khamzat Chimaev | Middleweight | 925.1 | 2089 | 16 | 5 |
| 32 | Cain Velasquez | Heavyweight | 889.5 | 1959 |  | 3 |
| 33 | Petr Yan | Bantamweight | 887.9 | 1952 | 26 | 6 |
| 34 | Junior Dos Santos | Heavyweight | 869.3 | 1913 |  | 4 |
| 35 | Dan Henderson | Middleweight | 859.8 | 1868 | 48 | 5 |
| 36 | Anthony Pettis | Lightweight | 825.2 | 1759 | 63 | 6 |
| 37 | Chris Weidman | Middleweight | 817.8 | 1871 | 35 | 7 |
| 38 | Patricio Freire | Featherweight | 813.8 | 1927 |  | 3 |
| 39 | Henry Cejudo | Flyweight | 806.2 | 1873 |  | 4 |
| 40 | Mauricio Rua | Light Heavyweight | 804.4 | 1833 | 49 | 6 |
| 41 | Ryan Bader | Light Heavyweight | 778.1 | 1926 | 36 | 5 |
| 42 | Randy Couture | Heavyweight | 776.1 | 1767 | 62 | 5 |
| 43 | Conor McGregor | Featherweight | 771.8 | 1838 |  | 4 |
| 44 | Vadim Nemkov | Light Heavyweight | 762.6 | 2066 | 19 | 5 |
| 45 | Movsar Evloev | Featherweight | 726.9 | 2104 |  | 4 |
| 46 | Robert Whittaker | Middleweight | 713.1 | 1893 | 33 | 7 |
| 47 | BJ Penn | Lightweight | 710.0 | 1793 | 58 | 5 |
| 48 | Tito Ortiz | Light Heavyweight | 692.0 | 1787 |  | 4 |
| 49 | Gegard Mousasi | Middleweight | 668.3 | 1920 |  | 4 |
| 50 | Antonio Rodrigo Nogueira | Heavyweight | 664.0 | 1890 |  | 4 |
| 51 | Sean O'Malley | Bantamweight | 649.3 | 1954 |  | 4 |
| 52 | Anthony Johnson | Light Heavyweight | 647.4 | 1941 | 28 | 6 |
| 53 | Chuck Liddell | Light Heavyweight | 646.5 | 1815 | 54 | 5 |
| 54 | Vitor Belfort | Middleweight | 641.1 | 1781 | 61 | 5 |
| 55 | Alexander Volkov | Heavyweight | 636.5 | 1905 | 31 | 7 |
| 56 | Eddie Alvarez | Lightweight | 632.4 | 1763 |  | 4 |
| 57 | Leon Edwards | Welterweight | 627.0 | 1887 |  | 4 |
| 58 | Luke Rockhold | Middleweight | 620.5 | 1863 | 43 | 6 |
| 59 | Rafael Dos Anjos | Lightweight | 618.7 | 1771 | 59 | 7 |
| 60 | Wanderlei Silva | Light Heavyweight | 608.1 | 1812 |  | 4 |
| 61 | Tom Aspinall | Heavyweight | 605.7 | 1933 |  | 4 |
| 62 | Jan Blachowicz | Light Heavyweight | 587.1 | 1801 | 56 | 5 |
| 63 | Phil Davis | Light Heavyweight | 585.2 | 1956 |  | 4 |
| 64 | Tyron Woodley | Welterweight | 573.0 | 1802 | 55 | 5 |
| 65 | Shavkat Rakhmonov | Welterweight | 572.2 | 2140 |  | 2 |
| 66 | Deiveson Figueiredo | Flyweight | 562.9 | 1830 | 53 | 5 |
| 67 | Beneil Dariush | Lightweight | 551.9 | 1850 | 46 | 6 |
| 68 | Quinton Jackson | Light Heavyweight | 545.1 | 1832 | 52 | 5 |
| 69 | Rashad Evans | Light Heavyweight | 540.9 | 1814 |  | 4 |
| 70 | Derrick Lewis | Heavyweight | 539.0 | 1771 |  | 4 |
| 71 | TJ Dillashaw | Bantamweight | 535.7 | 1850 |  | 3 |
| 72 | Joshua Van | Flyweight | 531.3 | 1963 |  | 3 |
| 73 | Curtis Blaydes | Heavyweight | 526.2 | 1909 | 37 | 5 |
| 74 | Fabricio Werdum | Heavyweight | 526.0 | 1892 |  | 4 |
| 75 | Belal Muhammad | Welterweight | 517.3 | 1898 | 40 | 5 |
| 76 | Nassourdine Imavov | Middleweight | 513.8 | 1940 | 29 | 6 |
| 77 | Matt Serra | Welterweight | 511.6 | 1689 |  | 1 |
| 78 | Mirko Filipovic | Heavyweight | 502.9 | 1831 |  | 4 |
| 79 | Glover Teixeira | Light Heavyweight | 496.0 | 1868 | 41 | 6 |
| 80 | Demian Maia | Welterweight | 487.5 | 1853 | 45 | 6 |
| 81 | Umar Nurmagomedov | Bantamweight | 477.8 | 2027 |  | 4 |
| 82 | Arman Tsarukyan | Lightweight | 475.8 | 2012 |  | 4 |
| 83 | Usman Nurmagomedov | Lightweight | 470.2 |  |  |  |
| 84 | Jake Shields | Welterweight | 465.2 | 1820 | 51 | 6 |
| 85 | Alexandre Pantoja | Flyweight | 464.6 | 1873 | 47 | 5 |
| 86 | Joseph Benavidez | Flyweight | 464.3 | 1848 |  | 2 |
| 87 | Michael Chandler | Lightweight | 453.3 | 1811 |  | 1 |
| 88 | Mark Coleman | Heavyweight | 442.5 | 1722 |  | 2 |
| 89 | Urijah Faber | Bantamweight | 438.6 | 1800 |  | 3 |
| 90 | Robbie Lawler | Welterweight | 437.8 | 1705 |  | 3 |
| 91 | Sean Sherk | Lightweight | 433.4 | 1891 | 44 | 5 |
| 92 | Brandon Moreno | Flyweight | 430.2 | 1775 |  | 3 |
| 93 | Magomed Ankalaev | Light Heavyweight | 427.3 | 1969 |  | 2 |
| 94 | Renan Barao | Bantamweight | 424.8 | 1648 |  | 3 |
| 95 | Andrei Arlovski | Heavyweight | 423.2 | 1781 |  | 4 |
| 96 | Carlos Condit | Welterweight | 421.9 | 1720 |  | 4 |
| 97 | Rich Franklin | Middleweight | 420.5 | 1801 |  | 2 |
| 98 | Matt Hamill | Light Heavyweight | 419.0 | 1651 |  | 2 |
| 99 | Donald Cerrone | Lightweight | 409.3 | 1849 | 50 | 5 |
| 100 | Raphael Assuncao | Bantamweight | 408.0 | 1724 | 65 | 5 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

The table prints both inputs instead of the internal ordering index.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Division | Prime | Elite wins |
| ---: | --- | --- | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 2211 | 12 |
| 2 | Islam Makhachev | Lightweight | 2198 | 9 |
| 3 | Georges St-Pierre | Welterweight | 2074 | 10 |
| 4 | Alexander Volkanovski | Featherweight | 2051 | 9 |
| 5 | Daniel Cormier | Light Heavyweight | 2080 | 8 |
| 6 | Kamaru Usman | Welterweight | 1968 | 10 |
| 7 | Francis Ngannou | Heavyweight | 2037 | 7 |
| 8 | Max Holloway | Featherweight | 1963 | 9 |
| 9 | Ciryl Gane | Heavyweight | 2059 | 6 |
| 10 | Merab Dvalishvili | Bantamweight | 1974 | 8 |
| 11 | Sean Strickland | Middleweight | 1921 | 10 |
| 12 | Ilia Topuria | Featherweight | 2120 | 5 |
| 13 | Dricus Du Plessis | Middleweight | 2044 | 6 |
| 14 | Israel Adesanya | Middleweight | 1935 | 9 |
| 15 | Jose Aldo | Featherweight | 1930 | 9 |
| 16 | Khamzat Chimaev | Middleweight | 2089 | 5 |
| 17 | Anderson Silva | Middleweight | 1922 | 9 |
| 18 | Charles Oliveira | Lightweight | 1980 | 7 |
| 19 | Vadim Nemkov | Light Heavyweight | 2066 | 5 |
| 20 | Justin Gaethje | Lightweight | 1995 | 6 |
| 21 | Stipe Miocic | Heavyweight | 1994 | 6 |
| 22 | Demetrious Johnson | Flyweight | 1982 | 6 |
| 23 | Lyoto Machida | Light Heavyweight | 1966 | 6 |
| 24 | Fedor Emelianenko | Heavyweight | 2014 | 5 |
| 25 | Alex Pereira | Light Heavyweight | 1964 | 6 |
| 26 | Petr Yan | Bantamweight | 1952 | 6 |
| 27 | Aljamain Sterling | Bantamweight | 1945 | 6 |
| 28 | Anthony Johnson | Light Heavyweight | 1941 | 6 |
| 29 | Nassourdine Imavov | Middleweight | 1940 | 6 |
| 30 | Frankie Edgar | Lightweight | 1906 | 7 |
| 31 | Alexander Volkov | Heavyweight | 1905 | 7 |
| 32 | Dustin Poirier | Lightweight | 1927 | 6 |
| 33 | Robert Whittaker | Middleweight | 1893 | 7 |
| 34 | Dominick Cruz | Bantamweight | 1941 | 5 |
| 35 | Chris Weidman | Middleweight | 1871 | 7 |
| 36 | Ryan Bader | Light Heavyweight | 1926 | 5 |
| 37 | Curtis Blaydes | Heavyweight | 1909 | 5 |
| 38 | Brendan Allen | Middleweight | 1908 | 5 |
| 39 | Benson Henderson | Lightweight | 1869 | 6 |
| 40 | Belal Muhammad | Welterweight | 1898 | 5 |
| 41 | Glover Teixeira | Light Heavyweight | 1868 | 6 |
| 42 | Yoel Romero | Middleweight | 1867 | 6 |
| 43 | Luke Rockhold | Middleweight | 1863 | 6 |
| 44 | Sean Sherk | Lightweight | 1891 | 5 |
| 45 | Demian Maia | Welterweight | 1853 | 6 |
| 46 | Beneil Dariush | Lightweight | 1850 | 6 |
| 47 | Alexandre Pantoja | Flyweight | 1873 | 5 |
| 48 | Dan Henderson | Middleweight | 1868 | 5 |
| 49 | Mauricio Rua | Light Heavyweight | 1833 | 6 |
| 50 | Donald Cerrone | Lightweight | 1849 | 5 |

<!-- BOARD:ELITEPRIME50:END -->

### Current — men, top 30

<!-- BOARD:CURRENT30:BEGIN -->

| # | Fighter | Division | Rating | UFC bouts | Last bout |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | Islam Makhachev | Welterweight | 2156 | 18 | 2026-08-15 |
| 2 | Movsar Evloev | Featherweight | 2041 | 10 | 2026-03-21 |
| 3 | Ilia Topuria | Lightweight | 2034 | 10 | 2026-06-14 |
| 4 | Ciryl Gane | Heavyweight | 2025 | 13 | 2026-06-14 |
| 5 | Francis Ngannou | Heavyweight | 2019 | 14 | 2026-05-16 |
| 6 | Khamzat Chimaev | Middleweight | 2001 | 10 | 2026-05-09 |
| 7 | Ian Machado Garry | Welterweight | 1991 | 11 | 2026-08-15 |
| 8 | Arman Tsarukyan | Lightweight | 1990 | 12 | 2025-11-22 |
| 9 | Dricus Du Plessis | Middleweight | 1986 | 11 | 2026-07-18 |
| 10 | Alexander Volkanovski | Featherweight | 1981 | 18 | 2026-01-31 |
| 11 | Umar Nurmagomedov | Bantamweight | 1978 | 9 | 2026-01-24 |
| 12 | Justin Gaethje | Lightweight | 1962 | 16 | 2026-06-14 |
| 13 | Merab Dvalishvili | Bantamweight | 1958 | 17 | 2025-12-06 |
| 14 | Carlos Ulberg | Light Heavyweight | 1958 | 11 | 2026-04-11 |
| 15 | Charles Oliveira | Lightweight | 1956 | 36 | 2026-03-07 |
| 16 | Sean Strickland | Middleweight | 1938 | 25 | 2026-05-09 |
| 17 | Joshua Van | Flyweight | 1931 | 11 | 2026-05-09 |
| 18 | Nassourdine Imavov | Middleweight | 1931 | 11 | 2025-09-06 |
| 19 | Gabriel Bonfim | Welterweight | 1929 | 8 | 2026-06-06 |
| 20 | Max Holloway | Featherweight | 1929 | 33 | 2026-07-11 |
| 21 | Magomed Ankalaev | Light Heavyweight | 1928 | 16 | 2026-07-25 |
| 22 | Sean O'Malley | Bantamweight | 1925 | 15 | 2026-06-14 |
| 23 | Petr Yan | Bantamweight | 1923 | 16 | 2025-12-06 |
| 24 | Corey Anderson | Light Heavyweight | 1919 | 15 | 2025-10-03 |
| 25 | Lerone Murphy | Featherweight | 1915 | 11 | 2026-03-21 |
| 26 | Mario Bautista | Bantamweight | 1915 | 15 | 2026-07-11 |
| 27 | Alex Pereira | Light Heavyweight | 1911 | 13 | 2026-06-14 |
| 28 | Aljamain Sterling | Bantamweight | 1908 | 23 | 2026-04-25 |
| 29 | Sean Brady | Welterweight | 1906 | 11 | 2026-05-09 |
| 30 | Sergei Pavlovich | Heavyweight | 1905 | 12 | 2026-05-30 |

<!-- BOARD:CURRENT30:END -->

## Where the numbers stop

All-time is a look back, so it uses everything we know about an opponent now,
not what was known on the night. Elite-win counts still reward the fighters who
got more chances at them, and the age curve understates decline in fighters who
never came back to show it.

Promotion labels are missing from 57% of rated fights, held-out checks put about
11% of the filled weight classes on the wrong fight, and four eligible careers
cannot be pinned to one fighter. Where something is missing we shrink it or leave
it out rather than guess and act certain. The [decision
register](docs/DECISIONS.md) has the evidence, including the changes we tested
and turned down.

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
