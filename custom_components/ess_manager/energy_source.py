"""Reads Home Assistant's own Energy dashboard configuration, for the
"Use my Energy dashboard" usage-forecast source.

The only HA-dependent half of that feature: fetching the raw preferences
dict. Turning it into the statistic-id lists the energy-balance identity
needs is `usage_forecast.energy_prefs_to_sources`, a pure function that's
unit-tested without Home Assistant.

`homeassistant.components.energy.data.async_get_manager` is an internal
Home Assistant interface, not a published integration API, and its data
shape has changed before (grid sources moved from `flow_from`/`flow_to`
arrays to one entry per connection) - so every failure here is caught and
reported as "no prefs available" rather than allowed to break the
coordinator's update. energy_prefs_to_sources handles both grid shapes.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_get_energy_prefs(hass: HomeAssistant) -> Optional[dict[str, Any]]:
    """The Energy dashboard preferences, or None if the energy integration
    isn't loaded, nothing has been configured yet, or HA's internal
    interface has changed in a way this integration doesn't recognize.
    """
    try:
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
        data = manager.data
    except Exception as err:  # noqa: BLE001 - internal HA API; degrade, don't crash
        _LOGGER.warning("ESS Manager: could not read the Energy dashboard configuration: %s", err)
        return None
    if not data:
        return None
    return dict(data)
