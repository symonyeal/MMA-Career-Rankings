# Field-coverage matrix

Each field has exactly ONE authoritative source. Lower-priority sources may
only populate where the authority is null/absent, and every fallback is
logged. Loader merge step asserts: for every (fight_url, field) pair, at most
one source produced a non-null value.

Priority: **Greco** (UFC granular) > **FightMatrix/Sherdog** (public cross-org results)
        > **DataLab** (career / comparison) > **FightMatrix-derived metrics** (diagnostic only)
        > **mmadecoded** (tertiary fallback).

## 1. Event / fight identity

| Field            | Source         | Column / shape                              | Notes |
|------------------|----------------|---------------------------------------------|-------|
| fight_url (PK)   | Greco          | `ufc_fight_results.URL`                     | Stable canonical key. |
| event_url        | Greco          | `ufc_event_details.URL`                     | |
| event_name       | Greco          | `ufc_event_details.EVENT`                   | Whitespace-stripped. |
| event_date       | Greco          | `ufc_event_details.DATE`                    | Parsed `"%B %d, %Y"`. |
| event_location   | Greco          | `ufc_event_details.LOCATION`                | |
| bout_string      | Greco          | `ufc_fight_results.BOUT` (`"A vs. B"`)      | Split into `fighter_a`, `fighter_b`. |
| weight_class     | Greco          | `ufc_fight_results.WEIGHTCLASS`             | |
| is_title_fight   | Greco (derived)| `WEIGHTCLASS` contains "Title"              | |

## 2. Outcome & method

| Field                  | Source         | Source / shape                                 | Notes |
|------------------------|----------------|------------------------------------------------|-------|
| fighter_a_outcome      | Greco          | `OUTCOME` split (`W/L`, `L/W`, `D/D`, `NC/NC`) | One of `W`, `L`, `D`, `NC`. |
| fighter_b_outcome      | Greco          | same                                            | |
| winner, loser          | Greco (derived)| from outcomes                                   | Null for draws / NCs. |
| is_draw, is_nc         | Greco (derived)|                                                 | |
| method_raw             | Greco          | `METHOD` (e.g. `"KO/TKO "`, `"Decision - Split "`) | Whitespace-stripped. |
| method_class           | Greco (bucketed)| one of `KO/TKO`, `Submission`, `Decision - Unanimous/Majority/Split`, `DQ`, `Could Not Continue`, `Overturned`, `Other` | v1 lumps KO with TKO and KO-by-sub with regular Submission. |
| method_score_winner    | derived        | `{KO/TKO:1.00, Submission:1.00, Dec-U:0.95, Dec-M:0.90, Dec-S:0.90, DQ:0.85}` (see `METHOD_SCORES` in `loaders/ufcstats_loader.py`) | **The published WHR winner score since 2026-08-28** (`ratings.constants.WHR_WINNER_SCORE_COL`), measured before it shipped; also the μ_method diagnostic. NOT in μ_canonical. The values listed here were stale until 2026-08-28 — read `ratings/constants.py`, not this cell, if they ever disagree again. |
| end_round              | Greco          | `ROUND`                                         | |
| end_time_seconds       | Greco          | `TIME` (parsed `mm:ss`)                         | |
| time_format            | Greco          | `TIME FORMAT`                                   | e.g. `"3 Rnd (5-5-5)"`. |
| referee                | Greco          | `REFEREE`                                       | |
| details_text           | Greco          | `DETAILS`                                       | Holds judge scorecards as semi-structured string. |
| ped_confirmed          | Greco (derived)| regex over `DETAILS`                            | True only when fight-level text confirms failed drug test / anti-doping violation. |
| ped_flagged_fighter    | Greco (derived)| fighter named in `DETAILS`                      | Used only for the separate PED-adjusted rating. |
| ped_confirmation_source| Greco (derived)| `details_text`                                  | Audit source for the flag. |
| ped_confirmation_detail| Greco          | `DETAILS`                                       | Verbatim audit detail; exported to `ped_confirmed_bouts.csv`. |
| scorecards             | Greco (parsed) | regex over `DETAILS`                            | v2; mmadecoded fallback if parse fails. |
| bonus_perf_of_night    | mmadecoded     | scraped per-fight flag                          | v2. |
| bonus_fight_of_night   | mmadecoded     | scraped per-fight flag                          | v2. |
| open_odds_a, open_odds_b | mmadecoded   | decimal odds                                    | v2. |

## 3. Per-round granular stats (Greco only — sole source)

| Field                                       | Source | Column        | Parse                                |
|---------------------------------------------|--------|---------------|--------------------------------------|
| round_num                                   | Greco  | `ROUND`       | `"Round 3"` → 3.                     |
| fighter                                     | Greco  | `FIGHTER`     | Strip whitespace.                    |
| kd                                          | Greco  | `KD`          | int.                                 |
| sig_str_landed, sig_str_attempted           | Greco  | `SIG.STR.`    | `"5 of 11"` → (5, 11).               |
| sig_str_pct                                 | Greco  | `SIG.STR. %`  | `"52%"` → 52.                        |
| total_str_landed, total_str_attempted       | Greco  | `TOTAL STR.`  | "X of Y".                            |
| td_landed, td_attempted                     | Greco  | `TD`          | "X of Y".                            |
| td_pct                                      | Greco  | `TD %`        | "%".                                 |
| sub_att                                     | Greco  | `SUB.ATT`     | int.                                 |
| rev                                         | Greco  | `REV.`        | int.                                 |
| ctrl_seconds                                | Greco  | `CTRL`        | `"4:47"` → 287.                      |
| head_*, body_*, leg_*, distance_*, clinch_*, ground_* | Greco | by-target sig strikes | "X of Y" landed/attempted pairs. |

## 4. Fighter biographical

| Field            | Source         | Column                                | Parse |
|------------------|----------------|---------------------------------------|-------|
| fighter_url (PK) | Greco          | `ufc_fighter_details.URL`             | |
| first_name       | Greco          | `FIRST`                               | |
| last_name        | Greco          | `LAST`                                | |
| nickname         | Greco          | `NICKNAME`                            | empty → null. |
| height_inches    | Greco          | `ufc_fighter_tott.HEIGHT`             | `5' 11"` → 71. |
| weight_lb        | Greco          | `WEIGHT`                              | `"155 lbs."` → 155. |
| reach_inches     | Greco          | `REACH`                               | `70"` → 70.0. |
| stance           | Greco          | `STANCE`                              | empty → null. |
| dob              | Greco          | `DOB`                                 | `"Jul 03, 1983"` → date. |

## 5. Career-wide / cross-organization (not covered by Greco)

### Coverage is per fighter, and it has to be measured that way

Completeness here has two axes and only one of them was ever checked. Per
**promotion** the corpus is roster-complete inside the seven event-crawled
promotions and `majors_coverage.json` reports it. Per **fighter** it was not:
the whole-career expansion ran over the 4,501 fighters who had appeared on a
PRIDE / WEC / Strikeforce / Affliction / Bellator / RIZIN card, and not over the
UFCStats roster, so a fighter who reached the UFC through one of those
promotions had their whole regional record in the model and a fighter who did
not had almost none of it. Measured on 2026-08-13 over the 1,825 fighters with
three or more UFC bouts: **547 (30.0%) had a whole-career page, with a median
recorded pre-UFC record of 13 bouts against 1 for the other 1,278.**

That is a modelling defect, not a reporting one. A low-loss Bradley–Terry record
has no interior maximum, so the prior alone stops the climb and the equilibrium
sits near `opponent_level + 173.72·ln(2k/v)` — where `k` is how many of the
fighter's bouts the corpus happens to hold.

`build_sherdog_careers.py` completes the coverage and
`loaders/career_coverage.py` states it as a number that a build can assert on;
the majors staging writes `career_coverage.parquet` and warns when the share
falls below `MIN_CAREER_PAGE_SHARE`, and `rating_run.json` publishes it.
**When a completeness figure is quoted here, name the axis it was measured on.**

| Field                       | Source     | Notes |
|-----------------------------|------------|-------|
| majors_fights               | Sherdog    | `loaders/majors_scope.py` stages the preserved seven-promotion event crawl plus completed whole-career pages as canonical-shaped rows. A staged build input: every row is in `combined_fights`. |
| career_coverage             | Derived    | Per UFC fighter: UFC bouts, corpus bouts, recorded pre-UFC bouts, Sherdog id, and whether their whole-career page was read. |
| fightmatrix_profiles        | FightMatrix public profiles | Ranked-cohort biography, debut, career summary, and diagnostic metrics. |
| fightmatrix_bouts           | FightMatrix public profiles | Deduplicated complete histories for the bounded current-ranked + all-time seed cohort. |
| fightmatrix_crossorg_fights | FightMatrix public profiles | Post-2000-11-17, non-UFC, UFC-deduplicated canonical rows; public ranks are not model inputs. |
| fightmatrix_profile_queue | FightMatrix public profiles | Persistent profile-ID queue with depth, priority, fetch/parse state, retries and stop reason. |
| fightmatrix_profiles_expanded | FightMatrix public profiles | Recursively fetched public profiles with independent HTTP, parse, record-reconciliation and modeling-completeness state. |
| fightmatrix_bouts_expanded | FightMatrix public profiles | Per-profile public history rows retained before deterministic reciprocal reconciliation. |
| fightmatrix_model_eligible_bouts | FightMatrix public profiles | Experimental canonical rows after UFC overlap removal and the declared completeness policy. |
| combined_fights              | Derived from selected scope | One model-input table preserving the union of admitted source columns, with `bout_fingerprint`, `source_corpus`, `source_priority`, `rated_scope`, and `is_model_bout`. |
| method_raw / method_class   | Sherdog    | Parsed from fighter history pages for cross-org bouts. |
| end_round / end_time_seconds| Sherdog    | Parsed from fighter history pages for cross-org bouts. |
| is_title_fight              | Sherdog (derived) | Derived from event-title patterns for cross-org bouts. |
| org_weight                  | Production unit / audit candidates | Production writes 1.0 for every admitted bout. `build_org_strength_audit.py` can overwrite it for explicit sensitivity models; old FightMatrix participant-caliber weights are research-only because they use eventual UFC-career information. |
| datalab_bouts_all           | DataLab    | UFC-DataLab `stats_processed_all_bouts.csv`; staged in snapshot as parquet. |
| datalab_merged_stats_scorecards | DataLab | UFC-DataLab merged stats + scorecards export; staged in snapshot as parquet. |
| datalab_fighter_details     | DataLab    | UFC-DataLab fighter details export; staged in snapshot as parquet. |
| datalab_scorecards          | DataLab    | OCR parsed scorecard totals; staged in snapshot and SQLite for judge-decision analysis. |
| career_wins / losses / draws / ncs | DataLab | Pending derived career summary from staged DataLab bouts. |
| pro_debut_date              | DataLab    | Pending derived career summary. |
| organizations               | DataLab    | Pending; DataLab UFC export does not yet provide cross-org organizations. |
| pre_ufc_record_summary      | DataLab    | Pending derived summary from staged cross-org bouts plus future broader sources. |

## 6. Public FightMatrix ranked-cohort histories

| Field                | Source                      | Notes |
|----------------------|-----------------------------|-------|
| fight_key (PK)       | FightMatrix public profile | Event id + normalized participant pair. |
| opponent / result    | FightMatrix public profile | W/L/D/NC, opponent profile id and URL. |
| method / round       | FightMatrix public profile | Parsed into the canonical method buckets. |
| event / date / country | FightMatrix public profile | Event id, URL, name, date and flag code. |
| opponent pre-fight rank/division | FightMatrix derived | Stored for audit only; never enters rating input. |
| association / debut / record | FightMatrix public profile | Queryable profile context. |
| quality %, 540 metric, combat age | FightMatrix derived | Stored for comparison only; never enters rating input. |

### Recursive public-profile boundary

`loaders/fightmatrix_expansion.py` follows only public opponent links carrying a
stable numeric profile ID. It does not use authenticated endpoints, CIRRS, or a
proprietary database. The breadth-first queue is bounded by depth, total and
per-run profile counts, request count, wall clock, minimum priority, earliest
date, minimum professional record, organization tier, unresolved-profile rate,
graph closure, and weighted edge support. Cached HTML is always preferred.

The priority score is transparent: `2*log1p(seed referrers) + 2*(opponent beat
or drew with referrer) + organization tier signal + 1.5*(title bout) + ranked
opponent signal`. This score orders work; it is not a rating input.

Deduplicating a public bout against the canonical UFC table is a name problem,
not just a key problem. The overlap test scans a one-day window (public profiles
date some Asian cards a day later than the UFC source) and treats a name-order
permutation, a generational suffix, a token subset and a three-character
first-name prefix as the same fighter. Names that no rule can derive - a ring
name replacing a family name, a married name, a mononym - live in
`data/external/fightmatrix/name_aliases.csv`, which records the reason and the
number of shared event dates behind each pair. That file is project-owned and
separate from the vendored `data/external/aliases/fighter_aliases.csv`, whose
upstream attribution must stay intact.

`analysis/fightmatrix_graph.py` blocks FightMatrix rank, points, quality
percentage, 540 metric, combat age, and pre-fight rank from the model schema.
The committed organization rule table is time-aware and initially diagnostic;
it does not add promotion prestige bonuses. Reliability weighting multiplies
the existing participant-caliber fight weight by the geometric mean of the two
profile completeness scores. FightMatrix remains a named diagnostic scope and
is not part of the published `majors,pre_unified` default.

Current Sherdog staging: `build_sherdog_majors.py` produced the roster-complete
six-promotion event crawl, and the completed whole-career crawl is preserved as
`data/external/sherdog/crossorg_bouts.parquet`. `loaders/majors_scope.py`
resolves identities and writes snapshot-local `majors_fights.parquet`.
`ratings/scope.py` admits it only through the named `majors` scope. The
one-off whole-career ingest driver is preserved in
`_archive/20260825-superseded-research-drivers/build_crossorg_careers.py`.

`loaders/fightmatrix_loader.py` stages the ranking and all-time tables.
`loaders/fightmatrix_profiles.py` then follows only the profile links in those
tables (no recursive opponent crawl), caches the HTML under
`data/external/fightmatrix/profiles/`, and emits profile, raw-bout, canonical
cross-org, and provenance-summary artifacts. The 2026-08-14 local run contains
302 profiles, 6,644 unique public bouts and 4,023 model-ready cross-org bouts.
FightMatrix ranks, points, quality percentages, 540 metrics and combat age are
diagnostic only. Only result/method/round/event/date fields enter the optional
rating input. The standard snapshot uses `majors,pre_unified`; the explicit
`2026-08-13-fightmatrix-public` snapshot preserves the bounded-cohort run.

## 7. Local SQLite database

`build_database.py` builds `data/ufc_rank_engine.sqlite` from the snapshot
bundle. It is an organized local database for audit and notebook support; it is
not a separate source of truth. The obsolete 2026-08-14 export was archived on
2026-08-26 and no current SQLite export is claimed until that optional command
is run against the current snapshot. A current export may include:

- Canonical UFC tables: `canonical_events`, `canonical_fights`,
  `canonical_rounds`, `canonical_fighters`.
- Canonical extension tables: `crossorg_fights` when present.
- Rating and derived tables: `ratings_current`, `ratings_history`,
  `ratings_history_whr`, `integrity_appearances`, `performance_appearances`,
  `fight_dominance`, `fighter_dominance`.
- Policy/audit tables: `integrity_ledger`, `integrity_discounted_board`,
  `completeness_gated_board`, `excluded_bouts`, `ped_confirmed_bouts`,
  `missed_weight_bouts`.
- External staged tables: `datalab_bouts_all`,
  `datalab_merged_stats_scorecards`, `datalab_fighter_details`,
  `datalab_scorecards`, `fightmatrix_rankings`, `fightmatrix_all_time`,
  `fightmatrix_profiles`, `fightmatrix_bouts`,
  `fightmatrix_crossorg_fights`, `fightmatrix_scope_comparison`.
- Metadata tables: `source_manifest`, `snapshot_manifest`,
  `table_row_counts`, `source_gaps`.

SQLite indexes are created on fighter, event date, fight URL, event name, and
source-specific fighter/division fields where those columns exist.

## 8. Tertiary fallback (mmadecoded — populated only if higher-priority is null)

| Field | Source     | Match key                                  | Notes |
|-------|------------|--------------------------------------------|-------|
| any   | mmadecoded | `(event_date, fighter_a, fighter_b)`       | Logged to `data/snapshots/<date>/_fallbacks.log`. |

## Exclusion rules (rating engine drops these)

- `event_date < 2000-11-17` → pre-unified-rules era (UFC 1–27). Dropped from the canonical table, then re-admitted only by the named `pre_unified` rating scope.
- `method_class == "Overturned"` → drug-violation reversal or post-fight overturn.
- `method_class == "Could Not Continue"` → treated as NC for rating purposes.
- `is_nc` true → no contest.

All excluded bouts are persisted to `_excluded_bouts.csv` for audit.

## Rating and policy architecture (current through 2026-08-25)

The production engine exposes two estimators of the same binary W/L/D evidence,
plus one same-pass method research diagnostic:

| Stream/score | Role | Notes |
|---|---|---|
| `mu_canonical` | causal skill filter | Strict W/L/D Glicko-2. |
| `mu_whr` | retrospective skill smoother | Binary Whole-History Rating, one shared likelihood weight per bout, era-neutral. Prior mass is fixed per fighter (anchor + virtual games), so an undefeated record's rating rises with the evidence behind it. |
| `mu_method` | research diagnostic | Glicko-2 stream scored with `method_score_winner` in the canonical pass; not public/core evidence. The WHR smoother now reads the same column directly, so `mu_whr` is method-aware and this stream is no longer the only place method appears. |
| `public_legacy_score` | public All-time board | Exposure-adjusted skill plus per-opponent title resume. Components are published separately and sum exactly to the score. |
| `symon_career_skill_mass` | diagnostic career functional | Annual field-relative WHR skill mass. It is retained for audit and is not the public board. |
| `symon_prime_score` | period diagnostic | Fixed 10y/13-appearance EB-shrunk WHR mean. `symon_peak_score` is no longer produced by the rating snapshot. |
| `wins` / `losses` / `draws` | rated record | Counted from the rated fight table; the evidence behind a rating, not an input to it. |
| `career_mass_uncertainty.parquet` | rank intervals | Career mass and rank re-estimated under Dirichlet-reweighted events; overlapping intervals are not a ranking. |

Former `method_*_integrity`, `method_*_performance`, and
`whr_integrity_performance` production histories are retired. In particular,
WHR rejects different winner/loser weights for one bout because they cannot be
the gradient of one joint likelihood.

The rolling opponent-quality period columns (`sustained_peak_*`,
`five_year_peak_*`) were removed outright on 2026-08-20 rather than kept for
compatibility: they re-scored opponent quality, titles, activity and era on top
of a rating that already reflects them. A snapshot built before that date still
carries them; the public controls ignore them and resolve to base WHR instead.

### Integrity audit and direct-debit policy

Three authoritative signals are OR-merged into per-fight audit flags:

* PED-confirmed (from `loaders/ped_flags.py`): factor `0.80` (-20% floor —
  the most severe integrity penalty). Confirmed cases also exported to
  `ped_confirmed_bouts.csv`.
* DQ winner (Greco `method_class == "DQ"`): factor `0.92` (-8%).
* Missed-weight winner: factor `0.88` (-12%). Detected from Greco
  `details_text` ("missed weight" phrase + winner name) and, when
  available, mdabbert `R_Weight_lbs`/`B_Weight_lbs` vs `weight_class`
  divergence (cross-check). Audit export: `missed_weight_bouts.csv`.

The standard board builder writes the event ledger and an optional direct
rating-point debit against base WHR. It never propagates a policy penalty
through opponents and it does not subtract rating points from Career Skill
Mass, whose unit is rating-point-years.

### Retired performance-weight research table

`performance_appearances.parquet` preserves the former proposed weighting
features for audit and research; it is not consumed by a production rating.
The
2026-05-14 rewrite replaced the old multiplicative-product-and-clamp design
with a tanh-smoothed additive log-signal `S`:

* Each sub-factor contributes a signed log-delta capped at its own amplitude:
  decisiveness, opponent quality, opponent streak, rank-gated upset,
  weight-class movement, activity-aware post-layoff loss.
* Opponent-quality contributors (opponent `mu`, division-rank context,
  championship context, P4P context) are **deduplicated via `max`** — a
  champion who is also top-15 division and top-15 P4P does not triple-count.
* The upset factor is **rank-gated**: it fires only when
  `winner_rank - opponent_rank >= PERF_UPSET_RANK_GAP_THRESHOLD` (champion =
  rank 0, unranked = 16). A #3-vs-#4 bout never triggers it.
* Final weight: `winner = 1 + 0.20*tanh(S/PERF_TANH_SCALE)` and
  `loser = 1 - 0.20*tanh(S/PERF_TANH_SCALE)` — both extremes are soft
  saturations inside `[SLEEVE_FACTOR_MIN, SLEEVE_FACTOR_MAX]`, not hard
  clamps. Losers now carry the symmetric mirror weight (no longer a flat 1.0).
* Market odds do **not** contribute to any rating. `perf_factor_odds` and the
  rank-gated odds confirmation were removed on 2026-08-18: the former was never
  a term in `S`, and the latter moved `performance_weight` on 35 of 16,958
  appearance rows for a paired held-out log-loss effect of
  −1.4×10⁻⁶ [−3.2×10⁻⁶, +3.4×10⁻⁷], an interval spanning zero.
  `odds_lines.parquet` is retained as the benchmark the engine is scored
  against in `ratings/prequential.py`.

All sub-factor amplitudes live in `ratings/constants.py`; the per-factor
`perf_factor_*` columns in `performance_appearances.parquet` are retained for
audit. The derived signal no longer feeds a public/core rating.

### Optional odds artifact

Field map for `odds_lines.parquet` (one row per bout, joined back to
`canonical_fights` by `fight_url`):

| Field | Notes |
|-------|-------|
| fight_url | FK to canonical_fights.fight_url |
| event_date, event_name | Mirrors canonical_fights for human audit |
| fighter_a, fighter_b | Same names as canonical_fights |
| odds_source | Free-text source label ("fixture", "jasonchanhku-v1", etc.) |
| odds_fighter_a, odds_fighter_b | Fighter the price belongs to; must match fighter_a/_b |
| american_odds_a, american_odds_b | Float, nullable |
| decimal_odds_a, decimal_odds_b | Float, nullable |
| implied_prob_a_raw, implied_prob_b_raw | Raw implied (with vig), derived |
| implied_prob_a_no_vig, implied_prob_b_no_vig | Proportionally rescaled, sums to 1.0, derived |
| market_favorite, market_underdog | Fighter names, derived |
| market_favorite_prob, market_underdog_prob | Floats in (0, 1), derived |
| odds_data_quality | `ok` / `one_side_missing` / `missing` / `negative_vig` / `implausible` |

**Source coverage today: mdabbert "Ultimate UFC Dataset"** (Apache-2.0),
joined on `frozenset({fighter_a, fighter_b})` + event_date (±1 day),
covers ~78% of canonical bouts with American moneyline odds spanning
~2010-2026. Ingested by `loaders/odds_ingest_mdabbert.py`. The
odds artifact is used as a held-out benchmark and results analysis; it never
changes a rating. `rate_snapshot` prints realised coverage at end-of-run.

Loaded odds sources:

| Source | Format | Era | License | Current role |
|--------|--------|-----|---------|--------------|
| mdabbert `ultimate_ufc_dataset` — `ufc-master.csv` | CSV American moneyline | 2010-03-21 -> 2026-03-28 (~6,900 bouts with both-side odds) | Apache-2.0 (`F U N/ultimate_ufc_dataset-main/LICENSE`); attribution required, redistributable | Primary ingest backing `odds_lines.parquet` as an external benchmark. Joined via fighter-pair + date. |

**Candidate external sources (not ingested, not redistributed in this repo):**

The github sibling repos that surfaced this work both ultimately point at
the same public archives. The plan for broader ingestion is to scrape those
public archives directly, treating github seed lists as pointers and
cross-checks rather than primary sources.

| Source | Format | Era | License | Role in plan |
|--------|--------|-----|---------|--------------|
| BestFightOdds.com (event archive pages) | HTML, multi-book aggregate | UFC 28+ | Public web; respect robots.txt and ToS, local use only | **Primary real-odds source.** `wrcarpenter/MMA-Betting-Model/Data/odds-event-links.csv` is essentially the seed URL list for this scrape. |
| OddsPortal.com (UFC archive) | HTML, multi-book aggregate | UFC 28+ | Public web; same caveat | Cross-validation / fill-in for BestFightOdds gaps. |

Implementation path (deferred to a later phase, after engine wiring):
1. `loaders/odds_ingest_bestfightodds.py` — crawl one event page at a
   time using the seed URL list, polite rate limit, cache HTML under
   `data/external/odds/bestfightodds/html/`.
2. Parse to the raw schema documented above and emit
   `data/snapshots/<date>/odds_lines.parquet`.
3. Match each row back to `canonical_fights.fight_url` by normalized
   event name + fighter pair; rows that fail to match are logged.

All raw HTML caches and ingested CSVs stay project-local. Nothing gets
redistributed. Cross-org / pre-UFC odds remain entirely out of scope.

Both github candidates are recorded under `source_gaps` until ingested.
