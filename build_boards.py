"""Generate the published and audit boards for one rating snapshot.

Writes the standard artifacts next to the snapshot (or to ``--out-dir`` when the
snapshot is finalized):

* ``integrity_ledger.parquet`` — every discounted appearance, with the reason
* ``integrity_discounted_board.parquet`` — the judgement board and its bill
* ``completeness_gated_board.parquet`` — the published men's board: ranks who
  can be ranked, abstains otherwise
* ``completeness_gated_board_women.parquet`` — the same board for the women's
  component, which is a separate ranking because the two never fight
* ``prime_board.parquet`` and ``prime_board_women.parquet`` — the ungated
  best-ten-year boards, kept as artifacts but no longer published: the
  elite-tested board answers the same question behind an evidence floor
* ``prime_elite_board.parquet`` and ``prime_elite_board_women.parquet`` — the
  same Prime score behind the elite-tested evidence floor
* ``current_board.parquet`` and ``current_board_women.parquet`` — current
  ratings for active fighters with a tested UFC record

"All-time" without a gender means the men's board. See ``GENDER_GAUGE_NOTE``.

Usage::

    python build_boards.py data/snapshots/2026-10-14
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from ratings import fights as F
from ratings.boards import (
    PUBLIC_BOARDS,
    PRIME_RATING_CANDIDATES,
    INTEGRITY_RATING_CANDIDATES, RATING_FLOOR_IS_UNRANKED,
    select_core_rating_col, select_integrity_rating_col, public_legacy_eligibility_override,
    UNRANKED_AT_FLOOR_STATUS,
    completeness_gated_board,
    elite_win_mass,
    integrity_discounted_board,
    integrity_ledger,
)
from ratings.constants import SUSTAINED_PEAK_MIN_FIGHTS  # board eligibility floor
from ratings.current_score import CURRENT_WINDOW_MONTHS
from ratings.era import ERA_COL, era_rated
from ratings.layoff import attach_opponent_layoff
from ratings.gender import (
    GENDER_GAUGE_NOTE,
    GENDER_SUFFIX,
    partition_by_gender,
)
from ratings.opponent_quality import (
    CONTENDER_LINE_MU,
    MIN_OPPONENT_UFC_BOUTS,
    MIN_QUALITY_WINS,
    best_elite_decade,
    quality_win_record,
)
from ratings.scope import DEFAULT_PUBLISHED_SCOPE, scope_sources
from ratings.divisions import MEN_LIMIT_LB
from ratings.division_legacy import class_board, class_ledger, class_scores
from ratings.divisions import division_column
import itertools

# d : published division label
# g : fighter gender label
# f : female-row mask

# The integrity debit is denominated in rating points, so keep that judgement
# on a base WHR point scale. This one is not shared: no other consumer applies a
# point-scale debit.
README_BOARD_BEGIN = "<!-- BOARD:TOP100:BEGIN -->"
README_BOARD_END = "<!-- BOARD:TOP100:END -->"
README_WOMEN_BEGIN = "<!-- BOARD:WOMEN10:BEGIN -->"
README_WOMEN_END = "<!-- BOARD:WOMEN10:END -->"
README_ELITE_PRIME_BEGIN = "<!-- BOARD:ELITEPRIME50:BEGIN -->"
README_ELITE_PRIME_END = "<!-- BOARD:ELITEPRIME50:END -->"
README_ELITE_PRIME_WOMEN_BEGIN = "<!-- BOARD:ELITEPRIMEWOMEN10:BEGIN -->"
README_ELITE_PRIME_WOMEN_END = "<!-- BOARD:ELITEPRIMEWOMEN10:END -->"
README_CURRENT_BEGIN = "<!-- BOARD:CURRENT30:BEGIN -->"
README_CURRENT_END = "<!-- BOARD:CURRENT30:END -->"
README_CURRENT_WOMEN_BEGIN = "<!-- BOARD:CURRENTWOMEN10:BEGIN -->"
README_CURRENT_WOMEN_END = "<!-- BOARD:CURRENTWOMEN10:END -->"
README_CLASS_BEGIN = "<!-- BOARD:CLASS:BEGIN -->"
README_CLASS_END = "<!-- BOARD:CLASS:END -->"
README_RELEASE_BEGIN = "<!-- PUBLICATION:RELEASE:BEGIN -->"
README_RELEASE_END = "<!-- PUBLICATION:RELEASE:END -->"

# The Current board answers the third published question -- "who is best right
# now" -- and since 2026-10-14 it answers it the way the All-time board answers
# "who had the best career": title, skill and résumé at the same weights, with
# the title and résumé ledgers summing only the last 18 months. The score is
# computed beside the All-time columns in ratings/current_score.py, which
# records the three owner decisions behind it: titles count, a UFC bout inside
# the window is required, and an unbeaten record's rating is capped at the best
# opponent it beat.
#
# It was a rating level until then, and that was the defect the owner named: a
# rating has no ceiling from above, so Movsar Evloev (20-0, best win rated 1,949
# going in) sat 2nd on 2,102 while Joshua Van, the flyweight champion with two
# defenses, sat 19th.
#
# Like the All-time score it has a floor at zero meaning "nothing in the window
# cleared the bar", so a fighter on it is told apart rather than ranked last.
#
# The window is stated policy, set by the owner at 18 months on 2026-09-03 and
# confirmed on 2026-10-14. It is not fitted. The other screens stay: 13 rated
# appearances and MIN_OPPONENT_UFC_BOUTS UFC bouts, the bar the Prime board
# applies to an opponent before a win over them counts.
CURRENT_BOARD_TOP = 30
CURRENT_MAX_MONTHS_INACTIVE = CURRENT_WINDOW_MONTHS
CURRENT_MIN_UFC_BOUTS = MIN_OPPONENT_UFC_BOUTS
CURRENT_SCORE_COL = PUBLIC_BOARDS["current"].score
CURRENT_SOURCE_COL = PUBLIC_BOARDS["current"].source
CURRENT_TESTED_LABEL = "UFC bouts"
CURRENT_RECENCY_COL = "months_since_ufc"

# Time away is charged where a win is PRICED, not here.
#
# An earlier version of this board discounted idle years itself. That was the
# right diagnosis in the wrong place: a layoff does not only make a fighter's
# current standing doubtful, it makes a win over them worth less, and every
# ledger that prices one needs to know. It lives in ratings/layoff.py as
# OPPONENT_LAYOFF_ELO_PER_TURNAROUND, reached through attach_opponent_layoff --
# the all-time title ledger, the contender resume and the Prime gate alike, not
# only here.
#
# It is NOT in the rating. Putting it in the WHR transition prior was built,
# measured and refused the same day: a symmetric prior satisfies "declined
# across this gap" by raising the earlier node, which lifted Sean Sherk's 1999
# rating from 1927 to 2124 and made the era skew worse (0.895 -> 0.813). See
# docs/DECISIONS.md.
#
# Charging it again on this board would post the same fact twice. Do not
# reinstate it.

# Prime answers a different question from the all-time board: not "what did this
# career amount to" but "how good was this fighter at their best". It is a
# rating level, so unlike the all-time score it has no zero floor meaning "no
# evidence" -- it is simply absent for anyone short of the appearance minimum,
# and must NOT be added to RATING_FLOOR_IS_UNRANKED.
PRIME_RATING_COL = PRIME_RATING_CANDIDATES[0]

# The elite-tested Prime board ranks the same Prime score behind a floor on
# PROVEN record inside the selected Prime window: at least MIN_QUALITY_WINS wins
# over opponents whose retrospective at-date rating clears the contender line
# AND whose final snapshot record contains enough UFC bouts to be well tested.
#
# Two simpler rules were built first and both failed on named fighters.
# Counting ranked-or-title bouts measures longevity, not difficulty: it seated
# Machida, Davis and Chandler on accumulated volume while withholding Makhachev
# and Topuria. Averaging the ten toughest opponents measures gatekeeping: a
# fighter who lost to ten elite opponents scored the same as one who beat them,
# so Roy Nelson (0-10) outranked Khabib and St-Pierre, and a 1950 bar excluded
# Jon Jones himself. Counting wins over a stated line does neither.
ELITE_PRIME_TOP = 50

# The elite board ranks elite-win mass -- qualifying wins multiplied by how far
# the fighter's peak level sat above the weakest qualifying level -- not the bare
# Prime level. A Prime score is a rate: it does not grow with the number of hard
# fights behind it, so ranking it put Ilia Topuria (5 qualifying wins) above
# Georges St-Pierre (11), and left Anderson Silva (11) below Vadim Nemkov (5).
# The product is extensive, so both halves count. It carries no tuning constant.
#
# The empirical-Bayes shrinkage already inside the Prime score cannot do this
# job. Between-fighter spread is 101.2 Elo against a median sampling variance of
# 33.96, so its lambda is 0.99+ for every fighter and it moves a qualifier's
# score by at most 2.9 Elo. It measures how noisy a fitted trajectory is; the
# question here is how much of it was tested.
#
# The discount is anchored at the weakest qualifying level, not the cohort mean.
# See ``evidence_weighted_score``: a mean anchor raises sub-mean fighters as
# evidence thins, which is backwards for a board.
ELITE_PRIME_RATING_COL = PUBLIC_BOARDS["prime"].score
ELITE_LEVEL_COL = PUBLIC_BOARDS["prime"].source

# The men's and women's boards are built and published SEPARATELY. The rule and
# the measurements behind it live in ``ratings/gender.py``, which every ranking
# surface in the project shares.


def _normalized_scope(scope: str) -> str:
    """Canonical text for comparing two equivalent scope specifications."""
    sources = scope_sources(scope)
    return ",".join(sources) if sources else "ufc"


def _validate_rating_scope(
    snapshot_dir: Path,
    requested_scope: str,
    *,
    required: bool = False,
) -> dict[str, object]:
    """Reject a board label that does not match the persisted rating run."""
    manifest_path = Path(snapshot_dir) / "rating_run.json"
    if not manifest_path.exists():
        if required:
            raise FileNotFoundError(
                f"cannot publish without the rating provenance manifest: {manifest_path}"
            )
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded_scope = manifest.get("scope")
    if not recorded_scope:
        raise ValueError(f"rating provenance manifest has no scope: {manifest_path}")
    if _normalized_scope(str(recorded_scope)) != _normalized_scope(requested_scope):
        raise ValueError(
            "requested board scope does not match the persisted rating scores: "
            f"requested {requested_scope!r}, rated {recorded_scope!r}"
        )
    return manifest


def _requested_core_rating_col(current: pd.DataFrame, requested: str | None) -> str:
    if requested is None:
        return select_core_rating_col(current)
    if "whr_integrity_performance" in requested:
        raise ValueError("retired whr_integrity_performance scores cannot be a core board")
    if requested not in current.columns:
        raise ValueError(f"requested core rating column is absent: {requested}")
    return requested


def _requested_integrity_rating_col(current: pd.DataFrame, requested: str | None) -> str:
    if requested is None:
        return select_integrity_rating_col(current)
    if requested not in INTEGRITY_RATING_CANDIDATES:
        raise ValueError(
            "the integrity debit is defined only for base WHR rating-point columns: "
            f"{', '.join(INTEGRITY_RATING_CANDIDATES)}"
        )
    if requested not in current.columns:
        raise ValueError(f"requested integrity rating column is absent: {requested}")
    return requested


def _elite_decade_map(snapshot_dir: Path) -> pd.DataFrame | None:
    """Fighter -> their best decade of beating contenders, and its level.

    Opponent strength is read from the same retrospective trajectory the board
    ranks, at the opponent's last appearance BEFORE the event -- the rule the
    contender résumé uses (``contender_resume_ledger``), so one win counts as a
    contender win in both places or in neither. It used to be read at the event
    itself, where the trajectory already carries that bout's result: a decisive
    win lowered the very rating it was priced at, and on the 2026-08-13 snapshot
    that kept Khabib Nurmagomedov and Cain Velasquez under the five wins Prime
    requires while the résumé counted five for each.

    Returns ``None`` when an input is missing, so a snapshot that cannot support
    the gate publishes no elite board rather than one withholding everybody.
    """
    snap = Path(snapshot_dir)
    appearances_path = snap / "performance_appearances.parquet"
    history_path = snap / "ratings_history_whr.parquet"
    combined_path = snap / "combined_fights.parquet"
    if not (appearances_path.exists() and history_path.exists() and combined_path.exists()):
        return None

    fights = pd.read_parquet(
        combined_path,
        columns=["fighter_a", "fighter_b", "source_corpus", "is_model_bout"],
    )
    ufc = fights[
        fights["source_corpus"].isin(["ufc", "pre_unified"])
        & fights["is_model_bout"].fillna(False).astype(bool)
    ]
    ufc_bouts = pd.concat([ufc["fighter_a"], ufc["fighter_b"]]).value_counts()

    appearances = pd.read_parquet(
        appearances_path,
        columns=[
            "fight_url", "fighter", "opponent", "event_date", "event_name", "is_winner",
        ],
    )
    # Era-adjusted (ratings.era), as the résumé reads it: the gate and the level are both read
    # against the opponent's and the fighter's own era.
    history = era_rated(pd.read_parquet(
        history_path, columns=["fighter", "event_date", "event_name", "mu_whr", ERA_COL]
    ))
    appearances["event_date"] = pd.to_datetime(appearances["event_date"])
    history["event_date"] = pd.to_datetime(history["event_date"])
    rated = (
        pd.merge_asof(
            appearances.reset_index().sort_values("event_date"),
            history.rename(columns={"fighter": "opponent", "mu_whr": "opponent_mu"})[
                ["opponent", "event_date", "opponent_mu"]
            ].sort_values("event_date"),
            on="event_date",
            by="opponent",
            allow_exact_matches=False,
        )
        .set_index("index")
        .sort_index()
    )
    if len(rated) != len(appearances) or rated.duplicated(["fight_url", "fighter"]).any():
        raise ValueError("elite Prime evidence must contain one row per fight and fighter")

    # The same layoff discount the score's ledgers apply, so the Prime gate and
    # the published score agree about what beating a returning fighter is worth.
    rated = attach_opponent_layoff(rated, history)
    tested = rated[rated["opponent"].map(ufc_bouts).fillna(0) >= MIN_OPPONENT_UFC_BOUTS]
    wins = quality_win_record(tested, min_opponent_mu=CONTENDER_LINE_MU)
    if wins.empty:
        return None
    qualifying = tested[
        tested["is_winner"].fillna(False).astype(bool)
        & (pd.to_numeric(tested["opponent_mu"], errors="coerce") >= CONTENDER_LINE_MU)
    ][["fighter", "event_date"]]
    own = (
        history.groupby(["fighter", "event_date"], as_index=False, sort=False)["mu_whr"]
        .mean()
    )
    decade = best_elite_decade(qualifying, own)
    return decade if not decade.empty else None


def write_board_artifacts(
    snapshot_dir: Path,
    *,
    rating_col: str | None = None,
    integrity_rating_col: str | None = None,
    min_rating_periods: int = SUSTAINED_PEAK_MIN_FIGHTS,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
    out_dir: Path | None = None,
) -> dict[str, object]:
    """Build and persist the standard board views for one snapshot.

    ``rating_col`` controls the completeness-gated core view.  The integrity
    view deliberately has a separate selector because its debit is measured in
    ordinary rating points and therefore must not be applied to Career Skill
    Mass (rating-point-years).
    """
    snap = Path(snapshot_dir)
    _validate_rating_scope(snap, scope)
    current = pd.read_parquet(snap / "ratings_current.parquet")
    appearances = pd.read_parquet(snap / "integrity_appearances.parquet")
    fights = F.load_fight_table(snap, scope=scope)

    core_col = _requested_core_rating_col(current, rating_col)
    integrity_col = _requested_integrity_rating_col(current, integrity_rating_col)
    ledger = integrity_ledger(appearances, fights)
    board = integrity_discounted_board(current, ledger, rating_col=integrity_col)
    def _gated(population: pd.DataFrame) -> pd.DataFrame:
        override = (
            public_legacy_eligibility_override(population)
            if core_col == "public_legacy_score"
            else None
        )
        return completeness_gated_board(
            population,
            rating_col=core_col,
            min_rating_periods=min_rating_periods,
            eligibility_override=override,
            unranked_at_or_below=RATING_FLOOR_IS_UNRANKED.get(core_col),
        )

    partition = partition_by_gender(current)
    boards = {
        gender: _gated(population)
        for gender, population in partition.items()
        if population is not None and not population.empty
    }
    gated = boards.get("M", _gated(current.iloc[0:0]))

    target = Path(out_dir) if out_dir is not None else (
        snap
        if not any(snap.glob("*_FINALIZED"))
        else Path("data/model_tuning") / snap.name
    )
    target.mkdir(parents=True, exist_ok=True)
    ledger.to_parquet(target / "integrity_ledger.parquet", index=False)
    board.to_parquet(target / "integrity_discounted_board.parquet", index=False)
    for gender, frame in boards.items():
        frame.to_parquet(
            target / PUBLIC_BOARDS["all_time"].filename(gender), index=False
        )

    classes = None
    if core_col == "public_legacy_score" and (snap / "performance_appearances.parquet").exists():
        classes = class_board_frame(snap, current, boards, scope)
        classes.to_parquet(target / "class_board.parquet", index=False)

    prime_boards: dict[str, pd.DataFrame] = {}
    elite_prime_boards: dict[str, pd.DataFrame] = {}
    if PRIME_RATING_COL in current.columns:
        decade = _elite_decade_map(snap)
        for gender, population in partition.items():
            if population is None or population.empty:
                continue
            suffix = GENDER_SUFFIX[gender]
            prime_boards[gender] = completeness_gated_board(
                population,
                rating_col=PRIME_RATING_COL,
                min_rating_periods=min_rating_periods,
            )
            prime_boards[gender].to_parquet(
                target / f"prime_board{suffix}.parquet", index=False
            )
            if decade is None:
                continue
            # The win count and the level both come from the same decade, so a
            # win can neither certify a stretch it falls outside nor be lost to
            # one picked on a different criterion.
            enriched = population.merge(decade, on="fighter", how="left")
            quality_wins = enriched.set_index("fighter")["elite_wins"]
            gate_only = completeness_gated_board(
                enriched,
                rating_col=ELITE_LEVEL_COL,
                min_rating_periods=min_rating_periods,
                tested_wins=quality_wins,
                min_tested_wins=MIN_QUALITY_WINS,
            )
            qualifiers = gate_only.loc[gate_only["status"].eq("ranked"), "fighter"]
            if qualifiers.empty:
                continue
            cohort = pd.to_numeric(
                enriched.set_index("fighter")[ELITE_LEVEL_COL].reindex(qualifiers),
                errors="coerce",
            ).dropna()
            if cohort.empty:
                continue
            weighted = enriched.assign(
                **{
                    ELITE_PRIME_RATING_COL: elite_win_mass(
                        enriched[ELITE_LEVEL_COL],
                        enriched["elite_wins"],
                        anchor=float(cohort.min()),
                    )
                }
            )
            elite_prime_boards[gender] = completeness_gated_board(
                weighted,
                rating_col=ELITE_PRIME_RATING_COL,
                min_rating_periods=min_rating_periods,
                tested_wins=quality_wins,
                min_tested_wins=MIN_QUALITY_WINS,
            ).merge(
                enriched[["fighter", ELITE_LEVEL_COL, "elite_window_start",
                          "elite_window_end"]],
                on="fighter", how="left",
            )
            elite_prime_boards[gender].to_parquet(
                target / PUBLIC_BOARDS["prime"].filename(gender), index=False
            )

    # The Current board ranks the score rate_snapshot stored beside the All-time
    # columns (ratings/current_score.py). Three screens: the shared rating-period
    # floor, the Prime board's tested-record bar, and a UFC bout inside the
    # window. A snapshot scored before 2026-10-14 has no Current score and
    # publishes no Current board rather than a rating-only one.
    current_boards: dict[str, pd.DataFrame] = {}
    current_col: str | None = None
    if CURRENT_SOURCE_COL in current.columns and "public_legacy_ufc_bouts" in current.columns:
        current_col = CURRENT_SOURCE_COL
        indexed = current.set_index("fighter")
        months_idle = (
            indexed[CURRENT_RECENCY_COL] if CURRENT_RECENCY_COL in current.columns else None
        )
        ufc_bouts = indexed["public_legacy_ufc_bouts"]
        for gender, population in partition.items():
            if population is None or population.empty:
                continue
            scored = population.assign(
                **{CURRENT_SCORE_COL: pd.to_numeric(population[current_col], errors="coerce")}
            )
            frame = completeness_gated_board(
                scored,
                rating_col=CURRENT_SCORE_COL,
                min_rating_periods=min_rating_periods,
                tested_wins=ufc_bouts,
                min_tested_wins=CURRENT_MIN_UFC_BOUTS,
                tested_wins_label=CURRENT_TESTED_LABEL,
                months_inactive=months_idle,
                max_months_inactive=CURRENT_MAX_MONTHS_INACTIVE,
                recency_label="UFC bout",
                unranked_at_or_below=0.0,
            )
            if frame.empty:
                continue
            current_boards[gender] = frame
            frame.to_parquet(
                target / PUBLIC_BOARDS["current"].filename(gender), index=False
            )

    return {
        "out_dir": target,
        "scope": scope,
        "core_rating_col": core_col,
        "integrity_rating_col": integrity_col,
        "ledger_rows": len(ledger),
        "ledger_fighters": ledger["fighter"].nunique() if len(ledger) else 0,
        "board_rows": len(board),
        "debited_fighters": int((board["integrity_cost"] > 0).sum()) if len(board) else 0,
        "genders": sorted(boards),
        "ranked_fighters": int(gated["status"].eq("ranked").sum()) if len(gated) else 0,
        "withheld_fighters": int((~gated["status"].eq("ranked")).sum()) if len(gated) else 0,
        "unranked_at_floor": (
            int(gated["status"].eq(UNRANKED_AT_FLOOR_STATUS).sum()) if len(gated) else 0
        ),
        "eligibility_overrides": (
            int(gated.get("eligibility_override", pd.Series(False, index=gated.index)).sum())
            if len(gated) else 0
        ),
        "ranked_by_gender": {
            gender: int(frame["status"].eq("ranked").sum())
            for gender, frame in boards.items()
        },
        "class_ranked_by_gender": (
            {g: int(n) for g, n in classes.groupby("gender")["fighter"].nunique().items()}
            if classes is not None else {}
        ),
        "prime_rating_col": PRIME_RATING_COL if prime_boards else None,
        "prime_ranked_by_gender": {
            gender: int(frame["status"].eq("ranked").sum())
            for gender, frame in prime_boards.items()
        },
        "contender_line_mu": CONTENDER_LINE_MU if elite_prime_boards else None,
        "min_quality_wins": MIN_QUALITY_WINS if elite_prime_boards else None,
        "elite_prime_ranked_by_gender": {
            gender: int(frame["status"].eq("ranked").sum())
            for gender, frame in elite_prime_boards.items()
        },
        "current_rating_col": CURRENT_SCORE_COL if current_boards else None,
        "current_source_rating_col": current_col if current_boards else None,
        "current_max_months_inactive": (
            CURRENT_MAX_MONTHS_INACTIVE if current_boards else None
        ),
        "current_min_ufc_bouts": CURRENT_MIN_UFC_BOUTS if current_boards else None,
        "current_ranked_by_gender": {
            gender: int(frame["status"].eq("ranked").sum())
            for gender, frame in current_boards.items()
        },
    }


def class_board_frame(
    snapshot_dir: Path, current: pd.DataFrame, gated: dict[str, pd.DataFrame], scope: str
) -> pd.DataFrame:
    """The All-time board by weight class (:mod:`ratings.division_legacy`).

    Refuses to publish unless every fighter's class scores sum to their published All-time
    score: the class boards and the All-time board are one measure, split by where it was earned.
    """
    from ratings.fights import resume_fights

    snap = Path(snapshot_dir)
    scores = class_scores(current, class_ledger(
        current, pd.read_parquet(snap / "performance_appearances.parquet"),
        source_fights=resume_fights(snap, scope),
        history=era_rated(pd.read_parquet(snap / "ratings_history_whr.parquet")),
    ))
    total = scores.groupby("fighter")["score"].sum().reindex(current["fighter"]).fillna(0.0)
    gap = (total.to_numpy() - pd.to_numeric(current["public_legacy_score"], errors="coerce").fillna(0.0).to_numpy())
    if abs(gap).max() > 1e-6:
        raise ValueError(f"class scores do not sum to the All-time score (max gap {abs(gap).max():.3g})")
    eligible = pd.concat([b.loc[b["status"].eq("ranked"), "fighter"] for b in gated.values()])
    return class_board(scores, current, eligible)


CLASS_ORDER = [c for c, _ in reversed(MEN_LIMIT_LB)] + [
    "Women's Featherweight", "Women's Bantamweight", "Women's Flyweight", "Women's Strawweight", "Women's Atomweight",
]


def class_board_markdown(classes: pd.DataFrame, all_time: dict[str, pd.Series], *, top: int = 10,
                         top_women: int = 5, min_ranked: int = 10) -> str:
    """One table per weight class, heaviest first: rank, fighter, class score, the share of the
    fighter's All-time score earned in the class, and their All-time rank."""
    parts = []
    for g, label, n in (("M", "Men", top), ("F", "Women", top_women)):
        frame = classes[classes["gender"].eq(g)]
        for d in [c for c in CLASS_ORDER if c in set(frame["division"])]:
            rows = frame[frame["division"].eq(d)]
            if len(rows) < min_ranked:
                continue
            rows = rows.head(n)
            parts.append(f"#### {label} — {d}\n\n" + _markdown_table(pd.DataFrame({
                "#": rows["rank"].to_numpy(),
                "Fighter": rows["fighter"].str.replace("|", r"\|", regex=False).to_numpy(),
                "Class score": rows["score"].round(1).to_numpy(),
                "Share of All-time": [f"{v:.0%}" for v in rows["share"]],
                "All-time #": ["" if pd.isna(v) else f"{v:.0f}" for v in rows["fighter"].map(all_time.get(g, {}))],
            })))
    return "\n\n".join(parts)


def board_rank_map(path: Path) -> pd.Series:
    """Fighter -> position on an already-written board, ranked rows only.

    A withheld fighter has no rank and must stay absent rather than be given
    one: the gate is an abstention, so mapping it to a number would publish a
    position the board declined to assert.
    """
    path = Path(path)
    if not path.exists():
        return pd.Series(dtype="float64")
    board = pd.read_parquet(path)
    ranked = board[board["status"].eq("ranked")]
    positions = ranked.set_index("fighter")["rank"]
    if positions.index.has_duplicates:
        raise ValueError(f"{path} ranks a fighter more than once")
    return positions


# Text reads left, figures read right.
_LEFT_ALIGNED_COLUMNS = {"Fighter", "Division"}

# The career boards answer what a career was worth, so they name the division
# the career was fought in; Current answers who is good now, so it names the
# division they are in now. The two disagree for anyone who moved up.
CAREER_DIVISION_COL = "career_division"
CURRENT_DIVISION_COL = "current_division"


def top_board_markdown(
    gated: pd.DataFrame,
    current: pd.DataFrame,
    *,
    rating_col: str,
    top: int = 100,
    prime_ranks: pd.Series | None = None,
) -> str:
    """Render the ranked head of the published board as a Markdown table.

    ``prime_ranks`` adds each fighter's position on the published elite-tested
    Prime board of their own gender. It is passed only to the all-time boards;
    on the Prime board itself the column would restate the rank beside it.
    """
    ranked = gated[gated["status"].eq("ranked")].head(top).copy()
    if ranked.empty:
        raise ValueError("the gated board has no ranked fighters to publish")

    lookup = current.set_index("fighter") if "fighter" in current.columns else current
    columns: dict[str, object] = {
        "#": ranked["rank"].astype(int).to_numpy(),
        # A pipe in a name would end the Markdown cell. The replacement is literal
        # (regex=False), so it must be ONE backslash: the previous two escaped
        # the backslash instead of the pipe and still broke the row.
        "Fighter": ranked["fighter"].str.replace("|", r"\|", regex=False).to_numpy(),
        "Division": division_column(ranked["fighter"], lookup, CAREER_DIVISION_COL),
    }
    # The elite board is ordered by elite-win mass, whose unit is rating points
    # times wins. Printing that adds a number nothing can be read against; the
    # two figures it is built from are printed instead.
    if rating_col != ELITE_PRIME_RATING_COL:
        columns["Score"] = ranked[rating_col].round(1).to_numpy()
    for label, source in (("Prime", ELITE_LEVEL_COL), ("Elite wins", "elite_wins")):
        values = None
        if source in ranked.columns:
            values = pd.to_numeric(ranked[source], errors="coerce")
        elif source in getattr(lookup, "columns", []):
            values = pd.to_numeric(ranked["fighter"].map(lookup[source]), errors="coerce")
        if values is not None:
            # Rendered as text: a fighter with no elite decade has no value, and
            # letting pandas hold the gap turns the whole column into floats.
            columns[label] = [
                "" if pd.isna(value) else f"{value:.0f}" for value in values
            ]
        # The two Prime columns sit together and are deliberately NOT monotone
        # in each other: the level is a rate over the fighter's best elite
        # decade, while the Prime board orders elite-win mass. An empty cell is
        # a fighter the elite-tested board withheld, not a bad Prime.
        if label == "Prime" and prime_ranks is not None:
            positions = pd.to_numeric(
                ranked["fighter"].map(prime_ranks), errors="coerce"
            )
            columns["Prime rank"] = [
                "" if pd.isna(value) else f"{value:.0f}" for value in positions
            ]
    return _markdown_table(pd.DataFrame(columns))


def _markdown_table(table: pd.DataFrame) -> str:
    """Render a prepared frame as a Markdown table: text left, figures right."""
    header = "| " + " | ".join(table.columns) + " |"
    align = "|" + "|".join(
        " --- " if name in _LEFT_ALIGNED_COLUMNS else " ---: "
        for name in table.columns
    ) + "|"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in table.itertuples(index=False)
    ]
    return "\n".join([header, align, *rows])


def current_board_markdown(
    gated: pd.DataFrame,
    current: pd.DataFrame,
    *,
    rating_col: str,
    top: int = CURRENT_BOARD_TOP,
) -> str:
    """Render the Current board: the score, what it was made of, and recency.

    It deliberately omits the Prime and all-time columns the other boards
    carry. Those answer what a career was worth, and setting them beside a "who
    is best now" figure invites exactly the comparison the three boards are
    separated to prevent.

    The columns it does print let the reader see the score working: title wins
    and contender wins inside the window, the UFC bout count the board screens
    on, and the date of the last UFC bout -- the date the window rule read, of
    any outcome. For Tom Aspinall that is his 2025-10-25 no contest, not his
    last rated bout of 2024-07-27. An older snapshot falls back to the last
    recorded bout, then the last rated one.
    """
    ranked = gated[gated["status"].eq("ranked")].head(top).copy()
    if ranked.empty:
        raise ValueError("the current board has no ranked fighters to publish")
    lookup = current.set_index("fighter") if "fighter" in current.columns else current
    columns = getattr(lookup, "columns", [])
    last = pd.Series(pd.NaT, index=ranked.index, dtype="datetime64[ns]")
    for date_col in ("last_ufc_event_date", "last_recorded_event_date", "whr_last_event_date"):
        if date_col in columns:
            last = last.fillna(
                pd.to_datetime(ranked["fighter"].map(lookup[date_col]), errors="coerce")
            )

    def counts(col: str) -> list[str]:
        if col not in columns:
            return [""] * len(ranked)
        values = pd.to_numeric(ranked["fighter"].map(lookup[col]), errors="coerce")
        return ["" if pd.isna(v) else f"{v:.0f}" for v in values]

    bouts = pd.to_numeric(ranked.get("tested_opponent_wins"), errors="coerce")
    return _markdown_table(pd.DataFrame({
        "#": ranked["rank"].astype(int).to_numpy(),
        "Fighter": ranked["fighter"].str.replace("|", "\\|", regex=False).to_numpy(),
        "Division": division_column(
            ranked["fighter"], lookup, CURRENT_DIVISION_COL
        ),
        "Score": ranked[rating_col].round(0).astype(int).to_numpy(),
        "Title wins": counts("current_title_wins"),
        "Contender wins": counts("current_contender_wins"),
        "UFC bouts": ["" if pd.isna(v) else f"{v:.0f}" for v in bouts],
        "Last UFC bout": ["" if pd.isna(d) else d.strftime("%Y-%m-%d") for d in last],
    }))


def peak_levels(snapshot_dir: Path) -> pd.Series:
    """Fighter -> highest era-adjusted rating they ever reached (:mod:`ratings.era`).

    The board's own score is a resume figure on no familiar scale. Printing the
    peak rating beside it puts every published fighter on the same scale as the
    contender line, so a reader can see what the line is worth without leaving
    the table. The line is read against each year's era, so the peak is too.
    """
    path = Path(snapshot_dir) / "ratings_history_whr.parquet"
    if not path.exists():
        return pd.Series(dtype="float64")
    history = pd.read_parquet(path, columns=["fighter", ERA_COL])
    return history.groupby("fighter")[ERA_COL].max()


def contender_line_reach(snapshot_dir: Path, current: pd.DataFrame) -> float | None:
    """Share of established fighters whose peak ever reached the contender line.

    Generated rather than written down, because a hand-typed percentage in the
    prose goes stale the first time the corpus is rebuilt.
    """
    peaks = peak_levels(snapshot_dir)
    if peaks.empty or "rating_periods" not in current.columns:
        return None
    established = current[
        pd.to_numeric(current["rating_periods"], errors="coerce").fillna(0)
        >= SUSTAINED_PEAK_MIN_FIGHTS
    ]
    reached = pd.to_numeric(established["fighter"].map(peaks), errors="coerce").dropna()
    if reached.empty:
        return None
    return float((reached >= CONTENDER_LINE_MU).mean())


def _contender_line_label(snapshot_dir: Path, current: pd.DataFrame) -> str:
    """The contender line, with the share of established fighters who reach it."""
    reach = contender_line_reach(snapshot_dir, current)
    if reach is None:
        return f"{CONTENDER_LINE_MU:,.0f}"
    return f"{CONTENDER_LINE_MU:,.0f} — reached by {reach:.1%} of established fighters"


def publication_release_markdown(
    snapshot_dir: Path,
    summary: dict[str, object],
    current: pd.DataFrame,
) -> str:
    """Release facts generated from the same snapshot as the tables."""
    snapshot = Path(snapshot_dir)
    rating_run_path = snapshot / "rating_run.json"
    combined_path = snapshot / "combined_fights_summary.json"
    rating_run = (
        json.loads(rating_run_path.read_text(encoding="utf-8"))
        if rating_run_path.exists()
        else {}
    )
    combined = (
        json.loads(combined_path.read_text(encoding="utf-8"))
        if combined_path.exists()
        else {}
    )
    scope = str(summary.get("scope", "not recorded"))
    scope_label = {
        DEFAULT_PUBLISHED_SCOPE: "UFC, early UFC and major-promotion careers",
        "ufc": "UFC only",
        "fightmatrix": "UFC and the FightMatrix comparison sample",
    }.get(scope, scope)
    score = str(summary.get("core_rating_col", "not recorded"))
    score_label = {
        "public_legacy_score": "All-time career score",
        "symon_career_skill_mass": "Career skill",
        "mu_whr": "Fight-based skill rating",
        "mu_canonical": "Fight-by-fight skill rating",
    }.get(score, score)

    run_fights = rating_run.get("combined_fights", {})
    date_range = run_fights.get("date_range", []) if isinstance(run_fights, dict) else []
    data_through = str(date_range[-1]) if date_range else "not recorded"

    coverage = rating_run.get("career_coverage", {})
    if isinstance(coverage, dict) and coverage.get("eligible"):
        eligible = int(coverage["eligible"])
        merged = int(coverage.get("whole_career_merged", 0))
        coverage_label = f"{merged:,} of {eligible:,} eligible fighters ({merged / eligible:.1%})"
    else:
        coverage_label = "not recorded"

    qualifiers = summary.get("elite_prime_ranked_by_gender", {})
    if isinstance(qualifiers, dict) and qualifiers:
        men = int(qualifiers.get("M", 0))
        women = int(qualifiers.get("F", 0))
        qualifier_label = (
            f"{men:,} {'man' if men == 1 else 'men'}; "
            f"{women:,} {'woman' if women == 1 else 'women'}"
        )
    else:
        qualifier_label = "not recorded"

    values = (
        ("Dataset", snapshot.name),
        ("Data through", data_through),
        ("Included records", scope_label),
        ("All-time basis", score_label),
        ("Rated fights", f"{int(rating_run.get('rated_bouts', 0)):,}"),
        ("Rated fighters", f"{len(current):,}"),
        ("Available fight records", f"{int(combined.get('rows', 0)):,}"),
        ("Whole-career coverage", coverage_label),
        ("Prime contender threshold", _contender_line_label(snapshot, current)),
        ("Prime qualifiers", qualifier_label),
    )
    rows = [f"| {label} | {value} |" for label, value in values]
    return "\n".join(["| Release fact | Value |", "| --- | ---: |", *rows])


def _rendered_publication(
    readme_path: Path,
    replacements: tuple[tuple[str, str, str], ...],
) -> str:
    """Validate every marker in one file and return its fully updated text."""
    readme = Path(readme_path)
    text = readme.read_text(encoding="utf-8")
    spans: list[tuple[int, int, str, str, str]] = []
    for begin, end, body in replacements:
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError(
                f"{readme} must contain exactly one board block: {begin} ... {end}"
            )
        start = text.index(begin)
        stop = text.index(end, start + len(begin))
        spans.append((start, stop + len(end), begin, end, body))

    ordered = sorted(spans)
    for previous, current in itertools.pairwise(ordered):
        if previous[1] > current[0]:
            raise ValueError(f"{readme} has overlapping board blocks")

    updated = text
    for start, stop, begin, end, body in reversed(ordered):
        updated = updated[:start] + f"{begin}\n\n{body}\n\n{end}" + updated[stop:]
    return updated


def _write_publication(readme_path: Path, text: str) -> None:
    """Promote one rendered publication file by atomic replace."""
    readme = Path(readme_path)
    build_path = readme.with_name(f"{readme.name}.building")
    try:
        build_path.write_text(text, encoding="utf-8")
        os.replace(build_path, readme)
    finally:
        build_path.unlink(missing_ok=True)


def update_publication_files(
    plans: tuple[tuple[Path, tuple[tuple[str, str, str], ...]], ...],
) -> None:
    """Refresh every publication file, validating all of them before any write.

    Related tables are updated together, and the overview reproduces two of the
    publication's tables. Rendering every document before any of them is
    promoted stops a missing marker from leaving one file half refreshed, or the
    first file published against a different release than the second.
    """
    rendered = [
        (Path(path), _rendered_publication(path, replacements))
        for path, replacements in plans
    ]
    for path, text in rendered:
        _write_publication(path, text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument(
        "--rating-col",
        default=None,
        help="Core board score; defaults to Public Legacy, then Career Skill Mass, then base WHR.",
    )
    ap.add_argument(
        "--integrity-rating-col",
        choices=INTEGRITY_RATING_CANDIDATES,
        default=None,
        help="Base WHR point score for the direct integrity debit.",
    )
    ap.add_argument("--min-rating-periods", type=int, default=SUSTAINED_PEAK_MIN_FIGHTS)
    ap.add_argument("--scope", default=DEFAULT_PUBLISHED_SCOPE)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument(
        "--write-readme",
        type=Path,
        nargs="?",
        const=Path("RANKINGS.md"),
        default=None,
        help="Also refresh the marked publication blocks (default RANKINGS.md).",
    )
    ap.add_argument(
        "--overview-path",
        type=Path,
        default=Path("README.md"),
        help="Overview whose headline boards are refreshed in the same "
             "run as --write-readme (default README.md).",
    )
    ap.add_argument("--readme-top", type=int, default=100)
    ap.add_argument(
        "--current-top",
        type=int,
        default=CURRENT_BOARD_TOP,
        help=f"Length of the published Current board (default {CURRENT_BOARD_TOP}).",
    )
    ap.add_argument(
        "--women-top",
        type=int,
        default=10,
        help="Length of the separately published women's board (default 10).",
    )
    args = ap.parse_args()

    summary = write_board_artifacts(
        args.snapshot_dir,
        rating_col=args.rating_col,
        integrity_rating_col=args.integrity_rating_col,
        min_rating_periods=args.min_rating_periods,
        scope=args.scope,
        out_dir=args.out_dir,
    )
    out = Path(summary["out_dir"])
    ledger = pd.read_parquet(out / "integrity_ledger.parquet")
    board = pd.read_parquet(out / "integrity_discounted_board.parquet")
    gated = pd.read_parquet(out / PUBLIC_BOARDS["all_time"].filename("M"))
    women_path = out / PUBLIC_BOARDS["all_time"].filename("F")
    women = pd.read_parquet(women_path) if women_path.exists() else None
    core_col = str(summary["core_rating_col"])
    debited = board[board["integrity_cost"] > 0]
    print(f"integrity ledger: {len(ledger):,} discounted appearances across "
          f"{ledger['fighter'].nunique() if len(ledger) else 0} fighters")
    if len(ledger):
        print(ledger["reason"].value_counts().to_string())
    print(f"\nboard: {len(board):,} rated fighters, {len(debited)} debited")
    if len(debited):
        print(debited[["rank", "undiscounted_rank", "rank_change", "fighter",
                       "integrity_cost", "discounted_fights"]]
              .sort_values("integrity_cost", ascending=False).round(1).to_string(index=False))

    ranked = gated[gated["status"].eq("ranked")]
    print(f"\ncompleteness-gated board (men's, the published default): "
          f"{len(ranked):,} ranked, {len(gated) - len(ranked):,} withheld")
    print(gated.loc[~gated["status"].eq("ranked"), "status"].value_counts().to_string())
    print(ranked.head(args.top)[["rank", "fighter", core_col]].round(1).to_string(index=False))
    if women is not None:
        women_ranked = women[women["status"].eq("ranked")]
        print(f"\ncompleteness-gated board (women's): {len(women_ranked):,} ranked, "
              f"{len(women) - len(women_ranked):,} withheld")
        print(women_ranked.head(args.women_top)[["rank", "fighter", core_col]]
              .round(1).to_string(index=False))
        print(f"\n{GENDER_GAUGE_NOTE}")
    current_ranked = summary.get("current_ranked_by_gender", {})
    if current_ranked:
        print(f"\ncurrent board (active within "
              f"{summary['current_max_months_inactive']:g} months): "
              + ", ".join(f"{g} {n:,} ranked" for g, n in sorted(current_ranked.items())))
    print(f"\nwritten to {out}")

    if args.write_readme is not None:
        current = pd.read_parquet(Path(args.snapshot_dir) / "ratings_current.parquet")
        # Every board prints the same two figures: the fighter's level across
        # their best elite decade, on the same scale as the contender line, and
        # how many contenders they beat inside it.
        decade = _elite_decade_map(args.snapshot_dir)
        if decade is not None:
            current = current.merge(
                decade[["fighter", ELITE_LEVEL_COL, "elite_wins"]],
                on="fighter", how="left",
            )
        release_table = publication_release_markdown(args.snapshot_dir, summary, current)
        # The Prime boards are read before the all-time tables are rendered, so
        # each all-time board can print the Prime position of the same gender.
        generated_elite = summary.get("elite_prime_ranked_by_gender", {})
        elite_path = out / PUBLIC_BOARDS["prime"].filename("M")
        elite_women_path = out / PUBLIC_BOARDS["prime"].filename("F")
        prime_rank_men = board_rank_map(elite_path) if "M" in generated_elite else None
        prime_rank_women = (
            board_rank_map(elite_women_path) if "F" in generated_elite else None
        )
        top_table = top_board_markdown(
            gated,
            current,
            rating_col=core_col,
            top=args.readme_top,
            prime_ranks=prime_rank_men,
        )
        elite_table: str | None = None
        replacements: list[tuple[str, str, str]] = [
            (README_RELEASE_BEGIN, README_RELEASE_END, release_table),
            (README_BOARD_BEGIN, README_BOARD_END, top_table),
        ]
        if women is not None:
            replacements.append(
                (
                    README_WOMEN_BEGIN,
                    README_WOMEN_END,
                    f"{GENDER_GAUGE_NOTE}\n\n"
                    + top_board_markdown(
                        women,
                        current,
                        rating_col=core_col,
                        top=args.women_top,
                        prime_ranks=prime_rank_women,
                    ),
                ),
            )
        if "M" in generated_elite:
            elite_table = top_board_markdown(
                pd.read_parquet(elite_path),
                current,
                rating_col=ELITE_PRIME_RATING_COL,
                top=ELITE_PRIME_TOP,
            )
            replacements.append(
                (README_ELITE_PRIME_BEGIN, README_ELITE_PRIME_END, elite_table)
            )
        current_col = summary.get("current_rating_col")
        generated_current = summary.get("current_ranked_by_gender", {})
        current_table: str | None = None
        if current_col and "M" in generated_current:
            current_table = current_board_markdown(
                pd.read_parquet(out / PUBLIC_BOARDS["current"].filename("M")),
                current,
                rating_col=str(current_col),
                top=args.current_top,
            )
            replacements.append(
                (README_CURRENT_BEGIN, README_CURRENT_END, current_table)
            )
        if current_col and "F" in generated_current:
            replacements.append(
                (
                    README_CURRENT_WOMEN_BEGIN,
                    README_CURRENT_WOMEN_END,
                    current_board_markdown(
                        pd.read_parquet(out / PUBLIC_BOARDS["current"].filename("F")),
                        current,
                        rating_col=str(current_col),
                        top=args.women_top,
                    ),
                )
            )
        if "F" in generated_elite:
            replacements.append(
                (
                    README_ELITE_PRIME_WOMEN_BEGIN,
                    README_ELITE_PRIME_WOMEN_END,
                    top_board_markdown(
                        pd.read_parquet(elite_women_path),
                        current,
                        rating_col=ELITE_PRIME_RATING_COL,
                        top=args.women_top,
                    ),
                )
            )
        class_path = out / "class_board.parquet"
        if class_path.exists():
            ranks = {
                g: board_rank_map(p)
                for g, p in (("M", out / PUBLIC_BOARDS["all_time"].filename("M")),
                             ("F", out / PUBLIC_BOARDS["all_time"].filename("F")))
                if p.exists()
            }
            replacements.append((README_CLASS_BEGIN, README_CLASS_END,
                                 class_board_markdown(pd.read_parquet(class_path), ranks)))
        plans: list[tuple[Path, tuple[tuple[str, str, str], ...]]] = [
            (Path(args.write_readme), tuple(replacements))
        ]
        # The overview carries the three headline boards. Their bodies are the
        # ones already published above, so the documents cannot disagree.
        overview: list[tuple[str, str, str]] = [
            (README_RELEASE_BEGIN, README_RELEASE_END, release_table),
            (README_BOARD_BEGIN, README_BOARD_END, top_table),
        ]
        if elite_table is not None:
            overview.append(
                (README_ELITE_PRIME_BEGIN, README_ELITE_PRIME_END, elite_table)
            )
        if current_table is not None:
            overview.append(
                (README_CURRENT_BEGIN, README_CURRENT_END, current_table)
            )
        overview_path = (
            Path(args.overview_path) if args.overview_path is not None else None
        )
        if overview_path is not None and overview_path != Path(args.write_readme):
            plans.append((overview_path, tuple(overview)))
        update_publication_files(tuple(plans))
        print(
            f"published release facts and {len(replacements) - 1} ranking tables "
            f"to {args.write_readme}"
        )
        if len(plans) > 1:
            print(
                f"published release facts and {len(overview) - 1} headline tables "
                f"to {overview_path}"
            )


if __name__ == "__main__":
    main()
