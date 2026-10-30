"""American/decimal odds conversions and their missing-value rules."""
from __future__ import annotations

import math


def _value(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def american_to_implied(odds: float | None) -> float | None:
    """American moneyline -> raw implied probability (with vig).

    `+A`  (A > 0): underdog. p = 100 / (A + 100).
    `-A`  (A < 0): favorite. p = |A| / (|A| + 100).
    """
    o = _value(odds)
    if o is None or o == 0:
        return None
    if o > 0:
        return 100.0 / (o + 100.0)
    return -o / (-o + 100.0)


def decimal_to_implied(decimal_odds: float | None) -> float | None:
    """Decimal odds -> raw implied probability.

    Decimal odds < 1.0 are nonsensical (the bettor would lose money on a
    winning bet), so return None for those.
    """
    d = _value(decimal_odds)
    if d is None or d <= 1.0:
        return None
    return 1.0 / d


def american_to_decimal(odds: float | None) -> float | None:
    """American moneyline -> decimal odds, for normalization in viz tables."""
    o = _value(odds)
    if o is None or o == 0:
        return None
    if o > 0:
        return 1.0 + o / 100.0
    return 1.0 + 100.0 / -o


def decimal_to_american(decimal_odds: object) -> float | None:
    dec = _value(decimal_odds)
    if dec is None or dec <= 1.0:
        return None
    if dec >= 2.0:
        return (dec - 1.0) * 100.0
    return -100.0 / (dec - 1.0)
