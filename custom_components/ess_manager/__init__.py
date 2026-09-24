"""The ESS Manager integration - battery/solar/price-aware charge and
discharge planning, ported from a hand-written Home Assistant template
sensor into a configurable, HACS-installable custom integration.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_CONTROL_MODE,
    CONF_NAME,
    CONF_USAGE_SOURCE,
    CONTROL_MODE_REMOVED_SCRIPT,
    DEFAULT_NAME,
    DEPRECATED_USAGE_SOURCES,
    DOMAIN,
    LEGACY_DEFAULT_USAGE_SOURCE,
    PLATFORMS,
    USAGE_SOURCE_LABELS,
)
from .coordinator import EssManagerCoordinator

_LOGGER = logging.getLogger(__name__)

README_USAGE_URL = "https://github.com/MisterX-RC/ESS-manager-HA#household-usage-forecast"


def _deprecated_source_issue_id(entry: ConfigEntry) -> str:
    return f"deprecated_usage_source_{entry.entry_id}"


def _async_update_deprecation_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Show a Repairs notice (Settings -> System -> Repairs) while this
    installation uses a deprecated usage source, and remove it as soon as it
    doesn't. Runs at setup and after every Configure change, so switching
    source clears the notice straight away. DEPRECATED handling - in 0.3.0
    this becomes a hard error for any entry still on a removed source.
    """
    conf = {**entry.data, **entry.options}
    source = conf.get(CONF_USAGE_SOURCE, LEGACY_DEFAULT_USAGE_SOURCE)
    issue_id = _deprecated_source_issue_id(entry)
    if source in DEPRECATED_USAGE_SOURCES:
        _LOGGER.warning(
            "ESS Manager (%s): usage source '%s' is deprecated and will be removed in 0.3.0 - "
            "switch to the Energy dashboard or a consumption sensor in Configure",
            entry.title,
            source,
        )
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_usage_source",
            translation_placeholders={
                "entry_title": entry.title,
                "source": USAGE_SOURCE_LABELS.get(source, source),
            },
            learn_more_url=README_USAGE_URL,
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


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

    async def _async_idle_on_stop(_event: Event) -> None:
        # Direct control: nobody supervises the battery while Home Assistant
        # is down, so don't leave a charge/discharge command running.
        await coordinator.controller.async_idle(coordinator.control_settings(), "Home Assistant stopping")

    entry.async_on_unload(hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, _async_idle_on_stop))

    _async_update_deprecation_issue(hass, entry)

    if {**entry.data, **entry.options}.get(CONF_CONTROL_MODE) == CONTROL_MODE_REMOVED_SCRIPT:
        _LOGGER.warning(
            "ESS Manager (%s): the 'Run a script' control option was removed in 0.2.15, so direct control "
            "is off - choose a number / input_number entity in Configure to turn it back on",
            entry.title,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Direct control: idle the target before the integration stops
    # supervising it (unload, reload, disable, remove).
    coordinator: EssManagerCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
    if coordinator is not None:
        await coordinator.controller.async_idle(coordinator.control_settings(), "integration unloaded")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Deleting the installation also clears its Repairs notice, if any."""
    ir.async_delete_issue(hass, DOMAIN, _deprecated_source_issue_id(entry))


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed (e.g. re-pointed an entity) - just refresh; entity
    references are re-read from entry.data/entry.options on every cycle so
    no reload is needed.
    """
    coordinator: EssManagerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    _async_update_deprecation_issue(hass, entry)
    coordinator.invalidate_usage_forecast()
    await coordinator.async_request_refresh()
