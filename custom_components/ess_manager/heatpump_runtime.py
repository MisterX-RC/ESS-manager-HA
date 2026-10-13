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

# days the card shows; the forecast itself covers every hour it can
CARD_DAYS = 5
# a failed statistics read is tried again after this long (s)
RETRY = 3600


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

    # -- store ---------------------------------------------------------------
    def restore(self, data: Optional[dict[str, Any]]) -> None:
        data = data or {}
        self.journal = list(data.get("journal") or [])
        self.live = dict(data.get("live") or {})
        self.key = data.get("key")
        self.subtract = bool(data.get("subtract", False))
        self.stats_day = data.get("stats_day")
        self.dirty = True

    def as_store(self) -> dict[str, Any]:
        return {
            "journal": self.journal,
            "live": self.live,
            "key": self.key,
            "subtract": self.subtract,
            "stats_day": self.stats_day,
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
        self.dirty = True

    # -- data in ---------------------------------------------------------------
    def merge(self, rows: list[dict[str, Any]], today: date) -> None:
        self.journal = hp.merge_rows(self.journal, rows, today)
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
        if wind_dir is not None:
            import math
            weight = wind if wind is not None and wind > 0 else 1.0
            lv["wd_x"] = lv.get("wd_x", 0.0) + weight * math.cos(math.radians(wind_dir))
            lv["wd_y"] = lv.get("wd_y", 0.0) + weight * math.sin(math.radians(wind_dir))
        if sun_today is not None:
            lv["s"] = round(float(sun_today), 2)
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

    # -- every cycle ---------------------------------------------------------------
    def refit(self, today: date, with_cooling: bool) -> None:
        if self.dirty or self.fitted_day != today.isoformat() or self.model is None:
            self.model = hp.fit(self.journal, today, with_cooling)
            self.fitted_day = today.isoformat()
            self.dirty = False

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
    ) -> tuple[list[float], dict[str, Any], bool]:
        """(the heat pump's energy per forecast hour - for the 'none' metering
        the difference to add to the usual forecast -, the Status sensor's
        `heat_pump` attribute, whether the model is used)."""
        today = now.astimezone(tz).date()
        self.refit(today, with_cooling)
        model = self.model
        last_day = datetime.fromtimestamp(hour0_epoch + (hours - 1) * hp.HOUR, tz).date()
        days = [today + timedelta(days=i) for i in range((last_day - today).days + 1)]
        heating_days = model["heating_days"] if model else 0
        factor = hp.correction(model, self.journal, today) if model else 1.0
        days_out = (
            hp.forecast_days(model, self.journal, weather, days, self.today_measured(now, tz), sun_by_day, setpoint, factor)
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
            "fitted_day": self.fitted_day,
            "forecast_120h": total,
        }
        if model:
            attribute["model"] = hp.summary(model)
            attribute["points"] = hp.points(self.journal, today)
            attribute["classes"] = hp.classes(model, self.journal, today)
            attribute["line"] = hp.model_line(model, self.journal, today)
        return total, attribute, usable
