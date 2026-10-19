# UFC Career Rankings

<p align="center">
  <a href="https://symonyeal.github.io/UFC-Career-Rankings/"><img alt="Open the interactive rankings site" src="https://img.shields.io/badge/Interactive%20rankings-Open%20the%20site-38bdf8?style=for-the-badge"></a>
</p>

<p align="center"><b><a href="https://symonyeal.github.io/UFC-Career-Rankings/">symonyeal.github.io/UFC-Career-Rankings</a></b>
· every ranking and analysis in the browser, no install</p>

[![The interactive site: the published boards, filtered by roster, weight class and depth](docs/site/rankings.png)](https://symonyeal.github.io/UFC-Career-Rankings/)

## In plain terms

Who is the greatest UFC fighter? The answer depends on the question, so this project
answers three: the best career of all time, the best fighter at their peak, and the best
fighter right now. Men and women are ranked separately.

Every recorded professional MMA fight (over 81,000 fights between 34,000 fighters) goes into
one rating model, which works like chess ratings. Beating a strong opponent raises a rating
more than beating a weak one, and later results can revise how strong past opponents really
were. A career score then adds up three things: title fights won, wins over top
contenders, and how far the fighter's rating stood above contender level, year by year.

By this measure Jon Jones ranks first for both career and peak. Islam Makhachev and
Georges St-Pierre fill the next two places on both lists. On the site you can change how
much each part of the score counts and watch the order change.

The site above is the way to read the answers. One set of controls (men or women, weight
class, how many fighters, minimum rated bouts) drives every section. The rest of this page
gives the exact rules.

## What the site does

| Feature | What you can do |
| --- | --- |
| [**Rankings**](https://symonyeal.github.io/UFC-Career-Rankings/#rankings) | All-time, Prime and Current, exactly as published below. Pick a weight class for that class's own board: the All-time score earned in UFC bouts in that class. |
| [**Weight-class boards**](https://symonyeal.github.io/UFC-Career-Rankings/#rankings) | UFC only. A champion in two classes is ranked in both, with the share of their All-time score earned in each. |
| [**Score anatomy**](https://symonyeal.github.io/UFC-Career-Rankings/#anatomy) | See each score split into championships, career skill and contender résumé. Move two sliders to change the exchange rate and watch the board re-rank. |
| [**Rank robustness**](https://symonyeal.github.io/UFC-Career-Rankings/#anatomy) | A heat map of one fighter's rank under every exchange rate, with the published choice marked. |
| [**Career arcs and tale of the tape**](https://symonyeal.github.io/UFC-Career-Rankings/#fighters) | Overlay up to six fighters' ratings fight by fight and compare their records, ranks and class placements side by side. |
| [**Where a career score comes from**](https://symonyeal.github.io/UFC-Career-Rankings/#careers) | A year-by-year receipt that sums to the career score, and how the order holds when every year's bar is raised. |
| [**Risers, fallers and streaks**](https://symonyeal.github.io/UFC-Career-Rankings/#movers) | The biggest rating moves of any year, and the longest UFC win streaks placed by length and by the strength of who they beat. |
| [**Weight classes and eras**](https://symonyeal.github.io/UFC-Career-Rankings/#divisions) | UFC only: how strong each class has been year by year, its top five in any year, and how fights end. |
| [**Title lineage**](https://symonyeal.github.io/UFC-Career-Rankings/#lineage) | Every reign in every class, with defences. |
| [**Integrity policy and outside check**](https://symonyeal.github.io/UFC-Career-Rankings/#policy) | The PED, disqualification and missed-weight ledger, and where the board disagrees with FightMatrix. |
| [**Forecast calibration**](https://symonyeal.github.io/UFC-Career-Rankings/#checks) | How often pre-fight favourites actually won, against the probability they were given, with 95% intervals. |

Each chart includes a finding calculated from the data under the current controls.
The page follows the reader's light or dark setting.

On a phone, open **Explore the rankings** to change the filters. Wide tables scroll
inside their panels. Weight-class buttons work with a keyboard, and the page follows
the reader's reduced-motion setting.

To check the interface locally, run `npm ci`, `npx playwright install chromium`, then
`npm test`. The browser checks cover search positions, roster filters, fighter
comparisons, analysis charts, phone layouts and dark mode. They also run in CI.

| Weight-class board | Score anatomy and exchange rates |
| --- | --- |
| [![Heavyweight class board](docs/site/class-board.png)](https://symonyeal.github.io/UFC-Career-Rankings/#rankings) | [![Score anatomy](docs/site/score-anatomy.png)](https://symonyeal.github.io/UFC-Career-Rankings/#anatomy) |
| **Career arcs and tale of the tape** | **Weight classes over time** |
| [![Career arcs](docs/site/career-arcs.png)](https://symonyeal.github.io/UFC-Career-Rankings/#fighters) | [![Division strength](docs/site/weight-classes.png)](https://symonyeal.github.io/UFC-Career-Rankings/#divisions) |

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
All-time = 1,000 × (30% √title + 17.5% √skill + 52.5% √résumé)
```

Each part is divided by the average of its own top 100, then square-rooted, before
weighting. A part of 1.0 still means "as much as a typical top-100 career", but
doubling a part adds only about 41%, so a career is paid for breadth across the
three parts more than for an extreme in one.

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

All-time and Prime read every rating against its own year's contender line. The
model's scale drifts upward over time: on this fit the 60th-best man stood at
1,834 in 2007 and 1,918 in 2023, so without this era adjustment a 2023 win would
be priced on a scale about 85 points higher than a 2007 win. Current, whose
fighters are all contemporaries, reads the unadjusted ratings.

**The score is a points total, not a ratio.** Jon Jones's 1,855 against Georges
St-Pierre's 1,554 does not mean Jones was 19% better. It means his three parts add
up to more points: title 618 against 486, résumé 853 against 764, skill 385
against 304. Most of the résumé gap is two elite wins: Daniel Cormier at 334
points above the line and Ciryl Gane at 258, where St-Pierre's best was Sean
Sherk at 189. For who was better at their best, read Prime: 2,192 against 2,110,
an 82-point edge, which the rating turns into about a 62% chance of winning.

Prime takes the ten-year stretch with the most wins over contenders, using the
same contender rule as the résumé, and needs five. It ranks by those wins times
the stretch's average rating above the lowest qualifying average. Current uses
the All-time formula over the last 18 months: title wins and contender wins in
that window, plus the latest rating above 1,750, capped at the best opponent the
fighter has ever beaten so an unbeaten run against weak opposition cannot keep
climbing. It needs 13 rated appearances, eight UFC bouts and a UFC bout within
18 months. Integrity deductions never alter a published board.

Each weight class has its own board, and it is UFC only: the All-time score counted
only from the title wins, contender wins and career years earned in UFC bouts in
that class. All-time and Prime count every promotion; the class boards and Current
count the UFC. What a fighter earned outside the UFC stays in their All-time score
but in no class, so their class scores add up to their All-time score less that
remainder. A champion in two classes is ranked in both.

## What is published

The men's headline boards are published below so the rankings are visible on
the repository front page. The full [Published UFC Rankings](RANKINGS.md) adds
the three women's boards and the weight-class boards.

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
| Prime contender threshold | 1,750 — reached by 25.3% of established fighters |
| Prime qualifiers | 65 men; 4 women |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

**Prime** and **Prime rank** come from the Prime board below, and **Elite
wins** is the evidence behind that rank. A blank rank means the fighter did not
qualify, not that they placed last.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Division | Score | Prime | Prime rank | Elite wins |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 1855.3 | 2192 | 1 | 11 |
| 2 | Islam Makhachev | Lightweight | 1594.2 | 2152 | 3 | 8 |
| 3 | Georges St-Pierre | Welterweight | 1553.9 | 2110 | 2 | 12 |
| 4 | Anderson Silva | Middleweight | 1361.4 | 1955 | 4 | 14 |
| 5 | Daniel Cormier | Light Heavyweight | 1349.4 | 2054 | 6 | 8 |
| 6 | Jose Aldo | Featherweight | 1348.3 | 1914 | 13 | 9 |
| 7 | Demetrious Johnson | Flyweight | 1341.1 | 1951 | 29 | 5 |
| 8 | Alexander Volkanovski | Featherweight | 1240.0 | 2007 | 7 | 9 |
| 9 | Stipe Miocic | Heavyweight | 1235.2 | 1949 | 23 | 6 |
| 10 | Fedor Emelianenko | Heavyweight | 1227.7 | 2085 | 5 | 9 |
| 11 | Dominick Cruz | Bantamweight | 1223.8 | 1934 | 35 | 5 |
| 12 | Matt Hughes | Welterweight | 1197.9 | 1976 |  | 4 |
| 13 | Lyoto Machida | Light Heavyweight | 1158.7 | 2011 | 9 | 7 |
| 14 | Francis Ngannou | Heavyweight | 1151.4 | 1993 | 15 | 6 |
| 15 | Randy Couture | Heavyweight | 1115.8 | 1879 | 21 | 9 |
| 16 | Ilia Topuria | Featherweight | 1105.5 | 2078 |  | 4 |
| 17 | Khabib Nurmagomedov | Lightweight | 1072.7 | 2131 |  | 4 |
| 18 | Tito Ortiz | Light Heavyweight | 1056.6 | 1869 | 49 | 6 |
| 19 | BJ Penn | Lightweight | 1049.8 | 1888 | 17 | 9 |
| 20 | Max Holloway | Featherweight | 1047.9 | 1920 | 12 | 9 |
| 21 | Dan Henderson | Middleweight | 1044.1 | 1946 | 16 | 7 |
| 22 | Chuck Liddell | Light Heavyweight | 1033.0 | 1883 | 19 | 9 |
| 23 | Israel Adesanya | Middleweight | 1023.8 | 1880 | 33 | 7 |
| 24 | Benson Henderson | Lightweight | 1005.1 | 1852 | 43 | 7 |
| 25 | Antonio Rodrigo Nogueira | Heavyweight | 995.0 | 2041 | 8 | 7 |
| 26 | Justin Gaethje | Lightweight | 981.9 | 1953 | 28 | 5 |
| 27 | Frankie Edgar | Lightweight | 965.0 | 1911 | 10 | 10 |
| 28 | Mauricio Rua | Light Heavyweight | 962.3 | 1854 | 41 | 7 |
| 29 | Cain Velasquez | Heavyweight | 958.3 | 1963 | 20 | 6 |
| 30 | Merab Dvalishvili | Bantamweight | 957.9 | 1930 | 25 | 6 |
| 31 | Junior Dos Santos | Heavyweight | 942.7 | 1909 | 30 | 6 |
| 32 | Sean Strickland | Middleweight | 930.0 | 1876 | 26 | 8 |
| 33 | Aljamain Sterling | Bantamweight | 925.0 | 1904 | 46 | 5 |
| 34 | Wanderlei Silva | Light Heavyweight | 923.0 | 1892 |  | 4 |
| 35 | Alex Pereira | Light Heavyweight | 922.8 | 1920 | 38 | 5 |
| 36 | Dricus Du Plessis | Middleweight | 911.7 | 2004 | 14 | 6 |
| 37 | Chris Weidman | Middleweight | 879.5 | 1853 | 42 | 7 |
| 38 | Kamaru Usman | Welterweight | 870.3 | 1924 | 22 | 7 |
| 39 | Charles Oliveira | Lightweight | 866.0 | 1937 | 24 | 6 |
| 40 | Vitor Belfort | Middleweight | 864.9 | 1812 | 58 | 5 |
| 41 | Khamzat Chimaev | Middleweight | 856.8 | 2047 |  | 4 |
| 42 | Mark Coleman | Heavyweight | 830.5 | 1873 |  | 3 |
| 43 | Henry Cejudo | Flyweight | 825.6 | 1836 |  | 4 |
| 44 | Ciryl Gane | Heavyweight | 822.2 | 2012 |  | 4 |
| 45 | Sean Sherk | Lightweight | 820.0 | 1984 | 11 | 7 |
| 46 | Anthony Pettis | Lightweight | 819.9 | 1756 | 63 | 5 |
| 47 | Petr Yan | Bantamweight | 814.9 | 1904 |  | 3 |
| 48 | Rashad Evans | Light Heavyweight | 812.9 | 1873 | 34 | 7 |
| 49 | Dustin Poirier | Lightweight | 810.8 | 1895 |  | 4 |
| 50 | Mirko Filipovic | Heavyweight | 810.2 | 1865 | 53 | 5 |
| 51 | Quinton Jackson | Light Heavyweight | 808.9 | 1873 | 45 | 6 |
| 52 | Gegard Mousasi | Middleweight | 808.7 | 1918 | 39 | 5 |
| 53 | Ryan Bader | Light Heavyweight | 806.2 | 1904 | 47 | 5 |
| 54 | Conor McGregor | Featherweight | 802.9 | 1805 |  | 4 |
| 55 | Patricio Freire | Featherweight | 802.8 | 1907 |  | 3 |
| 56 | Vadim Nemkov | Light Heavyweight | 794.0 | 2023 | 18 | 5 |
| 57 | Fabricio Werdum | Heavyweight | 784.9 | 1908 | 32 | 6 |
| 58 | Rich Franklin | Middleweight | 784.7 | 1908 | 31 | 6 |
| 59 | Josh Barnett | Heavyweight | 765.8 | 1994 |  | 4 |
| 60 | Andrei Arlovski | Heavyweight | 755.7 | 1811 | 59 | 5 |
| 61 | Sean O'Malley | Bantamweight | 750.9 | 1920 |  | 4 |
| 62 | Eddie Alvarez | Lightweight | 746.5 | 1724 |  | 4 |
| 63 | Matt Serra | Welterweight | 743.0 | 1766 |  | 3 |
| 64 | Joshua Van | Flyweight | 724.4 | 1951 |  | 3 |
| 65 | Luke Rockhold | Middleweight | 718.4 | 1841 | 56 | 5 |
| 66 | Phil Davis | Light Heavyweight | 716.0 | 1934 |  | 4 |
| 67 | Jens Pulver | Lightweight | 705.7 | 1715 | 65 | 5 |
| 68 | Jake Shields | Welterweight | 701.4 | 1833 | 48 | 8 |
| 69 | Kevin Randleman | Heavyweight | 689.3 | 1703 |  | 4 |
| 70 | Tim Sylvia | Heavyweight | 680.0 | 1856 |  | 3 |
| 71 | Tom Aspinall | Heavyweight | 671.9 | 1893 |  | 3 |
| 72 | Forrest Griffin | Light Heavyweight | 671.4 | 1850 | 51 | 6 |
| 73 | Ricardo Arona |  | 668.3 | 1925 | 37 | 5 |
| 74 | Frank Shamrock | Light Heavyweight | 655.9 | 1781 |  | 2 |
| 75 | Carlos Condit | Welterweight | 651.5 | 1704 |  | 4 |
| 76 | Tyron Woodley | Welterweight | 648.9 | 1763 |  | 4 |
| 77 | Urijah Faber | Bantamweight | 645.4 | 1800 |  | 3 |
| 78 | Kazushi Sakuraba | Welterweight | 640.8 | 1779 |  | 3 |
| 79 | Deiveson Figueiredo | Flyweight | 639.2 | 1774 |  | 4 |
| 80 | Robert Whittaker | Middleweight | 637.6 | 1844 | 52 | 6 |
| 81 | Frank Mir | Heavyweight | 631.8 | 1758 |  | 4 |
| 82 | Pedro Rizzo | Heavyweight | 631.7 | 1834 |  | 4 |
| 83 | Rafael Dos Anjos | Lightweight | 630.6 | 1726 | 64 | 6 |
| 84 | Movsar Evloev | Featherweight | 626.2 | 2060 |  | 4 |
| 85 | Renan Barao | Bantamweight | 624.4 | 1617 |  | 3 |
| 86 | Leon Edwards | Welterweight | 621.7 | 1801 |  | 2 |
| 87 | Jan Blachowicz | Light Heavyweight | 612.3 | 1751 |  | 3 |
| 88 | Anthony Johnson | Light Heavyweight | 609.5 | 1921 | 27 | 6 |
| 89 | Demian Maia | Welterweight | 594.9 | 1847 | 36 | 8 |
| 90 | TJ Dillashaw | Bantamweight | 594.7 | 1804 |  | 3 |
| 91 | Jeremy Horn | Middleweight | 594.5 | 1874 | 44 | 6 |
| 92 | Rogerio Nogueira | Light Heavyweight | 581.6 | 1863 | 54 | 5 |
| 93 | Robbie Lawler | Welterweight | 576.1 | 1670 |  | 3 |
| 94 | Mike Brown | Featherweight | 575.9 | 1683 |  | 2 |
| 95 | Alexander Volkov | Heavyweight | 574.4 | 1868 | 50 | 6 |
| 96 | Magomed Ankalaev | Light Heavyweight | 569.5 | 1928 |  | 2 |
| 97 | Diego Sanchez | Welterweight | 569.5 | 1807 |  | 4 |
| 98 | Alistair Overeem | Heavyweight | 561.4 | 1781 |  | 4 |
| 99 | Michael Bisping | Middleweight | 559.9 | 1822 |  | 2 |
| 100 | Johnny Eblen | Middleweight | 557.1 | 1995 |  | 2 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

The table prints both inputs instead of the internal ordering index.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Division | Prime | Elite wins |
| ---: | --- | --- | ---: | ---: |
| 1 | Jon Jones | Light Heavyweight | 2192 | 11 |
| 2 | Georges St-Pierre | Welterweight | 2110 | 12 |
| 3 | Islam Makhachev | Lightweight | 2152 | 8 |
| 4 | Anderson Silva | Middleweight | 1955 | 14 |
| 5 | Fedor Emelianenko | Heavyweight | 2085 | 9 |
| 6 | Daniel Cormier | Light Heavyweight | 2054 | 8 |
| 7 | Alexander Volkanovski | Featherweight | 2007 | 9 |
| 8 | Antonio Rodrigo Nogueira | Heavyweight | 2041 | 7 |
| 9 | Lyoto Machida | Light Heavyweight | 2011 | 7 |
| 10 | Frankie Edgar | Lightweight | 1911 | 10 |
| 11 | Sean Sherk | Lightweight | 1984 | 7 |
| 12 | Max Holloway | Featherweight | 1920 | 9 |
| 13 | Jose Aldo | Featherweight | 1914 | 9 |
| 14 | Dricus Du Plessis | Middleweight | 2004 | 6 |
| 15 | Francis Ngannou | Heavyweight | 1993 | 6 |
| 16 | Dan Henderson | Middleweight | 1946 | 7 |
| 17 | BJ Penn | Lightweight | 1888 | 9 |
| 18 | Vadim Nemkov | Light Heavyweight | 2023 | 5 |
| 19 | Chuck Liddell | Light Heavyweight | 1883 | 9 |
| 20 | Cain Velasquez | Heavyweight | 1963 | 6 |
| 21 | Randy Couture | Heavyweight | 1879 | 9 |
| 22 | Kamaru Usman | Welterweight | 1924 | 7 |
| 23 | Stipe Miocic | Heavyweight | 1949 | 6 |
| 24 | Charles Oliveira | Lightweight | 1937 | 6 |
| 25 | Merab Dvalishvili | Bantamweight | 1930 | 6 |
| 26 | Sean Strickland | Middleweight | 1876 | 8 |
| 27 | Anthony Johnson | Light Heavyweight | 1921 | 6 |
| 28 | Justin Gaethje | Lightweight | 1953 | 5 |
| 29 | Demetrious Johnson | Flyweight | 1951 | 5 |
| 30 | Junior Dos Santos | Heavyweight | 1909 | 6 |
| 31 | Rich Franklin | Middleweight | 1908 | 6 |
| 32 | Fabricio Werdum | Heavyweight | 1908 | 6 |
| 33 | Israel Adesanya | Middleweight | 1880 | 7 |
| 34 | Rashad Evans | Light Heavyweight | 1873 | 7 |
| 35 | Dominick Cruz | Bantamweight | 1934 | 5 |
| 36 | Demian Maia | Welterweight | 1847 | 8 |
| 37 | Ricardo Arona |  | 1925 | 5 |
| 38 | Alex Pereira | Light Heavyweight | 1920 | 5 |
| 39 | Gegard Mousasi | Middleweight | 1918 | 5 |
| 40 | Curtis Blaydes | Heavyweight | 1879 | 6 |
| 41 | Mauricio Rua | Light Heavyweight | 1854 | 7 |
| 42 | Chris Weidman | Middleweight | 1853 | 7 |
| 43 | Benson Henderson | Lightweight | 1852 | 7 |
| 44 | Jeremy Horn | Middleweight | 1874 | 6 |
| 45 | Quinton Jackson | Light Heavyweight | 1873 | 6 |
| 46 | Aljamain Sterling | Bantamweight | 1904 | 5 |
| 47 | Ryan Bader | Light Heavyweight | 1904 | 5 |
| 48 | Jake Shields | Welterweight | 1833 | 8 |
| 49 | Tito Ortiz | Light Heavyweight | 1869 | 6 |
| 50 | Alexander Volkov | Heavyweight | 1868 | 6 |

<!-- BOARD:ELITEPRIME50:END -->

### Current — men, top 30

<!-- BOARD:CURRENT30:BEGIN -->

| # | Fighter | Division | Score | Title wins | Contender wins | UFC bouts | Last UFC bout |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Justin Gaethje | Lightweight | 2075 | 2 | 2 | 16 | 2026-06-14 |
| 2 | Islam Makhachev | Welterweight | 1950 | 2 | 2 | 19 | 2026-08-15 |
| 3 | Joshua Van | Flyweight | 1810 | 3 | 4 | 12 | 2026-09-19 |
| 4 | Sean Strickland | Middleweight | 1718 | 1 | 2 | 25 | 2026-05-09 |
| 5 | Merab Dvalishvili | Bantamweight | 1536 | 2 | 2 | 17 | 2025-12-06 |
| 6 | Khamzat Chimaev | Middleweight | 1531 | 1 | 1 | 10 | 2026-05-09 |
| 7 | Petr Yan | Bantamweight | 1458 | 1 | 1 | 16 | 2025-12-06 |
| 8 | Ilia Topuria | Lightweight | 1418 | 1 | 1 | 10 | 2026-06-14 |
| 9 | Alexander Volkanovski | Featherweight | 1397 | 2 | 2 | 18 | 2026-01-31 |
| 10 | Alex Pereira | Light Heavyweight | 1310 | 1 | 1 | 13 | 2026-06-14 |
| 11 | Ciryl Gane | Heavyweight | 1270 | 1 | 1 | 13 | 2026-06-14 |
| 12 | Carlos Ulberg | Light Heavyweight | 1184 | 1 | 2 | 11 | 2026-04-11 |
| 13 | Jack Della Maddalena | Welterweight | 1058 | 1 | 1 | 10 | 2026-05-02 |
| 14 | Charles Oliveira | Lightweight | 1018 | 0 | 2 | 36 | 2026-03-07 |
| 15 | Ian Machado Garry | Welterweight | 927 | 0 | 2 | 12 | 2026-08-15 |
| 16 | Carlos Prates | Welterweight | 821 | 0 | 2 | 8 | 2026-05-02 |
| 17 | Movsar Evloev | Featherweight | 810 | 0 | 1 | 10 | 2026-03-21 |
| 18 | Nassourdine Imavov | Middleweight | 809 | 0 | 1 | 11 | 2025-09-06 |
| 19 | Sean O'Malley | Bantamweight | 796 | 0 | 2 | 15 | 2026-06-14 |
| 20 | Diego Lopes | Featherweight | 794 | 0 | 2 | 10 | 2026-06-14 |
| 21 | Song Yadong | Bantamweight | 791 | 0 | 1 | 18 | 2026-08-29 |
| 22 | Umar Nurmagomedov | Bantamweight | 772 | 0 | 1 | 10 | 2026-08-29 |
| 23 | Manel Kape | Flyweight | 768 | 0 | 2 | 11 | 2026-06-20 |
| 24 | Jean Silva | Featherweight | 746 | 0 | 2 | 8 | 2026-09-12 |
| 25 | Alexander Volkov | Heavyweight | 734 | 0 | 2 | 19 | 2026-05-09 |
| 26 | Gregory Rodrigues | Middleweight | 712 | 0 | 2 | 14 | 2026-08-22 |
| 27 | Max Holloway | Featherweight | 688 | 0 | 1 | 33 | 2026-07-11 |
| 28 | Brendan Allen | Middleweight | 687 | 0 | 2 | 20 | 2026-10-10 |
| 29 | Dricus Du Plessis | Middleweight | 669 | 0 | 1 | 11 | 2026-07-18 |
| 30 | Aljamain Sterling | Bantamweight | 640 | 0 | 2 | 23 | 2026-04-25 |

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
| [`site/`](site/) | Interactive analysis site, published at <https://symonyeal.github.io/UFC-Career-Rankings/>; open `site/index.html` locally |
| `tests/` | Verification |

Use the system Python:

```text
python -m pip install -r requirements.txt
python -m pytest -q
python check_release.py
python build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
```

The site draws the notebook's analyses from one snapshot. Its data file, `site/data.js`, is
generated; rebuild it after the boards change:

```text
python analysis/build_site.py data/snapshots/2026-08-13
```

`index.html` loads each asset as `name?v=<content hash>`, so a browser never pairs the page with a
cached older asset. After editing `app.js` or `style.css` alone, re-stamp with
`python analysis/build_site.py --stamp`; a test fails while the stamp is stale.
