"""A start before the other integrations are up (as of 2026.10.14): the first
cycle waits for the solar forecast instead of failing setup, and the next
cycle once it's there plans normally."""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states, solar_forecast


async def test_waits_for_the_solar_forecast_then_plans(hass, freezer):
    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_remove("sensor.helios_forecast_power_now")
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data=dict(BASE_DATA))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)     # setup itself succeeds
    await hass.async_block_till_done()
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert not coordinator.last_update_success
    assert "waiting for" in str(coordinator.last_exception)
    assert hass.states.get("sensor.thuis_status").state == "unavailable"
    # the forecast arrives: the next cycle plans
    hass.states.async_set("sensor.helios_forecast_power_now", "0", solar_forecast(now))
    freezer.tick(timedelta(minutes=1))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success, coordinator.last_exception
    assert hass.states.get("sensor.thuis_status").state != "unavailable"
