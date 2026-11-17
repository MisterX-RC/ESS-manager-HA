"""Manual EV charging (as of 2026.11.52).

The "EV charger control" switch: on, ESS Manager drives the EV charger as
the plugged-in car's plan says (as before). Off, the plan is still worked
out and shown, but nothing is sent to the charger and no EV notifications
go out: the card's buttons Slow / Fast / Off drive it by hand instead - one
command each time a button is pressed, after that the charger is left alone.

Switching Automatic control (the battery) off switches this one off too
(the plan can't be followed without the battery's setpoint), and it can't
be switched on while Automatic control is off.

Where a manual charge comes from (`source`): from the grid - while the
battery is steered, the grid setpoint goes up by what the car takes (as in a
planned grid window), so the house battery stays out of it - or from the
battery (no offset: the car counts as house usage).

Pure functions only (no Home Assistant), so the pipeline tests can call them.
"""
from __future__ import annotations

from typing import Any, Optional

from . import ev_charger as evc

ACTION_SLOW = "slow"
ACTION_FAST = "fast"
ACTION_OFF = "off"
ACTIONS = (ACTION_SLOW, ACTION_FAST, ACTION_OFF)

SOURCE_GRID = "grid"
SOURCE_BATTERY = "battery"
SOURCES = (SOURCE_GRID, SOURCE_BATTERY)
DEFAULT_SOURCE = SOURCE_GRID

# the zappi's mode per button
ZAPPI_MODES = {ACTION_SLOW: evc.ZAPPI_ECO, ACTION_FAST: evc.ZAPPI_FAST, ACTION_OFF: evc.ZAPPI_STOPPED}


def active_action(charger: Optional[str], mode: Optional[str], charge_on: Optional[bool],
                  current_a: Optional[float], min_a: float, max_a: float) -> Optional[str]:
    """Which button the charger's own state matches (so a change made on the
    charger or in its app shows too); None when none does or it can't be read.

    zappi: Eco -> slow, Fast -> fast, Stopped -> off (Eco+ matches none).
    Victron: charging switched off -> off; on in manual mode at the minimum
    current -> slow, at the maximum -> fast (min = max: fast); otherwise none.
    """
    if charger == evc.CHARGER_ZAPPI:
        for action, zmode in ZAPPI_MODES.items():
            if mode == zmode:
                return action
        return None
    if charge_on is None:
        return None
    if not charge_on:
        return ACTION_OFF
    if mode != evc.MODE_MANUAL or current_a is None:
        return None
    if abs(current_a - max_a) < 0.5:
        return ACTION_FAST
    if abs(current_a - min_a) < 0.5:
        return ACTION_SLOW
    return None


def victron_target(action: str, min_a: float, max_a: float) -> dict[str, Any]:
    """The Victron charger's values for a button, in charger_target's shape:
    slow / fast = manual mode at the minimum / maximum current, charging on;
    off = charging off (the mode is left as it is)."""
    if action == ACTION_OFF:
        return {"mode": None, "charge": False, "current": None, "why": "manual_off"}
    current = min_a if action == ACTION_SLOW else max_a
    return {"mode": evc.MODE_MANUAL, "charge": True, "current": int(round(current)), "why": f"manual_{action}"}


def grid_offset_kw(source: str, power_w: Optional[float]) -> float:
    """What the grid setpoint goes up by during a manual charge (kW): what
    the car takes now when it comes from the grid, else 0."""
    if source != SOURCE_GRID or not power_w or power_w <= evc.CHARGING_W:
        return 0.0
    return round(power_w / 1000.0, 1)
