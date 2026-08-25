"""Public career scores, computed from one appearance-level rating history.

Three functions, one input, no second scoring of the evidence:

* ``career_skill_mass`` — the all-time functional. Each active calendar year
  contributes at most once, and only the part of that year's mean rating that
  clears the year's bar. Measured in rating-point-years, which is not the same
  unit as a rating and must never be added to one.
* ``symon_prime_score`` — the best fixed 10-year window mean, empirical-Bayes
  shrunk toward the cohort by the window's own reliability. The fixed horizon
  keeps the leaderboard from being rank-shopped by sliding a window until a
  favourite wins.
* ``career_mass_family`` — the same functional across a range of bars, because
  the bar is what decides whether the board rewards height or duration and that
  choice should be visible rather than buried in a default.

Opponent quality, titles, method, streaks and activity are already inside the
rating history these read. They are deliberately not added again here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


PERIOD_COLUMNS = [
    "fighter",
    "score",
    "raw_mean",
    "shrinkage",
    "window_fights",
    "window_start",
    "window_end",
    "within_var",
    "sampling_var",
]

MASS_COLUMNS = [
    "fighter",
    "rank",
    "score",
    "active_years",
    "contributing_years",
    "peak_year_excess",
    "mean_year_excess",
    "first_year",
    "last_year",
]

# The bar a fighter-year is measured against, inside its own calendar year.
# "mean" is the average rated fighter-year; a float is that quantile of them.
#
# The choice is not cosmetic and is deliberately exposed rather than buried: it
# is what decides whether the board rewards height or duration. Three measured
# facts fix it (2026-08-21, snapshot 2026-08-13):
#
# 1. Scale drift is a pure LOCATION shift. Over 2005-2026 the level rises
#    steadily (year-vs-median r = +0.94, vs the 90th percentile +0.93) while the
#    spread does not move at all (90th-to-99th r = +0.03, median-to-90th +0.03).
#    A bar scoped to the year therefore cancels era drift exactly, and a fixed
#    absolute level would not -- it would hand modern fighters a bonus for the
#    roster having grown.
# 2. The bar must be sport-wide, NOT division-scoped. How deep a division was is
#    already posted in the rating, because the rating is built from the opponents
#    beaten. Scoping the bar to the division posts field depth a second time.
# 3. The height has to be the contender line, or the clip never binds. At the
#    mean, 100% of the top fifty's fighter-years clear the bar, so the positive
#    part is inert and career mass silently degenerates to years x average
#    excess -- a longevity board wearing a dominance label. The contender line is
#    ~60 fighters (a dozen divisions' top five) out of ~578 rated in a modern
#    year, i.e. the 0.896 quantile. Above ~0.95 the functional collapses instead
#    of tightening: at 0.975 the bar exceeds most careers outright and Aspinall
#    falls from 50th to 2364th into a mass tie at zero.
#
# The cost is honest and must travel with the board: a higher bar rests each
# career on fewer terms, so rank intervals widen. That is the price of measuring
# the intended thing, and is not a reason to measure a different one precisely.
#
# 4. **A quantile bar is population-relative, and 0.9 was calibrated on the
#    UFC-only population.** Point 3 justifies 0.9 by a *count* -- roughly 60
#    fighter-years out of roughly 578 in a modern year. A quantile only names
#    that count while the population stays that size. Measured on the
#    2026-08-13 snapshot:
#
#        scope                 year   rated fighter-years   clear the 0.9 bar
#        ufc                   2015                   570                  57
#        ufc                   2024                   625                  63
#        majors,pre_unified    2015                 4,190                 419
#        majors,pre_unified    2024                 2,441                 245
#
#    Same bar, same name, four to seven times as many fighters clearing it -- a
#    regional-circuit journeyman now clears a line that was chosen to mean "a
#    dozen divisions' top five". The published whole-sport board therefore
#    uses a capped contender line: the top decile while the observed sport is
#    small, capped at 60 fighter-years once mature. This prevents both scope
#    inflation (419 qualifiers on a whole-sport quantile) and the opposite
#    fixed-count failure (the 60th of only 65 fighters becoming 1994's bar).
DEFAULT_CAREER_REFERENCE = "contender:60"


def parse_reference(value: str | float) -> str | float:
    """Parse one CLI/config reference without rejecting named forms."""
    if not isinstance(value, str):
        return float(value)
    text = value.strip()
    if text == "mean" or text.startswith(("count:", "contender:", "hybrid:")):
        return text
    return float(text)


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _appearances(
    history: pd.DataFrame,
    *,
    mu_col: str,
    fighter_col: str,
    date_col: str,
    event_col: str,
) -> pd.DataFrame:
    required = [fighter_col, date_col, event_col, mu_col]
    if history is None or history.empty or any(c not in history.columns for c in required):
        return pd.DataFrame(columns=["fighter", "event_date", "event_name", "mu"])

    h = history[required].copy()
    h.columns = ["fighter", "event_date", "event_name", "mu"]
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h["mu"] = pd.to_numeric(h["mu"], errors="coerce")
    h = h.dropna(subset=["fighter", "event_date", "mu"])
    h["event_name"] = h["event_name"].fillna("").astype(str)
    return h


def _fighter_key(fighter: object) -> str:
    return f"{type(fighter).__name__}:{fighter!r}"


def _rank_order(df: pd.DataFrame, secondary: str) -> pd.DataFrame:
    """Sort by score, then by the stated secondary key, then reproducibly.

    The ``_fighter_key`` term is a determinism tie-break, not a ranking
    criterion: it exists so two identical runs emit identical row order. Row
    position is therefore **not** a rank, and callers must not read one off it.
    Use the explicit ``rank`` column that :func:`career_skill_mass` attaches --
    it is a ``method="min"`` rank, so tied fighters share one place instead of
    being separated alphabetically.
    """
    if df.empty:
        return df
    out = df.assign(_fighter_key=df["fighter"].map(_fighter_key))
    out = out.sort_values(
        ["score", secondary, "_fighter_key"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    return out.drop(columns="_fighter_key").reset_index(drop=True)


def _best_window(
    fighter: object,
    group: pd.DataFrame,
    *,
    window_days: int,
    min_fights: int,
) -> dict[str, object] | None:
    g = group.sort_values(["event_date", "event_name"], kind="mergesort").reset_index(drop=True)
    dates = g["event_date"].to_numpy(dtype="datetime64[ns]")
    mu = g["mu"].to_numpy(dtype="float64")
    cs = np.concatenate(([0.0], np.cumsum(mu, dtype="float64")))
    span = np.timedelta64(window_days, "D")

    best: tuple[float, int, np.datetime64, np.datetime64, int, int] | None = None
    i = 0
    for j in range(len(g)):
        floor = dates[j] - span
        while dates[i] < floor:
            i += 1
        n = j - i + 1
        if n < min_fights:
            continue
        mean = float((cs[j + 1] - cs[i]) / n)
        candidate = (mean, n, dates[i], dates[j], i, j)
        if best is None:
            best = candidate
            continue
        if mean > best[0]:
            best = candidate
        elif mean == best[0] and (
            n > best[1] or (n == best[1] and dates[i] < best[2])
        ):
            best = candidate

    if best is None:
        return None

    raw_mean, n, start, end, lo, hi = best
    values = mu[lo : hi + 1]
    within_var = float(np.var(values, ddof=1)) if n > 1 else 0.0
    sampling_var = within_var / n
    return {
        "fighter": fighter,
        "raw_mean": raw_mean,
        "window_fights": int(n),
        "window_start": pd.Timestamp(start),
        "window_end": pd.Timestamp(end),
        "within_var": within_var,
        "sampling_var": sampling_var,
    }


def _eb(rows: list[dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    raw = df["raw_mean"].to_numpy(dtype="float64")
    sampling = df["sampling_var"].to_numpy(dtype="float64")
    pooled = float(raw.mean())

    if len(df) < 2:
        shrinkage = np.ones(len(df), dtype="float64")
    else:
        observed_var = float(np.var(raw, ddof=1))
        tau2 = max(0.0, observed_var - float(sampling.mean()))
        if tau2 == 0.0:
            shrinkage = np.where(sampling == 0.0, 1.0, 0.0)
        else:
            shrinkage = tau2 / (tau2 + sampling)

    df["shrinkage"] = shrinkage
    df["score"] = pooled + shrinkage * (raw - pooled)
    return df[PERIOD_COLUMNS]


def symon_period_score(
    history: pd.DataFrame,
    *,
    window_days: int,
    min_fights: int,
    mu_col: str = "mu_whr",
    fighter_col: str = "fighter",
    date_col: str = "event_date",
    event_col: str = "event_name",
) -> pd.DataFrame:
    """Best fixed-day latent-rating mean, reliability-shrunk to its cohort."""
    if not isinstance(window_days, (int, np.integer)) or window_days < 0:
        raise ValueError("window_days must be a non-negative integer")
    if not isinstance(min_fights, (int, np.integer)) or min_fights < 1:
        raise ValueError("min_fights must be a positive integer")

    h = _appearances(
        history,
        mu_col=mu_col,
        fighter_col=fighter_col,
        date_col=date_col,
        event_col=event_col,
    )
    if h.empty:
        return _empty(PERIOD_COLUMNS)

    rows = []
    for fighter, group in h.groupby("fighter", sort=False):
        row = _best_window(
            fighter,
            group,
            window_days=int(window_days),
            min_fights=int(min_fights),
        )
        if row is not None:
            rows.append(row)
    if not rows:
        return _empty(PERIOD_COLUMNS)
    return _rank_order(_eb(rows), "raw_mean")


def symon_prime_score(
    history: pd.DataFrame,
    *,
    mu_col: str = "mu_whr",
    fighter_col: str = "fighter",
    date_col: str = "event_date",
    event_col: str = "event_name",
) -> pd.DataFrame:
    """Ten-year Symon period score; at least 13 actual appearances."""
    return symon_period_score(
        history,
        window_days=3652,
        min_fights=13,
        mu_col=mu_col,
        fighter_col=fighter_col,
        date_col=date_col,
        event_col=event_col,
    )


def year_reference(annual: pd.DataFrame, reference: str | float) -> pd.Series:
    """Return each year's bar, indexed by year.

    ``"mean"`` is the mean of that year's fighter-year means; a float in [0, 1]
    is that quantile of them.

    ``"count:<n>"`` is the level the ``n``-th best fighter-year of that year
    reached -- the same statement a quantile was chosen to make, but stated as
    a count so it survives a change of scope. A quantile names a fixed
    *fraction* of whoever happens to be rated; admitting a second corpus can
    multiply the rated population without changing the sport, and the bar then
    silently admits four to seven times as many fighters (see the note above
    ``DEFAULT_CAREER_REFERENCE``). A year with fewer than ``n`` rated
    fighter-years returns no local bar. :func:`career_skill_mass` then uses the
    whole-sample contender level, so sparse pioneer seasons do not get a free
    floor from their weakest observed fighter.

    ``"contender:<n>"`` is the capped contender line used in production: the
    top decile in a field smaller than ``10*n``, otherwise the top ``n``. It
    keeps a constant elite fraction while the sport is genuinely small, then a
    constant global contender capacity once roster growth becomes undercard
    breadth rather than more divisions.

    ``"hybrid:<lam>"`` blends the contemporaneous bar with a fixed level taken
    over the whole sample:

        bar(a) = lam * year_bar(a) + (1 - lam) * absolute_bar

    ``lam = 1`` reproduces ``"mean"`` exactly and reads "how far above his
    peers"; ``lam = 0`` is a single fixed level and reads "how high he actually
    was". The blend exists so the choice is a stated number rather than a buried
    default -- but see ``docs/`` before leaning on it: measured on UFC-only
    scope the whole lam range moves top-50 ranks by a median of 3 places inside
    bootstrap intervals a median of 102 places wide, so it is not currently an
    identified choice. It becomes one only when the scale spans genuinely
    different eras.
    """
    by_year = annual.groupby("year", sort=False)["annual_mean"]
    if isinstance(reference, str):
        if reference == "mean":
            return by_year.mean()
        if reference.startswith("count:"):
            n = int(reference.split(":", 1)[1])
            if n < 1:
                raise ValueError("a count reference must name at least one fighter-year")
            return by_year.apply(
                lambda s: float(s.nlargest(n).iloc[-1]) if len(s) >= n else float("nan")
            )
        if reference.startswith("contender:"):
            n = int(reference.split(":", 1)[1])
            if n < 1:
                raise ValueError("a contender reference must name at least one fighter-year")
            return by_year.apply(
                lambda s: float(
                    s.nlargest(min(n, max(1, int(np.ceil(0.10 * len(s)))))).iloc[-1]
                ) if len(s) else float("nan")
            )
        if reference.startswith("hybrid:"):
            lam = float(reference.split(":", 1)[1])
            if not 0.0 <= lam <= 1.0:
                raise ValueError("a hybrid lam must lie in [0, 1]")
            absolute = float(annual["annual_mean"].mean())
            return lam * by_year.mean() + (1.0 - lam) * absolute
        raise ValueError(f"unknown reference: {reference!r}")
    q = float(reference)
    if not 0.0 <= q <= 1.0:
        raise ValueError("a quantile reference must lie in [0, 1]")
    return by_year.quantile(q)


def career_skill_mass(
    history: pd.DataFrame,
    *,
    mu_col: str = "mu_whr",
    fighter_col: str = "fighter",
    date_col: str = "event_date",
    event_col: str = "event_name",
    min_appearances_per_year: int = 1,
    field_min_population: int = 5,
    reference: str | float = DEFAULT_CAREER_REFERENCE,
) -> pd.DataFrame:
    """Sum positive fighter-year skill excess, one contribution per active year."""
    if (
        not isinstance(min_appearances_per_year, (int, np.integer))
        or min_appearances_per_year < 1
    ):
        raise ValueError("min_appearances_per_year must be a positive integer")
    if not isinstance(field_min_population, (int, np.integer)) or field_min_population < 1:
        raise ValueError("field_min_population must be a positive integer")

    h = _appearances(
        history,
        mu_col=mu_col,
        fighter_col=fighter_col,
        date_col=date_col,
        event_col=event_col,
    )
    if h.empty:
        return _empty(MASS_COLUMNS)

    h["year"] = h["event_date"].dt.year.astype("int64")
    annual = (
        h.groupby(["fighter", "year"], sort=False)["mu"]
        .agg(annual_mean="mean", appearances="size")
        .reset_index()
    )
    annual = annual[annual["appearances"] >= int(min_appearances_per_year)].copy()
    if annual.empty:
        return _empty(MASS_COLUMNS)

    bar = year_reference(annual, reference)
    # A year too thin to describe its own field falls back to the whole-sample
    # bar, so a sparse early season cannot hand out cheap excess. If the entire
    # sample is thinner than a requested count, use its maximum: nobody clears
    # an unidentifiable contender line, which is conservative abstention rather
    # than a cheap floor or NaN scores.
    global_bar = float(year_reference(annual.assign(year=0), reference).iloc[0])
    if not np.isfinite(global_bar):
        global_bar = float(annual["annual_mean"].max())
    population = annual.groupby("year", sort=False)["annual_mean"].transform("size")
    annual["field_mean"] = annual["year"].map(bar)
    annual.loc[
        (population < int(field_min_population)) | annual["field_mean"].isna(),
        "field_mean",
    ] = global_bar
    annual["excess"] = (annual["annual_mean"] - annual["field_mean"]).clip(lower=0.0)

    grouped = annual.groupby("fighter", sort=False)["excess"]
    out = pd.DataFrame({
        "score": grouped.sum(),
        "active_years": grouped.size().astype(int),
        "contributing_years": grouped.apply(lambda s: int((s > 0.0).sum())),
        "peak_year_excess": grouped.max(),
        "mean_year_excess": grouped.mean(),
    })
    years = annual.groupby("fighter", sort=False)["year"]
    out["first_year"] = years.min().astype(int)
    out["last_year"] = years.max().astype(int)
    out = out.reset_index()
    # A "min" rank, so a tie prints as one shared place. The mass distribution
    # has one enormous tie by construction -- every fighter who never cleared
    # the bar in any year scores exactly zero -- and an ordinal rank across it
    # would present the determinism tie-break as if it measured something.
    out["rank"] = out["score"].rank(ascending=False, method="min").astype(int)
    out = out[MASS_COLUMNS]
    return _rank_order(out, "peak_year_excess")


def career_mass_family(
    history: pd.DataFrame,
    *,
    references: tuple[str | float, ...] = ("mean", 0.5, 0.75, 0.9, 0.95),
    **kwargs,
) -> pd.DataFrame:
    """Career mass and rank at several bars — the dominance/longevity dial.

    One row per (fighter, reference). A fighter whose rank barely moves across
    the family is ranked by something the bar choice does not control; one whose
    rank collapses as the bar rises was being carried by years spent slightly
    above average.
    """
    frames = []
    for reference in references:
        board = career_skill_mass(history, reference=reference, **kwargs)
        if board.empty:
            continue
        board = board.assign(reference=str(reference))
        frames.append(board)
    if not frames:
        return pd.DataFrame(columns=[*MASS_COLUMNS, "reference"])
    return pd.concat(frames, ignore_index=True)
