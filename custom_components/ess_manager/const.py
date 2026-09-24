"""Constants for the ESS Manager integration."""
from __future__ import annotations

DOMAIN = "ess_manager"
# number entities must be created before the coordinator's first refresh so
# that coordinator.get_number() has something to read - keep number first.
# switch.py (the "Automatic control" switch) must also be set up before the
# first refresh, so direct control knows whether it's allowed to send.
PLATFORMS = ["number", "switch", "sensor"]

UPDATE_INTERVAL_SECONDS = 30

# ---------------------------------------------------------------------------
# Config entry keys (set once during the config flow / options flow)
# ---------------------------------------------------------------------------
CONF_NAME = "name"
CONF_BATTERY_SOC_ENTITY = "battery_soc_entity"
CONF_PRICE_ENTITY = "price_entity"
CONF_SOLAR_FORECAST_ENTITIES = "solar_forecast_entities"
CONF_GRID_SETPOINT_ENTITY = "grid_setpoint_entity"

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
# setpoint itself - to a number/input_number entity, or by running a script
# with the setpoint as a variable. "Status sensor only" (off) is the default,
# so nothing changes for an installation until it's switched on in
# Configure. See control.py (the pure mapping) and controller.py (sending).
CONF_CONTROL_MODE = "control_mode"
CONTROL_MODE_OFF = "off"
CONTROL_MODE_NUMBER = "number"
CONTROL_MODE_SCRIPT = "script"
DEFAULT_CONTROL_MODE = CONTROL_MODE_OFF
CONF_CONTROL_TARGET_ENTITY = "control_target_entity"
CONF_CONTROL_UNIT = "control_unit"
DEFAULT_CONTROL_UNIT = "W"
CONF_CONTROL_SIGN = "control_sign"
DEFAULT_CONTROL_SIGN = "charge_positive"
CONF_CONTROL_IDLE_VALUE = "control_idle_value"
DEFAULT_CONTROL_IDLE_VALUE = 0.0

# -- household usage forecast: an existing "h0..h120" sensor, calculated --
# -- internally from HA's own long-term recorder statistics (the full --
# -- solar/import/export/battery energy-balance identity), or read --
# -- directly from a home-energy-consumption meter, if one is available --
CONF_USAGE_SOURCE = "usage_source"
USAGE_SOURCE_EXTERNAL_SENSOR = "external_sensor"
USAGE_SOURCE_CALCULATED = "calculated"
USAGE_SOURCE_CONSUMPTION_SENSOR = "consumption_sensor"
# Same energy-balance calculation as USAGE_SOURCE_CALCULATED, but the grid/
# solar/battery statistics are read live from Home Assistant's own Energy
# dashboard configuration (energy_source.py) instead of being picked by hand
# - so they can never drift out of sync with what the Energy dashboard uses.
USAGE_SOURCE_ENERGY_DASHBOARD = "energy_dashboard"
DEFAULT_USAGE_SOURCE = USAGE_SOURCE_ENERGY_DASHBOARD

# DEPRECATED - REMOVE IN 0.3.0: the external h0..h120 sensor and the
# hand-picked "calculated" source. Since 0.2.10 they can no longer be chosen
# for a new installation (setup only offers the Energy dashboard and the
# consumption sensor), but installations already using one keep working
# unchanged and get a Repairs notice asking them to switch (see
# __init__.py). In 0.3.0 their code paths, config fields and translations
# are deleted - see the project notes for the full removal checklist.
DEPRECATED_USAGE_SOURCES = (USAGE_SOURCE_EXTERNAL_SENSOR, USAGE_SOURCE_CALCULATED)
# What an entry that has no usage_source stored at all (only possible for
# installs from before usage_source existed, v0.1.0) has always been treated
# as. Kept separate from DEFAULT_USAGE_SOURCE (what new installs get) so
# changing the new-install default can't silently change such an entry.
# REMOVE IN 0.3.0 along with the deprecated sources.
LEGACY_DEFAULT_USAGE_SOURCE = USAGE_SOURCE_EXTERNAL_SENSOR
USAGE_SOURCE_LABELS = {
    USAGE_SOURCE_ENERGY_DASHBOARD: "Calculate it using the entities from my Energy dashboard",
    USAGE_SOURCE_CONSUMPTION_SENSOR: "Use a home energy consumption sensor I already have",
    USAGE_SOURCE_EXTERNAL_SENSOR: "An existing sensor with h0..h120 attributes",
    USAGE_SOURCE_CALCULATED: "Calculate it from hand-picked energy statistics",
}

CONF_USAGE_FORECAST_ENTITY = "usage_forecast_entity"

# Calculated-usage-forecast inputs. Import/export are lists, not single
# entities, because meters vary: a single-tariff meter exposes one
# cumulative import/export sensor, a dual-tariff meter (common e.g. for
# day/night rates) exposes two - every configured entity in each list is
# summed together for that side of the energy balance, so either shape
# works without the user needing to combine them into one sensor first.
# Solar production is a list for the same reason (multiple inverters/arrays).
# Battery charge/discharge energy are optional single entities (only some
# battery monitors expose lifetime charged/discharged energy) - when
# omitted, that term of the energy-balance identity is simply treated as 0.
CONF_GRID_IMPORT_ENTITIES = "grid_import_entities"
CONF_GRID_EXPORT_ENTITIES = "grid_export_entities"
CONF_SOLAR_PRODUCTION_ENTITIES = "solar_production_entities"
CONF_BATTERY_CHARGE_ENERGY_ENTITY = "battery_charge_energy_entity"
CONF_BATTERY_DISCHARGE_ENERGY_ENTITY = "battery_discharge_energy_entity"

# Direct-consumption-meter usage-forecast input (USAGE_SOURCE_CONSUMPTION_SENSOR).
# A list, same reasoning as solar/import/export above - some homes split
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
NUM_MIN_SOC_PERCENT = "min_soc_percent"
NUM_MAX_SOC_PERCENT = "max_soc_percent"
NUM_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
NUM_CHARGE_SPEED_KW = "charge_speed_kw"
NUM_DISCHARGE_SPEED_KW = "discharge_speed_kw"
NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW = "negative_price_charge_speed_kw"
NUM_SPIKE_DISCHARGE_SPEED_KW = "spike_discharge_speed_kw"
NUM_NEGATIVE_PRICE_THRESHOLD = "negative_price_threshold"
NUM_SPIKE_MARGIN = "spike_margin"
NUM_MINIMUM_CHARGE_TARGET_KWH = "minimum_charge_target_kwh"
NUM_PLANNING_HORIZON_HOURS = "planning_horizon_hours"
NUM_FULL_CHARGE_INTERVAL_DAYS = "full_charge_interval_days"
NUM_FULL_CHARGE_MAX_HOLD_MINUTES = "full_charge_max_hold_minutes"
NUM_FULL_CHARGE_TARGET_VOLTAGE = "full_charge_target_voltage"

# (key, name, icon, min, max, step, unit, default_fn(config_entry.data))
# default_fn takes the config entry's `data` dict and returns the seed value
# used the first time this number entity is ever created.
NUMBER_DEFINITIONS = [
    (
        NUM_MIN_SOC_PERCENT,
        "Minimum SOC",
        "mdi:battery-low",
        0,
        100,
        1,
        "%",
        lambda data: data.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT),
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
]

# ---------------------------------------------------------------------------
# Forecast horizon
# ---------------------------------------------------------------------------
FORECAST_HOURS = 121  # index 0 = current hour ... index 120

STORAGE_VERSION = 1
STORAGE_KEY_SUFFIX = "_state"
