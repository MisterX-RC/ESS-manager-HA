"""Switch platform - "Automatic control" (as of v0.2.14).

Only matters when direct control is set up in Configure (a number /
input_number entity to send the setpoint to). On: the integration sends the setpoint
every cycle. Off: it sends idle once and then leaves the target alone, so
the battery can be controlled by hand (or by an existing automation) without
reconfiguring anything. Restores its state across restarts; on by default.

Hidden while it has nothing to control (as of v0.3.2): with "Status sensor
only" (an external automation acts on the Status) it's marked hidden, and
choosing a number / input_number entity in Configure shows it again - see
visibility.py for the exact rules.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, HP_STEERING_PLAN
from .coordinator import EssManagerCoordinator
from .visibility import async_sync_visibility


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EssManagerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    async_add_entities([
        EssManagerAutomaticControlSwitch(coordinator, entry, device_info),
        EssManagerHeatPumpSteeringSwitch(coordinator, entry, device_info),
        EssManagerAutoBufferSwitch(coordinator, entry, device_info),
    ])


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
        # Keep the control_mode/control_target attributes and the hidden
        # state current after a Configure change (the switch isn't a
        # coordinator entity otherwise; Configure only triggers a refresh).
        self.async_on_remove(self._coordinator.async_add_listener(self._handle_coordinator_update))
        self._async_sync_visibility()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._async_sync_visibility()
        self.async_write_ha_state()

    @callback
    def _async_sync_visibility(self) -> None:
        """Hidden while direct control isn't set up - see visibility.py."""
        async_sync_visibility(self, self._coordinator.control_settings().active)

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


class EssManagerHeatPumpSteeringSwitch(SwitchEntity, RestoreEntity):
    """Heat pump steering (as of 2026.10.17): on, ESS Manager sets the
    thermostat (day/night temperature, the house as a buffer once the
    hour-by-hour model passed its self-check). Only there while both heat
    pump steps are on in Configure (hidden otherwise); off by default; on the
    heat pump card."""

    _attr_has_entity_name = True
    _attr_name = "Heat pump steering"
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(self, coordinator: EssManagerCoordinator, entry: ConfigEntry, device_info: DeviceInfo) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_heat_pump_steering"
        self._attr_device_info = device_info
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._attr_is_on = last_state.state == "on"
        self._coordinator.hp_steering_on = bool(self._attr_is_on)
        self._coordinator.hp_steering_entity = self
        self.async_on_remove(self._coordinator.async_add_listener(self._handle_coordinator_update))
        self._async_sync_visibility()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._async_sync_visibility()

    @callback
    def _async_sync_visibility(self) -> None:
        async_sync_visibility(self, self._coordinator.plan_enabled(HP_STEERING_PLAN))

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self._coordinator.hp_steering_on = True
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self._coordinator.hp_steering_on = False
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()


class EssManagerAutoBufferSwitch(SwitchEntity, RestoreEntity):
    """Automatic safety buffer (as of 2026.10.22): on, the plans use the
    forecast check's advice instead of the Safety buffer number - the
    smallest buffer that covered 95 % of the last 28 days, approached by at
    most 2 %-points a day, between 2 and 30 %. Until 14 days are measured
    (and whenever it's off) the number is used. Off by default; on the
    forecast check card."""

    _attr_has_entity_name = True
    _attr_name = "Automatic safety buffer"
    _attr_icon = "mdi:shield-sync-outline"

    def __init__(self, coordinator: EssManagerCoordinator, entry: ConfigEntry, device_info: DeviceInfo) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_automatic_safety_buffer"
        self._attr_device_info = device_info
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._attr_is_on = last_state.state == "on"
        self._coordinator.auto_buffer_on = bool(self._attr_is_on)
        self._coordinator.auto_buffer_entity_id = self.entity_id

    async def _async_set(self, on: bool) -> None:
        self._attr_is_on = on
        self._coordinator.auto_buffer_on = on
        self.async_write_ha_state()
        # another buffer: running windows are checked again
        self._coordinator.request_replan()
        await self._coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
