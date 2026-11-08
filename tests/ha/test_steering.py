"""Heat pump steering (step 2, as of 2026.10.17): the thermostat follows the
day/night temperatures; a change by hand wins until the next switch; off
puts it back once. And number settings restored before the first plan."""
from datetime import datetime, timedelta

from homeassistant.core import State, SupportsResponse
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache_with_extra_data

from .conftest import BASE_DATA, base_states
from .test_heatpump import HP_DATA


def _weather(hass, now):
    async def forecasts(call):
        base = dt_util.start_of_local_day(now)
        if call.data["type"] == "daily":
            return {"weather.home": {"forecast": [{"datetime": (base + timedelta(days=k, hours=12)).isoformat(),
                                                   "temperature": 6.0, "templow": 2.0} for k in range(6)]}}
        return {"weather.home": {"forecast": []}}

    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)


async def test_steering_day_night_override_and_off(hass, freezer):
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 10, 2, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    for eid, val in (("sensor.qube_heat", "100"), ("sensor.outdoor", "5"), ("sensor.indoor", "20.4")):
        hass.states.async_set(eid, val, {"unit_of_measurement": "kWh" if "heat" in eid else "°C"})
    hass.states.async_set("climate.house", "heat", {"hvac_action": "idle", "temperature": 19.0, "current_temperature": 20.4,
                                                     "target_temp_step": 0.5})
    _weather(hass, now)
    calls = []

    async def set_temperature(call):
        calls.append(call.data["temperature"])
        st = hass.states.get("climate.house")
        hass.states.async_set("climate.house", st.state, {**st.attributes, "temperature": call.data["temperature"]})

    hass.services.async_register("climate", "set_temperature", set_temperature)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis",
                            data={**BASE_DATA, **HP_DATA, "hp_buffer_enabled": True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert calls == []                                       # steering switch still off
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.thuis_heat_pump_steering"}, blocking=True)
    await coordinator.async_refresh()
    assert calls == [20.5]                                   # the day temperature (default 20.5 from 07:00)
    # changed by hand: left alone until the night switch (22:00)
    hass.states.async_set("climate.house", "heat", {**hass.states.get("climate.house").attributes, "temperature": 21.5})
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    freezer.tick(timedelta(hours=2))
    await coordinator.async_refresh()
    assert calls == [20.5] and coordinator.hp.steer.get("override_until")
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 22, 3, tzinfo=tz)))
    await coordinator.async_refresh()
    assert calls[-1] == 19.0                                 # the night temperature
    # off: once back to the plain schedule (it's there already), then left alone
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.thuis_heat_pump_steering"}, blocking=True)
    await coordinator.async_refresh()
    n = len(calls)
    hass.states.async_set("climate.house", "heat", {**hass.states.get("climate.house").attributes, "temperature": 23.0})
    await coordinator.async_refresh()
    assert len(calls) == n and coordinator.hp.steer == {}


async def test_numbers_restored_before_the_first_plan(hass):
    """A changed setting (here the minimum SOC) is back after a restart before the first
    cycle plans - not its default for the first minute (as of 2026.10.14)."""
    mock_restore_cache_with_extra_data(hass, [(
        State("number.thuis_minimum_soc_solar_deficit", "42.0"),
        {"native_value": 42.0, "native_min_value": 0, "native_max_value": 100, "native_step": 1,
         "native_unit_of_measurement": "%"},
    )])
    base_states(hass, dt_util.now())
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data=dict(BASE_DATA))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert hass.states.get("number.thuis_minimum_soc_solar_deficit").state == "42.0"
    assert coordinator.data["low_threshold_kwh"] is not None
    # the first plan already used it: the low threshold is at least 42 % of 30 kWh
    assert coordinator.data["low_threshold_kwh"] >= 30.0 * 0.42 - 0.01
