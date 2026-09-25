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

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

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
    CONF_FULL_CHARGE_TARGET_VOLTAGE,
    CONF_FULL_CHARGE_TRACKING_SOURCE,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_GRID_SETPOINT_SIGN,
    DEFAULT_GRID_SETPOINT_SIGN,
    CONF_HIGH_CELL_VOLTAGE_ENTITY,
    CONF_LOW_CELL_VOLTAGE_ENTITY,
    CONF_MAX_BATTERY_CHARGE_SPEED_KW,
    CONF_MAX_BATTERY_DISCHARGE_SPEED_KW,
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
    selector.SelectOptionDict(value=SIGN_CHARGE_POSITIVE, label="Positive = charge the battery, negative = discharge"),
    selector.SelectOptionDict(value=SIGN_DISCHARGE_POSITIVE, label="Positive = discharge the battery, negative = charge"),
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
        }
    )


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
      5. `plans` - the negative-price and spike plan switches, explained
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
            return await self.async_step_plans()
        return self.async_show_form(
            step_id="system", data_schema=_system_schema(self._defaults(), seed_values=self._seed_values)
        )

    async def async_step_plans(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_control()
        return self.async_show_form(step_id="plans", data_schema=_plans_schema(self._defaults()))

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
