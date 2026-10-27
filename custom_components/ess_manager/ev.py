"""Electric car charging sessions (as of 2026.10.11) - pure Python, no Home
Assistant imports, unit-tested in tests/test_pipeline.py.

Only meant for a car that charges from the home battery: its charging
energy then really comes out of the battery, so the planning has to know
when it charges and how much.

- The car's historical charging energy is taken out of the household usage
  forecast (always, whether sessions are predicted or not - see
  usage_forecast's `subtract_entities`); the car only enters the 120-hour
  forecast through its sessions.
- Sessions are predicted from the history (when "predict from history" is
  on): a session that starts around the same hour on the same weekday in
  more than half of the lookback weeks.
- The dashboard card edits them (overrides stored per predicted session) or
  adds manual ones.
- A session charges at a fixed current, or on solar surplus only (what's
  left of the solar forecast after the house), from its start hour.

Times are epochs (seconds); a session's key is its local start
"YYYY-MM-DDTHH".
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, tzinfo
from typing import Any, Optional

HOUR = 3600
VOLTAGE = 230.0  # per phase
# An hour with at least this much car energy counts as charging.
CHARGING_KWH = 0.3
# A historical session counts as a solar session when at least this share of
# its energy fits in the solar surplus of those hours.
SOLAR_SHARE = 0.8
# A session whose start has passed without the car charging is kept this long
# (and a charge this long after a session's start still belongs to it; 2 hours
# as of 2026.10.29, 1 up to then).
START_GRACE = 2 * HOUR

MODE_FIXED = "fixed"
MODE_SOLAR = "solar"
# (as of 2026.10.29, Victron charger) full by `deadline` (epoch): sun first, the
# rest in the cheapest quarters, at the lowest current that fits
MODE_DEADLINE = "deadline"
MODES = (MODE_FIXED, MODE_SOLAR, MODE_DEADLINE)
# the plug-in log (Victron charger) is kept this long
LOG_DAYS = 84
# -- the state-of-charge correction per car (as of 2026.10.35) ------------------
# Every charge with a state of charge you gave that the car finishes while
# still plugged in is a sample: the energy that really went in against what
# the state of charge and the target said. Over the last sessions that gives
# a factor per car the state-of-charge sums are multiplied by.
SOC_SAMPLES_KEEP = 30         # samples kept (all cars)
SOC_FACTOR_SESSIONS = 10      # the factor: the last this many used samples of a car
SOC_FACTOR_MIN_SESSIONS = 3   # ... and only from this many on
SOC_FACTOR_RANGE = (0.7, 1.5)
SOC_SAMPLE_MIN_KWH = 3.0      # less planned than this: too inaccurate to count
# before there's a long-term average a sample counts within this range; after
# that within SOC_OUTLIER of the car's long-term average (all its used samples)
SOC_SAMPLE_RANGE = (0.6, 1.6)
SOC_OUTLIER = 0.25


# a car without its own charge efficiency (%, as of 2026.10.36; the setting's default)
CHARGE_EFFICIENCY = 90.0


def car_efficiency(car: Optional[dict[str, Any]]) -> float:
    """A car's charge efficiency (0-1): what reaches its battery of the energy
    the charger delivers (as of 2026.10.36)."""
    eff = (car or {}).get("efficiency")
    eff = float(eff) if eff else CHARGE_EFFICIENCY
    return min(max(eff, 10.0), 100.0) / 100.0


def soc_long_term(samples: list[dict[str, Any]], car_id: Any, efficiency: float = 1.0) -> Optional[float]:
    """A car's long-term correction (all its used samples), None below
    SOC_FACTOR_MIN_SESSIONS. As of 2026.10.36 on top of its charge efficiency:
    the samples' "planned" is what the state of charge says goes into the
    battery, so the correction is energy charged x efficiency / planned."""
    used = [x for x in samples if x.get("car") == car_id and x.get("used")]
    if len(used) < SOC_FACTOR_MIN_SESSIONS:
        return None
    planned = sum(float(x["planned"]) for x in used)
    return sum(float(x["actual"]) for x in used) * efficiency / planned if planned > 0 else None


def soc_factor(samples: list[dict[str, Any]], car_id: Any, efficiency: float = 1.0) -> tuple[float, int]:
    """(factor, used samples of this car): what the energy from a state of
    charge is multiplied by - the energy really charged over the energy
    planned in the car's last SOC_FACTOR_SESSIONS used samples, 1.0 below
    SOC_FACTOR_MIN_SESSIONS, kept within SOC_FACTOR_RANGE."""
    used = [x for x in samples if x.get("car") == car_id and x.get("used")]
    recent = used[-SOC_FACTOR_SESSIONS:]
    if len(recent) < SOC_FACTOR_MIN_SESSIONS:
        return 1.0, len(used)
    planned = sum(float(x["planned"]) for x in recent)
    if planned <= 0:
        return 1.0, len(used)
    # (on top of the charge efficiency, as of 2026.10.36: see soc_long_term)
    factor = sum(float(x["actual"]) for x in recent) * efficiency / planned
    lo, hi = SOC_FACTOR_RANGE
    return round(min(max(factor, lo), hi), 3), len(used)


def soc_sample_used(
    samples: list[dict[str, Any]], car_id: Any, planned: float, actual: float, efficiency: float = 1.0
) -> tuple[bool, Optional[str]]:
    """Whether a new sample counts, and why not: too small, or too far off -
    from the car's long-term average once there is one (SOC_OUTLIER), from
    SOC_SAMPLE_RANGE before that. A sample that far off is most likely a
    state of charge typed wrong or the car stopping at another limit than
    its target in ESS Manager."""
    if planned < SOC_SAMPLE_MIN_KWH:
        return False, "small"
    ratio = actual * efficiency / planned
    average = soc_long_term(samples, car_id, efficiency)
    if average is not None:
        if abs(ratio - average) > SOC_OUTLIER * average:
            return False, "outlier"
    elif not SOC_SAMPLE_RANGE[0] <= ratio <= SOC_SAMPLE_RANGE[1]:
        return False, "outlier"
    return True, None


def charge_capacity(car: Optional[dict[str, Any]]) -> Optional[float]:
    """The energy (kWh) the charger delivers per 100% of the car's state of
    charge - what comes from the house battery or the grid: its battery size
    divided by its charge efficiency (as of 2026.10.36) times its correction
    factor (`kwh_factor`, as of 2026.10.35)."""
    cap = (car or {}).get("capacity_kwh")
    if not cap:
        return None
    return float(cap) * float((car or {}).get("kwh_factor") or 1.0) / car_efficiency(car)


LABEL_HISTORY = "history"
LABEL_EDITED = "edited"
LABEL_MANUAL = "manual"
WARNING_NO_SURPLUS = "no_surplus"
WARNING_SHORT = "short"


def power_kw(current_a: float, phases: int) -> float:
    """kW at `current_a` per phase on `phases` phases (230 V per phase)."""
    return round(max(float(current_a), 0.0) * VOLTAGE * max(int(phases), 1) / 1000.0, 3)


def current_for_power(kw: float, phases: int, min_a: float, max_a: float) -> int:
    """The whole-ampere current closest to `kw`, within min..max."""
    amps = kw * 1000.0 / (VOLTAGE * max(int(phases), 1))
    return int(min(max(round(amps), min_a), max_a))


def session_key(start_epoch: int, tz: tzinfo) -> str:
    return datetime.fromtimestamp(start_epoch, tz).strftime("%Y-%m-%dT%H")


def _local_epoch(day: datetime, hour: int, tz: tzinfo) -> int:
    """Epoch of `hour`:00 local time on `day`'s date (DST-correct)."""
    return int(datetime.combine(day.date(), time(hour), tzinfo=tz).timestamp())


def _historical_sessions(
    ev: dict[int, float], surplus: Optional[dict[int, float]], day_start: int, day_end: int
) -> tuple[bool, list[dict[str, Any]]]:
    """(any data that day, the charging runs that START that day) - each
    run: start epoch, kWh, hours, peak hour kWh, solar share (None without
    surplus data). A run is followed past midnight until it ends."""
    has_data = any(day_start <= e < day_end for e in ev)
    runs: list[dict[str, Any]] = []
    epoch = day_start
    # a run that started the day before belongs to that day: skip it
    while ev.get(epoch, 0.0) >= CHARGING_KWH and ev.get(epoch - HOUR, 0.0) >= CHARGING_KWH and epoch < day_end:
        epoch += HOUR
    while epoch < day_end:
        if ev.get(epoch, 0.0) < CHARGING_KWH:
            epoch += HOUR
            continue
        start = epoch
        kwh = 0.0
        peak = 0.0
        solar_kwh = 0.0
        solar_known = surplus is not None
        while ev.get(epoch, 0.0) >= CHARGING_KWH and epoch < day_end + 12 * HOUR:
            value = ev[epoch]
            kwh += value
            peak = max(peak, value)
            if solar_known:
                spare = surplus.get(epoch)
                if spare is None:
                    solar_known = False
                else:
                    solar_kwh += min(value, max(spare, 0.0))
            epoch += HOUR
        runs.append(
            {
                "start": start,
                "kwh": kwh,
                "hours": (epoch - start) // HOUR,
                "peak": peak,
                "solar_share": (solar_kwh / kwh) if solar_known and kwh > 0 else None,
            }
        )
    return has_data, runs


def detect_sessions(
    ev: dict[int, float],
    surplus: Optional[dict[int, float]],
    days: list[datetime],
    lookback_weeks: int,
    phases: int,
    min_a: float,
    max_a: float,
    tz: tzinfo,
) -> list[dict[str, Any]]:
    """Predicted sessions for each local day in `days` (their midnights).

    `ev`: the car's energy per hour (hour start epoch -> kWh); `surplus`:
    solar minus the house without the car per hour (None: unknown). For
    each day, the same weekday 1..lookback_weeks back: charging runs are
    grouped by start hour (within two hours of each other, as of 2026.10.29), and a group that
    occurs in more than half of the lookback weeks becomes a session - at
    its most common start hour, with the average energy of the weeks it
    occurred in, charging at the typical full hour (the median peak hour),
    and in solar mode when on average at least SOLAR_SHARE of it came from
    the solar surplus."""
    out: list[dict[str, Any]] = []
    need = lookback_weeks / 2.0
    for day in days:
        found: list[dict[str, Any]] = []
        for week in range(1, lookback_weeks + 1):
            past = day - timedelta(weeks=week)
            start = _local_epoch(past, 0, tz)
            end = int(datetime.combine(past.date() + timedelta(days=1), time(0), tzinfo=tz).timestamp())
            _, runs = _historical_sessions(ev, surplus, start, end)
            for run in runs:
                run["week"] = week
                run["hour"] = datetime.fromtimestamp(run["start"], tz).hour
                found.append(run)
        found.sort(key=lambda r: (r["hour"], r["week"]))
        groups: list[list[dict[str, Any]]] = []
        for run in found:
            if groups and run["hour"] - groups[-1][0]["hour"] <= 2:
                groups[-1].append(run)
            else:
                groups.append([run])
        for group in groups:
            weeks = sorted({r["week"] for r in group})
            if len(weeks) <= need:
                continue
            hours = [r["hour"] for r in group]
            hour = max(sorted(set(hours)), key=hours.count)
            kwh = sum(r["kwh"] for r in group) / len(weeks)
            peaks = sorted(r["peak"] for r in group)
            peak = peaks[len(peaks) // 2]
            current = current_for_power(peak, phases, min_a, max_a)
            shares = [r["solar_share"] for r in group if r["solar_share"] is not None]
            solar = bool(shares) and len(shares) == len(group) and sum(shares) / len(shares) >= SOLAR_SHARE
            start_epoch = _local_epoch(day, hour, tz)
            out.append(
                {
                    "id": "h:" + session_key(start_epoch, tz),
                    "key": session_key(start_epoch, tz),
                    "start": start_epoch,
                    "kwh": round(kwh, 2),
                    "mode": MODE_SOLAR if solar else MODE_FIXED,
                    "current_a": current,
                    "car": None,
                    "start_soc": None,
                    "target_soc": None,
                    "enabled": True,
                    "label": LABEL_HISTORY,
                    "solar_history": solar,
                    "weeks": len(weeks),
                }
            )
    out.sort(key=lambda s: s["start"])
    return out


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def detect_connections(
    log: list[dict[str, Any]],
    days: list[datetime],
    lookback_weeks: int,
    phases: int,
    min_a: float,
    max_a: float,
    tz: tzinfo,
) -> list[dict[str, Any]]:
    """Predicted sessions from the plug-in log (Victron charger, as of
    2026.10.29) instead of the charging energy: one session per time the
    car was plugged in, so two charge blocks in one connection (a "full by"
    split by the prices) are one session. For each day, the connections of
    the same weekday 1..lookback_weeks back are grouped by plug-in hour
    (within two hours of each other); a group in more than half the weeks
    becomes a session at its most common hour, with the average energy and
    the most common car. Its way of charging is the one chosen most often;
    "full by" - also without a choice when the car stays plugged in well
    over twice as long as charging takes - with as time the usual one
    (the times chosen, else the usual unplug time), counted from the
    plug-in."""
    out: list[dict[str, Any]] = []
    need = lookback_weeks / 2.0
    p_max = power_kw(max_a, phases)
    for day in days:
        found: list[dict[str, Any]] = []
        for week in range(1, lookback_weeks + 1):
            past = day - timedelta(weeks=week)
            start = _local_epoch(past, 0, tz)
            end = int(datetime.combine(past.date() + timedelta(days=1), time(0), tzinfo=tz).timestamp())
            for c in log:
                if start <= int(c.get("on", 0)) < end and c.get("off"):
                    found.append({**c, "week": week, "hour": datetime.fromtimestamp(int(c["on"]), tz).hour})
        found.sort(key=lambda r: (r["hour"], r["week"]))
        groups: list[list[dict[str, Any]]] = []
        for c in found:
            if groups and c["hour"] - groups[-1][0]["hour"] <= 2:
                groups[-1].append(c)
            else:
                groups.append([c])
        for group in groups:
            weeks = sorted({c["week"] for c in group})
            if len(weeks) <= need:
                continue
            hours = [c["hour"] for c in group]
            hour = max(sorted(set(hours)), key=hours.count)
            kwh = sum(float(c.get("kwh") or 0.0) for c in group) / len(weeks)
            cars = [c.get("car") for c in group if c.get("car")]
            car = max(sorted(set(cars)), key=cars.count) if cars else None
            choices = [c.get("choice") for c in group if c.get("choice")]
            choice = max(sorted(set(choices)), key=choices.count) if choices else None
            stay = _median([int(c["off"]) - int(c["on"]) for c in group])
            start_epoch = _local_epoch(day, hour, tz)
            session = {
                "id": "h:" + session_key(start_epoch, tz),
                "key": session_key(start_epoch, tz),
                "start": start_epoch,
                "kwh": round(kwh, 2),
                "mode": MODE_FIXED,
                "current_a": int(max_a),
                "car": car,
                "start_soc": None,
                "target_soc": None,
                "enabled": True,
                "label": LABEL_HISTORY,
                "solar_history": False,
                "weeks": len(weeks),
                "source": "log",
                "deadline": None,
            }
            long_stay = p_max > 0 and stay >= 3 * HOUR and kwh / p_max * HOUR * 2 < stay
            if choice == "deadline" or (choice is None and long_stay):
                # the usual time of day (counted from the plug-in day's midnight)
                def from_midnight(c: dict[str, Any], key: str) -> int:
                    on_day = datetime.fromtimestamp(int(c["on"]), tz)
                    return int(c[key]) - _local_epoch(on_day, 0, tz)

                offsets = [from_midnight(c, "deadline") for c in group if c.get("choice") == "deadline" and c.get("deadline")]
                if not offsets:
                    offsets = [from_midnight(c, "off") for c in group]
                dl = _local_epoch(day, 0, tz) + int(_median(offsets))
                session.update({"mode": MODE_DEADLINE, "current_a": None, "deadline": dl - dl % 900})
            elif choice == "solar":
                session.update({"mode": MODE_SOLAR, "current_a": None})
            elif choice == "calm":
                session["current_a"] = int(min_a)
            out.append(session)
    out.sort(key=lambda s: s["start"])
    return out


def apply_car(session: dict[str, Any], car: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The session with its car's battery: with a capacity the energy
    follows the start and target SOC (the start SOC worked back from the
    target when only the energy is known)."""
    s = dict(session)
    cap = charge_capacity(car)
    if not car or not cap:
        s["start_soc"] = None if not car else s.get("start_soc")
        return s
    target = s.get("target_soc")
    if target is None:
        target = car.get("target_soc", 80)
    target = min(max(float(target), 0.0), 100.0)
    start = s.get("start_soc")
    if start is None:
        start = target - float(s.get("kwh") or 0.0) / cap * 100.0
    start = min(max(float(start), 0.0), target)
    s["target_soc"] = round(target)
    s["start_soc"] = round(start)
    s["kwh"] = round((target - start) / 100.0 * cap, 2)
    return s


def build_sessions(
    predicted: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
    manual: list[dict[str, Any]],
    cars: list[dict[str, Any]],
    now_epoch: int,
    end_epoch: int,
    running_id: Optional[str] = None,
    done: Optional[set[str]] = None,
    keep_from: Optional[int] = None,
) -> list[dict[str, Any]]:
    """The card's session list: predicted sessions with their override (an
    edit: label "edited"), plus the manual ones (label "manual"), sorted by
    start. Gone: finished ones (`done`), ones past their start by more than
    START_GRACE without charging, and ones starting after `end_epoch`.
    `keep_from` (as of 2026.10.36, while a car is plugged in: the hour it was
    plugged in): sessions you added from then on stay past their start - they
    wait for the plugged-in car.
    With exactly one car, every session is that car's."""
    done = done or set()
    by_id = {c.get("id"): c for c in cars}
    only = cars[0] if len(cars) == 1 else None
    out: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for s in predicted:
        o = overrides.get(s["id"])
        if o:
            s = {**s, **{k: v for k, v in o.items() if k != "id"}, "id": s["id"], "label": LABEL_EDITED}
        candidates.append(s)
    for s in manual:
        candidates.append({**s, "label": LABEL_MANUAL})
    for s in candidates:
        if s["id"] in done:
            continue
        running = s["id"] == running_id
        waiting = keep_from is not None and s.get("label") == LABEL_MANUAL and s["start"] >= keep_from
        if not running and ((s["start"] + START_GRACE <= now_epoch and not waiting) or s["start"] >= end_epoch):
            continue
        car = by_id.get(s.get("car")) if s.get("car") else only
        s = apply_car({**s, "car": car.get("id") if car else None}, car)
        s["running"] = running
        out.append(s)
    out.sort(key=lambda s: (s["start"], s["id"]))
    return out


def session_profile(
    session: dict[str, Any],
    now_epoch: int,
    hour0_epoch: int,
    hours: int,
    net: list[float],
    phases: int,
    min_a: float,
    max_a: float,
    day_end_epoch: int,
    delivered_kwh: float = 0.0,
) -> tuple[list[float], dict[str, Any]]:
    """What the session takes per forecast hour (hour 0 = the current hour,
    as a full-hour value like the rest of the forecast: the battery
    forecast scales it to what's left of the hour), and {end, kwh,
    warning}: when it's done (epoch, or None when it doesn't get there),
    what it charges, and "no_surplus"/"short" for a solar session that gets
    nothing / not all of it before the end of its day.

    Fixed: the session's current (between min and max) from its start until
    the energy is in. Solar: per hour whatever the surplus (`net`: solar
    minus the house) has left, at most the max current and only when it's
    at least the min current, until the end of the day."""
    out = [0.0] * hours
    need = max(float(session.get("kwh") or 0.0) - max(delivered_kwh, 0.0), 0.0)
    solar = session.get("mode") == MODE_SOLAR
    p_max = power_kw(max_a, phases)
    p_min = power_kw(min_a, phases)
    rate_fixed = power_kw(min(max(float(session.get("current_a") or max_a), min_a), max_a), phases)
    begin = max(int(session["start"]), now_epoch)
    left = need
    got = 0.0
    end = None
    frac0 = max((hour0_epoch + HOUR - now_epoch) / HOUR, 1e-6)
    for h in range(hours):
        w0 = hour0_epoch + h * HOUR
        w1 = w0 + HOUR
        if left <= 1e-9:
            break
        if solar and w0 >= day_end_epoch:
            break
        lo = max(w0, begin)
        hi = min(w1, day_end_epoch) if solar else w1
        if hi <= lo:
            continue
        span = (hi - lo) / HOUR
        if solar:
            spare = max(net[h], 0.0) if h < len(net) else 0.0
            rate = min(spare, p_max) if spare >= p_min else 0.0
        else:
            rate = rate_fixed
        if rate <= 0:
            continue
        take = min(rate * span, left)
        left -= take
        got += take
        if left <= 1e-9:
            end = int(lo + take / rate * HOUR)
        out[h] = round(take / frac0, 4) if h == 0 else round(take, 4)
    warning = None
    if solar:
        if got <= 0.05 and need > 0:
            warning = WARNING_NO_SURPLUS
        elif left > 0.05:
            warning = WARNING_SHORT
    elif need <= 1e-9:
        end = begin
    return out, {"end": end, "kwh": round(got + max(delivered_kwh, 0.0), 2), "warning": warning}


def ev_forecast(
    sessions: list[dict[str, Any]],
    now_epoch: int,
    hour0_epoch: int,
    hours: int,
    net: list[float],
    phases: int,
    min_a: float,
    max_a: float,
    tz: tzinfo,
    delivered: Optional[dict[str, float]] = None,
) -> tuple[list[float], list[dict[str, Any]]]:
    """The car's energy per forecast hour from every enabled session (summed),
    plus each session with its `end`, `charged_kwh` and `warning`."""
    delivered = delivered or {}
    total = [0.0] * hours
    out: list[dict[str, Any]] = []
    for s in sessions:
        start_day = datetime.fromtimestamp(int(s["start"]), tz).date()
        day_end = int(datetime.combine(start_day + timedelta(days=1), time(0), tzinfo=tz).timestamp())
        profile, info = session_profile(
            s, now_epoch, hour0_epoch, hours, net, phases, min_a, max_a, day_end, delivered.get(s["id"], 0.0)
        )
        if s.get("enabled", True):
            total = [round(a + b, 4) for a, b in zip(total, profile)]
        out.append({**s, "end": info["end"], "charged_kwh": info["kwh"], "warning": info["warning"]})
    return total, out
