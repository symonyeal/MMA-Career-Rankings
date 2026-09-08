# Symon UFC Rank Engine

This project fits recorded MMA careers together, then answers three different
questions: career, peak and current strength.

## The argument

Weight classes are separate pools. Career division is where a fighter competed
most; current division changes only after a UFC title win. Each year is measured
against its division's top ten percent, roughly the fifth-best fighter; classes
with fewer than 30 fighter-years use the sport-wide line. Men and women remain
separate.

The fight rating ignores promotion. Exposure is applied later: UFC is `1.00`,
PRIDE `0.95`, Affliction `0.90`, WEC and Strikeforce `0.88`, Bellator `0.65`, and
PFL, RIZIN, ONE and DREAM `0.60`. Thin evidence shrinks toward the average.

A knockout or submission scores `1.00`, a unanimous decision `0.95`, a split or
majority decision `0.90`, a disqualification `0.85`, and a draw `0.50` for each
fighter; no-contests are excluded. Careers are fitted together, so later results
can revalue earlier fights. Ratings sit around 1,500, and a neutral virtual bout
checks tiny unbeaten records. Duplicate fights are removed and whole careers
are required.

## Three answers

```text
All-time = 30% championships + 17.5% career skill + 52.5% contender résumé
```

Each component is normalized against its top 100. Career skill sums years above
the division line. The résumé prices wins over opponents rated at least 1,750
before the bout with at least eight UFC fights, one per year. Returning
opponents lose 90 points per excess turnaround, capped at four. Major titles
carry a `0.05` floor.

Prime ranks the ten-year stretch with the most qualifying contender wins, then
its average rating; Five wins are required. Current ranks UFC-tested fighters,
not only the current UFC roster: it ages the latest rating forward, shrinks thin
records toward 1,750, and needs 13 rated appearances, eight UFC bouts and any
recorded MMA fight within 18 months. Integrity deductions never alter a
published board.

## What is published

The men's headline boards are published below so the rankings are visible on
the repository front page. The full [Published UFC Rankings](RANKINGS.md) adds
the three women's boards.

<!-- PUBLICATION:RELEASE:BEGIN -->

| Release fact | Value |
| --- | ---: |
| Dataset | 2026-08-13 |
| Data through | 2026-08-30 |
| Included records | UFC, early UFC and major-promotion careers |
| All-time basis | All-time career score |
| Rated fights | 81,512 |
| Rated fighters | 34,126 |
| Available fight records | 82,912 |
| Whole-career coverage | 1,827 of 1,827 eligible fighters (100.0%) |
| Prime contender threshold | 1,750 — reached by 19.5% of established fighters |
| Prime qualifiers | 65 men; 1 woman |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

**Prime** and **Prime rank** come from the Prime board below, and **Elite
wins** is the evidence behind that rank. A blank rank means the fighter did not
qualify, not that they placed last.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Division | Score | Prime | Prime rank | Elite wins |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 3709.3 | 2210 | 1 | 12 |
| 2 | Islam Makhachev | Lightweight | 2922.7 | 2198 | 2 | 9 |
| 3 | Georges St-Pierre | Welterweight | 2101.5 | 2073 | 3 | 10 |
| 4 | Demetrious Johnson | Flyweight | 2048.1 | 1982 | 22 | 6 |
| 5 | Daniel Cormier | Light Heavyweight | 2017.7 | 2080 | 5 | 8 |
| 6 | Jose Aldo | Featherweight | 1926.3 | 1930 | 15 | 9 |
| 7 | Alexander Volkanovski | Featherweight | 1897.5 | 2051 | 4 | 9 |
| 8 | Stipe Miocic | Heavyweight | 1759.9 | 1994 | 21 | 6 |
| 9 | Anderson Silva | Middleweight | 1633.0 | 1922 | 17 | 9 |
| 10 | Francis Ngannou | Heavyweight | 1571.8 | 2037 | 7 | 7 |
| 11 | Dominick Cruz | Bantamweight | 1512.0 | 1941 | 34 | 5 |
| 12 | Israel Adesanya | Middleweight | 1483.0 | 1935 | 14 | 9 |
| 13 | Max Holloway | Featherweight | 1462.2 | 1963 | 8 | 9 |
| 14 | Ilia Topuria | Featherweight | 1452.8 | 2120 | 12 | 5 |
| 15 | Khabib Nurmagomedov | Lightweight | 1412.1 | 2173 |  | 4 |
| 16 | Merab Dvalishvili | Bantamweight | 1367.3 | 1974 | 10 | 8 |
| 17 | Sean Strickland | Middleweight | 1251.2 | 1921 | 11 | 10 |
| 18 | Lyoto Machida | Light Heavyweight | 1213.8 | 1966 | 23 | 6 |
| 19 | Justin Gaethje | Lightweight | 1191.0 | 1995 | 20 | 6 |
| 20 | Alex Pereira | Light Heavyweight | 1161.1 | 1964 | 25 | 6 |
| 21 | Matt Hughes | Welterweight | 1144.6 | 1831 |  | 3 |
| 22 | Fedor Emelianenko | Heavyweight | 1106.6 | 2014 | 24 | 5 |
| 23 | Aljamain Sterling | Bantamweight | 1086.7 | 1945 | 27 | 6 |
| 24 | Kamaru Usman | Welterweight | 1085.5 | 1968 | 6 | 10 |
| 25 | Benson Henderson | Lightweight | 1068.0 | 1869 | 39 | 6 |
| 26 | Charles Oliveira | Lightweight | 1042.0 | 1980 | 18 | 7 |
| 27 | Dricus Du Plessis | Middleweight | 1033.3 | 2044 | 13 | 6 |
| 28 | Dustin Poirier | Lightweight | 973.9 | 1927 | 32 | 6 |
| 29 | Khamzat Chimaev | Middleweight | 951.0 | 2089 | 16 | 5 |
| 30 | Ciryl Gane | Heavyweight | 947.9 | 2060 | 9 | 6 |
| 31 | Petr Yan | Bantamweight | 918.9 | 1952 | 26 | 6 |
| 32 | Frankie Edgar | Lightweight | 917.2 | 1906 | 30 | 7 |
| 33 | Cain Velasquez | Heavyweight | 887.9 | 1959 |  | 3 |
| 34 | Junior Dos Santos | Heavyweight | 865.4 | 1913 |  | 4 |
| 35 | Chris Weidman | Middleweight | 823.1 | 1870 | 35 | 7 |
| 36 | Anthony Pettis | Lightweight | 822.1 | 1757 | 62 | 6 |
| 37 | Patricio Freire | Featherweight | 821.6 | 1927 |  | 3 |
| 38 | Dan Henderson | Middleweight | 820.3 | 1868 | 48 | 5 |
| 39 | Henry Cejudo | Flyweight | 800.3 | 1873 |  | 4 |
| 40 | Mauricio Rua | Light Heavyweight | 799.1 | 1832 | 49 | 6 |
| 41 | Ryan Bader | Light Heavyweight | 771.1 | 1926 | 36 | 5 |
| 42 | Conor McGregor | Featherweight | 767.9 | 1838 |  | 4 |
| 43 | Vadim Nemkov | Light Heavyweight | 764.7 | 2067 | 19 | 5 |
| 44 | Randy Couture | Heavyweight | 735.2 | 1763 |  | 4 |
| 45 | Movsar Evloev | Featherweight | 725.6 | 2104 |  | 4 |
| 46 | Robert Whittaker | Middleweight | 710.4 | 1893 | 33 | 7 |
| 47 | BJ Penn | Lightweight | 709.6 | 1793 | 58 | 5 |
| 48 | Tito Ortiz | Light Heavyweight | 683.7 | 1786 |  | 4 |
| 49 | Gegard Mousasi | Middleweight | 666.2 | 1919 |  | 4 |
| 50 | Anthony Johnson | Light Heavyweight | 664.0 | 1941 | 28 | 6 |
| 51 | Antonio Rodrigo Nogueira | Heavyweight | 659.7 | 1889 |  | 4 |
| 52 | Sean O'Malley | Bantamweight | 650.6 | 1954 |  | 4 |
| 53 | Alexander Volkov | Heavyweight | 633.8 | 1905 | 31 | 7 |
| 54 | Eddie Alvarez | Lightweight | 631.2 | 1763 |  | 4 |
| 55 | Leon Edwards | Welterweight | 628.6 | 1887 |  | 4 |
| 56 | Jan Blachowicz | Light Heavyweight | 626.3 | 1801 | 56 | 5 |
| 57 | Luke Rockhold | Middleweight | 618.0 | 1863 | 43 | 6 |
| 58 | Rafael Dos Anjos | Lightweight | 614.3 | 1771 | 59 | 7 |
| 59 | Vitor Belfort | Middleweight | 613.1 | 1781 | 61 | 5 |
| 60 | Chuck Liddell | Light Heavyweight | 612.3 | 1815 | 54 | 5 |
| 61 | Tom Aspinall | Heavyweight | 610.3 | 1934 |  | 4 |
| 62 | Wanderlei Silva | Light Heavyweight | 605.3 | 1812 |  | 4 |
| 63 | Phil Davis | Light Heavyweight | 583.5 | 1956 |  | 4 |
| 64 | Tyron Woodley | Welterweight | 573.9 | 1802 | 55 | 5 |
| 65 | Shavkat Rakhmonov | Welterweight | 573.0 | 2140 |  | 2 |
| 66 | Deiveson Figueiredo | Flyweight | 559.4 | 1830 | 53 | 5 |
| 67 | Quinton Jackson | Light Heavyweight | 548.3 | 1832 | 52 | 5 |
| 68 | Rashad Evans | Light Heavyweight | 543.7 | 1814 |  | 4 |
| 69 | Beneil Dariush | Lightweight | 542.5 | 1850 | 46 | 6 |
| 70 | Derrick Lewis | Heavyweight | 539.0 | 1771 |  | 4 |
| 71 | TJ Dillashaw | Bantamweight | 536.9 | 1850 |  | 3 |
| 72 | Curtis Blaydes | Heavyweight | 527.8 | 1910 | 37 | 5 |
| 73 | Joshua Van | Flyweight | 523.7 | 1955 |  | 3 |
| 74 | Fabricio Werdum | Heavyweight | 522.1 | 1892 |  | 4 |
| 75 | Belal Muhammad | Welterweight | 520.9 | 1898 | 40 | 5 |
| 76 | Demian Maia | Welterweight | 516.4 | 1853 | 45 | 6 |
| 77 | Nassourdine Imavov | Middleweight | 516.2 | 1941 | 29 | 6 |
| 78 | Matt Serra | Welterweight | 511.2 | 1688 |  | 1 |
| 79 | Mirko Filipovic | Heavyweight | 502.9 | 1831 |  | 4 |
| 80 | Glover Teixeira | Light Heavyweight | 495.0 | 1867 | 41 | 6 |
| 81 | Jake Shields | Welterweight | 480.5 | 1820 | 51 | 6 |
| 82 | Umar Nurmagomedov | Bantamweight | 479.9 | 2027 |  | 4 |
| 83 | Usman Nurmagomedov | Lightweight | 475.1 |  |  |  |
| 84 | Arman Tsarukyan | Lightweight | 474.0 | 2011 |  | 4 |
| 85 | Joseph Benavidez | Flyweight | 467.3 | 1848 |  | 2 |
| 86 | Alexandre Pantoja | Flyweight | 462.6 | 1872 | 47 | 5 |
| 87 | Michael Chandler | Lightweight | 453.0 | 1812 |  | 1 |
| 88 | Urijah Faber | Bantamweight | 449.7 | 1800 |  | 3 |
| 89 | Mark Coleman | Heavyweight | 442.6 | 1722 |  | 2 |
| 90 | Donald Cerrone | Lightweight | 437.6 | 1849 | 50 | 5 |
| 91 | Sean Sherk | Lightweight | 435.0 | 1891 | 44 | 5 |
| 92 | Robbie Lawler | Welterweight | 434.0 | 1705 |  | 3 |
| 93 | Brandon Moreno | Flyweight | 429.2 | 1775 |  | 3 |
| 94 | Magomed Ankalaev | Light Heavyweight | 427.2 | 1969 |  | 2 |
| 95 | Renan Barao | Bantamweight | 424.2 | 1648 |  | 3 |
| 96 | Andrei Arlovski | Heavyweight | 423.4 | 1780 |  | 4 |
| 97 | Matt Hamill | Light Heavyweight | 422.0 | 1652 |  | 2 |
| 98 | Carlos Condit | Welterweight | 417.6 | 1721 |  | 4 |
| 99 | Mateusz Gamrot | Lightweight | 412.0 | 1879 |  | 3 |
| 100 | Raphael Assuncao | Bantamweight | 407.7 | 1724 | 64 | 5 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

The table prints both inputs instead of the internal ordering index.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Division | Prime | Elite wins |
| ---: | --- | --- | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 2210 | 12 |
| 2 | Islam Makhachev | Lightweight | 2198 | 9 |
| 3 | Georges St-Pierre | Welterweight | 2073 | 10 |
| 4 | Alexander Volkanovski | Featherweight | 2051 | 9 |
| 5 | Daniel Cormier | Light Heavyweight | 2080 | 8 |
| 6 | Kamaru Usman | Welterweight | 1968 | 10 |
| 7 | Francis Ngannou | Heavyweight | 2037 | 7 |
| 8 | Max Holloway | Featherweight | 1963 | 9 |
| 9 | Ciryl Gane | Heavyweight | 2060 | 6 |
| 10 | Merab Dvalishvili | Bantamweight | 1974 | 8 |
| 11 | Sean Strickland | Middleweight | 1921 | 10 |
| 12 | Ilia Topuria | Featherweight | 2120 | 5 |
| 13 | Dricus Du Plessis | Middleweight | 2044 | 6 |
| 14 | Israel Adesanya | Middleweight | 1935 | 9 |
| 15 | Jose Aldo | Featherweight | 1930 | 9 |
| 16 | Khamzat Chimaev | Middleweight | 2089 | 5 |
| 17 | Anderson Silva | Middleweight | 1922 | 9 |
| 18 | Charles Oliveira | Lightweight | 1980 | 7 |
| 19 | Vadim Nemkov | Light Heavyweight | 2067 | 5 |
| 20 | Justin Gaethje | Lightweight | 1995 | 6 |
| 21 | Stipe Miocic | Heavyweight | 1994 | 6 |
| 22 | Demetrious Johnson | Flyweight | 1982 | 6 |
| 23 | Lyoto Machida | Light Heavyweight | 1966 | 6 |
| 24 | Fedor Emelianenko | Heavyweight | 2014 | 5 |
| 25 | Alex Pereira | Light Heavyweight | 1964 | 6 |
| 26 | Petr Yan | Bantamweight | 1952 | 6 |
| 27 | Aljamain Sterling | Bantamweight | 1945 | 6 |
| 28 | Anthony Johnson | Light Heavyweight | 1941 | 6 |
| 29 | Nassourdine Imavov | Middleweight | 1941 | 6 |
| 30 | Frankie Edgar | Lightweight | 1906 | 7 |
| 31 | Alexander Volkov | Heavyweight | 1905 | 7 |
| 32 | Dustin Poirier | Lightweight | 1927 | 6 |
| 33 | Robert Whittaker | Middleweight | 1893 | 7 |
| 34 | Dominick Cruz | Bantamweight | 1941 | 5 |
| 35 | Chris Weidman | Middleweight | 1870 | 7 |
| 36 | Ryan Bader | Light Heavyweight | 1926 | 5 |
| 37 | Curtis Blaydes | Heavyweight | 1910 | 5 |
| 38 | Brendan Allen | Middleweight | 1908 | 5 |
| 39 | Benson Henderson | Lightweight | 1869 | 6 |
| 40 | Belal Muhammad | Welterweight | 1898 | 5 |
| 41 | Glover Teixeira | Light Heavyweight | 1867 | 6 |
| 42 | Yoel Romero | Middleweight | 1866 | 6 |
| 43 | Luke Rockhold | Middleweight | 1863 | 6 |
| 44 | Sean Sherk | Lightweight | 1891 | 5 |
| 45 | Demian Maia | Welterweight | 1853 | 6 |
| 46 | Beneil Dariush | Lightweight | 1850 | 6 |
| 47 | Alexandre Pantoja | Flyweight | 1872 | 5 |
| 48 | Dan Henderson | Middleweight | 1868 | 5 |
| 49 | Mauricio Rua | Light Heavyweight | 1832 | 6 |
| 50 | Donald Cerrone | Lightweight | 1849 | 5 |

<!-- BOARD:ELITEPRIME50:END -->

### Current — men, top 30

<!-- BOARD:CURRENT30:BEGIN -->

| # | Fighter | Division | Rating | UFC bouts | Last bout |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | Islam Makhachev | Welterweight | 2166 | 19 | 2026-08-15 |
| 2 | Movsar Evloev | Featherweight | 2045 | 10 | 2026-03-21 |
| 3 | Ilia Topuria | Lightweight | 2043 | 10 | 2026-06-14 |
| 4 | Ciryl Gane | Heavyweight | 2029 | 13 | 2026-06-14 |
| 5 | Francis Ngannou | Heavyweight | 2022 | 14 | 2026-05-16 |
| 6 | Khamzat Chimaev | Middleweight | 2011 | 10 | 2026-05-09 |
| 7 | Ian Machado Garry | Welterweight | 2001 | 12 | 2026-08-15 |
| 8 | Dricus Du Plessis | Middleweight | 1998 | 11 | 2026-07-18 |
| 9 | Arman Tsarukyan | Lightweight | 1995 | 12 | 2025-11-22 |
| 10 | Alexander Volkanovski | Featherweight | 1983 | 18 | 2026-01-31 |
| 11 | Umar Nurmagomedov | Bantamweight | 1982 | 9 | 2026-01-24 |
| 12 | Justin Gaethje | Lightweight | 1981 | 16 | 2026-06-14 |
| 13 | Carlos Ulberg | Light Heavyweight | 1961 | 11 | 2026-04-11 |
| 14 | Charles Oliveira | Lightweight | 1958 | 36 | 2026-03-07 |
| 15 | Merab Dvalishvili | Bantamweight | 1956 | 17 | 2025-12-06 |
| 16 | Gabriel Bonfim | Welterweight | 1936 | 8 | 2026-06-06 |
| 17 | Petr Yan | Bantamweight | 1935 | 16 | 2025-12-06 |
| 18 | Nassourdine Imavov | Middleweight | 1934 | 11 | 2025-09-06 |
| 19 | Joshua Van | Flyweight | 1930 | 11 | 2026-05-09 |
| 20 | Magomed Ankalaev | Light Heavyweight | 1930 | 16 | 2026-07-25 |
| 21 | Max Holloway | Featherweight | 1930 | 33 | 2026-07-11 |
| 22 | Sean Strickland | Middleweight | 1929 | 25 | 2026-05-09 |
| 23 | Sean O'Malley | Bantamweight | 1928 | 15 | 2026-06-14 |
| 24 | Corey Anderson | Light Heavyweight | 1920 | 15 | 2025-10-03 |
| 25 | Mario Bautista | Bantamweight | 1918 | 15 | 2026-07-11 |
| 26 | Lerone Murphy | Featherweight | 1918 | 11 | 2026-03-21 |
| 27 | Sean Brady | Welterweight | 1916 | 11 | 2026-05-09 |
| 28 | Alex Pereira | Light Heavyweight | 1913 | 13 | 2026-06-14 |
| 29 | Aljamain Sterling | Bantamweight | 1912 | 23 | 2026-04-25 |
| 30 | Sergei Pavlovich | Heavyweight | 1907 | 12 | 2026-05-30 |

<!-- BOARD:CURRENT30:END -->

## Where the numbers stop

All-time is retrospective, elite wins reward opportunity, and the age curve
misses decline in fighters who never returned. Promotion labels are missing from 54% of rated fights;
11% of filled weight classes are estimated wrong. Whole-career coverage is
complete for every eligible fighter, and none has an evidenced source-ID
conflict. See the [decision register](docs/DECISIONS.md).

## Project map

| Path | Use it for |
| --- | --- |
| [`RANKINGS.md`](RANKINGS.md) | Full rankings |
| `ratings/` / `loaders/` | Model / data assembly |
| `data/snapshots/<date>/` | Release artifacts |
| [`docs/`](docs/) | Method and decisions |
| `tests/` | Verification |

Use the system Python:

```text
C:\Python314\python.exe -m pip install -r requirements.txt
C:\Python314\python.exe -m pytest -q
C:\Python314\python.exe build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
```
