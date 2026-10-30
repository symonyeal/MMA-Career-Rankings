"""Shared event selection must preserve folds, eligibility and paired bout coverage."""
import pandas as pd

from ratings.evaluation import event_keys, paired_predictions, select_predictions


def test_fold_selection_distinguishes_same_day_cards_and_checks_both_corners():
    day = pd.Timestamp("2024-01-01")
    predictions = pd.DataFrame({
        "fight_url": ["keep", "other-card", "short-a", "short-b"],
        "event_date": [day] * 4, "event_name": ["A", "B", "A", "A"],
        "prior_a": [3, 8, 2, 5], "prior_b": [4, 8, 5, 2],
    }, index=[9, 4, 7, 6])
    keys = event_keys(pd.DataFrame({"event_date": [day], "event_name": ["A"]}))
    selected = select_predictions(predictions, keys, 3)
    assert selected["fight_url"].tolist() == ["keep"]
    assert selected.index.tolist() == [9]
    assert select_predictions(predictions, set(), 3).empty
    assert event_keys(pd.DataFrame()) == set()


def test_paired_selection_counts_distinct_variants_without_deduplicating_rows():
    predictions = pd.DataFrame({
        "fight_url": ["paired", "missing", "paired", "missing", "paired"],
        "variant": ["A", "A", "B", "A", "A"], "p_a": [.3, .4, .5, .6, .7],
    })
    selected = paired_predictions(predictions, 2)
    assert selected["fight_url"].tolist() == ["paired"] * 3
    assert selected["p_a"].tolist() == [.3, .5, .7]
    assert selected.index.tolist() == [0, 1, 2]
