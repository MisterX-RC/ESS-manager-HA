"""Config flow: lets the user pick their own battery/price/solar/usage
entities and seed values for the tunables (which then become `number`
entities - see number.py) instead of anything being hardcoded to one
person's Victron/Nordpool/Solcast setup.

The household usage forecast has three mutually-exclusive sources, so this
flow branches after the main step: an existing "h0..h120" sensor (the
original behavior), calculated internally from Home Assistant's own
recorder statistics via the full solar/import/export/battery energy-balance
identity, or read directly from one or more home-energy-consumption
sensors, if the user already has one - see usage_forecast.py/
statistics_source.py. Each needs its own second step to collect the right
entities.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CHARGE_ENERGY_ENTITY,
    CONF_BATTERY_DISCHARGE_ENERGY_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_VOLTAGE_ENTITY,
    CONF_CHARGE_SPEED_KW,
    CONF_DISCHARGE_SPEED_KW,
    CONF_ENABLE_FULL_CHARGE_PLAN,
    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN,
    CONF_FULL_CHARGE_TARGET_VOLTAGE,
    CONF_GRID_EXPORT_ENTITIES,
    CONF_GRID_IMPORT_ENTITIES,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_HIGH_CELL_VOLTAGE_ENTITY,
    CONF_LOW_CELL_VOLTAGE_ENTITY,
    CONF_MAX_BATTERY_CHARGE_SPEED_KW,
    CONF_MAX_BATTERY_DISCHARGE_SPEED_KW,
    CONF_MAX_SOC_PERCENT,
    CONF_MIN_SOC_PERCENT,
    CONF_NAME,
    CONF_PRICE_ENTITY,
    CONF_SOLAR_FORECAST_ENTITIES,
    CONF_SOLAR_PRODUCTION_ENTITIES,
    CONF_USAGE_CONSUMPTION_ENTITIES,
    CONF_USAGE_FORECAST_ENTITY,
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
    DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW,
    DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW,
    DEFAULT_MAX_SOC_PERCENT,
    DEFAULT_MIN_SOC_PERCENT,
    DEFAULT_NAME,
    DEFAULT_USAGE_LOOKBACK_WEEKS,
    DEFAULT_USAGE_SOURCE,
    DOMAIN,
    USAGE_SOURCE_CALCULATED,
    USAGE_SOURCE_CONSUMPTION_SENSOR,
    USAGE_SOURCE_EXTERNAL_SENSOR,
)

USAGE_SOURCE_OPTIONS = [
    selector.SelectOptionDict(value=USAGE_SOURCE_EXTERNAL_SENSOR, label="An existing sensor with h0..h120 attributes"),
    selector.SelectOptionDict(value=USAGE_SOURCE_CALCULATED, label="Calculate it from my energy statistics"),
    selector.SelectOptionDict(
        value=USAGE_SOURCE_CONSUMPTION_SENSOR, label="Use a home energy consumption sensor I already have"
    ),
]


def _optional_entity_selector() -> vol.Maybe:
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
    return vol.Maybe(selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")))


def _main_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Everything except the usage-forecast source, which is its own
    branching step (see async_step_usage_sensor/async_step_usage_calculated
    below) since the calculated path needs a whole extra set of fields.
    """
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_BATTERY_SOC_ENTITY, default=defaults.get(CONF_BATTERY_SOC_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_PRICE_ENTITY, default=defaults.get(CONF_PRICE_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_SOLAR_FORECAST_ENTITIES, default=defaults.get(CONF_SOLAR_FORECAST_ENTITIES, [])
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Required(
                CONF_USAGE_SOURCE, default=defaults.get(CONF_USAGE_SOURCE, DEFAULT_USAGE_SOURCE)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=USAGE_SOURCE_OPTIONS, mode=selector.SelectSelectorMode.LIST)
            ),
            vol.Optional(
                CONF_GRID_SETPOINT_ENTITY, default=defaults.get(CONF_GRID_SETPOINT_ENTITY)
            ): _optional_entity_selector(),
            vol.Optional(
                CONF_VOLTAGE_DIFF_ENTITY, default=defaults.get(CONF_VOLTAGE_DIFF_ENTITY)
            ): _optional_entity_selector(),
            vol.Optional(
                CONF_LOW_CELL_VOLTAGE_ENTITY, default=defaults.get(CONF_LOW_CELL_VOLTAGE_ENTITY)
            ): _optional_entity_selector(),
            vol.Optional(
                CONF_HIGH_CELL_VOLTAGE_ENTITY, default=defaults.get(CONF_HIGH_CELL_VOLTAGE_ENTITY)
            ): _optional_entity_selector(),
            # Optional at the schema level (like the entity fields above) but
            # validated as conditionally required in async_step_user/
            # async_step_init - see battery_voltage_entity_required - since
            # it's only mandatory when the full-charge plan is enabled, a
            # relationship voluptuous can't express as cleanly as a
            # submit-time check.
            vol.Optional(
                CONF_BATTERY_VOLTAGE_ENTITY, default=defaults.get(CONF_BATTERY_VOLTAGE_ENTITY)
            ): _optional_entity_selector(),
            vol.Required(
                CONF_FULL_CHARGE_TARGET_VOLTAGE,
                default=defaults.get(CONF_FULL_CHARGE_TARGET_VOLTAGE, DEFAULT_FULL_CHARGE_TARGET_VOLTAGE),
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=1000, step=0.1, unit_of_measurement="V")),
            vol.Required(
                CONF_BATTERY_CAPACITY_KWH, default=defaults.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0.5, max=400, step=0.5, unit_of_measurement="kWh")),
            vol.Required(
                CONF_CHARGE_SPEED_KW, default=defaults.get(CONF_CHARGE_SPEED_KW, DEFAULT_CHARGE_SPEED_KW)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0.1, max=100, step=0.1, unit_of_measurement="kW")),
            vol.Required(
                CONF_DISCHARGE_SPEED_KW, default=defaults.get(CONF_DISCHARGE_SPEED_KW, DEFAULT_DISCHARGE_SPEED_KW)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0.1, max=100, step=0.1, unit_of_measurement="kW")),
            vol.Required(
                CONF_MAX_BATTERY_CHARGE_SPEED_KW,
                default=defaults.get(CONF_MAX_BATTERY_CHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW),
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0.1, max=200, step=0.1, unit_of_measurement="kW")),
            vol.Required(
                CONF_MAX_BATTERY_DISCHARGE_SPEED_KW,
                default=defaults.get(CONF_MAX_BATTERY_DISCHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW),
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0.1, max=200, step=0.1, unit_of_measurement="kW")),
            vol.Required(
                CONF_MIN_SOC_PERCENT, default=defaults.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%")),
            vol.Required(
                CONF_MAX_SOC_PERCENT, default=defaults.get(CONF_MAX_SOC_PERCENT, DEFAULT_MAX_SOC_PERCENT)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=50, max=150, step=1, unit_of_measurement="%")),
            vol.Required(
                CONF_ENABLE_NEGATIVE_PRICE_PLAN,
                default=defaults.get(CONF_ENABLE_NEGATIVE_PRICE_PLAN, DEFAULT_ENABLE_NEGATIVE_PRICE_PLAN),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_ENABLE_SPIKE_PLAN, default=defaults.get(CONF_ENABLE_SPIKE_PLAN, DEFAULT_ENABLE_SPIKE_PLAN)
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_ENABLE_FULL_CHARGE_PLAN,
                default=defaults.get(CONF_ENABLE_FULL_CHARGE_PLAN, DEFAULT_ENABLE_FULL_CHARGE_PLAN),
            ): selector.BooleanSelector(),
        }
    )


def _usage_sensor_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_USAGE_FORECAST_ENTITY, default=defaults.get(CONF_USAGE_FORECAST_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        }
    )


def _usage_calculated_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_GRID_IMPORT_ENTITIES, default=defaults.get(CONF_GRID_IMPORT_ENTITIES, [])
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Optional(
                CONF_GRID_EXPORT_ENTITIES, default=defaults.get(CONF_GRID_EXPORT_ENTITIES, [])
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Required(
                CONF_SOLAR_PRODUCTION_ENTITIES, default=defaults.get(CONF_SOLAR_PRODUCTION_ENTITIES, [])
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Optional(
                CONF_BATTERY_CHARGE_ENERGY_ENTITY, default=defaults.get(CONF_BATTERY_CHARGE_ENERGY_ENTITY)
            ): _optional_entity_selector(),
            vol.Optional(
                CONF_BATTERY_DISCHARGE_ENERGY_ENTITY, default=defaults.get(CONF_BATTERY_DISCHARGE_ENERGY_ENTITY)
            ): _optional_entity_selector(),
            vol.Required(
                CONF_USAGE_LOOKBACK_WEEKS, default=defaults.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=12, step=1, unit_of_measurement="weeks")),
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


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Blank optional entity-selector strings become None rather than ''."""
    data = dict(data)
    for key in (
        CONF_GRID_SETPOINT_ENTITY,
        CONF_VOLTAGE_DIFF_ENTITY,
        CONF_LOW_CELL_VOLTAGE_ENTITY,
        CONF_HIGH_CELL_VOLTAGE_ENTITY,
        CONF_BATTERY_CHARGE_ENERGY_ENTITY,
        CONF_BATTERY_DISCHARGE_ENERGY_ENTITY,
        CONF_BATTERY_VOLTAGE_ENTITY,
    ):
        if key in data and not data.get(key):
            data[key] = None
    return data


class EssManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow for one ESS Manager instance.

    Four possible steps: `user` (always), then whichever of
    `usage_sensor` / `usage_calculated` / `usage_consumption` matches what
    was picked for CONF_USAGE_SOURCE in `user` - whichever one runs is what
    actually creates the config entry.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            if not data.get(CONF_SOLAR_FORECAST_ENTITIES):
                errors["base"] = "solar_forecast_required"
            elif data.get(CONF_ENABLE_FULL_CHARGE_PLAN) and not data.get(CONF_BATTERY_VOLTAGE_ENTITY):
                # The battery-voltage confirmation leg is required alongside
                # the full-charge plan - it's a core leg of "genuinely
                # balanced" now, not an optional extra like the voltage-diff/
                # cell-voltage fields above.
                errors["base"] = "battery_voltage_entity_required"
            else:
                self._data = data
                if data[CONF_USAGE_SOURCE] == USAGE_SOURCE_CALCULATED:
                    return await self.async_step_usage_calculated()
                if data[CONF_USAGE_SOURCE] == USAGE_SOURCE_CONSUMPTION_SENSOR:
                    return await self.async_step_usage_consumption()
                return await self.async_step_usage_sensor()

        return self.async_show_form(step_id="user", data_schema=_main_schema({}), errors=errors)

    async def async_step_usage_sensor(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            data = {**self._data, **_clean(user_input)}
            return await self._async_create(data)
        return self.async_show_form(step_id="usage_sensor", data_schema=_usage_sensor_schema({}))

    async def async_step_usage_calculated(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**self._data, **_clean(user_input)}
            if not data.get(CONF_GRID_IMPORT_ENTITIES) or not data.get(CONF_SOLAR_PRODUCTION_ENTITIES):
                errors["base"] = "usage_calculated_entities_required"
            else:
                return await self._async_create(data)
        return self.async_show_form(step_id="usage_calculated", data_schema=_usage_calculated_schema({}), errors=errors)

    async def async_step_usage_consumption(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**self._data, **_clean(user_input)}
            if not data.get(CONF_USAGE_CONSUMPTION_ENTITIES):
                errors["base"] = "usage_consumption_entities_required"
            else:
                return await self._async_create(data)
        return self.async_show_form(
            step_id="usage_consumption", data_schema=_usage_consumption_schema({}), errors=errors
        )

    async def _async_create(self, data: dict[str, Any]):
        await self.async_set_unique_id(f"{DOMAIN}_{data[CONF_NAME].lower().replace(' ', '_')}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data[CONF_NAME], data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "EssManagerOptionsFlow":
        return EssManagerOptionsFlow()


class EssManagerOptionsFlow(config_entries.OptionsFlow):
    """Lets the user re-point entity references later (e.g. after renaming
    a sensor, or swapping their price/solar/usage-statistics setup) without
    deleting and recreating the whole config entry. Seed-only values
    (capacity/speeds/min/max SOC) are intentionally NOT editable here once
    their `number` entities exist - adjust those directly on the number
    entities instead, the same way you'd adjust an input_number.

    Max battery charge/discharge speed are the exception: they're a fixed
    hardware property rather than a dashboard-adjustable setpoint, so they
    have no `number` entity at all - they're editable only here, so a typo
    or a battery/inverter upgrade doesn't require deleting and re-adding the
    whole integration.

    Same branching as the initial config flow: `init` always runs first,
    then whichever of `usage_sensor` / `usage_calculated` /
    `usage_consumption` matches the chosen usage source.

    Does NOT store `config_entry` itself in `__init__` - recent Home
    Assistant core versions set `self.config_entry` automatically after
    constructing the flow, and an integration that assigns it manually
    (the pattern used by older HA templates/tutorials) crashes the options
    flow outright with an unhandled exception the frontend reports as a
    generic 500 error.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        current = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            if data.get(CONF_ENABLE_FULL_CHARGE_PLAN) and not data.get(CONF_BATTERY_VOLTAGE_ENTITY):
                errors["base"] = "battery_voltage_entity_required"
            else:
                self._data = data
                if data[CONF_USAGE_SOURCE] == USAGE_SOURCE_CALCULATED:
                    return await self.async_step_usage_calculated()
                if data[CONF_USAGE_SOURCE] == USAGE_SOURCE_CONSUMPTION_SENSOR:
                    return await self.async_step_usage_consumption()
                return await self.async_step_usage_sensor()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_BATTERY_SOC_ENTITY, default=current.get(CONF_BATTERY_SOC_ENTITY)
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_PRICE_ENTITY, default=current.get(CONF_PRICE_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_SOLAR_FORECAST_ENTITIES, default=current.get(CONF_SOLAR_FORECAST_ENTITIES, [])
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
                vol.Required(
                    CONF_USAGE_SOURCE, default=current.get(CONF_USAGE_SOURCE, DEFAULT_USAGE_SOURCE)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=USAGE_SOURCE_OPTIONS, mode=selector.SelectSelectorMode.LIST)
                ),
                vol.Optional(
                    CONF_GRID_SETPOINT_ENTITY, default=current.get(CONF_GRID_SETPOINT_ENTITY)
                ): _optional_entity_selector(),
                vol.Optional(
                    CONF_VOLTAGE_DIFF_ENTITY, default=current.get(CONF_VOLTAGE_DIFF_ENTITY)
                ): _optional_entity_selector(),
                vol.Optional(
                    CONF_LOW_CELL_VOLTAGE_ENTITY, default=current.get(CONF_LOW_CELL_VOLTAGE_ENTITY)
                ): _optional_entity_selector(),
                vol.Optional(
                    CONF_HIGH_CELL_VOLTAGE_ENTITY, default=current.get(CONF_HIGH_CELL_VOLTAGE_ENTITY)
                ): _optional_entity_selector(),
                vol.Optional(
                    CONF_BATTERY_VOLTAGE_ENTITY, default=current.get(CONF_BATTERY_VOLTAGE_ENTITY)
                ): _optional_entity_selector(),
                vol.Required(
                    CONF_MAX_BATTERY_CHARGE_SPEED_KW,
                    default=current.get(CONF_MAX_BATTERY_CHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=200, step=0.1, unit_of_measurement="kW")
                ),
                vol.Required(
                    CONF_MAX_BATTERY_DISCHARGE_SPEED_KW,
                    default=current.get(CONF_MAX_BATTERY_DISCHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=200, step=0.1, unit_of_measurement="kW")
                ),
                vol.Required(
                    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
                    default=current.get(CONF_ENABLE_NEGATIVE_PRICE_PLAN, DEFAULT_ENABLE_NEGATIVE_PRICE_PLAN),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_ENABLE_SPIKE_PLAN, default=current.get(CONF_ENABLE_SPIKE_PLAN, DEFAULT_ENABLE_SPIKE_PLAN)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_ENABLE_FULL_CHARGE_PLAN,
                    default=current.get(CONF_ENABLE_FULL_CHARGE_PLAN, DEFAULT_ENABLE_FULL_CHARGE_PLAN),
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_usage_sensor(self, user_input: dict[str, Any] | None = None):
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            data = {**self._data, **_clean(user_input)}
            return self.async_create_entry(title="", data=data)
        return self.async_show_form(step_id="usage_sensor", data_schema=_usage_sensor_schema(current))

    async def async_step_usage_calculated(self, user_input: dict[str, Any] | None = None):
        current = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**self._data, **_clean(user_input)}
            if not data.get(CONF_GRID_IMPORT_ENTITIES) or not data.get(CONF_SOLAR_PRODUCTION_ENTITIES):
                errors["base"] = "usage_calculated_entities_required"
            else:
                return self.async_create_entry(title="", data=data)
        return self.async_show_form(
            step_id="usage_calculated", data_schema=_usage_calculated_schema(current), errors=errors
        )

    async def async_step_usage_consumption(self, user_input: dict[str, Any] | None = None):
        current = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**self._data, **_clean(user_input)}
            if not data.get(CONF_USAGE_CONSUMPTION_ENTITIES):
                errors["base"] = "usage_consumption_entities_required"
            else:
                return self.async_create_entry(title="", data=data)
        return self.async_show_form(
            step_id="usage_consumption", data_schema=_usage_consumption_schema(current), errors=errors
        )
