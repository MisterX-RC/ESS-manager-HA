"""Switch platform - "Automatic control" (as of v0.2.14).

Only matters when direct control is set up in Configure (a number /
input_number entity to send the setpoint to). On: the integration sends the setpoint
every cycle. Off: it sends idle once and then leaves the target alone, so
the battery can be controlled by hand (or by an existing automation) without
reconfiguring anything. Restores its state across restarts; on by default.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import EssManagerCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EssManagerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    async_add_entities([EssManagerAutomaticControlSwitch(coordinator, entry, device_info)])


class EssManagerAutomaticControlSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = "Automatic control"
    _attr_icon = "mdi:robot-outline"

    def __init__(self, coordinator: EssManagerCoordinator, entry: ConfigEntry, device_info: DeviceInfo) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_automatic_control"
        self._attr_device_info = device_info
        self._attr_is_on = True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._attr_is_on = last_state.state == "on"
        self._coordinator.controller.enabled = bool(self._attr_is_on)
        # Keep the control_mode/control_target attributes current after a
        # Configure change (the switch isn't a coordinator entity otherwise).
        self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))

    async def async_will_remove_from_hass(self) -> None:
        # The integration is being unloaded/removed: stop sending (the
        # unload itself sends idle first - see __init__.py).
        self._coordinator.controller.enabled = False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        settings = self._coordinator.control_settings()
        return {"control_mode": settings.mode, "control_target": settings.target}

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self._coordinator.controller.enabled = True
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self._coordinator.controller.enabled = False
        self.async_write_ha_state()
        await self._coordinator.controller.async_idle(
            self._coordinator.control_settings(), "automatic control switched off", force=True
        )
        await self._coordinator.async_request_refresh()
