"""Pure-Python port of the five planning engines, the forecast-composition
chain, and system_status - originally five self-referencing Jinja2
attributes on sensor.ess_manager (see the project handoff doc). Every
function takes plain data in and returns plain data out; the coordinator is
responsible for state access, persistence of the "prev" lock-in dicts across
update cycles, and picking which config/number values to pass in.

15-minute "price units" are used throughout, exactly as in the original:
unit 0 = today 00:00-00:15, unit 95 = today 23:45-00:00, unit 96 = tomorrow
00:00-00:15, and so on. `cur_unit = hour*4 + minute // 15`.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional


def _hour0_start_unit(cur_unit: int, now: datetime) -> int:
    """Absolute unit at the top of the current hour."""
    return cur_unit - (now.minute // 15)


def _best_price_window(
    prices: list[float], search_start: int, search_end: int, units_needed: int, cheapest: bool
) -> int:
    """Sliding-window search for the cheapest (cheapest=True) or priciest
    contiguous `units_needed`-length window starting anywhere in
    [search_start, search_end). Falls back to `search_start` if the window
    doesn't fit. Direct port of the sub_ns / best_start pattern reused by
    every planning engine's own window search.
    """
    window_len = search_end - search_start
    if window_len <= units_needed:
        return search_start
    best_start = search_start
    best_sum: Optional[float] = None
    for s in range(search_start, search_end - units_needed + 1):
        window_sum = sum(prices[s : s + units_needed])
        if best_sum is None or (window_sum < best_sum if cheapest else window_sum > best_sum):
            best_sum = window_sum
            best_start = s
    return best_start


def _extend_flat_price_window(
    prices: list[float],
    start: int,
    end: int,
    min_start: int,
    tolerance_relative: float = 0.08,
    tolerance_absolute: float = 0.02,
) -> tuple[int, int]:
    """Grows a [start, end) price window outward, one 15-minute unit at a
    time on each side independently, for as long as the next adjacent
    unit's price stays within tolerance of the window's own current
    average price - either within `tolerance_relative` (8%) of it, or
    within `tolerance_absolute` (EUR 0.02), whichever is easier to satisfy.

    Mirrors the houseboat charge system's "extend into a flat-priced
    block" behavior (see claude/houseboat handoff notes): once a cheap
    window is found, it's fine to charge longer than the minimum computed
    duration if the surrounding price is basically the same, rather than
    always stopping exactly at that minimum. `min_start` prevents growing
    backward past the current unit (can't charge in the past); there's no
    corresponding forward bound beyond the price array's own length.
    """
    while start > min_start:
        window_avg = sum(prices[start:end]) / (end - start)
        diff = abs(prices[start - 1] - window_avg)
        if diff <= tolerance_absolute or (window_avg > 0 and diff / window_avg <= tolerance_relative):
            start -= 1
        else:
            break
    while end < len(prices):
        window_avg = sum(prices[start:end]) / (end - start)
        diff = abs(prices[end] - window_avg)
        if diff <= tolerance_absolute or (window_avg > 0 and diff / window_avg <= tolerance_relative):
            end += 1
        else:
            break
    return start, end


# ---------------------------------------------------------------------------
# Negative price plan
# ---------------------------------------------------------------------------
def compute_negative_price_plan(
    prev: Optional[dict],
    cur_unit: int,
    now: datetime,
    all_price: list[float],
    threshold: float,
    battery_forecast: list[float],
    discharge_speed_kw: float,
    negative_price_charge_speed_kw: float,
    low_threshold_kwh: float,
    high_threshold_kwh: float,
) -> dict:
    prev = prev or {"active": False}
    if prev.get("active") and cur_unit < prev.get("charge_end_unit", -1):
        return prev

    forecast = battery_forecast
    upper_limit = high_threshold_kwh

    start = None
    for i in range(cur_unit, len(all_price)):
        if all_price[i] < threshold:
            start = i
            break
    if start is None:
        return {"active": False}

    end_idx = start
    for _ in range(96):
        if (end_idx + 1) < len(all_price) and all_price[end_idx + 1] < threshold:
            end_idx += 1
    charge_start = start
    charge_end = end_idx + 1
    units = charge_end - charge_start

    charge_per_unit = negative_price_charge_speed_kw / 4
    raw_potential_kwh = round(units * charge_per_unit, 2)

    hour0_start_unit = _hour0_start_unit(cur_unit, now)
    hour_index_start = min(max((charge_start - cur_unit) // 4, 0), len(forecast) - 1) if forecast else 0
    level_at_start = float(forecast[hour_index_start]) if forecast else 0.0
    headroom_available = max(upper_limit - level_at_start, 0)
    discharge_needed_kwh = max(raw_potential_kwh - headroom_available, 0)

    pre_vals = []
    for h in range(len(forecast)):
        hs = hour0_start_unit + (h * 4)
        he = hs + 4
        if he > cur_unit and hs < charge_start:
            pre_vals.append(forecast[h])
    forecast_min_pre = min(pre_vals) if pre_vals else level_at_start
    max_safe_discharge_kwh = max(forecast_min_pre - low_threshold_kwh, 0)

    discharge_per_unit = discharge_speed_kw / 4
    discharge_units_needed_raw = max(math.ceil(discharge_needed_kwh / discharge_per_unit), 0)
    available_lead_units = max(charge_start - cur_unit, 0)
    discharge_units_by_energy = max(math.floor(max_safe_discharge_kwh / discharge_per_unit), 0)
    discharge_units = min(discharge_units_needed_raw, available_lead_units, discharge_units_by_energy)
    actual_discharge_kwh = round(discharge_units * discharge_per_unit, 2)
    achievable_headroom = headroom_available + actual_discharge_kwh
    achievable_charge_kwh = min(raw_potential_kwh, achievable_headroom)

    if discharge_units == 0:
        discharge_start = cur_unit
    else:
        search_end = charge_start - discharge_units
        if search_end <= cur_unit:
            discharge_start = cur_unit
        else:
            discharge_start = _best_price_window(all_price, cur_unit, search_end + discharge_units, discharge_units, cheapest=False)
    discharge_end = discharge_start + discharge_units

    target_after_discharge = round(upper_limit - achievable_charge_kwh, 2)
    export_start_unit = charge_start
    found_export = False
    for h in range(len(forecast)):
        hr_start = hour0_start_unit + (h * 4)
        hr_end = hr_start + 4
        if not found_export and hr_start >= discharge_end and hr_end <= charge_start and forecast[h] > target_after_discharge:
            found_export = True
            export_start_unit = hr_start
    solar_export_start = export_start_unit if found_export else charge_start
    solar_export_end = charge_start

    return {
        "active": True,
        "threshold": threshold,
        "charge_start_unit": charge_start,
        "charge_end_unit": charge_end,
        "charge_units": units,
        "raw_potential_kwh": raw_potential_kwh,
        "achievable_charge_kwh": round(achievable_charge_kwh, 2),
        "level_at_start_kwh": round(level_at_start, 2),
        "headroom_available_kwh": round(headroom_available, 2),
        "target_after_discharge_kwh": target_after_discharge,
        "discharge_needed_kwh": actual_discharge_kwh,
        "capped_by_energy_limit": discharge_units_by_energy < discharge_units_needed_raw,
        "discharge_start_unit": discharge_start,
        "discharge_end_unit": discharge_end,
        "solar_export_start_unit": solar_export_start,
        "solar_export_end_unit": solar_export_end,
        "effective_charge_per_unit": round(charge_per_unit, 4),
        "effective_discharge_per_unit": round(discharge_per_unit, 4),
    }


def compose_forecast_with_negative_price(
    raw: list[float], neg: dict, cur_unit: int, now: datetime, cap: float
) -> list[float]:
    """`cap` is the ceiling the charge phase is not allowed to cross - the
    original hardcoded `33 - 0.01`; here it's passed in as
    `high_threshold_kwh - 0.01` so it scales with the configured battery.
    """
    if not neg.get("active"):
        return list(raw)

    hour0_start_unit = _hour0_start_unit(cur_unit, now)
    values: list[float] = []
    discharge_delta = 0.0
    shift: Optional[float] = None
    for h in range(len(raw)):
        hour_start_unit = hour0_start_unit + (h * 4)
        hour_end_unit = hour_start_unit + 4
        if hour_end_unit <= neg["discharge_start_unit"]:
            values.append(round(raw[h], 2))
        elif hour_start_unit < neg["discharge_end_unit"]:
            overlap = max(min(hour_end_unit, neg["discharge_end_unit"]) - max(hour_start_unit, neg["discharge_start_unit"]), 0)
            discharge_delta -= overlap * neg["effective_discharge_per_unit"]
            values.append(round(raw[h] + discharge_delta, 2))
        elif hour_end_unit <= neg["charge_start_unit"]:
            values.append(round(min(raw[h] + discharge_delta, neg["target_after_discharge_kwh"]), 2))
        elif hour_start_unit < neg["charge_end_unit"]:
            charge_overlap = max(min(hour_end_unit, neg["charge_end_unit"]) - max(hour_start_unit, neg["charge_start_unit"]), 0)
            level_before = values[-1] if values else neg["target_after_discharge_kwh"]
            values.append(round(min(level_before + charge_overlap * neg["effective_charge_per_unit"], cap), 2))
        elif shift is None:
            level_before = values[-1] if values else neg["target_after_discharge_kwh"]
            shift = raw[h] - level_before
            values.append(round(raw[h] - shift, 2))
        else:
            values.append(round(raw[h] - shift, 2))
    return values


# ---------------------------------------------------------------------------
# Spike plan
# ---------------------------------------------------------------------------
def compute_spike_plan(
    prev: Optional[dict],
    cur_unit: int,
    all_price: list[float],
    battery_forecast: list[float],
    usage: list[float],
    low_threshold_kwh: float,
    upper_limit_kwh: float,
    high_threshold_kwh: float,
    spike_margin: float,
    charge_speed_kw: float,
    spike_discharge_speed_kw: float,
    neg_plan: Optional[dict],
) -> dict:
    prev = prev or {"active": False}
    if prev.get("active") and prev.get("charge_start_unit", -1) <= cur_unit < prev.get("discharge_end_unit", -1):
        return prev

    prices = all_price
    forecast = battery_forecast
    neg = neg_plan or {"active": False}
    neg_excl_start = neg.get("charge_start_unit", -1) if neg.get("active") else -1
    neg_excl_end = neg.get("charge_end_unit", -1) if neg.get("active") else -1
    high_sentinel = 999
    masked_prices = [
        high_sentinel if (neg.get("active") and neg_excl_start <= i < neg_excl_end) else prices[i]
        for i in range(len(prices))
    ]

    found = False
    day_start_sel = 0
    low_abs = high_abs = 0
    day_min = day_max = 0.0
    for day_start in (0, 96):
        if found or (day_start + 96) > len(prices):
            continue
        d_min = d_max = None
        min_idx = max_idx = day_start
        for i in range(day_start, day_start + 96):
            if neg.get("active") and neg_excl_start <= i < neg_excl_end:
                continue
            if d_min is None or prices[i] < d_min:
                d_min, min_idx = prices[i], i
            if d_max is None or prices[i] > d_max:
                d_max, max_idx = prices[i], i
        if d_min is not None and (d_max - d_min) > spike_margin:
            if min_idx < max_idx and max_idx > cur_unit:
                found = True
                day_start_sel = day_start
                low_abs, high_abs = min_idx, max_idx
                day_min, day_max = d_min, d_max

    if not found:
        return {"active": False}

    after = prices[high_abs + 1 :]
    later_min = min(after) if after else None
    recharge_qualifies = later_min is not None and (day_max - later_min) > spike_margin
    recharge_unit = high_abs + 1 + after.index(later_min) if recharge_qualifies else high_abs

    hour_index_high = min(max((high_abs - cur_unit) // 4, 0), len(forecast) - 1) if forecast else 0
    solar_only_level = float(forecast[hour_index_high]) if forecast else 0.0
    if solar_only_level >= high_threshold_kwh:
        charge_target_level = high_threshold_kwh - 0.1
    else:
        charge_target_level = upper_limit_kwh
    charge_needed_kwh = max(charge_target_level - solar_only_level, 0)

    charge_per_unit = charge_speed_kw / 4
    hour_index_low = min(max((low_abs - cur_unit) // 4, 0), len(usage) - 1) if usage else 0
    relevant_usage = usage[0 : hour_index_low + 1]
    avg_usage_kwh = sum(relevant_usage) / len(relevant_usage) if relevant_usage else 0
    avg_usage_per_unit = avg_usage_kwh / 4
    effective_charge_per_unit = max(charge_per_unit - avg_usage_per_unit, 0.1)
    charge_units_needed = max(math.ceil(charge_needed_kwh / effective_charge_per_unit), 0)

    if charge_units_needed == 0:
        charge_start = charge_end = cur_unit
    else:
        search_end = high_abs
        window_len = search_end - cur_unit
        if window_len <= charge_units_needed:
            charge_start = cur_unit
        else:
            best_start = cur_unit
            best_sum = None
            for s in range(cur_unit, search_end - charge_units_needed + 1):
                window_sum = sum(masked_prices[s : s + charge_units_needed])
                if best_sum is None or window_sum < best_sum:
                    best_sum = window_sum
                    best_start = s
            charge_start = best_start
        charge_end = charge_start + charge_units_needed

    discharge_per_unit = spike_discharge_speed_kw / 4
    relevant_usage_d = usage[0 : hour_index_high + 1]
    avg_usage_kwh_d = sum(relevant_usage_d) / len(relevant_usage_d) if relevant_usage_d else 0
    avg_usage_per_unit_d = avg_usage_kwh_d / 4
    effective_discharge_per_unit = discharge_per_unit + avg_usage_per_unit_d

    forecast_min = min(forecast) if forecast else low_threshold_kwh
    max_safe_surplus = max(forecast_min - low_threshold_kwh, 0)
    aggressive_target_kwh = max(charge_target_level - low_threshold_kwh, 0)
    if recharge_qualifies:
        hour_index_recharge = min(max((recharge_unit - cur_unit) // 4, hour_index_high), len(forecast) - 1) if forecast else 0
        natural_decline_to_recharge = max(solar_only_level - (float(forecast[hour_index_recharge]) if forecast else 0.0), 0)
        raw_desired_discharge_kwh = max(aggressive_target_kwh - natural_decline_to_recharge, 0)
    else:
        raw_desired_discharge_kwh = aggressive_target_kwh
    desired_discharge_kwh = min(raw_desired_discharge_kwh, max_safe_surplus)
    capped_by_energy_limit = desired_discharge_kwh < raw_desired_discharge_kwh

    desired_units = max(math.ceil(desired_discharge_kwh / effective_discharge_per_unit), 1)

    discharge_price_floor = (int(day_min * 100) / 100) + spike_margin
    day_end = day_start_sel + 96
    back_i = high_abs
    for _ in range(96):
        if back_i > day_start_sel and prices[back_i - 1] >= discharge_price_floor:
            back_i -= 1
    run_start = back_i
    fwd_i = high_abs
    for _ in range(96):
        if (fwd_i + 1) < day_end and prices[fwd_i + 1] >= discharge_price_floor:
            fwd_i += 1
    run_end_inclusive = fwd_i
    run_max_units = run_end_inclusive - run_start + 1

    discharge_units_needed = min(desired_units, run_max_units)
    discharge_capped_by_price = discharge_units_needed < desired_units

    if discharge_units_needed >= run_max_units:
        discharge_start = run_start
    else:
        best_start = high_abs
        best_sum = None
        for s in range(run_start, run_end_inclusive - discharge_units_needed + 2):
            window_sum = sum(prices[s : s + discharge_units_needed])
            if best_sum is None or window_sum > best_sum:
                best_sum = window_sum
                best_start = s
        discharge_start = best_start
    discharge_end = discharge_start + discharge_units_needed
    discharge_target_kwh = round(discharge_units_needed * effective_discharge_per_unit, 2)

    return {
        "active": True,
        "day_start": day_start_sel,
        "low_price_unit": low_abs,
        "high_price_unit": high_abs,
        "day_min_price": day_min,
        "day_max_price": day_max,
        "recharge_qualifies": recharge_qualifies,
        "recharge_unit": recharge_unit,
        "charge_target_level_kwh": round(charge_target_level, 2),
        "charge_needed_kwh": round(charge_needed_kwh, 2),
        "charge_start_unit": charge_start,
        "charge_end_unit": charge_end,
        "discharge_target_kwh": discharge_target_kwh,
        "discharge_desired_kwh": round(desired_discharge_kwh, 2),
        "capped_by_energy_limit": capped_by_energy_limit,
        "discharge_price_floor": round(discharge_price_floor, 3),
        "discharge_capped_by_price": discharge_capped_by_price,
        "discharge_start_unit": discharge_start,
        "discharge_end_unit": discharge_end,
        "effective_charge_per_unit": round(effective_charge_per_unit, 4),
        "effective_discharge_per_unit": round(effective_discharge_per_unit, 4),
    }


def compose_forecast_with_spike(
    raw: list[float], spike: dict, cur_unit: int, now: datetime, cap: float
) -> list[float]:
    if not spike.get("active"):
        return list(raw)

    hour0_start_unit = _hour0_start_unit(cur_unit, now)
    post_discharge_level = spike["charge_target_level_kwh"] - spike["discharge_target_kwh"]
    values: list[float] = []
    shift: Optional[float] = None
    charge_delta = 0.0
    for h in range(len(raw)):
        hour_start_unit = hour0_start_unit + (h * 4)
        hour_end_unit = hour_start_unit + 4
        if hour_end_unit <= spike["discharge_start_unit"]:
            charge_overlap = max(min(hour_end_unit, spike["charge_end_unit"]) - max(hour_start_unit, spike["charge_start_unit"]), 0)
            charge_delta += charge_overlap * spike["effective_charge_per_unit"]
            values.append(round(min(raw[h] + charge_delta, cap), 2))
        elif shift is None:
            shift = raw[h] - post_discharge_level
            values.append(round(raw[h] - shift, 2))
        else:
            values.append(round(raw[h] - shift, 2))
    return values


# ---------------------------------------------------------------------------
# Low charge plan / High discharge plan
# ---------------------------------------------------------------------------
def compute_low_charge_plan(
    prev: Optional[dict],
    cur_unit: int,
    forecast_with_spike: list[float],
    now: datetime,
    charge_speed_kw: float,
    low_threshold_kwh: float,
    minimum_charge_target_kwh: float,
    upper_limit_kwh: float,
    usage: list[float],
    all_price: list[float],
    planning_horizon_hours: int,
) -> dict:
    prev = prev or {"active": False}
    if prev.get("active") and prev.get("start_unit", -1) <= cur_unit < prev.get("end_unit", -1):
        return prev

    forecast = forecast_with_spike[0 : planning_horizon_hours + 1]
    charge_per_unit = charge_speed_kw / 4

    hour_index = None
    value = 0.0
    for h in range(len(forecast)):
        if forecast[h] < low_threshold_kwh:
            hour_index = h
            value = forecast[h]
            break

    if hour_index is None:
        return {"active": False, "breach_unit": 999999}

    units_to_next_hour = 4 - (now.minute // 15)
    breach_offset_units = units_to_next_hour + (hour_index * 4)
    breach_unit = cur_unit + breach_offset_units
    target_level = max(low_threshold_kwh, minimum_charge_target_kwh)
    deficit = round(target_level - value, 3)
    future_peak = max(forecast) if forecast else upper_limit_kwh
    headroom = upper_limit_kwh - future_peak
    target_kwh = max(deficit, headroom)

    relevant_usage = usage[0 : hour_index + 1]
    avg_usage_kwh = sum(relevant_usage) / len(relevant_usage) if relevant_usage else 0
    avg_usage_per_unit = avg_usage_kwh / 4
    effective_charge_per_unit = max(charge_per_unit - avg_usage_per_unit, 0.1)
    units_needed = max(math.ceil(target_kwh / effective_charge_per_unit), 1)

    search_end = min(breach_unit, len(all_price))
    best_start = _best_price_window(all_price, cur_unit, search_end, units_needed, cheapest=True)

    return {
        "active": True,
        "deficit_kwh": deficit,
        "target_kwh": target_kwh,
        "avg_home_load_kw": round(avg_usage_kwh, 3),
        "effective_charge_per_unit": round(effective_charge_per_unit, 4),
        "units_needed": units_needed,
        "breach_unit": breach_unit,
        "start_unit": best_start,
        "end_unit": best_start + units_needed,
    }


def compute_high_discharge_plan(
    prev: Optional[dict],
    cur_unit: int,
    forecast_with_spike: list[float],
    now: datetime,
    discharge_speed_kw: float,
    high_threshold_kwh: float,
    low_threshold_kwh: float,
    usage: list[float],
    all_price: list[float],
    planning_horizon_hours: int,
) -> dict:
    prev = prev or {"active": False}
    if prev.get("active") and prev.get("start_unit", -1) <= cur_unit < prev.get("end_unit", -1):
        return prev

    forecast = forecast_with_spike[0 : planning_horizon_hours + 1]
    discharge_per_unit = discharge_speed_kw / 4

    hour_index = None
    for h in range(len(forecast)):
        if forecast[h] > high_threshold_kwh:
            hour_index = h
            break

    if hour_index is None:
        return {"active": False, "breach_unit": 999999}

    units_to_next_hour = 4 - (now.minute // 15)
    breach_offset_units = units_to_next_hour + (hour_index * 4)
    breach_unit = cur_unit + breach_offset_units
    future_peak = max(forecast) if forecast else high_threshold_kwh
    raw_surplus = round(future_peak - high_threshold_kwh, 3)
    forecast_min = min(forecast) if forecast else low_threshold_kwh
    max_safe_surplus = round(forecast_min - low_threshold_kwh, 3)
    surplus = max(min(raw_surplus, max_safe_surplus), 0)

    if surplus <= 0:
        return {"active": False, "breach_unit": 999999}

    relevant_usage = usage[0 : hour_index + 1]
    avg_usage_kwh = sum(relevant_usage) / len(relevant_usage) if relevant_usage else 0
    avg_usage_per_unit = avg_usage_kwh / 4
    effective_discharge_per_unit = discharge_per_unit + avg_usage_per_unit
    units_needed = max(math.ceil(surplus / effective_discharge_per_unit), 1)

    search_end = min(breach_unit, len(all_price))
    best_start = _best_price_window(all_price, cur_unit, search_end, units_needed, cheapest=False)

    return {
        "active": True,
        "surplus_kwh": surplus,
        "target_kwh": surplus,
        "avg_home_load_kw": round(avg_usage_kwh, 3),
        "effective_discharge_per_unit": round(effective_discharge_per_unit, 4),
        "capped_by_low_limit": surplus < raw_surplus,
        "breach_unit": breach_unit,
        "start_unit": best_start,
        "end_unit": best_start + units_needed,
        "units_needed": units_needed,
    }


def compose_forecast_adjusted(
    base: list[float],
    low: dict,
    high: dict,
    cur_unit: int,
    now: datetime,
    full: Optional[dict] = None,
    upper_limit_kwh: float = 0.0,
) -> list[float]:
    """`full` (the full-charge plan) is optional, keyword-only in practice,
    and defaults to inactive - existing callers/tests that only care about
    the low/high plans can keep calling with just `base`/`low`/`high`/
    `cur_unit`/`now` and get the pre-v0.1.14 behavior unchanged.

    Its "scheduled"/"charging" phases add energy the same way the low
    charge plan does (a per-unit rate over its own start_unit/end_unit).
    Its "holding" phase is different in kind, not just in when it applies:
    the system deliberately keeps the battery pinned at 100% for the
    balancing wait (`hold_start_unit`..`hold_end_unit`, see
    `compute_full_charge_plan`) rather than drawing it down by the usage
    forecast like every other hour - so those hours are pinned outright to
    `upper_limit_kwh` instead of receiving a delta.
    """
    full = full or {"active": False, "phase": None}
    charge_rate = low.get("effective_charge_per_unit", 0) if low.get("active") else 0
    discharge_rate = high.get("effective_discharge_per_unit", 0) if high.get("active") else 0
    hour0_start_unit = _hour0_start_unit(cur_unit, now)
    low_start = low.get("start_unit", 0) if low.get("active") else 0
    low_end = low.get("end_unit", 0) if low.get("active") else 0
    high_start = high.get("start_unit", 0) if high.get("active") else 0
    high_end = high.get("end_unit", 0) if high.get("active") else 0

    full_charging = full.get("active") and full.get("phase") in ("scheduled", "charging")
    full_charge_rate = full.get("effective_charge_per_unit", 0) if full_charging else 0
    full_start = full.get("start_unit", 0) if full_charging else 0
    full_end = full.get("end_unit", 0) if full_charging else 0

    full_holding = full.get("active") and full.get("phase") == "holding"
    hold_start = full.get("hold_start_unit", 0) if full_holding else 0
    hold_end = full.get("hold_end_unit", 0) if full_holding else 0

    values: list[float] = []
    delta = 0.0
    for h in range(len(base)):
        hour_start = hour0_start_unit + (h * 4)
        hour_end = hour_start + 4
        charge_overlap = max(min(hour_end, low_end) - max(hour_start, low_start), 0)
        discharge_overlap = max(min(hour_end, high_end) - max(hour_start, high_start), 0)
        full_overlap = max(min(hour_end, full_end) - max(hour_start, full_start), 0)
        delta += (charge_overlap * charge_rate) - (discharge_overlap * discharge_rate) + (full_overlap * full_charge_rate)
        value = base[h] + delta
        hold_overlap = max(min(hour_end, hold_end) - max(hour_start, hold_start), 0)
        if hold_overlap > 0:
            value = upper_limit_kwh
        values.append(round(value, 2))
    return values


# ---------------------------------------------------------------------------
# Full charge plan
# ---------------------------------------------------------------------------
def compute_full_charge_plan(
    prev: Optional[dict],
    cur_unit: int,
    now: datetime,
    interval_days: float,
    time_since_days: float,
    soc_now_percent: float,
    max_hold_minutes: float,
    voltage_diff: Optional[float],
    battery_now_kwh: float,
    upper_limit_kwh: float,
    usage: list[float],
    charge_speed_kw: float,
    all_price: list[float],
    balance_threshold: float = 10.0,
) -> dict:
    prev = prev or {"active": False, "phase": None}
    is_full = soc_now_percent >= 99.5
    voltage_diff = voltage_diff if voltage_diff is not None else 999.0

    def _start_holding() -> dict:
        # hold_start_unit/hold_end_unit exist purely for display/forecast
        # purposes (compose_forecast_adjusted pins the battery forecast at
        # 100% across this range, since the system deliberately holds the
        # setpoint there while waiting for the cells to balance) - the
        # actual end of holding is still decided live, by voltage_diff or
        # the max_hold_minutes timeout above, not by this estimate.
        hold_units = max(math.ceil(max_hold_minutes / 15), 1)
        return {
            "active": True,
            "phase": "holding",
            "hold_start": now.isoformat(),
            "hold_start_unit": cur_unit,
            "hold_end_unit": cur_unit + hold_units,
        }

    if prev.get("active") and prev.get("phase") == "holding":
        hold_start = datetime.fromisoformat(prev["hold_start"])
        hold_minutes = round((now - hold_start).total_seconds() / 60, 1)
        if is_full and voltage_diff < balance_threshold:
            return {"active": False, "phase": None}
        if hold_minutes >= max_hold_minutes:
            return {"active": False, "phase": None, "timed_out": True}
        return {
            "active": True,
            "phase": "holding",
            "hold_start": prev["hold_start"],
            "hold_minutes": hold_minutes,
            "hold_start_unit": prev.get("hold_start_unit", cur_unit),
            "hold_end_unit": prev.get("hold_end_unit", cur_unit),
        }

    if prev.get("active") and prev.get("phase") == "charging":
        if is_full:
            return _start_holding()
        if cur_unit < prev.get("end_unit", -1):
            return prev
        # This session's window ran out without reaching full - a real
        # possibility now that a single session's energy is capped (see
        # session_cap_kwh below), for chargers too slow to finish in one
        # window. Stop here and fall through to search for a fresh window
        # below, instead of holding the setpoint on indefinitely regardless
        # of price. time_since_days only resets once is_full genuinely
        # fires, so it's still "due" on the very next cycle and immediately
        # re-plans against the reduced deficit left over from this
        # session's partial charge - this is what actually spreads a
        # too-big-for-one-window full charge across multiple days/sessions,
        # each picking whatever's cheapest when it runs.

    if (
        prev.get("active")
        and prev.get("phase") == "scheduled"
        and prev.get("start_unit", -1) <= cur_unit < prev.get("end_unit", -1)
    ):
        return {
            "active": True,
            "phase": "charging",
            "target_kwh": prev["target_kwh"],
            "deficit_kwh": prev["deficit_kwh"],
            "hold_hour_usage_kwh": prev["hold_hour_usage_kwh"],
            "session_cap_kwh": prev.get("session_cap_kwh", 0.0),
            "effective_charge_per_unit": prev["effective_charge_per_unit"],
            "units_needed": prev["units_needed"],
            "start_unit": prev["start_unit"],
            "end_unit": prev["end_unit"],
        }

    due = time_since_days >= interval_days
    if not due:
        return {"active": False, "phase": None}
    if is_full:
        return _start_holding()

    deficit = round(upper_limit_kwh - battery_now_kwh, 3)
    hold_hour_usage = float(usage[0]) if usage else 0.0
    target_kwh = round(deficit + hold_hour_usage, 3)

    # Cap a single session's energy commitment at 30x the home's own
    # average hourly consumption over the forecasted next 5 days (120
    # hours of the usage forecast) - the same "N-hour-average-equivalent
    # session cap" pattern used on the houseboat charge system. Without
    # this, a large deficit combined with a slow charge_speed_kw produces
    # one very long single window (see compute_full_charge_plan's docs);
    # capping it here, combined with the "charging" phase now expiring at
    # end_unit above instead of running indefinitely, is what actually lets
    # a too-big charge spread across multiple days/sessions instead of one
    # long straight run regardless of price.
    #
    # The cap is then floored at a 4-hour minimum window, expressed in kWh
    # via this session's own charge_speed_kw (min_session_kwh = 4 hours of
    # charging at this charger's speed). This is what makes charge speed a
    # factor in whether the cap ever actually binds: a fast charger (e.g.
    # 10 kW) reaches its 4-hour floor at 40 kWh - typically above what any
    # single session would need anyway, so the cap is effectively a no-op
    # and is_full remains the real backstop. A slow charger (e.g. 1.8 kW)
    # reaches its 4-hour floor at only 7.2 kWh, so the usage-based cap
    # still applies and can meaningfully spread a large deficit across
    # multiple days. If the usage-based cap already implies more than 4
    # hours at this charge speed, it's left unchanged - the floor only
    # raises a cap that would otherwise be shorter than 4 hours, never
    # shortens one that's already longer.
    horizon_hours = min(120, len(usage))
    avg_hourly_usage_5d = sum(usage[:horizon_hours]) / horizon_hours if horizon_hours > 0 else 0.0
    session_cap_kwh = round(avg_hourly_usage_5d * 30, 3)
    min_session_kwh = round(charge_speed_kw * 4, 3)
    session_cap_kwh = max(session_cap_kwh, min_session_kwh)
    if session_cap_kwh > 0:
        target_kwh = min(target_kwh, session_cap_kwh)

    charge_per_unit = charge_speed_kw / 4
    avg_usage_per_unit = hold_hour_usage / 4
    effective_charge_per_unit = max(charge_per_unit - avg_usage_per_unit, 0.1)
    units_needed = max(math.ceil(target_kwh / effective_charge_per_unit), 1)

    # The session cap (above) exists to keep the *initial* window search
    # from having to reach into meaningfully pricier hours just to fit a
    # large deficit's units_needed into one sitting - a small, cheap
    # units_needed-sized window is the point, not an artificially short
    # one. The flat-price extension below is a separate, narrower
    # decision: it only ever grows the window into neighboring units that
    # are still within the same 8%/EUR 0.02 tolerance of this window's own
    # average price (see _extend_flat_price_window), i.e. genuinely flat,
    # still-cheap territory - never into "the expensive part". Since it
    # can't do that, extending a capped session is safe by construction:
    # if a long flat-cheap valley happens to be available right where this
    # session landed, using more of it (and delivering correspondingly
    # more energy while the price is still just as good) is a win, not a
    # regression on the cap's purpose. Applies uniformly regardless of
    # whether this session's target was actually capped.
    search_end = len(all_price)
    best_start = _best_price_window(all_price, cur_unit, search_end, units_needed, cheapest=True)
    start_unit, end_unit = _extend_flat_price_window(all_price, best_start, best_start + units_needed, min_start=cur_unit)

    return {
        "active": True,
        "phase": "scheduled",
        "target_kwh": target_kwh,
        "deficit_kwh": deficit,
        "hold_hour_usage_kwh": round(hold_hour_usage, 3),
        "session_cap_kwh": session_cap_kwh,
        "effective_charge_per_unit": round(effective_charge_per_unit, 4),
        "units_needed": units_needed,
        "start_unit": start_unit,
        "end_unit": end_unit,
    }


# ---------------------------------------------------------------------------
# system_status
# ---------------------------------------------------------------------------
def compute_system_status(
    setpoint_w: float,
    idle_setpoint_w: float,
    cur_unit: int,
    full: dict,
    neg: dict,
    spike: dict,
    low: dict,
    high: dict,
    battery_now_kwh: float,
    low_threshold_kwh: float,
    charge_speed_kw: float,
    discharge_speed_kw: float,
    all_price: list[float],
) -> str:
    is_idle = abs(setpoint_w - idle_setpoint_w) < 50
    near_low_limit = (battery_now_kwh - low_threshold_kwh) <= 1
    charge_engaged_at = charge_speed_kw * 1000 * 0.5
    discharge_engaged_at = discharge_speed_kw * 1000 * 0.5

    price_now = all_price[cur_unit] if cur_unit < len(all_price) else 0
    high_breach_unit = high.get("breach_unit", 999999)
    price_at_breach = all_price[high_breach_unit] if high.get("active") and high_breach_unit < len(all_price) else 0
    same_day_breach = high.get("active") and high_breach_unit < 96
    export_favorable = high.get("active") and price_now > price_at_breach

    if full.get("active") and full.get("phase") in ("charging", "holding"):
        if full.get("phase") == "charging":
            return "Actief" if setpoint_w >= charge_engaged_at else "Start charge"
        return "Balancing" if setpoint_w >= charge_engaged_at else "Start charge"

    if full.get("active") and full.get("phase") == "scheduled":
        return "Full charge scheduled"

    if neg.get("active") and cur_unit < neg.get("charge_end_unit", -1):
        if neg["charge_start_unit"] <= cur_unit < neg["charge_end_unit"]:
            return "Negative price charge" if setpoint_w >= charge_engaged_at else "Start negative price charge"
        if neg["discharge_start_unit"] <= cur_unit < neg["discharge_end_unit"]:
            return "Actief" if setpoint_w <= -discharge_engaged_at else "Start discharge"
        if neg["solar_export_start_unit"] <= cur_unit < neg["solar_export_end_unit"]:
            return "Solar export"
        return "Standby"

    if spike.get("active") and cur_unit < spike.get("discharge_end_unit", -1):
        if spike["charge_start_unit"] <= cur_unit < spike["charge_end_unit"]:
            return "Actief" if setpoint_w >= charge_engaged_at else "Start charge"
        if cur_unit >= spike["discharge_start_unit"]:
            return "Spike discharge" if setpoint_w <= -discharge_engaged_at else "Start spike discharge"
        return "Standby"

    if low.get("active") and (not high.get("active") or low.get("breach_unit", 999999) <= high.get("breach_unit", 999999)):
        if low["start_unit"] <= cur_unit < low["end_unit"]:
            return "Actief" if setpoint_w >= charge_engaged_at else "Start charge"
        if cur_unit >= low["end_unit"] and not is_idle:
            return "Stop"
        if cur_unit < low["start_unit"] and near_low_limit:
            return "Grid usage"
        return "Standby"

    if high.get("active"):
        if high["start_unit"] <= cur_unit < high["end_unit"]:
            return "Actief" if setpoint_w <= -discharge_engaged_at else "Start discharge"
        if cur_unit >= high["end_unit"] and not is_idle:
            return "Stop"
        if cur_unit < high["start_unit"] and near_low_limit and same_day_breach and export_favorable:
            return "Solar export"
        return "Standby"

    return "Stop" if not is_idle else "Standby"
