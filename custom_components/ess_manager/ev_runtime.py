"""The electric car's live state (as of 2026.10.11): the card's edits, the
running session and the finished ones, kept in the coordinator's store, and
each cycle's session list + EV forecast. Pure Python (no Home Assistant
imports) so tests/test_pipeline.py can run it; the coordinator reads the
charger's power and energy and passes them in.

Session ids: "h:YYYY-MM-DDTHH" for a predicted session (its local start
hour, see ev.session_key) and "m:<hex>" for a manual one.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, tzinfo
from typing import Any, Optional

from . import ev

# The charger counts as charging above this power (W) ...
RUNNING_W = 50.0
# ... and the session as finished once it has been below it this long.
STOP_AFTER = 10 * 60
# A charge that starts up to this long before a session's start belongs to it.
EARLY = ev.HOUR
# Finished ids, past overrides and past manual sessions are forgotten after:
KEEP = 2 * 24 * ev.HOUR

# The fields the card may set on a session.
EDIT_FIELDS = ("start", "kwh", "mode", "current_a", "car", "start_soc", "target_soc", "enabled")


def _floor_hour(epoch: int) -> int:
    return epoch - epoch % ev.HOUR


def _clean_edit(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in EDIT_FIELDS:
        if key not in fields:
            continue
        value = fields[key]
        if key == "start" and value is not None:
            value = _floor_hour(int(value))
        elif key in ("kwh", "start_soc", "target_soc", "current_a") and value is not None:
            value = max(float(value), 0.0)
            if key in ("start_soc", "target_soc"):
                value = min(value, 100.0)
        elif key == "mode" and value not in (ev.MODE_FIXED, ev.MODE_SOLAR):
            continue
        elif key == "enabled":
            value = bool(value)
        out[key] = value
    return out


class EvRuntime:
    """Stored state: `overrides` (predicted id -> edited fields), `manual`
    (sessions added on the card, or a charge that matched no session),
    `running` ({id, energy_start, low_since}) and `done` (id -> epoch).
    `history` is the car's hourly energy (and solar surplus) from the
    statistics, refreshed with the usage forecast; not stored."""

    def __init__(self) -> None:
        self.overrides: dict[str, dict[str, Any]] = {}
        self.manual: list[dict[str, Any]] = []
        self.running: Optional[dict[str, Any]] = None
        self.done: dict[str, int] = {}
        self.history: Optional[tuple[dict[int, float], Optional[dict[int, float]]]] = None
        self.last_sessions: list[dict[str, Any]] = []

    # -- store ---------------------------------------------------------------
    def restore(self, data: Optional[dict[str, Any]]) -> None:
        data = data or {}
        self.overrides = dict(data.get("overrides") or {})
        self.manual = list(data.get("manual") or [])
        self.running = data.get("running") or None
        self.done = {k: int(v) for k, v in (data.get("done") or {}).items()}

    def as_store(self) -> dict[str, Any]:
        return {"overrides": self.overrides, "manual": self.manual, "running": self.running, "done": self.done}

    # -- card edits ----------------------------------------------------------
    def save(self, session_id: Optional[str], fields: dict[str, Any], now_epoch: int) -> str:
        """Create (no id) or change a session; returns its id. A running
        session keeps its day and start time."""
        edit = _clean_edit(fields)
        if self.running and session_id == self.running.get("id"):
            edit.pop("start", None)
        if not session_id:
            if edit.get("start") is None:
                raise ValueError("a new session needs a start")
            session_id = "m:" + uuid.uuid4().hex[:10]
            self.manual.append(
                {
                    "id": session_id,
                    "start": edit["start"],
                    "kwh": edit.get("kwh", 10.0),
                    "mode": edit.get("mode", ev.MODE_FIXED),
                    "current_a": edit.get("current_a"),
                    "car": edit.get("car"),
                    "start_soc": edit.get("start_soc"),
                    "target_soc": edit.get("target_soc"),
                    "enabled": edit.get("enabled", True),
                }
            )
            return session_id
        if session_id.startswith("h:"):
            self.overrides[session_id] = {**self.overrides.get(session_id, {}), **edit}
            return session_id
        for s in self.manual:
            if s["id"] == session_id:
                s.update(edit)
                return session_id
        raise KeyError(session_id)

    def remove(self, session_id: str) -> None:
        """A manual session is deleted; a predicted one goes back to the
        average (its edit is dropped)."""
        if session_id.startswith("h:"):
            self.overrides.pop(session_id, None)
            return
        before = len(self.manual)
        self.manual = [s for s in self.manual if s["id"] != session_id]
        if len(self.manual) == before:
            raise KeyError(session_id)
        if self.running and self.running.get("id") == session_id:
            self.running = None

    # -- every cycle ---------------------------------------------------------
    def _prune(self, now_epoch: int) -> None:
        self.done = {k: v for k, v in self.done.items() if now_epoch - v < KEEP}
        running_id = (self.running or {}).get("id")
        self.manual = [
            s for s in self.manual
            if s["id"] == running_id or s["id"] in self.done or int(s["start"]) + ev.START_GRACE > now_epoch
        ]
        keep = {}
        for sid, o in self.overrides.items():
            start = o.get("start")
            if start is None:
                try:
                    start = int(datetime.strptime(sid[2:], "%Y-%m-%dT%H").timestamp())
                except ValueError:
                    continue
            if sid == running_id or now_epoch - int(start) < KEEP:
                keep[sid] = o
        self.overrides = keep

    def _track_running(
        self,
        sessions: list[dict[str, Any]],
        power_w: Optional[float],
        energy_kwh: Optional[float],
        now_epoch: int,
        phases: int,
        min_a: float,
        max_a: float,
        typical_kwh: float,
    ) -> bool:
        """Follow the charger. Returns True when the session list changed
        (a session started without a match, or one finished)."""
        charging = power_w is not None and power_w > RUNNING_W
        if self.running:
            if charging:
                self.running["low_since"] = None
                if self.running.get("energy_start") is None and energy_kwh is not None:
                    self.running["energy_start"] = energy_kwh
                return False
            if power_w is None:
                return False  # unknown: keep it as it is
            if self.running.get("low_since") is None:
                self.running["low_since"] = now_epoch
                return False
            if now_epoch - int(self.running["low_since"]) >= STOP_AFTER:
                self.done[self.running["id"]] = now_epoch
                self.running = None
                return True
            return False
        if not charging:
            return False
        # the session this charge belongs to: started around its start
        match = None
        for s in sessions:
            if s["id"] in self.done:
                continue
            if int(s["start"]) - EARLY <= now_epoch < int(s["start"]) + ev.START_GRACE:
                if match is None or abs(int(s["start"]) - now_epoch) < abs(int(match["start"]) - now_epoch):
                    match = s
        hour = _floor_hour(now_epoch)
        if match is None:
            sid = "m:" + uuid.uuid4().hex[:10]
            self.manual.append(
                {
                    "id": sid,
                    "start": hour,
                    "kwh": round(typical_kwh, 2),
                    "mode": ev.MODE_FIXED,
                    "current_a": ev.current_for_power((power_w or 0.0) / 1000.0, phases, min_a, max_a),
                    "car": None,
                    "start_soc": None,
                    "target_soc": None,
                    "enabled": True,
                    "auto": True,
                }
            )
            self.running = {"id": sid, "energy_start": energy_kwh, "low_since": None}
            return True
        if int(match["start"]) > now_epoch:
            # started early: the session starts now
            self.save(match["id"], {"start": hour}, now_epoch)
        self.running = {"id": match["id"], "energy_start": energy_kwh, "low_since": None}
        return True

    def update(
        self,
        conf: dict[str, Any],
        now: datetime,
        tz: tzinfo,
        lookback_weeks: int,
        house_net: list[float],
        power_w: Optional[float],
        energy_kwh: Optional[float],
        days: int = 5,
    ) -> tuple[list[float], dict[str, Any]]:
        """This cycle's EV forecast per hour (hour 0 = the current hour, a
        full-hour value) and the Status sensor's `ev` attribute.
        `conf` holds the EV settings: phases, min_current, max_current,
        predict, cars."""
        phases = int(conf.get("phases") or 3)
        min_a = float(conf.get("min_current") or 6)
        max_a = float(conf.get("max_current") or 16)
        if max_a < min_a:
            max_a = min_a
        cars = list(conf.get("cars") or [])
        predict = bool(conf.get("predict", True))
        now_epoch = int(now.timestamp())
        hour0 = _floor_hour(now_epoch)
        hours = len(house_net)
        today = now.astimezone(tz).date()
        midnights = [datetime.combine(today + timedelta(days=i), time(0), tzinfo=tz) for i in range(days)]
        end_epoch = int(datetime.combine(today + timedelta(days=days), time(0), tzinfo=tz).timestamp())

        self._prune(now_epoch)
        predicted: list[dict[str, Any]] = []
        if predict and self.history:
            predicted = ev.detect_sessions(
                self.history[0], self.history[1], midnights, lookback_weeks, phases, min_a, max_a, tz
            )
        by_pred = {p["id"]: p for p in predicted}
        typical = sorted(p["kwh"] for p in predicted)
        typical_kwh = typical[len(typical) // 2] if typical else round(ev.power_kw(max_a, phases) * 2, 1)

        def build() -> list[dict[str, Any]]:
            return ev.build_sessions(
                predicted, self.overrides, self.manual, cars, now_epoch, end_epoch,
                running_id=(self.running or {}).get("id"), done=set(self.done),
            )

        sessions = build()
        if self._track_running(sessions, power_w, energy_kwh, now_epoch, phases, min_a, max_a, typical_kwh):
            sessions = build()

        delivered: dict[str, float] = {}
        if self.running and energy_kwh is not None and self.running.get("energy_start") is not None:
            delivered[self.running["id"]] = max(energy_kwh - float(self.running["energy_start"]), 0.0)

        # sessions in start order share the solar surplus: what one takes,
        # the next can't
        total = [0.0] * hours
        net_left = list(house_net)
        out: list[dict[str, Any]] = []
        for s in sessions:
            part, info = ev.ev_forecast([s], now_epoch, hour0, hours, net_left, phases, min_a, max_a, tz, delivered)
            if s.get("enabled", True):
                total = [round(a + b, 4) for a, b in zip(total, part)]
                net_left = [round(n - p, 4) for n, p in zip(net_left, part)]
            out.extend(info)
        self.last_sessions = out

        car_names = {c.get("id"): c.get("name") for c in cars}

        def iso(epoch: Optional[int]) -> Optional[str]:
            return datetime.fromtimestamp(int(epoch), tz).isoformat() if epoch is not None else None

        attr_sessions = []
        for s in out:
            current = s.get("current_a") or max_a
            item = {
                "id": s["id"],
                "start": iso(s["start"]),
                "end": iso(s.get("end")),
                "kwh": s.get("kwh"),
                "charged_kwh": s.get("charged_kwh"),
                "delivered_kwh": round(delivered.get(s["id"], 0.0), 2) if s.get("running") else None,
                "mode": s.get("mode", ev.MODE_FIXED),
                "current_a": int(round(min(max(float(current), min_a), max_a))),
                "power_kw": ev.power_kw(min(max(float(current), min_a), max_a), phases),
                "car": s.get("car"),
                "car_name": car_names.get(s.get("car")),
                "start_soc": s.get("start_soc"),
                "target_soc": s.get("target_soc"),
                "enabled": bool(s.get("enabled", True)),
                "label": s.get("label"),
                "solar_history": bool(s.get("solar_history")) and s.get("mode") == ev.MODE_SOLAR,
                "running": bool(s.get("running")),
                "warning": s.get("warning"),
            }
            original = by_pred.get(s["id"])
            if original is not None and s.get("label") == ev.LABEL_EDITED:
                car = next((c for c in cars if c.get("id") == s.get("car")), None)
                avg = ev.apply_car({**original, "car": s.get("car")}, car) if car else original
                item["history"] = {
                    "start": iso(original["start"]),
                    "kwh": avg.get("kwh"),
                    "start_soc": avg.get("start_soc"),
                    "mode": original.get("mode"),
                }
            attr_sessions.append(item)

        attribute = {
            "sessions": attr_sessions,
            "cars": [
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "capacity_kwh": c.get("capacity_kwh"),
                    "target_soc": c.get("target_soc"),
                }
                for c in cars
            ],
            "phases": phases,
            "min_current": int(min_a),
            "max_current": int(max_a),
            "predict": predict,
            "days": days,
            "power_w": power_w,
            "total_kwh": round(sum(s["charged_kwh"] or 0.0 for s in out if s.get("enabled", True)), 2),
            "forecast_120h": total,
            "house_net_120h": list(house_net),
        }
        return total, attribute
