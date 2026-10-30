"""Forecast check - the state that lives in the coordinator (as of 2026.10.22).

Keeps the solar / house-usage forecast of every day as it was at the day's
first cycle (snapshots, ~40 days, stored), once a day works out the check
from the statistics (accuracy.py) - which usage method to use, the level
factor, the buffer advice, what the card shows - and keeps the automatic
Safety buffer.
"""
from __future__ import annotations

from typing import Any, Optional

from . import accuracy as acc

SNAPSHOT_DAYS = 40
# a snapshot taken later than this many hours after midnight (Home
# Assistant was off at midnight) covers too little of the day to judge it
SNAPSHOT_LATEST_HOUR = 3
RETRY_SECONDS = 3600


class AccuracyRuntime:
    def __init__(self) -> None:
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.method: str = acc.METHOD_AVERAGE
        self.level: Optional[float] = None
        self.result: Optional[dict[str, Any]] = None
        self.refreshed_day: Optional[str] = None
        self.tried_at: float = 0.0
        self.auto_effective: Optional[float] = None
        self.auto_day: Optional[str] = None

    # -- store ---------------------------------------------------------------
    def as_store(self) -> dict[str, Any]:
        return {
            "snapshots": self.snapshots,
            "method": self.method,
            "level": self.level,
            "result": self.result,
            "refreshed_day": self.refreshed_day,
            "auto_effective": self.auto_effective,
            "auto_day": self.auto_day,
        }

    def restore(self, data: Optional[dict[str, Any]]) -> None:
        if not data:
            return
        self.snapshots = dict(data.get("snapshots") or {})
        self.method = data.get("method") if data.get("method") in acc.METHODS else acc.METHOD_AVERAGE
        self.level = data.get("level")
        self.result = data.get("result")
        self.refreshed_day = data.get("refreshed_day")
        self.auto_effective = data.get("auto_effective")
        self.auto_day = data.get("auto_day")

    # -- what the usage forecast uses -------------------------------------------
    def week_weights(self, lookback_weeks: int) -> Optional[list[float]]:
        return acc.week_weights(self.method, lookback_weeks)

    def usage_factor(self) -> float:
        if self.method == acc.METHOD_LEVEL and self.level:
            return float(self.level)
        return 1.0

    # -- snapshots ---------------------------------------------------------------
    def snapshot(
        self, day_iso: str, day_hours: list[int], base_epoch: int, solar: list[Optional[float]], usage: list[float]
    ) -> None:
        """Keep today's forecast as it is now - once, at the day's first cycle.
        Hours already past are None."""
        if day_iso in self.snapshots:
            return

        def pick(series: list) -> list[Optional[float]]:
            out: list[Optional[float]] = []
            for epoch in day_hours:
                i = (epoch - base_epoch) // 3600
                v = series[i] if 0 <= i < len(series) else None
                out.append(round(float(v), 3) if v is not None else None)
            return out

        first = max(0, (base_epoch - day_hours[0]) // 3600) if day_hours else 0
        self.snapshots[day_iso] = {"from": int(first), "solar": pick(solar), "usage": pick(usage)}
        for old in sorted(self.snapshots)[:-SNAPSHOT_DAYS]:
            del self.snapshots[old]

    # -- the daily check -----------------------------------------------------------
    def needs_refresh(self, today_iso: str, now_ts: float) -> bool:
        return self.refreshed_day != today_iso and now_ts - self.tried_at >= RETRY_SECONDS

    def refresh(
        self,
        *,
        today_iso: str,
        today_start: int,
        base_series: dict[int, Optional[float]],
        house_series: dict[int, Optional[float]],
        solar_series: Optional[dict[int, Optional[float]]],
        test_days: list[tuple[str, list[int]]],
        lookback_weeks: int,
        capacity_kwh: float,
        excluded: list[str],
    ) -> bool:
        """Work the check out from the measured series (oldest days first in
        test_days). Returns True when the usage method changed (the cached
        usage forecast has to be redone)."""
        bt = acc.backtest(base_series, test_days, lookback_weeks)
        old_method = self.method
        self.method = bt["chosen"]
        self.level = acc.level_factor(base_series, today_start, lookback_weeks)

        # usage: the last days, measured against the plain average and the method in use
        show = bt["per_day"]
        usage_pairs = [(d[acc.METHOD_AVERAGE], d["actual"]) for d in show]
        # a day without the chosen method (level: too little history before it) shows the average
        chosen_pairs = [(d.get(self.method, d[acc.METHOD_AVERAGE]), d["actual"]) for d in show]
        usage = {
            "per_day": [
                {"d": d["d"], "actual": d["actual"], "forecast": d.get(self.method, d[acc.METHOD_AVERAGE]), "average": d[acc.METHOD_AVERAGE]}
                for d in show
            ],
            "actual_avg": round(sum(a for _, a in usage_pairs) / len(usage_pairs), 2) if usage_pairs else None,
            "forecast_avg": round(sum(p for p, _ in usage_pairs) / len(usage_pairs), 2) if usage_pairs else None,
            **{k: v for k, v in acc._stats(usage_pairs).items()},
            "chosen_mae": acc._stats(chosen_pairs)["mae"],
            "chosen_bias_pct": acc._stats(chosen_pairs)["bias_pct"],
            "excluded": excluded,
        }

        # solar and the buffer: from the snapshots
        solar_days: list[dict[str, Any]] = []
        needed: list[float] = []
        recent = test_days[-acc.BUFFER_WINDOW_DAYS:]
        for iso, hours in recent:
            snap = self.snapshots.get(iso)
            if not snap or snap.get("from", 99) > SNAPSHOT_LATEST_HOUR:
                continue
            house = [house_series.get(e) for e in hours]
            solar_meas = [solar_series.get(e) for e in hours] if solar_series is not None else None
            snap_solar = snap.get("solar") or []
            if solar_meas is not None:
                covered = [i for i, v in enumerate(snap_solar) if v is not None and i < len(hours)]
                if covered and all(solar_meas[i] is not None for i in covered):
                    solar_days.append({
                        "d": iso,
                        "forecast": round(sum(snap_solar[i] for i in covered), 2),
                        "actual": round(sum(solar_meas[i] for i in covered), 2),
                    })
            short = acc.day_shortfall(snap.get("usage") or [], house, snap_solar if solar_meas is not None else None, solar_meas)
            if short is not None and capacity_kwh > 0:
                needed.append(round(short / capacity_kwh * 100, 2))
        solar_show = solar_days[-acc.SHOW_DAYS:]
        show_dates = [iso for iso, _ in test_days[-acc.SHOW_DAYS:]]
        by_date = {d["d"]: d for d in solar_show}
        solar = {
            "measured": solar_series is not None,
            "per_day": [by_date.get(iso, {"d": iso, "forecast": None, "actual": None}) for iso in show_dates],
            **acc.solar_check(solar_show),
        }

        self.result = {
            "updated": today_iso,
            "show_days": acc.SHOW_DAYS,
            "usage": usage,
            "solar": solar,
            "methods": {
                "rows": [{"key": m, **bt["methods"][m]} for m in acc.METHODS],
                "chosen": self.method,
                "level": round(self.level, 3) if self.level is not None else None,
                "test_days": bt["test_days"],
                "min_test_days": acc.MIN_TEST_DAYS,
                "lookback_weeks": lookback_weeks,
            },
            "needed_pct": needed,
        }
        self.refreshed_day = today_iso
        return self.method != old_method

    # -- the Safety buffer -----------------------------------------------------------
    def buffer(self, manual_pct: float, auto_on: bool, today_iso: str) -> dict[str, Any]:
        """The buffer the plans use, and what the card shows about it."""
        needed = (self.result or {}).get("needed_pct") or []
        advice = acc.buffer_advice(needed, manual_pct)
        effective = manual_pct
        if auto_on and advice["advice"] is not None:
            if self.auto_effective is None:
                self.auto_effective = float(manual_pct)
                self.auto_day = None
            if self.auto_day != today_iso:
                self.auto_effective = acc.step_towards(self.auto_effective, float(advice["advice"]))
                self.auto_day = today_iso
            effective = self.auto_effective
        elif not auto_on:
            self.auto_effective = None
            self.auto_day = None
        return {
            "manual": manual_pct,
            "effective": effective,
            "auto": bool(auto_on),
            "auto_active": bool(auto_on and advice["advice"] is not None),
            "min_days": acc.BUFFER_MIN_DAYS,
            "coverage_target": round(acc.BUFFER_COVERAGE * 100),
            **advice,
        }

    def attribute(self, buffer: dict[str, Any], switch_entity: Optional[str]) -> dict[str, Any]:
        result = dict(self.result or {})
        result.pop("needed_pct", None)
        return {**result, "buffer": {**buffer, "switch": switch_entity}, "ready": self.result is not None}
