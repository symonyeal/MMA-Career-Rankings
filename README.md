# Symon UFC Rank Engine

A Glicko-2 fighter rating system over UFCStats/Greco UFC fight data, with
staged UFC-DataLab and FightMatrix comparison sources, a local SQLite
database, and a VS Code Jupyter notebook for interactive analysis.

See `MATHEMATICAL_AUDIT.md` for the 2026-05-14 peer-review pass, including
the championship-defense floor, direct dominance score modifier, activity
penalty formula, collinearity ruling, and archival candidates.

## Architecture (post 2026-05-13 consolidation)

The engine emits five Glicko-2 streams plus one WHR sidecar stream in
`ratings_current.parquet`. Sleeves only attach to the method stream; canonical
is always pristine.

| Stream | Sleeves | Description |
|---|---|---|
| `mu_canonical` | none, ever | Strict W/L/D Glicko-2. |
| `mu_method` | none | Method-bonus winner score in [0.7, 1.0]. |
| `mu_method_integrity` | integrity | Damps PED/DQ/missed-weight wins. |
| `mu_method_performance` | performance | Rewards impressive wins (quality + signed market line + rank/champ/P4P/weight-class context). |
| `mu_method_integrity_performance` | both | Composed sleeves. |
| `mu_whr` | n/a — sidecar | Whole-History Rating: a Bayesian *smoother* (Coulom 2008) over the whole fight history. Unlike the Glicko-2 *filter* it propagates information both directions, so ratings are comparable across eras at the rating layer. See `ratings/whr.py`. |

**WHR is the default headline ranking.** Consensus validation showed the
windowed Glicko-2 period streams still carried era-inflation and career-shape
artifacts (and a title-bonus multiple-count) even after the empirical-Bayes
re-parameterization, whereas WHR — being a smoother — does not. The engine
report, the changelog top-10, and the notebook leaderboard all lead with
`sustained_peak_headline_mu_whr`; the `method_integrity_performance` stream is
retained as a comparison surface. See `MODEL_ISSUES_AND_DIAGNOSIS.md` Issue 10.

All per-fight sleeve weights fall in the symmetric envelope `[0.80, 1.20]`.
No individual sub-factor exceeds 0.20. Tunables in `ratings/constants.py`.

Two historical period metrics are emitted for every rating stream. The 2-year
career peak surface was retired (too easy to game with a short hot streak);
the surviving windows are the 10-year sustained peak and the 5-year diagnostic.
Each raw period score ships alongside a headline proven-resume-adjusted variant:

* `sustained_peak_mu_<stream>` / `sustained_peak_headline_mu_<stream>` - best
  rolling 10-year window. The window must contain at least 13 UFC fights to
  qualify; once it qualifies, **every** appearance in that window is scored
  (wins, losses, draws, elite and weak opponents, activity volume).
* `five_year_peak_mu_<stream>` / `five_year_peak_headline_mu_<stream>` - best
  rolling 5-year window, same scoring, qualifying at 8 UFC fights.

Each window's raw score is an **opponent-quality-weighted mean** of post-fight
rating plus a small result adjustment and capped activity bonuses. The
2026-05-14 Phase-1 rework replaced hand-picked sensitivity constants with
data-derived, reliability-weighted quantities grounded in the rating
literature:

* **Opponent quality is the first-priority signal.** The per-fight weight is a
  logistic (Bradley-Terry-shaped) mapping of opponent quality, with an extra
  multiplier for title bouts — a window of title-fight decisions over champions
  outweighs a window of finishes over mid-rank opponents. Method of victory is
  deliberately a minor signal.
* **Era/division normalization is empirical-Bayes.** Window mu is de-trended
  for calendar-year inflation and rescaled for division depth, but the
  *strength* of each correction is data-derived: James-Stein shrinkage by the
  cell's reliability, with the era shift gated by the year's "bridge fraction"
  (Berry, Reese & Larkey 1999 — era effects are only identifiable through
  fighters who span eras). Capped by one explicit conservatism prior.
* **Results are information-weighted.** A win is weighted by opponent quality;
  a loss is weighted by opponent *weakness* on top of a real floor — losing to
  a weak opponent is more damning than losing to a champion.
* **The window score is empirical-Bayes shrunk** toward the pooled mean by its
  sampling reliability — mild for well-sampled windows, firmer for noisy ones.

Headline columns add a proven-resume bonus on top:
`bonus = clip(HEADLINE_RESUME_RATE * sum(opp_weight in best window), 0,
HEADLINE_RESUME_BONUS_CAP)`. The bonus rewards longer, deeper resumes against
elite opposition. Cap is +50 mu so headline columns remain interpretable as
ratings.

Peak opponent quality is shared with the performance sleeve: actual bout
opponent, pre-fight canonical mu, divisional rank, championship, and P4P
context are deduplicated into one monotonic quality signal.

## Methodology

The base model is event-period Glicko-2. Every UFC event is one rating period:
all bouts on the card are evaluated from pre-event ratings, then each fighter
is updated once. Canonical scoring uses strict outcomes only: win = 1.0,
draw = 0.5, loss = 0.0. The Glicko-2 volatility constant is `tau = 0.5`,
with lazy inactivity inflation applied only when a fighter next appears.

The method stream keeps the same Glicko-2 update equation but replaces the
winner's score with a bounded method score (see `METHOD_SCORES` in
`loaders/ufcstats_loader.py`). Finishes are one rank: `KO/TKO = 1.00` and
`Submission = 1.00`. Decisions sit just below finishes in a very tight band:
`Decision - Unanimous = 0.985`, `Decision - Majority = 0.98`, and
`Decision - Split = 0.975`. Disqualification wins score `0.95` before the
integrity sleeve. The finish-vs-decision gap is intentionally small — the
method stream nudges, it does not dominate.

The integrity sleeve applies only to method ratings and only damps tainted
wins. PED-confirmed wins use the floor factor `0.80`; disqualification wins
use `0.92`; missed-weight wins use `0.88`. Multiple integrity flags multiply
and are clipped to `[0.80, 1.00]`. PED-confirmed losses are not damped because
dampening the losing update would make the loss less punitive.

The performance sleeve applies only to method ratings. It combines
transparent sub-factors for decisiveness, shared opponent quality, opponent
streak, market odds, rank-gated upset context, weight-class movement, and
activity-aware post-layoff losses, then clips the final factor to
`[0.80, 1.20]`.
The ranking/P4P factors use pre-fight model ranks only, so current external
rankings cannot leak backward into historical fights. The championship factor
uses title-fight labels plus a title lineage inferred from prior UFC title
bouts. Moving up and winning gets a modest boost; moving down and losing
modestly increases the losing update so the result detracts more. A loss
after a long layoff also increases the losing update; UFC debuts are neutral
because there is no prior UFC gap to measure. Odds are normalized
from signed moneylines inside the snapshot: the largest plus-money winner
maps to `1.15`, the largest absolute minus-money winner maps to `0.90`, and
intermediate lines are linearly scaled between those anchors. Missing odds
produce a neutral `1.00` market factor.

The combined stream multiplies integrity and performance weights per
appearance and clips the product back to `[0.80, 1.20]`. This keeps composed
sleeves inside the documented envelope and prevents a single fight from
dominating low-volume fighter histories.

## Model Selection Notes

The current production engine stays on Glicko-2 with `tau = 0.5`. Glickman's
Glicko-2 note describes reasonable `tau` choices as `0.3` to `1.2` and says
smaller values prevent volatility from changing by large amounts; the project
therefore keeps `0.5` as a conservative MMA default rather than moving to a
more reactive setting. A lower value such as `0.3` is plausible for sensitivity
testing, but it should be selected by backtesting predictive calibration, not
by convention alone.

OpenSkill and TrueSkill 2 are credible future directions, especially if the
project expands from one-on-one UFC outcomes into richer Bayesian graphs with
covariates. TrueSkill 2 explicitly adds extra observed features beyond
win/loss, while OpenSkill implements Weng-Lin Bradley-Terry,
Thurstone-Mosteller, and Plackett-Luce models. Neither is a drop-in replacement
for the current UFC-only Glicko stream without a calibration study.

Heavy-tailed or skewed-t likelihoods are theoretically sensible for combat
sports upsets because Student-t style residuals reduce outlier leverage, but
there is no project evidence yet that replacing Glicko-2's normal/logistic
components improves UFC prediction. Treat that as a research branch, not a
production setting.

## Current Status

The engine is working against the `2026-05-13` snapshot (the single canonical
snapshot after the 2026-05-14 consistency pass):

- Canonical Greco snapshot: 743 events, 8,346 rated fights, 39,886 round rows.
- Ratings snapshot: 2,507 rated fighters and 16,692 fighter-event history rows.
- Five rating streams emitted (see table above). Per-fighter integrity
  counts (`ped_confirmed_fights`, `dq_wins`, `missed_weight_wins`) live in
  `ratings_current.parquet`.
- Audit exports: `ped_confirmed_bouts.csv`, `missed_weight_bouts.csv`,
  `_excluded_bouts.csv`. Per-(fight, fighter) sleeve weights persisted as
  `integrity_appearances.parquet` and `performance_appearances.parquet`.
- External sources are staged: UFC-DataLab parquet outputs and
  FightMatrix rankings/cache.
- Sustained Peak: best 10-year window, qualifies at 13 UFC fights, all
  in-window appearances scored, opponent-quality-weighted and era/division
  normalized.
- 5-Yr Peak: best 5-year diagnostic window, qualifies at 8 UFC fights.
- Local SQLite database: `data/ufc_rank_engine.sqlite` (30 tables, 116 indexes).
- Build-time diagnostics: `calibration_residuals.parquet`,
  `sleeve_attribution.parquet`, and `division_entropy.parquet`.
- Odds: mdabbert "Ultimate UFC Dataset" (Apache-2.0) staged as
  `odds_lines.parquet` (6,562 ok-quality rows feeding the performance sleeve's
  market sub-factor).

FightMatrix and UFC-DataLab remain staged comparison sources only;
pre-UFC and cross-organization bouts are not yet merged into the
headline Glicko stream.

The archived `ratings/replacement_framework.py` research script is **not wired
into the engine**. The live period scores come from `ratings/peaks.py`.

## Layout

```text
Symon UFC Rank Engine/
  build_database.py           # builds data/ufc_rank_engine.sqlite
  refresh.py                  # end-to-end refresh orchestrator
  analysis/                   # Plotly builders + generated notebook
  data/
    raw/<YYYY-MM-DD>/         # copied Greco CSVs per refresh
    snapshots/<YYYY-MM-DD>/   # canonical parquet bundle + ratings outputs
    external/                 # project-local staged source caches
    SOURCE_MATRIX.md
    CHANGELOG.md
  loaders/                    # Greco, UFC-DataLab, FightMatrix, mdabbert
  ratings/                    # Glicko-2 engine, rating driver, sleeves, peaks
  tests/                      # engine, sleeves, peaks, loaders, viz
```

## Setup

From this project directory, with the local virtualenv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

All commands below assume `.venv/bin/python`. The project was developed on
Windows originally and now runs on Linux; paths are POSIX-style.

The Greco UFCStats CSVs used by the current snapshot are staged at:

```text
data/raw/2026-05-13/
```

The old vendored scraper checkout was archived during cleanup; `refresh.py`
and `loaders/ufcstats_loader.py` default to `data/raw/<snapshot-date>` when the
six Greco CSVs are already present.

The UFC-DataLab CSV exports the loader reads are vendored at
`data/external/api_sources/UFC-DataLab/`. The mdabbert Ultimate UFC Dataset
(Apache-2.0) is no longer kept in the tree as raw CSV — its ingested output
(`odds_lines.parquet`) is staged directly in the snapshot. To re-ingest odds
you must supply `ufc-master.csv` yourself via `--csv` / `--mdabbert-csv`.

## Refresh Sources

End-to-end refresh:

```bash
.venv/bin/python refresh.py --snapshot-date 2026-05-13 --include-external
```

Manual pieces:

```bash
.venv/bin/python loaders/ufcstats_loader.py --snapshot-date 2026-05-13 --project-root .
.venv/bin/python loaders/datalab_loader.py --snapshot-dir "data/snapshots/2026-05-13"
.venv/bin/python loaders/fightmatrix_loader.py --snapshot-dir "data/snapshots/2026-05-13" --cache-dir "data/external/fightmatrix/html"
.venv/bin/python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-05-13"
```

`odds_lines.parquet` is already staged in the snapshot; the performance
sleeve's market sub-factor picks it up automatically.

## Build SQLite

```bash
.venv/bin/python build_database.py --snapshot-dir "data/snapshots/2026-05-13"
```

## Use The Notebook

Open `analysis/notebook.ipynb` in VS Code Jupyter and run all cells. It
auto-loads the newest parquet snapshot under `data/snapshots/`.

Notebook sections include:

- Headline WHR top tables, split by gender because mixed-gender ordering is
  not identifiable from fight results.
- Calibration residuals: predicted `P(win)` vs empirical outcomes by division
  or stance.
- Sleeve attribution waterfall: exact base-method, integrity, performance,
  and interaction/clip deltas for a selected fighter.
- Division entropy: top-10 mu density and normalized entropy over time.

Regenerate the notebook after editing `analysis/build_notebook.py`:

```bash
.venv/bin/python analysis/build_notebook.py
```

## Verification

```bash
.venv/bin/python -m pytest -q
```

114 tests pass on the current snapshot.

## Included vs Pending

Included:

- UFC-only canonical Glicko-2 and method-weighted ratings.
- Lazy inactivity uncertainty inflation.
- Integrity sleeve (PED + DQ + missed-weight).
- Performance sleeve (quality of win + signed market line + rank/champ/P4P/weight-class context).
- Sustained Peak (10-year) + 5-Yr Peak diagnostic, each with a headline
  proven-resume-adjusted variant. The 2-year career peak was retired.
- Fight dominance and fighter dominance outputs.
- mdabbert odds staged as `odds_lines.parquet` (6,562 ok-quality rows).
- Staged UFC-DataLab and FightMatrix comparison tables.
- SQLite database with manifests, row counts, source gaps, and indexes.
- Notebook v2 with two-checkbox sleeve composer.

Pending:

- Pre-UFC and cross-organization bout ingestion into the headline Glicko stream.
- FightMatrix per-bout history scraping/merge.
- Deeper identity resolution between Greco, DataLab, and FightMatrix names.
