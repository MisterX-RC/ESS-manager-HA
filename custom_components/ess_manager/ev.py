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
# A session whose start has passed without the car charging is kept this long.
START_GRACE = HOUR

MODE_FIXED = "fixed"
MODE_SOLAR = "solar"
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
    grouped by start hour (within an hour of each other), and a group that
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
            if groups and run["hour"] - groups[-1][0]["hour"] <= 1:
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


def apply_car(session: dict[str, Any], car: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The session with its car's battery: with a capacity the energy
    follows the start and target SOC (the start SOC worked back from the
    target when only the energy is known)."""
    s = dict(session)
    cap = (car or {}).get("capacity_kwh")
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
) -> list[dict[str, Any]]:
    """The card's session list: predicted sessions with their override (an
    edit: label "edited"), plus the manual ones (label "manual"), sorted by
    start. Gone: finished ones (`done`), ones past their start by more than
    START_GRACE without charging, and ones starting after `end_epoch`.
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
        if not running and (s["start"] + START_GRACE <= now_epoch or s["start"] >= end_epoch):
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
