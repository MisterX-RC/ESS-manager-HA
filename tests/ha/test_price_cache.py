"""Stored price lists (price_cache.py): the cycle carries on with them while
the price sensor has none, also after a restart and across midnight; an old
day's list counts as none; the notice and card label only once two reloads
of the price integration didn't help."""
from datetime import datetime, timedelta

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .conftest import base_states
from .test_price_reload import _entry, _minutes, _price_integration, _record_reloads


def _raw(day, values):
    start = dt_util.start_of_local_day(datetime.combine(day, datetime.min.time()))
    return [{"start": start + timedelta(minutes=15 * i), "end": start + timedelta(minutes=15 * (i + 1)), "value": v}
            for i, v in enumerate(values)]


def _sensor(now, today_offset=0, raw=True, n=96):
    """Nordpool-HACS-like attributes; today 0.20/0.30, tomorrow 0.10/0.40 (distinct)."""
    day = now.date() + timedelta(days=today_offset)
    today = [0.20 if q < 24 else 0.30 for q in range(n)]
    tomorrow = [0.10 if q < 24 else 0.40 for q in range(n)]
    attrs = {"today": today, "tomorrow": tomorrow, "tomorrow_valid": True, "unit_of_measurement": "EUR/kWh"}
    if raw:
        attrs["raw_today"] = _raw(day, today)
        attrs["raw_tomorrow"] = _raw(day + timedelta(days=1), tomorrow)
    return attrs


async def test_cached_prices_keep_planning_and_notice_after_two_reloads(hass, freezer, monkeypatch):
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 24, 9, 0, tzinfo=dt_util.get_default_time_zone())))
    price_entry = _price_integration(hass)
    base_states(hass, dt_util.now())
    hass.states.async_set("sensor.price", "0.2", _sensor(dt_util.now()))
    entry, co = await _entry(hass)
    reloads = _record_reloads(hass, monkeypatch)
    await _minutes(hass, freezer, co, 11)                       # past the start
    before = list(co.data["all_price"])
    assert len(before) == 192 and co.data["price_source"]["source"] == "sensor"
    hass.states.async_set("sensor.price", "unavailable")
    await _minutes(hass, freezer, co, 1)
    assert co.data["all_price"] == before                       # same prices, from the store
    assert co.data["price_source"]["source"] == "cached" and co.data["price_source"]["problem"] is False
    await _minutes(hass, freezer, co, 23)                       # 1st reload at +5, 2nd at +20
    assert len(reloads) == 2 and co.data["price_source"]["problem"] is False
    reg = ir.async_get(hass)
    assert reg.async_get_issue("ess_manager", f"prices_cached_{entry.entry_id}") is None
    await _minutes(hass, freezer, co, 1)
    assert co.data["price_source"]["problem"] is False          # 4 minutes after the 2nd reload
    await _minutes(hass, freezer, co, 1)                        # 5 minutes after the 2nd: failed twice
    assert co.data["price_source"]["problem"] is True
    issue = reg.async_get_issue("ess_manager", f"prices_cached_{entry.entry_id}")
    assert issue is not None and issue.translation_placeholders["until"].endswith("00:00")
    assert reg.async_get_issue("ess_manager", f"input_unavailable_{entry.entry_id}") is None
    # back: label and notice go
    hass.states.async_set("sensor.price", "0.2", _sensor(dt_util.now()))
    await _minutes(hass, freezer, co, 1)
    assert co.data["price_source"] == {**co.data["price_source"], "source": "sensor", "problem": False}
    assert reg.async_get_issue("ess_manager", f"prices_cached_{entry.entry_id}") is None


async def test_cached_prices_after_restart_and_midnight(hass, freezer):
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 24, 23, 40, tzinfo=dt_util.get_default_time_zone())))
    base_states(hass, dt_util.now())
    attrs = _sensor(dt_util.now())
    hass.states.async_set("sensor.price", "0.3", attrs)
    entry, co = await _entry(hass)
    await hass.async_block_till_done()
    assert co.price_cache.as_diag()["stored"] == {"2026-11-24": 96, "2026-11-25": 96}
    # restart while the sensor is gone
    hass.states.async_remove("sensor.price")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    co = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert co.last_update_success and len(co.data["all_price"]) == 192
    assert co.data["price_source"]["source"] == "cached"
    # past midnight: yesterday's "tomorrow" is today's list, nothing for tomorrow
    await _minutes(hass, freezer, co, 25)
    assert co.data["all_price"] == attrs["tomorrow"]
    assert co.data["price_source"]["tomorrow_source"] is None


async def test_old_day_counts_as_none_and_partial_lists_not_stored(hass, freezer, monkeypatch):
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 24, 9, 0, tzinfo=dt_util.get_default_time_zone())))
    price_entry = _price_integration(hass)
    base_states(hass, dt_util.now())
    good = _sensor(dt_util.now())
    hass.states.async_set("sensor.price", "0.2", good)
    entry, co = await _entry(hass)
    reloads = _record_reloads(hass, monkeypatch)
    await _minutes(hass, freezer, co, 11)
    # the sensor shows yesterday's lists (still "available"): a fault
    hass.states.async_set("sensor.price", "0.2", _sensor(dt_util.now(), today_offset=-1))
    await _minutes(hass, freezer, co, 6)
    assert co.data["price_source"]["source"] == "cached" and co.data["all_price"] == good["today"] + good["tomorrow"]
    assert reloads == [price_entry.entry_id]
    # an incomplete list (hourly, no start times) isn't stored
    co.price_cache.days.clear()
    hass.states.async_set("sensor.price", "0.2", _sensor(dt_util.now(), raw=False, n=24))
    await _minutes(hass, freezer, co, 1)
    assert co.price_cache.as_diag()["stored"] == {}
    assert co.data["price_source"]["source"] == "sensor"        # still used as before
