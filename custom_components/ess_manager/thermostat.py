"""The thermostat learned from the house (as of 2026.11.20): when it switches
the heat demand on and off.

Almost every thermostat that switches a heat pump does the same thing: it asks
for heat when the room drops a little under the wanted temperature and stops
when the room gets a little above it. Those two thresholds, and how long a run
and a pause last at least, are learned here from the climate entity's history
(its `hvac_action`, `current_temperature` and `temperature` at each switch) -
no settings needed, and it works for any make. The house model
(heatpump_house) then plays the hours again quarter by quarter with that
behaviour, so the heat lands in the hours it really does (before, an
emulated controller spread it smoothly).

A thermostat that modulates (OpenTherm-like, no clear thresholds) shows its
switches scattered: then `kind` is "modulating" and the house model keeps its
smooth controller. And the house model only uses the thermostat when its
self-check places the hours better with it than without.

Pure Python (no Home Assistant imports) so tests/test_pipeline.py can run it.
"""
from __future__ import annotations

from typing import Any, Optional

HOUR = 3600
SP_SETTLE_S = 900          # a switch within 15 min of a setpoint or mode change is the change, not the room
EVENT_DAYS = 60            # switches kept / learned from
MAX_EVENTS = 1500
MIN_SWITCHES = 10          # each way, before anything is learned
MAX_SPREAD_C = 0.4         # the middle half of the switches within this: a thermostat with thresholds
MIN_BAND_C = 0.05          # off threshold at least this far above the on threshold
QON_DAYS = 30
MIN_QON_HOURS = 10         # hours of demand to tell the heat pump's power from
MIN_SLOPE_HOURS = 20       # mostly-on hours to tell it per outdoor temperature
MIN_SLOPE_SPAN_C = 4.0
MOSTLY_ON_S = 2700
QUARTER = 900
ENFORCED_TOL_S = 120       # runs this close to the shortest one ...
ENFORCED_SHARE = 0.15      # ... this share of them: a minimum the thermostat keeps
KIND_LEARNING = "learning"
KIND_ON_OFF = "on_off"
KIND_MODULATING = "modulating"

_HEAT = ("heating", "preheating", "defrosting")
_NOT_HEAT = ("idle", "off", "fan", "cooling", "drying")


def demand(state: Optional[str], attrs: dict[str, Any]) -> Optional[bool]:
    """The thermostat's own heat demand: only its hvac_action counts here
    (indoor below wanted would make thresholds of exactly 0)."""
    if state in (None, "unavailable", "unknown"):
        return None
    action = attrs.get("hvac_action")
    if not isinstance(action, str) or not action:
        return None
    action = action.lower()
    if action in _HEAT:
        return True
    if action in _NOT_HEAT:
        return False
    return None


def _quantile(values: list[float], q: float) -> float:
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def switch_events(rows: list[tuple[int, Optional[str], Optional[bool], Optional[float], Optional[float]]]) -> list[list]:
    """The switches in a climate entity's history. `rows` = (epoch, state
    (the hvac mode), demand, room, wanted) per recorded state, the state at
    the start first. Each switch: [epoch, 1 on / 0 off, room, wanted, how
    long the state before lasted (s, None when unknown), clean 1/0]. Clean =
    room and wanted known, the mode unchanged and no setpoint or mode change
    in the SP_SETTLE_S before - then the room made the thermostat switch."""
    rows = sorted(rows, key=lambda r: r[0])
    out: list[list] = []
    last_dem: Optional[bool] = None
    last_switch: Optional[int] = None
    last_change: Optional[int] = None
    last_sp: Optional[float] = None
    last_mode: Optional[str] = None
    for i, (ts, mode, dem, room, sp) in enumerate(rows):
        mode_changed = i > 0 and mode != last_mode
        sp_changed = sp is not None and last_sp is not None and abs(sp - last_sp) > 1e-6
        if mode_changed or sp_changed:
            last_change = ts
        if i > 0 and dem is not None and last_dem is not None and dem != last_dem:
            clean = (room is not None and sp is not None and not mode_changed and not sp_changed
                     and (last_change is None or ts - last_change >= SP_SETTLE_S))
            prev = ts - last_switch if last_switch is not None else None
            out.append([int(ts), 1 if dem else 0, room, sp, prev, 1 if clean else 0])
        if dem is not None:
            if last_dem is not None and dem != last_dem:
                last_switch = ts
            elif last_dem is None:
                last_switch = None  # unknown before: the first run's length isn't known
            last_dem = dem
        if sp is not None:
            last_sp = sp
        last_mode = mode
    return out


def merge_events(stored: list[list], new: list[list], now_epoch: float) -> list[list]:
    """The kept switches with the newly read ones (same moment = same switch;
    the new reading wins), older than EVENT_DAYS dropped."""
    by_ts = {int(e[0]): e for e in stored or []}
    for e in new:
        by_ts[int(e[0])] = e
    cutoff = now_epoch - EVENT_DAYS * 86400
    kept = [e for ts, e in sorted(by_ts.items()) if ts >= cutoff]
    return kept[-MAX_EVENTS:]


def learn(events: list[list], now_epoch: float) -> dict[str, Any]:
    """The thresholds (room minus wanted, degC) at which it switches on and
    off, their spread, the usual run and pause and a kept minimum (s). `kind`:
    learning (too few switches), on_off or modulating."""
    cutoff = now_epoch - EVENT_DAYS * 86400
    ev = [e for e in events if e[5] and e[0] >= cutoff and e[2] is not None and e[3] is not None]
    on = [e[2] - e[3] for e in ev if e[1] == 1]
    off = [e[2] - e[3] for e in ev if e[1] == 0]
    res: dict[str, Any] = {"kind": KIND_LEARNING, "n_on": len(on), "n_off": len(off),
                           "needed": MIN_SWITCHES}
    if len(on) < MIN_SWITCHES or len(off) < MIN_SWITCHES:
        return res
    on_c, off_c = _quantile(on, 0.5), _quantile(off, 0.5)
    spread_on = _quantile(on, 0.75) - _quantile(on, 0.25)
    spread_off = _quantile(off, 0.75) - _quantile(off, 0.25)
    runs = [e[4] for e in ev if e[1] == 0 and e[4]]      # how long it was on before switching off
    pauses = [e[4] for e in ev if e[1] == 1 and e[4]]
    ok = spread_on <= MAX_SPREAD_C and spread_off <= MAX_SPREAD_C and off_c - on_c >= MIN_BAND_C
    res.update({
        "kind": KIND_ON_OFF if ok else KIND_MODULATING,
        "on_c": round(on_c, 2),
        "off_c": round(off_c, 2),
        "mid_c": round((on_c + off_c) / 2, 3),
        "spread_on_c": round(spread_on, 2),
        "spread_off_c": round(spread_off, 2),
        "min_run_s": _enforced_min(runs),
        "min_pause_s": _enforced_min(pauses),
        "median_run_s": int(_quantile(runs, 0.5)) if runs else None,
        "median_pause_s": int(_quantile(pauses, 0.5)) if pauses else None,
    })
    return res


def _enforced_min(durations: list[float]) -> Optional[int]:
    """A minimum run or pause the thermostat keeps (a generic thermostat's
    min_cycle_duration): many runs end right at the shortest one. Not a
    minimum when the shortest is just the shortest of naturally long runs."""
    if len(durations) < 10:
        return None
    shortest = min(durations)
    if shortest > HOUR:
        return None
    at_min = sum(1 for d in durations if d <= shortest + ENFORCED_TOL_S)
    return int(shortest) if at_min >= ENFORCED_SHARE * len(durations) else None


def on_seconds(changes: list[tuple[int, Optional[bool]]], start: int, end: int) -> dict[int, int]:
    """Seconds of heat demand per hour (hours with 45 minutes or more known)."""
    changes = sorted((c for c in changes if c[0] < end), key=lambda c: c[0])  # by time only (2026.11.29)
    acc: dict[int, list[float]] = {}
    for i, (t0, v) in enumerate(changes):
        t1 = changes[i + 1][0] if i + 1 < len(changes) else end
        t0 = max(t0, start)
        if v is None:
            continue
        while t0 < t1:
            h = t0 // HOUR * HOUR
            seg = min(t1, h + HOUR) - t0
            a = acc.setdefault(h, [0.0, 0.0])
            a[0] += seg if v else 0.0
            a[1] += seg
            t0 += seg
    return {h: int(round(a[0] / a[1] * HOUR)) for h, a in acc.items() if a[1] >= 2700}


def power(heat: dict[int, float], on_s: dict[int, int], outdoor: Optional[dict[int, float]], now_epoch: float) -> Optional[dict[str, Any]]:
    """The heat pump's heat per hour of demand (in the units of `heat`):
    the heat of the hours with demand known over their demand time, and -
    with enough mostly-on hours over a wide enough outdoor range - per
    outdoor temperature (a heat pump gives more when it's colder). {a, b,
    mean, hours}: a + b * outdoor (b = 0 when not learned)."""
    cutoff = now_epoch - QON_DAYS * 86400
    hours = [h for h in on_s if h >= cutoff and heat.get(h) is not None]
    on_h = sum(on_s[h] for h in hours) / HOUR
    if on_h < MIN_QON_HOURS:
        return None
    mean = sum(heat[h] for h in hours) / on_h
    if mean <= 0:
        return None
    a, b = mean, 0.0
    pts = [(outdoor[h], heat[h] / (on_s[h] / HOUR)) for h in hours
           if on_s[h] >= MOSTLY_ON_S and outdoor and outdoor.get(h) is not None]
    if len(pts) >= MIN_SLOPE_HOURS:
        xs = [p[0] for p in pts]
        if max(xs) - min(xs) >= MIN_SLOPE_SPAN_C:
            mx = sum(xs) / len(xs)
            my = sum(p[1] for p in pts) / len(pts)
            sxx = sum((x - mx) ** 2 for x in xs)
            sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
            slope = sxy / sxx if sxx > 0 else 0.0
            if slope < 0:
                b = slope
                a = my - slope * mx
    return {"a": round(a, 4), "b": round(b, 4), "mean": round(mean, 4), "hours": round(on_h, 1)}


def power_at(pw: dict[str, Any], tout: Optional[float]) -> float:
    if tout is None or not pw.get("b"):
        return pw["mean"]
    return max(pw["a"] + pw["b"] * tout, 0.3 * pw["mean"])
