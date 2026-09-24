"""Direct control - the pure part (no Home Assistant imports, unit-tested in
tests/test_pipeline.py).

Every cycle the planning engines produce a Status plus a control *action*
(see plans.compute_system_status_and_action). This module turns that action
into the battery power it stands for, using the same speeds the plans were
sized with, and then into the exact value to send to the user's setpoint
entity (unit, sign convention, idle value). controller.py does the
actual sending.

Power convention inside the integration: kW, positive = charge the battery,
negative = discharge - the same convention the grid/inverter setpoint
readback has always used (see compute_system_status).
"""
from __future__ import annotations

import math
from typing import Optional

ACTION_IDLE = "idle"
ACTION_CHARGE = "charge"
ACTION_DISCHARGE = "discharge"
ACTION_NEGATIVE_PRICE_CHARGE = "negative_price_charge"
ACTION_SPIKE_DISCHARGE = "spike_discharge"

ACTIONS = (
    ACTION_IDLE,
    ACTION_CHARGE,
    ACTION_DISCHARGE,
    ACTION_NEGATIVE_PRICE_CHARGE,
    ACTION_SPIKE_DISCHARGE,
)

UNIT_W = "W"
UNIT_KW = "kW"

SIGN_CHARGE_POSITIVE = "charge_positive"
SIGN_DISCHARGE_POSITIVE = "discharge_positive"


def action_power_kw(
    action: str,
    charge_speed_kw: float,
    discharge_speed_kw: float,
    negative_price_charge_speed_kw: float,
    spike_discharge_speed_kw: float,
    max_charge_kw: float,
    max_discharge_kw: float,
) -> float:
    """The signed battery power (kW, + = charge) an action stands for.

    Each action uses the speed its plan was sized with - so the energy that
    actually moves matches what the plan expected - and is always clamped to
    the battery's own max charge/discharge speed from setup, whatever a plan
    asks for. Unknown actions are treated as idle.
    """
    max_charge_kw = max(float(max_charge_kw or 0.0), 0.0)
    max_discharge_kw = max(float(max_discharge_kw or 0.0), 0.0)
    if action == ACTION_CHARGE:
        return min(max(charge_speed_kw, 0.0), max_charge_kw)
    if action == ACTION_NEGATIVE_PRICE_CHARGE:
        return min(max(negative_price_charge_speed_kw, 0.0), max_charge_kw)
    if action == ACTION_DISCHARGE:
        return -min(max(discharge_speed_kw, 0.0), max_discharge_kw)
    if action == ACTION_SPIKE_DISCHARGE:
        return -min(max(spike_discharge_speed_kw, 0.0), max_discharge_kw)
    return 0.0


def power_to_output(power_kw: float, unit: str, sign: str) -> float:
    """Signed battery power (kW, + = charge) -> the value in the output's
    own unit and sign convention."""
    value = power_kw * 1000.0 if unit == UNIT_W else power_kw
    if sign == SIGN_DISCHARGE_POSITIVE:
        value = -value
    return round(value, 0 if unit == UNIT_W else 3) + 0.0  # + 0.0 turns -0.0 into 0.0


def output_to_power_w(value: float, unit: str, sign: str) -> float:
    """The reverse of power_to_output, in W - used to read a number entity
    back as the setpoint when no separate readback sensor is configured."""
    watts = value if unit == UNIT_W else value * 1000.0
    if sign == SIGN_DISCHARGE_POSITIVE:
        watts = -watts
    return watts + 0.0


def command_value(action: str, power_kw: float, unit: str, sign: str, idle_value: float) -> float:
    """The exact value to send. Idle sends the configured idle value as-is
    (already in the output's own unit and sign, e.g. 0 or -30), never a
    converted one."""
    if action == ACTION_IDLE or power_kw == 0:
        return float(idle_value)
    return power_to_output(power_kw, unit, sign)


def clamp_to_range(value: float, minimum: Optional[float], maximum: Optional[float]) -> float:
    """Keep a value inside a number entity's own min/max, so the write
    can't be rejected (or, worse, silently ignored) by the target entity."""
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def write_tolerance(value: float, step: Optional[float]) -> float:
    """How far an entity's state may be from the value we sent and still
    count as 'already set' - half a step (entities round to their step), and
    never less than a tiny float epsilon."""
    if step is not None and step > 0 and math.isfinite(step):
        return max(step / 2.0, 1e-6)
    return 1e-6


def needs_write(
    desired: float,
    last_sent: Optional[float],
    current_state: Optional[float],
    tolerance: float,
    seconds_since_last_send: Optional[float],
    resend_after_seconds: float = 60.0,
) -> bool:
    """Whether to send `desired` this cycle.

    - Always when it differs from what we last sent (or nothing was sent
      yet, e.g. right after a restart).
    - For a target we can read back (`current_state` not None): also when
      the entity no longer shows it - someone or something else changed it -
      but at most once per `resend_after_seconds`, so an entity that lags or
      rounds differently isn't rewritten every 30-second cycle.
    """
    if last_sent is None or abs(desired - last_sent) > tolerance:
        return True
    if current_state is None:
        return False
    if abs(current_state - desired) <= tolerance:
        return False
    return seconds_since_last_send is None or seconds_since_last_send >= resend_after_seconds
