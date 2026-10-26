"""A Victron EV charging station (as of 2026.10.27) - pure Python, no Home
Assistant imports, unit-tested in tests/test_pipeline.py.

With the charger set to "Victron EV charging station" (instead of plain
energy/power sensors) ESS Manager knows when a car is plugged in, asks on
the phone what should happen, and drives the charger:

- asap: right away, at the max current;
- calm: right away, at the min current;
- deadline: full by a time (today / tomorrow at an hour, or "doesn't
  matter" = within the prices known). Solar comes first - the charger's
  own Auto mode (charging on the solar surplus) - and what the solar
  forecast can't deliver in time is bought in the cheapest quarters before
  the deadline (Manual mode at the max current). During those grid windows
  the house battery is kept out of it: the grid setpoint goes up by what
  the car takes.

Until there's an answer (and when there never is one) the charger runs in
its Auto mode. The entities come from the Victron GX integration (core
since Home Assistant 2026.5), found on the chosen device by their
translation key.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

from . import ev as _ev
from .ev import power_kw

UNIT = 900

# Victron GX translation keys (= victron_mqtt short ids) of an EV charging station
VICTRON_KEYS = {
    "status": "evcharger_status",
    # the charger's connection to the GX - not the car (not used for that)
    "connected": "evcharger_connected",
    "power": "evcharger_power",
    "energy": "evcharger_total_energy",
    "session_energy": "evcharger_session_energy",
    "mode": "evcharger_mode",
    "current": "evcharger_set_current",
    "charge": "evcharger_charge",
    "min_current": "evcharger_min_set_current",
    "max_current": "evcharger_max_set_current",
}
VICTRON_REQUIRED = ("status", "power", "energy", "mode", "current", "charge")

MODE_MANUAL = "manual"
MODE_AUTO = "auto"

# charger Status values that mean no car
STATUS_DISCONNECTED = "disconnected"
STATUS_CHARGED = "charged"

CHOICE_ASAP = "asap"
CHOICE_CALM = "calm"
CHOICE_DEADLINE = "deadline"
# (as of 2026.10.29, from the card) the solar surplus only: the charger's Auto mode
CHOICE_SOLAR = "solar"
CHOICES = (CHOICE_ASAP, CHOICE_CALM, CHOICE_DEADLINE, CHOICE_SOLAR)
# "full by" is planned to be done this long before the time given (as of 2026.10.29)
DEADLINE_MARGIN = 3600
DAY_TODAY = "today"
DAY_TOMORROW = "tomorrow"
DAY_ANY = "any"
DAYS = (DAY_TODAY, DAY_TOMORROW, DAY_ANY)

# a grid window is at least this many quarters (no on/off every quarter)
MIN_WINDOW_UNITS = 2
# after plugging in the charger gets this long to start by itself (its own
# auto start) before it's put on Auto (as of 2026.10.28)
PLUGIN_GRACE = 120
# the charger counts as charging above this power (W) or with these Status values
CHARGING_W = 50.0
STATUS_CHARGING = ("charging", "start_charging")


def charging_by_itself(power_w: Optional[float], status: Optional[str], mode: Optional[str]) -> bool:
    """The charger charges and not on its Auto mode (that's ESS Manager's
    own waiting state): started on the charger, by its auto start or a
    schedule - "now, at the current it's set to"."""
    charging = (power_w or 0.0) > CHARGING_W or status in STATUS_CHARGING
    return charging and mode not in (None, MODE_AUTO)


# -- answers typed on the phone -------------------------------------------------
def parse_number(text: Any) -> Optional[float]:
    """The first number in `text` ("45", "45 %", "12,5 kWh"), None without one."""
    if text is None:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(text))
    return float(m.group(0).replace(",", ".")) if m else None


def parse_soc(text: Any) -> Optional[float]:
    value = parse_number(text)
    return value if value is not None and 0 <= value <= 100 else None


def parse_kwh(text: Any) -> Optional[float]:
    value = parse_number(text)
    return value if value is not None and 0 < value <= 250 else None


def parse_hour(text: Any) -> Optional[tuple[int, int]]:
    """(hour, minute) from "7", "07", "7:30", "07.30", "19u" - None when it isn't a time."""
    if text is None:
        return None
    m = re.search(r"(\d{1,2})(?:\s*[:.hu]\s*(\d{2}))?", str(text))
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if hour == 24 and minute == 0:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def match_car(text: Any, cars: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """A car by its number in the list (1 = the first) or (the start of) its name."""
    if not text:
        return None
    t = str(text).strip().lower()
    if t.isdigit() and 1 <= int(t) <= len(cars):
        return cars[int(t) - 1]
    exact = [c for c in cars if str(c.get("name", "")).lower() == t]
    if exact:
        return exact[0]
    start = [c for c in cars if str(c.get("name", "")).lower().startswith(t)]
    return start[0] if len(start) == 1 else None


def needed_kwh(car: Optional[dict[str, Any]], soc: float, target: Optional[float] = None) -> Optional[float]:
    """What a car at `soc` % needs to its target (the car's, or `target`),
    None without a battery size."""
    cap = (car or {}).get("capacity_kwh")
    if not cap:
        return None
    target = float(target if target is not None else ((car or {}).get("target_soc") or 80))
    return round(max(target - float(soc), 0.0) / 100.0 * float(cap), 2)


# -- the deadline plan ----------------------------------------------------------
def plan_deadline(
    now_epoch: int,
    deadline_epoch: int,
    need_kwh: float,
    net: list[Optional[float]],
    hour0_epoch: int,
    prices: list[Optional[float]],
    price_start_epoch: int,
    p_min_kw: float,
    p_max_kw: float,
    keep: Optional[list[int]] = None,
    grid_kw: Optional[float] = None,
) -> dict[str, Any]:
    """Where a charge that has to be done by `deadline_epoch` gets its
    `need_kwh`: solar first (per quarter what the surplus `net` - kWh per
    hour from `hour0_epoch`, solar minus the house - has left, from the
    charger's min power up to its max; that's what the charger's Auto mode
    does), the rest in the cheapest quarters before the deadline that have a
    price (`prices` per quarter from `price_start_epoch`), at the max power.
    `keep`: quarters (start epochs) of a grid window that is running - kept.
    `grid_kw` (as of 2026.10.29): the power of the grid quarters (default
    the max) - the sun keeps its own range up to the max.

    Returns {"windows": [[start, end], ...] (merged, epochs), "quarters":
    [start epochs], "solar_kwh", "grid_kwh", "short_kwh" (what doesn't fit
    before the deadline), "end" (epoch the energy is in, None when it isn't),
    "cost" (of the grid part)}."""
    need = max(float(need_kwh or 0.0), 0.0)
    first = now_epoch - now_epoch % UNIT
    quarters = list(range(first, max(deadline_epoch, first), UNIT))

    def frac(q: int) -> float:
        lo, hi = max(q, now_epoch), min(q + UNIT, deadline_epoch)
        return max(hi - lo, 0) / UNIT

    def solar(q: int) -> float:
        h = (q - hour0_epoch) // 3600
        spare = net[h] if 0 <= h < len(net) and net[h] is not None else 0.0
        rate = min(max(spare, 0.0), p_max_kw) if spare >= p_min_kw else 0.0
        return rate / 4 * frac(q)

    def price(q: int) -> Optional[float]:
        i = (q - price_start_epoch) // UNIT
        return prices[i] if 0 <= i < len(prices) else None

    grid_q = (grid_kw if grid_kw is not None else p_max_kw) / 4
    chosen: set[int] = {q for q in (keep or []) if q in quarters}
    sun = {q: solar(q) for q in quarters}
    total = sum(grid_q * frac(q) if q in chosen else sun[q] for q in quarters)

    candidates = sorted((q for q in quarters if price(q) is not None and frac(q) > 0), key=lambda q: (price(q), q))
    for q in candidates:
        if total >= need - 1e-9:
            break
        if q not in chosen:
            chosen.add(q)
            total += grid_q * frac(q) - sun[q]
    # no lone quarters: a quarter on its own takes its cheaper neighbour
    for q in sorted(chosen):
        run = [q]
        while run[-1] + UNIT in chosen:
            run.append(run[-1] + UNIT)
        if len(run) >= MIN_WINDOW_UNITS or (q - UNIT) in chosen:
            continue
        options = [n for n in (q - UNIT, q + UNIT) if n in quarters and price(n) is not None and frac(n) > 0]
        if options:
            chosen.add(min(options, key=lambda n: (price(n), n)))

    got = 0.0
    end = None
    solar_kwh = grid_kwh = cost = 0.0
    for q in quarters:
        e = grid_q * frac(q) if q in chosen else sun[q]
        if e <= 0:
            continue
        take = min(e, max(need - got, 0.0))
        if take <= 0:
            break
        if q in chosen:
            grid_kwh += take
            cost += take * (price(q) or 0.0)
        else:
            solar_kwh += take
        got += take
        if end is None and got >= need - 1e-9:
            start = max(q, now_epoch)
            end = int(start + (take / e) * frac(q) * UNIT)
    if need <= 0:
        end = now_epoch
    windows: list[list[int]] = []
    for q in sorted(chosen):
        if windows and windows[-1][1] == q:
            windows[-1][1] = q + UNIT
        else:
            windows.append([q, q + UNIT])
    return {
        "windows": windows,
        "quarters": sorted(chosen),
        "solar_kwh": round(solar_kwh, 2),
        "grid_kwh": round(grid_kwh, 2),
        "short_kwh": round(max(need - got, 0.0), 2),
        "end": end,
        "cost": round(cost, 2),
    }


def plan_full_by(
    now_epoch: int,
    deadline_epoch: int,
    need_kwh: float,
    net: list[Optional[float]],
    hour0_epoch: int,
    prices: list[Optional[float]],
    price_start_epoch: int,
    phases: int,
    min_a: float,
    max_a: float,
    keep: Optional[list[int]] = None,
    keep_a: Optional[int] = None,
    margin: int = DEADLINE_MARGIN,
) -> dict[str, Any]:
    """"Full by" with its own speed (as of 2026.10.29): planned to be done
    `margin` before the deadline, at the LOWEST current that still gets
    `need_kwh` in by then (sun first, the rest in the cheapest quarters) -
    a calm charge where there's time. `keep`/`keep_a`: a running grid window
    and its current stay. When even the max current doesn't make it, it's
    `tight`: charge at the max right away (the end is then later than the
    deadline, `reach_kwh` = what's in by the deadline). Adds `current_a`,
    `grid_kw`, `deadline`, `ready_by`, `tight`, `reach_kwh` to plan_deadline's
    dict."""
    ready_by = max(deadline_epoch - margin, now_epoch)
    p_min, p_max = power_kw(min_a, phases), power_kw(max_a, phases)
    lo, hi = int(round(min_a)), int(round(max_a))
    if keep and keep_a:
        lo = max(lo, min(int(keep_a), hi))
    plan = None
    for amps in range(lo, hi + 1):
        kw = power_kw(amps, phases)
        trial = plan_deadline(now_epoch, ready_by, need_kwh, net, hour0_epoch, prices, price_start_epoch, p_min, p_max, keep, kw)
        if trial["short_kwh"] <= 0.05:
            plan = {**trial, "current_a": amps, "grid_kw": kw, "tight": False}
            break
    if plan is None:
        # not even at the max: right away at the max, as much as fits
        quarters = list(range(now_epoch - now_epoch % UNIT, max(deadline_epoch, now_epoch), UNIT))
        reach = min(p_max * max(deadline_epoch - now_epoch, 0) / 3600, max(need_kwh, 0.0))
        end = now_epoch + int(max(need_kwh, 0.0) / p_max * 3600) if p_max > 0 else None
        windows = [[now_epoch - now_epoch % UNIT, end - end % UNIT + UNIT]] if end else []
        plan = {
            "windows": windows, "quarters": quarters, "solar_kwh": 0.0, "grid_kwh": round(max(need_kwh, 0.0), 2),
            "short_kwh": round(max(need_kwh - reach, 0.0), 2), "end": end, "cost": 0.0,
            "current_a": hi, "grid_kw": p_max, "tight": True,
        }
    plan["deadline"] = deadline_epoch
    plan["ready_by"] = ready_by
    plan["reach_kwh"] = round(max(need_kwh, 0.0) - plan["short_kwh"], 2)
    return plan


def in_windows(epoch: int, windows: list[list[int]]) -> bool:
    return any(a <= epoch < b for a, b in windows or [])


# -- what the charger should do ------------------------------------------------------
def charger_target(flow: Optional[dict[str, Any]], now_epoch: int, min_a: float, max_a: float) -> Optional[dict[str, Any]]:
    """{mode, charge, current} for the plugged-in car's flow; None = leave
    the charger alone (no car; full according to the sums; or, without a
    choice, charging by itself or just plugged in)."""
    if not flow:
        return None
    if flow.get("done"):
        # full according to the sums (or the charger says "charged"): the
        # charger is left as it is - the car stops by itself when it's really
        # full, and the sums can be off (as of 2026.10.29; up to then it was
        # switched off)
        return None
    choice = flow.get("choice")
    override = flow.get("current_a")
    if choice == CHOICE_ASAP:
        return {"mode": MODE_MANUAL, "charge": True, "current": int(override or max_a), "why": "asap"}
    if choice == CHOICE_CALM:
        return {"mode": MODE_MANUAL, "charge": True, "current": int(override or min_a), "why": "calm"}
    if choice == CHOICE_SOLAR:
        return {"mode": MODE_AUTO, "charge": True, "current": None, "why": "solar"}
    if choice == CHOICE_DEADLINE and flow.get("need_kwh") is not None:
        plan = flow.get("plan") or {}
        if in_windows(now_epoch, flow.get("windows") or []):
            return {"mode": MODE_MANUAL, "charge": True, "current": int(plan.get("current_a") or max_a), "why": "grid_window"}
        return {"mode": MODE_AUTO, "charge": True, "current": None, "why": "solar"}
    if choice is None:
        # started by itself (by hand, auto start, schedule): it goes on as it
        # is; just plugged in: a moment for the charger's own auto start
        if flow.get("external") or now_epoch - int(flow.get("since") or 0) < PLUGIN_GRACE:
            return None
        return {"mode": MODE_AUTO, "charge": True, "current": None, "why": "waiting"}
    return {"mode": MODE_AUTO, "charge": True, "current": None, "why": "solar"}


def grid_profile(windows: list[list[int]], hour0_epoch: int, hours: int, now_epoch: int, p_max_kw: float, need_left: float) -> list[float]:
    """The car's grid-window energy per forecast hour (hour 0 a full-hour
    value, like the rest of the forecast) - the part the house battery stays
    out of."""
    out = [0.0] * hours
    left = max(need_left, 0.0)
    frac0 = max((hour0_epoch + 3600 - now_epoch) / 3600, 1e-6)
    for a, b in sorted(windows or []):
        a = max(a, now_epoch)
        while a < b and left > 1e-9:
            h = (a - hour0_epoch) // 3600
            hour_end = hour0_epoch + (h + 1) * 3600
            seg = min(b, hour_end) - a
            take = min(p_max_kw * seg / 3600, left)
            if 0 <= h < hours:
                out[h] += take / frac0 if h == 0 else take
            left -= take
            a += seg
    return [round(v, 4) for v in out]


def planned_full_by(
    session: dict[str, Any],
    now_epoch: int,
    hour0_epoch: int,
    hours: int,
    net: list[Optional[float]],
    prices: list[Optional[float]],
    price_start_epoch: int,
    phases: int,
    min_a: float,
    max_a: float,
) -> tuple[list[float], list[float], dict[str, Any]]:
    """A planned "full by" session (as of 2026.10.29) in the forecast: per
    hour what it takes (a full-hour value for hour 0) and the part of it in
    grid windows (the house battery stays out of that), plus {end, kwh,
    warning, plan}. Planned as for a plugged-in car from its start; where the
    prices for its time aren't known yet, a calm charge from the start at the
    lowest current that gets it in an hour before its time."""
    start = max(int(session["start"]), now_epoch)
    deadline = int(session.get("deadline") or 0)
    need = max(float(session.get("kwh") or 0.0), 0.0)
    zero = [0.0] * hours
    if need <= 0 or deadline <= start:
        return zero, zero, {"end": start, "kwh": 0.0, "warning": None, "plan": None}
    prices_end = price_start_epoch + len(prices) * UNIT
    if deadline - DEADLINE_MARGIN <= prices_end:
        plan = plan_full_by(start, deadline, need, net, hour0_epoch, prices, price_start_epoch, phases, min_a, max_a)
    else:
        ready = max(deadline - DEADLINE_MARGIN, start + UNIT)
        amps = int(round(max_a))
        for a in range(int(round(min_a)), int(round(max_a)) + 1):
            if power_kw(a, phases) * (ready - start) / 3600 >= need:
                amps = a
                break
        kw = power_kw(amps, phases)
        end = start + int(need / kw * 3600) if kw > 0 else None
        reach = min(need, kw * (deadline - start) / 3600)
        plan = {
            "windows": [[start - start % UNIT, (end or start) - (end or start) % UNIT + UNIT]] if end else [],
            "solar_kwh": 0.0, "grid_kwh": round(need, 2), "short_kwh": round(need - reach, 2), "end": end,
            "current_a": amps, "grid_kw": kw, "tight": need - reach > 0.05, "deadline": deadline,
            "ready_by": ready, "reach_kwh": round(reach, 2), "estimate": True,
        }
    grid = grid_profile(plan["windows"], hour0_epoch, hours, now_epoch, float(plan["grid_kw"]), float(plan["grid_kwh"]))
    solar, _ = _ev.session_profile(
        {"start": start, "kwh": plan["solar_kwh"], "mode": _ev.MODE_SOLAR}, now_epoch, hour0_epoch, hours, net,
        phases, min_a, max_a, int(plan.get("ready_by") or deadline),
    )
    total = [round(a + b, 4) for a, b in zip(grid, solar)]
    info = {
        "end": plan["end"],
        "kwh": round(plan["solar_kwh"] + plan["grid_kwh"], 2),
        "warning": _ev.WARNING_SHORT if plan.get("tight") else None,
        "plan": plan,
    }
    return total, grid, info
