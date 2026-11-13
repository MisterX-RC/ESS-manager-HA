"""The daily house fit waits for yesterday's last hour (as of 2026.11.43): the
recorder writes an hour's statistics a few seconds after the hour, and a fit in
the first cycle after midnight left all of yesterday out of the self-check."""
from datetime import datetime, timedelta

from homeassistant.core import SupportsResponse
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states
from .test_heatpump import HP_DATA


async def _setup(hass, monkeypatch, complete):
    from custom_components.ess_manager import coordinator as coord
    from custom_components.ess_manager import heatpump_house

    def hours(start, end):
        a = int(start.timestamp()) // 3600 * 3600
        b = int(end.timestamp()) // 3600 * 3600
        last = b if complete["now"] else b - 3600      # the hour before midnight missing
        return range(a, last, 3600)

    async def sums(hass_, ids, start, end):
        out = {}
        for e in ids:
            if e == "sensor.qube_heat":
                total, series = 100.0, {}
                for h in hours(start, end):
                    total += 0.5
                    series[h] = total
                out[e] = series
        return out

    async def means(hass_, ids, start, end, **kwargs):
        return {e: {h: (5.0 if e == "sensor.outdoor" else 21.0) for h in hours(start, end)}
                for e in ids if e in ("sensor.outdoor", "sensor.indoor")}

    monkeypatch.setattr(coord, "async_fetch_hourly_sums", sums)
    monkeypatch.setattr(coord, "async_fetch_hourly_means", means)
    fits = []

    def fake_learn(*args, **kwargs):
        fits.append(max(args[2]) if args[2] else None)    # the newest hour of heat it saw
        return {"cop": None, "cop_check": None, "model": None, "review": None, "thermostat": None}

    monkeypatch.setattr(heatpump_house, "learn", fake_learn)

    async def forecasts(call):
        base = dt_util.start_of_local_day(dt_util.now())
        if call.data["type"] == "daily":
            return {"weather.home": {"forecast": [{"datetime": (base + timedelta(days=k, hours=12)).isoformat(),
                                                   "temperature": 6.0, "templow": 2.0} for k in range(6)]}}
        return {"weather.home": {"forecast": []}}

    base_states(hass, dt_util.now())
    hass.states.async_set("sensor.qube_heat", "100", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
    hass.states.async_set("sensor.outdoor", "5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.indoor", "21.0", {"unit_of_measurement": "°C"})
    hass.states.async_set("climate.house", "heat", {"hvac_action": "idle", "temperature": 21.0, "current_temperature": 21.0})
    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **HP_DATA})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data["ess_manager"][entry.entry_id]["coordinator"], fits


async def test_house_fit_waits_for_the_last_hour(hass, freezer, monkeypatch):
    tz = dt_util.get_default_time_zone()
    midnight = datetime(2026, 11, 13, 0, 0, 0, tzinfo=tz)
    freezer.move_to(dt_util.as_utc(midnight + timedelta(seconds=2)))
    complete = {"now": False}
    co, fits = await _setup(hass, monkeypatch, complete)
    # 00:00:02 - the hour before midnight isn't in the statistics yet: no fit
    assert fits == [] and co.hp.thermal_day != "2026-11-13"
    # a minute later still missing: waits, no fit
    freezer.tick(timedelta(minutes=1))
    await co.async_refresh()
    assert fits == []
    # written: the next try (within a few minutes) fits with yesterday complete
    complete["now"] = True
    freezer.tick(timedelta(minutes=5))
    await co.async_refresh()
    assert len(fits) == 1 and fits[0] == int((midnight - timedelta(hours=1)).timestamp())
    assert co.hp.thermal_day == "2026-11-13"
    # once a day: no second fit
    freezer.tick(timedelta(minutes=10))
    await co.async_refresh()
    assert len(fits) == 1


async def test_house_fit_without_the_last_hour_after_two_hours(hass, freezer, monkeypatch):
    tz = dt_util.get_default_time_zone()
    midnight = datetime(2026, 11, 13, 0, 0, 0, tzinfo=tz)
    freezer.move_to(dt_util.as_utc(midnight + timedelta(seconds=2)))
    complete = {"now": False}
    co, fits = await _setup(hass, monkeypatch, complete)
    assert fits == []
    # a sensor that stopped: past two hours after midnight fitted anyway, as before
    for _ in range(25):
        freezer.tick(timedelta(minutes=5))
        await co.async_refresh()
    assert len(fits) == 1 and co.hp.thermal_day == "2026-11-13"
