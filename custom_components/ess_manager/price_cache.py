"""The last good price lists, kept (as of 2026.11.64) - pure Python.

Day-ahead prices don't change once they're published, so when the price
sensor drops out (unavailable, gone, or showing an old day) the cycle can
carry on with the lists it saw before: today's from the store, and
tomorrow's turning into today's after midnight. Only when there's no list
for today at all does planning stop.

What counts as a good list:
- `today` / `tomorrow` attributes, non-empty;
- when the sensor has `raw_today` / `raw_tomorrow` (the Nordpool HACS
  integration: start times per quarter), the date of their first start
  must be today / tomorrow - an old list is a fault, the same as none;
- an empty `tomorrow` is normal (prices come out around 13:00), not a fault.

Stored (per date, yesterday / today / tomorrow kept) only when complete:
as many quarters as the day has (96, or 92 / 100 on a DST day). Without
start times the date is the local date, and nothing is stored in the first
minutes after midnight (the sensor may still show yesterday's lists).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

UNSTAMPED_WAIT = timedelta(minutes=5)


def day_units(day: date, tz: Any) -> int:
    """Quarters in a local day (96; 92 / 100 when the clock changes)."""
    if tz is None:
        return 96
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    return round((end.timestamp() - start.timestamp()) / 900)


def _start_date(raw: Any, tz: Any) -> Optional[date]:
    """The local date of the first start in a raw_today / raw_tomorrow list,
    None when there's none (or it can't be read)."""
    if not isinstance(raw, (list, tuple)) or not raw or not isinstance(raw[0], dict):
        return None
    start = raw[0].get("start")
    if isinstance(start, str):
        try:
            start = datetime.fromisoformat(start)
        except ValueError:
            return None
    if not isinstance(start, datetime):
        return None
    if start.tzinfo is not None and tz is not None:
        start = start.astimezone(tz)
    return start.date()


def _floats(values: Any) -> Optional[list[float]]:
    if not isinstance(values, (list, tuple)) or not values:
        return None
    try:
        return [float(v) for v in values]
    except (TypeError, ValueError):
        return None


def read_sensor(state: Any, now: datetime) -> dict[str, Any]:
    """What the price sensor gives this cycle:
    {today, tomorrow (lists or None), today_stale, tomorrow_stale, stamped}."""
    out: dict[str, Any] = {"today": None, "tomorrow": None, "today_stale": False,
                           "tomorrow_stale": False, "stamped": False}
    if state is None or state.state in ("unavailable", "unknown"):
        return out
    attrs = state.attributes
    tz = now.tzinfo
    today = now.date()
    for key, want, stale_key in (("today", today, "today_stale"),
                                 ("tomorrow", today + timedelta(days=1), "tomorrow_stale")):
        values = _floats(attrs.get(key))
        if values is None:
            continue
        raw = attrs.get(f"raw_{key}")
        stamp = _start_date(raw, tz)
        if stamp is not None:
            out["stamped"] = True
            if stamp != want:
                out[stale_key] = True
                continue
        out[key] = values
    return out


class PriceCache:
    """The stored lists per date, and where this cycle's prices came from."""

    def __init__(self) -> None:
        self.days: dict[str, list[float]] = {}
        self.source: str = "sensor"           # sensor / cached / none (today's list)
        self.tomorrow_source: Optional[str] = None
        self.fault_since: Optional[datetime] = None

    def restore(self, data: Any) -> None:
        if isinstance(data, dict) and isinstance(data.get("days"), dict):
            self.days = {k: [float(x) for x in v] for k, v in data["days"].items()
                         if isinstance(v, list) and v}

    def as_store(self) -> dict[str, Any]:
        return {"days": self.days}

    def note(self, day: date, values: Optional[list[float]], tz: Any) -> bool:
        """Keep a complete list for `day`. True when the store changed."""
        if not values or len(values) != day_units(day, tz):
            return False
        key = day.isoformat()
        if self.days.get(key) == values:
            return False
        self.days[key] = list(values)
        return True

    def prune(self, today: date) -> bool:
        keep = {(today + timedelta(days=d)).isoformat() for d in (-1, 0, 1)}
        gone = [k for k in self.days if k not in keep]
        for k in gone:
            del self.days[k]
        return bool(gone)

    def resolve(self, sensor: dict[str, Any], now: datetime) -> dict[str, Any]:
        """This cycle's lists - the sensor's where good, the stored ones
        otherwise - and whether the sensor is at fault. Stores what's good
        (`changed` True when the store should be saved)."""
        tz = now.tzinfo
        today = now.date()
        tomorrow = today + timedelta(days=1)
        changed = False
        storable = sensor["stamped"] or now - now.replace(hour=0, minute=0, second=0, microsecond=0) >= UNSTAMPED_WAIT
        if storable:
            changed |= self.note(today, sensor["today"], tz)
            changed |= self.note(tomorrow, sensor["tomorrow"], tz)
        changed |= self.prune(today)
        today_list = sensor["today"]
        self.source = "sensor"
        if today_list is None:
            today_list = self.days.get(today.isoformat())
            self.source = "cached" if today_list else "none"
        tomorrow_list = sensor["tomorrow"]
        self.tomorrow_source = "sensor" if tomorrow_list else None
        if tomorrow_list is None and self.days.get(tomorrow.isoformat()):
            tomorrow_list = self.days[tomorrow.isoformat()]
            self.tomorrow_source = "cached"
        fault = sensor["today"] is None or sensor["tomorrow_stale"]
        if not fault:
            self.fault_since = None
        elif self.fault_since is None:
            self.fault_since = now
        return {"today": list(today_list or []), "tomorrow": list(tomorrow_list or []),
                "fault": fault, "changed": changed}

    def known_until(self, now: datetime, today_n: int, tomorrow_n: int) -> Optional[str]:
        """When the last known price ends (local ISO), None without prices."""
        if not today_n:
            return None
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        days = 2 if tomorrow_n else 1
        end = datetime.combine(midnight.date() + timedelta(days=days), datetime.min.time(), tzinfo=now.tzinfo)
        return end.isoformat(timespec="minutes")

    def as_diag(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "tomorrow_source": self.tomorrow_source,
            "fault_since": self.fault_since.isoformat(timespec="seconds") if self.fault_since else None,
            "stored": {k: len(v) for k, v in sorted(self.days.items())},
        }
