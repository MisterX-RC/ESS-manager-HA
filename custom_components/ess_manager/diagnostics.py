"""Diagnostics download (as of 2026.10.22): Settings > Devices & services >
ESS Manager > (three dots) > Download diagnostics.

One JSON file with everything needed to see why the integration does what
it does, instead of copying YAML out of Developer tools:
- the version, the Configure settings, the number entities and switches;
- every configured entity as the integration sees it (state, unit,
  availability; long attributes summarised - the price lists in full, a
  solar forecast sensor as the hourly kWh the integration reads from it);
- the coordinator's last result (forecasts, plans, control, heat pump, EV);
- the decision history: the moments of the last 24 hours the action,
  setpoint, status or control error changed.

ESS Manager stores no passwords or tokens, so nothing is redacted; the file
does contain the household's energy data and entity names. Home Assistant
only hands it to whoever clicks the button.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, valid_entity_id
from homeassistant.loader import async_get_integration

from . import forecasting
from .const import CONF_PRICE_ENTITY, CONF_SOLAR_FORECAST_ENTITIES, DOMAIN

# A list attribute longer than this is summarised (length, first and last
# items) instead of copied whole.
LIST_KEEP = 12


def _jsonable(value: Any) -> Any:
    """Make `value` safe for the diagnostics JSON."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _summarise(value: Any) -> Any:
    """A long list as its length plus the first and last items."""
    if isinstance(value, (list, tuple)) and len(value) > LIST_KEEP:
        return {
            "list_length": len(value),
            "first": _jsonable(list(value[:3])),
            "last": _jsonable(value[-1]),
        }
    return _jsonable(value)


def _entity_ids(value: Any) -> list[str]:
    """Every entity id in a Configure value (strings, lists, nested dicts)."""
    found: list[str] = []
    if isinstance(value, str):
        if value[:1].isalpha() and valid_entity_id(value):
            found.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            found.extend(_entity_ids(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            found.extend(_entity_ids(v))
    return found


def _entity_snapshot(hass: HomeAssistant, entity_id: str, conf: dict[str, Any]) -> dict[str, Any]:
    state = hass.states.get(entity_id)
    if state is None:
        return {"missing": True}
    attrs = dict(state.attributes)
    out: dict[str, Any] = {
        "state": state.state,
        "available": state.state not in ("unavailable", "unknown"),
        "unit": attrs.get("unit_of_measurement"),
        "device_class": attrs.get("device_class"),
        "last_updated": state.last_updated.isoformat(),
    }
    if entity_id == conf.get(CONF_PRICE_ENTITY):
        # the price lists are what the planning runs on - whole
        out["today"] = _jsonable(attrs.pop("today", None))
        out["tomorrow"] = _jsonable(attrs.pop("tomorrow", None))
    if entity_id in (conf.get(CONF_SOLAR_FORECAST_ENTITIES) or []):
        points = forecasting.solar_points_from_attributes(attrs)
        out["solar_format"] = (
            "solcast" if attrs.get("detailedHourly") else "helios" if points else "not recognised"
        )
        out["solar_hourly_kwh"] = _jsonable(points)
    skip = {"unit_of_measurement", "device_class"}
    out["attributes"] = {k: _summarise(v) for k, v in attrs.items() if k not in skip}
    return out


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    integration = await async_get_integration(hass, DOMAIN)
    conf = {**entry.data, **entry.options}
    result: dict[str, Any] = {
        "integration": {"version": str(integration.version), "home_assistant": HA_VERSION},
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "state": str(entry.state),
            "data": _jsonable(dict(entry.data)),
            "options": _jsonable(dict(entry.options)),
        },
    }

    ids: list[str] = []
    for value in conf.values():
        for entity_id in _entity_ids(value):
            if entity_id not in ids:
                ids.append(entity_id)
    result["inputs"] = {entity_id: _entity_snapshot(hass, entity_id, conf) for entity_id in ids}

    stored = (hass.data.get(DOMAIN) or {}).get(entry.entry_id) or {}
    coordinator = stored.get("coordinator") if isinstance(stored, dict) else None
    if coordinator is None:
        result["coordinator"] = None
        return result

    result["coordinator"] = {
        "last_update_success": coordinator.last_update_success,
        "last_exception": repr(coordinator.last_exception) if coordinator.last_exception else None,
        "update_interval_seconds": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
    }
    result["numbers"] = {
        key: _jsonable(getattr(entity, "native_value", None)) for key, entity in sorted(coordinator._numbers.items())
    }
    result["switches"] = {
        "automatic_control": coordinator.controller.enabled,
        "heat_pump_steering": getattr(coordinator, "hp_steering_on", None),
    }
    result["decisions_24h"] = _jsonable(coordinator.decision_history())
    result["data"] = _jsonable(coordinator.data)
    return result
