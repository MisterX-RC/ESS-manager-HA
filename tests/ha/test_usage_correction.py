"""The short-term usage correction (as of 2026.11.33): the last
three hours measured against what was forecast for them, the difference per
hour added to the coming hours, fading out over six."""
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states


async def test_short_term_correction_follows_a_new_load(hass, freezer, monkeypatch):
    from custom_components.ess_manager import coordinator as coord

    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 12, 0, 0, 30, tzinfo=tz)))
    t0 = int(dt_util.now().replace(minute=0, second=0).timestamp())

    # the house used 0.35 kWh an hour for weeks; from midnight on 0.92 (a new load)
    def rate(hour_epoch: int) -> float:
        return 0.92 if hour_epoch >= t0 else 0.35

    async def sums(hass_, entity_ids, start, end):
        a = int(start.timestamp()) // 3600 * 3600
        b = int(end.timestamp()) // 3600 * 3600
        series, total = {}, 1000.0
        for h in range(a, b + 1, 3600):
            total += rate(h)
            series[h] = round(total, 3)
        return {e: dict(series) for e in entity_ids if e == "sensor.house"}

    monkeypatch.setattr(coord, "async_fetch_hourly_sums", sums)
    base_states(hass, dt_util.now())
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data=dict(BASE_DATA))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert co.data["energy_usage_120h"][0] == 0.35          # the weekly pattern
    assert co.data["usage_correction"]["offset_kwh_h"] is None   # nothing to compare yet

    # a cycle every 20 minutes through 00:00-03:00
    for _ in range(9):
        freezer.tick(timedelta(minutes=20))
        await co.async_refresh()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 12, 3, 6, 0, tzinfo=tz)))
    await co.async_refresh()
    corr = co.data["usage_correction"]
    assert corr["offset_kwh_h"] == 0.57
    assert [h[1] for h in corr["hours"]] == [0.35, 0.35, 0.35] and [h[2] for h in corr["hours"]] == [0.92, 0.92, 0.92]
    usage = co.data["energy_usage_120h"]
    assert usage[0] == 0.92 and usage[3] == round(0.35 + 0.57 * 0.5, 3) and usage[6] == 0.35

    # the load stops: three normal hours later the correction is gone again
    t_stop = t0 + 3 * 3600

    def rate2(hour_epoch: int) -> float:
        return 0.92 if t0 <= hour_epoch < t_stop else 0.35

    async def sums2(hass_, entity_ids, start, end):
        a = int(start.timestamp()) // 3600 * 3600
        b = int(end.timestamp()) // 3600 * 3600
        series, total = {}, 1000.0
        for h in range(a, b + 1, 3600):
            total += rate2(h)
            series[h] = round(total, 3)
        return {e: dict(series) for e in entity_ids if e == "sensor.house"}

    monkeypatch.setattr(coord, "async_fetch_hourly_sums", sums2)
    for _ in range(10):
        freezer.tick(timedelta(minutes=20))
        await co.async_refresh()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 12, 6, 6, 0, tzinfo=tz)))
    await co.async_refresh()
    assert co.data["usage_correction"]["offset_kwh_h"] == 0.0
    assert co.data["energy_usage_120h"][0] == 0.35
