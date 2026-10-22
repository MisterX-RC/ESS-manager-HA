"""The heat pump model's live state (as of 2026.10.16): the journal, today's
live samples (wind, wind direction, setpoint, indoor and outdoor
temperature, the day's solar forecast), the fitted model, and each cycle's
forecast and Status attribute. Pure Python (no Home Assistant imports) so
tests/test_pipeline.py can run it; the coordinator fetches the statistics,
the weather forecast and the states and passes them in. See heatpump.py.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Optional

from . import heatpump as hp
from . import heatpump_house as hh

# days the card shows; the forecast itself covers every hour it can
CARD_DAYS = 5
# a failed statistics read is tried again after this long (s)
RETRY = 3600
# a fit that gave no model is tried again after this long (s), unless the
# journal or the day changes first (as of 2026.10.20)
REFIT_RETRY = 3600


class HeatPumpRuntime:
    """Stored: `journal` (rows, see heatpump.build_rows), `live` (today's
    samples), `key` (the settings the journal was built from), `subtract`
    (whether the usage history leaves the heat pump out), `stats_day` (the
    day the statistics were last merged). Not stored: the model (fitted
    again after a restart)."""

    def __init__(self) -> None:
        self.journal: list[dict[str, Any]] = []
        self.live: dict[str, Any] = {}
        self.key: Optional[str] = None
        self.subtract = False
        self.stats_day: Optional[str] = None
        self.stats_tried_at = 0.0
        self.model: Optional[dict[str, Any]] = None
        self.fitted_day: Optional[str] = None
        self.dirty = True
        # the house's cooling rate (heatpump.fit_thermal), fitted once a day
        self.thermal: Optional[dict[str, Any]] = None
        self.thermal_day: Optional[str] = None
        # hourly indoor temperatures of the last THERMAL_DAYS days {date: [24]},
        # for the usual indoor temperature per hour (heatpump.indoor_profile)
        self.indoor_days: dict[str, list[Optional[float]]] = {}
        # the indoor sensor the journal's rows were read with (ti / tid);
        # another one (or none yet, as before 2026.10.17) refills them once
        self.rows_src: Optional[str] = None
        # hourly indoor temperatures recorded here {epoch: degC} - for a
        # thermostat's current temperature, which has no statistics; and the
        # thermostat's heat demand hours per day (both as of 2026.10.17)
        self.indoor_hist: dict[str, float] = {}
        self.demand: dict[str, float] = {}
        self.setpoints: dict[str, float] = {}
        self._hour: Optional[list[float]] = None
        # the house hour by hour (heatpump_house, as of 2026.10.17): the daily
        # round's result {model, cop, review, day}; the heating electricity per
        # hour recorded live {epoch: kWh}
        self.house: Optional[dict[str, Any]] = None
        self.heat_hist: dict[str, float] = {}
        # steering (as of 2026.10.17): {last_set, override_until}
        self.steer: dict[str, Any] = {}
        self._heat_acc: Optional[list[float]] = None
        self._plan_cache: Optional[tuple] = None
        self._fit_tried_at = 0.0

    # -- store ---------------------------------------------------------------
    def restore(self, data: Optional[dict[str, Any]]) -> None:
        data = data or {}
        self.journal = list(data.get("journal") or [])
        self.live = dict(data.get("live") or {})
        self.key = data.get("key")
        self.subtract = bool(data.get("subtract", False))
        self.stats_day = data.get("stats_day")
        self.thermal = data.get("thermal")
        self.thermal_day = data.get("thermal_day")
        self.indoor_days = dict(data.get("indoor_days") or {})
        self.rows_src = data.get("rows_src")
        self.indoor_hist = dict(data.get("indoor_hist") or {})
        self.demand = dict(data.get("demand") or {})
        self.setpoints = dict(data.get("setpoints") or {})
        self.house = data.get("house")
        self.heat_hist = dict(data.get("heat_hist") or {})
        self.steer = dict(data.get("steer") or {})
        self.dirty = True

    def as_store(self) -> dict[str, Any]:
        return {
            "journal": self.journal,
            "live": self.live,
            "key": self.key,
            "subtract": self.subtract,
            "stats_day": self.stats_day,
            "thermal": self.thermal,
            "thermal_day": self.thermal_day,
            "indoor_days": self.indoor_days,
            "rows_src": self.rows_src,
            "indoor_hist": self.indoor_hist,
            "demand": self.demand,
            "setpoints": self.setpoints,
            "house": self.house,
            "heat_hist": self.heat_hist,
            "steer": self.steer,
        }

    def reset(self, key: str) -> None:
        """New settings: start the journal again (the backfill refills it)."""
        self.journal = []
        self.live = {}
        self.key = key
        self.stats_day = None
        self.stats_tried_at = 0.0
        self.model = None
        self.fitted_day = None
        self.thermal = None
        self.thermal_day = None
        self.indoor_days = {}
        self.rows_src = None
        self.indoor_hist = {}
        self.demand = {}
        self.setpoints = {}
        self.house = None
        self.heat_hist = {}
        self.dirty = True

    # -- data in ---------------------------------------------------------------
    def merge(self, rows: list[dict[str, Any]], today: date) -> None:
        self.journal = hp.merge_rows(self.journal, rows, today)
        for r in self.journal:
            if r.get("dem") is None and r["d"] in self.demand:
                r["dem"] = self.demand[r["d"]]
            if r.get("sp") is None and r["d"] in self.setpoints:
                r["sp"] = self.setpoints[r["d"]]
        self.dirty = True

    def set_setpoints(self, days: dict[str, float], today: Optional[date] = None) -> None:
        """The wanted temperature per day from the thermostat's history (as
        of 2026.10.17) - kept for rows that come later, like the demand."""
        self.setpoints.update(days)
        if today is not None:
            cutoff = (today - timedelta(days=hp.JOURNAL_DAYS)).isoformat()
            self.setpoints = {d: v for d, v in self.setpoints.items() if d >= cutoff}
        for r in self.journal:
            if r["d"] in days:
                r["sp"] = days[r["d"]]
        self.dirty = True

    def set_demand(self, hours: dict[str, float], today: Optional[date] = None) -> None:
        """Heat demand hours per day from the climate entity's history (kept,
        so rows that come later get them too)."""
        self.demand.update(hours)
        if today is not None:
            cutoff = (today - timedelta(days=hp.JOURNAL_DAYS)).isoformat()
            self.demand = {d: v for d, v in self.demand.items() if d >= cutoff}
        for r in self.journal:
            if r["d"] in hours:
                r["dem"] = hours[r["d"]]
        self.dirty = True

    def add_indoor_hours(self, hours: dict[int, float], now_epoch: float) -> None:
        """Hourly indoor temperatures (a thermostat's history) - what was
        recorded live stays; older than THERMAL_DAYS + 2 days goes."""
        for h, v in hours.items():
            self.indoor_hist.setdefault(str(int(h)), v)
        cutoff = now_epoch - (hp.THERMAL_DAYS + 2) * 86400
        self.indoor_hist = {k: v for k, v in self.indoor_hist.items() if int(k) >= cutoff}

    def indoor_series(self) -> dict[int, float]:
        return {int(k): v for k, v in self.indoor_hist.items()}

    def forget_indoor(self) -> None:
        """Before the rows are read again with another indoor sensor."""
        for r in self.journal:
            r.pop("tid", None)
        self.dirty = True

    def sample(
        self,
        now: datetime,
        tz: tzinfo,
        t_out: Optional[float] = None,
        wind: Optional[float] = None,
        wind_dir: Optional[float] = None,
        setpoint: Optional[float] = None,
        indoor: Optional[float] = None,
        sun_today: Optional[float] = None,
        demand: Optional[bool] = None,
        heat_kwh: Optional[float] = None,
    ) -> None:
        """One cycle's live readings, averaged per day. When the day changes,
        the finished day's averages go into its journal row (only what the
        statistics didn't give it)."""
        today = now.astimezone(tz).date().isoformat()
        if self.live.get("d") != today:
            self._finish_live()
            self.live = {"d": today}
        lv = self.live

        def add(name: str, value: Optional[float]) -> None:
            if value is None:
                return
            lv[name + "_sum"] = lv.get(name + "_sum", 0.0) + float(value)
            lv[name + "_n"] = lv.get(name + "_n", 0) + 1

        add("t", t_out)
        add("w", wind)
        add("sp", setpoint)
        add("ti", indoor)
        if indoor is not None:
            # the hour's mean into indoor_hist when the hour is over
            hour = int(now.timestamp()) // hp.HOUR * hp.HOUR
            if self._hour is not None and self._hour[0] != hour and self._hour[2]:
                self.indoor_hist[str(int(self._hour[0]))] = round(self._hour[1] / self._hour[2], 2)
                self._hour = None
            if self._hour is None:
                self._hour = [hour, 0.0, 0]
            self._hour[1] += float(indoor)
            self._hour[2] += 1
        if wind_dir is not None:
            import math
            weight = wind if wind is not None and wind > 0 else 1.0
            lv["wd_x"] = lv.get("wd_x", 0.0) + weight * math.cos(math.radians(wind_dir))
            lv["wd_y"] = lv.get("wd_y", 0.0) + weight * math.sin(math.radians(wind_dir))
        if sun_today is not None:
            lv["s"] = round(float(sun_today), 2)
        if demand is not None:
            # the thermostat's heat demand (2026.10.17): share of the samples
            lv["dem_n"] = lv.get("dem_n", 0) + 1
            lv["dem_yes"] = lv.get("dem_yes", 0) + (1 if demand else 0)
        if heat_kwh is not None:
            # the heating meter's reading: its rise per hour into heat_hist
            hour = int(now.timestamp()) // hp.HOUR * hp.HOUR
            acc = self._heat_acc
            if acc is not None and acc[0] != hour:
                if hour - acc[0] == hp.HOUR:
                    self.heat_hist[str(int(acc[0]))] = round(max(float(heat_kwh) - acc[1], 0.0), 3)
                acc = None
            if acc is None:
                self._heat_acc = [hour, float(heat_kwh)]
            cutoff = now.timestamp() - 3 * 86400
            if len(self.heat_hist) > 80:
                self.heat_hist = {k: v for k, v in self.heat_hist.items() if int(k) >= cutoff}
        lv["first"] = lv.get("first") or now.timestamp()
        lv["last"] = now.timestamp()

    def _mean(self, name: str) -> Optional[float]:
        n = self.live.get(name + "_n")
        return round(self.live[name + "_sum"] / n, 2) if n else None

    def today_measured(self, now: datetime, tz: tzinfo) -> Optional[tuple[float, float]]:
        """(mean outdoor temperature so far, share of the day it covers)."""
        mean = self._mean("t")
        if mean is None or self.live.get("first") is None:
            return None
        local = now.astimezone(tz)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        share = (now.timestamp() - max(self.live["first"], midnight.timestamp())) / 86400.0
        return mean, max(min(share, 1.0), 0.0)

    def _finish_live(self) -> None:
        lv = self.live
        if not lv.get("d"):
            return
        import math
        extra: dict[str, Any] = {"d": lv["d"]}
        for name, key in (("w", "w"), ("sp", "sp"), ("ti", "ti")):
            mean = self._mean(name)
            if mean is not None:
                extra[key] = mean
        if lv.get("wd_x") is not None:
            if abs(lv["wd_x"]) > 1e-9 or abs(lv.get("wd_y", 0.0)) > 1e-9:
                extra["wd"] = round(math.degrees(math.atan2(lv.get("wd_y", 0.0), lv["wd_x"])) % 360, 1)
        if lv.get("s") is not None:
            extra["s"] = lv["s"]
        if lv.get("dem_n"):
            extra["dem"] = round(24.0 * lv["dem_yes"] / lv["dem_n"], 1)
        row = next((r for r in self.journal if r["d"] == lv["d"]), None)
        if row is None:
            # no statistics row (yet): keep the live values for when it comes
            row = {"d": lv["d"]}
            self.journal.append(row)
            self.journal.sort(key=lambda r: r["d"])
        for k, v in extra.items():
            if row.get(k) is None:
                row[k] = v
        self.dirty = True

    # -- the house hour by hour (as of 2026.10.17) ---------------------------------
    def q_hist(self, hour0_epoch: int, t_out: Optional[float]) -> list[float]:
        """The heat of the 11 hours before hour0 (oldest first) - as the
        house model counts it (heat with a COP model, else electricity)."""
        house = self.house or {}
        model, copm = house.get("model"), house.get("cop")
        cop = hh.cop_at(copm, t_out) if model and model.get("thermal") else 1.0
        return [self.heat_hist.get(str(hour0_epoch - j * hp.HOUR), 0.0) * cop for j in range(hh.LAG_HOURS - 1, 0, -1)]

    def plan_heat(self, hour0_epoch: int, indoor: Optional[float], hourly: list, target: list[float],
                  cop_fallback: float) -> Optional[dict[str, Any]]:
        """Floor control (as of 2026.10.23): the heat per hour (thermal kWh)
        that keeps the house on `target` - the house model's emulated heat
        pump, the floor's delay and the heat of the hours before included.
        None without a house model, indoor temperature or weather."""
        house = self.house or {}
        hm, copm = house.get("model"), house.get("cop")
        if not hm or indoor is None or not hourly or not target:
            return None
        n = min(len(hourly), len(target), 24)
        inputs = hourly[:n]
        if not inputs or inputs[0][0] is None:
            return None
        temps, q_el = hh.simulate(hm, indoor, inputs, target[:n], self.q_hist(hour0_epoch, inputs[0][0]), copm)
        q_th = [round(q * (hh.cop_at(copm, inp[0]) if copm else cop_fallback), 3) for q, inp in zip(q_el, inputs)]
        return {"temps": temps, "q_el": q_el, "q_th": q_th}

    @staticmethod
    def _window(win, hour0_epoch, tz):
        if not win:
            return None
        return {**win, "from": datetime.fromtimestamp(hour0_epoch + win["start"] * hp.HOUR, tz).isoformat(),
                "until": datetime.fromtimestamp(hour0_epoch + (win["start"] + win["hours"]) * hp.HOUR, tz).isoformat()}

    def _house_forecast(self, now, tz, hour0_epoch, hours, total, indoor, hourly, profile, level, model,
                        prices, steering, meter, usable, schedule=None, delta=0.0) -> dict[str, Any]:
        house = self.house or {}
        hm, copm, rev = house.get("model"), house.get("cop"), house.get("review")
        stage = hh.stage_of(hm, rev, steering)
        out: dict[str, Any] = {
            "stage": stage,
            "review": rev,
            "fitted_day": house.get("day"),
            "model": hm,
            "cop": ({"c0": copm["c0"], "c1": copm["c1"], "at_7": round(hh.cop_at(copm, 7.0), 2),
                     "at_minus_2": round(hh.cop_at(copm, -2.0), 2), "hours": copm["n"]} if copm else None),
            "steer": self.steer,
        }
        # measured: the last 24 hours
        out["measured"] = [[int(k), v] for k, v in sorted(self.indoor_hist.items(), key=lambda kv: int(kv[0]))
                           if int(k) >= hour0_epoch - 24 * hp.HOUR]
        # the heating electricity measured per complete hour, the last 24 hours
        # (as of 2026.10.23) - next to the expected kWh on the indoor chart
        out["measured_kwh"] = [[int(k), v] for k, v in sorted(self.heat_hist.items(), key=lambda kv: int(kv[0]))
                               if hour0_epoch - 24 * hp.HOUR <= int(k) < hour0_epoch]
        if not hm or indoor is None or not hourly:
            return out
        n = min(hh.FORECAST_HOURS, len(hourly), hours)
        inputs = hourly[:n]
        t_out = inputs[0][0] if inputs else None
        if schedule:
            # steering: the day/night temperatures, the buffer plan on top
            # once the model passed its self-check (worked out once an hour)
            target = list(schedule[:n])
            plan = None
            if stage == hh.STAGE_STEERING and prices and prices.get("buy"):
                key = (hour0_epoch, house.get("day"), tuple(schedule[:n]), delta, round(indoor, 1))
                if self._plan_cache and self._plan_cache[0][:3] == key[:3] and self._plan_cache[0][3] == delta:
                    plan = self._plan_cache[1]
                else:
                    plan = hh.plan_buffer(hm, copm, indoor, inputs, target, self.q_hist(hour0_epoch, t_out),
                                          prices["buy"], prices.get("sell") or prices["buy"], prices.get("surplus") or [], delta)
                    self._plan_cache = (key, plan)
            if plan:
                for i, o in enumerate(plan["offsets"]):
                    target[i] = round(target[i] + o, 2)
                out["plan"] = {
                    **{k: plan[k] for k in ("saving", "cost")},
                    "boost": self._window(plan.get("boost"), hour0_epoch, tz),
                    "dip": self._window(plan.get("dip"), hour0_epoch, tz),
                    "offset_now": plan["offsets"][0] if plan["offsets"] else 0.0,
                }
            out["setpoint_now"] = target[0] if target else None
        else:
            target = hh.targets(profile, level, hour0_epoch, n, tz)
        if not target:
            return out
        temps, q = hh.simulate(hm, indoor, inputs, target, self.q_hist(hour0_epoch, t_out), copm)
        out["forecast"] = {"start": hour0_epoch, "temps": temps, "kwh": q, "target": target[:len(q)]}
        if stage in (hh.STAGE_USED, hh.STAGE_STEERING) and usable and meter != hp.METER_NONE and len(q) >= 24:
            base_hour = max(model["coef"][0], 0.0) / 24.0 if model else 0.0
            placed = hh.reshape(total, q, base_hour, hour0_epoch, tz, [])
            out["placed"] = placed
        return out
        return out

    # -- every cycle ---------------------------------------------------------------
    def refit(self, today: date, with_cooling: bool, now_ts: Optional[float] = None) -> None:
        """The energy signature fitted again when the journal changed or the
        day did - and, when the last fit gave no model (too few or too
        scattered days), not again every cycle but at most once an hour
        (as of 2026.10.20: it's a grid search over up to two years)."""
        if self.dirty or self.fitted_day != today.isoformat():
            pass
        elif self.model is None:
            if now_ts is None or now_ts - self._fit_tried_at < REFIT_RETRY:
                return
        else:
            return
        self.model = hp.fit(self.journal, today, with_cooling)
        self.fitted_day = today.isoformat()
        self.dirty = False
        self._fit_tried_at = now_ts if now_ts is not None else 0.0

    def compute(
        self,
        meter: str,
        now: datetime,
        tz: tzinfo,
        hour0_epoch: int,
        hours: int,
        weather: dict[str, dict[str, Optional[float]]],
        sun_by_day: dict[str, float],
        lookback_weeks: int,
        setpoint: Optional[float] = None,
        with_cooling: bool = False,
        indoor: Optional[float] = None,
        hourly_weather: Optional[list[tuple[Optional[float], Optional[float], Optional[float]]]] = None,
        prices: Optional[dict[str, list[float]]] = None,
        steering: bool = False,
        schedule: Optional[list[float]] = None,
        buffer_delta: float = 0.0,
        hourly_model: bool = True,
    ) -> tuple[list[float], dict[str, Any], bool]:
        """(the heat pump's energy per forecast hour - for the 'none' metering
        the difference to add to the usual forecast -, the Status sensor's
        `heat_pump` attribute, whether the model is used)."""
        today = now.astimezone(tz).date()
        self.refit(today, with_cooling, now.timestamp())
        model = self.model
        last_day = datetime.fromtimestamp(hour0_epoch + (hours - 1) * hp.HOUR, tz).date()
        days = [today + timedelta(days=i) for i in range((last_day - today).days + 1)]
        heating_days = model["heating_days"] if model else 0
        factor = hp.correction(model, self.journal, today) if model else 1.0
        # the coming days with a whole day's wanted temperature, not this hour's
        day_setpoint = hp.typical_setpoint(self.journal, today, self._mean("sp"), setpoint)
        # with the indoor temperature in the model: the one the coming days keep
        day_indoor = hp.expected_indoor(model, self.journal, today, day_setpoint)
        days_out = (
            hp.forecast_days(model, self.journal, weather, days, self.today_measured(now, tz), sun_by_day, day_setpoint, factor, day_indoor)
            if model else []
        )
        state = hp.state_of(model, days_out[:CARD_DAYS], heating_days)
        usable = state in (hp.STATE_ACTIVE, hp.STATE_SUMMER)
        shape = hp.hourly_shape(self.journal, today)

        old = {d.isoformat(): hp.same_weekday_mean(self.journal, d, lookback_weeks) for d in days}
        total = [0.0] * hours
        if usable:
            if meter == hp.METER_NONE:
                deltas = {}
                for day in days_out:
                    if day["kwh"] is None:
                        continue
                    base = hp.same_weekday_model_mean(model, self.journal, date.fromisoformat(day["d"]), lookback_weeks)
                    if base is not None:
                        deltas[day["d"]] = day["kwh"] - base
                total = hp.spread(deltas, shape, hour0_epoch, hours, tz)
            else:
                day_kwh = {}
                for day in days_out:
                    if day["kwh"] is not None:
                        day_kwh[day["d"]] = day["kwh"]
                    elif old.get(day["d"]) is not None:
                        # past the weather forecast: the usual average
                        day_kwh[day["d"]] = old[day["d"]]
                total = hp.spread(day_kwh, shape, hour0_epoch, hours, tz)

        # the house's own heat: warmer than wanted coasts, colder needs extra
        effect = None
        changed = 0.0
        # (heating season only, and only with the heat pump's own metering -
        # without it there are no hours it didn't heat to learn the cooling from)
        usual = None
        profile = hp.indoor_profile(self.indoor_days, hp.heating_dates(model, self.journal)) if model and self.indoor_days else None
        if profile:
            usual = [profile[datetime.fromtimestamp(hour0_epoch + i * hp.HOUR, tz).hour] for i in range(hours)]
        if state == hp.STATE_ACTIVE and model and self.thermal and indoor is not None and (usual or setpoint is not None):
            effect = hp.house_effect(self.thermal, model, indoor, setpoint, hourly_weather or [], usual)
            base_hour = max(model["coef"][0], 0.0) / 24.0
            before = total
            total, changed = hp.apply_house(total, effect, base_hour)
            if effect and changed:
                # the card's day totals follow (coasting can run past midnight)
                per_day: dict[str, float] = {}
                for i, (a, b) in enumerate(zip(before, total)):
                    if a != b:
                        d = datetime.fromtimestamp(hour0_epoch + i * hp.HOUR, tz).date().isoformat()
                        per_day[d] = per_day.get(d, 0.0) + (b - a)
                for day in days_out:
                    if day.get("kwh") is not None and day["d"] in per_day:
                        day["kwh"] = round(max(day["kwh"] + per_day[day["d"]], 0.0), 2)

        # the house hour by hour: forecast, self-check, placement, advice
        house_attr = None
        if hourly_model:
            house_attr = self._house_forecast(
                now, tz, hour0_epoch, hours, total, indoor, hourly_weather or [], profile,
                day_indoor if day_indoor is not None else (setpoint if setpoint is not None else None),
                model, prices, steering, meter, usable, schedule, buffer_delta,
            )
            if house_attr.get("placed"):
                total = house_attr.pop("placed")
            else:
                house_attr.pop("placed", None)

        card_days = []
        for day in days_out[:CARD_DAYS] if days_out else [{"d": d.isoformat(), "kwh": None} for d in days[:CARD_DAYS]]:
            card_days.append({
                "date": day["d"],
                "temp_c": day.get("t"),
                "wind_ms": day.get("w"),
                "wind_dir": day.get("wd"),
                "sun_kwh": day.get("s"),
                "kwh": day.get("kwh"),
                "average_kwh": old.get(day["d"]),
            })
        attribute: dict[str, Any] = {
            "state": state,
            "meter": meter,
            "used": usable,
            "correction": factor,
            "setpoint_change_c": hp.setpoint_change(self.journal, today),
            "days": card_days,
            "total_kwh": round(sum(d["kwh"] for d in card_days if d["kwh"] is not None), 2) if usable else None,
            "average_total_kwh": round(sum(d["average_kwh"] for d in card_days if d["average_kwh"] is not None), 2),
            "journal_days": len([r for r in self.journal if r.get("e") is not None]),
            "oldest_day": next((r["d"] for r in self.journal if r.get("e") is not None), None),
            "heating_days": heating_days,
            "heating_days_needed": hp.MIN_HEATING_DAYS,
            "heating_classes": model.get("heating_classes") if model else 0,
            "heating_classes_needed": hp.MIN_HEATING_CLASSES,
            "fitted_day": self.fitted_day,
            "day_setpoint_c": day_setpoint,
            "day_indoor_c": day_indoor,
            "forecast_120h": total,
        }
        if self.thermal and model:
            # the heat held leans on the kWh per degree colder: only once the
            # model is used (while learning that figure isn't there yet)
            per_degree = hp.stored_kwh_per_degree(self.thermal, model) if state == hp.STATE_ACTIVE else None
            attribute["thermal"] = {
                "cooling_per_hour": self.thermal["k"],
                "time_constant_h": round(1 / self.thermal["k"], 1),
                "floor_hours": self.thermal.get("off_hours"),
                "kwh_per_degree": per_degree,
                "wind_term": self.thermal.get("kw"),
                "sun_term": self.thermal.get("ks"),
                "hours_used": self.thermal.get("n"),
                "fitted_day": self.thermal_day,
            }
        if indoor is not None or effect:
            until = None
            if effect and effect["kind"] == "surplus" and effect["hours"]:
                until = datetime.fromtimestamp(hour0_epoch + effect["hours"] * hp.HOUR, tz).isoformat()
            ref = usual[0] if usual else setpoint
            attribute["house"] = {
                "indoor_c": round(indoor, 1) if indoor is not None else None,
                "wanted_c": setpoint,
                "usual_c": round(usual[0], 1) if usual else None,
                "usual_profile": profile,
                "reference": "usual" if usual else ("wanted" if setpoint is not None else None),
                "difference_c": effect["surplus_c"] if effect else (round(indoor - ref, 1) if indoor is not None and ref is not None else None),
                "kind": effect["kind"] if effect else None,
                "hours": effect["hours"] if effect else None,
                "until": until,
                "kwh": changed if effect else None,
            }
        if house_attr is not None:
            attribute["house_model"] = house_attr
        if model:
            attribute["model"] = hp.summary(model)
            attribute["points"] = hp.points(self.journal, today, left_out=model.get("left_out"))
            attribute["classes"] = hp.classes(model, self.journal, today)
            attribute["line"] = hp.model_line(model, self.journal, today)
        return total, attribute, usable
