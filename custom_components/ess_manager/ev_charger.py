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

Until there's an answer (and when there never is one) ESS Manager doesn't
start anything - unless a planned or predicted session is taken over (as of
2026.10.31; up to then the charger was put on its Auto mode). A charge the
charger starts by itself goes on; unplugging puts it back to rest (Manual,
off). The entities come from the Victron GX integration (core
since Home Assistant 2026.5), found on the chosen device by their
translation key.
"""
from __future__ import annotations

import heapq
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

# A myenergi zappi (as of 2026.11.21, the myenergi integration): no current to
# set - ESS Manager picks one of its charge modes per quarter. Its entities by
# role, found on its device by the end of their unique id (the integration's
# own names depend on the zappi's name).
ZAPPI_SUFFIXES = {
    "mode": ("select", "-charge_mode"),
    "status": ("sensor", "-status"),
    "plug": ("sensor", "-plug_status"),
    "session_energy": ("sensor", "-charge_added"),
    "locked": ("binary_sensor", "-locked"),
    "when_locked": ("binary_sensor", "-charge_when_locked"),
}
ZAPPI_REQUIRED = ("mode", "status", "plug")
ZAPPI_FAST = "Fast"
ZAPPI_ECO = "Eco"
ZAPPI_ECO_PLUS = "Eco+"
ZAPPI_STOPPED = "Stopped"
# what a zappi is put back to when the car is unplugged: nothing starts by itself
ZAPPI_REST = ZAPPI_STOPPED
CHARGER_VICTRON = "victron"
CHARGER_ZAPPI = "zappi"

MODE_MANUAL = "manual"
MODE_AUTO = "auto"
# what the charger is put back to when the car is unplugged (as of 2026.10.31):
# the next car plugged in without a plan doesn't charge (unless the charger's
# own auto start starts it)
REST_TARGET = {"mode": MODE_MANUAL, "charge": False, "current": None, "why": "unplugged"}

# charger Status values that mean no car
STATUS_DISCONNECTED = "disconnected"
STATUS_CHARGED = "charged"
# really charging (as of 2026.10.37): this Status and power going in - only
# then has a session started; "charged" before that (the charger passes it
# right after plugging in) doesn't end it
STATUS_CHARGING_NOW = "charging"

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
# the day after tomorrow (as of 2026.10.31)
DAY_AFTER = "after"
DAY_ANY = "any"
DAYS = (DAY_TODAY, DAY_TOMORROW, DAY_AFTER, DAY_ANY)
# days from today
DAY_OFFSET = {DAY_TODAY: 0, DAY_TOMORROW: 1, DAY_AFTER: 2}

# a grid window is at least this many quarters (no on/off every quarter)
MIN_WINDOW_UNITS = 2
# the charger counts as charging above this power (W) or with these Status values
CHARGING_W = 50.0
STATUS_CHARGING = ("charging", "start_charging")


def charging_by_itself(power_w: Optional[float], status: Optional[str], mode: Optional[str]) -> bool:
    """The charger charges without a choice: started on the charger, by its
    auto start, a schedule or its own Auto mode - "now, at the current it's
    set to". (Up to 2026.10.30 not on Auto: that was ESS Manager's own
    waiting state; `mode` is kept for the callers.)"""
    del mode
    return (power_w or 0.0) > CHARGING_W or status in STATUS_CHARGING


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
    cap = _ev.charge_capacity(car)  # with the car's correction factor (as of 2026.10.35)
    if not cap:
        return None
    target = float(target if target is not None else ((car or {}).get("target_soc") or 80))
    return round(max(target - float(soc), 0.0) / 100.0 * float(cap), 2)


# -- the deadline plan ----------------------------------------------------------
def battery_option(
    now_epoch: int, hour0_epoch: int, house_net: list[Optional[float]], until_epoch: int,
    level_kwh: Optional[float], floor_kwh: float, capacity_kwh: float, max_discharge_kw: float, losses: float,
) -> Optional[dict[str, Any]]:
    """What the house battery can give the car (as of 2026.11.4): `budget_kwh`
    - the lowest level the battery reaches until `until_epoch` on the house
    alone (solar minus the house, per hour), above `floor_kwh` (taking
    energy earlier lowers every later hour by as much); `room_kw` per hour -
    its max discharge speed minus what the house takes; `losses` - charge x
    discharge efficiency. None without a battery level."""
    if level_kwh is None or max_discharge_kw <= 0:
        return None
    level = float(level_kwh)
    low = level
    room = []
    hours = max(math.ceil((until_epoch - hour0_epoch) / 3600), 1)
    for h in range(len(house_net)):
        n = house_net[h] if house_net[h] is not None else 0.0
        room.append(max(max_discharge_kw - max(-n, 0.0), 0.0))
        if h < hours:
            frac = max((hour0_epoch + 3600 - now_epoch) / 3600, 0.0) if h == 0 else 1.0
            level = min(level + n * frac, capacity_kwh)
            low = min(low, level)
    return {"budget_kwh": round(max(low - floor_kwh, 0.0), 3), "room_kw": room, "losses": max(losses, 0.01)}


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
    battery: Optional[dict[str, Any]] = None,
    keep_battery: Optional[list[int]] = None,
    sun: bool = True,
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

    `battery` (as of 2026.11.4, battery_option): a quarter can also come out
    of the house battery, at what it costs to fill it up again - the
    cheapest price after that quarter, / the losses - within the battery's
    budget and its room (its max discharge minus the house, at least the
    car's power); per quarter the cheaper of the two. `keep_battery`: the
    battery quarters of a window that is running - kept.

    Returns {"windows": [[start, end], ...] (merged, epochs - the grid part),
    "quarters": [start epochs], "battery_windows", "battery_quarters",
    "solar_kwh", "grid_kwh", "battery_kwh", "short_kwh" (what doesn't fit
    before the deadline), "end" (epoch the energy is in, None when it isn't),
    "cost" (grid at its price, battery at its refill price)}."""
    need = max(float(need_kwh or 0.0), 0.0)
    first = now_epoch - now_epoch % UNIT
    quarters = list(range(first, max(deadline_epoch, first), UNIT))

    def frac(q: int) -> float:
        lo, hi = max(q, now_epoch), min(q + UNIT, deadline_epoch)
        return max(hi - lo, 0) / UNIT

    def solar(q: int) -> float:
        if not sun:
            # (as of 2026.11.21) a charger that can't follow the sun (a zappi): no sun part
            return 0.0
        h = (q - hour0_epoch) // 3600
        spare = net[h] if 0 <= h < len(net) and net[h] is not None else 0.0
        rate = min(max(spare, 0.0), p_max_kw) if spare >= p_min_kw else 0.0
        return rate / 4 * frac(q)

    def price(q: int) -> Optional[float]:
        i = (q - price_start_epoch) // UNIT
        return prices[i] if 0 <= i < len(prices) else None

    car_kw = grid_kw if grid_kw is not None else p_max_kw
    grid_q = car_kw / 4
    # the refill price after each quarter: the cheapest price later on
    refill: dict[int, Optional[float]] = {}
    if battery:
        n_p = len(prices)
        later: list[Optional[float]] = [None] * (n_p + 1)
        for i in range(n_p - 1, -1, -1):
            p, nxt = prices[i], later[i + 1]
            later[i] = nxt if p is None else (p if nxt is None else min(p, nxt))
        for q in quarters:
            i = (q - price_start_epoch) // UNIT
            refill[q] = later[i + 1] if 0 <= i + 1 <= n_p else None
    budget = float((battery or {}).get("budget_kwh") or 0.0)
    losses = float((battery or {}).get("losses") or 1.0)

    def batt_cost(q: int) -> Optional[float]:
        if not battery or refill.get(q) is None:
            return None
        h = (q - hour0_epoch) // 3600
        room = (battery.get("room_kw") or [])
        if not (0 <= h < len(room)) or room[h] < car_kw - 1e-6:
            return None
        return refill[q] / losses

    chosen: set[int] = {q for q in (keep or []) if q in quarters}
    from_batt: set[int] = set()
    for q in keep_battery or []:
        if q in quarters and q not in chosen:
            chosen.add(q)
            from_batt.add(q)
            budget -= grid_q * frac(q)
    sun = {q: solar(q) for q in quarters}
    total = sum(grid_q * frac(q) if q in chosen else sun[q] for q in quarters)

    heap: list[tuple[float, int, int]] = []
    for q in quarters:
        if frac(q) <= 0 or q in chosen:
            continue
        if price(q) is not None:
            heap.append((price(q), q, 0))
        bc = batt_cost(q)
        if bc is not None:
            heap.append((bc, q, 1))
    heapq.heapify(heap)

    def take(q: int, kind: int) -> bool:
        nonlocal budget, total
        e = grid_q * frac(q)
        if kind == 1:
            if budget < e - 1e-9:
                return False
            budget -= e
            from_batt.add(q)
        chosen.add(q)
        total += e - sun[q]
        return True

    while heap and total < need - 1e-9:
        _, q, kind = heapq.heappop(heap)
        if q not in chosen:
            take(q, kind)
    # no lone quarters: a quarter on its own takes its cheaper neighbour
    for q in sorted(chosen):
        run = [q]
        while run[-1] + UNIT in chosen:
            run.append(run[-1] + UNIT)
        if len(run) >= MIN_WINDOW_UNITS or (q - UNIT) in chosen:
            continue
        options = []
        for n in (q - UNIT, q + UNIT):
            if n in quarters and frac(n) > 0 and n not in chosen:
                if price(n) is not None:
                    options.append((price(n), n, 0))
                bc = batt_cost(n)
                if bc is not None and budget >= grid_q * frac(n):
                    options.append((bc, n, 1))
        if options:
            _, n, kind = min(options)
            take(n, kind)

    got = 0.0
    end = None
    solar_kwh = grid_kwh = batt_kwh = cost = 0.0
    # per quarter what goes in and what it costs (for the card's charge
    # plan, as of 2026.11.5)
    q_kwh: dict[int, float] = {}
    q_cost: dict[int, float] = {}
    for q in quarters:
        e = grid_q * frac(q) if q in chosen else sun[q]
        if e <= 0:
            continue
        part = min(e, max(need - got, 0.0))
        if part <= 0:
            break
        if q in from_batt:
            batt_kwh += part
            c = part * (batt_cost(q) or (refill.get(q) or 0.0) / losses)
            cost += c
            q_kwh[q], q_cost[q] = part, c
        elif q in chosen:
            grid_kwh += part
            c = part * (price(q) or 0.0)
            cost += c
            q_kwh[q], q_cost[q] = part, c
        else:
            solar_kwh += part
        got += part
        if end is None and got >= need - 1e-9:
            start = max(q, now_epoch)
            end = int(start + (part / e) * frac(q) * UNIT)
    if need <= 0:
        end = now_epoch

    def merged(qs: set[int]) -> list[list[int]]:
        out: list[list[int]] = []
        for q in sorted(qs):
            if out and out[-1][1] == q:
                out[-1][1] = q + UNIT
            else:
                out.append([q, q + UNIT])
        return out

    def sums(windows: list[list[int]], per_q: dict[int, float]) -> list[float]:
        return [round(sum(v for q, v in per_q.items() if a <= q < b), 3) for a, b in windows]

    grid_set = chosen - from_batt
    grid_windows = merged(grid_set)
    batt_windows = merged(from_batt)
    return {
        "windows": grid_windows,
        "window_kwh": sums(grid_windows, q_kwh),
        "window_cost": sums(grid_windows, q_cost),
        "battery_window_kwh": sums(batt_windows, q_kwh),
        "battery_window_cost": sums(batt_windows, q_cost),
        "quarters": sorted(grid_set),
        "battery_windows": batt_windows,
        "battery_quarters": sorted(from_batt),
        "solar_kwh": round(solar_kwh, 2),
        "grid_kwh": round(grid_kwh, 2),
        "battery_kwh": round(batt_kwh, 2),
        "short_kwh": round(max(need - got, 0.0), 2),
        "end": end,
        "cost": round(cost, 2),
    }


# "full by" charges calm by preference (as of 2026.11.7): a lower current may
# cost this much more per kWh than the cheapest plan (EUR/kWh)
CALM_MARGIN = 0.02


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
    battery: Optional[dict[str, Any]] = None,
    keep_battery: Optional[list[int]] = None,
    sun: bool = True,
    sun_min_a: Optional[float] = None,
) -> dict[str, Any]:
    """"Full by" with its own speed (as of 2026.10.29): planned to be done
    `margin` before the deadline (sun first, the rest in the cheapest
    quarters). As of 2026.11.4 at the current that costs least - a faster
    charge can fit in the cheap quarters where a slow one needs dear ones -
    and of equal cost the lowest (a calm charge where there's time); dear
    quarters can come out of the house battery (`battery`, see
    plan_deadline). `keep`/`keep_a`: a running grid window
    and its current stay. When even the max current doesn't make it, it's
    `tight`: charge at the max right away (the end is then later than the
    deadline, `reach_kwh` = what's in by the deadline). Adds `current_a`,
    `grid_kw`, `deadline`, `ready_by`, `tight`, `reach_kwh` to plan_deadline's
    dict."""
    ready_by = max(deadline_epoch - margin, now_epoch)
    # the sun from this much surplus on (as of 2026.11.21 `sun_min_a`: a zappi's
    # windows run at its max, its Eco+ takes the sun from the min current on)
    p_min = power_kw(sun_min_a if sun_min_a is not None else min_a, phases)
    p_max = power_kw(max_a, phases)
    lo, hi = int(round(min_a)), int(round(max_a))
    if keep and keep_a:
        lo = max(lo, min(int(keep_a), hi))
    plan = None
    fits: list[dict[str, Any]] = []
    for amps in range(lo, hi + 1):
        kw = power_kw(amps, phases)
        trial = plan_deadline(now_epoch, ready_by, need_kwh, net, hour0_epoch, prices, price_start_epoch, p_min, p_max, keep, kw,
                              battery, keep_battery, sun)
        if trial["short_kwh"] <= 0.05:
            fits.append({**trial, "current_a": amps, "grid_kw": kw, "tight": False})
    if fits:
        # (as of 2026.11.7) calm by preference: the lowest current that costs
        # at most CALM_MARGIN per kWh more than the cheapest plan
        cheapest = min(f["cost"] for f in fits)
        allowed = cheapest + CALM_MARGIN * max(need_kwh, 0.0) + 1e-9
        plan = next(f for f in fits if f["cost"] <= allowed)
    if plan is None:
        # not even at the max: right away at the max, as much as fits
        quarters = list(range(now_epoch - now_epoch % UNIT, max(deadline_epoch, now_epoch), UNIT))
        reach = min(p_max * max(deadline_epoch - now_epoch, 0) / 3600, max(need_kwh, 0.0))
        end = now_epoch + int(max(need_kwh, 0.0) / p_max * 3600) if p_max > 0 else None
        windows = [[now_epoch - now_epoch % UNIT, end - end % UNIT + UNIT]] if end else []
        plan = {
            "windows": windows, "quarters": quarters, "battery_windows": [], "battery_quarters": [], "battery_kwh": 0.0,
            "solar_kwh": 0.0, "grid_kwh": round(max(need_kwh, 0.0), 2),
            "short_kwh": round(max(need_kwh - reach, 0.0), 2), "end": end, "cost": 0.0,
            "current_a": hi, "grid_kw": p_max, "tight": True,
        }
    plan["deadline"] = deadline_epoch
    plan["ready_by"] = ready_by
    plan["reach_kwh"] = round(max(need_kwh, 0.0) - plan["short_kwh"], 2)
    return plan


def zappi_status(plug: Optional[str], status: Optional[str]) -> Optional[str]:
    """A zappi's plug and charge status as the Victron Status values the
    session follows: no car -> disconnected, Completed -> charged (the car
    stopped), Charging / Boosting -> charging; None when it can't be read."""
    p = (plug or "").strip().lower()
    st = (status or "").strip().lower()
    if p in ("", "unknown", "unavailable") and st in ("", "unknown", "unavailable"):
        return None
    if p in ("ev disconnected", "unknown", "unavailable", ""):
        return STATUS_DISCONNECTED if p == "ev disconnected" else None
    if st == "completed":
        return STATUS_CHARGED
    if st in ("charging", "boosting") or p == "charging":
        return STATUS_CHARGING_NOW
    return "connected"


def zappi_mode(target: Optional[dict[str, Any]], choice: Optional[str], min_a: float) -> Optional[str]:
    """The zappi charge mode for a charger target (charger_target). Its CT
    clamp sits between the house and the Victron, so what it sees as export
    is the solar the house doesn't use - what would otherwise go into the
    house battery (or out through it). Off -> Stopped; "now, slowly" (the min
    current) -> Eco (the solar surplus, at least 6 A - the rest from the
    Victron side); a grid or battery window, "now" -> Fast; the sun - also a
    "full by" between its windows -> Eco+ (only the surplus, from ~1.4 kW on
    a phase). The Victron's grid setpoint doesn't move that CT, so the two
    don't chase each other."""
    del choice
    if target is None:
        return None
    if not target.get("charge"):
        return ZAPPI_STOPPED
    if target.get("mode") == MODE_AUTO:
        return ZAPPI_ECO_PLUS
    if target.get("current") is not None and float(target["current"]) <= float(min_a):
        return ZAPPI_ECO
    return ZAPPI_FAST


def in_windows(epoch: int, windows: list[list[int]]) -> bool:
    return any(a <= epoch < b for a, b in windows or [])


# -- what the charger should do ------------------------------------------------------
def charger_target(flow: Optional[dict[str, Any]], now_epoch: int, min_a: float, max_a: float) -> Optional[dict[str, Any]]:
    """{mode, charge, current} for the plugged-in car's flow; None = leave
    the charger alone (no car; full according to the sums; no choice yet)."""
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
        if in_windows(now_epoch, flow.get("battery_windows") or []):
            # (as of 2026.11.4) a dear quarter out of the house battery: the
            # grid setpoint isn't raised, so the battery supplies the car
            return {"mode": MODE_MANUAL, "charge": True, "current": int(plan.get("current_a") or max_a), "why": "battery_window"}
        return {"mode": MODE_AUTO, "charge": True, "current": None, "why": "solar"}
    if choice is None:
        # no choice and nothing planned to take over: ESS Manager doesn't
        # start anything (as of 2026.10.31; up to then the charger was put on
        # its Auto mode) - a charge the charger starts by itself goes on
        return None
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
    battery: Optional[dict[str, Any]] = None,
    sun: bool = True,
    sun_min_a: Optional[float] = None,
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
        plan = plan_full_by(start, deadline, need, net, hour0_epoch, prices, price_start_epoch, phases, min_a, max_a,
                            battery=battery, sun=sun, sun_min_a=sun_min_a)
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
    # (as of 2026.11.4) the part out of the house battery counts as usage
    batt = grid_profile(plan.get("battery_windows") or [], hour0_epoch, hours, now_epoch, float(plan["grid_kw"]),
                        float(plan.get("battery_kwh") or 0.0))
    solar, _ = _ev.session_profile(
        {"start": start, "kwh": plan["solar_kwh"], "mode": _ev.MODE_SOLAR}, now_epoch, hour0_epoch, hours, net,
        phases, sun_min_a if sun_min_a is not None else min_a, max_a, int(plan.get("ready_by") or deadline),
    )
    total = [round(a + b + c, 4) for a, b, c in zip(grid, batt, solar)]
    info = {
        "end": plan["end"],
        "kwh": round(plan["solar_kwh"] + plan["grid_kwh"] + float(plan.get("battery_kwh") or 0.0), 2),
        "warning": _ev.WARNING_SHORT if plan.get("tight") else None,
        "plan": plan,
    }
    return total, grid, info
