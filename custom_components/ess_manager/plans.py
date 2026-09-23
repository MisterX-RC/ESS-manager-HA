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
    max_end: Optional[int] = None,
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
    backward past the current unit (can't charge in the past). `max_end`
    is an optional deadline - when set, the rightward extension won't grow
    past it (e.g. a forecasted peak the window needs to finish by); left
    at None (the default) there's no forward bound beyond the price
    array's own length, same as before this parameter existed.
    """
    while start > min_start:
        window_avg = sum(prices[start:end]) / (end - start)
        diff = abs(prices[start - 1] - window_avg)
        if diff <= tolerance_absolute or (window_avg > 0 and diff / window_avg <= tolerance_relative):
            start -= 1
        else:
            break
    while end < len(prices) and (max_end is None or end < max_end):
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
    minimum_charge_target_kwh: float,
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
    # Unlike the low charge plan - where minimum_charge_target_kwh raises the
    # *target level* it charges up to, so the plan never bothers charging to
    # just barely above low_threshold_kwh - the spike plan's target is
    # already the top of the battery (charge_target_level, above), so
    # there's no floor to raise. The equivalent, and what was actually asked
    # for, is a floor on whether the resulting top-up is worth doing at all:
    # a forecasted gap smaller than minimum_charge_target_kwh is treated as
    # "close enough to full," so no charge window is scheduled and nothing
    # shows up on the charge sensors for it (Timo's reported case: a 1.16
    # kWh top-up scheduled purely to counteract a small forecasted dip
    # before the day's price peak).
    if charge_needed_kwh < minimum_charge_target_kwh:
        charge_needed_kwh = 0.0

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
    battery_now_kwh: float,
) -> dict:
    prev = prev or {"active": False}
    if prev.get("active") and prev.get("start_unit", -1) <= cur_unit < prev.get("end_unit", -1):
        # Live-target early stop (Timo's proposal): the window's own length
        # (units_needed, below) is always rounded UP to a whole 15-minute
        # unit at the full configured charge rate, so a small target_kwh
        # can finish well before the unit's 15 minutes are up - continuing
        # to command the full rate for the rest of the window overshoots
        # past what was actually needed. target_energy_kwh (set once below,
        # the moment this window was found - which, since this function
        # keeps re-searching fresh every cycle right up until start_unit
        # actually arrives, is always genuinely "now") gives
        # compute_system_status a second stop condition alongside the
        # existing end_unit timeout: whichever comes first. Once reached,
        # target_reached latches permanently for the rest of this window
        # (checked here, not recomputed live in compute_system_status)
        # specifically so a brief post-stop dip in the setpoint readback
        # can never flip it back to "Actief"/"Start charge" and restart
        # the session - see the same reasoning in compute_high_discharge_plan.
        if not prev.get("target_reached") and battery_now_kwh >= prev.get("target_energy_kwh", float("inf")):
            updated = dict(prev)
            updated["target_reached"] = True
            return updated
        return prev

    forecast = forecast_with_spike[0 : planning_horizon_hours + 1]
    charge_per_unit = charge_speed_kw / 4

    hour_index = None
    for h in range(len(forecast)):
        if forecast[h] < low_threshold_kwh:
            hour_index = h
            break

    if hour_index is None:
        return {"active": False, "breach_unit": 999999}

    # Size the charge against the LOWEST point of this dip, not the first
    # hour it crosses below the threshold. The forecast usually keeps falling
    # for hours after that first crossing (evening/night usage with no
    # solar), so topping up only to cover the first-crossing hour leaves the
    # battery short again a few hours later. Live report: first crossing
    # 2.89 kWh (-> a 0.11 kWh "charge"), but the same dip kept falling to
    # -0.38 kWh five hours later, before solar recovered it - the real
    # shortfall was 3.38 kWh. The dip ends where the forecast climbs back
    # to the threshold (or at the end of the horizon); a later, separate dip
    # gets its own plan once this one is behind us. breach_unit (the
    # deadline) still comes from the FIRST crossing - the charge has to be
    # in before the battery first runs short. (The original template sensor
    # had this same first-crossing-only sizing; it was ported as-is.)
    dip_end = len(forecast)
    for h in range(hour_index + 1, len(forecast)):
        if forecast[h] >= low_threshold_kwh:
            dip_end = h
            break
    value = min(forecast[hour_index:dip_end])

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
        "dip_min_kwh": round(value, 3),
        "target_kwh": target_kwh,
        "avg_home_load_kw": round(avg_usage_kwh, 3),
        "effective_charge_per_unit": round(effective_charge_per_unit, 4),
        "units_needed": units_needed,
        "breach_unit": breach_unit,
        "start_unit": best_start,
        "end_unit": best_start + units_needed,
        # See the live-target early-stop comment above: computed here,
        # every single fresh (non-echoed) cycle, using whatever
        # battery_now_kwh genuinely is *right now* - and since this
        # function keeps recomputing fresh every cycle until cur_unit
        # actually reaches start_unit (only then does the echo branch
        # above start firing), the LAST fresh computation before that
        # happens always has start_unit == cur_unit, so battery_now_kwh
        # here is already accurate for "right as the window begins," with
        # no separate re-anchoring step needed.
        "target_energy_kwh": round(battery_now_kwh + target_kwh, 3),
        "target_reached": False,
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
    battery_now_kwh: float,
    suppress_new: bool = False,
    minimum_charge_target_kwh: float = 0.0,
) -> dict:
    """`minimum_charge_target_kwh` raises the lowest level a sale may leave
    the battery at: a sale is capped so the forecast never drops below
    max(low_threshold_kwh, minimum_charge_target_kwh) after it - the same
    level the low charge plan tops the battery back up to. Selling right
    down to the bare low threshold (the old behavior, and still what a
    default of 0.0 gives) means any forecast error - a bit more evening
    usage, a bit less morning solar - pushes the battery under the
    threshold and makes the low charge plan buy energy back, possibly
    energy it just sold.

    `suppress_new` blocks scheduling a brand-new discharge window - used
    when the full-charge plan is relying on a future solar peak (or is
    actively charging/holding) to reach/hold the same high_threshold_kwh
    ceiling this function would otherwise sell surplus down from. This
    plan's own peak-scan only looks `planning_horizon_hours` ahead (a few
    days by default) and has no idea the full-charge plan exists, so
    without this it could sell off exactly the surplus energy a much
    longer-horizon full-charge peak-scan (compute_full_charge_plan, which
    scans the whole ~5-day forecast) is counting on to reach that peak for
    free - see coordinator.py for how the two are wired together. Checked
    *after* the lock-in check below, so a discharge window already in
    progress finishes normally rather than being cut off mid-window; only
    scheduling a *new* one is blocked. Left at its default (False), nothing
    changes from before this parameter existed.
    """
    prev = prev or {"active": False}
    if prev.get("active") and prev.get("start_unit", -1) <= cur_unit < prev.get("end_unit", -1):
        # Live-target early stop (Timo's proposal, mirroring
        # compute_low_charge_plan above): units_needed is always rounded UP
        # to a whole 15-minute unit at the full configured discharge rate,
        # so a small surplus (e.g. a live report: 0.96 kWh target against a
        # 10kW discharge speed) finishes well before the unit's 15 minutes
        # are up, and continuing to discharge at full rate for the rest of
        # the window sells off far more stored energy than the surplus
        # calculation ever called for. target_energy_kwh (set once below,
        # always genuinely "now" for the same reason described in
        # compute_low_charge_plan) gives compute_system_status a second
        # stop condition alongside the existing end_unit timeout - whichever
        # comes first. target_reached latches permanently once crossed, so
        # a setpoint readback dip right after stopping can't flip this back
        # to "Actief"/"Start discharge" and reopen the session.
        if not prev.get("target_reached") and battery_now_kwh <= prev.get("target_energy_kwh", float("-inf")):
            updated = dict(prev)
            updated["target_reached"] = True
            return updated
        return prev
    if suppress_new:
        return {"active": False, "breach_unit": 999999, "suppressed_by_full_charge": True}

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
    if raw_surplus <= 0:
        return {"active": False, "breach_unit": 999999}

    relevant_usage = usage[0 : hour_index + 1]
    avg_usage_kwh = sum(relevant_usage) / len(relevant_usage) if relevant_usage else 0
    avg_usage_per_unit = avg_usage_kwh / 4
    effective_discharge_per_unit = discharge_per_unit + avg_usage_per_unit
    search_end = min(breach_unit, len(all_price))
    hour0_unit = _hour0_start_unit(cur_unit, now)
    sale_floor_kwh = max(low_threshold_kwh, minimum_charge_target_kwh)

    # Safety cap, based on WHERE the sale actually lands: the battery may not
    # be forecast to drop below sale_floor_kwh (the higher of the low
    # threshold and the Minimum charge target) after the sale. Selling
    # energy lowers the battery for every hour from the sale onward, never
    # for hours before it - so only low points from the sale's own hour
    # onward can be pushed under the floor by it. (Previously
    # the cap used the lowest point anywhere in the horizon: a live report
    # had it capped at 0.84 kWh because of a 05:00 low point, while the sale
    # itself was scheduled for 19:45 that evening - long after that low
    # point - and the lowest point after the sale left room for the full
    # 1.79 kWh surplus.) Everything after the sale up to the end of the
    # horizon is still checked, including after the peak: with a max SOC
    # below 100% the peak isn't clipped, so the sold energy really is
    # missing from every later hour too.
    #
    # Size and placement depend on each other (the amount sets how many
    # units the window needs, the window sets which low points count), so
    # start from the full surplus and only ever shrink it until the window
    # it lands in is safe - a few rounds at most.
    def _size_from(search_start: int) -> Optional[tuple[float, int, int, float]]:
        amount = raw_surplus
        low_point = None
        for _ in range(6):
            units = max(math.ceil(amount / effective_discharge_per_unit), 1)
            start = _best_price_window(all_price, search_start, search_end, units, cheapest=False)
            sale_hour = min(max((start - hour0_unit) // 4, 0), len(forecast) - 1)
            low_point = min(forecast[sale_hour:])
            capped = round(min(amount, low_point - sale_floor_kwh), 3)
            if capped <= 0:
                return None
            if capped >= amount:
                return amount, units, start, low_point
            amount = capped
        units = max(math.ceil(amount / effective_discharge_per_unit), 1)
        start = _best_price_window(all_price, search_start, search_end, units, cheapest=False)
        return amount, units, start, low_point

    best = _size_from(cur_unit)
    # If the best-priced window lands before a low point that caps (or
    # blocks) the sale, also try selling only after the lowest point before
    # the breach - a slightly cheaper slot that can sell more (or at all)
    # can be worth more than an expensive slot that has to sell less.
    if best is None or best[0] < raw_surplus:
        pre_breach = forecast[0 : hour_index + 1]
        low_h = pre_breach.index(min(pre_breach))
        after_low_start = hour0_unit + (low_h + 1) * 4
        if cur_unit < after_low_start < search_end:
            alt = _size_from(after_low_start)
            if alt is not None and (best is None or alt[0] > best[0]):
                best = alt
    if best is None:
        return {"active": False, "breach_unit": 999999}
    surplus, units_needed, best_start, low_point_after_sale = best

    return {
        "active": True,
        "surplus_kwh": surplus,
        "target_kwh": surplus,
        "avg_home_load_kw": round(avg_usage_kwh, 3),
        "effective_discharge_per_unit": round(effective_discharge_per_unit, 4),
        "capped_by_low_limit": surplus < raw_surplus,
        "low_point_after_sale_kwh": round(low_point_after_sale, 3),
        "sale_floor_kwh": round(sale_floor_kwh, 3),
        "breach_unit": breach_unit,
        "start_unit": best_start,
        "end_unit": best_start + units_needed,
        "units_needed": units_needed,
        "target_energy_kwh": round(battery_now_kwh - surplus, 3),
        "target_reached": False,
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

    The low/high plans' own rates are deliberately NOT their
    `effective_charge_per_unit`/`effective_discharge_per_unit` fields -
    those are the full configured rate for a WHOLE 15-minute unit, and
    since `units_needed` always rounds up to at least one whole unit
    (see commit 38/39's overshoot notes in plans.py), that rate times the
    window length is usually MORE than the plan's own genuine
    `target_kwh`. As of commit 39 the real hardware stops early once
    `target_energy_kwh` is reached, so charting the full per-unit rate
    for the whole window paints a deeper swing than what actually
    happens (a live report: a 0.09 kWh discharge target showed up here
    as a ~2.72 kWh drop, an apparent - but not real - undershoot).
    Deriving the rate from `target_kwh` spread evenly over the plan's own
    committed window instead means the total delta by the window's own
    end always equals the plan's real, intended amount, matching the
    live target-energy stop. `compute_full_charge_plan` is unaffected -
    it doesn't have this floor-rounding overshoot (it stops on live SOC,
    not a per-unit target), so its own rate is left as-is.
    """
    full = full or {"active": False, "phase": None}
    low_window_units = max(low.get("end_unit", 0) - low.get("start_unit", 0), 0) if low.get("active") else 0
    charge_rate = (low.get("target_kwh", 0) / low_window_units) if low_window_units > 0 else 0
    high_window_units = max(high.get("end_unit", 0) - high.get("start_unit", 0), 0) if high.get("active") else 0
    discharge_rate = (high.get("target_kwh", 0) / high_window_units) if high_window_units > 0 else 0
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
    high_threshold_kwh: float,
    usage: list[float],
    charge_speed_kw: float,
    all_price: list[float],
    battery_forecast: list[float],
    battery_voltage: Optional[float],
    target_voltage: float,
    balance_threshold: float = 10.0,
) -> dict:
    prev = prev or {"active": False, "phase": None}
    is_full = soc_now_percent >= 99.5
    voltage_diff = voltage_diff if voltage_diff is not None else 999.0

    # Third confirmation leg, on top of SOC and the cell voltage
    # differential above: the battery pack's own measured voltage must
    # also have reached its configured full-charge target, minus a small
    # margin (chasing the exact figure to the millivolt is neither
    # realistic nor useful). A missing reading is treated the same
    # conservative way as a missing voltage_diff reading - assume it
    # hasn't been reached yet, never assume it has.
    VOLTAGE_MARGIN = 0.1
    voltage_at_target = battery_voltage is not None and battery_voltage >= (target_voltage - VOLTAGE_MARGIN)
    balance_confirmed_now = is_full and voltage_diff < balance_threshold and voltage_at_target

    # Entering the holding phase, separately, is triggered by *either* of
    # two independent signals - SOC reaching 99.5% (is_full, above) or the
    # battery pack's own measured voltage getting within 1.0V of its
    # configured full-charge target - so a problem with one doesn't block
    # the other. SOC on most BMS/inverter setups is coulomb-counted and can
    # drift over days/weeks (Timo's own report: "sometimes the SOC
    # drifts"); pack voltage is a second, independent way to notice a
    # genuinely full battery even if SOC under- or over-reports. This
    # margin (1.0V) is deliberately much looser than VOLTAGE_MARGIN above
    # (0.1V) - it only needs to catch "the pack is essentially full", not to
    # confirm balance by itself. Deliberately kept separate from `is_full`
    # itself (rather than folded into it) so it can never loosen
    # balance_confirmed_now above: that still requires genuine SOC>=99.5%,
    # since resetting the "days since last full charge" clock on voltage
    # alone - without SOC ever actually confirming full - would be a much
    # bigger, less reversible claim than just deciding it's time to stop
    # pushing more energy in and start holding/watching for balance.
    FULL_VOLTAGE_TRIGGER_MARGIN = 1.0
    voltage_near_full = battery_voltage is not None and battery_voltage >= (target_voltage - FULL_VOLTAGE_TRIGGER_MARGIN)
    should_enter_holding = is_full or voltage_near_full

    # Once a holding attempt times out without ever confirming balance,
    # `retry_after_timeout` carries the instruction "don't shortcut
    # straight back into holding just because SOC still happens to be
    # >=99.5%" forward through every subsequent fresh (phase=None)
    # recomputation - whether that lands back in a quiet wait for a future
    # solar peak or a freshly scheduled grid session - until either a real
    # charging session's own completion earns a clean new attempt (that
    # transition doesn't consult this flag at all), or the interval
    # genuinely resets via balance_confirmed_now succeeding elsewhere.
    retry_after_timeout = bool(prev.get("retry_after_timeout"))

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
        if balance_confirmed_now:
            return {"active": False, "phase": None, "balance_confirmed": True}
        if hold_minutes >= max_hold_minutes:
            # Don't force anything further, and don't let the very next
            # fresh evaluation immediately re-enter holding just because
            # SOC still happens to be >=99.5% - defer to the same
            # forward-looking logic used before any charge was ever
            # forced (below): if solar is still expected to carry the
            # battery to a genuine future overshoot, quietly wait for it
            # (still passively checking for balance meanwhile, same as
            # the "not due" path); if not, let the charging logic pick a
            # fresh cheapest window instead. See retry_after_timeout above.
            return {"active": False, "phase": None, "timed_out": True, "retry_after_timeout": True}
        return {
            "active": True,
            "phase": "holding",
            "hold_start": prev["hold_start"],
            "hold_minutes": hold_minutes,
            "hold_start_unit": prev.get("hold_start_unit", cur_unit),
            "hold_end_unit": prev.get("hold_end_unit", cur_unit),
        }

    if prev.get("active") and prev.get("phase") == "charging":
        if should_enter_holding:
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
            "anchor_kwh": prev.get("anchor_kwh", battery_now_kwh),
            "anchor_unit": prev.get("anchor_unit", prev["start_unit"]),
            "peak_kwh": prev.get("peak_kwh", battery_now_kwh),
        }

    due = time_since_days >= interval_days

    if not due:
        # Passive balance confirmation: even with nothing due, if the
        # battery happens to be sitting genuinely full (solar, most
        # commonly) and already satisfies all three confirmation legs,
        # that's a perfectly good, unforced full+balanced cycle - checked
        # quietly every cycle regardless of `due`, so the caller
        # (coordinator.py) can reset the "days since last full charge"
        # clock without ever entering an active plan or forcing a
        # setpoint. If it never gets there before SOC drops back below
        # 99.5% again, nothing happens - the interval keeps counting
        # toward becoming genuinely due, same as always.
        return {"active": False, "phase": None, "balance_confirmed": balance_confirmed_now}

    if should_enter_holding and not retry_after_timeout:
        return _start_holding()

    # Don't necessarily base the deficit on right now. battery_forecast is
    # an *uncapped* running projection (solar minus usage, no clipping at
    # the battery's real capacity - see forecasting.build_battery_forecast)
    # - find its highest point anywhere in the forecast horizon. If that
    # peak is genuinely in the future (solar expected to raise the battery
    # further before it's needed), there's no point buying grid energy for
    # a gap solar will close for free - anchor the deficit to that peak's
    # own forecasted level instead of today's. The purchased top-up must
    # then be scheduled to *finish by* that peak, not after it: by the time
    # the peak has already passed, the optimal window - where a grid
    # top-up combines with solar's still-rising contribution - is gone, and
    # buying afterwards only fights the declining tail on the far side.
    # `anchor_unit` is therefore used as a deadline (search_end), mirroring
    # the breach_unit deadline pattern already used by
    # compute_low_charge_plan/compute_high_discharge_plan, not as a floor.
    peak_hour_index = 0
    peak_kwh = battery_now_kwh
    for h, level in enumerate(battery_forecast):
        if level is not None and level > peak_kwh:
            peak_kwh = level
            peak_hour_index = h
    hour0_start_unit = _hour0_start_unit(cur_unit, now)

    if peak_hour_index > 0:
        anchor_kwh = peak_kwh
        anchor_unit = hour0_start_unit + (peak_hour_index * 4)
        search_start = cur_unit
        search_end = min(anchor_unit, len(all_price))
    else:
        # No meaningful future rise forecast (e.g. no solar) - today's
        # level effectively already IS the peak. Rather than anchoring to
        # right now, find where the cheapest window would actually land
        # (sized off today's level, purely as a first-pass estimate of a
        # plausible window length) and use the battery's own forecasted
        # level at THAT point instead - ordinary usage between now and
        # then still moves the number even with no solar to speak of.
        prelim_deficit = round(high_threshold_kwh - battery_now_kwh, 3)
        prelim_hold_usage = float(usage[0]) if usage else 0.0
        prelim_target = max(round(prelim_deficit + prelim_hold_usage, 3), 0.0)
        prelim_effective = max((charge_speed_kw / 4) - (prelim_hold_usage / 4), 0.1)
        prelim_units = max(math.ceil(prelim_target / prelim_effective), 1)
        prelim_start = _best_price_window(all_price, cur_unit, len(all_price), prelim_units, cheapest=True)
        prelim_hour_index = min(max((prelim_start - cur_unit) // 4, 0), len(battery_forecast) - 1) if battery_forecast else 0
        anchor_kwh = battery_forecast[prelim_hour_index] if battery_forecast else battery_now_kwh
        anchor_unit = hour0_start_unit + (prelim_hour_index * 4)
        search_start = cur_unit
        search_end = len(all_price)

    deficit = round(high_threshold_kwh - anchor_kwh, 3)
    if deficit <= 0:
        # The anchor point already reaches (or exceeds) the same max-SOC
        # overshoot ceiling used elsewhere for solar headroom - not just a
        # fleeting graze past 100%, but a real, sustained surplus. In
        # practice that means the real (capped) battery is expected to sit
        # pegged at its true 100% for a genuine stretch while the excess
        # gets curtailed/exported, which is long enough to finish the
        # cell-balancing hold on its own. Nothing to buy - live SOC
        # crossing 99.5% (is_full, above) will still drive the holding
        # phase exactly as it already does, for free.
        #
        # relying_on_peak_unit still flags which future hour this "solar
        # will handle it" conclusion depends on, even though there's no
        # active plan here for the discharge plan's own active/phase check
        # to notice. Without it, compute_high_discharge_plan (working off
        # its own, much shorter-horizon forecast) could sell exactly the
        # surplus this decision is counting on before it ever accumulates,
        # silently turning a "free" balance charge into one that never
        # actually happens - see coordinator.py's discharge-suppression
        # logic, which reads this field.
        return {
            "active": False,
            "phase": None,
            "relying_on_peak_unit": anchor_unit if peak_hour_index > 0 else None,
            "retry_after_timeout": retry_after_timeout,
        }

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
    best_start = _best_price_window(all_price, search_start, search_end, units_needed, cheapest=True)
    start_unit, end_unit = _extend_flat_price_window(
        all_price, best_start, best_start + units_needed, min_start=search_start, max_end=search_end
    )

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
        "anchor_kwh": round(anchor_kwh, 3),
        "anchor_unit": anchor_unit,
        "peak_kwh": round(peak_kwh, 3),
        # See the deficit<=0 branch above for why this exists: a genuine
        # future peak (peak_hour_index > 0) that this session's own target
        # is anchored to, so the discharge plan knows not to sell it off
        # before it happens. None for the no-future-rise (cheapest-window)
        # case, since there's no peak there to protect.
        "relying_on_peak_unit": anchor_unit if peak_hour_index > 0 else None,
        # A legitimate new charging session is starting here - carry the
        # flag forward unchanged (it isn't consulted again until the next
        # fresh phase=None evaluation), rather than clearing it, since
        # this path doesn't itself decide whether the retry restriction
        # is still needed.
        "retry_after_timeout": retry_after_timeout,
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
    status = _compute_system_status_raw(
        setpoint_w,
        idle_setpoint_w,
        cur_unit,
        full,
        neg,
        spike,
        low,
        high,
        battery_now_kwh,
        low_threshold_kwh,
        charge_speed_kw,
        discharge_speed_kw,
        all_price,
    )
    # The full-charge plan can quietly decide there's nothing to buy because
    # a genuine future solar peak will reach the overshoot ceiling on its
    # own (see compute_full_charge_plan's deficit<=0 "skip" branch) -
    # relying_on_peak_unit flags this even though full.active stays False,
    # since nothing is actually scheduled. Without surfacing it, the
    # entities card just shows plain "Standby" with no indication a full
    # charge is being planned around that peak at all. Only replaces a
    # genuine "Standby" (nothing else going on) - never overrides a real
    # in-progress action from another plan.
    if status == "Standby" and not full.get("active") and full.get("relying_on_peak_unit") is not None:
        return "Awaiting solar (full charge)"
    return status


def _compute_system_status_raw(
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
        # Holding: keep commanding a charge setpoint for the WHOLE hold,
        # regardless of what the setpoint readback shows. Solar alone can
        # already be holding the battery at 100% with zero grid setpoint
        # needed, in which case setpoint_w never ramps up - but "Start
        # charge" is precisely the signal the external automation reacts
        # to in order to keep enforcing a charge setpoint, so household
        # loads can't erode the SOC while waiting for the cells to
        # balance. "Balancing" was display-only and never an automation
        # trigger (see dashboard/automation_example.yaml), so nothing is
        # lost by retiring it here.
        return "Start charge"

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

    if spike.get("active"):
        if spike["charge_start_unit"] <= cur_unit < spike["charge_end_unit"]:
            return "Actief" if setpoint_w >= charge_engaged_at else "Start charge"
        if spike["discharge_start_unit"] <= cur_unit < spike["discharge_end_unit"]:
            return "Spike discharge" if setpoint_w <= -discharge_engaged_at else "Start spike discharge"
        # The spike plan stays "active" for its whole lifecycle, charge
        # phase through discharge phase (compute_spike_plan only clears it
        # once cur_unit reaches discharge_end_unit) - so once its own charge
        # window has passed (or, as here, was a zero-length/zero-kWh no-op
        # window) and its discharge window hasn't started yet, this must NOT
        # return "Standby" outright: that would mask a genuinely due low
        # charge plan sitting in that same gap, which is exactly this bug
        # class already fixed in display.charge_display (v0.1.30) and the
        # dashboard charts (v0.1.31) - just never carried over to this
        # function until now. Falling through (no return here) lets the low
        # charge plan below get its turn instead.

    if low.get("active") and (not high.get("active") or low.get("breach_unit", 999999) <= high.get("breach_unit", 999999)):
        if low["start_unit"] <= cur_unit < low["end_unit"]:
            # Live-target early stop: the window itself is sized in whole
            # 15-minute units at full charge rate, so a small target_kwh can
            # genuinely be delivered before the unit's 15 minutes are up -
            # target_reached (compute_low_charge_plan) latches the moment
            # battery_now_kwh crosses target_energy_kwh, stopping here
            # rather than riding out the rest of the window at full rate.
            if low.get("target_reached"):
                return "Stop"
            return "Actief" if setpoint_w >= charge_engaged_at else "Start charge"
        if cur_unit >= low["end_unit"] and not is_idle:
            return "Stop"
        if cur_unit < low["start_unit"] and near_low_limit:
            return "Grid usage"
        return "Standby"

    if high.get("active"):
        if high["start_unit"] <= cur_unit < high["end_unit"]:
            # Same live-target early stop as the low charge plan above,
            # mirrored for discharge - see compute_high_discharge_plan.
            if high.get("target_reached"):
                return "Stop"
            return "Actief" if setpoint_w <= -discharge_engaged_at else "Start discharge"
        if cur_unit >= high["end_unit"] and not is_idle:
            return "Stop"
        if cur_unit < high["start_unit"] and near_low_limit and same_day_breach and export_favorable:
            return "Solar export"
        return "Standby"

    return "Stop" if not is_idle else "Standby"
