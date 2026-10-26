"""The EV card's services (as of 2026.10.11): save or remove a charging
session; and (as of 2026.10.27, Victron charger) the plugged-in car's plan. The card passes its Status sensor as `entity_id`, which picks the
installation; with a single installation it may be left out."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SERVICE_EV_CHARGE_PLAN, SERVICE_EV_SESSION_REMOVE, SERVICE_EV_SESSION_SAVE
from .ev_charger import CHOICES, DAYS
from .ev import MODE_DEADLINE, MODE_FIXED, MODE_SOLAR

_LOGGER = logging.getLogger(__name__)

_NUMBER = vol.Any(None, vol.Coerce(float))

SAVE_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("id"): vol.Any(None, cv.string),
        vol.Optional("start"): cv.datetime,
        vol.Optional("kwh"): vol.All(vol.Coerce(float), vol.Range(min=0, max=500)),
        vol.Optional("mode"): vol.In([MODE_FIXED, MODE_SOLAR, MODE_DEADLINE]),
        vol.Optional("deadline"): vol.Any(None, cv.datetime),
        vol.Optional("current_a"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional("car"): vol.Any(None, cv.string),
        vol.Optional("start_soc"): _NUMBER,
        vol.Optional("target_soc"): _NUMBER,
        vol.Optional("enabled"): cv.boolean,
    }
)

REMOVE_SCHEMA = vol.Schema({vol.Optional("entity_id"): cv.entity_id, vol.Required("id"): cv.string})

PLAN_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("car"): vol.Any(None, cv.string),
        vol.Required("choice"): vol.In(list(CHOICES)),
        vol.Optional("day"): vol.Any(None, vol.In(list(DAYS))),
        vol.Optional("hour"): vol.Any(None, cv.string),
        vol.Optional("soc"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=100))),
        vol.Optional("kwh"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=250))),
        vol.Optional("target_soc"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=100))),
        vol.Optional("current_a"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=100))),
    }
)


def _coordinator(hass: HomeAssistant, call: ServiceCall):
    entries: dict[str, Any] = hass.data.get(DOMAIN, {})
    entity_id = call.data.get("entity_id")
    if entity_id:
        entry = er.async_get(hass).async_get(entity_id)
        if entry is None or entry.platform != DOMAIN or entry.config_entry_id not in entries:
            raise ServiceValidationError(f"{entity_id} is not an ESS Manager entity")
        return entries[entry.config_entry_id]["coordinator"]
    loaded = [v["coordinator"] for v in entries.values() if isinstance(v, dict) and "coordinator" in v]
    if len(loaded) != 1:
        raise ServiceValidationError("Pass the entity_id of the ESS Manager Status sensor")
    return loaded[0]


async def _async_after_edit(coordinator) -> None:
    coordinator.request_replan()
    await coordinator.async_persist_state()
    await coordinator.async_refresh()


def async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_EV_SESSION_SAVE):
        return

    async def _save(call: ServiceCall) -> dict[str, Any]:
        coordinator = _coordinator(hass, call)
        fields = {k: v for k, v in call.data.items() if k not in ("entity_id", "id")}
        if "start" in fields:
            fields["start"] = int(fields["start"].timestamp())
        if fields.get("deadline") is not None:
            fields["deadline"] = int(fields["deadline"].timestamp())
        try:
            session_id = coordinator.ev.save(call.data.get("id"), fields, int(coordinator.now().timestamp()))
        except KeyError as err:
            raise ServiceValidationError(f"No charging session {err}") from err
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await _async_after_edit(coordinator)
        return {"id": session_id}

    async def _remove(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        try:
            coordinator.ev.remove(call.data["id"])
        except KeyError as err:
            raise ServiceValidationError(f"No charging session {err}") from err
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await _async_after_edit(coordinator)

    hass.services.async_register(
        DOMAIN, SERVICE_EV_SESSION_SAVE, _save, schema=SAVE_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(DOMAIN, SERVICE_EV_SESSION_REMOVE, _remove, schema=REMOVE_SCHEMA)

    async def _plan(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        fields = {k: v for k, v in call.data.items() if k != "entity_id"}
        try:
            coordinator.ev.set_plan(fields, int(coordinator.now().timestamp()))
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await coordinator.async_ev_flush()
        await _async_after_edit(coordinator)

    hass.services.async_register(DOMAIN, SERVICE_EV_CHARGE_PLAN, _plan, schema=PLAN_SCHEMA)


def async_unload_services(hass: HomeAssistant) -> None:
    for service in (SERVICE_EV_SESSION_SAVE, SERVICE_EV_SESSION_REMOVE, SERVICE_EV_CHARGE_PLAN):
        hass.services.async_remove(DOMAIN, service)
