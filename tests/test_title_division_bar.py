"""The title resume must be priced against the opponent's own division line.

`legacy_resume.title_quality_ledger` takes `divisions` as an OPTIONAL argument
and falls back to the sport-wide contender line when it is absent. Nothing
raises. So a caller that scores the resume before the division columns exist
gets the sport-wide bar silently, which is the pricing the comment above
`TITLE_QUALITY_SCALE` explicitly rejects: light divisions are then measured
against heavier ones and their champions score near zero.

That is exactly what `rate_snapshot.run()` did until 2026-08-25. The unit test
below pins the mechanism; the integration test pins the call ordering, which is
what actually regressed.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ratings.legacy_resume import _division_labels, title_quality_ledger

# The contender line is struck per division-YEAR, and a division-year thinner
# than symon_score.DEFAULT_DIVISION_MIN_POPULATION cannot describe its own line
# -- it correctly falls back to the sport-wide bar, which would make every
# assertion here vacuous. Thirty-two fighters active in each of two years is
# the smallest fixture that clears the floor in both years. That guard itself
# is pinned in test_symon_score.
HEAVY = [f"Heavy {i}" for i in range(32)]
FLY = [f"Fly {i}" for i in range(32)]
# The two pools do not overlap in rating, so a flyweight title win is worth
# almost nothing against a sport-wide bar and a real amount against its own.
RATING = {name: 1900.0 + 5 * i for i, name in enumerate(HEAVY)}
RATING.update({name: 1600.0 + 5 * i for i, name in enumerate(FLY)})
DIVISION = {name: "Heavyweight" for name in HEAVY} | {name: "Flyweight" for name in FLY}


def _history() -> pd.DataFrame:
    rows = [
        {"fighter": name, "event_date": pd.Timestamp(f"{year}-06-01"), "mu_whr": mu}
        for name, mu in RATING.items()
        for year in (2023, 2024)
    ]
    return pd.DataFrame(rows)


def _title_fight() -> pd.DataFrame:
    """One flyweight title fight: Fly 0 beats the best flyweight in the pool."""
    return pd.DataFrame([
        {
            "event_date": pd.Timestamp("2024-09-01"),
            "fighter_a": "Fly 0", "fighter_b": FLY[-1],
            "winner": "Fly 0", "is_title_fight": True,
            "is_excluded": False, "is_draw": False, "is_nc": False,
        }
    ])


def test_division_bar_prices_a_light_division_title_win_far_above_the_sport_wide_bar():
    history, fights = _history(), _title_fight()
    divisions = pd.Series(DIVISION)

    sport_wide = title_quality_ledger(fights, history, reference="contender:60")
    by_division = title_quality_ledger(
        fights, history, reference="contender:60", divisions=divisions
    )

    weak = float(sport_wide.loc[sport_wide["fighter"].eq("Fly 0"), "public_legacy_title_quality"].iloc[0])
    strong = float(by_division.loc[by_division["fighter"].eq("Fly 0"), "public_legacy_title_quality"].iloc[0])

    # Beating your own division's best is a real achievement; measured against
    # heavyweights it rounds to nothing.
    assert weak < 0.01
    assert strong > 0.05
    assert strong > 10 * weak


def _synthetic_snapshot(snapshot_dir: Path) -> None:
    """Two divisions, each thick enough to earn its own bar, and separated.

    The separation has to be *earned*. Two pools that never meet have no
    identified level difference -- that is the whole defect the division bar
    exists to handle -- so a symmetric fixture makes the division line and the
    sport-wide line agree, and the guard below would then pass vacuously in the
    other direction. A handful of cross-division bouts the heavyweights win is
    what puts the flyweight pool genuinely below the sport-wide contender line.
    """
    rows = []

    def _bout(a, b, winner, division, date, url, title=False):
        loser = b if winner == a else a
        return {
            "fight_url": url, "event_url": f"e/{url}",
            "event_name": f"Synthetic {url}", "event_date": date,
            "event_location": "", "bout_string": f"{a} vs. {b}",
            "fighter_a": a, "fighter_b": b,
            "fighter_a_outcome": "W" if winner == a else "L",
            "fighter_b_outcome": "W" if winner == b else "L",
            "winner": winner, "loser": loser,
            "is_draw": False, "is_nc": False,
            "is_excluded": False, "exclusion_reason": None,
            "weight_class": division, "is_title_fight": title,
            "method_raw": "Decision - Unanimous",
            "method_class": "Decision - Unanimous",
            "method_score_winner": 0.85,
            "end_round": 3, "end_time_seconds": 300,
            "time_format": "3 Rnd (5-5-5)",
            "referee": "", "details_text": "",
            "ped_confirmed": False, "ped_flagged_fighter": None,
            "ped_confirmation_source": None, "ped_confirmation_detail": None,
        }

    for pool, division in ((HEAVY, "Heavyweight"), (FLY, "Flyweight")):
        for year in (2023, 2024):
            for i in range(len(pool)):
                # Round robin inside the division; the higher-rated name wins.
                a, b = pool[i], pool[(i + 1) % len(pool)]
                winner, loser = (a, b) if RATING[a] > RATING[b] else (b, a)
                title = division == "Flyweight" and year == 2024 and i == 0
                # Spread the card across the year; thirty-two bouts no longer
                # fit one per month.
                rows.append(_bout(
                    a, b, winner, division,
                    pd.Timestamp(f"{year}-01-05") + pd.Timedelta(days=10 * i),
                    f"u/{division}/{year}/{i}", title=title,
                ))

    # Heavyweight-billed crossovers, won by the heavyweight, in both years.
    # Enough to identify the offset between the pools and push the flyweights
    # clearly below the sport-wide contender line; still a minority of every
    # flyweight's record, so nobody's career_division moves off Flyweight.
    for year in (2023, 2024):
        for i in range(12):
            rows.append(_bout(
                HEAVY[i], FLY[i], HEAVY[i], "Heavyweight",
                pd.Timestamp(f"{year}-12-01") + pd.Timedelta(days=i),
                f"u/cross/{year}/{i}",
            ))
    pd.DataFrame(rows).to_parquet(snapshot_dir / "canonical_fights.parquet", index=False)
    pd.DataFrame(columns=[
        "fight_url", "event_name", "event_date", "bout_string",
        "round_num", "fighter", "kd", "sig_str_landed", "sub_att", "ctrl_seconds",
    ]).to_parquet(snapshot_dir / "canonical_rounds.parquet", index=False)


def test_run_scores_the_public_resume_after_the_division_columns_exist(tmp_path: Path):
    """The persisted board must equal the division-bar pricing, not the fallback."""
    from ratings.rate_snapshot import _source_fights_for_public_resume
    from ratings.rate_snapshot import run as run_ratings

    snap = tmp_path / "snap"
    snap.mkdir()
    _synthetic_snapshot(snap)
    run_ratings(snap, min_fights=1, scope="ufc")

    current = pd.read_parquet(snap / "ratings_current.parquet")
    assert "career_division" in current.columns
    divisions = _division_labels(current)
    assert divisions is not None, "the resume was scored before divisions existed"

    history = pd.read_parquet(snap / "ratings_history_whr.parquet")
    fights = _source_fights_for_public_resume(snap, "ufc")

    def _quality(**kwargs) -> pd.Series:
        led = title_quality_ledger(fights, history, reference="contender:60", **kwargs)
        return led.set_index("fighter")["public_legacy_title_quality"]

    stored = current.set_index("fighter")["public_legacy_title_quality"]
    by_division = _quality(divisions=divisions)
    sport_wide = _quality()

    champion = by_division.idxmax()
    # Guard against a vacuous pass: the fixture must make the two bars differ.
    assert by_division[champion] > 2 * sport_wide.get(champion, 0.0)
    assert stored[champion] == pytest.approx(by_division[champion], rel=1e-9)
    assert stored[champion] != pytest.approx(sport_wide[champion], rel=1e-9)
