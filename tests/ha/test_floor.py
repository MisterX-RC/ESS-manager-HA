"""Floor control with a Qube (as of 2026.11.13): the heat pump's status and
three-way valve from its device decide which minutes count for the floor."""
from datetime import datetime, timedelta

from homeassistant.core import SupportsResponse
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states, charger_device
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
