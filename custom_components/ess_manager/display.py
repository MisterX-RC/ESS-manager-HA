"""Small pure-function helpers that flatten the plan dicts into the
human-readable display values the original sensor exposed as its own
attributes (`charge energy kwh`, `charge start time`, ...). Kept separate
from plans.py because these are presentation-only, not planning logic.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def _format_time(now: datetime, cur_unit: int, target_unit: int) -> str:
    """`now` is the coordinator's actual wall-clock timestamp at the moment
    it last recalculated (e.g. 19:23:07), not the start of the current
    15-minute price unit (19:15) - so it's floored to that unit's start
    first. Otherwise every displayed time would carry forward whatever
    odd number of minutes "now" happened to be past the last quarter-hour
    (offset_units * 15 is always a whole multiple of 15, so that leftover
    never cancels out), showing e.g. "19:08" instead of "19:00"/"19:15" and
    drifting a little between updates as the real clock advances.
    """
    unit_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    offset_units = target_unit - cur_unit
    return (unit_start + timedelta(minutes=offset_units * 15)).strftime("%a %H:%M")


def charge_display(
    full: dict, neg: dict, spike: dict, low: dict, cur_unit: int, now: datetime
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Returns (energy_kwh, start_time_text, stop_time_text) for whichever
    plan currently governs the charge side, priority: full charge plan ->
    negative price plan -> spike plan -> low charge plan. All three None
    when nothing's active.

    Full charge plan takes top priority (over the day-to-day cost-driven
    plans) because it's a deliberate, infrequent maintenance action (once
    every `full_charge_interval_days`) rather than routine charging - if
    it's scheduled or actively running, that's the charge cycle worth
    surfacing. Only its "scheduled" and "charging" phases carry a
    start_unit/end_unit/target_kwh to show; "holding" (post-full balancing)
    doesn't represent a charge window at all, so it falls through to the
    other plans same as when full charge plan isn't active.
    """
    if full.get("active") and full.get("phase") in ("scheduled", "charging"):
        return (
            # with blocks (as of 2026.10.6): what this block charges
            round(full.get("block_kwh", full["target_kwh"]), 2),
            _format_time(now, cur_unit, full["start_unit"]),
            _format_time(now, cur_unit, full["end_unit"]),
        )
    if neg.get("active") and cur_unit < neg.get("charge_end_unit", -1):
        return (
            round(neg["achievable_charge_kwh"], 2),
            _format_time(now, cur_unit, neg["charge_start_unit"]),
            _format_time(now, cur_unit, neg["charge_end_unit"]),
        )
    # The spike plan stays "active" for its whole lifetime, charge phase
    # through discharge phase (compute_spike_plan only clears it once
    # cur_unit reaches discharge_end_unit), so this checks the plan's own
    # charge_end_unit here - not discharge_end_unit - otherwise the charge
    # window would still display as upcoming (with a stale, already-past
    # start/stop time) for the entire gap between the charge window ending
    # and the discharge window beginning.
    if spike.get("active") and cur_unit < spike.get("charge_end_unit", -1):
        return (
            round(spike["charge_needed_kwh"], 2),
            _format_time(now, cur_unit, spike["charge_start_unit"]),
            _format_time(now, cur_unit, spike["charge_end_unit"]),
        )
    if low.get("active"):
        return (
            round(low.get("block_kwh", low["target_kwh"]), 2),
            _format_time(now, cur_unit, low["start_unit"]),
            _format_time(now, cur_unit, low["end_unit"]),
        )
    return None, None, None


def discharge_display(
    neg: dict, spike: dict, high: dict, cur_unit: int, now: datetime
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Same as charge_display, for the discharge side: negative price plan
    (pre-discharge) -> spike plan -> high discharge plan.
    """
    if neg.get("active") and cur_unit < neg.get("discharge_end_unit", -1) and neg.get("discharge_needed_kwh", 0) > 0:
        return (
            round(neg["discharge_needed_kwh"], 2),
            _format_time(now, cur_unit, neg["discharge_start_unit"]),
            _format_time(now, cur_unit, neg["discharge_end_unit"]),
        )
    if spike.get("active") and cur_unit < spike.get("discharge_end_unit", -1):
        return (
            round(spike["discharge_target_kwh"], 2),
            _format_time(now, cur_unit, spike["discharge_start_unit"]),
            _format_time(now, cur_unit, spike["discharge_end_unit"]),
        )
    if high.get("active"):
        return (
            round(high["target_kwh"], 2),
            _format_time(now, cur_unit, high["start_unit"]),
            _format_time(now, cur_unit, high["end_unit"]),
        )
    return None, None, None


def spike_status_text(spike: dict) -> str:
    if spike.get("active"):
        return f"Active (€{spike['day_min_price']} → €{spike['day_max_price']})"
    return "Inactive"


def negative_price_status_text(neg: dict) -> str:
    if neg.get("active"):
        return f"Active (below €{neg['threshold']}, {neg['achievable_charge_kwh']} kWh)"
    return "Inactive"


def next_full_charge_in_days(interval_days: float, time_since_days: float) -> float:
    return round(max(interval_days - time_since_days, 0), 1)


def cell_voltage_differential_mv(low_v: Optional[float], high_v: Optional[float]) -> Optional[float]:
    """The full-charge balancing plan's voltage_diff input, derived from a
    pair of lowest/highest individual-cell-voltage sensors instead of a BMS
    that already exposes the differential as its own sensor.

    Individual per-cell voltage sensors are conventionally reported in
    Home Assistant in volts (e.g. 3.285), while
    plans.compute_full_charge_plan's balance_threshold default (10.0) - and
    the single-sensor CONF_VOLTAGE_DIFF_ENTITY path - both assume
    millivolts (matching how a BMS like a JK BMS exposes its own "cell
    voltage differential" sensor). So this multiplies by 1000 to convert,
    not just subtracts. None if either reading isn't available - the
    caller should NOT substitute a fallback voltage into the subtraction,
    since that would fabricate a specific (and possibly wrong) differential
    rather than honestly reporting "no reading this cycle" and letting
    compute_full_charge_plan's own None-handling (treat as unbalanced,
    matching its 999.0 default) take over.
    """
    if low_v is None or high_v is None:
        return None
    return round((high_v - low_v) * 1000, 1)


# ---------------------------------------------------------------------------
# Status card data (as of v0.5.0) - the Buy and Sell blocks of the
# integration's own status card, one dict per side.
# ---------------------------------------------------------------------------
def _unit_datetime(now: datetime, cur_unit: int, target_unit: int) -> datetime:
    unit_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    return unit_start + timedelta(minutes=(target_unit - cur_unit) * 15)


def _card_side(
    source: str,
    charging: bool,
    start_unit: int,
    end_unit: int,
    energy_kwh: float,
    target_level_kwh: Optional[float],
    rate_kw: float,
    target_reached: bool,
    cur_unit: int,
    now: datetime,
    battery_now_kwh: float,
    capacity_kwh: float,
) -> dict:
    """One block: when, how much, to which level, and - once it has started
    - how much of it is done, measured on the battery level against the
    plan's target level (energy, not time: a plan stops on its target)."""
    energy = max(float(energy_kwh or 0.0), 0.0)
    started = cur_unit >= start_unit
    if target_reached:
        remaining = 0.0
    elif not started or target_level_kwh is None:
        remaining = energy
    elif charging:
        remaining = min(max(target_level_kwh - battery_now_kwh, 0.0), energy)
    else:
        remaining = min(max(battery_now_kwh - target_level_kwh, 0.0), energy)
    target_soc = None
    if target_level_kwh is not None and capacity_kwh:
        target_soc = round(min(max(target_level_kwh / capacity_kwh * 100.0, 0.0), 100.0), 1)
    return {
        "source": source,
        "start": _unit_datetime(now, cur_unit, start_unit).isoformat(),
        "stop": _unit_datetime(now, cur_unit, end_unit).isoformat(),
        "energy_kwh": round(energy, 2),
        "target_level_kwh": round(target_level_kwh, 2) if target_level_kwh is not None else None,
        "target_soc_percent": target_soc,
        "rate_kw": round(max(float(rate_kw or 0.0), 0.0), 3),
        "started": started,
        "target_reached": bool(target_reached) or (started and remaining <= 0.0 and energy > 0),
        "done_kwh": round(energy - remaining, 2),
        "remaining_kwh": round(remaining, 2),
    }


def _add_blocks(side: dict, plan: dict, cur_unit: int, now: datetime) -> None:
    """A charge in several blocks (as of 2026.10.6): the side shows the first
    (or running) one; `blocks` lists the ones after it as {start, stop,
    energy_kwh} and `more_blocks` counts them, for the cards."""
    later = [b for b in (plan.get("blocks") or [])[1:] if b.get("end_unit", 0) > cur_unit]
    if not later:
        return
    side["more_blocks"] = len(later)
    side["blocks"] = [
        {
            "start": _unit_datetime(now, cur_unit, b["start_unit"]).isoformat(),
            "stop": _unit_datetime(now, cur_unit, b["end_unit"]).isoformat(),
            "energy_kwh": round(float(b.get("kwh", 0) or 0), 2),
        }
        for b in later
    ]


def _holding_side(
    full: dict, balance: dict, cur_unit: int, now: datetime, battery_now_kwh: float, capacity_kwh: float
) -> dict:
    """The Buy block during the full charge plan's holding phase."""
    try:
        start = datetime.fromisoformat(full["hold_start"])
    except (KeyError, TypeError, ValueError):
        start = _unit_datetime(now, cur_unit, full.get("hold_start_unit", cur_unit))
    max_hold = balance.get("max_hold_minutes")
    if max_hold:
        stop = start + timedelta(minutes=float(max_hold))
    else:
        stop = _unit_datetime(now, cur_unit, full.get("hold_end_unit", cur_unit + 1))

    def _rounded(value, digits):
        return round(float(value), digits) if value is not None else None

    return {
        "source": "full_charge",
        "phase": "holding",
        "start": start.isoformat(),
        "stop": stop.isoformat(),
        "energy_kwh": 0.0,
        "target_level_kwh": round(capacity_kwh, 2) if capacity_kwh else None,
        "target_soc_percent": 100.0,
        "rate_kw": 0.0,
        "started": True,
        "target_reached": False,
        "done_kwh": 0.0,
        "remaining_kwh": 0.0,
        "voltage_diff_mv": _rounded(balance.get("voltage_diff_mv"), 1),
        "balance_threshold_mv": _rounded(balance.get("balance_threshold_mv"), 1),
        "battery_voltage": _rounded(balance.get("battery_voltage"), 2),
        "target_voltage": _rounded(balance.get("target_voltage"), 2),
    }


def _level_at_unit(
    forecast: Optional[list], battery_now_kwh: float, now: datetime, unit: int
) -> Optional[float]:
    """The forecast battery level (kWh) at the start of price unit `unit`
    (15-minute units from today's midnight; tomorrow's continue past 96),
    interpolated between now (the live level) and the forecast's hourly
    points (entry i = the level at the end of hour i, hour 0 = this one).
    None without a forecast."""
    if not forecast:
        return None
    now_min = now.hour * 60 + now.minute + now.second / 60.0
    target = (unit * 15 - now_min) / 60.0  # hours from now
    if target <= 0:
        return battery_now_kwh
    first = 1.0 - now_min % 60 / 60.0  # hours from now to the end of hour 0
    points = [(0.0, battery_now_kwh)] + [(first + i, float(v)) for i, v in enumerate(forecast) if v is not None]
    for (ta, va), (tb, vb) in zip(points, points[1:]):
        if target <= tb:
            return va + (vb - va) * (target - ta) / (tb - ta) if tb > ta else vb
    return points[-1][1]


def card_plans(
    full: dict,
    neg: dict,
    spike: dict,
    low: dict,
    high: dict,
    cur_unit: int,
    now: datetime,
    battery_now_kwh: float,
    capacity_kwh: float,
    forecast: Optional[list] = None,
    balance: Optional[dict] = None,
) -> dict:
    """{"buy": side | None, "sell": side | None} - the same plan priority as
    charge_display / discharge_display (full charge -> negative price ->
    spike -> low charge; negative price -> spike -> high discharge), so the
    card shows what the charge/discharge sensors show (except a spike plan
    without a top-up, which leaves the Buy block to the next plan). `source`
    names the plan, for the card's chip and outline.

    The low charge / high discharge plans carry their target level as
    "battery now +/- amount" (target_energy_kwh), which is only right once
    the window starts - their stop condition only uses it then. For a
    window still ahead (as of v0.5.5) the card's target is the expected
    level at its start (from `forecast`, the forecast with the plans in it)
    +/- the amount, so a sale tomorrow evening doesn't show "SOC now minus
    the sale".

    The full charge plan's holding phase (the balancing wait at 100%, as
    of v0.5.11) fills the Buy block too, with phase "holding": start = when
    the hold began, stop = when it times out (max hold), and from `balance`
    (max_hold_minutes, voltage_diff_mv, balance_threshold_mv,
    battery_voltage, target_voltage) the live readings the card shows. The
    hold ends earlier the moment balance is confirmed."""
    common = (cur_unit, now, battery_now_kwh, capacity_kwh)

    def ahead_target(plan: dict, charging: bool) -> Optional[float]:
        target = plan.get("target_energy_kwh")
        if cur_unit < plan.get("start_unit", 0):
            level = _level_at_unit(forecast, battery_now_kwh, now, plan["start_unit"])
            if level is not None:
                amount = plan.get("target_kwh", 0) or 0
                target = level + amount if charging else level - amount
        return target

    buy = None
    if full.get("active") and full.get("phase") == "holding":
        buy = _holding_side(full, balance or {}, *common)
    elif full.get("active") and full.get("phase") in ("scheduled", "charging"):
        buy = _card_side(
            "full_charge", True, full["start_unit"], full["end_unit"], full.get("block_kwh", full.get("target_kwh", 0)),
            capacity_kwh, full.get("effective_charge_per_unit", 0) * 4, False, *common,
        )
        buy["phase"] = full["phase"]
        _add_blocks(buy, full, cur_unit, now)
    elif neg.get("active") and cur_unit < neg.get("charge_end_unit", -1):
        target = (neg.get("level_at_start_kwh") or 0) + (neg.get("achievable_charge_kwh") or 0)
        buy = _card_side(
            "negative_price", True, neg["charge_start_unit"], neg["charge_end_unit"], neg.get("achievable_charge_kwh", 0),
            target, neg.get("effective_charge_per_unit", 0) * 4, False, *common,
        )
    elif spike.get("active") and cur_unit < spike.get("charge_end_unit", -1) and spike.get("charge_needed_kwh", 0) > 0:
        buy = _card_side(
            "spike", True, spike["charge_start_unit"], spike["charge_end_unit"], spike.get("charge_needed_kwh", 0),
            spike.get("charge_target_level_kwh"), spike.get("effective_charge_per_unit", 0) * 4, False, *common,
        )
    elif low.get("active"):
        # with blocks (as of 2026.10.6) the block shows its own amount
        low_block = {**low, "target_kwh": low.get("block_kwh", low.get("target_kwh", 0))}
        buy = _card_side(
            "low_charge", True, low["start_unit"], low["end_unit"], low_block.get("target_kwh", 0),
            ahead_target(low_block, True), low.get("effective_charge_per_unit", 0) * 4, low.get("target_reached", False),
            *common,
        )
        _add_blocks(buy, low, cur_unit, now)

    sell = None
    if neg.get("active") and cur_unit < neg.get("discharge_end_unit", -1) and neg.get("discharge_needed_kwh", 0) > 0:
        sell = _card_side(
            "negative_price", False, neg["discharge_start_unit"], neg["discharge_end_unit"], neg.get("discharge_needed_kwh", 0),
            neg.get("target_after_discharge_kwh"), neg.get("effective_discharge_per_unit", 0) * 4, False, *common,
        )
    elif spike.get("active") and cur_unit < spike.get("discharge_end_unit", -1):
        level = spike.get("charge_target_level_kwh")
        target = (level - spike.get("discharge_target_kwh", 0)) if level is not None else None
        sell = _card_side(
            "spike", False, spike["discharge_start_unit"], spike["discharge_end_unit"], spike.get("discharge_target_kwh", 0),
            target, spike.get("effective_discharge_per_unit", 0) * 4, False, *common,
        )
    elif high.get("active"):
        sell = _card_side(
            "high_discharge", False, high["start_unit"], high["end_unit"], high.get("target_kwh", 0),
            ahead_target(high, False), high.get("effective_discharge_per_unit", 0) * 4, high.get("target_reached", False),
            *common,
        )
    return {"buy": buy, "sell": sell}
