"""Reference price of the last week (as of 2026.11.50).

While tomorrow's prices are not known yet, the planner only sees the rest of
today. On a day that is dear as a whole, "the cheapest quarter left today" is
itself dear: the house was taken from the grid and soft charges were bought
at prices well above what a charge normally costs. The reference price is
what a charge usually cost in the past week:

- per day: the average buy price of its 6 cheapest hours (hour = mean of its
  quarters; a day needs at least 20 hours with a price);
- over the last 7 finished days: the median (at least 3 days), so a single
  day with very low or negative prices doesn't drag it along.

It is used only while no prices after today are known, before 18:00 local
time and when the battery doesn't drop below the low threshold within 12
hours (the safety net: then the plan is made as before, in the cheapest
quarters left today). Hard needs (below the threshold before the end of the
known prices) are never held back by it.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Any, Iterable, Optional

CHEAPEST_HOURS = 6
MIN_DAY_HOURS = 20
LOOKBACK_DAYS = 7
MIN_DAYS = 3
LAST_HOUR = 18          # local hour from which it's no longer used
EMPTY_WITHIN_HOURS = 12  # battery below the low threshold this soon: not used


def day_value(buy: Iterable[Optional[float]]) -> Optional[float]:
    """The average of a day's cheapest `CHEAPEST_HOURS` hours (each hour the
    mean of its known quarters), or None with fewer than `MIN_DAY_HOURS`
    hours known."""
    quarters = list(buy)
    hours: list[float] = []
    for i in range(0, len(quarters), 4):
        known = [float(p) for p in quarters[i:i + 4] if p is not None]
        if known:
            hours.append(sum(known) / len(known))
    if len(hours) < MIN_DAY_HOURS:
        return None
    cheapest = sorted(hours)[:CHEAPEST_HOURS]
    return sum(cheapest) / len(cheapest)


def reference(day_values: dict[str, Optional[float]], today: date) -> Optional[float]:
    """The median of the day values of the `LOOKBACK_DAYS` days before
    `today` (ISO date keys), None with fewer than `MIN_DAYS` of them."""
    wanted = {(today - timedelta(days=k)).isoformat() for k in range(1, LOOKBACK_DAYS + 1)}
    values = [v for d, v in day_values.items() if d in wanted and v is not None]
    if len(values) < MIN_DAYS:
        return None
    return float(statistics.median(values))


def active_reason(ref: Optional[float], tomorrow_known: bool, local_hour: int,
                  hours_to_empty: Optional[int]) -> str:
    """Whether the reference is used now: "active", or why not."""
    if ref is None:
        return "too_few_days"
    if tomorrow_known:
        return "tomorrow_known"
    if local_hour >= LAST_HOUR:
        return "after_18"
    if hours_to_empty is not None and hours_to_empty <= EMPTY_WITHIN_HOURS:
        return "empty_soon"
    return "active"


def fill_reason(raw_reason: str, hold_until: Optional[float], now_ts: float) -> str:
    """The reason with the fill hold (as of 2026.11.66): a charge planned
    while the battery was about to run low (reference not used) is finished
    to its plan - the first block lifting the forecast above the threshold
    no longer brings the reference back halfway through - see
    `next_fill_hold`."""
    if raw_reason == "active" and hold_until is not None and now_ts < hold_until:
        return "fill_plan"
    return raw_reason


def next_fill_hold(raw_reason: str, hold_until: Optional[float], now_ts: float,
                   blocks: list[tuple[float, float]]) -> Optional[float]:
    """The end of the fill hold after this cycle's charge plan (epoch, None =
    no hold). `blocks` are the plan's charge blocks as (start, end) epochs.
    Starts when the reference isn't used because the battery runs low soon
    and the plan has blocks starting within `EMPTY_WITHIN_HOURS`; it lasts
    until the end of the last of those blocks - the charge as it was planned
    then, not a later one (a morning charge at dearer prices stays held
    back). Ends earlier when no block of the plan starts before that any
    more, or when tomorrow's prices are in."""
    if raw_reason in ("tomorrow_known", "too_few_days"):
        return None
    if hold_until is not None and now_ts >= hold_until:
        hold_until = None
    if raw_reason == "empty_soon":
        window = now_ts + EMPTY_WITHIN_HOURS * 3600
        ends = [e for s, e in blocks if s < window and e > now_ts]
        if hold_until is None and ends:
            return max(ends)
        return hold_until
    if hold_until is not None and not any(s < hold_until and e > now_ts for s, e in blocks):
        return None
    return hold_until


def hours_below(forecast: list[float], threshold_kwh: float) -> Optional[int]:
    """The first forecast hour (0 = this hour) below the threshold."""
    return next((h for h, v in enumerate(forecast) if v is not None and v < threshold_kwh), None)


def attribute(ref: Optional[float], reason: str, days: dict[str, Optional[float]], today: date,
              fill_until: Optional[str] = None) -> dict[str, Any]:
    wanted = [(today - timedelta(days=k)).isoformat() for k in range(LOOKBACK_DAYS, 0, -1)]
    return {
        "price": None if ref is None else round(ref, 4),
        "active": reason == "active",
        "reason": reason,
        "fill_until": fill_until,
        "days": {d: (None if days.get(d) is None else round(days[d], 4)) for d in wanted if d in days},
    }
