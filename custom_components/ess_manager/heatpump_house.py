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

HOUR = 3600
LAG_HOURS = 12                  # the floor's delay: the heat of the last 12 hours
LAG_TAUS = [1.0, 2.0, 3.0, 4.0, 6.0]  # its time constant (h), the best fit chosen
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
def fit_cop(cop: dict[int, float], outdoor: dict[int, float], heat: dict[int, float]) -> Optional[dict[str, Any]]:
    """COP = c0 + c1 x outdoor from the hours the heat pump heated (the COP
    sensor's hourly means). None with fewer than MIN_COP_HOURS such hours."""
    pts = [(outdoor[h], c) for h, c in cop.items()
           if h in outdoor and heat.get(h, 0.0) > 0.1 and 1.0 < c < 10.0]
    if len(pts) < MIN_COP_HOURS:
        return None
    n = len(pts)
    mx = sum(t for t, _ in pts) / n
    my = sum(c for _, c in pts) / n
    sxx = sum((t - mx) ** 2 for t, _ in pts)
    c1 = sum((t - mx) * (c - my) for t, c in pts) / sxx if sxx > 1e-9 else 0.0
    c0 = my - c1 * mx
    return {"c0": round(c0, 3), "c1": round(c1, 4), "n": n}


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


def _x(h, d, lag, wind, sun, use_wind, use_sun):
    x = [1.0, -d, lag]
    if use_wind:
        x.append(-(wind.get(h) or 0.0) * d)
    if use_sun:
        x.append(sun.get(h) or 0.0)
    return x


def fit_house(
    indoor: dict[int, float],
    outdoor: dict[int, float],
    heat: dict[int, float],
    wind: Optional[dict[int, float]] = None,
    sun: Optional[dict[int, float]] = None,
    cool: Optional[dict[int, float]] = None,
    copm: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """dT(indoor, next hour) = a - k x d + g x heat(lagged) - kw x wind x d +
    ks x sun, d = indoor - outdoor, the heat delayed by the floor (kernel,
    its time constant the best fit). With a COP model the heat is the heat
    pump's heat (electricity x COP), else its electricity. None with fewer
    than MIN_HOUSE_ROWS hours or unlikely values."""
    if copm:
        heat = {h: q * cop_at(copm, outdoor.get(h)) for h, q in heat.items()}
    best = None
    for tau in LAG_TAUS:
        w = kernel(tau)
        rows = _rows(indoor, outdoor, heat, cool, w)
        if len(rows) < MIN_HOUSE_ROWS:
            continue
        use_wind = bool(wind) and sum(1 for r in rows if wind.get(r[0]) is not None) >= 0.7 * len(rows)
        use_sun = bool(sun) and sum(1 for r in rows if sun.get(r[0]) is not None) >= 0.7 * len(rows)
        xs = [_x(h, d, lag, wind, sun, use_wind, use_sun) for h, _, d, lag in rows]
        ys = [dy for _, dy, _, _ in rows]
        k = len(xs[0])
        ata = [[sum(x[i] * x[j] for x in xs) for j in range(k)] for i in range(k)]
        atb = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(k)]
        coef = _solve(ata, atb)
        if coef is None or not 0.001 <= coef[1] <= 0.2 or coef[2] <= 0:
            continue
        sse = sum((y - sum(c * v for c, v in zip(coef, x))) ** 2 for x, y in zip(xs, ys))
        if best is None or sse < best[0]:
            best = (sse, tau, coef, use_wind, use_sun, ys, len(rows))
    if best is None:
        return None
    sse, tau, coef, use_wind, use_sun, ys, n = best
    ymean = sum(ys) / len(ys)
    sst = sum((y - ymean) ** 2 for y in ys)
    i = 3
    kw = ks = None
    if use_wind:
        kw = coef[i]
        i += 1
    if use_sun:
        ks = coef[i]
    on = sorted(v for v in heat.values() if v > 0.05)
    qmax = on[int(0.95 * (len(on) - 1))] if on else 0.0
    return {
        "a": round(coef[0], 5), "k": round(coef[1], 5), "g": round(coef[2], 5),
        "kw": round(kw, 6) if kw is not None else None, "ks": round(ks, 5) if ks is not None else None,
        "tau": tau, "n": n, "r2": round(1 - sse / sst, 3) if sst > 0 else None,
        "qmax": round(max(qmax, 0.1), 3), "thermal": bool(copm),
    }


def simulate(
    model: dict[str, Any],
    t0: float,
    inputs: list[tuple[Optional[float], Optional[float], Optional[float]]],
    target: Optional[list[float]] = None,
    q_hist: Optional[list[float]] = None,
    copm: Optional[dict[str, Any]] = None,
    fixed_q: Optional[list[float]] = None,
) -> tuple[list[float], list[float]]:
    """(indoor temperature at the start of each hour + one more, heating
    electricity per hour). `inputs` = (outdoor, wind, sun) per hour; `target`
    = the indoor temperature the emulated heat pump keeps (feed-forward of the
    heat loss at that temperature + KP of the gap); `q_hist` = the heat of the
    hours before (oldest first); `fixed_q` = electricity per hour instead of
    the controller (to check the house against measured heating)."""
    w = kernel(model["tau"])
    a, k, g = model["a"], model["k"], model["g"]
    kw, ks = model.get("kw") or 0.0, model.get("ks") or 0.0
    hist = list(q_hist or [])[-(LAG_HOURS - 1):]
    hist = [0.0] * (LAG_HOURS - 1 - len(hist)) + hist  # thermal heat, oldest first
    temps = [t0]
    q_el_out = []
    t = t0
    for i, (tout, wind, sun) in enumerate(inputs):
        if tout is None:
            break
        wind = wind or 0.0
        sun = sun or 0.0
        prev = sum(w[j] * hist[-j] for j in range(1, LAG_HOURS))  # the hours before
        cop = cop_at(copm, tout) if model.get("thermal") else 1.0
        if fixed_q is not None:
            q_el = fixed_q[i] if i < len(fixed_q) and fixed_q[i] is not None else 0.0
            q = q_el * cop
        else:
            tgt = target[i] if target and i < len(target) else t
            loss = k * (tgt - tout) + kw * wind * (tgt - tout) - ks * sun - a
            need = loss + KP * (tgt - t)            # degC this hour
            q = (need - g * prev) / (g * w[0])      # what this hour's heat has to add
            q = max(0.0, min(q, model["qmax"]))
            q_el = q / cop
        lag = w[0] * q + prev
        d = t - tout
        t = t + a - k * d - kw * wind * d + ks * sun + g * lag
        hist.append(q)
        hist = hist[-(LAG_HOURS - 1):]
        temps.append(round(t, 3))
        q_el_out.append(round(q_el, 4))
    return temps, q_el_out


# -- the self-check -----------------------------------------------------------------
def day_series(
    d: date, tz: tzinfo, indoor, outdoor, heat, wind, sun
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
        "inputs": [(outdoor[h], (wind or {}).get(h), (sun or {}).get(h)) for h in hours],
        "q": [heat[h] for h in hours],
        "q_hist": hist,
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
    sim_err = pat_err = temp_err = 0.0
    n_hours = n_temp = n_days = 0
    for day in days:
        total = sum(day["q"])
        if total < TEST_HEAT_KWH:
            continue
        cop_hist = [cop_at(copm, day["inputs"][0][0])] * len(day["q_hist"]) if model.get("thermal") else [1.0] * len(day["q_hist"])
        hist_th = [q * c for q, c in zip(day["q_hist"], cop_hist)]
        level = sum(v for v in day["indoor"] if v is not None) / sum(1 for v in day["indoor"] if v is not None)
        if profile:
            hours_local = [datetime.fromtimestamp(h, tz).hour for h in day["hours"]]
            mean_p = sum(profile) / 24.0
            target = [profile[x] - mean_p + level for x in hours_local]
        else:
            target = [level] * len(day["hours"])
        _, q_sim = simulate(model, day["indoor"][0], day["inputs"], target, hist_th, copm)
        s = sum(q_sim)
        if len(q_sim) < len(day["q"]):
            continue
        pat = [shape[datetime.fromtimestamp(h, tz).hour] for h in day["hours"]]
        ps = sum(pat)
        for i, q in enumerate(day["q"]):
            sim_q = q_sim[i] / s * total if s > 1e-6 else total / len(day["q"])
            pat_q = pat[i] / ps * total if ps > 1e-9 else total / len(day["q"])
            sim_err += abs(sim_q - q)
            pat_err += abs(pat_q - q)
            n_hours += 1
        temps, _ = simulate(model, day["indoor"][0], day["inputs"], None, hist_th, copm, fixed_q=day["q"])
        for i, v in enumerate(day["indoor"]):
            if v is not None and i < len(temps):
                temp_err += abs(temps[i] - v)
                n_temp += 1
        n_days += 1
    sim_mae = round(sim_err / n_hours, 3) if n_hours else None
    pat_mae = round(pat_err / n_hours, 3) if n_hours else None
    temp_mae = round(temp_err / n_temp, 2) if n_temp else None
    passed = (
        n_days >= MIN_TEST_DAYS and sim_mae is not None and pat_mae is not None and temp_mae is not None
        and sim_mae <= GATE_RATIO * pat_mae and temp_mae <= GATE_TEMP_C
    )
    return {"days": n_days, "hour_error_kwh": sim_mae, "pattern_error_kwh": pat_mae,
            "temp_error_c": temp_mae, "passed": passed}


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
) -> dict[str, Any]:
    """The daily round: the COP model, the house fitted on the hours before
    the newest TEST_DAYS heating days and checked on those (out of sample),
    then fitted again on everything for the forecast. {cop, model, review}."""
    copm = fit_cop(cop, outdoor, heat) if cop else None
    test_days = []
    d = today - timedelta(days=1)
    while len(test_days) < TEST_DAYS and (today - d).days <= 60:
        series = day_series(d, tz, indoor, outdoor, heat, wind, sun)
        if series and sum(series["q"]) >= TEST_HEAT_KWH:
            test_days.append(series)
        d -= timedelta(days=1)
    result: dict[str, Any] = {"cop": copm, "model": None, "review": None}
    if test_days:
        cutoff = min(day["hours"][0] for day in test_days)
        older = {h: v for h, v in indoor.items() if h < cutoff}
        fit_old = fit_house(older, outdoor, heat, wind, sun, cool, copm)
        if fit_old:
            result["review"] = review(fit_old, copm, test_days, profile, shape, tz)
    result["model"] = fit_house(indoor, outdoor, heat, wind, sun, cool, copm)
    if result["review"] is None:
        result["review"] = {"days": len(test_days), "hour_error_kwh": None, "pattern_error_kwh": None,
                            "temp_error_c": None, "passed": False}
    return result


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
