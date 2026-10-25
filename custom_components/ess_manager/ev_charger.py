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

UNIT = 900

# Victron GX translation keys (= victron_mqtt short ids) of an EV charging station
VICTRON_KEYS = {
    "status": "evcharger_status",
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
CHOICES = (CHOICE_ASAP, CHOICE_CALM, CHOICE_DEADLINE)
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


def needed_kwh(car: Optional[dict[str, Any]], soc: float) -> Optional[float]:
    """What a car at `soc` % needs to its target, None without a battery size."""
    cap = (car or {}).get("capacity_kwh")
    if not cap:
        return None
    target = float((car or {}).get("target_soc") or 80)
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
) -> dict[str, Any]:
    """Where a charge that has to be done by `deadline_epoch` gets its
    `need_kwh`: solar first (per quarter what the surplus `net` - kWh per
    hour from `hour0_epoch`, solar minus the house - has left, from the
    charger's min power up to its max; that's what the charger's Auto mode
    does), the rest in the cheapest quarters before the deadline that have a
    price (`prices` per quarter from `price_start_epoch`), at the max power.
    `keep`: quarters (start epochs) of a grid window that is running - kept.

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

    grid_q = p_max_kw / 4
    chosen: set[int] = {q for q in (keep or []) if q in quarters}

    def total() -> float:
        return sum(grid_q * frac(q) if q in chosen else solar(q) for q in quarters)

    candidates = sorted((q for q in quarters if price(q) is not None and frac(q) > 0), key=lambda q: (price(q), q))
    for q in candidates:
        if total() >= need - 1e-9:
            break
        if q not in chosen:
            chosen.add(q)
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
        e = grid_q * frac(q) if q in chosen else solar(q)
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


def in_windows(epoch: int, windows: list[list[int]]) -> bool:
    return any(a <= epoch < b for a, b in windows or [])


# -- what the charger should do ------------------------------------------------------
def charger_target(flow: Optional[dict[str, Any]], now_epoch: int, min_a: float, max_a: float) -> Optional[dict[str, Any]]:
    """{mode, charge, current} for the plugged-in car's flow; None = leave
    the charger alone (no car; or, without a choice, charging by itself or
    just plugged in)."""
    if not flow:
        return None
    if flow.get("done"):
        return {"mode": MODE_MANUAL, "charge": False, "current": None, "why": "done"}
    choice = flow.get("choice")
    if choice == CHOICE_ASAP:
        return {"mode": MODE_MANUAL, "charge": True, "current": int(max_a), "why": "asap"}
    if choice == CHOICE_CALM:
        return {"mode": MODE_MANUAL, "charge": True, "current": int(min_a), "why": "calm"}
    if choice == CHOICE_DEADLINE and flow.get("need_kwh") is not None:
        if in_windows(now_epoch, flow.get("windows") or []):
            return {"mode": MODE_MANUAL, "charge": True, "current": int(max_a), "why": "grid_window"}
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
