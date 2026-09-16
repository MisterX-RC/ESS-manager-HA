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
CONF_USAGE_FORECAST_ENTITY = "usage_forecast_entity"
CONF_SOLAR_FORECAST_ENTITIES = "solar_forecast_entities"
CONF_GRID_SETPOINT_ENTITY = "grid_setpoint_entity"
CONF_VOLTAGE_DIFF_ENTITY = "voltage_diff_entity"

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
CONF_MIN_SOC_PERCENT = "min_soc_percent"
CONF_MAX_SOC_PERCENT = "max_soc_percent"

# ---------------------------------------------------------------------------
# Defaults for the initial config flow
# ---------------------------------------------------------------------------
DEFAULT_NAME = "ESS Manager"
DEFAULT_BATTERY_CAPACITY_KWH = 30.0
DEFAULT_CHARGE_SPEED_KW = 7.0
DEFAULT_DISCHARGE_SPEED_KW = 10.0
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
