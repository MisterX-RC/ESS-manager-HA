"""Number platform - exposes every tunable (min/max SOC, charge/discharge
speeds, negative-price threshold, spike margin, planning horizon, full
charge scheduling, ...) as an adjustable Home Assistant `number` entity, so
they can be tuned from the dashboard the same way an `input_number` helper
would be, without the user having to create those helpers by hand.

Each entity restores its last set value across restarts (RestoreNumber) -
the seed value from NUMBER_DEFINITIONS is only used the very first time the
entity is ever created.
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NUMBER_DEFINITIONS, plan_for_entity_key
from .coordinator import EssManagerCoordinator
from .visibility import async_sync_visibility


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EssManagerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]

    entities = []
    for key, name, icon, min_value, max_value, step, unit, default_fn in NUMBER_DEFINITIONS:
        entity = EssManagerNumber(
            coordinator=coordinator,
            entry=entry,
            device_info=device_info,
            key=key,
            name=name,
            icon=icon,
            min_value=min_value,
            max_value=max_value,
            step=step,
            unit=unit,
            default_value=default_fn(entry.data),
        )
        coordinator.register_number(key, entity)
        entities.append(entity)

    async_add_entities(entities)


class EssManagerNumber(RestoreNumber, NumberEntity):
    """A single tunable, backed by RestoreNumber so its value survives
    Home Assistant restarts independently of the config entry's own data.
    """

    _attr_has_entity_name = True
    _attr_entity_category = None  # shown as a normal, dashboard-able entity

    def __init__(
        self,
        coordinator: EssManagerCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        key: str,
        name: str,
        icon: str,
        min_value: float,
        max_value: float,
        step: float,
        unit: str,
        default_value: float,
    ) -> None:
        self._coordinator = coordinator
        self._key = key
        self._default_value = default_value
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info
        self._attr_native_value = default_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data is not None and last_data.native_value is not None:
            self._attr_native_value = last_data.native_value
        # A plan-specific tunable is hidden while its plan is switched off
        # in Configure (see visibility.py); Configure only triggers a
        # coordinator refresh, so follow the coordinator's updates.
        self._plan = plan_for_entity_key(self._key)
        if self._plan is not None:
            self.async_on_remove(self._coordinator.async_add_listener(self._async_sync_visibility))
            self._async_sync_visibility()

    @callback
    def _async_sync_visibility(self) -> None:
        async_sync_visibility(self, self._coordinator.plan_enabled(self._plan))

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        # A tunable changed - refresh immediately rather than waiting up to
        # 30s for the next scheduled cycle, so the dashboard feels responsive.
        await self._coordinator.async_request_refresh()
