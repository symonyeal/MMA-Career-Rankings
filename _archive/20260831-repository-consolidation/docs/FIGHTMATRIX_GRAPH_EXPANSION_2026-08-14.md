# FightMatrix public graph expansion — 2026-08-14 snapshot

Report completed 2026-08-18 against the `2026-08-14` crawl.

> **Historical experimental record.** The promotion decision below was correct
> for 2026-08-18, but it predates the later Sherdog `majors,pre_unified`
> published scope. The FightMatrix crawl remains unpromoted. Reproduction
> drivers were closed and preserved under
> `_archive/20260825-superseded-research-drivers/`.

## Summary

The depth-one crawl completed: 4,337 of 4,337 fetch-eligible public profiles
fetched, parsed and reconciled, with no failures. The defect this work was
commissioned to fix is measured and closed at depth one - **mean seed opponent
coverage rose from 10.2% to 100%**, and 81 of 302 seeds that previously had no
covered opponents at all now have complete ones.

That did not translate into a materially better ranking. On the only fair
comparison - 31 fighters shared by every scope and the public reference,
re-ranked inside that subset - rank correlation moves 0.7226 to 0.7238 and mean
rank error 5.23 to 5.16. The named anomalies improve substantially (Nogueira 192
to 70, Fedor unrated to 66) without approaching the reference, and the residual
gap is now traceable to the cross-organization fight weight rather than to
missing opponent history.

**This work remains experimental. The UFC-only `2026-08-13` snapshot is still
the production default and `data/ufc_rank_engine.sqlite` was not rebuilt.** More
fights are not sufficient evidence for promotion. The full reasoning is in
"Promotion decision" below.

Three findings are worth reading even if nothing is promoted: admitting
incomplete opponents (`raw`) makes the model measurably *worse* than the
UFC-only baseline; most of the apparent rating regressions are a cohort-size
artifact rather than lost rating; and two of them are genuine, correct, and
explained bout by bout.

## Initial audit

The 302 ranked seed profiles expose 4,337 stable public profile IDs: 302 fetched
seeds and 4,035 direct depth-one opponents. Before expansion, profile coverage
and graph closure are both 6.96%. Reconciliation of the existing cache found
297 seed profiles whose W/L/D/NC history agrees with the stated public record
and five conflicts requiring review. HTTP success alone is never called
complete.

The old `fightmatrix_bouts.parquet` contains one selected perspective per bout.
The recursive pipeline instead retains new per-profile perspectives before
classifying reciprocal records, exact/likely duplicates, conflicts, and UFC
source overlaps. Conflicts are excluded rather than silently resolved.

The UFC-overlap test is deliberately wider than an exact key match, because a
first implementation left real UFC bouts in the cross-organization input and so
double-counted them against the canonical UFC table. Two failure modes were
measured on the live cache: public profiles date an Asian card one day away from
the UFC source (Hunt versus Kongo, UFC 144, is 2012-02-25 in the UFC data and
2012-02-26 publicly), and the two sources spell the same fighter differently
(`Tank Abbott` / `David Abbott`, `Tsuyoshi Kosaka` / `Tsuyoshi Kohsaka`,
`Manny` / `Manvel Gamburyan`, `Antonio Rogerio Nogueira` / `Rogerio Nogueira`).
The matcher therefore scans a one-day window and requires one fighter to match
strictly before accepting a family-name variant on the other side; a bout where
neither side matches strictly is never merged.

A strict match is identical names, a token subset, a three-character first-name
prefix, a name-order permutation, or a generational suffix, with hyphens treated
as punctuation rather than name boundaries. That last rule is not cosmetic: the
public source writes `Georges St. Pierre` where the UFC source writes
`Georges St-Pierre`, and without it every one of his UFC bouts was admitted a
second time as a cross-organization edge. The permutation rule
matters more than it sounds: public sources render Chinese names given-name
first and the UFC source renders them family-name first, so `Jingliang Li` and
`Li Jingliang` are one fighter, as are `Weili Zhang` / `Zhang Weili` and
`Shayilan Nuerdanbieke` / `Nuerdanbieke Shayilan`.

What no rule can derive from the strings is a name that is simply different: a
ring name replacing a family name (`Renato Carneiro` is `Renato Moicano`,
`Patricio Freire` is `Patricio Pitbull`), a married name, or a mononym. Those
are recorded by hand in `data/external/fightmatrix/name_aliases.csv` with the
number of shared event dates that evidenced each pair, and each one is covered
by a regression test. The table was built by listing every bout where one
fighter matched the UFC source strictly on the same day and the other did not,
then keeping only pairs evidenced by more than one event - single-event
coincidences are two different fighters on the same card, not an alias.

Mirko Cro Cop is worth naming because it is the case this design would *not*
solve: a nickname that replaces the family name is exactly what the rules
refuse to guess. He needs no entry here only because both sources happen to
spell him `Mirko Filipovic`.

## Identity and provenance

Numeric FightMatrix profile IDs are primary identities. Unicode, punctuation,
quoted nicknames, suffixes and the committed alias table support matching, but
unique name-only UFC matches have confidence 0.95 and remain visible as
exceptions. Ambiguous normalized names never merge without a committed manual
override in `data/external/fightmatrix/identity_overrides.csv`.

Every fetched or reused page records URL, timestamp, HTTP status, SHA-256,
parser version, snapshot, profile ID, depth, referrer, cache path, parse warning,
TLS state and cache-hit state. Generated snapshots and HTML caches remain
ignored by Git.

## Completeness definitions

- **Profile coverage:** parsed profile IDs / discovered stable profile IDs.
- **Bout reconciliation:** stated W/L/D and any explicitly stated NC are checked
  against parsed outcome rows. Unstated NC rows do not make an otherwise exact
  W/L/D reconciliation fail.
- **Opponent coverage:** parsed unique opponent profile IDs / all unique stable
  opponent IDs for a fighter.
- **Weighted opponent coverage:** the same ratio weighted by result, title,
  organization tier and published pre-fight-rank context. Rank context is used
  only for crawl/audit importance, never as a rating feature.
- **Edge support:** model-ready edges whose two endpoints each have completeness
  score at least 0.8 / all model-ready edges.
- **Graph closure:** parsed profiles / discovered queue profiles.

Completeness states are `complete`, `partial`, `conflicting`, `unresolved`, and
`failed`. Fetch status, parse status, record reconciliation and modeling
eligibility are stored independently.

## Expansion and stopping rules

The crawler is breadth-first and cache-first. Its configurable limits cover
maximum depth, total profiles, new profiles per run, requests, wall clock,
minimum priority, earliest fight date, minimum professional bouts, maximum
organization tier, unresolved percentage, target graph closure, and target
weighted edge support. Reaching a limit is a successful checkpoint, not a
failure.

The depth-one run uses a 5,000-profile ceiling, 4,035 new-profile ceiling,
one-second pacing, three retries with exponential HTTP backoff, and verified TLS
by default. The Yukon managed network presents a self-signed interception
certificate; any explicit `--insecure` retry is recorded as
`tls_verification=false` and does not change the secure default.

## Modeling policies

Five implemented bout policies can be compared without individual-fighter bonuses:

1. `raw` is an intentionally unsafe sensitivity scope with no completeness adjustment.
2. `complete_edge` admits only edges whose endpoints clear a completeness bar.
3. `reliability` weights an edge by the geometric mean of endpoint completeness.
4. `boundary` retains incomplete boundary nodes with reduced weight and higher
   initial-uncertainty metadata.
5. `burn_in` requires complete endpoints or a configurable number of earlier
   appearances.

The generated table also supports seed-only publication, component-size
eligibility and uncertainty-based suppression as reporting filters. These do not
feed FightMatrix reference values into the rating engine.

## Comparing scopes of different sizes

Each scope rates a different number of fighters, because the headline score
requires a sustained peak and more cross-organization history lets more careers
qualify. UFC-only rates 354 men; the depth-one scopes rate over 700. An integer
rank is therefore not comparable across scopes: a fighter can hold a *worse*
rank number in a scope that rates him *better* relative to the field.

Two cohort-independent measures are reported next to the raw rank. The first is
the percentile, `rank / cohort size`. The second re-ranks every scope inside the
set of fighters that all scopes and the public reference share, so no scope is
rewarded or punished for the size of its board. The anomaly summary uses the
percentile to separate a real rating loss from cohort growth, and labels the
latter `cohort_growth_artifact` rather than calling it a regression.

## Validation protocol

The validation builder compares UFC-only, the old 302-seed cohort, depth one,
and any later priority/deeper or stricter-policy snapshots. It reports graph
closure, weighted edge support, connectedness, rating stability, external-rank
correlation and errors, top-30 churn, the required historical panel, and
per-bout anomaly traces. Movement toward FightMatrix is not automatically an
improvement; each trace labels incomplete-history exposure, identity uncertainty
or new fight-result evidence.

## Crawl result

The depth-one crawl completed. Every fetch-eligible profile was retrieved,
parsed and reconciled:

| Depth | Discovered | Fetched and parsed | Stop reason |
| --- | --- | --- | --- |
| 0 (ranked seeds) | 302 | 302 | seed cohort |
| 1 (direct opponents) | 4,035 | 4,035 | queue exhausted |
| 2 (opponents of opponents) | 26,944 | 0 | `maximum_depth` |
| total | 31,281 | 4,337 | |

Crawl limits used: maximum depth 1, 5,000 total profiles, 5,000 new profiles and
5,000 requests per run, a three-hour wall clock, one request per second, three
retries with exponential backoff, earliest accepted fight date 1990-01-01,
minimum one professional bout, maximum organization tier 4. No limit bound the
run; it ended on `queue_exhausted`. The local cache holds 4,337 profile pages at
823 MB and is excluded from Git.

Of the 4,337 parsed profiles, 4,226 reconcile exactly against the public stated
record, 77 are partial, and 34 conflict. Nothing failed to fetch or parse. Four
profiles hit the retry limit on the first attempt with
`CERTIFICATE_VERIFY_FAILED` against the managed network's interception
certificate; those retries were re-run with an explicit `--insecure` opt-in that
is recorded as `tls_verification=false` on every affected provenance row. The
secure default was not changed.

Depth two is discovered but deliberately unfetched. Reporting closure against
only the fetch-eligible set would have overstated it, so the queue records all
26,944 boundary identities with stop reason `maximum_depth` and closure is
measured against the full discovered set.

## The reported defect, measured

The task's premise was that seed fighters have complete histories and their
opponents do not. That is measurable, and it was true:

| Seed opponent coverage | Before | After |
| --- | --- | --- |
| mean | 10.2% | 100.0% |
| median | 7.1% | 100.0% |
| seeds with zero covered opponents | 81 of 302 | 0 |
| weighted mean (result, title, organization tier) | - | 100.0% |

Before expansion a seed's opponent counted as "covered" only when that opponent
happened to be another seed. After the depth-one crawl every opponent of every
seed has a fetched, parsed profile. Fedor Emelianenko's 23 post-cutoff opponents,
Wanderlei Silva's 32 and Dan Henderson's 32 are all covered.

The bias did not disappear; it moved outward by one hop. Depth-one fighters now
carry the low coverage the seeds used to have - Zach Makovsky sits at 8 of 26
opponents covered - and that is exactly what the depth-two boundary in the queue
represents. Graph closure is honest about this: 4,337 of 31,281 discovered
identities are parsed, 13.9%, against 7.0% before the crawl.

## Identity

FightMatrix numeric profile IDs are the primary identity for all 31,281
discovered fighters, so profile-ID coverage inside the public graph is 100% and
no expansion followed a link without a stable ID.

The bridge to the UFC dataset is weaker, and the report should not pretend
otherwise. The canonical UFC data carries no FightMatrix IDs, so every
cross-source link is a name match: 3,590 identities matched a UFC fighter by
unique normalized name at confidence 0.95, and 27,691 have no UFC match. The
exceptions artifact carries 31,879 rows - 26,944 unresolved boundary opponents,
3,590 name-only matches held open for review, 819 unmatched UFC fighters, 426
duplicate normalized names and 100 ambiguous UFC matches. No two fighters were
merged on a normalized name alone; ambiguity requires a committed override in
`data/external/fightmatrix/identity_overrides.csv`, and none were needed.

## Reconciliation

The 4,337 profiles yield 80,667 per-profile bout perspectives covering 65,846
distinct bouts. Every perspective is classified and the decision is written to
`fightmatrix_bout_reconciliation.parquet`:

| Class | Perspective rows |
| --- | --- |
| unique | 48,105 |
| reciprocal profile records | 20,622 |
| UFC source overlap | 11,930 |
| exact duplicate | 6 |
| conflicting records | 4 |

The four conflicting records are perspectives that disagree about who won. They
are excluded from model input and both raw rows are preserved, because choosing
one silently is exactly what the task forbids.

The UFC-overlap class deserves the detail, because getting it wrong is what
double-counts a fighter's UFC career as cross-organization evidence. It now
removes 11,930 perspective rows covering 7,426 distinct canonical UFC bouts of
8,479. Two rounds of correction were needed:

| Matcher | UFC rows still admitted (complete-edge) |
| --- | --- |
| exact date and exact names | 458 |
| one-day window, name variants, committed aliases | 116 |
| plus hyphen treated as punctuation | 81 |

The last step is the one that mattered most. Reconciliation runs on raw public
names, and the public source writes `Georges St. Pierre` where the UFC source
writes `Georges St-Pierre`; until hyphens were folded, all 35 of his UFC bouts
re-entered the model as cross-organization edges. He is on the required
validation panel, so this defect alone would have made the panel unreliable.

The 81 that remain are not duplicates, and the distinction matters: the
canonical UFC table holds no matching bout for any of them.

- 43 are results overturned to no contest - Parisyan vs Kim, Oliveira vs Lentz,
  Davis vs Prado, Shields vs Herman, Miller vs Healy - which the canonical UFC
  dataset does not carry at all.
- 3 are not UFC events. FightMatrix files `UFR 5`, `RUFF 5` and `RUFF 12` under
  its own `UFC` organization code, along with `UFC 4 - Underground Fight Club`
  and `CFM - Ultimate Fighting Mexico`.
- The rest are developmental cards such as `Road to UFC` and scattered
  preliminary bouts absent from the canonical source.

That residual is 81 rows in 9,925 admitted edges, 0.8%, and it is additive
rather than duplicated.

Two further exclusion stages run after reconciliation: 1,826 bouts fall before
the 2000-11-17 model cutoff, which is the first date the canonical UFC dataset
covers, and 46,666 are excluded by the reliability completeness policy.

## Organizations

The committed rule table resolves 23,046 of 65,844 reconciled public bouts to a named
promotion. The largest are UFC 7,792, Major Regional 3,576, Bellator 1,994,
ACA 1,484, Shooto 1,412, PFL 1,033, M-1 869, Pancrase 779, PRIDE 753, ONE 571,
RIZIN 486, KSW 442, Invicta 359, Rings 349, Cage Warriors 339, Strikeforce 328,
WEC 285, DREAM 177 and Affliction 18.

The remaining 42,798 bouts, 65%, stay `Unknown`, and that number should not be
read as a defect to be tuned away. Those bouts carry 5,830 distinct raw labels,
about seven bouts each, and the labels are mostly bare abbreviations whose
expansion is genuinely ambiguous: `JF`, `EC`, `EFC`, `FFC`, `CW`, `SF`, `SFC`,
`CFC`, `TFC`, `LFC`, `GFC`, `WFC`, `IFC`, `MF`, `NFC`, `OC`, `GC`, `FF`. Several
of those initialisms belong to more than one promotion. Guessing them would
manufacture confidence, so the rule table leaves them unresolved at tier 4 and
the count is reported.

This costs the rating model nothing, and that is the important part. Fight
weight comes from `compute_fight_weights`, which is a bridge on the two
*participants'* UFC-anchored caliber percentiles - not from the promotion label.
Organization tier is used only for crawl priority and for weighting the opponent
coverage statistic. An unresolved promotion therefore changes no rating.

Two labels are wrong in the source rather than in the rule table: FightMatrix
files `UFC 4 - Underground Fight Club` and `CFM - Ultimate Fighting Mexico`
under its own `UFC` organization code. They are not UFC events. They survive as
two rows and are noted rather than special-cased.

## Scope comparison

Five rating scopes were built. Cohort size differs by scope because the headline
score needs a sustained peak, and more cross-organization history lets more
careers qualify, so the common-subset rows are the ones that compare fairly.

| | UFC-only | 302-seed | depth-1 raw | depth-1 complete-edge | depth-1 reliability |
| --- | --- | --- | --- | --- | --- |
| profiles | 0 | 0 | 4,337 | 4,337 | 4,337 |
| rated fighters | 354 | 477 | 2,587 | 696 | 697 |
| model-ready bouts | 8,479 | 12,502 | 65,070 | 18,394 | 18,404 |
| graph closure | - | - | 13.9% | 13.9% | 13.9% |
| weighted edge support | - | - | 26.3% | 26.3% | 26.3% |
| rating stability vs UFC-only | 1.000 | 0.984 | 0.936 | 0.964 | 0.964 |
| common-subset Spearman | 0.7226 | 0.7190 | 0.7000 | 0.7238 | 0.7238 |
| common-subset mean rank error | 5.226 | 5.161 | 5.484 | 5.161 | 5.161 |
| top-30 churn vs UFC-only | 0 | 0 | 2 | 1 | 1 |
| runtime | - | - | 14,041 s | 2,925 s | 2,922 s |

The common-subset row is the honest headline, and it is a small number. Measured
on the 31 fighters every scope shares with the public reference, re-ranked
inside that subset so no scope is rewarded for a longer board, depth-one
reliability moves rank correlation from 0.7226 to 0.7238 and mean rank error
from 5.23 to 5.16. That is a marginal improvement, not a breakthrough.

Two other results matter more than that number.

**The completeness policy is doing real work.** `raw`, which admits all 56,591
edges including those whose opponent has no fetched history at all, is worse
than the UFC-only baseline on every comparable measure: correlation 0.700
against 0.7226, mean rank error 5.48 against 5.23, and the weakest rating
stability at 0.936. It also inflates the board to 2,587 fighters, most of them
one-edge boundary nodes. Admitting incomplete opponents does not merely add
noise, it actively degrades the ordering. That is the experimental confirmation
that the policy layer is load-bearing rather than decorative.

**`complete_edge` and `reliability` are near-identical**, at 9,915 and 9,925
admitted edges. That is not a coincidence and it should be stated plainly:
completeness at depth one is bimodal. 4,226 of 4,337 fetched profiles reconcile
exactly and score 1.0, and everything past the crawl boundary scores 0.0, so the
geometric-mean weighting in `reliability` has almost nothing to interpolate
between. The two policies differ by ten edges. Reliability is recommended over
complete-edge on design grounds - it degrades gracefully if a later run has a
fatter partial-completeness middle - not because this snapshot distinguishes
them.

## Historical panel

Ranks are not comparable across scopes; percentiles are. Both are shown,
UFC-only against the recommended depth-one reliability scope.

| Fighter | UFC-only | reliability | UFC-only %ile | reliability %ile | FM ref |
| --- | --- | --- | --- | --- | --- |
| Georges St-Pierre | 2 | 2 | 0.6 | 0.3 | 1 |
| Jon Jones | 1 | 1 | 0.3 | 0.1 | 2 |
| Anderson Silva | 4 | 8 | 1.1 | 1.1 | 6 |
| Jose Aldo | 9 | 11 | 2.5 | 1.6 | 3 |
| Demetrious Johnson | 5 | 5 | 1.4 | 0.7 | 10 |
| Fedor Emelianenko | unrated | 66 | - | 9.5 | 4 |
| Antonio Rodrigo Nogueira | 192 | 70 | 54.2 | 10.0 | 18 |
| Wanderlei Silva | unrated | 286 | - | 41.0 | 32 |
| Dan Henderson | 126 | 137 | 35.6 | 19.7 | 16 |
| Urijah Faber | 82 | 75 | 23.2 | 10.8 | 19 |
| Eddie Alvarez | unrated | 118 | - | 16.9 | 23 |
| BJ Penn | 17 | 15 | 4.8 | 2.2 | 11 |
| Matt Hughes | 18 | 17 | 5.1 | 2.4 | 7 |
| Chuck Liddell | 36 | 36 | 10.2 | 5.2 | 31 |
| Randy Couture | 16 | 19 | 4.5 | 2.7 | 21 |
| Dominick Cruz | unrated | 28 | - | 4.0 | 26 |
| Frankie Edgar | 26 | 25 | 7.3 | 3.6 | 20 |
| Lyoto Machida | 46 | 42 | 13.0 | 6.0 | 24 |
| Khabib Nurmagomedov | 15 | 16 | 4.2 | 2.3 | 13 |
| Daniel Cormier | 7 | 6 | 2.0 | 0.9 | 14 |

Four of the twenty cannot be ranked at all by the UFC-only baseline. Fedor never
fought in the UFC; Wanderlei Silva, Eddie Alvarez and Dominick Cruz have too few
UFC rating periods to earn a sustained peak. Producing a defensible rank for
them is the clearest thing the expanded graph buys, and it is a capability the
baseline lacks rather than an accuracy gain. Across the whole board, 343 of the
697 rated fighters are newly rateable.

Every panel fighter improves on percentile. Nogueira is the largest single
movement on the board: rank 192 to 70, percentile 54.2 to 10.0, on 25 added
bouts that went 21-3-1 against opponents who are now fully covered.

The anomalies named in the brief improved but did not close:

| Fighter | Before (302-seed) | After (depth-1) | FM reference |
| --- | --- | --- | --- |
| Fedor Emelianenko | 105 | 66 | 4 |
| Antonio Rodrigo Nogueira | 108 | 70 | 18 |
| Wanderlei Silva | 263 | 286 (percentile 55.1 to 41.0) | 32 |
| Dan Henderson | 141 | 137 | 16 |
| Eddie Alvarez | 123 | 118 | 23 |
| Urijah Faber | 90 | 75 | 19 |
| Lyoto Machida | 50 | 42 | 24 |
| Chuck Liddell | 44 | 36 | 31 |

## Why the gap to the reference does not close

This is the central finding, and it changes what the remaining gap means.

Fedor's opponent coverage is now 100%: all 23 of his post-cutoff opponents have
fetched, parsed, reconciled histories, and 95% of his 44 added bouts are against
opponents scoring 1.0 on completeness. Missing-opponent bias no longer explains
his rank. He sits at 66 rather than 4 because his 36 added wins carry a mean
model weight of 0.660, not 1.0.

That weight is not a completeness penalty and not an organization prestige
judgment. `compute_fight_weights` sets a bout's weight from the percentile of
its two participants' UFC-anchored ratings, so a career built outside the UFC is
bridged through whichever opponents did reach the UFC. It is a deliberate,
pre-existing design choice in this model: non-UFC results count, but they count
less.

The residual disagreement with FightMatrix is therefore a *modeling* difference,
not a data gap. Closing it would mean raising cross-organization weight, which
is a separate decision that must be argued on its own evidence rather than
smuggled in under a data-completeness change. The brief is explicit that moving
toward the reference is not itself proof of improvement, and this is precisely
that case.

## Anomaly traces

Every fighter in the "unexpectedly lost rating" panel was traced bout by bout.
On raw rank all six look worse. On percentile five of six improved, because the
rated board grows from 354 to 697 and an integer rank inflates mechanically:

| Fighter | Rank before | Rank after | %ile before | %ile after | Cause |
| --- | --- | --- | --- | --- | --- |
| Joseph Benavidez | 55 | 93 | 15.5 | 13.3 | cohort growth |
| Andrei Arlovski | 53 | 73 | 15.0 | 10.5 | cohort growth |
| Forrest Griffin | 107 | 195 | 30.2 | 28.0 | cohort growth |
| Rich Franklin | 37 | 52 | 10.5 | 7.5 | cohort growth |
| Raphael Assuncao | 116 | 297 | 32.8 | 42.6 | new evidence |
| Mark Hunt | 176 | 453 | 49.7 | 65.0 | new evidence |

The two genuine regressions are correct, and the traces say why.

**Mark Hunt** gains 10 bouts, 3-6-1, every opponent fully reconciled, mean model
weight 0.790. They are his real PRIDE and DREAM years: losses to Yoshida,
Barnett, Fedor, Overeem, Manhoef and Mousasi, wins over Wanderlei Silva, Mirko
Filipovic and Kosaka. He went 2-6 across 2006-2009 and the model now knows it.
The UFC-only baseline flattered him by omitting that stretch.

**Raphael Assuncao** gains 6 bouts, 3-3, but the split is asymmetric: the losses
are to Urijah Faber (rated 1960 at the time) and Diego Nunes in the WEC, while
the wins are over regional opponents rated 1215, 1236 and 1380. Three wins over
weak opposition do not offset two losses to strong opposition.

Neither is cohort dilution, missing opponent history, identity failure, or a
model defect. Both are the model correctly absorbing losing records the UFC-only
view could not see.

The largest rank regressions overall are all bottom-of-board fighters - Mac
Danzig 348 to 682, Alessio Sakara 346 to 679 - whose percentile is flat or
improved. That is the cohort effect and nothing else.

## Leakage controls

FightMatrix rank, points, quality percentage, the 540 metric, combat age and
pre-fight rank are blocked from model input by `assert_no_reference_leakage`,
which fails closed and is asserted on every generated model frame. A regression
test fails if any such column reaches the model schema.

Published rank is used in exactly two diagnostic places, both documented: the
crawl priority score, and the importance weight inside the opponent-coverage
statistic. Neither reaches the rating engine, and neither is a rating feature.

The sampling bias is stated rather than hidden. The 302 seeds are drawn from
FightMatrix current and all-time rankings, so this graph is a ranked-cohort
neighbourhood, not a random sample of professional MMA. Fighters who never
appeared near those rankings are systematically absent, and the depth-two
boundary inherits that shape. No hyperparameter was tuned against the reference
in this work.

## Promotion decision

**The expanded scope stays experimental. The UFC-only `2026-08-13` snapshot
remains the production default, and `data/ufc_rank_engine.sqlite` was not
rebuilt.**

Promotion was not earned, and the reasoning should be explicit rather than
hedged:

1. Reference agreement is essentially unchanged on the only fair comparison.
   Spearman 0.7226 to 0.7238 and mean rank error 5.23 to 5.16 are inside the
   noise of a 31-fighter panel.
2. The anomalies the brief named improved substantially but remain far from the
   reference, and the residual is now known to be the cross-organization weight
   rather than missing data. That is a modeling argument nobody has made yet.
3. Graph closure is 13.9%. The depth-two boundary - 26,944 discovered profiles -
   is the new frontier, and depth-one fighters now carry the incompleteness the
   seeds used to.

What the work does earn is narrower and real: the missing-opponent bias the
brief describes is measured and eliminated at depth one, 343 fighters become
rateable who were not, every modeled cross-organization bout carries provenance
and a reconciliation decision, and the policy comparison shows that admitting
incomplete opponents makes the model worse rather than better.

## Limitations

- **Depth two is unfetched.** 26,944 discovered identities are recorded with
  stop reason `maximum_depth`. Closure is 13.9% against the full discovered set,
  100% against the fetch-eligible set, and the report uses the former.
- **The cohort is a ranked-cohort neighbourhood**, not a sample of the sport.
- **65% of bouts have no resolved organization.** 5,830 raw labels are ambiguous
  abbreviations. Tier is diagnostic only, so no rating depends on it.
- **81 UFC-labelled rows survive deduplication**, 0.8% of admitted edges. They
  are additive rather than duplicated: 43 are overturned no-contests absent from
  the canonical UFC table, 3 are non-UFC promotions FightMatrix files under its
  own `UFC` code, and the rest are developmental cards.
- **The UFC-to-FightMatrix bridge is name-based.** The canonical UFC data carries
  no FightMatrix IDs, so all 3,590 cross-source links are name matches at
  confidence 0.95, held open as exceptions. 819 UFC fighters are unmatched.
- **34 profiles have conflicting stated records** and 4 bouts have contradictory
  winner perspectives; all are excluded from model input and preserved raw.
- **`reliability` and `complete_edge` are not distinguished by this data.**
- **Fetches used `--insecure`** for four profiles behind a TLS-intercepting
  managed network, recorded as `tls_verification=false` in provenance.

## Reproducing each scope

Every command is in `README.md`. In order: the audit and crawl into the working
directory; one `--stage-rating-snapshot --run-ratings` invocation per policy;
`_archive/20260825-superseded-research-drivers/build_fightmatrix_validation.py`
across all five scopes; and
`build_database.py` against the recommended snapshot with an explicit
`--db-path`, which is what keeps the production database out of the experiment.

