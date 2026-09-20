"""Pure-Python port of the solar / usage / net-energy / battery forecast
pipeline that used to live in sensor.ess_manager's Jinja2 attributes.

Every function here is a plain function of its inputs - no Home Assistant
state access - so it can be unit tested without a running HA instance, the
same way the original was validated with a standalone Jinja render harness.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from .const import FORECAST_HOURS


def merge_hourly_points(entities_raw: list[list[dict]]) -> list[dict]:
    """Flatten several solar-forecast entities' hourly point lists into one.

    Each source entity is expected to expose a list of dicts shaped like
    Solcast's `detailedHourly` attribute: [{"period_start": <iso str or
    datetime>, "pv_estimate": <float>}, ...]. Multiple entities (e.g.
    today/tomorrow/day_3/... forecast sensors) are chained exactly like the
    original sensor chained up to six Solcast day sensors, so the combined
    coverage always reaches the full forecast horizon regardless of what
    time of day the update runs.
    """
    merged: list[dict] = []
    for points in entities_raw:
        if points:
            merged.extend(points)
    return merged


def _as_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def build_solar_forecast(
    points: list[dict], now: datetime, hours: int = FORECAST_HOURS
) -> list[Optional[float]]:
    """Hourly solar forecast, index 0 = current hour, aligned to `now`.

    Direct port of the `solar 120 hrs` Jinja attribute: for every target
    hour, look for a source point whose period_start matches exactly and
    take its pv_estimate; None when no source point covers that hour (the
    original's own None/0 handling downstream is unchanged - see
    build_net_energy).
    """
    # Build a lookup keyed by the top-of-hour timestamp for speed - the
    # original did an O(hours * points) nested scan each cycle, which is
    # fine for ~121 x a few hundred points but a dict lookup is both faster
    # and clearer here.
    lookup: dict[datetime, float] = {}
    for point in points:
        ts = _as_datetime(point.get("period_start"))
        if ts is None:
            continue
        ts = ts.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        estimate = point.get("pv_estimate")
        if estimate is not None:
            lookup[ts] = float(estimate)

    base = now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    values: list[Optional[float]] = []
    for h in range(hours):
        target = base + timedelta(hours=h)
        values.append(lookup.get(target))
    return values


def build_usage_forecast(
    hourly_values: dict, hours: int = FORECAST_HOURS
) -> list[float]:
    """Hourly usage forecast, index 0 = current hour.

    `hourly_values` is expected to be a mapping like {"h0": 1.23, "h1":
    0.98, ...} - the attribute shape exposed by the SQL-based
    sensor.predicted_energy_forecast this was originally built against.
    Missing/None entries fall back to 0, matching the original's
    `value | float(0) if value is not none else 0`.
    """
    values: list[float] = []
    for h in range(hours):
        value = hourly_values.get(f"h{h}")
        values.append(float(value) if value is not None else 0.0)
    return values


def build_net_energy(
    solar: list[Optional[float]], usage: list[float]
) -> list[float]:
    """solar minus usage, per hour - matches solar's own length exactly."""
    values: list[float] = []
    for h in range(len(solar)):
        solar_val = solar[h] if h < len(solar) and solar[h] is not None else 0.0
        usage_val = usage[h] if h < len(usage) else 0.0
        values.append(round(solar_val - usage_val, 3))
    return values


def build_battery_forecast(
    net: list[float],
    start_kwh: float,
    now: datetime,
    max_charge_kw: Optional[float] = None,
    max_discharge_kw: Optional[float] = None,
) -> list[float]:
    """Cumulative running battery level (kWh), compensated for the partial
    current hour.

    net[0] represents the FULL current calendar hour, but `start_kwh` is a
    live reading taken mid-hour. Scaling net[0] by the fraction of the hour
    still remaining avoids double-counting whatever already happened
    between the top of the hour and now (ported verbatim from the
    2026-09-14 fix to the original template sensor's `battery forecast`
    attribute - see the project handoff doc's Resolved Decisions for the
    full reasoning, including why a "lock SOC at the top of the hour"
    alternative was considered and rejected in favor of this).

    `max_charge_kw`/`max_discharge_kw` optionally cap what the battery
    itself can absorb or supply each hour. Each entry in `net` already
    represents a full-hour-equivalent kWh figure (see build_net_energy), so
    it doubles directly as an average kW over that hour - a positive net
    (solar exceeding usage) above `max_charge_kw` is clamped down to it,
    and a negative net (usage exceeding solar) more negative than
    `-max_discharge_kw` is clamped up to it. Whatever's left over is
    assumed to flow to/from the grid instead (curtailed export on the
    charge side, grid import on the discharge side) rather than the
    battery - this function only tracks what the battery itself sees; the
    unclamped `net` array (exposed separately as `net_energy_120h`) still
    shows the raw solar-minus-usage figure. The cap is applied to the
    full-hour rate *before* the partial-current-hour scaling above, since
    that scaling only accounts for elapsed time, not the physical power
    limit. Left at None (the default) for either side, there's no cap on
    that side, matching behavior before these parameters existed.
    """
    fraction_remaining = (60 - now.minute) / 60
    values: list[float] = []
    soc = start_kwh
    for h, delta in enumerate(net):
        capped_delta = delta
        if max_charge_kw is not None:
            capped_delta = min(capped_delta, max_charge_kw)
        if max_discharge_kw is not None:
            capped_delta = max(capped_delta, -max_discharge_kw)
        step = capped_delta * fraction_remaining if h == 0 else capped_delta
        soc = soc + step
        values.append(round(soc, 2))
    return values
