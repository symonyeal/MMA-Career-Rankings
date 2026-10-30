# Code nothing reached — 2026-10-29

Modules that no production path imported. Their tests are beside them. No ranking moved: the
full release chain was rerun before and after and every published artifact was identical.

- `ratings/crossover.py`: promotion-crossover profiles and a transfer test. Only its own test
  called it.
- `loaders/crossorg_identity_audit.py`: a fuzzy candidate list for cross-source names. Only its
  own test called it; the finding it produced (sibling fighters defeat a surname-plus-initial
  join) is recorded in `loaders/crossorg_identity.py`.

Functions removed from live modules, recoverable from git history at 7a0b2a1:
`career_mass_family`, `rank_is_separated`, `is_championship_bout(row)`,
`fold_in_loose_files`, `PageCache.has`, `unmatched_names`, `select_current_rating_col`,
`remove_vig` (the vectorised no-vig pair in `compute_implied_probs` is the live one),
`merge_crossorg_fights` (its scope-guard tests now call `ratings.scope.merge_scope`),
`Glicko2.rate_1vs1`, `Glicko2.quality_1vs1`, `RatingEngine.predict_win_prob`,
`RatingEngine.matchup_quality`, and the fighter-seeded Sherdog crawl in `sherdog_loader.py`
(`parse_fighter_history`, `fetch_fighter_history`, `build_crossorg_bouts`).

Flags removed: `--experimental-crossorg` (refresh and rate_snapshot; in rate_snapshot it always
raised, because the alias set the scope and then failed the alias's own check),
`--with-crossorg` in `build_prequential_evaluation.py` (ignored, because `--scope` always had a
value), and `--min-fights` in `rate_snapshot` (never read). Use `--scope fightmatrix`.
