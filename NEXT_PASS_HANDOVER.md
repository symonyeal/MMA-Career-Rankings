# UFC Rank Engine — Next-Pass Handover

**Last updated:** 2026-05-14  
**Snapshot:** `data/snapshots/2026-05-13`  
**Python:** `py -3` (Python 3.14, Windows)  
**Run command:** `py -3 -m ratings.rate_snapshot --snapshot-dir "data\snapshots\2026-05-13"`

---

## Current State — What Is Fully Shipped

### Rating Streams (all persisted in `ratings_current.parquet`)

| Stream | Description |
|---|---|
| `canonical` | Pure Glicko-2, binary W/L. Ground truth for opponent strength. Never sleeved. |
| `method` | Glicko-2 + continuous method score (KO=1.0 → split decision=0.82). |
| `method_integrity` | method + integrity sleeve (PED ×0.80, DQ ×0.92, missed weight ×0.88). |
| `method_performance` | method + performance sleeve (tanh-smoothed, rank-gated upset, opp quality). |
| `method_integrity_performance` | method + both sleeves. |
| `whr` | WHR Bayesian smoother (Coulom 2008). Binary W/L. **Default headline.** Era-fair. |
| `whr_integrity` | WHR + integrity likelihood weights. |
| `whr_performance` | WHR + performance likelihood weights. |
| `whr_integrity_performance` | WHR + both sleeves. **Second headline.** |

WHR sleeve architecture: weight scales only the BT likelihood terms
`g *= w`, `h_diag *= w`; Wiener-process and anchor priors are unweighted.
`_attach_appearance_weights` feeds the same weight tables to both Glicko-2 and
WHR — sleeves are fully modular.

### Peak Columns (per stream, all in `ratings_current.parquet`)

- `five_year_peak_headline_mu_<stream>` — best 5-year window, min 8 UFC fights.
- `sustained_peak_headline_mu_<stream>` — best 10-year window, min 13 UFC fights.
- Raw (non-headline) variants also present for debug.
- Era/division normalization: empirical-Bayes James-Stein shrinkage gated by
  bridge fraction (Berry, Reese & Larkey 1999).

### Headline Rankings (Men, 10-Year Sustained, WHR)

1. Jon Jones 2. Georges St-Pierre 3. Anderson Silva 4. Demetrious Johnson
5. Alexander Volkanovski 6. Islam Makhachev 7. Jose Aldo 8. Daniel Cormier
9. Alex Pereira 10. Israel Adesanya

**Women headline:** Amanda Nunes #1 overall (3rd combined), Valentina Shevchenko,
Jose Aldo, Zhang Weili, Joanna Jedrzejczyk.

### Summary Document

`RANKINGS_SUMMARY.md` — generated 2026-05-14. Contains:
- Men overall top 30: WHR / WHR I+P / Method I+P / Canonical, both 10-yr and 5-yr.
- Men top 30 by division (8 divisions, WHR 10-yr).
- Women overall top 30: all four streams, both windows.
- Women top 30 by division (4 divisions).

Regenerate with:
```
py -3 -c "exec(open('scripts/gen_summary.py').read())"
```
Or re-run the inline script from the session that created it (2026-05-14).

---

## What Is NOT Done — Open Items

### Issue 1 (Open): UFC longevity underweighted
`mu - k*phi` conservative ranking column not yet added. The headline proven-resume
bonus in `HEADLINE_RESUME_RATE` partially addresses this, but no explicit
reliability score is surfaced.

### Issue 10 (Under review): WHR I+P vs WHR base — sleeve effect muted
WHR's joint global estimation absorbs sleeve weights smoothly across career arcs.
Max delta in sustained peak: Pereira +19 mu. This is a feature (robust, hard to
game) but means WHR I+P and WHR base rank order is nearly identical. Investigate
whether `WHR_W2_PER_DAY` tuning (predictive backtest) changes this picture.

### Issue 10 (sub): `replacement_framework.py` is dead code
`ratings/replacement_framework.py` (~57 KB) is not imported by anything.
It was superseded by `ratings/peaks.py` Pass B and WHR promotion. Either
delete it or formally archive it. Do not leave it as false documentation.

### WHR_W2_PER_DAY calibration (Research §9)
Current value `0.0004` is an MMA-prior default. Should be chosen by Brier/log-loss
backtest on held-out events. Candidate range: `0.0001` – `0.0010`.

### Predictive backtest (Research §1)
No Brier/log-loss evaluation exists yet. WHR vs canonical vs Method I+P comparison
not run. Blocking `tau` calibration and `WHR_W2_PER_DAY` calibration both.

### Continuous decisiveness score (Research §10)
`perf_factor_decisiveness` exists but is a simple 3-level signal. Full
calibrated `d ∈ [0,1]` per scorecard margin / round / seconds not yet built.

### Non-UFC priors (Research §12)
Debut fighters start at mu=1500/phi=350 regardless of feeder org record.
Hierarchical priors blocked on cross-org identity resolution.

---

## Architecture Invariants — Do Not Break

- **Canonical is never sleeved.** It is the opponent-strength ground truth.
- **WHR priors are unweighted.** Only BT likelihood terms receive sleeve weights.
- **`_attach_appearance_weights` is the single entry point** for wiring any
  weight table to any engine (Glicko-2 or WHR).
- **`_attach_activity_adjusted_mu` is now dynamic** — finds all `mu_*` columns
  automatically; adding new streams requires no edits to that function.
- **`probe700/` is OneDrive-locked (EPERM).** Use `_diagnostics/` for scratch scripts.
- **Memory dir:** `~/.claude/projects/c--Users-sislam-OneDrive---Government-of-Yukon-Documents-GitHub-Codex/memory/`

---

## Verification After Any Change

```powershell
py -3 -m pytest -q
py -3 -m ratings.rate_snapshot --snapshot-dir "data\snapshots\2026-05-13"
```

Sanity checks:
- Jones, GSP, Silva top 3 sustained WHR (men).
- Amanda Nunes #1 sustained WHR (women), top 3–5 combined.
- Khabib #15 men (13 fights, just meets minimum).
- Jiri Prochazka and Shavkat Rakhmonov: no sustained peak row (< 13 fights).
- Strickland def. Adesanya performance weight ≈ 1.19; GSP loser weight ≈ 0.81.
- WHR I+P vs WHR base: max sustained-peak delta < 25 mu (by design).
