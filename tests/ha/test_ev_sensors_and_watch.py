"""A charger without control (energy and power sensors only): while the house
battery charges from the grid, the car's power goes on top of the grid
setpoint (as of 2026.10.40). And a battery level that stops updating is
noticed (as of 2026.10.44)."""
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, CAR, base_states


async def _cheap_low(hass, freezer):
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 14, 1, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    q = (now.hour * 60 + now.minute) // 15
    today = [0.40] * 96
    for i in range(q, q + 8):
        today[i] = 0.05
    hass.states.async_set("sensor.price", "0.05", {"today": today, "tomorrow": [0.40] * 96, "tomorrow_valid": True,
                                                  "unit_of_measurement": "EUR/kWh"})
    hass.states.async_set("sensor.soc", "20", {"unit_of_measurement": "%", "device_class": "battery"})


async def test_sensors_charger_car_on_top_of_a_grid_charge(hass, freezer):
    await _cheap_low(hass, freezer)
    hass.states.async_set("sensor.ev_power", "2800", {"unit_of_measurement": "W", "device_class": "power"})
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={
        **BASE_DATA, "min_soc_percent": 50.0, "ev_enabled": True, "ev_charger": "sensors", "ev_cars": [CAR],
        "ev_energy_entity": "sensor.ev_energy", "ev_power_entity": "sensor.ev_power", "ev_min_current": 6,
        "ev_max_current": 16, "ev_phases": 3, "ev_predict": False})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    await coordinator.async_refresh()
    assert coordinator.data["control_action"] in ("charge", "negative_price_charge")
    assert coordinator._ev_offset_w == 2800.0
    # the car stops: no offset
    hass.states.async_set("sensor.ev_power", "0", {"unit_of_measurement": "W", "device_class": "power"})
    await coordinator.async_refresh()
    assert coordinator._ev_offset_w == 0.0


async def test_frozen_battery_level_is_noticed(hass, freezer):
    from homeassistant.helpers import issue_registry as ir

    await _cheap_low(hass, freezer)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data=dict(BASE_DATA))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    issue = f"sensor_frozen_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue("ess_manager", issue) is None
    # it reports regularly (the same value again: reported later than changed) ...
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set("sensor.soc", "20", {"unit_of_measurement": "%", "device_class": "battery"})
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue("ess_manager", issue) is None
    # ... and then stops
    for _ in range(12):                     # 12 minutes without a new SOC report
        freezer.tick(timedelta(minutes=1))
        await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue("ess_manager", issue) is not None
    hass.states.async_set("sensor.soc", "21", {"unit_of_measurement": "%", "device_class": "battery"})
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue("ess_manager", issue) is None
