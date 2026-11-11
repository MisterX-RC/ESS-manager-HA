"""The car chargers ESS Manager drives: the Victron EV charging station (its
current) and, as of 2026.11.21, a myenergi zappi (its charge mode)."""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ess_manager.diagnostics import async_get_config_entry_diagnostics

from .conftest import BASE_DATA, CAR, base_states, charger_device, record_calls

EV_DATA = {"ev_enabled": True, "ev_cars": [CAR], "ev_min_current": 6, "ev_max_current": 13, "ev_phases": 1,
           "ev_predict": False, "ev_notify_services": []}


async def _setup(hass, data):
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **EV_DATA, **data})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data["ess_manager"][entry.entry_id]["coordinator"]


# -- Victron ------------------------------------------------------------------------
VICTRON = [
    ("sensor", "v-status", "evcharger_status", "ev_status"),
    ("sensor", "v-power", "evcharger_power", "ev_v_power"),
    ("sensor", "v-energy", "evcharger_total_energy", "ev_v_energy"),
    ("select", "v-mode", "evcharger_mode", "ev_mode"),
    ("number", "v-current", "evcharger_set_current", "ev_current"),
    ("switch", "v-charge", "evcharger_charge", "ev_charge"),
]


async def test_victron_charger(hass):
    now = dt_util.now()
    base_states(hass, now)
    device, ids = charger_device(hass, "victron_gx", VICTRON)
    hass.states.async_set(ids["ev_status"], "connected")
    hass.states.async_set(ids["ev_v_power"], "0", {"unit_of_measurement": "W"})
    hass.states.async_set(ids["ev_v_energy"], "500.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set(ids["ev_mode"], "auto", {"options": ["manual", "auto", "scheduled"]})
    hass.states.async_set(ids["ev_current"], "6", {"min": 6, "max": 16})
    hass.states.async_set(ids["ev_charge"], "off")
    entry, coordinator = await _setup(hass, {"ev_charger": "victron", "ev_victron_device": device,
                                             "ev_energy_entity": ids["ev_v_energy"], "ev_power_entity": ids["ev_v_power"]})
    # (after the setup: loading ESS Manager's own platforms registers the real services)
    calls: list = []
    for d, sv in (("select", "select_option"), ("number", "set_value"), ("switch", "turn_on"), ("switch", "turn_off")):
        record_calls(hass, d, sv, calls)
    assert coordinator.ev.flow is not None                      # plugged in: a session
    assert calls == []                                          # no choice yet: nothing started
    coordinator.ev.set_plan({"choice": "asap", "soc": 40}, int(now.timestamp()))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert ("select", "select_option", {"entity_id": ids["ev_mode"], "option": "manual"}) in calls
    assert ("number", "set_value", {"entity_id": ids["ev_current"], "value": 13.0}) in calls
    assert ("switch", "turn_on", {"entity_id": ids["ev_charge"]}) in calls
    attr = coordinator.data["ev"]["charger"]
    assert attr["type"] == "victron" and not attr["blocked"]
    # calm: the min current
    calls.clear()
    coordinator.ev.set_plan({"choice": "calm"}, int(now.timestamp()))
    await coordinator.async_refresh()
    assert ("number", "set_value", {"entity_id": ids["ev_current"], "value": 6.0}) in calls
    # unplugged: back to rest (manual, off)
    calls.clear()
    hass.states.async_set(ids["ev_status"], "disconnected")
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert coordinator.ev.flow is None
    assert ("switch", "turn_off", {"entity_id": ids["ev_charge"]}) in calls


# -- zappi ---------------------------------------------------------------------------
ZAPPI = [
    ("select", "E1-20890313-charge_mode", "", "myenergi_zappi_charge_mode"),
    ("select", "E1-20890313-phase_setting_select", "", "myenergi_zappi_phase_setting"),
    ("sensor", "E1-20890313-status", "", "myenergi_zappi_status"),
    ("sensor", "E1-20890313-plug_status", "", "myenergi_zappi_plug_status"),
    ("sensor", "E1-20890313-charge_added", "", "myenergi_zappi_charge_added_session"),
    ("binary_sensor", "E1-20890313-locked", "", "myenergi_zappi_locked"),
    ("binary_sensor", "E1-20890313-charge_when_locked", "", "myenergi_zappi_charge_when_locked"),
]


async def test_zappi_charger(hass, freezer):
    now = dt_util.now()
    base_states(hass, now)
    device, ids = charger_device(hass, "myenergi", ZAPPI)
    mode, plug, status = ids["myenergi_zappi_charge_mode"], ids["myenergi_zappi_plug_status"], ids["myenergi_zappi_status"]
    hass.states.async_set(mode, "Stopped", {"options": ["Fast", "Eco", "Eco+", "Stopped"]})
    hass.states.async_set(plug, "EV Connected")
    hass.states.async_set(status, "Paused")
    hass.states.async_set(ids["myenergi_zappi_locked"], "on")
    hass.states.async_set(ids["myenergi_zappi_charge_when_locked"], "on")
    entry, coordinator = await _setup(hass, {"ev_charger": "zappi", "ev_zappi_device": device,
                                             "ev_energy_entity": "sensor.ev_energy", "ev_power_entity": "sensor.ev_power"})
    calls: list = []
    record_calls(hass, "select", "select_option", calls, apply_state=False)
    from custom_components.ess_manager.coordinator import zappi_entities

    found = zappi_entities(hass, device)
    assert found["mode"] == mode and found["plug"] == plug and found["status"] == status
    assert found["session_energy"] == ids["myenergi_zappi_charge_added_session"]
    assert coordinator.ev.flow is not None and calls == []      # plugged in, no choice: stays Stopped
    attr = coordinator.data["ev"]["charger"]
    assert attr["type"] == "zappi" and not attr["blocked"] and attr["zappi_mode"] == "Stopped"

    # now: Fast
    coordinator.ev.set_plan({"choice": "asap", "soc": 40}, int(now.timestamp()))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert calls == [("select", "select_option", {"entity_id": mode, "option": "Fast"})]
    # (2026.11.30) the zappi doesn't take it on: not again right away, but after 3 minutes
    await coordinator.async_refresh()
    assert len(calls) == 1
    freezer.tick(timedelta(seconds=200))
    await coordinator.async_refresh()
    assert len(calls) == 2 and calls[-1][2]["option"] == "Fast"
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "try 2" in diag["ev_charger_commands"][-1]["why"]
    # it shows Fast: taken on; not sent again while the plan stays the same - also after a change in the app
    hass.states.async_set(mode, "Fast", {"options": ["Fast", "Eco", "Eco+", "Stopped"]})
    await coordinator.async_refresh()
    hass.states.async_set(mode, "Eco", {"options": ["Fast", "Eco", "Eco+", "Stopped"]})
    await coordinator.async_refresh()
    freezer.tick(timedelta(seconds=400))
    await coordinator.async_refresh()
    assert len(calls) == 2
    # the meter follows after 70 s: the delay in the diagnostics
    freezer.tick(timedelta(seconds=70))
    hass.states.async_set("sensor.ev_power", "2800", {"unit_of_measurement": "W", "device_class": "power"})
    await coordinator.async_refresh()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    cmd = diag["ev_charger_commands"][-1]
    assert cmd["to"] == "Fast" and cmd["from"] == "Stopped" and cmd["power_after_w"] == 2800

    # slowly: Eco; the sun: Stopped (2026.11.31 - Eco+ chases the house battery)
    coordinator.ev.set_plan({"choice": "calm"}, int(now.timestamp()))
    await coordinator.async_refresh()
    assert calls[-1][2]["option"] == "Eco" or hass.states.get(mode).state == "Eco"
    coordinator.ev.set_plan({"choice": "solar"}, int(now.timestamp()))
    await coordinator.async_refresh()
    assert calls[-1][2]["option"] == "Stopped"

    # the car stops by itself well short of the goal: Completed -> done, "stopped early"
    hass.states.async_set(status, "Charging")
    await coordinator.async_refresh()
    hass.states.async_set("sensor.ev_energy", "501.0", {"unit_of_measurement": "kWh", "state_class": "total_increasing",
                                                         "device_class": "energy"})
    hass.states.async_set(status, "Completed")
    await coordinator.async_refresh()
    assert coordinator.ev.flow["done"] and coordinator.data["ev"]["charger"]["session"]["stopped_early"] is not None

    # locked without "charge when locked": blocked, on the card
    hass.states.async_set(ids["myenergi_zappi_charge_when_locked"], "off")
    await coordinator.async_refresh()
    assert coordinator.data["ev"]["charger"]["blocked"]

    # unplugged: back to Stopped, once
    calls.clear()
    hass.states.async_set(plug, "EV Disconnected")
    hass.states.async_set(status, "Paused")
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert coordinator.ev.flow is None
    assert calls == [("select", "select_option", {"entity_id": mode, "option": "Stopped"})]
    await coordinator.async_refresh()
    assert len(calls) == 1
    hass.states.async_set(mode, "Stopped", {"options": ["Fast", "Eco", "Eco+", "Stopped"]})
    freezer.tick(timedelta(seconds=400))
    await coordinator.async_refresh()
    assert len(calls) == 1 and not coordinator.ev.rest_charger


async def test_zappi_gives_up_after_a_few_tries(hass, freezer):
    """(2026.11.30) a zappi that never takes a mode on: sent 4 times, then a warning and left alone."""
    now = dt_util.now()
    base_states(hass, now)
    device, ids = charger_device(hass, "myenergi", ZAPPI)
    mode = ids["myenergi_zappi_charge_mode"]
    hass.states.async_set(mode, "Stopped", {"options": ["Fast", "Eco", "Eco+", "Stopped"]})
    hass.states.async_set(ids["myenergi_zappi_plug_status"], "EV Connected")
    hass.states.async_set(ids["myenergi_zappi_status"], "Paused")
    entry, coordinator = await _setup(hass, {"ev_charger": "zappi", "ev_zappi_device": device,
                                             "ev_energy_entity": "sensor.ev_energy", "ev_power_entity": "sensor.ev_power"})
    calls: list = []
    record_calls(hass, "select", "select_option", calls, apply_state=False)
    coordinator.ev.set_plan({"choice": "asap", "soc": 40}, int(now.timestamp()))
    for _ in range(8):
        await coordinator.async_refresh()
        freezer.tick(timedelta(seconds=200))
    assert len(calls) == 4
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "didn't take on Fast" in (coordinator._ev_error or "")


async def test_victron_grid_window_keeps_the_battery_out(hass, freezer):
    """A "full by" grid window: the car's power goes on top of the grid setpoint
    (as of 2026.10.27), so the house battery doesn't feed the car."""
    from datetime import datetime

    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 14, 1, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    q = (now.hour * 60 + now.minute) // 15
    today = [0.40] * 96
    for i in range(q, q + 8):
        today[i] = 0.10                     # the next two hours cheap
    hass.states.async_set("sensor.price", "0.10", {"today": today, "tomorrow": [0.40] * 96, "tomorrow_valid": True,
                                                  "unit_of_measurement": "EUR/kWh"})
    device, ids = charger_device(hass, "victron_gx", VICTRON)
    hass.states.async_set(ids["ev_status"], "connected")
    hass.states.async_set(ids["ev_v_power"], "0", {"unit_of_measurement": "W"})
    hass.states.async_set(ids["ev_v_energy"], "500.0", {"unit_of_measurement": "kWh"})
    hass.states.async_set(ids["ev_mode"], "auto", {"options": ["manual", "auto", "scheduled"]})
    hass.states.async_set(ids["ev_current"], "6", {"min": 6, "max": 16})
    hass.states.async_set(ids["ev_charge"], "off")
    entry, coordinator = await _setup(hass, {"ev_charger": "victron", "ev_victron_device": device,
                                             "ev_energy_entity": ids["ev_v_energy"], "ev_power_entity": ids["ev_v_power"]})
    calls: list = []
    for d, sv in (("select", "select_option"), ("number", "set_value"), ("switch", "turn_on"), ("switch", "turn_off")):
        record_calls(hass, d, sv, calls)
    # full by 20:00, 4 kWh (60 -> 80 % of 20 kWh): the cheap quarters now
    coordinator.ev.set_plan({"choice": "deadline", "day": "today", "hour": "20:00", "soc": 60}, int(now.timestamp()))
    await coordinator.async_refresh()
    flow = coordinator.ev.flow
    assert flow["windows"] and flow["windows"][0][0] <= now.timestamp() < flow["windows"][0][1]
    assert ("switch", "turn_on", {"entity_id": ids["ev_charge"]}) in calls
    hass.states.async_set(ids["ev_v_power"], "3000", {"unit_of_measurement": "W"})
    await coordinator.async_refresh()
    assert coordinator._ev_offset_w == 3000.0
