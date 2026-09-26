"""Time-dependent grid transport tariff (as of v0.4.0) - the pure part (no
Home Assistant imports, unit-tested in tests/test_pipeline.py).

Buying from the grid will cost the price-sensor price PLUS a transport
tariff that depends on the month and the hour: the base tariff (a
sensor/number/input_number chosen in setup, EUR/kWh, same unit and VAT basis
as the price sensor) times a factor from transport_factors.json. Selling is
never charged transport, so the integration keeps two price lists:

- sell price = the price sensor's own price (`all_price`, unchanged)
- buy price  = price + (tariff x factor for that 15-minute unit)
  (`all_buy_price`)

Every buy decision (low charge, full-charge balancing, negative price
charging, the spike plan's charge side) uses the buy price; every sell
decision uses the sell price.

The factors come with the integration (a HACS update brings new ones). A
different table means a fork of the repository.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Optional

FACTORS_FILE = os.path.join(os.path.dirname(__file__), "transport_factors.json")
UNIT_MINUTES = 15


def parse_factors(data: Any) -> dict[int, list[float]]:
    """{month 1-12: [24 hourly factors]} from the JSON document; raises
    ValueError when it isn't a complete 12 x 24 table of numbers."""
    table = data.get("factors") if isinstance(data, dict) else None
    if not isinstance(table, dict):
        raise ValueError("no 'factors' table")
    out: dict[int, list[float]] = {}
    for month in range(1, 13):
        row = table.get(str(month))
        if not isinstance(row, list) or len(row) != 24:
            raise ValueError(f"month {month} needs 24 hourly factors")
        out[month] = [float(v) for v in row]
    return out


def load_factors(path: str = FACTORS_FILE) -> dict[int, list[float]]:
    """Read and check transport_factors.json (blocking - run it in an
    executor from Home Assistant)."""
    with open(path, encoding="utf-8") as handle:
        return parse_factors(json.load(handle))


def unit_local_times(day_start: datetime, count: int, tz: tzinfo) -> list[datetime]:
    """Local start time of each 15-minute price unit, counted in real
    (elapsed) time from local midnight today - the way a quarter-hour price
    list runs, also on the 23- and 25-hour days of a summer-time change."""
    start_utc = day_start.astimezone(timezone.utc)
    return [(start_utc + timedelta(minutes=UNIT_MINUTES * i)).astimezone(tz) for i in range(count)]


def unit_factors(times: list[datetime], factors: dict[int, list[float]]) -> list[float]:
    """The factor for each unit: its local month and clock hour."""
    return [factors[t.month][t.hour] for t in times]


def compute_buy_prices(
    all_price: list[float], tariff: Optional[float], factors_per_unit: list[float]
) -> list[float]:
    """buy price = price + (tariff x factor) per unit. No tariff (None or
    0) -> the prices themselves."""
    if not tariff:
        return list(all_price)
    return [
        round(price + (tariff * (factors_per_unit[i] if i < len(factors_per_unit) else 1.0)), 5)
        for i, price in enumerate(all_price)
    ]
