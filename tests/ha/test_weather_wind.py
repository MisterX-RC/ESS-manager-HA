"""Wind from the weather entity (as of 2026.11.54): without a wind sensor the
heat pump model takes the wind speed and direction from the weather entity -
live per hour into its own series, once ~10 days from the recorder - and
fills the journal's days with it."""
from datetime import timedelta

from homeassistant.core import State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ess_manager.diagnostics import async_get_config_entry_diagnostics

from .conftest import BASE_DATA, base_states
from .test_heatpump import HP_DATA


def _weather_history(start, end):
    """The weather entity every 30 minutes: 36 km/h from the south-west."""
    out = []
    t = start
    while t < end:
        out.append(State("weather.home", "cloudy", {"wind_speed": 36.0, "wind_speed_unit": "km/h", "wind_bearing": 225},
                         last_changed=t, last_updated=t))
        t += timedelta(minutes=30)
    return out


async def test_wind_from_the_weather_entity(hass, monkeypatch, freezer):
    from custom_components.ess_manager import coordinator as coord

    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_set("sensor.qube_heat", "100", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
    hass.states.async_set("sensor.outdoor", "5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.indoor", "21.0", {"unit_of_measurement": "°C"})
    hass.states.async_set("climate.house", "heat", {"hvac_action": "idle", "temperature": 21.0, "current_temperature": 21.0})
    hass.states.async_set("weather.home", "cloudy", {"wind_speed": 18.0, "wind_speed_unit": "km/h", "wind_bearing": 270})
    read: list = []

    async def history(hass_, entity_id, start, end):
        read.append(entity_id)
        return _weather_history(start, end) if entity_id == "weather.home" else []

    monkeypatch.setattr(coord, "async_fetch_state_changes", history)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **HP_DATA})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    # once from the recorder: ~10 days of 10 m/s from 225 degrees, and the journal's days filled
    assert co.hp.wind_src == "weather.home" and read.count("weather.home") == 1
    hist = co.hp.wind_series()
    assert len(hist) >= 24 * 9 and all(abs(v - 10.0) < 0.01 for v in hist.values())
    assert all(abs(v[1] - 225.0) < 0.5 for v in co.hp.wind_hist.values())
    # journal days (from the statistics, here put in by hand) get it at the next hourly fill
    for i in range(2, 8):
        co.hp.journal.append({"d": (dt_util.now().date() - timedelta(days=i)).isoformat(), "e": 4.0, "t": 5.0})
    co.hp.journal.sort(key=lambda r: r["d"])
    co._hp_wind_fill_hour = None
    await co.async_refresh()
    days = [r for r in co.hp.journal if r.get("w") is not None]
    assert len(days) == 6 and all(abs(r["w"] - 10.0) < 0.01 and abs(r["wd"] - 225.0) < 0.5 for r in days)
    # not read again
    await co.async_refresh()
    assert read.count("weather.home") == 1
    # live: the hour's mean (18 km/h = 5 m/s from the west) once the hour is over
    h0 = int(dt_util.utcnow().timestamp()) // 3600 * 3600
    freezer.move_to(dt_util.utc_from_timestamp(h0 + 3600 + 30))
    await co.async_refresh()
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    assert co.hp.wind_hist.get(str(h0)) == [5.0, 270.0]
    attr = co.data["heat_pump"]["wind"]
    assert attr["source"] == "weather.home" and attr["hours"] >= 24 * 9 and attr["days"] >= 6 and attr["days_needed"] == 21
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["data"]["heat_pump"]["wind"]["hours"] == attr["hours"]


async def test_wind_sensor_wins_over_the_weather_entity(hass, monkeypatch):
    from custom_components.ess_manager import coordinator as coord

    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_set("sensor.qube_heat", "100", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
    hass.states.async_set("sensor.outdoor", "5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.indoor", "21.0", {"unit_of_measurement": "°C"})
    hass.states.async_set("climate.house", "heat", {"hvac_action": "idle", "temperature": 21.0, "current_temperature": 21.0})
    hass.states.async_set("weather.home", "cloudy", {"wind_speed": 18.0, "wind_speed_unit": "km/h", "wind_bearing": 270})
    hass.states.async_set("sensor.wind", "7.2", {"unit_of_measurement": "km/h"})
    hass.states.async_set("sensor.wind_dir", "90", {"unit_of_measurement": "°"})
    read: list = []

    async def history(hass_, entity_id, start, end):
        read.append(entity_id)
        return []

    monkeypatch.setattr(coord, "async_fetch_state_changes", history)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis",
                            data={**BASE_DATA, **HP_DATA, "hp_wind_entity": "sensor.wind", "hp_wind_dir_entity": "sensor.wind_dir"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    # both sensors set: the weather entity isn't read for wind at all
    assert "weather.home" not in read and co.hp.wind_src is None
    assert co._hp_weather_wind({**BASE_DATA, **HP_DATA, "hp_wind_entity": "sensor.wind", "hp_wind_dir_entity": "sensor.wind_dir"}) is None
    acc = co.hp._wind_hour
    assert acc is not None and abs(acc[1] / acc[2] - 2.0) < 0.01        # 7.2 km/h = 2 m/s from the sensor
