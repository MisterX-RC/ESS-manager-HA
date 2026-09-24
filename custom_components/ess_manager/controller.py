"""Direct control - the Home Assistant side: sends the setpoint that
control.py worked out to the user's number/input_number entity.

Safety rules (as of v0.2.14):
- Nothing is sent unless a control mode is chosen in Configure AND the
  "Automatic control" switch is on. Turning the switch off sends idle once,
  then leaves the target alone so it can be controlled by hand.
- Fail-safe: when an update fails (SOC unavailable, price sensor missing,
  an unexpected error), idle is sent instead of leaving the last command
  running unsupervised.
- Idle is sent when the integration is unloaded/removed and when Home
  Assistant stops.
- Values are clamped to the battery's max charge/discharge speed (control.py)
  and to the target number entity's own min/max.
- A failed send never fails the update itself; it's logged and shown in the
  Status sensor's `control` attribute (last_error).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import control
from .const import (
    CONF_CONTROL_IDLE_VALUE,
    CONF_CONTROL_MODE,
    CONF_CONTROL_SIGN,
    CONF_CONTROL_TARGET_ENTITY,
    CONF_CONTROL_UNIT,
    CONTROL_MODE_NUMBER,
    CONTROL_MODE_OFF,
    DEFAULT_CONTROL_IDLE_VALUE,
    DEFAULT_CONTROL_MODE,
    DEFAULT_CONTROL_SIGN,
    DEFAULT_CONTROL_UNIT,
)

_LOGGER = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 10


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ControlSettings:
    """The direct-control part of the entry's config, read fresh each cycle
    (Configure changes don't reload the integration)."""

    def __init__(self, conf: dict[str, Any]) -> None:
        # Only "off" and "number" exist; anything else stored (the "script"
        # mode that existed only in v0.2.14) is treated as off.
        stored_mode = conf.get(CONF_CONTROL_MODE) or DEFAULT_CONTROL_MODE
        self.mode: str = stored_mode if stored_mode in (CONTROL_MODE_OFF, CONTROL_MODE_NUMBER) else CONTROL_MODE_OFF
        self.target: Optional[str] = conf.get(CONF_CONTROL_TARGET_ENTITY) or None
        self.unit: str = conf.get(CONF_CONTROL_UNIT) or DEFAULT_CONTROL_UNIT
        self.sign: str = conf.get(CONF_CONTROL_SIGN) or DEFAULT_CONTROL_SIGN
        idle = _float_or_none(conf.get(CONF_CONTROL_IDLE_VALUE))
        self.idle_value: float = DEFAULT_CONTROL_IDLE_VALUE if idle is None else idle

    @property
    def active(self) -> bool:
        """Sending to a number/input_number entity."""
        return self.mode == CONTROL_MODE_NUMBER and bool(self.target)

    @property
    def idle_power_w(self) -> float:
        """The idle value expressed as a readback in W (+ = charge)."""
        return control.output_to_power_w(self.idle_value, self.unit, self.sign)


class EssController:
    """Owns what was sent, to which target, and when."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.hass = hass
        self.name = name
        # Set by the "Automatic control" switch when it's added (restored
        # state, default on). False until then, so nothing is ever sent
        # before the switch exists.
        self.enabled: bool = False
        self._last_target: Optional[str] = None
        self._last_sent: Optional[float] = None
        self._last_sent_at: Optional[datetime] = None
        self._last_action: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_reason: Optional[str] = None
        self._lock = asyncio.Lock()

    # -- readback -------------------------------------------------------------
    def readback_power_w(self, settings: ControlSettings) -> Optional[float]:
        """The target number entity's current value as a setpoint readback
        (W, + = charge) - used for the Status when no separate readback
        sensor is configured. None when there's nothing to go on.
        """
        if not settings.active:
            return None
        value = self._entity_value(settings.target)
        if value is None:
            return None
        return control.output_to_power_w(value, settings.unit, settings.sign)

    def _entity_value(self, entity_id: Optional[str]) -> Optional[float]:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return _float_or_none(state.state)

    # -- sending --------------------------------------------------------------
    async def async_apply(
        self, settings: ControlSettings, action: str, power_kw: float, reason: str
    ) -> None:
        """One cycle: send the value for `action` if control is on and the
        target doesn't already have it."""
        async with self._lock:
            await self._async_release_previous_target(settings)
            if not settings.active or not self.enabled:
                return
            desired = control.command_value(action, power_kw, settings.unit, settings.sign, settings.idle_value)
            await self._async_send(settings, desired, action, reason)

    async def async_idle(self, settings: ControlSettings, reason: str, force: bool = False) -> None:
        """Send idle (fail-safe, switch off, unload, shutdown). `force` sends
        even while the switch is off - used by the switch itself when it's
        turned off."""
        async with self._lock:
            await self._async_release_previous_target(settings)
            if not settings.active or not (self.enabled or force):
                return
            await self._async_send(settings, settings.idle_value, control.ACTION_IDLE, reason)

    async def _async_release_previous_target(self, settings: ControlSettings) -> None:
        """If Configure switched to another target (or turned control off)
        while the old target still has a non-idle command, idle the old one
        once so it isn't left charging/discharging unattended."""
        new_target = settings.target if settings.active else None
        old_target = self._last_target
        if old_target is None or old_target == new_target:
            return
        if self._last_action not in (None, control.ACTION_IDLE):
            _LOGGER.info("ESS Manager (%s): control target changed - idling %s", self.name, old_target)
            try:
                await self._async_call_set_value(old_target, settings.idle_value)
            except Exception as err:  # noqa: BLE001 - best effort, logged
                _LOGGER.warning("ESS Manager (%s): could not idle previous target %s: %s", self.name, old_target, err)
        self._last_target = None
        self._last_sent = None
        self._last_sent_at = None
        self._last_action = None

    async def _async_send(self, settings: ControlSettings, desired: float, action: str, reason: str) -> None:
        target = settings.target
        assert target is not None
        now = dt_util.utcnow()
        state = self.hass.states.get(target)
        if state is None or state.state in ("unknown", "unavailable"):
            self._set_error(f"{target} is unavailable")
            return
        desired = control.clamp_to_range(
            desired, _float_or_none(state.attributes.get("min")), _float_or_none(state.attributes.get("max"))
        )
        tolerance = control.write_tolerance(desired, _float_or_none(state.attributes.get("step")))
        current = _float_or_none(state.state)

        last_sent = self._last_sent if self._last_target == target else None
        since = (now - self._last_sent_at).total_seconds() if self._last_sent_at and last_sent is not None else None
        if not control.needs_write(desired, last_sent, current, tolerance, since):
            self._last_action = action
            return

        try:
            await self._async_call_set_value(target, desired)
        except Exception as err:  # noqa: BLE001 - a failed send must not fail the update
            self._set_error(f"sending {desired} to {target} failed: {type(err).__name__}: {err}")
            return

        _LOGGER.info(
            "ESS Manager (%s): sent %s %s to %s (%s - %s)", self.name, desired, settings.unit, target, action, reason
        )
        self._last_target = target
        self._last_sent = desired
        self._last_sent_at = now
        self._last_action = action
        self._last_reason = reason
        self._last_error = None

    def _set_error(self, message: str) -> None:
        """Record a problem; log it once, not every 30-second cycle it lasts."""
        if message != self._last_error:
            _LOGGER.warning("ESS Manager (%s): %s", self.name, message)
        self._last_error = message

    async def _async_call_set_value(self, entity_id: str, value: float) -> None:
        domain = entity_id.split(".", 1)[0]
        if domain not in ("number", "input_number"):
            raise ValueError(f"{entity_id} is not a number or input_number entity")
        await asyncio.wait_for(
            self.hass.services.async_call(
                domain, "set_value", {"entity_id": entity_id, "value": value}, blocking=True
            ),
            SEND_TIMEOUT_SECONDS,
        )

    # -- reporting ------------------------------------------------------------
    def as_attribute(self, settings: ControlSettings, action: str, power_kw: float) -> dict[str, Any]:
        """The Status sensor's `control` attribute."""
        return {
            "mode": settings.mode,
            "target": settings.target if settings.active else None,
            "automatic_control": self.enabled,
            "sending": settings.active and self.enabled,
            "action": action,
            "planned_power_kw": round(power_kw, 3),
            "planned_value": control.command_value(
                action, power_kw, settings.unit, settings.sign, settings.idle_value
            ),
            "unit": settings.unit,
            "sign": settings.sign,
            "last_sent_value": self._last_sent,
            "last_sent_at": self._last_sent_at.isoformat() if self._last_sent_at else None,
            "last_sent_reason": self._last_reason,
            "last_error": self._last_error,
        }
