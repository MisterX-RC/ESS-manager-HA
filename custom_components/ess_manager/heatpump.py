"""Heat pump model (as of 2026.10.16) - pure Python, no Home Assistant
imports, unit-tested in tests/test_pipeline.py.

A heat pump's electricity follows the weather: the 6-week average of the
household usage forecast underestimates it in autumn and overestimates it in
spring. So, like the electric car, the heat pump's own energy is taken out
of the household usage history, and its forecast comes from a model:

- a JOURNAL of days (one row per local day: the heat pump's energy, the mean
  outdoor temperature, wind, wind direction, sun, the thermostat setpoint),
  up to two years, kept in the integration's store and filled from the
  long-term statistics at the start;
- the SLOW part, an energy signature per day fitted on the journal:
      kWh = base + b x HDD + c x wind x HDD (+ direction) - d x sun + k x CDD
  HDD = degrees below the balance temperature (fitted), CDD = degrees above
  the cooling temperature (fitted, only with cooling data), both on a
  smoothed outdoor temperature (floor heating reacts slowly). Recent days
  weigh more (half-life ~ a season); the newest days of each temperature
  class keep weight, so last winter's frost days count until newer ones
  replace them;
- the FAST part: a correction factor from the last few days (measured
  against the model), which fades when the difference goes;
- day totals spread over the hours with the recent hourly pattern.

Metering: separate sensors (heating + cooling; hot water stays in the
house usage), one total sensor (hot water becomes the model's daily base),
or none (the model works on the total household usage and only adds the
weather difference to the usual forecast).
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, Callable, Optional

HOUR = 3600
METER_SEPARATE = "separate"
METER_TOTAL = "total"
METER_NONE = "none"

STATE_ACTIVE = "active"
STATE_LEARNING = "learning"
STATE_SUMMER = "summer"
STATE_FALLBACK = "fallback"

JOURNAL_DAYS = 730
HALF_LIFE_DAYS = 90.0
CLASS_WIDTH = 2.5
KEEP_PER_CLASS = 3
KEEP_WEIGHT = 0.5
SMOOTH = 0.7  # today's share of the effective temperature, yesterday's is the rest
MIN_ROWS = 14
MIN_HEATING_DAYS = 21
MIN_DIRECTION_DAYS = 30
POOR_R2 = 0.3
SHAPE_DAYS = 14
CORRECTION_DAYS = 4
CORRECTION_MIN = 0.05
TB_RANGE = [x / 2 for x in range(20, 41)]  # 10 .. 20 degC
TC_RANGE = [float(x) for x in range(20, 29)]  # 20 .. 28 degC


# -- journal --------------------------------------------------------------------
def local_day_start(d: date, tz: tzinfo) -> int:
    return int(datetime.combine(d, time(0), tzinfo=tz).timestamp())


def hourly_deltas(series: dict[int, float]) -> dict[int, float]:
    """A cumulative hourly 'sum' series -> energy per hour (hour start epoch);
    negative steps (a meter reset) count as 0."""
    out: dict[int, float] = {}
    for epoch, value in series.items():
        prev = series.get(epoch - HOUR)
        if prev is not None:
            out[epoch] = max(value - prev, 0.0)
    return out


def add_series(*series: dict[int, float]) -> dict[int, float]:
    """Hour-by-hour sum of several per-hour series - an hour counts only when
    every series has it."""
    present = [s for s in series if s is not None]
    if not present:
        return {}
    keys = set(present[0])
    for s in present[1:]:
        keys &= set(s)
    return {k: sum(s[k] for s in present) for k in keys}


def build_rows(
    first: date,
    last: date,
    tz: tzinfo,
    energy: dict[int, float],
    temp: dict[int, float],
    parts: Optional[dict[str, dict[int, float]]] = None,
    wind: Optional[dict[int, float]] = None,
    sun: Optional[dict[int, float]] = None,
) -> list[dict[str, Any]]:
    """Journal rows for the local days first..last from hourly data (energy
    per hour, mean temperature per hour, ...). A day needs 20 of its hours of
    energy and 16 of temperature; `parts` (heat/cool) are kept per day too;
    `hours` is the day's hourly energy (for the hourly pattern)."""
    rows: list[dict[str, Any]] = []
    d = first
    while d <= last:
        start = local_day_start(d, tz)
        end = local_day_start(d + timedelta(days=1), tz)
        hours = list(range(start, end, HOUR))
        e_vals = [energy.get(h) for h in hours]
        t_vals = [temp.get(h) for h in hours if temp.get(h) is not None]
        if sum(v is not None for v in e_vals) >= len(hours) - 4 and len(t_vals) >= 16:
            have = [v for v in e_vals if v is not None]
            scale = len(hours) / len(have)
            row: dict[str, Any] = {
                "d": d.isoformat(),
                "e": round(sum(have) * scale, 3),
                "t": round(sum(t_vals) / len(t_vals), 2),
                "hours": [round(v, 3) if v is not None else None for v in e_vals],
            }
            for name, series in (parts or {}).items():
                vals = [series.get(h) for h in hours if series.get(h) is not None]
                row[name] = round(sum(vals) * len(hours) / max(len(vals), 1), 3) if vals else None
            if wind:
                w = [wind.get(h) for h in hours if wind.get(h) is not None]
                row["w"] = round(sum(w) / len(w), 2) if len(w) >= 12 else None
            if sun:
                s = [sun.get(h) for h in hours if sun.get(h) is not None]
                row["s"] = round(sum(s), 2) if len(s) >= 20 else None
            rows.append(row)
        d += timedelta(days=1)
    return rows


def merge_rows(journal: list[dict[str, Any]], new: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """New rows replace rows of the same day, but keep what only the live
    record has (wind direction, setpoint, sun forecast, wind) when the new row
    lacks it. Pruned to JOURNAL_DAYS; sorted by day."""
    by_day = {r["d"]: r for r in journal}
    for r in new:
        old = by_day.get(r["d"], {})
        merged = {**old, **{k: v for k, v in r.items() if v is not None}}
        by_day[r["d"]] = merged
    cutoff = (today - timedelta(days=JOURNAL_DAYS)).isoformat()
    return [by_day[k] for k in sorted(by_day) if k >= cutoff]


def effective_temps(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Smoothed outdoor temperature per day: SMOOTH x today + the rest x the
    day before (when the journal has it)."""
    out: dict[str, float] = {}
    by_day = {r["d"]: r for r in rows if r.get("t") is not None}
    for d, r in by_day.items():
        prev = by_day.get((date.fromisoformat(d) - timedelta(days=1)).isoformat())
        out[d] = round(SMOOTH * r["t"] + (1 - SMOOTH) * prev["t"], 2) if prev else r["t"]
    return out


def temp_class(t: float) -> int:
    return int(math.floor(t / CLASS_WIDTH))


# -- fit --------------------------------------------------------------------------
def _solve(a: list[list[float]], b: list[float]) -> Optional[list[float]]:
    """Gaussian elimination with partial pivoting (a tiny ridge keeps it
    stable); None when singular."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        m[i][i] += 1e-9
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                if f:
                    for c in range(col, n + 1):
                        m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def _features(row: dict[str, Any], teff: float, tb: float, tc: Optional[float], use: dict[str, Any]) -> list[float]:
    sp_off = (row.get("sp") - use["sp_ref"]) if use.get("sp") and row.get("sp") is not None else 0.0
    hdd = max(0.0, tb + sp_off - teff)
    x = [1.0, hdd]
    if use.get("wind"):
        w = row.get("w") or 0.0
        x.append(w * hdd)
        if use.get("dir"):
            wd = row.get("wd")
            if wd is None:
                x += [0.0, 0.0]
            else:
                x += [w * hdd * math.cos(math.radians(wd)), w * hdd * math.sin(math.radians(wd))]
    if use.get("sun"):
        x.append((row.get("s") or 0.0) * (1.0 if hdd > 0 else 0.0))
    if tc is not None:
        x.append(max(0.0, teff - tc))
    return x


def _weights(rows: list[dict[str, Any]], teffs: dict[str, float], today: date) -> list[float]:
    """Recency weight (half-life HALF_LIFE_DAYS), at least KEEP_WEIGHT for the
    newest KEEP_PER_CLASS days of each temperature class."""
    newest: dict[int, list[str]] = {}
    for r in sorted(rows, key=lambda r: r["d"], reverse=True):
        cls = temp_class(teffs[r["d"]])
        lst = newest.setdefault(cls, [])
        if len(lst) < KEEP_PER_CLASS:
            lst.append(r["d"])
    keep = {d for lst in newest.values() for d in lst}
    out = []
    for r in rows:
        age = (today - date.fromisoformat(r["d"])).days
        w = 0.5 ** (max(age, 0) / HALF_LIFE_DAYS)
        if r["d"] in keep:
            w = max(w, KEEP_WEIGHT)
        out.append(w)
    return out


def _wls(rows, teffs, weights, tb, tc, use):
    xs = [_features(r, teffs[r["d"]], tb, tc, use) for r in rows]
    ys = [r["e"] for r in rows]
    k = len(xs[0])
    ata = [[0.0] * k for _ in range(k)]
    atb = [0.0] * k
    for x, y, w in zip(xs, ys, weights):
        for i in range(k):
            wi = w * x[i]
            atb[i] += wi * y
            row = ata[i]
            for j in range(i, k):
                row[j] += wi * x[j]
    for i in range(k):
        for j in range(i):
            ata[i][j] = ata[j][i]
    coef = _solve(ata, atb)
    if coef is None:
        return None
    sse = sum(w * (y - sum(c * v for c, v in zip(coef, x))) ** 2 for x, y, w in zip(xs, ys, weights))
    return coef, sse


def fit(journal: list[dict[str, Any]], today: date, with_cooling: bool = False) -> Optional[dict[str, Any]]:
    """The energy signature fitted on the journal, or None with fewer than
    MIN_ROWS usable days. Grid search over the balance temperature (and the
    cooling temperature), weighted least squares for the rest; a candidate
    with heating getting cheaper in the cold, or a negative base, is skipped."""
    rows = [r for r in journal if r.get("e") is not None and r.get("t") is not None and r["d"] < today.isoformat()]
    if len(rows) < MIN_ROWS:
        return None
    teffs = effective_temps(rows)
    weights = _weights(rows, teffs, today)
    cold = [r for r in rows if teffs[r["d"]] < 15.0]
    share = lambda key: (sum(1 for r in cold if r.get(key) is not None) / len(cold)) if cold else 0.0
    sps = [r["sp"] for r in rows if r.get("sp") is not None]
    use: dict[str, Any] = {
        "wind": share("w") >= 0.6,
        "sun": share("s") >= 0.6,
        "sp": share("sp") >= 0.6 and len(sps) >= MIN_ROWS and (max(sps) - min(sps)) >= 0.3,
        "sp_ref": sorted(sps)[len(sps) // 2] if sps else 20.0,
    }
    dir_days = [r for r in cold if r.get("wd") is not None and r.get("w") is not None]
    sectors = {int(((r["wd"] + 45) % 360) // 90) for r in dir_days}
    use["dir"] = use["wind"] and len(dir_days) >= MIN_DIRECTION_DAYS and len(sectors) >= 3

    def valid(coef):
        return coef[0] >= -0.05 and coef[1] >= 0.0

    best = None
    for tb in TB_RANGE:
        res = _wls(rows, teffs, weights, tb, None, use)
        if res and valid(res[0]) and (best is None or res[1] < best[2]):
            best = (tb, None, res[1], res[0])
    if best is None:
        return None
    if with_cooling and sum(1 for r in rows if teffs[r["d"]] >= 20.0) >= 10:
        for tc in TC_RANGE:
            res = _wls(rows, teffs, weights, best[0], tc, use)
            if res and valid(res[0]) and res[0][-1] > 0 and res[1] < best[2]:
                best = (best[0], tc, res[1], res[0])
    tb, tc, sse, coef = best
    wsum = sum(weights)
    ymean = sum(w * r["e"] for w, r in zip(weights, rows)) / wsum
    sst = sum(w * (r["e"] - ymean) ** 2 for w, r in zip(weights, rows))
    model = {"tb": tb, "tc": tc, "coef": [round(c, 5) for c in coef], "use": use}
    recent = [r for r in rows if (today - date.fromisoformat(r["d"])).days <= 14]
    errs = [abs(r["e"] - predict_row(model, r, teffs[r["d"]])) for r in recent]
    model.update({
        "r2": round(1 - sse / sst, 3) if sst > 0 else None,
        "mae14": round(sum(errs) / len(errs), 2) if errs else None,
        "rows": len(rows),
        "heating_days": sum(1 for r in rows if teffs[r["d"]] <= tb - 1.0),
        "oldest": rows[0]["d"],
    })
    return model


def predict_row(model: dict[str, Any], row: dict[str, Any], teff: float) -> float:
    x = _features(row, teff, model["tb"], model["tc"], model["use"])
    return max(sum(c * v for c, v in zip(model["coef"], x)), 0.0)


def summary(model: dict[str, Any]) -> dict[str, Any]:
    """The model's figures for the card and the diagnostic sensor."""
    coef, use = model["coef"], model["use"]
    i = 2
    wind = direction = sun = cool = None
    if use.get("wind"):
        wind = coef[i]
        i += 1
        if use.get("dir"):
            direction = [coef[i], coef[i + 1]]
            i += 2
    if use.get("sun"):
        sun = coef[i]
        i += 1
    if model["tc"] is not None:
        cool = coef[i]
    return {
        "balance_temp_c": model["tb"],
        "kwh_per_degree_day": round(coef[1], 3),
        "base_kwh_day": round(max(coef[0], 0.0), 2),
        "wind_kwh_per_ms_degree": round(wind, 4) if wind is not None else None,
        "wind_direction_terms": [round(v, 4) for v in direction] if direction else None,
        "solar_kwh_per_kwh": round(sun, 3) if sun is not None else None,
        "cooling_temp_c": model["tc"],
        "cooling_kwh_per_degree_day": round(cool, 3) if cool is not None else None,
        "setpoint_ref_c": use["sp_ref"] if use.get("sp") else None,
        "r2": model.get("r2"),
        "mae_14d_kwh": model.get("mae14"),
        "heating_days": model.get("heating_days"),
    }


# -- fast part ----------------------------------------------------------------------
def correction(model: dict[str, Any], journal: list[dict[str, Any]], today: date) -> float:
    """Measured / model over the last CORRECTION_DAYS complete days (days the
    model expects at least 1 kWh), between 0.6 and 1.6; 1.0 with fewer than
    two such days or less than CORRECTION_MIN difference."""
    rows = [r for r in journal if r.get("e") is not None and r.get("t") is not None and r["d"] < today.isoformat()]
    teffs = effective_temps(rows)
    recent = [r for r in rows if (today - date.fromisoformat(r["d"])).days <= CORRECTION_DAYS]
    pairs = [(r["e"], predict_row(model, r, teffs[r["d"]])) for r in recent]
    pairs = [(a, p) for a, p in pairs if p >= 1.0]
    if len(pairs) < 2:
        return 1.0
    ratio = sum(a for a, _ in pairs) / sum(p for _, p in pairs)
    ratio = min(max(ratio, 0.6), 1.6)
    return round(ratio, 3) if abs(ratio - 1.0) >= CORRECTION_MIN else 1.0


def setpoint_change(journal: list[dict[str, Any]], today: date) -> Optional[float]:
    """The thermostat's mean of the last 3 days minus the 14 days before, when
    at least 0.5 degC."""
    def mean(lo, hi):
        vals = [r["sp"] for r in journal if r.get("sp") is not None and lo <= (today - date.fromisoformat(r["d"])).days <= hi]
        return sum(vals) / len(vals) if len(vals) >= 2 else None
    new, old = mean(0, 3), mean(4, 17)
    if new is None or old is None or abs(new - old) < 0.5:
        return None
    return round(new - old, 1)


# -- forecast -----------------------------------------------------------------------
def typical_setpoint(
    journal: list[dict[str, Any]], today: date, live_mean: Optional[float] = None, current: Optional[float] = None
) -> Optional[float]:
    """The wanted temperature to forecast the coming days with: the mean of
    the last 7 days' day averages - with a schedule (a little higher in the
    evening, lower at night) that's what a whole day looks like; the value of
    this moment would make every day look like this hour. Without days yet:
    today's average so far, else the current value."""
    vals = [r["sp"] for r in journal
            if r.get("sp") is not None and 1 <= (today - date.fromisoformat(r["d"])).days <= 7]
    if vals:
        return round(sum(vals) / len(vals), 2)
    return live_mean if live_mean is not None else current


def hourly_shape(journal: list[dict[str, Any]], today: date) -> list[float]:
    """The share of each hour of the day in the day's energy, averaged over
    the last SHAPE_DAYS days (uniform without data)."""
    acc = [0.0] * 24
    n = 0
    for r in journal:
        hours = r.get("hours")
        if not hours or len(hours) != 24 or not r.get("e") or (today - date.fromisoformat(r["d"])).days > SHAPE_DAYS:
            continue
        total = sum(v for v in hours if v is not None)
        if total <= 0:
            continue
        for i, v in enumerate(hours):
            acc[i] += (v or 0.0) / total
        n += 1
    if not n:
        return [1 / 24] * 24
    total = sum(acc)
    return [a / total for a in acc]


def weather_days(
    hourly: list[dict[str, Any]],
    daily: list[dict[str, Any]],
    tz: tzinfo,
    wind_factor: float = 1.0,
) -> dict[str, dict[str, Optional[float]]]:
    """Per local day {t, w, wd} from a weather entity's forecasts (HA's
    weather.get_forecasts): the hourly mean where the day has 18+ hourly
    entries, else the daily (temperature + templow) / 2. Wind in m/s
    (`wind_factor` converts the entity's unit)."""
    out: dict[str, dict[str, Optional[float]]] = {}
    by_day: dict[str, list[dict[str, Any]]] = {}
    for f in hourly or []:
        dt = _parse(f.get("datetime"), tz)
        if dt is not None and f.get("temperature") is not None:
            by_day.setdefault(dt.date().isoformat(), []).append(f)
    for f in daily or []:
        dt = _parse(f.get("datetime"), tz)
        if dt is None or f.get("temperature") is None:
            continue
        hi = float(f["temperature"])
        lo = f.get("templow")
        out[dt.date().isoformat()] = {
            "t": round((hi + float(lo)) / 2, 2) if lo is not None else round(hi - 4.0, 2),
            "w": round(float(f["wind_speed"]) * wind_factor, 2) if f.get("wind_speed") is not None else None,
            "wd": float(f["wind_bearing"]) if isinstance(f.get("wind_bearing"), (int, float)) else None,
        }
    for d, items in by_day.items():
        winds = [float(f["wind_speed"]) * wind_factor for f in items if f.get("wind_speed") is not None]
        dirs = [float(f["wind_bearing"]) for f in items if isinstance(f.get("wind_bearing"), (int, float))]
        entry = {
            "t": round(sum(float(f["temperature"]) for f in items) / len(items), 2),
            "w": round(sum(winds) / len(winds), 2) if winds else None,
            "wd": mean_direction(dirs, winds if len(winds) == len(dirs) else None),
            "hours": len(items),
        }
        if len(items) >= 18 or d not in out:
            out[d] = entry
        else:
            out[d]["hours"] = len(items)
            out[d]["hourly"] = entry
    return out


def mean_direction(dirs: list[float], weights: Optional[list[float]] = None) -> Optional[float]:
    """Wind direction mean as a vector (weighted by speed when given)."""
    if not dirs:
        return None
    weights = weights or [1.0] * len(dirs)
    x = sum(w * math.cos(math.radians(d)) for d, w in zip(dirs, weights))
    y = sum(w * math.sin(math.radians(d)) for d, w in zip(dirs, weights))
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return round(math.degrees(math.atan2(y, x)) % 360, 1)


def _parse(value: Any, tz: tzinfo) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def forecast_days(
    model: dict[str, Any],
    journal: list[dict[str, Any]],
    weather: dict[str, dict[str, Optional[float]]],
    days: list[date],
    today_measured: Optional[tuple[float, float]] = None,
    sun: Optional[dict[str, float]] = None,
    setpoint: Optional[float] = None,
    factor: float = 1.0,
) -> list[dict[str, Any]]:
    """Each day's expected energy: [{d, t, teff, w, wd, s, kwh}] - kwh None
    when the weather forecast has no entry for that day. Today's temperature
    mixes what was measured so far (`today_measured` = (mean, share of the
    day)) with the forecast."""
    out = []
    by_day = {r["d"]: r for r in journal if r.get("t") is not None}
    prev_t = None
    if days:
        yesterday = by_day.get((days[0] - timedelta(days=1)).isoformat())
        prev_t = yesterday["t"] if yesterday else None
    for i, d in enumerate(days):
        key = d.isoformat()
        w = weather.get(key)
        if w is None or w.get("t") is None:
            out.append({"d": key, "t": None, "teff": None, "w": None, "wd": None, "s": None, "kwh": None})
            prev_t = None
            continue
        t = w["t"]
        if i == 0 and today_measured is not None:
            mean, share = today_measured
            share = min(max(share, 0.0), 1.0)
            t = round(mean * share + t * (1 - share), 2)
        teff = round(SMOOTH * t + (1 - SMOOTH) * prev_t, 2) if prev_t is not None else t
        row = {"d": key, "w": w.get("w"), "wd": w.get("wd"), "s": (sun or {}).get(key), "sp": setpoint}
        kwh = predict_row(model, row, teff) * factor
        out.append({"d": key, "t": t, "teff": teff, "w": w.get("w"), "wd": w.get("wd"), "s": row["s"], "kwh": round(kwh, 2)})
        prev_t = t
    return out


def spread(
    day_kwh: dict[str, float],
    shape: list[float],
    hour0_epoch: int,
    hours: int,
    tz: tzinfo,
) -> list[float]:
    """Day totals over the forecast hours by the hourly shape (hour 0 a
    full-hour value, like the rest of the forecast); a day without a total
    gets 0 here (the caller falls back)."""
    out = []
    for h in range(hours):
        dt = datetime.fromtimestamp(hour0_epoch + h * HOUR, tz)
        total = day_kwh.get(dt.date().isoformat())
        out.append(round(total * shape[dt.hour], 4) if total is not None else 0.0)
    return out


def same_weekday_mean(journal: list[dict[str, Any]], d: date, weeks: int) -> Optional[float]:
    """The journal's mean energy on d's weekday over the last `weeks` weeks -
    what the 6-week average expects for that day."""
    vals = []
    for k in range(1, weeks + 1):
        r = next((r for r in journal if r["d"] == (d - timedelta(weeks=k)).isoformat()), None)
        if r and r.get("e") is not None:
            vals.append(r["e"])
    return round(sum(vals) / len(vals), 2) if vals else None


def same_weekday_model_mean(model: dict[str, Any], journal: list[dict[str, Any]], d: date, weeks: int) -> Optional[float]:
    """What the model says for d's weekday over the last `weeks` weeks, on the
    weather those days really had (for the 'no own metering' difference)."""
    teffs = effective_temps(journal)
    vals = []
    for k in range(1, weeks + 1):
        key = (d - timedelta(weeks=k)).isoformat()
        r = next((r for r in journal if r["d"] == key and r.get("t") is not None), None)
        if r:
            vals.append(predict_row(model, r, teffs[key]))
    return sum(vals) / len(vals) if vals else None


def classes(model: dict[str, Any], journal: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Per temperature class (CLASS_WIDTH): days, measured mean, model mean,
    the newest day - the card's memory table."""
    rows = [r for r in journal if r.get("e") is not None and r.get("t") is not None and r["d"] < today.isoformat()]
    teffs = effective_temps(rows)
    groups: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(temp_class(teffs[r["d"]]), []).append(r)
    out = []
    for cls in sorted(groups):
        g = groups[cls]
        out.append({
            "from": cls * CLASS_WIDTH,
            "to": (cls + 1) * CLASS_WIDTH,
            "days": len(g),
            "measured": round(sum(r["e"] for r in g) / len(g), 2),
            "model": round(sum(predict_row(model, r, teffs[r["d"]]) for r in g) / len(g), 2),
            "last": max(r["d"] for r in g),
        })
    return out


def points(journal: list[dict[str, Any]], today: date, limit: int = 240) -> list[list[float]]:
    """[teff, kWh, age in days] of the newest days - the signature chart."""
    rows = [r for r in journal if r.get("e") is not None and r.get("t") is not None and r["d"] < today.isoformat()]
    teffs = effective_temps(rows)
    rows = rows[-limit:]
    return [[teffs[r["d"]], round(r["e"], 2), (today - date.fromisoformat(r["d"])).days] for r in rows]


def model_line(model: dict[str, Any], journal: list[dict[str, Any]], today: date) -> list[list[float]]:
    """The model across the measured temperatures, at the median wind and sun
    of the journal's days ([teff, kWh] per degree) - the signature chart's
    line."""
    pts = points(journal, today)
    if not pts:
        return []
    def median(key):
        vals = sorted(r[key] for r in journal if r.get(key) is not None)
        return vals[len(vals) // 2] if vals else None
    row = {"w": median("w"), "s": median("s")}
    lo = int(math.floor(min(p[0] for p in pts))) - 1
    hi = int(math.ceil(max(p[0] for p in pts))) + 1
    return [[float(t), round(predict_row(model, row, float(t)), 2)] for t in range(lo, hi + 1)]


def state_of(model: Optional[dict[str, Any]], days_out: list[dict[str, Any]], heating_days: int) -> str:
    """active / learning / summer / fallback - see the module docstring."""
    if model is None:
        return STATE_LEARNING
    have = [d for d in days_out if d["kwh"] is not None]
    if not have:
        return STATE_FALLBACK
    warm = all(d["teff"] is not None and d["teff"] > model["tb"] and (model["tc"] is None or d["teff"] < model["tc"]) for d in have)
    if heating_days < MIN_HEATING_DAYS:
        return STATE_SUMMER if warm and model["rows"] >= MIN_ROWS else STATE_LEARNING
    if model.get("r2") is not None and model["r2"] < POOR_R2:
        return STATE_FALLBACK
    return STATE_SUMMER if warm else STATE_ACTIVE


# -- the house's heat (as of 2026.10.16) ------------------------------------------------
# How fast the house cools while the heat pump doesn't heat, learned from the
# indoor temperature's hourly statistics: per hour the indoor temperature
# drops by k x (indoor - outdoor) (more with wind, less with sun). With the
# energy signature's kWh per degree-day (b, electricity) that gives the heat
# the house holds per degree, as electricity the heat pump doesn't have to
# use: C = (b / 24) / k kWh per degC. A house warmer than wanted coasts until
# it's back at the wanted temperature; a colder one needs that heat extra.
OFF_KWH = 0.05          # an hour with less heating energy than this: not heating
OFF_HOURS_BEFORE = 3    # ... and the hours before it too (the floor still gives heat)
OFF_HOURS_LONG = 6      # ... or this many, when the floor measurably gives heat longer
AFTERGLOW_MIN = 0.01    # degC per hour the house warms more than the cooling says
PROFILE_DAYS = 14       # the usual indoor temperature per hour over these days
MIN_DIFF = 2.0          # degC indoor - outdoor, else the cooling drowns in noise
MIN_THERMAL_ROWS = 48
SURPLUS_MIN = 0.3       # degC above/below wanted that counts
DEFICIT_HOURS = 6       # a colder house is heated up over this many hours
THERMAL_DAYS = 60
MAX_COAST_HOURS = 72    # the simulation stops here (sun can keep a house warm)


def _thermal_rows(indoor, outdoor, heat, before: int) -> list[tuple[int, float, float]]:
    rows = []
    for h, tin in indoor.items():
        nxt = indoor.get(h + HOUR)
        tout = outdoor.get(h)
        if nxt is None or tout is None:
            continue
        d = tin - tout
        if d < MIN_DIFF:
            continue
        hours = [heat.get(h + HOUR * i) for i in range(-before, 2)]
        if any(v is None or v >= OFF_KWH for v in hours):
            continue
        rows.append((h, nxt - tin, d))
    return rows


def _thermal_x(h: int, d: float, wind, sun, use_wind: bool, use_sun: bool) -> list[float]:
    x = [1.0, -d]
    if use_wind:
        x.append(-(wind.get(h) or 0.0) * d)
    if use_sun:
        x.append(sun.get(h) or 0.0)
    return x


def _thermal_lsq(rows, wind, sun, use_wind, use_sun) -> Optional[list[float]]:
    xs = [_thermal_x(h, d, wind, sun, use_wind, use_sun) for h, _, d in rows]
    ys = [dy for _, dy, _ in rows]
    k = len(xs[0])
    ata = [[sum(x[i] * x[j] for x in xs) for j in range(k)] for i in range(k)]
    atb = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(k)]
    return _solve(ata, atb)


def fit_thermal(
    indoor: dict[int, float],
    outdoor: dict[int, float],
    heat: dict[int, float],
    wind: Optional[dict[int, float]] = None,
    sun: Optional[dict[int, float]] = None,
) -> Optional[dict[str, Any]]:
    """The house's cooling rate from hours the heat pump didn't heat:
    dT(indoor, next hour) = a - k x d - kw x wind x d + ks x sun, d = indoor -
    outdoor. A floor keeps giving heat after the heat pump stops: the hours
    before count as heating too - OFF_HOURS_BEFORE, or OFF_HOURS_LONG when the
    house measurably still warms up in the hours between (it then looks like
    it cools slower than it does). None with fewer than MIN_THERMAL_ROWS such
    hours or an unlikely k (outside 0.001 .. 0.2 per hour)."""
    rows = _thermal_rows(indoor, outdoor, heat, OFF_HOURS_BEFORE)
    if len(rows) < MIN_THERMAL_ROWS:
        return None
    use_wind = bool(wind) and sum(1 for h, _, _ in rows if wind.get(h) is not None) >= 0.7 * len(rows)
    use_sun = bool(sun) and sum(1 for h, _, _ in rows if sun.get(h) is not None) >= 0.7 * len(rows)
    off_hours = OFF_HOURS_BEFORE
    long_rows = _thermal_rows(indoor, outdoor, heat, OFF_HOURS_LONG)
    if len(long_rows) >= MIN_THERMAL_ROWS:
        coef_long = _thermal_lsq(long_rows, wind, sun, use_wind, use_sun)
        long_set = {h for h, _, _ in long_rows}
        between = [(h, dy, d) for h, dy, d in rows if h not in long_set]
        if coef_long is not None and len(between) >= 12:
            res = [dy - sum(c * v for c, v in zip(coef_long, _thermal_x(h, d, wind, sun, use_wind, use_sun)))
                   for h, dy, d in between]
            mean = sum(res) / len(res)
            sd = math.sqrt(sum((r - mean) ** 2 for r in res) / max(len(res) - 1, 1))
            if mean > AFTERGLOW_MIN and mean > 2 * sd / math.sqrt(len(res)):
                rows, off_hours = long_rows, OFF_HOURS_LONG
    coef = _thermal_lsq(rows, wind, sun, use_wind, use_sun)
    if coef is None or not 0.001 <= coef[1] <= 0.2:
        return None
    i = 2
    kw = ks = None
    if use_wind:
        kw = coef[i]
        i += 1
    if use_sun:
        ks = coef[i]
    ys = [dy for _, dy, _ in rows]
    ymean = sum(ys) / len(ys)
    sst = sum((y - ymean) ** 2 for y in ys)
    sse = sum((dy - sum(c * v for c, v in zip(coef, _thermal_x(h, d, wind, sun, use_wind, use_sun)))) ** 2
              for h, dy, d in rows)
    return {
        "a": round(coef[0], 5),
        "k": round(coef[1], 5),
        "kw": round(kw, 6) if kw is not None else None,
        "ks": round(ks, 5) if ks is not None else None,
        "n": len(rows),
        "r2": round(1 - sse / sst, 3) if sst > 0 else None,
        "off_hours": off_hours,
    }


def indoor_hours(indoor: dict[int, float], tz: tzinfo) -> dict[str, list[Optional[float]]]:
    """Hourly indoor temperatures per local day: {date: [24 values or None]}."""
    out: dict[str, list[Optional[float]]] = {}
    for h, v in indoor.items():
        if v is None:
            continue
        dt = datetime.fromtimestamp(h, tz)
        out.setdefault(dt.date().isoformat(), [None] * 24)[dt.hour] = round(float(v), 2)
    return out


def heating_dates(model: Optional[dict[str, Any]], journal: list[dict[str, Any]]) -> set[str]:
    """Days the model counts as heating days (smoothed outdoor temperature at
    least a degree below the balance temperature)."""
    if not model:
        return set()
    teffs = effective_temps(journal)
    return {d for d, t in teffs.items() if t <= model["tb"] - 1.0}


def indoor_profile(
    days: dict[str, list[Optional[float]]], heating: set[str], n: int = PROFILE_DAYS
) -> Optional[list[float]]:
    """The usual indoor temperature per hour of the day over the newest `n`
    heating days - a heating schedule (warmer in the evening, cooler at night)
    is in it. Heating days only: after a summer the house was warm for weeks,
    that isn't 'usual' for the heating season. None with fewer than 5 such
    days."""
    picked = [d for d in sorted(days, reverse=True)
              if d in heating and sum(1 for v in days[d] if v is not None) >= 20][:n]
    if len(picked) < 5:
        return None
    out = []
    for hour in range(24):
        vals = [days[d][hour] for d in picked if days[d][hour] is not None]
        if not vals:
            return None
        out.append(round(sum(vals) / len(vals), 2))
    return out


def stored_kwh_per_degree(thermal: dict[str, Any], model: dict[str, Any]) -> Optional[float]:
    """Electricity the house's heat stands for, per degC indoor: (b/24) / k."""
    b = model["coef"][1]
    if not thermal or b <= 0:
        return None
    return round((b / 24.0) / thermal["k"], 2)


def house_effect(
    thermal: dict[str, Any],
    model: dict[str, Any],
    indoor: float,
    wanted: Optional[float],
    hourly: list[tuple[Optional[float], Optional[float], Optional[float]]],
    usual: Optional[list[float]] = None,
) -> Optional[dict[str, Any]]:
    """What the house's own heat does to the coming hours. `hourly` = (outdoor,
    wind, sun) per forecast hour from now; `usual` = the usual indoor
    temperature for those same hours (indoor_profile). The reference is the
    usual temperature when known - the forecast's hourly pattern already
    holds the usual way of heating (an evening boost, a night without), so
    only what differs from it counts - else the wanted temperature. Warmer
    than the reference: the hours until the house is back at it (simulated
    with the learned cooling rate), in which the heat pump doesn't heat.
    Colder: the heat it misses, extra in the first DEFICIT_HOURS hours. None
    within SURPLUS_MIN."""
    use_usual = bool(usual)
    ref0 = usual[0] if use_usual else wanted
    per_degree = stored_kwh_per_degree(thermal, model)
    if per_degree is None or ref0 is None:
        return None
    diff = indoor - ref0
    if abs(diff) < SURPLUS_MIN:
        return None
    base = {"surplus_c": round(diff, 1), "reference": "usual" if use_usual else "wanted",
            "reference_c": round(ref0, 1), "per_degree_kwh": per_degree}
    if diff < 0:
        return {"kind": "deficit", "hours": DEFICIT_HOURS, "kwh": round(-diff * per_degree, 2), **base}
    t = indoor
    hours = 0
    for i, (tout, wind, sun) in enumerate(hourly[:MAX_COAST_HOURS]):
        ref = usual[i] if use_usual and i < len(usual) else ref0
        if t <= ref or tout is None:
            break
        d = t - tout
        # the fit's own terms: cooling by the difference (more with wind),
        # warming by the sun and by what the house gives off itself (a)
        drop = (thermal["k"] * d + (thermal.get("kw") or 0.0) * (wind or 0.0) * d
                - (thermal.get("ks") or 0.0) * (sun or 0.0) - thermal.get("a", 0.0))
        t -= drop
        hours += 1
    return {"kind": "surplus", "hours": hours, "kwh": round(diff * per_degree, 2), **base}


def apply_house(total: list[float], effect: Optional[dict[str, Any]], base_hour: float) -> tuple[list[float], float]:
    """The forecast with the house's own heat in it: coasting hours keep only
    the base (hot water / standby), at most the heat the house holds; a
    deficit spreads its kWh over its hours. Returns (forecast, kWh it changed -
    negative is less)."""
    if not effect:
        return total, 0.0
    out = list(total)
    changed = 0.0
    if effect["kind"] == "surplus":
        budget = effect["kwh"]
        for h in range(min(effect["hours"], len(out))):
            cut = min(max(out[h] - base_hour, 0.0), budget)
            out[h] = round(out[h] - cut, 4)
            budget -= cut
            changed -= cut
            if budget <= 0:
                break
    else:
        n = min(effect["hours"], len(out))
        if n:
            add = effect["kwh"] / n
            for h in range(n):
                out[h] = round(out[h] + add, 4)
            changed = effect["kwh"]
    return out, round(changed, 2)


def hourly_weather(
    hourly: list[dict[str, Any]],
    weather: dict[str, dict[str, Optional[float]]],
    hour0: int,
    hours: int,
    tz: tzinfo,
    wind_factor: float = 1.0,
    sun: Optional[list[Optional[float]]] = None,
) -> list[tuple[Optional[float], Optional[float], Optional[float]]]:
    """(outdoor degC, wind m/s, sun kWh) per forecast hour from hour0: the
    weather entity's hourly forecast where it has the hour, else the day's
    mean; `sun` = the solar forecast per hour from hour0."""
    by_hour: dict[int, dict[str, Any]] = {}
    for f in hourly or []:
        dt = _parse(f.get("datetime"), tz)
        if dt is not None and f.get("temperature") is not None:
            by_hour[int(dt.timestamp()) // HOUR * HOUR] = f
    out = []
    for i in range(hours):
        epoch = hour0 + i * HOUR
        f = by_hour.get(epoch)
        day = weather.get(datetime.fromtimestamp(epoch, tz).date().isoformat()) or {}
        if f is not None:
            t = float(f["temperature"])
            w = float(f["wind_speed"]) * wind_factor if f.get("wind_speed") is not None else day.get("w")
        else:
            t, w = day.get("t"), day.get("w")
        s = sun[i] if sun is not None and i < len(sun) else None
        out.append((t, w, s))
    return out
