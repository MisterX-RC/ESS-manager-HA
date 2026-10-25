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

from . import ev, ev_charger as evc, ev_notify as evn

# The charger counts as charging above this power (W) ...
RUNNING_W = 50.0
# ... and the session as finished once it has been below it this long.
STOP_AFTER = 10 * 60
# A charge that starts up to this long before a session's start belongs to it.
EARLY = ev.HOUR
# Finished ids, past overrides and past manual sessions are forgotten after:
KEEP = 2 * 24 * ev.HOUR

# The morning question about the day's planned sessions (Victron charger)
MORNING_HOUR = 9

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


# -- the Victron charger (as of 2026.10.27) --------------------------------------
def _token() -> str:
    return uuid.uuid4().hex[:8]


class _VictronMixin:
    """Bolted onto EvRuntime below: the conversation with the phone when a
    car is plugged in, the plan for it, and the morning questions."""

    flow: Optional[dict[str, Any]]
    morning: dict[str, dict[str, Any]]
    morning_day: Optional[str]
    outbox: list[dict[str, Any]]
    ctx: dict[str, Any]
    manual: list[dict[str, Any]]
    done: dict[str, int]
    running: Optional[dict[str, Any]]

    # -- sending ---------------------------------------------------------------
    def _tag(self, sid: Optional[str] = None) -> str:
        entry = self.ctx.get("entry_id", "")
        return f"ess_ev_{entry}" if sid is None else f"ess_ev_morning_{entry}_{sid.replace(':', '_')}"

    def _send(self, message: str, actions: Optional[list[dict[str, Any]]] = None, sid: Optional[str] = None) -> None:
        if not self.ctx.get("notify"):
            return
        self.outbox.append({"payload": evn.payload(self.ctx["language"], message, self._tag(sid), actions)})

    def _clear(self, sid: Optional[str] = None) -> None:
        if self.ctx.get("notify"):
            self.outbox.append({"payload": evn.clear(self._tag(sid))})

    def _t(self, key: str, **values: Any) -> str:
        return evn.t(self.ctx["language"], key, **values)

    def _car(self, car_id: Optional[str]) -> Optional[dict[str, Any]]:
        cars = self.ctx.get("cars") or []
        if car_id:
            return next((c for c in cars if c.get("id") == car_id), None)
        return cars[0] if len(cars) == 1 else None

    # -- the questions ------------------------------------------------------------
    def _ask(self, step: str, bad: bool = False) -> None:
        flow = self.flow
        assert flow is not None
        flow["step"] = step
        entry, token, lg = self.ctx["entry_id"], flow["token"], self.ctx["language"]
        prefix = self._t("bad") if bad else ""
        if step == "car":
            cars = self.ctx.get("cars") or []
            if len(cars) <= evn.MAX_BUTTONS:
                self._send(prefix + self._t("which_car"), evn.buttons(entry, token, [(f"car={c['id']}", c["name"]) for c in cars]))
            else:
                listing = "\n".join(f"{i}. {c['name']}" for i, c in enumerate(cars, 1))
                self._send(prefix + self._t("which_car_typed", list=listing), evn.reply(entry, token, "car", lg, "ph_car"))
        elif step == "choice":
            car = self._car(flow.get("car"))
            text = self._t("connected", car=car["name"]) if car else self._t("connected_nocar")
            self._send(prefix + text, evn.buttons(entry, token, [
                (f"choice={evc.CHOICE_ASAP}", self._t("asap")),
                (f"choice={evc.CHOICE_CALM}", self._t("calm")),
                (f"choice={evc.CHOICE_DEADLINE}", self._t("deadline")),
            ]))
        elif step == "day":
            self._send(prefix + self._t("day"), evn.buttons(entry, token, [
                (f"day={d}", self._t(d)) for d in evc.DAYS
            ]))
        elif step in ("hour", "hour_past"):
            flow["step"] = "hour"
            self._send(self._t(step, day=self._t(flow.get("day") or evc.DAY_TODAY).lower()), evn.reply(entry, token, "hour", lg, "ph_hour"))
        elif step == "soc":
            self._send(prefix + self._t("soc"), evn.reply(entry, token, "soc", lg, "ph_soc"))
        elif step == "kwh":
            self._send(prefix + self._t("kwh"), evn.reply(entry, token, "kwh", lg, "ph_kwh"))

    def _ask_amount(self) -> None:
        car = self._car((self.flow or {}).get("car"))
        self._ask("soc" if car and car.get("capacity_kwh") else "kwh")

    # -- plug in / out ------------------------------------------------------------------
    def _victron_track(self, sessions: list[dict[str, Any]], connected: bool, status: Optional[str], energy_kwh: Optional[float], now_epoch: int, typical_kwh: float) -> bool:
        """Follow the charger: a car plugged in starts a session and the
        questions; unplugged ends it. True when the session list changed."""
        flow = self.flow
        if flow and not connected:
            self.done[flow["sid"]] = now_epoch
            if self.running and self.running.get("id") == flow["sid"]:
                self.running = None
            self.flow = None
            self._clear()
            return True
        if flow or not connected:
            if flow is not None:
                flow["last_energy"] = energy_kwh
                if status == evc.STATUS_CHARGED and flow.get("choice") is not None:
                    flow["done"] = True
            return False
        # a car plugged in: a new session; planned ones it overlaps go
        hour = _floor_hour(now_epoch)
        expected = None
        for s in sessions:
            if s.get("running"):
                continue
            start = int(s["start"])
            end = max(int(s.get("end") or 0), start + ev.START_GRACE)
            if start - EARLY <= now_epoch < end:
                if expected is None:
                    expected = s.get("kwh")
                self.done[s["id"]] = now_epoch
        cars = self.ctx.get("cars") or []
        sid = "m:" + uuid.uuid4().hex[:10]
        self.manual.append({
            "id": sid,
            "start": hour,
            "kwh": round(float(expected or typical_kwh), 2),
            "mode": ev.MODE_SOLAR,
            "current_a": None,
            "car": cars[0]["id"] if len(cars) == 1 else None,
            "start_soc": None,
            "target_soc": None,
            "enabled": True,
            "auto": True,
            "victron": True,
        })
        self.running = {"id": sid, "energy_start": energy_kwh, "low_since": None}
        self.flow = {
            "sid": sid, "token": _token(), "step": None, "since": now_epoch,
            "car": cars[0]["id"] if len(cars) == 1 else None,
            "choice": None, "day": None, "deadline": None, "need_kwh": None, "soc": None,
            "energy_at_need": energy_kwh, "last_energy": energy_kwh, "windows": [], "quarters": [],
            "plan": None, "done": False, "announce": False,
        }
        if len(cars) > 1:
            self._ask("car")
        else:
            self._ask("choice")
        return True

    def _session(self, sid: str) -> Optional[dict[str, Any]]:
        return next((s for s in self.manual if s["id"] == sid), None)

    # -- answers ----------------------------------------------------------------------
    # -- shared by the phone and the card ------------------------------------------------
    def _apply_car(self, car: dict[str, Any]) -> None:
        flow = self.flow
        assert flow is not None
        flow["car"] = car["id"]
        session = self._session(flow["sid"])
        if session is not None:
            session["car"] = car["id"]

    def _apply_choice(self, value: str) -> None:
        flow = self.flow
        assert flow is not None
        flow["choice"] = value
        flow["done"] = False
        session = self._session(flow["sid"])
        if session is not None:
            if value == evc.CHOICE_DEADLINE:
                session.update({"mode": ev.MODE_SOLAR, "current_a": None})
            else:
                max_a, min_a = self.ctx["max_a"], self.ctx["min_a"]
                session.update({"mode": ev.MODE_FIXED, "current_a": max_a if value == evc.CHOICE_ASAP else min_a})
            session["plan"] = value

    def _deadline(self, day: Optional[str], hm: tuple[int, int], now_epoch: int) -> int:
        tz = self.ctx["tz"]
        today = datetime.fromtimestamp(now_epoch, tz).date()
        date = today + timedelta(days=1 if day == evc.DAY_TOMORROW else 0)
        return int(datetime.combine(date, time(hm[0], hm[1]), tzinfo=tz).timestamp())

    def _apply_need(self, need: float, soc: Optional[float]) -> None:
        flow = self.flow
        assert flow is not None
        car = self._car(flow.get("car"))
        flow["step"] = None
        flow["soc"] = soc
        flow["need_kwh"] = need
        flow["energy_at_need"] = flow.get("last_energy")
        flow["announce"] = True
        flow["done"] = need <= 0
        session = self._session(flow["sid"])
        if session is not None:
            # the session counts from plugging in: what went in before the
            # answer plus what's still needed (its start SOC follows from
            # that, see ev.apply_car)
            start = (self.running or {}).get("energy_start") if (self.running or {}).get("id") == flow["sid"] else None
            last = flow.get("last_energy")
            before = max(float(last) - float(start), 0.0) if start is not None and last is not None else 0.0
            session["kwh"] = round(need + before, 2)
            session["start_soc"] = None
            if car and car.get("target_soc") is not None:
                session["target_soc"] = car["target_soc"]

    # -- answers on the phone -------------------------------------------------------------
    def answer(self, token: str, what: str, reply_text: Optional[str], now_epoch: int) -> bool:
        """A tap or reply on the phone. True when something changed."""
        if what.startswith("m_"):
            return self._answer_morning(token, what, reply_text, now_epoch)
        flow = self.flow
        if not flow or token != flow.get("token"):
            return False
        key, _, value = what.partition("=")
        if key == "car":
            car = self._car(value) if value else evc.match_car(reply_text, self.ctx.get("cars") or [])
            if car is None:
                self._ask("car", bad=True)
                return False
            self._apply_car(car)
            self._ask("choice")
            return True
        if key == "choice" and value in evc.CHOICES:
            self._apply_choice(value)
            if value == evc.CHOICE_DEADLINE:
                self._ask("day")
            elif flow.get("need_kwh") is None:
                self._ask_amount()
            else:
                flow["announce"] = True
            return True
        if key == "day" and value in evc.DAYS:
            flow["day"] = value
            if value == evc.DAY_ANY:
                flow["deadline"] = None
                self._ask_amount() if flow.get("need_kwh") is None else flow.update(announce=True)
            else:
                self._ask("hour")
            return True
        if key == "hour":
            hm = evc.parse_hour(reply_text)
            if hm is None:
                self._ask("hour")
                return False
            deadline = self._deadline(flow.get("day"), hm, now_epoch)
            if deadline <= now_epoch:
                self._ask("hour_past")
                return False
            flow["deadline"] = deadline
            self._ask_amount() if flow.get("need_kwh") is None else flow.update(announce=True)
            return True
        if key in ("soc", "kwh"):
            car = self._car(flow.get("car"))
            if key == "soc":
                soc = evc.parse_soc(reply_text)
                need = evc.needed_kwh(car, soc) if soc is not None else None
            else:
                soc = None
                need = evc.parse_kwh(reply_text)
            if need is None:
                self._ask(key, bad=True)
                return False
            self._apply_need(need, soc)
            return True
        return False

    # -- the same on the card (as of 2026.10.27) ---------------------------------------------
    def set_plan(self, fields: dict[str, Any], now_epoch: int) -> None:
        """The plugged-in car's plan in one go, from the EV card (service
        ess_manager.ev_charge_plan): car, choice (asap / calm / deadline),
        day (today / tomorrow / any) and hour ("HH:MM") for a deadline, and
        soc (%) or kwh. What isn't given stays as it was (a SOC or kWh that
        is already known can be left out). The open question on the phone
        is withdrawn; the end time comes as a notification like after an
        answer there. Raises ValueError with what's missing."""
        flow = self.flow
        if not flow:
            raise ValueError("No car is plugged in")
        cars = self.ctx.get("cars") or []
        car = None
        if fields.get("car"):
            car = self._car(fields["car"])
            if car is None:
                raise ValueError(f"No car {fields['car']}")
        elif flow.get("car"):
            car = self._car(flow["car"])
        elif len(cars) > 1:
            raise ValueError("Pick the car")
        else:
            car = self._car(None)
        choice = fields.get("choice") or flow.get("choice")
        if choice not in evc.CHOICES:
            raise ValueError("Pick as fast as possible, slowly or full by a time")
        day = fields.get("day") or flow.get("day")
        deadline = flow.get("deadline")
        if choice == evc.CHOICE_DEADLINE:
            if day not in evc.DAYS:
                raise ValueError("Pick the day: today, tomorrow or doesn't matter")
            if day == evc.DAY_ANY:
                deadline = None
            elif fields.get("hour") is not None or deadline is None or fields.get("day"):
                hm = evc.parse_hour(fields.get("hour"))
                if hm is None:
                    raise ValueError("Give the time it should be full")
                deadline = self._deadline(day, hm, now_epoch)
                if deadline <= now_epoch:
                    raise ValueError("That time has passed")
        need = soc = None
        if fields.get("soc") is not None:
            soc = float(fields["soc"])
            if not 0 <= soc <= 100:
                raise ValueError("The state of charge is 0-100 %")
            need = evc.needed_kwh(car, soc)
            if need is None:
                raise ValueError("This car has no battery size: give the kWh")
        elif fields.get("kwh") is not None:
            need = float(fields["kwh"])
            if not 0 < need <= 250:
                raise ValueError("The energy is 0-250 kWh")
        elif flow.get("need_kwh") is None:
            raise ValueError("Give the car's state of charge" if car and car.get("capacity_kwh") else "Give the kWh to charge")
        # all checked: apply
        if car is not None:
            self._apply_car(car)
        self._apply_choice(choice)
        flow["day"] = day if choice == evc.CHOICE_DEADLINE else None
        flow["deadline"] = deadline if choice == evc.CHOICE_DEADLINE else None
        if need is not None:
            self._apply_need(need, soc)
        flow["step"] = None
        flow["announce"] = True
        # the phone's buttons go stale; its open question goes away
        flow["token"] = _token()
        self._clear()

    def need_left(self) -> Optional[float]:
        flow = self.flow or {}
        need = flow.get("need_kwh")
        if need is None:
            return None
        start, last = flow.get("energy_at_need"), flow.get("last_energy")
        got = max(float(last) - float(start), 0.0) if start is not None and last is not None else 0.0
        return max(float(need) - got, 0.0)

    # -- each cycle: the plan, done, the announcement ------------------------------------
    def _victron_plan(self, now_epoch: int, hour0: int, house_net: list[float], phases: int, min_a: float, max_a: float) -> None:
        flow = self.flow
        if not flow:
            return
        left = self.need_left()
        if left is not None and left <= 0.05 and flow.get("choice") is not None:
            flow["done"] = True
        p_max, p_min = ev.power_kw(max_a, phases), ev.power_kw(min_a, phases)
        tz = self.ctx["tz"]
        lg = self.ctx["language"]
        plan = None
        if flow.get("choice") == evc.CHOICE_DEADLINE and left is not None and not flow.get("done"):
            prices = self.ctx.get("prices") or []
            price_start = int(self.ctx.get("price_start") or 0)
            deadline = flow.get("deadline") or (price_start + len(prices) * evc.UNIT)
            keep: list[int] = []
            quarter = now_epoch - now_epoch % evc.UNIT
            for a, b in flow.get("windows") or []:
                if a <= now_epoch < b:
                    keep = list(range(quarter, b, evc.UNIT))
            plan = evc.plan_deadline(now_epoch, deadline, left, house_net, hour0, prices, price_start, p_min, p_max, keep)
            plan["deadline"] = deadline
            flow["windows"] = plan["windows"]
            flow["quarters"] = plan["quarters"]
        else:
            flow["windows"] = []
            flow["quarters"] = []
        flow["plan"] = plan
        if not flow.get("announce"):
            return
        flow["announce"] = False
        need = flow.get("need_kwh") or 0.0
        choice = flow.get("choice")
        if choice in (evc.CHOICE_ASAP, evc.CHOICE_CALM):
            kw = p_max if choice == evc.CHOICE_ASAP else p_min
            end = now_epoch + int((left or 0.0) / kw * 3600) if kw > 0 else None
            self._send(self._t("plan_" + choice, kw=f"{kw:g}", kwh=f"{need:g}", end=evn.clock(end, tz, now_epoch, lg)))
        elif plan is not None:
            windows = evn.windows_text(plan["windows"], tz, now_epoch, lg)
            if plan["short_kwh"] > 0.05:
                self._send(self._t("plan_short", deadline=evn.clock(plan["deadline"], tz, now_epoch, lg), kwh=f"{need:g}",
                                   short=f"{plan['short_kwh']:g}", windows=windows))
            elif flow.get("deadline") is None:
                self._send(self._t("plan_any", kwh=f"{need:g}", windows=windows, end=evn.clock(plan["end"], tz, now_epoch, lg)))
            else:
                self._send(self._t("plan_deadline", deadline=evn.clock(plan["deadline"], tz, now_epoch, lg), kwh=f"{need:g}",
                                   solar=f"{plan['solar_kwh']:g}", grid=f"{plan['grid_kwh']:g}", windows=windows,
                                   end=evn.clock(plan["end"], tz, now_epoch, lg)))

    # -- the morning question ---------------------------------------------------------------
    def _victron_morning(self, sessions: list[dict[str, Any]], now: datetime, now_epoch: int) -> None:
        tz = self.ctx["tz"]
        local = now.astimezone(tz)
        self.morning = {k: v for k, v in self.morning.items() if int(v.get("start", 0)) + ev.START_GRACE > now_epoch}
        today = local.date().isoformat()
        if not self.ctx.get("notify") or local.hour < MORNING_HOUR or self.morning_day == today:
            return
        self.morning_day = today
        flow_sid = (self.flow or {}).get("sid")
        lg = self.ctx["language"]
        for s in sessions:
            start = int(s["start"])
            if s.get("running") or s["id"] == flow_sid or not s.get("enabled", True) or start <= now_epoch:
                continue
            if datetime.fromtimestamp(start, tz).date() != local.date():
                continue
            token = _token()
            self.morning[s["id"]] = {"token": token, "step": "confirm", "start": start}
            when = evn.clock(start, tz, now_epoch, lg)
            entry = self.ctx["entry_id"]
            self._send(self._t("morning", time=when, kwh=f"{float(s.get('kwh') or 0):g}"), evn.buttons(entry, token, [
                (f"m_yes={s['id']}", self._t("yes")), (f"m_no={s['id']}", self._t("no")),
            ]), sid=s["id"])

    def _answer_morning(self, token: str, what: str, reply_text: Optional[str], now_epoch: int) -> bool:
        key, _, sid = what.partition("=")
        ask = self.morning.get(sid)
        if not ask or ask.get("token") != token:
            return False
        tz, lg, entry = self.ctx["tz"], self.ctx["language"], self.ctx["entry_id"]
        when = evn.clock(ask["start"], tz, now_epoch, lg)
        session = next((s for s in self.last_sessions if s["id"] == sid), None)  # type: ignore[attr-defined]
        car = self._car((session or {}).get("car"))
        if key == "m_no":
            if sid.startswith("h:"):
                self.done[sid] = now_epoch
            else:
                self.manual = [s for s in self.manual if s["id"] != sid]
            self.morning.pop(sid, None)
            self._send(self._t("morning_removed", time=when), sid=sid)
            return True
        if key == "m_yes":
            ask["step"] = "value"
            use_soc = bool(car and car.get("capacity_kwh"))
            ask["soc"] = use_soc
            self._send(self._t("morning_soc" if use_soc else "morning_kwh", time=when),
                       evn.reply(entry, token, f"m_val={sid}", lg, "ph_soc" if use_soc else "ph_kwh"), sid=sid)
            return True
        if key == "m_val":
            if ask.get("soc"):
                soc = evc.parse_soc(reply_text)
                kwh = evc.needed_kwh(car, soc) if soc is not None else None
                fields: dict[str, Any] = {"start_soc": soc}
            else:
                kwh = evc.parse_kwh(reply_text)
                fields = {"kwh": kwh}
            if kwh is None:
                self._send(self._t("bad") + self._t("morning_soc" if ask.get("soc") else "morning_kwh", time=when),
                           evn.reply(entry, token, f"m_val={sid}", lg, "ph_soc" if ask.get("soc") else "ph_kwh"), sid=sid)
                return False
            if car is not None and session is not None and not session.get("car"):
                fields["car"] = car["id"]
            try:
                self.save(sid, fields, now_epoch)  # type: ignore[attr-defined]
            except KeyError:
                return False
            self.morning.pop(sid, None)
            self._send(self._t("morning_set", time=when, kwh=f"{kwh:g}"), sid=sid)
            return True
        return False


class EvRuntime(_VictronMixin):
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
        # the Victron charger (as of 2026.10.27): the plugged-in car's
        # conversation and plan, the morning questions, and the
        # notifications to send this cycle (not stored)
        self.flow: Optional[dict[str, Any]] = None
        self.morning_day: Optional[str] = None
        self.morning: dict[str, dict[str, Any]] = {}
        self.outbox: list[dict[str, Any]] = []
        self.ctx: dict[str, Any] = {}

    # -- store ---------------------------------------------------------------
    def restore(self, data: Optional[dict[str, Any]]) -> None:
        data = data or {}
        self.overrides = dict(data.get("overrides") or {})
        self.manual = list(data.get("manual") or [])
        self.running = data.get("running") or None
        self.done = {k: int(v) for k, v in (data.get("done") or {}).items()}
        self.flow = data.get("flow") or None
        self.morning_day = data.get("morning_day")
        self.morning = dict(data.get("morning") or {})

    def as_store(self) -> dict[str, Any]:
        return {
            "overrides": self.overrides, "manual": self.manual, "running": self.running, "done": self.done,
            "flow": self.flow, "morning_day": self.morning_day, "morning": self.morning,
        }

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
        victron: Optional[dict[str, Any]] = None,
    ) -> tuple[list[float], dict[str, Any]]:
        """This cycle's EV forecast per hour (hour 0 = the current hour, a
        full-hour value) and the Status sensor's `ev` attribute.
        `conf` holds the EV settings: phases, min_current, max_current,
        predict, cars. `victron` (a Victron EV charging station, as of
        2026.10.27): {connected, status, entry_id, language, notify,
        prices, price_start} - plugging in starts a session and the
        questions on the phone (`outbox`), see _VictronMixin; the
        attribute's `grid_120h` is the car's energy in its grid windows
        (the house battery stays out of it)."""
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

        self.outbox = []
        if victron is not None:
            self.ctx = {**victron, "tz": tz, "cars": cars, "min_a": min_a, "max_a": max_a, "phases": phases}
        sessions = build()
        if victron is not None:
            changed = self._victron_track(
                sessions, bool(victron.get("connected")), victron.get("status"), energy_kwh, now_epoch, typical_kwh
            )
        else:
            changed = self._track_running(sessions, power_w, energy_kwh, now_epoch, phases, min_a, max_a, typical_kwh)
        if changed:
            sessions = build()
        if victron is not None:
            self._victron_plan(now_epoch, hour0, house_net, phases, min_a, max_a)
            self._victron_morning(sessions, now, now_epoch)

        delivered: dict[str, float] = {}
        if self.running and energy_kwh is not None and self.running.get("energy_start") is not None:
            delivered[self.running["id"]] = max(energy_kwh - float(self.running["energy_start"]), 0.0)

        # sessions in start order share the solar surplus: what one takes,
        # the next can't
        total = [0.0] * hours
        grid_total = [0.0] * hours
        net_left = list(house_net)
        out: list[dict[str, Any]] = []
        flow = self.flow if victron is not None else None
        for s in sessions:
            if flow and s["id"] == flow["sid"] and (flow.get("plan") or flow.get("done")):
                part, grid_part, info = self._flow_profile(s, now_epoch, hour0, hours, net_left, phases, min_a, max_a, delivered)
                grid_total = [round(a + b, 4) for a, b in zip(grid_total, grid_part)]
            else:
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
            "grid_120h": grid_total,
        }
        if victron is not None:
            attribute["charger"] = self._charger_attribute(victron, now_epoch, tz)
        return total, attribute

    def _flow_profile(
        self, s: dict[str, Any], now_epoch: int, hour0: int, hours: int, net: list[float],
        phases: int, min_a: float, max_a: float, delivered: dict[str, float],
    ) -> tuple[list[float], list[float], list[dict[str, Any]]]:
        """The plugged-in car's session with a deadline plan: the grid
        windows at the max power, the rest on the sun up to the deadline."""
        flow = self.flow or {}
        got = delivered.get(s["id"], 0.0)
        zero = [0.0] * hours
        if flow.get("done") or not flow.get("plan"):
            return zero, zero, [{**s, "end": now_epoch, "charged_kwh": round(got, 2), "warning": None}]
        plan = flow["plan"]
        p_max = ev.power_kw(max_a, phases)
        left = self.need_left() or 0.0
        grid = evc.grid_profile(plan["windows"], hour0, hours, now_epoch, p_max, min(plan["grid_kwh"], left))
        solar, _ = ev.session_profile(
            {"start": now_epoch, "kwh": plan["solar_kwh"], "mode": ev.MODE_SOLAR}, now_epoch, hour0, hours, net,
            phases, min_a, max_a, int(plan["deadline"]),
        )
        part = [round(a + b, 4) for a, b in zip(grid, solar)]
        info = {
            **s, "end": plan["end"], "charged_kwh": round(got + plan["solar_kwh"] + plan["grid_kwh"], 2),
            "warning": ev.WARNING_SHORT if plan["short_kwh"] > 0.05 else None,
        }
        return part, grid, [info]

    def _charger_attribute(self, victron: dict[str, Any], now_epoch: int, tz: tzinfo) -> dict[str, Any]:
        flow = self.flow
        def iso(epoch: Optional[int]) -> Optional[str]:
            return datetime.fromtimestamp(int(epoch), tz).isoformat() if epoch is not None else None
        out: dict[str, Any] = {
            "connected": bool(victron.get("connected")),
            "status": victron.get("status"),
            "notify": bool(victron.get("notify")),
            "session": None,
        }
        if flow:
            plan = flow.get("plan") or {}
            out["session"] = {
                "id": flow["sid"],
                "car": flow.get("car"),
                "question": flow.get("step"),
                "choice": flow.get("choice"),
                "day": flow.get("day"),
                "deadline": iso(plan.get("deadline") or flow.get("deadline")),
                "need_kwh": flow.get("need_kwh"),
                "left_kwh": round(self.need_left(), 2) if self.need_left() is not None else None,
                "soc": flow.get("soc"),
                "done": bool(flow.get("done")),
                "windows": [[iso(a), iso(b)] for a, b in flow.get("windows") or []],
                "solar_kwh": plan.get("solar_kwh"),
                "grid_kwh": plan.get("grid_kwh"),
                "short_kwh": plan.get("short_kwh"),
                "end": iso(plan.get("end")),
            }
        return out

