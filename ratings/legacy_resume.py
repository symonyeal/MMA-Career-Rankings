"""Public legacy scoring built from skill mass plus a resume ledger.

The latent rating estimates how strong a fighter looked from bout outcomes.
That is not the same public question as "greatest": title fights, title wins,
successful defenses, and belts in multiple divisions are resume achievements.
They belong in a transparent board-layer ledger, not inside the likelihood that
learns fighter strength.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from loaders.fightmatrix_organizations import normalize_organization
from ratings.opponent_quality import CONTENDER_LINE_MU, MIN_OPPONENT_UFC_BOUTS
from ratings.performance_adjustment import (
    is_real_ufc_title_bout,
    normalize_division_label,
    womens_division_label,
)


LEGACY_SCORE_COLUMNS = [
    "fighter",
    "public_legacy_score",
    "public_legacy_skill_mass",
    "public_legacy_skill_score",
    "public_legacy_exposure_factor",
    "public_legacy_title_score",
    "public_legacy_title_quality",
    "public_legacy_qualifying_title_wins",
    "public_legacy_resume_score",
    "public_legacy_resume_quality",
    "public_legacy_contender_wins",
    "public_legacy_title_appearances",
    "public_legacy_title_wins",
    "public_legacy_title_defenses",
    "public_legacy_title_win_divisions",
    "public_legacy_rank_context_win_mass",
    "public_legacy_multi_division_bonus",
    "public_legacy_ufc_bouts",
    "public_legacy_top_org_bouts",
    "public_legacy_unknown_org_bouts",
]

# Title resume is priced by the opponent actually beaten, in order, not by a
# flat point per resume line.
#
# For each title-fight win, ``q`` is the probability that a contender-level
# fighter would have LOST to that opponent, from the opponent's pre-fight rating
# against the contender line **of that opponent's own division and year**. The
# win contributes ``q ** TITLE_QUALITY_EXPONENT``.
#
# Two choices here were made by measurement, not taste (2026-08-25):
#
# * **A hinge at the bar was tried first and is WRONG.** ``(2q - 1)+`` reads
#   well -- "nothing for beating a sub-contender" -- but a title challenger is
#   by construction near contender level, so the modal title fight sits right on
#   the hinge. It zeroed the title component for **38 fighters with three or
#   more title wins**, including Valentina Shevchenko (11 title wins -> 0),
#   Kamaru Usman (6 -> 0) and Chuck Liddell (5 -> 0), while a single upset over
#   a very highly rated opponent scored huge: Matt Serra went to 50th all-time
#   on a 7-7 record. A convex weight keeps the ordering the hinge was reaching
#   for and zeroes nobody.
# * **The bar must be division-scoped HERE**, unlike the career functional. The
#   question a title fight asks is "was this opponent a contender in their own
#   division", which is what a number-one contender is. Against a sport-wide bar
#   the light divisions are priced against heavier ones -- women's strawweight
#   p99 is 1812 against light heavyweight's 1986 -- and flyweight and women's
#   champions score near zero for beating their own division's best.
#
# Three things this deliberately removes, all of which double-posted evidence
# the opponent's rating already carries:
#   * the flat 20/45/60 per appearance/win/defense -- a title fight against a
#     1523-rated opponent and one against a 1950-rated opponent were the same
#     number of points;
#   * the 600-point multi-division bonus, which made one extra belt worth ten
#     title defenses;
#   * ``ORG_FACTOR_BY_CANONICAL`` on the title path. Measured 2026-08-25:
#     P(a random Bellator title opponent rates above a random UFC one) = 0.477,
#     and the Bradley-Terry transfer gap for Bellator is +4 [-4, +28] on 171
#     crossovers, so a promotion-level discount is ruled out. The organisation
#     is already inside the opponent's rating; pricing it again is a second
#     posting of one fact.
#
# TITLE_QUALITY_SCALE is display only. The published score value-normalises each
# component by its own maximum, so this constant cannot affect any ordering.
TITLE_QUALITY_SCALE = 1000.0

# Convexity of the per-win weight. Swept 2026-08-25 over {1, 2, 4, 6} against
# four external references with skill and schedule held fixed; 4 maximised
# Tapology (+0.697) and The 100 Greatest (+0.475) -- both the best of any
# variant tried this session, including the shipped flat ledger -- while holding
# ESPN at +0.915 against the flat ledger's +0.939. Above 4 the single-upset
# artifact returns (at q**6 Matt Serra climbs back to 42nd).
TITLE_QUALITY_EXPONENT = 4.0

# Held-out level offset between the UFC-tested and never-UFC pools, in Elo.
#
# **This is a ledger term, not a rating term.** It never enters the bout
# likelihood, so §2.4 of the operating contract -- no organisation weight in the
# likelihood -- is untouched. What it corrects is the mis-location the code note
# above ``title_quality_ledger`` already names as the reason the two contender
# lines could not be unified: ``mu_whr`` over-rating lightly-tested careers, so
# that welterweight's 2010 contender line is set by a 21-5 regional fighter.
#
# The 2026-08-25 removal of ``ORG_FACTOR_BY_CANONICAL`` from this path rested on
# two statistics computed **from these same ratings** -- P(a random Bellator
# title opponent rates above a random UFC one) = 0.477, and a Bradley-Terry
# transfer gap of +4 [-4, +28]. A pool offset is exactly the quantity a
# within-model statistic cannot see, because the smoother has no pool parameter
# and free per-fighter thetas absorb it. Measured out of sample instead
# (2026-08-28, seven cutoffs, 120-day scoring windows, event bootstrap):
#
#   ever-UFC vs never-UFC, all crossing bouts   +104 Elo [ +67, +148], n=486
#     decomposed by state at the bout:
#   future UFC signee, pre-debut                +274 Elo [+185, +389], n=156
#   prior UFC experience, fighting outside       +54 Elo [ +10, +100], n=328
#   UFC debutant vs incumbent                    +48 Elo [  -8,  +98], n=169
#
# The +274 pre-debut term is selection on a latent variable -- the UFC signs
# fighters whose record the model has already priced too low -- and is NOT used
# here: pricing an achievement by who was later signed is a look-ahead dressed
# as a resume. The applied constant is the +54 term, the one that survives after
# the crossing has happened and the only one that describes a standing
# difference between the two pools.
#
# The transfer is stated, not measured: the offset was fitted on the prospective
# filter state and is applied to the retrospective smoother. Both estimators
# share one likelihood and one weak pool bridge, so the same identification
# failure applies to both, but that the magnitude carries across is an
# assumption. Set to 0.0 to reproduce the 2026-08-27 unadjusted ledger.
UFC_POOL_OFFSET_ELO = 54.0

# Retained as a REPORTED diagnostic only. Until 2026-09-01 this priced the third
# component; see the note above ``contender_resume_ledger`` for why it no longer
# does. It is not added to any score.
RANK_CONTEXT_WIN_POINTS = 1200.0

# Display scale for the résumé quality sum, mirroring TITLE_QUALITY_SCALE. Both
# are display only: the published score normalises each component by its own
# scale statistic, so neither constant can affect an ordering.
RESUME_QUALITY_SCALE = 1000.0

# One contribution per active year, the same Single-Entry rule Career Skill Mass
# already applies. Each qualifying win is worth at most 1.0, so a year is capped
# at the value of one maximal win however many contenders were beaten in it.
#
# Without this the résumé is unbounded in career length, which is the
# Single-Entry violation ``docs/NEXT_2026-08-28.md`` §3.2 names against the
# component this replaces: Career Skill Mass already posts one contribution per
# active year, so an uncapped win ledger posts career length a second time. The
# cap is a bound, not a mechanism: measured on the 2026-08-13 published scope it
# binds on 1 of the 639 fighters with any qualifying win, costing Islam
# Makhachev 0.023 of 2.964. What it buys is that the ledger is now bounded by
# active years the way Career Skill Mass is, so career length cannot be posted a
# second time however long a career runs. The uncapped count stays visible as
# ``public_legacy_contender_wins``.
RESUME_YEAR_CAP = 1.0

# How the two questions the board answers are combined, as ONE stated exchange
# rate rather than an emergent one.
#
# Until 2026-09-01 the three components were each divided by their own MAXIMUM
# and summed, described in this file as combining them "without an exchange rate
# anyone had to invent". That was not what it did. A maximum is a single order
# statistic, so the exchange rate was invented -- by whichever career happened to
# top each column, which on the 2026-08-13 snapshot was Jon Jones for two of the
# three. And because the three have very different tail shapes (max/median of
# 10.6 for skill, 8.3 for title, 2.9 for the third component), dividing by the
# max gave the FLATTEST component the most weight. Measured over the published
# top 100 on that snapshot:
#
#   component   share of score mass   variance share, ranks 1-25   ranks 26-100
#   skill                    21.9%                         36.6%          12.2%
#   title                    25.1%                         38.9%          29.1%
#   schedule                 53.0%                         24.5%          58.7%
#
# So the board changed its own definition at about rank 25: title and skill above
# it, schedule below. 52% of the top 100 sat below a tenth of skill's maximum and
# 43% below a tenth of title's, against 3% for schedule -- the first two had
# resolution only at the very top, the third had it everywhere.
#
# The weights are POLICY, not fits. Nothing in a bout outcome can score them:
# the public legacy score never enters a win probability, so held-out log loss is
# silent on it. They say what the board is for, and they are stated here so a
# reader can disagree with the number rather than with an artifact.
#
# Set to 0.30 by the project owner on 2026-09-01 after reading the resulting
# order. Swept with the skill share held at 0.25, correlations read over a FIXED
# population (the incumbent published top 100, so the statistic does not change
# with the board):
#
#   achievement  rho(elite wins)  rho(prime)  non-anchors@100  Matt Serra  zero-title@100
#   0.30                   0.730       0.632                2          60              15
#   0.40                   0.694       0.604                3          49              12
#   0.50                   0.639       0.551                4          43               7
#   0.60                   0.592       0.505                5          40               4
#   (incumbent board:      0.519       0.418                6          77              14)
#
# The trade is legible in that table: weight achievement harder and the board
# agrees more with the belts and less with the record, and the single-upset
# artifact section 4 of the 2026-09-01 brief warns about -- Matt Serra high on
# one win over St-Pierre -- climbs. 0.30 keeps the title ledger a real term while
# leaving the ordering to the record.
LEGACY_ACHIEVEMENT_WEIGHT = 0.30

# Inside the quality half: how much is "how good were you" (Career Skill Mass)
# against "who did you actually beat" (the contender resume).
#
# NOT equal, and the asymmetry is evidential rather than aesthetic. The resume is
# screened twice -- the opponent was above the contender line at the time AND had
# eight UFC bouts of their own -- while Career Skill Mass is screened not at all:
# it accumulates positive excess above a bar against whoever was in front of the
# fighter. That is exactly why the 2026-08-24 audit found it seating Usman
# Nurmagomedov 6th and Yaroslav Amosov 7th all-time. Weighting an unscreened
# quantity equally with a doubly-screened one is not the neutral choice.
#
# Swept 2026-09-01 with the achievement weight held at 0.5, reading the count of
# names on ``build_top100_audit.PUBLIC_NON_ANCHORS`` inside the top 100 -- the
# smell test ``build_boards`` already documents -- and the printed columns'
# agreement over a FIXED population (the incumbent published top 100, so the
# statistic does not change with the board):
#
#   skill share   non-anchors in top 100   rho(score, elite wins)   rho(score, prime)
#   0.00                               1                    0.693               0.517
#   0.25                               4                    0.639               0.551
#   0.33                               6                    0.620               0.567
#   0.50                               9                    0.567               0.598
#   0.75                              10                    0.475               0.626
#   (incumbent board, for reference:   6                    0.519               0.418)
#
# The untested-record promotion this project has fought twice is that first
# column, and the skill share is the dial on it. 0.25 keeps Career Skill Mass a
# real term, lands below the incumbent's own non-anchor count, and is the point
# past which the count starts exceeding it. It is a policy number, not a fit: no
# bout outcome scores it.
LEGACY_QUALITY_SKILL_SHARE = 0.25

# The scale statistic each component is divided by: the mean of its own top N
# values. It is a location statistic over a hundred careers rather than a single
# order statistic, so no one career sets an exchange rate, and it is computed per
# component from that component alone -- never from the score -- so it cannot be
# circular with the board it produces.
LEGACY_NORMALISER_TOP_N = 100

PUBLIC_LEGACY_DISPLAY_SCALE = 1000.0

# A division-year thinner than this cannot describe its own title bar. Kept
# separate from symon_score.DEFAULT_DIVISION_MIN_POPULATION because the two
# lines are, for now, deliberately different statistics -- see the note in
# title_quality_ledger.
TITLE_DIVISION_MIN_YEARS = 5

QUALITY_LEDGER_COLUMNS = [
    "fighter",
    "public_legacy_title_quality",
    "public_legacy_qualifying_title_wins",
]


def _scale(values: pd.Series, *, top_n: int = LEGACY_NORMALISER_TOP_N) -> pd.Series:
    """Divide by the mean of the column's own top ``top_n`` values.

    Not a maximum: see the note above :data:`LEGACY_ACHIEVEMENT_WEIGHT`. A column
    with fewer than ``top_n`` positive entries falls back to the mean of those it
    has, so a small frame still normalises to something a single fighter does not
    own. An all-zero column stays zero.
    """
    v = pd.to_numeric(values, errors="coerce").fillna(0.0)
    positive = v[v > 0]
    if positive.empty:
        return v * 0.0
    norm = float(positive.nlargest(min(top_n, len(positive))).mean())
    return v / norm if norm > 0 else v * 0.0


def _empty_quality_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=QUALITY_LEDGER_COLUMNS)


def _division_labels(current: pd.DataFrame) -> pd.Series | None:
    """Fighter -> division label, women's classes kept separate from men's.

    A woman's ``career_division`` is folded onto one canonical women's division
    first. Without that fold the same division splits into as many pools as the
    corpus has spellings for it -- "Women's Flyweight" from UFCStats and a bare
    "Flyweight" from the Sherdog majors rows -- and each pool strikes its own
    contender line. Measured on 2026-08-13 those two lines sat 91 rating points
    apart over the same eleven years, so which one a career was scored against
    was decided by its source, not by its division.

    The ``"W " + div`` prefix is kept as the fallback for a label the fold
    cannot place, so a fighter is never silently pooled with the men.
    """
    if current is None or "career_division" not in current.columns:
        return None
    div = current["career_division"].astype(str)
    gender = current.get("gender", pd.Series("", index=current.index)).astype(str)
    female = gender.str.upper().str.startswith("F")
    folded = div.map(womens_division_label)
    return pd.Series(
        np.where(female, folded.fillna("W " + div), div), index=current["fighter"]
    ).groupby(level=0).first()

ORG_FACTOR_BY_CANONICAL = {
    "UFC": 1.0,
    "PRIDE": 0.95,
    "Affliction": 0.90,
    "Strikeforce": 0.88,
    "WEC": 0.88,
    "Bellator": 0.65,
    "PFL": 0.60,
    "RIZIN": 0.60,
    "ONE": 0.60,
    "DREAM": 0.60,
}
ORG_FACTOR_BY_TIER = {
    1: 0.82,
    2: 0.60,
    3: 0.42,
    4: 0.20,
}


TITLE_COUNT_COLUMNS = [
    "fighter",
    "public_legacy_title_appearances",
    "public_legacy_title_wins",
    "public_legacy_title_defenses",
    "public_legacy_title_win_divisions",
]
TITLE_LEDGER_COLUMNS = [
    *TITLE_COUNT_COLUMNS,
    "public_legacy_source_title_score",
]

EXPOSURE_LEDGER_COLUMNS = [
    "fighter",
    "public_legacy_exposure_factor",
    "public_legacy_ufc_bouts",
    "public_legacy_top_org_bouts",
    "public_legacy_unknown_org_bouts",
]

COMBINED_TITLE_LEDGER_COLUMNS = [
    *TITLE_COUNT_COLUMNS,
    "public_legacy_rank_context_win_mass",
    "public_legacy_appearance_title_score",
    "public_legacy_source_title_score",
]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=LEGACY_SCORE_COLUMNS)


def _empty_title_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=TITLE_LEDGER_COLUMNS)


def _empty_exposure_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=EXPOSURE_LEDGER_COLUMNS)


def title_quality(opponent_mu: pd.Series, bar: pd.Series) -> pd.Series:
    """Value of beating an opponent rated ``opponent_mu`` against ``bar``.

    ``q`` is the logistic probability that a contender-level fighter loses to
    that opponent; the weight is ``q ** TITLE_QUALITY_EXPONENT``. Strictly
    positive everywhere -- beating a weak champion is worth little, never
    nothing -- and strongly convex, so an elite opponent dominates a merely
    contender-level one. See the note above :data:`TITLE_QUALITY_SCALE`.
    """
    gap = pd.to_numeric(opponent_mu, errors="coerce") - pd.to_numeric(bar, errors="coerce")
    q = 1.0 / (1.0 + np.power(10.0, -gap / 400.0))
    return q ** TITLE_QUALITY_EXPONENT


def ufc_debut_dates_from(fights: pd.DataFrame | None) -> pd.Series:
    """First UFC-family event date per fighter, the pool-state clock.

    ``ufc`` and ``pre_unified`` are one promotion under two corpus labels, which
    is the same rule the held-out pool probe used to fit
    :data:`UFC_POOL_OFFSET_ELO`. Applying a different rule here than the one the
    number was measured under would make the constant unfalsifiable.
    """
    empty = pd.Series(dtype="datetime64[ns]")
    if fights is None or fights.empty or "source_corpus" not in fights.columns:
        return empty
    ufc = fights[fights["source_corpus"].isin(["ufc", "pre_unified"])]
    if ufc.empty:
        return empty
    stacked = pd.concat(
        [
            ufc[["fighter_a", "event_date"]].rename(columns={"fighter_a": "fighter"}),
            ufc[["fighter_b", "event_date"]].rename(columns={"fighter_b": "fighter"}),
        ],
        ignore_index=True,
    )
    stacked["event_date"] = pd.to_datetime(stacked["event_date"], errors="coerce")
    stacked = stacked.dropna(subset=["fighter", "event_date"])
    if stacked.empty:
        return empty
    return stacked.groupby("fighter")["event_date"].min()


def _pool_offset(
    fighters: pd.Series,
    at: pd.Series,
    debuts: pd.Series | None,
    offset_elo: float,
) -> pd.Series:
    """``offset_elo`` where the fighter had already fought in the UFC, else 0.

    ``at`` may be a date or a calendar year; a year is read as "any UFC bout in
    or before this year", which is the coarsest statement the annual bar can
    make about the same rule.
    """
    zero = pd.Series(0.0, index=fighters.index)
    if debuts is None or not len(debuts) or not float(offset_elo):
        return zero
    first = fighters.map(debuts)
    if pd.api.types.is_datetime64_any_dtype(at):
        tested = first.notna() & first.lt(at)
    else:
        year = pd.to_numeric(at, errors="coerce")
        tested = first.notna() & pd.to_datetime(first).dt.year.le(year)
    return zero.mask(tested.fillna(False), float(offset_elo))


def _organization_factor(canonical_organization: object, tier: object) -> float:
    org = str(canonical_organization or "Unknown")
    if org in ORG_FACTOR_BY_CANONICAL:
        return ORG_FACTOR_BY_CANONICAL[org]
    tier_num = pd.to_numeric(pd.Series([tier]), errors="coerce").iloc[0]
    if pd.isna(tier_num):
        return ORG_FACTOR_BY_TIER[4]
    return ORG_FACTOR_BY_TIER.get(int(tier_num), ORG_FACTOR_BY_TIER[4])


def _legacy_division_bucket(weight_class: object) -> str | None:
    """Normalize title divisions for cross-promotion public resume counts."""
    label = normalize_division_label(weight_class)
    if not isinstance(label, str):
        return None
    text = " ".join(label.split()).strip()
    for prefix in ("Women's ", "Womens ", "Female "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text or None


def _organization_context(fights: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "fight_url",
        "canonical_organization",
        "organization_tier",
        "public_legacy_org_factor",
    ]
    if fights is None or fights.empty or "fight_url" not in fights.columns:
        return pd.DataFrame(columns=columns)

    work = fights[["fight_url", "event_date"]].copy()
    work["source"] = fights.get("source", pd.Series("", index=fights.index))
    work["org"] = fights.get("org", pd.Series(pd.NA, index=fights.index))
    work["event_date"] = pd.to_datetime(work["event_date"], errors="coerce")
    work["_org_label"] = work["org"].fillna("Unknown").astype(str)
    ufc_source = work["source"].astype(str).eq("ufc") & work["org"].isna()
    work.loc[ufc_source, "_org_label"] = "UFC"
    work["_year"] = work["event_date"].dt.year.fillna(0).astype(int)

    keys = (
        work.groupby(["_org_label", "_year"], dropna=False, as_index=False)
        .agg(sample_date=("event_date", "median"))
    )
    records = []
    for org_label, year, sample_date in keys[
        ["_org_label", "_year", "sample_date"]
    ].itertuples(index=False, name=None):
        rec = normalize_organization(org_label, sample_date)
        records.append(
            {
                "_org_label": org_label,
                "_year": year,
                "canonical_organization": rec["canonical_organization"],
                "organization_tier": rec["organization_tier"],
                "public_legacy_org_factor": _organization_factor(
                    rec["canonical_organization"], rec["organization_tier"]
                ),
            }
        )
    mapped = work.merge(pd.DataFrame(records), on=["_org_label", "_year"], how="left")
    return mapped[columns].drop_duplicates("fight_url")


def organization_exposure_ledger(fights: pd.DataFrame) -> pd.DataFrame:
    """Evaluate how much of each career was proven in top organization context."""
    if fights is None or fights.empty or "fighter_a" not in fights.columns:
        return _empty_exposure_ledger()

    context = _organization_context(fights)
    sides = pd.concat(
        [
            fights[["fight_url", "fighter_a"]].rename(columns={"fighter_a": "fighter"}),
            fights[["fight_url", "fighter_b"]].rename(columns={"fighter_b": "fighter"}),
        ],
        ignore_index=True,
        sort=False,
    )
    sides = sides.merge(context, on="fight_url", how="left")
    sides["public_legacy_org_factor"] = pd.to_numeric(
        sides["public_legacy_org_factor"], errors="coerce"
    ).fillna(ORG_FACTOR_BY_TIER[4])
    sides["_is_ufc"] = sides["canonical_organization"].eq("UFC")
    sides["_is_top_org"] = sides["public_legacy_org_factor"].ge(0.82)
    sides["_is_unknown_org"] = sides["canonical_organization"].fillna("Unknown").eq("Unknown")

    def _top_quartile_mean(values: pd.Series) -> float:
        clean = pd.to_numeric(values, errors="coerce").dropna().sort_values(ascending=False)
        if clean.empty:
            return ORG_FACTOR_BY_TIER[4]
        return float(clean.head(max(1, int(np.ceil(len(clean) * 0.25)))).mean())

    grouped = sides.groupby("fighter", sort=False)
    out = grouped.agg(
        _mean_factor=("public_legacy_org_factor", "mean"),
        _top_quartile_factor=("public_legacy_org_factor", _top_quartile_mean),
        public_legacy_ufc_bouts=("_is_ufc", "sum"),
        public_legacy_top_org_bouts=("_is_top_org", "sum"),
        public_legacy_unknown_org_bouts=("_is_unknown_org", "sum"),
    ).reset_index()
    out["public_legacy_exposure_factor"] = (
        0.5 * pd.to_numeric(out["_mean_factor"], errors="coerce").fillna(ORG_FACTOR_BY_TIER[4])
        + 0.5 * pd.to_numeric(out["_top_quartile_factor"], errors="coerce").fillna(ORG_FACTOR_BY_TIER[4])
    ).clip(lower=ORG_FACTOR_BY_TIER[4], upper=1.0)
    for col in (
        "public_legacy_ufc_bouts",
        "public_legacy_top_org_bouts",
        "public_legacy_unknown_org_bouts",
    ):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    return out[EXPOSURE_LEDGER_COLUMNS]


def championship_resume_ledger(appearances: pd.DataFrame) -> pd.DataFrame:
    """Count public resume achievements from appearance context rows."""
    columns = [
        "fighter",
        "public_legacy_title_appearances",
        "public_legacy_title_wins",
        "public_legacy_title_defenses",
        "public_legacy_title_win_divisions",
        "public_legacy_rank_context_win_mass",
    ]
    if appearances is None or appearances.empty or "fighter" not in appearances.columns:
        return pd.DataFrame(columns=columns)

    app = appearances.copy()
    idx = app.index
    title = (
        app.get("is_championship_bout", pd.Series(False, index=idx)).fillna(False).astype(bool)
        | app.get("is_interim_title_bout", pd.Series(False, index=idx)).fillna(False).astype(bool)
    )
    won = pd.to_numeric(
        app.get("actual_score", pd.Series(0.0, index=idx)),
        errors="coerce",
    ).fillna(0.0).ge(1.0)
    entered_champ = (
        app.get("fighter_entered_as_champion", pd.Series(False, index=idx))
        .fillna(False)
        .astype(bool)
        | app.get("fighter_entered_as_interim_champion", pd.Series(False, index=idx))
        .fillna(False)
        .astype(bool)
    )
    app["_title"] = title
    app["_title_win"] = title & won
    app["_title_defense"] = title & won & entered_champ
    app["_rank_context_win_mass"] = np.where(
        won,
        (
            pd.to_numeric(
                app.get("perf_factor_rank_context", pd.Series(1.0, index=idx)),
                errors="coerce",
            )
            .fillna(1.0)
            .sub(1.0)
            .clip(lower=0.0)
        ),
        0.0,
    )

    grouped = app.groupby("fighter", sort=False)
    out = grouped.agg(
        public_legacy_title_appearances=("_title", "sum"),
        public_legacy_title_wins=("_title_win", "sum"),
        public_legacy_title_defenses=("_title_defense", "sum"),
        public_legacy_rank_context_win_mass=("_rank_context_win_mass", "sum"),
    ).reset_index()

    if "division" in app.columns:
        divisions = (
            app.loc[app["_title_win"]]
            .assign(_division_bucket=lambda x: x["division"].map(_legacy_division_bucket))
            .dropna(subset=["_division_bucket"])
            .groupby("fighter")["_division_bucket"]
            .nunique()
            .rename("public_legacy_title_win_divisions")
            .reset_index()
        )
        out = out.merge(divisions, on="fighter", how="left")
    else:
        out["public_legacy_title_win_divisions"] = 0

    for col in columns:
        if col == "fighter":
            continue
        if col == "public_legacy_rank_context_win_mass":
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    return out[columns]


def source_title_resume_ledger(fights: pd.DataFrame) -> pd.DataFrame:
    """Count title resume from source fight rows.

    ``performance_appearances`` deliberately narrows championship context to
    UFC divisional title bouts for its performance factor. The public legacy
    board needs the source title facts across the rated scope, including PRIDE,
    WEC, Strikeforce, Bellator, and RIZIN rows that already carry
    ``is_title_fight``.
    """
    if fights is None or fights.empty or "fighter_a" not in fights.columns:
        return _empty_title_ledger()

    f = fights.copy()
    f = f.merge(_organization_context(f), on="fight_url", how="left")
    idx = f.index
    raw_title = f.get("is_title_fight", pd.Series(False, index=idx)).fillna(False).astype(bool)
    ufc_org = f["canonical_organization"].eq("UFC")
    real_ufc_title = f.get("weight_class", pd.Series(pd.NA, index=idx)).map(
        is_real_ufc_title_bout
    )
    f["_is_title"] = np.where(ufc_org, real_ufc_title, raw_title)
    f = f[f["_is_title"]].copy()
    if f.empty:
        return _empty_title_ledger()

    f["event_date"] = pd.to_datetime(f.get("event_date", pd.Series(pd.NaT, index=f.index)), errors="coerce")
    f["_division"] = f.get("weight_class", pd.Series(pd.NA, index=f.index)).map(
        _legacy_division_bucket
    )
    f["_title_factor"] = pd.to_numeric(
        f["public_legacy_org_factor"], errors="coerce"
    ).fillna(ORG_FACTOR_BY_TIER[4])
    if "org" not in f.columns:
        f["org"] = ""
    f["_org_division"] = (
        f["canonical_organization"].fillna("Unknown").astype(str)
        + "::"
        + f["_division"].fillna("").astype(str)
    )
    f["_winner"] = f.get("winner", pd.Series(pd.NA, index=f.index))
    f["_is_draw"] = f.get("is_draw", pd.Series(False, index=f.index)).fillna(False).astype(bool)
    f = f.sort_values(["event_date", "event_name", "fight_url"], na_position="last")

    champions: dict[str, str] = {}
    defense_by_url_fighter: set[tuple[object, str]] = set()
    for fight_url, org_division, winner, is_draw in f[
        ["fight_url", "_org_division", "_winner", "_is_draw"]
    ].itertuples(index=False, name=None):
        org_division = str(org_division)
        if pd.isna(winner) or bool(is_draw):
            continue
        winner = str(winner)
        incumbent = champions.get(org_division)
        if incumbent == winner:
            defense_by_url_fighter.add((fight_url, winner))
        champions[org_division] = winner

    def _side(side: str) -> pd.DataFrame:
        other = "b" if side == "a" else "a"
        frame = f[
            [
                "fight_url",
                "event_date",
                "_division",
                f"fighter_{side}",
                f"fighter_{other}",
                "_winner",
                "_is_draw",
                "_title_factor",
                "canonical_organization",
            ]
        ].rename(
            columns={
                f"fighter_{side}": "fighter",
                f"fighter_{other}": "opponent",
                "_winner": "winner",
                "_is_draw": "is_draw",
            }
        )
        return frame

    app = pd.concat([_side("a"), _side("b")], ignore_index=True, sort=False)
    app["title_appearance"] = True
    app["title_win"] = app["winner"].eq(app["fighter"]) & ~app["is_draw"].fillna(False).astype(bool)
    app["title_defense"] = [
        (fight_url, fighter) in defense_by_url_fighter
        for fight_url, fighter in zip(app["fight_url"], app["fighter"])
    ]
    missing_division_wins = app["title_win"] & app["_division"].isna()
    if missing_division_wins.any():
        fallback = app.loc[missing_division_wins, [
            "fight_url",
            "fighter",
            "event_date",
            "canonical_organization",
        ]].copy()
        fallback["_win_number"] = (
            fallback.sort_values(["fighter", "canonical_organization", "event_date", "fight_url"])
            .groupby(["fighter", "canonical_organization"])
            .cumcount()
        )
        fallback_defenses = {
            (fight_url, fighter)
            for fight_url, fighter in fallback.loc[
                fallback["_win_number"].gt(0), ["fight_url", "fighter"]
            ].itertuples(index=False, name=None)
        }
        fallback_mask = pd.Series(
            [
                (fight_url, fighter) in fallback_defenses
                for fight_url, fighter in zip(app["fight_url"], app["fighter"])
            ],
            index=app.index,
        )
        app["title_defense"] = app["title_defense"] | fallback_mask

    grouped = app.groupby("fighter", sort=False)
    out = grouped.agg(
        public_legacy_title_appearances=("title_appearance", "sum"),
        public_legacy_title_wins=("title_win", "sum"),
        public_legacy_title_defenses=("title_defense", "sum"),
    ).reset_index()
    divisions = (
        app.loc[app["title_win"]]
        .dropna(subset=["_division"])
        .groupby("fighter")["_division"]
        .nunique()
        .rename("public_legacy_title_win_divisions")
        .reset_index()
    )
    out = out.merge(divisions, on="fighter", how="left")
    # Flat per-line points and the organisation factor were removed
    # 2026-08-25; the title score now comes from :func:`title_quality_ledger`,
    # which prices each win by the opponent beaten. This ledger keeps the
    # COUNTS, which remain the auditable display facts.
    out["public_legacy_source_title_score"] = 0.0

    for col in TITLE_COUNT_COLUMNS:
        if col == "fighter":
            continue
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    out["public_legacy_source_title_score"] = pd.to_numeric(
        out["public_legacy_source_title_score"], errors="coerce"
    ).fillna(0.0)
    return out[TITLE_LEDGER_COLUMNS]


def _combine_title_ledgers(
    appearance_ledger: pd.DataFrame,
    source_ledger: pd.DataFrame,
) -> pd.DataFrame:
    app = appearance_ledger.copy() if appearance_ledger is not None else pd.DataFrame()
    source = source_ledger.copy() if source_ledger is not None else pd.DataFrame()
    if app.empty and source.empty:
        return pd.DataFrame(columns=COMBINED_TITLE_LEDGER_COLUMNS)
    if app.empty:
        app = pd.DataFrame(columns=[*TITLE_COUNT_COLUMNS, "public_legacy_rank_context_win_mass"])
    if source.empty:
        source = pd.DataFrame(columns=TITLE_LEDGER_COLUMNS)

    if not app.empty:
        # Flat per-line points removed 2026-08-25 -- see TITLE_QUALITY_SCALE.
        app["public_legacy_appearance_title_score"] = 0.0
    if "public_legacy_source_title_score" not in source.columns:
        source["public_legacy_source_title_score"] = 0.0

    out = app.merge(
        source,
        on="fighter",
        how="outer",
        suffixes=("_appearance", "_source"),
    )
    for col in TITLE_COUNT_COLUMNS:
        if col == "fighter":
            continue
        app_col = f"{col}_appearance"
        source_col = f"{col}_source"
        out[col] = np.maximum(
            pd.to_numeric(out.get(app_col), errors="coerce").fillna(0),
            pd.to_numeric(out.get(source_col), errors="coerce").fillna(0),
        ).astype(int)
    rank_context = "public_legacy_rank_context_win_mass"
    if rank_context not in out.columns:
        out[rank_context] = 0.0
    out[rank_context] = pd.to_numeric(out[rank_context], errors="coerce").fillna(0.0)

    if "public_legacy_appearance_title_score" not in out.columns:
        out["public_legacy_appearance_title_score"] = 0.0
    if "public_legacy_source_title_score" not in out.columns:
        out["public_legacy_source_title_score"] = 0.0
    for col in ("public_legacy_appearance_title_score", "public_legacy_source_title_score"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out[COMBINED_TITLE_LEDGER_COLUMNS]


# Minimum rated fighter-years before a division-year gets its own contender
# line. Below this the quantile is noise and the sport-wide line is used.


def title_quality_ledger(
    fights: pd.DataFrame | None,
    history: pd.DataFrame | None,
    *,
    reference: str | float | None = None,
    divisions: pd.Series | None = None,
    ufc_debut_dates: pd.Series | None = None,
    pool_offset_elo: float = UFC_POOL_OFFSET_ELO,
) -> pd.DataFrame:
    """Title resume priced by the opponent actually beaten, bout by bout.

    Every title-fight win is looked up against the opponent's rating **as it
    stood before that bout** -- ``merge_asof`` with ``allow_exact_matches=False``
    so the bout's own result cannot price itself -- and scored by
    :func:`title_quality` against that year's contender bar.

    Given ``ufc_debut_dates``, :data:`UFC_POOL_OFFSET_ELO` is added to the rating
    of any fighter who had already fought in the UFC, on **both** sides of the
    comparison -- the opponent being priced and the annual means the contender
    line is read from -- so the two stay on one scale. A division whose pool is
    already UFC-tested therefore barely moves; a mixed one moves by however much
    of it is not.

    Returns one row per fighter with the summed quality and the count of wins
    that cleared the contender line.
    """
    from ratings.symon_score import DEFAULT_CAREER_REFERENCE, year_reference

    if (
        fights is None or fights.empty
        or history is None or history.empty
        or "fighter_a" not in fights.columns
    ):
        return _empty_quality_ledger()

    ref = DEFAULT_CAREER_REFERENCE if reference is None else reference
    h = history[["fighter", "event_date", "mu_whr"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h["mu_whr"] = pd.to_numeric(h["mu_whr"], errors="coerce")
    h = h.dropna(subset=["fighter", "event_date", "mu_whr"])
    if h.empty:
        return _empty_quality_ledger()
    annual = (
        h.assign(year=h["event_date"].dt.year)
        .groupby(["fighter", "year"])["mu_whr"]
        .agg(annual_mean="mean")
        .reset_index()
    )
    # The pool correction is applied to the line as well as to the opponent, so
    # ``q`` compares two numbers on one scale. See UFC_POOL_OFFSET_ELO.
    annual["annual_mean"] = annual["annual_mean"] + _pool_offset(
        annual["fighter"], annual["year"], ufc_debut_dates, pool_offset_elo
    )
    bar = year_reference(annual, ref)
    # Contender line inside each division-year, used in preference to the
    # sport-wide line -- see the note above TITLE_QUALITY_SCALE.
    #
    # KNOWN INCOHERENCE, deliberately left in place 2026-08-26. This is a 0.90
    # quantile; the career functional next door is measured against
    # `contender:5` from `symon_score.division_year_reference`. One board with
    # two different contender lines is wrong, and the quantile is the weaker of
    # the two on its own terms -- it names a fixed *fraction* of whoever happens
    # to be rated, which is the mistake the note above
    # `symon_score.DEFAULT_CAREER_REFERENCE` rejects for the career bar.
    # Measured over the 230 division-years both cover, it sits a mean 90.9
    # rating points BELOW the contender line and the shortfall tracks field
    # size: 5.7 points in women's strawweight against 139.9 in featherweight.
    #
    # Unifying the two was tried and REVERTED the same day, because the
    # published output got worse, and the reason is worth recording. Against
    # `contender:5` the deep men's divisions price a title win at nearly
    # nothing while the women's divisions price one richly -- St-Pierre's title
    # resume fell to 279 against Namajunas's 657, and Namajunas reached 9th
    # all-time. That is not the bar statistic failing. It is `mu_whr`
    # over-rating lightly-tested careers, surfacing in the line itself:
    # welterweight's 2010 contender line comes out at 1838 and is set by Rick
    # Hawn, a 21-5 regional fighter, with Ben Askren and Andrey Koreshkov above
    # him, while women's strawweight in 2021 lands at 1627 because that pool is
    # almost entirely UFC-tested. A higher bar simply reads that error more
    # sensitively.
    #
    # So the quantile stays until the rating error is addressed. Raising
    # `WHR_VIRTUAL_GAMES` is NOT the fix -- that was rebuilt across
    # {2,4,6,10,16,24} on this scope and refuted (at v=24 Travis Fulton is
    # first all-time). Fix the rating, then unify this line; do not unify it
    # first.
    division_bar = None
    if divisions is not None and len(divisions):
        annual["_division"] = annual["fighter"].map(divisions)
        counts = annual.groupby(["_division", "year"])["annual_mean"].transform("size")
        eligible = annual[counts >= TITLE_DIVISION_MIN_YEARS]
        if not eligible.empty:
            division_bar = eligible.groupby(["_division", "year"])["annual_mean"].quantile(0.90)

    f = fights.copy()
    f["event_date"] = pd.to_datetime(f.get("event_date"), errors="coerce")
    idx = f.index
    keep = f.get("is_title_fight", pd.Series(False, index=idx)).fillna(False).astype(bool)
    keep &= ~f.get("is_excluded", pd.Series(False, index=idx)).fillna(False).astype(bool)
    keep &= ~f.get("is_draw", pd.Series(False, index=idx)).fillna(False).astype(bool)
    keep &= ~f.get("is_nc", pd.Series(False, index=idx)).fillna(False).astype(bool)
    f = f[keep & f["event_date"].notna()]
    if f.empty:
        return _empty_quality_ledger()

    sides = pd.concat(
        [
            f.assign(fighter=f["fighter_a"], opponent=f["fighter_b"]),
            f.assign(fighter=f["fighter_b"], opponent=f["fighter_a"]),
        ],
        ignore_index=True,
        sort=False,
    )[["fighter", "opponent", "event_date", "winner"]].dropna(
        subset=["fighter", "opponent"]
    )
    wins = sides[sides["winner"].eq(sides["fighter"])].sort_values("event_date")
    if wins.empty:
        return _empty_quality_ledger()

    priced = pd.merge_asof(
        wins,
        h.sort_values("event_date").rename(
            columns={"fighter": "opponent", "mu_whr": "opponent_mu"}
        ),
        on="event_date",
        by="opponent",
        allow_exact_matches=False,
    )
    priced["opponent_mu"] = priced["opponent_mu"] + _pool_offset(
        priced["opponent"], priced["event_date"], ufc_debut_dates, pool_offset_elo
    )
    # A title bout can fall in a year with no rated appearances -- the bar has
    # no entry for it. Dropping those rows would silently zero a real title win,
    # so fall back to the nearest rated year, then to the whole-sample level.
    years = pd.Index(sorted(bar.dropna().index))
    fight_years = priced["event_date"].dt.year
    if len(years):
        nearest = years[
            np.abs(years.to_numpy()[None, :] - fight_years.to_numpy()[:, None]).argmin(axis=1)
        ]
        priced["bar"] = pd.Series(bar.reindex(nearest).to_numpy(), index=priced.index)
    else:
        priced["bar"] = np.nan
    priced["bar"] = priced["bar"].fillna(float(annual["annual_mean"].mean()))
    priced = priced.dropna(subset=["opponent_mu", "bar"])
    if priced.empty:
        return _empty_quality_ledger()
    if division_bar is not None:
        keys = pd.MultiIndex.from_arrays([
            priced["opponent"].map(divisions),
            priced["event_date"].dt.year,
        ])
        local = pd.Series(division_bar.reindex(keys).to_numpy(), index=priced.index)
        priced["bar"] = local.fillna(priced["bar"])
    priced["weight"] = title_quality(priced["opponent_mu"], priced["bar"])
    # Reported diagnostic, not a scoring term: title wins over an opponent at or
    # above their division's contender line. The SCORE uses the convex weight,
    # which never zeroes -- this count is what a reader wants to see beside it.
    priced["qualifying"] = priced["opponent_mu"] >= priced["bar"]

    out = priced.groupby("fighter", sort=False).agg(
        public_legacy_title_quality=("weight", "sum"),
        public_legacy_qualifying_title_wins=("qualifying", "sum"),
    ).reset_index()
    out["public_legacy_qualifying_title_wins"] = (
        out["public_legacy_qualifying_title_wins"].astype(int)
    )
    return out[QUALITY_LEDGER_COLUMNS]


RESUME_LEDGER_COLUMNS = [
    "fighter",
    "public_legacy_resume_quality",
    "public_legacy_contender_wins",
]


def _empty_resume_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=RESUME_LEDGER_COLUMNS)


def ufc_bout_counts(fights: pd.DataFrame | None) -> pd.Series:
    """Model bouts each fighter had inside the UFC family, over the whole scope.

    The same count ``build_boards._elite_decade_map`` screens on, so the score
    and the printed Elite-wins column admit the same opponents.
    """
    empty = pd.Series(dtype="int64")
    if fights is None or fights.empty or "source_corpus" not in fights.columns:
        return empty
    model = fights.get("is_model_bout", pd.Series(True, index=fights.index))
    ufc = fights[
        fights["source_corpus"].isin(["ufc", "pre_unified"])
        & model.fillna(False).astype(bool)
    ]
    if ufc.empty:
        return empty
    return pd.concat([ufc["fighter_a"], ufc["fighter_b"]]).value_counts()


def contender_resume_ledger(
    fights: pd.DataFrame | None,
    history: pd.DataFrame | None,
    *,
    contender_line: float = CONTENDER_LINE_MU,
    min_opponent_ufc_bouts: int = MIN_OPPONENT_UFC_BOUTS,
    year_cap: float = RESUME_YEAR_CAP,
) -> pd.DataFrame:
    """Contenders actually beaten, priced by how far above the line they stood.

    **This replaces the rank-context schedule component** (2026-09-01). That
    component credited a win over an opponent standing in the top
    ``min(0.20 * pool, 15)`` of their division. Three things were wrong with it,
    all measured on the 2026-08-13 published scope:

    * **Its bar was a rank position in a pool the note defining it did not
      describe.** ``RANK_CONTEXT_TOP_SHARE`` was adopted 2026-08-26 to replace a
      fixed fifteen with a share of the field, against a table of median active
      division fields of 37-85. On the published ``majors,pre_unified`` scope
      those fields are 144-1435, so ``0.20 * pool > 15`` on **92.7%** of
      appearances, the clip to ``RANK_CONTEXT_TOP_N`` binds, and the share rule
      changes the window on 7.0% of them -- almost all catchweight rows. Top
      fifteen is the top **1.05%** of lightweight against **2.88%** of light
      heavyweight, a 2.7x difference inside the men's board alone.
    * **It did not agree with the board's own contender line.** 42.9% of wins
      over an opponent past this screen scored zero there, and 77.8% of the wins
      it did credit were over opponents below the line. Neil Magny is the pure
      case: six wins over contenders, and a rank-context win mass of 0.021.
    * **It read exposure, not contention.** Across the published top 100 it
      correlated **+0.360 with elite LOSSES** and **+0.013 with elite W-L**,
      because a fighter repeatedly booked against the division's top fifteen
      accumulates both. That is the gatekeeping failure this project already
      rejected for the elite board -- "a fighter who lost to ten elite opponents
      scores the same as one who beat them" -- sitting inside the majority of the
      published score's mass. Sean Strickland (9-7 against the screen, three of
      those wins as a betting underdog) and Michael Chandler (2-5, and 0-5 since
      2021) scored 232.0 and 225.6 on it.

    The screen here is the board's own: an opponent rated at or above
    ``contender_line`` **as at that bout** who also has ``min_opponent_ufc_bouts``
    UFC bouts of their own. Both halves are load-bearing and neither is new --
    see :data:`ratings.opponent_quality.MIN_OPPONENT_UFC_BOUTS`.

    Pricing reuses :func:`title_quality` against the contender line, so one
    function prices both ledgers and a win just past the line is worth a
    sixteenth of one 400 points above it. That answers the other half of the old
    component's defect, recorded in ``docs/NEXT_2026-08-28.md`` section 3.2: it
    counted ranked wins inside an 8% band rather than pricing them.

    :data:`UFC_POOL_OFFSET_ELO` is deliberately NOT applied here. On the title
    path the offset moves the opponent and the annual bar together, so ``q``
    still compares two numbers on one scale. The contender line is an absolute
    level on the published trajectory -- the one ``quality_win_record`` and the
    printed Elite-wins column read -- and adding an offset to one side of an
    absolute comparison would move the line rather than correct it.

    Returns the year-capped quality sum and the uncapped count of qualifying
    wins, which is the auditable display fact beside it.
    """
    if (
        fights is None or fights.empty
        or history is None or history.empty
        or "fighter_a" not in fights.columns
    ):
        return _empty_resume_ledger()

    h = history[["fighter", "event_date", "mu_whr"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h["mu_whr"] = pd.to_numeric(h["mu_whr"], errors="coerce")
    h = h.dropna(subset=["fighter", "event_date", "mu_whr"]).sort_values("event_date")
    if h.empty:
        return _empty_resume_ledger()

    f = fights.copy()
    f["event_date"] = pd.to_datetime(f.get("event_date"), errors="coerce")
    idx = f.index
    keep = f["event_date"].notna()
    for flag in ("is_excluded", "is_draw", "is_nc"):
        keep &= ~f.get(flag, pd.Series(False, index=idx)).fillna(False).astype(bool)
    f = f[keep]
    if f.empty:
        return _empty_resume_ledger()

    sides = pd.concat(
        [
            f.assign(fighter=f["fighter_a"], opponent=f["fighter_b"]),
            f.assign(fighter=f["fighter_b"], opponent=f["fighter_a"]),
        ],
        ignore_index=True,
        sort=False,
    )[["fighter", "opponent", "event_date", "winner"]].dropna(
        subset=["fighter", "opponent"]
    )
    wins = sides[sides["winner"].eq(sides["fighter"])].sort_values("event_date")
    if wins.empty:
        return _empty_resume_ledger()

    # The opponent's rating BEFORE the bout: a win may not price itself.
    priced = pd.merge_asof(
        wins,
        h.rename(columns={"fighter": "opponent", "mu_whr": "opponent_mu"}),
        on="event_date",
        by="opponent",
        allow_exact_matches=False,
    ).dropna(subset=["opponent_mu"])
    if priced.empty:
        return _empty_resume_ledger()

    tested = ufc_bout_counts(fights)
    priced = priced[
        priced["opponent"].map(tested).fillna(0).ge(int(min_opponent_ufc_bouts))
        & priced["opponent_mu"].ge(float(contender_line))
    ]
    if priced.empty:
        return _empty_resume_ledger()

    priced = priced.assign(
        weight=title_quality(
            priced["opponent_mu"], pd.Series(float(contender_line), index=priced.index)
        ),
        _year=priced["event_date"].dt.year,
    )
    per_year = (
        priced.groupby(["fighter", "_year"])["weight"].sum().clip(upper=float(year_cap))
    )
    out = (
        per_year.groupby("fighter")
        .sum()
        .rename("public_legacy_resume_quality")
        .reset_index()
    )
    counts = (
        priced.groupby("fighter")
        .size()
        .rename("public_legacy_contender_wins")
        .reset_index()
    )
    out = out.merge(counts, on="fighter", how="left")
    out["public_legacy_contender_wins"] = (
        pd.to_numeric(out["public_legacy_contender_wins"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
    return out[RESUME_LEDGER_COLUMNS]


def public_legacy_score_rows(
    current: pd.DataFrame,
    appearances: pd.DataFrame,
    *,
    skill_col: str = "symon_career_skill_mass",
    source_fights: pd.DataFrame | None = None,
    history: pd.DataFrame | None = None,
    reference: str | float | None = None,
    ufc_debut_dates: pd.Series | None = None,
    pool_offset_elo: float = UFC_POOL_OFFSET_ELO,
) -> pd.DataFrame:
    """Return one public legacy score row per fighter.

    The board answers two questions and says so. **Achievement** is what the
    career won: the title resume, priced by the opponent actually beaten in each
    title bout (:func:`title_quality_ledger`). **Quality of work** is how good
    the fighter was and who they actually beat: exposure-adjusted Career Skill
    Mass, and the contender resume (:func:`contender_resume_ledger`).

    The two halves are combined at :data:`LEGACY_ACHIEVEMENT_WEIGHT`, and the
    quality half is split at :data:`LEGACY_QUALITY_SKILL_SHARE`. Both are stated
    policy: no bout outcome can score them, because this score never enters a win
    probability. Each component is first divided by :func:`_scale`, the mean of
    its own top hundred values, so the weights mean what they say -- see the note
    above :data:`LEGACY_ACHIEVEMENT_WEIGHT` for what the previous divide-by-max
    silently did instead.

    ``history`` is the appearance-level WHR table. **Without it both the title
    and the contender resume are zero for everyone**, which silently reduces the
    board to skill alone -- callers that want the published board must pass it.

    The resume ledger is intentionally auditable. It repairs the product-label
    bug without mutating the latent rating model.
    """
    if current is None or current.empty or skill_col not in current.columns:
        return _empty()

    out = current[["fighter", skill_col]].copy()
    out = out.rename(columns={skill_col: "public_legacy_skill_mass"})
    debuts = (
        ufc_debut_dates
        if ufc_debut_dates is not None
        else ufc_debut_dates_from(source_fights)
    )
    quality_ledger = title_quality_ledger(
        source_fights,
        history,
        reference=reference,
        divisions=_division_labels(current),
        ufc_debut_dates=debuts,
        pool_offset_elo=pool_offset_elo,
    )
    resume_ledger = contender_resume_ledger(source_fights, history)
    ledger = _combine_title_ledgers(
        championship_resume_ledger(appearances),
        source_title_resume_ledger(source_fights) if source_fights is not None else _empty_title_ledger(),
    )
    out = out.merge(ledger, on="fighter", how="left")
    exposure = (
        organization_exposure_ledger(source_fights)
        if source_fights is not None
        else _empty_exposure_ledger()
    )
    out = out.merge(exposure, on="fighter", how="left")
    for col in (
        "public_legacy_title_appearances",
        "public_legacy_title_wins",
        "public_legacy_title_defenses",
        "public_legacy_title_win_divisions",
    ):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    if "public_legacy_rank_context_win_mass" not in out.columns:
        out["public_legacy_rank_context_win_mass"] = 0.0
    out["public_legacy_rank_context_win_mass"] = pd.to_numeric(
        out["public_legacy_rank_context_win_mass"], errors="coerce"
    ).fillna(0.0)
    out["public_legacy_exposure_factor"] = pd.to_numeric(
        out["public_legacy_exposure_factor"], errors="coerce"
    ).fillna(1.0)
    for col in (
        "public_legacy_ufc_bouts",
        "public_legacy_top_org_bouts",
        "public_legacy_unknown_org_bouts",
    ):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    for col in ("public_legacy_appearance_title_score", "public_legacy_source_title_score"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    # The multi-division bonus is retained as a REPORTED count only. It is no
    # longer added to any score: one extra belt used to be worth ten title
    # defenses, and the divisions a fighter won in are already inside the
    # opponents he beat to win them.
    out["public_legacy_multi_division_bonus"] = np.maximum(
        0, out["public_legacy_title_win_divisions"] - 1
    ).astype(float)

    quality = quality_ledger if quality_ledger is not None else _empty_quality_ledger()
    out = out.merge(quality, on="fighter", how="left")
    for col in ("public_legacy_title_quality", "public_legacy_qualifying_title_wins"):
        out[col] = pd.to_numeric(out.get(col), errors="coerce").fillna(0.0)
    out["public_legacy_qualifying_title_wins"] = (
        out["public_legacy_qualifying_title_wins"].astype(int)
    )
    out["public_legacy_title_score"] = (
        TITLE_QUALITY_SCALE * out["public_legacy_title_quality"]
    )

    out = out.merge(
        resume_ledger if resume_ledger is not None else _empty_resume_ledger(),
        on="fighter",
        how="left",
    )
    out["public_legacy_resume_quality"] = pd.to_numeric(
        out.get("public_legacy_resume_quality"), errors="coerce"
    ).fillna(0.0)
    out["public_legacy_contender_wins"] = (
        pd.to_numeric(out.get("public_legacy_contender_wins"), errors="coerce")
        .fillna(0)
        .astype(int)
    )
    # Exposure still multiplies both quality components. Neutralising it was
    # measured on 2026-08-27 and refuted -- zero-UFC fighters in the top 100
    # doubled -- so it stays until something measured replaces it, and it is the
    # standing item in ``docs/NEXT_2026-08-28.md`` section 3.3.
    out["public_legacy_resume_score"] = (
        RESUME_QUALITY_SCALE * out["public_legacy_resume_quality"]
        * out["public_legacy_exposure_factor"]
    )
    out["public_legacy_skill_score"] = (
        pd.to_numeric(out["public_legacy_skill_mass"], errors="coerce").fillna(0.0)
        * out["public_legacy_exposure_factor"]
    )
    # Achievement against quality of work, at one stated exchange rate.
    achievement = _scale(out["public_legacy_title_score"])
    quality = (
        LEGACY_QUALITY_SKILL_SHARE * _scale(out["public_legacy_skill_score"])
        + (1.0 - LEGACY_QUALITY_SKILL_SHARE) * _scale(out["public_legacy_resume_score"])
    )
    out["public_legacy_score"] = PUBLIC_LEGACY_DISPLAY_SCALE * (
        LEGACY_ACHIEVEMENT_WEIGHT * achievement
        + (1.0 - LEGACY_ACHIEVEMENT_WEIGHT) * quality
    )
    return out[LEGACY_SCORE_COLUMNS]
