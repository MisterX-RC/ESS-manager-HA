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
    CONTROL_MODE_OFF,
    CONTROL_MODE_NUMBER,
    DEFAULT_NAME,
    DOMAIN,
    PLATFORMS,
    REMOVED_CONFIG_KEYS,
    REMOVED_USAGE_SOURCE_LABELS,
    REMOVED_USAGE_SOURCES,
    SUPPORTED_USAGE_SOURCES,
    USAGE_SOURCE_ENERGY_DASHBOARD,
)
from .coordinator import EssManagerCoordinator
from .energy_source import async_get_energy_prefs
from .usage_forecast import energy_prefs_to_sources

_LOGGER = logging.getLogger(__name__)

README_USAGE_URL = "https://github.com/MisterX-RC/ESS-manager-HA#household-usage-forecast"


def _issue_id(kind: str, entry: ConfigEntry) -> str:
    return f"{kind}_{entry.entry_id}"


# Repairs issue ids used by this integration, per entry. The v0.2.10-0.2.20
# "deprecated_usage_source" notice is only listed so it gets cleaned up.
_ISSUE_KINDS = ("usage_source_switched", "usage_source_removed", "deprecated_usage_source")


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 -> v2 (ESS Manager 0.3.0): the external h0..h120 sensor and the
    hand-picked statistics usage sources are gone.

    - Their config keys are dropped from data and options.
    - An entry on one of them (or with no usage_source at all, which has
      always meant the external sensor) is switched to the Energy dashboard
      source when the Energy dashboard has a grid source, with a Repairs
      notice asking to check the forecast. Otherwise its source stays as it
      was, so setup shows a Repairs error until a source is picked in
      Configure (see _async_update_usage_source_issue) - it never silently
      plans with zero household usage.
    - The v0.2.14-only "script" control mode becomes "off" (it has counted
      as off since v0.2.15).
    """
    if entry.version > 2:
        return False  # a newer ESS Manager was installed before - don't guess
    if entry.version == 2:
        return True

    data = {k: v for k, v in entry.data.items() if k not in REMOVED_CONFIG_KEYS}
    options = {k: v for k, v in entry.options.items() if k not in REMOVED_CONFIG_KEYS}
    for part in (data, options):
        if part.get(CONF_CONTROL_MODE) not in (None, CONTROL_MODE_OFF, CONTROL_MODE_NUMBER):
            part[CONF_CONTROL_MODE] = CONTROL_MODE_OFF

    source = {**entry.data, **entry.options}.get(CONF_USAGE_SOURCE) or "external_sensor"
    if source in REMOVED_USAGE_SOURCES:
        sources = energy_prefs_to_sources(await async_get_energy_prefs(hass))
        if sources["import"]:
            data[CONF_USAGE_SOURCE] = USAGE_SOURCE_ENERGY_DASHBOARD
            if CONF_USAGE_SOURCE in options:
                options[CONF_USAGE_SOURCE] = USAGE_SOURCE_ENERGY_DASHBOARD
            _LOGGER.warning(
                "ESS Manager (%s): usage source '%s' was removed in 0.3.0 - switched to the Energy dashboard",
                entry.title,
                source,
            )
            ir.async_create_issue(
                hass,
                DOMAIN,
                _issue_id("usage_source_switched", entry),
                is_fixable=False,
                is_persistent=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="usage_source_switched",
                translation_placeholders={
                    "entry_title": entry.title,
                    "source": REMOVED_USAGE_SOURCE_LABELS.get(source, source),
                },
                learn_more_url=README_USAGE_URL,
            )
        else:
            # Keep it explicit, so the Repairs error can name it.
            data[CONF_USAGE_SOURCE] = source

    hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
    _LOGGER.info("ESS Manager (%s): configuration migrated to version 2", entry.title)
    return True


def _async_update_usage_source_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A Repairs error while this entry has no supported usage source (only
    possible after a v2 migration that couldn't switch automatically);
    removed as soon as one is chosen. Also clears the pre-0.3.0 deprecation
    notice.
    """
    ir.async_delete_issue(hass, DOMAIN, _issue_id("deprecated_usage_source", entry))
    source = {**entry.data, **entry.options}.get(CONF_USAGE_SOURCE)
    issue_id = _issue_id("usage_source_removed", entry)
    if source in SUPPORTED_USAGE_SOURCES:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="usage_source_removed",
        translation_placeholders={
            "entry_title": entry.title,
            "source": REMOVED_USAGE_SOURCE_LABELS.get(source, str(source)),
        },
        learn_more_url=README_USAGE_URL,
    )


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

    # Before the first refresh: with no supported usage source that refresh
    # fails (setup is then retried), and the Repairs error must already be
    # there to say why.
    _async_update_usage_source_issue(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _async_idle_on_stop(_event: Event) -> None:
        # Direct control: nobody supervises the battery while Home Assistant
        # is down, so don't leave a charge/discharge command running.
        await coordinator.controller.async_idle(coordinator.control_settings(), "Home Assistant stopping")

    entry.async_on_unload(hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, _async_idle_on_stop))

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
    """Deleting the installation also clears its Repairs notices, if any."""
    for kind in _ISSUE_KINDS:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(kind, entry))


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed (e.g. re-pointed an entity) - just refresh; entity
    references are re-read from entry.data/entry.options on every cycle so
    no reload is needed.
    """
    coordinator: EssManagerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    _async_update_usage_source_issue(hass, entry)
    # Saving Configure means the usage source has been looked at - the
    # "switched automatically" notice from the v2 migration has done its job.
    ir.async_delete_issue(hass, DOMAIN, _issue_id("usage_source_switched", entry))
    coordinator.invalidate_usage_forecast()
    await coordinator.async_request_refresh()
