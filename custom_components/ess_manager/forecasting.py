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


def solar_points_from_attributes(attributes) -> list[dict]:
    """One solar-forecast entity's points, Solcast-shaped (as of 2026.10.21).

    Two formats are recognised by themselves, no setting needed:
    - Solcast: `detailedHourly` = [{"period_start", "pv_estimate" (kWh in
      that hour)}, ...] - used as is.
    - Helios Forecast: `forecast` = [{"datetime", "watts", "p10", "p90"},
      ...], one point per quarter hour, in W. Turned into hourly points:
      the mean of the hour's quarters in W / 1000 = kWh in that hour (an
      hour with only some quarters - the end of the horizon - counts its
      average, not a partial sum).
    Anything else gives no points.
    """
    attrs = attributes or {}
    hourly = attrs.get("detailedHourly")
    if hourly:
        return list(hourly)
    quarters = attrs.get("forecast")
    if not isinstance(quarters, (list, tuple)):
        return []
    sums: dict[datetime, list[float]] = {}
    for point in quarters:
        if not isinstance(point, dict) or "watts" not in point:
            continue
        ts = _as_datetime(point.get("datetime"))
        watts = point.get("watts")
        if ts is None or watts is None:
            continue
        try:
            w = float(watts)
        except (TypeError, ValueError):
            continue
        hour = ts.replace(minute=0, second=0, microsecond=0)
        acc = sums.setdefault(hour, [0.0, 0])
        acc[0] += w
        acc[1] += 1
    return [
        {"period_start": hour.isoformat(), "pv_estimate": round(total / n / 1000.0, 4)}
        for hour, (total, n) in sorted(sums.items(), key=lambda kv: kv[0].isoformat())
    ]


def merge_hourly_points(entities_raw: list[list[dict]]) -> list[dict]:
    """Combine several solar-forecast entities' hourly points into one list.

    Each entity's points are Solcast-shaped (see solar_points_from_attributes):
    [{"period_start": <iso str or datetime>, "pv_estimate": <kWh>}, ...].
    Hours that several entities cover are ADDED (as of 2026.10.21): Helios
    Forecast set up once per roof plane gives one sensor per plane for the
    same hours, and the house gets the sum. Solcast's day sensors
    (today/tomorrow/day_3/...) each cover their own day, so for them this is
    the same chaining as before. Within one entity a repeated hour keeps its
    last value, as before. Hours are keyed like build_solar_forecast does:
    the local wall-clock top of the hour.
    """
    totals: dict[datetime, float] = {}
    for points in entities_raw:
        own: dict[datetime, float] = {}
        for point in points or []:
            ts = _as_datetime(point.get("period_start"))
            estimate = point.get("pv_estimate")
            if ts is None or estimate is None:
                continue
            try:
                own[ts.replace(minute=0, second=0, microsecond=0, tzinfo=None)] = float(estimate)
            except (TypeError, ValueError):
                continue
        for hour, value in own.items():
            totals[hour] = totals.get(hour, 0.0) + value
    return [
        {"period_start": hour.isoformat(), "pv_estimate": round(value, 4)}
        for hour, value in sorted(totals.items())
    ]


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
    charge_efficiency: float = 1.0,
    discharge_efficiency: float = 1.0,
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

    `charge_efficiency` / `discharge_efficiency` (0-1, as of v0.4.3): the
    inverter/battery losses. A solar surplus of 2.0 kWh at 90% charge
    efficiency puts 1.8 kWh into the battery; covering 0.5 kWh of usage at
    90% discharge efficiency takes 0.5 / 0.9 = 0.56 kWh out of it. Applied
    first, so the max charge/discharge caps are on the battery side.
    """
    fraction_remaining = (60 - now.minute) / 60
    values: list[float] = []
    soc = start_kwh
    for h, delta in enumerate(net):
        capped_delta = delta * charge_efficiency if delta > 0 else delta / discharge_efficiency
        if max_charge_kw is not None:
            capped_delta = min(capped_delta, max_charge_kw)
        if max_discharge_kw is not None:
            capped_delta = max(capped_delta, -max_discharge_kw)
        step = capped_delta * fraction_remaining if h == 0 else capped_delta
        soc = soc + step
        values.append(round(soc, 2))
    return values


# ---------------------------------------------------------------------------
# Solar deficit / surplus (as of v0.4.2) - which minimum SOC applies
# ---------------------------------------------------------------------------
SOLAR_MODE_DEFICIT = "deficit"
SOLAR_MODE_SURPLUS = "surplus"


def compute_solar_mode(raw_forecast: list[float], capacity_kwh: float, previous_mode: Optional[str] = None) -> dict:
    """Whether solar carries the house over the whole forecast (surplus) or
    the grid will be needed (deficit), from the RAW battery forecast
    (solar and usage only - no planned charges or sales), all 121 hours.

    - The first hour it drops below 0 kWh (the battery would run empty) is
      the empty hour; the first hour it goes above 100% of capacity (the
      battery would fill up on solar alone) is the full hour.
    - Deficit when it runs empty before it fills up (or runs empty and
      never fills up); surplus when it fills up first (or fills up and
      never runs empty). A small dip right now followed by a climb to 100%
      therefore stays surplus: the sun refills the battery before it's
      empty, so a charge from the grid would be wasted.
    - Neither within the forecast (it stays between 0% and 100% all along):
      the mode stays what it was (`previous_mode`, as of 2026.10.8) - 0%
      and 100% are the two switch points, in between nothing changes.
      Surplus when there's no previous mode (a brand-new installation).

    Deficit uses the higher "Minimum SOC (solar deficit)" (backup energy
    for a grid failure when the grid is what refills the battery);
    surplus the lower "Minimum SOC (solar surplus)".
    """
    empty_hour = next((h for h, kwh in enumerate(raw_forecast) if kwh < 0), None)
    full_hour = next((h for h, kwh in enumerate(raw_forecast) if kwh > capacity_kwh), None)
    if empty_hour is None and full_hour is None:
        held = previous_mode in (SOLAR_MODE_DEFICIT, SOLAR_MODE_SURPLUS)
        return {
            "mode": previous_mode if held else SOLAR_MODE_SURPLUS,
            "empty_hour": None,
            "full_hour": None,
            "held": held,
        }
    deficit = empty_hour is not None and (full_hour is None or empty_hour < full_hour)
    return {
        "mode": SOLAR_MODE_DEFICIT if deficit else SOLAR_MODE_SURPLUS,
        "empty_hour": empty_hour,
        "full_hour": full_hour,
        "held": False,
    }


# ---------------------------------------------------------------------------
# The battery can't go above 100% (as of 2026.10.1)
# ---------------------------------------------------------------------------
def clip_at_capacity(forecast: list[float], start_kwh: float, capacity_kwh: float) -> tuple[list[float], list[float]]:
    """The forecast as the battery will really see it: never above
    `capacity_kwh`. The forecasts are otherwise running sums without a top,
    so after a solar day that "fills" the battery to e.g. 106% every later
    hour is 6% too high - in reality that energy went to the grid and the
    battery drains from 100%. Here each hour's change is applied to the
    clipped level instead; whatever would have pushed it over the top is
    returned per hour as the spill (battery side, kWh).

    Not clipped at the bottom: a level below 0 is what tells the charge plan
    how much is missing.

    The sale logic (high discharge plan) keeps using the unclipped forecast -
    the highest expected level is exactly what it sells off."""
    clipped: list[float] = []
    spill: list[float] = []
    prev_raw = start_kwh
    level = min(start_kwh, capacity_kwh)
    for value in forecast:
        delta = float(value) - prev_raw
        prev_raw = float(value)
        new = level + delta
        over = max(new - capacity_kwh, 0.0)
        level = new - over
        clipped.append(round(level, 2))
        spill.append(round(over, 3))
    return clipped, spill


def solar_surplus_windows(
    spill_full_kwh: list[float],
    spill_rate_kwh: list[float],
    now: datetime,
    min_kwh: float = 0.05,
) -> list[dict]:
    """The hours solar goes to the grid because the battery is full
    (`spill_full_kwh`) or can't charge as fast as the solar comes in
    (`spill_rate_kwh`), both per forecast hour (hour 0 = this one), merged
    into windows: [{start, stop, kwh, reason}] - reason "full" when the
    battery is full in any of its hours, otherwise "rate". Hour 0 starts
    now; an hour counts from `min_kwh` (so rounding noise isn't a window)."""
    hour0 = now.replace(minute=0, second=0, microsecond=0)
    out: list[dict] = []
    current = None
    n = max(len(spill_full_kwh), len(spill_rate_kwh))
    for h in range(n):
        full = spill_full_kwh[h] if h < len(spill_full_kwh) else 0.0
        rate = spill_rate_kwh[h] if h < len(spill_rate_kwh) else 0.0
        total = full + rate
        if total >= min_kwh:
            start = now if h == 0 else hour0 + timedelta(hours=h)
            stop = hour0 + timedelta(hours=h + 1)
            if current is None:
                current = {"start": start, "stop": stop, "kwh": 0.0, "full": False}
            current["stop"] = stop
            current["kwh"] += total
            current["full"] = current["full"] or full >= min_kwh
        elif current is not None:
            out.append(current)
            current = None
    if current is not None:
        out.append(current)
    return [
        {
            "start": w["start"].isoformat(),
            "stop": w["stop"].isoformat(),
            "kwh": round(w["kwh"], 2),
            "reason": "full" if w["full"] else "rate",
        }
        for w in out
    ]


def rate_spill(net: list[float], now: datetime, max_charge_kw: Optional[float], charge_efficiency: float = 1.0) -> list[float]:
    """Per forecast hour, the solar surplus (solar minus usage, kWh) the
    battery can't take because it's more than `max_charge_kw` - the same
    cap build_battery_forecast applies - as grid-side kWh (it goes to the
    grid). Hour 0 only counts what's left of it."""
    if not max_charge_kw or max_charge_kw <= 0:
        return [0.0] * len(net)
    eff = charge_efficiency if charge_efficiency > 0 else 1.0
    fraction_remaining = (60 - now.minute) / 60
    out = []
    for h, value in enumerate(net):
        over = max(float(value) - max_charge_kw / eff, 0.0)
        out.append(round(over * (fraction_remaining if h == 0 else 1.0), 3))
    return out


NIGHT_FROM_HOUR = 22   # the night limit (as of 2026.10.18): 22:00 ...
NIGHT_UNTIL_HOUR = 7   # ... to 07:00


def is_night_hour(hour: int) -> bool:
    return hour >= NIGHT_FROM_HOUR or hour < NIGHT_UNTIL_HOUR


def unit_is_night(unit: int) -> bool:
    """A 15-minute unit (from today's midnight) in the night window."""
    return is_night_hour((unit // 4) % 24)


def night_share(units: list[int]) -> float:
    """Share of the given units that fall in the night window."""
    return sum(1 for u in units if unit_is_night(u)) / len(units) if units else 0.0


def _window_units(plan: dict) -> list[int]:
    if plan.get("discharge_start_unit") is not None:
        return list(range(plan["discharge_start_unit"], plan.get("discharge_end_unit", plan["discharge_start_unit"])))
    if plan.get("blocks"):
        return [u for b in plan["blocks"] for u in range(b["start_unit"], b["end_unit"])]
    if plan.get("start_unit") is not None:
        return list(range(plan["start_unit"], plan.get("end_unit", plan["start_unit"])))
    return []


def night_discharge_plan(compute, day_kw: float, night_kw: Optional[float], rounds: int = 4) -> dict:
    """A discharge plan with the night limit (as of 2026.10.18), per quarter:
    the setpoint sent is the night speed in the quarters between 22:00 and
    07:00 and the plan's own speed in the others, so the plan is worked out
    at the average of those over its window - its energy is then exactly
    what the quarters really move, also for a block across 07:00 or 22:00.
    The window can move with the speed, so this is repeated (a few rounds)
    until it settles. `plan["night_share"]` = its share of night quarters,
    `plan["speed_kw"]` = the average it was worked out at."""
    plan = compute(day_kw)
    if night_kw is None or night_kw <= 0 or not plan.get("active"):
        return plan
    kw = day_kw
    share = 0.0
    for _ in range(rounds):
        units = _window_units(plan)
        if not units:
            return plan
        share = night_share(units)
        avg = share * night_kw + (1 - share) * day_kw
        if abs(avg - kw) < 1e-6:
            break
        kw = avg
        plan = compute(kw)
        if not plan.get("active"):
            return plan
    if share > 0:
        plan["night_limited"] = True
        plan["night_share"] = round(share, 3)
        plan["speed_kw"] = round(kw, 3)
    return plan


def grid_charge_rates(
    net: list[float],
    now: datetime,
    speed_kw: float,
    max_charge_kw: Optional[float],
    n_units: int,
    charge_efficiency: float = 1.0,
    discharge_efficiency: float = 1.0,
    night_kw: Optional[float] = None,
) -> list[float]:
    """Per 15-minute unit (index = units from today's midnight, like the
    prices), how much a grid charge at `speed_kw` really adds to the battery
    on top of the forecast (battery side, kWh) - as of 2026.10.4.

    The battery takes at most `max_charge_kw`. Solar left over after usage
    (`net`, per forecast hour, hour 0 = this one) already charges it, so in a
    sunny hour the grid can only add what's left up to that max - nothing at
    all when the sun alone already fills the max charge speed. In an hour
    without solar the grid charge also covers the house, which the forecast
    otherwise takes out of the battery. Units before this hour are 0. With
    `night_kw` (the night limit) that speed replaces `speed_kw` between
    22:00 and 07:00."""
    ce = charge_efficiency if charge_efficiency > 0 else 1.0
    de = discharge_efficiency if discharge_efficiency > 0 else 1.0
    cap = float(max_charge_kw) if max_charge_kw and max_charge_kw > 0 else float("inf")
    speed = min(max(float(speed_kw or 0.0), 0.0), cap)

    def gain(kw: float) -> float:
        return min(kw * ce, cap) if kw > 0 else kw / de

    night = min(max(float(night_kw), 0.0), cap) if night_kw is not None else None
    hour0 = now.hour * 4
    out = [0.0] * max(n_units, 0)
    for u in range(hour0, len(out)):
        h = (u - hour0) // 4
        x = float(net[h]) if h < len(net) and net[h] is not None else 0.0
        s = night if night is not None and unit_is_night(u) else speed
        out[u] = round(max(gain(s + x) - gain(x), 0.0) / 4, 4) if s > 0 else 0.0
    return out
