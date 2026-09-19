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

next_days = display.next_full_charge_in_days(interval_days=14, time_since_days=20)
check("next_full_charge_in_days floors at 0 when overdue", next_days == 0)

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
