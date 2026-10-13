UFC-Rank-Engine has substantial tests, careful data provenance and explicit model decisions, but the WHR solver has a confirmed numerical defect. Its ratings should be recomputed after that defect is repaired before drawing new conclusions from the published boards.

Reviewed on 2026-10-08 at commit `c0072b493cfbe2427d0c14744e7031dbd876ac74`, which matched GitHub `main`. Repository source and published artifacts were left unchanged. This evaluation combines source review, the full checks, committed-data audits and three independently executed synthetic reproductions. It does not measure changes to real fighters' ranks.

| Check | Result |
| --- | --- |
| System Python | 3.14.7; existing installation used |
| Full pytest suite | 542 passed, 30 skipped; 30.16 seconds |
| Ruff | Passed |
| Dependency consistency | `pip check` passed |
| Available fight records | 82,912 |
| Published-scope model bouts | 81,512; matches run manifest |
| Model fighters | 34,126; matches run manifest |
| Model date range | 1980-04-25 through 2026-08-30 |
| Basic model-row checks | No self-bouts, invalid decided winners, missing dates or missing participants |
| Board rebuild | Failed: `ratings_current.parquet` absent |

The first test run stopped during collection because Plotly was missing. Installing the declared `requirements.txt` into the existing system Python resolved collection. This also installed missing PyArrow, lxml and widget packages. The final check results above are from the subsequent run; see [pytest.txt](pytest.txt), [ruff.txt](ruff.txt), [pip-check.txt](pip-check.txt) and [data_audit.json](data_audit.json).

1. **P1: WHR recentering prevents the stated posterior fit and couples disconnected fighters.**

   [ratings/whr.py:470](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/ratings/whr.py#L470>) subtracts the mean appearance rating after every pass. The Gaussian anchor and virtual-game priors already fix the origin; shifting ratings changes these terms. The resulting iteration does not solve the stated maximum a posteriori problem.

   Let one fighter win ten fights against distinct opponents, separated by 90 days. With the solver's default prior and drift parameters and 500 passes, an independent optimization of the same negative log posterior gives:

   | Quantity | Repository solver | Independent MAP reference |
   | --- | ---: | ---: |
   | Negative log posterior | 10.824488 | 9.369110 |
   | Gradient infinity norm | 0.203993 | 5.81e-11 |
   | Final winner–last opponent rating gap | 326.45 | 446.10 |

   Adding ten entirely disconnected, alternating C–D results changes the original rating gap to 420.33: a **93.88-point change**. The model's posterior should factorize across these disconnected graphs. Relative ratings and predictions change here, so this cannot be explained by choosing a display origin.

   The reproduction uses binary scoring without age drift to isolate the solver. Production uses the same recentering operation, but the effect on the published corpus has not been measured. Increasing the iteration count does not establish numerical correctness. [Coulom's WHR formulation](https://www.remi-coulom.fr/WHR/) describes joint posterior optimization; the objective-gradient comparison here is an independent check of this repository's particular priors.

   Repair the optimization to respect its stated priors. Add certificates for joint stationarity and independence of disconnected components, then rerun the production fit, held-out evaluation, scoring and publication. If zero appearance mean is intended as an additional model constraint, state that constraint and solve its constrained problem explicitly.

   Evidence: [probe_whr_centering.py](probe_whr_centering.py), [whr_centering.json](whr_centering.json).

2. **P2: Glicko evaluation probabilities omit inactivity inflation.**

   [ratings/prequential.py:341](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/ratings/prequential.py#L341>) shifts the previous post-event rating deviation into the next forecast. The engine inflates that deviation for elapsed inactive months before taking the entering-event state at [ratings/glicko2_engine.py:158](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/ratings/glicko2_engine.py#L158>). The benchmark therefore predicts with different uncertainty from the engine it evaluates.

   Ten wins followed by a long absence produce forecast probability 0.949074 from the reconstructed state versus 0.929508 from the actual entering-event state. The respective deviations are 200.722 and 256.969. The long gap makes the discrepancy easy to detect; it is not an estimate of its aggregate effect on normal UFC forecasts.

   Record entering-event states in the engine, or reproduce the same inactivity update using the previous volatility and event dates. Verify equality on a schedule containing inactive months before comparing Glicko with WHR.

   Evidence: [probe_prequential_inactivity.py](probe_prequential_inactivity.py), [prequential_inactivity.json](prequential_inactivity.json).

3. **P2: Prime reports a different interval from the interval used to compute its level.**

   [ratings/opponent_quality.py:336](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/ratings/opponent_quality.py#L336>) averages appearances through the full ten-year endpoint. At [line 342](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/ratings/opponent_quality.py#L342>) it stores the last qualifying win as the returned endpoint.

   Five qualifying wins during 2000–2004 at rating 2100, followed by a nonqualifying appearance in 2009 at 1500, return a level of 2000 and dates 2000–2004. The mean inside those reported dates is 2100. The deliberately win-anchored start rule is coherent; the provenance of the returned mean is inconsistent.

   Return the endpoint actually used in the mean, and give the last qualifying win its own field if needed. Test a later nonqualifying appearance inside the selected decade.

   Evidence: [probe_prime_window.py](probe_prime_window.py), [prime_window.json](prime_window.json).

4. **P2: the documented publication path is incomplete in the versioned checkout.**

   The authoritative combined fight table is committed and its basic counts match the manifest. However, canonical fights, rounds, fighter metadata, staged major-promotion fights, the career-coverage audit, fitted ratings and board parquets are absent. The quick-start board command fails when [build_boards.py:413](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/build_boards.py#L413>) reads the missing fitted ratings. The full fit first needs canonical rounds at [ratings/rate_snapshot.py:532](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/ratings/rate_snapshot.py#L532>); a combined fight table alone does not satisfy that entry point.

   Several checks of published rankings and complete-career coverage skip when these artifacts are absent. Consequently, passing CI verifies many mechanisms and manifest labels without reproducing the actual rankings or re-establishing the coverage claim. Publish a reproducible input bundle or a documented build path from committed evidence, and require the relevant publication checks for a release.

   The documented `C:\Python314\python.exe` path is also obsolete on this laptop. The existing interpreter is `C:\Users\Yeal\AppData\Local\Python\pythoncore-3.14-64\python.exe`; portable instructions should use `py -3.14`.

   Evidence: [audit_data.py](audit_data.py), [data_audit.json](data_audit.json), [board-rebuild.txt](board-rebuild.txt), [.gitignore](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/.gitignore>) and [publication tests](<https://github.com/symonyeal/UFC-Rank-Engine/blob/c0072b493cfbe2427d0c14744e7031dbd876ac74/tests/test_readme_narrative_figures.py#L18>).

The strongest design choices are substantive. Production WHR forecasts refit on observations strictly before the forecast date. The age profile is learned within that training fit, default calibration precedes evaluation, and shared bout weights are enforced. Conditional block curvature is explicitly distinguished from marginal posterior uncertainty. Cross-source identity resolution and scope membership have dedicated tests. The decision register distinguishes owner policy, unresolved evidence and rejected model changes.

Some statistical limits remain separate from these defects. Promotion factors, score weights and eligibility thresholds are policy choices rather than fitted facts. Career Skill Mass bootstrap intervals do not describe the complete published All-time composite. The older `whr_backtest` uses a binary, age-neutral, decided-bout model and cannot directly calibrate the published method-aware model. The `paired_delta` helper resamples bouts individually, which assumes more independence than an event-cluster analysis. These are reasons to qualify claims and identify the evaluated model precisely, not reasons to undo changes already tested and refused.

The source-documentation contract also needs attention: the committed Sherdog directory and FightMatrix page directory lack adjacent `ATTRIBUTION.txt` files, although the working contract requires source attribution and licence records. This is a repository documentation gap; no conclusion about redistribution rights was established.

Prioritize the WHR solver, then verify Glicko forecast states and Prime interval provenance. Restore a reproducible release bundle before treating a passing suite as validation of the published rankings. Do not tune policy constants around the solver defect.

To rerun the synthetic checks from this directory with the normal Python launcher:

```powershell
py -3.14 probe_whr_centering.py
py -3.14 probe_prequential_inactivity.py
py -3.14 probe_prime_window.py
py -3.14 audit_data.py
```

The WHR reference probe also uses SciPy, which was already available in the system interpreter. The recorded checks used the absolute interpreter path because Windows application-execution aliases cannot run under this session's sandbox.

## Status after repair, 2026-10-12

The probes were rerun from `docs/validation/review-2026-10-08/` against `main` after the repair commits. The original outputs above are unchanged; the reruns are beside them as `*_after_repair.json`.

| Finding | Before | After |
| --- | --- | --- |
| P1, WHR objective at `run_whr`'s result | 10.824488, gradient 0.203993 | 9.369110, gradient 1.9e-16; equals the independent MAP |
| P1, winner–last opponent gap | 326.45, moved 93.88 by disconnected bouts | 446.10, unchanged by disconnected bouts |
| P2, forecast probability after a long absence | 0.949074 against the engine's 0.929508 | 0.929508, equal |
| P3, reported Prime level against mean inside the returned window | 2000 against 2100 | 2000 and 2000, with the window ending 2009-12-31 |

P4 is not resolved. `check_release.py` now names what a release needs, and the published boards still predate the repair; see the WHR entry in [the decision register](../../DECISIONS.md).
