"""What comes in: the solar forecast (Helios), prices including taxes, the
night limit, the problem notices, the dashboard cards, a DST day."""
from datetime import datetime, timedelta

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states


async def _entry(hass, extra=None):
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **(extra or {})})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data["ess_manager"][entry.entry_id]["coordinator"]


def _helios(now, watts_at):
    start = dt_util.start_of_local_day(now)
    pts = []
    for i in range(96 * 3):
        t = start + timedelta(minutes=15 * i)
        pts.append({"datetime": t.isoformat(), "watts": float(watts_at(t)), "p10": None, "p90": None})
    return {"forecast": pts, "unit_of_measurement": "W"}


async def test_helios_solar_forecast(hass, freezer):
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 6, 5, tzinfo=dt_util.get_default_time_zone())))
    now = dt_util.now()
    base_states(hass, now)
    # 2 kW from 11:00 to 13:00 every day, nothing else
    hass.states.async_set("sensor.helios_forecast_power_now", "0",
                          _helios(now, lambda t: 2000 if 11 <= t.hour < 13 else 0))
    entry, coordinator = await _entry(hass)
    solar = coordinator.data["solar_120h"]
    hour0 = now.replace(minute=0, second=0, microsecond=0)
    by_hour = {(hour0 + timedelta(hours=i)).hour: v for i, v in enumerate(solar[:24])}
    assert abs(by_hour[11] - 2.0) < 0.05 and abs(by_hour[12] - 2.0) < 0.05
    assert by_hour[10] == 0 and by_hour[13] == 0 and abs(sum(solar[:24]) - 4.0) < 0.1


async def test_prices_incl_manual(hass):
    base_states(hass, dt_util.now())
    entry, coordinator = await _entry(hass, {"price_incl_mode": "manual", "price_purchase_fee": 0.02,
                                             "price_energy_tax": 0.10, "price_vat_percent": 21.0})
    bare = coordinator.data["all_price"]
    incl = coordinator.data["all_buy_price_incl"]
    assert len(incl) == len(bare) > 0
    # incl = (price + fee + tax) x 1.21
    for p, i in list(zip(bare, incl))[:8]:
        assert abs(i - (p + 0.02 + 0.10) * 1.21) < 0.002


async def test_night_limit_caps_the_charge(hass, freezer):
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 2, 1, tzinfo=dt_util.get_default_time_zone())))
    now = dt_util.now()
    base_states(hass, now)
    q = (now.hour * 60 + now.minute) // 15
    today = [0.40] * 96
    for i in range(q, q + 8):
        today[i] = 0.05
    hass.states.async_set("sensor.price", "0.05", {"today": today, "tomorrow": [0.40] * 96, "tomorrow_valid": True,
                                                  "unit_of_measurement": "EUR/kWh"})
    hass.states.async_set("sensor.soc", "20", {"unit_of_measurement": "%", "device_class": "battery"})
    entry, coordinator = await _entry(hass, {"min_soc_percent": 50.0, "night_limit_enabled": True,
                                             "night_charge_speed_kw": 1.5, "night_discharge_speed_kw": 1.5})
    decision = coordinator.decision_history()[-1]
    assert decision["action"] in ("charge", "negative_price_charge"), decision
    assert decision["night_limit"] and 0 < decision["power_kw"] <= 1.5


async def test_night_limited_charge_reads_actief_once_applied(hass, freezer):
    """2026.11.39: a charge below half the charge speed (the night limit) is
    "Actief" once the setpoint reads back what was sent - up to 2026.11.38 it
    stayed "Start charge" all night."""
    from .conftest import record_calls

    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 9, 2, 1, tzinfo=dt_util.get_default_time_zone())))
    now = dt_util.now()
    base_states(hass, now)
    q = (now.hour * 60 + now.minute) // 15
    today = [0.40] * 96
    for i in range(q, q + 8):
        today[i] = 0.05
    hass.states.async_set("sensor.price", "0.05", {"today": today, "tomorrow": [0.40] * 96, "tomorrow_valid": True,
                                                  "unit_of_measurement": "EUR/kWh"})
    hass.states.async_set("sensor.soc", "20", {"unit_of_measurement": "%", "device_class": "battery"})
    entry, coordinator = await _entry(hass, {"min_soc_percent": 50.0, "charge_speed_kw": 7.0, "night_limit_enabled": True,
                                             "night_charge_speed_kw": 1.5, "night_discharge_speed_kw": 1.5})
    calls: list = []
    record_calls(hass, "number", "set_value", calls)
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    assert calls and 0 < float(calls[-1][2]["value"]) <= 1500      # the night speed was sent
    assert coordinator.data["system_status"] == "Start charge"      # not read back yet when the status was made
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    assert coordinator.data["control_action"] == "charge"
    assert coordinator.data["system_status"] == "Actief"            # 1.5 kW read back, far below 7 kW x 0.5


async def test_problem_notice_unavailable_input(hass, freezer):
    base_states(hass, dt_util.now())
    entry, coordinator = await _entry(hass)
    hass.states.async_set("sensor.price", "unavailable")
    await coordinator.async_refresh()
    assert "input_unavailable" in coordinator.problems.active()
    reg = ir.async_get(hass)
    assert reg.async_get_issue("ess_manager", f"input_unavailable_{entry.entry_id}") is None   # not before 15 minutes
    freezer.tick(timedelta(minutes=16))
    await coordinator.async_refresh()
    assert reg.async_get_issue("ess_manager", f"input_unavailable_{entry.entry_id}") is not None
    # back: the notice goes
    from .conftest import prices_today_tomorrow
    hass.states.async_set("sensor.price", "0.25", prices_today_tomorrow(dt_util.now()))
    await coordinator.async_refresh()
    assert reg.async_get_issue("ess_manager", f"input_unavailable_{entry.entry_id}") is None


async def test_cards_served_and_resource(hass):
    from homeassistant.setup import async_setup_component

    await async_setup_component(hass, "http", {})
    base_states(hass, dt_util.now())
    added = []
    import homeassistant.components.frontend as fe

    orig = fe.add_extra_js_url
    fe.add_extra_js_url = lambda h, url, es5=False: added.append(url)
    try:
        await _entry(hass)
    finally:
        fe.add_extra_js_url = orig
    assert any("ess-manager-cards.js?v=" in u for u in added), added


async def test_dst_end_day(hass, freezer):
    # 25 Oct 2026: the clocks go back - 100 quarters that day
    tz = dt_util.get_default_time_zone()
    freezer.move_to(dt_util.as_utc(datetime(2026, 10, 25, 1, 30, tzinfo=tz)))
    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_set("sensor.price", "0.25", {"today": [0.25] * 100, "tomorrow": [0.25] * 96, "tomorrow_valid": True,
                                                  "unit_of_measurement": "EUR/kWh"})
    entry, coordinator = await _entry(hass)
    assert coordinator.last_update_success, coordinator.last_exception
    assert coordinator.data["today_price_units"] in (96, 100)
    freezer.tick(timedelta(hours=2))       # past the doubled hour
    await coordinator.async_refresh()
    assert coordinator.last_update_success, coordinator.last_exception
