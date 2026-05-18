# Field-coverage matrix

Each field has exactly ONE authoritative source. Lower-priority sources may
only populate where the authority is null/absent, and every fallback is
logged. Loader merge step asserts: for every (fight_url, field) pair, at most
one source produced a non-null value.

Priority: **Greco** (UFC granular) > **DataLab** (career / cross-org)
        > **FightMatrix** (pre-UFC bouts) > **mmadecoded** (tertiary fallback).

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
| method_score_winner    | derived        | `{KO/TKO:1.00, Submission:1.00, Dec-U:0.985, Dec-M:0.98, Dec-S:0.975, DQ:0.95}` (see `METHOD_SCORES` in `loaders/ufcstats_loader.py`) | Used in μ_method only — NOT in μ_canonical. Finishes sit at the 1.0 cap; decisions are a hair below. |
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

| Field                       | Source     | Notes |
|-----------------------------|------------|-------|
| datalab_bouts_all           | DataLab    | UFC-DataLab `stats_processed_all_bouts.csv`; staged in snapshot as parquet. |
| datalab_merged_stats_scorecards | DataLab | UFC-DataLab merged stats + scorecards export; staged in snapshot as parquet. |
| datalab_fighter_details     | DataLab    | UFC-DataLab fighter details export; staged in snapshot as parquet. |
| datalab_scorecards          | DataLab    | OCR parsed scorecard totals; staged in snapshot and SQLite for judge-decision analysis. |
| career_wins / losses / draws / ncs | DataLab | Pending derived career summary from staged DataLab bouts. |
| pro_debut_date              | DataLab    | Pending derived career summary. |
| organizations               | DataLab    | Pending; DataLab UFC export does not yet provide cross-org organizations. |
| pre_ufc_record_summary      | DataLab    | Pending; requires FightMatrix/cross-org bout merge. |

## 6. Pre-UFC bouts (per-bout, for Glicko seeding)

| Field                | Source                      | Notes |
|----------------------|-----------------------------|-------|
| pre_ufc_bout_id (PK) | FightMatrix (HTML scrape)   | Only attempted under free-data; give up + notify if blocked. |
| pre_ufc_opponent     | FightMatrix                 | |
| pre_ufc_result       | FightMatrix                 | W/L/D/NC. |
| pre_ufc_method       | FightMatrix                 | |
| pre_ufc_date         | FightMatrix                 | |
| pre_ufc_organization | FightMatrix                 | |

Current FightMatrix staging: `loaders/fightmatrix_loader.py` fetches public
FightMatrix ranking pages, caches the HTML under `data/external/fightmatrix/`,
and writes `fightmatrix_rankings.parquet` with division, rank, fighter, age,
record, points, profile URL, last-fight text, and next-fight text. Per-bout
pre-UFC history is still the next merge step.

## 7. Local SQLite database

`build_database.py` builds `data/ufc_rank_engine.sqlite` from the snapshot
bundle. It is an organized local database for audit and notebook support; it is
not a separate source of truth. Tables include:

- Canonical UFC tables: `canonical_events`, `canonical_fights`,
  `canonical_rounds`, `canonical_fighters`.
- Rating and derived tables: `ratings_current`, `ratings_history`,
  `ratings_history_method_integrity`, `ratings_history_method_performance`,
  `ratings_history_method_integrity_performance`, `ratings_history_whr`,
  `integrity_appearances`, `performance_appearances`,
  `fight_dominance`, `fighter_dominance`.
- Audit tables: `excluded_bouts`, `ped_confirmed_bouts`, `missed_weight_bouts`.
- External staged tables: `datalab_bouts_all`,
  `datalab_merged_stats_scorecards`, `datalab_fighter_details`,
  `datalab_scorecards`, `fightmatrix_rankings`.
- Metadata tables: `source_manifest`, `snapshot_manifest`,
  `table_row_counts`, `source_gaps`.

SQLite indexes are created on fighter, event date, fight URL, event name, and
source-specific fighter/division fields where those columns exist.

## 8. Tertiary fallback (mmadecoded — populated only if higher-priority is null)

| Field | Source     | Match key                                  | Notes |
|-------|------------|--------------------------------------------|-------|
| any   | mmadecoded | `(event_date, fighter_a, fighter_b)`       | Logged to `data/snapshots/<date>/_fallbacks.log`. |

## Exclusion rules (rating engine drops these)

- `event_date < 2000-11-17` → pre-unified-rules era (UFC 1–27). Dropped from the canonical fights table.
- `method_class == "Overturned"` → drug-violation reversal or post-fight overturn.
- `method_class == "Could Not Continue"` → treated as NC for rating purposes.
- `is_nc` true → no contest.

All excluded bouts are persisted to `_excluded_bouts.csv` for audit.

## Sleeve architecture (post 2026-05-13 consolidation)

The rating engine emits five Glicko-2 streams plus one WHR sidecar stream in
`ratings_current.parquet`:

| Stream | Sleeves applied | Notes |
|---|---|---|
| `mu_canonical` | none | Strict W/L/D Glicko-2. Never sleeved. |
| `mu_method` | none | Method-bonus winner score in [0.7, 1.0]. Never sleeved. |
| `mu_method_integrity` | integrity | Method + PED/DQ/missed-weight damp. |
| `mu_method_performance` | performance | Method + quality + odds reward. |
| `mu_method_integrity_performance` | both | Method with both sleeves composed. |
| `mu_whr` | n/a — sidecar | Whole-History Rating smoother (Coulom 2008); see `ratings/whr.py`. **The default headline ranking** — comparable across eras at the rating layer. |

All per-fight sleeve weights fall in the symmetric envelope
`[SLEEVE_FACTOR_MIN, SLEEVE_FACTOR_MAX] = [0.80, 1.20]`. No individual
sub-factor amplitude exceeds 0.20. Tunables live in `ratings/constants.py`.
WHR period scores (`sustained_peak_*_whr`, `five_year_peak_*_whr`) and history
(`ratings_history_whr.parquet`) are emitted alongside the Glicko-2 streams.

### Integrity sleeve

`mu_method_integrity` damps tainted results on the winner's side. Three
authoritative signals are OR-merged into per-fight flags
(`integrity_flags.parquet` audit table):

* PED-confirmed (from `loaders/ped_flags.py`): factor `0.80` (-20% floor —
  the most severe integrity penalty). Confirmed cases also exported to
  `ped_confirmed_bouts.csv`.
* DQ winner (Greco `method_class == "DQ"`): factor `0.92` (-8%).
* Missed-weight winner: factor `0.88` (-12%). Detected from Greco
  `details_text` ("missed weight" phrase + winner name) and, when
  available, mdabbert `R_Weight_lbs`/`B_Weight_lbs` vs `weight_class`
  divergence (cross-check). Audit export: `missed_weight_bouts.csv`.

Factors compose multiplicatively and are then clamped to
`[SLEEVE_FACTOR_MIN, 1.0]` (integrity only penalises, never rewards).

### Performance sleeve

`mu_method_performance` rewards impressive results and damps poor ones. The
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
* Market odds (from `odds_lines.parquet`) only contribute when the rank gate
  is already open; fights without odds fall back to pure quality.

All sub-factor amplitudes live in `ratings/constants.py`; the per-factor
`perf_factor_*` columns in `performance_appearances.parquet` are retained for
audit even though only the deduplicated signal feeds `S`.

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
performance sleeve's odds sub-factor is active wherever this artifact is
present; rate_snapshot prints the realised coverage at end-of-run.

Loaded odds sources:

| Source | Format | Era | License | Current role |
|--------|--------|-----|---------|--------------|
| mdabbert `ultimate_ufc_dataset` — `ufc-master.csv` | CSV American moneyline | 2010-03-21 -> 2026-03-28 (~6,900 bouts with both-side odds) | Apache-2.0 (`F U N/ultimate_ufc_dataset-main/LICENSE`); attribution required, redistributable | Primary ingest backing `odds_lines.parquet` and the performance sleeve's market sub-factor. Joined via fighter-pair + date. |

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
