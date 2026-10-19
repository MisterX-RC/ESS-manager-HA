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
control = _load("control")
forecasting = _load("forecasting")
plans = _load("plans")
display = _load("display")
ev = _load("ev")
usage_forecast = _load("usage_forecast")
transport = _load("transport")

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

usage = [1.0] * 121  # a flat 1 kWh/h household usage forecast

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
    battery_now_kwh=10.0,
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
    battery_now_kwh=10.0,
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
    battery_now_kwh=10.0,
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
    battery_now_kwh=10.0,  # unchanged from low_plan's own reading, well under its target_energy_kwh (30.0) - target_reached must stay False so this stays a pure echo
)
check("an active plan locks in and ignores new input mid-window", locked_again == low_plan)

# Live report (v0.2.3): the forecast first dips under the 3.0 kWh threshold
# at hour 14 (2.89) but keeps falling to -0.38 at hour 19 before solar
# recovers it at hour 23. The plan used to size the charge against the
# first-crossing hour only (a 0.11 kWh "charge"); it must cover the lowest
# point of the dip (3.0 - -0.38 = 3.38 kWh), with the deadline still at the
# first crossing.
live_dip_forecast = [7.81, 9.11, 9.93, 10.61, 10.74, 9.83, 8.67, 7.14, 6.13, 5.56, 5.01, 4.45, 3.91, 3.4,
                     2.89, 2.37, 1.85, 1.33, 0.66, -0.38, -0.18, 0.55, 1.91, 4.44, 7.09, 10.01]
live_dip_plan = plans.compute_low_charge_plan(
    None,
    cur_unit=48,
    forecast_with_spike=live_dip_forecast,
    now=now_top_of_hour,
    charge_speed_kw=10.0,
    low_threshold_kwh=3.0,
    minimum_charge_target_kwh=3.0,
    upper_limit_kwh=10.74,  # no headroom term, so the dip alone decides target_kwh
    usage=usage_flat,
    all_price=[0.20] * 192,
    planning_horizon_hours=72,
    battery_now_kwh=7.38,
)
check(
    "low charge plan sizes the charge against the dip's lowest point, not the first hour it crosses the threshold",
    live_dip_plan["dip_min_kwh"] == -0.38 and live_dip_plan["deficit_kwh"] == 3.38 and live_dip_plan["target_kwh"] == 3.38,
)
check(
    "low charge plan's deadline (breach_unit) is still the dip's first crossing",
    live_dip_plan["breach_unit"] == 48 + 4 + 14 * 4,
)
# A separate, later dip (after the forecast climbs back above the threshold)
# must NOT inflate this plan - it gets its own plan once this one is behind us.
two_dip_forecast = [8.0] * 3 + [2.5, 2.0, 2.5] + [8.0] * 5 + [-5.0] + [8.0] * 5
two_dip_plan = plans.compute_low_charge_plan(
    None,
    cur_unit=0,
    forecast_with_spike=two_dip_forecast,
    now=now_top_of_hour,
    charge_speed_kw=10.0,
    low_threshold_kwh=3.0,
    minimum_charge_target_kwh=3.0,
    upper_limit_kwh=8.0,
    usage=usage_flat,
    all_price=[0.20] * 192,
    planning_horizon_hours=72,
    battery_now_kwh=8.0,
)
check(
    "low charge plan only sizes against the first dip, not a separate later one",
    two_dip_plan["dip_min_kwh"] == 2.0 and two_dip_plan["deficit_kwh"] == 1.0,
)

# ---------------------------------------------------------------------------
# plans.py - live-target early stop (target_energy_kwh / target_reached)
# ---------------------------------------------------------------------------
# low_plan's own target_energy_kwh is 30.0 (battery_now_kwh=10.0 + target_kwh=20.0,
# see the comment on its battery_now_kwh= above). Feeding that reading back in
# while still inside the window must latch target_reached, still echoing every
# other field from prev unchanged.
low_plan_target_reached = plans.compute_low_charge_plan(
    low_plan,
    cur_unit=low_plan["start_unit"],
    forecast_with_spike=[999.0] * 25,  # deliberately different input data - must be ignored
    now=now_top_of_hour,
    charge_speed_kw=7.0,
    low_threshold_kwh=3.0,
    minimum_charge_target_kwh=5.0,
    upper_limit_kwh=30.0,
    usage=usage_flat,
    all_price=all_price,
    planning_horizon_hours=72,
    battery_now_kwh=low_plan["target_energy_kwh"],
)
check(
    "compute_low_charge_plan latches target_reached once battery_now_kwh reaches target_energy_kwh mid-window",
    low_plan_target_reached == {**low_plan, "target_reached": True},
)

# Once latched, a later cycle reporting a lower battery_now_kwh (e.g. a
# setpoint-readback dip right after stopping) must NOT unlatch it - the plan
# keeps echoing target_reached=True for the rest of the window.
low_plan_stays_latched = plans.compute_low_charge_plan(
    low_plan_target_reached,
    cur_unit=low_plan["start_unit"],
    forecast_with_spike=[999.0] * 25,
    now=now_top_of_hour,
    charge_speed_kw=7.0,
    low_threshold_kwh=3.0,
    minimum_charge_target_kwh=5.0,
    upper_limit_kwh=30.0,
    usage=usage_flat,
    all_price=all_price,
    planning_horizon_hours=72,
    battery_now_kwh=low_plan["target_energy_kwh"] - 5.0,  # dipped back below target
)
check(
    "compute_low_charge_plan's target_reached latch survives a later reading dropping back below target_energy_kwh",
    low_plan_stays_latched == low_plan_target_reached,
)

# Mirror both cases for compute_high_discharge_plan (high_plan's own
# target_energy_kwh is 3.0: battery_now_kwh=10.0 - surplus=7.0).
high_plan_target_reached = plans.compute_high_discharge_plan(
    high_plan,
    cur_unit=high_plan["start_unit"],
    forecast_with_spike=[999.0] * 25,
    now=now_top_of_hour,
    discharge_speed_kw=10.0,
    high_threshold_kwh=33.0,
    low_threshold_kwh=3.0,
    usage=usage_flat,
    all_price=all_price,
    planning_horizon_hours=72,
    battery_now_kwh=high_plan["target_energy_kwh"],
)
check(
    "compute_high_discharge_plan latches target_reached once battery_now_kwh drops to target_energy_kwh mid-window",
    high_plan_target_reached == {**high_plan, "target_reached": True},
)

high_plan_stays_latched = plans.compute_high_discharge_plan(
    high_plan_target_reached,
    cur_unit=high_plan["start_unit"],
    forecast_with_spike=[999.0] * 25,
    now=now_top_of_hour,
    discharge_speed_kw=10.0,
    high_threshold_kwh=33.0,
    low_threshold_kwh=3.0,
    usage=usage_flat,
    all_price=all_price,
    planning_horizon_hours=72,
    battery_now_kwh=high_plan["target_energy_kwh"] + 5.0,  # bounced back above target
)
check(
    "compute_high_discharge_plan's target_reached latch survives a later reading rising back above target_energy_kwh",
    high_plan_stays_latched == high_plan_target_reached,
)

# compute_system_status must report "Stop" the moment target_reached is set,
# instead of riding out the rest of the window as "Actief"/"Start charge" (or
# the discharge equivalents) - this is the whole point of the second trigger.
status_low_target_reached = plans.compute_system_status(
    setpoint_w=4000.0,
    idle_setpoint_w=0.0,
    cur_unit=21,
    full={"active": False, "phase": None},
    neg={"active": False},
    spike={"active": False},
    low={"active": True, "start_unit": 20, "end_unit": 24, "breach_unit": 30, "target_reached": True},
    high={"active": False, "breach_unit": 999999},
    battery_now_kwh=10.0,
    low_threshold_kwh=3.0,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 96,
)
check(
    "system_status reports Stop for a low charge plan once target_reached, even mid-window with the setpoint still engaged",
    status_low_target_reached == "Stop",
)

status_high_target_reached = plans.compute_system_status(
    setpoint_w=-8000.0,
    idle_setpoint_w=0.0,
    cur_unit=21,
    full={"active": False, "phase": None},
    neg={"active": False},
    spike={"active": False},
    low={"active": False, "breach_unit": 999999},
    high={"active": True, "start_unit": 20, "end_unit": 24, "breach_unit": 30, "target_reached": True},
    battery_now_kwh=10.0,
    low_threshold_kwh=3.0,
    charge_speed_kw=7.0,
    discharge_speed_kw=10.0,
    all_price=[0.20] * 96,
)
check(
    "system_status reports Stop for a high discharge plan once target_reached, even mid-window with the setpoint still engaged",
    status_high_target_reached == "Stop",
)

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
    minimum_charge_target_kwh=5.0,
)
check("spike plan detects the qualifying spread", spike_plan["active"] is True)

# ---------------------------------------------------------------------------
# compute_spike_plan - a forecasted top-up smaller than minimum_charge_target_kwh
# is treated as "close enough to full" and not scheduled at all, same threshold
# the low charge plan uses to avoid trivial charges - added per Timo, who caught
# a live 1.16 kWh top-up (well under a 5.0 kWh minimum) showing up as a real
# "Start charge" trigger just to counteract a small forecasted pre-peak dip.
# ---------------------------------------------------------------------------
tiny_gap_forecast = [29.5] * 30  # only 0.5 kWh under upper_limit_kwh (30.0)
spike_plan_below_minimum = plans.compute_spike_plan(
    None,
    cur_unit=0,
    all_price=spike_price,
    battery_forecast=tiny_gap_forecast,
    usage=usage_flat,
    low_threshold_kwh=3.0,
    upper_limit_kwh=30.0,
    high_threshold_kwh=33.0,
    spike_margin=0.40,
    charge_speed_kw=7.0,
    spike_discharge_speed_kw=15.0,
    neg_plan={"active": False},
    minimum_charge_target_kwh=5.0,
)
check(
    "spike plan skips a sub-minimum top-up entirely (charge_needed_kwh forced to 0, zero-length window)",
    spike_plan_below_minimum["charge_needed_kwh"] == 0
    and spike_plan_below_minimum["charge_start_unit"] == spike_plan_below_minimum["charge_end_unit"],
)

spike_plan_above_minimum = plans.compute_spike_plan(
    None,
    cur_unit=0,
    all_price=spike_price,
    battery_forecast=[24.5] * 30,  # 5.5 kWh under upper_limit_kwh - just above the 5.0 minimum
    usage=usage_flat,
    low_threshold_kwh=3.0,
    upper_limit_kwh=30.0,
    high_threshold_kwh=33.0,
    spike_margin=0.40,
    charge_speed_kw=7.0,
    spike_discharge_speed_kw=15.0,
    neg_plan={"active": False},
    minimum_charge_target_kwh=5.0,
)
check(
    "spike plan still schedules a genuine top-up once it clears the minimum",
    spike_plan_above_minimum["charge_needed_kwh"] == 5.5
    and spike_plan_above_minimum["charge_start_unit"] < spike_plan_above_minimum["charge_end_unit"],
)

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

# compose_forecast_adjusted must use the plan's own target_kwh, not its
# effective_discharge_per_unit/effective_charge_per_unit rate - a live report
# showed a genuine 0.09 kWh discharge target (against a much larger
# effective_discharge_per_unit, since units_needed always rounds up to at
# least one whole 15-minute unit) rendering as a ~2.72 kWh drop on the SOC
# forecast/chart - an apparent undershoot that never actually happens once
# the live target-energy stop (commit 39) halts the real discharge at 0.09
# kWh. A tiny target_kwh over a whole-unit window must show up as only that
# tiny amount, not the full per-unit rate times the window length.
adjusted_undersized_discharge = plans.compose_forecast_adjusted(
    [10.0] * 4,
    {"active": False},
    {
        "active": True,
        "start_unit": 0,
        "end_unit": 1,
        "target_kwh": 0.09,
        "effective_discharge_per_unit": 2.7183,
    },
    cur_unit=0,
    now=now_top_of_hour,
)
check(
    "forecast_adjusted charts an undersized discharge plan's real target_kwh, not its whole-unit effective rate (no phantom overshoot/undershoot)",
    adjusted_undersized_discharge == [9.91, 9.91, 9.91, 9.91],
)

adjusted_undersized_charge = plans.compose_forecast_adjusted(
    [10.0] * 4,
    {
        "active": True,
        "start_unit": 0,
        "end_unit": 1,
        "target_kwh": 0.12,
        "effective_charge_per_unit": 1.75,
    },
    {"active": False},
    cur_unit=0,
    now=now_top_of_hour,
)
check(
    "forecast_adjusted mirrors the same fix for an undersized low charge plan",
    adjusted_undersized_charge == [10.12, 10.12, 10.12, 10.12],
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

# Holding (the balancing wait) reports like the charging phase, as of
# v0.5.11: "Start charge" until the setpoint readback shows the charge
# applied, then "Actief" (up to v0.5.10 it always said "Start charge").
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
    "system_status shows Start charge while holding with zero setpoint readback",
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
    "system_status shows Actief while holding once the setpoint readback has ramped up",
    status_holding_with_setpoint == "Actief",
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
    battery_now_kwh=6.0,  # irrelevant: suppress_new short-circuits before this is used
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
    battery_now_kwh=discharge_forecast_with_spike[0],
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
    # Same reading as unsuppressed_discharge_plan's own - stays above its
    # target_energy_kwh (target not yet reached), so target_reached is
    # still False on both sides and the exact-equality check below holds.
    battery_now_kwh=discharge_forecast_with_spike[0],
    suppress_new=True,
)
check(
    "compute_high_discharge_plan's suppress_new doesn't cut off a discharge window already locked in and in progress",
    locked_in_discharge_plan == unsuppressed_discharge_plan,
)

# The discharge plan's low-threshold cap must only count low points from the
# sale onward. Live report (15 kWh battery, thresholds 4.5/16.5, 3 kW
# discharge): the lowest point anywhere was 5.34 kWh at 05:00, capping the
# sale at 0.84 kWh - but the sale itself was at 19:45 that evening, and the
# lowest point after it was 9.5 kWh, leaving room for the full 1.79 kWh.
live_sale_forecast = [7.55, 8.01, 8.19, 7.99, 7.3, 6.76, 6.44, 6.27, 6.18, 6.1, 6.02, 5.94, 5.85, 5.77, 5.7, 5.63,
                      5.5, 5.34, 6.02, 7.31, 8.65, 10.08, 11.39, 12.49, 13.16, 13.42, 13.32, 12.9, 12.05, 11.43, 10.9,
                      10.61, 10.51, 10.41, 10.32, 10.24, 10.15, 10.06, 9.98, 9.91, 9.72, 9.5, 10.3, 11.69, 13.21, 14.81,
                      16.18, 17.34, 18.07, 18.29, 18.1, 17.66, 17.01, 16.6, 16.27, 15.89, 15.74, 15.65, 15.58, 15.51,
                      15.42, 15.34, 15.27, 15.2, 15.13, 15.06, 14.98, 14.97, 15.17, 15.22, 15.47, 15.6, 15.94, 16.11]
live_sale_prices = [0.10] * 192
live_sale_prices[174:177] = [0.259, 0.288, 0.273]  # the evening's priciest 45 minutes, well after the 05:00 low point
live_sale_plan = plans.compute_high_discharge_plan(
    None,
    cur_unit=59,
    forecast_with_spike=live_sale_forecast,
    now=datetime(2026, 9, 23, 14, 49),
    discharge_speed_kw=3.0,
    high_threshold_kwh=16.5,
    low_threshold_kwh=4.5,
    usage=[0.234] * 121,
    all_price=live_sale_prices,
    planning_horizon_hours=72,
    battery_now_kwh=7.46,
)
check(
    "discharge plan ignores low points before the sale: sells the full 1.79 kWh surplus at 19:30-20:15, not a 0.84 kWh capped amount",
    live_sale_plan["surplus_kwh"] == 1.79
    and live_sale_plan["capped_by_low_limit"] is False
    and live_sale_plan["low_point_after_sale_kwh"] == 9.5
    and live_sale_plan["start_unit"] == 174,
)

# ...but a low point AFTER the sale still caps it: priciest slot in hour 0,
# followed by a 6.0 kWh night dip before the peak (20.0 vs a 16.5 ceiling).
dip_after_sale_prices = [0.50] * 4 + [0.10] * 44
dip_after_sale_plan = plans.compute_high_discharge_plan(
    None,
    cur_unit=0,
    forecast_with_spike=[10.0, 10.0, 6.0, 6.0, 6.0, 6.0, 12.0, 18.0, 20.0],
    now=now_top_of_hour,
    discharge_speed_kw=10.0,
    high_threshold_kwh=16.5,
    low_threshold_kwh=4.5,
    usage=usage_flat,
    all_price=dip_after_sale_prices,
    planning_horizon_hours=72,
    battery_now_kwh=10.0,
)
check(
    "discharge plan still caps a sale by a low point that comes after it (6.0 - 4.5 = 1.5 kWh in the pricey hour 0)",
    dip_after_sale_plan["start_unit"] == 0 and dip_after_sale_plan["block_kwh"] == 1.5
    and dip_after_sale_plan["low_point_after_sale_kwh"] == 6.0,
)
# 2026.10.10 (blocks): the rest of the surplus is sold after that low point - the full 3.5 kWh in total
check(
    "discharge plan sells the rest after the low point in a second block (3.5 kWh in total, not capped)",
    dip_after_sale_plan["surplus_kwh"] == 3.5 and dip_after_sale_plan["capped_by_low_limit"] is False
    and len(dip_after_sale_plan["blocks"]) == 2 and dip_after_sale_plan["blocks"][1]["start_unit"] >= 20
    and dip_after_sale_plan["blocks"][1]["kwh"] == 2.0,
)

# The sale floor is the low threshold + the Safety buffer (v0.2.17): with a
# 0.5 kWh buffer the same scenario may only sell down to 5.0, so
# 6.0 - 5.0 = 1.0 kWh - never down to the bare 4.5 kWh low threshold.
dip_after_sale_mct_plan = plans.compute_high_discharge_plan(
    None,
    cur_unit=0,
    forecast_with_spike=[10.0, 10.0, 6.0, 6.0, 6.0, 6.0, 12.0, 18.0, 20.0],
    now=now_top_of_hour,
    discharge_speed_kw=10.0,
    high_threshold_kwh=16.5,
    low_threshold_kwh=4.5,
    usage=usage_flat,
    all_price=dip_after_sale_prices,
    planning_horizon_hours=72,
    battery_now_kwh=10.0,
    safety_buffer_kwh=0.5,
)
check(
    "discharge plan never sells into the safety buffer above the low threshold (1.0 kWh, not 1.5)",
    dip_after_sale_mct_plan["block_kwh"] == 1.0 and dip_after_sale_mct_plan["sale_floor_kwh"] == 5.0,
)
# ...and no buffer sells right down to the low threshold.
dip_after_sale_low_mct_plan = plans.compute_high_discharge_plan(
    None,
    cur_unit=0,
    forecast_with_spike=[10.0, 10.0, 6.0, 6.0, 6.0, 6.0, 12.0, 18.0, 20.0],
    now=now_top_of_hour,
    discharge_speed_kw=10.0,
    high_threshold_kwh=16.5,
    low_threshold_kwh=4.5,
    usage=usage_flat,
    all_price=dip_after_sale_prices,
    planning_horizon_hours=72,
    battery_now_kwh=10.0,
    safety_buffer_kwh=0.0,
)
check(
    "discharge plan's sale floor is the bare low threshold with no safety buffer",
    dip_after_sale_low_mct_plan["block_kwh"] == 1.5 and dip_after_sale_low_mct_plan["sale_floor_kwh"] == 4.5,
)

# When the priciest slot sits just before a low point that almost blocks the
# sale, selling after that low point instead (a cheaper slot) can sell the
# full surplus - that option wins.
after_dip_plan = plans.compute_high_discharge_plan(
    None,
    cur_unit=0,
    forecast_with_spike=[8.0, 4.6, 8.0, 12.0, 18.0, 20.0, 19.0],
    now=now_top_of_hour,
    discharge_speed_kw=10.0,
    high_threshold_kwh=16.5,
    low_threshold_kwh=4.5,
    usage=usage_flat,
    all_price=dip_after_sale_prices,
    planning_horizon_hours=72,
    battery_now_kwh=8.0,
)
check(
    "discharge plan moves the sale after a blocking low point when that lets it sell the full surplus",
    after_dip_plan["surplus_kwh"] == 3.5 and after_dip_plan["capped_by_low_limit"] is False
    and after_dip_plan["blocks"][-1]["start_unit"] >= 8 and after_dip_plan["blocks"][-1]["kwh"] >= 3.4,
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

# ---------------------------------------------------------------------------
# usage_forecast.py - Energy-dashboard usage source: mapping HA's Energy
# dashboard preferences onto the energy-balance identity's statistic lists
# ---------------------------------------------------------------------------
# Legacy grid shape: one "grid" entry with flow_from/flow_to arrays (here a
# dual-tariff meter - two imports, two exports).
legacy_prefs = {
    "energy_sources": [
        {
            "type": "grid",
            "flow_from": [{"stat_energy_from": "sensor.import_t1"}, {"stat_energy_from": "sensor.import_t2"}],
            "flow_to": [{"stat_energy_to": "sensor.export_t1"}, {"stat_energy_to": "sensor.export_t2"}],
        },
        {"type": "solar", "stat_energy_from": "sensor.solar"},
        {"type": "battery", "stat_energy_from": "sensor.batt_discharge", "stat_energy_to": "sensor.batt_charge"},
        {"type": "gas", "stat_energy_from": "sensor.gas"},
    ],
    "device_consumption": [{"stat_consumption": "sensor.fridge"}],
}
check(
    "energy_prefs_to_sources maps the legacy flow_from/flow_to grid shape, solar and battery (battery from = discharge, to = charge), and ignores gas/devices",
    usage_forecast.energy_prefs_to_sources(legacy_prefs)
    == {
        "import": ["sensor.import_t1", "sensor.import_t2"],
        "export": ["sensor.export_t1", "sensor.export_t2"],
        "solar": ["sensor.solar"],
        "battery_charge": ["sensor.batt_charge"],
        "battery_discharge": ["sensor.batt_discharge"],
    },
)

# Current grid shape: one "grid" entry per connection, stat_energy_from/_to
# directly on it (export optional); multiple solar arrays and batteries;
# an external statistic id (colon form) passes straight through.
unified_prefs = {
    "energy_sources": [
        {"type": "grid", "stat_energy_from": "tibber:energy_consumption", "stat_energy_to": "sensor.export"},
        {"type": "grid", "stat_energy_from": "sensor.import_annex"},
        {"type": "solar", "stat_energy_from": "sensor.solar_east"},
        {"type": "solar", "stat_energy_from": "sensor.solar_west"},
        {"type": "battery", "stat_energy_from": "sensor.b1_out", "stat_energy_to": "sensor.b1_in"},
        {"type": "battery", "stat_energy_from": "sensor.b2_out", "stat_energy_to": "sensor.b2_in"},
        {"type": "water", "stat_energy_from": "sensor.water"},
    ],
}
check(
    "energy_prefs_to_sources maps the current one-entry-per-grid-connection shape, multiple solar arrays/batteries, and external statistic ids",
    usage_forecast.energy_prefs_to_sources(unified_prefs)
    == {
        "import": ["tibber:energy_consumption", "sensor.import_annex"],
        "export": ["sensor.export"],
        "solar": ["sensor.solar_east", "sensor.solar_west"],
        "battery_charge": ["sensor.b1_in", "sensor.b2_in"],
        "battery_discharge": ["sensor.b1_out", "sensor.b2_out"],
    },
)
check(
    "energy_prefs_to_sources returns empty lists (not a crash) when the Energy dashboard can't be read or is unconfigured",
    usage_forecast.energy_prefs_to_sources(None)
    == {"import": [], "export": [], "solar": [], "battery_charge": [], "battery_discharge": []}
    and usage_forecast.energy_prefs_to_sources({"energy_sources": []})["import"] == [],
)
check(
    "energy_prefs_to_sources drops duplicates and blanks",
    usage_forecast.energy_prefs_to_sources(
        {
            "energy_sources": [
                {"type": "grid", "flow_from": [{"stat_energy_from": "sensor.import"}, {"stat_energy_from": ""}]},
                {"type": "grid", "stat_energy_from": "sensor.import", "stat_energy_to": None},
            ]
        }
    )["import"]
    == ["sensor.import"],
)

# End-to-end: the Energy-dashboard mapping fed into compute_usage_forecast
# gives exactly the same answer as the equivalent hand-picked config (week
# 1's complete sample from the calculated-usage fixtures above: 3.7).
dashboard_sources = usage_forecast.energy_prefs_to_sources(
    {
        "energy_sources": [
            {"type": "grid", "stat_energy_from": "sensor.import", "stat_energy_to": "sensor.export"},
            {"type": "solar", "stat_energy_from": "sensor.solar"},
            {"type": "battery", "stat_energy_from": "sensor.batt_discharge", "stat_energy_to": "sensor.batt_charge"},
        ]
    }
)
dashboard_result = usage_forecast.compute_usage_forecast(
    hourly_sums,
    dashboard_sources["import"],
    dashboard_sources["export"],
    dashboard_sources["solar"],
    dashboard_sources["battery_charge"],
    dashboard_sources["battery_discharge"],
    now=usage_now,
    forecast_hours=1,
    lookback_weeks=1,
)
check("the Energy-dashboard source gives the same usage as the equivalent hand-picked config", dashboard_result[0] == 3.7)

# Multiple batteries (only possible via the Energy dashboard): every
# battery's charge is subtracted and every battery's discharge added.
hourly_sums["sensor.batt2_charge"] = {e1: 3.5, e1 - HOUR_S: 3.0}  # delta 0.5
hourly_sums["sensor.batt2_discharge"] = {e1: 1.3, e1 - HOUR_S: 1.0}  # delta 0.3
two_battery_result = usage_forecast.compute_usage_forecast(
    hourly_sums,
    import_entities=["sensor.import"],
    export_entities=["sensor.export"],
    solar_entities=["sensor.solar"],
    battery_charge_entity=["sensor.batt_charge", "sensor.batt2_charge"],
    battery_discharge_entity=["sensor.batt_discharge", "sensor.batt2_discharge"],
    now=usage_now,
    forecast_hours=1,
    lookback_weeks=1,
)
# 2.0 solar + 3.0 import + (0.2 + 0.3) discharge - 0.5 export - (1.0 + 0.5) charge = 3.5
check("compute_usage_forecast sums every battery's charge/discharge when given lists", two_battery_result[0] == 3.5)

# Usage-forecast cache: h0 is the hour the forecast was computed in, so it
# must be recomputed exactly when the hour changes - not before (nothing it
# depends on changes within the hour), and not later (a live dump at 19:04
# still showed the 18:00 value at h0 under the old 55-minute age limit).
computed_1810 = datetime(2026, 9, 23, 18, 10)
check(
    "usage cache is still fresh later in the same hour, even past the old 55-minute limit",
    usage_forecast.usage_cache_is_stale(computed_1810, datetime(2026, 9, 23, 18, 59, 59)) is False,
)
check(
    "usage cache goes stale as soon as the hour changes",
    usage_forecast.usage_cache_is_stale(computed_1810, datetime(2026, 9, 23, 19, 0, 5)) is True,
)
check(
    "usage cache with no computation yet is stale",
    usage_forecast.usage_cache_is_stale(None, datetime(2026, 9, 23, 19, 4)) is True,
)

# ---------------------------------------------------------------------------
# Direct control (v0.2.14): the action behind the Status, and control.py
# ---------------------------------------------------------------------------
def _status_action(setpoint_w=0.0, cur_unit=21, full=None, neg=None, spike=None, low=None, high=None, idle_setpoint_w=0.0):
    return plans.compute_system_status_and_action(
        setpoint_w=setpoint_w,
        idle_setpoint_w=idle_setpoint_w,
        cur_unit=cur_unit,
        full=full or {"active": False, "phase": None},
        neg=neg or {"active": False},
        spike=spike or {"active": False},
        low=low or {"active": False, "breach_unit": 999999},
        high=high or {"active": False, "breach_unit": 999999},
        battery_now_kwh=10.0,
        low_threshold_kwh=3.0,
        charge_speed_kw=7.0,
        discharge_speed_kw=10.0,
        all_price=[0.20] * 96,
    )


LOW_WINDOW = {"active": True, "start_unit": 20, "end_unit": 24, "breach_unit": 30}
HIGH_WINDOW = {"active": True, "start_unit": 20, "end_unit": 24, "breach_unit": 30}
check("action: idle when nothing is going on", _status_action() == ("Standby", "idle"))
check("action: charge when a low charge window opens", _status_action(low=LOW_WINDOW) == ("Start charge", "charge"))
check(
    "action: 'Actief' in a charge window keeps charging",
    _status_action(setpoint_w=7000.0, low=LOW_WINDOW) == ("Actief", "charge"),
)
check(
    "action: 'Actief' in a discharge window keeps discharging",
    _status_action(setpoint_w=-10000.0, high=HIGH_WINDOW) == ("Actief", "discharge"),
)
check(
    "action: idle once the charge target is reached mid-window",
    _status_action(setpoint_w=7000.0, low={**LOW_WINDOW, "target_reached": True}) == ("Stop", "idle"),
)
check(
    "action: idle after the discharge window with the setpoint still engaged",
    _status_action(setpoint_w=-10000.0, cur_unit=25, high=HIGH_WINDOW) == ("Stop", "idle"),
)
NEG = {
    "active": True,
    "charge_start_unit": 40, "charge_end_unit": 44,
    "discharge_start_unit": 30, "discharge_end_unit": 32,
    "solar_export_start_unit": 34, "solar_export_end_unit": 36,
}
check("action: negative price charge", _status_action(cur_unit=41, neg=NEG)[1] == "negative_price_charge")
check("action: negative plan's pre-discharge is a normal discharge", _status_action(cur_unit=30, neg=NEG)[1] == "discharge")
check("action: negative plan's solar export is idle", _status_action(cur_unit=35, neg=NEG) == ("Solar export", "idle"))
SPIKE = {"active": True, "charge_start_unit": 10, "charge_end_unit": 12, "discharge_start_unit": 70, "discharge_end_unit": 72}
check("action: spike charge leg is a normal charge", _status_action(cur_unit=11, spike=SPIKE)[1] == "charge")
check("action: spike discharge", _status_action(cur_unit=70, spike=SPIKE) == ("Start spike discharge", "spike_discharge"))
check(
    "action: full charge holding keeps charging",
    _status_action(full={"active": True, "phase": "holding"}) == ("Start charge", "charge"),
)
check(
    "action: full charge scheduled is idle",
    _status_action(full={"active": True, "phase": "scheduled"}) == ("Full charge scheduled", "idle"),
)
check(
    "action: awaiting solar (full charge) is idle",
    _status_action(full={"active": False, "phase": None, "relying_on_peak_unit": 60}) == ("Awaiting solar (full charge)", "idle"),
)
check(
    "compute_system_status still returns only the Status string",
    plans.compute_system_status(0.0, 0.0, 21, {"active": False, "phase": None}, {"active": False}, {"active": False},
                                LOW_WINDOW, {"active": False, "breach_unit": 999999}, 10.0, 3.0, 7.0, 10.0, [0.2] * 96)
    == "Start charge",
)
check(
    "a non-zero idle value (-300 W) counts as idle for the Status",
    _status_action(setpoint_w=-300.0, cur_unit=25, low=LOW_WINDOW, idle_setpoint_w=-300.0) == ("Standby", "idle")
    and _status_action(setpoint_w=-300.0, cur_unit=25, low=LOW_WINDOW, idle_setpoint_w=0.0) == ("Stop", "idle"),
)

speeds = dict(charge_speed_kw=7.0, discharge_speed_kw=10.0, negative_price_charge_speed_kw=14.0,
              spike_discharge_speed_kw=15.0, max_charge_kw=10.0, max_discharge_kw=12.0)
check("power: charge uses the charge speed", control.action_power_kw("charge", **speeds) == 7.0)
check("power: discharge is negative at the discharge speed", control.action_power_kw("discharge", **speeds) == -10.0)
check("power: negative price charge is clamped to the max charge speed", control.action_power_kw("negative_price_charge", **speeds) == 10.0)
check("power: spike discharge is clamped to the max discharge speed", control.action_power_kw("spike_discharge", **speeds) == -12.0)
check("power: idle and unknown actions are 0", control.action_power_kw("idle", **speeds) == 0.0 and control.action_power_kw("bogus", **speeds) == 0.0)
check("output: W, charge positive", control.command_value("charge", 7.0, "W", "charge_positive", 0) == 7000.0)
check("output: kW, discharge positive", control.command_value("discharge", -10.0, "kW", "discharge_positive", 0) == 10.0)
check("output: idle sends the idle value as-is", control.command_value("idle", 0.0, "W", "discharge_positive", -30) == -30.0)
check("output: no negative zero", str(control.power_to_output(0.0, "kW", "discharge_positive")) == "0.0")
check("readback: output_to_power_w reverses the conversion", control.output_to_power_w(10.0, "kW", "discharge_positive") == -10000.0)
check("readback (v0.3.4): a kW input_number/number reads as W", control.readback_to_watts(7, "kW") == 7000.0)
check("readback (v0.3.4): negative kW (discharging) reads as W", control.readback_to_watts(-10, "kW") == -10000.0)
check("readback (v0.3.4): W stays W", control.readback_to_watts(500, "W") == 500.0)
check("readback (v0.3.4): no unit is taken as W", control.readback_to_watts(500, None) == 500.0)
check("readback (v0.3.4): polarity 'positive = discharge' is flipped", control.readback_to_watts(-7, "kW", "discharge_positive") == 7000.0)
check("readback (v0.3.4): polarity 'positive = charge' is kept", control.readback_to_watts(-7, "kW", "charge_positive") == -7000.0)
check("clamp: inside a number entity's min/max", control.clamp_to_range(20000, -15000, 15000) == 15000)
check("tolerance: half the entity's step", control.write_tolerance(100.0, 10) == 5.0)
check("needs_write: first send", control.needs_write(7000, None, 0, 0.5, None) is True)
check("needs_write: new value", control.needs_write(-10000, 7000, 7000, 0.5, 5) is True)
check("needs_write: entity already has it", control.needs_write(7000, 7000, 7000, 0.5, 5) is False)
check("needs_write: changed by someone else, too soon", control.needs_write(7000, 7000, 0, 0.5, 30) is False)
check("needs_write: changed by someone else, re-send after a minute", control.needs_write(7000, 7000, 0, 0.5, 61) is True)
check("needs_write: script (no readback) only on change", control.needs_write(7000, 7000, None, 1e-6, 999) is False)

# ---------------------------------------------------------------------------
# High discharge plan: a capped evening sale vs. the fallback after the
# overnight low point is compared by revenue, not kWh (v0.2.16). Live dump
# 2026-09-24 15:27: the evening window (18:45, avg 0.267) is capped from
# 18.65 to 18.23 kWh by the 07:00 low point; the fallback (tomorrow 08:00,
# avg 0.210) sells the full 18.65 but earns less - it used to win anyway.
# ---------------------------------------------------------------------------
_d924 = {}
exec('price="""0.176 0.147 0.149 0.15 0.151 0.156 0.152 0.152 0.122 0.126 0.135 0.139 0.151 0.153 0.155 0.153 0.155 0.153 0.154 0.154 0.151 0.155 0.16 0.167 0.155 0.169 0.178 0.192 0.206 0.221 0.227 0.218 0.221 0.214 0.204 0.187 0.194 0.177 0.144 0.129 0.135 0.121 0.106 0.099 0.101 0.098 0.078 0.064 0.054 0.056 0.05 0.052 0.043 0.037 0.037 0.041 0.03 0.035 0.04 0.051 0.043 0.07 0.097 0.11 0.086 0.109 0.132 0.155 0.134 0.163 0.182 0.207 0.177 0.209 0.236 0.262 0.25 0.264 0.268 0.288 0.273 0.266 0.254 0.248 0.24 0.23 0.223 0.21 0.221 0.205 0.201 0.193 0.197 0.189 0.186 0.181 0.197 0.184 0.176 0.171 0.175 0.172 0.171 0.17 0.167 0.166 0.165 0.162 0.164 0.165 0.165 0.164 0.165 0.161 0.16 0.159 0.158 0.16 0.168 0.177 0.167 0.177 0.183 0.193 0.199 0.202 0.204 0.226 0.221 0.222 0.21 0.198 0.23 0.202 0.189 0.158 0.179 0.162 0.148 0.131 0.133 0.119 0.099 0.072 0.083 0.063 0.053 0.047 0.044 0.041 0.031 0.024 0.028 0.04 0.045 0.061 0.044 0.074 0.104 0.122 0.116 0.133 0.153 0.179 0.156 0.19 0.201 0.234 0.201 0.23 0.248 0.283 0.285 0.298 0.308 0.299 0.27 0.255 0.247 0.237 0.244 0.231 0.218 0.203 0.22 0.209 0.202 0.195 0.2 0.189 0.166 0.153"""\nfws="""28.04 29.91 30.36 30.28 28.49 27.59 26.82 26.26 25.7 25.17 24.64 24.12 23.61 23.1 22.56 21.89 21.23 21.82 22.86 24.41 26.91 30.12 33.41 36.07 38.95 41.37 42.79 43.76 42.97 42.23 41.64 41.06 40.53 40.02 39.51 39.03 38.53 38.02 37.48 36.81 36.24 35.73 35.73 36.59 38.23 40.17 42.34 44.56 46.97 48.83 49.53 49.21 48.27 47.6 47.01 46.48 45.97 45.47 44.97 44.48 43.99 43.5 42.97 42.38 41.85 41.42 41.56 42.8 44.79 46.85 48.87 49.8 51.65 53.13 53.45 52.74 51.64 50.86 50.24 49.58 49.03 48.51 48.01 47.49 46.99 46.49 45.96 45.28 44.52 44.32 44.99 46.21 48.2 50.64 51.57 49.46 51.24 52.25 51.52 50.74 49.37 48.8 48.26 47.72 47.17 46.65 46.15 45.66 45.16 44.66 44.14 43.57 42.49 41.81 41.17 40.39 39.64 38.99 38.37 37.59 36.84"""\nusage="""1.567 1.481 2.26 1.184 1.824 0.898 0.775 0.561 0.551 0.538 0.524 0.519 0.514 0.506 0.547 0.667 0.756 0.59 0.704 0.846 0.854 0.783 1.002 1.535 0.915 1.081 1.529 0.959 1.002 0.739 0.589 0.58 0.529 0.516 0.502 0.487 0.499 0.506 0.538 0.669 0.589 0.687 0.723 0.622 0.529 0.732 0.949 1.103 0.644 0.731 1.077 0.81 0.964 0.677 0.59 0.53 0.504 0.498 0.508 0.482 0.492 0.489 0.532 0.593 0.546 1.031 1.257 0.839 0.642 0.899 1.208 2.212 0.821 0.876 1.292 1.115 1.118 0.779 0.621 0.656 0.552 0.52 0.505 0.514 0.502 0.505 0.528 0.677 0.777 0.556 0.547 0.618 0.535 0.679 2.212 5.069 0.742 0.665 1.48 0.94 1.379 0.572 0.541 0.541 0.546 0.522 0.5 0.492 0.495 0.503 0.522 0.568 1.084 0.679 0.636 0.783 0.752 0.642 0.626 0.775 0.751"""\nall_price=[float(x) for x in price.split()]\nforecast=[float(x) for x in fws.split()]\nusage=[float(x) for x in usage.split()]\n', _d924)
plan_0924 = plans.compute_high_discharge_plan(
    None, 61, _d924["forecast"], datetime(2026, 9, 24, 15, 27), 10.0, 33.0, 3.0,
    _d924["usage"], _d924["all_price"], 72, 26.82, False, 0.0,
)
check("capped evening sale wins over a bigger but cheaper morning sale (starts today 18:45)", plan_0924["start_unit"] == 75)
check("the evening block is capped by the overnight low point (18.23 kWh)", plan_0924["block_kwh"] == 18.23)
check("the evening block keeps the battery above the floor after it", plan_0924["low_point_after_sale_kwh"] - plan_0924["block_kwh"] >= 3.0)
check("2026.10.10 (blocks): the remaining 0.42 kWh is sold after the low point (tomorrow), 18.65 kWh in total",
      plan_0924["surplus_kwh"] == 18.65 and not plan_0924["capped_by_low_limit"] and len(plan_0924["blocks"]) == 2
      and plan_0924["blocks"][1]["start_unit"] >= 128 and plan_0924["blocks"][1]["kwh"] == 0.42)

# The fallback still wins when it earns more. Cap every price before
# tomorrow 08:00 at X: the capped evening sale earns 18.23 * X, the full
# 18.65 kWh at tomorrow 08:00 earns 3.922 - so X = 0.214 (3.90) must pick
# tomorrow, X = 0.216 (3.94) must still pick this evening.
def _plan_with_cap(x):
    prices = list(_d924["all_price"])
    for u in range(61, 128):
        prices[u] = min(prices[u], x)
    return plans.compute_high_discharge_plan(
        None, 61, _d924["forecast"], datetime(2026, 9, 24, 15, 27), 10.0, 33.0, 3.0,
        _d924["usage"], prices, 72, 26.82, False, 0.0,
    )


def _blocks_revenue(plan, prices):
    return sum(b["kwh"] * sum(prices[b["start_unit"]:b["end_unit"]]) / (b["end_unit"] - b["start_unit"]) for b in plan["blocks"])


# 2026.10.10 (blocks): no longer either/or - the blocks earn at least what the better single option did
for _x in (0.214, 0.216):
    _px = list(_d924["all_price"])
    for _u in range(61, 128):
        _px[_u] = min(_px[_u], _x)
    _plan_x = _plan_with_cap(_x)
    check(f"blocks earn at least the best single window (prices before tomorrow 08:00 capped at {_x})",
          _plan_x["surplus_kwh"] == 18.65 and _blocks_revenue(_plan_x, _px) >= max(3.922, 18.23 * _x) - 0.01)

# ---------------------------------------------------------------------------
# v0.2.17: Minimum charge target = the smallest amount a charge buys; the
# low charge plan lifts the dip to the low threshold and rounds a smaller
# need UP to the minimum (capped so the later peak stays under the high
# threshold). Selling uses the separate Safety buffer.
# ---------------------------------------------------------------------------
def _small_dip_plan(minimum, high_threshold):
    return plans.compute_low_charge_plan(
        None,
        cur_unit=0,
        forecast_with_spike=[5.0, 4.0, 3.5, 2.5, 2.8, 4.0, 6.0, 8.0],
        now=datetime(2026, 9, 24, 0, 0),
        charge_speed_kw=4.0,
        low_threshold_kwh=3.0,
        minimum_charge_target_kwh=minimum,
        upper_limit_kwh=8.0,  # future peak == upper limit -> no headroom term
        usage=[0.5] * 10,
        all_price=[0.2] * 96,
        planning_horizon_hours=72,
        battery_now_kwh=5.0,
        high_threshold_kwh=high_threshold,
    )


_p_min2 = _small_dip_plan(2.0, 12.0)
check("low charge lifts the dip to the low threshold (deficit 0.5 kWh)", _p_min2["deficit_kwh"] == 0.5)
check("a 0.5 kWh need is rounded up to the 2 kWh minimum charge", _p_min2["target_kwh"] == 2.0 and _p_min2["rounded_up_to_minimum"] is True)
_p_cap = _small_dip_plan(2.0, 9.0)
check("rounding up stops where the later peak would cross the high threshold (9 - 8 = 1 kWh)", _p_cap["target_kwh"] == 1.0)
_p_min0 = _small_dip_plan(0.0, 12.0)
check("no minimum: buys just the deficit", _p_min0["target_kwh"] == 0.5 and _p_min0["rounded_up_to_minimum"] is False)
_p_big = _small_dip_plan(0.3, 12.0)
check("a need above the minimum isn't changed", _p_big["target_kwh"] == 0.5 and _p_big["rounded_up_to_minimum"] is False)

# ---------------------------------------------------------------------------
# v0.2.18: battery_forecast_adjusted draws a running window by what's really
# left (distance to target_energy_kwh), and takes the house use during a
# window into account (the stop is a battery level, the forecast already
# subtracts house use). Live dump 2026-09-24 20:07, mid-sale.
# ---------------------------------------------------------------------------
_f2007 = [18.2, 17.42, 16.86, 16.31, 15.77, 15.25, 14.73, 14.21, 13.71, 13.16, 12.49, 11.81, 12.37, 13.38, 14.92]
_high2007 = {
    "active": True, "surplus_kwh": 16.1, "target_kwh": 16.1, "avg_home_load_kw": 0.735,
    "effective_discharge_per_unit": 2.6837, "start_unit": 77, "end_unit": 83, "units_needed": 6,
    "target_energy_kwh": 13.15, "target_reached": False,
}
_now2007 = datetime(2026, 9, 24, 20, 7)
_adj2007 = plans.compose_forecast_adjusted(
    _f2007, {"active": False}, _high2007, 80, _now2007, battery_now_kwh=18.99
)
# 5.84 kWh left to the target, ~0.40 of it is house use already in the
# forecast -> 5.44 below the 11.81 no-sale low point = 6.37 (was drawn as 3.76).
check("running sale draws only what's left to its target (07:00 low 6.37, not 3.76)", _adj2007[11] == 6.37)
check("running sale's remainder all lands in the current hour", _adj2007[0] == round(18.2 - (5.84 - 0.735 / 4 * 5.84 / 2.6837), 2))
_adj2007_done = plans.compose_forecast_adjusted(
    _f2007, {"active": False}, {**_high2007, "target_reached": True}, 82, _now2007, battery_now_kwh=13.1
)
check("a sale that reached its target draws nothing more", _adj2007_done == _f2007)
# Before the window starts: target_kwh minus the house use while it runs.
_adj_pre = plans.compose_forecast_adjusted(
    [20.0] * 4, {"active": False}, {**_high2007, "start_unit": 81, "end_unit": 87}, 80, datetime(2026, 9, 24, 20, 0),
    battery_now_kwh=29.0,
)
_units = 16.1 / 2.6837
check("a planned sale is drawn as target minus house use during it", _adj_pre[-1] == round(20.0 - (16.1 - 0.735 / 4 * _units), 2))
# Charging mirrors it: house use during the window adds to the lift.
_low_run = {
    "active": True, "target_kwh": 4.0, "avg_home_load_kw": 0.8, "effective_charge_per_unit": 1.8,
    "start_unit": 78, "end_unit": 81, "target_energy_kwh": 9.0, "target_reached": False,
}
_adj_chg = plans.compose_forecast_adjusted(
    [6.0, 5.5, 5.0], _low_run, {"active": False}, 80, datetime(2026, 9, 24, 20, 0), battery_now_kwh=8.1
)
_left = 0.9
check("running charge draws what's left to its target plus house use", _adj_chg[0] == round(6.0 + _left + 0.2 * (_left / 1.8), 2))

# ---------------------------------------------------------------------------
# v0.3.2: a sale triggered by the max-SOC (high) threshold brings the peak
# down to 100% of capacity, not to just under the threshold. Live dump from
# the 15 kWh system (2026-09-25 16:55): peak 16.71 kWh vs a 16.5 kWh (110%)
# threshold used to give a 0.21 kWh sale; now it sells 16.71 - 15 = 1.71.
# ---------------------------------------------------------------------------
_d925 = {}
exec('price="""0.197 0.184 0.176 0.171 0.175 0.172 0.171 0.17 0.167 0.166 0.165 0.162 0.164 0.165 0.165 0.164 0.165 0.161 0.16 0.159 0.158 0.16 0.168 0.177 0.167 0.177 0.183 0.193 0.199 0.202 0.204 0.226 0.221 0.222 0.21 0.198 0.23 0.202 0.189 0.158 0.179 0.162 0.148 0.131 0.133 0.119 0.099 0.072 0.083 0.063 0.053 0.047 0.044 0.041 0.031 0.024 0.028 0.04 0.045 0.061 0.044 0.074 0.104 0.122 0.116 0.133 0.153 0.179 0.156 0.19 0.201 0.234 0.201 0.23 0.248 0.283 0.285 0.298 0.308 0.299 0.27 0.255 0.247 0.237 0.244 0.231 0.218 0.203 0.22 0.209 0.202 0.195 0.2 0.189 0.166 0.153 0.207 0.2 0.195 0.186 0.188 0.185 0.183 0.182 0.182 0.18 0.174 0.168 0.167 0.164 0.164 0.163 0.161 0.162 0.162 0.163 0.16 0.159 0.162 0.166 0.169 0.177 0.182 0.189 0.193 0.195 0.195 0.197 0.211 0.203 0.187 0.166 0.193 0.166 0.139 0.128 0.132 0.121 0.105 0.101 0.078 0.061 0.046 0.054 0.047 0.046 0.039 0.031 0.024 0.016 0.017 0.017 0.01 0.013 0.023 0.031 0.023 0.04 0.072 0.096 0.089 0.12 0.132 0.16 0.153 0.19 0.203 0.2 0.192 0.206 0.221 0.234 0.222 0.23 0.244 0.251 0.239 0.232 0.222 0.212 0.218 0.21 0.206 0.2 0.207 0.201 0.198 0.192 0.195 0.188 0.183 0.178"""\nfws="""13.47 13.04 12.38 11.98 11.64 11.27 11.12 11.03 10.95 10.89 10.8 10.72 10.65 10.58 10.51 10.43 10.32 10.27 10.68 11.22 12.05 12.69 13.35 13.58 13.44 13.09 12.37 12.03 11.72 11.47 11.27 11.13 11.01 10.88 10.76 10.63 10.51 10.4 10.29 10.19 10.37 11.01 11.9 12.99 14.18 15.22 15.97 16.32 16.35 16.11 15.68 15.37 15.14 14.91 14.75 14.62 14.49 14.36 14.23 14.1 13.99 13.88 13.73 13.41 13.31 13.49 13.91 14.46 14.97 15.49 16.05 16.47 16.71 16.18 15.71 15.36 15.05 14.92 14.84 14.75 14.68 14.59 14.5 14.43 14.36 14.3 14.14 13.95 13.96 14.49 15.42 16.52 17.61 18.58 19.29 19.54 19.4 19.16"""\nusage="""0.257 0.484 0.696 0.413 0.337 0.375 0.147 0.091 0.077 0.067 0.087 0.083 0.069 0.07 0.07 0.076 0.169 0.296 0.295 0.571 0.41 0.522 0.236 0.284 0.289 0.422 0.772 0.343 0.314 0.252 0.191 0.14 0.124 0.127 0.12 0.131 0.118 0.111 0.109 0.107 0.134 0.288 0.442 0.395 0.237 0.157 0.128 0.216 0.337 0.513 0.52 0.319 0.228 0.227 0.162 0.129 0.127 0.133 0.132 0.125 0.113 0.109 0.15 0.328 0.157 0.091 0.08 0.095 0.206 0.21 0.122 0.134 0.12 0.699 0.511"""\nall_price=[float(x) for x in price.split()]\nforecast=[float(x) for x in fws.split()]\nusage=[float(x) for x in usage.split()]\n', _d925)
def _sale_925(target, high=16.5):
    return plans.compute_high_discharge_plan(
        None, 67, _d925["forecast"], datetime(2026, 9, 25, 16, 55), 3.0, high, 3.0,
        _d925["usage"], _d925["all_price"], 72, 13.48, False, 0.75, target,
    )


_old925 = _sale_925(None)
_new925 = _sale_925(15.0)
check("without a sale target the old behaviour stays (0.21 kWh down to the threshold)", _old925["surplus_kwh"] == 0.21)
check("a max-SOC-triggered sale brings the peak down to 100% (1.71 kWh)", _new925["surplus_kwh"] == 1.71 and _new925["sale_target_kwh"] == 15.0)
check("the bigger sale takes the evening peak 19:15-20:00", _new925["start_unit"] == 77 and _new925["end_unit"] == 80)
check("its stop target is 1.71 kWh below the battery now", _new925["target_energy_kwh"] == round(13.48 - 1.71, 3))
_below = _sale_925(15.0, high=14.0)
check("with max SOC below 100% the threshold itself stays the target", _below["sale_target_kwh"] == 14.0 and _below["surplus_kwh"] == round(16.71 - 14.0, 3))
_nobreach = _sale_925(15.0, high=17.0)
check("no sale while the peak stays under the threshold, even above 100%", _nobreach["active"] is False)

# ---------------------------------------------------------------------------
# v0.3.5: a statistic/sensor younger than a week - recent-days fallback
# ---------------------------------------------------------------------------
DAY_S = 24 * HOUR_S


def _young_sums(age_hours, per_hour):
    """A cumulative consumption series that starts `age_hours` before now;
    per_hour(epoch) is the usage in the hour starting at epoch. Keys are
    hour-start epochs up to the last complete hour (the current hour has no
    statistic yet)."""
    first = usage_base_epoch - age_hours * HOUR_S
    series, total = {}, 0.0
    for epoch in range(first, usage_base_epoch, HOUR_S):
        total += per_hour(epoch)
        series[epoch] = round(total, 6)
    return {"sensor.new_meter": series}


def _clock_usage(epoch):
    return 0.5 + (epoch // HOUR_S % 24) / 10.0  # 0.5 kWh at 00 UTC .. 2.8 at 23


_f1, _src1 = usage_forecast.compute_usage_forecast_from_consumption_detailed(
    _young_sums(26, _clock_usage), ["sensor.new_meter"], usage_now, 121, 6
)
_h1 = usage_forecast.summarize_usage_history(_src1, 6)
check("young statistic (1 day): every hour is filled in, none at 0 kWh", all(v > 0 for v in _f1))
check("young statistic (1 day): each hour is yesterday's same clock hour", all(
    abs(_f1[h] - _clock_usage(usage_base_epoch + h * HOUR_S)) < 1e-6 for h in range(121)))
check("young statistic (1 day): status Short history, all hours recent days",
      _h1["status"] == "Short history" and _h1["hours_recent_days"] == 121 and _h1["hours_without_history"] == 0)

# 3 days of history with a different level each day -> the 3-day average
def _daily_level(epoch):
    return {0: 1.0, 1: 2.0, 2: 3.0}[(usage_base_epoch - epoch - 1) // DAY_S]


_f3, _src3 = usage_forecast.compute_usage_forecast_from_consumption_detailed(
    _young_sums(3 * 24, _daily_level), ["sensor.new_meter"], usage_now, 24, 6
)
check("young statistic (3 days): each hour averages the days that have data", all(abs(v - 2.0) < 1e-6 for v in _f3[1:]))

# only 3 hours of data -> most hours have nothing at all
_fn, _srcn = usage_forecast.compute_usage_forecast_from_consumption_detailed(
    _young_sums(3, lambda e: 1.0), ["sensor.new_meter"], usage_now, 121, 6
)
_hn = usage_forecast.summarize_usage_history(_srcn, 6)
check("3 hours of data: hours without any history stay at 0 kWh and are counted",
      _hn["status"] == "No history" and _hn["hours_without_history"] > 100 and _fn.count(0.0) == _hn["hours_without_history"])
check("3 hours of data: the hours that do have a sample use it", _hn["hours_recent_days"] >= 1)

# 6 days old: the far hours already have a same-weekday sample, the near ones use recent days
_f6, _src6 = usage_forecast.compute_usage_forecast_from_consumption_detailed(
    _young_sums(6 * 24, _clock_usage), ["sensor.new_meter"], usage_now, 121, 6
)
check("6 days old: near hours use recent days, far hours the same-weekday average",
      _src6[0] == "recent_days" and _src6[23] == "recent_days" and _src6[25] == "weekly" and _src6[120] == "weekly")

# 8 days old: everything on the weekday average -> OK
_f8, _src8 = usage_forecast.compute_usage_forecast_from_consumption_detailed(
    _young_sums(8 * 24, _clock_usage), ["sensor.new_meter"], usage_now, 121, 6
)
_h8 = usage_forecast.summarize_usage_history(_src8, 6)
check("8 days old: every hour uses the same-weekday average, status OK",
      _h8["status"] == "OK" and _h8["hours_weekday_average"] == 121)

# Energy-balance path: one new term (battery meter, 1 day old) next to old grid/solar history
_old = {k: v for k, v in _young_sums(30 * 24, lambda e: 1.0)["sensor.new_meter"].items()}
_bal_sums = {"sensor.grid": _old, "sensor.pv": dict(_old), "sensor.bat_out": _young_sums(26, lambda e: 0.25)["sensor.new_meter"]}
_fb, _srcb = usage_forecast.compute_usage_forecast_detailed(
    _bal_sums, ["sensor.grid"], [], ["sensor.pv"], None, ["sensor.bat_out"], usage_now, 121, 6
)
check("Energy dashboard with one new battery statistic: no longer 0 kWh everywhere",
      all(abs(v - 2.25) < 1e-6 for v in _fb) and set(_srcb) == {"recent_days"})
check("compute_usage_forecast still returns just the list", usage_forecast.compute_usage_forecast(
    _bal_sums, ["sensor.grid"], [], ["sensor.pv"], None, ["sensor.bat_out"], usage_now, 3, 6) == _fb[:3])

# ---------------------------------------------------------------------------
# v0.4.0: grid transport tariff - buy price = price + (tariff x factor)
# ---------------------------------------------------------------------------
from zoneinfo import ZoneInfo  # noqa: E402

AMS = ZoneInfo("Europe/Amsterdam")
_tf = transport.load_factors()
check("transport_factors.json: 12 months x 24 hours", sorted(_tf) == list(range(1, 13)) and all(len(r) == 24 for r in _tf.values()))
check("transport factors: January as in the draft (0.7 / 0.5 / 0.7 / 0.5 / 1.0 16-22h / 0.7)",
      _tf[1] == [0.7] + [0.5] * 6 + [0.7] * 3 + [0.5] * 6 + [1.0] * 7 + [0.7])
check("transport factors: June as in the draft (0.5 / 0.3 / 0.0 10-16h / 0.3 / 0.7)",
      _tf[6] == [0.5] * 3 + [0.3] * 7 + [0.0] * 7 + [0.3] * 2 + [0.7] * 5)
check("transport factors: months 1-3 and 10-12 share the winter row, 4-9 the summer row",
      all(_tf[m] == _tf[1] for m in (2, 3, 10, 11, 12)) and all(_tf[m] == _tf[6] for m in (4, 5, 7, 8, 9)))
try:
    transport.parse_factors({"factors": {"1": [1.0] * 23}})
    _bad = False
except ValueError:
    _bad = True
check("an incomplete factor table is refused", _bad)

check("formula: buy = price + (tariff x factor)",
      transport.compute_buy_prices([0.20, -0.05, 0.10], 0.10, [1.0, 0.0, 0.5]) == [0.3, -0.05, 0.15])
check("formula: no tariff (None or 0) -> the prices themselves",
      transport.compute_buy_prices([0.2, 0.1], None, [1.0, 1.0]) == [0.2, 0.1]
      and transport.compute_buy_prices([0.2, 0.1], 0.0, [1.0, 1.0]) == [0.2, 0.1])

_jan = transport.unit_local_times(datetime(2027, 1, 12, 0, 0, tzinfo=AMS), 192, AMS)
_janf = transport.unit_factors(_jan, _tf)
check("unit 67 (16:45) on a January day uses hour 16 = 1.0, unit 63 (15:45) = 0.5", _janf[67] == 1.0 and _janf[63] == 0.5)
check("tomorrow's units (96+) are tomorrow's hours", _jan[96].day == 13 and _jan[96].hour == 0 and _janf[96] == 0.7)
_mar = transport.unit_local_times(datetime(2027, 3, 31, 0, 0, tzinfo=AMS), 192, AMS)
_marf = transport.unit_factors(_mar, _tf)
check("23:45 on 31 March is still March (1.0 at hour 22, 0.7 at 23); 00:00 is April (0.5)",
      _marf[91] == 1.0 and _marf[95] == 0.7 and _mar[96].month == 4 and _marf[96] == 0.5)
# Summer-time start 28 March 2027: 02:00 doesn't exist, 23-hour day (92 units)
_dst = transport.unit_local_times(datetime(2027, 3, 28, 0, 0, tzinfo=AMS), 96, AMS)
check("summer-time start: unit 8 is 03:00 (02:00 doesn't exist), unit 92 is the next midnight",
      _dst[8].hour == 3 and _dst[92].day == 29 and _dst[92].hour == 0)
# Winter-time start 31 October 2027: 25-hour day (100 units), 02:00 twice
_wt = transport.unit_local_times(datetime(2027, 10, 31, 0, 0, tzinfo=AMS), 104, AMS)
check("winter-time start: 02:00 comes twice, unit 100 is the next midnight",
      _wt[8].hour == 2 and _wt[12].hour == 2 and _wt[100].day == 1 and _wt[100].hour == 0)

# Low charge plan: the raw price is cheapest 16:00-18:00 (winter factor 1.0),
# but with transport 10:00-12:00 (factor 0.5) is cheaper to buy.
_raw = [0.20] * 96 + [0.20] * 96
for _u in range(40, 48):
    _raw[_u] = 0.16  # 10:00-12:00
for _u in range(64, 72):
    _raw[_u] = 0.14  # 16:00-18:00 (cheapest raw)
_buy = transport.compute_buy_prices(_raw, 0.10, _janf)
_low_args = dict(cur_unit=0, forecast_with_spike=[10.0] * 20 + [2.0] * 20, now=datetime(2027, 1, 12, 0, 0),
                 charge_speed_kw=7.0, low_threshold_kwh=3.0, minimum_charge_target_kwh=5.0, upper_limit_kwh=30.0,
                 usage=[1.0] * 121, all_price=_raw, planning_horizon_hours=72, battery_now_kwh=10.0)
_low_raw = plans.compute_low_charge_plan(None, **_low_args)
_low_buy = plans.compute_low_charge_plan(None, **_low_args, buy_price=_buy)
check("low charge plan without transport goes in the cheapest raw price (16:00-18:00)",
      64 <= _low_raw["start_unit"] and _low_raw["end_unit"] <= 72)
check("low charge plan with transport goes in the cheapest BUY price (10:00-12:00) instead",
      40 <= _low_buy["start_unit"] and _low_buy["end_unit"] <= 48)

# Negative price plan: raw price below the threshold, but not once transport is added
_negraw = [0.10] * 40 + [-0.25] * 8 + [0.10] * 48
_negargs = dict(cur_unit=0, now=now_top_of_hour, all_price=_negraw, threshold=-0.20, battery_forecast=[10.0] * 30,
                discharge_speed_kw=10.0, negative_price_charge_speed_kw=15.0, low_threshold_kwh=3.0, high_threshold_kwh=33.0)
check("negative price plan: raw price -0.25 < -0.20 triggers", plans.compute_negative_price_plan(None, **_negargs)["active"] is True)
check("negative price plan: buy price -0.25 + 0.10 = -0.15 doesn't",
      plans.compute_negative_price_plan(None, **_negargs, buy_price=[p + 0.10 for p in _negraw])["active"] is False)

# Spike plan: spread 0.45 > margin 0.40 on raw prices, gone once buying costs +0.10
_spk = [0.10] * 30 + [0.55] * 4 + [0.10] * 62
_spkargs = dict(cur_unit=0, all_price=_spk, battery_forecast=[10.0] * 30, usage=usage_flat, low_threshold_kwh=3.0,
                upper_limit_kwh=30.0, high_threshold_kwh=33.0, spike_margin=0.40, charge_speed_kw=7.0,
                spike_discharge_speed_kw=15.0, neg_plan={"active": False}, minimum_charge_target_kwh=5.0)
check("spike plan: spread on raw prices qualifies", plans.compute_spike_plan(None, **_spkargs)["active"] is True)
check("spike plan: sell max - BUY min (0.55 - 0.20 = 0.35) no longer beats the 0.40 margin",
      plans.compute_spike_plan(None, **_spkargs, buy_price=[p + 0.10 for p in _spk])["active"] is False)
_spk2 = plans.compute_spike_plan(None, **{**_spkargs, "spike_margin": 0.30}, buy_price=[p + 0.10 for p in _spk])
check("spike plan: day_min_price is the buy price, day_max_price the sell price",
      _spk2["active"] and abs(_spk2["day_min_price"] - 0.20) < 1e-9 and _spk2["day_max_price"] == 0.55)
check("spike plan: discharge floor = buy min + margin, window stays on the sell peak",
      abs(_spk2["discharge_price_floor"] - 0.50) < 1e-9 and 30 <= _spk2["discharge_start_unit"] < 34)

# Full-charge balancing: its window follows the buy price
_fc_raw = [0.20] * 40
for _u in range(4, 12):
    _fc_raw[_u] = 0.10
_fc_buy = list(_fc_raw)
for _u in range(4, 12):
    _fc_buy[_u] = 0.40  # expensive to buy there once transport is added
for _u in range(24, 32):
    _fc_buy[_u] = 0.12
_fcargs = dict(prev=None, cur_unit=0, now=now_top_of_hour, interval_days=14.0, time_since_days=20.0, soc_now_percent=20.0,
               max_hold_minutes=120.0, voltage_diff=None, battery_now_kwh=12.0, high_threshold_kwh=15.0, usage=[0.3] * 120,
               charge_speed_kw=10.0, all_price=_fc_raw, battery_forecast=[12.0] * 10, battery_voltage=None, target_voltage=55.2)
_fc1 = plans.compute_full_charge_plan(**_fcargs)
_fc2 = plans.compute_full_charge_plan(**_fcargs, buy_price=_fc_buy)
check("full-charge window without transport: cheapest raw price", 4 <= _fc1["start_unit"] < 12)
check("full-charge window with transport: cheapest buy price", 24 <= _fc2["start_unit"] < 32)

# ---------------------------------------------------------------------------
# v0.4.2: solar deficit / surplus - which minimum SOC applies
# ---------------------------------------------------------------------------
_sm = forecasting.compute_solar_mode
check("solar mode: never runs empty -> surplus", _sm([10.0, 8.0, 5.0, 3.0] + [4.0] * 117, 30.0)["mode"] == "surplus")
check("solar mode: runs empty, never fills -> deficit", _sm([5.0, 3.0, 1.0, -0.5] + [-2.0] * 117, 30.0)["mode"] == "deficit")
_dip = [5.0, 3.0, 1.0, 0.5] + [2.0 + 2 * h for h in range(117)]
check("solar mode: a dip just above 0 followed by a climb past 100% -> surplus (no useless charge)",
      _sm(_dip, 30.0)["mode"] == "surplus" and _sm(_dip, 30.0)["full_hour"] is not None)
_empty_first = [5.0] * 10 + [-1.0] * 20 + [31.0] * 91
check("solar mode: empty before full -> deficit (the nearest breach decides)",
      _sm(_empty_first, 30.0) == {"mode": "deficit", "empty_hour": 10, "full_hour": 30, "held": False})
_full_first = [20.0] * 8 + [31.0] * 32 + [-1.0] * 81
check("solar mode: full before empty -> surplus",
      _sm(_full_first, 30.0) == {"mode": "surplus", "empty_hour": 40, "full_hour": 8, "held": False})
check("solar mode: the whole 121 hours count (empty only in hour 120 -> deficit)",
      _sm([10.0] * 120 + [-0.1], 30.0)["mode"] == "deficit")

# 2026.10.8: between 0% and 100% all along -> the mode stays what it was (0% and 100% are the switch points)
_between = [12.0, 9.0, 6.0, 2.0] + [8.0] * 117
check("solar mode: between 0% and 100% after a deficit -> stays deficit",
      _sm(_between, 30.0, "deficit") == {"mode": "deficit", "empty_hour": None, "full_hour": None, "held": True})
check("solar mode: between 0% and 100% after a surplus -> stays surplus",
      _sm(_between, 30.0, "surplus")["mode"] == "surplus" and _sm(_between, 30.0, "surplus")["held"])
check("solar mode: between 0% and 100% with nothing known yet -> surplus (not held)",
      _sm(_between, 30.0) == {"mode": "surplus", "empty_hour": None, "full_hour": None, "held": False})
check("solar mode: a previous deficit doesn't hold once the forecast fills up first",
      _sm(_full_first, 30.0, "deficit")["mode"] == "surplus")
check("solar mode: a previous surplus doesn't hold once the forecast runs empty first",
      _sm(_empty_first, 30.0, "surplus")["mode"] == "deficit")

# ---------------------------------------------------------------------------
# v0.4.3: charge / discharge efficiency
# ---------------------------------------------------------------------------
_eff_now = datetime(2026, 9, 30, 12, 0, 0)
_ef = forecasting.build_battery_forecast([2.0, -0.5, -0.5], 10.0, _eff_now, charge_efficiency=0.9, discharge_efficiency=0.9)
check("efficiency: 2.0 kWh surplus at 90% puts 1.8 kWh into the battery", _ef[0] == 11.8)
check("efficiency: 0.5 kWh usage at 90% takes 0.56 kWh out of the battery", _ef[1] == round(11.8 - 0.5 / 0.9, 2))
check("efficiency: 100% (the default) changes nothing",
      forecasting.build_battery_forecast([2.0, -0.5], 10.0, _eff_now) == [12.0, 11.5])
_ef_cap = forecasting.build_battery_forecast([12.0, -12.0], 20.0, _eff_now, max_charge_kw=10.0, max_discharge_kw=10.0,
                                             charge_efficiency=0.9, discharge_efficiency=0.9)
check("efficiency: the max charge/discharge caps are on the battery side",
      _ef_cap[0] == 30.0 and _ef_cap[1] == 20.0)

_lowargs_eff = dict(cur_unit=0, forecast_with_spike=[10.0] * 5 + [2.0] * 20, now=now_top_of_hour, charge_speed_kw=7.0,
                    low_threshold_kwh=3.0, minimum_charge_target_kwh=10.0, upper_limit_kwh=30.0, usage=[1.0] * 121,
                    all_price=[0.30] * 40 + [0.10] * 20 + [0.30] * 40, planning_horizon_hours=72, battery_now_kwh=10.0)
_low100 = plans.compute_low_charge_plan(None, **_lowargs_eff)
_low90 = plans.compute_low_charge_plan(None, **_lowargs_eff, charge_efficiency=0.9)
check("efficiency: low charge rate per unit = (charge - house) x 90%",
      abs(_low90["effective_charge_per_unit"] - round((7.0 / 4 - 0.25) * 0.9, 4)) < 1e-9)
check("efficiency: the low charge window gets longer to put the same energy in",
      _low90["units_needed"] > _low100["units_needed"] and _low90["target_kwh"] == _low100["target_kwh"])

_high_eff = dict(cur_unit=0, forecast_with_spike=[20.0] * 5 + [34.0] * 20, now=now_top_of_hour, discharge_speed_kw=10.0,
                 high_threshold_kwh=33.0, low_threshold_kwh=3.0, usage=[1.0] * 121, all_price=[0.20] * 100,
                 planning_horizon_hours=72, battery_now_kwh=20.0, sale_target_kwh=30.0)
_h90 = plans.compute_high_discharge_plan(None, **_high_eff, discharge_efficiency=0.9)
check("efficiency: sale rate per unit = (discharge + house) / 90% on the battery side",
      abs(_h90["effective_discharge_per_unit"] - round((10.0 / 4 + 0.25) / 0.9, 4)) < 1e-9)
_neg90 = plans.compute_negative_price_plan(None, cur_unit=0, now=now_top_of_hour, all_price=[0.1] * 40 + [-0.3] * 8 + [0.1] * 48,
                                           threshold=-0.2, battery_forecast=[10.0] * 30, discharge_speed_kw=10.0,
                                           negative_price_charge_speed_kw=15.0, low_threshold_kwh=3.0, high_threshold_kwh=33.0,
                                           charge_efficiency=0.9, discharge_efficiency=0.9)
check("efficiency: negative price charging at 90% puts 90% into the battery",
      abs(_neg90["raw_potential_kwh"] - round(8 * 15.0 / 4 * 0.9, 2)) < 1e-9)
# Drawing a sale over the forecast: the forecast already took house/0.9 out
_dw = plans._plan_draw_window({"active": True, "start_unit": 8, "end_unit": 12, "target_kwh": 4.0, "avg_home_load_kw": 1.0,
                               "effective_discharge_per_unit": (2.5 + 0.25) / 0.9, "discharge_efficiency": 0.9},
                              0, None, charging=False)
check("efficiency: a sale drawn over the forecast removes only the sale itself (house / 90% is already in it)",
      abs((_dw[1] - _dw[0]) * _dw[2] - (4.0 - 0.25 / 0.9 * (4.0 / ((2.5 + 0.25) / 0.9)))) < 1e-6)

# ---------------------------------------------------------------------------
# v0.4.4: the dashboard cards file is generated from the dashboard examples
# ---------------------------------------------------------------------------
_bspec = importlib.util.spec_from_file_location("build_cards", os.path.join(_REPO_ROOT, "tools", "build_cards.py"))
_bc = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(_bc)
with open(_bc.OUT, encoding="utf-8") as _fh:
    check("frontend/ess-manager-cards.js is up to date with tools/cards_template.js (run tools/build_cards.py)", _fh.read() == _bc.build())

# ---------------------------------------------------------------------------
# v0.5.0: status card data (display.card_plans)
# ---------------------------------------------------------------------------
_cp_now = datetime(2026, 10, 2, 18, 7, 0)
_cur = 18 * 4  # 18:00 unit
_high = {"active": True, "start_unit": _cur - 1, "end_unit": _cur + 6, "target_kwh": 4.8, "target_energy_kwh": 18.6,
         "effective_discharge_per_unit": 0.6875, "target_reached": False}
_neg = {"active": True, "charge_start_unit": _cur + 68, "charge_end_unit": _cur + 80, "achievable_charge_kwh": 7.5,
        "level_at_start_kwh": 22.5, "effective_charge_per_unit": 3.0, "discharge_needed_kwh": 0}
_cp = display.card_plans({"active": False}, _neg, {"active": False}, {"active": False}, _high, _cur, _cp_now, 21.5, 30.0)
check("card plans: Sell = the running high discharge, Buy = the negative price charge",
      _cp["sell"]["source"] == "high_discharge" and _cp["buy"]["source"] == "negative_price")
check("card plans: a running sale's progress is measured on energy (battery 21.5 vs target 18.6 of 4.8 kWh)",
      _cp["sell"]["started"] and _cp["sell"]["remaining_kwh"] == 2.9 and _cp["sell"]["done_kwh"] == 1.9)
check("card plans: target SOC from the target level (18.6 of 30 kWh = 62 %)", _cp["sell"]["target_soc_percent"] == 62.0)
check("card plans: start/stop as times on the 15-minute grid", _cp["sell"]["start"].startswith("2026-10-02T17:45")
      and _cp["sell"]["stop"].startswith("2026-10-02T19:30"))
check("card plans: a planned window hasn't started, nothing done yet",
      _cp["buy"]["started"] is False and _cp["buy"]["done_kwh"] == 0 and _cp["buy"]["target_soc_percent"] == 100.0)
check("card plans: battery-side rate in kWh per hour", _cp["sell"]["rate_kw"] == 2.75 and _cp["buy"]["rate_kw"] == 12.0)
_spk = {"active": True, "charge_start_unit": _cur + 36, "charge_end_unit": _cur + 45, "charge_needed_kwh": 14.2,
        "charge_target_level_kwh": 30.0, "discharge_start_unit": _cur + 98, "discharge_end_unit": _cur + 104,
        "discharge_target_kwh": 12.4, "effective_charge_per_unit": 1.575, "effective_discharge_per_unit": 3.75}
_low = {"active": True, "start_unit": _cur + 30, "end_unit": _cur + 34, "target_kwh": 5.0, "target_energy_kwh": 9.6,
        "effective_charge_per_unit": 1.5}
_cp2 = display.card_plans({"active": False}, {"active": False}, _spk, _low, {"active": False}, _cur, _cp_now, 20.0, 30.0)
check("card plans: an active spike drives both blocks (before a low charge)",
      _cp2["buy"]["source"] == "spike" and _cp2["sell"]["source"] == "spike" and _cp2["sell"]["target_soc_percent"] == 58.7)
_cp3 = display.card_plans({"active": False}, {"active": False}, {"active": False},
                          {**_low, "start_unit": _cur - 4, "target_reached": True}, {"active": False}, _cur, _cp_now, 9.7, 30.0)
check("card plans: a charge whose target is reached is done", _cp3["buy"]["target_reached"] and _cp3["buy"]["remaining_kwh"] == 0
      and _cp3["sell"] is None)

# v0.5.5: a window still ahead gets its target from the expected level at its start
_fc = [round(10 + 0.1 * (i + 1), 3) for i in range(121)]  # rising 0.1 kWh per hour
_high_tmw = {"active": True, "start_unit": 96 + 77, "end_unit": 96 + 79, "target_kwh": 1.6, "target_energy_kwh": 8.4,
             "effective_discharge_per_unit": 0.8, "target_reached": False}
_cp4 = display.card_plans({"active": False}, {"active": False}, {"active": False}, {"active": False}, _high_tmw,
                          _cur, _cp_now, 10.0, 15.0, _fc)
check("card plans: a sale tomorrow 19:15 targets the level expected then minus the sale (12.53 - 1.6), not SOC now minus it",
      abs(_cp4["sell"]["target_level_kwh"] - 10.93) < 0.01 and _cp4["sell"]["target_soc_percent"] == 72.8)
_cp5 = display.card_plans({"active": False}, {"active": False}, {"active": False},
                          {**_low, "start_unit": _cur + 8, "end_unit": _cur + 12}, {"active": False}, _cur, _cp_now, 10.0, 30.0, _fc)
check("card plans: a charge at 20:00 targets the level expected then plus the charge (10.2 + 5.0)",
      abs(_cp5["buy"]["target_level_kwh"] - 15.2) < 0.01)
check("card plans: a running sale keeps its own target level (forecast ignored)",
      display.card_plans({"active": False}, {"active": False}, {"active": False}, {"active": False}, _high, _cur, _cp_now, 21.5, 30.0, _fc)["sell"]["target_level_kwh"] == 18.6)
check("card plans: without a forecast the plan's own target level is used",
      display.card_plans({"active": False}, {"active": False}, {"active": False}, {"active": False}, _high_tmw, _cur, _cp_now, 10.0, 15.0)["sell"]["target_level_kwh"] == 8.4)

# v0.5.11: the full charge plan's balancing wait fills the Buy block
_hold = {"active": True, "phase": "holding", "hold_start": "2026-10-02T17:30:00",
         "hold_start_unit": _cur - 2, "hold_end_unit": _cur + 6}
_bal = {"max_hold_minutes": 120, "voltage_diff_mv": 18.04, "balance_threshold_mv": 10.0,
        "battery_voltage": 55.83, "target_voltage": 56.0}
_cp6 = display.card_plans(_hold, _neg, {"active": False}, {"active": False}, {"active": False}, _cur, _cp_now, 30.0, 30.0,
                          None, _bal)
check("card plans: holding shows in the Buy block (before a negative price charge), phase holding",
      _cp6["buy"]["source"] == "full_charge" and _cp6["buy"]["phase"] == "holding" and _cp6["buy"]["started"])
check("card plans: holding runs from its start to the max hold timeout (17:30 + 120 min)",
      _cp6["buy"]["start"] == "2026-10-02T17:30:00" and _cp6["buy"]["stop"] == "2026-10-02T19:30:00")
check("card plans: holding carries the balance readings",
      _cp6["buy"]["voltage_diff_mv"] == 18.0 and _cp6["buy"]["balance_threshold_mv"] == 10.0
      and _cp6["buy"]["battery_voltage"] == 55.83 and _cp6["buy"]["target_voltage"] == 56.0)
_cp7 = display.card_plans(_hold, {"active": False}, {"active": False}, {"active": False}, {"active": False}, _cur, _cp_now,
                          30.0, 30.0)
check("card plans: holding without readings falls back to the hold units, readings None",
      _cp7["buy"]["stop"].startswith("2026-10-02T19:30") and _cp7["buy"]["voltage_diff_mv"] is None)
_charging = {"active": True, "phase": "charging", "start_unit": _cur - 2, "end_unit": _cur + 6, "target_kwh": 10.0,
             "effective_charge_per_unit": 1.5}
check("card plans: the charging phase is labelled too",
      display.card_plans(_charging, {"active": False}, {"active": False}, {"active": False}, {"active": False}, _cur, _cp_now,
                         22.0, 30.0)["buy"]["phase"] == "charging")

# ---------------------------------------------------------------------------
# v0.5.1: today's measured hours for the battery card (history_today)
# ---------------------------------------------------------------------------
_md_start = datetime(2026, 10, 2, 0, 0, tzinfo=AMS)
_md_now = datetime(2026, 10, 2, 10, 20, tzinfo=AMS)
_md_first = int(_md_start.timestamp()) - 3600


def _md_series(per_hour, skip=()):
    out, total = {}, 0.0
    for k, epoch in enumerate(range(_md_first, int(_md_start.timestamp()) + 10 * 3600, 3600)):
        total += per_hour(k - 1)
        if (k - 1) not in skip:
            out[epoch] = round(total, 6)
    return out


_md_sums = {
    "sensor.grid": _md_series(lambda h: 0.5),
    "sensor.pv": _md_series(lambda h: 2.0 if h in (8, 9) else 0.0, skip=(5,)),
    "sensor.bat_in": _md_series(lambda h: 1.0 if h == 9 else 0.0),
}
_md = usage_forecast.measured_hours(_md_sums, ["sensor.grid"], [], ["sensor.pv"], ["sensor.bat_in"], None, _md_start, _md_now)
check("measured today: one value per complete hour since midnight (00-09 at 10:20)", len(_md["usage"]) == 10 and len(_md["solar"]) == 10)
check("measured today: usage = import + solar - battery charge (09h: 0.5 + 2.0 - 1.0)", _md["usage"][9] == 1.5 and _md["usage"][8] == 2.5)
check("measured today: solar production per hour from its statistic", _md["solar"][8] == 2.0 and _md["solar"][0] == 0.0)
check("measured today: an hour with a missing statistic is None (not 0)", _md["solar"][5] is None and _md["usage"][5] is None
      and _md["solar"][6] is None)
_md_c = usage_forecast.measured_hours(_md_sums, ["sensor.grid"], [], [], None, None, _md_start, _md_now)
check("measured today: a consumption meter alone gives usage, no solar", _md_c["solar"] is None and _md_c["usage"] == [0.5] * 10)

# ---------------------------------------------------------------------------
# v0.5.12: running windows are re-checked after a settings change (replan),
# and the negative price / spike plans only lock the window that's running
# ---------------------------------------------------------------------------
_lkw = dict(forecast_with_spike=no_breach_forecast, now=now_top_of_hour, charge_speed_kw=7.0, low_threshold_kwh=3.0,
            minimum_charge_target_kwh=5.0, upper_limit_kwh=30.0, usage=usage_flat, all_price=all_price,
            planning_horizon_hours=72, battery_now_kwh=10.0)
check("replan: a running low charge is kept without a settings change",
      plans.compute_low_charge_plan(low_plan, cur_unit=low_plan["start_unit"], **_lkw) == low_plan)
check("replan: a running low charge that's no longer needed stops after a settings change",
      plans.compute_low_charge_plan(low_plan, cur_unit=low_plan["start_unit"], replan=True, **_lkw)["active"] is False)
_hkw = dict(forecast_with_spike=[10.0] * 25, now=now_top_of_hour, discharge_speed_kw=10.0, high_threshold_kwh=33.0,
            low_threshold_kwh=3.0, usage=usage_flat, all_price=all_price, planning_horizon_hours=72, battery_now_kwh=10.0)
check("replan: a running high discharge is kept without a settings change",
      plans.compute_high_discharge_plan(high_plan, cur_unit=high_plan["start_unit"], **_hkw) == high_plan)
check("replan: a running high discharge that's no longer needed stops after a settings change",
      plans.compute_high_discharge_plan(high_plan, cur_unit=high_plan["start_unit"], replan=True, **_hkw)["active"] is False)

_nkw = dict(now=now_top_of_hour, all_price=neg_price, threshold=-0.20, discharge_speed_kw=10.0,
            negative_price_charge_speed_kw=15.0, low_threshold_kwh=3.0, high_threshold_kwh=33.0)
_n0 = plans.compute_negative_price_plan(None, cur_unit=0, battery_forecast=[10.0] * 30, **_nkw)
check("negative plan: the running pre-discharge is kept (units 0-2)",
      _n0["discharge_start_unit"] == 0 and _n0["discharge_end_unit"] == 2
      and plans.compute_negative_price_plan(_n0, cur_unit=1, battery_forecast=[6.0] * 30, **_nkw) == _n0)
_n1 = plans.compute_negative_price_plan(_n0, cur_unit=2, battery_forecast=[6.0] * 30, **_nkw)
check("negative plan: between the pre-discharge and the charge it's re-planned on the live level (less room needed: 2.5 kWh)",
      _n1 is not _n0 and _n1["level_at_start_kwh"] == 6.0 and _n1["discharge_needed_kwh"] == 2.5
      and _n1["charge_start_unit"] == 40)
check("negative plan: the running charge is kept",
      plans.compute_negative_price_plan(_n1, cur_unit=41, battery_forecast=[30.0] * 30, **_nkw) == _n1)
check("negative plan: a settings change re-plans even the running charge",
      plans.compute_negative_price_plan(_n1, cur_unit=41, battery_forecast=[30.0] * 30, replan=True, **_nkw) is not _n1)

_skw = dict(all_price=spike_price, usage=usage_flat, low_threshold_kwh=3.0, upper_limit_kwh=30.0, high_threshold_kwh=33.0,
            spike_margin=0.40, charge_speed_kw=7.0, spike_discharge_speed_kw=15.0, neg_plan={"active": False},
            minimum_charge_target_kwh=5.0)
_s0 = plans.compute_spike_plan(None, cur_unit=0, battery_forecast=[10.0] * 30, **_skw)
check("spike plan: the running charge is kept (units 0-14)",
      _s0["charge_end_unit"] == 14 and plans.compute_spike_plan(_s0, cur_unit=5, battery_forecast=[29.0] * 30, **_skw) == _s0)
check("spike plan: the running sale is kept",
      plans.compute_spike_plan(_s0, cur_unit=30, battery_forecast=[5.0] * 30, **_skw) == _s0)
_s1 = plans.compute_spike_plan(_s0, cur_unit=20, battery_forecast=[22.0] * 30, **_skw)
check("spike plan: between charge and sale it's re-planned; 8 kWh short at the peak -> a top-up at 0.10 (<= 0.60 - 0.40)",
      _s1["topup"] and _s1["topup_price_cap"] == 0.2 and _s1["charge_needed_kwh"] == 8.0
      and _s1["charge_start_unit"] == 20 and _s1["charge_end_unit"] > 20 and _s1["discharge_start_unit"] >= 30)
_s2 = plans.compute_spike_plan(_s0, cur_unit=20, battery_forecast=[22.0] * 30,
                               **{**_skw, "all_price": [0.10] * 14 + [0.25] * 16 + [0.60] * 4 + [0.10] * 62})
check("spike plan: no top-up when it wouldn't pay (0.25 > 0.60 - 0.40); the sale is sized on the 22 kWh expected at the peak",
      _s2["topup"] and _s2["charge_needed_kwh"] == 0 and _s2["charge_start_unit"] == _s2["charge_end_unit"]
      and _s2["level_at_peak_kwh"] == 22.0)
_s3 = plans.compute_spike_plan(_s0, cur_unit=20, battery_forecast=[26.0] * 30, **_skw)
check("spike plan: a top-up smaller than the minimum charge target is skipped (4 < 5 kWh)",
      _s3["charge_needed_kwh"] == 0 and _s3["level_at_peak_kwh"] == 26.0)
check("spike plan: before its charge starts it's not a top-up (normal planning)",
      plans.compute_spike_plan(None, cur_unit=0, battery_forecast=[10.0] * 30, **_skw)["topup"] is False)
check("spike plan: a settings change re-plans even the running charge",
      plans.compute_spike_plan(_s0, cur_unit=5, battery_forecast=[29.0] * 30, replan=True, **_skw)["charge_needed_kwh"] == 0)

_fkw = dict(cur_unit=2, now=now_top_of_hour, interval_days=14.0, soc_now_percent=60.0, max_hold_minutes=120.0,
            voltage_diff=None, battery_now_kwh=8.0, high_threshold_kwh=15.0, usage=[0.3] * 120, charge_speed_kw=3.0,
            all_price=[0.10] * 20, battery_forecast=[8.0] * 5, battery_voltage=None, target_voltage=55.2)
check("full charge: a settings change that makes it not due stops a running charge (interval 14 d, 5 d since)",
      plans.compute_full_charge_plan(prev=midway_prev, time_since_days=5.0, replan=True, **_fkw)["active"] is False)
check("full charge: without a settings change a running charge is kept even when not due",
      plans.compute_full_charge_plan(prev=midway_prev, time_since_days=5.0, **_fkw) == midway_prev)
_f2 = plans.compute_full_charge_plan(prev=midway_prev, time_since_days=20.0, replan=True, **_fkw)
check("full charge: still due and the cheapest window is now -> goes straight on charging (no scheduled cycle)",
      _f2["phase"] == "charging" and _f2["start_unit"] == 2)
_hold_prev = {"active": True, "phase": "holding", "hold_start": now_top_of_hour.isoformat(), "hold_start_unit": 0, "hold_end_unit": 8}
check("full charge: a settings change never interrupts the balancing wait",
      plans.compute_full_charge_plan(prev=_hold_prev, time_since_days=20.0, replan=True,
                                     **{**_fkw, "now": now_top_of_hour + timedelta(minutes=30)})["phase"] == "holding")

# ---------------------------------------------------------------------------
# v0.5.13: solar deficit mode - the surplus minimum stays the hard floor,
# the band up to the deficit minimum is not urgent and capped to what fits
# ---------------------------------------------------------------------------
_sd_now = datetime(2026, 10, 6, 20, 10)
_sd_cur = 20 * 4


def _sd_forecast(start, solar):
    level, out = start, []
    for h in range(121):
        t = _sd_now + timedelta(hours=h + 1)
        d = (t.date() - _sd_now.date()).days
        if d >= 4:
            level -= 1.0
        elif 9 <= t.hour < 16:
            level += solar.get(d, 0)
        else:
            level -= 0.15
        out.append(round(level, 2))
    return out


# battery 8 kWh (27 %) under a 9 kWh (30 %) deficit minimum, 1.5 kWh (5 %) surplus minimum;
# tonight it dips to 6.2, day 3 peaks at 28.05 (93.5 %), day 5 runs empty
_sd_fc = _sd_forecast(8.0, {1: 1.6, 2: 1.4, 3: 0.85})
_sd_price = ([0.30] * 96 + [0.15] * 24 + [0.25] * 72) * 3
_sd_kw = dict(now=_sd_now, charge_speed_kw=7.0, low_threshold_kwh=9.0, upper_limit_kwh=30.0, usage=[0.5] * 121,
              all_price=_sd_price, planning_horizon_hours=72, battery_now_kwh=8.0, high_threshold_kwh=33.0)
check("deficit mode scenario: deficit (day 5 empty, day 3 short of full)",
      forecasting.compute_solar_mode(_sd_fc, 30.0)["mode"] == forecasting.SOLAR_MODE_DEFICIT)
_sd_old = plans.compute_low_charge_plan(None, _sd_cur, _sd_fc, minimum_charge_target_kwh=1.0, **_sd_kw)
check("one threshold (no floor): charges the whole 2.8 kWh right away at 0.30",
      _sd_old["target_kwh"] == 2.8 and _sd_old["start_unit"] == _sd_cur)
_sd_new = plans.compute_low_charge_plan(None, _sd_cur, _sd_fc, minimum_charge_target_kwh=1.0, floor_kwh=1.5, **_sd_kw)
check("deficit band: only what fits under 100 % at the day-3 peak (1.95 of 2.8 kWh), capped",
      _sd_new["active"] and _sd_new["target_kwh"] == 1.95 and _sd_new["soft_capped"] and _sd_new["hard_deficit_kwh"] == 0)
check("deficit band: no hurry - charged in tonight's cheap window (0.15 from midnight), before the dip ends at 09:00",
      _sd_new["start_unit"] >= 96 and _sd_price[_sd_new["start_unit"]] == 0.15 and _sd_new["end_unit"] <= 96 + 9 * 4)
_sd_skip = plans.compute_low_charge_plan(None, _sd_cur, _sd_fc, minimum_charge_target_kwh=3.0, floor_kwh=1.5, **_sd_kw)
check("deficit band: less than the minimum charge target fits (1.95 < 3.0) -> no charge now",
      _sd_skip["active"] is False and _sd_skip["soft_skipped"]["fits_kwh"] == 1.95)
_sd_full = [round(v + 1.95, 2) for v in _sd_fc]  # after that charge: peak at exactly 100 %
check("deficit band: once the peak is at 100 % nothing more is charged for it (no repeat charges)",
      plans.compute_low_charge_plan(None, _sd_cur, _sd_full, minimum_charge_target_kwh=1.0, floor_kwh=1.5,
                                    **{**_sd_kw, "battery_now_kwh": 9.95})["active"] is False)
# the dip reaches below the floor: that part is uncapped and urgent
_sd_hard_fc = _sd_forecast(3.0, {1: 1.6, 2: 1.4, 3: 0.85})  # tonight down to 1.2 < 1.5
_sd_hard = plans.compute_low_charge_plan(None, _sd_cur, _sd_hard_fc, minimum_charge_target_kwh=1.0, floor_kwh=1.5,
                                         **{**_sd_kw, "battery_now_kwh": 3.0})
check("below the floor: the hard part (0.3 kWh to 1.5) is always charged, plus what fits of the band",
      _sd_hard["active"] and _sd_hard["hard_deficit_kwh"] == 0.3 and _sd_hard["target_kwh"] >= 0.3)
check("below the floor: deadline = the hour it would cross the floor (not the end of the dip)",
      _sd_hard["breach_unit"] < 96 + 9 * 4 and _sd_hard["end_unit"] <= _sd_hard["breach_unit"] + _sd_hard["units_needed"])
check("surplus mode (no floor): unchanged",
      plans.compute_low_charge_plan(None, _sd_cur, _sd_fc, minimum_charge_target_kwh=1.0, **_sd_kw) == _sd_old)

# ---------------------------------------------------------------------------
# 2026.10.1: the forecast clipped at 100%, and the solar surplus
# ---------------------------------------------------------------------------
_cl, _sp = forecasting.clip_at_capacity([28.0, 31.0, 32.4, 31.0, 29.0, 2.0], 27.0, 30.0)
check("clip at 100 %: never above capacity, the hour it would go over spills the rest",
      _cl[:3] == [28.0, 30.0, 30.0] and _sp[:3] == [0.0, 1.0, 1.4])
check("clip at 100 %: after the peak it drains from 100 % (32.4 -> 31 -> 29 is 30 - 1.4 - 2), not from the running sum",
      _cl[3:5] == [28.6, 26.6] and _sp[3] == 0.0)
check("clip at 100 %: not clipped at the bottom (a level below the threshold / 0 stays)",
      forecasting.clip_at_capacity([1.0, -2.0], 3.0, 30.0)[0] == [1.0, -2.0])
_rs = forecasting.rate_spill([2.0, 6.0, 4.0], datetime(2026, 10, 7, 12, 30), 5.0, 1.0)
check("rate spill: solar surplus above the max charge speed goes to the grid (hour 0 half left)",
      _rs == [0.0, 1.0, 0.0])
check("rate spill: none without a max charge speed", forecasting.rate_spill([9.0], datetime(2026, 10, 7, 12, 0), None) == [0.0])
_ss = forecasting.solar_surplus_windows([0.0, 0.0, 1.0, 1.4, 0.0, 0.0], [0.0, 0.6, 0.0, 0.0, 0.0, 0.3],
                                        datetime(2026, 10, 7, 10, 20))
check("solar surplus: consecutive hours merge into one window, 'full' when the battery is full in any of them",
      len(_ss) == 2 and _ss[0]["start"] == "2026-10-07T11:00:00" and _ss[0]["stop"] == "2026-10-07T14:00:00"
      and _ss[0]["kwh"] == 3.0 and _ss[0]["reason"] == "full")
check("solar surplus: only the charge speed -> reason 'rate'", _ss[1]["reason"] == "rate" and _ss[1]["kwh"] == 0.3)
check("solar surplus: hour 0 starts now; rounding noise isn't a window",
      forecasting.solar_surplus_windows([0.2, 0.01], [0, 0], datetime(2026, 10, 7, 10, 20))
      == [{"start": "2026-10-07T10:20:00", "stop": "2026-10-07T11:00:00", "kwh": 0.2, "reason": "full"}])

# The example from the discussion: the running sum peaks at 108 % (under a 110 % max SOC, so nothing is
# sold) and shows 12 % the next morning; really the battery stops at 100 % and is at 4 %.
_cc_now = datetime(2026, 10, 7, 9, 0)
_cc_fc = [21.0, 24.0, 27.0, 30.0, 32.4, 32.4] + [round(32.4 - 1.2 * (h + 1), 2) for h in range(19)] + [12.0] * 10
_cc_kw = dict(now=_cc_now, charge_speed_kw=7.0, low_threshold_kwh=3.0, minimum_charge_target_kwh=1.0,
              upper_limit_kwh=30.0, usage=[1.2] * 121, all_price=[0.25] * 192, planning_horizon_hours=72,
              battery_now_kwh=18.0, high_threshold_kwh=33.0)
check("charge plan on the unclipped forecast: misses the morning dip (lowest 9.6 kWh > 3)",
      plans.compute_low_charge_plan(None, 36, _cc_fc, **_cc_kw)["active"] is False)
_cc_clip, _ = forecasting.clip_at_capacity(_cc_fc, 18.0, 30.0)
_cc = plans.compute_low_charge_plan(None, 36, _cc_clip, peak_kwh=max(_cc_fc), **_cc_kw)
check("charge plan on the clipped forecast: sees it (100 % minus the drain = 7.2 kWh lower)",
      min(_cc_clip) == 7.2 and min(_cc_fc[:25]) == 9.6)
_cc_deep = _cc_fc[:6] + [round(32.4 - 1.2 * (h + 1), 2) for h in range(24)] + [12.0] * 5  # a longer night
_cc_deep_clip, _ = forecasting.clip_at_capacity(_cc_deep, 18.0, 30.0)
_cc2 = plans.compute_low_charge_plan(None, 36, _cc_deep_clip, peak_kwh=max(_cc_deep), **_cc_kw)
check("charge plan on the clipped forecast: a dip below the threshold after a full day is planned (unclipped: 3.6 > 3)",
      plans.compute_low_charge_plan(None, 36, _cc_deep, **_cc_kw)["active"] is False
      and _cc2["active"] and _cc2["dip_min_kwh"] == 1.2)
check("charge plan: how much fits is still measured on the unclipped peak (no headroom left at 108 %)",
      _cc2["target_kwh"] == 1.8)

# 2026.10.1: the negative price plan on the clipped forecast, never planning above 100 %
_np_now = datetime(2026, 10, 7, 9, 0)
_np_fc = [21.0, 24.0, 27.0, 30.0, 32.4, 32.4] + [round(32.4 - 0.5 * (h + 1), 2) for h in range(30)]  # 108 % peak
_np_price = [0.10] * (9 * 4 + 20 * 4) + [-0.30] * 8 + [0.10] * 80  # tomorrow 05:00-07:00 negative
_np_kw = dict(now=_np_now, all_price=_np_price, threshold=-0.20, discharge_speed_kw=10.0,
              negative_price_charge_speed_kw=15.0, low_threshold_kwh=3.0)
_np_old = plans.compute_negative_price_plan(None, 36, battery_forecast=_np_fc, high_threshold_kwh=33.0, **_np_kw)
_np_clip, _ = forecasting.clip_at_capacity(_np_fc, 18.0, 30.0)
_np_new = plans.compute_negative_price_plan(None, 36, battery_forecast=_np_clip, high_threshold_kwh=min(33.0, 30.0), **_np_kw)
check("negative plan: level at the window start from the clipped forecast (100 % minus the drain, not 108 % minus it)",
      _np_new["level_at_start_kwh"] == round(_np_old["level_at_start_kwh"] - 2.4, 2))
check("negative plan: the room it makes is measured up to 100 %, not up to a 110 % max SOC",
      _np_new["target_after_discharge_kwh"] + _np_new["achievable_charge_kwh"] <= 30.0
      and _np_old["target_after_discharge_kwh"] + _np_old["achievable_charge_kwh"] > 30.0)

# 2026.10.3: Solar export - solar left over now, the battery full later today, and the price now higher
# than every price until then (no planned sale or nearly empty battery needed any more)
_se_kw = dict(setpoint_w=0.0, idle_setpoint_w=0.0, cur_unit=40, full={"active": False}, neg={"active": False},
              spike={"active": False}, low={"active": False, "breach_unit": 999999}, high={"active": False},
              battery_now_kwh=20.0, low_threshold_kwh=3.0, charge_speed_kw=7.0, discharge_speed_kw=10.0)
_se_lower = [0.20] * 40 + [0.30] + [0.25] * 15 + [0.10] * 40  # now 0.30, everything until 14:00 lower
_se_dip_up = [0.20] * 40 + [0.30] + [0.25] * 7 + [0.35] + [0.25] * 7 + [0.10] * 40  # a higher price in between
check("Solar export: price now higher than every price until the battery is full (14:00 today)",
      plans.compute_system_status(all_price=_se_lower, full_unit=56, solar_surplus_now=True, **_se_kw) == "Solar export")
check("Solar export: not when a price before that moment is higher",
      plans.compute_system_status(all_price=_se_dip_up, full_unit=56, solar_surplus_now=True, **_se_kw) == "Standby")
check("Solar export: not when the battery only gets full tomorrow",
      plans.compute_system_status(all_price=_se_lower + [0.1] * 96, full_unit=100, solar_surplus_now=True, **_se_kw) == "Standby")
check("Solar export: not without solar left over right now",
      plans.compute_system_status(all_price=_se_lower, full_unit=56, solar_surplus_now=False, **_se_kw) == "Standby")
check("Solar export: never replaces a running action",
      plans.compute_system_status(all_price=_se_lower, full_unit=56, solar_surplus_now=True,
                                  **{**_se_kw, "low": {"active": True, "start_unit": 39, "end_unit": 42, "breach_unit": 50}})
      == "Start charge")
check("Solar export: is a label only (idle)",
      plans.compute_system_status_and_action(all_price=_se_lower, full_unit=56, solar_surplus_now=True, **_se_kw)[1] == "idle")

# 2026.10.3: live report (15 kWh battery, 09:39, 3.9 kWh, deficit minimum 4.5, surplus 0.75): the battery was
# just under the deficit minimum, the sun lifts it above within the hour - and it started a 6.6 kWh charge
# right away at 0.16 instead of in the cheap 12:00-16:00 window.
_lr_fc = [4, 4.81, 5.77, 6.72, 7.58, 8.15, 8.38, 8.36, 7.93, 6.89, 6.13, 5.62, 5.39, 5.28, 5.18, 5.07, 4.97, 4.87, 4.79,
          4.7, 4.63, 4.41, 4.08, 3.88, 3.81, 3.82, 3.91, 3.96, 4.08, 4.2, 4.26, 4.28, 4.02, 3.31, 2.85, 2.59, 2.3, 2.14,
          2.04, 1.95, 1.87, 1.77, 1.69, 1.61, 1.54, 1.46, 1.38, 1.27, 1.47, 1.96, 2.55, 3.16, 3.82, 4.35, 4.62, 4.66,
          4.47, 3.63, 3.25, 2.9, 2.63, 2.43, 2.28, 2.14, 1.99, 1.85, 1.71, 1.59, 1.47, 1.35, 1.23, 1.19, 1.21, 1.35]
_lr_price = [0.178, 0.152, 0.139, 0.127, 0.139, 0.134, 0.129, 0.118, 0.12, 0.116, 0.114, 0.115, 0.114, 0.111, 0.114,
             0.113, 0.114, 0.112, 0.112, 0.113, 0.118, 0.117, 0.113, 0.121, 0.126, 0.139, 0.151, 0.151, 0.175, 0.174,
             0.179, 0.184, 0.206, 0.201, 0.193, 0.179, 0.192, 0.178, 0.163, 0.156, 0.161, 0.142, 0.129, 0.114, 0.12,
             0.117, 0.106, 0.1, 0.102, 0.09, 0.087, 0.083, 0.091, 0.08, 0.07, 0.063, 0.078, 0.067, 0.07, 0.079, 0.074,
             0.069, 0.078, 0.089, 0.093, 0.103, 0.117, 0.125, 0.113, 0.136, 0.153, 0.171, 0.153, 0.171, 0.184, 0.2,
             0.208, 0.21, 0.211, 0.22, 0.22, 0.22, 0.239, 0.239, 0.21, 0.212, 0.2, 0.186, 0.195, 0.195, 0.197, 0.2,
             0.161, 0.157, 0.154, 0.15]
_lr_now = datetime(2026, 10, 8, 9, 39)
_lr = plans.compute_low_charge_plan(None, 38, _lr_fc, _lr_now, 1.7, 4.5, 1.0, 15.0, [0.15] * 121, _lr_price, 72, 3.9,
                                    high_threshold_kwh=16.5, charge_efficiency=0.9, discharge_efficiency=0.9,
                                    floor_kwh=0.75, peak_kwh=max(_lr_fc))
check("deficit band: a dip that's at its lowest right now (the sun lifts it) doesn't start a charge right away",
      _lr["start_unit"] > 38 and _lr["dip_min_kwh"] == 1.27)
check("deficit band: the next dip's charge goes in the cheap midday window (11:30-16:30, 0.063-0.10)",
      46 <= _lr["start_unit"] and _lr["end_unit"] <= 68 and max(_lr_price[_lr["start_unit"]:_lr["end_unit"]]) <= 0.103)

# 2026.10.3: a charge in a sunny window is drawn as it runs - the grid stops at the target level, the sun counts toward it
_lr_run = {"active": True, "start_unit": 38, "end_unit": 58, "target_kwh": 6.67, "target_energy_kwh": 10.5,
           "avg_home_load_kw": 0.156, "effective_charge_per_unit": 0.3474, "discharge_efficiency": 0.9,
           "grid_rate_per_unit": 0.3825, "target_reached": False}
_lr_adj = plans.compose_forecast_adjusted(_lr_fc, _lr_run, {"active": False}, 38, _lr_now, upper_limit_kwh=15.0,
                                          battery_now_kwh=3.9)
check("forecast: the running charge stops at 10.5 kWh and the sun takes it to ~12.2, not over 15 (no false surplus)",
      abs(max(_lr_adj[:12]) - 12.21) < 0.05 and _lr_adj[3] > 10.5 > _lr_adj[2])
_lr_sale = {"active": True, "start_unit": 40, "end_unit": 44, "target_kwh": 2.0, "target_energy_kwh": 2.0,
            "grid_rate_per_unit": 2.5, "target_reached": False}
_lr_sale_adj = plans.compose_forecast_adjusted([4.0] * 6, {"active": False}, _lr_sale, 40, datetime(2026, 10, 8, 10, 0),
                                               upper_limit_kwh=15.0, battery_now_kwh=4.0)
check("forecast: a running sale stops at its target level", _lr_sale_adj[0] == 2.0 and _lr_sale_adj[5] == 2.0)

# ---------------------------------------------------------------------------
# 2026.10.4: the charge plans know what the grid can really add per quarter
# (the battery's max charge speed minus the sun already charging it)
# ---------------------------------------------------------------------------
_gr_now = datetime(2026, 10, 8, 6, 0)
_gr_net = [round((2.5 if 9 <= (6 + h) % 24 < 16 and h < 24 else 0.0) - 0.4, 2) for h in range(72)]  # 2.5 kW sun, 0.4 kW house
_gr = forecasting.grid_charge_rates(_gr_net, _gr_now, 1.8, 1.8, 192, 0.9, 0.9)
check("charge rates: no sun - the grid charge plus the house it now covers (1.8 x 0.9 - 0.4 x 0.9 + 0.4 / 0.9) / 4",
      abs(_gr[24] - round((1.4 * 0.9 + 0.4 / 0.9) / 4, 4)) < 1e-4)
check("charge rates: the sun alone already fills the 1.8 kW max charge speed - the grid adds nothing", _gr[44] == 0.0)
check("charge rates: before this hour 0", _gr[0] == 0.0 and _gr[23] == 0.0)
check("charge rates: half the sun - the grid fills the rest up to the max charge speed",
      forecasting.grid_charge_rates([1.0], datetime(2026, 10, 8, 12, 0), 1.8, 1.8, 52, 1.0, 1.0)[48] == round(0.8 / 4, 4))

# A 10 kWh battery with a 1.8 kW charger, 2.5 kW sun and 0.4 kW house: the sun fills it today, then two dark days.
# The cheapest hours (0.08) are in the sun, where the grid can't add anything.
_gr_raw = forecasting.build_battery_forecast(_gr_net, 5.5, _gr_now, 1.8, 3.0, 0.9, 0.9)
_gr_fc, _ = forecasting.clip_at_capacity(_gr_raw, 5.5, 10.0)
_gr_price = [0.25] * 36 + [0.20] * 8 + [0.08] * 20 + [0.22] * 32 + [0.18] * 96
_gr_kw = dict(charge_speed_kw=1.8, low_threshold_kwh=3.0, minimum_charge_target_kwh=0.5, upper_limit_kwh=10.0,
              usage=[0.4] * 121, all_price=_gr_price, planning_horizon_hours=48, battery_now_kwh=5.5,
              high_threshold_kwh=11.0, charge_efficiency=0.9, discharge_efficiency=0.9, peak_kwh=max(_gr_raw[:49]))
_gr_old = plans.compute_low_charge_plan(None, 24, _gr_fc, _gr_now, **_gr_kw)
_gr_new = plans.compute_low_charge_plan(None, 24, _gr_fc, _gr_now, charge_rates=_gr, **_gr_kw)
check("charge plan without the rates: a window in the sun, where the grid adds only a fraction",
      _gr_old["start_unit"] < 64 and sum(_gr[_gr_old["start_unit"]:_gr_old["end_unit"]]) < _gr_old["target_kwh"] / 2)
check("charge plan with the rates: a window where the grid really delivers (tonight, after the sun)",
      _gr_new["start_unit"] >= 64 and sum(_gr[_gr_new["start_unit"]:_gr_new["end_unit"]]) >= _gr_new["block_kwh"] - 1e-3)
check("charge plan with the rates (2026.10.6): only what's needed before the last known price now, the rest later",
      _gr_new["planned_kwh"] < _gr_new["target_kwh"] and _gr_new["blocks"][-1]["end_unit"] <= len(_gr_price))
check("charge plan with the rates: never stops above 100 %", _gr_new["target_energy_kwh"] <= 10.0)
check("charge plan with the rates: its per-quarter rates are kept for drawing",
      len(_gr_new["grid_rates"]) == _gr_new["end_unit"] - _gr_new["start_unit"])

_rw = plans._rate_window(1.0, [0.4] * 8 + [0.0] * 8 + [0.4] * 8, [0.30] * 8 + [0.05] * 8 + [0.20] * 8,
                         [0.30] * 8 + [0.05] * 8 + [0.20] * 8, 0, 24, 0.45, 0.9)
check("rate window: quarters the grid can't add anything in don't count toward the amount", _rw == (16, 19))
# sun 09-11 / 15-17 1.2 kW, 11-15 2.5 kW, house 0.4, 1.8 kW charger; 09:00-17:00 cheap (0.10)
_sw_net = [round((2.5 if 11 <= (6 + h) % 24 < 15 else (1.2 if 9 <= (6 + h) % 24 < 11 or 15 <= (6 + h) % 24 < 17 else 0.0))
                 - 0.4, 2) for h in range(48)]
_sw_rates = forecasting.grid_charge_rates(_sw_net, datetime(2026, 10, 8, 6, 0), 1.8, 1.8, 192, 0.9, 0.9)
_sw_price = [0.25] * 36 + [0.10] * 32 + [0.22] * 28 + [0.20] * 96
check("rate window: the sun only makes the cheap window longer - 4 kWh in 09:00-16:45 (through the full-sun hours), "
      "not moved to the pricier night", plans._rate_window(4.0, _sw_rates, _sw_price, _sw_price, 24, 120, 0.45, 0.9) == (36, 67))

# negative price charge in the sun: only what the battery can still take
_nr_kw = dict(now=datetime(2026, 10, 8, 6, 0), all_price=[0.10] * 48 + [-0.30] * 8 + [0.10] * 40, threshold=-0.20,
              battery_forecast=[5.0] * 30, discharge_speed_kw=3.0, negative_price_charge_speed_kw=1.8,
              low_threshold_kwh=1.0, high_threshold_kwh=10.0, charge_efficiency=0.9)
check("negative price plan with the rates: nothing to gain when the sun already fills the max charge speed",
      plans.compute_negative_price_plan(None, 24, charge_rates=[0.0] * 96, **_nr_kw)["raw_potential_kwh"] == 0.0
      and plans.compute_negative_price_plan(None, 24, **_nr_kw)["raw_potential_kwh"] == 3.24)

# 2026.10.4: a dip only in the deficit band charges just what's missing, not up to 100 % at the peak
check("deficit band: just the deficit (4.5 - 1.27 = 3.23 kWh), not filled up to the peak (6.62 would fit)",
      _lr["target_kwh"] == 3.23 and not _lr["rounded_up_to_minimum"])
_lr_small = plans.compute_low_charge_plan(None, 38, [round(v + 2.73, 2) for v in _lr_fc], _lr_now, 1.7, 4.5, 1.0, 15.0,
                                          [0.15] * 121, _lr_price, 72, 6.63, high_threshold_kwh=16.5,
                                          charge_efficiency=0.9, discharge_efficiency=0.9, floor_kwh=0.75,
                                          peak_kwh=max(_lr_fc) + 2.73)
check("deficit band: a small deficit (0.5 kWh) is rounded up to the minimum charge target (1.0), still not filled up",
      _lr_small["target_kwh"] == 1.0 and _lr_small["rounded_up_to_minimum"] and _lr_small["soft_deficit_kwh"] == 0.5)

# 2026.10.4: a charge lifts the dip to the low threshold plus the Safety buffer
_cb = plans.compute_low_charge_plan(None, 38, _lr_fc, _lr_now, 1.7, 4.5, 1.0, 15.0, [0.15] * 121, _lr_price, 72, 3.9,
                                    high_threshold_kwh=16.5, charge_efficiency=0.9, discharge_efficiency=0.9,
                                    floor_kwh=0.75, peak_kwh=max(_lr_fc), charge_buffer_kwh=0.75)
check("charge buffer: the deficit band charges up to the deficit minimum + the Safety buffer (4.5 + 0.75 - 1.27)",
      _cb["target_kwh"] == 3.98)
_cb_low = plans.compute_low_charge_plan(None, 0, synthetic_forecast, now_top_of_hour, 7.0, 3.0, 0.0, 30.0, usage_flat,
                                        all_price, 72, 10.0, charge_buffer_kwh=1.5)
check("charge buffer: a normal low charge too (3.0 + 1.5 - 2.0 = 2.5)", _cb_low["deficit_kwh"] == 2.5)
check("charge buffer: when to charge still follows the threshold itself (a dip to 3.5 with a 3.0 threshold: nothing)",
      plans.compute_low_charge_plan(None, 0, [10.0] * 5 + [3.5] * 20, now_top_of_hour, 7.0, 3.0, 0.0, 30.0, usage_flat,
                                    all_price, 72, 10.0, charge_buffer_kwh=1.5)["active"] is False)

# 2026.10.5: live dump (30 kWh, 14:24, 24.6 kWh, deficit minimum 9 + 3 buffer). Nothing was planned for the dip to
# 5.58 tomorrow night: "only 1.56 kWh fits" - measured on this afternoon's peak (28.44), which a charge after it
# can't touch.
_d30_fc = [25.47,27.17,28.44,28.23,27.7,25.92,25.2,24.5,23.92,23.38,22.85,22.33,21.82,21.31,20.79,20.22,19.63,18.85,18.37,17.99,17.65,17.65,17.55,17.42,16.83,16.48,15.56,14.12,13.35,12.3,11.73,11.22,10.7,10.17,9.68,9.2,8.72,8.24,7.75,7.21,6.65,6.1,5.58,5.78,6.65,8.21,9.91,11.84,13.32,14.9,15.88,15.3,14.72,13.48,12.87,12.26,11.72,11.21,10.7,10.21,9.73,9.23,8.75,8.18,7.65,7.11,6.25,5.76,6.2,7.56,8.93,9.76,9.99,10.98,11.57,10.76,9.88,8.93,8.27,7.47,6.87,6.32,5.81,5.3,4.8,4.31,3.81,3.27,2.64,1.85,1.56,2.04,3.11,4.97,7.27,8.08,6,7.99,9.53,9.33,8.53,7.28,6.66,6.11,5.59,5.04,4.53,4.04,3.54,3.04,2.55,2.02,1.48,0.35,-0.24,-0.37,0.03,0.97,2.2,3.3,4]
_d30_price = [0.178,0.152,0.139,0.127,0.139,0.134,0.129,0.118,0.12,0.116,0.114,0.115,0.114,0.111,0.114,0.113,0.114,0.112,0.112,0.113,0.118,0.117,0.113,0.121,0.126,0.139,0.151,0.151,0.175,0.174,0.179,0.184,0.206,0.201,0.193,0.179,0.192,0.178,0.163,0.156,0.161,0.142,0.129,0.114,0.12,0.117,0.106,0.1,0.102,0.09,0.087,0.083,0.091,0.08,0.07,0.063,0.078,0.067,0.07,0.079,0.074,0.069,0.078,0.089,0.093,0.103,0.117,0.125,0.113,0.136,0.153,0.171,0.153,0.171,0.184,0.2,0.208,0.21,0.211,0.22,0.22,0.22,0.239,0.239,0.21,0.212,0.2,0.186,0.195,0.195,0.197,0.2,0.161,0.157,0.154,0.15,0.138,0.124,0.119,0.117,0.108,0.105,0.1,0.098,0.09,0.083,0.086,0.084,0.088,0.081,0.079,0.077,0.08,0.079,0.081,0.08,0.083,0.084,0.087,0.1,0.099,0.114,0.117,0.128,0.14,0.146,0.148,0.143,0.169,0.158,0.15,0.128,0.14,0.127,0.117,0.089,0.122,0.106,0.092,0.086,0.09,0.084,0.079,0.075,0.066,0.061,0.054,0.051,0.053,0.051,0.048,0.057,0.063,0.064,0.06,0.046,0.038,0.043,0.048,0.049,0.047,0.058,0.062,0.07,0.078,0.085,0.088,0.092,0.104,0.106,0.119,0.121,0.126,0.12,0.118,0.113,0.112,0.103,0.102,0.1,0.099,0.096,0.082,0.067,0.083,0.073,0.078,0.067,0.058,0.048,0.047,0.044]
_d30_net = [1.506,1.699,1.271,-0.211,-0.537,-1.776,-0.724,-0.693,-0.584,-0.542,-0.528,-0.515,-0.512,-0.516,-0.511,-0.573,-0.596,-0.78,-0.476,-0.379,-0.34,-0.002,-0.096,-0.136,-0.584,-0.351,-0.922,-1.435,-0.779,-1.042,-0.578,-0.502,-0.521,-0.532,-0.489,-0.48,-0.482,-0.483,-0.486,-0.544,-0.553,-0.557,-0.512,0.198,0.865,1.559,1.708,1.93,1.475,1.582,0.983,-0.58,-0.586,-1.235,-0.617,-0.608,-0.534,-0.512,-0.509,-0.493,-0.483,-0.494,-0.482,-0.57,-0.534,-0.536,-0.857,-0.496,0.438,1.366,1.371,0.831,0.221,0.992,0.588] + [-0.5]*50
_d30_rates = forecasting.grid_charge_rates(_d30_net, datetime(2026, 10, 8, 14, 24), 3.0, 5.0, 192, 0.9, 0.9)
_d30 = plans.compute_low_charge_plan(None, 57, _d30_fc, datetime(2026, 10, 8, 14, 24), 3.0, 9.0, 2.0, 30.0, [0.6] * 121,
                                     _d30_price, 72, 24.57, high_threshold_kwh=31.5, charge_efficiency=0.9,
                                     discharge_efficiency=0.9, floor_kwh=1.5, peak_kwh=max(_d30_fc[:73]),
                                     charge_rates=_d30_rates, charge_buffer_kwh=3.0)
check("deficit band: an earlier peak (this afternoon) doesn't limit a charge that comes after it - the whole 6.42 kWh",
      _d30["active"] and _d30["target_kwh"] == 6.42 and not _d30["soft_capped"])
check("deficit band: placed after that peak, in tomorrow's cheapest quarters (13:45-16:15, ~0.05)",
      _d30["start_unit"] >= 96 + 52 and _d30["end_unit"] <= 96 + 68
      and max(_d30_price[_d30["start_unit"]:_d30["end_unit"]]) <= 0.064)
check("deficit band: it fits under 100 % at every later peak",
      max(_d30_fc[(_d30["start_unit"] - 56) // 4:73]) + _d30["target_kwh"] <= 30.0)

# ---------------------------------------------------------------------------
# 2026.10.6: each part of a charge before it's needed, in the cheapest quarters, in blocks
# ---------------------------------------------------------------------------
# 18:00, 10 kWh, threshold 9, the battery drains 0.5 kWh an hour for two days; tonight 0.20, tomorrow 11-15 0.05
_tp_now = datetime(2026, 10, 9, 18, 0)
_tp_net = [-0.5] * 72
_tp_fc = forecasting.build_battery_forecast(_tp_net, 10.0, _tp_now, 5.0, 5.0, 1.0, 1.0)
_tp_price = [0.25] * 72 + [0.20] * 24 + [0.25] * 44 + [0.05] * 16 + [0.25] * 36
_tp_rates = forecasting.grid_charge_rates(_tp_net, _tp_now, 3.0, 5.0, 192, 1.0, 1.0)
_tp_kw = dict(high_threshold_kwh=33.0, charge_efficiency=1.0, discharge_efficiency=1.0, charge_rates=_tp_rates)
_tp = plans.compute_low_charge_plan(None, 72, _tp_fc, _tp_now, 3.0, 9.0, 0.5, 30.0, [0.5] * 121, _tp_price, 48, 10.0,
                                    min_charge_units=2, **_tp_kw)
check("blocks: tonight (0.20) only what's needed until the cheap valley tomorrow 11:00 (9 - 1.5 = 7.5 kWh)",
      _tp["start_unit"] == 72 and _tp["block_kwh"] == 7.5 and _tp["blocks"][0]["target_level_kwh"] == 16.25)
check("blocks: the rest in tomorrow's cheap valley (0.05), up to the last known price (14.25 kWh in all)",
      len(_tp["blocks"]) == 2 and _tp_price[_tp["blocks"][1]["start_unit"]] == 0.05 and _tp["planned_kwh"] == 14.25)
check("blocks: what's needed after the known prices waits for them (23.5 kWh needed in all)",
      _tp["target_kwh"] == 23.5 and _tp["planned_kwh"] < _tp["target_kwh"])
_tp_adj = plans.compose_forecast_adjusted(_tp_fc, _tp, {"active": False}, 72, _tp_now, upper_limit_kwh=30.0,
                                          battery_now_kwh=10.0)
check("blocks: drawn with both blocks - down to exactly 9 kWh at 11:00, then up again",
      _tp_adj[16] == 9.0 and _tp_adj[18] > 13.0)
_tp_sum = display.card_plans({"active": False}, {"active": False}, {"active": False}, _tp, {"active": False}, 72,
                             _tp_now, 10.0, 30.0)
check("blocks: the status card shows the first block (7.5 kWh) and +1 more",
      _tp_sum["buy"]["energy_kwh"] == 7.5 and _tp_sum["buy"]["more_blocks"] == 1
      and _tp_sum["buy"]["blocks"][0]["start"].startswith("2026-10-10T11:00"))
check("blocks: the Charge amount sensor follows the block",
      display.charge_display({"active": False}, {"active": False}, {"active": False}, _tp, 72, _tp_now)[0] == 7.5)

# the minimum charge duration: one cheap quarter in the middle of a dear stretch becomes a block of that length
_md_rates = [0.0] * 8 + [0.5] * 16
_md_price = [0.0] * 8 + [0.30] * 7 + [0.05] + [0.30] * 8
_md1 = plans._schedule_charge([(24, 0.5, True)], _md_rates, _md_price, _md_price, 8, 24, 0.5, 1.0, 1, [], 0, 1e9)
_md4 = plans._schedule_charge([(24, 0.5, True)], _md_rates, _md_price, _md_price, 8, 24, 0.5, 1.0, 4, [], 0, 1e9)
check("minimum duration: 15 min -> just the one cheap quarter", _md1 == [15])
check("minimum duration: 60 min -> a block of 4 quarters around it", len(_md4) == 4 and 15 in _md4
      and _md4 == list(range(_md4[0], _md4[0] + 4)))
check("minimum duration: blocks are trimmed back to what's needed (never below the minimum)",
      plans._schedule_charge([(24, 1.0, True)], _md_rates, _md_price, _md_price, 8, 24, 0.5, 1.0, 2, [], 0, 1e9)
      in ([14, 15], [15, 16]))

# 2026.10.7: a charge buys what's missing up to the low threshold + Safety buffer - no longer filled up to 100%
_nf = plans.compute_low_charge_plan(None, 0, [10.0] * 5 + [2.0] * 20, now_top_of_hour, 7.0, 3.0, 1.0, 30.0, usage_flat,
                                    all_price, 72, 10.0, charge_buffer_kwh=1.5)
check("no fill: just the deficit + buffer (3.0 + 1.5 - 2.0 = 2.5), not up to 100 % at the peak (20 would fit)",
      _nf["target_kwh"] == 2.5)
check("no fill: still rounded up to the minimum charge target",
      plans.compute_low_charge_plan(None, 0, [10.0] * 5 + [2.0] * 20, now_top_of_hour, 7.0, 3.0, 5.0, 30.0, usage_flat,
                                    all_price, 72, 10.0, high_threshold_kwh=33.0, charge_buffer_kwh=1.5)["target_kwh"] == 5.0)

print()

# 2026.10.8: live dump (30 kWh, 18:36, 15.15 kWh, deficit minimum 9 + buffer 3, surplus 1.5): the band dip bottoms
# out at 08:00 (7.21). It planned 3.5 kWh at 01:00 and the last 1.29 kWh at 10:45 - after the lowest point, with
# the battery already climbing on the sun (36%), where it lifts nothing. The band is now in by its lowest point.
_eb_fc = [14.96, 13.92, 13.34, 12.84, 12.32, 11.79, 11.3, 10.82, 10.34, 9.85, 9.37, 8.82, 8.27, 7.71, 7.21, 7.41, 8.27, 9.82, 11.5, 13.38, 14.81, 16.32, 17.22, 16.58, 15.99, 14.75, 14.14, 13.53, 13, 12.48, 11.97, 11.48, 11, 10.5, 10.02, 9.45, 8.92, 8.38, 7.61, 7.37, 7.91, 9.45, 11.25, 12.52, 13.23, 14.87, 16.22, 16.15, 15.37, 14.41, 13.75, 12.95, 12.35, 11.81, 11.29, 10.79, 10.28, 9.79, 9.3, 8.76, 8.13, 7.33, 6.99, 7.49, 8.58, 10.55, 13.13, 14.26, 12.46, 14.49, 15.86, 15.45, 14.63, 13.38, 12.76, 12.21, 11.69, 11.14, 10.63, 10.14]
_eb_price = [0.138, 0.124, 0.119, 0.117, 0.108, 0.105, 0.1, 0.098, 0.09, 0.083, 0.086, 0.084, 0.088, 0.081, 0.079, 0.077, 0.08, 0.079, 0.081, 0.08, 0.083, 0.084, 0.087, 0.1, 0.099, 0.114, 0.117, 0.128, 0.14, 0.146, 0.148, 0.143, 0.169, 0.158, 0.15, 0.128, 0.14, 0.127, 0.117, 0.089, 0.122, 0.106, 0.092, 0.086, 0.09, 0.084, 0.079, 0.075, 0.066, 0.061, 0.054, 0.051, 0.053, 0.051, 0.048, 0.057, 0.063, 0.064, 0.06, 0.046, 0.038, 0.043, 0.048, 0.049, 0.047, 0.058, 0.062, 0.07, 0.078, 0.085, 0.088, 0.092, 0.104, 0.106, 0.119, 0.121, 0.126, 0.12, 0.118, 0.113, 0.112, 0.103, 0.102, 0.1, 0.099, 0.096, 0.082, 0.067, 0.083, 0.073, 0.078, 0.067, 0.058, 0.048, 0.047, 0.044, 0.01, 0.02, 0.019, 0.014, 0.014, 0.011, 0.015, 0.017, 0.014, 0.013, 0.014, 0.018, 0.016, 0.015, 0.015, 0.018, 0.014, 0.016, 0.015, 0.017, 0.013, 0.013, 0.014, 0.017, 0.018, 0.025, 0.028, 0.027, 0.047, 0.048, 0.048, 0.044, 0.057, 0.06, 0.058, 0.053, 0.057, 0.048, 0.046, 0.036, 0.035, 0.033, 0.021, 0.011, 0.015, 0.007, 0.003, 0.004, -0.003, -0.004, -0.005, -0.004, -0.0, -0.0, -0.001, -0.002, -0.004, -0.003, -0.003, -0.003, 0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 0.021, 0.034, 0.031, 0.065, 0.109, 0.128, 0.115, 0.126, 0.139, 0.176, 0.171, 0.168, 0.166, 0.169, 0.153, 0.147, 0.144, 0.139, 0.133, 0.128, 0.127, 0.121, 0.127, 0.123, 0.129, 0.134, 0.118, 0.119, 0.121, 0.116]
_eb_usage = [0.834, 1.042, 0.578, 0.502, 0.521, 0.532, 0.489, 0.48, 0.482, 0.483, 0.486, 0.544, 0.553, 0.557, 0.667, 0.636, 0.65, 0.582, 0.847, 0.838, 1.201, 0.763, 0.8, 1.322, 0.685, 1.235, 0.617, 0.608, 0.534, 0.512, 0.509, 0.493, 0.483, 0.494, 0.482, 0.57, 0.534, 0.536, 0.987, 1.221, 1.089, 0.784, 0.953, 1.637, 2.045, 0.821, 0.756, 1.32, 0.957, 0.954, 0.659, 0.801, 0.601, 0.545, 0.516, 0.502, 0.509, 0.489, 0.493, 0.541, 0.63, 0.795, 0.523, 0.51, 0.606, 0.581, 0.579, 2.245, 5.007, 0.649, 0.715, 1.432, 0.898, 1.246, 0.621, 0.548, 0.521, 0.557, 0.51, 0.488]
_eb_rates = [0.0] * 72 + [1.75] * 120
_eb = plans.compute_low_charge_plan(None, 74, _eb_fc, datetime(2026, 10, 9, 18, 36), 7.0, 9.0, 1.0, 30.0, _eb_usage,
                                    _eb_price, 72, 15.15, high_threshold_kwh=31.5, floor_kwh=1.5,
                                    peak_kwh=max(_eb_fc[:73]), charge_rates=_eb_rates, charge_buffer_kwh=3.0)
check("band dip: all of it bought before the lowest point (08:00-09:00), none after",
      _eb["active"] and _eb["dip_min_kwh"] == 7.21 and _eb["breach_unit"] == 132
      and all(b["end_unit"] <= 132 for b in _eb["blocks"]) and round(sum(b["kwh"] for b in _eb["blocks"]), 2) == 4.79)
check("band dip: in the cheap night (0.01-0.02), not at 10:45",
      all(max(_eb_price[b["start_unit"]:b["end_unit"]]) <= 0.02 for b in _eb["blocks"]))


# 2026.10.10: a sale before an overflow has to beat the overflow's own price. Live dump (30 kWh, max SOC 110%,
# 14:40): it planned 3.72 kWh at 16:30-17:00 (0.119/0.149) because the forecast passes 110% at 17:00, while the
# overflow it prevents would go to the grid at ~0.126 anyway and the price kept rising (0.24 tonight, 0.288
# tomorrow 08:00). Now the overflow goes to the grid and the rest (1.82 kWh) is sold before tomorrow's overflow.
_ov_fc = [28.4, 30.13, 31.61, 31.9, 31.4, 30.44, 29.78, 28.98, 28.38, 27.84, 27.32, 26.82, 26.31, 25.82, 25.33, 24.79, 24.16, 23.36, 23.2, 23.84, 24.94, 26.88, 29.41, 30.54, 28.82, 31.24, 33.33, 33.72, 33.12, 31.88, 31.26, 30.71, 30.19, 29.63, 29.12, 28.63, 28.14, 27.64, 27.15, 26.62, 26.07, 24.94, 24.36, 24.18, 24.35, 24.76, 25.18, 25.73, 26.22, 26.46, 26.17, 24.29, 23.38, 21.99, 21.01, 20.46, 19.92, 19.4, 18.89, 18.39, 17.89, 17.39, 16.89, 16.35, 15.79, 14.82, 14.41, 14.59, 15.38, 17.03, 19.22, 21.47, 22.69]
_ov_price = [0.142, 0.118, 0.104, 0.097, 0.112, 0.106, 0.105, 0.098, 0.105, 0.099, 0.101, 0.099, 0.098, 0.1, 0.103, 0.1, 0.102, 0.103, 0.104, 0.105, 0.104, 0.1, 0.102, 0.104, 0.099, 0.103, 0.107, 0.114, 0.125, 0.129, 0.123, 0.127, 0.14, 0.141, 0.144, 0.139, 0.136, 0.129, 0.117, 0.106, 0.112, 0.095, 0.076, 0.052, 0.045, 0.029, 0.025, 0.034, 0.025, 0.026, 0.023, 0.018, 0.016, 0.014, 0.012, 0.017, 0.019, 0.025, 0.035, 0.047, 0.04, 0.057, 0.075, 0.098, 0.094, 0.106, 0.119, 0.149, 0.15, 0.19, 0.216, 0.232, 0.217, 0.228, 0.229, 0.238, 0.224, 0.234, 0.24, 0.242, 0.241, 0.235, 0.233, 0.226, 0.226, 0.215, 0.212, 0.206, 0.206, 0.203, 0.201, 0.19, 0.199, 0.189, 0.182, 0.166, 0.18, 0.179, 0.178, 0.176, 0.175, 0.17, 0.172, 0.172, 0.174, 0.17, 0.165, 0.163, 0.166, 0.166, 0.165, 0.167, 0.164, 0.163, 0.165, 0.171, 0.166, 0.171, 0.178, 0.198, 0.195, 0.215, 0.227, 0.241, 0.24, 0.257, 0.263, 0.269, 0.288, 0.276, 0.254, 0.236, 0.263, 0.227, 0.21, 0.187, 0.211, 0.194, 0.186, 0.175, 0.183, 0.171, 0.164, 0.161, 0.156, 0.154, 0.15, 0.146, 0.146, 0.142, 0.142, 0.139, 0.14, 0.143, 0.15, 0.153, 0.151, 0.155, 0.161, 0.165, 0.155, 0.171, 0.192, 0.208, 0.187, 0.223, 0.248, 0.268, 0.259, 0.26, 0.277, 0.291, 0.284, 0.282, 0.28, 0.272, 0.273, 0.257, 0.247, 0.225, 0.217, 0.205, 0.193, 0.184, 0.196, 0.188, 0.189, 0.177, 0.182, 0.178, 0.177, 0.173]
_ov_usage = [2.045, 0.821, 0.756, 1.32, 0.957, 0.954, 0.659, 0.801, 0.601, 0.545, 0.516, 0.502, 0.509, 0.489, 0.493, 0.541, 0.63, 0.795, 0.523, 0.51, 0.606, 0.581, 0.579, 2.245, 5.007, 0.649, 0.715, 1.432, 0.898, 1.246, 0.621, 0.548, 0.521, 0.557, 0.51, 0.488, 0.496, 0.497, 0.495, 0.526, 0.548, 1.13, 0.663, 0.627, 0.786, 0.766, 0.66, 0.658, 0.818, 0.72, 0.881, 2.099, 0.957, 1.387, 0.98, 0.549, 0.541, 0.52, 0.508, 0.501, 0.505, 0.497, 0.5, 0.543, 0.558, 0.968, 0.526, 0.59, 0.766, 0.646, 0.666, 0.879, 1.597]
_ov_kw = dict(safety_buffer_kwh=3.0, sale_target_kwh=30.0)
_ov_old = plans.compute_high_discharge_plan(None, 58, _ov_fc, datetime(2026, 10, 11, 14, 40), 10.0, 31.5, 1.5, _ov_usage,
                                            _ov_price, 72, 28.14, **_ov_kw)
_ov = plans.compute_high_discharge_plan(None, 58, _ov_fc, datetime(2026, 10, 11, 14, 40), 10.0, 31.5, 1.5, _ov_usage,
                                        _ov_price, 72, 28.14, capacity_kwh=30.0, **_ov_kw)
check("overflow: without the capacity it still sells before the first overflow (16:30, 3.72 kWh)",
      _ov_old["start_unit"] == 66 and _ov_old["surplus_kwh"] == 3.72 and "overflow_to_grid" not in _ov_old)
check("overflow: today's overflow (15:00-18:00, 1.9 kWh at ~0.126) goes to the grid - a sale at ~0.134 isn't worth it",
      len(_ov["overflow_to_grid"]) == 1 and _ov["overflow_to_grid"][0]["start_unit"] == 60
      and _ov["overflow_to_grid"][0]["end_unit"] == 72 and _ov["overflow_to_grid"][0]["kwh"] == 1.9
      and abs(_ov["overflow_to_grid"][0]["price"] - 0.1258) < 0.0005)
check("overflow: the rest (tomorrow's peak minus what went to the grid) is sold before tomorrow's overflow, at its best price",
      _ov["active"] and _ov["surplus_kwh"] == 1.82 and _ov["breach_unit"] == 168 and _ov["start_unit"] >= 72
      and _ov_price[_ov["start_unit"]] == max(_ov_price[72:168]))
check("overflow: the deferred sale keeps the safety floor (low point after it above 4.5)",
      _ov["low_point_after_sale_kwh"] > _ov["sale_floor_kwh"] == 4.5)

# the classic case stays: an expensive morning before a cheap midday overflow -> sell in the morning
_mo_fc = [25.0, 26.0, 27.5, 29.5, 31.0, 32.5, 33.0, 32.0, 30.5, 29.0] + [28.0 - 0.5 * h for h in range(40)]
_mo_price = [0.10] * 24 + [0.30] * 8 + [0.05] * 32 + [0.20] * 32 + [0.10] * 96
_mo = plans.compute_high_discharge_plan(None, 24, _mo_fc, datetime(2026, 10, 12, 6, 0), 10.0, 31.5, 1.5, [0.5] * 50,
                                        _mo_price, 48, 25.0, safety_buffer_kwh=3.0, sale_target_kwh=30.0, capacity_kwh=30.0)
check("overflow: a sale at 0.30 before a midday overflow at 0.05 still happens before the overflow",
      _mo["active"] and _mo["start_unit"] < _mo["breach_unit"] and _mo_price[_mo["start_unit"]] == 0.30
      and "overflow_to_grid" not in _mo)
# overflow hours without known prices: can't compare, so the sale stays before the first overflow
_mo2 = plans.compute_high_discharge_plan(None, 24, _mo_fc, datetime(2026, 10, 12, 6, 0), 10.0, 31.5, 1.5, [0.5] * 50,
                                         [0.05] * 34, 48, 25.0, safety_buffer_kwh=3.0, sale_target_kwh=30.0, capacity_kwh=30.0)
check("overflow: overflow prices not known yet -> sale before the first overflow, as before",
      _mo2["active"] and "overflow_to_grid" not in _mo2)


# 2026.10.10: a sale in blocks is shown and drawn like a charge in blocks
_sb_now = datetime(2026, 9, 24, 15, 27)
_sb_cards = display.card_plans({}, {}, {}, {}, plan_0924, 61, _sb_now, 26.82, 30.0, forecast=_d924["forecast"])
check("sale blocks: the Sell side shows the first block's amount and '+1' for the block after it",
      _sb_cards["sell"]["energy_kwh"] == 18.23 and _sb_cards["sell"]["more_blocks"] == 1
      and _sb_cards["sell"]["blocks"][0]["energy_kwh"] == 0.42)
check("sale blocks: the discharge sensors show the first block",
      display.discharge_display({}, {}, plan_0924, 61, _sb_now)[0] == 18.23)
_sb_adj = plans.compose_forecast_adjusted(_d924["forecast"], {"active": False}, plan_0924, 61, _sb_now,
                                          battery_now_kwh=26.82)
_sb_drop = [round(a - b, 2) for a, b in zip(_d924["forecast"], _sb_adj)]
check("sale blocks: both blocks are drawn (the drop grows after the second one and never exceeds the 18.65 kWh)",
      _sb_drop[10] > 10 and _sb_drop[-1] > _sb_drop[16] and max(_sb_drop) <= 18.65 + 0.01)


# ---------------------------------------------------------------------------
# 2026.10.11: electric car sessions (ev.py)
# ---------------------------------------------------------------------------
from zoneinfo import ZoneInfo as _ZI
_tz = _ZI("Europe/Amsterdam")
_mon = datetime(2026, 10, 12, tzinfo=_tz)  # a Monday
_evh: dict = {}
_sur: dict = {}
def _put(day, hour, values, surplus=None):
    e0 = int(datetime.combine(day.date(), datetime.min.time().replace(hour=hour), tzinfo=_tz).timestamp())
    for i, v in enumerate(values):
        _evh[e0 + i * 3600] = v
        if surplus is not None:
            _sur[e0 + i * 3600] = surplus[i]
for _w in range(1, 7):
    _past = _mon - timedelta(weeks=_w)
    for _h in range(24):  # data exists every hour (0 when not charging)
        _evh.setdefault(int(datetime.combine(_past.date(), datetime.min.time().replace(hour=_h), tzinfo=_tz).timestamp()), 0.0)
    if _w in (1, 2, 3, 5):
        _put(_past, 18, [3.0, 3.6, 3.6])          # Monday evening, 10.2 kWh
    if _w == 4:
        _put(_past, 19, [3.6, 3.6, 1.0])          # same group, an hour later
    if _w in (2, 6):
        _put(_past + timedelta(days=1), 20, [3.6, 3.6])   # Tuesday: only 2 of 6 weeks
    _put(_past + timedelta(days=2), 11, [2.0, 3.0, 2.5], surplus=[2.5, 3.5, 3.0]) if _w <= 4 else None  # Wednesday solar
_days = [_mon + timedelta(days=i) for i in range(5)]
_pred = ev.detect_sessions(_evh, _sur, _days, 6, 3, 6, 16, _tz)
_by_day = {s["key"][:10]: s for s in _pred}
check("ev: Monday evening predicted (5 of 6 weeks, start 18:00, 9.8 kWh average: 4x 10.2 + 8.2)",
      "2026-10-12" in _by_day and _by_day["2026-10-12"]["key"] == "2026-10-12T18"
      and abs(_by_day["2026-10-12"]["kwh"] - 9.8) < 0.01 and _by_day["2026-10-12"]["mode"] == "fixed")
check("ev: the charging current comes from the typical full hour (3.6 kWh in an hour on 3 phases -> 5 A, at least the min 6 A)",
      _by_day["2026-10-12"]["current_a"] == 6)
check("ev: Tuesday (2 of 6 weeks, not more than half) is not predicted", "2026-10-13" not in _by_day)
check("ev: Wednesday's sessions that fit in the solar surplus become a solar session",
      _by_day["2026-10-14"]["mode"] == "solar" and _by_day["2026-10-14"]["solar_history"] is True
      and _by_day["2026-10-14"]["key"] == "2026-10-14T11")
check("ev: no prediction without history", ev.detect_sessions({}, None, _days, 6, 3, 6, 16, _tz) == [])

check("ev: power from current - 16 A on 3 phases is 11.04 kW, 6 A on 1 phase 1.38 kW",
      ev.power_kw(16, 3) == 11.04 and ev.power_kw(6, 1) == 1.38)

# a car with a battery: the session in %, the start SOC worked back from the target
_car = {"id": "c1", "name": "Gezinsauto", "capacity_kwh": 60, "target_soc": 80}
_s = ev.apply_car({"id": "x", "start": 0, "kwh": 10.2}, _car)
check("ev: 10.2 kWh on a 60 kWh car with target 80% starts at 63%", _s["start_soc"] == 63 and _s["target_soc"] == 80)
_s2 = ev.apply_car({"id": "x", "start": 0, "kwh": 10.2, "start_soc": 30, "target_soc": 80}, _car)
check("ev: a lower start SOC makes the session bigger (30% -> 80% = 30 kWh)", _s2["kwh"] == 30.0)

_now = int(datetime(2026, 10, 12, 14, 20, tzinfo=_tz).timestamp())
_lst = ev.build_sessions(_pred, {"h:2026-10-12T18": {"current_a": 16, "enabled": True}},
                         [{"id": "m1", "start": int(datetime(2026, 10, 13, 9, tzinfo=_tz).timestamp()), "kwh": 5.0,
                           "mode": "fixed", "current_a": 10, "car": None, "enabled": False}],
                         [_car], _now, _now + 5 * 86400)
check("ev: an override marks the session 'edited', a manual one 'manual', sorted by start",
      [s["label"] for s in _lst] == ["edited", "manual", "history"] and _lst[0]["current_a"] == 16)
check("ev: with one car every session is that car's (in %)", all(s["car"] == "c1" and s["start_soc"] is not None for s in _lst))
_lst2 = ev.build_sessions(_pred, {}, [], [_car, {"id": "c2", "name": "Werkauto", "capacity_kwh": 52, "target_soc": 90}],
                          _now, _now + 5 * 86400)
check("ev: with two cars a historical session has no car (kWh only)", all(s["car"] is None and s["start_soc"] is None for s in _lst2))
_late = int(datetime(2026, 10, 12, 19, 30, tzinfo=_tz).timestamp())
check("ev: a session more than an hour past its start without charging is gone",
      not any(s["key"] == "2026-10-12T18" for s in ev.build_sessions(_pred, {}, [], [], _late, _late + 86400)))
check("ev: ...unless it's running",
      any(s.get("key") == "2026-10-12T18" and s["running"]
          for s in ev.build_sessions(_pred, {}, [], [], _late, _late + 86400, running_id="h:2026-10-12T18")))

# profiles: fixed 16 A / 3 phases = 11.04 kW, 20 kWh from 18:00 -> done at 19:48:42
_h0 = int(datetime(2026, 10, 12, 14, tzinfo=_tz).timestamp())
_fixed = {"id": "f", "start": int(datetime(2026, 10, 12, 18, tzinfo=_tz).timestamp()), "kwh": 20.0, "mode": "fixed", "current_a": 16}
_prof, _info = ev.session_profile(_fixed, _now, _h0, 24, [0.0] * 24, 3, 6, 16, _h0 + 10 * 3600)
check("ev: fixed session 11.04 kW from 18:00: 11.04 kWh at 18:00, the rest at 19:00, done 19:48",
      _prof[4] == 11.04 and abs(_prof[5] - 8.96) < 0.001 and sum(_prof) == 20.0
      and datetime.fromtimestamp(_info["end"], _tz).strftime("%H:%M") == "19:48" and _info["warning"] is None)
# solar: surplus per hour 2 / 5 / 8 / 3 kWh from 11:00; min 6 A on 3 phases = 4.14 kW, so the 2 and 3 don't start it
_sol = {"id": "s", "start": int(datetime(2026, 10, 12, 11, tzinfo=_tz).timestamp()), "kwh": 10.0, "mode": "solar", "current_a": 16}
_h11 = int(datetime(2026, 10, 12, 11, tzinfo=_tz).timestamp())
_net = [2.0, 5.0, 8.0, 3.0] + [0.0] * 20
_ps, _is = ev.session_profile(_sol, _h11, _h11, 24, _net, 3, 6, 16, _h11 + 13 * 3600)
check("ev: solar session takes only the surplus above the min current: 0, 5, 5 (of 8), done 13:37",
      _ps[:4] == [0.0, 5.0, 5.0, 0.0] and datetime.fromtimestamp(_is["end"], _tz).strftime("%H:%M") == "13:37")
_ps2, _is2 = ev.session_profile({**_sol, "kwh": 20.0}, _h11, _h11, 24, _net, 3, 6, 16, _h11 + 13 * 3600)
check("ev: not enough surplus that day -> 'short', charged 13 kWh, no end", _is2["warning"] == "short" and _is2["kwh"] == 13.0 and _is2["end"] is None)
_ps3, _is3 = ev.session_profile(_sol, _h11, _h11, 24, [1.0] * 24, 3, 6, 16, _h11 + 13 * 3600)
check("ev: no surplus above the min current that day -> 'no_surplus'", _is3["warning"] == "no_surplus" and sum(_ps3) == 0)
# a running session: what's already delivered counts, hour 0 is a full-hour value
_run = {**_fixed, "start": _h0}
_pr, _ir = ev.session_profile(_run, _now, _h0, 24, [0.0] * 24, 3, 6, 16, _h0 + 10 * 3600, delivered_kwh=15.0)
check("ev: running session: 5 kWh left, in the current hour (scaled to a full-hour value: 5 / (40/60))",
      abs(_pr[0] - 7.5) < 0.001 and sum(_pr[1:]) == 0)
_tot, _sess = ev.ev_forecast([_fixed, {**_sol, "enabled": False}], _now, _h0, 24, [0.0] * 24, 3, 6, 16, _tz)
check("ev: a switched-off session doesn't count in the forecast, but still gets its info",
      abs(sum(_tot) - 20.0) < 0.001 and len(_sess) == 2 and _sess[1]["warning"] == "no_surplus")

# the house usage forecast leaves the car's history out (always, also with
# prediction off); a charger younger than the history counts as 0
def _ev_sums(age_hours, per_hour):
    first = usage_base_epoch - age_hours * HOUR_S
    series, total = {}, 0.0
    for epoch in range(first, usage_base_epoch, HOUR_S):
        total += per_hour(epoch)
        series[epoch] = round(total, 6)
    return series

# the meter includes the car: 1 kWh house every hour, plus 4 kWh car at 17 UTC
_sums_ev = {
    "sensor.new_meter": _ev_sums(24 * 7 * 6 + 2, lambda e: 1.0 + (4.0 if (e // HOUR_S) % 24 == 17 else 0.0)),
    "sensor.ev": _ev_sums(24 * 7 * 6 + 2, lambda e: 4.0 if (e // HOUR_S) % 24 == 17 else 0.0),
}
_fe, _ = usage_forecast.compute_usage_forecast_from_consumption_detailed(
    _sums_ev, ["sensor.new_meter"], usage_now, 48, 6, subtract_entities=["sensor.ev"])
_fw, _ = usage_forecast.compute_usage_forecast_from_consumption_detailed(
    _sums_ev, ["sensor.new_meter"], usage_now, 48, 6)
check("usage: the car's history is taken out of the house usage forecast (1 kWh every hour, also at 17 UTC)",
      all(abs(v - 1.0) < 1e-6 for v in _fe) and max(_fw) > 4.9)
_young_ev = {**_sums_ev, "sensor.ev": _ev_sums(30, lambda e: 4.0 if (e // HOUR_S) % 24 == 17 else 0.0)}
_fy, _ = usage_forecast.compute_usage_forecast_from_consumption_detailed(
    _young_ev, ["sensor.new_meter"], usage_now, 48, 6, subtract_entities=["sensor.ev"])
check("usage: a charger younger than the history counts as 0 there, never below 0",
      min(_fy) >= 0 and len(_fy) == 48)
_evh2, _sur2 = usage_forecast.ev_hourly_history(
    _sums_ev, ["sensor.ev"], None, [], usage_base_epoch - 48 * HOUR_S, usage_base_epoch)
check("ev history: the car's kWh per hour, no surplus without solar statistics",
      _sur2 is None and len(_evh2) == 48 and abs(sum(_evh2.values()) - 8.0) < 1e-6)
_sums_sol = {
    "sensor.imp": _ev_sums(50, lambda e: 1.0 + (4.0 if (e // HOUR_S) % 24 == 17 else 0.0)),
    "sensor.exp": _ev_sums(50, lambda e: 2.0),
    "sensor.pv": _ev_sums(50, lambda e: 3.0),
    "sensor.ev": _ev_sums(50, lambda e: 4.0 if (e // HOUR_S) % 24 == 17 else 0.0),
}
_evh3, _sur3 = usage_forecast.ev_hourly_history(
    _sums_sol, ["sensor.ev"], (["sensor.imp"], ["sensor.exp"], ["sensor.pv"], None, None), ["sensor.pv"],
    usage_base_epoch - 24 * HOUR_S, usage_base_epoch)
_e17 = [e for e in _evh3 if (e // HOUR_S) % 24 == 17][0]
check("ev history: solar surplus = solar minus the house without the car (3 - 2 = 1 kWh, also while charging)",
      abs(_sur3[_e17] - 1.0) < 1e-6 and all(abs(v - 1.0) < 1e-6 for v in _sur3.values()))

# ev_runtime: the card's edits, the running session, the forecast
ev_runtime = _load("ev_runtime")
_rt = ev_runtime.EvRuntime()
_rt.history = (_evh, _sur)
_conf1 = {"phases": 3, "min_current": 6, "max_current": 16, "predict": True, "cars": [_car]}
_n1 = datetime(2026, 10, 12, 14, 20, tzinfo=_tz)
_tot1, _a1 = _rt.update(_conf1, _n1, _tz, 6, [0.0] * 121, 0.0, 100.0)
check("ev runtime: predicted sessions with the single car, in %, and the evening session in the forecast",
      [s["id"] for s in _a1["sessions"]][:2] == ["h:2026-10-12T18", "h:2026-10-14T11"]
      and _a1["sessions"][0]["car"] == "c1" and _a1["sessions"][0]["target_soc"] == 80
      and abs(sum(_tot1) - _a1["total_kwh"]) < 0.01 and _tot1[4] > 0)
check("ev runtime: a solar session without surplus warns, and is in the list with a red border",
      _a1["sessions"][1]["warning"] == "no_surplus" and _a1["sessions"][1]["solar_history"] is True)
_rt.save("h:2026-10-12T18", {"start_soc": 30, "current_a": 16}, int(_n1.timestamp()))
_tot2, _a2 = _rt.update(_conf1, _n1, _tz, 6, [0.0] * 121, 0.0, 100.0)
_s18 = _a2["sessions"][0]
check("ev runtime: an edit (start 30%) makes it 'edited', 30 kWh at 16 A, and keeps the average for 'back to average'",
      _s18["label"] == "edited" and _s18["kwh"] == 30.0 and _s18["current_a"] == 16 and _s18["power_kw"] == 11.04
      and _s18["history"]["start_soc"] == 64 and abs(sum(_tot2) - 30.0 - (_a2["total_kwh"] - 30.0)) < 0.01)
_mid = _rt.save(None, {"start": int(datetime(2026, 10, 13, 9, 30, tzinfo=_tz).timestamp()), "kwh": 5.0, "mode": "fixed"}, int(_n1.timestamp()))
_tot3, _a3 = _rt.update(_conf1, _n1, _tz, 6, [0.0] * 121, 0.0, 100.0)
check("ev runtime: a manual session lands in order, on the whole hour, labelled 'manual'",
      [s["id"] for s in _a3["sessions"]][1] == _mid and _a3["sessions"][1]["label"] == "manual"
      and _a3["sessions"][1]["start"].startswith("2026-10-13T09:00"))
# the charger starts at 17:50: the 18:00 session runs and starts now (17:00 hour)
_n4 = datetime(2026, 10, 12, 17, 50, tzinfo=_tz)
_tot4, _a4 = _rt.update(_conf1, _n4, _tz, 6, [0.0] * 121, 7400.0, 100.0)
_r4 = _a4["sessions"][0]
check("ev runtime: charging 10 min early -> that session runs, starting in the current hour",
      _r4["running"] and _r4["id"] == "h:2026-10-12T18" and _r4["start"].startswith("2026-10-12T17:00"))
_rt.save("h:2026-10-12T18", {"start": int(datetime(2026, 10, 13, 20, tzinfo=_tz).timestamp()), "target_soc": 75}, int(_n4.timestamp()))
_tot5, _a5 = _rt.update(_conf1, datetime(2026, 10, 12, 18, 30, tzinfo=_tz), _tz, 6, [0.0] * 121, 7400.0, 107.0)
_r5 = _a5["sessions"][0]
check("ev runtime: a running session keeps its start (the target can change: 30 -> 75% = 27 kWh); 7 kWh delivered counts, 20 stays planned",
      _r5["start"].startswith("2026-10-12T17:00") and _r5["delivered_kwh"] == 7.0 and _r5["kwh"] == 27.0
      and abs(sum(_tot5[1:]) + _tot5[0] * 0.5 - (20.0 + 5.0)) < 0.05)  # + the 5 kWh manual session
_rt.update(_conf1, datetime(2026, 10, 12, 19, 0, tzinfo=_tz), _tz, 6, [0.0] * 121, 0.0, 120.0)
_tot6, _a6 = _rt.update(_conf1, datetime(2026, 10, 12, 19, 11, tzinfo=_tz), _tz, 6, [0.0] * 121, 0.0, 120.0)
check("ev runtime: 10 minutes without power -> the session is done and gone",
      _rt.running is None and "h:2026-10-12T18" in _rt.done
      and not any(s["id"] == "h:2026-10-12T18" for s in _a6["sessions"]))
_rt2 = ev_runtime.EvRuntime()
_tot7, _a7 = _rt2.update({**_conf1, "predict": False}, _n1, _tz, 6, [0.0] * 121, 3000.0, 50.0)
check("ev runtime: prediction off -> empty list; a charge without a session becomes a manual running session",
      len(_a7["sessions"]) == 1 and _a7["sessions"][0]["label"] == "manual" and _a7["sessions"][0]["running"]
      and _a7["sessions"][0]["start"].startswith("2026-10-12T14:00"))
_rt2.remove(_a7["sessions"][0]["id"])
check("ev runtime: removing a manual session deletes it (and stops following it)", _rt2.manual == [] and _rt2.running is None)
_rt3 = ev_runtime.EvRuntime()
_rt3.restore(_rt.as_store())
check("ev runtime: the store round-trips", _rt3.as_store() == _rt.as_store())
# two solar sessions the same day share the surplus
_rt4 = ev_runtime.EvRuntime()
_h = lambda hh: int(datetime(2026, 10, 12, hh, tzinfo=_tz).timestamp())
_rt4.save(None, {"start": _h(11), "kwh": 6.0, "mode": "solar"}, _h(10))
_rt4.save(None, {"start": _h(11), "kwh": 6.0, "mode": "solar"}, _h(10))
_net4 = [0.0] * 121
_net4[1] = 6.0
_net4[2] = 6.0  # 11:00 and 12:00
_tot8, _a8 = _rt4.update({**_conf1, "cars": []}, datetime(2026, 10, 12, 10, 0, tzinfo=_tz), _tz, 6, _net4, 0.0, None)
check("ev runtime: two solar sessions share the surplus (6 + 6 kWh, not 12 + 6)",
      abs(sum(_tot8) - 12.0) < 0.01 and _tot8[1] == 6.0 and _tot8[2] == 6.0)

# ---------------------------------------------------------------------------
# 2026.10.13: the rest of a charge in blocks isn't dropped once the first block lifted the dip above the threshold
# ---------------------------------------------------------------------------
# 20:00, 12 kWh, threshold 9 + Safety buffer 1, -0.5 kWh an hour until 05:00; cheap (0.10) at 21:00 and 03:00 (30 min each)
_fu_price = [0.30] * 192
for _u in (84, 85, 108, 109):
    _fu_price[_u] = 0.10
_fu_net = [-0.5] * 9 + [2.0] * 20 + [-0.5] * 40
def _fu(now, batt, net, prev, unit, floor=None):
    fc = forecasting.build_battery_forecast(net, batt, now, 5.0, 5.0, 1.0, 1.0)
    rates = forecasting.grid_charge_rates(net, now, 3.0, 5.0, 192, 1.0, 1.0)
    return plans.compute_low_charge_plan(prev, unit, fc, now, 3.0, 9.0, 0.5, 30.0, [0.5] * 121, _fu_price, 48, batt,
                                         high_threshold_kwh=33.0, charge_efficiency=1.0, discharge_efficiency=1.0,
                                         charge_rates=rates, charge_buffer_kwh=1.0, min_charge_units=2, floor_kwh=floor)
_fu1 = _fu(datetime(2026, 10, 13, 20, 0), 12.0, _fu_net, None, 80)
check("follow-up: 2.5 kWh in two blocks - 1.5 at 21:00 and 1.0 at 03:00",
      [b["start_unit"] for b in _fu1["blocks"]] == [84, 108] and [b["kwh"] for b in _fu1["blocks"]] == [1.5, 1.0])
_fu2 = _fu(datetime(2026, 10, 13, 21, 0), 11.5, _fu_net[1:], _fu1, 84)
check("follow-up: while the first block runs the plan gets follow_up_until = the end of the last block (03:30)",
      _fu2["follow_up_until"] == int(datetime(2026, 10, 14, 3, 30).timestamp()) and _fu2["start_unit"] == 84)
# after the first block: 12.75 kWh, the dip's lowest point now 9.0 - not under the threshold any more
_fu3 = _fu(datetime(2026, 10, 13, 21, 30), 12.75, _fu_net[1:], _fu2, 86)
check("follow-up: the second block stays (1.0 kWh at 03:00, up to threshold + buffer), not rounded up to the minimum",
      _fu3["active"] and _fu3["start_unit"] == 108 and _fu3["target_kwh"] == 1.0 and _fu3.get("follow_up")
      and _fu3["follow_up_until"] == _fu2["follow_up_until"])
check("follow-up: without it the second block was dropped (the old behaviour)",
      not _fu(datetime(2026, 10, 13, 21, 30), 12.75, _fu_net[1:], {**_fu2, "follow_up_until": None}, 86)["active"])
check("follow-up: the marker is carried while nothing is needed, and ends at its time",
      _fu(datetime(2026, 10, 13, 21, 30), 14.0, _fu_net[1:], _fu2, 86) == {"active": False, "breach_unit": 999999, "follow_up_until": _fu2["follow_up_until"]}
      and not _fu(datetime(2026, 10, 14, 3, 45), 9.6, _fu_net[8:], _fu2, 96 + 15)["active"])
# (a smaller solar day after it, so the band charge fits under 100 % at the peak)
_fu_net2 = [-0.5] * 9 + [0.5] * 20 + [0.0] * 40
_fu5 = _fu(datetime(2026, 10, 13, 21, 30), 12.75, _fu_net2[1:], _fu2, 86, floor=7.0)
check("follow-up: in solar deficit mode too (the band up to deficit minimum + buffer)",
      _fu5["active"] and _fu5["target_kwh"] == 1.0 and _fu5["follow_up_until"] == _fu2["follow_up_until"]
      and not _fu(datetime(2026, 10, 13, 21, 30), 12.75, _fu_net2[1:], {**_fu2, "follow_up_until": None}, 86, floor=7.0)["active"])

# ---------------------------------------------------------------------------
# 2026.10.14: a full charge session worked out with another capacity / max SOC is planned again;
# the charging phase keeps its blocks; a stored session from another day isn't revived
# ---------------------------------------------------------------------------
_fc_now = datetime(2026, 10, 13, 21, 0)
_fc_price = [0.30] * 84 + [0.10] * 4 + [0.30] * 8 + [0.12] * 80 + [0.30] * 16
_fc_rates = [0.3932] * 192
def _fcp(prev, high, unit=84, now=_fc_now, batt=6.06, soc=40.4):
    return plans.compute_full_charge_plan(prev, unit, now, 14, 17.2, soc, 120, 30.0, batt, high, [0.2] * 121, 7.0,
                                          _fc_price, [batt] * 72, 52.5, 55.2, charge_efficiency=1.0,
                                          charge_rates=_fc_rates, min_charge_units=2)
_fc30 = _fcp(None, 33.0)
check("full charge: worked out with 33 kWh max (capacity 30): 27 kWh, the first block now",
      _fc30["phase"] == "scheduled" and _fc30["start_unit"] == 84 and _fc30["high_threshold_kwh"] == 33.0
      and _fc30["end_unit"] == 88 and len(_fc30["blocks"]) == 2
      and _fc30["end_at"] == int(datetime(2026, 10, 13, 22, 0).timestamp()))
_fc15 = _fcp(_fc30, 16.5)
check("full charge: the capacity is now 15 (max 16.5): planned again, not started with 27 kWh",
      _fc15["phase"] == "scheduled" and _fc15["deficit_kwh"] == round(16.5 - 6.06, 3) and _fc15["high_threshold_kwh"] == 16.5)
_fcc = _fcp(_fc15, 16.5)
check("full charge: the charging phase keeps the block - the cards show the first block, not the whole charge",
      _fcc["phase"] == "charging" and _fcc["block_kwh"] == _fc15["block_kwh"] and _fcc["blocks"] == _fc15["blocks"]
      and display.card_plans(_fcc, {"active": False}, {"active": False}, {"active": False}, {"active": False}, 84,
                             _fc_now, 6.06, 15.0)["buy"]["energy_kwh"] == round(_fc15["block_kwh"], 2)
      and display.charge_display(_fcc, {"active": False}, {"active": False}, {"active": False}, 84, _fc_now)[0]
      == round(_fc15["block_kwh"], 2))
check("full charge: a stored session of another day (its end time passed) isn't picked up again at the same time of day",
      _fcp({**_fcc, "end_at": int(datetime(2026, 10, 12, 22, 0).timestamp())}, 16.5)["phase"] == "scheduled")
check("full charge: a stored charging session without the new fields (older version) still runs on",
      _fcp({k: v for k, v in _fcc.items() if k not in ("high_threshold_kwh", "end_at")}, 16.5)["phase"] == "charging")

# ---------------------------------------------------------------------------
# 2026.10.16: heat pump model (heatpump.py, heatpump_runtime.py)
# ---------------------------------------------------------------------------
heatpump = _load("heatpump")
heatpump_runtime = _load("heatpump_runtime")
import math as _m
import random as _rnd
from datetime import date as _date
_rnd.seed(1)
_hp_today = _date(2026, 10, 13)
def _hp_journal(days=400, base=3.1, tb=15.5, b=0.92, wind=0.03, sun=-0.35, noise=0.5, start_offset=0):
    rows, prev = [], None
    for i in range(days + start_offset, start_offset, -1):
        d = _hp_today - timedelta(days=i)
        doy = d.timetuple().tm_yday
        t = 10 - 8 * _m.cos((doy - 15) / 365 * 2 * _m.pi) + _rnd.gauss(0, 3)
        w = abs(_rnd.gauss(4, 2))
        so = max(0.0, _rnd.gauss(8 + 6 * _m.sin((doy - 80) / 365 * 2 * _m.pi), 3))
        teff = 0.7 * t + 0.3 * (prev if prev is not None else t)
        prev = t
        hdd = max(0.0, tb - teff)
        e = base + b * hdd + wind * w * hdd + sun * so * (1 if hdd > 0 else 0) + _rnd.gauss(0, noise)
        hours = [0.03] * 24
        for hh in (6, 7, 12):
            hours[hh] = 0.1
        rows.append({"d": d.isoformat(), "e": round(max(e, 0.2), 3), "t": round(t, 2), "w": round(w, 2), "s": round(so, 2), "hours": hours})
    return rows
_hpj = _hp_journal()
_hpm = heatpump.fit(_hpj, _hp_today)
_hps = heatpump.summary(_hpm)
check("heat pump: the energy signature is found back (balance 15.5 C, 0.92 kWh/degree, base 3.1, sun -0.35, wind 0.03)",
      abs(_hps["balance_temp_c"] - 15.5) <= 0.5 and abs(_hps["kwh_per_degree_day"] - 0.92) < 0.08
      and abs(_hps["base_kwh_day"] - 3.1) < 0.4 and abs(_hps["solar_kwh_per_kwh"] + 0.35) < 0.1
      and abs(_hps["wind_kwh_per_ms_degree"] - 0.03) < 0.012 and _hps["r2"] > 0.9)
check("heat pump: too few days -> no model", heatpump.fit(_hpj[-10:], _hp_today) is None)
# frost days from long ago keep weight until newer days of their class come
_teffs = heatpump.effective_temps(_hpj)
_w = heatpump._weights(_hpj, _teffs, _hp_today)
_oldest_cold = min((r for r in _hpj), key=lambda r: _teffs[r["d"]])
_idx = _hpj.index(_oldest_cold)
check("heat pump: the coldest days keep weight (newest of their temperature class), ordinary old days fade",
      _w[_idx] >= 0.5 and min(_w) < 0.1)
# the fast part
_bump = [dict(r) for r in _hpj]
for r in _bump[-4:]:
    r["e"] = round(heatpump.predict_row(_hpm, r, heatpump.effective_temps(_bump)[r["d"]]) * 1.2, 3)
check("heat pump: 4 days 20 % above the model -> correction 1.2", abs(heatpump.correction(_hpm, _bump, _hp_today) - 1.2) < 0.02)
check("heat pump: no difference -> no correction", heatpump.correction(_hpm, _hpj, _hp_today) in (1.0,) or abs(heatpump.correction(_hpm, _hpj, _hp_today) - 1) < 0.15)
# weather forecast per day
from zoneinfo import ZoneInfo as _ZI2
_tzA = _ZI2("Europe/Amsterdam")
_hourly = [{"datetime": datetime(2026, 10, 14, h, tzinfo=_tzA).isoformat(), "temperature": 8.0 + (h % 4), "wind_speed": 18.0, "wind_bearing": 270} for h in range(24)]
_daily = [{"datetime": datetime(2026, 10, 14 + k, 12, tzinfo=_tzA).isoformat(), "temperature": 12.0, "templow": 4.0, "wind_speed": 36.0, "wind_bearing": 90} for k in range(5)]
_wd = heatpump.weather_days(_hourly, _daily, _tzA, 1 / 3.6)
check("heat pump: weather per day - hourly mean where the day is complete, else (max + min) / 2; km/h -> m/s",
      _wd["2026-10-14"]["t"] == 9.5 and _wd["2026-10-14"]["w"] == 5.0 and _wd["2026-10-14"]["wd"] == 270.0
      and _wd["2026-10-15"]["t"] == 8.0 and _wd["2026-10-15"]["w"] == 10.0)
check("heat pump: wind direction is averaged as a vector (350 and 10 -> 0)", heatpump.mean_direction([350, 10]) in (0.0, 360.0))
# forecast days and spreading over the hours
_fd = heatpump.forecast_days(_hpm, _hpj, {"2026-10-13": {"t": 5.0, "w": 4.0}, "2026-10-14": {"t": 5.0, "w": 4.0}}, [_hp_today, _hp_today + timedelta(days=1), _hp_today + timedelta(days=2)])
check("heat pump: a cold day is forecast by the model, a day without weather gets none",
      _fd[1]["kwh"] > 10 and _fd[2]["kwh"] is None)
_shape = heatpump.hourly_shape(_hpj, _hp_today)
check("heat pump: the hourly pattern comes from the recent days (7:00 more than 3:00), shares add up to 1",
      _shape[7] > _shape[3] * 2 and abs(sum(_shape) - 1) < 1e-9)
_h0 = int(datetime(2026, 10, 13, 20, tzinfo=_tzA).timestamp())
_sp = heatpump.spread({"2026-10-13": 24.0, "2026-10-14": 12.0}, [1 / 24] * 24, _h0, 30, _tzA)
check("heat pump: day totals spread over the forecast hours", _sp[0] == 1.0 and _sp[4] == 0.5 and len(_sp) == 30)
# rows from hourly statistics
_e_hourly = {int(datetime(2026, 10, 12, h, tzinfo=_tzA).timestamp()): 0.5 for h in range(24)}
_t_hourly = {int(datetime(2026, 10, 12, h, tzinfo=_tzA).timestamp()): 10.0 for h in range(24)}
_rows = heatpump.build_rows(_date(2026, 10, 12), _date(2026, 10, 12), _tzA, _e_hourly, _t_hourly)
check("heat pump: a journal row from hourly statistics (12 kWh, 10 C, the hours kept)",
      _rows[0]["e"] == 12.0 and _rows[0]["t"] == 10.0 and len(_rows[0]["hours"]) == 24)
check("heat pump: states - active in the cold, summer when warm, learning without enough heating days",
      heatpump.state_of(_hpm, _fd[:2], 100) == "active"
      and heatpump.state_of(_hpm, [{"kwh": 3.0, "teff": 19.0}], 100) == "summer"
      and heatpump.state_of(_hpm, _fd[:2], 5) == "learning" and heatpump.state_of(None, [], 0) == "learning")
# cooling branch
_cool = _hp_journal(days=300)
for r in _cool:
    if r["t"] > 18:
        r["e"] = round(r["e"] + 0.5 * (r["t"] - 18), 3)
_hpc = heatpump.fit(_cool, _hp_today, with_cooling=True)
# (as of 2026.10.17 the cooling temperature can be found from 16 degC)
check("heat pump: with cooling data a cooling branch is found above its own temperature (also below 20 degC)",
      _hpc["tc"] is not None and 17.0 <= _hpc["tc"] <= 19.0 and heatpump.summary(_hpc)["cooling_kwh_per_degree_day"] > 0.3)
# runtime
_rt_hp = heatpump_runtime.HeatPumpRuntime()
_rt_hp.merge(_hpj, _hp_today)
_now_hp = datetime(2026, 10, 13, 20, 10, tzinfo=_tzA)
_rt_hp.sample(_now_hp, _tzA, t_out=7.0, wind=5.0, wind_dir=250, setpoint=20.5, sun_today=3.0)
_weather = {(_hp_today + timedelta(days=k)).isoformat(): {"t": 6.0 + k, "w": 4.0, "wd": 240.0} for k in range(5)}
_tot_hp, _att_hp, _used_hp = _rt_hp.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6)
check("heat pump runtime: active, 5 days on the card, the forecast filled for 121 hours (past the weather: the average)",
      _used_hp and _att_hp["state"] == "active" and len(_att_hp["days"]) == 5 and all(v > 0 for v in _tot_hp)
      and _att_hp["model"]["balance_temp_c"] == _hps["balance_temp_c"] and _att_hp["classes"] and _att_hp["points"])
_tot_none, _att_none, _ = _rt_hp.compute("none", _now_hp, _tzA, _h0, 121, _weather, {}, 6)
check("heat pump runtime: no own metering -> only the weather difference is added (can be negative), nothing past the weather",
      any(v != 0 for v in _tot_none[:48]) and all(v == 0 for v in _tot_none[-20:]))
_rt_hp.sample(datetime(2026, 10, 14, 0, 5, tzinfo=_tzA), _tzA, t_out=5.0, wind=3.0)
_row13 = next(r for r in _rt_hp.journal if r["d"] == "2026-10-13")
check("heat pump runtime: at midnight the live day goes into the journal (wind direction, setpoint, sun forecast)",
      _row13.get("wd") == 250.0 and _row13.get("sp") == 20.5 and _rt_hp.live["d"] == "2026-10-14")
_rt2_hp = heatpump_runtime.HeatPumpRuntime()
_rt2_hp.merge(_hpj[-12:], _hp_today)
_t2, _a2, _u2 = _rt2_hp.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6)
check("heat pump runtime: too little history -> learning, not used, nothing added",
      not _u2 and _a2["state"] == "learning" and sum(_t2) == 0)
# 2026.10.16 (also): the house's cooling rate and its own heat
def _house_series(days=60, k=0.025, kw=0.002, ks=0.15, a=0.02, seed=7, glow=0.0):
    import random as _r
    rnd = _r.Random(seed)
    h0 = int(datetime(2026, 8, 14, 0, 0, tzinfo=_tzA).timestamp())
    indoor, outdoor, heat, wind, sun = {}, {}, {}, {}, {}
    tin, on, since = 21.0, False, 99
    for i in range(days * 24):
        h = h0 + i * 3600
        hod = datetime.fromtimestamp(h, _tzA).hour
        tout = 9 + 5 * _m.sin(i / 24 * 0.7) + 3 * _m.sin((hod - 9) / 24 * 2 * _m.pi)
        w = rnd.uniform(0, 8)
        s = max(0.0, 3.0 * _m.sin((hod - 6) / 14 * _m.pi)) if 6 <= hod <= 20 else 0.0
        if tin < 19.5:
            on = True
        elif tin > 21.0:
            on = False
        indoor[h], outdoor[h], wind[h], sun[h] = round(tin, 3), round(tout, 2), round(w, 2), round(s, 3)
        heat[h] = 1.5 if on else 0.0
        d = tin - tout
        since = 0 if on else since + 1
        # a floor still giving heat after the heat pump stopped
        floor = glow * _m.exp(-since / 3.0) if not on else 0.0
        tin += a - k * d - kw * w * d + ks * s + (0.6 if on else 0.0) + floor + rnd.gauss(0, 0.01)
    return indoor, outdoor, heat, wind, sun


_hin, _hout, _hheat, _hwind, _hsun = _house_series()
_th = heatpump.fit_thermal(_hin, _hout, _hheat, _hwind, _hsun)
check("house: the cooling rate is learned from the hours the heat pump didn't heat (k, wind, sun)",
      _th is not None and abs(_th["k"] - 0.025) < 0.004 and abs(_th["kw"] - 0.002) < 0.0008
      and abs(_th["ks"] - 0.15) < 0.04 and _th["n"] >= 48)
_pin, _pout, _pheat, _, _ = _house_series(ks=0.0)
_th_plain = heatpump.fit_thermal(_pin, _pout, _pheat)
# without the wind series its mean is folded in: 0.025 + 0.002 x 4 m/s
check("house: without wind statistics the cooling rate is still found (the mean wind folded in)",
      _th_plain is not None and abs(_th_plain["k"] - 0.033) < 0.006 and _th_plain["kw"] is None)
check("house: always heating -> nothing to learn",
      heatpump.fit_thermal(_hin, _hout, {h: 1.0 for h in _hheat}) is None)
_th_fixed = {"a": 0.0, "k": 0.025, "kw": None, "ks": None, "n": 200}
_pd = heatpump.stored_kwh_per_degree(_th_fixed, _hpm)
check("house: heat held per degC = (b / 24) / k", abs(_pd - round(_hpm["coef"][1] / 24 / 0.025, 2)) < 0.01)
_calm = [(8.0, 0.0, 0.0)] * 120
_eff = heatpump.house_effect(_th_fixed, _hpm, 24.0, 21.0, _calm)
# 24 -> 21 at 8 degC outdoor: t(n) = 8 + 16 x 0.975^n -> about 8 hours
check("house: 3 degC warmer than wanted -> coasts until it's back (simulated), the heat it holds",
      _eff["kind"] == "surplus" and 7 <= _eff["hours"] <= 9 and abs(_eff["kwh"] - 3 * _pd) < 0.05)
_eff_cold = heatpump.house_effect(_th_fixed, _hpm, 24.0, 21.0, [(0.0, 0.0, 0.0)] * 120)
check("house: colder outside -> back sooner", _eff_cold["hours"] < _eff["hours"])
_eff_def = heatpump.house_effect(_th_fixed, _hpm, 19.0, 21.0, _calm)
check("house: 2 degC colder -> that heat extra over the first hours",
      _eff_def["kind"] == "deficit" and _eff_def["hours"] == heatpump.DEFICIT_HOURS and abs(_eff_def["kwh"] - 2 * _pd) < 0.05)
check("house: within 0.3 degC of wanted -> no effect", heatpump.house_effect(_th_fixed, _hpm, 21.2, 21.0, _calm) is None)
_ah, _ach = heatpump.apply_house([1.0] * 24, {"kind": "surplus", "hours": 10, "kwh": 3.0}, 0.13)
check("house: coasting hours keep only the base, at most the heat the house holds",
      _ach == -3.0 and _ah[0] == 0.13 and _ah[2] == 0.13 and 0.13 < _ah[3] < 1.0 and _ah[4] == 1.0 and _ah[12] == 1.0)
_ah2, _ach2 = heatpump.apply_house([1.0] * 24, {"kind": "deficit", "hours": 6, "kwh": 3.0}, 0.13)
check("house: a deficit is spread over its hours", _ach2 == 3.0 and _ah2[0] == 1.5 and _ah2[6] == 1.0)
_hw = heatpump.hourly_weather(
    [{"datetime": datetime.fromtimestamp(_h0, _tzA).isoformat(), "temperature": 4.0, "wind_speed": 36.0}],
    {datetime.fromtimestamp(_h0 + 3600, _tzA).date().isoformat(): {"t": 7.0, "w": 2.0}}, _h0, 3, _tzA, 1 / 3.6, [0.0, 1.0])
check("house: hourly weather from the hourly forecast, else the day's mean; the solar forecast per hour",
      _hw[0] == (4.0, 10.0, 0.0) and _hw[1][0] == 7.0 and _hw[1][2] == 1.0 and _hw[2][2] is None)
_rt_hp.thermal = _th_fixed
_tot_house, _att_house, _ = _rt_hp.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=21.0,
                                           indoor=24.0, hourly_weather=_calm)
_tot_plain, _att_plain, _ = _rt_hp.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=21.0)
check("house runtime: a warmer house takes its heat off the forecast and the card's days, the attribute says until when",
      _att_house["house"]["kind"] == "surplus" and _att_house["house"]["kwh"] < 0
      and abs(sum(_tot_house) - sum(_tot_plain) - _att_house["house"]["kwh"]) < 0.05
      and abs(sum(d["kwh"] for d in _att_house["days"]) - sum(d["kwh"] for d in _att_plain["days"]) - _att_house["house"]["kwh"]) < 0.05
      and _att_house["house"]["until"] and _att_house["thermal"]["time_constant_h"] == 40.0
      and _att_house["thermal"]["kwh_per_degree"] == _pd)
_rt_hp.thermal = None
# a schedule (evening boost, night without) and a floor that keeps giving heat
check("house: without a floor giving heat long the usual 3 hours count as heating", _th["off_hours"] == 3)
_gin, _gout, _gheat, _gwind, _gsun = _house_series(glow=0.6)
_th_glow = heatpump.fit_thermal(_gin, _gout, _gheat, _gwind, _gsun)
check("house: a floor that measurably keeps giving heat -> 6 hours count as heating, the cooling rate stays right",
      _th_glow["off_hours"] == 6 and abs(_th_glow["k"] - 0.025) < 0.004)
_sp_j = [{"d": (_hp_today - timedelta(days=k)).isoformat(), "sp": 20.8} for k in range(1, 9)]
check("heat pump: the coming days are forecast with the last week's average wanted temperature, not this hour's",
      heatpump.typical_setpoint(_sp_j, _hp_today, 21.4, 21.5) == 20.8
      and heatpump.typical_setpoint([], _hp_today, 21.1, 21.5) == 21.1 and heatpump.typical_setpoint([], _hp_today, None, 21.5) == 21.5)
_sched = [20.5] * 24
for _hh in range(18, 23):
    _sched[_hh] = 21.6
_sched[18], _sched[19] = 20.8, 21.1  # the house follows the boost with a lag
for _hh in (23, 0, 1, 2, 3, 4, 5):
    _sched[_hh] = 21.2
_idays = {}
for _k in range(1, 21):
    _dd = (_hp_today - timedelta(days=_k)).isoformat()
    _idays[_dd] = [v + (0.05 if _k % 2 else -0.05) for v in _sched]
for _k in range(21, 40):  # summer weeks: warm house, no heating days
    _idays[(_hp_today - timedelta(days=_k)).isoformat()] = [24.0] * 24
_heat_days = {(_hp_today - timedelta(days=_k)).isoformat() for _k in range(1, 21)}
_prof = heatpump.indoor_profile(_idays, _heat_days)
check("house: the usual indoor temperature per hour from the newest heating days (the schedule in it)",
      _prof is not None and abs(_prof[20] - 21.6) < 0.06 and abs(_prof[2] - 21.2) < 0.06 and abs(_prof[12] - 20.5) < 0.06)
_summer_days = {(_hp_today - timedelta(days=_k)).isoformat() for _k in range(21, 40)}
check("house: warm summer days aren't 'usual' - without heating days no profile",
      heatpump.indoor_profile(_idays, set()) is None and heatpump.indoor_profile(_idays, _summer_days | {"x"}) is not None)
_usual20 = [_prof[(20 + i) % 24] for i in range(120)]
_usual19 = [_prof[(19 + i) % 24] for i in range(120)]
check("house: the evening boost itself is usual -> no 'colder than wanted' extra (against the wanted temperature it would be)",
      heatpump.house_effect(_th_fixed, _hpm, 21.1, 21.6, _calm, _usual19) is None
      and heatpump.house_effect(_th_fixed, _hpm, 21.1, 21.6, _calm)["kind"] == "deficit")
check("house: the night after the boost is usual too -> no 'warmer than wanted' (against the wanted temperature it would be)",
      heatpump.house_effect(_th_fixed, _hpm, 21.2, 20.5, _calm, [_prof[(1 + i) % 24] for i in range(120)]) is None
      and heatpump.house_effect(_th_fixed, _hpm, 21.2, 20.5, _calm)["kind"] == "surplus")
_eff_autumn = heatpump.house_effect(_th_fixed, _hpm, 23.4, 20.5, _calm, _usual20)
check("house: out of the summer, 23.4 degC against a usual 21.6 at this hour -> warmer than usual, back on its track later",
      _eff_autumn["kind"] == "surplus" and _eff_autumn["reference"] == "usual" and _eff_autumn["surplus_c"] == 1.8
      and _eff_autumn["hours"] > 0 and abs(_eff_autumn["kwh"] - 1.8 * _pd) < 0.05)
_rt4 = heatpump_runtime.HeatPumpRuntime()
_rt4.merge(_hpj, _hp_today)
_rt4.thermal = _th_fixed
_rt4.indoor_days = {d: v for d, v in _idays.items()}
_t4, _a4, _ = _rt4.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=21.6, indoor=23.4, hourly_weather=_calm)
check("house runtime: the usual temperature per hour is the reference once there are heating days with indoor data",
      _a4["house"]["reference"] == "usual" and _a4["house"]["usual_c"] == 21.6 and _a4["house"]["difference_c"] == 1.8
      and _a4["house"]["kind"] == "surplus" and len(_a4["house"]["usual_profile"]) == 24)
# 2026.10.17: days left out of the fit, cooling from 16 degC, thermal from cool hours only
_coast = [dict(r) for r in _hpj]
for r in _coast[-12:]:
    r.update({"t": 10.0, "e": 0.3, "tid": -0.4})
_m_coast = heatpump.fit(_coast, _hp_today)
_no_tid = [{k: v for k, v in r.items() if k != "tid"} for r in _coast]
_m_no = heatpump.fit(_no_tid, _hp_today)
check("heat pump: cool days on which the house cooled down without heating are left out (coasting), the signature stays",
      sum(1 for v in _m_coast["left_out"].values() if v == "coasting") == 12
      and abs(_m_coast["coef"][1] - _hpm["coef"][1]) < 0.03 and abs(_m_no["coef"][1] - _hpm["coef"][1]) > 0.1
      and heatpump.summary(_m_coast)["coasting_days"] == 12)
_steady = [dict(r) for r in _coast]
for r in _steady[-12:]:
    r["tid"] = -0.1
check("heat pump: a house that stayed at its temperature isn't coasting",
      not any(v == "coasting" for v in heatpump.fit(_steady, _hp_today)["left_out"].values()))
_busy = [dict(r) for r in _coast]
for r in _busy[-12:]:
    r["hours"] = [0.5] * 24
check("heat pump: a cooling house while the heat pump heated all day (a cold snap) isn't coasting",
      not any(v == "coasting" for v in heatpump.fit(_busy, _hp_today)["left_out"].values()))
_jump = [dict(r) for r in _hpj]
_jump[-30]["e"] = 40.0
_m_jump = heatpump.fit(_jump, _hp_today)
check("heat pump: a day far off the model (a meter jump) is left out and the model fitted again without it",
      _m_jump["left_out"].get(_jump[-30]["d"]) == "outlier" and abs(_m_jump["coef"][1] - _hpm["coef"][1]) < 0.02
      and heatpump.summary(_m_jump)["outlier_days"] == [_jump[-30]["d"]])
_pts_jump = heatpump.points(_jump, _hp_today, left_out=_m_jump["left_out"])
check("heat pump: the chart marks the left-out day, the memory table leaves it out",
      any(len(p) == 4 and p[3] == "outlier" and p[1] == 40.0 for p in _pts_jump)
      and sum(c["days"] for c in heatpump.classes(_m_jump, _jump, _hp_today)) == sum(c["days"] for c in heatpump.classes(_hpm, _hpj, _hp_today)) - 1)
_ind = {int(datetime(2026, 10, 12, h, tzinfo=_tzA).timestamp()): 22.0 - h * 0.02 for h in range(24)}
_ind[int(datetime(2026, 10, 13, 0, tzinfo=_tzA).timestamp())] = 21.5
_rows_i = heatpump.build_rows(_date(2026, 10, 12), _date(2026, 10, 12), _tzA, _e_hourly, _t_hourly, indoor=_ind)
check("heat pump: the rows get the indoor day mean and its change from midnight to midnight",
      abs(_rows_i[0]["ti"] - 21.77) < 0.01 and _rows_i[0]["tid"] == -0.5)
_warm_out = {h: v + 12.0 for h, v in _hout.items()}
check("house: summer hours (outdoor above 15 degC) don't teach the cooling rate",
      heatpump.fit_thermal({h: v + 12.0 for h, v in _hin.items()}, _warm_out, _hheat) is None)
_rt5 = heatpump_runtime.HeatPumpRuntime()
_rt5.merge(_hpj[-12:], _hp_today)
_rt5.thermal = _th_fixed
_, _a5, _ = _rt5.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=21.0, indoor=21.0, hourly_weather=_calm)
check("house runtime: while learning no 'heat held' (it leans on the kWh per degree colder)",
      _a5["state"] == "learning" and (_a5.get("thermal") is None or _a5["thermal"]["kwh_per_degree"] is None))
# 2026.10.17 (also): the thermostat's heat demand
check("heat pump: heat demand from a climate entity (hvac_action, else indoor below wanted)",
      heatpump.climate_demand("heat", {"hvac_action": "heating"}) is True
      and heatpump.climate_demand("heat", {"hvac_action": "idle"}) is False
      and heatpump.climate_demand("heat", {"current_temperature": 20.4, "temperature": 21}) is True
      and heatpump.climate_demand("heat", {"current_temperature": 21.1, "temperature": 16}) is False
      and heatpump.climate_demand("off", {}) is False and heatpump.climate_demand("unavailable", {}) is None
      and heatpump.climate_demand("heat", {}) is None)
_d0 = int(datetime(2026, 10, 11, 0, 0, tzinfo=_tzA).timestamp())
_chg = [(_d0 - 5 * 3600, False), (_d0 + 6 * 3600, True), (_d0 + 9 * 3600, False), (_d0 + 30 * 3600, True), (_d0 + 31 * 3600, False)]
_dh = heatpump.demand_hours(_chg, _d0 - 5 * 3600, _d0 + 48 * 3600, _tzA)
check("heat pump: heat demand hours per day from the thermostat's history (only whole days)",
      _dh == {"2026-10-11": 3.0, "2026-10-12": 1.0})
_nod = [dict(r) for r in _hpj]
for r in _nod[-12:]:
    r.update({"t": 10.0, "e": 0.3, "dem": 0.0})
_m_nod = heatpump.fit(_nod, _hp_today)
check("heat pump: cool days without heat demand (warm house, a holiday at 16 degC) are left out",
      heatpump.summary(_m_nod)["no_demand_days"] == 12 and abs(_m_nod["coef"][1] - _hpm["coef"][1]) < 0.03)
_dem_ok = [dict(r) for r in _nod]
for r in _dem_ok[-12:]:
    r["dem"] = 9.0
check("heat pump: a day with heat demand counts", heatpump.summary(heatpump.fit(_dem_ok, _hp_today))["no_demand_days"] == 0)
check("house: thermostat at 16 degC on holiday (outside its usual 20.5..21.6) -> the wanted temperature is the reference",
      heatpump.house_effect(_th_fixed, _hpm, 21.1, 16.0, _calm, _usual20)["reference"] == "wanted"
      and heatpump.house_effect(_th_fixed, _hpm, 21.1, 16.0, _calm, _usual20)["kind"] == "surplus"
      and heatpump.house_effect(_th_fixed, _hpm, 21.1, 21.0, _calm, _usual20)["reference"] == "usual")
_hol = [dict(r) for r in _hpj]
for r in _hol[-30:]:
    r["sp"] = 21.0
for r in _hol[-5:]:
    r["sp"] = 16.0
_hd_hol = heatpump.heating_dates(_hpm, _hol)
check("house: holiday days (thermostat clearly lower) don't make the usual indoor temperature",
      not any(r["d"] in _hd_hol for r in _hol[-5:]) and any(r["d"] in _hd_hol for r in _hol[-30:-5]))
_rt6 = heatpump_runtime.HeatPumpRuntime()
_rt6.merge(_hpj, _hp_today)
_rt6.sample(datetime(2026, 10, 13, 10, 0, tzinfo=_tzA), _tzA, t_out=8.0, demand=True)
_rt6.sample(datetime(2026, 10, 13, 16, 0, tzinfo=_tzA), _tzA, t_out=8.0, demand=False)
_rt6.sample(datetime(2026, 10, 13, 22, 0, tzinfo=_tzA), _tzA, t_out=8.0, demand=False)
_rt6.sample(datetime(2026, 10, 14, 0, 5, tzinfo=_tzA), _tzA, t_out=8.0)
check("heat pump runtime: the live heat demand goes into the day's journal row at midnight",
      next(r for r in _rt6.journal if r["d"] == "2026-10-13").get("dem") == 8.0)
_rt6.set_demand({"2026-10-13": 5.5})
check("heat pump runtime: the thermostat's history sets the demand hours",
      next(r for r in _rt6.journal if r["d"] == "2026-10-13")["dem"] == 5.5)
# 2026.10.17 (also): the thermostat's current temperature as the indoor temperature
_s0 = int(datetime(2026, 10, 12, 10, 0, tzinfo=_tzA).timestamp())
_hm = heatpump.step_hourly_means([(_s0 - 600, 21.0), (_s0 + 1800, 22.0), (_s0 + 3600 + 1200, None)], _s0 - 3600, _s0 + 3 * 3600)
check("house: hourly means from a thermostat's temperature changes (time-weighted, gaps left out)",
      _hm.get(_s0) == 21.5 and _s0 + 3600 not in _hm and _s0 - 3600 not in _hm)
_rt7 = heatpump_runtime.HeatPumpRuntime()
for _mi, _v in ((0, 21.0), (20, 21.2), (40, 21.4), (61, 21.6)):
    _rt7.sample(datetime(2026, 10, 13, 10, 0, tzinfo=_tzA) + timedelta(minutes=_mi), _tzA, indoor=_v)
_h10 = int(datetime(2026, 10, 13, 10, 0, tzinfo=_tzA).timestamp())
check("heat pump runtime: the indoor temperature is recorded per hour live",
      _rt7.indoor_series() == {_h10: 21.2})
_rt7.add_indoor_hours({_h10: 19.0, _h10 - 3600: 20.5, _h10 - 90 * 86400: 18.0}, _h10 + 7200)
check("heat pump runtime: the thermostat's history fills hours, what was recorded live stays, old hours go",
      _rt7.indoor_series() == {_h10: 21.2, _h10 - 3600: 20.5})
_rt7.set_demand({"2026-10-10": 2.5})
_rt7.merge([{"d": "2026-10-10", "e": 3.0, "t": 9.0}], _hp_today)
check("heat pump runtime: demand hours read before the day's row arrives are applied when it does",
      _rt7.journal[0].get("dem") == 2.5)
# 2026.10.17 (also): heat loss by indoor - outdoor, the wanted temperature from the thermostat's history
_rti = _rnd.Random(11)
_tij = []
for r in _hp_journal(days=300, noise=0.3):
    r = dict(r)
    ti = round(21.0 + _rti.uniform(-1.5, 1.5), 2)
    r["ti"] = ti
    _tij.append(r)
_teff_ti = heatpump.effective_temps(_tij)
for r in _tij:
    hdd = max(0.0, 15.5 + (r["ti"] - 21.0) - _teff_ti[r["d"]])
    r["e"] = round(max(3.1 + 0.92 * hdd + 0.03 * r["w"] * hdd - 0.35 * r["s"] * (1 if hdd > 0 else 0) + _rti.gauss(0, 0.3), 0.2), 3)
_m_ti = heatpump.fit(_tij, _hp_today)
_s_ti = heatpump.summary(_m_ti)
check("heat pump: with the indoor temperature the loss follows indoor - outdoor (kWh per degree, balance at the usual indoor temperature)",
      _m_ti["use"]["ti"] and abs(_s_ti["kwh_per_degree_day"] - 0.92) < 0.06 and abs(_s_ti["indoor_ref_c"] - 21.0) < 0.3
      and abs((_s_ti["balance_temp_c"] - (_s_ti["indoor_ref_c"] - 21.0)) - 15.5) <= 0.5)
_cold_row = {"w": 4.0, "s": 2.0, "ti": 21.0}
_warm_row = dict(_cold_row, ti=22.0)
_d_cost = heatpump.predict_row(_m_ti, _warm_row, 5.0) - heatpump.predict_row(_m_ti, _cold_row, 5.0)
check("heat pump: a degree warmer inside costs about the kWh per degree (+ wind) on a cold day",
      abs(_d_cost - (_s_ti["kwh_per_degree_day"] + (_s_ti["wind_kwh_per_ms_degree"] or 0) * 4.0)) < 0.05)
check("heat pump: without indoor temperatures on most days the old balance temperature stays", not _hpm["use"].get("ti"))
_ei = [dict(r) for r in _tij]
for r in _ei[-20:]:
    r["sp"] = 21.0
_exp = heatpump.expected_indoor(_m_ti, _ei, _hp_today, 21.0)
_exp_hol = heatpump.expected_indoor(_m_ti, _ei, _hp_today, 16.0)
check("heat pump: the coming days keep the usual indoor temperature, moved with the thermostat (a holiday at 16 degC)",
      _exp is not None and 19.5 < _exp < 22.5 and abs((_exp - _exp_hol) - 5.0) < 0.01
      and heatpump.expected_indoor(_hpm, _hpj, _hp_today, 21.0) is None)
_fd_hol = heatpump.forecast_days(_m_ti, _ei, {"2026-10-13": {"t": 5.0, "w": 4.0}}, [_hp_today], None, None, 16.0, 1.0, _exp_hol)
_fd_home = heatpump.forecast_days(_m_ti, _ei, {"2026-10-13": {"t": 5.0, "w": 4.0}}, [_hp_today], None, None, 21.0, 1.0, _exp)
check("heat pump: on holiday at 16 degC the forecast is about 5 degree-days lower",
      abs((_fd_home[0]["kwh"] - _fd_hol[0]["kwh"]) - 5 * (_s_ti["kwh_per_degree_day"] + (_s_ti["wind_kwh_per_ms_degree"] or 0) * 4.0)) < 0.3)
_hh = {int(datetime(2026, 10, 12, h, tzinfo=_tzA).timestamp()): 20.0 + (1.0 if h >= 18 else 0.0) for h in range(24)}
check("heat pump: day means from hourly values (whole days only)",
      heatpump.daily_means(_hh, _tzA) == {"2026-10-12": 20.25} and heatpump.daily_means({k: v for k, v in list(_hh.items())[:10]}, _tzA) == {})
_rt8 = heatpump_runtime.HeatPumpRuntime()
_rt8.set_setpoints({"2026-10-10": 20.6})
_rt8.merge([{"d": "2026-10-10", "e": 3.0, "t": 9.0}], _hp_today)
check("heat pump runtime: the thermostat's wanted temperature per day from its history goes into the rows",
      _rt8.journal[0].get("sp") == 20.6)
# 2026.10.17 (also): the house hour by hour (heatpump_house)
heatpump_house = _load("heatpump_house")
_hh = heatpump_house


def _hh_house(days=60, seed=3, sun_scale=1.0):
    rnd = _rnd.Random(seed)
    true = {"a": 0.03, "k": 0.02, "g": 0.12, "kw": 0.001, "ks": 0.08 * sun_scale, "tau": 3.0}
    prof = [20.5] * 24
    for hh_ in range(18, 23):
        prof[hh_] = 21.5
    start = int(datetime(2026, 10, 16, tzinfo=_tzA).timestamp())
    ind, out, heat, wnd, sn, cop = {}, {}, {}, {}, {}, {}
    t, hist, w = 20.5, [0.0] * 11, _hh.kernel(3.0)
    for i in range(days * 24):
        h = start + i * 3600
        lt = datetime.fromtimestamp(h, _tzA)
        day = i // 24
        tout = 4 + 4 * _m.sin(day * 0.5) + 3 * _m.sin((lt.hour - 9) / 24 * 2 * _m.pi) + rnd.gauss(0, 0.5)
        wd = abs(rnd.gauss(3, 2))
        s = max(0.0, 2.5 * _m.sin((lt.hour - 7) / 10 * _m.pi)) * (0.3 + 0.7 * rnd.random()) if 7 <= lt.hour <= 17 else 0.0
        tgt = prof[lt.hour]
        prev = sum(w[j] * hist[-j] for j in range(1, 12))
        loss = true["k"] * (tgt - tout) + true["kw"] * wd * (tgt - tout) - true["ks"] * s - true["a"]
        q = max(0.0, min((loss + 0.3 * (tgt - t) - true["g"] * prev) / (true["g"] * w[0]), 4.0))
        q = max(0.0, q * (1 + rnd.gauss(0, 0.1)))
        c = 3.5 + 0.08 * tout
        ind[h], out[h], wnd[h], sn[h] = round(t + rnd.gauss(0, 0.03), 2), round(tout, 2), round(wd, 2), round(s, 3)
        heat[h], cop[h] = round(q / c, 3), round(c + rnd.gauss(0, 0.1), 2)
        lag = w[0] * q + prev
        d = t - tout
        t = t + true["a"] - true["k"] * d - true["kw"] * wd * d + true["ks"] * s + true["g"] * lag + rnd.gauss(0, 0.02)
        hist = (hist + [q])[-11:]
    return ind, out, heat, wnd, sn, cop, prof


_hi, _ho, _hq, _hw, _hs, _hc, _hprof = _hh_house()
_hcop = _hh.fit_cop(_hc, _ho, _hq)
check("house hourly: the COP by the outdoor temperature from the COP sensor",
      _hcop is not None and abs(_hcop["c0"] - 3.5) < 0.1 and abs(_hcop["c1"] - 0.08) < 0.01
      and _hh.cop_at(_hcop, 100) == _hh.COP_MAX and _hh.cop_at(None, 5) == 1.0)
_hfit = _hh.fit_house(_hi, _ho, _hq, _hw, _hs, None, _hcop)
check("house hourly: cooling, heating per kWh of heat (with the floor's delay), wind and sun learned",
      _hfit is not None and abs(_hfit["k"] - 0.02) < 0.003 and abs(_hfit["g"] - 0.12) < 0.015
      and _hfit["tau"] == 3.0 and abs(_hfit["ks"] - 0.08) < 0.015 and _hfit["thermal"])
_hday = _date(2026, 12, 15)
_hlearn = _hh.learn(_hi, _ho, _hq, _hw, _hs, None, _hc, _tzA, _hday, _hprof, [1 / 24] * 24)
_hrev = _hlearn["review"]
check("house hourly: the self-check on the newest 14 heating days (fitted on the days before) passes against a flat pattern",
      _hrev["days"] == 14 and _hrev["passed"] and _hrev["hour_error_kwh"] < 0.9 * _hrev["pattern_error_kwh"]
      and _hrev["temp_error_c"] < 0.3)
_hfew = _hh.learn({h: v for h, v in _hi.items() if h > max(_hi) - 9 * 86400}, _ho, _hq, _hw, _hs, None, _hc, _tzA, _hday, _hprof, [1 / 24] * 24)
check("house hourly: with too few test days the self-check doesn't pass - shadow, not used",
      _hfew["review"]["days"] < _hh.MIN_TEST_DAYS and not _hfew["review"]["passed"]
      and _hh.stage_of(None, None, True) == "learning" and _hh.stage_of(_hfit, {"passed": False}, True) == "shadow"
      and _hh.stage_of(_hfit, {"passed": True}, False) == "used" and _hh.stage_of(_hfit, {"passed": True}, True) == "steering")
_h0h = int(datetime(2026, 12, 15, 8, tzinfo=_tzA).timestamp())
_hin = [(2 + 3 * _m.sin((datetime.fromtimestamp(_h0h + i * 3600, _tzA).hour - 9) / 24 * 2 * _m.pi), 3.0, 0.0) for i in range(48)]
_htg = _hh.targets(_hprof, None, _h0h, 48, _tzA)
_ht, _hqq = _hh.simulate(_hfit, 20.5, _hin, _htg, [0.5] * 11, _hcop)
check("house hourly: the emulated heat pump keeps the house near its usual temperature (and heats more for the evening)",
      len(_ht) == 49 and len(_hqq) == 48 and max(abs(a - b) for a, b in zip(_ht[24:48], _htg[24:48])) < 1.1 and max(_hqq[8:16]) >= max(_hqq[16:24])
      and all(0 <= q <= _hfit["qmax"] for q in _hqq))
_hcold, _ = _hh.simulate(_hfit, 21.0, [(0.0, 0.0, 0.0)] * 24, None, [0.0] * 11, _hcop, fixed_q=[0.0] * 24)
check("house hourly: without heating the house cools", _hcold[-1] < 21.0 - 2.0)
check("house hourly: the targets follow the usual profile, moved to the expected level (a holiday)",
      _hh.targets(_hprof, 16.0, _h0h, 24, _tzA)[10] == round(21.5 - (sum(_hprof) / 24 - 16.0), 2)
      and _hh.targets(None, None, _h0h, 3, _tzA, 20.0) == [20.0] * 3 and _hh.targets(None, None, _h0h, 3, _tzA) is None)
_htot = [0.5] * 60
_hre = _hh.reshape(_htot, _hqq, 0.1, _h0h, _tzA, [])
check("house hourly: the planning's hours placed by the simulation, each day's kWh kept (a day past it untouched)",
      abs(sum(_hre[:16]) - sum(_htot[:16])) < 0.01 and abs(sum(_hre[16:40]) - sum(_htot[16:40])) < 0.01
      and _hre[40:] == _htot[40:] and _hre[:16] != _htot[:16])
_hbuy = [0.40 if 17 <= datetime.fromtimestamp(_h0h + i * 3600, _tzA).hour <= 22 else
         (0.10 if 11 <= datetime.fromtimestamp(_h0h + i * 3600, _tzA).hour <= 15 else 0.25) for i in range(36)]
_hadv = _hh.preheat_advice(_hfit, _hcop, 20.5, _hin, _htg, [0.5] * 11, _hbuy, [b * 0.8 for b in _hbuy], [0.0] * 36)
check("house hourly: preheating advised in the cheap afternoon before the expensive evening",
      _hadv is not None and 11 <= datetime.fromtimestamp(_h0h + _hadv["start"] * 3600, _tzA).hour <= 15
      and _hadv["saving"] >= _hh.MIN_SAVING and _hadv["extra_kwh"] > 0)
check("house hourly: flat prices -> no advice; too few prices -> none",
      _hh.preheat_advice(_hfit, _hcop, 20.5, _hin, _htg, [0.5] * 11, [0.25] * 36, [0.2] * 36, [0.0] * 36) is None
      and _hh.preheat_advice(_hfit, _hcop, 20.5, _hin, _htg, [0.5] * 11, _hbuy[:6], _hbuy[:6], []) is None)
_hds = int(datetime(2026, 12, 15, tzinfo=_tzA).timestamp())
check("house hourly: hourly prices from quarter-hour prices",
      _hh.hourly_prices([0.1, 0.2, 0.3, 0.4] * 48, 96, _hds, _hds + 3600, 3) == [0.25, 0.25, 0.25]
      and len(_hh.hourly_prices([0.1] * 96, 96, _hds, _hds + 20 * 3600, 10)) == 4)
# runtime
_rt9 = heatpump_runtime.HeatPumpRuntime()
_rt9.merge(_hpj, _hp_today)
_rt9.house = {"model": _hfit, "cop": _hcop, "review": dict(_hrev), "day": "2026-10-13"}
_hw9 = [(_hin[i % 48][0], 3.0, 0.0) for i in range(121)]
_buy9 = [0.40 if 17 <= datetime.fromtimestamp(_h0 + i * 3600, _tzA).hour <= 22 else
         (0.10 if 11 <= datetime.fromtimestamp(_h0 + i * 3600, _tzA).hour <= 15 else 0.25) for i in range(36)]
_t9p, _a9p, _ = _rt9.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=20.5, indoor=20.6, hourly_weather=_hw9)
_rt9.house["review"]["passed"] = False
_t9s, _a9s, _ = _rt9.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=20.5, indoor=20.6, hourly_weather=_hw9)
check("house runtime: passed -> 'used', the planning's hours placed by the simulation (same total); not passed -> 'shadow', the pattern",
      _a9p["house_model"]["stage"] == "used" and _a9s["house_model"]["stage"] == "shadow"
      and abs(sum(_t9p) - sum(_t9s)) < 0.05 and _t9p != _t9s
      and len(_a9s["house_model"]["forecast"]["temps"]) == 49)
_rt9.house["review"]["passed"] = True
_sched9 = _hh.day_night(21.0, 19.0, 7, 22, _h0, 48, _tzA)
_t9a, _a9a, _ = _rt9.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=20.5, indoor=20.6,
                             hourly_weather=_hw9, prices={"buy": _buy9, "sell": _buy9, "surplus": []}, steering=True,
                             schedule=_sched9, buffer_delta=1.0)
_hm9 = _a9a["house_model"]
check("house runtime: steering - the day/night temperatures with the buffer plan on top (warmer in the cheap afternoon)",
      _hm9["stage"] == "steering" and (_hm9["plan"]["boost"] or _hm9["plan"]["dip"])
      and _hm9["plan"]["saving"] >= _hh.MIN_SAVING
      and _hm9["setpoint_now"] == _sched9[0] + _hm9["plan"]["offset_now"]
      and max(_hm9["forecast"]["target"]) <= 22.0 and min(_hm9["forecast"]["target"]) >= 18.0)
_rt9.house["review"]["passed"] = False
_, _a9n, _ = _rt9.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=20.5, indoor=20.6,
                          hourly_weather=_hw9, prices={"buy": _buy9, "sell": _buy9, "surplus": []}, steering=True,
                          schedule=_sched9, buffer_delta=1.0)
check("house runtime: steering before the self-check passed - only the plain day/night temperatures, no buffer",
      _a9n["house_model"]["stage"] == "shadow" and "plan" not in _a9n["house_model"]
      and _a9n["house_model"]["setpoint_now"] == _sched9[0])
_rt9.house["review"]["passed"] = True
_, _a9off, _ = _rt9.compute("separate", _now_hp, _tzA, _h0, 121, _weather, {}, 6, setpoint=20.5, indoor=20.6,
                            hourly_weather=_hw9, hourly_model=False)
check("house runtime: step 1 off -> no hour-by-hour model at all", "house_model" not in _a9off)
check("house hourly: day/night temperatures per hour (also with the night past midnight)",
      _hh.day_night(21, 18, 7, 22, _hds, 24, _tzA)[6:8] == [18, 21] and _hh.day_night(21, 18, 7, 22, _hds, 24, _tzA)[22] == 18
      and _hh.day_night(21, 18, 22, 6, _hds, 24, _tzA)[23] == 21 and _hh.day_night(21, 18, 22, 6, _hds, 24, _tzA)[12] == 18)
_hbase = _hh.day_night(21.0, 19.0, 7, 22, _h0h, 48, _tzA)
_hplan = _hh.plan_buffer(_hfit, _hcop, 20.5, _hin, _hbase, [0.5] * 11, _hbuy, _hbuy, [0.0] * 36, 1.0)
check("house hourly: the buffer plan - warmer before the expensive evening, cooler in it, within the range",
      _hplan["boost"] is not None and _hplan["dip"] is not None
      and 17 <= datetime.fromtimestamp(_h0h + _hplan["dip"]["start"] * 3600, _tzA).hour <= 22
      and set(_hplan["offsets"]) <= {-1.0, 0.0, 1.0} and _hplan["saving"] >= 2 * _hh.MIN_SAVING)
check("house hourly: no range or flat prices -> no buffering",
      _hh.plan_buffer(_hfit, _hcop, 20.5, _hin, _hbase, [0.5] * 11, _hbuy, _hbuy, [], 0.0) is None
      and _hh.plan_buffer(_hfit, _hcop, 20.5, _hin, _hbase, [0.5] * 11, [0.25] * 36, [0.2] * 36, [], 1.0)["saving"] == 0.0)
_rt10 = heatpump_runtime.HeatPumpRuntime()
for _mi, _kwh in ((0, 100.0), (30, 100.4), (61, 100.9), (125, 101.5), (250, 102.0)):
    _rt10.sample(datetime(2026, 10, 13, 10, 0, tzinfo=_tzA) + timedelta(minutes=_mi), _tzA, heat_kwh=_kwh)
check("heat pump runtime: the heating meter's rise per hour recorded live (an hour skipped is left out)",
      _rt10.heat_hist == {str(_h10): 0.9, str(_h10 + 3600): 0.6})
# 2026.10.18: the night limit (22:00-07:00)
check("night limit: 22:00-07:00 is night, by the quarter from today's midnight (tomorrow too)",
      forecasting.unit_is_night(88) and forecasting.unit_is_night(27) and not forecasting.unit_is_night(28)
      and not forecasting.unit_is_night(87) and forecasting.unit_is_night(96 + 10) and not forecasting.unit_is_night(96 + 40)
      and forecasting.night_share([86, 87, 88, 89]) == 0.5)
_nl_now = datetime(2026, 10, 18, 12, 0)
_nl_net = [0.0] * 48
_nl_day = forecasting.grid_charge_rates(_nl_net, _nl_now, 6.0, 10.0, 192)
_nl = forecasting.grid_charge_rates(_nl_net, _nl_now, 6.0, 10.0, 192, night_kw=2.0)
check("night limit: charge rates use the night speed at night only",
      _nl[56] == _nl_day[56] == 1.5 and _nl[90] == 0.5 and _nl[96 + 20] == 0.5 and _nl[96 + 30] == 1.5)
check("night limit: a night speed above the battery's max is capped; 0 means no charging at night",
      forecasting.grid_charge_rates(_nl_net, _nl_now, 6.0, 4.0, 192, night_kw=9.0)[90] == 1.0
      and forecasting.grid_charge_rates(_nl_net, _nl_now, 6.0, 10.0, 192, night_kw=0.0)[90] == 0.0)
_nl_calls = []


def _nl_compute(start, end):
    def compute(kw):
        _nl_calls.append(kw)
        return {"active": True, "discharge_start_unit": start, "discharge_end_unit": end, "kw": kw}
    return compute


_nl_p = forecasting.night_discharge_plan(_nl_compute(90, 98), 8.0, 3.0)
check("night limit: a sale at night is worked out again at the night speed",
      _nl_p["kw"] == 3.0 and _nl_p.get("night_limited") and _nl_calls == [8.0, 3.0])
_nl_calls.clear()
_nl_p2 = forecasting.night_discharge_plan(_nl_compute(70, 78), 8.0, 3.0)
check("night limit: a sale in the evening keeps the day speed; no limit -> nothing changes",
      _nl_p2["kw"] == 8.0 and _nl_calls == [8.0]
      and forecasting.night_discharge_plan(_nl_compute(90, 98), 8.0, None)["kw"] == 8.0)
_nl_calls.clear()
_nl_mix = forecasting.night_discharge_plan(_nl_compute(24, 32), 8.0, 3.0)
check("night limit: a sale across 07:00 is worked out at the average of its night and day quarters (what is really sent)",
      _nl_mix["kw"] == 5.5 and _nl_mix["night_share"] == 0.5 and _nl_mix["speed_kw"] == 5.5 and _nl_calls == [8.0, 5.5])


def _nl_moving(kw):
    # a slower speed needs a longer window that starts earlier (into the night)
    n = int(round(24 / kw))
    return {"active": True, "discharge_start_unit": 30 - n, "discharge_end_unit": 30, "kw": kw}


_nl_mv = forecasting.night_discharge_plan(_nl_moving, 8.0, 2.0)
_nl_units = list(range(_nl_mv["discharge_start_unit"], _nl_mv["discharge_end_unit"]))
check("night limit: when the window moves with the speed it's repeated until it settles (energy = what's sent)",
      abs(_nl_mv["kw"] - (forecasting.night_share(_nl_units) * 2.0 + (1 - forecasting.night_share(_nl_units)) * 8.0)) < 1.0)
_nl_blocks = forecasting.night_discharge_plan(
    lambda kw: {"active": True, "blocks": [{"start_unit": 100, "end_unit": 104}], "kw": kw}, 8.0, 2.0)
check("night limit: a sale in blocks counts its blocks' quarters", _nl_blocks["kw"] == 2.0)
_rt3_hp = heatpump_runtime.HeatPumpRuntime()
_rt3_hp.restore(_rt_hp.as_store())
check("heat pump runtime: the store round-trips", _rt3_hp.as_store() == _rt_hp.as_store())

if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED:")
    for f in FAILURES:
        print(f" - {f}")
    sys.exit(1)
else:
    print("All checks passed.")
