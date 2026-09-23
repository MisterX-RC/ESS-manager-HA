"""Sensor platform: one rich "status" sensor carrying every forecast array
and plan dict as attributes (for dashboard/ApexCharts compatibility with
the original template-sensor dashboard), plus a handful of standalone
sensors for the values most useful directly in automations or history
graphs.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EssManagerCoordinator

# Attributes carried on the main status sensor - matches (renamed to
# snake_case) the original template sensor's attribute set, so the
# dashboard/ApexCharts data_generator scripts only need their entity_id and
# attribute-name references updated, not their logic.
STATUS_ATTRIBUTES = [
    "battery_energy_kwh",
    "battery_soc_percent",
    "low_threshold_kwh",
    "high_threshold_kwh",
    "capacity_kwh",
    "current_price_unit",
    "all_price",
    "today_price_units",
    "solar_120h",
    "energy_usage_120h",
    "usage_source",
    "energy_dashboard_sources",
    "net_energy_120h",
    "battery_forecast",
    "battery_forecast_with_negative_price",
    "battery_forecast_with_spike",
    "battery_forecast_adjusted",
    "negative_price_plan",
    "spike_plan",
    "low_charge_plan",
    "high_discharge_plan",
    "full_charge_plan",
    "cell_voltage_differential_mv",
    "battery_voltage",
    "time_since_full_charge_days",
    "planning_horizon_hours",
    "charge_energy_kwh",
    "charge_start_time",
    "charge_stop_time",
    "discharge_energy_kwh",
    "discharge_start_time",
    "discharge_stop_time",
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EssManagerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]

    entities: list[SensorEntity] = [
        EssManagerStatusSensor(coordinator, entry, device_info),
        EssManagerValueSensor(
            coordinator, entry, device_info, "battery_level_kwh", "Battery level", "battery_energy_kwh", "kWh", "mdi:battery"
        ),
        EssManagerValueSensor(
            coordinator,
            entry,
            device_info,
            "next_full_charge_in_days",
            "Next full charge in",
            "next_full_charge_in_days",
            "d",
            "mdi:calendar-clock",
        ),
        EssManagerValueSensor(
            coordinator, entry, device_info, "spike_status", "Spike status", "spike_status_text", None, "mdi:flash-alert"
        ),
        EssManagerValueSensor(
            coordinator,
            entry,
            device_info,
            "negative_price_status",
            "Negative price status",
            "negative_price_status_text",
            None,
            "mdi:sale",
        ),
        EssManagerValueSensor(
            coordinator, entry, device_info, "charge_amount", "Charge amount", "charge_energy_kwh", "kWh", "mdi:battery-plus"
        ),
        EssManagerValueSensor(
            coordinator, entry, device_info, "charge_start", "Charge start", "charge_start_time", None, "mdi:clock-start"
        ),
        EssManagerValueSensor(
            coordinator, entry, device_info, "charge_stop", "Charge stop", "charge_stop_time", None, "mdi:clock-end"
        ),
        EssManagerValueSensor(
            coordinator,
            entry,
            device_info,
            "discharge_amount",
            "Discharge amount",
            "discharge_energy_kwh",
            "kWh",
            "mdi:battery-minus",
        ),
        EssManagerValueSensor(
            coordinator, entry, device_info, "discharge_start", "Discharge start", "discharge_start_time", None, "mdi:clock-start"
        ),
        EssManagerValueSensor(
            coordinator, entry, device_info, "discharge_stop", "Discharge stop", "discharge_stop_time", None, "mdi:clock-end"
        ),
    ]
    async_add_entities(entities)


class EssManagerStatusSensor(CoordinatorEntity[EssManagerCoordinator], SensorEntity):
    """The main sensor - its state is system_status, and it carries every
    forecast array / plan dict the dashboard cards need as attributes.
    """

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:home-battery"

    def __init__(self, coordinator: EssManagerCoordinator, entry: ConfigEntry, device_info: DeviceInfo) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("system_status")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        return {key: self.coordinator.data.get(key) for key in STATUS_ATTRIBUTES}


class EssManagerValueSensor(CoordinatorEntity[EssManagerCoordinator], SensorEntity):
    """A single flattened display value read straight from coordinator.data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EssManagerCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        key: str,
        name: str,
        data_key: str,
        unit: str | None,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._data_key = data_key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_device_info = device_info

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self._data_key)
        if value is not None:
            return value
        # charge/discharge amount and start/stop time are legitimately
        # None whenever no plan is currently active - that's the normal,
        # frequent case, not an error, so every one of these sensors shows
        # the same "-" placeholder rather than "unknown". A sensor with a
        # unit of measurement (kWh, d) can't safely report "-" while its
        # unit is still set, though: Home Assistant treats a unit as a
        # promise that the state is numeric and raises instead of just
        # showing "unknown"/the placeholder if it ever gets a non-numeric
        # string while a (unit-convertible) unit like kWh is attached. See
        # native_unit_of_measurement below, which hides the unit for
        # exactly this case so "-" is safe to return unconditionally here.
        return "-"

    @property
    def native_unit_of_measurement(self) -> str | None:
        # Mirrors native_value: hide the configured unit whenever there's
        # nothing to show, so the placeholder "-" above is never paired
        # with a unit Home Assistant would try to numerically validate.
        if self.coordinator.data is not None and self.coordinator.data.get(self._data_key) is None:
            return None
        return self._attr_native_unit_of_measurement
