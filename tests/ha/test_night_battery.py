"""The night limit on the battery (as of 2026.11.22): with the battery's power
measured, 22:00-07:00 the setpoint follows it so the battery charges and gives
at most the night speeds - more comes from the grid, like the house from the grid."""
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states

NIGHT = {"night_limit_enabled": True, "night_charge_speed_kw": 1.5, "night_discharge_speed_kw": 1.5,
         "battery_power_entity": "sensor.bat_power", "battery_power_sign": "charge_positive"}


def _bat(hass, w):
    hass.states.async_set("sensor.bat_power", str(w), {"unit_of_measurement": "W", "device_class": "power"})


async def _entry(hass, extra):
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **NIGHT, **extra})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data["ess_manager"][entry.entry_id]["coordinator"]


async def test_night_charge_holds_the_battery_at_the_night_speed(hass, freezer):
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 2, 1, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    q = (now.hour * 60 + now.minute) // 15
    today = [0.40] * 96
    for i in range(q, q + 12):
        today[i] = 0.05
    hass.states.async_set("sensor.price", "0.05", {"today": today, "tomorrow": [0.40] * 96, "tomorrow_valid": True,
                                                  "unit_of_measurement": "EUR/kWh"})
    hass.states.async_set("sensor.soc", "20", {"unit_of_measurement": "%", "device_class": "battery"})
    _bat(hass, 700)                          # the setpoint gave 1.5 kW, the house took 0.8: the battery got 0.7
    entry, coordinator = await _entry(hass, {"min_soc_percent": 50.0})
    first = coordinator.decision_history()[-1]
    assert first["action"] in ("charge", "negative_price_charge") and first["power_kw"] > 1.5   # more from the grid
    # the battery at 1.5 kW: the setpoint stays where it is
    _bat(hass, 1500)
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    held = coordinator.decision_history()[-1]["power_kw"]
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    assert coordinator.data["control_power_kw"] == held
    # the fast loop between the cycles follows it too (the house drops: the battery would get 2.0 kW)
    _bat(hass, 2000)
    freezer.tick(timedelta(seconds=20))
    await coordinator.async_fast_control()
    assert coordinator._night_loop["kw"] < held


async def test_night_idle_takes_the_peak_from_the_grid(hass, freezer):
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 23, 1, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_set("sensor.soc", "80", {"unit_of_measurement": "%", "device_class": "battery"})
    _bat(hass, -300)
    entry, coordinator = await _entry(hass, {})
    assert coordinator.data["control_action"] == "idle"
    assert not coordinator.decision_history()[-1].get("night_grid_kw")      # 300 W: the battery covers it
    # the oven: the battery gives 3 kW - the grid takes over above 1.5 kW
    _bat(hass, -3000)
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    extra = coordinator._night_loop["extra"]
    assert extra > 0.5
    # sent: the idle value plus what the grid takes over (W)
    assert coordinator.controller._last_sent == round(coordinator.control_settings().idle_value + extra * 1000.0)
    # at the limit it holds; the oven off - back to idle
    _bat(hass, -1500)
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    assert coordinator._night_loop["extra"] == extra
    _bat(hass, -200)
    for _ in range(6):
        freezer.tick(timedelta(minutes=1))
        await coordinator.async_refresh()
    assert coordinator._night_loop["extra"] == 0.0


async def test_by_day_no_night_loop(hass, freezer):
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 12, 1, tzinfo=tz)))
    base_states(hass, dt_util.now())
    _bat(hass, -3000)
    entry, coordinator = await _entry(hass, {})
    assert coordinator._night_loop is None
