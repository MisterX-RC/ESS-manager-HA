"""The car charger page of the settings (the zappi as of 2026.11.21), the
diagnostics download and what survives a restart."""
import json

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ess_manager.config_flow import EssManagerOptionsFlow
from custom_components.ess_manager.diagnostics import async_get_config_entry_diagnostics

from .conftest import BASE_DATA, CAR, base_states, charger_device
from .test_ev_chargers import ZAPPI


async def _entry(hass, extra=None):
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **(extra or {})})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _ev_form(**over):
    form = {"ev_charger": "zappi", "ev_notify_services": [], "ev_energy_entity": "sensor.ev_energy",
            "ev_power_entity": "sensor.ev_power", "ev_min_current": 6, "ev_max_current": 13, "ev_phases": "1",
            "ev_predict": True}
    form.update(over)
    return form


async def _options_flow(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow = hass.config_entries.options._progress[result["flow_id"]]
    assert isinstance(flow, EssManagerOptionsFlow)
    return flow


async def test_ev_page_zappi(hass):
    base_states(hass, dt_util.now())
    entry = await _entry(hass)
    flow = await _options_flow(hass, entry)
    # no device picked
    res = await flow.async_step_ev(_ev_form())
    assert res["type"] == "form" and res["errors"] == {"base": "ev_zappi_device_required"}
    # a device without the zappi's entities (only its phase setting)
    device, _ = charger_device(hass, "myenergi", [ZAPPI[1]])
    res = await flow.async_step_ev(_ev_form(ev_zappi_device=device))
    assert res["errors"] == {"base": "ev_zappi_incomplete"}
    # the whole zappi: on to the cars
    reg = er.async_get(hass)
    other = next(e for e in hass.config_entries.async_entries("myenergi"))
    for platform, unique_id, _key, object_id in ZAPPI:
        reg.async_get_or_create(platform, "myenergi", unique_id, device_id=device, config_entry=other,
                                suggested_object_id=object_id)
    res = await flow.async_step_ev(_ev_form(ev_zappi_device=device))
    assert res["type"] == "form" and res["step_id"] == "ev_cars" and not res.get("errors")
    assert flow._data["ev_charger"] == "zappi" and flow._data["ev_zappi_device"] == device
    assert flow._data["ev_energy_entity"] == "sensor.ev_energy"      # the charger's own meter stays


async def test_diagnostics_plain_json(hass):
    base_states(hass, dt_util.now())
    entry = await _entry(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(diag)
    assert len(text) < 400_000
    assert diag["coordinator"]["last_update_success"] is True
    assert diag["floor_records"]["keys"][:3] == ["h", "run_s", "th_kwh"]
    assert "ev_charger_commands" not in diag and "thermostat_events" not in diag
    assert diag["inputs"]["sensor.soc"]["state"] == "60"


async def test_restart_keeps_sessions_and_thermostat(hass):
    now = dt_util.now()
    base_states(hass, now)
    extra = {"ev_enabled": True, "ev_cars": [CAR], "ev_energy_entity": "sensor.ev_energy",
             "ev_power_entity": "sensor.ev_power", "ev_min_current": 6, "ev_max_current": 13, "ev_phases": 1,
             "ev_predict": False}
    entry = await _entry(hass, extra)
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    start = int(now.replace(minute=0, second=0, microsecond=0).timestamp()) + 2 * 3600
    sid = coordinator.ev.save(None, {"start": start, "kwh": 9.0, "mode": "fixed", "current_a": 10, "car": "c1"},
                              int(now.timestamp()))
    coordinator.hp.add_thermostat([[1000, 1, 20.8, 21.0, None, 1]], {3600: 21.0}, {3600: 1800}, now.timestamp())
    await coordinator.async_refresh()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    again = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert again is not coordinator
    assert any(m["id"] == sid and m["kwh"] == 9.0 for m in again.ev.manual)
    assert again.hp.thermo["sp"] == {"3600": 21.0} and again.hp.thermo["on"] == {"3600": 1800}


async def test_night_limit_needs_the_battery_power(hass):
    """As of 2026.11.22 the night limit works on the battery itself: without the battery's
    power sensor the battery page doesn't go on."""
    base_states(hass, dt_util.now())
    entry = await _entry(hass)
    flow = await _options_flow(hass, entry)
    res = await flow.async_step_system({"night_limit_enabled": True})
    assert res["type"] == "form" and res["step_id"] == "system" and res["errors"] == {"base": "battery_power_required_night"}
    hass.states.async_set("sensor.bat_power", "0", {"unit_of_measurement": "W"})
    res = await flow.async_step_system({"night_limit_enabled": True, "battery_power_entity": "sensor.bat_power"})
    assert res["type"] == "form" and res["step_id"] == "night_limit"
    # without the night limit no sensor is needed
    flow2 = await _options_flow(hass, entry)
    res = await flow2.async_step_system({"night_limit_enabled": False})
    assert res["step_id"] != "system"
