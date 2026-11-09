"""Home Assistant tests (as of 2026.11.21 in the repo - before that they lived
outside it and were lost once). Run with pytest-homeassistant-custom-component:

    pytest -q tests/ha

The recorder isn't loaded: the statistics reads are patched to return nothing,
so the integration starts as on a fresh install."""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from typing import Any

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from homeassistant.util import dt as dt_util  # noqa: E402

import custom_components  # noqa: E402  (the test package's own, from pytest-homeassistant-custom-component)

# ESS Manager's integration next to it
_ours = os.path.join(ROOT, "custom_components")
if _ours not in list(custom_components.__path__):
    custom_components.__path__.append(_ours)

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def _recorder_first(request):
    """A test with the real recorder (recorder_mock) needs it set up before
    hass (2026.11.27)."""
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_mock")


@pytest.fixture(autouse=True)
async def amsterdam(_recorder_first, hass):
    """The house is in the Netherlands: its time zone (DST, the price day)."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    yield


@pytest.fixture(autouse=True)
def no_recorder(monkeypatch):
    """No statistics: every recorder read returns nothing."""
    from custom_components.ess_manager import coordinator as coord

    async def empty_dict(*args, **kwargs):
        return {}

    async def empty_list(*args, **kwargs):
        return []

    async def none(*args, **kwargs):
        return None

    for name in ("async_fetch_hourly_sums", "async_fetch_hourly_means", "async_fetch_5min_changes", "async_fetch_5min_soc"):
        monkeypatch.setattr(coord, name, empty_dict)
    for name in ("async_fetch_state_changes", "async_fetch_numeric_states"):
        monkeypatch.setattr(coord, name, empty_list)
    monkeypatch.setattr(coord, "async_last_recorded_state", none)
    monkeypatch.setattr(coord, "recorder_keep_days", lambda hass: 10)
    yield


def prices_today_tomorrow(now) -> dict[str, Any]:
    """A Nord Pool-like price sensor: 96 quarters today and tomorrow, cheap at night."""
    def day(offset):
        return [0.20 if (q // 4) < 6 else 0.30 for q in range(96)]
    return {"today": day(0), "tomorrow": day(1), "tomorrow_valid": True, "unit_of_measurement": "EUR/kWh"}


def solar_forecast(now) -> dict[str, Any]:
    """A Helios-like forecast: watts per quarter for 3 days, nothing (November)."""
    start = dt_util.start_of_local_day(now)
    return {"forecast": [{"datetime": (start + timedelta(minutes=15 * i)).isoformat(), "watts": 0.0}
                         for i in range(96 * 3)], "unit_of_measurement": "W"}


def base_states(hass, now) -> None:
    hass.states.async_set("sensor.soc", "60", {"unit_of_measurement": "%", "device_class": "battery"})
    hass.states.async_set("sensor.price", "0.25", prices_today_tomorrow(now))
    hass.states.async_set("sensor.helios_forecast_power_now", "0", solar_forecast(now))
    hass.states.async_set("sensor.house", "1000", {"unit_of_measurement": "kWh", "state_class": "total_increasing",
                                                   "device_class": "energy"})
    hass.states.async_set("number.gx_setpoint", "0", {"min": -10000, "max": 10000, "step": 10, "unit_of_measurement": "W"})
    hass.states.async_set("sensor.ev_energy", "500.0", {"unit_of_measurement": "kWh", "state_class": "total_increasing",
                                                        "device_class": "energy"})
    hass.states.async_set("sensor.ev_power", "0", {"unit_of_measurement": "W", "device_class": "power"})


BASE_DATA = {
    "name": "Thuis", "battery_soc_entity": "sensor.soc", "price_entity": "sensor.price",
    "solar_forecast_entities": ["sensor.helios_forecast_power_now"], "usage_source": "consumption_sensor",
    "usage_consumption_entities": ["sensor.house"], "usage_lookback_weeks": 6,
    "control_mode": "number", "control_target_entity": "number.gx_setpoint", "control_unit": "W",
    "control_sign": "charge_positive",
}


CAR = {"id": "c1", "name": "Tiguan", "capacity_kwh": 20.0, "target_soc": 80, "efficiency": 100}


def charger_device(hass, domain: str, entities: list[tuple[str, str, str, str]]) -> tuple[str, dict[str, str]]:
    """A charger's device of another integration with its entities:
    (platform, unique id, translation key or "", object id) -> (device id, {object id: entity id})."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    other = MockConfigEntry(domain=domain, title=domain)
    other.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=other.entry_id, identifiers={(domain, "dev1")}, name="charger")
    reg = er.async_get(hass)
    ids = {}
    for platform, unique_id, key, object_id in entities:
        ent = reg.async_get_or_create(platform, domain, unique_id, device_id=device.id, config_entry=other,
                                      translation_key=key or None, suggested_object_id=object_id)
        ids[object_id] = ent.entity_id
    return device.id, ids


def record_calls(hass, domain: str, service: str, calls: list, apply_state: bool = True):
    """A fake service that records its calls (and sets the entity's state, like the real one)."""
    async def handler(call):
        calls.append((domain, service, dict(call.data)))
        if not apply_state:
            return
        for entity_id in ([call.data["entity_id"]] if isinstance(call.data["entity_id"], str) else call.data["entity_id"]):
            st = hass.states.get(entity_id)
            attrs = dict(st.attributes) if st else {}
            if service == "select_option":
                hass.states.async_set(entity_id, call.data["option"], attrs)
            elif service == "set_value":
                hass.states.async_set(entity_id, str(call.data["value"]), attrs)
            elif service in ("turn_on", "turn_off"):
                hass.states.async_set(entity_id, "on" if service == "turn_on" else "off", attrs)
    hass.services.async_register(domain, service, handler)
