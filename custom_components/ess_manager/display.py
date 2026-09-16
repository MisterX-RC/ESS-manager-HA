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
    neg: dict, spike: dict, low: dict, cur_unit: int, now: datetime
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Returns (energy_kwh, start_time_text, stop_time_text) for whichever
    plan currently governs the charge side, priority: negative price plan
    -> spike plan -> low charge plan. All three None when nothing's active.
    """
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


def next_full_charge_in_days(interval_days: float, time_since_days: float) -> float:
    return round(max(interval_days - time_since_days, 0), 1)
