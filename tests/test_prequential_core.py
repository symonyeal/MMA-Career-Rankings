from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import build_prequential_evaluation as build_eval
from ratings import prequential as pq
from ratings.scope import SCOPE_ARTIFACT


def _fight(url: str, source: str, date: str) -> dict:
    return {
        "fight_url": url,
        "event_date": pd.Timestamp(date),
        "event_name": f"Event {url}",
        "fighter_a": f"A {url}",
        "fighter_b": f"B {url}",
        "winner": f"A {url}",
        "is_draw": False,
        "is_nc": False,
        "method_class": "Decision",
        "method_score_winner": 1.0,
        "details_text": "",
        "source": source,
    }


def test_default_variants_are_the_lean_coherent_set() -> None:
    variants = pq.default_variants()
    assert [v.name for v in variants] == [
        "canonical",
        "whr",
        "whr_symmetric_dominance_research",
    ]

    whr = variants[1]
    assert whr.engine == "whr"
    assert whr.use_age_drift is True
    assert whr.project_age_inactivity is True
    assert whr.weight is None
    assert whr.use_quality_score is False
    assert whr.use_dominance is False

    research = variants[2]
    assert research.engine == "whr"
    assert research.weight is None
    assert research.use_quality_score is False
    assert research.use_dominance is True
    assert research.use_age_drift is True
    assert research.project_age_inactivity is True


def test_ablation_pairs_contain_no_retired_sleeves_or_market_arm() -> None:
    names = {name for pair in build_eval.ABLATION_PAIRS for name in pair[:2]}
    assert names == {"canonical", "whr", "whr_symmetric_dominance_research"}
    assert not any("integrity" in name or "performance" in name for name in names)
    assert not any("market" in isolate or "odds" in isolate for *_, isolate in build_eval.ABLATION_PAIRS)


def test_fight_loader_defaults_to_ufc_only(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    pd.DataFrame([_fight("ufc/1", "ufc", "2024-01-01")]).to_parquet(
        snapshot / "canonical_fights.parquet", index=False
    )
    pd.DataFrame([_fight("x/1", "sherdog", "2023-01-01")]).to_parquet(
        snapshot / SCOPE_ARTIFACT["fightmatrix"], index=False
    )

    core = pq.load_fight_table(snapshot)
    experimental = pq.load_fight_table(snapshot, with_crossorg=True)

    assert core["fight_url"].tolist() == ["ufc/1"]
    assert set(experimental["fight_url"]) == {"ufc/1", "x/1"}


def test_symmetric_dominance_research_uses_one_weight_per_bout() -> None:
    fights = pd.DataFrame([_fight("ufc/1", "ufc", "2024-01-01")])
    fights["org_weight"] = 1.0
    inputs = pq.Inputs(
        snapshot_dir=Path("snapshot"),
        fights=fights,
        history=pd.DataFrame(),
        dominance_level={"ufc/1": 1.0},
    )
    variant = pq.default_variants()[2]

    weighted = pq._weighted_fights(inputs, variant)

    assert weighted.loc[0, "weight_a"] == pytest.approx(weighted.loc[0, "weight_b"])
    assert weighted.loc[0, "weight_a"] > 1.0


def test_whr_rejects_side_specific_appearance_sleeves() -> None:
    fights = pd.DataFrame([_fight("ufc/1", "ufc", "2024-01-01")])
    fights["org_weight"] = 1.0
    inputs = pq.Inputs(
        snapshot_dir=Path("snapshot"),
        fights=fights,
        history=pd.DataFrame(),
    )
    variant = pq.Variant("invalid", engine="whr", weight="integrity")

    with pytest.raises(ValueError, match="side-specific appearance sleeves are retired"):
        pq._weighted_fights(inputs, variant)


def test_fractional_whr_score_is_passed_only_when_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fights = pd.DataFrame(
        [
            _fight("ufc/1", "ufc", "2024-01-01"),
            _fight("ufc/2", "ufc", "2024-02-01"),
        ]
    )
    fights["fighter_a"] = "Alice"
    fights["fighter_b"] = "Bob"
    fights["winner"] = "Alice"
    fights["org_weight"] = 1.0
    inputs = pq.Inputs(
        snapshot_dir=Path("snapshot"),
        fights=fights,
        history=pd.DataFrame(),
        quality_score=pd.DataFrame(
            {
                "fight_url": ["ufc/1", "ufc/2"],
                "quality_score_winner": [0.8, 0.8],
            }
        ),
    )
    events = pd.DataFrame(
        {
            "event_date": [pd.Timestamp("2024-02-01")],
            "event_name": ["Event ufc/2"],
        }
    )
    seen_kwargs: list[dict] = []

    def fake_run_whr(train: pd.DataFrame, **kwargs) -> pd.DataFrame:
        seen_kwargs.append(kwargs)
        return pd.DataFrame(
            {
                "fighter": ["Alice", "Bob"],
                "event_date": [pd.Timestamp("2024-01-01")] * 2,
                "event_name": ["Event ufc/1"] * 2,
                "mu_whr": [1510.0, 1490.0],
            }
        )

    monkeypatch.setattr(pq, "run_whr", fake_run_whr)

    pq.whr_predictions(inputs, pq.Variant("base", engine="whr"), events)
    pq.whr_predictions(
        inputs,
        pq.Variant("soft", engine="whr", use_quality_score=True),
        events,
    )

    assert "winner_score_col" not in seen_kwargs[0]
    assert seen_kwargs[1]["winner_score_col"] == "quality_score_winner"


def test_age_aware_forecast_projects_last_rating_across_inactivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fights = pd.DataFrame(
        [
            _fight("ufc/1", "ufc", "2020-01-01"),
            _fight("ufc/2", "ufc", "2024-01-01"),
        ]
    )
    fights["fighter_a"] = "Alice"
    fights["fighter_b"] = "Bob"
    fights["winner"] = "Alice"
    fights["org_weight"] = 1.0
    inputs = pq.Inputs(
        snapshot_dir=Path("snapshot"),
        fights=fights,
        history=pd.DataFrame(),
        birth_dates={"Alice": pd.Timestamp("1984-01-01")},
    )
    events = pd.DataFrame(
        {
            "event_date": [pd.Timestamp("2024-01-01")],
            "event_name": ["Event ufc/2"],
        }
    )

    def fake_run_whr(_train: pd.DataFrame, **_kwargs) -> pd.DataFrame:
        history = pd.DataFrame(
            {
                "fighter": ["Alice", "Bob"],
                "event_date": [pd.Timestamp("2020-01-01")] * 2,
                "event_name": ["Event ufc/1"] * 2,
                "mu_whr": [1600.0, 1500.0],
            }
        )
        history.attrs["age_drift_elo_per_year"] = [-10.0] * 8
        return history

    monkeypatch.setattr(pq, "run_whr", fake_run_whr)
    unprojected = pq.whr_predictions(
        inputs, pq.Variant("age", engine="whr", use_age_drift=True), events
    )
    projected = pq.whr_predictions(
        inputs,
        pq.Variant(
            "age_projected",
            engine="whr",
            use_age_drift=True,
            project_age_inactivity=True,
        ),
        events,
    )

    assert projected.loc[0, "p_a"] < unprojected.loc[0, "p_a"]


def test_segments_align_market_role_and_completeness_after_side_flip() -> None:
    fight_url = "ufc/favorite-won"
    predictions = pd.DataFrame({
        "variant": ["canonical"],
        "fight_url": [fight_url],
        "event_date": [pd.Timestamp("2024-01-01")],
        "event_name": ["Favorite won"],
        "fighter_a": ["Favorite"],
        "fighter_b": ["Underdog"],
        "p_a": [0.75],
        "y_a": [1],
        "prior_a": [8],
        "prior_b": [4],
    })
    fights = pd.DataFrame({
        "fight_url": [fight_url],
        "event_date": [pd.Timestamp("2024-01-01")],
        "weight_class": ["Lightweight"],
        "method_class": ["Decision"],
        "source": ["ufc"],
        "fighter_a_completeness": [0.9],
        "fighter_b_completeness": [0.2],
    })
    odds = pd.DataFrame({
        "fight_url": [fight_url],
        "implied_prob_a_no_vig": [0.8],
        "implied_prob_b_no_vig": [0.2],
        "odds_data_quality": ["ok"],
    })

    flipped = pq.symmetrize_sides(predictions, seed=0)
    assert bool(flipped.loc[0, "side_flipped"])

    row = pq.attach_segments(flipped, fights, odds=odds).iloc[0]

    assert row["fighter_a"] == "Underdog"
    assert row["y_a"] == 0
    assert row["implied_prob_a_no_vig"] == pytest.approx(0.2)
    assert row["role"] == "favourite_won"
    assert row["fighter_a_completeness"] == pytest.approx(0.2)
    assert row["fighter_b_completeness"] == pytest.approx(0.9)


def test_crossorg_scope_refuses_to_be_a_silent_no_op(tmp_path: Path) -> None:
    """Asking for cross-org without the artifact must raise, not rate UFC-only.

    The standard snapshot carries the bouts only under suffixed names, so the
    flag used to merge zero rows and emit a board identical to UFC-only with no
    signal that it had done nothing. That reads as "cross-org makes no
    difference", which the differentiator audit contradicts.
    """
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    pd.DataFrame([_fight("ufc/1", "ufc", "2024-01-01")]).to_parquet(
        snapshot / "canonical_fights.parquet", index=False
    )
    # Present, but under an obsolete suffix the loader does not read.
    pd.DataFrame([_fight("x/1", "sherdog", "2023-01-01")]).to_parquet(
        snapshot / "crossorg_fights.fightmatrix-public.parquet", index=False
    )

    # UFC-only still works and says nothing about a file it was not asked for.
    assert pq.load_fight_table(snapshot)["fight_url"].tolist() == ["ufc/1"]

    with pytest.raises(FileNotFoundError) as excinfo:
        pq.load_fight_table(snapshot, with_crossorg=True)
    message = str(excinfo.value)
    assert "crossorg_fights.fightmatrix-public.parquet" in message, (
        "the error must name the suffixed artifact that is actually present")


def test_crossorg_scope_refuses_an_empty_artifact(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    fights = pd.DataFrame([_fight("ufc/1", "ufc", "2024-01-01")])
    fights.to_parquet(snapshot / "canonical_fights.parquet", index=False)
    fights.iloc[0:0].to_parquet(snapshot / SCOPE_ARTIFACT["fightmatrix"], index=False)

    with pytest.raises(ValueError, match="zero bouts"):
        pq.load_fight_table(snapshot, with_crossorg=True)


def test_crossorg_scope_reports_no_artifact_at_all(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    pd.DataFrame([_fight("ufc/1", "ufc", "2024-01-01")]).to_parquet(
        snapshot / "canonical_fights.parquet", index=False
    )
    with pytest.raises(FileNotFoundError, match="no cross-org artifact at all"):
        pq.load_fight_table(snapshot, with_crossorg=True)
