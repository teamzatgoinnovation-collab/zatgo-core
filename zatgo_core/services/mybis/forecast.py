"""Statistical forecasting for MyBis: small, explicit, dependency-free engines over a numeric history.

This is classical time-series arithmetic, NOT machine learning, and the app says so: every result carries its method, its
parameters, an approximate likely range, a backtest-based confidence and a list of limitations. The engines share one interface
(`ForecastEngine`) so a learned model can be added later without touching the API or the app.

Engines
- moving average (flat forecast of the last `window` points)
- weighted moving average (recent points weigh more: 1..window)
- simple exponential smoothing (alpha picked by minimising one-step error)
- Holt's linear trend (alpha, beta picked the same way)

Around any of them: an optional seasonal wrapper (multiplicative indices per weekday / month, only when the history has at least
two full cycles and the pattern is not negligible), the rolling one-step backtest used for the likely range and for `auto`
(pick the engine with the lowest weighted absolute percentage error), and the confidence label.

No database, no frappe: unit-tested alone.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence

Z80 = 1.2816  # normal quantile for a two-sided ~80% range
MIN_HISTORY = 7


class InsufficientHistory(ValueError):
    """Raised when there is too little history to forecast honestly."""


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# -- engines ----------------------------------------------------------------------------------------------------------


class ForecastEngine(ABC):
    """`one_step(y)` predicts each y[t] from y[:t] (None where there is not enough history); `forecast(y, h)` extrapolates;
    `variance_factor(h)` scales the one-step error variance to horizon h (so the range widens with the horizon)."""

    key: str
    label: str

    @property
    def params(self) -> dict[str, float]:
        return {}

    @abstractmethod
    def one_step(self, y: Sequence[float]) -> list[float | None]: ...

    @abstractmethod
    def forecast(self, y: Sequence[float], horizon: int) -> list[float]: ...

    def variance_factor(self, h: int) -> float:
        return 1.0

    def fit(self, y: Sequence[float]) -> "ForecastEngine":
        """Engines with tunable parameters return a tuned copy; the others return themselves."""
        return self


class MovingAverage(ForecastEngine):
    key = "moving_average"
    label = "Moving average"

    def __init__(self, window: int = 7):
        self.window = max(1, int(window))

    @property
    def params(self):
        return {"window": self.window}

    def one_step(self, y):
        w = self.window
        return [None if t < w else _mean(y[t - w : t]) for t in range(len(y))]

    def forecast(self, y, horizon):
        level = _mean(y[-self.window :])
        return [level] * horizon

    def variance_factor(self, h):
        return 1.0 + 1.0 / self.window  # the average itself is an estimate


class WeightedMovingAverage(MovingAverage):
    key = "weighted_moving_average"
    label = "Weighted moving average"

    def _wavg(self, xs: Sequence[float]) -> float:
        weights = range(1, len(xs) + 1)  # oldest 1 ... newest n
        return sum(w * x for w, x in zip(weights, xs)) / sum(weights)

    def one_step(self, y):
        w = self.window
        return [None if t < w else self._wavg(y[t - w : t]) for t in range(len(y))]

    def forecast(self, y, horizon):
        return [self._wavg(y[-self.window :])] * horizon


class ExponentialSmoothing(ForecastEngine):
    key = "exponential_smoothing"
    label = "Exponential smoothing"

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha

    @property
    def params(self):
        return {"alpha": round(self.alpha, 2)}

    def _run(self, y: Sequence[float]) -> tuple[list[float | None], float]:
        level = y[0]
        preds: list[float | None] = [None]
        for t in range(1, len(y)):
            preds.append(level)
            level = self.alpha * y[t] + (1 - self.alpha) * level
        return preds, level

    def one_step(self, y):
        return self._run(y)[0]

    def forecast(self, y, horizon):
        return [self._run(y)[1]] * horizon

    def variance_factor(self, h):
        return 1.0 + (h - 1) * self.alpha**2  # ETS(A,N,N)

    def fit(self, y):
        best, best_sse = self, math.inf
        for a in [i / 20 for i in range(1, 20)]:
            cand = ExponentialSmoothing(a)
            sse = sum((v - p) ** 2 for v, p in zip(y, cand.one_step(y)) if p is not None)
            if sse < best_sse:
                best, best_sse = cand, sse
        return best


class Holt(ForecastEngine):
    key = "holt"
    label = "Linear trend (Holt)"

    def __init__(self, alpha: float = 0.3, beta: float = 0.1):
        self.alpha, self.beta = alpha, beta

    @property
    def params(self):
        return {"alpha": round(self.alpha, 2), "beta": round(self.beta, 2)}

    def _run(self, y: Sequence[float]) -> tuple[list[float | None], float, float]:
        level, trend = y[0], 0.0  # no peeking: the trend is learned from the data that follows
        preds: list[float | None] = [None]
        for t in range(1, len(y)):
            preds.append(level + trend)
            prev = level
            level = self.alpha * y[t] + (1 - self.alpha) * (level + trend)
            trend = self.beta * (level - prev) + (1 - self.beta) * trend
        return preds, level, trend

    def one_step(self, y):
        return self._run(y)[0]

    def forecast(self, y, horizon):
        _p, level, trend = self._run(y)
        return [level + (i + 1) * trend for i in range(horizon)]

    def variance_factor(self, h):
        return 1.0 + sum((self.alpha * (1 + j * self.beta)) ** 2 for j in range(1, h))  # ETS(A,A,N)

    def fit(self, y):
        best, best_sse = self, math.inf
        for a in [i / 10 for i in range(1, 10)]:
            for b in (0.05, 0.1, 0.2, 0.3, 0.5):
                cand = Holt(a, b)
                sse = sum((v - p) ** 2 for v, p in zip(y, cand.one_step(y)) if p is not None)
                if sse < best_sse:
                    best, best_sse = cand, sse
        return best


ENGINES = {
    "moving_average": MovingAverage,
    "weighted_moving_average": WeightedMovingAverage,
    "exponential_smoothing": ExponentialSmoothing,
    "holt": Holt,
}
METHODS = ("auto", *ENGINES)


# -- seasonality ------------------------------------------------------------------------------------------------------


def seasonal_indices(y: Sequence[float], period: int, offset: int = 0) -> list[float] | None:
    """Multiplicative indices per position in the cycle (mean 1), or None when the history is too short (< 2 cycles), has no
    volume, or the pattern is negligible (max - min < 0.15). `offset` is the cycle position of y[0]."""
    if period < 2 or len(y) < 2 * period:
        return None
    overall = _mean(y)
    if overall <= 0:
        return None
    buckets: list[list[float]] = [[] for _ in range(period)]
    for i, v in enumerate(y):
        buckets[(offset + i) % period].append(v)
    raw = [_mean(b) / overall if b else 1.0 for b in buckets]
    norm = _mean(raw)
    idx = [r / norm for r in raw] if norm > 0 else None
    if idx is None or max(idx) - min(idx) < 0.15:
        return None
    return idx


# -- result -----------------------------------------------------------------------------------------------------------


@dataclass
class ForecastResult:
    method: str
    label: str
    params: dict[str, float]
    values: list[float]
    lower: list[float]
    upper: list[float]
    sigma: float  # typical one-step error (RMSE) on the backtest window
    wape: float | None  # weighted absolute % error of one-step predictions on the backtest window
    confidence: str  # high | medium | low
    n_history: int
    seasonal: dict | None = None
    candidates: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def _backtest(y: Sequence[float], preds: Sequence[float | None], window: int) -> tuple[float, float | None]:
    pairs = [(v, p) for v, p in zip(y, preds) if p is not None][-window:]
    if not pairs:
        return 0.0, None
    errs = [v - p for v, p in pairs]
    sigma = math.sqrt(sum(e * e for e in errs) / len(errs))
    total = sum(abs(v) for v, _p in pairs)
    return sigma, (sum(abs(e) for e in errs) / total if total > 0 else None)


def confidence_label(n: int, wape: float | None, min_history: int = 28, good_history: int = 60) -> str:
    if wape is None or n < MIN_HISTORY * 2:
        return "low"
    if n >= good_history and wape <= 0.35:
        return "high"
    if n >= min_history and wape <= 0.7:
        return "medium"
    return "low"


def run(
    y: Sequence[float],
    horizon: int,
    *,
    method: str = "auto",
    window: int = 7,
    period: int = 0,
    offset: int = 0,
    floor: float | None = 0.0,
    min_history: int = MIN_HISTORY,
    backtest_points: int = 30,
    cycle_name: str = "period",
) -> ForecastResult:
    """Forecast `horizon` steps from `y`. `period` > 1 enables the seasonal wrapper (cycle position of y[0] = `offset`);
    `floor` clamps results (0 for sales; None for cash movement)."""
    if method not in METHODS:
        raise ValueError(f"Unknown forecast method: {method!r}")
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    y = [float(v) for v in y]
    if len(y) < min_history:
        raise InsufficientHistory(f"Need at least {min_history} data points, have {len(y)}.")

    idx = seasonal_indices(y, period, offset) if period else None

    def pos(i: int) -> int:
        return (offset + i) % period if period else 0

    base = [v / idx[pos(i)] if idx and idx[pos(i)] > 0 else v for i, v in enumerate(y)]

    def evaluate(engine: ForecastEngine) -> tuple[ForecastEngine, list[float | None], float, float | None]:
        tuned = engine.fit(base)
        raw = tuned.one_step(base)
        preds = [None if p is None else (p * idx[pos(i)] if idx else p) for i, p in enumerate(raw)]
        sigma, wape = _backtest(y, preds, backtest_points)
        return tuned, preds, sigma, wape

    names = list(ENGINES) if method == "auto" else [method]
    scored = []
    for name in names:
        cls = ENGINES[name]
        engine = cls(window) if name in ("moving_average", "weighted_moving_average") else cls()
        tuned, preds, sigma, wape = evaluate(engine)
        scored.append((tuned, sigma, wape))
    candidates = [{"method": e.key, "label": e.label, "params": e.params, "wape": None if w is None else round(w, 3)} for e, _s, w in scored]
    # lowest error wins; a series with no volume has no wape -> first (simplest) engine
    best, sigma, wape = min(scored, key=lambda s: (math.inf if s[2] is None else s[2]))

    point = best.forecast(base, horizon)
    values, lower, upper = [], [], []
    for h in range(1, horizon + 1):
        season = idx[pos(len(y) + h - 1)] if idx else 1.0
        v = point[h - 1] * season
        half = Z80 * sigma * math.sqrt(best.variance_factor(h))
        lo, hi = v - half, v + half
        if floor is not None:
            v, lo, hi = max(floor, v), max(floor, lo), max(floor, hi)
        values.append(round(v, 2))
        lower.append(round(lo, 2))
        upper.append(round(hi, 2))

    limitations: list[str] = []
    if len(y) < 28:
        limitations.append(f"Only {len(y)} data points of history: treat this as a rough guide.")
    if all(v == 0 for v in y):
        limitations.append("There was no activity in the history window, so the forecast is zero.")
    elif sum(1 for v in y if v == 0) / len(y) > 0.4:
        limitations.append("Many periods in the history had no activity, which makes daily figures erratic.")
    if wape is not None and wape > 0.7:
        limitations.append("Period-to-period figures are very volatile; the likely range is wide.")
    if horizon > len(y) / 2:
        limitations.append("The forecast looks further ahead than half of the history; confidence falls with distance.")
    if period and not idx:
        limitations.append(f"No clear {cycle_name} pattern was found, so none was applied." if len(y) >= 2 * period else f"Less than two full {cycle_name}s of history, so no seasonal pattern was applied.")
    limitations.append("Statistical extrapolation of past figures: it cannot anticipate promotions, price changes, new customers or holidays.")

    return ForecastResult(
        method=best.key,
        label=best.label,
        params=best.params,
        values=values,
        lower=lower,
        upper=upper,
        sigma=round(sigma, 2),
        wape=None if wape is None else round(wape, 3),
        confidence=confidence_label(len(y), wape),
        n_history=len(y),
        seasonal={"period": period, "indices": [round(i, 3) for i in idx], "offset": offset} if idx else None,
        candidates=candidates,
        limitations=limitations,
    )
