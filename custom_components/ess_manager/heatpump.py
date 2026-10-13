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
