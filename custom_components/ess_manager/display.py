"""Small pure-function helpers that flatten the plan dicts into the
human-readable display values the original sensor exposed as its own
attributes (`charge energy kwh`, `charge start time`, ...). Kept separate
from plans.py because these are presentation-only, not planning logic.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def _format_time(now: datetime, cur_unit: int, target_unit: int) -> str:
    offset_units = target_unit - cur_unit
    return (now + timedelta(minutes=offset_units * 15)).strftime("%a %H:%M")


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
            round(full["target_kwh"], 2),
            _format_time(now, cur_unit, full["start_unit"]),
            _format_time(now, cur_unit, full["end_unit"]),
        )
    if neg.get("active") and cur_unit < neg.get("charge_end_unit", -1):
        return (
            round(neg["achievable_charge_kwh"], 2),
            _format_time(now, cur_unit, neg["charge_start_unit"]),
            _format_time(now, cur_unit, neg["charge_end_unit"]),
        )
    if spike.get("active") and cur_unit < spike.get("discharge_end_unit", -1):
        return (
            round(spike["charge_needed_kwh"], 2),
            _format_time(now, cur_unit, spike["charge_start_unit"]),
            _format_time(now, cur_unit, spike["charge_end_unit"]),
        )
    if low.get("active"):
        return (
            round(low["target_kwh"], 2),
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
