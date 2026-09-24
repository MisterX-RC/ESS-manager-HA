"""Standalone test for direct control's sending logic (controller.py) with a
stubbed Home Assistant - no real HA needed. Checks what is sent, when, and
the safety rules (switch off, fail-safe idle, clamping, re-send limits,
target changes, errors never raising).

Run with: python3 tests/test_controller.py   (from the repo root)
"""
import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG_DIR = os.path.join(_REPO_ROOT, "custom_components", "ess_manager")

# -- Home Assistant stubs ------------------------------------------------------
_clock = {"now": datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)}


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


_mod("homeassistant")
_mod("homeassistant.core", HomeAssistant=object)
_mod("homeassistant.util")
_mod("homeassistant.util.dt", utcnow=lambda: _clock["now"], now=lambda: _clock["now"])
sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]

_pkg = types.ModuleType("ess_ctrl")
_pkg.__path__ = [_PKG_DIR]
sys.modules["ess_ctrl"] = _pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"ess_ctrl.{name}", os.path.join(_PKG_DIR, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"ess_ctrl.{name}"] = module
    spec.loader.exec_module(module)
    return module


_load("const")
control = _load("control")
controller = _load("controller")


class State:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class States:
    def __init__(self):
        self.data = {}

    def get(self, entity_id):
        return self.data.get(entity_id)


class Services:
    def __init__(self, hass):
        self.hass = hass
        self.calls = []
        self.fail = False

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, dict(data)))
        if self.fail:
            raise RuntimeError("inverter offline")
        # A number entity takes the value it's given (like the real thing).
        if service == "set_value":
            old = self.hass.states.get(data["entity_id"])
            self.hass.states.data[data["entity_id"]] = State(str(data["value"]), old.attributes if old else {})


class Hass:
    def __init__(self):
        self.states = States()
        self.services = Services(self)


FAILURES = []


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        FAILURES.append(label)


NUMBER_CONF = {
    "control_mode": "number",
    "control_target_entity": "number.grid_setpoint",
    "control_unit": "W",
    "control_sign": "charge_positive",
    "control_idle_value": 0,
}


async def main():
    hass = Hass()
    hass.states.data["number.grid_setpoint"] = State("0", {"min": -15000, "max": 15000, "step": 1})
    c = controller.EssController(hass, "Test")
    settings = controller.ControlSettings(NUMBER_CONF)

    # Switch not on yet (enabled False until the switch restores) -> nothing.
    await c.async_apply(settings, control.ACTION_CHARGE, 7.0, "Start charge")
    check("nothing is sent before the Automatic control switch is on", hass.services.calls == [])

    c.enabled = True
    await c.async_apply(settings, control.ACTION_CHARGE, 7.0, "Start charge")
    check(
        "charge sends 7000 W to the number entity",
        hass.services.calls == [("number", "set_value", {"entity_id": "number.grid_setpoint", "value": 7000.0})],
    )
    await c.async_apply(settings, control.ACTION_CHARGE, 7.0, "Actief")
    check("the same value isn't sent again while the entity already has it", len(hass.services.calls) == 1)

    # Someone else changes the entity: re-sent, but at most once a minute.
    hass.states.data["number.grid_setpoint"] = State("0", {"min": -15000, "max": 15000, "step": 1})
    _clock["now"] += timedelta(seconds=30)
    await c.async_apply(settings, control.ACTION_CHARGE, 7.0, "Actief")
    check("a changed entity isn't rewritten within a minute of the last send", len(hass.services.calls) == 1)
    _clock["now"] += timedelta(seconds=31)
    await c.async_apply(settings, control.ACTION_CHARGE, 7.0, "Actief")
    check("a changed entity is rewritten after a minute", len(hass.services.calls) == 2)

    # Discharge beyond the entity's own max is clamped.
    await c.async_apply(settings, control.ACTION_SPIKE_DISCHARGE, -20.0, "Start spike discharge")
    check("a value outside the entity's min/max is clamped", hass.services.calls[-1][2]["value"] == -15000)

    # Readback from the number entity (W, + = charge).
    check("the number entity reads back as the setpoint", c.readback_power_w(settings) == -15000.0)

    # Fail-safe idle.
    await c.async_idle(settings, "update failed: SOC unavailable")
    check("fail-safe sends the idle value", hass.services.calls[-1][2]["value"] == 0.0)
    n = len(hass.services.calls)
    await c.async_idle(settings, "update failed again")
    check("fail-safe doesn't resend idle when it's already idle", len(hass.services.calls) == n)

    # Switch off: nothing sent by apply; the switch's forced idle still goes out.
    await c.async_apply(settings, control.ACTION_DISCHARGE, -10.0, "Start discharge")
    c.enabled = False
    n = len(hass.services.calls)
    await c.async_apply(settings, control.ACTION_CHARGE, 7.0, "Start charge")
    check("with the switch off, apply sends nothing", len(hass.services.calls) == n)
    await c.async_idle(settings, "automatic control switched off", force=True)
    check("turning the switch off sends idle once", hass.services.calls[-1][2]["value"] == 0.0)
    c.enabled = True

    # Unavailable target: no call, error reported, no exception.
    hass.states.data["number.grid_setpoint"] = State("unavailable")
    n = len(hass.services.calls)
    await c.async_apply(settings, control.ACTION_CHARGE, 7.0, "Start charge")
    check("an unavailable target isn't written", len(hass.services.calls) == n)
    check("an unavailable target is reported", "unavailable" in (c.as_attribute(settings, "charge", 7.0)["last_error"] or ""))
    hass.states.data["number.grid_setpoint"] = State("0", {"min": -15000, "max": 15000, "step": 1})

    # A failing service call never raises.
    hass.services.fail = True
    try:
        await c.async_apply(settings, control.ACTION_DISCHARGE, -10.0, "Start discharge")
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
    hass.services.fail = False
    check("a failing send doesn't raise", raised is False)
    check("a failing send is reported", "inverter offline" in (c.as_attribute(settings, "discharge", -10.0)["last_error"] or ""))
    await c.async_apply(settings, control.ACTION_DISCHARGE, -10.0, "Start discharge")
    check("the next cycle retries after a failed send", hass.services.calls[-1][2]["value"] == -10000.0)
    check("a successful send clears the error", c.as_attribute(settings, "discharge", -10.0)["last_error"] is None)

    # Target changes in Configure while discharging: the old one is idled.
    new_settings = controller.ControlSettings({**NUMBER_CONF, "control_target_entity": "input_number.ess_kw", "control_unit": "kW"})
    hass.states.data["input_number.ess_kw"] = State("0", {"min": -20, "max": 20, "step": 0.1})
    await c.async_apply(new_settings, control.ACTION_DISCHARGE, -10.0, "Actief")
    check(
        "switching target idles the old one first",
        hass.services.calls[-2] == ("number", "set_value", {"entity_id": "number.grid_setpoint", "value": 0.0}),
    )
    check(
        "then the new target (kW) gets the command",
        hass.services.calls[-1] == ("input_number", "set_value", {"entity_id": "input_number.ess_kw", "value": -10.0}),
    )

    # Control switched off in Configure while discharging: target idled once.
    off_settings = controller.ControlSettings({**NUMBER_CONF, "control_mode": "off", "control_target_entity": "input_number.ess_kw"})
    await c.async_apply(off_settings, control.ACTION_DISCHARGE, -10.0, "Actief")
    check("turning control off in Configure idles the target once", hass.services.calls[-1][2]["value"] == 0.0)
    n = len(hass.services.calls)
    await c.async_apply(off_settings, control.ACTION_CHARGE, 7.0, "Start charge")
    check("with control off nothing more is sent", len(hass.services.calls) == n)

    # Script mode: sent on change only (no readback), with variables.
    hass2 = Hass()
    s = controller.EssController(hass2, "Test")
    s.enabled = True
    script_settings = controller.ControlSettings(
        {"control_mode": "script", "control_target_entity": "script.ess", "control_unit": "kW",
         "control_sign": "discharge_positive", "control_idle_value": 0}
    )
    await s.async_apply(script_settings, control.ACTION_DISCHARGE, -10.0, "Start discharge")
    call = hass2.services.calls[-1]
    check("script mode runs script.turn_on", call[:2] == ("script", "turn_on") and call[2]["entity_id"] == "script.ess")
    check("script gets the setpoint in its own sign convention", call[2]["variables"]["setpoint"] == 10.0)
    check("script gets power_kw with + = charge", call[2]["variables"]["power_kw"] == -10.0)
    check("script gets the action and reason", call[2]["variables"]["action"] == "discharge" and call[2]["variables"]["reason"] == "Start discharge")
    await s.async_apply(script_settings, control.ACTION_DISCHARGE, -10.0, "Actief")
    check("script isn't re-run for an unchanged setpoint", len(hass2.services.calls) == 1)
    check("script readback is what was last sent", s.readback_power_w(script_settings) == -10000.0)
    await s.async_apply(script_settings, control.ACTION_IDLE, 0.0, "Stop")
    check("script idle sends the idle value and power 0", hass2.services.calls[-1][2]["variables"]["setpoint"] == 0.0
          and hass2.services.calls[-1][2]["variables"]["power_kw"] == 0.0)

    # Wrong entity type never gets called.
    bad = controller.ControlSettings({**NUMBER_CONF, "control_target_entity": "sensor.not_a_number"})
    hass.states.data["sensor.not_a_number"] = State("0")
    n = len(hass.services.calls)
    c2 = controller.EssController(hass, "Test")
    c2.enabled = True
    await c2.async_apply(bad, control.ACTION_CHARGE, 7.0, "Start charge")
    check("a non-number target is refused without a service call", len(hass.services.calls) == n)


asyncio.run(main())

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED:")
    for f in FAILURES:
        print(f" - {f}")
    sys.exit(1)
print("All checks passed.")
