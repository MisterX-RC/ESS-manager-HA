"""Floor control with a Qube (as of 2026.11.13): the heat pump's status and
three-way valve from its device decide which minutes count for the floor."""
from datetime import datetime, timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import SupportsResponse
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states, charger_device, record_calls
from .test_heatpump import HP_DATA

FLOOR_DATA = {
    "floor_enabled": True, "floor_return_setpoint_entity": "number.qube_return_sp", "floor_demand_entity": "switch.qube_demand",
    "floor_thermostat_helper_entity": "input_boolean.thermostat_demand", "floor_supply_entity": "sensor.qube_supply",
    "floor_return_entity": "sensor.qube_return", "floor_pump_entity": "sensor.qube_pump",
    "floor_thermal_power_entity": "sensor.qube_power",
}


async def test_qube_status_counts_heating_and_hot_water(hass, freezer):
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 10, 0, 30, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    for eid, val, unit in (("sensor.qube_heat", "100", "kWh"), ("sensor.outdoor", "5", "°C"), ("sensor.indoor", "20.9", "°C"),
                           ("sensor.qube_supply", "31", "°C"), ("sensor.qube_return", "27", "°C"), ("sensor.qube_pump", "80", "%"),
                           ("sensor.qube_power", "4000", "W"), ("number.qube_return_sp", "28", "°C")):
        hass.states.async_set(eid, val, {"unit_of_measurement": unit})
    hass.states.async_set("switch.qube_demand", "on")
    hass.states.async_set("input_boolean.thermostat_demand", "on")
    hass.states.async_set("climate.house", "heat", {"hvac_action": "heating", "temperature": 21.0, "current_temperature": 20.9})
    device, ids = charger_device(hass, "qube_heatpump", [
        ("sensor", "q-status", "status_heatpump", "qube_status"),
        ("sensor", "q-valve", "threeway_valve_status", "qube_valve"),
    ])
    hass.states.async_set(ids["qube_status"], "heating")
    hass.states.async_set(ids["qube_valve"], "ch")

    async def forecasts(call):
        base = dt_util.start_of_local_day(now)
        if call.data["type"] == "daily":
            return {"weather.home": {"forecast": [{"datetime": (base + timedelta(days=k, hours=12)).isoformat(),
                                                   "temperature": 6.0, "templow": 2.0} for k in range(6)]}}
        return {"weather.home": {"forecast": []}}

    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis",
                            data={**BASE_DATA, **HP_DATA, **FLOOR_DATA, "floor_qube_device": device})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert coordinator.floor_configured()

    # 10:00-11:00 heating the floor, then hot water from 11:00
    for minute in range(1, 80):
        freezer.tick(timedelta(minutes=1))
        if minute == 60:
            hass.states.async_set(ids["qube_status"], "heating_dhw")
            hass.states.async_set(ids["qube_valve"], "dhw")
        await coordinator.async_refresh()
    h10 = int(datetime(2026, 11, 9, 10, tzinfo=tz).timestamp())
    rec = next(r for r in coordinator.floor.records if r["h"] == h10)
    assert rec["heat_s"] >= 3300 and not rec.get("dhw_s")
    acc = coordinator.floor.acc
    assert acc["h"] == h10 + 3600 and acc.get("dhw_s", 0) >= 15 * 60 and not acc.get("heat_s")
    floor_attr = coordinator.data["heat_pump"]["floor"]
    assert floor_attr["stage"] == "watch"


# --- 2026.11.33 -------------------------------------------------------------------------------------------
# A's floor model (diagnostics 12 Nov); the house model's heat plan fixed: 3.26 kW -> return setpoint 26.5
A_MODEL = {"u": 0.4332, "delta": 3.86, "p_min": 3.26, "p_max": 4.18, "n": 31, "err": 0.087, "ok": True, "slab": False}


async def _floor_a(hass, freezer, ret="27.4"):
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 11, 6, 0, 30, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    for eid, val, unit in (("sensor.qube_heat", "100", "kWh"), ("sensor.outdoor", "2", "°C"), ("sensor.indoor", "20.8", "°C"),
                           ("sensor.qube_supply", "31", "°C"), ("sensor.qube_return", ret, "°C"), ("sensor.qube_pump", "80", "%"),
                           ("sensor.qube_power", "3700", "W")):
        hass.states.async_set(eid, val, {"unit_of_measurement": unit})
    hass.states.async_set("number.qube_return_sp", "27.5", {"unit_of_measurement": "°C", "min": 20.0, "max": 65.0, "step": 0.5})
    hass.states.async_set("switch.qube_demand", "on")
    hass.states.async_set("input_boolean.thermostat_demand", "on")
    hass.states.async_set("climate.house", "heat", {"hvac_action": "heating", "temperature": 21.0, "current_temperature": 20.8})

    async def forecasts(call):
        return {"weather.home": {"forecast": []}}

    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **HP_DATA, **FLOOR_DATA})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    calls = []
    record_calls(hass, "number", "set_value", calls)
    co = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    co.floor.refit = lambda now_ts: None
    co.floor.model = dict(A_MODEL)
    co.hp.plan_heat = lambda *a, **k: {"temps": [20.8] * 25, "q_el": [1.0] * 24, "q_th": [3.26] * 24}
    co.floor_mode = "full"
    return co, calls


async def test_floor_response_kept_over_a_missing_input_and_a_restart(hass, freezer):
    """A, 11 Nov: one cycle with a Qube sensor not there (after the restart for
    the update) started the response check over - the running hours were lost."""
    co, _ = await _floor_a(hass, freezer)
    for _ in range(3 * 60 + 5):
        freezer.tick(timedelta(minutes=1))
        await co.async_refresh()
    since = co.floor.setpoint_since
    n = co.data["heat_pump"]["floor"]["response"]["n"]
    assert co.floor.stage == "setpoint" and since and n >= 2

    # an input missing for one cycle: handed back for that minute, the count stays
    hass.states.async_set("sensor.qube_supply", "unavailable")
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    assert co.floor.stage == "watch" and co.data["heat_pump"]["floor"]["waiting"] == ["inputs"]
    hass.states.async_set("sensor.qube_supply", "31", {"unit_of_measurement": "°C"})
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    assert co.floor.stage == "setpoint" and co.floor.setpoint_since == since
    assert co.data["heat_pump"]["floor"]["response"]["n"] == n

    # a restart: stopped (handed back), restored from the store, the first cycle without the Qube's sensor
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert co.floor.stage == "watch"
    stored = co.floor.as_store()
    co.floor.restore(stored)
    hass.states.async_set("sensor.qube_supply", "unavailable")
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    hass.states.async_set("sensor.qube_supply", "31", {"unit_of_measurement": "°C"})
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    assert co.floor.stage == "setpoint" and co.floor.setpoint_since == since
    assert co.data["heat_pump"]["floor"]["response"]["n"] == n

    # floor control set to watch by hand: then it starts over
    co.floor_mode = "watch"
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    assert co.floor.setpoint_since is None
    co.floor_mode = "full"
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    assert co.floor.setpoint_since > since and co.data["heat_pump"]["floor"]["response"]["n"] == 0


async def test_floor_return_setpoint_down_in_steps_while_running(hass, freezer):
    """Timo (12 Nov): down one step at a time while the compressor runs, the
    next once the return is within 0.1 of the setpoint; off: straight to it."""
    co, calls = await _floor_a(hass, freezer, ret="27.4")
    await co.async_refresh()
    now = co.data["heat_pump"]["floor"]["now"]
    assert now["sp_goal"] == 26.5 and now["compressor_running"] is True
    assert calls[-1][2]["value"] == 27.0                       # 27.5 -> 27.0, not straight to 26.5
    # 10 min later the return still at 27.4 (above 27.0 + 0.1): stays
    for _ in range(10):
        freezer.tick(timedelta(minutes=1))
        await co.async_refresh()
    assert hass.states.get("number.qube_return_sp").state == "27.0" and len(calls) == 1
    # the return down to 27.1: the next step, once 5 minutes after the last write
    hass.states.async_set("sensor.qube_return", "27.1", {"unit_of_measurement": "°C"})
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    assert calls[-1][2]["value"] == 26.5 and len(calls) == 2

    # compressor off (no heat): straight from 28.0 to 26.5
    hass.states.async_set("number.qube_return_sp", "28.0", {"unit_of_measurement": "°C", "min": 20.0, "max": 65.0, "step": 0.5})
    hass.states.async_set("sensor.qube_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.qube_return", "27.8", {"unit_of_measurement": "°C"})
    freezer.tick(timedelta(minutes=6))
    await co.async_refresh()
    assert co.data["heat_pump"]["floor"]["now"]["compressor_running"] is False
    assert calls[-1][2]["value"] == 26.5


async def test_floor_full_hours_kept_for_the_house_model(hass, freezer, monkeypatch):
    """2026.11.35: the hours ESS Manager switches the heat demand itself (full)
    are kept per hour - the house model's self-check plays them as ESS
    Manager plans them, not with the learned thermostat."""
    from custom_components.ess_manager import floor_control

    co, _ = await _floor_a(hass, freezer)
    switch_calls = []
    record_calls(hass, "switch", "turn_on", switch_calls)
    record_calls(hass, "switch", "turn_off", switch_calls)
    monkeypatch.setattr(floor_control, "effective_stage", lambda *a, **k: ("full", []))
    for _ in range(30):
        freezer.tick(timedelta(minutes=1))
        await co.async_refresh()
    assert co.floor.stage == "full" and co.hp.ess_switches
    ess = co.hp.thermostat_series("ess")
    assert 25 * 60 <= sum(ess.values()) <= 30 * 60
    # stored with the heat pump's data
    assert co.hp.as_store()["thermo"]["ess"]

    # back to the thermostat: nothing counted any more
    co.floor_mode = "setpoint"
    monkeypatch.setattr(floor_control, "effective_stage", lambda *a, **k: ("setpoint", []))
    before = sum(co.hp.thermostat_series("ess").values())
    for _ in range(10):
        freezer.tick(timedelta(minutes=1))
        await co.async_refresh()
    assert not co.hp.ess_switches and sum(co.hp.thermostat_series("ess").values()) == before


async def test_floor_minimum_floor_temperature(hass, freezer):
    """The minimum floor temperature (2026.11.45): the return setpoint never asks
    for less than keeps the mean water there, and the card gets the setting and
    the temperature above which the house would get too warm."""
    co, calls = await _floor_a(hass, freezer)
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    mf = co.data["heat_pump"]["floor"]["min_floor"]
    assert mf["entity"] and mf["t_c"] is None and mf["sp_min"] is None and not mf["active"]
    sp_off = co.data["heat_pump"]["floor"]["now"]["sp_planned"]

    await co._numbers["floor_min_temperature"].async_set_native_value(32.0)
    # an hourly forecast at 5 degC, for the limit
    t0 = dt_util.now().replace(minute=0, second=0, microsecond=0)
    co._hp_hourly = [{"datetime": (t0 + timedelta(hours=i)).isoformat(), "temperature": 5.0, "wind_speed": 0.0}
                     for i in range(48)]
    # a house model in the hour-by-hour sense, for the limit
    co.hp.house = {**(co.hp.house or {}), "model": {"a": 0.0, "k": 0.004, "g": 0.06, "kw": None, "ks": 0.0, "kg": 0.0,
                                                     "tau": 2.0, "qmax": 4.0, "thermal": True}}
    freezer.tick(timedelta(minutes=6))
    await co.async_refresh()
    fl = co.data["heat_pump"]["floor"]
    mf = fl["min_floor"]
    # 32 - delta/2 (3.86 / 2) = 30.07, rounded up to the 0.5 step
    assert mf["t_c"] == 32.0 and mf["active"] and mf["sp_min"] == 30.5
    assert sp_off < 30.5 and fl["now"]["sp_planned"] == 30.5
    assert any(c[2].get("entity_id") == "number.qube_return_sp" and c[2].get("value") == 30.5 for c in calls)
    assert all(n["sp"] is None or n["sp"] >= 30.5 for n in fl["next"])
    # 21 + 0.004 x 16 / 0.06 / 0.4332 = 23.5 (no sun in the test): 32 is far too warm
    assert mf["target_c"] == 21.0 and mf["limit_c"] is not None and 23.0 <= mf["limit_c"] <= 24.0 and mf["too_warm"]
