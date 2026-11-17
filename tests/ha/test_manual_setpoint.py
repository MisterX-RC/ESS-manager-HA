"""The grid setpoint by hand on the status card (as of 2026.11.53): only while
Automatic control is off, converted to the entity's own unit, sign and step,
within +/- 20 kW and the entity's own range; the slider's range and quick
picks in the Status sensor's `control.manual`."""
import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states, record_calls


async def _setup(hass, data=None):
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **(data or {})})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data["ess_manager"][entry.entry_id]["coordinator"]


async def _auto_switch(hass, entry):
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_platform import async_get_platforms

    eid = er.async_get(hass).async_get_entity_id("switch", "ess_manager", f"{entry.entry_id}_automatic_control")
    for platform in async_get_platforms(hass, "ess_manager"):
        if platform.domain == "switch" and eid in platform.entities:
            return platform.entities[eid]
    raise AssertionError("no Automatic control switch")


async def test_manual_setpoint_w(hass):
    base_states(hass, dt_util.now())
    entry, co = await _setup(hass, {"max_battery_charge_speed_kw": 5.0, "max_battery_discharge_speed_kw": 6.0})
    manual = co.data["control"]["manual"]
    # the entity's own range (+/- 10000 W) caps +/- 20 kW; steps of at least 100 W; quick picks at 80 %
    assert manual["min_kw"] == -10.0 and manual["max_kw"] == 10.0 and manual["step_kw"] == 0.1
    assert manual["quick_kw"] == [-10.0, -4.8, 4.0, 10.0]
    # while Automatic control is on: refused
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("ess_manager", "manual_setpoint", {"power_kw": 3}, blocking=True)
    calls: list = []
    record_calls(hass, "number", "set_value", calls)
    switch = await _auto_switch(hass, entry)
    await switch.async_turn_off()
    calls.clear()                                          # the switch itself sends idle once
    await hass.services.async_call("ess_manager", "manual_setpoint", {"power_kw": 3.456}, blocking=True)
    assert calls == [("number", "set_value", {"entity_id": "number.gx_setpoint", "value": 3460.0})]   # on the 10 W step
    await hass.services.async_call("ess_manager", "manual_setpoint", {"power_kw": -20}, blocking=True)
    assert calls[-1][2]["value"] == -10000.0                # the entity's own minimum
    await hass.services.async_call("ess_manager", "manual_setpoint", {"idle": True}, blocking=True)
    assert calls[-1][2]["value"] == 0.0
    # a cycle while it's off sends nothing (the value set by hand stays)
    n = len(calls)
    hass.states.async_set("number.gx_setpoint", "1500", {"min": -10000, "max": 10000, "step": 10, "unit_of_measurement": "W"})
    await co.async_refresh()
    assert len(calls) == n
    decisions = co.decision_history()
    assert any(d.get("action") == "manual" and d.get("value") == 3460.0 for d in decisions)


async def test_manual_setpoint_kw_discharge_positive(hass):
    base_states(hass, dt_util.now())
    hass.states.async_set("input_number.setpoint", "0", {"min": -20, "max": 20, "step": 1, "unit_of_measurement": "kW"})
    entry, co = await _setup(hass, {"control_target_entity": "input_number.setpoint", "control_unit": "kW",
                                    "control_sign": "discharge_positive", "control_idle_value": 0})
    manual = co.data["control"]["manual"]
    assert manual["min_kw"] == -20.0 and manual["max_kw"] == 20.0 and manual["step_kw"] == 1.0
    calls: list = []
    record_calls(hass, "input_number", "set_value", calls)
    record_calls(hass, "number", "set_value", calls)
    switch = await _auto_switch(hass, entry)
    await switch.async_turn_off()
    calls.clear()
    await hass.services.async_call("ess_manager", "manual_setpoint", {"power_kw": 5.6}, blocking=True)
    # + = charge in, flipped for "positive = discharge", on the 1 kW step
    assert calls == [("input_number", "set_value", {"entity_id": "input_number.setpoint", "value": -6.0})]


async def test_no_manual_without_setpoint_entity(hass):
    base_states(hass, dt_util.now())
    entry, co = await _setup(hass, {"control_mode": "off", "control_target_entity": None})
    assert co.data["control"]["manual"] is None
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("ess_manager", "manual_setpoint", {"power_kw": 1}, blocking=True)
