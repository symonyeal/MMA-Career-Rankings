from pathlib import Path

import pandas as pd

from analysis.source_scope import build_scope_comparison


def test_scope_comparison_ranks_and_matches_reference_names(tmp_path: Path):
    ufc = tmp_path / "ufc"
    public = tmp_path / "public"
    ufc.mkdir()
    public.mkdir()
    score = "sustained_peak_headline_mu_whr_integrity_performance"
    pd.DataFrame([
        {"fighter": "Georges St-Pierre", score: 2000.0, "rating_periods": 22, "gender": "M"},
        {"fighter": "Fedor Emelianenko", score: 1800.0, "rating_periods": 0, "gender": "M"},
    ]).to_parquet(ufc / "ratings_current.parquet", index=False)
    pd.DataFrame([
        {"fighter": "Fedor Emelianenko", score: 2050.0, "rating_periods": 43, "gender": "M"},
        {"fighter": "Georges St-Pierre", score: 2010.0, "rating_periods": 28, "gender": "M"},
    ]).to_parquet(public / "ratings_current.parquet", index=False)
    pd.DataFrame([
        {"fighter": "Georges St. Pierre", "rank": 1, "points": 38570},
        {"fighter": "Fedor Emelianenko", "rank": 4, "points": 22856},
    ]).to_parquet(public / "fightmatrix_all_time.parquet", index=False)

    out = build_scope_comparison(ufc, public).set_index("fighter")

    assert out.loc["Georges St-Pierre", "ufc_only_rank"] == 1
    assert out.loc["Georges St-Pierre", "fightmatrix_public_rank"] == 2
    assert out.loc["Georges St-Pierre", "fightmatrix_reference_rank"] == 1
    assert out.loc["Fedor Emelianenko", "score_delta_public_minus_ufc"] == 250.0
