"""Config flow: lets the user pick their own battery/price/solar/usage
entities and seed values for the tunables (which then become `number`
entities - see number.py) instead of anything being hardcoded to one
person's Victron/Nordpool/Solcast setup.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CHARGE_SPEED_KW,
    CONF_DISCHARGE_SPEED_KW,
    CONF_ENABLE_FULL_CHARGE_PLAN,
    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_MAX_SOC_PERCENT,
    CONF_MIN_SOC_PERCENT,
    CONF_NAME,
    CONF_PRICE_ENTITY,
    CONF_SOLAR_FORECAST_ENTITIES,
    CONF_USAGE_FORECAST_ENTITY,
    CONF_VOLTAGE_DIFF_ENTITY,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_CHARGE_SPEED_KW,
    DEFAULT_DISCHARGE_SPEED_KW,
    DEFAULT_ENABLE_FULL_CHARGE_PLAN,
    DEFAULT_ENABLE_NEGATIVE_PRICE_PLAN,
    DEFAULT_ENABLE_SPIKE_PLAN,
    DEFAULT_MAX_SOC_PERCENT,
    DEFAULT_MIN_SOC_PERCENT,
    DEFAULT_NAME,
    DOMAIN,
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
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
                CONF_USAGE_FORECAST_ENTITY, default=defaults.get(CONF_USAGE_FORECAST_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_SOLAR_FORECAST_ENTITIES, default=defaults.get(CONF_SOLAR_FORECAST_ENTITIES, [])
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Optional(
                CONF_GRID_SETPOINT_ENTITY, default=defaults.get(CONF_GRID_SETPOINT_ENTITY, "")
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_VOLTAGE_DIFF_ENTITY, default=defaults.get(CONF_VOLTAGE_DIFF_ENTITY, "")
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
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
                CONF_MIN_SOC_PERCENT, default=defaults.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%")),
            vol.Required(
                CONF_MAX_SOC_PERCENT, default=defaults.get(CONF_MAX_SOC_PERCENT, DEFAULT_MAX_SOC_PERCENT)
            ): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=150, step=1, unit_of_measurement="%")),
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


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Blank optional entity-selector strings become None rather than ''."""
    data = dict(user_input)
    for key in (CONF_GRID_SETPOINT_ENTITY, CONF_VOLTAGE_DIFF_ENTITY):
        if not data.get(key):
            data[key] = None
    return data


class EssManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow for one ESS Manager instance."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            if not data.get(CONF_SOLAR_FORECAST_ENTITIES):
                errors["base"] = "solar_forecast_required"
            else:
                await self.async_set_unique_id(f"{DOMAIN}_{data[CONF_NAME].lower().replace(' ', '_')}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_NAME], data=data)

        return self.async_show_form(step_id="user", data_schema=_schema({}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "EssManagerOptionsFlow":
        return EssManagerOptionsFlow(config_entry)


class EssManagerOptionsFlow(config_entries.OptionsFlow):
    """Lets the user re-point entity references later (e.g. after renaming
    a sensor, or swapping their price/solar integration) without deleting
    and recreating the whole config entry. Seed-only values
    (capacity/speeds/min/max SOC) are intentionally NOT editable here once
    their `number` entities exist - adjust those directly on the number
    entities instead, the same way you'd adjust an input_number.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(title="", data=_clean(user_input))

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_BATTERY_SOC_ENTITY, default=current.get(CONF_BATTERY_SOC_ENTITY)
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_PRICE_ENTITY, default=current.get(CONF_PRICE_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_USAGE_FORECAST_ENTITY, default=current.get(CONF_USAGE_FORECAST_ENTITY)
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(
                    CONF_SOLAR_FORECAST_ENTITIES, default=current.get(CONF_SOLAR_FORECAST_ENTITIES, [])
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
                vol.Optional(
                    CONF_GRID_SETPOINT_ENTITY, default=current.get(CONF_GRID_SETPOINT_ENTITY) or ""
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    CONF_VOLTAGE_DIFF_ENTITY, default=current.get(CONF_VOLTAGE_DIFF_ENTITY) or ""
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
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
        return self.async_show_form(step_id="init", data_schema=schema)
