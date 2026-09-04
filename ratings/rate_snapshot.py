"""Build the lean rating core and its explicitly separate audit layers.

The rating layer retains causal Glicko-2 (``canonical``) as a diagnostic and
uses retrospective Whole-History Rating (``whr``) for the published skill
trajectory. Production WHR grades a decided result by its staged method score;
setting ``WHR_WINNER_SCORE_COL`` to ``None`` restores binary W/L/D scoring.
``method`` is retained as a zero-extra-pass research diagnostic.
Side-specific performance/integrity sleeves and the era premium are not
production ratings: they either fail to define one paired likelihood or add a
scenario assumption that bout outcomes cannot identify.

The skill career functional is Symon Career Skill Mass: the sum of positive
annual WHR skill above that year's global contender line, with at most one
contribution per active year -- a skill *diagnostic*, not the public board.
The published all-time board is Public Legacy Score: exposure-adjusted career
skill mass plus auditable championship and contender-win ledgers. Prime is the
fixed ten-year WHR window.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

# Package import shim: let `python ratings/rate_snapshot.py` work as well as `-m`.
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratings.glicko2_engine import DEFAULT_TAU, RatingEngine
from ratings.dominance import per_fight_dominance, per_fighter_dominance
from ratings.constants import rename_rating_columns
from ratings.diagnostics import (
    calibration_residual_rows,
    division_entropy_rows,
)
from ratings.division_resume import division_resume_rows, primary_division_rows
from ratings.integrity_adjustment import build_integrity_appearances
from ratings.appearance_context import peak_appearance_quality
from ratings.symon_score import (
    DEFAULT_CAREER_REFERENCE,
    DEFAULT_DIVISION_REFERENCE,
    DEFAULT_HINGE_SPREAD_FRACTION,
    career_skill_mass,
    parse_reference,
    symon_prime_score,
)
from ratings.gender import GENDER_GAUGE_NOTE, GENDER_LABEL, partition_by_gender
from ratings.legacy_resume import _division_labels, public_legacy_score_rows
from ratings.whr import production_score_kwargs, project_age_rating, run_whr
from ratings.age import load_birth_dates
from ratings.performance_adjustment import build_performance_appearances
from ratings.performance_adjustment import _group_bounds, normalize_division_label
from loaders.integrity_flags import (
    INTEGRITY_COLUMNS,
    build_integrity_flags,
    confirmed_counts,
)
from loaders.odds_loader import has_odds_artifact, load_odds_lines
from ratings.rules_era import RULES_ERA_WEIGHT, label_rules_era, rules_era_factor
from ratings.scope import (  # noqa: F401
    DEFAULT_PUBLISHED_SCOPE,
    SCOPE_ARTIFACT,
    SCOPES,
    UFC_ONLY,
    merge_scope,
    scope_guard,
    scope_sources,
)
from loaders.career_coverage import coverage_summary, is_coverage_symmetric
from loaders.combined_fights import (
    load_combined_fights,
    write_combined_fights,
)
from loaders.majors_scope import CAREER_COVERAGE_ARTIFACT
from loaders.ufcstats_loader import METHOD_SCORES


# ---------------------------------------------------------------------------
# Helpers


def _ensure_integrity_columns(fights: pd.DataFrame) -> pd.DataFrame:
    out = fights.copy()
    for col in INTEGRITY_COLUMNS:
        if col == "fight_url":
            continue
        if col not in out.columns:
            out[col] = False if col in {"ped_confirmed", "is_dq", "missed_weight"} else None
    for col in ("ped_confirmed", "is_dq", "missed_weight"):
        out[col] = out[col].fillna(False).astype(bool)
    return out


def _iter_event_bouts(fights: pd.DataFrame, columns: list[str]):
    """Yield ``(event_date, event_name, bouts)`` per event from column arrays.

    A ``groupby(...).to_dict("records")`` per event costs more than the Glicko
    arithmetic it feeds once the fight table carries tens of thousands of
    events, so the frame is converted to arrays once and sliced.
    """
    f = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    arrays = {c: f[c].to_numpy() for c in columns}
    dates = f["event_date"].to_numpy()
    names = f["event_name"].to_numpy()
    for lo, hi in zip(*_group_bounds(f["event_date"], f["event_name"])):
        bouts = [{c: arrays[c][k] for c in columns} for k in range(lo, hi)]
        yield pd.Timestamp(dates[lo]), names[lo], bouts


def _run_canonical_engine(fights: pd.DataFrame, tau: float) -> RatingEngine:
    engine = RatingEngine(tau=tau)
    columns = ["fighter_a", "fighter_b", "winner", "is_draw", "method_score_winner"]
    for event_date, event_name, bouts in _iter_event_bouts(fights, columns):
        engine.process_event(event_date, event_name, bouts)
    return engine


def _career_columns(table: pd.DataFrame) -> pd.DataFrame:
    """Give the public career table its stable snapshot column names."""
    return table.rename(
        columns={
            c: ("symon_career_skill_mass" if c == "score" else f"symon_career_{c}")
            for c in table.columns
            if c != "fighter"
        }
    )


def _career_coverage_summary(snapshot_dir: Path) -> dict:
    """Read the coverage audit the majors staging wrote, if it is there.

    Absent on a snapshot staged before the audit existed. Reported as such
    rather than defaulted to "symmetric", because a silent pass is exactly how
    the two-rule corpus survived four board repairs.
    """
    path = Path(snapshot_dir) / CAREER_COVERAGE_ARTIFACT
    if not path.exists():
        return {"status": "not measured; stage the majors scope to produce it"}
    summary = coverage_summary(pd.read_parquet(path))
    summary["symmetric"] = bool(is_coverage_symmetric(summary))
    return summary


def _require_career_coverage(snapshot_dir: Path, scope: str) -> dict:
    """Refuse a majors fit whose whole-career coverage was not proved."""
    summary = _career_coverage_summary(snapshot_dir)
    if "majors" not in scope_sources(scope):
        return summary
    if "status" in summary:
        raise ValueError(
            "the majors scope requires a career-coverage audit; "
            "run stage_majors_scope before rating"
        )
    if not summary.get("symmetric", False):
        raise ValueError(
            "the majors scope has asymmetric whole-career coverage; "
            "run build_sherdog_careers.py before rating"
        )
    return summary


def _source_fights_for_public_resume(snapshot_dir: Path, scope: str) -> pd.DataFrame:
    fights, _ = load_combined_fights(snapshot_dir, scope=scope, label="resume")
    if "is_excluded" in fights.columns:
        fights = fights[~fights["is_excluded"].fillna(False).astype(bool)].copy()
    return fights


def refresh_career_columns(
    snapshot_dir: Path,
    *,
    reference: str | float = DEFAULT_CAREER_REFERENCE,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
) -> dict[str, object]:
    """Recompute career columns without changing what the persisted fit saw."""
    snapshot_dir = Path(snapshot_dir)
    metadata_path = snapshot_dir / "rating_run.json"
    metadata: dict[str, object] = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    fitted_scope = metadata.get("scope")
    if fitted_scope and str(fitted_scope) != str(scope):
        raise ValueError(
            "career-only refresh scope does not match the persisted WHR fit: "
            f"requested {scope!r}, fitted {fitted_scope!r}"
        )
    history = pd.read_parquet(snapshot_dir / "ratings_history_whr.parquet")
    current_path = snapshot_dir / "ratings_current.parquet"
    current = pd.read_parquet(current_path)
    current = current.drop(
        columns=[
            c for c in current.columns
            if (
                c.startswith("symon_career_")
                or c.startswith("symon_peak_")
                or c.startswith("public_legacy_")
            )
        ],
        errors="ignore",
    )
    # This path reads a persisted snapshot, so the division columns are already
    # present and the division bar is available without any reordering.
    current = current.merge(
        _career_columns(
            career_skill_mass(
                history,
                reference=reference,
                divisions=_division_labels(current),
                division_reference=DEFAULT_DIVISION_REFERENCE,
                hinge_spread_fraction=DEFAULT_HINGE_SPREAD_FRACTION,
            )
        ),
        on="fighter",
        how="left",
    )
    appearances_path = snapshot_dir / "performance_appearances.parquet"
    appearances = pd.read_parquet(appearances_path) if appearances_path.exists() else pd.DataFrame()
    source_fights = _source_fights_for_public_resume(snapshot_dir, scope)
    current = current.merge(
        public_legacy_score_rows(
            current,
            appearances,
            source_fights=source_fights,
            history=history,
            reference=reference,
        ),
        on="fighter",
        how="left",
    )
    current = current.sort_values(
        ["mu_canonical", "fighter"], ascending=[False, True]
    ).reset_index(drop=True)
    current.to_parquet(current_path, index=False)

    metadata.update(
        {
            "scope": scope,
            "career_reference": str(reference),
            "age_drift": True,
            "rated_bouts": int(metadata.get("rated_bouts", len(source_fights))),
            "birth_dates": int(len(load_birth_dates(snapshot_dir))),
            "history_rows": int(len(history)),
            "current_fighters": int(len(current)),
            "events_processed": int(history["event_date"].nunique()),
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def merge_crossorg_fights(
    fights: pd.DataFrame,
    snapshot_dir: Path,
    *,
    enabled: bool,
    label: str = "rate",
) -> pd.DataFrame:
    """Back-compatible entry point for the FightMatrix cross-org scope.

    Kept because ``--experimental-crossorg`` is a documented flag, but it is one
    scope among several now: see :mod:`ratings.scope`, which is where the scope
    registry, the missing-artifact error and the dedupe guard live.
    """
    return merge_scope(
        fights, snapshot_dir,
        scope="fightmatrix" if enabled else UFC_ONLY,
        label=label,
    )


def attach_bout_weights(
    fights: pd.DataFrame,
    *,
    rules_era_weight: float = RULES_ERA_WEIGHT,
) -> pd.DataFrame:
    """Set the one shared likelihood weight each bout contributes.

    Two factors, and both are the same number on both sides -- WHR needs a
    single bout likelihood, so a side-specific weight is not admissible here.

    ``org_weight``
        1.0 in production. The column is read rather than hard-coded so the
        research sweep can vary it without a second code path; see the
        org-weight note in :func:`run` for why production never does.
    ``rules_era``
        how far a UFC bout fought before the unified rules is allowed to move a
        rating. Defaults to 1.0 -- full admission -- and is a measured quantity,
        not an asserted one. See :mod:`ratings.rules_era`.
    """
    out = fights.copy()
    ow = pd.to_numeric(out.get("org_weight", 1.0), errors="coerce")
    ow = ow.fillna(1.0) if hasattr(ow, "fillna") else pd.Series(1.0, index=out.index)
    weight = ow * rules_era_factor(out, weight=rules_era_weight)
    out["weight_a"] = weight
    out["weight_b"] = weight
    return out


# The name this was called before the rules-era term joined the org weight.
_attach_org_only_weights = attach_bout_weights


def _attach_months_inactive(
    current: pd.DataFrame, snapshot_max_date: pd.Timestamp
) -> pd.DataFrame:
    """Measure recency for the Current eligibility rule."""
    out = current.copy()
    last = pd.to_datetime(out.get("last_event_date"), errors="coerce")
    months = (pd.Timestamp(snapshot_max_date) - last).dt.days / 30.4375
    out["months_inactive"] = months.clip(lower=0.0).round(2)
    return out


def _attach_record(current: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    """Attach each fighter's rated win/loss/draw record.

    The board already carried an appearance count, which cannot distinguish a
    fighter who has never lost from one who splits every card. That difference
    is exactly what decides how far a Bradley--Terry rating can travel, so it
    belongs beside the rating.
    """
    for col in ("wins", "losses", "draws"):
        current[col] = 0
    if fights is None or fights.empty:
        return current
    sides = [
        fights[[side, "winner", "is_draw"]].rename(columns={side: "fighter"})
        for side in ("fighter_a", "fighter_b")
    ]
    long = pd.concat(sides, ignore_index=True, sort=False).dropna(subset=["fighter"])
    long["is_draw"] = long["is_draw"].fillna(False).astype(bool)
    long["win"] = long["winner"].eq(long["fighter"]) & ~long["is_draw"]
    long["loss"] = long["winner"].notna() & ~long["winner"].eq(long["fighter"]) & ~long["is_draw"]
    record = long.groupby("fighter").agg(
        wins=("win", "sum"), losses=("loss", "sum"), draws=("is_draw", "sum"),
    ).reset_index()
    out = current.drop(columns=["wins", "losses", "draws"]).merge(
        record, on="fighter", how="left")
    for col in ("wins", "losses", "draws"):
        out[col] = out[col].fillna(0).astype(int)
    return out


# Divisions whose bare label is used by men's promotions only. A women's bout
# billed with one of these is a RIZIN openweight, of which this corpus holds
# six; the men's component carries 7,768. The rule below is a majority, so that
# margin decides it without a hand-maintained exception list.
_MENS_ONLY_BILLING = frozenset({
    "Light Heavyweight", "Heavyweight", "Middleweight", "Welterweight", "Lightweight",
})


def _female_by_bout_graph(appearances: pd.DataFrame) -> set[str]:
    """Fighters the corpus shows to be women, from the shape of the bout graph.

    Gender cannot be read off one bout's billing. Measured on the 2026-08-13
    snapshot, only 247 of 1,752 women carry a "Women's ..." label on their most
    recent bout: the Sherdog majors rows arrive with ``weight_class`` null on
    2,606 of the 3,938 women's bouts, and unprefixed ("Flyweight",
    "108lb Catchweight") on most of the rest. The last-bout rule therefore
    called 1,503 women men, and a career UNION rule does not fix it -- it raises
    the number of bouts the corpus believes were fought between a man and a
    woman from 663 to 740, because it converts one side of a bout and not the
    other.

    What does fix it is that the two populations are **disjoint components of
    the bout graph**: 0 of 80,697 bouts and 0 shared opponents join them. So a
    component that fights women's bouts contains only women, and the label
    propagates with certainty rather than by inference. The majority test on
    gendered billings guards the one way this could go wrong -- a genuine
    intergender bout in some later snapshot merging the two -- without
    hard-coding names: on this snapshot the men's component is 0 women's-billed
    against 7,768 men's-billed, and the women's is 929 against 6.
    """
    adjacency: dict[str, set[str]] = defaultdict(set)
    for left, right in zip(appearances["fighter_a"], appearances["fighter_b"]):
        if isinstance(left, str) and isinstance(right, str):
            adjacency[left].add(right)
            adjacency[right].add(left)

    component: dict[str, int] = {}
    total = 0
    for start in adjacency:
        if start in component:
            continue
        queue = deque([start])
        component[start] = total
        while queue:
            node = queue.popleft()
            for neighbour in adjacency[node]:
                if neighbour not in component:
                    component[neighbour] = total
                    queue.append(neighbour)
        total += 1

    division = appearances["recent_division"].fillna("").astype(str)
    womens = division.str.startswith("Women's")
    mens = division.isin(_MENS_ONLY_BILLING)
    tally: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for side, is_w, is_m in zip(appearances["fighter_a"], womens, mens):
        cid = component.get(side)
        if cid is None:
            continue
        tally[cid][0] += int(is_w)
        tally[cid][1] += int(is_m)

    female_components = {cid for cid, (w, m) in tally.items() if w > m}
    return {name for name, cid in component.items() if cid in female_components}


def _attach_recent_division_gender(current: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    """Attach each fighter's most recent UFC division and inferred gender split."""
    if fights is None or fights.empty:
        current["recent_division"] = pd.NA
        current["gender"] = pd.NA
        return current
    f = fights[["event_date", "event_name", "fighter_a", "fighter_b", "weight_class"]].copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["recent_division"] = f["weight_class"].map(normalize_division_label)
    a = f[["event_date", "event_name", "recent_division", "fighter_a"]].rename(columns={"fighter_a": "fighter"})
    b = f[["event_date", "event_name", "recent_division", "fighter_b"]].rename(columns={"fighter_b": "fighter"})
    recent = (
        pd.concat([a, b], ignore_index=True, sort=False)
        .dropna(subset=["fighter"])
        .sort_values(["fighter", "event_date", "event_name"])
        .groupby("fighter", as_index=False)
        .last()[["fighter", "recent_division"]]
    )
    female = _female_by_bout_graph(f)
    recent["gender"] = np.where(recent["fighter"].isin(female), "F", "M")
    return current.merge(recent, on="fighter", how="left")


def _gender_isolated_prime_score(
    whr_history: pd.DataFrame,
    current: pd.DataFrame,
) -> pd.DataFrame:
    """Score Prime independently inside each disconnected bout component.

    The empirical-Bayes step estimates a cohort mean and between-fighter
    variance. Pooling the men's and women's components lets evidence from a
    graph with no connecting bouts change the other graph's scores. The public
    boards are separate for exactly this reason, so their shrinkage cohorts must
    be separate too.
    """
    pieces: list[pd.DataFrame] = []
    for population in partition_by_gender(current).values():
        if population is None or population.empty:
            continue
        fighters = set(population["fighter"].dropna())
        part = symon_prime_score(whr_history[whr_history["fighter"].isin(fighters)])
        if not part.empty:
            pieces.append(part)
    if not pieces:
        return symon_prime_score(whr_history.iloc[0:0])
    return pd.concat(pieces, ignore_index=True, sort=False)


def _print_one_board(
    population: pd.DataFrame,
    *,
    rating_col: str,
    extra_cols: list[str],
    title: str,
    n: int,
    min_fights: int,
) -> None:
    eligible = population[population["rating_periods"].fillna(0) >= min_fights].copy()
    eligible = eligible.dropna(subset=[rating_col])
    if eligible.empty:
        return
    cols = ["fighter", rating_col, *[c for c in extra_cols if c in eligible.columns]]
    out = eligible.sort_values(rating_col, ascending=False).head(n)[cols]
    out = rename_rating_columns(out)
    print(f"\n=== {title} ===")
    print(out.to_string(index=False))


def _print_top(
    current: pd.DataFrame,
    *,
    rating_col: str,
    extra_cols: list[str],
    title: str,
    n: int = 20,
    min_fights: int = 3,
) -> None:
    """Print one headline board per bout-graph component, men's first.

    Every board printed here used to be mixed, which published the unidentified
    men/women gauge as a rank -- and it published it on **Prime** as well as on
    the career and legacy boards. Prime is where it bites hardest, because Prime
    reads ``mu_whr`` directly with no exposure factor and no resume ledger, so
    nothing downstream damps the gauge. See :mod:`ratings.gender`.
    """
    partition = partition_by_gender(current)
    for gender, population in partition.items():
        if population is None or population.empty:
            continue
        suffix = "" if len(partition) == 1 else f" [{GENDER_LABEL[gender]}]"
        _print_one_board(
            population,
            rating_col=rating_col,
            extra_cols=extra_cols,
            title=f"{title}{suffix}",
            n=n,
            min_fights=min_fights,
        )
    if "F" in partition and not partition["F"].empty:
        print(f"\n  {GENDER_GAUGE_NOTE}")


# ---------------------------------------------------------------------------
# Main


def run(
    snapshot_dir: Path,
    tau: float = DEFAULT_TAU,
    min_fights: int = 3,
    *,
    mdabbert_csv: Path | None = None,
    include_experimental_crossorg: bool = False,
    experimental_org_weight: bool = False,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
    career_reference: str | float = DEFAULT_CAREER_REFERENCE,
) -> dict:
    snapshot_dir = Path(snapshot_dir).resolve()
    rounds = pd.read_parquet(snapshot_dir / "canonical_rounds.parquet")
    if include_experimental_crossorg:
        if scope != DEFAULT_PUBLISHED_SCOPE:
            raise ValueError(
                "include_experimental_crossorg is a deprecated alias for scope='fightmatrix'; "
                "do not supply both"
            )
        scope = "fightmatrix"
    career_coverage = _require_career_coverage(snapshot_dir, scope)
    # One authoritative fight table, written at every corpus the snapshot
    # staged, then filtered to the scope this run is allowed to rate. The
    # artifact used to be written at the *run's* scope, so a UFC-only run
    # overwrote the whole-sport table with a narrower one and the next reader
    # inherited it without being told.
    write_combined_fights(snapshot_dir, label="rate")
    fights, combined_summary = load_combined_fights(snapshot_dir, scope=scope, label="rate")
    fights["rules_era"] = label_rules_era(fights)
    # No organisation weight. ``compute_fight_weights`` prices a non-UFC bout by
    # both participants' UFC-anchored caliber percentiles, so a 2003 PRIDE bout
    # would be weighted by what those two fighters went on to do years later --
    # future information inside historical evidence. Setting every bout to 1.0
    # dissolves that by construction rather than patching it: there is no weight
    # derived from future careers because there is no weight, and promotion
    # strength becomes an output of the joint fit, read off the fighters who
    # crossed. Measured cost of the removal: none. On held-out UFC bouts with
    # both fighters covered, the cross-org gain is -0.01896 [-0.02376, -0.01397]
    # log-loss weighted and byte-identical unweighted for the Glicko filters,
    # which never read the column at all.
    if not experimental_org_weight:
        staged = pd.to_numeric(fights["org_weight"], errors="coerce").fillna(1.0)
        if not np.allclose(staged.to_numpy(dtype=float), 1.0):
            print(f"[rate] discarding staged org_weight on "
                  f"{int((staged != 1.0).sum()):,} bouts; the joint fit is unweighted")
        fights["org_weight"] = 1.0

    fights["event_date"] = pd.to_datetime(fights["event_date"])
    if "method_class" in fights.columns:
        recalculated_method_scores = fights["method_class"].map(METHOD_SCORES)
        fights["method_score_winner"] = recalculated_method_scores.combine_first(
            pd.to_numeric(fights.get("method_score_winner"), errors="coerce")
        )
    fights = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Integrity flags (PED + DQ + missed-weight)
    integrity = build_integrity_flags(fights, mdabbert_csv=mdabbert_csv)
    # Merge flags onto the fight rows for the audit layers and exclusions.
    fights = fights.drop(columns=[c for c in INTEGRITY_COLUMNS if c != "fight_url" and c in fights.columns], errors="ignore")
    fights = fights.merge(integrity, on="fight_url", how="left")
    fights = _ensure_integrity_columns(fights)

    # Drop excluded bouts before rating. Keep them for audit if present.
    rated_fights = fights[~fights["is_excluded"]].copy() if "is_excluded" in fights.columns else fights.copy()

    # ------------------------------------------------------------------
    # Canonical + method base engine (one pass, two ratings)
    base_engine = _run_canonical_engine(rated_fights, tau=tau)
    history = base_engine.history_df()
    current = base_engine.current_table().drop(
        columns=["peak_mu_canonical", "peak_mu_method"],
        errors="ignore",
    )
    fight_counts = history.groupby("fighter").size().rename("rating_periods").reset_index()
    current = current.merge(fight_counts, on="fighter", how="left")

    # ------------------------------------------------------------------
    # Audit layers. These explain source coverage, method/dominance and policy
    # questions, but they do not mutate the production skill likelihood.
    integrity_app = build_integrity_appearances(rated_fights)

    odds_lines = load_odds_lines(snapshot_dir) if has_odds_artifact(snapshot_dir) else pd.DataFrame()
    # Judge scorecards feed the decision "round win gap" dominance component.
    scorecards_path = snapshot_dir / "datalab_scorecards.parquet"
    scorecards = pd.read_parquet(scorecards_path) if scorecards_path.exists() else None
    fight_dom = per_fight_dominance(rounds, rated_fights, scorecards=scorecards)
    fighter_dom = per_fighter_dominance(fight_dom, rated_fights)

    perf_app = build_performance_appearances(
        rated_fights,
        history,
        odds_lines if not odds_lines.empty else None,
        fight_dominance=fight_dom,
    )

    # Persist appearance audit frames.
    integrity_app.to_parquet(snapshot_dir / "integrity_appearances.parquet", index=False)
    perf_app.to_parquet(snapshot_dir / "performance_appearances.parquet", index=False)

    # ------------------------------------------------------------------
    # WHR is the retrospective estimator. Production scoring grades the winner
    # by the staged method score and treats draws symmetrically. It receives one shared source weight per bout and no
    # implicit quality-score column. Era is neutral by default because a common
    # additive era term cancels from every within-era Bradley--Terry matchup.
    birth_dates = load_birth_dates(snapshot_dir)
    whr_fights = _attach_org_only_weights(rated_fights)
    whr_history = run_whr(
        whr_fights,
        birth_dates=birth_dates,
        age_drift=True,
        **production_score_kwargs(whr_fights),
    )
    drift_profile = whr_history.attrs.get("age_drift_elo_per_year")
    whr_current = (
        whr_history.sort_values(["fighter", "event_date"])
        .groupby("fighter", sort=False)
        .tail(1)[["fighter", "event_date", "mu_whr"]]
        .rename(columns={"event_date": "whr_last_event_date"})
        .reset_index(drop=True)
    )
    snapshot_max_date = rated_fights["event_date"].max()
    whr_current["mu_whr_age_activity_adjusted"] = [
        project_age_rating(
            float(row.mu_whr),
            last_date=row.whr_last_event_date,
            target_date=snapshot_max_date,
            birth_date=birth_dates.get(str(row.fighter)),
            drift_elo_per_year=drift_profile,
        )
        for row in whr_current.itertuples(index=False)
    ]
    whr_current["whr_age_inactivity_adjustment"] = (
        whr_current["mu_whr_age_activity_adjusted"] - whr_current["mu_whr"]
    )
    whr_history.to_parquet(snapshot_dir / "ratings_history_whr.parquet", index=False)
    current = current.merge(whr_current, on="fighter", how="left")

    current = _attach_record(current, rated_fights)
    current = _attach_recent_division_gender(current, rated_fights)

    # Prime reads only WHR history, but its empirical-Bayes cohort must follow
    # the same disconnected-component boundary as every published board. Score
    # it after gender is attached so one component cannot move the other.
    prime = _gender_isolated_prime_score(whr_history, current)
    current = current.merge(
        prime.rename(
            columns={
                c: ("symon_prime_score" if c == "score" else f"symon_prime_{c}")
                for c in prime.columns
                if c != "fighter"
            }
        ),
        on="fighter",
        how="left",
    )

    current = _attach_months_inactive(current, snapshot_max_date)

    # Opponent context per appearance. Division boards score a fighter inside
    # one weight class from it; the latent skill model does not read it.
    peak_quality = peak_appearance_quality(rated_fights, history)

    # Division-context all-time rows. These are the correct source for
    # divisional leaderboards; they use only bouts fought in that division and
    # shrink short title cameos toward the divisional pool.
    division_resume = division_resume_rows(whr_history, peak_quality)
    division_resume.to_parquet(snapshot_dir / "division_resume.parquet", index=False)
    current = current.drop(
        columns=[
            "primary_division", "primary_division_share", "primary_division_reliability",
            "career_division", "career_division_reliability",
            "current_division", "current_division_reliability",
        ],
        errors="ignore",
    )
    current = current.merge(primary_division_rows(division_resume), on="fighter", how="left")

    # Career Skill Mass MUST be scored after career_division and gender exist,
    # for the same reason the public resume must: without the labels the bar is
    # struck sport-wide, across divisions whose levels are not mutually
    # identified, and eleven of the top hundred score exactly zero. See the note
    # above symon_score.DEFAULT_DIVISION_REFERENCE. This call used to sit ~35
    # lines above, before the division columns were attached.
    current = current.merge(
        _career_columns(
            career_skill_mass(
                whr_history,
                reference=career_reference,
                divisions=_division_labels(current),
                division_reference=DEFAULT_DIVISION_REFERENCE,
                hinge_spread_fraction=DEFAULT_HINGE_SPREAD_FRACTION,
            )
        ),
        on="fighter",
        how="left",
    )

    # The public resume MUST be scored after career_division and gender exist.
    #
    # legacy_resume._division_labels returns None when career_division is absent,
    # and title_quality_ledger then silently prices every title win against the
    # sport-wide contender line instead of the division line. It does not raise:
    # the divisions argument is optional, so the intended bar just never runs.
    #
    # This call used to sit ~30 lines above, before the division columns were
    # attached, so the published board was built on the sport-wide bar the
    # comment above TITLE_QUALITY_SCALE explicitly rejects. Measured on
    # 2026-08-13 that under-priced exactly the divisions it was supposed to
    # protect -- Zhang Weili 8.2x, Shevchenko 4.3x, Demetrious Johnson 3.0x --
    # and it put Matt Hughes above Volkanovski on title resume, reversed once
    # each is priced against their own division.
    #
    # refresh_career_columns() reads a persisted snapshot that already has the
    # division columns, so it always used the division bar. The two paths
    # therefore disagreed on the same snapshot. Keep this call last.
    current = current.merge(
        public_legacy_score_rows(
            current,
            perf_app,
            source_fights=rated_fights,
            history=whr_history,
            reference=career_reference,
        ),
        on="fighter",
        how="left",
    )

    # ------------------------------------------------------------------
    # Integrity counts
    counts = confirmed_counts(integrity)
    current = current.merge(counts, on="fighter", how="left")
    for col in ("ped_confirmed_fights", "dq_wins", "missed_weight_wins"):
        if col not in current.columns:
            current[col] = 0
        current[col] = current[col].fillna(0).astype(int)

    # 203 fighters tie on mu_canonical (mostly unrated debutants at the 1500
    # default), and sort_values defaults to a non-stable quicksort, so two
    # identical runs used to emit byte-different row orders. Tie-break on the
    # name so a rebuild is reproducible and can be diffed against its inputs.
    current = current.sort_values(
        ["mu_canonical", "fighter"], ascending=[False, True]
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Persist
    history.to_parquet(snapshot_dir / "ratings_history.parquet", index=False)
    current.to_parquet(snapshot_dir / "ratings_current.parquet", index=False)

    # Audit exports.
    ped_audit_cols = [
        "fight_url", "event_date", "event_name", "fighter_a", "fighter_b",
        "winner", "ped_flagged_fighter", "ped_confirmation_detail",
    ]
    ped_audit = fights[fights["ped_confirmed"]].loc[:, [c for c in ped_audit_cols if c in fights.columns]]
    ped_audit.to_csv(snapshot_dir / "ped_confirmed_bouts.csv", index=False)

    mw_audit_cols = [
        "fight_url", "event_date", "event_name", "fighter_a", "fighter_b",
        "winner", "missed_weight_fighter", "missed_weight_source", "weight_class",
    ]
    mw_audit = fights[fights["missed_weight"]].loc[:, [c for c in mw_audit_cols if c in fights.columns]]
    mw_audit.to_csv(snapshot_dir / "missed_weight_bouts.csv", index=False)

    fight_dom.to_parquet(snapshot_dir / "fight_dominance.parquet", index=False)
    fighter_dom.to_parquet(snapshot_dir / "fighter_dominance.parquet", index=False)

    # Build-time diagnostic tables. The notebook reads these directly.
    fighters_path = snapshot_dir / "canonical_fighters.parquet"
    fighters = pd.read_parquet(fighters_path) if fighters_path.exists() else pd.DataFrame()
    calibration_residual_rows(history, rated_fights, fighters).to_parquet(
        snapshot_dir / "calibration_residuals.parquet",
        index=False,
    )
    division_entropy_rows(history, rated_fights).to_parquet(
        snapshot_dir / "division_entropy.parquet",
        index=False,
    )

    # Remove artifacts a previous pipeline version wrote that this one does not,
    # so a rebuilt snapshot never carries a stale file alongside fresh ones.
    for legacy in (
        "ratings_history_ped_adjusted.parquet",
        "ratings_history_odds_adjusted.parquet",
        "odds_adjustment_distribution.parquet",
        # Retired 2026-08-19: each cost a full smoother pass and nothing read it.
        "ratings_history_whr_integrity.parquet",
        "ratings_history_whr_performance.parquet",
        "ratings_history_whr_integrity_performance.parquet",
        "ratings_history_method_integrity.parquet",
        "ratings_history_method_performance.parquet",
        "ratings_history_method_integrity_performance.parquet",
        "sleeve_attribution.parquet",
    ):
        legacy_path = snapshot_dir / legacy
        if legacy_path.exists():
            legacy_path.unlink()

    # ------------------------------------------------------------------
    # Reporting
    print(f"tau used: {tau}")
    print(f"events processed: {whr_history['event_date'].nunique()}")
    print(f"published WHR appearance rows: {len(whr_history)}")
    print(f"unique fighters rated: {len(current)}")
    print(
        f"integrity flags  PED={int(integrity['ped_confirmed'].fillna(False).sum())} "
        f" DQ={int(integrity['is_dq'].fillna(False).sum())} "
        f" missed_weight={int(integrity['missed_weight'].fillna(False).sum())}"
    )
    cov_rows = int((odds_lines.get('odds_data_quality', pd.Series(dtype=object)).eq('ok')).sum()) if not odds_lines.empty else 0
    print(f"odds-covered fights (ok-quality rows): {cov_rows}")

    print(
        "headline = Public Legacy Score: exposure-adjusted Career Skill Mass "
        "plus a transparent championship resume ledger; raw Career Skill Mass "
        "and Prime are separate diagnostics."
    )
    _print_top(
        current,
        rating_col="symon_career_skill_mass",
        extra_cols=[
            "symon_career_active_years",
            "symon_career_contributing_years",
            "symon_career_peak_year_excess",
            "symon_prime_score",
            "career_division",
            "rating_periods",
        ],
        title="DIAGNOSTIC - Top 25 by Career Skill Mass",
        n=25, min_fights=0,
    )
    _print_top(
        current,
        rating_col="symon_prime_score",
        extra_cols=["symon_prime_raw_mean", "symon_prime_window_fights"],
        title="HEADLINE - Top 25 ten-year Prime (minimum 13 appearances)",
        n=25, min_fights=0,
    )
    _print_top(
        current,
        rating_col="public_legacy_score",
        extra_cols=[
            "public_legacy_skill_mass",
            "public_legacy_skill_score",
            "public_legacy_exposure_factor",
            "public_legacy_title_score",
            "public_legacy_resume_score",
            "public_legacy_contender_wins",
            "public_legacy_title_wins",
            "public_legacy_title_defenses",
            "public_legacy_title_win_divisions",
            "symon_prime_score",
            "career_division",
            "rating_periods",
        ],
        title="HEADLINE - Top 25 by Public Legacy Score",
        n=25, min_fights=0,
    )

    summary = {
        "scope": scope,
        "career_reference": str(career_reference),
        "age_drift": True,
        "rated_bouts": int(len(rated_fights)),
        "birth_dates": int(len(birth_dates)),
        # Keep the metadata invariant across a full fit and ``--career-only``.
        # The public career and board layers read WHR history; recording the
        # diagnostic Glicko row count here made the same snapshot report two
        # different values depending on which rebuild path ran last.
        "history_rows": int(len(whr_history)),
        "current_fighters": int(len(current)),
        "events_processed": int(whr_history["event_date"].nunique()),
        "combined_fights": combined_summary,
        # Whether the corpus gave every fighter the same coverage rule. A
        # low-loss Bradley-Terry record has no interior maximum, so its rating
        # grows with how many of the fighter's bouts the corpus happens to
        # hold; a run built on asymmetric coverage is reading that as skill.
        "career_coverage": career_coverage,
        "ped_confirmed_fights": int(integrity["ped_confirmed"].fillna(False).sum()),
        "dq_fights": int(integrity["is_dq"].fillna(False).sum()),
        "missed_weight_fights": int(integrity["missed_weight"].fillna(False).sum()),
        "odds_covered_fights": cov_rows,
    }
    (snapshot_dir / "rating_run.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", required=True, help="data/snapshots/<date>")
    parser.add_argument("--tau", type=float, default=DEFAULT_TAU)
    parser.add_argument("--min-fights", type=int, default=3, help="ranking eligibility threshold")
    parser.add_argument(
        "--reference",
        default=str(DEFAULT_CAREER_REFERENCE),
        help="Career bar: contender:N (published), count:N, mean, hybrid:L, or quantile.",
    )
    parser.add_argument(
        "--career-only",
        action="store_true",
        help="Recompute career columns from existing WHR history without refitting ratings.",
    )
    parser.add_argument(
        "--mdabbert-csv",
        type=str,
        default=None,
        help="Optional path to mdabbert ufc-master.csv for missed-weight cross-check.",
    )
    parser.add_argument(
        "--scope", default=None,
        help=(
            "Which bouts the rating may see. 'majors' is the roster-complete "
            "six-promotion Sherdog corpus; 'fightmatrix' is the bounded "
            "ranked-cohort crawl; 'all' admits both. They move the board in "
            "opposite directions, so nothing merges unless it is named. "
            "Combine explicitly: --scope majors,pre_unified."
        ),
    )
    parser.add_argument(
        "--experimental-crossorg",
        action="store_true",
        help="Deprecated alias for --scope fightmatrix.",
    )
    parser.add_argument(
        "--experimental-org-weight",
        action="store_true",
        help=(
            "Also consume the staged per-bout org_weight. Research only, and it "
            "leaks: those weights are derived from fighters' eventual UFC careers."
        ),
    )
    args = parser.parse_args()
    if args.experimental_crossorg and args.scope is not None:
        parser.error("--experimental-crossorg cannot be combined with --scope")
    args.scope = (
        "fightmatrix"
        if args.experimental_crossorg
        else (args.scope or DEFAULT_PUBLISHED_SCOPE)
    )
    if args.career_only:
        print(
            refresh_career_columns(
                Path(args.snapshot_dir).resolve(),
                reference=parse_reference(args.reference),
                scope=args.scope,
            )
        )
        return
    run(
        Path(args.snapshot_dir).resolve(),
        tau=args.tau,
        min_fights=args.min_fights,
        mdabbert_csv=Path(args.mdabbert_csv).resolve() if args.mdabbert_csv else None,
        include_experimental_crossorg=args.experimental_crossorg,
        experimental_org_weight=args.experimental_org_weight,
        scope=args.scope,
        career_reference=parse_reference(args.reference),
    )


if __name__ == "__main__":
    main()
