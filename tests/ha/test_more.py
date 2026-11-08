"""The savings card's numbers, the 09:00 question about today's car sessions
(with a tap on the phone), the forecast check and the house from the grid."""
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, CAR, base_states


async def _entry(hass, extra=None):
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **(extra or {})})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data["ess_manager"][entry.entry_id]["coordinator"]


async def test_savings_today(hass, freezer, monkeypatch):
    """The battery gave 0.6 kWh an hour all morning and nothing was bought: without it all of
    that would have been bought - today's saving is that energy at the buy price."""
    from custom_components.ess_manager import coordinator as coord

    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 10, 20, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    sources = {"import": ["sensor.grid_in"], "export": ["sensor.grid_out"],
               "battery_charge": ["sensor.bat_in"], "battery_discharge": ["sensor.bat_out"], "solar": []}

    async def fake_sources(self):
        return sources

    monkeypatch.setattr(coord.EssManagerCoordinator, "_async_savings_sources", fake_sources)

    async def stats(hass_, ids, start, end):
        out = {}
        t = int(start.timestamp()) // 300 * 300
        while t < min(end.timestamp(), now.timestamp()) - 300:
            for i in ids:
                out.setdefault(i, {})[t] = 0.05 if i == "sensor.bat_out" else 0.0
            t += 300
        return out

    monkeypatch.setattr(coord, "async_fetch_5min_changes", stats)
    entry, coordinator = await _entry(hass)
    await hass.async_block_till_done()
    sav = coordinator.data["savings"]
    assert sav["status"] == "ok"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    today = coordinator.savings.attribute(coordinator._buy_line)["today"]
    row = today["row"]
    # [date, kWh bought, EUR, kWh sold, EUR, kWh bought without, EUR, kWh sold without, EUR, stock]
    assert row[1] == 0 and row[5] > 5.5 and row[6] > 5.5 * 0.19
    assert len(today["quarters"]) >= 40


async def test_morning_question_and_no(hass, freezer):
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 8, 58, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    sent = []

    async def notify(call):
        sent.append(dict(call.data))

    hass.services.async_register("notify", "mobile_app_x", notify)
    entry, coordinator = await _entry(hass, {
        "ev_enabled": True, "ev_charger": "sensors", "ev_cars": [CAR], "ev_energy_entity": "sensor.ev_energy",
        "ev_power_entity": "sensor.ev_power", "ev_min_current": 6, "ev_max_current": 16, "ev_phases": 3,
        "ev_predict": False, "ev_notify_services": ["mobile_app_x"]})
    start = int(datetime(2026, 11, 9, 17, 0, tzinfo=tz).timestamp())
    sid = coordinator.ev.save(None, {"start": start, "kwh": 8.0, "mode": "fixed", "current_a": 16, "car": "c1"},
                              int(now.timestamp()))
    await coordinator.async_refresh()
    assert not any("17:00" in (m.get("message") or "") for m in sent)       # not before 09:00
    freezer.tick(timedelta(minutes=5))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    question = next(m for m in sent if "17:00" in (m.get("message") or ""))
    actions = question["data"]["actions"]
    no = next(a for a in actions if a["action"].endswith(f"m_no={sid}"))
    # a tap on "No": the session stays, switched off
    hass.bus.async_fire("mobile_app_notification_action", {"action": no["action"]})
    await hass.async_block_till_done()
    session = next(m for m in coordinator.ev.manual if m["id"] == sid)
    assert session["enabled"] is False


async def test_forecast_check_attribute(hass):
    base_states(hass, dt_util.now())
    entry, coordinator = await _entry(hass)
    fc = coordinator.data["forecast_check"]
    # the card's parts are there (on a fresh install without test days)
    assert {"buffer", "methods", "ready", "solar", "usage"} <= set(fc)
    assert isinstance(fc["ready"], bool) and isinstance(fc["methods"], (list, dict))


async def test_grid_use_follows_the_battery(hass, freezer):
    """The house from the grid at a low price (as of 2026.10.41): the setpoint moves so the
    battery's power goes to 0 - here 900 W discharging -> the setpoint goes up."""
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 3, 1, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_set("sensor.bat_power", "-900", {"unit_of_measurement": "W", "device_class": "power"})
    entry, coordinator = await _entry(hass, {"enable_grid_use_plan": True, "battery_power_entity": "sensor.bat_power",
                                             "battery_power_sign": "charge_positive"})
    settings = coordinator.control_settings()
    coordinator._grid_use_kw = None
    first = coordinator._grid_use_setpoint_kw({**BASE_DATA, "battery_power_entity": "sensor.bat_power",
                                               "battery_power_sign": "charge_positive"}, settings)
    assert first > 0.3                      # more from the grid: the battery's 900 W
    hass.states.async_set("sensor.bat_power", "0", {"unit_of_measurement": "W", "device_class": "power"})
    second = coordinator._grid_use_setpoint_kw({**BASE_DATA, "battery_power_entity": "sensor.bat_power",
                                                "battery_power_sign": "charge_positive"}, settings)
    assert second == first                  # at 0 W it stays (dead band)
