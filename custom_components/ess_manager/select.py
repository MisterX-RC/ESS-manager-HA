"""Select platform - "Floor control" (as of 2026.10.23): how far ESS Manager
may go with the floor heating (floor_control.py): watch (learn and show,
nothing changes), setpoint (it sets the heat pump's return setpoint, the
thermostat still switches heat demand) or full (it also switches heat
demand). A stage only runs once the one before has proven itself - the
heat pump card shows what it waits for. Restored across restarts; watch by
default; hidden while floor control isn't set up in Configure.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import floor_control as fc
from .const import DOMAIN
from .coordinator import EssManagerCoordinator
from .visibility import async_sync_visibility


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EssManagerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    async_add_entities([EssManagerFloorControlSelect(coordinator, entry, device_info)])


class EssManagerFloorControlSelect(SelectEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = "Floor control"
    _attr_icon = "mdi:heating-coil"
    _attr_options = list(fc.MODES)

    def __init__(self, coordinator: EssManagerCoordinator, entry: ConfigEntry, device_info: DeviceInfo) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_floor_control"
        self._attr_device_info = device_info
        self._attr_current_option = fc.MODE_WATCH

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in fc.MODES:
            self._attr_current_option = last.state
        self._coordinator.floor_mode = self._attr_current_option
        self._coordinator.floor_mode_entity_id = self.entity_id
        self.async_on_remove(self._coordinator.async_add_listener(self._handle_coordinator_update))
        self._async_sync_visibility()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._async_sync_visibility()

    @callback
    def _async_sync_visibility(self) -> None:
        async_sync_visibility(self, self._coordinator.floor_configured())

    async def async_select_option(self, option: str) -> None:
        if option not in fc.MODES:
            return
        self._attr_current_option = option
        self._coordinator.floor_mode = option
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()
