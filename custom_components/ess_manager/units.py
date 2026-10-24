"""Price units and real time (as of 2026.10.25) - pure Python.

A quarter-hour price list runs in real (elapsed) time from local midnight:
96 units a normal day, 100 on the day summer time ends (the hour 02:00-03:00
comes twice) and 92 on the day it starts (02:00-03:00 doesn't exist). So the
current unit is the number of real quarters since local midnight, not
hour * 4 + minute // 15 - that clock count is an hour behind the price list
for the rest of the long day (and an hour ahead on the short one), and up to
2026.10.24 the plans ran an hour late on those days: a block planned in a
cheap quarter ran in the quarter an hour later, and the card showed it there.

Times from units the same way: real time added, then shown as local clock
time. Naive datetimes (tests) keep the plain clock arithmetic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

UNIT_SECONDS = 900


def local_midnight(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def shift(dt: datetime, delta: timedelta) -> datetime:
    """`dt` plus `delta` of real time, in dt's own time zone."""
    if dt.tzinfo is None:
        return dt + delta
    return (dt.astimezone(timezone.utc) + delta).astimezone(dt.tzinfo)


def seconds_since_midnight(now: datetime) -> float:
    if now.tzinfo is None:
        return now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
    return now.timestamp() - local_midnight(now).timestamp()


def price_unit(now: datetime) -> int:
    """The current 15-minute price unit (0 = today 00:00-00:15)."""
    return int(seconds_since_midnight(now) // UNIT_SECONDS)


def unit_start(now: datetime, cur_unit: int, unit: int) -> datetime:
    """When `unit` starts, counted from the current unit (cur_unit = the unit `now` is in)."""
    quarter = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    return shift(quarter, timedelta(minutes=(unit - cur_unit) * 15))


def unit_hour(unit: int, now: datetime | None = None) -> int:
    """The local clock hour `unit` (from today's midnight) starts in."""
    if now is None or now.tzinfo is None:
        return (unit // 4) % 24
    return shift(local_midnight(now), timedelta(minutes=15 * unit)).hour
