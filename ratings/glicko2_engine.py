"""Glicko-2 rating engine wrapper.

Two parallel ratings are maintained for every fighter:
- `μ_canonical`: scores strictly {0, 0.5, 1}. Use this for calibration plots
   and win-probability predictions — it's mathematically clean.
- `μ_method`:   continuous winner-score in [0.7, 1.0] depending on Greco's
   method bucket. Use this for the "method-bonus" leaderboard the user
   asked for. Flagged as experimental — DO NOT use for calibration.

Rating periods: per-event. Each UFC event triggers one round of updates for
every fighter on the card. Fighters who didn't fight on the event are NOT
inflated this round; they're lazy-inflated when they next appear, based on
elapsed real-world months.

τ (volatility constant): 0.5 — Glickman's worked-example value, and a
conservative choice for the small-sample regime of MMA. **Tweak this** if
you want more or less ranking churn between fights. See `DEFAULT_TAU`. The
vendored `_glicko2.py` default TAU is shadowed here by the project default
of 0.5.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

import pandas as pd

from ._glicko2 import Glicko2, Rating


# τ controls volatility. Lower = more conservative ratings. The Glickman
# paper uses 0.5 and the library default is 1.0 — start at 0.5 and tweak
# upward if rankings feel sluggish.
DEFAULT_TAU = 0.5


@dataclass
class FighterState:
    canonical: Rating
    method: Rating
    last_event_date: pd.Timestamp | None = None
    peak_mu_canonical: float = 0.0
    peak_mu_method: float = 0.0


@dataclass
class HistoryRow:
    fighter: str
    event_date: pd.Timestamp
    event_name: str
    mu_canonical: float
    phi_canonical: float
    sigma_canonical: float
    mu_method: float
    phi_method: float
    sigma_method: float
    opponents_this_event: int


def _months_between(a: pd.Timestamp, b: pd.Timestamp) -> float:
    if a is None or b is None:
        return 0.0
    return (b - a).days / 30.4375


def _rate_weighted(
    env: Glicko2,
    rating: Rating,
    series: list[tuple[float, Rating, float]],
) -> Rating:
    """Weighted Glicko-2 rate-step.

    Mirrors `Glicko2.rate()` in `_glicko2.py` (which is vendored and not
    edited per its header), but multiplies each term in the variance and
    difference accumulators by a per-result weight `w_i`. When every weight
    is exactly 1.0 the output is byte-for-byte identical to `env.rate()`
    within floating-point tolerance — verified by a regression test.

    `series` entries are `(actual_score, other_rating, weight)`. Weights
    of 0.0 drop the result from the update. An empty series, or a series
    whose weights sum (in the variance-inverse sense) to zero, returns
    the inactive-period φ-inflated rating, same as `env.rate(_, [])`.
    """
    rating = env.scale_down(rating)
    if not series:
        phi_star = math.sqrt(rating.phi ** 2 + rating.sigma ** 2)
        return env.scale_up(env.create_rating(rating.mu, phi_star, rating.sigma))

    variance_inv = 0.0
    difference = 0.0
    for actual_score, other_rating, weight in series:
        if weight == 0:
            continue
        other_rating = env.scale_down(other_rating)
        impact = env.reduce_impact(other_rating)
        expected_score = env.expect_score(rating, other_rating, impact)
        # The weight multiplies both accumulators, preserving Glickman's
        # variance-weighted-difference invariant while scaling result impact.
        variance_inv += weight * (impact ** 2) * expected_score * (1 - expected_score)
        difference += weight * impact * (actual_score - expected_score)

    if variance_inv == 0:
        # Either an empty series after weight=0 filtering, or numerical
        # degeneracy. Treat as inactive period.
        phi_star = math.sqrt(rating.phi ** 2 + rating.sigma ** 2)
        return env.scale_up(env.create_rating(rating.mu, phi_star, rating.sigma))

    difference /= variance_inv
    variance = 1.0 / variance_inv
    sigma = env.determine_sigma(rating, difference, variance)
    phi_star = math.sqrt(rating.phi ** 2 + sigma ** 2)
    phi = 1.0 / math.sqrt(1.0 / phi_star ** 2 + 1.0 / variance)
    mu = rating.mu + (phi ** 2) * (difference / variance)
    return env.scale_up(env.create_rating(mu, phi, sigma))


class RatingEngine:
    """Per-event Glicko-2 engine with lazy φ-inflation between appearances."""

    def __init__(self, tau: float = DEFAULT_TAU):
        self.env = Glicko2(tau=tau)
        self.tau = tau
        self.states: dict[str, FighterState] = {}
        self.history: list[HistoryRow] = []

    def _ensure(self, fighter: str) -> FighterState:
        if fighter not in self.states:
            self.states[fighter] = FighterState(
                canonical=self.env.create_rating(),
                method=self.env.create_rating(),
            )
        return self.states[fighter]

    def _inflate(self, fighter: str, current_date: pd.Timestamp) -> None:
        st = self.states[fighter]
        if st.last_event_date is None:
            return
        n = int(_months_between(st.last_event_date, current_date))
        if n <= 0:
            return
        # apply the inactive-period update once per elapsed month
        for _ in range(n):
            st.canonical = self.env.rate(st.canonical, [])
            st.method = self.env.rate(st.method, [])

    def process_event(self, event_date: pd.Timestamp, event_name: str, bouts: list[dict]) -> None:
        """Process all bouts on a single event atomically.

        Each dict must have: fighter_a, fighter_b, winner, is_draw,
        method_score_winner (None if draw or unknown).
        """
        fighters = set()
        for b in bouts:
            fighters.add(b["fighter_a"])
            fighters.add(b["fighter_b"])

        for f in fighters:
            self._ensure(f)
            self._inflate(f, event_date)

        # Snapshot pre-event ratings — opponents are evaluated at start-of-period.
        pre_canon = {f: self.states[f].canonical for f in fighters}
        pre_method = {f: self.states[f].method for f in fighters}

        series_canon: dict[str, list[tuple[float, Rating]]] = {f: [] for f in fighters}
        series_method: dict[str, list[tuple[float, Rating]]] = {f: [] for f in fighters}

        for b in bouts:
            a, c = b["fighter_a"], b["fighter_b"]
            if b["is_draw"]:
                sa_c, sc_c = 0.5, 0.5
                sa_m, sc_m = 0.5, 0.5
            elif b["winner"] == a:
                sa_c, sc_c = 1.0, 0.0
                ms = b.get("method_score_winner")
                if ms is None or pd.isna(ms):
                    sa_m, sc_m = 1.0, 0.0
                else:
                    sa_m, sc_m = float(ms), 1.0 - float(ms)
            elif b["winner"] == c:
                sa_c, sc_c = 0.0, 1.0
                ms = b.get("method_score_winner")
                if ms is None or pd.isna(ms):
                    sa_m, sc_m = 0.0, 1.0
                else:
                    sa_m, sc_m = 1.0 - float(ms), float(ms)
            else:
                # winner None for non-draw, non-excluded bout — shouldn't happen
                # in the canonical table, but skip defensively.
                continue
            series_canon[a].append((sa_c, pre_canon[c]))
            series_canon[c].append((sc_c, pre_canon[a]))
            series_method[a].append((sa_m, pre_method[c]))
            series_method[c].append((sc_m, pre_method[a]))

        # Apply rate() once per fighter using pre-event snapshots.
        for f in fighters:
            st = self.states[f]
            if series_canon[f]:
                st.canonical = self.env.rate(pre_canon[f], series_canon[f])
                st.method = self.env.rate(pre_method[f], series_method[f])
            st.peak_mu_canonical = max(st.peak_mu_canonical, st.canonical.mu)
            st.peak_mu_method = max(st.peak_mu_method, st.method.mu)
            st.last_event_date = event_date
            self.history.append(HistoryRow(
                fighter=f,
                event_date=event_date,
                event_name=event_name,
                mu_canonical=st.canonical.mu,
                phi_canonical=st.canonical.phi,
                sigma_canonical=st.canonical.sigma,
                mu_method=st.method.mu,
                phi_method=st.method.phi,
                sigma_method=st.method.sigma,
                opponents_this_event=len(series_canon[f]),
            ))

    # ------------------------------------------------------------------
    # Output helpers

    def history_df(self) -> pd.DataFrame:
        rows = [r.__dict__ for r in self.history]
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        return df.sort_values(["fighter", "event_date"]).reset_index(drop=True)

    def current_table(self) -> pd.DataFrame:
        rows = []
        for f, st in self.states.items():
            rows.append({
                "fighter": f,
                "mu_canonical": st.canonical.mu,
                "phi_canonical": st.canonical.phi,
                "sigma_canonical": st.canonical.sigma,
                "mu_method": st.method.mu,
                "phi_method": st.method.phi,
                "sigma_method": st.method.sigma,
                "peak_mu_canonical": st.peak_mu_canonical,
                "peak_mu_method": st.peak_mu_method,
                "last_event_date": st.last_event_date,
            })
        df = pd.DataFrame(rows).sort_values("mu_canonical", ascending=False).reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    # Prediction helpers (use μ_canonical only — calibration valid)

    def predict_win_prob(self, a: str, b: str) -> float:
        """Probability that `a` beats `b` at current ratings."""
        ra = self.states[a].canonical if a in self.states else self.env.create_rating()
        rb = self.states[b].canonical if b in self.states else self.env.create_rating()
        # scale down for the internal expect_score
        ra_s = self.env.scale_down(ra)
        rb_s = self.env.scale_down(rb)
        impact = self.env.reduce_impact(rb_s)
        return self.env.expect_score(ra_s, rb_s, impact)

    def matchup_quality(self, a: str, b: str) -> float:
        ra = self.states[a].canonical if a in self.states else self.env.create_rating()
        rb = self.states[b].canonical if b in self.states else self.env.create_rating()
        return self.env.quality_1vs1(ra, rb)


@dataclass
class WeightedFighterState:
    rating: Rating
    last_event_date: pd.Timestamp | None = None
    peak_mu: float = 0.0


@dataclass
class WeightedHistoryRow:
    fighter: str
    event_date: pd.Timestamp
    event_name: str
    mu: float
    phi: float
    sigma: float
    opponents_this_event: int
    total_weight: float


class WeightedRatingEngine:
    """Per-event Glicko-2 engine that applies a per-result update weight.

    Drop-in alternative for the odds-adjusted rating stream. Tracks a
    single canonical-scored rating (no method-bonus side stream — odds
    adjustment is orthogonal to method scoring by design). With every
    weight set to 1.0 the per-event mu/phi/sigma evolve identically to
    `RatingEngine`'s canonical stream (regression-tested).
    """

    def __init__(self, tau: float = DEFAULT_TAU, score_mode: str = "canonical"):
        if score_mode not in {"canonical", "method", "quality_method"}:
            raise ValueError(f"unknown weighted score mode: {score_mode!r}")
        self.env = Glicko2(tau=tau)
        self.tau = tau
        self.score_mode = score_mode
        self.states: dict[str, WeightedFighterState] = {}
        self.history: list[WeightedHistoryRow] = []

    def _ensure(self, fighter: str) -> WeightedFighterState:
        if fighter not in self.states:
            self.states[fighter] = WeightedFighterState(rating=self.env.create_rating())
        return self.states[fighter]

    def _inflate(self, fighter: str, current_date: pd.Timestamp) -> None:
        st = self.states[fighter]
        if st.last_event_date is None:
            return
        n = int(_months_between(st.last_event_date, current_date))
        if n <= 0:
            return
        for _ in range(n):
            st.rating = self.env.rate(st.rating, [])

    def process_event(
        self,
        event_date: pd.Timestamp,
        event_name: str,
        bouts: list[dict],
    ) -> None:
        """Process all bouts on a single event atomically.

        Each dict must have: fighter_a, fighter_b, winner, is_draw,
        weight_a (per-result update weight applied to fighter_a's update),
        weight_b (same for fighter_b). Weights default to 1.0 when absent.
        """
        fighters = set()
        for b in bouts:
            fighters.add(b["fighter_a"])
            fighters.add(b["fighter_b"])

        for f in fighters:
            self._ensure(f)
            self._inflate(f, event_date)

        pre = {f: self.states[f].rating for f in fighters}
        series: dict[str, list[tuple[float, Rating, float]]] = {f: [] for f in fighters}

        for b in bouts:
            a, c = b["fighter_a"], b["fighter_b"]
            wa = float(b.get("weight_a", 1.0))
            wc = float(b.get("weight_b", 1.0))
            if b["is_draw"]:
                sa, sc = 0.5, 0.5
            elif b["winner"] == a:
                if self.score_mode in {"method", "quality_method"}:
                    ms = (
                        b.get("quality_score_winner")
                        if self.score_mode == "quality_method"
                        else b.get("method_score_winner")
                    )
                    if ms is None or pd.isna(ms):
                        ms = b.get("method_score_winner")
                    sa, sc = (1.0, 0.0) if ms is None or pd.isna(ms) else (float(ms), 1.0 - float(ms))
                else:
                    sa, sc = 1.0, 0.0
            elif b["winner"] == c:
                if self.score_mode in {"method", "quality_method"}:
                    ms = (
                        b.get("quality_score_winner")
                        if self.score_mode == "quality_method"
                        else b.get("method_score_winner")
                    )
                    if ms is None or pd.isna(ms):
                        ms = b.get("method_score_winner")
                    sa, sc = (0.0, 1.0) if ms is None or pd.isna(ms) else (1.0 - float(ms), float(ms))
                else:
                    sa, sc = 0.0, 1.0
            else:
                continue
            series[a].append((sa, pre[c], wa))
            series[c].append((sc, pre[a], wc))

        for f in fighters:
            st = self.states[f]
            if series[f]:
                st.rating = _rate_weighted(self.env, pre[f], series[f])
            st.peak_mu = max(st.peak_mu, st.rating.mu)
            st.last_event_date = event_date
            self.history.append(WeightedHistoryRow(
                fighter=f,
                event_date=event_date,
                event_name=event_name,
                mu=st.rating.mu,
                phi=st.rating.phi,
                sigma=st.rating.sigma,
                opponents_this_event=len(series[f]),
                total_weight=float(sum(w for _, _, w in series[f])),
            ))

    def history_df(self) -> pd.DataFrame:
        rows = [r.__dict__ for r in self.history]
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        return df.sort_values(["fighter", "event_date"]).reset_index(drop=True)

    def current_table(self) -> pd.DataFrame:
        rows = []
        for f, st in self.states.items():
            rows.append({
                "fighter": f,
                "mu": st.rating.mu,
                "phi": st.rating.phi,
                "sigma": st.rating.sigma,
                "peak_mu": st.peak_mu,
                "last_event_date": st.last_event_date,
            })
        df = pd.DataFrame(rows).sort_values("mu", ascending=False).reset_index(drop=True)
        return df


# Standalone predictor — usable without instantiating a full engine, e.g. from
# notebook cells that loaded ratings_current.parquet.
def predict_win_prob_from_ratings(
    mu_a: float, phi_a: float,
    mu_b: float, phi_b: float,
    tau: float = DEFAULT_TAU,
) -> float:
    """Probability that fighter A beats B given their (μ, φ) pairs."""
    env = Glicko2(tau=tau)
    ra = env.create_rating(mu_a, phi_a)
    rb = env.create_rating(mu_b, phi_b)
    ra_s = env.scale_down(ra)
    rb_s = env.scale_down(rb)
    impact = env.reduce_impact(rb_s)
    return env.expect_score(ra_s, rb_s, impact)


def matchup_quality_from_ratings(
    mu_a: float, phi_a: float,
    mu_b: float, phi_b: float,
    tau: float = DEFAULT_TAU,
) -> float:
    env = Glicko2(tau=tau)
    ra = env.create_rating(mu_a, phi_a)
    rb = env.create_rating(mu_b, phi_b)
    return env.quality_1vs1(ra, rb)
