"""Optional market-odds loader for the `mu_odds_adjusted` rating stream.

This module is the data-side half of the odds adjustment feature. The
analysis-side math (residual -> percentile -> weight) lives in
`ratings/odds_adjustment.py`.

Design:
- `mu_canonical` and `mu_method` are never odds-aware. This module never
  mutates `canonical_fights`; odds live in a separate optional artifact
  `odds_lines.parquet` keyed by `fight_url`.
- If `odds_lines.parquet` does not exist for a snapshot, `load_odds_lines`
  returns an empty DataFrame with the enriched schema and the engine
  skips the odds-adjusted pass entirely. Downstream notebook/viz code
  should detect the empty frame and show "odds unavailable" rather than
  fail.
- Conversion helpers are pure (American/decimal -> implied -> no-vig)
  and unit-testable independently of pandas.

Schema of `odds_lines.parquet` (raw, prior to enrichment):
    fight_url, event_date, event_name,
    fighter_a, fighter_b,
    odds_source,                           # str, e.g. "fixture", "vendor-X"
    odds_fighter_a, odds_fighter_b,        # str, matches the fighter the price belongs to
    american_odds_a, american_odds_b,      # float, nullable
    decimal_odds_a,  decimal_odds_b,       # float, nullable

Columns added by `compute_implied_probs`:
    implied_prob_a_raw, implied_prob_b_raw,
    implied_prob_a_no_vig, implied_prob_b_no_vig,
    market_favorite, market_underdog,
    market_favorite_prob, market_underdog_prob,
    odds_data_quality                      # 'ok' | 'one_side_missing' | 'missing'
                                           # | 'negative_vig' | 'implausible'
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


# Raw columns that an ingest tool must populate.
RAW_ODDS_COLUMNS: tuple[str, ...] = (
    "fight_url",
    "event_date",
    "event_name",
    "fighter_a",
    "fighter_b",
    "odds_source",
    "odds_fighter_a",
    "odds_fighter_b",
    "american_odds_a",
    "american_odds_b",
    "decimal_odds_a",
    "decimal_odds_b",
)

# Columns added by `compute_implied_probs`.
ENRICHED_ODDS_COLUMNS: tuple[str, ...] = (
    "implied_prob_a_raw",
    "implied_prob_b_raw",
    "implied_prob_a_no_vig",
    "implied_prob_b_no_vig",
    "market_favorite",
    "market_underdog",
    "market_favorite_prob",
    "market_underdog_prob",
    "odds_data_quality",
)

# Sanity bounds on the raw implied-probability sum across both sides of a
# bout. A single sportsbook's vig'd line sums to ~1.04–1.08 (the vig). But
# this loader also accepts best-of-market aggregated quotes (e.g. from the
# jasonchanhku UFC archive) where competition between books has competed
# the vig away and individual bouts can show sums slightly below 1.0. The
# floor here is permissive (0.85) — only truly broken data falls below
# that empirical range; the no-vig math still works regardless.
_RAW_SUM_MIN = 0.85
_RAW_SUM_MAX = 2.0


# ---------------------------------------------------------------------------
# Pure conversions

def american_to_implied(odds: float | int | None) -> float | None:
    """American moneyline -> raw implied probability (with vig).

    `+A`  (A > 0): underdog. p = 100 / (A + 100).
    `-A`  (A < 0): favorite. p = |A| / (|A| + 100).
    """
    if odds is None:
        return None
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if math.isnan(o) or o == 0:
        return None
    if o > 0:
        return 100.0 / (o + 100.0)
    return -o / (-o + 100.0)


def decimal_to_implied(decimal_odds: float | None) -> float | None:
    """Decimal odds -> raw implied probability.

    Decimal odds < 1.0 are nonsensical (the bettor would lose money on a
    winning bet), so return None for those.
    """
    if decimal_odds is None:
        return None
    try:
        d = float(decimal_odds)
    except (TypeError, ValueError):
        return None
    if math.isnan(d) or d <= 1.0:
        return None
    return 1.0 / d


def american_to_decimal(odds: float | int | None) -> float | None:
    """American moneyline -> decimal odds, for normalization in viz tables."""
    if odds is None:
        return None
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if math.isnan(o) or o == 0:
        return None
    if o > 0:
        return 1.0 + o / 100.0
    return 1.0 + 100.0 / -o


def remove_vig(p_a_raw: float | None, p_b_raw: float | None) -> tuple[float | None, float | None]:
    """Proportionally rescale a pair of raw implieds so they sum to 1.0.

    If either side is missing the no-vig pair is undefined; both come back
    as None and the caller should flag `odds_data_quality`.
    """
    if p_a_raw is None or p_b_raw is None:
        return (None, None)
    if math.isnan(p_a_raw) or math.isnan(p_b_raw):
        return (None, None)
    s = p_a_raw + p_b_raw
    if s <= 0:
        return (None, None)
    return (p_a_raw / s, p_b_raw / s)


# ---------------------------------------------------------------------------
# Pandas enrichment

def _implied_for_side(american: float | None, decimal: float | None) -> float | None:
    """Resolve which odds format to use for one fighter side.

    Preference order: American moneyline first (the dominant US sportsbook
    format for UFC), then decimal as fallback. If neither is present,
    return None.
    """
    if american is not None and not _isnan(american):
        return american_to_implied(american)
    if decimal is not None and not _isnan(decimal):
        return decimal_to_implied(decimal)
    return None


def _isnan(x) -> bool:
    if x is None:
        return True
    try:
        return math.isnan(float(x))
    except (TypeError, ValueError):
        return True


def _quality_flag(p_a_raw: float | None, p_b_raw: float | None) -> str:
    a_missing = p_a_raw is None or _isnan(p_a_raw)
    b_missing = p_b_raw is None or _isnan(p_b_raw)
    if a_missing and b_missing:
        return "missing"
    if a_missing or b_missing:
        return "one_side_missing"
    s = p_a_raw + p_b_raw
    if s < _RAW_SUM_MIN:
        return "negative_vig"
    if s > _RAW_SUM_MAX:
        return "implausible"
    return "ok"


def compute_implied_probs(df: pd.DataFrame) -> pd.DataFrame:
    """Add implied / no-vig / favorite-underdog columns to a raw odds frame.

    Leaves raw columns untouched. Returns a copy.
    """
    if df.empty:
        out = df.copy()
        for c in ENRICHED_ODDS_COLUMNS:
            out[c] = pd.Series(dtype="object" if c.startswith("market_") or c == "odds_data_quality" else "float64")
        return out

    out = df.copy()
    amer_a = out.get("american_odds_a", pd.Series(index=out.index, dtype="float64"))
    amer_b = out.get("american_odds_b", pd.Series(index=out.index, dtype="float64"))
    dec_a = out.get("decimal_odds_a", pd.Series(index=out.index, dtype="float64"))
    dec_b = out.get("decimal_odds_b", pd.Series(index=out.index, dtype="float64"))
    raw_a = amer_a.map(american_to_implied).combine_first(dec_a.map(decimal_to_implied))
    raw_b = amer_b.map(american_to_implied).combine_first(dec_b.map(decimal_to_implied))
    raw_sum = raw_a + raw_b
    valid_pair = raw_a.notna() & raw_b.notna() & raw_sum.gt(0)
    out["implied_prob_a_raw"] = raw_a
    out["implied_prob_b_raw"] = raw_b
    out["implied_prob_a_no_vig"] = raw_a.where(valid_pair) / raw_sum.where(valid_pair)
    out["implied_prob_b_no_vig"] = raw_b.where(valid_pair) / raw_sum.where(valid_pair)

    missing_a = raw_a.isna()
    missing_b = raw_b.isna()
    out["odds_data_quality"] = "ok"
    out.loc[missing_a & missing_b, "odds_data_quality"] = "missing"
    out.loc[missing_a ^ missing_b, "odds_data_quality"] = "one_side_missing"
    complete = ~(missing_a | missing_b)
    out.loc[complete & raw_sum.lt(_RAW_SUM_MIN), "odds_data_quality"] = "negative_vig"
    out.loc[complete & raw_sum.gt(_RAW_SUM_MAX), "odds_data_quality"] = "implausible"

    fav_is_a = out["implied_prob_a_no_vig"] > out["implied_prob_b_no_vig"]
    fav_is_b = out["implied_prob_b_no_vig"] > out["implied_prob_a_no_vig"]
    out["market_favorite"] = pd.NA
    out["market_underdog"] = pd.NA
    out["market_favorite_prob"] = pd.NA
    out["market_underdog_prob"] = pd.NA
    out.loc[fav_is_a, "market_favorite"] = out.loc[fav_is_a, "fighter_a"]
    out.loc[fav_is_a, "market_underdog"] = out.loc[fav_is_a, "fighter_b"]
    out.loc[fav_is_a, "market_favorite_prob"] = out.loc[fav_is_a, "implied_prob_a_no_vig"]
    out.loc[fav_is_a, "market_underdog_prob"] = out.loc[fav_is_a, "implied_prob_b_no_vig"]
    out.loc[fav_is_b, "market_favorite"] = out.loc[fav_is_b, "fighter_b"]
    out.loc[fav_is_b, "market_underdog"] = out.loc[fav_is_b, "fighter_a"]
    out.loc[fav_is_b, "market_favorite_prob"] = out.loc[fav_is_b, "implied_prob_b_no_vig"]
    out.loc[fav_is_b, "market_underdog_prob"] = out.loc[fav_is_b, "implied_prob_a_no_vig"]
    return out


# ---------------------------------------------------------------------------
# Snapshot I/O

def _empty_enriched_frame() -> pd.DataFrame:
    cols = list(RAW_ODDS_COLUMNS) + list(ENRICHED_ODDS_COLUMNS)
    return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})


def load_odds_lines(snapshot_dir: Path) -> pd.DataFrame:
    """Read `odds_lines.parquet` for a snapshot, enriched with implied probs.

    Returns an empty frame (with the enriched schema) if the artifact is
    absent. This lets downstream callers always do the merge without
    branching on existence — empty merges are no-ops.
    """
    path = Path(snapshot_dir) / "odds_lines.parquet"
    if not path.exists():
        return _empty_enriched_frame()
    raw = pd.read_parquet(path)
    return compute_implied_probs(raw)


def has_odds_artifact(snapshot_dir: Path) -> bool:
    """True iff `odds_lines.parquet` exists for the snapshot."""
    return (Path(snapshot_dir) / "odds_lines.parquet").exists()
