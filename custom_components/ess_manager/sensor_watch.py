"""Sensors that stop updating (as of 2026.10.44).

A sensor whose integration lost its connection often keeps its last value
instead of going unavailable - and then ESS Manager would keep steering on a
battery level or a battery power that's no longer true. Two signs:

- **No new report for too long**: the battery SOC for more than
  SOC_STALE_S, the battery's power for more than POWER_STALE_S while the
  setpoint follows it (House from grid / Solar export). Only for a sensor
  that is known to report regularly - one whose `last_reported` was seen
  later than its `last_updated`, so it reports even when nothing changed.
  A sensor that only reports changes keeps the same value for hours when
  the battery stands still, which says nothing.
- **Flat while steered**: the setpoint changed FLAT_STEPS times in a row and
  the battery's power stayed exactly the same (and at least FLAT_MIN_W) - a
  real battery always moves a little. For a sensor that reports regularly a
  step only counts after a new report with that same value (a slow poller
  isn't stuck); for one that only reports changes, a step without any new
  value counts.

It's over as soon as the sensor reports again (stale) or its value changes
(flat). Pure Python - no Home Assistant needed (tested in test_pipeline).
"""
from __future__ import annotations

from typing import Any, Optional

SOC_STALE_S = 600.0
POWER_STALE_S = 120.0
FLAT_STEPS = 4
FLAT_MIN_W = 50.0


class SensorWatch:
    """What's known about each watched sensor."""

    def __init__(self) -> None:
        self._periodic: set[str] = set()
        # entity -> (power seen at the last loop step, its report time, steps flat)
        self._flat: dict[str, tuple[float, Optional[float], int]] = {}
        # entity -> the value it got stuck at
        self._stuck: dict[str, float] = {}

    def is_periodic(self, entity_id: str) -> bool:
        return entity_id in self._periodic

    def stale(self, entity_id: Optional[str], reported_ts: Optional[float], updated_ts: Optional[float],
              now_ts: float, limit_s: float) -> bool:
        """No report for more than `limit_s` from a sensor known to report
        regularly."""
        if not entity_id or reported_ts is None:
            return False
        if updated_ts is not None and reported_ts - updated_ts > 0.5:
            self._periodic.add(entity_id)
        return entity_id in self._periodic and now_ts - reported_ts > limit_s

    def loop_step(self, entity_id: Optional[str], before_kw: float, after_kw: float,
                  power_w: Optional[float], reported_ts: Optional[float]) -> None:
        """One step of a setpoint loop: the setpoint went from `before_kw` to
        `after_kw` on a battery power reading of `power_w`."""
        if not entity_id or power_w is None:
            return
        last = self._flat.get(entity_id)
        if last is None or power_w != last[0] or abs(power_w) < FLAT_MIN_W:
            self._flat[entity_id] = (power_w, reported_ts, 0)
            return
        steps = last[2]
        if after_kw != before_kw:
            new_report = reported_ts is not None and last[1] is not None and reported_ts > last[1]
            if new_report or entity_id not in self._periodic:
                steps += 1
        self._flat[entity_id] = (power_w, reported_ts, steps)
        if steps >= FLAT_STEPS:
            self._stuck[entity_id] = power_w

    def stuck(self, entity_id: Optional[str], power_w: Optional[float]) -> bool:
        """Still stuck at the value it froze at; over once it changes."""
        if not entity_id or entity_id not in self._stuck:
            return False
        if power_w is not None and power_w != self._stuck[entity_id]:
            del self._stuck[entity_id]
            self._flat.pop(entity_id, None)
            return False
        return True

    def leave_loop(self, entity_id: Optional[str]) -> None:
        """The loop stopped: the flat count starts over next time (a value
        it's stuck at is kept until it changes)."""
        if entity_id:
            self._flat.pop(entity_id, None)

    def as_dict(self) -> dict[str, Any]:
        """For the diagnostics."""
        return {"periodic": sorted(self._periodic), "stuck": dict(self._stuck),
                "flat_steps": {k: v[2] for k, v in self._flat.items() if v[2]}}
