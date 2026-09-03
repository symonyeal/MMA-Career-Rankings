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
| Current | How good are they now? | Their latest rating, aged forward and discounted for unidentified career, among fighters active in the last 18 months with 8+ UFC bouts |
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

**Two careers, and why the board separates them.** Demetrious Johnson is 7th and
Fedor Emelianenko 23rd, and the first thing to notice is that Fedor rates *higher*
at his peak — 2,014 against Johnson's 1,982. The board is not saying Johnson was
the better fighter at his best. It is saying he achieved more with it, and three
numbers carry that. **What they won:** Johnson has 12 title wins and 11 defenses
against Fedor's 5 and 2, which scores 2,248 against 804 — by far the largest gap
between them, and the achievement term is 30% of the whole score. **Who they
beat:** almost level, 6 contender wins to 5, scoring 1,139 against 1,009. **How
much of the career we can see:** Fedor never fought in the UFC, so his career is
judged on the promotions we can name, and his exposure factor is 0.835 against
Johnson's 0.897 — which cuts his skill figure by more than it cuts Johnson's.

That last one is a stated policy, not a fact the results prove, and it is the
part of Fedor's placement most open to argument — it is listed under
[Important limitations](#important-limitations) for exactly that reason. The
first two are not: a fighter who defended a world title eleven times did
something a fighter who defended twice did not, and the score is built to say so.


<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Prime | Prime rank | Elite wins |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | 3936.1 | 2210 | 1 | 12 |
| 2 | Islam Makhachev | 2337.0 | 2180 | 3 | 7 |
| 3 | Georges St-Pierre | 2209.2 | 2073 | 2 | 11 |
| 4 | Daniel Cormier | 1955.4 | 2080 | 5 | 8 |
| 5 | Jose Aldo | 1924.2 | 1930 | 16 | 9 |
| 6 | Alexander Volkanovski | 1878.4 | 2048 | 4 | 9 |
| 7 | Demetrious Johnson | 1814.4 | 1982 | 24 | 6 |
| 8 | Stipe Miocic | 1761.9 | 1994 | 22 | 6 |
| 9 | Anderson Silva | 1752.3 | 1922 | 8 | 11 |
| 10 | Francis Ngannou | 1667.2 | 2037 | 6 | 8 |
| 11 | Israel Adesanya | 1503.5 | 1935 | 15 | 9 |
| 12 | Max Holloway | 1473.9 | 1963 | 9 | 9 |
| 13 | Dominick Cruz | 1423.2 | 1941 | 34 | 5 |
| 14 | Khabib Nurmagomedov | 1408.7 | 2172 |  | 4 |
| 15 | Ilia Topuria | 1394.8 | 2119 | 12 | 5 |
| 16 | Merab Dvalishvili | 1350.9 | 1974 | 11 | 8 |
| 17 | Sean Strickland | 1269.1 | 1921 | 13 | 10 |
| 18 | Lyoto Machida | 1265.4 | 1976 | 19 | 7 |
| 19 | Aljamain Sterling | 1226.9 | 1945 | 25 | 7 |
| 20 | Matt Hughes | 1205.6 | 1830 |  | 3 |
| 21 | Alex Pereira | 1186.1 | 1962 | 21 | 7 |
| 22 | Justin Gaethje | 1181.1 | 1994 | 23 | 6 |
| 23 | Fedor Emelianenko | 1094.4 | 2014 | 27 | 5 |
| 24 | Charles Oliveira | 1067.7 | 1978 | 18 | 7 |
| 25 | Kamaru Usman | 1057.7 | 1968 | 7 | 10 |
| 26 | Benson Henderson | 1054.7 | 1869 | 42 | 6 |
| 27 | Dricus Du Plessis | 977.5 | 2044 | 14 | 6 |
| 28 | Dustin Poirier | 962.2 | 1922 | 38 | 5 |
| 29 | Junior Dos Santos | 944.5 | 1914 |  | 4 |
| 30 | Khamzat Chimaev | 923.5 | 2089 | 17 | 5 |
| 31 | Ciryl Gane | 921.0 | 2060 | 10 | 6 |
| 32 | Henry Cejudo | 900.4 | 1873 | 48 | 5 |
| 33 | Frankie Edgar | 889.6 | 1905 | 26 | 8 |
| 34 | Cain Velasquez | 882.9 | 1964 |  | 4 |
| 35 | Chris Weidman | 856.2 | 1871 | 33 | 8 |
| 36 | Patricio Freire | 845.5 | 1933 |  | 3 |
| 37 | Vadim Nemkov | 836.0 | 2067 | 20 | 5 |
| 38 | Petr Yan | 819.5 | 1951 | 28 | 6 |
| 39 | Dan Henderson | 813.1 | 1869 | 50 | 5 |
| 40 | Anthony Pettis | 808.6 | 1759 | 69 | 6 |
| 41 | Mauricio Rua | 797.4 | 1833 | 52 | 6 |
| 42 | Conor McGregor | 788.3 | 1840 |  | 4 |
| 43 | Ryan Bader | 788.1 | 1926 | 37 | 5 |
| 44 | Randy Couture | 758.2 | 1763 |  | 4 |
| 45 | Chuck Liddell | 747.6 | 1820 | 54 | 6 |
| 46 | BJ Penn | 745.2 | 1793 | 63 | 5 |
| 47 | Wanderlei Silva | 720.9 | 1812 |  | 4 |
| 48 | Tito Ortiz | 711.4 | 1786 |  | 4 |
| 49 | Robert Whittaker | 700.3 | 1893 | 32 | 7 |
| 50 | Movsar Evloev | 677.5 | 2103 |  | 4 |
| 51 | Anthony Johnson | 662.2 | 1938 | 30 | 6 |
| 52 | Gegard Mousasi | 661.3 | 1919 | 39 | 5 |
| 53 | Antonio Rodrigo Nogueira | 653.6 | 1889 |  | 4 |
| 54 | Leon Edwards | 651.6 | 1888 |  | 4 |
| 55 | Jan Blachowicz | 647.7 | 1801 | 62 | 5 |
| 56 | Eddie Alvarez | 645.3 | 1763 |  | 4 |
| 57 | Rashad Evans | 645.3 | 1814 | 60 | 5 |
| 58 | Fabricio Werdum | 638.2 | 1894 |  | 4 |
| 59 | Sean O'Malley | 627.2 | 1953 |  | 4 |
| 60 | Alexander Volkov | 608.7 | 1906 | 31 | 7 |
| 61 | Vitor Belfort | 606.8 | 1781 | 68 | 5 |
| 62 | Tom Aspinall | 600.3 | 1934 |  | 4 |
| 63 | Luke Rockhold | 592.8 | 1863 | 45 | 6 |
| 64 | Quinton Jackson | 585.6 | 1832 | 56 | 5 |
| 65 | Shavkat Rakhmonov | 585.2 | 2146 |  | 2 |
| 66 | Rafael Dos Anjos | 581.4 | 1772 | 66 | 7 |
| 67 | Phil Davis | 579.6 | 1956 |  | 4 |
| 68 | Derrick Lewis | 546.1 | 1818 | 59 | 5 |
| 69 | TJ Dillashaw | 544.8 | 1853 |  | 4 |
| 70 | Matt Serra | 542.4 | 1688 |  | 1 |
| 71 | Tyron Woodley | 542.0 | 1803 | 61 | 5 |
| 72 | Mirko Filipovic | 522.9 | 1831 |  | 4 |
| 73 | Jake Shields | 512.9 | 1820 | 51 | 7 |
| 74 | Deiveson Figueiredo | 508.6 | 1828 | 58 | 5 |
| 75 | Beneil Dariush | 507.6 | 1850 | 47 | 6 |
| 76 | Belal Muhammad | 505.9 | 1901 | 35 | 6 |
| 77 | Glover Teixeira | 504.7 | 1867 | 43 | 6 |
| 78 | Curtis Blaydes | 504.1 | 1910 | 40 | 5 |
| 79 | Nassourdine Imavov | 494.9 | 1941 | 29 | 6 |
| 80 | Joshua Van | 484.0 | 1944 |  | 3 |
| 81 | Arman Tsarukyan | 483.1 | 2014 |  | 4 |
| 82 | Demian Maia | 473.0 | 1853 | 46 | 6 |
| 83 | Sean Sherk | 470.3 | 1894 | 36 | 6 |
| 84 | Umar Nurmagomedov | 458.0 | 2027 |  | 4 |
| 85 | Urijah Faber | 456.8 | 1800 |  | 3 |
| 86 | Alistair Overeem | 450.1 | 1810 |  | 4 |
| 87 | Mark Coleman | 436.5 | 1722 |  | 2 |
| 88 | Robbie Lawler | 431.8 | 1705 |  | 3 |
| 89 | Andrei Arlovski | 424.1 | 1780 |  | 4 |
| 90 | Michael Chandler | 421.7 | 1812 |  | 1 |
| 91 | Renan Barao | 418.1 | 1648 |  | 3 |
| 92 | Carlos Condit | 417.3 | 1721 |  | 4 |
| 93 | Alexandre Pantoja | 414.4 | 1869 | 49 | 5 |
| 94 | Matt Hamill | 407.3 | 1652 |  | 2 |
| 95 | Magomed Ankalaev | 405.3 | 1968 |  | 2 |
| 96 | Sergio Pettis | 403.5 | 1830 |  | 3 |
| 97 | Joseph Benavidez | 403.2 | 1847 |  | 2 |
| 98 | Yaroslav Amosov | 402.5 | 2047 |  | 2 |
| 99 | Josh Barnett | 399.5 | 1903 |  | 2 |
| 100 | Ian Machado Garry | 399.0 | 2071 |  | 4 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

How good was the fighter at their best — counting only the peaks they actually
proved? To qualify, a fighter must have beaten **5 contenders within a single
ten-year stretch**. A contender means an opponent rated **1,750 or higher at the
time of the fight** who also had a tested record of their own: at least 8 UFC
bouts. That number is easier to read as names than as a figure. In the Prime
column of the top-100 table above — a fighter's rating across their best decade,
not their highest single reading — Anthony Pettis rates 1,759 and Randy Couture
1,763, both just over the line; Mark Coleman at 1,722 and Robbie Lawler at 1,705
sit just under it.
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
data. 72 men qualify, so this top 50 is full. Only 2 women do. That is a
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

### Current — men, top 30

How good is the fighter now? This starts from their last fitted rating, carried
to the snapshot date through the measured age-drift curve. Two screens then
decide who is on the board at all — both borrowed from the boards above rather
than invented for this one — and two discounts decide where they land.

**They must have fought within the last 18 months.** The age projection is
deliberately shallow — it charges Khabib Nurmagomedov 37 points for five years
out and Georges St-Pierre 48 for nine — so without this bar the board would seat
retired champions 4th and 21st and answer "how good were they" for a third time.
It is strict enough to withhold fighters who have not retired: Jon Jones and
Shavkat Rakhmonov are both out on it.

**They must have a tested record: at least 8 UFC bouts.** This is the same bar
the Prime board applies to an *opponent* before a win over them counts, used here
on the fighter. It matters because nothing in this kind of rating model caps an
unbeaten record from above — a fighter who rarely loses is rated above everyone
they have beaten, however weak the field. Ranked without it, this board put six
Bellator and PFL fighters in the top thirty, Usman Nurmagomedov 2nd, ahead of men
who had beaten the division. That is not a verdict on those fighters; it is the
model saying it cannot place them, and the honest response is to say so rather
than to rank them anyway.

**Time away is then charged, and it compounds.** The recency screen asks when a
fighter last competed; it cannot see a layoff that *ended* recently. Ronda Rousey
last fought in the UFC in 2016 and returned in May 2026, and the decade in
between cost her 36 rating points — because the age prior is a measured per-year
population rate, applied once across the gap. That put a 2015 rating 3rd on the
women's board.

A year out does not cost a fixed number of points. It costs a fraction of what a
fighter has left, and fractions multiply, so each year of the last ten holding no
bout retains 80% of that fighter's edge over the contender line. One idle year is
barely felt. Eight leave 17% of it, and Rousey is 11th rather than 3rd.

**The rating is also discounted by how much of the career we can identify**, the
same exposure factor the all-time board applies, adapted to the scale. The
all-time board multiplies Career Skill Mass, a sum with a real zero. A rating has
no zero, so multiplying it would be meaningless; the distance above the contender
line is shrunk instead.

Both the 18-month bar and the 80% retention are stated policy about what the word
"current" is willing to claim. Neither is fitted: there is no comeback sample in
this data large enough to estimate a return-from-layoff effect, and this project
does not dress a judgement as a measurement.

The result is on the same scale as the contender line in the release facts above.
The columns beside it are the screens and the discounts: the UFC bout count the
board gates on, how many of the last ten years held no bout, and the date the
rating was last proved.

Do not read this board against the two above it. All-time and Prime are
retrospective, and a career does not expire; this one is a claim about today.
The women's Current board is in [Published UFC Rankings](RANKINGS.md).

<!-- BOARD:CURRENT30:BEGIN -->

| # | Fighter | Rating | UFC bouts | Idle yrs | Last bout |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Islam Makhachev | 2068 | 18 | 1 | 2025-11-15 |
| 2 | Ilia Topuria | 2050 | 10 | 0 | 2026-06-14 |
| 3 | Movsar Evloev | 2050 | 10 | 0 | 2026-03-21 |
| 4 | Dricus Du Plessis | 2005 | 11 | 0 | 2026-07-18 |
| 5 | Arman Tsarukyan | 2003 | 12 | 0 | 2025-11-22 |
| 6 | Alexander Volkanovski | 1992 | 18 | 0 | 2026-01-31 |
| 7 | Umar Nurmagomedov | 1989 | 9 | 0 | 2026-01-24 |
| 8 | Justin Gaethje | 1985 | 16 | 0 | 2026-06-14 |
| 9 | Francis Ngannou | 1973 | 14 | 1 | 2026-05-16 |
| 10 | Merab Dvalishvili | 1967 | 17 | 0 | 2025-12-06 |
| 11 | Khamzat Chimaev | 1964 | 10 | 1 | 2026-05-09 |
| 12 | Charles Oliveira | 1961 | 36 | 0 | 2026-03-07 |
| 13 | Magomed Ankalaev | 1936 | 16 | 0 | 2026-07-25 |
| 14 | Ciryl Gane | 1933 | 13 | 2 | 2026-06-14 |
| 15 | Max Holloway | 1932 | 33 | 0 | 2026-07-11 |
| 16 | Sean O'Malley | 1932 | 15 | 0 | 2026-06-14 |
| 17 | Corey Anderson | 1923 | 15 | 0 | 2025-10-03 |
| 18 | Mario Bautista | 1922 | 15 | 0 | 2026-07-11 |
| 19 | Sean Brady | 1920 | 11 | 0 | 2026-05-09 |
| 20 | Aljamain Sterling | 1915 | 23 | 0 | 2026-04-25 |
| 21 | Alexander Volkov | 1907 | 19 | 0 | 2026-05-09 |
| 22 | Sean Strickland | 1906 | 25 | 1 | 2026-05-09 |
| 23 | Gabriel Bonfim | 1905 | 8 | 1 | 2026-06-06 |
| 24 | Caio Borralho | 1903 | 9 | 0 | 2026-03-07 |
| 25 | Petr Yan | 1900 | 16 | 1 | 2025-12-06 |
| 26 | Ian Machado Garry | 1897 | 11 | 3 | 2025-11-22 |
| 27 | Brendan Allen | 1893 | 19 | 0 | 2026-06-06 |
| 28 | Paddy Pimblett | 1893 | 9 | 0 | 2026-07-11 |
| 29 | Carlos Prates | 1891 | 8 | 0 | 2026-05-02 |
| 30 | Anthony Hernandez | 1890 | 12 | 0 | 2026-02-21 |

<!-- BOARD:CURRENT30:END -->

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

- **The all-time score is retrospective.** An opponent is priced on everything now
  known about them, so it measures how good a win turned out to be, not how good
  it looked on the night.
- **The contender résumé favours long careers**, though it counts at most one win
  per active year. Read it as context, not as a separate measure of skill.
- **The exposure factor is a stated policy** — a declared ranking of promotions.
  It helps compare careers we can only see part of, but it is an assumption, not
  something the fight results prove. 64% of rated fights carry no promotion name.
  Those fights are left out of the calculation rather than counted as small-show
  fights, because not knowing where a fight happened is not evidence that it was
  a minor event. A career we can only identify from a handful of fights is then
  pulled toward the average of everything we can identify, so it is not credited
  at full confidence on thin evidence. Jiri Prochazka, 18 of whose 40 fights are
  unnamed, reads 0.848 against the published men's top-100 median of 0.919. The
  limitation that remains is that a barely-identifiable career still receives an
  estimate rather than an admission that we cannot tell.
- **The major-title floor fixes the zero, not every pricing issue.** Value still
  comes mainly from the opponent beaten, measured against their own division.
  The new floor raises Prochazka's UFC title win over Glover Teixeira from 0.073
  to 0.119. His RIZIN title win remains 0.008 because RIZIN is outside the
  tier-1 gate, while his three title losses would price at 0.210–0.236 on the
  same opponent scale and are not counted. The mechanism and remaining policy
  choices are in the [decision register](docs/DECISIONS.md).
- **Weight class and fighter identity are partly inferred** where the sources are
  incomplete. About 17% of filled weight classes are wrong for that particular
  fight, and four fighters cannot be told apart from namesakes at all, so only
  their UFC record is held. Those inferences are audited, but they feed the
  rankings.
- **Close-date repeats need source evidence.** Canonical UFC URLs preserve
  Kazushi Sakuraba and Marcus Silveira's genuine same-night tournament rematch.
  Two non-UFC pairs recur one day apart — Anthony Ruiz–Jaime Jara and Mike
  Whitehead–Tim Sylvia — and both rows are retained because the source names
  successive events and no available evidence establishes a duplicate. Neither
  ambiguous pair changes the contender-win count.
- **The Current board's idle-year discount is a judgement, not a measurement.**
  Charging 20% of a fighter's edge per idle year is a statement about what
  "current" should claim, chosen because the alternative — the measured age prior
  alone — charged Ronda Rousey 36 points for a decade away and seated a 2015
  rating 3rd. The discount is applied to a rating, not to evidence: it does not
  make the model know what a fighter looks like after a layoff.
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
