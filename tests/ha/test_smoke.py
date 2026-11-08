from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states


async def test_setup(hass):
    base_states(hass, dt_util.now())
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data=dict(BASE_DATA))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]
    assert coordinator.last_update_success, coordinator.last_exception
