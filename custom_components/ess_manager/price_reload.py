"""Reload the integration behind the price sensor when it has no prices.

A price integration (e.g. Nord Pool) sometimes leaves its sensor unavailable
until it's reloaded by hand. Without prices nothing can be planned, so when
the configured price sensor has had no usable value for a while, the config
entry the sensor belongs to (looked up in the entity registry - no setting)
is reloaded, the same as "Reload" on the integration's page.

Timing:
- the first reload once the prices are missing for FIRST_AFTER, and never
  within STARTUP_WAIT of ESS Manager's own start or while Home Assistant is
  still starting;
- if the prices don't come back, again after the next delay in BACKOFF,
  then every BACKOFF[-1];
- a reload is skipped while that entry is loading/unloading or disabled;
- as soon as the prices are back, it starts over.

A sensor that doesn't belong to a config entry (a YAML template, say) is
never reloaded; that is logged once.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

FIRST_AFTER = timedelta(minutes=5)
STARTUP_WAIT = timedelta(minutes=10)
# wait after the 1st, 2nd, 3rd reload; the last one repeats
BACKOFF = (timedelta(minutes=15), timedelta(minutes=30), timedelta(minutes=60))

_BUSY_STATES = (ConfigEntryState.SETUP_IN_PROGRESS, ConfigEntryState.UNLOAD_IN_PROGRESS)


def next_reload_at(since: datetime, started_at: datetime, attempts: int, last: Optional[datetime]) -> datetime:
    """When the next reload is due: the first FIRST_AFTER after the prices
    went missing (not before STARTUP_WAIT after the start), then BACKOFF."""
    if attempts == 0 or last is None:
        return max(since + FIRST_AFTER, started_at + STARTUP_WAIT)
    return last + BACKOFF[min(attempts - 1, len(BACKOFF) - 1)]


def price_missing(state: Any) -> bool:
    """The same test as the price check of the cycle: no state, unavailable /
    unknown, or no prices for today."""
    return state is None or state.state in ("unavailable", "unknown") or not state.attributes.get("today")


class PriceReloader:
    """Per installation: whether the prices are missing, and the reloads."""

    def __init__(self, hass: HomeAssistant, title: str, own_entry_id: str) -> None:
        self.hass = hass
        self.title = title
        self.own_entry_id = own_entry_id
        self.since: Optional[datetime] = None
        self.attempts = 0
        self.last_at: Optional[datetime] = None
        self.last_result: Optional[str] = None
        self.entry_id: Optional[str] = None
        self.entry_title: Optional[str] = None
        self._running = False
        self._no_entry_logged: Optional[str] = None

    def _owner(self, price_id: str) -> Any:
        reg_entry = er.async_get(self.hass).async_get(price_id)
        entry_id = reg_entry.config_entry_id if reg_entry is not None else None
        if not entry_id or entry_id == self.own_entry_id:
            return None
        return self.hass.config_entries.async_get_entry(entry_id)

    def step(self, price_id: Optional[str], missing: bool, now: datetime, started_at: datetime,
             create_task: Optional[Callable[[Any], Any]] = None) -> None:
        """Called every cycle with whether the prices are missing now."""
        if not missing or not price_id:
            if self.since is not None and self.attempts:
                _LOGGER.info("ESS Manager (%s): prices back after %d reload(s) of %s",
                             self.title, self.attempts, self.entry_title or self.entry_id)
            self.since = None
            self.attempts = 0
            self.last_at = None
            return
        if self.since is None:
            self.since = now
        if self._running or self.hass.state is not CoreState.running:
            return
        if now < next_reload_at(self.since, started_at, self.attempts, self.last_at):
            return
        entry = self._owner(price_id)
        if entry is None:
            if self._no_entry_logged != price_id:
                self._no_entry_logged = price_id
                _LOGGER.warning(
                    "ESS Manager (%s): %s has no prices, but it doesn't belong to an integration "
                    "ESS Manager can reload - check it yourself", self.title, price_id)
            self.last_result = "no_integration"
            return
        self.entry_id = entry.entry_id
        self.entry_title = entry.title
        if entry.disabled_by is not None:
            self.last_result = "disabled"
            return
        if entry.state in _BUSY_STATES:
            self.last_result = "busy"
            return
        self.attempts += 1
        self.last_at = now
        self._running = True
        _LOGGER.warning(
            "ESS Manager (%s): %s has had no prices since %s - reloading %s (%s), attempt %d",
            self.title, price_id, self.since.isoformat(timespec="minutes"), entry.title, entry.domain,
            self.attempts)
        (create_task or self.hass.async_create_task)(self._async_reload(entry.entry_id))

    async def _async_reload(self, entry_id: str) -> None:
        try:
            ok = await self.hass.config_entries.async_reload(entry_id)
            self.last_result = "ok" if ok else "not_loaded"
        except Exception as err:  # noqa: BLE001 - whatever the other integration raises
            self.last_result = f"failed: {err}"
            _LOGGER.warning("ESS Manager (%s): reloading the price integration failed: %s", self.title, err)
        finally:
            self._running = False

    def as_diag(self) -> dict[str, Any]:
        return {
            "missing_since": self.since.isoformat(timespec="seconds") if self.since else None,
            "attempts": self.attempts,
            "last_at": self.last_at.isoformat(timespec="seconds") if self.last_at else None,
            "last_result": self.last_result,
            "entry_id": self.entry_id,
            "entry_title": self.entry_title,
        }
