"""The minute cycle: a cheap moment with a low battery charges; a battery
level that can't be read is a fail-safe idle (no guessing)."""
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states


async def _entry(hass, extra=None):
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **(extra or {})})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data["ess_manager"][entry.entry_id]["coordinator"]


async def test_cheap_now_low_battery_charges(hass):
    now = dt_util.now()
    base_states(hass, now)
    q = (now.hour * 60 + now.minute) // 15
    today = [0.40] * 96
    for i in range(q, min(q + 8, 96)):
        today[i] = 0.05                      # the next two hours very cheap, the rest dear
    hass.states.async_set("sensor.price", str(today[q]), {"today": today, "tomorrow": [0.40] * 96, "tomorrow_valid": True,
                                                         "unit_of_measurement": "EUR/kWh"})
    hass.states.async_set("sensor.soc", "20", {"unit_of_measurement": "%", "device_class": "battery"})
    hass.states.async_set("sensor.house", "1000", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
    # no usage history in a test: a minimum SOC above the battery makes a charge needed
    entry, coordinator = await _entry(hass, {"min_soc_percent": 50.0})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    decision = coordinator.decision_history()[-1]
    assert decision["action"] in ("charge", "negative_price_charge"), decision
    # sent to the grid setpoint (direct control on): a positive value in W
    assert decision["sending"] and decision["unit"] == "W" and decision["value"] > 0

async def test_unreadable_soc_is_failsafe_idle(hass):
    base_states(hass, dt_util.now())
    entry, coordinator = await _entry(hass)
    hass.states.async_set("sensor.soc", "unavailable")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.decision_history()[-1]["action"] == "idle (fail-safe)"
