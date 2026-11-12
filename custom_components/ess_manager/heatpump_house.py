"""The house hour by hour (as of 2026.10.17): how the indoor temperature
follows the outdoor temperature, wind, sun and the heat the heat pump puts in
(with the floor's delay), how much the heat pump makes of a kWh (its COP by
the outdoor temperature), and from that:

- a 48-hour forecast of the indoor temperature and of the heating energy per
  hour (the heat pump emulated as a controller that keeps the house on its
  usual temperature per hour),
- a daily self-check against what was measured: the newest heating days are
  played again with the measured weather - is the energy placed in the right
  hours better than the usual hourly pattern does, does the house follow the
  measured temperature? Only then the planning uses it (and drops it again
  when it gets worse) - nothing to switch by hand,
- preheating advice: the cheapest window to put a degree more into the house
  (prices, solar surplus, the COP at that hour's temperature, how long the
  house holds it).

Pure Python (no Home Assistant imports), unit-tested in tests/test_pipeline.py.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Optional

from . import thermostat

HOUR = 3600
# what the model is built from changes with these (as of 2026.11.11): a new
# version learns again right away instead of the next day
MODEL_VERSION = "2026.11.36"   # the thermostat learned on fewer switches when they agree: checked again right after the update
# the floor's delay (as of 2026.11.9 36 hours back and up to 24 h - up to
# then 12 and 6: a concrete floor heated in a block of a few hours gives its
# heat off over far more hours, and the day's simulation drifted)
LAG_HOURS = 36                  # the heat of the last 36 hours
LAG_TAUS = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 18.0, 24.0]  # its time constant (h), the best fit chosen
MIN_HOUSE_ROWS = 150            # hours to fit on
MAX_OUT = 18.0                  # degC outdoor at most (summer hours say little)
MIN_COP_HOURS = 48
COP_MIN, COP_MAX = 1.5, 8.0
KP = 0.3                        # the emulated controller: share of the gap closed per hour
TEST_DAYS = 14                  # the self-check: the newest heating days ...
MIN_TEST_DAYS = 10              # ... at least this many
TEST_HEAT_KWH = 1.0             # a day with at least this much heating counts as a test day
GATE_RATIO = 0.9                # hourly energy error at most 90% of the pattern's
GATE_TEMP_C = 0.6               # and the indoor temperature within this on average
# the self-check as of 2026.11.12: cross-validation - the test days in FOLDS
# groups, each group checked with a model fitted on all other hours - so the
# model is judged on many heating days, not only on the few before the
# newest two weeks (early in the season hardly any)
FOLDS = 3
# and a drift guard: the newest RECENT_DAYS heating days checked with a model
# fitted only on the hours before them - clearly worse there (no better than
# the pattern, or the room further off than RECENT_TEMP_C) and it doesn't pass
RECENT_DAYS = 4
RECENT_MIN_DAYS = 3
RECENT_TEMP_C = 1.0
# (as of 2026.11.35) an hour in which ESS Manager switched the heat demand
# itself (floor control "full") for at least this long: the self-check plays
# it with the smooth controller - the plan ESS Manager followed - not with
# the learned thermostat, which didn't switch the heat pump then
ESS_HOUR_S = 1800
# (as of 2026.11.35) the self-check's energy test in blocks of this many hours,
# each started from the measured room (before: the whole day blind, per hour)
BLOCK_HOURS = 6
FORECAST_HOURS = 48
BOOST_C = 1.0                   # preheating: a degree more
BOOST_WINDOWS = (2, 3, 4)       # hours
ADVICE_HORIZON = 36             # hours the cost is compared over
MIN_PRICE_HOURS = 12            # prices needed ahead
MIN_SAVING = 0.10               # currency units
STAGE_LEARNING = "learning"
STAGE_SHADOW = "shadow"
STAGE_USED = "used"
STAGE_STEERING = "steering"


def _solve(a: list[list[float]], b: list[float]) -> Optional[list[float]]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def kernel(tau: float) -> list[float]:
    """Weights of the heat of this hour and the hours before (newest first)."""
    w = [math.exp(-j / tau) for j in range(LAG_HOURS)]
    s = sum(w)
    return [x / s for x in w]


def _lag(q: dict[int, float], h: int, w: list[float]) -> Optional[float]:
    total = 0.0
    for j, wj in enumerate(w):
        v = q.get(h - j * HOUR)
        if v is None:
            return None
        total += wj * v
    return total


# -- COP ------------------------------------------------------------------------
def fit_cop(cop: dict[int, float], outdoor: dict[int, float], heat: dict[int, float],
            cop_min: Optional[dict[int, float]] = None) -> Optional[dict[str, Any]]:
    """COP = c0 + c1 x outdoor from the hours the heat pump heated (the COP
    sensor's hourly means). None with fewer than MIN_COP_HOURS such hours.

    With the sensor's hourly minimum (as of 2026.10.38) only hours it never
    dropped below 1 count - the heat pump ran the whole hour. A COP sensor
    reads 0 while the heat pump is off, so the mean of an hour it ran for 26
    minutes is less than half its COP; without enough whole hours there's no
    COP model (the floor control then uses its measured heat / electricity)."""
    pts = [(outdoor[h], c) for h, c in cop.items()
           if h in outdoor and heat.get(h, 0.0) > 0.1 and 1.0 < c < 10.0
           and (cop_min is None or (cop_min.get(h) or 0.0) >= 1.0)]
    if len(pts) < MIN_COP_HOURS:
        return None
    n = len(pts)
    mx = sum(t for t, _ in pts) / n
    my = sum(c for _, c in pts) / n
    sxx = sum((t - mx) ** 2 for t, _ in pts)
    c1 = sum((t - mx) * (c - my) for t, c in pts) / sxx if sxx > 1e-9 else 0.0
    c0 = my - c1 * mx
    return {"c0": round(c0, 3), "c1": round(c1, 4), "n": n}


def heating_heat(thermal: dict[int, float], heat_el: dict[int, float], total_el: Optional[dict[int, float]]) -> dict[int, float]:
    """The heat that went into the house per hour (as of 2026.11.10): the
    heat pump's heat meter counts heating and hot water together, so each
    hour's heat goes by the share of the heating in its electricity -
    heating electricity / all its electricity (an hour of only hot water:
    0, only heating: all of it; a mixed hour shared out). Without the total
    meter every hour with heating counts whole."""
    out: dict[int, float] = {}
    for h, th in thermal.items():
        el = heat_el.get(h)
        if el is None or th is None:
            continue
        if el <= 0.0:
            out[h] = 0.0
            continue
        share = 1.0
        if total_el is not None:
            tot = total_el.get(h)
            if tot is None:
                continue
            share = min(el / tot, 1.0) if tot > 0.0 else 1.0
        out[h] = max(th, 0.0) * share
    return out


def fit_cop_meters(heat_th: dict[int, float], heat_el: dict[int, float], outdoor: dict[int, float]) -> Optional[dict[str, Any]]:
    """COP = c0 + c1 x outdoor from the heat and electricity meters (as of
    2026.11.10): per hour the heating's heat / its electricity, hours with at
    least 0.2 kWh of heating - no need for whole running hours."""
    pts = []
    for h, el in heat_el.items():
        th = heat_th.get(h)
        if el is None or el < 0.2 or th is None or h not in outdoor:
            continue
        c = th / el
        if 1.0 < c < 10.0:
            pts.append((outdoor[h], c))
    if len(pts) < MIN_COP_HOURS:
        return None
    n = len(pts)
    mx = sum(t for t, _ in pts) / n
    my = sum(c for _, c in pts) / n
    sxx = sum((t - mx) ** 2 for t, _ in pts)
    c1 = sum((t - mx) * (c - my) for t, c in pts) / sxx if sxx > 1e-9 else 0.0
    return {"c0": round(my - c1 * mx, 3), "c1": round(c1, 4), "n": n, "source": "meters"}


def cop_check(cop: dict[int, float], outdoor: dict[int, float], heat: dict[int, float],
              cop_min: Optional[dict[int, float]] = None) -> dict[str, int]:
    """Why there is (no) COP model (as of 2026.11.9, for the diagnostics):
    the COP sensor's hours, and how many fall out - no outdoor temperature,
    hardly any heating that hour (hot water / standby), a COP outside 1-10,
    not running the whole hour (its minimum below 1) - and what's left."""
    out = {"hours": len(cop), "no_outdoor": 0, "no_heating": 0, "out_of_range": 0, "not_whole_hour": 0,
           "used": 0, "needed": MIN_COP_HOURS}
    for h, c in cop.items():
        if h not in outdoor:
            out["no_outdoor"] += 1
        elif heat.get(h, 0.0) <= 0.1:
            out["no_heating"] += 1
        elif not 1.0 < c < 10.0:
            out["out_of_range"] += 1
        elif cop_min is not None and (cop_min.get(h) or 0.0) < 1.0:
            out["not_whole_hour"] += 1
        else:
            out["used"] += 1
    return out


def cop_at(copm: Optional[dict[str, Any]], tout: Optional[float]) -> float:
    if not copm or tout is None:
        return 1.0
    return max(COP_MIN, min(COP_MAX, copm["c0"] + copm["c1"] * tout))


# -- the house -------------------------------------------------------------------
def _rows(indoor, outdoor, heat, cool, w):
    rows = []
    for h, tin in indoor.items():
        nxt = indoor.get(h + HOUR)
        tout = outdoor.get(h)
        if nxt is None or tout is None or tout > MAX_OUT:
            continue
        if cool and cool.get(h, 0.0) >= 0.05:
            continue
        lag = _lag(heat, h, w)
        if lag is None:
            continue
        rows.append((h, nxt - tin, tin - tout, lag))
    return rows


def _x(h, d, lag, wind, sun, use_wind, use_sun, gains=None, use_gains=False):
    x = [1.0, -d, lag]
    if use_wind:
        x.append(-(wind.get(h) or 0.0) * d)
    if use_sun:
        x.append(sun.get(h) or 0.0)
    if use_gains:
        x.append(gains.get(h) or 0.0)
    return x


def gains_profile(gains: dict[int, float], tz: tzinfo, today: date, days: int = 14) -> Optional[list[float]]:
    """The house's own electricity per local hour of the day (as of
    2026.11.11): the mean of the last `days` days - what the forecast counts
    on for ironing, cooking and the rest."""
    start = datetime.combine(today - timedelta(days=days), datetime.min.time(), tzinfo=tz).timestamp()
    sums = [0.0] * 24
    counts = [0] * 24
    for h, v in gains.items():
        if h >= start and v is not None:
            hr = datetime.fromtimestamp(h, tz).hour
            sums[hr] += v
            counts[hr] += 1
    if min(counts) < 3:
        return None
    return [round(sums[i] / counts[i], 3) for i in range(24)]


SPIKE_SIGMAS = 4.0              # an hour this far off the fit (robust spread) is left out - ironing, the oven


def _solve_rows(xs: list[list[float]], ys: list[float]) -> Optional[list[float]]:
    k = len(xs[0])
    ata = [[sum(x[i] * x[j] for x in xs) for j in range(k)] for i in range(k)]
    atb = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(k)]
    return _solve(ata, atb)


def _fit_robust(xs: list[list[float]], ys: list[float]) -> tuple[Optional[list[float]], list[int]]:
    """Least squares, then once more without the hours that are far off it
    (as of 2026.11.11): a room that jumps a few degrees while ironing and
    falls back right after isn't the house - left in, it bends the fit for
    every normal hour. (coefficients, the indexes kept)"""
    coef = _solve_rows(xs, ys)
    if coef is None:
        return None, list(range(len(ys)))
    res = [y - sum(c * v for c, v in zip(coef, x)) for x, y in zip(xs, ys)]
    mad = sorted(abs(r) for r in res)[len(res) // 2]
    if mad <= 0:
        return coef, list(range(len(ys)))
    keep = [i for i, r in enumerate(res) if abs(r) <= SPIKE_SIGMAS * 1.4826 * mad]
    if len(keep) < max(MIN_HOUSE_ROWS, len(ys) // 2):
        return coef, list(range(len(ys)))
    coef2 = _solve_rows([xs[i] for i in keep], [ys[i] for i in keep])
    return (coef2 or coef), keep


def fit_house(
    indoor: dict[int, float],
    outdoor: dict[int, float],
    heat: dict[int, float],
    wind: Optional[dict[int, float]] = None,
    sun: Optional[dict[int, float]] = None,
    cool: Optional[dict[int, float]] = None,
    copm: Optional[dict[str, Any]] = None,
    heat_th: Optional[dict[int, float]] = None,
    gains: Optional[dict[int, float]] = None,
) -> Optional[dict[str, Any]]:
    """dT(indoor, next hour) = a - k x d + g x heat(lagged) - kw x wind x d +
    ks x sun, d = indoor - outdoor, the heat delayed by the floor (kernel,
    its time constant the best fit). With a COP model the heat is the heat
    pump's heat (electricity x COP), else its electricity; `heat_th` (as of
    2026.11.10): the measured heat per hour, used where it's there. None
    with fewer than MIN_HOUSE_ROWS hours or unlikely values.

    The time constant (as of 2026.11.10) is the one whose model plays the
    last heating days again best (the indoor temperature over each whole
    day, with the measured heat) - not the one that fits the step of one
    hour best: over one hour the temperature moves hundredths of a degree
    and the noise favours a short delay, while over a day a short delay
    drifts.

    `gains` (as of 2026.11.11): the house's own electricity per hour (all of
    it minus the heat pump and the car) - nearly all of it ends up as heat
    indoors (ironing, cooking, appliances): its own term `kg`."""
    if copm:
        heat = {h: (heat_th[h] if heat_th and h in heat_th else q * cop_at(copm, outdoor.get(h))) for h, q in heat.items()}
    windows = _sim_windows(indoor, outdoor, heat)
    best = None
    for tau in LAG_TAUS:
        w = kernel(tau)
        rows = _rows(indoor, outdoor, heat, cool, w)
        if len(rows) < MIN_HOUSE_ROWS:
            continue
        use_wind = bool(wind) and sum(1 for r in rows if wind.get(r[0]) is not None) >= 0.7 * len(rows)
        use_sun = bool(sun) and sum(1 for r in rows if sun.get(r[0]) is not None) >= 0.7 * len(rows)
        use_gains = bool(gains) and sum(1 for r in rows if gains.get(r[0]) is not None) >= 0.7 * len(rows)
        xs = [_x(h, d, lag, wind, sun, use_wind, use_sun, gains, use_gains) for h, _, d, lag in rows]
        ys = [dy for _, dy, _, _ in rows]
        coef, keep = _fit_robust(xs, ys)
        if coef is None or not 0.001 <= coef[1] <= 0.2 or coef[2] <= 0:
            continue
        xs = [xs[i] for i in keep]
        ys = [ys[i] for i in keep]
        sse = sum((y - sum(c * v for c, v in zip(coef, x))) ** 2 for x, y in zip(xs, ys))
        score = _sim_score(coef, tau, use_wind, use_sun, windows, indoor, outdoor, heat, wind, sun, gains if use_gains else None)
        key = (score if score is not None else float("inf"), sse)
        if best is None or key < best[0]:
            best = (key, tau, coef, use_wind, use_sun, ys, len(rows), sse, score, use_gains, len(rows) - len(keep))
    if best is None:
        return None
    _, tau, coef, use_wind, use_sun, ys, n, sse, score, use_gains, dropped = best
    ymean = sum(ys) / len(ys)
    sst = sum((y - ymean) ** 2 for y in ys)
    i = 3
    kw = ks = kg = None
    if use_wind:
        kw = coef[i]
        i += 1
    if use_sun:
        ks = coef[i]
        i += 1
    if use_gains:
        kg = coef[i]
    on = sorted(v for v in heat.values() if v > 0.05)
    qmax = on[int(0.95 * (len(on) - 1))] if on else 0.0
    return {
        "a": round(coef[0], 5), "k": round(coef[1], 5), "g": round(coef[2], 5),
        "kw": round(kw, 6) if kw is not None else None, "ks": round(ks, 5) if ks is not None else None,
        "tau": tau, "n": n, "r2": round(1 - sse / sst, 3) if sst > 0 else None,
        "qmax": round(max(qmax, 0.1), 3), "thermal": bool(copm),
        "day_error_c": round(score, 3) if score is not None else None,
        "kg": round(kg, 5) if kg is not None else None,
        "spikes_left_out": dropped,
    }


SIM_DAYS = 10                   # the heating days the time constant is chosen on


def _sim_windows(indoor, outdoor, heat) -> list[int]:
    """The start hours of the last SIM_DAYS whole 24-hour stretches (back
    from the newest indoor hour) with heating and everything measured."""
    if not indoor:
        return []
    last = max(indoor) - 24 * HOUR
    out = []
    start = last
    while len(out) < SIM_DAYS and start > last - 60 * 86400:
        hours = range(start, start + 24 * HOUR, HOUR)
        ok = all(indoor.get(h) is not None and outdoor.get(h) is not None and heat.get(h) is not None for h in hours)
        ok = ok and all(heat.get(start - j * HOUR) is not None for j in range(1, LAG_HOURS))
        if ok and sum(heat[h] for h in hours) >= TEST_HEAT_KWH:
            out.append(start)
        start -= 24 * HOUR
    return out


def smooth3(values: list[Optional[float]]) -> list[Optional[float]]:
    """The median of each hour and its neighbours (as of 2026.11.11): a
    one-hour jump of the room (ironing) doesn't count as the house."""
    out: list[Optional[float]] = []
    for i, v in enumerate(values):
        win = [x for x in values[max(i - 1, 0):i + 2] if x is not None]
        out.append(sorted(win)[len(win) // 2] if v is not None and win else v)
    return out


def _sim_score(coef, tau, use_wind, use_sun, windows, indoor, outdoor, heat, wind, sun, gains=None) -> Optional[float]:
    """Mean indoor temperature error (degC) of playing the windows again with
    the measured heat - the model as fitted for this time constant."""
    if not windows:
        return None
    i = 3
    kw = ks = 0.0
    if use_wind:
        kw = coef[i]
        i += 1
    if use_sun:
        ks = coef[i]
        i += 1
    kg = coef[i] if gains else 0.0
    model = {"a": coef[0], "k": coef[1], "g": coef[2], "kw": kw, "ks": ks, "kg": kg, "tau": tau, "qmax": 1e9, "thermal": False}
    err = 0.0
    n = 0
    for start in windows:
        hours = list(range(start, start + 24 * HOUR, HOUR))
        inputs = [(outdoor[h], (wind or {}).get(h) if use_wind else None, (sun or {}).get(h) if use_sun else None,
                   (gains or {}).get(h)) for h in hours]
        hist = [heat[start - j * HOUR] for j in range(LAG_HOURS - 1, 0, -1)]
        temps, _ = simulate(model, indoor[start], inputs, None, hist, None, fixed_q=[heat[h] for h in hours])
        measured = smooth3([indoor.get(h) for h in hours])
        for k in range(1, len(hours)):
            if k < len(temps) and measured[k] is not None:
                err += abs(temps[k] - measured[k])
                n += 1
    return err / n if n else None


def simulate(
    model: dict[str, Any],
    t0: float,
    inputs: list[tuple[Optional[float], Optional[float], Optional[float]]],
    target: Optional[list[float]] = None,
    q_hist: Optional[list[float]] = None,
    copm: Optional[dict[str, Any]] = None,
    fixed_q: Optional[list[float]] = None,
    on0: Optional[bool] = None,
    free: Optional[list[bool]] = None,
) -> tuple[list[float], list[float]]:
    """(indoor temperature at the start of each hour + one more, heating
    electricity per hour). `inputs` = (outdoor, wind, sun) per hour; `target`
    = the indoor temperature the emulated heat pump keeps (feed-forward of the
    heat loss at that temperature + KP of the gap); `q_hist` = the heat of the
    hours before (oldest first); `fixed_q` = electricity per hour instead of
    the controller (to check the house against measured heating).
    As of 2026.11.20, with a learned on/off thermostat in the model
    (`thermostat`, see thermostat.py): the hours played quarter by quarter -
    the demand switches on below wanted + on_c and off above wanted + off_c
    (wanted = target - mid_c), heating at the heat pump's learned power while
    on; `on0` = whether it asked for heat at the start (None: from the room).
    `free` (as of 2026.11.35): hours in which ESS Manager switched the heat
    demand itself (floor control "full") - played as it plans them, with the
    smooth controller on the wanted temperature (target - mid_c), even with a
    thermostat in the model."""
    w = kernel(model["tau"])
    th = model.get("thermostat") if fixed_q is None else None
    on = on0
    since = 10 ** 9  # s since the thermostat last switched
    a, k, g = model["a"], model["k"], model["g"]
    kw, ks = model.get("kw") or 0.0, model.get("ks") or 0.0
    kg = model.get("kg") or 0.0
    hist = list(q_hist or [])[-(LAG_HOURS - 1):]
    hist = [0.0] * (LAG_HOURS - 1 - len(hist)) + hist  # thermal heat, oldest first
    temps = [t0]
    q_el_out = []
    t = t0
    for i, row in enumerate(inputs):
        tout, wind, sun = row[0], row[1], row[2]
        # (as of 2026.11.11) the house's own electricity, when given
        gain = (row[3] if len(row) > 3 else None) or 0.0
        if tout is None:
            break
        wind = wind or 0.0
        sun = sun or 0.0
        prev = sum(w[j] * hist[-j] for j in range(1, LAG_HOURS))  # the hours before
        cop = cop_at(copm, tout) if model.get("thermal") else 1.0
        if fixed_q is not None:
            q_el = fixed_q[i] if i < len(fixed_q) and fixed_q[i] is not None else 0.0
            q = q_el * cop
        elif th and not (free and i < len(free) and free[i]):
            tgt = target[i] if target and i < len(target) else t
            sp = tgt - th["mid_c"]
            pw = thermostat.power_at(th["power"], tout)
            if model.get("thermal") and th["power"].get("units") != "th":
                pw *= cop  # the power learned as electricity, the model in heat
            pw = min(pw, model["qmax"])
            min_run = min(th.get("min_run_s") or 0, HOUR)
            min_pause = min(th.get("min_pause_s") or 0, HOUR)
            if on is None:
                on = t <= sp + th["on_c"]
            q_sum = 0.0
            tq = t
            for _ in range(4):
                qq = pw if on else 0.0
                dq = tq - tout
                tq += (a - k * dq - kw * wind * dq + ks * sun + kg * gain + g * (w[0] * qq + prev)) / 4.0
                q_sum += qq
                since += thermostat.QUARTER
                if on and tq >= sp + th["off_c"] and since >= min_run:
                    on, since = False, 0
                elif not on and tq <= sp + th["on_c"] and since >= min_pause:
                    on, since = True, 0
            q = q_sum / 4.0
            q_el = q / cop
            t = tq
            hist.append(q)
            hist = hist[-(LAG_HOURS - 1):]
            temps.append(round(t, 3))
            q_el_out.append(round(q_el, 4))
            continue
        else:
            tgt = target[i] if target and i < len(target) else t
            if th:
                # an hour ESS Manager switched (as of 2026.11.35): its own plan for
                # the wanted temperature; the thermostat's state from the room after it
                tgt -= th["mid_c"]
                on, since = None, 10 ** 9
            loss = k * (tgt - tout) + kw * wind * (tgt - tout) - ks * sun - kg * gain - a
            need = loss + KP * (tgt - t)            # degC this hour
            q = (need - g * prev) / (g * w[0])      # what this hour's heat has to add
            q = max(0.0, min(q, model["qmax"]))
            q_el = q / cop
        lag = w[0] * q + prev
        d = t - tout
        t = t + a - k * d - kw * wind * d + ks * sun + kg * gain + g * lag
        hist.append(q)
        hist = hist[-(LAG_HOURS - 1):]
        temps.append(round(t, 3))
        q_el_out.append(round(q_el, 4))
    return temps, q_el_out


# -- the self-check -----------------------------------------------------------------
def day_series(
    d: date, tz: tzinfo, indoor, outdoor, heat, wind, sun, gains=None, setpoint=None, ess=None
) -> Optional[dict[str, Any]]:
    """One day's hourly inputs for the self-check (None when incomplete)."""
    start = int(datetime(d.year, d.month, d.day, tzinfo=tz).timestamp())
    end = int(datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=tz).timestamp())
    hours = list(range(start, end, HOUR))
    if any(outdoor.get(h) is None or heat.get(h) is None for h in hours):
        return None
    temps = [indoor.get(h) for h in hours] + [indoor.get(end)]
    if temps[0] is None or sum(1 for v in temps if v is not None) < len(temps) - 3:
        return None
    hist = [heat.get(start - j * HOUR) for j in range(LAG_HOURS - 1, 0, -1)]
    if any(v is None for v in hist):
        return None
    return {
        "d": d.isoformat(),
        "hours": hours,
        "indoor": temps,
        "inputs": [(outdoor[h], (wind or {}).get(h), (sun or {}).get(h), (gains or {}).get(h)) for h in hours],
        "q": [heat[h] for h in hours],
        "q_hist": hist,
        # the thermostat's wanted temperature per hour (as of 2026.11.20), None when unknown
        "sp": [(setpoint or {}).get(h) for h in hours],
        # the hours ESS Manager switched the heat demand itself (as of 2026.11.35)
        "ess": [(ess or {}).get(h, 0) >= ESS_HOUR_S for h in hours],
    }


def review(
    model: dict[str, Any],
    copm: Optional[dict[str, Any]],
    days: list[dict[str, Any]],
    profile: Optional[list[float]],
    shape: list[float],
    tz: tzinfo,
) -> dict[str, Any]:
    """Each test day played again with its measured weather: the energy per
    hour (both scaled to the measured day total - only the placement counts)
    against the usual pattern, and the indoor temperature with the measured
    heating against the measured one. `passed` = good enough to plan with."""
    return _verdict(_review_sums(model, copm, days, profile, shape, tz))


def _review_sums(
    model: dict[str, Any],
    copm: Optional[dict[str, Any]],
    days: list[dict[str, Any]],
    profile: Optional[list[float]],
    shape: list[float],
    tz: tzinfo,
) -> list[float]:
    """The error sums of review(): [sim, pattern, blocks, temp, temp hours,
    days] - added up over the cross-validation's groups. The energy is
    compared per block of BLOCK_HOURS (as of 2026.11.35; per hour before). With a thermostat
    in the model (as of 2026.11.20) the day is played with its real wanted
    temperatures where they're known, starting with the demand on when the
    hour before heated."""
    th = model.get("thermostat")
    sim_err = pat_err = temp_err = 0.0
    n_hours = n_temp = n_days = 0
    for day in days:
        total = sum(day["q"])
        if total < TEST_HEAT_KWH:
            continue
        cop_hist = [cop_at(copm, day["inputs"][0][0])] * len(day["q_hist"]) if model.get("thermal") else [1.0] * len(day["q_hist"])
        hist_th = [q * c for q, c in zip(day["q_hist"], cop_hist)]
        level = sum(v for v in day["indoor"] if v is not None) / sum(1 for v in day["indoor"] if v is not None)
        sps = day.get("sp") or []
        on0 = None
        if th and sps and all(v is not None for v in sps):
            target = [v + th["mid_c"] for v in sps]
            on0 = (day["q_hist"][-1] or 0.0) > 0.05
        elif profile:
            hours_local = [datetime.fromtimestamp(h, tz).hour for h in day["hours"]]
            mean_p = sum(profile) / 24.0
            target = [profile[x] - mean_p + level for x in hours_local]
        else:
            target = [level] * len(day["hours"])
        # (as of 2026.11.35) in blocks of BLOCK_HOURS, each started again from the
        # measured room and the heat measured before it - as the live control
        # starts from the measurement every cycle - and compared per block:
        # whether a run lands at 3 or at 4 o'clock is the live control's, what
        # the house needs over a few hours is the model's
        n = len(day["q"])
        q_th_day = [q * (cop_at(copm, day["inputs"][j][0]) if model.get("thermal") else 1.0) for j, q in enumerate(day["q"])]
        free = day.get("ess") or []
        sims: list[float] = []
        t_end: Optional[float] = None
        for b0 in range(0, n, BLOCK_HOURS):
            b1 = min(b0 + BLOCK_HOURS, n)
            t0 = day["indoor"][b0] if day["indoor"][b0] is not None else t_end
            if t0 is None:
                break
            hist_b = (hist_th + q_th_day[:b0])[-(LAG_HOURS - 1):]
            on_b = None
            if on0 is not None:
                on_b = ((day["q"][b0 - 1] if b0 else day["q_hist"][-1]) or 0.0) > 0.05
            temps_b, q_b = simulate(model, t0, day["inputs"][b0:b1], target[b0:b1], hist_b, copm, on0=on_b,
                                    free=free[b0:b1] or None)
            if len(q_b) < b1 - b0:
                break
            sims.append(sum(q_b))
            t_end = temps_b[-1]
        if len(sims) * BLOCK_HOURS < n:
            continue
        s = sum(sims)
        pat_h = [shape[datetime.fromtimestamp(h, tz).hour] for h in day["hours"]]
        ps = sum(pat_h)
        for bi, b0 in enumerate(range(0, n, BLOCK_HOURS)):
            meas = sum(day["q"][b0:b0 + BLOCK_HOURS])
            share = min(BLOCK_HOURS, n - b0) / n
            sim_q = sims[bi] / s * total if s > 1e-6 else total * share
            pat_q = sum(pat_h[b0:b0 + BLOCK_HOURS]) / ps * total if ps > 1e-9 else total * share
            sim_err += abs(sim_q - meas)
            pat_err += abs(pat_q - meas)
            n_hours += 1
        temps, _ = simulate(model, day["indoor"][0], day["inputs"], None, hist_th, copm, fixed_q=day["q"])
        # against the room's trend, not a one-hour jump (as of 2026.11.11)
        for i, v in enumerate(smooth3(day["indoor"])):
            if v is not None and i < len(temps):
                temp_err += abs(temps[i] - v)
                n_temp += 1
        n_days += 1
    return [sim_err, pat_err, n_hours, temp_err, n_temp, n_days]


def _verdict(sums: list[float], min_days: int = MIN_TEST_DAYS) -> dict[str, Any]:
    sim_err, pat_err, n_hours, temp_err, n_temp, n_days = sums
    n_days = int(n_days)
    sim_mae = round(sim_err / n_hours, 3) if n_hours else None
    pat_mae = round(pat_err / n_hours, 3) if n_hours else None
    temp_mae = round(temp_err / n_temp, 2) if n_temp else None
    passed = (
        n_days >= min_days and sim_mae is not None and pat_mae is not None and temp_mae is not None
        and sim_mae <= GATE_RATIO * pat_mae and temp_mae <= GATE_TEMP_C
    )
    # hour_error_kwh / pattern_error_kwh: per block of block_hours (as of 2026.11.35)
    return {"days": n_days, "hour_error_kwh": sim_mae, "pattern_error_kwh": pat_mae,
            "temp_error_c": temp_mae, "passed": passed, "block_hours": BLOCK_HOURS}


def learn(
    indoor: dict[int, float],
    outdoor: dict[int, float],
    heat: dict[int, float],
    wind: Optional[dict[int, float]],
    sun: Optional[dict[int, float]],
    cool: Optional[dict[int, float]],
    cop: Optional[dict[int, float]],
    tz: tzinfo,
    today: date,
    profile: Optional[list[float]],
    shape: list[float],
    cop_min: Optional[dict[int, float]] = None,
    heat_th: Optional[dict[int, float]] = None,
    gains: Optional[dict[int, float]] = None,
    thermo: Optional[dict[str, Any]] = None,
    on_s: Optional[dict[int, int]] = None,
    setpoint: Optional[dict[int, float]] = None,
    ess_s: Optional[dict[int, int]] = None,
) -> dict[str, Any]:
    """The daily round: the COP model, the house checked on the newest
    TEST_DAYS heating days out of sample (as of 2026.11.12 cross-validated,
    with a drift guard on the newest days - _cross_review), then fitted on
    everything for the forecast. {cop, model, review}.
    `heat_th` (as of 2026.11.10, heating_heat): the measured heat into the
    house per hour - the COP from the meters, the house fitted on it.
    `thermo` / `on_s` / `setpoint` (as of 2026.11.20): the learned thermostat
    (thermostat.learn), its heat demand seconds and wanted temperature per
    hour - an on/off thermostat is tried in the self-check and kept in the
    model when it places the hours better (`thermostat` in the result: what
    was learned, with the heat pump's power while asking).
    `ess_s` (as of 2026.11.35): the seconds per hour ESS Manager switched the
    heat demand itself (floor control "full"). Those hours are played with
    the smooth controller in the self-check, and their thermostat demand
    seconds don't count for the heat pump's power - the thermostat didn't
    switch it then."""
    copm = fit_cop_meters(heat_th, heat, outdoor) if heat_th else None
    if copm is None:
        copm = fit_cop(cop, outdoor, heat, cop_min) if cop else None
    check = cop_check(cop, outdoor, heat, cop_min) if cop else None
    test_days = []
    d = today - timedelta(days=1)
    while len(test_days) < TEST_DAYS and (today - d).days <= 60:
        series = day_series(d, tz, indoor, outdoor, heat, wind, sun, gains, setpoint, ess_s)
        if series and sum(series["q"]) >= TEST_HEAT_KWH:
            test_days.append(series)
        d -= timedelta(days=1)
    result: dict[str, Any] = {"cop": copm, "cop_check": check, "model": None, "review": None}
    th = None
    if on_s and ess_s:
        on_s = {h: v for h, v in on_s.items() if not ess_s.get(h)}
    if thermo is not None:
        th = dict(thermo)
        if th.get("kind") == thermostat.KIND_ON_OFF and on_s:
            now_epoch = max(on_s)
            pw = thermostat.power(heat, on_s, outdoor, now_epoch)
            th["power_el"] = {**pw, "units": "el"} if pw else None
            pw = thermostat.power(heat_th, on_s, outdoor, now_epoch) if heat_th else None
            th["power_th"] = {**pw, "units": "th"} if pw else None
        result["thermostat"] = th
    try_th = th if th and th.get("kind") == thermostat.KIND_ON_OFF and (th.get("power_el") or th.get("power_th")) else None
    if test_days:
        result["review"] = _cross_review(test_days, indoor, outdoor, heat, wind, sun, cool, copm,
                                         heat_th, gains, profile, shape, tz, try_th)
    result["model"] = fit_house(indoor, outdoor, heat, wind, sun, cool, copm, heat_th, gains)
    rev = result["review"] or {}
    if result["model"] and try_th and (rev.get("thermostat") or {}).get("used"):
        result["model"] = with_thermostat(result["model"], try_th) or result["model"]
    if result["review"] is None:
        result["review"] = {"days": len(test_days), "hour_error_kwh": None, "pattern_error_kwh": None,
                            "temp_error_c": None, "passed": False, "method": "cross", "recent": None}
    return result


def _cross_review(test_days, indoor, outdoor, heat, wind, sun, cool, copm, heat_th, gains,
                  profile, shape, tz, thermo=None) -> Optional[dict[str, Any]]:
    """The self-check (as of 2026.11.12): cross-validation over FOLDS groups
    of the test days (spread over time: day i in group i mod FOLDS), each
    group played with a model that never saw its days; plus the drift guard
    on the newest RECENT_DAYS days (a model from only the hours before
    them). None when no group could be fitted.
    `thermo` (as of 2026.11.20): a learned on/off thermostat with the heat
    pump's power (power_el / power_th); each group is then also played with
    it, and it's used (`rev["thermostat"]["used"]`) when it places the hours
    better than the smooth controller."""
    total = [0.0] * 6
    total_th = [0.0] * 6
    folds_fitted = 0

    def with_th(m):
        return with_thermostat(m, thermo)

    for f in range(FOLDS):
        group = [d for i, d in enumerate(test_days) if i % FOLDS == f]
        if not group:
            continue
        leave_out = {h for d in group for h in d["hours"]}
        rest = {h: v for h, v in indoor.items() if h not in leave_out}
        m = fit_house(rest, outdoor, heat, wind, sun, cool, copm, heat_th, gains)
        if not m:
            continue
        folds_fitted += 1
        total = [a + b for a, b in zip(total, _review_sums(m, copm, group, profile, shape, tz))]
        mt = with_th(m)
        if mt:
            total_th = [a + b for a, b in zip(total_th, _review_sums(mt, copm, group, profile, shape, tz))]
    if not folds_fitted:
        return None
    rev_ctrl = _verdict(total)
    use_th = False
    th_info = None
    if thermo and total_th[2]:
        rev_th = _verdict(total_th)
        use_th = (rev_th["hour_error_kwh"] is not None and rev_ctrl["hour_error_kwh"] is not None
                  and rev_th["hour_error_kwh"] < rev_ctrl["hour_error_kwh"])
        th_info = {"hour_error_kwh": rev_th["hour_error_kwh"], "temp_error_c": rev_th["temp_error_c"],
                   "controller_hour_error_kwh": rev_ctrl["hour_error_kwh"], "used": use_th}
    rev = _verdict(total_th) if use_th else rev_ctrl
    rev["method"] = "cross"
    rev["folds"] = folds_fitted
    # (as of 2026.11.35) the test hours ESS Manager switched the heat demand itself
    rev["ess_hours"] = sum(sum(1 for x in d.get("ess") or [] if x) for d in test_days)
    rev["thermostat"] = th_info
    # the drift guard: test_days are newest first
    recent_days = test_days[:RECENT_DAYS]
    recent = None
    cutoff = min(d["hours"][0] for d in recent_days)
    m_old = fit_house({h: v for h, v in indoor.items() if h < cutoff}, outdoor, heat, wind, sun, cool,
                      copm, heat_th, gains)
    if m_old and use_th:
        m_old = with_th(m_old)
    if m_old:
        r = _verdict(_review_sums(m_old, copm, recent_days, profile, shape, tz), RECENT_MIN_DAYS)
        if r["days"] >= RECENT_MIN_DAYS and r["hour_error_kwh"] is not None:
            drift = (r["hour_error_kwh"] > r["pattern_error_kwh"]
                     or (r["temp_error_c"] is not None and r["temp_error_c"] > RECENT_TEMP_C))
            recent = {"days": r["days"], "hour_error_kwh": r["hour_error_kwh"],
                      "pattern_error_kwh": r["pattern_error_kwh"], "temp_error_c": r["temp_error_c"],
                      "drift": drift}
    rev["recent"] = recent
    if recent and recent["drift"]:
        rev["passed"] = False
    return rev


def without_thermostat(model: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The model with the smooth controller (as of 2026.11.35): for what ESS
    Manager plans itself - the floor's heat per hour, and the forecast while
    it switches the heat demand - the learned thermostat only describes the
    hours the thermostat switches."""
    if not model or not model.get("thermostat"):
        return model
    return {k: v for k, v in model.items() if k != "thermostat"}


def with_thermostat(model: dict[str, Any], thermo: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The model with the learned thermostat in it (as of 2026.11.20) - the
    heat pump's power in the model's units where measured (the heat meter
    for a model in heat), else as electricity (simulate turns it into heat
    with the COP). None without a thermostat or power."""
    if not thermo:
        return None
    pw = (thermo.get("power_th") if model.get("thermal") else None) or thermo.get("power_el")
    if not pw:
        return None
    keep = {k: thermo.get(k) for k in ("on_c", "off_c", "mid_c", "min_run_s", "min_pause_s")}
    return {**model, "thermostat": {**keep, "power": pw}}


def stage_of(model: Optional[dict[str, Any]], rev: Optional[dict[str, Any]], steering: bool) -> str:
    if not model:
        return STAGE_LEARNING
    if not rev or not rev.get("passed"):
        return STAGE_SHADOW
    return STAGE_STEERING if steering else STAGE_USED


def targets(profile: Optional[list[float]], level: Optional[float], hour0: int, hours: int, tz: tzinfo,
            fallback: Optional[float] = None) -> Optional[list[float]]:
    """The indoor temperature per forecast hour the house is kept at: the
    usual one per hour, moved to `level` (the expected indoor temperature of
    the coming days - lower on holiday)."""
    if profile:
        mean_p = sum(profile) / 24.0
        shift = (level - mean_p) if level is not None else 0.0
        return [round(profile[datetime.fromtimestamp(hour0 + i * HOUR, tz).hour] + shift, 2) for i in range(hours)]
    base = level if level is not None else fallback
    return [base] * hours if base is not None else None


def reshape(total: list[float], q_sim: list[float], base_hour: float, hour0: int, tz: tzinfo,
            day_shape: list[float]) -> list[float]:
    """The forecast with the heat pump's day totals placed by the simulation
    instead of the hourly pattern, for the days (or rest of today) it covers
    fully: each day's kWh in those hours stays the same."""
    out = list(total)
    by_day: dict[str, list[int]] = {}
    for i in range(min(len(total), len(q_sim))):
        by_day.setdefault(datetime.fromtimestamp(hour0 + i * HOUR, tz).date().isoformat(), []).append(i)
    covered = len(q_sim)
    for d, idx in by_day.items():
        last_hour = datetime.fromtimestamp(hour0 + idx[-1] * HOUR, tz).hour
        if last_hour != 23 and idx[-1] >= covered - 1:
            continue  # the day goes on past the simulation: keep the pattern
        kwh = sum(total[i] for i in idx)
        weights = [q_sim[i] + base_hour for i in idx]
        ws = sum(weights)
        if kwh <= 0 or ws <= 1e-9:
            continue
        for i, wv in zip(idx, weights):
            out[i] = round(kwh * wv / ws, 4)
    return out


def _cost(q_el: list[float], buy: list[float], sell: list[float], surplus: list[float]) -> float:
    cost = 0.0
    for i, q in enumerate(q_el):
        if i >= len(buy):
            break
        free = max(surplus[i], 0.0) if i < len(surplus) else 0.0
        own = min(q, free)
        cost += own * (sell[i] if i < len(sell) else buy[i]) + (q - own) * buy[i]
    return cost


def preheat_advice(
    model: dict[str, Any],
    copm: Optional[dict[str, Any]],
    t0: float,
    inputs: list[tuple[Optional[float], Optional[float], Optional[float]]],
    target: list[float],
    q_hist: list[float],
    buy: list[float],
    sell: list[float],
    surplus: list[float],
) -> Optional[dict[str, Any]]:
    """The cheapest window (starting within 24 hours, BOOST_WINDOWS long) to
    keep the house BOOST_C warmer, compared over ADVICE_HORIZON hours (or the
    hours with prices): {start, hours, saving, cost, extra_kwh} or None when
    nothing saves MIN_SAVING."""
    horizon = min(ADVICE_HORIZON, len(buy), len(inputs), len(target))
    if horizon < MIN_PRICE_HOURS:
        return None
    inp, tgt = inputs[:horizon], target[:horizon]
    _, base_q = simulate(model, t0, inp, tgt, q_hist, copm)
    base_cost = _cost(base_q, buy, sell, surplus)
    best = None
    for start in range(0, min(24, horizon - 2)):
        for n in BOOST_WINDOWS:
            if start + n > horizon:
                continue
            t2 = [v + (BOOST_C if start <= i < start + n else 0.0) for i, v in enumerate(tgt)]
            _, q = simulate(model, t0, inp, t2, q_hist, copm)
            saving = base_cost - _cost(q, buy, sell, surplus)
            if best is None or saving > best["saving"]:
                best = {"start": start, "hours": n, "saving": round(saving, 3),
                        "extra_kwh": round(sum(q[start:start + n]) - sum(base_q[start:start + n]), 2),
                        "cost": round(base_cost, 3)}
    if best is None or best["saving"] < MIN_SAVING:
        return None
    return best


def plan_buffer(
    model: dict[str, Any],
    copm: Optional[dict[str, Any]],
    t0: float,
    inputs: list[tuple[Optional[float], Optional[float], Optional[float]]],
    base: list[float],
    q_hist: list[float],
    buy: list[float],
    sell: list[float],
    surplus: list[float],
    delta: float,
) -> Optional[dict[str, Any]]:
    """The house as a buffer within +-delta of the wanted temperature per
    hour (`base`, day/night): the cheapest window to keep it `delta` warmer
    (heat in cheap or sunny hours - an evening boost before a cold night),
    then the window to let it `delta` cooler (the most expensive hours),
    each only when it saves MIN_SAVING. {offsets per hour, boost, dip,
    saving} over the hours with prices; None without prices or delta."""
    horizon = min(ADVICE_HORIZON, len(buy), len(inputs), len(base))
    if horizon < MIN_PRICE_HOURS or delta <= 0:
        return None
    inp, tgt = inputs[:horizon], base[:horizon]

    def cost_of(offsets):
        _, q = simulate(model, t0, inp, [v + o for v, o in zip(tgt, offsets)], q_hist, copm)
        return _cost(q, buy, sell, surplus), q

    zero = [0.0] * horizon
    base_cost, base_q = cost_of(zero)
    mean_price = sum(buy[:horizon]) / horizon

    def best_window(current, sign, cur_cost, cur_q, taken):
        # a warmer window has to save money outright; a cooler one only
        # counts what it moves to cheaper hours - being colder on its own
        # isn't a saving the buffer may make
        best = None
        for start in range(0, min(24, horizon - 1)):
            for n in BOOST_WINDOWS:
                if start + n > horizon or any(taken[i] for i in range(start, start + n)):
                    continue
                trial = [o + (sign * delta if start <= i < start + n else 0.0) for i, o in enumerate(current)]
                c, q = cost_of(trial)
                saving = cur_cost - c
                if sign < 0:
                    saving -= max(sum(cur_q) - sum(q), 0.0) * mean_price
                if saving >= MIN_SAVING and (best is None or saving > best[0]):
                    best = (saving, start, n, trial, c, q)
        return best

    offsets, cost, taken = zero, base_cost, [False] * horizon
    boost = dip = None
    b = best_window(offsets, 1.0, cost, base_q, taken)
    if b:
        boost = {"start": b[1], "hours": b[2], "saving": round(b[0], 3),
                 "extra_kwh": round(sum(b[5][b[1]:b[1] + b[2]]) - sum(base_q[b[1]:b[1] + b[2]]), 2)}
        offsets, cost = b[3], b[4]
        taken = [taken[i] or b[1] <= i < b[1] + b[2] for i in range(horizon)]
    d = best_window(offsets, -1.0, cost, b[5] if b else base_q, taken)
    if d:
        dip = {"start": d[1], "hours": d[2], "saving": round(d[0], 3)}
        offsets, cost = d[3], d[4]
    if not boost and not dip:
        return {"offsets": zero, "boost": None, "dip": None, "saving": 0.0, "cost": round(base_cost, 3)}
    saving = (boost["saving"] if boost else 0.0) + (dip["saving"] if dip else 0.0)
    return {"offsets": offsets, "boost": boost, "dip": dip, "saving": round(saving, 3), "cost": round(base_cost, 3)}


def day_night(day_temp: float, night_temp: float, day_from: int, night_from: int,
              hour0: int, hours: int, tz: tzinfo) -> list[float]:
    """The wanted temperature per hour from a day and a night setting."""
    out = []
    for i in range(hours):
        h = datetime.fromtimestamp(hour0 + i * HOUR, tz).hour
        if day_from <= night_from:
            is_day = day_from <= h < night_from
        else:
            is_day = h >= day_from or h < night_from
        out.append(day_temp if is_day else night_temp)
    return out


def hourly_prices(units: list[float], units_per_day: int, day_start: int, hour0: int, hours: int) -> list[float]:
    """Hourly means of a day-aligned price list (24 or 96 units a day) from hour0."""
    if not units or units_per_day <= 0:
        return []
    per_hour = max(units_per_day // 24, 1)
    out = []
    first = (hour0 - day_start) // HOUR
    for i in range(hours):
        a = (first + i) * per_hour
        chunk = units[a:a + per_hour]
        if len(chunk) < per_hour:
            break
        out.append(sum(chunk) / per_hour)
    return out
