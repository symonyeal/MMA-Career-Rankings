"""Generate the boards that survived the 2026-08-18 differentiator audit.

Writes three artifacts next to the snapshot (or to ``--out-dir`` when the
snapshot is finalized):

* ``integrity_ledger.parquet`` — every discounted appearance, with the reason
* ``integrity_discounted_board.parquet`` — the judgement board and its bill
* ``completeness_gated_board.parquet`` — the published men's board: ranks who
  can be ranked, abstains otherwise
* ``completeness_gated_board_women.parquet`` — the same board for the women's
  component, which is a separate ranking because the two never fight

"All-time" without a gender means the men's board. See ``GENDER_GAUGE_NOTE``.

Usage::

    python build_boards.py data/snapshots/2026-08-13
"""
from __future__ import annotations

import argparse
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
from ratings.legacy_resume import PUBLIC_LEGACY_DISPLAY_SCALE
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

# The men's and women's boards are built and published SEPARATELY, and that is
# an identification statement, not a presentation preference.
#
# Measured on the 2026-08-13 snapshot: of 80,697 rated bouts, **zero** join a
# man to a woman and the two sides share **zero** opponents. They are disjoint
# components of the bout graph, so adding any constant to every rating in the
# women's component changes no modelled bout probability -- the offset between
# the two levels is set by the prior, not by evidence. It is not a small effect
# on the board: 2026-08-25 measured total female career mass running from 0 at
# -200 Elo to 45,382 at +200, moving Zhang Weili from rank 30 with zero mass to
# rank 13 with 886. One number therefore cannot rank a man against a woman, and
# a mixed board publishes that unidentified gauge as if it were a result.
#
# Ranks *within* each component are identified and are what get published.
BOARD_GENDER_SUFFIX = {"M": "", "F": "_women"}
BOARD_GENDER_LABEL = {"M": "men's", "F": "women's"}
GENDER_GAUGE_NOTE = (
    "Men and women never fight, so no bout locates the two rating levels "
    "against each other: their relative level is set by the prior, not by "
    "evidence, and one number cannot rank them together. The boards are "
    "therefore separate, and each one's ranks are identified within it."
)


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


def gender_partition(current: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split the rated population into the two disjoint bout-graph components.

    A snapshot rated before gender inference existed has no ``gender`` column;
    it gets one mixed board under the men's key rather than a silent claim to
    have separated something. ``rate_snapshot._attach_recent_division_gender``
    is what fills the column, and it propagates across the same components this
    splits on.
    """
    if current is None or current.empty or "gender" not in current.columns:
        return {"M": current}
    label = current["gender"].astype(str).str.upper().str.strip()
    female = label.str.startswith("F")
    male = label.str.startswith("M")
    # An unlabelled fighter never fought a gendered billing the inference could
    # read. Keeping them on the default board is the same abstention the
    # completeness gate makes: they are not evidence for a women's rank.
    return {"M": current[~female].copy(), "F": current[female & ~male].copy()}


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


def write_board_artifacts(
    snapshot_dir: Path,
    *,
    rating_col: str | None = None,
    integrity_rating_col: str | None = None,
    min_rating_periods: int = SUSTAINED_PEAK_MIN_FIGHTS,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
    out_dir: Path | None = None,
) -> dict[str, object]:
    """Build and persist the three standard board views for one snapshot.

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


def update_readme_board(readme_path: Path, table: str) -> None:
    """Replace the marked board block in the README with a freshly built table."""
    update_readme_block(
        readme_path, table, begin=README_BOARD_BEGIN, end=README_BOARD_END
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
        help="Core completeness-board score; defaults to Career Skill Mass, then base WHR.",
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
        const=Path("README.md"),
        default=None,
        help="Also refresh the published board block in this README (default README.md).",
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
        update_readme_board(
            args.write_readme,
            top_board_markdown(gated, current, rating_col=core_col, top=args.readme_top),
        )
        print(f"published men's top {args.readme_top} to {args.write_readme}")
        if women is not None:
            update_readme_women_board(
                args.write_readme,
                top_board_markdown(
                    women, current, rating_col=core_col, top=args.women_top
                ),
            )
            print(f"published women's top {args.women_top} to {args.write_readme}")


if __name__ == "__main__":
    main()
