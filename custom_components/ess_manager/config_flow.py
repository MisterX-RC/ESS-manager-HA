"""Config flow: lets the user pick their own battery/price/solar/usage
entities and seed values for the tunables (which then become `number`
entities - see number.py) instead of anything being hardcoded to one
person's Victron/Nordpool/Solcast setup.

The household usage forecast has two sources (as of v0.3.0): the Energy
dashboard's grid/solar/battery statistics (energy_source.py), or one or
more home-energy-consumption sensors. Each gets its own page after the
first one - see _EssManagerSteps for the page order.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_VOLTAGE_ENTITY,
    CONF_CHARGE_SPEED_KW,
    CONF_CONTROL_IDLE_VALUE,
    CONF_CONTROL_MODE,
    CONF_CONTROL_SIGN,
    CONF_CONTROL_TARGET_ENTITY,
    CONF_CONTROL_UNIT,
    CONTROL_MODE_NUMBER,
    CONTROL_MODE_OFF,
    DEFAULT_CONTROL_IDLE_VALUE,
    DEFAULT_CONTROL_MODE,
    DEFAULT_CONTROL_SIGN,
    DEFAULT_CONTROL_UNIT,
    CONF_DAYS_SINCE_FULL_CHARGE_ENTITY,
    CONF_DISCHARGE_SPEED_KW,
    CONF_ENABLE_FULL_CHARGE_PLAN,
    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN,
    CONF_EV_CARS,
    CONF_EV_CHARGER,
    CONF_EV_NOTIFY,
    CONF_EV_VICTRON_DEVICE,
    DEFAULT_EV_CHARGER,
    EV_CHARGER_SENSORS,
    EV_CHARGER_VICTRON,
    VICTRON_GX_DOMAIN,
    CONF_HP_COOL_ENTITIES,
    CONF_HP_ENABLED,
    CONF_HP_HEAT_ENTITIES,
    CONF_HP_INDOOR_ENTITY,
    CONF_HP_METER,
    CONF_HP_OUTDOOR_ENTITY,
    CONF_HP_SETPOINT_ENTITY,
    CONF_HP_COP_ENTITY,
    CONF_HP_BUFFER_ENABLED,
    DEFAULT_HP_BUFFER_ENABLED,
    CONF_FLOOR_COOL_CLIMATE_ENTITY,
    CONF_FLOOR_COOL_SWITCH_ENTITY,
    CONF_FLOOR_DEMAND_ENTITY,
    CONF_FLOOR_ENABLED,
    CONF_FLOOR_HELPER_ENTITY,
    CONF_FLOOR_POWER_ENTITY,
    CONF_FLOOR_PUMP_ENTITY,
    CONF_FLOOR_RETURN_ENTITY,
    CONF_FLOOR_SETPOINT_ENTITY,
    CONF_FLOOR_SLAB_ENTITY,
    CONF_FLOOR_SUPPLY_ENTITY,
    DEFAULT_FLOOR_ENABLED,
    FLOOR_REQUIRED,
    CONF_HP_HOURLY_ENABLED,
    DEFAULT_HP_HOURLY_ENABLED,
    CONF_HP_TOTAL_ENTITY,
    CONF_HP_WEATHER_ENTITY,
    CONF_HP_WIND_DIR_ENTITY,
    CONF_HP_WIND_ENTITY,
    DEFAULT_HP_ENABLED,
    DEFAULT_HP_METER,
    HP_METER_NONE,
    HP_METER_SEPARATE,
    HP_METER_TOTAL,
    CONF_EV_ENABLED,
    CONF_EV_ENERGY_ENTITY,
    CONF_EV_MAX_CURRENT,
    CONF_EV_MIN_CURRENT,
    CONF_EV_PHASES,
    CONF_EV_POWER_ENTITY,
    CONF_EV_PREDICT,
    DEFAULT_EV_ENABLED,
    DEFAULT_EV_MAX_CURRENT,
    DEFAULT_EV_MIN_CURRENT,
    DEFAULT_EV_PHASES,
    DEFAULT_EV_PREDICT,
    DEFAULT_EV_TARGET_SOC,
    EV_MAX_CURRENT_LIMIT,
    CONF_FULL_CHARGE_TARGET_VOLTAGE,
    CONF_FULL_CHARGE_TRACKING_SOURCE,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_GRID_SETPOINT_SIGN,
    DEFAULT_GRID_SETPOINT_SIGN,
    CONF_HIGH_CELL_VOLTAGE_ENTITY,
    CONF_LOW_CELL_VOLTAGE_ENTITY,
    CONF_MAX_BATTERY_CHARGE_SPEED_KW,
    CONF_NIGHT_LIMIT_ENABLED,
    CONF_NIGHT_CHARGE_SPEED_KW,
    CONF_NIGHT_DISCHARGE_SPEED_KW,
    DEFAULT_NIGHT_LIMIT_ENABLED,
    DEFAULT_NIGHT_CHARGE_SPEED_KW,
    DEFAULT_NIGHT_DISCHARGE_SPEED_KW,
    CONF_MAX_BATTERY_DISCHARGE_SPEED_KW,
    CONF_CHARGE_EFFICIENCY_PERCENT,
    CONF_DISCHARGE_EFFICIENCY_PERCENT,
    CONF_MAX_SOC_PERCENT,
    CONF_MIN_SOC_PERCENT,
    CONF_NAME,
    CONF_PRICE_ENTITY,
    CONF_SOLAR_FORECAST_ENTITIES,
    CONF_USAGE_CONSUMPTION_ENTITIES,
    CONF_USAGE_LOOKBACK_WEEKS,
    CONF_USAGE_SOURCE,
    CONF_VOLTAGE_DIFF_ENTITY,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_CHARGE_SPEED_KW,
    DEFAULT_DISCHARGE_SPEED_KW,
    DEFAULT_ENABLE_FULL_CHARGE_PLAN,
    DEFAULT_ENABLE_NEGATIVE_PRICE_PLAN,
    DEFAULT_ENABLE_SPIKE_PLAN,
    DEFAULT_FULL_CHARGE_TARGET_VOLTAGE,
    DEFAULT_FULL_CHARGE_TRACKING_SOURCE,
    DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW,
    DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW,
    DEFAULT_CHARGE_EFFICIENCY_PERCENT,
    DEFAULT_DISCHARGE_EFFICIENCY_PERCENT,
    DEFAULT_MAX_SOC_PERCENT,
    DEFAULT_MIN_SOC_PERCENT,
    DEFAULT_NAME,
    DEFAULT_USAGE_LOOKBACK_WEEKS,
    DEFAULT_USAGE_SOURCE,
    DOMAIN,
    FULL_CHARGE_TRACKING_EXTERNAL_SENSOR,
    FULL_CHARGE_TRACKING_INTERNAL,
    USAGE_SOURCE_ENERGY_DASHBOARD,
    SUPPORTED_USAGE_SOURCES,
    USAGE_SOURCE_LABELS,
)
from .control import SIGN_CHARGE_POSITIVE, SIGN_DISCHARGE_POSITIVE, UNIT_KW, UNIT_W
from .energy_source import async_get_energy_prefs
from .usage_forecast import energy_prefs_to_sources

def _usage_source_options() -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=value, label=USAGE_SOURCE_LABELS[value]) for value in SUPPORTED_USAGE_SOURCES
    ]


CONTROL_MODE_OPTIONS = [
    selector.SelectOptionDict(
        value=CONTROL_MODE_OFF, label="Status sensor only - my own automation controls the battery (default)"
    ),
    selector.SelectOptionDict(value=CONTROL_MODE_NUMBER, label="Set a number / input_number entity"),
]

CONTROL_UNIT_OPTIONS = [
    selector.SelectOptionDict(value=UNIT_W, label="W"),
    selector.SelectOptionDict(value=UNIT_KW, label="kW"),
]

CONTROL_SIGN_OPTIONS = [
    selector.SelectOptionDict(
        value=SIGN_CHARGE_POSITIVE,
        label="Positive = import from the grid (battery charges), negative = export",
    ),
    selector.SelectOptionDict(
        value=SIGN_DISCHARGE_POSITIVE,
        label="Positive = export to the grid (battery discharges), negative = import",
    ),
]

CONTROL_TARGET_DOMAINS = {
    CONTROL_MODE_NUMBER: ["number", "input_number"],
}

FULL_CHARGE_TRACKING_SOURCE_OPTIONS = [
    selector.SelectOptionDict(value=FULL_CHARGE_TRACKING_INTERNAL, label="Track internally (default)"),
    selector.SelectOptionDict(
        value=FULL_CHARGE_TRACKING_EXTERNAL_SENSOR, label="Use an external \"days since full charge\" sensor"
    ),
]


def _optional_entity_selector(domain: str | list[str] = "sensor") -> vol.Maybe:
    """An EntitySelector for a field that may be genuinely left unset
    (grid/inverter setpoint, cell voltage differential and its low/high-cell
    alternative, battery charge/discharge energy entities).

    Home Assistant's EntitySelector.__call__ validates whatever value it's
    given by calling cv.entity_id_or_uuid(value) unconditionally - it has
    no special case for None. voluptuous substitutes AND VALIDATES a
    vol.Optional's default whenever the key is missing from the submitted
    data (confirmed directly against voluptuous 0.15), so a plain
    `default=None` (the v0.1.4 fix) only ever addressed the cosmetic
    pre-fill display - submitting the form with the field actually left
    blank still fails validation every time, with "Entity None is neither
    a valid entity ID nor a valid UUID".

    vol.Maybe(x) (== vol.Any(None, x)) fixes this at the validator level:
    it accepts a literal None outright before ever reaching the entity
    validator, for both a substituted default and a value explicitly
    cleared to None. It's also not a hack around Home Assistant's own
    tooling - voluptuous_serialize (which HA uses to describe this schema
    to the frontend) specifically recognizes exactly this
    `vol.Any(None, selector)` shape, unwraps it, and still renders the
    proper entity-picker widget (with allow_none set), confirmed by
    reading voluptuous_serialize 2.7.0's convert() directly.
    """
    return vol.Maybe(selector.EntitySelector(selector.EntitySelectorConfig(domain=domain)))


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=minimum, max=maximum, step=step, unit_of_measurement=unit)
    )


def _sensors_schema(defaults: dict[str, Any], include_name: bool) -> vol.Schema:
    """Page 1 - the sensors ESS Manager reads, which usage source to use, and
    whether to enable full-charge balancing (its own sensors get their own
    page next, only when it's switched on). The name is only asked at setup.
    """
    fields: dict[Any, Any] = {}
    if include_name:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME))] = str
    current_source = defaults.get(CONF_USAGE_SOURCE)
    if current_source not in SUPPORTED_USAGE_SOURCES:
        current_source = None  # e.g. a removed source the v2 migration couldn't switch
    fields.update(
        {
            vol.Required(CONF_BATTERY_SOC_ENTITY, default=defaults.get(CONF_BATTERY_SOC_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_PRICE_ENTITY, default=defaults.get(CONF_PRICE_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_SOLAR_FORECAST_ENTITIES, default=defaults.get(CONF_SOLAR_FORECAST_ENTITIES, [])
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Optional(
                CONF_GRID_SETPOINT_ENTITY, default=defaults.get(CONF_GRID_SETPOINT_ENTITY)
            ): _optional_entity_selector(["sensor", "number", "input_number"]),
            vol.Required(
                CONF_GRID_SETPOINT_SIGN,
                default=defaults.get(CONF_GRID_SETPOINT_SIGN) or DEFAULT_GRID_SETPOINT_SIGN,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=CONTROL_SIGN_OPTIONS, mode=selector.SelectSelectorMode.LIST)
            ),
            vol.Required(
                CONF_USAGE_SOURCE, default=current_source or DEFAULT_USAGE_SOURCE
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_usage_source_options(), mode=selector.SelectSelectorMode.LIST
                )
            ),
            vol.Required(
                CONF_ENABLE_FULL_CHARGE_PLAN,
                default=defaults.get(CONF_ENABLE_FULL_CHARGE_PLAN, DEFAULT_ENABLE_FULL_CHARGE_PLAN),
            ): selector.BooleanSelector(),
        }
    )
    return vol.Schema(fields)


def _full_charge_schema(defaults: dict[str, Any], include_target_voltage: bool) -> vol.Schema:
    """Only shown when full-charge balancing is switched on. The target
    voltage is only asked at setup: it then becomes an adjustable number
    entity, so in Configure it's changed there instead.
    """
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_VOLTAGE_DIFF_ENTITY, default=defaults.get(CONF_VOLTAGE_DIFF_ENTITY)
        ): _optional_entity_selector(),
        vol.Optional(
            CONF_LOW_CELL_VOLTAGE_ENTITY, default=defaults.get(CONF_LOW_CELL_VOLTAGE_ENTITY)
        ): _optional_entity_selector(),
        vol.Optional(
            CONF_HIGH_CELL_VOLTAGE_ENTITY, default=defaults.get(CONF_HIGH_CELL_VOLTAGE_ENTITY)
        ): _optional_entity_selector(),
        # Optional at the schema level but required at submit time on this
        # page (battery_voltage_entity_required) - an empty required
        # entity field can't be expressed cleanly in voluptuous, see
        # _optional_entity_selector.
        vol.Optional(
            CONF_BATTERY_VOLTAGE_ENTITY, default=defaults.get(CONF_BATTERY_VOLTAGE_ENTITY)
        ): _optional_entity_selector(),
        vol.Required(
            CONF_FULL_CHARGE_TRACKING_SOURCE,
            default=defaults.get(CONF_FULL_CHARGE_TRACKING_SOURCE, DEFAULT_FULL_CHARGE_TRACKING_SOURCE),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=FULL_CHARGE_TRACKING_SOURCE_OPTIONS, mode=selector.SelectSelectorMode.LIST
            )
        ),
        # Required at submit time only with the external-sensor tracking
        # option (days_since_full_charge_entity_required).
        vol.Optional(
            CONF_DAYS_SINCE_FULL_CHARGE_ENTITY, default=defaults.get(CONF_DAYS_SINCE_FULL_CHARGE_ENTITY)
        ): _optional_entity_selector(),
    }
    if include_target_voltage:
        fields[
            vol.Required(
                CONF_FULL_CHARGE_TARGET_VOLTAGE,
                default=defaults.get(CONF_FULL_CHARGE_TARGET_VOLTAGE, DEFAULT_FULL_CHARGE_TARGET_VOLTAGE),
            )
        ] = _number(0, 1000, 0.1, "V")
    return vol.Schema(fields)


def _system_schema(defaults: dict[str, Any], seed_values: bool) -> vol.Schema:
    """Page 2 - the battery/system. At setup (seed_values=True) this includes
    the values that then become adjustable `number` entities (capacity,
    normal speeds, min/max SOC); in Configure those are adjusted on the
    number entities instead, so only the max battery speeds (a fixed
    hardware property with no number entity) are asked there.
    """
    fields: dict[Any, Any] = {}
    if seed_values:
        fields.update(
            {
                vol.Required(
                    CONF_BATTERY_CAPACITY_KWH,
                    default=defaults.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH),
                ): _number(0.5, 400, 0.5, "kWh"),
                vol.Required(
                    CONF_CHARGE_SPEED_KW, default=defaults.get(CONF_CHARGE_SPEED_KW, DEFAULT_CHARGE_SPEED_KW)
                ): _number(0.1, 100, 0.1, "kW"),
                vol.Required(
                    CONF_DISCHARGE_SPEED_KW, default=defaults.get(CONF_DISCHARGE_SPEED_KW, DEFAULT_DISCHARGE_SPEED_KW)
                ): _number(0.1, 100, 0.1, "kW"),
            }
        )
    fields.update(
        {
            vol.Required(
                CONF_MAX_BATTERY_CHARGE_SPEED_KW,
                default=defaults.get(CONF_MAX_BATTERY_CHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW),
            ): _number(0.1, 200, 0.1, "kW"),
            vol.Required(
                CONF_MAX_BATTERY_DISCHARGE_SPEED_KW,
                default=defaults.get(CONF_MAX_BATTERY_DISCHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW),
            ): _number(0.1, 200, 0.1, "kW"),
            vol.Required(
                CONF_CHARGE_EFFICIENCY_PERCENT,
                default=defaults.get(CONF_CHARGE_EFFICIENCY_PERCENT, DEFAULT_CHARGE_EFFICIENCY_PERCENT),
            ): _number(50, 100, 0.5, "%"),
            vol.Required(
                CONF_DISCHARGE_EFFICIENCY_PERCENT,
                default=defaults.get(CONF_DISCHARGE_EFFICIENCY_PERCENT, DEFAULT_DISCHARGE_EFFICIENCY_PERCENT),
            ): _number(50, 100, 0.5, "%"),
            # as of 2026.10.18: its two speeds on the next page
            vol.Required(
                CONF_NIGHT_LIMIT_ENABLED, default=defaults.get(CONF_NIGHT_LIMIT_ENABLED, DEFAULT_NIGHT_LIMIT_ENABLED)
            ): selector.BooleanSelector(),
        }
    )
    if seed_values:
        fields.update(
            {
                vol.Required(
                    CONF_MIN_SOC_PERCENT, default=defaults.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT)
                ): _number(0, 100, 1, "%"),
                vol.Required(
                    CONF_MAX_SOC_PERCENT, default=defaults.get(CONF_MAX_SOC_PERCENT, DEFAULT_MAX_SOC_PERCENT)
                ): _number(50, 150, 1, "%"),
            }
        )
    return vol.Schema(fields)


def _night_limit_schema(defaults: dict[str, Any]) -> vol.Schema:
    """The night limit's speeds (as of 2026.10.18) - between 22:00 and 07:00
    they replace every other charge/discharge speed."""
    return vol.Schema(
        {
            vol.Required(
                CONF_NIGHT_CHARGE_SPEED_KW, default=defaults.get(CONF_NIGHT_CHARGE_SPEED_KW, DEFAULT_NIGHT_CHARGE_SPEED_KW)
            ): _number(0, 100, 0.1, "kW"),
            vol.Required(
                CONF_NIGHT_DISCHARGE_SPEED_KW,
                default=defaults.get(CONF_NIGHT_DISCHARGE_SPEED_KW, DEFAULT_NIGHT_DISCHARGE_SPEED_KW),
            ): _number(0.1, 100, 0.1, "kW"),
        }
    )


def _plans_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Page 3 - the two optional price plans (explained in the page text)."""
    return vol.Schema(
        {
            vol.Required(
                CONF_ENABLE_NEGATIVE_PRICE_PLAN,
                default=defaults.get(CONF_ENABLE_NEGATIVE_PRICE_PLAN, DEFAULT_ENABLE_NEGATIVE_PRICE_PLAN),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_ENABLE_SPIKE_PLAN, default=defaults.get(CONF_ENABLE_SPIKE_PLAN, DEFAULT_ENABLE_SPIKE_PLAN)
            ): selector.BooleanSelector(),
            # the electric car (as of 2026.10.11) - its own pages follow
            vol.Required(CONF_EV_ENABLED, default=defaults.get(CONF_EV_ENABLED, DEFAULT_EV_ENABLED)): selector.BooleanSelector(),
            # the heat pump model (as of 2026.10.16) - its own pages follow
            vol.Required(CONF_HP_ENABLED, default=defaults.get(CONF_HP_ENABLED, DEFAULT_HP_ENABLED)): selector.BooleanSelector(),
        }
    )


HP_METER_OPTIONS = [
    selector.SelectOptionDict(value=HP_METER_SEPARATE, label="Separate sensors per mode (heating, cooling, hot water)"),
    selector.SelectOptionDict(value=HP_METER_TOTAL, label="One total sensor for the whole heat pump"),
    selector.SelectOptionDict(value=HP_METER_NONE, label="No own metering (only the total household usage)"),
]


def _hp_meter_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HP_METER, default=defaults.get(CONF_HP_METER, DEFAULT_HP_METER)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=HP_METER_OPTIONS, mode=selector.SelectSelectorMode.LIST)
            ),
        }
    )


def _hp_schema(defaults: dict[str, Any], meter: str) -> vol.Schema:
    """The heat pump's sensors (as of 2026.10.16): its energy (per the
    metering), the outdoor temperature, the weather forecast, and optional
    wind, wind direction, indoor and wanted temperature."""
    fields: dict[Any, Any] = {}
    multi = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True))
    if meter == HP_METER_SEPARATE:
        fields[vol.Required(CONF_HP_HEAT_ENTITIES, default=defaults.get(CONF_HP_HEAT_ENTITIES, []))] = multi
        fields[vol.Optional(CONF_HP_COOL_ENTITIES, default=defaults.get(CONF_HP_COOL_ENTITIES, []))] = multi
    elif meter == HP_METER_TOTAL:
        fields[vol.Optional(CONF_HP_TOTAL_ENTITY, default=defaults.get(CONF_HP_TOTAL_ENTITY))] = _optional_entity_selector()
    fields.update(
        {
            vol.Optional(CONF_HP_OUTDOOR_ENTITY, default=defaults.get(CONF_HP_OUTDOOR_ENTITY)): _optional_entity_selector(),
            vol.Optional(CONF_HP_WEATHER_ENTITY, default=defaults.get(CONF_HP_WEATHER_ENTITY)): _optional_entity_selector("weather"),
            vol.Optional(CONF_HP_WIND_ENTITY, default=defaults.get(CONF_HP_WIND_ENTITY)): _optional_entity_selector(),
            vol.Optional(CONF_HP_WIND_DIR_ENTITY, default=defaults.get(CONF_HP_WIND_DIR_ENTITY)): _optional_entity_selector(),
            vol.Optional(CONF_HP_INDOOR_ENTITY, default=defaults.get(CONF_HP_INDOOR_ENTITY)): _optional_entity_selector(),
            vol.Optional(CONF_HP_SETPOINT_ENTITY, default=defaults.get(CONF_HP_SETPOINT_ENTITY)): _optional_entity_selector(
                ["climate", "sensor", "number", "input_number"]
            ),
            # as of 2026.10.17
            vol.Optional(CONF_HP_COP_ENTITY, default=defaults.get(CONF_HP_COP_ENTITY)): _optional_entity_selector(),
            vol.Optional(
                CONF_HP_HOURLY_ENABLED, default=defaults.get(CONF_HP_HOURLY_ENABLED, DEFAULT_HP_HOURLY_ENABLED)
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_HP_BUFFER_ENABLED, default=defaults.get(CONF_HP_BUFFER_ENABLED, DEFAULT_HP_BUFFER_ENABLED)
            ): selector.BooleanSelector(),
            # as of 2026.10.23 - its own page follows
            vol.Optional(
                CONF_FLOOR_ENABLED, default=defaults.get(CONF_FLOOR_ENABLED, DEFAULT_FLOOR_ENABLED)
            ): selector.BooleanSelector(),
        }
    )
    return vol.Schema(fields)


def _floor_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Floor control's entities (as of 2026.10.23)."""
    req = lambda key, _unused: vol.Required(key, default=defaults.get(key)) if defaults.get(key) else vol.Required(key)  # noqa: E731
    return vol.Schema(
        {
            req(CONF_FLOOR_SETPOINT_ENTITY, None): selector.EntitySelector(selector.EntitySelectorConfig(domain=["number", "input_number"])),
            req(CONF_FLOOR_DEMAND_ENTITY, None): selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "input_boolean"])),
            req(CONF_FLOOR_HELPER_ENTITY, None): selector.EntitySelector(selector.EntitySelectorConfig(domain=["input_boolean", "switch"])),
            req(CONF_FLOOR_SUPPLY_ENTITY, None): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            req(CONF_FLOOR_RETURN_ENTITY, None): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            req(CONF_FLOOR_PUMP_ENTITY, None): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            req(CONF_FLOOR_POWER_ENTITY, None): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_FLOOR_SLAB_ENTITY, default=defaults.get(CONF_FLOOR_SLAB_ENTITY)): _optional_entity_selector(),
            vol.Optional(CONF_FLOOR_COOL_SWITCH_ENTITY, default=defaults.get(CONF_FLOOR_COOL_SWITCH_ENTITY)): _optional_entity_selector(
                ["switch", "input_boolean", "binary_sensor"]
            ),
            vol.Optional(CONF_FLOOR_COOL_CLIMATE_ENTITY, default=defaults.get(CONF_FLOOR_COOL_CLIMATE_ENTITY)): _optional_entity_selector("climate"),
        }
    )


EV_PHASE_OPTIONS = [
    selector.SelectOptionDict(value="1", label="1 phase"),
    selector.SelectOptionDict(value="3", label="3 phases"),
]

# Fields of the cars page that aren't settings themselves.
EV_CAR_REMOVE = "ev_car_remove"
EV_CAR_NAME = "ev_car_name"
EV_CAR_CAPACITY = "ev_car_capacity_kwh"
EV_CAR_TARGET = "ev_car_target_soc"
EV_CAR_ADD_ANOTHER = "ev_car_add_another"


EV_CHARGER_OPTIONS = [
    selector.SelectOptionDict(value=EV_CHARGER_SENSORS, label="Energy and power sensors (forecast only)"),
    selector.SelectOptionDict(value=EV_CHARGER_VICTRON, label="Victron EV charging station (ESS Manager drives it)"),
]


def victron_charger_entities(hass, device_id: Optional[str]) -> dict[str, str]:
    """The Victron GX entities of an EV charging station device, by role
    (see ev_charger.VICTRON_KEYS) - found by their translation key."""
    from .ev_charger import VICTRON_KEYS

    if not device_id:
        return {}
    by_key = {v: k for k, v in VICTRON_KEYS.items()}
    out: dict[str, str] = {}
    for entry in er.async_entries_for_device(er.async_get(hass), device_id):
        role = by_key.get(entry.translation_key or "")
        if role and not entry.disabled_by:
            out[role] = entry.entity_id
    return out


def _notify_options(hass) -> list[selector.SelectOptionDict]:
    """The Companion app notify services (the ones that can show buttons)."""
    services = sorted(s for s in (hass.services.async_services().get("notify") or {}) if s.startswith("mobile_app_"))
    return [selector.SelectOptionDict(value=s, label=f"notify.{s}") for s in services]


def _ev_schema(defaults: dict[str, Any], notify_options: Optional[list] = None) -> vol.Schema:
    """The car charger (as of 2026.10.11): its energy and power sensors, the
    charging current range and phases, and whether sessions are predicted
    from the history. As of 2026.10.27 the charger can instead be a Victron
    EV charging station (a device of the Victron GX integration) with the
    phones to ask on."""
    current = _number(1, EV_MAX_CURRENT_LIMIT, 1, "A")
    return vol.Schema(
        {
            vol.Required(CONF_EV_CHARGER, default=defaults.get(CONF_EV_CHARGER, DEFAULT_EV_CHARGER)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=EV_CHARGER_OPTIONS, mode=selector.SelectSelectorMode.LIST)
            ),
            vol.Optional(CONF_EV_VICTRON_DEVICE, default=defaults.get(CONF_EV_VICTRON_DEVICE)): vol.Maybe(
                selector.DeviceSelector(selector.DeviceSelectorConfig(integration=VICTRON_GX_DOMAIN))
            ),
            vol.Optional(CONF_EV_NOTIFY, default=list(defaults.get(CONF_EV_NOTIFY) or [])): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_options or [], multiple=True, custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_EV_ENERGY_ENTITY, default=defaults.get(CONF_EV_ENERGY_ENTITY)): _optional_entity_selector(),
            vol.Optional(CONF_EV_POWER_ENTITY, default=defaults.get(CONF_EV_POWER_ENTITY)): _optional_entity_selector(),
            vol.Required(
                CONF_EV_MIN_CURRENT, default=defaults.get(CONF_EV_MIN_CURRENT, DEFAULT_EV_MIN_CURRENT)
            ): current,
            vol.Required(
                CONF_EV_MAX_CURRENT, default=defaults.get(CONF_EV_MAX_CURRENT, DEFAULT_EV_MAX_CURRENT)
            ): current,
            vol.Required(
                CONF_EV_PHASES, default=str(defaults.get(CONF_EV_PHASES, DEFAULT_EV_PHASES))
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=EV_PHASE_OPTIONS, mode=selector.SelectSelectorMode.LIST)
            ),
            vol.Required(CONF_EV_PREDICT, default=defaults.get(CONF_EV_PREDICT, DEFAULT_EV_PREDICT)): selector.BooleanSelector(),
        }
    )


def _ev_cars_schema(cars: list[dict[str, Any]]) -> vol.Schema:
    """Add a car (name, battery, target) and/or remove existing ones; "add
    another" shows the page again."""
    fields: dict[Any, Any] = {}
    if cars:
        fields[vol.Optional(EV_CAR_REMOVE, default=[])] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=c["id"], label=c["name"]) for c in cars],
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
            )
        )
    fields.update(
        {
            vol.Optional(EV_CAR_NAME): selector.TextSelector(),
            vol.Optional(EV_CAR_CAPACITY): _number(1, 250, 0.1, "kWh"),
            vol.Required(EV_CAR_TARGET, default=DEFAULT_EV_TARGET_SOC): _number(10, 100, 1, "%"),
            vol.Required(EV_CAR_ADD_ANOTHER, default=False): selector.BooleanSelector(),
        }
    )
    return vol.Schema(fields)


def _cars_text(cars: list[dict[str, Any]]) -> str:
    if not cars:
        return "(none)"
    lines = []
    for c in cars:
        battery = f"{c['capacity_kwh']:g} kWh, target {c['target_soc']:g}%" if c.get("capacity_kwh") else "no battery size (kWh only)"
        lines.append(f"- {c['name']}: {battery}")
    return "\n".join(lines)


def _control_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Page 4 - whether ESS Manager sends the setpoint itself (explained in
    the page text). Off ("Status sensor only") is the default."""
    current_mode = defaults.get(CONF_CONTROL_MODE)
    if current_mode not in (CONTROL_MODE_OFF, CONTROL_MODE_NUMBER):
        current_mode = DEFAULT_CONTROL_MODE  # e.g. the removed v0.2.14 "script" mode
    return vol.Schema(
        {
            vol.Required(CONF_CONTROL_MODE, default=current_mode): selector.SelectSelector(
                selector.SelectSelectorConfig(options=CONTROL_MODE_OPTIONS, mode=selector.SelectSelectorMode.LIST)
            ),
        }
    )


def _control_target_schema(defaults: dict[str, Any], mode: str) -> vol.Schema:
    """Only when direct control is chosen: the number/input_number entity to
    send the setpoint to, and its unit/sign convention. The previous target
    is only pre-filled if it's still a number/input_number entity."""
    domains = CONTROL_TARGET_DOMAINS[mode]
    current_target = defaults.get(CONF_CONTROL_TARGET_ENTITY)
    if current_target and current_target.split(".", 1)[0] in domains:
        target_key = vol.Required(CONF_CONTROL_TARGET_ENTITY, default=current_target)
    else:
        target_key = vol.Required(CONF_CONTROL_TARGET_ENTITY)
    return vol.Schema(
        {
            target_key: selector.EntitySelector(selector.EntitySelectorConfig(domain=domains)),
            vol.Required(
                CONF_CONTROL_UNIT, default=defaults.get(CONF_CONTROL_UNIT) or DEFAULT_CONTROL_UNIT
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=CONTROL_UNIT_OPTIONS, mode=selector.SelectSelectorMode.LIST)
            ),
            vol.Required(
                CONF_CONTROL_SIGN, default=defaults.get(CONF_CONTROL_SIGN) or DEFAULT_CONTROL_SIGN
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=CONTROL_SIGN_OPTIONS, mode=selector.SelectSelectorMode.LIST)
            ),
            vol.Required(
                CONF_CONTROL_IDLE_VALUE,
                default=defaults.get(CONF_CONTROL_IDLE_VALUE, DEFAULT_CONTROL_IDLE_VALUE),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-100000, max=100000, step="any", mode=selector.NumberSelectorMode.BOX
                )
            ),
        }
    )


def _usage_consumption_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_USAGE_CONSUMPTION_ENTITIES, default=defaults.get(CONF_USAGE_CONSUMPTION_ENTITIES, [])
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Required(
                CONF_USAGE_LOOKBACK_WEEKS, default=defaults.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=12, step=1, unit_of_measurement="weeks")),
        }
    )


def _usage_energy_dashboard_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_USAGE_LOOKBACK_WEEKS, default=defaults.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=12, step=1, unit_of_measurement="weeks")),
        }
    )


async def _async_detect_energy_dashboard(hass) -> tuple[dict[str, list[str]], str]:
    """What the Energy dashboard currently has configured, plus a
    human-readable summary for the setup form's description - so the user
    can see exactly which statistics will be used before confirming.
    """
    sources = energy_prefs_to_sources(await async_get_energy_prefs(hass))
    labels = (
        ("import", "Grid import"),
        ("export", "Grid export"),
        ("solar", "Solar production"),
        ("battery_discharge", "Battery discharge"),
        ("battery_charge", "Battery charge"),
    )
    lines = [f"- {label}: {', '.join(sources[key]) if sources[key] else '(none)'}" for key, label in labels]
    return sources, "\n".join(lines)


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Blank optional entity-selector strings become None rather than ''."""
    data = dict(data)
    for key in (
        CONF_GRID_SETPOINT_ENTITY,
            CONF_VOLTAGE_DIFF_ENTITY,
        CONF_LOW_CELL_VOLTAGE_ENTITY,
        CONF_HIGH_CELL_VOLTAGE_ENTITY,
        CONF_BATTERY_VOLTAGE_ENTITY,
        CONF_DAYS_SINCE_FULL_CHARGE_ENTITY,
        CONF_EV_ENERGY_ENTITY,
        CONF_EV_POWER_ENTITY,
        CONF_HP_TOTAL_ENTITY,
        CONF_HP_OUTDOOR_ENTITY,
        CONF_HP_WEATHER_ENTITY,
        CONF_HP_WIND_ENTITY,
        CONF_HP_WIND_DIR_ENTITY,
        CONF_HP_INDOOR_ENTITY,
        CONF_HP_SETPOINT_ENTITY,
        CONF_HP_COP_ENTITY,
        CONF_FLOOR_SLAB_ENTITY,
        CONF_FLOOR_COOL_SWITCH_ENTITY,
        CONF_FLOOR_COOL_CLIMATE_ENTITY,
    ):
        if key in data and not data.get(key):
            data[key] = None
    return data


class _EssManagerSteps:
    """The pages shared by setup and Configure, in order:

      1. `user` (setup) / `init` (Configure) - sensors, usage source, and the
         full-charge balancing switch
      2. the usage-source page for the chosen source (`usage_energy_dashboard`
         / `usage_consumption`)
      3. `full_charge` - only when full-charge balancing is switched on
      4. `system` - battery/system values
      5. `plans` - the negative-price and spike plan switches, explained,
         and the electric car switch
      5a. `ev` and `ev_cars` - only with the electric car: the charger, and
         the cars (as of 2026.10.11)
      5b. `hp_meter` and `hp` - only with the heat pump model: its metering,
         and its sensors and weather forecast (as of 2026.10.16)
      6. `control` - whether ESS Manager sends the setpoint itself
      7. `control_target` - only when it does: where to, unit, sign, idle

    The flow ends after `control` (Status sensor only) or `control_target`.

    Subclasses provide `_defaults()` (empty at setup, the current settings in
    Configure), `_seed_values` (whether the system page includes the values
    that become number entities) and `_async_finish(data)`.
    """

    _data: dict[str, Any]
    _seed_values: bool

    def _defaults(self) -> dict[str, Any]:
        raise NotImplementedError

    async def _async_finish(self, data: dict[str, Any]):
        raise NotImplementedError

    async def _async_after_sensors(self):
        source = self._data[CONF_USAGE_SOURCE]
        if source == USAGE_SOURCE_ENERGY_DASHBOARD:
            return await self.async_step_usage_energy_dashboard()
        return await self.async_step_usage_consumption()

    async def _async_after_usage(self):
        if self._data.get(CONF_ENABLE_FULL_CHARGE_PLAN):
            return await self.async_step_full_charge()
        return await self.async_step_system()

    def _sensors_errors(self, data: dict[str, Any]) -> dict[str, str]:
        if not data.get(CONF_SOLAR_FORECAST_ENTITIES):
            return {"base": "solar_forecast_required"}
        return {}

    async def async_step_usage_energy_dashboard(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        sources, detected = await _async_detect_energy_dashboard(self.hass)
        if user_input is not None:
            if not sources["import"]:
                errors["base"] = "energy_dashboard_not_configured"
            else:
                self._data.update(_clean(user_input))
                return await self._async_after_usage()
        return self.async_show_form(
            step_id="usage_energy_dashboard",
            data_schema=_usage_energy_dashboard_schema(self._defaults()),
            errors=errors,
            description_placeholders={"detected": detected},
        )

    async def async_step_usage_consumption(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not cleaned.get(CONF_USAGE_CONSUMPTION_ENTITIES):
                errors["base"] = "usage_consumption_entities_required"
            else:
                self._data.update(cleaned)
                return await self._async_after_usage()
        return self.async_show_form(
            step_id="usage_consumption", data_schema=_usage_consumption_schema(self._defaults()), errors=errors
        )

    async def async_step_full_charge(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not cleaned.get(CONF_BATTERY_VOLTAGE_ENTITY):
                # A core leg of "genuinely balanced" - required whenever the
                # full-charge plan is on.
                errors["base"] = "battery_voltage_entity_required"
            elif (
                cleaned.get(CONF_FULL_CHARGE_TRACKING_SOURCE) == FULL_CHARGE_TRACKING_EXTERNAL_SENSOR
                and not cleaned.get(CONF_DAYS_SINCE_FULL_CHARGE_ENTITY)
            ):
                errors["base"] = "days_since_full_charge_entity_required"
            else:
                self._data.update(cleaned)
                return await self.async_step_system()
        return self.async_show_form(
            step_id="full_charge",
            data_schema=_full_charge_schema(self._defaults(), include_target_voltage=self._seed_values),
            errors=errors,
        )

    async def async_step_system(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data.update(user_input)
            if user_input.get(CONF_NIGHT_LIMIT_ENABLED):
                return await self.async_step_night_limit()
            return await self.async_step_plans()
        return self.async_show_form(
            step_id="system", data_schema=_system_schema(self._defaults(), seed_values=self._seed_values)
        )

    async def async_step_night_limit(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_plans()
        return self.async_show_form(
            step_id="night_limit", data_schema=_night_limit_schema({**self._defaults(), **self._data})
        )

    async def async_step_plans(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data.update(user_input)
            if user_input.get(CONF_EV_ENABLED):
                return await self.async_step_ev()
            return await self._async_after_ev()
        return self.async_show_form(step_id="plans", data_schema=_plans_schema(self._defaults()))

    async def async_step_ev(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            cleaned[CONF_EV_NOTIFY] = [s.removeprefix("notify.") for s in (cleaned.get(CONF_EV_NOTIFY) or []) if s]
            victron = cleaned.get(CONF_EV_CHARGER) == EV_CHARGER_VICTRON
            if victron:
                from .ev_charger import VICTRON_REQUIRED

                found = victron_charger_entities(self.hass, cleaned.get(CONF_EV_VICTRON_DEVICE))
                if not cleaned.get(CONF_EV_VICTRON_DEVICE):
                    errors["base"] = "ev_victron_device_required"
                elif any(k not in found for k in VICTRON_REQUIRED):
                    errors["base"] = "ev_victron_incomplete"
                else:
                    # the history and the live values come from the charger itself
                    cleaned[CONF_EV_ENERGY_ENTITY] = found["energy"]
                    cleaned[CONF_EV_POWER_ENTITY] = found["power"]
            if errors:
                pass
            elif not cleaned.get(CONF_EV_ENERGY_ENTITY) or not cleaned.get(CONF_EV_POWER_ENTITY):
                errors["base"] = "ev_entities_required"
            elif float(cleaned[CONF_EV_MIN_CURRENT]) > float(cleaned[CONF_EV_MAX_CURRENT]):
                errors["base"] = "ev_current_range"
            else:
                cleaned[CONF_EV_PHASES] = int(cleaned[CONF_EV_PHASES])
                cleaned[CONF_EV_MIN_CURRENT] = int(cleaned[CONF_EV_MIN_CURRENT])
                cleaned[CONF_EV_MAX_CURRENT] = int(cleaned[CONF_EV_MAX_CURRENT])
                self._data.update(cleaned)
                return await self.async_step_ev_cars()
        return self.async_show_form(
            step_id="ev", data_schema=_ev_schema({**self._defaults(), **self._data}, _notify_options(self.hass)), errors=errors
        )

    async def async_step_ev_cars(self, user_input: dict[str, Any] | None = None):
        cars = [dict(c) for c in self._data.get(CONF_EV_CARS, self._defaults().get(CONF_EV_CARS) or [])]
        errors: dict[str, str] = {}
        if user_input is not None:
            remove = set(user_input.get(EV_CAR_REMOVE) or [])
            cars = [c for c in cars if c["id"] not in remove]
            name = (user_input.get(EV_CAR_NAME) or "").strip()
            if name:
                if any(c["name"].lower() == name.lower() for c in cars):
                    errors["base"] = "ev_car_exists"
                else:
                    capacity = user_input.get(EV_CAR_CAPACITY)
                    cars.append(
                        {
                            "id": uuid.uuid4().hex[:8],
                            "name": name,
                            "capacity_kwh": float(capacity) if capacity else None,
                            "target_soc": float(user_input.get(EV_CAR_TARGET, DEFAULT_EV_TARGET_SOC)),
                        }
                    )
            if not errors:
                self._data[CONF_EV_CARS] = cars
                if user_input.get(EV_CAR_ADD_ANOTHER):
                    return self.async_show_form(
                        step_id="ev_cars",
                        data_schema=_ev_cars_schema(cars),
                        description_placeholders={"cars": _cars_text(cars)},
                    )
                return await self._async_after_ev()
        return self.async_show_form(
            step_id="ev_cars",
            data_schema=_ev_cars_schema(cars),
            errors=errors,
            description_placeholders={"cars": _cars_text(cars)},
        )

    async def _async_after_ev(self):
        if self._data.get(CONF_HP_ENABLED):
            return await self.async_step_hp_meter()
        return await self.async_step_control()

    async def async_step_hp_meter(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_hp()
        return self.async_show_form(
            step_id="hp_meter", data_schema=_hp_meter_schema({**self._defaults(), **self._data})
        )

    async def async_step_hp(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        meter = self._data.get(CONF_HP_METER, DEFAULT_HP_METER)
        if user_input is not None:
            cleaned = _clean(user_input)
            if meter == HP_METER_SEPARATE and not cleaned.get(CONF_HP_HEAT_ENTITIES):
                errors["base"] = "hp_heat_required"
            elif meter == HP_METER_TOTAL and not cleaned.get(CONF_HP_TOTAL_ENTITY):
                errors["base"] = "hp_total_required"
            elif not cleaned.get(CONF_HP_OUTDOOR_ENTITY):
                errors["base"] = "hp_outdoor_required"
            elif not cleaned.get(CONF_HP_WEATHER_ENTITY):
                errors["base"] = "hp_weather_required"
            elif cleaned.get(CONF_FLOOR_ENABLED) and not (cleaned.get(CONF_HP_SETPOINT_ENTITY) or "").startswith("climate."):
                errors["base"] = "floor_needs_thermostat"
            elif cleaned.get(CONF_FLOOR_ENABLED) and not cleaned.get(CONF_HP_HOURLY_ENABLED):
                errors["base"] = "floor_needs_hourly"
            else:
                self._data.update(cleaned)
                if cleaned.get(CONF_FLOOR_ENABLED):
                    return await self.async_step_floor()
                return await self.async_step_control()
        return self.async_show_form(
            step_id="hp", data_schema=_hp_schema({**self._defaults(), **self._data}, meter), errors=errors
        )

    async def async_step_floor(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = _clean(user_input)
            if not all(cleaned.get(k) for k in FLOOR_REQUIRED):
                errors["base"] = "floor_entities_required"
            elif cleaned.get(CONF_FLOOR_HELPER_ENTITY) == cleaned.get(CONF_FLOOR_DEMAND_ENTITY):
                errors["base"] = "floor_helper_same"
            else:
                self._data.update(cleaned)
                return await self.async_step_control()
        return self.async_show_form(step_id="floor", data_schema=_floor_schema({**self._defaults(), **self._data}), errors=errors)

    async def async_step_control(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data.update(user_input)
            if user_input.get(CONF_CONTROL_MODE) in CONTROL_TARGET_DOMAINS:
                return await self.async_step_control_target()
            return await self._async_finish(self._data)
        return self.async_show_form(step_id="control", data_schema=_control_schema(self._defaults()))

    async def async_step_control_target(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        mode = self._data[CONF_CONTROL_MODE]
        if user_input is not None:
            target = user_input.get(CONF_CONTROL_TARGET_ENTITY) or ""
            if target.split(".", 1)[0] not in CONTROL_TARGET_DOMAINS[mode]:
                errors["base"] = "control_target_wrong_type"
            else:
                self._data.update(user_input)
                return await self._async_finish(self._data)
        return self.async_show_form(
            step_id="control_target",
            data_schema=_control_target_schema({**self._defaults(), **self._data}, mode),
            errors=errors,
        )


class EssManagerConfigFlow(_EssManagerSteps, config_entries.ConfigFlow, domain=DOMAIN):
    """Initial setup of one ESS Manager instance - see _EssManagerSteps for
    the page order. The last page (`control`, or `control_target` when direct
    control is chosen) creates the config entry.
    """

    # 2 as of v0.3.0 - see __init__.async_migrate_entry.
    VERSION = 2

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._seed_values = True

    def _defaults(self) -> dict[str, Any]:
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            errors = self._sensors_errors(data)
            if not errors:
                self._data = data
                return await self._async_after_sensors()
        return self.async_show_form(
            step_id="user", data_schema=_sensors_schema({}, include_name=True), errors=errors
        )

    async def _async_finish(self, data: dict[str, Any]):
        await self.async_set_unique_id(f"{DOMAIN}_{data[CONF_NAME].lower().replace(' ', '_')}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data[CONF_NAME], data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "EssManagerOptionsFlow":
        return EssManagerOptionsFlow()


class EssManagerOptionsFlow(_EssManagerSteps, config_entries.OptionsFlow):
    """Configure - the same pages as setup (see _EssManagerSteps), pre-filled
    with the current settings, except that the name and the values that
    became `number` entities at setup (capacity, normal charge/discharge
    speed, min/max SOC) aren't asked again - adjust those on the number
    entities. Max battery charge/discharge speed are the exception: a fixed
    hardware property with no number entity, so they're editable here.

    Does NOT store `config_entry` itself in `__init__` - recent Home
    Assistant core versions set `self.config_entry` automatically after
    constructing the flow, and an integration that assigns it manually
    crashes the options flow with a generic 500 error.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._seed_values = False

    def _defaults(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            errors = self._sensors_errors(data)
            if not errors:
                self._data = data
                return await self._async_after_sensors()
        return self.async_show_form(
            step_id="init", data_schema=_sensors_schema(self._defaults(), include_name=False), errors=errors
        )

    async def _async_finish(self, data: dict[str, Any]):
        # Saving options replaces them entirely, so start from the previous
        # options: settings on pages that were skipped this time (e.g. the
        # full-charge sensors while that plan is switched off) are kept
        # rather than silently dropped.
        return self.async_create_entry(title="", data={**self.config_entry.options, **data})
