"""Snapshot inputs and published policy for Career Skill Mass intervals."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ratings.age import load_birth_dates
from ratings.constants import SUSTAINED_PEAK_MIN_FIGHTS
from ratings.divisions import division_labels
from ratings.fights import load_fight_table
from ratings.gender import DEFAULT_GENDER, select_component_fights, select_gender
from ratings.scope import DEFAULT_PUBLISHED_SCOPE
from ratings.symon_score import DEFAULT_CAREER_REFERENCE, DEFAULT_DIVISION_REFERENCE, DEFAULT_HINGE_SPREAD_FRACTION
from ratings.uncertainty import career_mass_bootstrap
from ratings.whr import production_score_kwargs


def bootstrap_snapshot(
    snapshot: Path, *, scope: str = DEFAULT_PUBLISHED_SCOPE, gender: str = DEFAULT_GENDER,
    min_rating_periods: int = SUSTAINED_PEAK_MIN_FIGHTS, reference: str | float = DEFAULT_CAREER_REFERENCE,
    replicates: int = 12, seed: int = 0, lo: float = 0.025, hi: float = 0.975, progress: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Refit the published functional inside one gender component, returning paired draws."""
    population = select_gender(pd.read_parquet(snapshot / "ratings_current.parquet"), gender)
    fights = select_component_fights(load_fight_table(snapshot, scope=scope), population)
    eligible = set(population.loc[
        population["rating_periods"].fillna(0) >= min_rating_periods, "fighter"
    ].astype(str))
    return career_mass_bootstrap(
        fights, replicates=replicates, seed=seed, lo=lo, hi=hi, progress=progress,
        whr_kwargs={
            "birth_dates": load_birth_dates(snapshot), "age_drift": True, **production_score_kwargs(fights),
        },
        mass_kwargs={
            "reference": reference, "divisions": division_labels(population),
            "division_reference": DEFAULT_DIVISION_REFERENCE, "hinge_spread_fraction": DEFAULT_HINGE_SPREAD_FRACTION,
        },
        eligible_fighters=eligible, return_draws=True,
    )
