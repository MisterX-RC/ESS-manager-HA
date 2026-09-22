"""Standalone sanity test for the ported pipeline (forecasting.py + plans.py
+ display.py) - no Home Assistant needed, mirrors the original project's
test_120h_pipeline.py / test_partial_hour.py validation approach.

Run with: python3 test_pipeline.py   (from the repo root)
"""
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta

# Load the pure-Python modules directly, bypassing custom_components/
# ess_manager/__init__.py (which imports Home Assistant itself and isn't
# available in this standalone test environment).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG_DIR = os.path.join(_REPO_ROOT, "custom_components", "ess_manager")
_pkg = types.ModuleType("ess_manager_pure")
_pkg.__path__ = [_PKG_DIR]
sys.modules["ess_manager_pure"] = _pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"ess_manager_pure.{name}", os.path.join(_PKG_DIR, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"ess_manager_pure.{name}"] = module
    spec.loader.exec_module(module)
    return module


_load("const")
forecasting = _load("forecasting")
plans = _load("plans")
display = _load("display")
usage_forecast = _load("usage_forecast")

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAILURES.append(label)
    print(f"[{status}] {label}")


# ---------------------------------------------------------------------------
# forecasting.py
# ---------------------------------------------------------------------------
now = datetime(2026, 9, 16, 14, 37, 0)
base_hour = now.replace(minute=0, second=0, microsecond=0)

solar_points = [
    {"period_start": (base_hour + timedelta(hours=h)).isoformat(), "pv_estimate": 1.5}
    for h in range(0, 48)
]
solar = forecasting.build_solar_forecast(solar_points, now, hours=121)
check("solar forecast is 121 long", len(solar) == 121)
check("solar[0] resolved from source data", solar[0] == 1.5)
check("solar[120] is None (no source data that far out)", solar[120] is None)

usage_attrs = {f"h{h}": 1.0 for h in range(0, 121)}
usage = forecasting.build_usage_forecast(usage_attrs, hours=121)
check("usage forecast is 121 long", len(usage) == 121)
check("usage[0] == 1.0", usage[0] == 1.0)

net = forecasting.build_net_energy(solar, usage)
check("net energy length matches solar length", len(net) == len(solar))
check("net[0] == solar[0] - usage[0]", net[0] == round(1.5 - 1.0, 3))
check("net[120] treats missing solar as 0", net[120] == round(0 - 1.0, 3))

# Partial-hour compensation: at minute=37, fraction_remaining = 23/60
start_kwh = 15.0
battery_forecast = forecasting.build_battery_forecast(net, start_kwh, now)
fraction_remaining = (60 - now.minute) / 60
expected_h0 = round(start_kwh + net[0] * fraction_remaining, 2)
check("battery_forecast[0] applies partial-hour scaling", battery_forecast[0] == expected_h0)
expected_h1 = round(expected_h0 + net[1], 2)
check("battery_forecast[1] is a full, unscaled hour", battery_forecast[1] == expected_h1)

# minute=0 must exactly reproduce the unscaled (no-op) case
now_top_of_hour = datetime(2026, 9, 16, 14, 0, 0)
battery_forecast_top = forecasting.build_battery_forecast(net, start_kwh, now_top_of_hour)
check(
    "at minute=0, partial-hour scaling is a no-op",
    battery_forecast_top[0] == round(start_kwh + net[0], 2),
)

# build_battery_forecast's optional max_charge_kw/max_discharge_kw - the
# battery's own physical power limit, distinct from the grid-charge-speed
# tunables used by the planning engines. h0: solar surplus of 8 kWh (would
# charge faster than a 5 kW physical limit); h1: usage deficit of 6 kWh
# (would discharge faster than a 3 kW physical limit); h2/h3 stay within
# both limits and should be completely unaffected.
cap_net = [8.0, -6.0, 2.0, -1.0]
cap_start = 10.0
uncapped_cap_forecast = forecasting.build_battery_forecast(cap_net, cap_start, now_top_of_hour)
capped_forecast = forecasting.build_battery_forecast(
    cap_net, cap_start, now_top_of_hour, max_charge_kw=5.0, max_discharge_kw=3.0
)
check(
    "build_battery_forecast without a cap follows the raw solar/usage net exactly",
    uncapped_cap_forecast == [18.0, 12.0, 14.0, 13.0],
)
check(
    "build_battery_forecast's max_charge_kw clamps an hour's charge to the battery's physical limit",
    capped_forecast[0] == round(cap_start + 5.0, 2),
)
check(
    "build_battery_forecast's max_discharge_kw clamps an hour's discharge to the battery's physical limit",
    capped_forecast[1] == round(capped_forecast[0] - 3.0, 2),
)
check(
    "build_battery_forecast's caps don't affect hours already within both limits",
    capped_forecast[2] == round(capped_forecast[1] + 2.0, 2) and capped_forecast[3] == round(capped_forecast[2] - 1.0, 2),
)

# The cap applies to the full-hour-equivalent rate before the partial-hour
# scaling, not after - at minute=37 (fraction_remaining = 23/60), the
# clamped-to-5kW h0 should scale by that fraction, not the raw 8kW.
now_partial = datetime(2026, 9, 16, 14, 37, 0)
capped_partial = forecasting.build_battery_forecast(
    cap_net, cap_start, now_partial, max_charge_kw=5.0, max_discharge_kw=3.0
)
partial_fraction = (60 - 37) / 60
check(
    "build_battery_forecast applies the charge/discharge cap before partial-hour scaling, not after",
    capped_partial[0] == round(cap_start + 5.0 * partial_fraction, 2),
)

# ---------------------------------------------------------------------------
# plans.py - low charge plan / high discharge plan basic breach detection
# ---------------------------------------------------------------------------
# Build a synthetic forecast that dips below the low threshold at hour 5,
# and a flat price curve so the cheapest-window search is well-defined.
synthetic_forecast = [10.0] * 5 + [2.0] * 20  # breaches low_threshold=3.0 at h=5
all_price = [0.30] * 40 + [0.10] * 20 + [0.30] * 40  # cheap window units 40-59
usage_flat = [1.0] * 121

low_plan = plans.compute_low_charge_plan(
    None,
    cur_unit=0,
    forecast_with_spike=synthetic_forecast,
    now=now_top_of_hour,
    charge_speed_kw=7.0,
    low_threshold_kwh=3.0,
    minimum_charge_target_kwh=5.0,
    upper_limit_kwh=30.0,
    usage=usage_flat,
    all_price=all_price,
    planning_horizon_hours=72,
)
check("low charge plan detects the breach", low_plan["active"] is True)
# breach_offset_units = units_to_next_hour (4, since now is exactly on the
# hour) + hour_index * 4 = 4 + 5*4 = 24 - ported verbatim from the original
# template sensor's `low charge plan` attribute.
check("low charge plan's breach_unit accounts for the current-hour offset", low_plan["breach_unit"] == 24)

# A forecast that never breaches should report inactive
no_breach_forecast = [10.0] * 25
low_plan_inactive = plans.compute_low_charge_plan(
    None,
    cur_unit=0,
    forecast_with_spike=no_breach_forecast,
    now=now_top_of_hour,
    charge_speed_kw=7.0,
    low_threshold_kwh=3.0,
    minimum_charge_target_kwh=5.0,
    upper_limit_kwh=30.0,
    usage=usage_flat,
    all_price=all_price,
    planning_horizon_hours=72,
)
check("low charge plan reports inactive with no breach", low_plan_inactive["active"] is False)

high_breach_forecast = [10.0] * 5 + [40.0] * 20  # breaches high_threshold=33 at h=5
high_plan = plans.compute_high_discharge_plan(
    None,
    cur_unit=0,
    forecast_with_spike=high_breach_forecast,
    now=now_top_of_hour,
    discharge_speed_kw=10.0,
    high_threshold_kwh=33.0,
    low_threshold_kwh=3.0,
    usage=usage_flat,
    all_price=all_price,
    planning_horizon_hours=72,
)
check("high discharge plan detects the breach", high_plan["active"] is True)

# Lock-in: once active and cur_unit is inside [start_unit, end_unit), the
# exact same dict must be returned unchanged, not recomputed.
locked_again = plans.compute_low_charge_plan(
    low_plan,
    cur_unit=low_plan["start_unit"],
    forecast_with_spike=[999.0] * 25,  # deliberately different input data
    now=now_top_of_hour,
    charge_speed_kw=7.0,
    low_threshold_kwh=3.0,
    minimum_charge_target_kwh=5.0,
    upper_limit_kwh=30.0,
    usage=usage_flat,
    all_price=all_price,
    planning_horizon_hours=72,
)
check("an active plan locks in and ignores new input mid-window", locked_again == low_plan)

# ---------------------------------------------------------------------------
# plans.py - negative price plan + spike plan + composition chain smoke test
# ---------------------------------------------------------------------------
neg_price = [0.10] * 40 + [-0.30] * 8 + [0.10] * 40  # negative window units 40-47
neg_plan = plans.compute_negative_price_plan(
    None,
    cur_unit=0,
    now=now_top_of_hour,
    all_price=neg_price,
    threshold=-0.20,
    battery_forecast=[10.0] * 30,
    discharge_speed_kw=10.0,
    negative_price_charge_speed_kw=15.0,
    low_threshold_kwh=3.0,
    high_threshold_kwh=33.0,
)
check("negative price plan detects the negative window", neg_plan["active"] is True)
check("negative price plan's charge window starts at unit 40", neg_plan["charge_start_unit"] == 40)

composed_neg = plans.compose_forecast_with_negative_price(
    [10.0] * 30, neg_plan, cur_unit=0, now=now_top_of_hour, cap=33.0 - 0.01
)
check("composed-with-negative-price forecast is same length", len(composed_neg) == 30)

spike_price = [0.10] * 30 + [0.60] * 4 + [0.10] * 62  # a clear spike around units 30-33
spike_plan = plans.compute_spike_plan(
    None,
    cur_unit=0,
    all_price=spike_price,
    battery_forecast=[10.0] * 30,
    usage=usage_flat,
    low_threshold_kwh=3.0,
    upper_limit_kwh=30.0,
    high_threshold_kwh=33.0,
    spike_margin=0.40,
    charge_speed_kw=7.0,
    spike_discharge_speed_kw=15.0,
    neg_plan={"active": False},
)
check("spike plan detects the qualifying spread", spike_plan["active"] is True)

composed_spike = plans.compose_forecast_with_spike(
    composed_neg, spike_plan, cur_unit=0, now=now_top_of_hour, cap=33.0 - 0.01
)
check("composed-with-spike forecast is same length", len(composed_spike) == 30)

adjusted = plans.compose_forecast_adjusted(
    composed_spike, {"active": False}, {"active": False}, cur_unit=0, now=now_top_of_hour
)
check(
    "forecast_adjusted with no active low/high plan equals its base input",
    adjusted == [round(v, 2) for v in composed_spike],
)

# The full-charge plan's "scheduled"/"charging" phases add energy the same
# way the low charge plan does (v0.1.14) - a per-unit rate over its own
# start_unit/end_unit, unaffected by whether low/high are active.
adjusted_full_charging = plans.compose_forecast_adjusted(
    [10.0] * 4,
    {"active": False},
    {"active": False},
    cur_unit=0,
    now=now_top_of_hour,
    full={"active": True, "phase": "charging", "start_unit": 0, "end_unit": 8, "effective_charge_per_unit": 0.5},
    upper_limit_kwh=15.0,
)
check(
    "forecast_adjusted adds the full-charge plan's charging delta over its own window, then holds it",
    adjusted_full_charging == [12.0, 14.0, 14.0, 14.0],
)

# The full-charge plan's "holding" phase pins the forecast at 100%
# (upper_limit_kwh) across hold_start_unit..hold_end_unit instead of
# adding a delta - the system genuinely sits at the ceiling during that
# wait rather than declining per the usage forecast.
adjusted_full_holding = plans.compose_forecast_adjusted(
    [14.0, 13.5, 13.0, 12.5],
    {"active": False},
    {"active": False},
    cur_unit=0,
    now=now_top_of_hour,
    full={"active": True, "phase": "holding", "hold_start_unit": 0, "hold_end_unit": 8},
    upper_limit_kwh=15.0,
)
check(
    "forecast_adjusted pins the battery forecast at upper_limit_kwh across the full-charge plan's holding window",
    adjusted_full_holding == [15.0, 15.0, 13.0, 12.5],
)

# ---------------------------------------------------------------------------
# system_status
# ---------------------------------------------------------------------------
status_idle = plans.compute_system_status(
    setpoint_w=0.0,
    idle_setpoint_w=0.0,
    cur_unit=10,
    full={"active": False, "phase": None},
    neg={"active": False},
    spike={"active": False},
    low={"active": False, "breach_unit": 999999},
    high={"active": False, "breach_unit": 999999},
    battery_now_kwh=15.0,
    low_threshold_kwh=3.0,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 96,
)
check("system_status is Standby when everything is idle and inactive", status_idle == "Standby")

status_charging = plans.compute_system_status(
    setpoint_w=0.0,
    idle_setpoint_w=0.0,
    cur_unit=20,
    full={"active": False, "phase": None},
    neg={"active": False},
    spike={"active": False},
    low={"active": True, "start_unit": 20, "end_unit": 24, "breach_unit": 30},
    high={"active": False, "breach_unit": 999999},
    battery_now_kwh=2.0,
    low_threshold_kwh=3.0,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 96,
)
check("system_status is Start charge when low plan's window just opened", status_charging == "Start charge")

status_full_scheduled = plans.compute_system_status(
    setpoint_w=0.0,
    idle_setpoint_w=0.0,
    cur_unit=93,
    full={"active": True, "phase": "scheduled", "start_unit": 135, "end_unit": 164, "target_kwh": 11.99},
    neg={"active": False},
    spike={"active": False},
    low={"active": False, "breach_unit": 999999},
    high={"active": False, "breach_unit": 999999},
    battery_now_kwh=3.15,
    low_threshold_kwh=1.5,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 192,
)
check(
    "system_status shows Full charge scheduled instead of falling through to Standby",
    status_full_scheduled == "Full charge scheduled",
)

status_awaiting_solar = plans.compute_system_status(
    setpoint_w=0.0,
    idle_setpoint_w=0.0,
    cur_unit=81,
    full={"active": False, "phase": None, "relying_on_peak_unit": 540},
    neg={"active": False},
    spike={"active": False},
    low={"active": False, "breach_unit": 999999},
    high={"active": False, "breach_unit": 999999, "suppressed_by_full_charge": True},
    battery_now_kwh=9.5,
    low_threshold_kwh=1.5,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 192,
)
check(
    "system_status shows Awaiting solar (full charge) instead of a bare Standby when relying on a future peak",
    status_awaiting_solar == "Awaiting solar (full charge)",
)

status_awaiting_solar_overridden_by_real_action = plans.compute_system_status(
    setpoint_w=4000.0,
    idle_setpoint_w=0.0,
    cur_unit=21,
    full={"active": False, "phase": None, "relying_on_peak_unit": 540},
    neg={"active": False},
    spike={"active": False},
    low={"active": True, "start_unit": 20, "end_unit": 24, "breach_unit": 30},
    high={"active": False, "breach_unit": 999999},
    battery_now_kwh=2.0,
    low_threshold_kwh=3.0,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 96,
)
check(
    "Awaiting solar (full charge) never overrides a genuinely active plan's own status",
    status_awaiting_solar_overridden_by_real_action == "Actief",
)

# Holding always reports "Start charge" for its entire duration now,
# regardless of the setpoint readback - solar alone can hold the battery
# at 100% with zero grid setpoint needed, so "Balancing"/setpoint-ramp-up
# is retired (it was never even an automation trigger - see
# dashboard/automation_example.yaml).
status_holding_no_setpoint = plans.compute_system_status(
    setpoint_w=0.0,
    idle_setpoint_w=0.0,
    cur_unit=12,
    full={"active": True, "phase": "holding", "hold_start_unit": 10, "hold_end_unit": 18},
    neg={"active": False},
    spike={"active": False},
    low={"active": False, "breach_unit": 999999},
    high={"active": False, "breach_unit": 999999},
    battery_now_kwh=15.0,
    low_threshold_kwh=1.5,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 96,
)
check(
    "system_status shows Start charge while holding even with zero setpoint readback (solar alone holding it full)",
    status_holding_no_setpoint == "Start charge",
)

status_holding_with_setpoint = plans.compute_system_status(
    setpoint_w=4000.0,
    idle_setpoint_w=0.0,
    cur_unit=12,
    full={"active": True, "phase": "holding", "hold_start_unit": 10, "hold_end_unit": 18},
    neg={"active": False},
    spike={"active": False},
    low={"active": False, "breach_unit": 999999},
    high={"active": False, "breach_unit": 999999},
    battery_now_kwh=15.0,
    low_threshold_kwh=1.5,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 96,
)
check(
    "system_status still shows Start charge while holding even once the setpoint readback has ramped up (Balancing retired)",
    status_holding_with_setpoint == "Start charge",
)

# ---------------------------------------------------------------------------
# display.py
# ---------------------------------------------------------------------------
energy, start_text, stop_text = display.charge_display(
    {"active": False, "phase": None}, {"active": False}, {"active": False}, low_plan, cur_unit=0, now=now_top_of_hour
)
check("charge_display falls through to the low charge plan", energy == round(low_plan["target_kwh"], 2))
check("charge_display produces a start time string", isinstance(start_text, str))

full_scheduled = {"active": True, "phase": "scheduled", "start_unit": 135, "end_unit": 164, "target_kwh": 11.99}
energy_full, start_full, stop_full = display.charge_display(
    full_scheduled, {"active": False}, {"active": False}, low_plan, cur_unit=93, now=now_top_of_hour
)
check(
    "charge_display shows the full charge plan's scheduled window ahead of an active low charge plan",
    energy_full == 11.99 and start_full is not None and stop_full is not None,
)

full_holding = {"active": True, "phase": "holding", "hold_start": now_top_of_hour.isoformat(), "hold_minutes": 5.0}
energy_holding, start_holding, stop_holding = display.charge_display(
    full_holding, {"active": False}, {"active": False}, low_plan, cur_unit=0, now=now_top_of_hour
)
check(
    "charge_display falls through to the low charge plan while full charge plan is only holding/balancing",
    energy_holding == round(low_plan["target_kwh"], 2),
)

spike_charge_window = {
    "active": True,
    "charge_start_unit": 60,
    "charge_end_unit": 62,
    "charge_needed_kwh": 1.91,
    "discharge_start_unit": 172,
    "discharge_end_unit": 176,
}
energy_spike_upcoming, start_spike_upcoming, stop_spike_upcoming = display.charge_display(
    {"active": False, "phase": None}, {"active": False}, spike_charge_window, low_plan, cur_unit=50, now=now_top_of_hour
)
check(
    "charge_display shows the spike plan's own charge window while it's still upcoming",
    energy_spike_upcoming == 1.91,
)
energy_spike_past, start_spike_past, stop_spike_past = display.charge_display(
    {"active": False, "phase": None}, {"active": False}, spike_charge_window, low_plan, cur_unit=74, now=now_top_of_hour
)
check(
    "charge_display falls through to the low charge plan once the spike plan's own charge window has "
    "passed, even though the spike plan is still 'active' waiting for its later discharge phase "
    "(regression: a live dump showed a past charge_start_time/charge_stop_time here)",
    energy_spike_past == round(low_plan["target_kwh"], 2),
)

energy_snap, start_snap, stop_snap = display.charge_display(
    {"active": False, "phase": None},
    {"active": False},
    {"active": False},
    {"active": True, "target_kwh": 0.57, "start_unit": 77, "end_unit": 78},
    cur_unit=77,
    now=datetime(2026, 9, 21, 19, 23, 27),
)
check(
    "charge_display snaps the displayed time to the 15-minute price grid instead of carrying "
    "forward 'now''s own minutes/seconds (19:23:27 -> the 19:15 unit boundary, not 19:23)",
    start_snap == "Mon 19:15",
)

next_days = display.next_full_charge_in_days(interval_days=14, time_since_days=20)
check("next_full_charge_in_days floors at 0 when overdue", next_days == 0)

# ---------------------------------------------------------------------------
# compute_full_charge_plan - session cap, multi-day spread, flat-price extension
# ---------------------------------------------------------------------------

# A large deficit + a slow charger would otherwise want a single very long
# window; the session cap (30x the 5-day average hourly usage, floored at
# a 4-hour-equivalent minimum for this session's own charge_speed_kw - see
# below) should limit target_kwh, and units_needed/end_unit should reflect
# the capped figure, not the full deficit. all_price is sized to exactly
# units_needed so there's no room for _extend_flat_price_window to grow
# the window either direction, isolating the cap math from the extension
# logic. Here the raw usage-average cap (9.0 kWh) is actually smaller than
# this charger's 4-hour floor (3.0 kW * 4h = 12.0 kWh), so the floor is
# what ends up binding - 12.0, not 9.0.
capped_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=20.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=3.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 18,
    battery_forecast=[3.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan caps a single session's target_kwh at max(30x 5-day avg usage, 4h at charge_speed_kw)",
    capped_plan["session_cap_kwh"] == 12.0 and capped_plan["target_kwh"] == 12.0,
)
check(
    "compute_full_charge_plan's units_needed/end_unit reflect the capped target, not the full 12.3kWh deficit",
    capped_plan["units_needed"] == 18 and capped_plan["end_unit"] == 18,
)

# The 4-hour-minimum floor is what makes charge speed itself a factor in
# whether the cap ever actually binds (added v0.1.17, per Timo: a 10kW
# charger can empty/fill a typical battery in ~3 hours regardless, so a
# cap is unnecessary there, while a 1.8kW charger taking 8+ hours for the
# same energy genuinely needs one). Same deficit/usage in both cases below
# - only charge_speed_kw differs.
fast_charger_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=20.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=3.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=10.0,
    all_price=[0.10] * 6,
    battery_forecast=[3.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan: a fast charger's 4h-floor cap (40 kWh) is well above the deficit, so the cap doesn't bind at all",
    fast_charger_plan["session_cap_kwh"] == 40.0 and fast_charger_plan["target_kwh"] == 12.3,
)

slow_charger_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=20.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=3.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=1.8,
    all_price=[0.10] * 24,
    battery_forecast=[3.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan: a slow charger's usage-average cap (9.0 kWh, above its 7.2 kWh floor) still meaningfully binds",
    slow_charger_plan["session_cap_kwh"] == 9.0 and slow_charger_plan["target_kwh"] == 9.0,
)

low_usage_slow_charger_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=20.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=3.0,
    high_threshold_kwh=15.0,
    usage=[0.05] * 120,
    charge_speed_kw=1.8,
    all_price=[0.10] * 17,
    battery_forecast=[3.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan: with very low average usage, the 4h floor (7.2 kWh) itself becomes the binding cap, not the tiny 1.5 kWh usage-average figure",
    low_usage_slow_charger_plan["session_cap_kwh"] == 7.2 and low_usage_slow_charger_plan["target_kwh"] == 7.2,
)

# A session-capped window still gets the flat-price extension (v0.1.16 -
# reverts v0.1.15's blanket "never extend a capped session", per Timo:
# the session cap exists to keep the *initial* window search from having
# to reach into meaningfully pricier hours just to fit a large deficit's
# units_needed in one sitting, not to cap total energy delivered outright
# - and the extension can't violate that on its own, since it only ever
# grows into neighbors within the same 8%/EUR 0.02 tolerance (still
# genuinely cheap, never "the expensive part"). So if a long flat-cheap
# valley happens to be available right where a capped session lands,
# using more of it is fine. Same shape as the original live-reported
# scenario (a session capped well below the raw deficit, with a long
# flat near-zero valley available right where the cheapest window lands)
# - here the 4-hour floor (v0.1.17) is what caps this particular session
# at 12.0 kWh/18 units, and the window still extends well past that into
# the flat valley, confirming the floor doesn't disable the extension.
flat_valley_price = [0.03] * 20 + [0.005] * 40 + [0.25] * 20
capped_with_flat_valley = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=15.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=1.79,
    high_threshold_kwh=15.0,
    usage=[0.21] * 120,
    charge_speed_kw=3.0,
    all_price=flat_valley_price,
    battery_forecast=[1.79] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan still extends a session-capped window into an available flat-price valley",
    capped_with_flat_valley["end_unit"] - capped_with_flat_valley["start_unit"] > capped_with_flat_valley["units_needed"],
)

# A small deficit that's already under the cap shouldn't be touched by it.
uncapped_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=90.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=14.5,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 2,
    battery_forecast=[14.5] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan leaves target_kwh alone when it's already under the session cap",
    uncapped_plan["session_cap_kwh"] == 12.0 and uncapped_plan["target_kwh"] == 0.8,
)

# A "charging" session whose window has fully elapsed without reaching
# full should NOT just keep returning prev (the old, run-forever
# behavior) - it should fall through and compute a fresh plan, which is
# what actually lets a too-big charge spread across multiple days.
midway_prev = {
    "active": True,
    "phase": "charging",
    "target_kwh": 9.0,
    "deficit_kwh": 12.0,
    "hold_hour_usage_kwh": 0.3,
    "session_cap_kwh": 9.0,
    "effective_charge_per_unit": 0.675,
    "units_needed": 14,
    "start_unit": 0,
    "end_unit": 5,
}
continued_plan = plans.compute_full_charge_plan(
    prev=midway_prev,
    cur_unit=5,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=60.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=8.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[8.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan re-plans a fresh session once an elapsed window didn't reach full, instead of running forever",
    continued_plan["phase"] == "scheduled" and continued_plan is not midway_prev,
)

# The same session, still mid-window and not yet full, should keep
# returning the locked-in plan unchanged (existing behavior, unaffected).
still_charging_plan = plans.compute_full_charge_plan(
    prev=midway_prev,
    cur_unit=2,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=60.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=8.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[8.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check("compute_full_charge_plan keeps charging unchanged while still inside its locked window", still_charging_plan == midway_prev)

# Reaching full mid-window (or right as the window elapses) always wins
# and moves to holding, regardless of how much window time is left.
full_mid_window_plan = plans.compute_full_charge_plan(
    prev=midway_prev,
    cur_unit=2,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=99.6,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=14.95,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[14.95] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check("compute_full_charge_plan moves to holding as soon as full, even mid-window", full_mid_window_plan["phase"] == "holding")
check(
    "compute_full_charge_plan's fresh holding entry (from charging) stamps hold_start_unit/hold_end_unit from cur_unit and max_hold_minutes",
    full_mid_window_plan["hold_start_unit"] == 2 and full_mid_window_plan["hold_end_unit"] == 10,
)

# Reaching the due-and-already-full path (no prior charging session at
# all - e.g. a fresh calibration check right as the battery happens to
# already be full) should stamp the same hold_start_unit/hold_end_unit
# fields, needed by compose_forecast_adjusted to pin the forecast at 100%.
due_and_full_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=10,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=99.8,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=15.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan starts holding directly (skipping scheduled/charging) when already full and due",
    due_and_full_plan["phase"] == "holding" and due_and_full_plan["hold_start_unit"] == 10 and due_and_full_plan["hold_end_unit"] == 18,
)

# Continuing an already-in-progress holding phase must carry its
# hold_start_unit/hold_end_unit forward unchanged from prev, not
# recompute them from the current cycle's cur_unit.
holding_prev = {
    "active": True,
    "phase": "holding",
    "hold_start": now_top_of_hour.isoformat(),
    "hold_minutes": 30.0,
    "hold_start_unit": 10,
    "hold_end_unit": 18,
}
continued_holding_plan = plans.compute_full_charge_plan(
    prev=holding_prev,
    cur_unit=16,
    now=now_top_of_hour + timedelta(minutes=30),
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=99.8,
    max_hold_minutes=120.0,
    voltage_diff=999.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan keeps a continuing holding phase's hold_start_unit/hold_end_unit fixed from when holding began",
    continued_holding_plan["hold_start_unit"] == 10 and continued_holding_plan["hold_end_unit"] == 18,
)

# ---------------------------------------------------------------------------
# compute_full_charge_plan - deficit anchored to a forecasted peak or the
# cheapest window, not always to right now (added v0.1.18, per Timo: if
# solar is forecast to raise the battery later - even days out - there's
# no point buying grid energy for a gap solar will close for free; if
# there's no such rise, at least look at the level forecast to exist once
# the cheapest window actually arrives, not the level right now).
# ---------------------------------------------------------------------------

# battery_forecast rises to a peak of 12.0 kWh at hour 6 (unit 24), well
# below the 16.5 kWh overshoot ceiling, then declines - a real but partial
# future rise. The deficit should be anchored to that peak (12.0), not
# today's 5.0 kWh, and the window must be scheduled to *finish by* the
# peak (unit 24) rather than after it - the peak is the optimal moment
# (grid top-up landing right as solar's own rise crests), not a floor to
# wait out. Here the cheapest prices (0.01) happen to sit right before the
# peak anyway, so the window lands at [0, 24).
future_peak_forecast = [6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 11.0, 10.0, 9.0]
future_peak_price = [0.01] * 24 + [0.20] * 6 + [0.40] * 10
future_peak_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=33.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=5.0,
    high_threshold_kwh=16.5,
    usage=[1.0] * 120,
    charge_speed_kw=5.0,
    all_price=future_peak_price,
    battery_forecast=future_peak_forecast,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan anchors the deficit to a genuine future peak (12.0 kWh), not today's 5.0 kWh",
    future_peak_plan["anchor_kwh"] == 12.0 and future_peak_plan["deficit_kwh"] == 4.5 and future_peak_plan["target_kwh"] == 5.5,
)
check(
    "compute_full_charge_plan schedules the window to finish by the peak (deadline), not after it",
    future_peak_plan["start_unit"] == 0 and future_peak_plan["end_unit"] == 24,
)
check(
    "compute_full_charge_plan flags relying_on_peak_unit at the genuine future peak's own unit, for the discharge plan to respect",
    future_peak_plan["relying_on_peak_unit"] == 24,
)

# The same shape, but the forecasted peak (17.0 kWh) now reaches past the
# 16.5 kWh overshoot ceiling - a genuine, sustained surplus, not just a
# graze past 100%. Nothing should be scheduled at all: live SOC crossing
# 99.5% will drive the holding phase on its own once solar gets it there.
overshoot_forecast = [6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 17.0, 16.0, 15.0, 14.0]
overshoot_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=33.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=6.0,
    high_threshold_kwh=16.5,
    usage=[1.0] * 120,
    charge_speed_kw=5.0,
    all_price=[0.10] * 30,
    battery_forecast=overshoot_forecast,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan schedules nothing when the forecasted peak already reaches the overshoot ceiling on its own",
    overshoot_plan == {"active": False, "phase": None, "relying_on_peak_unit": 24, "retry_after_timeout": False},
)
check(
    "compute_full_charge_plan still flags relying_on_peak_unit even when skipping scheduling entirely - the discharge plan must not sell off a peak this decision is silently counting on",
    overshoot_plan["relying_on_peak_unit"] == 24,
)

# No future rise at all (forecast strictly declines from today's level -
# e.g. no solar) - "now" is effectively the peak. Rather than anchoring to
# right now (10.0 kWh), the deficit should be anchored to whatever the
# battery is forecast to be AT the cheapest available window (unit 20,
# where forecast[5] == 7.5 kWh, lower than today because of ordinary usage
# in the meantime) - producing a bigger, more honest target (10.0 kWh) than
# the naive today-anchored figure would (7.5 kWh).
no_rise_forecast = [10.0 - 0.5 * h for h in range(10)]
no_rise_price = [0.30] * 20 + [0.05] * 10 + [0.30] * 10
no_rise_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=0,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=66.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=10.0,
    high_threshold_kwh=16.5,
    usage=[1.0] * 120,
    charge_speed_kw=5.0,
    all_price=no_rise_price,
    battery_forecast=no_rise_forecast,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan with no future rise anchors to the forecasted level at the cheapest window (7.5 kWh), not today's 10.0 kWh",
    no_rise_plan["anchor_kwh"] == 7.5 and no_rise_plan["anchor_unit"] == 20,
)
check(
    "compute_full_charge_plan's no-future-rise target (10.0 kWh) is bigger than the naive today-anchored figure would be (7.5 kWh)",
    no_rise_plan["target_kwh"] == 10.0 and no_rise_plan["start_unit"] == 20 and no_rise_plan["end_unit"] == 30,
)
check(
    "compute_full_charge_plan leaves relying_on_peak_unit as None for the no-future-rise (cheapest-window) case - there's no future peak there for the discharge plan to protect",
    no_rise_plan["relying_on_peak_unit"] is None,
)

# ---------------------------------------------------------------------------
# compute_full_charge_plan - "full" (the trigger to enter holding) is
# satisfied by SOC>=99.5% OR battery pack voltage within 1.0V of target,
# either one on its own - added per Timo: SOC can drift over time, so pack
# voltage is a second, independent way to notice a genuinely full battery.
# ---------------------------------------------------------------------------

# SOC well below 99.5% (drifted low), but pack voltage already within 1.0V
# of target - should trigger holding on voltage alone, same as due_and_full_plan
# above does via SOC.
voltage_triggered_full_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=10,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=90.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=15.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=54.3,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan starts holding on pack voltage alone (within 1.0V of target) even though SOC is only 90%",
    voltage_triggered_full_plan["phase"] == "holding",
)

# Just below that 1.0V trigger margin, with SOC still well under 99.5% -
# neither leg fires, so nothing should be forced.
voltage_not_yet_full_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=10,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=90.0,
    max_hold_minutes=120.0,
    voltage_diff=None,
    battery_now_kwh=13.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[13.0] * 5,
    battery_voltage=54.1,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan does not start holding when pack voltage is still more than 1.0V under target and SOC is under 99.5%",
    voltage_not_yet_full_plan["phase"] != "holding",
)

# A holding phase already in progress (entered via voltage alone, SOC
# still under 99.5%) must NOT auto-confirm balance just because that same
# loose 1.0V voltage reading persists - balance_confirmed_now still
# requires genuine SOC>=99.5% (is_full), which the looser holding-entry
# margin deliberately never substitutes for. It should keep holding,
# waiting for real SOC (or a tighter voltage reading) to confirm.
voltage_triggered_holding_prev = {
    "active": True,
    "phase": "holding",
    "hold_start": now_top_of_hour.isoformat(),
    "hold_minutes": 5.0,
    "hold_start_unit": 10,
    "hold_end_unit": 18,
}
voltage_triggered_still_holding_plan = plans.compute_full_charge_plan(
    prev=voltage_triggered_holding_prev,
    cur_unit=11,
    now=now_top_of_hour + timedelta(minutes=5),
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=90.0,
    max_hold_minutes=120.0,
    voltage_diff=2.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=16.5,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=54.3,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan's looser 1.0V holding-entry margin doesn't also satisfy balance_confirmed, which still needs genuine SOC>=99.5%",
    voltage_triggered_still_holding_plan == {
        "active": True,
        "phase": "holding",
        "hold_start": voltage_triggered_holding_prev["hold_start"],
        "hold_minutes": 5.0,
        "hold_start_unit": 10,
        "hold_end_unit": 18,
    },
)

# ---------------------------------------------------------------------------
# compute_full_charge_plan - balance_confirmed (three-way AND: SOC, cell
# voltage differential, battery pack voltage vs. target) and
# retry_after_timeout (a timed-out hold defers to the normal flow instead
# of immediately re-forcing another hold). Added per Timo's situation
# 1/situation 2 spec and the "default to normal flow" timeout answer.
# ---------------------------------------------------------------------------

# Situation 1: nothing due, but the battery is genuinely full and all three
# confirmation legs are satisfied together - passively confirmed, no active
# plan forced.
passive_confirmed_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=10,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=1.0,
    soc_now_percent=99.6,
    max_hold_minutes=120.0,
    voltage_diff=5.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=16.5,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=55.2,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan passively confirms balance (and forces nothing) when full+balanced with nothing due",
    passive_confirmed_plan == {"active": False, "phase": None, "balance_confirmed": True},
)

# Same, but the battery pack voltage hasn't actually reached the target yet
# (still well under target - 0.1V) - SOC and voltage_diff alone are not
# enough, balance_confirmed must stay False.
passive_unconfirmed_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=10,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=1.0,
    soc_now_percent=99.6,
    max_hold_minutes=120.0,
    voltage_diff=5.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=16.5,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=54.0,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan withholds balance_confirmed when battery voltage hasn't reached target - 0.1V yet",
    passive_unconfirmed_plan == {"active": False, "phase": None, "balance_confirmed": False},
)

# A missing battery_voltage reading must be treated the same conservative
# way as a missing voltage_diff reading - never assume the target's met.
passive_missing_voltage_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=10,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=1.0,
    soc_now_percent=99.6,
    max_hold_minutes=120.0,
    voltage_diff=5.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=16.5,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan treats a missing battery_voltage reading as not-yet-confirmed, never as satisfied",
    passive_missing_voltage_plan["balance_confirmed"] is False,
)

# Situation 2: a hold already in progress ends the moment all three legs
# are satisfied together, regardless of how long is left on the timeout.
holding_all_confirmed_prev = {
    "active": True,
    "phase": "holding",
    "hold_start": now_top_of_hour.isoformat(),
    "hold_minutes": 5.0,
    "hold_start_unit": 10,
    "hold_end_unit": 18,
}
holding_confirmed_plan = plans.compute_full_charge_plan(
    prev=holding_all_confirmed_prev,
    cur_unit=11,
    now=now_top_of_hour + timedelta(minutes=5),
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=99.8,
    max_hold_minutes=120.0,
    voltage_diff=2.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=55.5,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan ends a holding phase as soon as all three legs are genuinely satisfied together",
    holding_confirmed_plan == {"active": False, "phase": None, "balance_confirmed": True},
)

# A hold that times out without ever confirming balance must NOT reset the
# interval (balance_confirmed absent/false) and must flag
# retry_after_timeout, so the very next fresh evaluation doesn't just
# shortcut straight back into another hold.
holding_timeout_prev = {
    "active": True,
    "phase": "holding",
    "hold_start": now_top_of_hour.isoformat(),
    "hold_minutes": 30.0,
    "hold_start_unit": 10,
    "hold_end_unit": 18,
}
holding_timed_out_plan = plans.compute_full_charge_plan(
    prev=holding_timeout_prev,
    cur_unit=18,
    now=now_top_of_hour + timedelta(minutes=125),
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=99.8,
    max_hold_minutes=120.0,
    voltage_diff=999.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan flags retry_after_timeout (and not balance_confirmed) when a hold times out unbalanced",
    holding_timed_out_plan == {"active": False, "phase": None, "timed_out": True, "retry_after_timeout": True},
)

# The very next fresh (phase=None) evaluation, still due and still
# genuinely full, must NOT shortcut straight back into holding just
# because retry_after_timeout is set - it falls through to the same
# forward-looking peak/deficit logic used before any charge was ever
# forced. Here battery_now_kwh already equals high_threshold_kwh with a
# flat forecast, so deficit<=0 and nothing gets scheduled either - proving
# holding was genuinely skipped, not just deferred into a scheduled plan.
retry_after_timeout_plan = plans.compute_full_charge_plan(
    prev=holding_timed_out_plan,
    cur_unit=18,
    now=now_top_of_hour + timedelta(minutes=130),
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=99.8,
    max_hold_minutes=120.0,
    voltage_diff=999.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan does not immediately re-enter holding on the fresh evaluation right after a timeout, even though SOC is still >=99.5%",
    retry_after_timeout_plan["phase"] is None and retry_after_timeout_plan["active"] is False,
)
check(
    "compute_full_charge_plan carries retry_after_timeout forward across consecutive fresh evaluations, until real progress resets it",
    retry_after_timeout_plan["retry_after_timeout"] is True,
)

# Contrast: the SAME due+genuinely-full scenario, but with no prior timeout
# (prev=None) - the direct, immediate is_full -> holding transition (the
# ORIGINAL, non-timeout situation-2 behavior) must be unaffected by any of
# the above.
fresh_due_and_full_plan = plans.compute_full_charge_plan(
    prev=None,
    cur_unit=18,
    now=now_top_of_hour,
    interval_days=14.0,
    time_since_days=20.0,
    soc_now_percent=99.8,
    max_hold_minutes=120.0,
    voltage_diff=999.0,
    battery_now_kwh=15.0,
    high_threshold_kwh=15.0,
    usage=[0.3] * 120,
    charge_speed_kw=3.0,
    all_price=[0.10] * 20,
    battery_forecast=[15.0] * 5,
    battery_voltage=None,
    target_voltage=55.2,
)
check(
    "compute_full_charge_plan still enters holding immediately on a genuine first-time is_full+due, unaffected by retry_after_timeout logic",
    fresh_due_and_full_plan["phase"] == "holding",
)

# compute_high_discharge_plan's suppress_new - blocks scheduling a brand new
# discharge window while the full-charge plan is relying on the same future
# solar peak this function would otherwise sell surplus down from (see
# coordinator.py's suppress_high_discharge wiring), without disturbing a
# discharge window that's already locked in and in progress.
discharge_forecast_with_spike = [6.0] * 5 + [20.0] * 60  # breaches high_threshold almost immediately
suppressed_discharge_plan = plans.compute_high_discharge_plan(
    prev=None,
    cur_unit=0,
    forecast_with_spike=discharge_forecast_with_spike,
    now=now_top_of_hour,
    discharge_speed_kw=5.0,
    high_threshold_kwh=16.5,
    low_threshold_kwh=1.0,
    usage=[1.0] * 120,
    all_price=[0.10] * 96,
    planning_horizon_hours=72,
    suppress_new=True,
)
check(
    "compute_high_discharge_plan's suppress_new blocks scheduling a brand new discharge window",
    suppressed_discharge_plan == {"active": False, "breach_unit": 999999, "suppressed_by_full_charge": True},
)
unsuppressed_discharge_plan = plans.compute_high_discharge_plan(
    prev=None,
    cur_unit=0,
    forecast_with_spike=discharge_forecast_with_spike,
    now=now_top_of_hour,
    discharge_speed_kw=5.0,
    high_threshold_kwh=16.5,
    low_threshold_kwh=1.0,
    usage=[1.0] * 120,
    all_price=[0.10] * 96,
    planning_horizon_hours=72,
)
check(
    "compute_high_discharge_plan schedules normally when suppress_new is left at its default (False)",
    unsuppressed_discharge_plan["active"] is True,
)
locked_in_discharge_plan = plans.compute_high_discharge_plan(
    prev=unsuppressed_discharge_plan,
    cur_unit=unsuppressed_discharge_plan["start_unit"],
    forecast_with_spike=discharge_forecast_with_spike,
    now=now_top_of_hour,
    discharge_speed_kw=5.0,
    high_threshold_kwh=16.5,
    low_threshold_kwh=1.0,
    usage=[1.0] * 120,
    all_price=[0.10] * 96,
    planning_horizon_hours=72,
    suppress_new=True,
)
check(
    "compute_high_discharge_plan's suppress_new doesn't cut off a discharge window already locked in and in progress",
    locked_in_discharge_plan == unsuppressed_discharge_plan,
)

# _extend_flat_price_window - the houseboat-style "extend into a flat
# block" heuristic (8% relative OR EUR 0.02 absolute, whichever is easier).
ext_start, ext_end = plans._extend_flat_price_window([1.00, 1.03], start=0, end=1, min_start=0)
check(
    "_extend_flat_price_window extends via the 8% relative tolerance even when the absolute diff exceeds EUR 0.02",
    (ext_start, ext_end) == (0, 2),
)

mixed_prices = [0.50, 0.10, 0.10, 0.10, 0.105, 0.30, 0.30]
ext2_start, ext2_end = plans._extend_flat_price_window(mixed_prices, start=1, end=4, min_start=0)
check(
    "_extend_flat_price_window extends forward via the EUR 0.02 absolute tolerance and stops at the next real jump",
    (ext2_start, ext2_end) == (1, 5),
)
check(
    "_extend_flat_price_window doesn't extend backward into a much higher price just because it's adjacent",
    ext2_start == 1,
)

flat_prices = [0.10, 0.10, 0.10, 0.10]
ext3_start, _ = plans._extend_flat_price_window(flat_prices, start=2, end=3, min_start=2)
check("_extend_flat_price_window never grows backward past min_start, even into an equally cheap unit", ext3_start == 2)

flat_prices_long = [0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
_, ext4_end = plans._extend_flat_price_window(flat_prices_long, start=0, end=1, min_start=0, max_end=4)
check(
    "_extend_flat_price_window's optional max_end stops the rightward extension at a deadline, even into equally cheap units beyond it",
    ext4_end == 4,
)
_, ext5_end = plans._extend_flat_price_window(flat_prices_long, start=0, end=1, min_start=0)
check(
    "_extend_flat_price_window still extends to the end of the array when max_end is left at its default (None)",
    ext5_end == 6,
)

# ---------------------------------------------------------------------------
# compute_system_status - regression for a live report: at exactly a low
# charge plan's own start_unit, with a spike plan still nominally "active"
# (waiting on a later discharge phase, its own charge window already past
# or - as in the live report - a zero-length/zero-kWh no-op window), the
# state stayed "Standby" instead of "Start charge". Same root cause already
# fixed in display.charge_display (v0.1.30) and the dashboard charts
# (v0.1.31), just never carried over to this function - previously untested
# by this suite at all.
# ---------------------------------------------------------------------------
status_full = {"active": False, "phase": None, "balance_confirmed": False}
status_neg = {"active": False}
status_high = {"active": False, "breach_unit": 999999}
status_all_price = [0.10] * 160

spike_gap_plan = {
    "active": True,
    "charge_start_unit": 34,
    "charge_end_unit": 34,
    "discharge_start_unit": 76,
    "discharge_end_unit": 81,
}
low_plan_starting_now = {"active": True, "start_unit": 55, "end_unit": 56, "breach_unit": 128}
status_at_low_start = plans.compute_system_status(
    setpoint_w=0.0,
    idle_setpoint_w=0.0,
    cur_unit=55,
    full=status_full,
    neg=status_neg,
    spike=spike_gap_plan,
    low=low_plan_starting_now,
    high=status_high,
    battery_now_kwh=24.87,
    low_threshold_kwh=3,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=status_all_price,
)
check(
    "compute_system_status falls through a spike plan's own charge/discharge gap to report the low charge plan's 'Start charge', "
    "instead of masking it with a blanket 'Standby' (regression: a live dump showed Standby exactly at the low plan's start_unit)",
    status_at_low_start == "Start charge",
)

# The spike plan's own charge window must still take priority and report
# correctly while it's genuinely current, unaffected by the fix above.
spike_charging_now = {
    "active": True,
    "charge_start_unit": 50,
    "charge_end_unit": 56,
    "discharge_start_unit": 76,
    "discharge_end_unit": 81,
}
status_spike_charging = plans.compute_system_status(
    setpoint_w=0.0,
    idle_setpoint_w=0.0,
    cur_unit=55,
    full=status_full,
    neg=status_neg,
    spike=spike_charging_now,
    low={"active": False, "breach_unit": 999999},
    high=status_high,
    battery_now_kwh=24.87,
    low_threshold_kwh=3,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=status_all_price,
)
check(
    "compute_system_status still reports 'Start charge' for the spike plan's own currently-active charge window",
    status_spike_charging == "Start charge",
)

# And its discharge window, once reached, still takes priority over the
# fallthrough - the fix only changes what happens in the gap between them.
status_spike_discharging = plans.compute_system_status(
    setpoint_w=0.0,
    idle_setpoint_w=0.0,
    cur_unit=78,
    full=status_full,
    neg=status_neg,
    spike=spike_gap_plan,
    low={"active": False, "breach_unit": 999999},
    high=status_high,
    battery_now_kwh=24.87,
    low_threshold_kwh=3,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=status_all_price,
)
check(
    "compute_system_status still reports 'Start spike discharge' for the spike plan's own currently-active discharge window",
    status_spike_discharging == "Start spike discharge",
)

# cell_voltage_differential_mv - the low/high individual-cell-voltage
# alternative to a BMS's own differential sensor (added with the
# low/high cell voltage config option).
diff_mv = display.cell_voltage_differential_mv(low_v=3.285, high_v=3.301)
check(
    "cell_voltage_differential_mv converts volts to millivolts, not just subtracts",
    diff_mv == 16.0,
)
check(
    "cell_voltage_differential_mv is None when either reading is unavailable (low)",
    display.cell_voltage_differential_mv(low_v=None, high_v=3.301) is None,
)
check(
    "cell_voltage_differential_mv is None when either reading is unavailable (high)",
    display.cell_voltage_differential_mv(low_v=3.285, high_v=None) is None,
)

# negative_price_status_text - mirrors spike_status_text, exposed as its
# own "Negative price status" sensor the same way spike already was.
neg_status_active = display.negative_price_status_text(
    {"active": True, "threshold": -0.02, "achievable_charge_kwh": 4.5}
)
check(
    "negative_price_status_text shows the threshold and achievable charge while active",
    neg_status_active == "Active (below €-0.02, 4.5 kWh)",
)
check(
    "negative_price_status_text is 'Inactive' when the plan isn't active",
    display.negative_price_status_text({"active": False}) == "Inactive",
)

# ---------------------------------------------------------------------------
# usage_forecast.py - calculated household usage forecast (no HA needed:
# operates on a plain dict of pre-fetched hourly cumulative sums, the same
# shape statistics_source.py produces from the real recorder)
# ---------------------------------------------------------------------------
HOUR_S = 3600
WEEK_S = 7 * 24 * HOUR_S
usage_now = now_top_of_hour  # 2026-09-16 14:00:00, top of hour
usage_base_epoch = int(usage_now.replace(minute=0, second=0, microsecond=0).timestamp())


def _hist_epoch(weeks_back: int) -> int:
    return usage_base_epoch - weeks_back * WEEK_S


hourly_sums = {"sensor.solar": {}, "sensor.import": {}, "sensor.export": {}, "sensor.batt_charge": {}, "sensor.batt_discharge": {}}

# 1 week back: a complete sample. solar +2.0, import +3.0, export +0.5,
# battery charge +1.0, battery discharge +0.2
# consumption = solar + import + discharge - export - charge = 3.7
e1 = _hist_epoch(1)
hourly_sums["sensor.solar"][e1] = 100.0
hourly_sums["sensor.solar"][e1 - HOUR_S] = 98.0
hourly_sums["sensor.import"][e1] = 50.0
hourly_sums["sensor.import"][e1 - HOUR_S] = 47.0
hourly_sums["sensor.export"][e1] = 10.5
hourly_sums["sensor.export"][e1 - HOUR_S] = 10.0
hourly_sums["sensor.batt_charge"][e1] = 5.0
hourly_sums["sensor.batt_charge"][e1 - HOUR_S] = 4.0
hourly_sums["sensor.batt_discharge"][e1] = 2.2
hourly_sums["sensor.batt_discharge"][e1 - HOUR_S] = 2.0

# 2 weeks back: deliberately missing the export entity's data entirely, to
# verify a week with any missing term is dropped from the average outright
# (not coalesced to a 0 contribution - the fix over the original's SQL).
e2 = _hist_epoch(2)
hourly_sums["sensor.solar"][e2] = 30.0
hourly_sums["sensor.solar"][e2 - HOUR_S] = 29.0
hourly_sums["sensor.import"][e2] = 20.0
hourly_sums["sensor.import"][e2 - HOUR_S] = 16.0
hourly_sums["sensor.batt_charge"][e2] = 8.0
hourly_sums["sensor.batt_charge"][e2 - HOUR_S] = 8.0
hourly_sums["sensor.batt_discharge"][e2] = 3.0
hourly_sums["sensor.batt_discharge"][e2 - HOUR_S] = 3.0
# sensor.export has no entries at all for week 2 - that week's sample must
# be dropped, not treated as a 0 export delta.

result = usage_forecast.compute_usage_forecast(
    hourly_sums,
    import_entities=["sensor.import"],
    export_entities=["sensor.export"],
    solar_entities=["sensor.solar"],
    battery_charge_entity="sensor.batt_charge",
    battery_discharge_entity="sensor.batt_discharge",
    now=usage_now,
    forecast_hours=3,
    lookback_weeks=2,
)
check("compute_usage_forecast returns the requested number of hours", len(result) == 3)
check(
    "h0 averages only the complete week - the week with missing export data is skipped, not zeroed",
    result[0] == 3.7,
)
check("hours with no historical data at all fall back to 0.0", result[1] == 0.0 and result[2] == 0.0)

# Dual-tariff import + multiple solar arrays: every configured entity in a
# list is summed together for that term, so a 1-sensor or 2-sensor meter
# both work without the user needing to pre-combine them.
hourly_sums["sensor.import_t1"] = {e1: 10.0, e1 - HOUR_S: 8.0}  # delta 2.0
hourly_sums["sensor.import_t2"] = {e1: 6.0, e1 - HOUR_S: 4.5}  # delta 1.5
hourly_sums["sensor.solar_array2"] = {e1: 5.0, e1 - HOUR_S: 4.0}  # delta 1.0
multi_result = usage_forecast.compute_usage_forecast(
    hourly_sums,
    import_entities=["sensor.import_t1", "sensor.import_t2"],
    export_entities=[],
    solar_entities=["sensor.solar_array2"],
    battery_charge_entity=None,
    battery_discharge_entity=None,
    now=usage_now,
    forecast_hours=1,
    lookback_weeks=1,
)
check("multiple import/solar entities in one category are summed together", multi_result[0] == 4.5)

# ---------------------------------------------------------------------------
# usage_forecast.py - direct consumption-meter usage forecast (no
# solar/import/export/battery balance identity involved at all)
# ---------------------------------------------------------------------------
consumption_sums = {"sensor.consumption": {}, "sensor.consumption_annex": {}}
# 1 week back: two consumption sensors (e.g. main house + a separate annex
# submeter) - their deltas should simply be summed, same as a multi-entity
# import/solar list in the calculated path above.
consumption_sums["sensor.consumption"][e1] = 40.0
consumption_sums["sensor.consumption"][e1 - HOUR_S] = 38.5  # delta 1.5
consumption_sums["sensor.consumption_annex"][e1] = 12.2
consumption_sums["sensor.consumption_annex"][e1 - HOUR_S] = 12.0  # delta 0.2
# 2 weeks back: missing entirely for the annex meter - that week must be
# dropped from the average, not treated as a 0 contribution from it.
consumption_sums["sensor.consumption"][e2] = 25.0
consumption_sums["sensor.consumption"][e2 - HOUR_S] = 24.0  # delta 1.0

consumption_result = usage_forecast.compute_usage_forecast_from_consumption(
    consumption_sums,
    consumption_entities=["sensor.consumption", "sensor.consumption_annex"],
    now=usage_now,
    forecast_hours=3,
    lookback_weeks=2,
)
check("compute_usage_forecast_from_consumption returns the requested number of hours", len(consumption_result) == 3)
check(
    "h0 sums both consumption sensors and averages only the complete week",
    consumption_result[0] == 1.7,
)
check(
    "compute_usage_forecast_from_consumption needs no solar/import/export/battery entities at all",
    consumption_result[1] == 0.0 and consumption_result[2] == 0.0,
)

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED:")
    for f in FAILURES:
        print(f" - {f}")
    sys.exit(1)
else:
    print("All checks passed.")
