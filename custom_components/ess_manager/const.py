"""Constants for the ESS Manager integration."""
from __future__ import annotations

DOMAIN = "ess_manager"
# number entities must be created before the coordinator's first refresh so
# that coordinator.get_number() has something to read - keep number first.
PLATFORMS = ["number", "sensor"]

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

# -- household usage forecast: an existing "h0..h120" sensor, calculated --
# -- internally from HA's own long-term recorder statistics (the full --
# -- solar/import/export/battery energy-balance identity), or read --
# -- directly from a home-energy-consumption meter, if one is available --
CONF_USAGE_SOURCE = "usage_source"
USAGE_SOURCE_EXTERNAL_SENSOR = "external_sensor"
USAGE_SOURCE_CALCULATED = "calculated"
USAGE_SOURCE_CONSUMPTION_SENSOR = "consumption_sensor"
DEFAULT_USAGE_SOURCE = USAGE_SOURCE_EXTERNAL_SENSOR

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

# The calculated usage forecast queries long-term recorder statistics, which
# only ever land once per hour - recomputing it every 30-second coordinator
# cycle (like the rest of the pipeline) would just hammer the database for
# an answer that can't have changed. Recomputed at most this often; cached
# in between (see coordinator.py's _async_get_calculated_usage_forecast).
USAGE_FORECAST_RECALC_MINUTES = 55

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
CONF_MAX_BATTERY_CHARGE_SPEED_KW = "max_battery_charge_speed_kw"
CONF_MAX_BATTERY_DISCHARGE_SPEED_KW = "max_battery_discharge_speed_kw"

CONF_MIN_SOC_PERCENT = "min_soc_percent"
CONF_MAX_SOC_PERCENT = "max_soc_percent"

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
NUM_MAX_BATTERY_CHARGE_SPEED_KW = "max_battery_charge_speed_kw"
NUM_MAX_BATTERY_DISCHARGE_SPEED_KW = "max_battery_discharge_speed_kw"
NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW = "negative_price_charge_speed_kw"
NUM_SPIKE_DISCHARGE_SPEED_KW = "spike_discharge_speed_kw"
NUM_NEGATIVE_PRICE_THRESHOLD = "negative_price_threshold"
NUM_SPIKE_MARGIN = "spike_margin"
NUM_MINIMUM_CHARGE_TARGET_KWH = "minimum_charge_target_kwh"
NUM_PLANNING_HORIZON_HOURS = "planning_horizon_hours"
NUM_FULL_CHARGE_INTERVAL_DAYS = "full_charge_interval_days"
NUM_FULL_CHARGE_MAX_HOLD_MINUTES = "full_charge_max_hold_minutes"

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
        0,
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
        NUM_MAX_BATTERY_CHARGE_SPEED_KW,
        "Max battery charge speed",
        "mdi:battery-charging-100",
        0.1,
        200,
        0.1,
        "kW",
        lambda data: data.get(CONF_MAX_BATTERY_CHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW),
    ),
    (
        NUM_MAX_BATTERY_DISCHARGE_SPEED_KW,
        "Max battery discharge speed",
        "mdi:battery-arrow-down-outline",
        0.1,
        200,
        0.1,
        "kW",
        lambda data: data.get(CONF_MAX_BATTERY_DISCHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW),
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
        100.0,
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
]

# ---------------------------------------------------------------------------
# Forecast horizon
# ---------------------------------------------------------------------------
FORECAST_HOURS = 121  # index 0 = current hour ... index 120

STORAGE_VERSION = 1
STORAGE_KEY_SUFFIX = "_state"
