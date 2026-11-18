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
    assert co.hp.wind_src == "speed:weather.home|dir:weather.home" and read.count("weather.home") == 1
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
    assert attr["source"] == "speed:weather.home|dir:weather.home" and attr["hours"] >= 24 * 9 and attr["days"] >= 6 and attr["days_needed"] == 21
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
    # both sensors set: the weather entity isn't read for wind at all (their own histories are)
    assert "weather.home" not in read and "sensor.wind" in read and "sensor.wind_dir" in read
    assert co.hp.wind_src is None                                     # nothing recorded: tried again tomorrow
    assert co._hp_weather_wind({**BASE_DATA, **HP_DATA, "hp_wind_entity": "sensor.wind", "hp_wind_dir_entity": "sensor.wind_dir"}) is None
    acc = co.hp._wind_hour
    assert acc is not None and abs(acc[1] / acc[2] - 2.0) < 0.01        # 7.2 km/h = 2 m/s from the sensor


async def test_wind_sensor_history_and_weather_left_out_of_the_recorder(hass, monkeypatch, freezer):
    """(2026.11.55) A wind speed sensor without statistics (only its states) and
    the weather entity left out of the recorder: the speed comes from the
    sensor's history, the direction only live; nothing of the weather entity
    is read, and it's tried again a day later. The house's fits get the series
    where the sensor's statistics have no hours."""
    from custom_components.ess_manager import coordinator as coord

    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_set("sensor.qube_heat", "100", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
    hass.states.async_set("sensor.outdoor", "5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.indoor", "21.0", {"unit_of_measurement": "°C"})
    hass.states.async_set("climate.house", "heat", {"hvac_action": "idle", "temperature": 21.0, "current_temperature": 21.0})
    hass.states.async_set("weather.home", "cloudy", {"wind_speed": 18.0, "wind_speed_unit": "km/h", "wind_bearing": 270})
    hass.states.async_set("sensor.wind", "36", {"unit_of_measurement": "km/h", "state_class": "measurement"})
    read: list = []

    async def history(hass_, entity_id, start, end):
        read.append(entity_id)
        if entity_id != "sensor.wind":
            return []                                    # the weather entity: left out of the recorder
        out, t = [], start
        while t < end:
            out.append(State("sensor.wind", "36", {"unit_of_measurement": "km/h"}, last_changed=t, last_updated=t))
            t += timedelta(minutes=20)
        return out

    monkeypatch.setattr(coord, "async_fetch_state_changes", history)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis",
                            data={**BASE_DATA, **HP_DATA, "hp_wind_entity": "sensor.wind"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert co.hp.wind_src == "speed:sensor.wind|dir:weather.home"
    speeds = co.hp.wind_series()
    assert len(speeds) >= 24 * 9 and all(abs(v - 10.0) < 0.01 for v in speeds.values())   # 36 km/h = 10 m/s
    assert all(v[1] is None for k, v in co.hp.wind_hist.items() if int(k) < int(now.timestamp()) - 3600)
    rd = co.data["heat_pump"]["wind"]["read"]
    assert rd["states"] == {"sensor.wind": rd["states"]["sensor.wind"], "weather.home": 0} and rd["hours_dir"] == 0
    assert rd["hours_speed"] >= 24 * 9
    n = len(read)
    await co.async_refresh()
    assert len(read) == n                                 # done: not read again
    # a row with a value from a few live hours (before 2026.11.55) gets the whole day at the next read
    day = (dt_util.now().date() - timedelta(days=3)).isoformat()
    co.hp.journal = [r for r in co.hp.journal if r["d"] != day] + [{"d": day, "e": 4.0, "t": 5.0, "w": 2.5, "wd": 90.0}]
    co.hp.journal.sort(key=lambda r: r["d"])
    co.hp.wind_src = None
    co._hp_wind_tried_at = 0.0
    await co.async_refresh()
    row = next(r for r in co.hp.journal if r["d"] == day)
    assert row["w"] == 10.0 and row["wd"] == 90.0          # speed renewed; no direction in the series: kept
    # the fits: the sensor's statistics (one hour here) and the series for the rest
    h = int(now.timestamp()) // 3600 * 3600 - 7200
    merged = co._hp_wind_hourly({**BASE_DATA, **HP_DATA, "hp_wind_entity": "sensor.wind"}, {"sensor.wind": {h: 3.0}})
    assert merged[h] == 3.0 and len(merged) >= 24 * 9


async def test_wind_read_again_a_day_later_when_nothing_recorded(hass, monkeypatch, freezer):
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
        return []

    monkeypatch.setattr(coord, "async_fetch_state_changes", history)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **HP_DATA})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    w = lambda: read.count("weather.home")
    assert w() == 1 and co.hp.wind_src is None
    freezer.tick(timedelta(hours=2))
    await co.async_refresh()
    assert w() == 1                                       # not every cycle
    freezer.tick(timedelta(hours=23))
    await co.async_refresh()
    assert w() == 2                                       # a day later again


async def test_wind_forecast_from_the_wind_sensor(hass, monkeypatch):
    """(2026.11.56) A wind sensor with a forecast list of its own: the forecast's
    wind speed comes from it (per hour and per day), the direction and the
    temperature stay the weather entity's."""
    from homeassistant.core import SupportsResponse
    from custom_components.ess_manager import coordinator as coord

    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_set("sensor.qube_heat", "100", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
    hass.states.async_set("sensor.outdoor", "5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.indoor", "21.0", {"unit_of_measurement": "°C"})
    hass.states.async_set("climate.house", "heat", {"hvac_action": "idle", "temperature": 21.0, "current_temperature": 21.0})
    hass.states.async_set("weather.home", "cloudy", {"wind_speed": 18.0, "wind_speed_unit": "km/h", "wind_bearing": 270})
    day0 = dt_util.start_of_local_day(now)
    hours = [day0 + timedelta(hours=i) for i in range(72)]
    hass.states.async_set("sensor.wind", "36", {"unit_of_measurement": "km/h", "state_class": "measurement",
                                               "forecast": [{"datetime": h.isoformat(), "wind_speed": 36.0} for h in hours]})

    async def forecasts(call):
        if call.data.get("type") == "hourly":
            return {"weather.home": {"forecast": [{"datetime": h.isoformat(), "temperature": 6.0, "wind_speed": 18.0,
                                                   "wind_bearing": 200} for h in hours]}}
        return {"weather.home": {"forecast": []}}

    async def history(hass_, entity_id, start, end):
        return []

    monkeypatch.setattr(coord, "async_fetch_state_changes", history)
    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis",
                            data={**BASE_DATA, **HP_DATA, "hp_wind_entity": "sensor.wind"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    day = co._hp_weather[tomorrow]
    assert day["w"] == 10.0 and abs(day["wd"] - 200.0) < 0.5 and day["t"] == 6.0      # 36 km/h from the sensor
    assert all(abs(float(f["wind_speed"]) * co._hp_wind_factor - 10.0) < 0.01 for f in co._hp_hourly)
    assert co.data["heat_pump"]["wind"]["forecast"] == "sensor.wind"
    assert co.data["heat_pump"]["wind"]["cool_days"] == 0
