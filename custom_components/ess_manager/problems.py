"""Problem notices in Settings > Repairs (as of 2026.10.23).

A problem has to last a while before it becomes a notice (a sensor that's
briefly unavailable after a restart isn't worth one), and the notice goes
away by itself as soon as the problem is over. One notice per kind per
installation; its text says what's wrong and what to check.

Kinds:
- control_write_failed: direct control can't send the setpoint (the target
  entity is unavailable, gone, or the service call fails) - 5 minutes.
- input_unavailable: the battery SOC or price sensor has no usable value,
  so nothing is planned (and direct control idles) - 15 minutes.
- solar_unreadable: a solar forecast sensor is available but has no
  forecast the integration can read - 15 minutes.
- battery_below_minimum: even with the plans, the battery is expected to
  drop below its minimum within the hours that have prices - 30 minutes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PROBLEM_DELAYS = {
    "control_write_failed": timedelta(minutes=5),
    "input_unavailable": timedelta(minutes=15),
    "solar_unreadable": timedelta(minutes=15),
    "battery_below_minimum": timedelta(minutes=30),
}
PROBLEM_KINDS = tuple(PROBLEM_DELAYS)
LEARN_MORE = "https://github.com/MisterX-RC/ESS-manager-HA#problem-notices"


def problem_issue_id(kind: str, entry_id: str) -> str:
    return f"{kind}_{entry_id}"


def below_minimum(
    forecast: list[Any], floor_kwh: float, hours: int, tolerance_kwh: float
) -> Optional[tuple[int, float]]:
    """The first hour (1..hours) the planned battery level runs into a dip
    below floor - tolerance, as (hour, kWh); None when it doesn't. Entry i
    of `forecast` is the level at the end of hour i. A level that is
    recovering (rising) towards the floor isn't a new dip - right after a
    power cut the battery can be below the minimum with a charge planned."""
    limit = floor_kwh - tolerance_kwh
    for i in range(1, min(hours, len(forecast))):
        level, before = forecast[i], forecast[i - 1]
        if level is None or before is None:
            continue
        if level < limit and level < before:
            return i, float(level)
    return None


class ProblemTracker:
    """When each problem started, and which notices are up."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._since: dict[str, datetime] = {}
        self._raised: dict[str, dict[str, str]] = {}

    def report(self, kind: str, active: bool, now: datetime, placeholders: Optional[dict[str, Any]] = None) -> None:
        """This cycle's state of one problem."""
        issue_id = problem_issue_id(kind, self.entry.entry_id)
        if not active:
            self._since.pop(kind, None)
            if kind in self._raised:
                del self._raised[kind]
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                _LOGGER.info("ESS Manager (%s): problem over - %s", self.entry.title, kind)
            return
        since = self._since.setdefault(kind, now)
        if now - since < PROBLEM_DELAYS[kind]:
            return
        values = {"entry_title": self.entry.title, **{k: str(v) for k, v in (placeholders or {}).items()}}
        if self._raised.get(kind) == values:
            return
        new = kind not in self._raised
        self._raised[kind] = values
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING if kind != "control_write_failed" else ir.IssueSeverity.ERROR,
            translation_key=kind,
            translation_placeholders=values,
            learn_more_url=LEARN_MORE,
        )
        if new:
            _LOGGER.warning("ESS Manager (%s): problem notice - %s %s", self.entry.title, kind, values)

    def active(self) -> dict[str, Any]:
        """For the diagnostics / Status: what's going on, and since when."""
        return {
            kind: {"since": since.isoformat(timespec="seconds"), "notice": kind in self._raised}
            for kind, since in self._since.items()
        }

    def clear_all(self) -> None:
        for kind in PROBLEM_KINDS:
            ir.async_delete_issue(self.hass, DOMAIN, problem_issue_id(kind, self.entry.entry_id))
        self._since.clear()
        self._raised.clear()
