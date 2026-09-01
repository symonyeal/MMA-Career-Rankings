# Symon UFC Rank Engine

The Symon UFC Rank Engine turns fight history into explainable rankings. It
answers three questions: what a fighter's completed career amounted to, how
strong they were at their best, and how strong they are now. It is built for
analysts and editors who need a ranking that can be reproduced and traced back
to the fights behind it, rather than one assembled by opinion.

The all-time top 100 and the elite-tested Prime 50 are below, under
[Published rankings](#published-rankings). Every generated table, including the
women's boards, is in [Published UFC Rankings](RANKINGS.md). Both documents
record the snapshot, scope, score and row counts beside the tables, so a release
cannot be separated from the facts it was built from.

## What is published

| Ranking | Question it answers | Measure |
| --- | --- | --- |
| All-time | What did the fighter's completed career amount to? | Sustained skill, championship results and schedule strength, combined into one score |
| Prime | How good were they at their best, and how often did they prove it? | Their level across their strongest ten-year stretch, multiplied by how many rated contenders they beat inside it |
| Current | How strong are they now? | Their latest estimated level, adjusted for age and time out of competition |
| Integrity | How would the stated conduct discounts change the order? | An itemised deduction against a fighter's rating, published with the reason for each |

All-time, Prime and Current are three views of the same fight history and must
not be added together. Integrity is an audit published beside them; it never
alters the ratings themselves.

## Published rankings

The two headline boards are here; the women's boards are in
[Published UFC Rankings](RANKINGS.md). One `build_boards.py` run writes both
documents from one snapshot, and every marked block in both is checked before
either is rewritten, so no table can drift from the release facts beside it.

<!-- PUBLICATION:RELEASE:BEGIN -->

| Release fact | Value |
| --- | ---: |
| Snapshot | 2026-08-13 |
| Published scope | majors,pre_unified |
| Published score | public_legacy_score |
| Rated bouts | 80,697 |
| Rated fighters | 33,692 |
| Maximum-coverage fight rows | 82,171 |
| Contender line | 1,750 — reached by 19.2% of established fighters |

<!-- PUBLICATION:RELEASE:END -->

### All-time — men, top 100

What the fighter's completed career amounted to: sustained skill, championship
results and the strength of who they faced, combined into one score.

**Prime** and **Elite wins** are printed beside it, on every board. Prime is the
fighter's level across their best elite decade, on the same scale as the
contender line in the release facts above, so that line can be read against
names. Elite wins is how many contenders they beat inside that decade. A blank
means the fighter never beat one.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Prime | Elite wins |
| ---: | --- | ---: | ---: | ---: |
| 1 | Jon Jones | 2854.6 | 2213 | 12 |
| 2 | Georges St-Pierre | 2207.8 | 2074 | 11 |
| 3 | Demetrious Johnson | 1840.6 | 1975 | 6 |
| 4 | Jose Aldo | 1609.1 | 1930 | 9 |
| 5 | Daniel Cormier | 1589.0 | 2084 | 8 |
| 6 | Islam Makhachev | 1576.6 | 2195 | 9 |
| 7 | Alexander Volkanovski | 1311.3 | 2050 | 9 |
| 8 | Anderson Silva | 1297.7 | 1923 | 11 |
| 9 | Matt Hughes | 1237.9 | 1831 | 3 |
| 10 | Stipe Miocic | 1210.3 | 2003 | 6 |
| 11 | Max Holloway | 1186.3 | 1962 | 9 |
| 12 | Dominick Cruz | 1134.6 | 1941 | 5 |
| 13 | Khabib Nurmagomedov | 1126.4 | 2172 | 4 |
| 14 | Randy Couture | 1044.0 | 1769 | 5 |
| 15 | Francis Ngannou | 992.8 | 2039 | 8 |
| 16 | Lyoto Machida | 975.9 | 1978 | 8 |
| 17 | Aljamain Sterling | 971.3 | 1945 | 7 |
| 18 | Chuck Liddell | 960.4 | 1823 | 8 |
| 19 | Ilia Topuria | 954.4 | 2118 | 5 |
| 20 | Cain Velasquez | 930.0 | 1967 | 4 |
| 21 | Israel Adesanya | 911.0 | 1934 | 9 |
| 22 | Fedor Emelianenko | 900.8 | 2017 | 5 |
| 23 | Dan Henderson | 886.6 | 1870 | 5 |
| 24 | Patricio Freire | 874.2 | 1927 | 3 |
| 25 | BJ Penn | 827.0 | 1791 | 5 |
| 26 | Merab Dvalishvili | 824.2 | 1975 | 8 |
| 27 | Alex Pereira | 790.4 | 1962 | 7 |
| 28 | Justin Gaethje | 778.5 | 1993 | 6 |
| 29 | Joseph Benavidez | 754.5 | 1850 | 2 |
| 30 | Henry Cejudo | 750.5 | 1875 | 5 |
| 31 | Quinton Jackson | 722.8 | 1826 | 5 |
| 32 | Benson Henderson | 709.1 | 1880 | 7 |
| 33 | Ryan Bader | 705.2 | 1935 | 6 |
| 34 | Frankie Edgar | 700.0 | 1893 | 8 |
| 35 | Petr Yan | 684.5 | 1953 | 6 |
| 36 | Vitor Belfort | 684.1 | 1783 | 5 |
| 37 | Josh Barnett | 680.1 | 1906 | 2 |
| 38 | Junior Dos Santos | 678.5 | 1916 | 4 |
| 39 | Fabricio Werdum | 676.4 | 1895 | 4 |
| 40 | Kamaru Usman | 670.2 | 1967 | 9 |
| 41 | Khamzat Chimaev | 667.2 | 2090 | 5 |
| 42 | Chris Weidman | 660.9 | 1871 | 8 |
| 43 | Charles Oliveira | 655.2 | 1978 | 7 |
| 44 | Tyron Woodley | 615.5 | 1803 | 5 |
| 45 | Antonio Rodrigo Nogueira | 611.9 | 1891 | 4 |
| 46 | TJ Dillashaw | 602.2 | 1855 | 4 |
| 47 | Dricus Du Plessis | 592.2 | 2043 | 6 |
| 48 | Mauricio Rua | 590.9 | 1835 | 6 |
| 49 | Eddie Alvarez | 554.0 | 1772 | 4 |
| 50 | Rashad Evans | 545.3 | 1816 | 5 |
| 51 | Deiveson Figueiredo | 538.0 | 1832 | 5 |
| 52 | Conor McGregor | 521.7 | 1840 | 4 |
| 53 | Mirko Filipovic | 508.6 | 1833 | 4 |
| 54 | Luke Rockhold | 507.8 | 1865 | 6 |
| 55 | Robbie Lawler | 498.0 | 1706 | 3 |
| 56 | Ciryl Gane | 497.9 | 2058 | 6 |
| 57 | Vadim Nemkov | 495.4 | 2068 | 5 |
| 58 | Tito Ortiz | 487.5 | 1789 | 4 |
| 59 | Wanderlei Silva | 487.1 | 1819 | 4 |
| 60 | Michael Chandler | 475.0 | 1811 | 2 |
| 61 | Rich Franklin | 472.5 | 1805 | 2 |
| 62 | Sean Strickland | 471.6 | 1918 | 9 |
| 63 | Movsar Evloev | 465.5 | 2102 | 4 |
| 64 | Yoel Romero | 454.2 | 1868 | 6 |
| 65 | Leon Edwards | 453.9 | 1887 | 4 |
| 66 | Frank Mir | 445.5 | 1738 | 3 |
| 67 | Brandon Moreno | 444.2 | 1777 | 3 |
| 68 | Dustin Poirier | 436.5 | 1925 | 6 |
| 69 | Alistair Overeem | 428.1 | 1812 | 4 |
| 70 | Rafael Dos Anjos | 428.1 | 1771 | 7 |
| 71 | Urijah Faber | 424.5 | 1799 | 3 |
| 72 | Anthony Pettis | 423.4 | 1771 | 6 |
| 73 | Takanori Gomi | 415.6 |  |  |
| 74 | Jussier Formiga | 408.8 | 1771 | 3 |
| 75 | Robert Whittaker | 386.9 | 1900 | 8 |
| 76 | Renan Barao | 382.4 | 1647 | 3 |
| 77 | Matt Serra | 382.3 | 1685 | 1 |
| 78 | Mark Coleman | 378.0 | 1724 | 2 |
| 79 | Kyoji Horiguchi | 376.9 | 1921 | 3 |
| 80 | Sean Sherk | 374.2 | 1894 | 6 |
| 81 | Gegard Mousasi | 373.1 | 1922 | 5 |
| 82 | Joshua Van | 369.8 | 1962 | 3 |
| 83 | Shavkat Rakhmonov | 367.8 | 2138 | 2 |
| 84 | Phil Davis | 361.7 | 1958 | 4 |
| 85 | Anthony Johnson | 361.4 | 1945 | 6 |
| 86 | Sean O'Malley | 361.0 | 1956 | 4 |
| 87 | Chael Sonnen | 360.3 | 1752 | 3 |
| 88 | Tim Sylvia | 358.5 | 1678 | 2 |
| 89 | Demian Maia | 357.4 | 1855 | 7 |
| 90 | Sergio Pettis | 349.2 | 1828 | 3 |
| 91 | Donald Cerrone | 336.5 | 1851 | 5 |
| 92 | Hayato Sakurai | 334.4 |  |  |
| 93 | Beneil Dariush | 327.4 | 1848 | 6 |
| 94 | Ricardo Arona | 318.6 | 1829 | 4 |
| 95 | Jacare Souza | 318.6 | 1837 | 4 |
| 96 | Johnny Eblen | 313.3 | 2037 | 2 |
| 97 | Michael Bisping | 313.1 | 1828 | 3 |
| 98 | Jake Shields | 311.9 | 1824 | 7 |
| 99 | Ben Askren | 310.6 |  |  |
| 100 | Jiri Prochazka | 310.1 | 1930 | 4 |

<!-- BOARD:TOP100:END -->

### Prime, elite-tested — men, top 50

How good was the fighter at their best, counting only peaks they actually
proved? A fighter qualifies by beating at least **5 contenders inside one
ten-year stretch**, where a contender was rated **1750 or higher** at the time
of the bout *and* had a tested record of their own — at least 8 UFC bouts.

**Which ten years.** The stretch is the one holding the most wins over
contenders, not the one with the highest average rating. Choosing it by rating
picks the years a fighter lost least, because an unbeaten record is rated above
everyone in it — which made Daniel Cormier's peak his 13-0 Strikeforce run and
put his entire UFC title reign outside it, counting 2 qualifying wins where he
has 8. Mirko Filipovic scored none at all. A stretch is a peak because of who
was beaten in it. Both figures come from that one stretch, so a win can neither
certify a peak it falls outside nor be lost to a stretch picked on other
grounds.

**How the order is decided.** Not by the level alone. A level is a rate: it does
not rise with the number of hard fights behind it, so ranking it puts a fighter
who scraped past the minimum above one who cleared it many times over. The order
multiplies the two printed figures — how many contenders were beaten, by how far
the fighter's level stood above the weakest level on the board. A high peak
proved once and a good peak proved eleven times are different achievements. The
wins are never added to the rating; they scale how much of the level is
credited, so nothing is counted twice, and there is no tuning constant in it.

The contender line and the five-win minimum are stated policy, not fitted
values. 71 men qualify, so this top 50 fills. Only 2 women do, which is a fact
about how few women in the corpus have a long UFC record rather than about the
fighters — see [Published UFC Rankings](RANKINGS.md) for that board.

<!-- BOARD:ELITEPRIME50:BEGIN -->

| # | Fighter | Prime | Elite wins |
| ---: | --- | ---: | ---: |
| 1 | Jon Jones | 2213 | 12 |
| 2 | Islam Makhachev | 2195 | 9 |
| 3 | Georges St-Pierre | 2074 | 11 |
| 4 | Alexander Volkanovski | 2050 | 9 |
| 5 | Daniel Cormier | 2084 | 8 |
| 6 | Francis Ngannou | 2039 | 8 |
| 7 | Anderson Silva | 1923 | 11 |
| 8 | Kamaru Usman | 1967 | 9 |
| 9 | Max Holloway | 1962 | 9 |
| 10 | Lyoto Machida | 1978 | 8 |
| 11 | Merab Dvalishvili | 1975 | 8 |
| 12 | Ciryl Gane | 2058 | 6 |
| 13 | Ilia Topuria | 2118 | 5 |
| 14 | Dricus Du Plessis | 2043 | 6 |
| 15 | Israel Adesanya | 1934 | 9 |
| 16 | Jose Aldo | 1930 | 9 |
| 17 | Khamzat Chimaev | 2090 | 5 |
| 18 | Charles Oliveira | 1978 | 7 |
| 19 | Sean Strickland | 1918 | 9 |
| 20 | Vadim Nemkov | 2068 | 5 |
| 21 | Stipe Miocic | 2003 | 6 |
| 22 | Alex Pereira | 1962 | 7 |
| 23 | Justin Gaethje | 1993 | 6 |
| 24 | Aljamain Sterling | 1945 | 7 |
| 25 | Demetrious Johnson | 1975 | 6 |
| 26 | Fedor Emelianenko | 2017 | 5 |
| 27 | Robert Whittaker | 1900 | 8 |
| 28 | Petr Yan | 1953 | 6 |
| 29 | Frankie Edgar | 1893 | 8 |
| 30 | Anthony Johnson | 1945 | 6 |
| 31 | Nassourdine Imavov | 1938 | 6 |
| 32 | Ryan Bader | 1935 | 6 |
| 33 | Alexander Volkov | 1904 | 7 |
| 34 | Dustin Poirier | 1925 | 6 |
| 35 | Chris Weidman | 1871 | 8 |
| 36 | Benson Henderson | 1880 | 7 |
| 37 | Dominick Cruz | 1941 | 5 |
| 38 | Sean Sherk | 1894 | 6 |
| 39 | Gegard Mousasi | 1922 | 5 |
| 40 | Curtis Blaydes | 1910 | 5 |
| 41 | Demian Maia | 1855 | 7 |
| 42 | Belal Muhammad | 1898 | 5 |
| 43 | Yoel Romero | 1868 | 6 |
| 44 | Luke Rockhold | 1865 | 6 |
| 45 | Chuck Liddell | 1823 | 8 |
| 46 | Glover Teixeira | 1854 | 6 |
| 47 | Henry Cejudo | 1875 | 5 |
| 48 | Alexandre Pantoja | 1874 | 5 |
| 49 | Beneil Dariush | 1848 | 6 |
| 50 | Dan Henderson | 1870 | 5 |

<!-- BOARD:ELITEPRIME50:END -->

## How the ranking is governed

- One authoritative fight table supplies every model path. A bout may be
  available from several corpora, but it is rated once using the preferred
  parse while retaining its source membership.
- A fighter's level over time is estimated from their entire record at once,
  rather than updated fight by fight, and how a bout ended counts towards the
  result rather than only who won. Two simpler models are kept alongside as
  comparisons. The method is documented in
  [Rating Layer and Public Ledger](docs/RATING_LAYER_AND_LEDGER_2026-08-28.md).
- The all-time score is the published board. The career-skill diagnostic that
  feeds it must not be promoted in its place without a fresh top-100 audit; it
  ranks unbeaten records from thin circuits alongside title legends.
- Men and women are ranked separately. No fight evidence connects the two
  populations, so a combined order would be determined by the prior rather
  than observed competition.
- Fighters below the evidence threshold are withheld. An abstention is not a
  low score and is never converted into an arbitrary rank.
- Every published table and the release facts beside it are checked before
  either document is rewritten, so a release is never left half-updated.

## Data coverage

The current published scope combines canonical UFCStats history, recovered
pre-unified UFC bouts, and staged major-promotion history from Sherdog. The
bounded FightMatrix profile cohort is retained as diagnostic evidence and can
be selected explicitly; it is not silently merged into the published scope.

Every admitted bout is held once, in a single evidence table, together with a
record of which sources supplied it. Where two sources describe the same bout
the more authoritative one is used, but the other source's claim on it is kept.
That is what lets a narrower release be selected without silently losing bouts a
broader source also carried. Field-level detail is in the source matrix below.

Source ownership, licensing notes, and known coverage gaps are maintained in
[Source Matrix](data/SOURCE_MATRIX.md). Release history is maintained in
[Data Changelog](data/CHANGELOG.md).

## Important limitations

- The all-time score is retrospective. An opponent's quality is priced using
  everything now known about them, so it answers how good a win was rather than
  how good it looked at the time.
- The schedule component tracks how many ranked wins a fighter has and has no
  annual cap, so it rewards long careers. Read it as context, not as a fourth
  independent measure of skill.
- The exposure factor is a declared organization mapping. It helps compare
  partially observed careers but remains a policy assumption, not a quantity
  identified solely by bout outcomes.
- Division and identity are partly inferred where the sources are incomplete.
  Those inferences are audited, but they feed division-based context.
- Canonical UFC fight URLs distinguish legitimate same-night rematches.
  Non-UFC sources do not always provide an equivalent stable bout key, so an
  ambiguous same-day duplicate is conservatively collapsed.
- No model can recover fights absent from every admitted source. Coverage and
  identity exceptions therefore remain part of every release decision.

These are current boundaries, not invitations to repeat closed tuning loops.
The decision register in [Next Decisions](docs/NEXT_2026-08-28.md) records
options already tested or rejected.

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
| `data/model_tuning/` | Held-out comparisons and top-100 audit evidence |
| `docs/` | Current methodology, coverage, and decision records |
| `_archive/` | Recoverable historical research, retired code, and stale generated material |

## Current technical records

- [Rating Layer and Public Ledger](docs/RATING_LAYER_AND_LEDGER_2026-08-28.md)
  explains the production skill layer, Public Legacy components, and audit
  separation.
- [Career Coverage](docs/CAREER_COVERAGE_2026-08-27.md) documents source
  completeness and the authoritative whole-career coverage rule.
- [Next Decisions](docs/NEXT_2026-08-28.md) is the active handoff and decision
  register, including closed options that should not be re-run without new
  evidence.
- [Published UFC Rankings](RANKINGS.md) holds every generated table.

Historical design notes and retired experiments are preserved under
[`_archive/`](_archive/) with restoration instructions. They are evidence of
past work, not current operating guidance.
