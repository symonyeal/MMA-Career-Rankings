"""Glicko-2 rating engine wrapper.

Two parallel ratings are maintained for every fighter:
- `μ_canonical`: scores strictly {0, 0.5, 1}. Use this for calibration plots
   and win-probability predictions — it's mathematically clean.
- `μ_method`: continuous winner-score in [0.7, 1.0] depending on Greco's
  method bucket. Retained as a same-pass research diagnostic; it is not a
  public leaderboard or calibration stream.

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
from dataclasses import dataclass

import pandas as pd

from ._glicko2 import DRAW, LOSS, WIN, Glicko2, Rating
from .constants import DAYS_PER_MONTH


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
    pre_mu_canonical: float
    pre_phi_canonical: float
    pre_mu_method: float
    pre_phi_method: float


def _result_scores(bout: dict, *, method: bool, quality: bool) -> tuple[float, float] | None:
    a, b, winner = bout["fighter_a"], bout["fighter_b"], bout["winner"]
    if bout["is_draw"]:
        return DRAW, DRAW
    if winner == a:
        scores = (WIN, LOSS)
        winner_side = 0
    elif winner == b:
        scores = (LOSS, WIN)
        winner_side = 1
    else:
        return None
    if not method:
        return scores
    value = bout.get("quality_score_winner") if quality else bout.get("method_score_winner")
    if value is None or pd.isna(value):
        value = bout.get("method_score_winner")
    if value is None or pd.isna(value):
        return scores
    winner_score = float(value)
    return (winner_score, 1.0 - winner_score) if winner_side == 0 else (1.0 - winner_score, winner_score)


def _process_event(
    engine,
    event_date: pd.Timestamp,
    event_name: str,
    bouts: list[dict],
    *,
    fields: tuple[str, ...],
    score_mode: str,
    weighted: bool,
    state_factory,
    history_factory,
) -> None:
    fighters = {fighter for bout in bouts for fighter in (bout["fighter_a"], bout["fighter_b"])}
    for fighter in fighters:
        if fighter not in engine.states:
            engine.states[fighter] = state_factory(engine.env)
        state = engine.states[fighter]
        if state.last_event_date is not None:
            months = 0 if event_date is None else int((event_date - state.last_event_date).days / DAYS_PER_MONTH)
            for field in fields:
                setattr(state, field, engine.env.inflate(getattr(state, field), months))

    pre = {fighter: {field: getattr(engine.states[fighter], field) for field in fields} for fighter in fighters}
    series = {fighter: {field: [] for field in fields} for fighter in fighters}
    is_method = score_mode in {"method", "quality_method"} or "method" in fields
    quality = score_mode == "quality_method"

    for bout in bouts:
        a, b = bout["fighter_a"], bout["fighter_b"]
        wa = float(bout.get("weight_a", 1.0)) if weighted else 1.0
        wb = float(bout.get("weight_b", 1.0)) if weighted else 1.0
        scores = _result_scores(bout, method=is_method, quality=quality)
        if scores is None:
            continue
        # Canonical and method ratings consume separate score pairs; a weighted
        # engine has one score stream selected by score_mode.
        if "canonical" in fields and "method" in fields:
            canonical = _result_scores(bout, method=False, quality=False)
            for field, pair, wa_i, wb_i in (
                ("canonical", canonical, wa, wb), ("method", scores, wa, wb),
            ):
                for fighter, opponent, score, weight in ((a, b, pair[0], wa_i), (b, a, pair[1], wb_i)):
                    item = (score, pre[opponent][field], weight) if weighted else (score, pre[opponent][field])
                    series[fighter][field].append(item)
        else:
            for fighter, opponent, score, weight in ((a, b, scores[0], wa), (b, a, scores[1], wb)):
                field = fields[0]
                item = (score, pre[opponent][field], weight) if weighted else (score, pre[opponent][field])
                series[fighter][field].append(item)

    for fighter in fighters:
        state = engine.states[fighter]
        for field in fields:
            if series[fighter][field]:
                if weighted:
                    updated = engine.env.rate_weighted(pre[fighter][field], series[fighter][field])
                else:
                    updated = engine.env.rate(pre[fighter][field], series[fighter][field])
                setattr(state, field, updated)
        if fields == ("canonical", "method"):
            state.peak_mu_canonical = max(state.peak_mu_canonical, state.canonical.mu)
            state.peak_mu_method = max(state.peak_mu_method, state.method.mu)
            row = history_factory(
                fighter, event_date, event_name, state, len(series[fighter]["canonical"]), pre[fighter],
            )
        else:
            state.peak_mu = max(state.peak_mu, state.rating.mu)
            total_weight = float(sum(w for _, _, w in series[fighter]["rating"]))
            row = history_factory(
                fighter, event_date, event_name, state, len(series[fighter]["rating"]),
                total_weight, pre[fighter],
            )
        state.last_event_date = event_date
        engine.history.append(row)


def _history_frame(history: list) -> pd.DataFrame:
    frame = pd.DataFrame([row.__dict__ for row in history])
    if frame.empty:
        return frame
    return frame.sort_values(["fighter", "event_date"]).reset_index(drop=True)


def _current_frame(engine, columns: dict[str, tuple[str, str]], sort_column: str) -> pd.DataFrame:
    rows = []
    for fighter, state in engine.states.items():
        row = {"fighter": fighter}
        for column, (field, attribute) in columns.items():
            value = getattr(state, field)
            row[column] = getattr(value, attribute) if attribute else value
        row["last_event_date"] = state.last_event_date
        rows.append(row)
    return pd.DataFrame(rows).sort_values(sort_column, ascending=False).reset_index(drop=True)


class RatingEngine:
    """Per-event Glicko-2 engine with lazy φ-inflation between appearances."""

    def __init__(self, tau: float = DEFAULT_TAU, backend: str = "auto"):
        self.env = Glicko2(tau=tau, backend=backend)
        self.tau = tau
        self.states: dict[str, FighterState] = {}
        self.history: list[HistoryRow] = []


    def process_event(self, event_date: pd.Timestamp, event_name: str, bouts: list[dict]) -> None:
        """Process all bouts on a single event atomically.

        Each dict must have: fighter_a, fighter_b, winner, is_draw,
        method_score_winner (None if draw or unknown).
        """
        _process_event(
            self, event_date, event_name, bouts,
            fields=("canonical", "method"), score_mode="method", weighted=False,
            state_factory=lambda env: FighterState(env.create_rating(), env.create_rating()),
            history_factory=lambda fighter, date, name, state, n, pre: HistoryRow(
                fighter, date, name,
                state.canonical.mu, state.canonical.phi, state.canonical.sigma,
                state.method.mu, state.method.phi, state.method.sigma,
                n, pre["canonical"].mu, pre["canonical"].phi,
                pre["method"].mu, pre["method"].phi,
            ),
        )

    # ------------------------------------------------------------------
    # Output helpers

    def history_df(self) -> pd.DataFrame:
        return _history_frame(self.history)

    def current_table(self) -> pd.DataFrame:
        return _current_frame(self, {
            "mu_canonical": ("canonical", "mu"), "phi_canonical": ("canonical", "phi"),
            "sigma_canonical": ("canonical", "sigma"), "mu_method": ("method", "mu"),
            "phi_method": ("method", "phi"), "sigma_method": ("method", "sigma"),
            "peak_mu_canonical": ("peak_mu_canonical", ""), "peak_mu_method": ("peak_mu_method", ""),
        }, "mu_canonical")


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
    pre_mu: float
    pre_phi: float


class WeightedRatingEngine:
    """Per-event Glicko-2 engine that applies a per-result update weight.

    Drop-in alternative for the odds-adjusted rating stream. Tracks a
    single canonical-scored rating (no method-bonus side stream — odds
    adjustment is orthogonal to method scoring by design). With every
    weight set to 1.0 the per-event mu/phi/sigma evolve identically to
    `RatingEngine`'s canonical stream (regression-tested).
    """

    def __init__(self, tau: float = DEFAULT_TAU, score_mode: str = "canonical", backend: str = "auto"):
        if score_mode not in {"canonical", "method", "quality_method"}:
            raise ValueError(f"unknown weighted score mode: {score_mode!r}")
        self.env = Glicko2(tau=tau, backend=backend)
        self.tau = tau
        self.score_mode = score_mode
        self.states: dict[str, WeightedFighterState] = {}
        self.history: list[WeightedHistoryRow] = []


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
        if self.score_mode not in {"canonical", "method", "quality_method"}:
            raise ValueError(f"unknown weighted score mode: {self.score_mode!r}")
        _process_event(
            self, event_date, event_name, bouts, fields=("rating",), score_mode=self.score_mode, weighted=True,
            state_factory=lambda env: WeightedFighterState(env.create_rating()),
            history_factory=lambda fighter, date, name, state, n, total_weight, pre: WeightedHistoryRow(
                fighter, date, name, state.rating.mu, state.rating.phi, state.rating.sigma,
                n, total_weight, pre["rating"].mu, pre["rating"].phi,
            ),
        )

    def history_df(self) -> pd.DataFrame:
        return _history_frame(self.history)

    def current_table(self) -> pd.DataFrame:
        return _current_frame(self, {
            "mu": ("rating", "mu"), "phi": ("rating", "phi"), "sigma": ("rating", "sigma"),
            "peak_mu": ("peak_mu", ""),
        }, "mu")


# Standalone predictor — usable without instantiating a full engine, e.g. from
# notebook cells that loaded ratings_current.parquet.
def predict_win_prob_from_ratings(
    mu_a: float, phi_a: float,
    mu_b: float, phi_b: float,
    tau: float = DEFAULT_TAU,
) -> float:
    """Reciprocal probability that fighter A beats B from two rating states.

    Match prediction is a comparison of *both* uncertain ratings.  Glickman's
    predictive equation therefore applies ``g`` to the root-sum-square of the
    two scaled deviations, rather than to whichever fighter happened to be
    passed as the opponent.  Besides using all available uncertainty, this
    guarantees ``P(A > B) + P(B > A) == 1`` (within floating-point error).
    """
    env = Glicko2(tau=tau)
    ra = env.create_rating(mu_a, phi_a)
    rb = env.create_rating(mu_b, phi_b)
    ra_s = env.scale_down(ra)
    rb_s = env.scale_down(rb)
    combined_phi = math.hypot(ra_s.phi, rb_s.phi)
    impact = 1.0 / math.sqrt(1.0 + 3.0 * combined_phi**2 / math.pi**2)
    logit = impact * (ra_s.mu - rb_s.mu)
    if logit >= 0.0:
        return 1.0 / (1.0 + math.exp(-logit))
    exp_logit = math.exp(logit)
    return exp_logit / (1.0 + exp_logit)
