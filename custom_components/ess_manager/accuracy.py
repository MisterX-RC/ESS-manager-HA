"""Forecast check (as of 2026.10.22) - pure Python, no Home Assistant.

How good were the forecasts, and how big does the Safety buffer have to be?

Household usage (the house without heat pump and car, which have their own
forecasts) can be recalculated for any past day from the statistics, so its
check is complete from the first day: three ways of forecasting it are
tested on the last weeks (backtest) and the best one is used - only when it
is clearly better than the plain average:

- METHOD_AVERAGE: the same hour on the same weekday, 1..L weeks back
  (L = the "Usage lookback" setting, usually 6) - what the integration has
  always done.
- METHOD_WEIGHTED: the same, recent weeks weighing more (L, L-1, .., 1).
- METHOD_LEVEL: the pattern of the L weeks, the level of the last week:
  the average times (last 7 days) / (the L weeks' weekly average, which
  includes those 7 days). Worked out fresh every day and not accumulated,
  so it fades to 1 by itself as the average catches up with a changed
  usage - it doesn't overshoot, the way a correction learned from last
  week's error would (the higher week would count twice). Limited to
  LEVEL_MIN..LEVEL_MAX so one odd week can't throw it.

Solar can't be recalculated (the forecast sensors keep no history), so the
forecast for each day is stored at the day's first cycle (snapshot) and
compared once the day's production is measured.

The Safety buffer covers what the forecasts get wrong: per day, the worst
shortfall since midnight - the measured usage above the forecast plus the
measured solar below it, added up hour by hour - in % of the capacity. The
advice is the smallest buffer that would have covered BUFFER_COVERAGE of
the last BUFFER_WINDOW_DAYS days. The car is left out (an unplanned charge
session isn't a forecast error the buffer should grow for); the heat pump
counts (its weather errors are real).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Optional

from .usage_forecast import _hour_delta, _week_sample

HOUR_SECONDS = 3600
WEEK_SECONDS = 7 * 24 * HOUR_SECONDS

METHOD_AVERAGE = "average"
METHOD_WEIGHTED = "weighted"
METHOD_LEVEL = "level"
METHODS = (METHOD_AVERAGE, METHOD_WEIGHTED, METHOD_LEVEL)

LEVEL_MIN = 0.8
LEVEL_MAX = 1.25
# the level needs this share of the hours in both windows
LEVEL_COVERAGE = 0.9

TEST_DAYS = 56          # backtest: the last 8 weeks
MIN_TEST_DAYS = 14      # fewer complete days: the average stays
BETTER_BY = 0.05        # another method must beat the average by 5 % (daily error)
SHOW_DAYS = 14          # the card's "per day" and averages

BUFFER_WINDOW_DAYS = 28
BUFFER_MIN_DAYS = 14
BUFFER_COVERAGE = 0.95
BUFFER_MIN = 2.0        # % of capacity - the advice / automatic buffer never goes outside
BUFFER_MAX = 30.0
BUFFER_STEP = 2.0       # automatic: at most this many %-points a day


# -- measured hours ------------------------------------------------------------
def usage_hour(
    hourly_sums: dict[str, dict[int, float]],
    terms: tuple,
    epoch: int,
    subtract: Iterable[str] = (),
) -> Optional[float]:
    """One hour's household usage via the same identity as the usage
    forecast (terms = import, export, solar, battery charge, battery
    discharge), minus `subtract` (a missing value there counts as 0); None
    when a term has no data."""
    value = _week_sample(hourly_sums, *terms, epoch)
    if value is None:
        return None
    for entity_id in subtract:
        value -= max(_hour_delta(hourly_sums, entity_id, epoch) or 0.0, 0.0)
    return max(value, 0.0)


def sum_hour(hourly_sums: dict[str, dict[int, float]], ids: list[str], epoch: int) -> Optional[float]:
    """The sum of `ids` over one hour (solar production), None when one is missing."""
    if not ids:
        return None
    total = 0.0
    for entity_id in ids:
        delta = _hour_delta(hourly_sums, entity_id, epoch)
        if delta is None:
            return None
        total += max(delta, 0.0)
    return total


# -- usage forecasting methods ---------------------------------------------------
def week_weights(method: str, lookback_weeks: int) -> Optional[list[float]]:
    """The weight of week 1..L for the usage forecast, None = all equal."""
    if method == METHOD_WEIGHTED:
        return [float(lookback_weeks + 1 - k) for k in range(1, lookback_weeks + 1)]
    return None


def forecast_hour(
    series: dict[int, Optional[float]], epoch: int, lookback_weeks: int, weights: Optional[list[float]] = None
) -> Optional[float]:
    """The same hour on the same weekday 1..L weeks back, (weighted) mean."""
    total = 0.0
    weight = 0.0
    for k in range(1, lookback_weeks + 1):
        value = series.get(epoch - k * WEEK_SECONDS)
        if value is None:
            continue
        w = weights[k - 1] if weights else 1.0
        total += value * w
        weight += w
    return total / weight if weight else None


def level_factor(series: dict[int, Optional[float]], start_epoch: int, lookback_weeks: int) -> Optional[float]:
    """The last 7 days before `start_epoch` against the weekly average of the
    last L weeks (which includes those 7 days), limited to
    LEVEL_MIN..LEVEL_MAX; None without enough data."""
    week_hours = 7 * 24

    def window(hours: int) -> Optional[float]:
        values = [series.get(start_epoch - h * HOUR_SECONDS) for h in range(1, hours + 1)]
        known = [v for v in values if v is not None]
        if len(known) < LEVEL_COVERAGE * hours:
            return None
        return sum(known) * hours / len(known)

    last = window(week_hours)
    longer = window(week_hours * lookback_weeks)
    if last is None or longer is None or longer <= 0:
        return None
    return min(max(last / (longer / lookback_weeks), LEVEL_MIN), LEVEL_MAX)


def method_forecast(
    series: dict[int, Optional[float]], hours: list[int], lookback_weeks: int, method: str
) -> Optional[list[float]]:
    """A day's hourly forecast by `method`, made at the day's start
    (hours[0]); None when an hour has no history."""
    weights = week_weights(method, lookback_weeks)
    factor = 1.0
    if method == METHOD_LEVEL:
        factor = level_factor(series, hours[0], lookback_weeks)
        if factor is None:
            return None
    out = []
    for epoch in hours:
        value = forecast_hour(series, epoch, lookback_weeks, weights)
        if value is None:
            return None
        out.append(value * factor)
    return out


def _stats(pairs: list[tuple[float, float]]) -> dict[str, Optional[float]]:
    """Mean absolute error per day (kWh) and bias (% of the measured total)."""
    if not pairs:
        return {"mae": None, "bias_pct": None, "days": 0}
    mae = sum(abs(p - a) for p, a in pairs) / len(pairs)
    actual = sum(a for _, a in pairs)
    bias = (sum(p for p, _ in pairs) - actual) / actual * 100 if actual > 0 else None
    return {"mae": round(mae, 2), "bias_pct": round(bias, 1) if bias is not None else None, "days": len(pairs)}


def backtest(
    series: dict[int, Optional[float]], days: list[tuple[str, list[int]]], lookback_weeks: int
) -> dict[str, Any]:
    """Every method on every complete day of `days` ([(iso date, hour
    epochs)], oldest first): the daily error per method, which one to use,
    and the last SHOW_DAYS days for the card.

    A day counts as soon as it is measured completely and the plain average
    can be made for it; a method that cannot be made that day (the level
    method needs LEVEL_COVERAGE of the L weeks before it) only skips that
    day for itself. Another method is chosen only with at least
    MIN_TEST_DAYS days of its own, compared with the average on the days
    both have."""
    pairs: dict[str, list[tuple[float, float]]] = {m: [] for m in METHODS}
    rows: list[dict[str, Any]] = []
    for iso, hours in days:
        actual_hours = [series.get(e) for e in hours]
        if any(v is None for v in actual_hours):
            continue
        forecasts = {m: method_forecast(series, hours, lookback_weeks, m) for m in METHODS}
        if forecasts[METHOD_AVERAGE] is None:
            continue
        actual = sum(actual_hours)
        row: dict[str, Any] = {"d": iso, "actual": round(actual, 2)}
        for m, f in forecasts.items():
            if f is None:
                continue
            total = sum(f)
            pairs[m].append((total, actual))
            row[m] = round(total, 2)
        rows.append(row)
    stats = {m: _stats(pairs[m]) for m in METHODS}
    chosen = METHOD_AVERAGE
    n = len(pairs[METHOD_AVERAGE])
    if n >= MIN_TEST_DAYS and stats[METHOD_AVERAGE]["mae"]:
        best_gain = BETTER_BY
        for m in METHODS:
            if m == METHOD_AVERAGE or stats[m]["days"] < MIN_TEST_DAYS:
                continue
            common = [r for r in rows if m in r]
            base = sum(abs(r[METHOD_AVERAGE] - r["actual"]) for r in common)
            own = sum(abs(r[m] - r["actual"]) for r in common)
            if base <= 0:
                continue
            gain = 1 - own / base
            if gain >= best_gain:
                best_gain = gain
                chosen = m
    return {"methods": stats, "chosen": chosen, "test_days": n, "per_day": rows[-SHOW_DAYS:]}


# -- the Safety buffer -------------------------------------------------------------
def day_shortfall(
    usage_fc: list[Optional[float]],
    usage_meas: list[Optional[float]],
    solar_fc: Optional[list[Optional[float]]],
    solar_meas: Optional[list[Optional[float]]],
) -> Optional[float]:
    """The worst cumulative shortfall (kWh, >= 0) of a day: usage above and
    solar below the forecast, added up hour by hour. Only the hours the
    snapshot covers count; None when one of those has no measurement."""
    worst = 0.0
    running = 0.0
    counted = 0
    for i, fc in enumerate(usage_fc):
        if fc is None:
            continue
        meas = usage_meas[i] if i < len(usage_meas) else None
        if meas is None:
            return None
        running += meas - fc
        if solar_fc is not None and solar_meas is not None:
            sfc = solar_fc[i] if i < len(solar_fc) else None
            smeas = solar_meas[i] if i < len(solar_meas) else None
            if sfc is not None:
                if smeas is None:
                    return None
                running -= smeas - sfc
        counted += 1
        worst = max(worst, running)
    return worst if counted else None


def buffer_advice(needed_pct: list[float], manual_pct: float) -> dict[str, Any]:
    """The smallest buffer (whole %) that covered BUFFER_COVERAGE of the days,
    within BUFFER_MIN..BUFFER_MAX, and how often the manual one did."""
    n = len(needed_pct)
    if n < BUFFER_MIN_DAYS:
        return {"advice": None, "days": n, "coverage_manual": None, "coverage_advice": None}
    ordered = sorted(needed_pct)
    k = max(math.ceil(BUFFER_COVERAGE * n), 1)
    advice = min(max(math.ceil(ordered[k - 1] - 1e-9), BUFFER_MIN), BUFFER_MAX)
    covered = lambda b: round(sum(1 for v in ordered if v <= b + 1e-9) / n * 100)  # noqa: E731
    return {"advice": advice, "days": n, "coverage_manual": covered(manual_pct), "coverage_advice": covered(advice)}


def step_towards(current: float, target: float) -> float:
    """The automatic buffer moves at most BUFFER_STEP %-points a day."""
    return round(current + min(max(target - current, -BUFFER_STEP), BUFFER_STEP), 1)


def solar_check(days: list[dict[str, Any]]) -> dict[str, Any]:
    """Solar forecast against measured, per day ({d, forecast, actual})."""
    pairs = [(d["forecast"], d["actual"]) for d in days if d.get("forecast") is not None and d.get("actual") is not None]
    stats = _stats(pairs)
    stats["forecast_avg"] = round(sum(p for p, _ in pairs) / len(pairs), 2) if pairs else None
    stats["actual_avg"] = round(sum(a for _, a in pairs) / len(pairs), 2) if pairs else None
    return stats
