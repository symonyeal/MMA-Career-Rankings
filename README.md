# Symon UFC Rank Engine

A local, auditable UFC ranking lab built around a deliberately small
mathematical core. The engine separates three questions that older versions
mixed together:

1. What is a fighter's latent skill?
2. How much high-level skill did the fighter sustain across a career?
3. Which data-quality or integrity policies should change what is displayed?

The full design and 2026-08-20 audit are in
[Principled Core Evolution](docs/PRINCIPLED_CORE_EVOLUTION_2026-08-20.md), and
the follow-up pass — the prior-mass defect, the retired period scores, and the
bootstrap rank intervals — is in
[Prior Mass and Uncertainty](docs/PRIOR_MASS_AND_UNCERTAINTY_2026-08-20.md).
The forward plan — whole-sport scope, evidence precision, era depth, and the
Single-Entry principle that separates this engine from points-stacking systems —
is in [Whole-Sport Engine](docs/PLAN_WHOLE_SPORT_ENGINE_2026-08-21.md).

## The Core

Every decided bout contributes one binary Bradley--Terry likelihood. The
winner and loser share the same bout weight:

\[
\ell_b=\omega_b\{y_b\log\sigma(\theta_i-\theta_j)
+(1-y_b)\log\sigma(\theta_j-\theta_i)\}.
\]

The production scope currently has \(\omega_b=1\) for UFC bouts. Two estimators
read the same evidence:

- **Skill filter**: causal Glicko-2 for one-step-ahead validation and current
  skill.
- **Skill smoother**: Whole-History Rating (WHR) for retrospective career
  analysis.

### Prior mass is fixed per fighter

An undefeated record has no interior maximum-likelihood rating: the
Bradley--Terry gradient stays positive at every finite rating, so only the prior
stops the climb. If the prior is applied once per appearance, its mass grows
with career length at the same rate as the likelihood and the stopping point
becomes a constant that ignores the evidence. Measured on this database before
the fix, the highest rating of all 2,554 fighters belonged to a man with one UFC
bout, and 56 fighters at 1-0 averaged above the 98th percentile of the roster;
going from 1-0 to 10-0 bought 67 rating points.

Both priors now carry a fixed mass per fighter, spread across that fighter's
appearances: a Gaussian anchor (`WHR_PRIOR_VAR`) and `WHR_VIRTUAL_GAMES = 2`
bouts of prior evidence against an average opponent, half won and half lost, as
in Coulom's paper. That value was measured over 60 held-out events and is
**unresolved** — every paired interval crosses zero — so it ships on a stated
tie-break (the smallest prior mass that wins the point estimate), with no
accuracy claim attached. An undefeated fighter with \(k\) wins over average
opposition then settles at \(\sigma(r)=(k+v/2)/(k+v)\), which rises with the
evidence as it must.

The public all-time score is **Symon Career Skill Mass**:

\[
C_i=\sum_{y\in A_i}
\left[\overline{\theta}_{iy}-\overline{\theta}_{\text{field},y}\right]_+.
\]

It contributes at most once per active calendar year. Peak height, losses,
opponent strength, activity, and longevity therefore enter through the latent
rating history without adding opponent rank, title, streak, or activity points
a second time.

The yearly bar is an explicit parameter, not a hidden default. At the field mean
97% of the top fifty's years clear it, the positive part never binds, and the
score reduces to *active years x mean excess* — a longevity board. Raising the
bar to a quantile of the year's field makes the clip do real work.
``career_mass_family`` recomputes the same functional from the mean up to the
95th percentile and the notebook plots the whole ladder, so the
dominance-versus-longevity choice is visible rather than asserted.

### Rank uncertainty

`build_uncertainty.py` refits the entire smoother under Dirichlet-reweighted
events (the Bayesian bootstrap) and recomputes the career functional on each
replicate, writing `career_mass_uncertainty.parquet`. Ranks are published with
those intervals: where two intervals overlap, the board is not claiming an
ordering.

The first 150-replicate run says this matters. Median rank-interval width across
the top 50 is **102 places**, and no pair inside the top twenty is separated.
The defensible reading of the all-time board today is *Jon Jones, then a large
tied group* — printing 1 through 25 as an ordering would claim precision the
evidence does not contain. Resampling events with replacement is deliberately *not* used —
career mass is a sum over years, so dropping ~37% of events biases every
replicate low.

WHR's optional `return_variance` is not this quantity and is not a rank
interval: it inverts one fighter's Hessian block with every opponent held
fixed.

## Public Ranking Views

| View | Definition | Unit |
|---|---|---|
| All-time | Career Skill Mass | rating-points-years above the annual field |
| Prime | Best fixed 10-year WHR mean, at least 13 appearances, EB-shrunk | rating points |
| Peak | Best fixed 5-year WHR mean, at least 8 appearances, EB-shrunk | rating points |
| Current skill | Latest base WHR state | rating points |

Prime and Peak are diagnostics; neither feeds back into All-time. Their
windows and eligibility gates are fixed so the public leaderboard cannot be
rank-shopped with sliders.

## What Is Not in the Core

- **Titles, rankings, P4P labels, streaks, and odds** are descriptive or
  benchmarking data, not repeated rating bonuses.
- **Integrity** is a visible ledger and optional direct-debit board. It does
  not propagate a penalty through an opponent graph.
- **Completeness** is a separate gate. Insufficient history is shown as such,
  not disguised as low skill.
- **Era strength** is neutral by default. A common era offset is not
  identifiable from within-era bout outcomes; any modern-depth premium must be
  labelled as an external scenario.
- **Cross-organization history** is quarantined from production. The current
  experimental weights use eventual UFC-career information and cannot support
  a prequential accuracy claim until they are recomputed inside each cutoff or
  replaced by outcome-independent source reliability.

Former `method_*_performance`, `method_*_integrity`, and
`whr_integrity_performance` production streams are retired. The WHR solver also
rejects side-specific winner/loser likelihood weights because they do not form
one joint posterior.

The rolling opponent-quality period scores (`sustained_peak_*`,
`five_year_peak_*`) were retired on 2026-08-20 along with their era/division
normaliser. They re-counted opponent quality, title status, activity volume and
era position on top of a rating that already reflects all four, and needed about
twenty hand-set constants to do it. Opponent context survives only where it
answers a different question: `ratings/appearance_context.py` feeds the
division resume boards.

## Notebook

Open the generated dashboard:

```bash
jupyter lab analysis/notebook.ipynb
```

Or regenerate it from source:

```bash
python analysis/build_notebook.py
```

The public narrative is intentionally short:

1. snapshot and scope contract;
2. one ranking control and leaderboard;
3. held-out scorecard and paired ablation forest;
4. how firm the ranking is — bootstrap rank intervals, the bar-sensitivity
   ladder, and rating against the evidence under it;
5. where the score came from — one fighter's yearly contribution receipt, and
   the whole board decomposed into years above the field versus distance above
   it;
6. fighter and division exploration;
7. results versus the closing market;
8. integrity, source-scope, and FightMatrix appendices.

FightMatrix is a sanity check, never a tuning target. The odds are an external
prediction benchmark, never a rating input.

## Current Data Scope

The standard local snapshot is `data/snapshots/2026-08-13`:

- 8,479 rated UFC fights;
- 2,554 fighters;
- UFCStats/Greco fight and round data;
- optional UFC-DataLab, mdabbert odds, and FightMatrix comparison artifacts.

Large raw snapshots, caches, and generated SQLite files are intentionally
ignored by Git. Field-level provenance and known source gaps live in
[data/SOURCE_MATRIX.md](data/SOURCE_MATRIX.md).

## Rebuild

Run these commands from the project root.

Refresh the canonical snapshot, ratings, policy boards, changelog, and
notebook:

```bash
python refresh.py --snapshot-date 2026-08-13 \
  --greco-dir "data/raw/2026-08-13" \
  --include-external --include-odds \
  --mdabbert-csv "../../archive/ufc-master.csv"
```

Rebuild only ratings and the three standard board artifacts:

```bash
python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-08-13"
python build_boards.py "data/snapshots/2026-08-13"
```

Publish rank intervals for the career board (about five seconds per replicate
on an idle machine, so this is an offline step, not a notebook-time one):

```bash
python build_uncertainty.py "data/snapshots/2026-08-13" --replicates 150
```

`refresh.py --bootstrap-replicates 150` does the same inside a full refresh.

Regenerate held-out evaluation after any estimator or probability change:

```bash
python build_prequential_evaluation.py "data/snapshots/2026-08-13" \
  --events 40 --calibration-events 40 --mode recent --force \
  --artifact-dir "data/snapshots/2026-08-13"
```

Build the queryable SQLite export:

```bash
python build_database.py --snapshot-dir "data/snapshots/2026-08-13"
```

Run the test suite:

```bash
python -m pytest -q
```

## Experimental Cross-Organization Scope

Build cross-organization data only as an isolated research snapshot:

```bash
python build_crossorg.py \
  --base "data/snapshots/2026-08-13" \
  --out "data/snapshots/2026-08-13-crossorg"

python -m ratings.rate_snapshot \
  --snapshot-dir "data/snapshots/2026-08-13-crossorg" \
  --experimental-crossorg
```

The explicit flag is intentional. Results from that scope must be labelled
experimental until the future-information problem is fixed and the held-out
comparison is rerun.

## Project Layout

```text
analysis/                    Notebook builder and Plotly charts
ratings/                     Glicko-2, WHR, Career Skill Mass, policy boards
loaders/                     UFCStats and optional-source ingestion
build_boards.py              Integrity ledger/debit and completeness views
build_prequential_evaluation.py  Rolling-origin validation artifacts
build_database.py            SQLite export
data/SOURCE_MATRIX.md        Field-level provenance and coverage contract
docs/                        Current audit and design notes
docs/archive/                Superseded historical reports
tests/                       Model, pipeline, database, and chart tests
```

## Mathematical References

- Mark Glickman, [Example of the Glicko-2 system](https://www.glicko.net/glicko/glicko2.pdf)
- Mark Glickman, [Parameter estimation in large dynamic paired-comparison experiments](https://www.glicko.net/research/acjpaper.pdf)
- Rémi Coulom, [Whole-History Rating](https://www.remi-coulom.fr/WHR/)

Symon's novelty is the disciplined composition: one paired likelihood, two
estimators, one transparent career functional, and policy layers that never
silently mutate the skill model. It does not claim to have invented Glicko-2,
Bradley--Terry, WHR, or empirical Bayes.
