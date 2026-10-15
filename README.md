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

## What the score measures

```text
All-time = 1,000 × (30% title + 17.5% skill + 52.5% résumé)
```

Each part is divided by the average of its own top 100 before weighting, so 1.0
on a part means "as much as a typical top-100 career".

| Part | Weight | What it measures | Exact rule |
| --- | ---: | --- | --- |
| Title | 30% | Title fights won, valued by who was beaten | Each title win is worth `q⁴`, where `q` is the chance the opponent beats a contender-level fighter, using the opponent's rating going in against that division's contender level that year. A major-promotion title win is worth at least `0.05`. |
| Résumé | 52.5% | Wins over contenders, valued by how strong they were | Counts a win over an opponent rated at least 1,750 going in, with eight or more UFC bouts. Each is worth `q⁴` against 1,750: `0.06` just over the line, `0.17` at 100 points above, `0.52` at 300 above. At most `1.0` per calendar year. |
| Skill | 17.5% | How far the fighter's own rating stood above contender level | For every year with a fight: the fighter's average rating that year minus the division's contender level that year (about its fifth-best fighter). Years below the line add almost nothing; years above add the excess. Summed over the career. |

The rating behind all three is one model of every recorded fight, so beating a
fighter counts more the better that fighter proved to be. Skill and résumé are
then multiplied by the promotion exposure above, between 0.20 and 1.00. An
opponent returning from a long absence is marked down 90 points per excess
layoff, up to four. Because `q⁴` rises steeply, one win over an elite opponent
is worth about eight wins over borderline contenders.

**The score is a points total, not a ratio.** Jon Jones's 3,714 against Georges
St-Pierre's 2,104 does not mean Jones was 77% better. It means his parts add up
to more top-100 careers' worth: title 1,281 against 784, résumé 1,588 against
793, skill 845 against 527. Most of the résumé gap is two elite wins: Daniel
Cormier at 353 points above the line and Ciryl Gane at 302, where St-Pierre's
best was Jon Fitch at 140. For who was better at their best, read Prime: 2,205
against 2,073, a 132-point edge, which the rating turns into about a 68% chance
of winning.

Prime takes the ten-year stretch with the most wins over contenders, using the
same contender rule as the résumé, and needs five. It ranks by those wins times
the stretch's average rating above the lowest qualifying average. Current uses
the All-time formula over the last 18 months: title wins and contender wins in
that window, plus the latest rating above 1,750, capped at the best opponent the
fighter has ever beaten so an unbeaten run against weak opposition cannot keep
climbing. It needs 13 rated appearances, eight UFC bouts and a UFC bout within
18 months. Integrity deductions never alter a published board.

## What is published

The men's headline boards are published below so the rankings are visible on
the repository front page. The full [Published UFC Rankings](RANKINGS.md) adds
the three women's boards.

<!-- PUBLICATION:RELEASE:BEGIN -->

| Release fact | Value |
| --- | ---: |
| Dataset | 2026-10-14 |
| Data through | 2026-10-10 |
| Included records | UFC, early UFC and major-promotion careers |
| All-time basis | All-time career score |
| Rated fights | 81,616 |
| Rated fighters | 34,147 |
| Available fight records | 83,016 |
| Whole-career coverage | 1,826 of 1,837 eligible fighters (99.4%) |
| Prime contender threshold | 1,750 — reached by 19.4% of established fighters |
| Prime qualifiers | 78 men; 2 women |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

**Prime** and **Prime rank** come from the Prime board below, and **Elite
wins** is the evidence behind that rank. A blank rank means the fighter did not
qualify, not that they placed last.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Division | Score | Prime | Prime rank | Elite wins |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 3714.2 | 2208 | 1 | 13 |
| 2 | Islam Makhachev | Lightweight | 2892.9 | 2196 | 3 | 8 |
| 3 | Georges St-Pierre | Welterweight | 2103.5 | 2073 | 2 | 11 |
| 4 | Demetrious Johnson | Flyweight | 2061.7 | 1983 | 19 | 7 |
| 5 | Daniel Cormier | Light Heavyweight | 2022.5 | 2080 | 5 | 8 |
| 6 | Jose Aldo | Featherweight | 1962.5 | 1930 | 17 | 9 |
| 7 | Alexander Volkanovski | Featherweight | 1893.3 | 2050 | 4 | 9 |
| 8 | Stipe Miocic | Heavyweight | 1763.8 | 1994 | 26 | 6 |
| 9 | Anderson Silva | Middleweight | 1634.9 | 1922 | 7 | 12 |
| 10 | Francis Ngannou | Heavyweight | 1588.4 | 2038 | 10 | 7 |
| 11 | Dominick Cruz | Bantamweight | 1514.9 | 1942 | 42 | 5 |
| 12 | Israel Adesanya | Middleweight | 1464.2 | 1933 | 8 | 11 |
| 13 | Ilia Topuria | Featherweight | 1457.3 | 2120 | 15 | 5 |
| 14 | Max Holloway | Featherweight | 1451.2 | 1962 | 11 | 9 |
| 15 | Khabib Nurmagomedov | Lightweight | 1405.5 | 2172 | 9 | 5 |
| 16 | Merab Dvalishvili | Bantamweight | 1285.5 | 1970 | 13 | 8 |
| 17 | Lyoto Machida | Light Heavyweight | 1216.5 | 1966 | 23 | 7 |
| 18 | Sean Strickland | Middleweight | 1211.2 | 1918 | 14 | 10 |
| 19 | Justin Gaethje | Lightweight | 1179.6 | 1993 | 27 | 6 |
| 20 | Alex Pereira | Light Heavyweight | 1160.4 | 1963 | 24 | 7 |
| 21 | Matt Hughes | Welterweight | 1145.5 | 1831 |  | 3 |
| 22 | Fedor Emelianenko | Heavyweight | 1109.2 | 2014 | 31 | 5 |
| 23 | Aljamain Sterling | Bantamweight | 1088.3 | 1945 | 28 | 7 |
| 24 | Kamaru Usman | Welterweight | 1076.3 | 1967 | 6 | 10 |
| 25 | Benson Henderson | Lightweight | 1066.9 | 1868 | 40 | 8 |
| 26 | Charles Oliveira | Lightweight | 1035.3 | 1979 | 21 | 7 |
| 27 | Dricus Du Plessis | Middleweight | 1027.2 | 2045 | 16 | 6 |
| 28 | Khamzat Chimaev | Middleweight | 945.0 | 2087 | 20 | 5 |
| 29 | Ciryl Gane | Heavyweight | 929.3 | 2057 | 12 | 6 |
| 30 | Dustin Poirier | Lightweight | 925.8 | 1925 | 38 | 6 |
| 31 | Frankie Edgar | Lightweight | 916.4 | 1906 | 25 | 9 |
| 32 | Petr Yan | Bantamweight | 915.9 | 1952 | 34 | 6 |
| 33 | Cain Velasquez | Heavyweight | 889.9 | 1964 | 39 | 5 |
| 34 | Junior Dos Santos | Heavyweight | 867.0 | 1914 |  | 4 |
| 35 | Chris Weidman | Middleweight | 823.2 | 1870 | 44 | 7 |
| 36 | Dan Henderson | Middleweight | 823.1 | 1868 | 52 | 5 |
| 37 | Anthony Pettis | Lightweight | 819.7 | 1756 | 76 | 6 |
| 38 | Patricio Freire | Featherweight | 814.0 | 1927 |  | 3 |
| 39 | Henry Cejudo | Flyweight | 811.0 | 1878 |  | 4 |
| 40 | Mauricio Rua | Light Heavyweight | 801.2 | 1832 | 56 | 6 |
| 41 | Ryan Bader | Light Heavyweight | 774.0 | 1926 | 45 | 5 |
| 42 | Conor McGregor | Featherweight | 767.0 | 1837 |  | 4 |
| 43 | Vadim Nemkov | Light Heavyweight | 760.1 | 2066 | 22 | 5 |
| 44 | Randy Couture | Heavyweight | 736.3 | 1764 | 72 | 7 |
| 45 | Movsar Evloev | Featherweight | 724.3 | 2099 | 18 | 5 |
| 46 | BJ Penn | Lightweight | 710.1 | 1793 | 67 | 5 |
| 47 | Robert Whittaker | Middleweight | 699.6 | 1892 | 29 | 9 |
| 48 | Sean O'Malley | Bantamweight | 693.1 | 1960 |  | 4 |
| 49 | Tito Ortiz | Light Heavyweight | 685.4 | 1786 |  | 4 |
| 50 | Gegard Mousasi | Middleweight | 671.3 | 1922 |  | 4 |
| 51 | Joshua Van | Flyweight | 668.4 | 1976 |  | 4 |
| 52 | Anthony Johnson | Light Heavyweight | 665.2 | 1941 | 35 | 6 |
| 53 | Antonio Rodrigo Nogueira | Heavyweight | 662.0 | 1889 |  | 4 |
| 54 | Jan Blachowicz | Light Heavyweight | 629.8 | 1800 | 63 | 6 |
| 55 | Tom Aspinall | Heavyweight | 626.0 | 1935 |  | 4 |
| 56 | Eddie Alvarez | Lightweight | 625.8 | 1762 |  | 4 |
| 57 | Leon Edwards | Welterweight | 621.7 | 1885 |  | 4 |
| 58 | Luke Rockhold | Middleweight | 618.3 | 1863 | 48 | 6 |
| 59 | Curtis Blaydes | Heavyweight | 614.9 | 1921 | 32 | 7 |
| 60 | Vitor Belfort | Middleweight | 614.7 | 1781 | 73 | 5 |
| 61 | Chuck Liddell | Light Heavyweight | 613.8 | 1815 | 61 | 6 |
| 62 | Rafael Dos Anjos | Lightweight | 610.0 | 1761 | 74 | 7 |
| 63 | Wanderlei Silva | Light Heavyweight | 607.1 | 1812 |  | 4 |
| 64 | Alexander Volkov | Heavyweight | 604.9 | 1903 | 30 | 8 |
| 65 | Phil Davis | Light Heavyweight | 582.5 | 1956 |  | 4 |
| 66 | Tyron Woodley | Welterweight | 571.7 | 1801 | 65 | 5 |
| 67 | Deiveson Figueiredo | Flyweight | 564.0 | 1813 | 64 | 5 |
| 68 | Quinton Jackson | Light Heavyweight | 549.4 | 1832 | 62 | 5 |
| 69 | Derrick Lewis | Heavyweight | 548.3 | 1768 |  | 4 |
| 70 | Rashad Evans | Light Heavyweight | 545.1 | 1814 |  | 4 |
| 71 | Shavkat Rakhmonov | Welterweight | 542.5 | 2139 |  | 2 |
| 72 | TJ Dillashaw | Bantamweight | 532.5 | 1860 | 54 | 5 |
| 73 | Beneil Dariush | Lightweight | 525.0 | 1848 | 51 | 6 |
| 74 | Fabricio Werdum | Heavyweight | 522.2 | 1892 |  | 4 |
| 75 | Belal Muhammad | Welterweight | 518.0 | 1897 | 43 | 6 |
| 76 | Demian Maia | Welterweight | 516.0 | 1853 | 46 | 7 |
| 77 | Nassourdine Imavov | Middleweight | 514.5 | 1940 | 36 | 6 |
| 78 | Matt Serra | Welterweight | 511.5 | 1688 |  | 1 |
| 79 | Arman Tsarukyan | Lightweight | 508.1 | 2025 |  | 4 |
| 80 | Mirko Filipovic | Heavyweight | 504.1 | 1831 |  | 4 |
| 81 | Glover Teixeira | Light Heavyweight | 493.7 | 1867 | 41 | 8 |
| 82 | Usman Nurmagomedov | Lightweight | 492.0 |  |  |  |
| 83 | Jake Shields | Welterweight | 481.0 | 1820 | 53 | 7 |
| 84 | Joseph Benavidez | Flyweight | 470.5 | 1847 |  | 2 |
| 85 | Alexandre Pantoja | Flyweight | 469.4 | 1856 | 55 | 5 |
| 86 | Mateusz Gamrot | Lightweight | 456.9 | 1877 | 50 | 5 |
| 87 | Urijah Faber | Bantamweight | 447.7 | 1800 |  | 3 |
| 88 | Mark Coleman | Heavyweight | 443.2 | 1723 |  | 2 |
| 89 | Sean Sherk | Lightweight | 436.0 | 1891 | 49 | 5 |
| 90 | Robbie Lawler | Welterweight | 433.9 | 1704 |  | 4 |
| 91 | Magomed Ankalaev | Light Heavyweight | 432.7 | 1971 |  | 3 |
| 92 | Renan Barao | Bantamweight | 424.8 | 1648 |  | 3 |
| 93 | Andrei Arlovski | Heavyweight | 424.5 | 1780 |  | 4 |
| 94 | Matt Hamill | Light Heavyweight | 423.1 | 1652 |  | 2 |
| 95 | Carlos Condit | Welterweight | 417.5 | 1712 |  | 3 |
| 96 | Brandon Moreno | Flyweight | 414.9 | 1783 |  | 3 |
| 97 | Raphael Assuncao | Bantamweight | 409.1 | 1722 | 77 | 5 |
| 98 | Donald Cerrone | Lightweight | 404.4 | 1848 | 57 | 5 |
| 99 | Yoel Romero | Middleweight | 400.2 | 1866 | 47 | 6 |
| 100 | Carlos Ulberg | Light Heavyweight | 399.6 | 1992 |  | 4 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

The table prints both inputs instead of the internal ordering index.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Division | Prime | Elite wins |
| ---: | --- | --- | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 2208 | 13 |
| 2 | Georges St-Pierre | Welterweight | 2073 | 11 |
| 3 | Islam Makhachev | Lightweight | 2196 | 8 |
| 4 | Alexander Volkanovski | Featherweight | 2050 | 9 |
| 5 | Daniel Cormier | Light Heavyweight | 2080 | 8 |
| 6 | Kamaru Usman | Welterweight | 1967 | 10 |
| 7 | Anderson Silva | Middleweight | 1922 | 12 |
| 8 | Israel Adesanya | Middleweight | 1933 | 11 |
| 9 | Khabib Nurmagomedov | Lightweight | 2172 | 5 |
| 10 | Francis Ngannou | Heavyweight | 2038 | 7 |
| 11 | Max Holloway | Featherweight | 1962 | 9 |
| 12 | Ciryl Gane | Heavyweight | 2057 | 6 |
| 13 | Merab Dvalishvili | Bantamweight | 1970 | 8 |
| 14 | Sean Strickland | Middleweight | 1918 | 10 |
| 15 | Ilia Topuria | Featherweight | 2120 | 5 |
| 16 | Dricus Du Plessis | Middleweight | 2045 | 6 |
| 17 | Jose Aldo | Featherweight | 1930 | 9 |
| 18 | Movsar Evloev | Featherweight | 2099 | 5 |
| 19 | Demetrious Johnson | Flyweight | 1983 | 7 |
| 20 | Khamzat Chimaev | Middleweight | 2087 | 5 |
| 21 | Charles Oliveira | Lightweight | 1979 | 7 |
| 22 | Vadim Nemkov | Light Heavyweight | 2066 | 5 |
| 23 | Lyoto Machida | Light Heavyweight | 1966 | 7 |
| 24 | Alex Pereira | Light Heavyweight | 1963 | 7 |
| 25 | Frankie Edgar | Lightweight | 1906 | 9 |
| 26 | Stipe Miocic | Heavyweight | 1994 | 6 |
| 27 | Justin Gaethje | Lightweight | 1993 | 6 |
| 28 | Aljamain Sterling | Bantamweight | 1945 | 7 |
| 29 | Robert Whittaker | Middleweight | 1892 | 9 |
| 30 | Alexander Volkov | Heavyweight | 1903 | 8 |
| 31 | Fedor Emelianenko | Heavyweight | 2014 | 5 |
| 32 | Curtis Blaydes | Heavyweight | 1921 | 7 |
| 33 | Brendan Allen | Middleweight | 1919 | 7 |
| 34 | Petr Yan | Bantamweight | 1952 | 6 |
| 35 | Anthony Johnson | Light Heavyweight | 1941 | 6 |
| 36 | Nassourdine Imavov | Middleweight | 1940 | 6 |
| 37 | Sean Brady | Welterweight | 1967 | 5 |
| 38 | Dustin Poirier | Lightweight | 1925 | 6 |
| 39 | Cain Velasquez | Heavyweight | 1964 | 5 |
| 40 | Benson Henderson | Lightweight | 1868 | 8 |
| 41 | Glover Teixeira | Light Heavyweight | 1867 | 8 |
| 42 | Dominick Cruz | Bantamweight | 1942 | 5 |
| 43 | Belal Muhammad | Welterweight | 1897 | 6 |
| 44 | Chris Weidman | Middleweight | 1870 | 7 |
| 45 | Ryan Bader | Light Heavyweight | 1926 | 5 |
| 46 | Demian Maia | Welterweight | 1853 | 7 |
| 47 | Yoel Romero | Middleweight | 1866 | 6 |
| 48 | Luke Rockhold | Middleweight | 1863 | 6 |
| 49 | Sean Sherk | Lightweight | 1891 | 5 |
| 50 | Mateusz Gamrot | Lightweight | 1877 | 5 |

<!-- BOARD:ELITEPRIME50:END -->

### Current — men, top 30

<!-- BOARD:CURRENT30:BEGIN -->

| # | Fighter | Division | Score | Title wins | Contender wins | UFC bouts | Last UFC bout |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Justin Gaethje | Lightweight | 4544 | 2 | 2 | 16 | 2026-06-14 |
| 2 | Islam Makhachev | Welterweight | 3914 | 2 | 2 | 19 | 2026-08-15 |
| 3 | Joshua Van | Flyweight | 3555 | 3 | 4 | 12 | 2026-09-19 |
| 4 | Sean Strickland | Middleweight | 3017 | 1 | 2 | 25 | 2026-05-09 |
| 5 | Merab Dvalishvili | Bantamweight | 2455 | 2 | 2 | 17 | 2025-12-06 |
| 6 | Khamzat Chimaev | Middleweight | 2368 | 1 | 1 | 10 | 2026-05-09 |
| 7 | Petr Yan | Bantamweight | 2187 | 1 | 1 | 16 | 2025-12-06 |
| 8 | Ilia Topuria | Lightweight | 2058 | 1 | 1 | 10 | 2026-06-14 |
| 9 | Alexander Volkanovski | Featherweight | 2055 | 2 | 2 | 18 | 2026-01-31 |
| 10 | Alex Pereira | Light Heavyweight | 1746 | 1 | 1 | 13 | 2026-06-14 |
| 11 | Ciryl Gane | Heavyweight | 1622 | 1 | 1 | 13 | 2026-06-14 |
| 12 | Charles Oliveira | Lightweight | 1487 | 0 | 2 | 36 | 2026-03-07 |
| 13 | Carlos Ulberg | Light Heavyweight | 1413 | 1 | 2 | 11 | 2026-04-11 |
| 14 | Ian Machado Garry | Welterweight | 1229 | 0 | 2 | 12 | 2026-08-15 |
| 15 | Jack Della Maddalena | Welterweight | 1144 | 1 | 1 | 10 | 2026-05-02 |
| 16 | Carlos Prates | Welterweight | 968 | 0 | 2 | 8 | 2026-05-02 |
| 17 | Movsar Evloev | Featherweight | 938 | 0 | 1 | 10 | 2026-03-21 |
| 18 | Nassourdine Imavov | Middleweight | 935 | 0 | 1 | 11 | 2025-09-06 |
| 19 | Diego Lopes | Featherweight | 924 | 0 | 2 | 10 | 2026-06-14 |
| 20 | Sean O'Malley | Bantamweight | 905 | 0 | 2 | 15 | 2026-06-14 |
| 21 | Song Yadong | Bantamweight | 901 | 0 | 1 | 18 | 2026-08-29 |
| 22 | Umar Nurmagomedov | Bantamweight | 851 | 0 | 1 | 10 | 2026-08-29 |
| 23 | Manel Kape | Flyweight | 846 | 0 | 2 | 11 | 2026-06-20 |
| 24 | Jean Silva | Featherweight | 794 | 0 | 2 | 8 | 2026-09-12 |
| 25 | Alexander Volkov | Heavyweight | 771 | 0 | 2 | 19 | 2026-05-09 |
| 26 | Gregory Rodrigues | Middleweight | 733 | 0 | 2 | 14 | 2026-08-22 |
| 27 | Max Holloway | Featherweight | 685 | 0 | 1 | 33 | 2026-07-11 |
| 28 | Brendan Allen | Middleweight | 675 | 0 | 2 | 20 | 2026-10-10 |
| 29 | Dricus Du Plessis | Middleweight | 645 | 0 | 1 | 11 | 2026-07-18 |
| 30 | Aljamain Sterling | Bantamweight | 595 | 0 | 2 | 23 | 2026-04-25 |

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
| `data/snapshots/<date>/` | The release: inputs, fitted ratings and boards, all versioned |
| [`docs/`](docs/) | Method and decisions |
| `tests/` | Verification |

Use the system Python:

```text
python -m pip install -r requirements.txt
python -m pytest -q
python check_release.py
python build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
```
