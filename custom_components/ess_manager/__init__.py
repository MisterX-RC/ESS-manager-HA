"""The ESS Manager integration - battery/solar/price-aware charge and
discharge planning, ported from a hand-written Home Assistant template
sensor into a configurable, HACS-installable custom integration.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN, PLATFORMS
from .coordinator import EssManagerCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    coordinator = EssManagerCoordinator(hass, entry)

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        manufacturer="ESS Manager",
        model="Battery / solar / price planner",
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device_info": device_info,
    }

    # number.py must run before the coordinator's first refresh so the
    # coordinator has live `number` entities to read tunables from - see the
    # PLATFORMS ordering note in const.py.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed (e.g. re-pointed an entity) - just refresh; entity
    references are re-read from entry.data/entry.options on every cycle so
    no reload is needed.
    """
    coordinator: EssManagerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.async_request_refresh()
