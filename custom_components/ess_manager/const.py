"""Constants for the ESS Manager integration."""
from __future__ import annotations

DOMAIN = "ess_manager"
# number entities must be created before the coordinator's first refresh so
# that coordinator.get_number() has something to read - keep number first.
# switch.py (the "Automatic control" switch) must also be set up before the
# first refresh, so direct control knows whether it's allowed to send.
PLATFORMS = ["number", "switch", "select", "sensor"]

# One cycle a minute (as of 2026.10.20; was 30 s). On top of that a cycle
# runs right at every quarter boundary (:00/:15/:30/:45, see
# QUARTER_REFRESH_SECOND), so a planned block, a price quarter or the night
# limit at 07:00/22:00 starts and stops on time; since each cycle restarts
# the one-minute timer, the loop runs on that same second every minute.
UPDATE_INTERVAL_SECONDS = 60
QUARTER_REFRESH_SECOND = 2
# Diagnostics download (as of 2026.10.22): the decision history keeps the
# changes of the last 24 hours, at most this many entries.
DECISION_HISTORY_HOURS = 24
DECISION_HISTORY_MAX = 1500

# ---------------------------------------------------------------------------
# Config entry keys (set once during the config flow / options flow)
# ---------------------------------------------------------------------------
CONF_NAME = "name"
CONF_BATTERY_SOC_ENTITY = "battery_soc_entity"
CONF_PRICE_ENTITY = "price_entity"
CONF_SOLAR_FORECAST_ENTITIES = "solar_forecast_entities"
CONF_GRID_SETPOINT_ENTITY = "grid_setpoint_entity"
# Polarity of that setpoint (as of v0.3.4): "charge_positive" (positive =
# charging, the default and the only option before) or "discharge_positive".
CONF_GRID_SETPOINT_SIGN = "grid_setpoint_sign"
DEFAULT_GRID_SETPOINT_SIGN = "charge_positive"

# Cell voltage differential (only used by the full-charge balancing plan, to
# decide when the pack is balanced enough to stop holding at full). Two ways
# to supply it, both optional and independent of each other:
#  - CONF_VOLTAGE_DIFF_ENTITY: a BMS that already exposes the differential
#    directly as its own sensor (e.g. a JK BMS's "cell voltage differential"
#    entity) - assumed to report millivolts, matching compute_full_charge_plan's
#    balance_threshold default of 10.0.
#  - CONF_LOW_CELL_VOLTAGE_ENTITY + CONF_HIGH_CELL_VOLTAGE_ENTITY: for a BMS
#    that instead exposes the lowest/highest individual cell voltages as
#    their own sensors (the more common shape) - the differential is derived
#    as (highest - lowest), converted from volts to millivolts to match the
#    same balance_threshold convention. When both of these are configured,
#    they take priority over CONF_VOLTAGE_DIFF_ENTITY.
CONF_VOLTAGE_DIFF_ENTITY = "voltage_diff_entity"
CONF_LOW_CELL_VOLTAGE_ENTITY = "low_cell_voltage_entity"
CONF_HIGH_CELL_VOLTAGE_ENTITY = "high_cell_voltage_entity"

# A third, independent confirmation leg for the full-charge balancing plan,
# on top of SOC (>=99.5%) and the cell voltage differential above: the
# battery pack's own measured voltage must also have reached its configured
# full-charge target (see CONF_FULL_CHARGE_TARGET_VOLTAGE below), minus a
# small margin - see compute_full_charge_plan's voltage_at_target check.
# Required alongside CONF_ENABLE_FULL_CHARGE_PLAN (validated in
# config_flow.py), since it's now a core leg of "genuinely balanced", not an
# optional extra like the differential sources above.
CONF_BATTERY_VOLTAGE_ENTITY = "battery_voltage_entity"

# How "days since last full charge" is tracked, when the full-charge plan is
# enabled: either this integration tracks it itself (internal - the original,
# and still default, behavior: it remembers the last time
# compute_full_charge_plan reported balance_confirmed and measures forward
# from there; a new installation starts that clock at setup, as if the
# battery had just been balanced - as of v0.2.13), or an external sensor already tracks it (e.g. a BMS's
# own "days since full charge" entity, which resets to 0 the moment it
# observes a genuine full charge) and is read directly instead.
# CONF_DAYS_SINCE_FULL_CHARGE_ENTITY is required alongside the external
# option (validated in config_flow.py), the same way CONF_BATTERY_VOLTAGE_ENTITY
# is required alongside CONF_ENABLE_FULL_CHARGE_PLAN itself.
CONF_FULL_CHARGE_TRACKING_SOURCE = "full_charge_tracking_source"
FULL_CHARGE_TRACKING_INTERNAL = "internal"
FULL_CHARGE_TRACKING_EXTERNAL_SENSOR = "external_sensor"
DEFAULT_FULL_CHARGE_TRACKING_SOURCE = FULL_CHARGE_TRACKING_INTERNAL

CONF_DAYS_SINCE_FULL_CHARGE_ENTITY = "days_since_full_charge_entity"

# -- direct control (as of v0.2.14) --------------------------------------
# Optional: instead of (or before switching away from) an external
# automation that reacts to the Status sensor, the integration sends the
# setpoint itself, to a number/input_number entity. (v0.2.14 also offered
# running a script; removed in v0.2.15 - the v0.3.0 migration turns a stored
# "script" mode into off.) "Status sensor only" (off) is the default,
# so nothing changes for an installation until it's switched on in
# Configure. See control.py (the pure mapping) and controller.py (sending).
CONF_CONTROL_MODE = "control_mode"
CONTROL_MODE_OFF = "off"
CONTROL_MODE_NUMBER = "number"
DEFAULT_CONTROL_MODE = CONTROL_MODE_OFF
CONF_CONTROL_TARGET_ENTITY = "control_target_entity"
CONF_CONTROL_UNIT = "control_unit"
DEFAULT_CONTROL_UNIT = "W"
CONF_CONTROL_SIGN = "control_sign"
DEFAULT_CONTROL_SIGN = "charge_positive"
CONF_CONTROL_IDLE_VALUE = "control_idle_value"
DEFAULT_CONTROL_IDLE_VALUE = 0.0

# -- household usage forecast ---------------------------------------------
# Two sources (as of v0.3.0): the grid/solar/battery statistics Home
# Assistant's Energy dashboard is configured with (energy_source.py, the
# energy-balance identity in usage_forecast.compute_usage_forecast), or one
# or more home-energy-consumption sensors read directly. The external
# h0..h120 sensor ("external_sensor") and the hand-picked statistics
# ("calculated") were deprecated in v0.2.10 and removed in v0.3.0 - see
# REMOVED_USAGE_SOURCES and the config-entry migration in __init__.py.
CONF_USAGE_SOURCE = "usage_source"
USAGE_SOURCE_CONSUMPTION_SENSOR = "consumption_sensor"
USAGE_SOURCE_ENERGY_DASHBOARD = "energy_dashboard"
DEFAULT_USAGE_SOURCE = USAGE_SOURCE_ENERGY_DASHBOARD
SUPPORTED_USAGE_SOURCES = (USAGE_SOURCE_ENERGY_DASHBOARD, USAGE_SOURCE_CONSUMPTION_SENSOR)
USAGE_SOURCE_LABELS = {
    USAGE_SOURCE_ENERGY_DASHBOARD: "Calculate it using the entities from my Energy dashboard",
    USAGE_SOURCE_CONSUMPTION_SENSOR: "Use a home energy consumption sensor I already have",
}
# Only for the v1 -> v2 config-entry migration (__init__.async_migrate_entry):
# the removed sources, and the config keys only they used. An entry with no
# usage_source stored at all predates the choice and meant the external
# sensor.
REMOVED_USAGE_SOURCES = ("external_sensor", "calculated")
REMOVED_USAGE_SOURCE_LABELS = {
    "external_sensor": "an existing sensor with h0..h120 attributes",
    "calculated": "hand-picked energy statistics",
}
REMOVED_CONFIG_KEYS = (
    "usage_forecast_entity",
    "grid_import_entities",
    "grid_export_entities",
    "solar_production_entities",
    "battery_charge_energy_entity",
    "battery_discharge_energy_entity",
)

# Direct-consumption-meter usage-forecast input (USAGE_SOURCE_CONSUMPTION_SENSOR).
# A list - some homes split
# whole-house consumption across more than one energy monitor/circuit. This
# sidesteps the energy-balance identity entirely (nothing to derive - a
# direct consumption meter already *is* the household's usage), which also
# avoids a real failure mode the balance identity is exposed to: if the
# grid/solar/battery entities that feed it don't all update at the same
# resolution (e.g. a grid meter that only ticks in coarse 0.1 kWh steps
# next to a battery shunt updating every couple of minutes), Home
# Assistant's hourly statistics can attribute a real, continuous energy
# flow entirely to whichever single hour the coarse sensor happened to
# tick over in - producing nonsensical (even negative) per-hour swings
# even though the day's total works out fine. A direct meter has only one
# term, so there's nothing for it to disagree with.
CONF_USAGE_CONSUMPTION_ENTITIES = "usage_consumption_entities"

CONF_USAGE_LOOKBACK_WEEKS = "usage_lookback_weeks"
DEFAULT_USAGE_LOOKBACK_WEEKS = 6

CONF_ENABLE_FULL_CHARGE_PLAN = "enable_full_charge_plan"
CONF_ENABLE_SPIKE_PLAN = "enable_spike_plan"
CONF_ENABLE_NEGATIVE_PRICE_PLAN = "enable_negative_price_plan"

# Electric car charging from the home battery (as of 2026.10.11) - see ev.py.
# The charger's energy statistic is always taken out of the household usage
# history; the car enters the 120-hour forecast only through its sessions
# (predicted from history, edited or added on the EV card).
CONF_EV_ENABLED = "ev_enabled"
CONF_EV_ENERGY_ENTITY = "ev_energy_entity"
CONF_EV_POWER_ENTITY = "ev_power_entity"
CONF_EV_MIN_CURRENT = "ev_min_current"
CONF_EV_MAX_CURRENT = "ev_max_current"
CONF_EV_PHASES = "ev_phases"
CONF_EV_PREDICT = "ev_predict"
CONF_EV_CARS = "ev_cars"
# The charger (as of 2026.10.27): plain energy/power sensors (forecast only),
# or a Victron EV charging station (via the Victron GX integration) that
# ESS Manager drives, asking on the phone what to do when a car is plugged in.
CONF_EV_CHARGER = "ev_charger"
EV_CHARGER_SENSORS = "sensors"
EV_CHARGER_VICTRON = "victron"
DEFAULT_EV_CHARGER = EV_CHARGER_SENSORS
CONF_EV_VICTRON_DEVICE = "ev_victron_device"
CONF_EV_NOTIFY = "ev_notify_services"
VICTRON_GX_DOMAIN = "victron_gx"
DEFAULT_EV_ENABLED = False
DEFAULT_EV_MIN_CURRENT = 6
DEFAULT_EV_MAX_CURRENT = 16
EV_MAX_CURRENT_LIMIT = 75
DEFAULT_EV_PHASES = 3
DEFAULT_EV_PREDICT = True
DEFAULT_EV_TARGET_SOC = 80
# how many local days of sessions the card shows (today + 4)
EV_DAYS = 5
# Heat pump model (as of 2026.10.16) - see heatpump.py. The heat pump's
# energy is taken out of the household usage history and forecast from the
# weather with a model the integration keeps itself.
CONF_HP_ENABLED = "hp_enabled"
CONF_HP_METER = "hp_meter"
CONF_HP_HEAT_ENTITIES = "hp_heat_entities"
CONF_HP_COOL_ENTITIES = "hp_cool_entities"
CONF_HP_TOTAL_ENTITY = "hp_total_entity"
CONF_HP_OUTDOOR_ENTITY = "hp_outdoor_entity"
CONF_HP_WEATHER_ENTITY = "hp_weather_entity"
CONF_HP_WIND_ENTITY = "hp_wind_entity"
CONF_HP_WIND_DIR_ENTITY = "hp_wind_dir_entity"
CONF_HP_INDOOR_ENTITY = "hp_indoor_entity"
CONF_HP_SETPOINT_ENTITY = "hp_setpoint_entity"
# as of 2026.10.17: the heat pump's COP sensor (optional), and whether ESS
# Manager may preheat the house by raising the thermostat (off unless switched on)
CONF_HP_COP_ENTITY = "hp_cop_entity"
# the two steps (as of 2026.10.17): 1. the house hour by hour (forecast; the
# planning uses it once it passed its self-check), 2. steering the thermostat
# (day/night temperature, the house as a buffer) - switched on and off on the
# card once both are on here
CONF_HP_HOURLY_ENABLED = "hp_hourly_enabled"
DEFAULT_HP_HOURLY_ENABLED = False
CONF_HP_BUFFER_ENABLED = "hp_buffer_enabled"
# Floor control (as of 2026.10.23) - floor_control.py: ESS Manager sets the
# heat pump's return setpoint and switches its heat demand, the thermostat
# (a generic_thermostat on a helper switch) stays where the wanted
# temperature is set.
CONF_FLOOR_ENABLED = "floor_enabled"
CONF_FLOOR_SETPOINT_ENTITY = "floor_return_setpoint_entity"
CONF_FLOOR_DEMAND_ENTITY = "floor_demand_entity"
CONF_FLOOR_HELPER_ENTITY = "floor_thermostat_helper_entity"
CONF_FLOOR_SUPPLY_ENTITY = "floor_supply_entity"
CONF_FLOOR_RETURN_ENTITY = "floor_return_entity"
CONF_FLOOR_PUMP_ENTITY = "floor_pump_entity"
CONF_FLOOR_POWER_ENTITY = "floor_thermal_power_entity"
CONF_FLOOR_SLAB_ENTITY = "floor_slab_entity"
# cooling (as of 2026.10.23): the changeover switch (on = cooling) and/or a
# cooling thermostat (calling for cooling, as of 2026.10.24) - floor control steps aside
CONF_FLOOR_COOL_SWITCH_ENTITY = "floor_cool_switch_entity"
CONF_FLOOR_COOL_CLIMATE_ENTITY = "floor_cool_climate_entity"
DEFAULT_FLOOR_ENABLED = False
FLOOR_REQUIRED = (
    "floor_return_setpoint_entity", "floor_demand_entity", "floor_thermostat_helper_entity",
    "floor_supply_entity", "floor_return_entity", "floor_pump_entity", "floor_thermal_power_entity",
)
DEFAULT_HP_BUFFER_ENABLED = False
HP_STEERING_PLAN = "hp_steering"  # pseudo plan key: heat pump + both steps on
DEFAULT_HP_ENABLED = False
HP_METER_SEPARATE = "separate"
HP_METER_TOTAL = "total"
HP_METER_NONE = "none"
DEFAULT_HP_METER = HP_METER_SEPARATE

SERVICE_EV_SESSION_SAVE = "ev_session_save"
SERVICE_EV_SESSION_REMOVE = "ev_session_remove"
# the plugged-in car's plan from the EV card (Victron charger, as of 2026.10.27)
SERVICE_EV_CHARGE_PLAN = "ev_charge_plan"

# Seed values only - the live, user-adjustable copies of these live as
# `number` entities once the config entry is set up (see number.py). These
# CONF_* keys are only consulted the first time those number entities are
# created, so changing them later via the options flow has no effect on an
# already-configured installation - use the number entities (or the
# Home Assistant UI's entity settings) to change values afterward.
CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
CONF_CHARGE_SPEED_KW = "charge_speed_kw"
CONF_DISCHARGE_SPEED_KW = "discharge_speed_kw"

# The battery's own physical charge/discharge power limit - distinct from
# CONF_CHARGE_SPEED_KW/CONF_DISCHARGE_SPEED_KW above, which are how fast the
# system deliberately charges/discharges *from the grid* for the various
# planning engines (low charge, spike, full charge, ...). These two instead
# cap the passive, solar/usage-driven battery energy forecast
# (forecasting.build_battery_forecast): whatever solar or usage would
# otherwise imply a faster charge/discharge rate than the battery can
# physically handle is assumed to flow to/from the grid instead (curtailed
# export or grid import), not the battery.
#
# Unlike the seed values above, these are NOT backed by a `number` entity -
# they're a fixed hardware property, not something to tweak from a dashboard.
# They're set during initial setup and stay editable afterward via the
# integration's Configure (options) screen (see EssManagerOptionsFlow in
# config_flow.py) and coordinator.py reads them straight from the config
# entry's merged data/options each cycle.
CONF_MAX_BATTERY_CHARGE_SPEED_KW = "max_battery_charge_speed_kw"
CONF_MAX_BATTERY_DISCHARGE_SPEED_KW = "max_battery_discharge_speed_kw"
# Inverter/battery efficiency (as of v0.4.3), % - fixed hardware properties
# like the max speeds above: what reaches the battery per kWh charged, and
# what's delivered per kWh taken out. See forecasting.build_battery_forecast.
CONF_CHARGE_EFFICIENCY_PERCENT = "charge_efficiency_percent"
CONF_DISCHARGE_EFFICIENCY_PERCENT = "discharge_efficiency_percent"

CONF_MIN_SOC_PERCENT = "min_soc_percent"
CONF_MAX_SOC_PERCENT = "max_soc_percent"

# Seed value for the full-charge target voltage `number` entity (see
# NUMBER_DEFINITIONS below) - the pack's own fully-charged voltage setpoint,
# checked (minus a small margin) as the third confirmation leg alongside SOC
# and the cell voltage differential. Unlike CONF_MAX_BATTERY_CHARGE_SPEED_KW
# above, this one IS meant to be tweaked live from a dashboard (a
# calibration figure you dial in/adjust over time), so it follows the
# ordinary seed-value pattern, not the setup+options-only one.
CONF_FULL_CHARGE_TARGET_VOLTAGE = "full_charge_target_voltage"

# ---------------------------------------------------------------------------
# Defaults for the initial config flow
# ---------------------------------------------------------------------------
DEFAULT_NAME = "ESS Manager"
DEFAULT_BATTERY_CAPACITY_KWH = 30.0
DEFAULT_CHARGE_SPEED_KW = 7.0
DEFAULT_DISCHARGE_SPEED_KW = 10.0
# Battery hardware max power is typically at or above its own grid-charge
# speed - 10 kW is a reasonably common ballpark for a home battery's own
# charge/discharge limit, easy to tune per-install either way.
DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW = 10.0
DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW = 10.0
# Night limit (as of 2026.10.18): between 22:00 and 07:00 these speeds
# replace every other charge/discharge speed - in the plans and in the
# setpoint sent
CONF_NIGHT_LIMIT_ENABLED = "night_limit_enabled"
CONF_NIGHT_CHARGE_SPEED_KW = "night_charge_speed_kw"
CONF_NIGHT_DISCHARGE_SPEED_KW = "night_discharge_speed_kw"
DEFAULT_NIGHT_LIMIT_ENABLED = False
DEFAULT_NIGHT_CHARGE_SPEED_KW = 3.0
DEFAULT_NIGHT_DISCHARGE_SPEED_KW = 3.0
DEFAULT_CHARGE_EFFICIENCY_PERCENT = 100.0  # 100 = no losses (behavior before v0.4.3)
DEFAULT_DISCHARGE_EFFICIENCY_PERCENT = 100.0
DEFAULT_MIN_SOC_PERCENT = 15.0
# >100 is intentional: this is the "allow deliberate overshoot from solar up
# to this % of nominal capacity before actively discharging surplus"
# ceiling, not a hard cap - it mirrors the original hand-written sensor's
# hardcoded 33 kWh threshold on a 30 kWh battery (110%).
DEFAULT_MAX_SOC_PERCENT = 110.0
# 48V-class LiFePO4 pack (16S), fully charged - a reasonable starting point
# only; battery voltage varies widely by chemistry/pack size, so this should
# be tuned to your own system's actual full-charge voltage after setup.
DEFAULT_FULL_CHARGE_TARGET_VOLTAGE = 55.2
DEFAULT_ENABLE_FULL_CHARGE_PLAN = False
DEFAULT_ENABLE_SPIKE_PLAN = True
DEFAULT_ENABLE_NEGATIVE_PRICE_PLAN = True

# ---------------------------------------------------------------------------
# `number` entity keys - these are the live, user-tunable knobs. Each maps to
# one NumberEntity created by number.py. The coordinator reads the *current*
# value of these entities every update cycle (not the CONF_* seed values
# above) via coordinator.get_number(key).
# ---------------------------------------------------------------------------
# The solar-deficit minimum SOC keeps the original key (so an existing
# "Minimum SOC" entity simply becomes it, value and history included); the
# solar-surplus one is new in v0.4.2 - see forecasting.compute_solar_mode.
NUM_MIN_SOC_PERCENT = "min_soc_percent"
NUM_MIN_SOC_SURPLUS_PERCENT = "min_soc_surplus_percent"
NUM_MAX_SOC_PERCENT = "max_soc_percent"
NUM_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
NUM_CHARGE_SPEED_KW = "charge_speed_kw"
NUM_DISCHARGE_SPEED_KW = "discharge_speed_kw"
NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW = "negative_price_charge_speed_kw"
NUM_SPIKE_DISCHARGE_SPEED_KW = "spike_discharge_speed_kw"
NUM_NEGATIVE_PRICE_THRESHOLD = "negative_price_threshold"
NUM_SPIKE_MARGIN = "spike_margin"
NUM_MINIMUM_CHARGE_TARGET_KWH = "minimum_charge_target_kwh"
NUM_MINIMUM_CHARGE_MINUTES = "minimum_charge_minutes"
NUM_SAFETY_BUFFER_PERCENT = "safety_buffer_percent"
NUM_TRANSPORT_TARIFF = "transport_tariff"
NUM_PLANNING_HORIZON_HOURS = "planning_horizon_hours"
NUM_FULL_CHARGE_INTERVAL_DAYS = "full_charge_interval_days"
NUM_FULL_CHARGE_MAX_HOLD_MINUTES = "full_charge_max_hold_minutes"
NUM_FULL_CHARGE_TARGET_VOLTAGE = "full_charge_target_voltage"
# heat pump steering (as of 2026.10.17)
NUM_HP_DAY_TEMP = "hp_day_temperature"
NUM_HP_NIGHT_TEMP = "hp_night_temperature"
NUM_HP_BUFFER_DELTA = "hp_buffer_delta"
NUM_HP_DAY_FROM = "hp_day_from"
NUM_HP_NIGHT_FROM = "hp_night_from"

# (key, name, icon, min, max, step, unit, default_fn(config_entry.data))
# default_fn takes the config entry's `data` dict and returns the seed value
# used the first time this number entity is ever created.
NUMBER_DEFINITIONS = [
    (
        NUM_MIN_SOC_PERCENT,
        "Minimum SOC (solar deficit)",
        "mdi:battery-low",
        0,
        100,
        1,
        "%",
        lambda data: data.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT),
    ),
    (
        # No seed of its own: the coordinator copies the deficit minimum's
        # CURRENT value into it on its first update (EssManagerNumber.
        # seed_if_unset), so nothing changes until it's lowered.
        NUM_MIN_SOC_SURPLUS_PERCENT,
        "Minimum SOC (solar surplus)",
        "mdi:battery-10",
        0,
        100,
        1,
        "%",
        lambda data: None,
    ),
    (
        NUM_MAX_SOC_PERCENT,
        "Maximum SOC",
        "mdi:battery-high",
        50,
        150,
        1,
        "%",
        lambda data: data.get(CONF_MAX_SOC_PERCENT, DEFAULT_MAX_SOC_PERCENT),
    ),
    (
        NUM_BATTERY_CAPACITY_KWH,
        "Battery capacity",
        "mdi:battery",
        0.5,
        400,
        0.5,
        "kWh",
        lambda data: data.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH),
    ),
    (
        NUM_CHARGE_SPEED_KW,
        "Charge speed",
        "mdi:battery-charging-high",
        0.1,
        100,
        0.1,
        "kW",
        lambda data: data.get(CONF_CHARGE_SPEED_KW, DEFAULT_CHARGE_SPEED_KW),
    ),
    (
        NUM_DISCHARGE_SPEED_KW,
        "Discharge speed",
        "mdi:battery-arrow-down",
        0.1,
        100,
        0.1,
        "kW",
        lambda data: data.get(CONF_DISCHARGE_SPEED_KW, DEFAULT_DISCHARGE_SPEED_KW),
    ),
    (
        NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW,
        "Negative price charge speed",
        "mdi:battery-charging-100",
        0.1,
        100,
        0.1,
        "kW",
        lambda data: data.get(CONF_CHARGE_SPEED_KW, DEFAULT_CHARGE_SPEED_KW) * 2,
    ),
    (
        NUM_SPIKE_DISCHARGE_SPEED_KW,
        "Spike discharge speed",
        "mdi:flash-alert",
        0.1,
        100,
        0.1,
        "kW",
        lambda data: data.get(CONF_DISCHARGE_SPEED_KW, DEFAULT_DISCHARGE_SPEED_KW) * 1.5,
    ),
    (
        NUM_NEGATIVE_PRICE_THRESHOLD,
        "Negative price threshold",
        "mdi:cash-minus",
        -5.0,
        0.0,
        0.01,
        "EUR/kWh",
        lambda data: -0.20,
    ),
    (
        NUM_SPIKE_MARGIN,
        "Spike margin",
        "mdi:chart-bell-curve",
        0.0,
        5.0,
        0.01,
        "EUR/kWh",
        lambda data: 0.40,
    ),
    (
        # The smallest amount any charge buys (as of v0.2.17) - see
        # compute_low_charge_plan / compute_spike_plan.
        NUM_MINIMUM_CHARGE_TARGET_KWH,
        "Minimum charge target",
        "mdi:battery-plus",
        0.0,
        10.0,
        0.5,
        "kWh",
        lambda data: 5.0,
    ),
    (
        # The shortest charge block (as of 2026.10.6): a charge may be split
        # over the cheapest quarters before it's needed, but never into
        # blocks shorter than this.
        NUM_MINIMUM_CHARGE_MINUTES,
        "Minimum charge/sale duration",
        "mdi:timer-sand",
        15,
        120,
        15,
        "min",
        lambda data: 30,
    ),
    (
        # Kept on top of the low threshold when selling (as of v0.2.17) -
        # room for usage/solar to differ from the forecast.
        NUM_SAFETY_BUFFER_PERCENT,
        "Safety buffer",
        "mdi:shield-half-full",
        0,
        50,
        1,
        "%",
        lambda data: 5,
    ),
    (
        # Base grid transport tariff (as of v0.4.0), in the price sensor's
        # unit per kWh: buy price = price + (tariff x factor from
        # transport_factors.json) - see transport.py. 0 = no transport.
        NUM_TRANSPORT_TARIFF,
        "Transport tariff",
        "mdi:transmission-tower-import",
        0.0,
        1.0,
        0.001,
        "EUR/kWh",
        lambda data: 0.0,
    ),
    (
        NUM_PLANNING_HORIZON_HOURS,
        "Planning horizon",
        "mdi:clock-outline",
        1,
        120,
        1,
        "h",
        lambda data: 72,
    ),
    (
        NUM_FULL_CHARGE_INTERVAL_DAYS,
        "Full charge interval",
        "mdi:calendar-refresh",
        0,
        90,
        1,
        "d",
        lambda data: 14,
    ),
    (
        NUM_FULL_CHARGE_MAX_HOLD_MINUTES,
        "Full charge max hold",
        "mdi:timer-sand",
        0,
        600,
        5,
        "min",
        lambda data: 120,
    ),
    (
        NUM_FULL_CHARGE_TARGET_VOLTAGE,
        "Full charge target voltage",
        "mdi:flash",
        0,
        1000,
        0.1,
        "V",
        lambda data: data.get(CONF_FULL_CHARGE_TARGET_VOLTAGE, DEFAULT_FULL_CHARGE_TARGET_VOLTAGE),
    ),
    # heat pump steering (as of 2026.10.17) - on the heat pump card
    (NUM_HP_DAY_TEMP, "Heat pump day temperature", "mdi:white-balance-sunny", 10, 28, 0.5, "\u00b0C", lambda data: 20.5),
    (NUM_HP_NIGHT_TEMP, "Heat pump night temperature", "mdi:weather-night", 10, 28, 0.5, "\u00b0C", lambda data: 19.0),
    (NUM_HP_BUFFER_DELTA, "Heat pump buffer range", "mdi:thermometer-plus", 0, 3, 0.5, "\u00b0C", lambda data: 1.0),
    (NUM_HP_DAY_FROM, "Heat pump day from", "mdi:clock-start", 0, 23, 1, "h", lambda data: 7),
    (NUM_HP_NIGHT_FROM, "Heat pump night from", "mdi:clock-end", 0, 23, 1, "h", lambda data: 22),
]

# ---------------------------------------------------------------------------
# Forecast horizon
# ---------------------------------------------------------------------------
FORECAST_HOURS = 121  # index 0 = current hour ... index 120

STORAGE_VERSION = 1
STORAGE_KEY_SUFFIX = "_state"

# ---------------------------------------------------------------------------
# Plan-specific entities (as of v0.3.2): hidden while the plan they belong to
# is switched off in Configure, shown again when it's switched on - see
# visibility.py. Keys are the entities' own keys (number keys / sensor keys).
# ---------------------------------------------------------------------------
PLAN_ENTITY_KEYS = {
    CONF_ENABLE_NEGATIVE_PRICE_PLAN: (
        NUM_NEGATIVE_PRICE_THRESHOLD,
        NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW,
        "negative_price_status",
    ),
    CONF_ENABLE_SPIKE_PLAN: (
        NUM_SPIKE_MARGIN,
        NUM_SPIKE_DISCHARGE_SPEED_KW,
        "spike_status",
    ),
    # the heat pump model's diagnostic sensor (as of 2026.10.16)
    CONF_HP_ENABLED: ("heat_pump_model",),
    # steering's settings and switch (as of 2026.10.17)
    HP_STEERING_PLAN: (NUM_HP_DAY_TEMP, NUM_HP_NIGHT_TEMP, NUM_HP_BUFFER_DELTA, NUM_HP_DAY_FROM, NUM_HP_NIGHT_FROM, "heat_pump_steering"),
    CONF_ENABLE_FULL_CHARGE_PLAN: (
        NUM_FULL_CHARGE_INTERVAL_DAYS,
        NUM_FULL_CHARGE_MAX_HOLD_MINUTES,
        NUM_FULL_CHARGE_TARGET_VOLTAGE,
        "next_full_charge_in_days",
    ),
}
PLAN_ENABLED_DEFAULTS = {
    CONF_ENABLE_NEGATIVE_PRICE_PLAN: DEFAULT_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN: DEFAULT_ENABLE_SPIKE_PLAN,
    CONF_ENABLE_FULL_CHARGE_PLAN: DEFAULT_ENABLE_FULL_CHARGE_PLAN,
    CONF_HP_ENABLED: DEFAULT_HP_ENABLED,
    HP_STEERING_PLAN: False,
}


def plan_for_entity_key(key: str) -> str | None:
    """The Configure switch (CONF_ENABLE_*) an entity key belongs to, if any."""
    for plan, keys in PLAN_ENTITY_KEYS.items():
        if key in keys:
            return plan
    return None
