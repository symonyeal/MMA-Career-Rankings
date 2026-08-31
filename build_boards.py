"""Generate the published and audit boards for one rating snapshot.

Writes the standard artifacts next to the snapshot (or to ``--out-dir`` when the
snapshot is finalized):

* ``integrity_ledger.parquet`` — every discounted appearance, with the reason
* ``integrity_discounted_board.parquet`` — the judgement board and its bill
* ``completeness_gated_board.parquet`` — the published men's board: ranks who
  can be ranked, abstains otherwise
* ``completeness_gated_board_women.parquet`` — the same board for the women's
  component, which is a separate ranking because the two never fight
* ``prime_board.parquet`` and ``prime_board_women.parquet`` — the corresponding
  best-ten-year boards when the snapshot contains the Prime score
* ``prime_elite_board.parquet`` and ``prime_elite_board_women.parquet`` — the
  same Prime score behind the elite-tested evidence floor

"All-time" without a gender means the men's board. See ``GENDER_GAUGE_NOTE``.

Usage::

    python build_boards.py data/snapshots/2026-08-13
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from ratings import prequential as PQ
from ratings.boards import (
    UNRANKED_AT_FLOOR_STATUS,
    completeness_gated_board,
    integrity_discounted_board,
    integrity_ledger,
)
from ratings.constants import SUSTAINED_PEAK_MIN_FIGHTS  # board eligibility floor
from ratings.gender import (
    GENDER_GAUGE_NOTE,
    GENDER_LABEL,
    GENDER_SUFFIX,
    partition_by_gender,
)
from ratings.legacy_resume import PUBLIC_LEGACY_DISPLAY_SCALE
from ratings.opponent_quality import (
    CONTENDER_LINE_MU,
    MIN_OPPONENT_UFC_BOUTS,
    MIN_QUALITY_WINS,
    quality_win_record,
)
from ratings.scope import DEFAULT_PUBLISHED_SCOPE


# The public/core board is Public Legacy Score, NOT raw Career Skill Mass.
#
# Career Skill Mass is a retrospective WHR functional: it backfills whole-career
# evidence into earlier years, so a clean low-loss record in a less-tested
# circuit accumulates above-bar years and lands beside title legends as if the
# public resume question had been answered. It had not been. Selecting it as the
# public board is what put Usman Nurmagomedov 6th, Yaroslav Amosov 7th and Josh
# Barnett 8th all-time (2026-08-25 audit); under Public Legacy the same fighters
# sit 60th, 51st and 27th and the top 25 had zero unanchored names on that day's
# corpus. On the 2026-08-28 board the count is 3 -- Ngannou, Sterling and
# Dvalishvili, all UFC champions absent from the three supplied anchor lists
# rather than regional outliers. The count is a smell test, not a target: the
# anchor lists were authored in the same commit as the layer they score.
#
# This was diagnosed and repaired on 2026-08-24
# (_archive/20260826-stale-project-material/docs/PUBLIC_PERCEPTION_REPAIR_2026-08-24.md),
# reverted by the 2026-08-25
# cohesive pass, and restored here. **Career Skill Mass is a skill diagnostic,
# not the public board.** Do not promote it again without re-running
# build_top100_audit.py and reading the unanchored top-25 count.
#
# The integrity debit is denominated in rating points, so keep that judgement on
# a base WHR point scale.
CORE_RATING_CANDIDATES = (
    "public_legacy_score",
    "symon_career_skill_mass",
    "mu_whr",
)
INTEGRITY_RATING_CANDIDATES = (
    "mu_whr",
)

# Scores with a hard floor that means "no evidence of clearing the bar", not
# "the lowest measured level". Career Skill Mass sums a clipped positive excess,
# so zero is an abstention and every fighter sitting on it is tied, not ordered.
# Base WHR mu has no such floor and must not appear here.
RATING_FLOOR_IS_UNRANKED = {
    "public_legacy_score": 0.0,
    "symon_career_skill_mass": 0.0,
}

# The published score is a value-normalised sum: each component is divided by its
# own observed maximum, so the three printed contributions add back to the total
# exactly. Printing them is the receipt for a rank, not three more scores.
PUBLIC_LEGACY_COMPONENTS = (
    ("public_legacy_skill_score", "Skill"),
    ("public_legacy_title_score", "Title"),
    ("public_legacy_schedule_score", "Schedule"),
)

README_BOARD_BEGIN = "<!-- BOARD:TOP100:BEGIN -->"
README_BOARD_END = "<!-- BOARD:TOP100:END -->"
README_WOMEN_BEGIN = "<!-- BOARD:WOMEN10:BEGIN -->"
README_WOMEN_END = "<!-- BOARD:WOMEN10:END -->"
README_PRIME_BEGIN = "<!-- BOARD:PRIME100:BEGIN -->"
README_PRIME_END = "<!-- BOARD:PRIME100:END -->"
README_PRIME_WOMEN_BEGIN = "<!-- BOARD:PRIMEWOMEN10:BEGIN -->"
README_PRIME_WOMEN_END = "<!-- BOARD:PRIMEWOMEN10:END -->"
README_ELITE_PRIME_BEGIN = "<!-- BOARD:ELITEPRIME50:BEGIN -->"
README_ELITE_PRIME_END = "<!-- BOARD:ELITEPRIME50:END -->"
README_ELITE_PRIME_WOMEN_BEGIN = "<!-- BOARD:ELITEPRIMEWOMEN10:BEGIN -->"
README_ELITE_PRIME_WOMEN_END = "<!-- BOARD:ELITEPRIMEWOMEN10:END -->"
README_RELEASE_BEGIN = "<!-- PUBLICATION:RELEASE:BEGIN -->"
README_RELEASE_END = "<!-- PUBLICATION:RELEASE:END -->"

# Prime answers a different question from the all-time board: not "what did this
# career amount to" but "how good was this fighter at their best". It is a
# rating level, so unlike the all-time score it has no zero floor meaning "no
# evidence" -- it is simply absent for anyone short of the appearance minimum,
# and must NOT be added to RATING_FLOOR_IS_UNRANKED.
PRIME_RATING_COL = "symon_prime_score"

# The elite-tested Prime board ranks the same Prime score behind a floor on
# PROVEN record: at least MIN_QUALITY_WINS career wins over opponents who were
# above the contender line at the time AND had a tested record of their own.
#
# Two simpler rules were built first and both failed on named fighters.
# Counting ranked-or-title bouts measures longevity, not difficulty: it seated
# Machida, Davis and Chandler on accumulated volume while withholding Makhachev
# and Topuria. Averaging the ten toughest opponents measures gatekeeping: a
# fighter who lost to ten elite opponents scored the same as one who beat them,
# so Roy Nelson (0-10) outranked Khabib and St-Pierre, and a 1950 bar excluded
# Jon Jones himself. Counting wins over a stated line does neither.
ELITE_PRIME_TOP = 50

# The men's and women's boards are built and published SEPARATELY. The rule and
# the measurements behind it live in ``ratings/gender.py``, which every ranking
# surface in the project shares -- these names are re-exported so this module's
# existing callers keep working.
BOARD_GENDER_SUFFIX = GENDER_SUFFIX
BOARD_GENDER_LABEL = GENDER_LABEL


def _select_rating_col(
    current: pd.DataFrame,
    candidates: tuple[str, ...],
    *,
    board_name: str,
) -> str:
    for column in candidates:
        if column in current.columns:
            return column
    raise ValueError(
        f"cannot build {board_name}: none of the supported rating columns are present "
        f"({', '.join(candidates)})"
    )


def select_core_rating_col(current: pd.DataFrame) -> str:
    """Choose the lean headline score, never a retired weighted stream."""
    return _select_rating_col(current, CORE_RATING_CANDIDATES, board_name="core board")


def select_integrity_rating_col(current: pd.DataFrame) -> str:
    """Choose a base WHR point score compatible with the direct integrity debit."""
    return _select_rating_col(
        current,
        INTEGRITY_RATING_CANDIDATES,
        board_name="integrity-discounted board",
    )


def public_legacy_eligibility_override(current: pd.DataFrame) -> pd.Series:
    """Let proven UFC title resumes rank before the generic 13-period floor."""
    idx = current.index
    periods = pd.to_numeric(current.get("rating_periods", pd.Series(0, index=idx)), errors="coerce").fillna(0)
    score = pd.to_numeric(current.get("public_legacy_score", pd.Series(0, index=idx)), errors="coerce").fillna(0)
    title_wins = pd.to_numeric(
        current.get("public_legacy_title_wins", pd.Series(0, index=idx)), errors="coerce"
    ).fillna(0)
    title_defenses = pd.to_numeric(
        current.get("public_legacy_title_defenses", pd.Series(0, index=idx)), errors="coerce"
    ).fillna(0)
    ufc_bouts = pd.to_numeric(
        current.get("public_legacy_ufc_bouts", pd.Series(0, index=idx)), errors="coerce"
    ).fillna(0)
    return (
        periods.ge(8)
        & ufc_bouts.ge(8)
        & score.gt(0)
        & (title_wins.ge(3) | (title_wins.ge(2) & title_defenses.ge(1)))
    )


# Kept as a module-level name because tests and build_top100_audit.py import it
# from here; the implementation is the shared one.
gender_partition = partition_by_gender


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


def _quality_win_map(snapshot_dir: Path) -> pd.Series | None:
    """Fighter -> career wins over tested opponents above the contender line.

    Opponent strength is read off the same published WHR trajectory the board
    ranks, at the date of the bout, so the gate and the ranking are one estimate
    of one set of fighters rather than two sources that can disagree.

    Returns ``None`` rather than an empty map when an input is missing: a
    snapshot that cannot support the gate publishes no elite board at all,
    instead of one that withholds every fighter for lack of evidence.
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
        appearances_path, columns=["fighter", "opponent", "event_date", "is_winner"]
    )
    history = pd.read_parquet(
        history_path, columns=["fighter", "event_date", "mu_whr"]
    ).rename(columns={"fighter": "opponent", "mu_whr": "opponent_mu"})
    rated = appearances.merge(history, on=["opponent", "event_date"], how="left")
    tested = rated[rated["opponent"].map(ufc_bouts).fillna(0) >= MIN_OPPONENT_UFC_BOUTS]
    record = quality_win_record(tested, min_opponent_mu=CONTENDER_LINE_MU)
    if record.empty:
        return None
    return record.set_index("fighter")["quality_wins"]


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
    current = pd.read_parquet(snap / "ratings_current.parquet")
    appearances = pd.read_parquet(snap / "integrity_appearances.parquet")
    fights = PQ.load_fight_table(snap, scope=scope)

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

    partition = gender_partition(current)
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
        suffix = BOARD_GENDER_SUFFIX[gender]
        frame.to_parquet(
            target / f"completeness_gated_board{suffix}.parquet", index=False
        )

    prime_boards: dict[str, pd.DataFrame] = {}
    elite_prime_boards: dict[str, pd.DataFrame] = {}
    if PRIME_RATING_COL in current.columns:
        quality_wins = _quality_win_map(snap)
        for gender, population in partition.items():
            if population is None or population.empty:
                continue
            suffix = BOARD_GENDER_SUFFIX[gender]
            prime_boards[gender] = completeness_gated_board(
                population,
                rating_col=PRIME_RATING_COL,
                min_rating_periods=min_rating_periods,
            )
            prime_boards[gender].to_parquet(
                target / f"prime_board{suffix}.parquet", index=False
            )
            if quality_wins is None:
                continue
            elite_prime_boards[gender] = completeness_gated_board(
                population,
                rating_col=PRIME_RATING_COL,
                min_rating_periods=min_rating_periods,
                tested_wins=quality_wins,
                min_tested_wins=MIN_QUALITY_WINS,
            )
            elite_prime_boards[gender].to_parquet(
                target / f"prime_elite_board{suffix}.parquet", index=False
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
    }


def _public_legacy_contributions(current: pd.DataFrame) -> pd.DataFrame:
    """Per-fighter display points for each component of the published score."""
    out = current[["fighter"]].copy()
    for column, label in PUBLIC_LEGACY_COMPONENTS:
        values = pd.to_numeric(current[column], errors="coerce").fillna(0.0)
        ceiling = float(values.max())
        out[label] = (
            PUBLIC_LEGACY_DISPLAY_SCALE * values / ceiling if ceiling > 0 else values * 0.0
        )
    return out


def top_board_markdown(
    gated: pd.DataFrame,
    current: pd.DataFrame,
    *,
    rating_col: str,
    top: int = 100,
) -> str:
    """Render the ranked head of the published board as a Markdown table."""
    ranked = gated[gated["status"].eq("ranked")].head(top).copy()
    if ranked.empty:
        raise ValueError("the gated board has no ranked fighters to publish")

    table = pd.DataFrame(
        {
            "#": ranked["rank"].astype(int).to_numpy(),
            "Fighter": ranked["fighter"].str.replace("|", r"\|", regex=False).to_numpy(),
            "Score": ranked[rating_col].round(1).to_numpy(),
        }
    )
    if rating_col == "public_legacy_score":
        merged = ranked[["fighter"]].merge(
            _public_legacy_contributions(current), on="fighter", how="left"
        )
        for _, label in PUBLIC_LEGACY_COMPONENTS:
            table[label] = merged[label].round(1).to_numpy()

    header = "| " + " | ".join(table.columns) + " |"
    align = "| ---: | --- |" + " ---: |" * (len(table.columns) - 2)
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in table.itertuples(index=False)
    ]
    return "\n".join([header, align, *rows])


def publication_release_markdown(
    snapshot_dir: Path,
    summary: dict[str, object],
    current: pd.DataFrame,
) -> str:
    """Business-facing release facts generated from the same snapshot."""
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
    values = (
        ("Snapshot", snapshot.name),
        ("Published scope", str(summary.get("scope", "not recorded"))),
        ("Published score", str(summary.get("core_rating_col", "not recorded"))),
        ("Rated bouts", f"{int(rating_run.get('rated_bouts', 0)):,}"),
        ("Rated fighters", f"{len(current):,}"),
        ("Maximum-coverage fight rows", f"{int(combined.get('rows', 0)):,}"),
    )
    rows = [f"| {label} | {value} |" for label, value in values]
    return "\n".join(["| Release fact | Value |", "| --- | ---: |", *rows])


def update_readme_block(readme_path: Path, body: str, *, begin: str, end: str) -> None:
    """Replace one marked block in the README with freshly built content."""
    readme = Path(readme_path)
    text = readme.read_text(encoding="utf-8")
    start = text.find(begin)
    stop = text.find(end)
    if start < 0 or stop < 0:
        raise ValueError(f"{readme} has no board block: expected {begin} ... {end}")
    readme.write_text(
        text[:start] + f"{begin}\n\n{body}\n\n" + text[stop:], encoding="utf-8"
    )


def update_readme_blocks(
    readme_path: Path,
    replacements: tuple[tuple[str, str, str], ...],
) -> None:
    """Validate and replace several marked blocks in one file write.

    The publisher updates related tables together. Validating every marker
    before changing the file prevents a missing later marker from leaving the
    publication half refreshed.
    """
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
    for previous, current in zip(ordered, ordered[1:]):
        if previous[1] > current[0]:
            raise ValueError(f"{readme} has overlapping board blocks")

    updated = text
    for start, stop, begin, end, body in reversed(ordered):
        updated = updated[:start] + f"{begin}\n\n{body}\n\n{end}" + updated[stop:]
    build_path = readme.with_name(f"{readme.name}.building")
    try:
        build_path.write_text(updated, encoding="utf-8")
        os.replace(build_path, readme)
    finally:
        build_path.unlink(missing_ok=True)


def update_readme_board(readme_path: Path, table: str) -> None:
    """Replace the marked board block in the README with a freshly built table."""
    update_readme_block(
        readme_path, table, begin=README_BOARD_BEGIN, end=README_BOARD_END
    )


def update_readme_prime_board(readme_path: Path, table: str) -> None:
    """Replace the Prime block, published beside the all-time table."""
    update_readme_block(
        readme_path, table, begin=README_PRIME_BEGIN, end=README_PRIME_END
    )


def update_readme_prime_women_board(readme_path: Path, table: str) -> None:
    """Replace the separately ranked women's Prime block."""
    update_readme_block(
        readme_path,
        f"{GENDER_GAUGE_NOTE}\n\n{table}",
        begin=README_PRIME_WOMEN_BEGIN,
        end=README_PRIME_WOMEN_END,
    )


def update_readme_women_board(readme_path: Path, table: str) -> None:
    """Replace the women's block, which is published beside the men's table."""
    update_readme_block(
        readme_path,
        f"{GENDER_GAUGE_NOTE}\n\n{table}",
        begin=README_WOMEN_BEGIN,
        end=README_WOMEN_END,
    )


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
    ap.add_argument("--readme-top", type=int, default=100)
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
    gated = pd.read_parquet(out / "completeness_gated_board.parquet")
    women_path = out / "completeness_gated_board_women.parquet"
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
    prime_path = out / "prime_board.parquet"
    if prime_path.exists():
        prime_ranked = pd.read_parquet(prime_path)
        prime_ranked = prime_ranked[prime_ranked["status"].eq("ranked")]
        print(f"\nprime board (men's): {len(prime_ranked):,} ranked")
        print(prime_ranked.head(args.top)[["rank", "fighter", PRIME_RATING_COL]]
              .round(1).to_string(index=False))
    if women is not None:
        women_ranked = women[women["status"].eq("ranked")]
        print(f"\ncompleteness-gated board (women's): {len(women_ranked):,} ranked, "
              f"{len(women) - len(women_ranked):,} withheld")
        print(women_ranked.head(args.women_top)[["rank", "fighter", core_col]]
              .round(1).to_string(index=False))
        print(f"\n{GENDER_GAUGE_NOTE}")
    print(f"\nwritten to {out}")

    if args.write_readme is not None:
        current = pd.read_parquet(Path(args.snapshot_dir) / "ratings_current.parquet")
        replacements: list[tuple[str, str, str]] = [
            (
                README_RELEASE_BEGIN,
                README_RELEASE_END,
                publication_release_markdown(args.snapshot_dir, summary, current),
            ),
            (
                README_BOARD_BEGIN,
                README_BOARD_END,
                top_board_markdown(
                    gated, current, rating_col=core_col, top=args.readme_top
                ),
            )
        ]
        prime_path = out / "prime_board.parquet"
        prime = None
        if prime_path.exists():
            prime = pd.read_parquet(prime_path)
            replacements.append(
                (
                    README_PRIME_BEGIN,
                    README_PRIME_END,
                    top_board_markdown(
                        prime, current, rating_col=PRIME_RATING_COL, top=args.readme_top
                    ),
                ),
            )
        if women is not None:
            replacements.append(
                (
                    README_WOMEN_BEGIN,
                    README_WOMEN_END,
                    f"{GENDER_GAUGE_NOTE}\n\n"
                    + top_board_markdown(
                        women, current, rating_col=core_col, top=args.women_top
                    ),
                ),
            )
        prime_women_path = out / "prime_board_women.parquet"
        if prime_women_path.exists():
            prime_women = pd.read_parquet(prime_women_path)
            replacements.append(
                (
                    README_PRIME_WOMEN_BEGIN,
                    README_PRIME_WOMEN_END,
                    f"{GENDER_GAUGE_NOTE}\n\n"
                    + top_board_markdown(
                        prime_women,
                        current,
                        rating_col=PRIME_RATING_COL,
                        top=args.women_top,
                    ),
                )
            )
        elite_path = out / "prime_elite_board.parquet"
        if elite_path.exists():
            replacements.append(
                (
                    README_ELITE_PRIME_BEGIN,
                    README_ELITE_PRIME_END,
                    top_board_markdown(
                        pd.read_parquet(elite_path),
                        current,
                        rating_col=PRIME_RATING_COL,
                        top=ELITE_PRIME_TOP,
                    ),
                )
            )
        elite_women_path = out / "prime_elite_board_women.parquet"
        if elite_women_path.exists():
            replacements.append(
                (
                    README_ELITE_PRIME_WOMEN_BEGIN,
                    README_ELITE_PRIME_WOMEN_END,
                    f"{GENDER_GAUGE_NOTE}\n\n"
                    + top_board_markdown(
                        pd.read_parquet(elite_women_path),
                        current,
                        rating_col=PRIME_RATING_COL,
                        top=args.women_top,
                    ),
                )
            )
        update_readme_blocks(args.write_readme, tuple(replacements))
        print(f"published {len(replacements)} ranking tables to {args.write_readme}")


if __name__ == "__main__":
    main()
