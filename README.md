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
| Prime contender threshold | 1,750 — reached by 59.9% of established fighters |
| Prime qualifiers | 334 men; 23 women |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

**Prime** and **Prime rank** come from the Prime board below, and **Elite
wins** is the evidence behind that rank. A blank rank means the fighter did not
qualify, not that they placed last.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Division | Score | Prime | Prime rank | Elite wins |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 3100.1 | 2462 | 1 | 17 |
| 2 | Georges St-Pierre | Welterweight | 2302.5 | 2332 | 3 | 15 |
| 3 | Islam Makhachev | Lightweight | 2141.5 | 2419 | 2 | 14 |
| 4 | Jose Aldo | Featherweight | 2020.7 | 2190 | 22 | 12 |
| 5 | Demetrious Johnson | Flyweight | 1887.2 | 2204 | 28 | 11 |
| 6 | Anderson Silva | Middleweight | 1845.4 | 2204 | 5 | 17 |
| 7 | Daniel Cormier | Light Heavyweight | 1761.8 | 2340 | 4 | 13 |
| 8 | Alexander Volkanovski | Featherweight | 1670.3 | 2278 | 11 | 12 |
| 9 | Stipe Miocic | Heavyweight | 1500.4 | 2238 | 17 | 12 |
| 10 | Max Holloway | Featherweight | 1478.0 | 2207 | 6 | 15 |
| 11 | Khabib Nurmagomedov | Lightweight | 1361.1 | 2400 | 8 | 10 |
| 12 | Dominick Cruz | Bantamweight | 1353.0 | 2182 | 67 | 8 |
| 13 | Israel Adesanya | Middleweight | 1241.9 | 2215 | 15 | 13 |
| 14 | Francis Ngannou | Heavyweight | 1182.3 | 2272 | 30 | 9 |
| 15 | Charles Oliveira | Lightweight | 1179.3 | 2195 | 9 | 15 |
| 16 | Frankie Edgar | Lightweight | 1140.5 | 2170 | 14 | 15 |
| 17 | Lyoto Machida | Light Heavyweight | 1132.2 | 2143 | 35 | 12 |
| 18 | Fedor Emelianenko | Heavyweight | 1117.2 | 2272 | 21 | 10 |
| 19 | Kamaru Usman | Welterweight | 1106.6 | 2207 | 12 | 14 |
| 20 | Aljamain Sterling | Bantamweight | 1085.1 | 2171 | 27 | 12 |
| 21 | Ilia Topuria | Featherweight | 1079.6 | 2334 | 29 | 8 |
| 22 | Matt Hughes | Welterweight | 1060.3 | 2108 | 92 | 8 |
| 23 | Dustin Poirier | Lightweight | 1050.9 | 2177 | 16 | 14 |
| 24 | Benson Henderson | Lightweight | 1003.2 | 2135 | 39 | 12 |
| 25 | Gegard Mousasi | Middleweight | 980.4 | 2187 | 18 | 13 |
| 26 | Merab Dvalishvili | Bantamweight | 966.5 | 2144 | 26 | 13 |
| 27 | Dan Henderson | Middleweight | 964.2 | 2073 | 80 | 10 |
| 28 | Junior Dos Santos | Heavyweight | 960.4 | 2168 | 38 | 11 |
| 29 | Justin Gaethje | Lightweight | 956.9 | 2223 | 23 | 11 |
| 30 | Chris Weidman | Middleweight | 942.3 | 2127 | 45 | 11 |
| 31 | Petr Yan | Bantamweight | 930.2 | 2184 | 55 | 9 |
| 32 | Ryan Bader | Light Heavyweight | 888.7 | 2186 | 24 | 12 |
| 33 | BJ Penn | Lightweight | 886.8 | 2084 | 66 | 11 |
| 34 | Randy Couture | Heavyweight | 863.9 | 2017 | 118 | 10 |
| 35 | Cain Velasquez | Heavyweight | 862.6 | 2213 | 60 | 8 |
| 36 | Dricus Du Plessis | Middleweight | 851.2 | 2265 | 34 | 9 |
| 37 | Rafael Dos Anjos | Lightweight | 850.0 | 2068 | 52 | 13 |
| 38 | Sean Strickland | Middleweight | 849.2 | 2175 | 19 | 13 |
| 39 | Fabricio Werdum | Heavyweight | 842.7 | 2136 | 44 | 11 |
| 40 | Donald Cerrone | Lightweight | 842.3 | 2085 | 7 | 21 |
| 41 | Robert Whittaker | Middleweight | 820.8 | 2151 | 31 | 12 |
| 42 | Chuck Liddell | Light Heavyweight | 820.2 | 2090 | 74 | 10 |
| 43 | Demian Maia | Welterweight | 816.2 | 2142 | 10 | 17 |
| 44 | Henry Cejudo | Flyweight | 815.0 | 2096 | 101 | 8 |
| 45 | Anthony Pettis | Lightweight | 806.3 | 2033 | 103 | 10 |
| 46 | Patricio Freire | Featherweight | 797.7 | 2173 |  | 3 |
| 47 | Alex Pereira | Light Heavyweight | 796.9 | 2188 | 53 | 9 |
| 48 | Mauricio Rua | Light Heavyweight | 788.1 | 2098 | 69 | 10 |
| 49 | Ciryl Gane | Heavyweight | 755.9 | 2281 | 20 | 10 |
| 50 | Tyron Woodley | Welterweight | 747.8 | 2088 | 88 | 9 |
| 51 | Leon Edwards | Welterweight | 739.2 | 2125 | 48 | 11 |
| 52 | Khamzat Chimaev | Middleweight | 737.8 | 2311 | 50 | 7 |
| 53 | Rashad Evans | Light Heavyweight | 717.6 | 2124 | 49 | 11 |
| 54 | Conor McGregor | Featherweight | 711.2 | 2087 | 106 | 8 |
| 55 | Tito Ortiz | Light Heavyweight | 695.5 | 2059 | 172 | 6 |
| 56 | Joseph Benavidez | Flyweight | 694.9 | 2121 | 64 | 10 |
| 57 | Antonio Rodrigo Nogueira | Heavyweight | 691.2 | 2212 | 43 | 9 |
| 58 | Deiveson Figueiredo | Flyweight | 675.3 | 2060 | 75 | 11 |
| 59 | Rich Franklin | Middleweight | 673.0 | 2123 | 51 | 11 |
| 60 | Vitor Belfort | Middleweight | 669.7 | 2080 | 110 | 8 |
| 61 | Glover Teixeira | Light Heavyweight | 667.8 | 2149 | 13 | 16 |
| 62 | Alexander Volkov | Heavyweight | 659.3 | 2149 | 25 | 13 |
| 63 | Beneil Dariush | Lightweight | 654.7 | 2091 | 37 | 14 |
| 64 | Jan Blachowicz | Light Heavyweight | 648.0 | 2054 | 77 | 11 |
| 65 | Robbie Lawler | Welterweight | 643.2 | 2020 | 137 | 9 |
| 66 | Jacare Souza | Middleweight | 629.7 | 2122 | 33 | 13 |
| 67 | TJ Dillashaw | Bantamweight | 617.8 | 2090 | 104 | 8 |
| 68 | Alistair Overeem | Heavyweight | 617.1 | 2088 | 54 | 12 |
| 69 | Quinton Jackson | Light Heavyweight | 615.9 | 2106 | 96 | 8 |
| 70 | Alexandre Pantoja | Flyweight | 615.1 | 2099 | 59 | 11 |
| 71 | Vadim Nemkov | Light Heavyweight | 611.3 | 2280 | 100 | 5 |
| 72 | Wanderlei Silva | Light Heavyweight | 603.2 | 2091 | 182 | 5 |
| 73 | Andrei Arlovski | Heavyweight | 593.0 | 2000 | 188 | 7 |
| 74 | Neil Magny | Welterweight | 590.4 | 2033 | 62 | 14 |
| 75 | Luke Rockhold | Middleweight | 574.1 | 2118 | 91 | 8 |
| 76 | Michael Bisping | Middleweight | 566.8 | 2084 | 56 | 12 |
| 77 | Phil Davis | Light Heavyweight | 565.7 | 2203 | 76 | 7 |
| 78 | Eddie Alvarez | Lightweight | 557.2 | 2128 | 140 | 6 |
| 79 | Urijah Faber | Bantamweight | 553.4 | 2069 | 82 | 10 |
| 80 | Anthony Johnson | Light Heavyweight | 551.5 | 2173 | 36 | 11 |
| 81 | Renan Barao | Bantamweight | 547.9 | 2013 | 159 | 8 |
| 82 | Brandon Moreno | Flyweight | 545.2 | 1988 | 160 | 9 |
| 83 | Curtis Blaydes | Heavyweight | 543.2 | 2140 | 42 | 11 |
| 84 | Josh Barnett | Heavyweight | 543.1 | 2184 | 144 | 5 |
| 85 | Carlos Condit | Welterweight | 542.2 | 1987 | 201 | 7 |
| 86 | Johny Hendricks | Welterweight | 541.1 | 2046 | 70 | 12 |
| 87 | Belal Muhammad | Welterweight | 539.9 | 2127 | 46 | 11 |
| 88 | Sean Sherk | Lightweight | 537.4 | 2134 | 85 | 8 |
| 89 | Sean O'Malley | Bantamweight | 537.2 | 2156 | 121 | 6 |
| 90 | Magomed Ankalaev | Light Heavyweight | 529.7 | 2192 | 40 | 10 |
| 91 | Diego Sanchez | Welterweight | 528.7 | 2043 | 83 | 11 |
| 92 | Michael Chandler | Lightweight | 507.4 | 2058 |  | 4 |
| 93 | Movsar Evloev | Featherweight | 502.0 | 2290 | 41 | 8 |
| 94 | Mirko Filipovic | Heavyweight | 500.3 | 2085 | 135 | 7 |
| 95 | Frank Mir | Heavyweight | 493.8 | 2004 | 184 | 7 |
| 96 | Tom Aspinall | Heavyweight | 491.0 | 2131 | 138 | 6 |
| 97 | Mark Coleman | Heavyweight | 488.8 | 1977 |  | 4 |
| 98 | Jake Shields | Welterweight | 488.2 | 2086 | 107 | 8 |
| 99 | Edson Barboza | Lightweight | 471.4 | 2018 | 116 | 10 |
| 100 | Shavkat Rakhmonov | Welterweight | 469.7 | 2313 | 47 | 7 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

The table prints both inputs instead of the internal ordering index.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Division | Prime | Elite wins |
| ---: | --- | --- | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 2462 | 17 |
| 2 | Islam Makhachev | Lightweight | 2419 | 14 |
| 3 | Georges St-Pierre | Welterweight | 2332 | 15 |
| 4 | Daniel Cormier | Light Heavyweight | 2340 | 13 |
| 5 | Anderson Silva | Middleweight | 2204 | 17 |
| 6 | Max Holloway | Featherweight | 2207 | 15 |
| 7 | Donald Cerrone | Lightweight | 2085 | 21 |
| 8 | Khabib Nurmagomedov | Lightweight | 2400 | 10 |
| 9 | Charles Oliveira | Lightweight | 2195 | 15 |
| 10 | Demian Maia | Welterweight | 2142 | 17 |
| 11 | Alexander Volkanovski | Featherweight | 2278 | 12 |
| 12 | Kamaru Usman | Welterweight | 2207 | 14 |
| 13 | Glover Teixeira | Light Heavyweight | 2149 | 16 |
| 14 | Frankie Edgar | Lightweight | 2170 | 15 |
| 15 | Israel Adesanya | Middleweight | 2215 | 13 |
| 16 | Dustin Poirier | Lightweight | 2177 | 14 |
| 17 | Stipe Miocic | Heavyweight | 2238 | 12 |
| 18 | Gegard Mousasi | Middleweight | 2187 | 13 |
| 19 | Sean Strickland | Middleweight | 2175 | 13 |
| 20 | Ciryl Gane | Heavyweight | 2281 | 10 |
| 21 | Fedor Emelianenko | Heavyweight | 2272 | 10 |
| 22 | Jose Aldo | Featherweight | 2190 | 12 |
| 23 | Justin Gaethje | Lightweight | 2223 | 11 |
| 24 | Ryan Bader | Light Heavyweight | 2186 | 12 |
| 25 | Alexander Volkov | Heavyweight | 2149 | 13 |
| 26 | Merab Dvalishvili | Bantamweight | 2144 | 13 |
| 27 | Aljamain Sterling | Bantamweight | 2171 | 12 |
| 28 | Demetrious Johnson | Flyweight | 2204 | 11 |
| 29 | Ilia Topuria | Featherweight | 2334 | 8 |
| 30 | Francis Ngannou | Heavyweight | 2272 | 9 |
| 31 | Robert Whittaker | Middleweight | 2151 | 12 |
| 32 | Brendan Allen | Middleweight | 2123 | 13 |
| 33 | Jacare Souza | Middleweight | 2122 | 13 |
| 34 | Dricus Du Plessis | Middleweight | 2265 | 9 |
| 35 | Lyoto Machida | Light Heavyweight | 2143 | 12 |
| 36 | Anthony Johnson | Light Heavyweight | 2173 | 11 |
| 37 | Beneil Dariush | Lightweight | 2091 | 14 |
| 38 | Junior Dos Santos | Heavyweight | 2168 | 11 |
| 39 | Benson Henderson | Lightweight | 2135 | 12 |
| 40 | Magomed Ankalaev | Light Heavyweight | 2192 | 10 |
| 41 | Movsar Evloev | Featherweight | 2290 | 8 |
| 42 | Curtis Blaydes | Heavyweight | 2140 | 11 |
| 43 | Antonio Rodrigo Nogueira | Heavyweight | 2212 | 9 |
| 44 | Fabricio Werdum | Heavyweight | 2136 | 11 |
| 45 | Chris Weidman | Middleweight | 2127 | 11 |
| 46 | Belal Muhammad | Welterweight | 2127 | 11 |
| 47 | Shavkat Rakhmonov | Welterweight | 2313 | 7 |
| 48 | Leon Edwards | Welterweight | 2125 | 11 |
| 49 | Rashad Evans | Light Heavyweight | 2124 | 11 |
| 50 | Khamzat Chimaev | Middleweight | 2311 | 7 |

<!-- BOARD:ELITEPRIME50:END -->

### Current — men, top 30

<!-- BOARD:CURRENT30:BEGIN -->

| # | Fighter | Division | Rating | UFC bouts | Last bout |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | Islam Makhachev | Welterweight | 2381 | 19 | 2026-08-15 |
| 2 | Ilia Topuria | Lightweight | 2231 | 10 | 2026-06-14 |
| 3 | Francis Ngannou | Heavyweight | 2225 | 14 | 2026-05-16 |
| 4 | Ciryl Gane | Heavyweight | 2223 | 13 | 2026-06-14 |
| 5 | Movsar Evloev | Featherweight | 2213 | 10 | 2026-03-21 |
| 6 | Charles Oliveira | Lightweight | 2209 | 36 | 2026-03-07 |
| 7 | Dricus Du Plessis | Middleweight | 2197 | 11 | 2026-07-18 |
| 8 | Khamzat Chimaev | Middleweight | 2197 | 10 | 2026-05-09 |
| 9 | Justin Gaethje | Lightweight | 2193 | 16 | 2026-06-14 |
| 10 | Alexander Volkanovski | Featherweight | 2182 | 18 | 2026-01-31 |
| 11 | Ian Machado Garry | Welterweight | 2179 | 12 | 2026-08-15 |
| 12 | Arman Tsarukyan | Lightweight | 2178 | 12 | 2025-11-22 |
| 13 | Max Holloway | Featherweight | 2172 | 33 | 2026-07-11 |
| 14 | Carlos Ulberg | Light Heavyweight | 2156 | 11 | 2026-04-11 |
| 15 | Sean Strickland | Middleweight | 2155 | 25 | 2026-05-09 |
| 16 | Umar Nurmagomedov | Bantamweight | 2147 | 9 | 2026-01-24 |
| 17 | Merab Dvalishvili | Bantamweight | 2147 | 17 | 2025-12-06 |
| 18 | Petr Yan | Bantamweight | 2140 | 16 | 2025-12-06 |
| 19 | Magomed Ankalaev | Light Heavyweight | 2134 | 16 | 2026-07-25 |
| 20 | Aljamain Sterling | Bantamweight | 2121 | 23 | 2026-04-25 |
| 21 | Alexander Volkov | Heavyweight | 2116 | 19 | 2026-05-09 |
| 22 | Nassourdine Imavov | Middleweight | 2115 | 11 | 2025-09-06 |
| 23 | Corey Anderson | Light Heavyweight | 2112 | 15 | 2025-10-03 |
| 24 | Sean O'Malley | Bantamweight | 2111 | 15 | 2026-06-14 |
| 25 | Alex Pereira | Light Heavyweight | 2104 | 13 | 2026-06-14 |
| 26 | Sean Brady | Welterweight | 2097 | 11 | 2026-05-09 |
| 27 | Gabriel Bonfim | Welterweight | 2091 | 8 | 2026-06-06 |
| 28 | Sergei Pavlovich | Heavyweight | 2089 | 12 | 2026-05-30 |
| 29 | Anthony Hernandez | Middleweight | 2086 | 12 | 2026-02-21 |
| 30 | Mario Bautista | Bantamweight | 2086 | 15 | 2026-07-11 |

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
| [`site/`](site/) | Interactive analysis site, published at <https://symonyeal.github.io/UFC-Rank-Engine/>; open `site/index.html` locally |
| `tests/` | Verification |

Use the system Python:

```text
python -m pip install -r requirements.txt
python -m pytest -q
python build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
```

The site draws the notebook's analyses from one snapshot. Its data file, `site/data.js`, is
generated; rebuild it after the boards change:

```text
python analysis/build_site.py data/snapshots/2026-08-13
```
