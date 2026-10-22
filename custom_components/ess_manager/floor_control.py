"""Floor control (as of 2026.10.23) - ESS Manager heats the floor itself.

The thermostat switches the heat pump on until the room reaches its
setpoint; by then the floor (2-3 hours delay) still holds heat that comes
out afterwards, so the room overshoots. Here the hour-by-hour house model
plans the heat per hour that keeps the room on its wanted temperature
(starting to ease off before the room is there, because it knows the floor
keeps giving), and ESS Manager turns that heat into:

- a return temperature setpoint for the heat pump: the floor gives off heat
  in proportion to (mean water temperature - room), learned from the
  supply / return temperatures, the room and the heat pump's thermal power
  (U, kW per degC; the mean water temperature is the return + half the
  supply-return difference). Little heat needed -> a low setpoint -> a
  better COP;
- heat demand on/off: on when the heat owed (planned minus delivered) is
  worth a run, off once it's delivered - with a minimum run and off time
  for the compressor and hard comfort limits.

Three stages, chosen on the heat pump card and each only once the one
before has proven itself:

- watch: everything as before (the thermostat switches, the return
  setpoint untouched); ESS Manager learns U, the heat pump's power range
  and the supply-return difference, and shows what it would do;
- setpoint: ESS Manager sets the return setpoint, the thermostat still
  switches heat demand - once the floor's emission is learned well enough;
- full: ESS Manager also switches heat demand; the thermostat is only where
  the wanted temperature is set - once the heat pump followed the setpoints
  well for a day's worth of running hours and the house model passed its
  self-check.

The supply and return sensors sit in the heat pump: with the circulation
pump stopped they warm up from the cabinet, so only samples with the pump
running (and settled for SETTLE_S) count. A floor sensor in the screed
(optional) is used instead of the room temperature as the reference once
it's there.

Pure Python (no Home Assistant), unit-tested in tests/test_pipeline.py.
"""
from __future__ import annotations

from typing import Any, Optional

MODE_WATCH = "watch"
MODE_SETPOINT = "setpoint"
MODE_FULL = "full"
MODES = (MODE_WATCH, MODE_SETPOINT, MODE_FULL)
STAGE_OFF = "off"            # not configured
STAGES = (STAGE_OFF, *MODES)

PUMP_RUNNING_PCT = 5.0
SETTLE_S = 600               # the water needs this long to come back from the floor
MIN_RUN_S = 45 * 60          # compressor: at least this long on ...
MIN_OFF_S = 20 * 60          # ... and off
SP_LIMITS = (20.0, 35.0)     # return setpoint, degC (within the entity's own range)
SP_WRITE_EVERY_S = 300
MIN_EMIT_HOURS = 30          # settled running hours to learn the floor from
EMIT_MAX_ERR = 0.25          # mean error of the emission model, share of the power
MIN_RESPONSE_HOURS = 24      # running hours in the setpoint stage ...
RESPONSE_MAX_ERR = 0.30      # ... with the heat pump following the target power this well
COMFORT_BAND = 1.0           # degC from the wanted temperature: heat on / off regardless
COMFORT_HARD = 1.5           # degC: also outside the minimum run / off time
DEBT_CAP_H = 2.0             # heat owed / ahead at most this many hours of maximum power
RECORD_HOURS = 21 * 24
DEFAULT_P_MIN = 1.0          # kW, until learned
DEFAULT_COP = 3.5


def _pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))]


def fit_emission(records: list[dict[str, Any]]) -> dict[str, Any]:
    """U (kW per degC of mean water - reference temperature), the supply-
    return difference, the heat pump's power range, from the settled running
    hours. The reference is the floor sensor when most hours have it, else
    the room. Checked on the newest quarter of the hours (fitted on the
    rest); `ok` when enough hours and a small enough error."""
    rows = [r for r in records if (r.get("run_s") or 0) >= 1800 and r.get("p_th") and r.get("t_sup") is not None
            and r.get("t_ret") is not None]
    slab = len(rows) >= MIN_EMIT_HOURS and sum(1 for r in rows if r.get("t_slab") is not None) >= 0.8 * len(rows)
    pts = []
    for r in rows:
        ref = r.get("t_slab") if slab else r.get("t_room")
        if ref is None:
            continue
        x = (r["t_sup"] + r["t_ret"]) / 2 - ref
        if x > 0.5 and r["p_th"] > 0.1:
            pts.append((x, r["p_th"], r["t_sup"] - r["t_ret"]))
    out: dict[str, Any] = {"n": len(pts), "slab": slab, "ok": False, "u": None, "err": None,
                           "delta": None, "p_min": None, "p_max": None}
    if len(pts) < 8:
        return out

    def fit(ps):
        sxx = sum(x * x for x, _, _ in ps)
        return sum(x * y for x, y, _ in ps) / sxx if sxx > 1e-9 else None

    u = fit(pts)
    if not u or u <= 0:
        return out
    split = int(len(pts) * 0.75)
    train, test = pts[:split], pts[split:]
    u_train = fit(train) if len(train) >= 6 else u
    check = test if len(test) >= 4 and u_train else pts
    uu = u_train if check is test else u
    err = sum(abs(y - uu * x) for x, y, _ in check) / max(sum(y for _, y, _ in check), 1e-9)
    powers = [y for _, y, _ in pts]
    out.update({
        "u": round(u, 4), "err": round(err, 3),
        "delta": round(_pct([d for _, _, d in pts], 0.5), 2),
        "p_min": round(_pct(powers, 0.1), 2), "p_max": round(_pct(powers, 0.9), 2),
    })
    out["ok"] = len(pts) >= MIN_EMIT_HOURS and err <= EMIT_MAX_ERR
    return out


def response_check(records: list[dict[str, Any]], since_ts: Optional[float]) -> dict[str, Any]:
    """How well the heat pump delivered the target power while ESS Manager
    set the return setpoint (settled running hours since `since_ts`)."""
    rows = [r for r in records if since_ts is not None and r["h"] >= since_ts and (r.get("run_s") or 0) >= 1800
            and r.get("p_th") and r.get("p_target")]
    if not rows:
        return {"n": 0, "err": None, "ok": False}
    err = sum(abs(r["p_th"] - r["p_target"]) for r in rows) / max(sum(r["p_target"] for r in rows), 1e-9)
    return {"n": len(rows), "err": round(err, 3), "ok": len(rows) >= MIN_RESPONSE_HOURS and err <= RESPONSE_MAX_ERR}


def return_setpoint(model: dict[str, Any], p_kw: float, t_ref: float, lo: float, hi: float, step: float) -> Optional[float]:
    """The return setpoint that makes the floor give off `p_kw`."""
    u, delta = model.get("u"), model.get("delta")
    if not u or delta is None:
        return None
    sp = t_ref + max(p_kw, 0.0) / u - delta / 2
    sp = min(max(sp, lo), hi)
    if step and step > 0:
        sp = round(round(sp / step) * step, 2)
    return min(max(sp, lo), hi)


def comfort_power(p_kw: float, room: Optional[float], target: Optional[float], p_min: float, p_max: float) -> float:
    """More power when the room lags the wanted temperature: from 0.2 degC
    too cold on, full power at COMFORT_BAND + 0.2 - a safety net for a
    floor that gives off less than learned."""
    p = min(max(p_kw, p_min), max(p_max, p_min))
    if room is None or target is None:
        return p
    gap = target - room - 0.2
    if gap > 0:
        p += gap / COMFORT_BAND * (max(p_max, p_min) - p_min)
    return round(min(p, max(p_max, p_min)), 3)


def control_step(
    st: dict[str, Any], now_ts: float, plan_kw: float, delivered_kw: float, room: Optional[float],
    target: Optional[float], p_min: float, p_max: float,
) -> dict[str, Any]:
    """Heat demand on/off and the target power, from the heat owed (plan -
    delivered, kWh) - `st` = {on, since, debt, last, hour} is kept by the
    caller. On: until the owed heat is delivered (at least MIN_RUN_S, earlier
    when the room is COMFORT_HARD too warm). Off: until the owed heat is
    worth half a minimum run (at least MIN_OFF_S, earlier when the room is
    COMFORT_HARD too cold). The room COMFORT_BAND off the wanted
    temperature switches regardless once the minimum time is over."""
    last = st.get("last") or now_ts
    dt = min(max(now_ts - last, 0.0), 300.0) / 3600.0
    cap = max(p_max, 1.0) * DEBT_CAP_H
    hour = int(now_ts // 3600)
    debt = float(st.get("debt") or 0.0)
    if st.get("hour") is not None and st["hour"] != hour:
        # the plan is worked out again every hour from what was delivered,
        # so only a small rest carries over (enough to gather a run)
        debt = min(max(debt, -p_min * 0.5), p_min * MIN_RUN_S / 3600)
    debt = min(max(debt + (plan_kw - delivered_kw) * dt, -cap), cap)
    on = bool(st.get("on"))
    since = st.get("since") or now_ts
    elapsed = now_ts - since
    reason = "running" if on else "idle"
    warm = room is not None and target is not None and room - target
    if on:
        if warm is not False and warm >= COMFORT_HARD:
            on, reason = False, "too_warm"
        elif elapsed >= MIN_RUN_S and (debt <= 0 or (warm is not False and warm >= COMFORT_BAND)):
            on, reason = False, "too_warm" if (warm is not False and warm >= COMFORT_BAND) else "delivered"
    else:
        if warm is not False and -warm >= COMFORT_HARD and elapsed >= 300:
            on, reason = True, "too_cold"
        elif elapsed >= MIN_OFF_S and (warm is False or warm < COMFORT_BAND):
            if warm is not False and -warm >= COMFORT_BAND:
                on, reason = True, "too_cold"
            elif debt >= p_min * MIN_RUN_S / 3600 * 0.5:
                on, reason = True, "heat_owed"
    if on != bool(st.get("on")):
        since = now_ts
    st.update({"on": on, "since": since, "debt": round(debt, 4), "last": now_ts, "hour": hour})
    p_target = min(max(plan_kw + max(debt, 0.0), p_min), max(p_max, p_min)) if on else 0.0
    return {"on": on, "p_target": round(p_target, 3), "reason": reason, "debt": round(debt, 3)}


def effective_stage(mode: str, emission_ok: bool, response_ok: bool, house_ok: bool, inputs_ok: bool) -> tuple[str, list[str]]:
    """The stage that may run for the chosen mode, and what a higher one waits for."""
    waiting: list[str] = []
    allowed = MODE_WATCH
    if not inputs_ok:
        waiting.append("inputs")
    elif not emission_ok:
        waiting.append("emission")
    else:
        allowed = MODE_SETPOINT
        if not response_ok:
            waiting.append("response")
        if not house_ok:
            waiting.append("house")
        if response_ok and house_ok:
            allowed = MODE_FULL
    order = {m: i for i, m in enumerate(MODES)}
    chosen = mode if mode in order else MODE_WATCH
    return (chosen if order[chosen] <= order[allowed] else allowed), waiting


class FloorRuntime:
    """What floor control keeps between cycles (stored)."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.acc: Optional[dict[str, Any]] = None
        self.pump_since: Optional[float] = None
        self.last_ts: Optional[float] = None
        self.model: dict[str, Any] = {}
        self.model_hour: Optional[int] = None
        self.ctl: dict[str, Any] = {}
        self.stage: str = MODE_WATCH
        self.setpoint_since: Optional[float] = None   # when ESS Manager started setting the return setpoint
        self.baseline_sp: Optional[float] = None      # the return setpoint before it took over
        self.last_sp: Optional[float] = None
        self.last_sp_ts: float = 0.0

    def as_store(self) -> dict[str, Any]:
        return {"records": self.records, "model": self.model, "ctl": self.ctl, "stage": self.stage,
                "setpoint_since": self.setpoint_since, "baseline_sp": self.baseline_sp}

    def restore(self, data: Optional[dict[str, Any]]) -> None:
        if not data:
            return
        self.records = list(data.get("records") or [])
        self.model = dict(data.get("model") or {})
        self.ctl = dict(data.get("ctl") or {})
        self.stage = data.get("stage") if data.get("stage") in MODES else MODE_WATCH
        self.setpoint_since = data.get("setpoint_since")
        self.baseline_sp = data.get("baseline_sp")

    # -- the measurements ------------------------------------------------------------
    def sample(self, now_ts: float, r: dict[str, Optional[float]], p_target: Optional[float], plan_kw: Optional[float]) -> None:
        """One cycle's readings (pump %, t_sup, t_ret, t_room, t_slab, p_th kW,
        sp) into the hour's record; a finished hour into self.records."""
        hour = int(now_ts // 3600) * 3600
        dt = min(max(now_ts - self.last_ts, 0.0), 300.0) if self.last_ts is not None else 0.0
        self.last_ts = now_ts
        if self.acc is not None and self.acc["h"] != hour:
            self._finish()
        if self.acc is None:
            self.acc = {"h": hour, "run_s": 0.0, "all_s": 0.0, "th_kwh": 0.0, "plan_kwh": 0.0}
        a = self.acc
        pump = r.get("pump")
        running = pump is not None and pump >= PUMP_RUNNING_PCT
        if running:
            self.pump_since = self.pump_since or now_ts
        else:
            self.pump_since = None
        a["all_s"] += dt
        if r.get("p_th") is not None:
            a["th_kwh"] += max(r["p_th"], 0.0) * dt / 3600
        if plan_kw is not None:
            a["plan_kwh"] += max(plan_kw, 0.0) * dt / 3600
        if r.get("sp") is not None:
            a["sp_sum"] = a.get("sp_sum", 0.0) + r["sp"] * dt
            a["sp_s"] = a.get("sp_s", 0.0) + dt
        if r.get("t_room") is not None:
            a["room_sum"] = a.get("room_sum", 0.0) + r["t_room"] * dt
            a["room_s"] = a.get("room_s", 0.0) + dt
        if r.get("t_slab") is not None:
            a["slab_all_sum"] = a.get("slab_all_sum", 0.0) + r["t_slab"] * dt
            a["slab_all_s"] = a.get("slab_all_s", 0.0) + dt
        settled = running and now_ts - self.pump_since >= SETTLE_S
        if settled and all(r.get(k) is not None for k in ("t_sup", "t_ret", "p_th")):
            a["run_s"] += dt
            for k in ("t_sup", "t_ret", "p_th", "t_room", "t_slab"):
                if r.get(k) is not None:
                    a[k + "_sum"] = a.get(k + "_sum", 0.0) + r[k] * dt
                    a[k + "_n"] = a.get(k + "_n", 0.0) + dt
            if p_target:
                a["pt_sum"] = a.get("pt_sum", 0.0) + p_target * dt
                a["pt_s"] = a.get("pt_s", 0.0) + dt

    def _finish(self) -> None:
        a = self.acc
        self.acc = None
        if not a or a["all_s"] < 600:
            return
        rec: dict[str, Any] = {"h": a["h"], "run_s": round(a["run_s"]), "th_kwh": round(a["th_kwh"], 3),
                               "plan_kwh": round(a["plan_kwh"], 3)}
        for k in ("t_sup", "t_ret", "p_th", "t_room", "t_slab"):
            if a.get(k + "_n"):
                rec[k] = round(a[k + "_sum"] / a[k + "_n"], 3)
        if a.get("sp_s"):
            rec["sp"] = round(a["sp_sum"] / a["sp_s"], 2)
        if a.get("room_s"):
            rec["room"] = round(a["room_sum"] / a["room_s"], 2)
        if a.get("slab_all_s"):
            rec["slab"] = round(a["slab_all_sum"] / a["slab_all_s"], 2)
        if a.get("pt_s"):
            rec["p_target"] = round(a["pt_sum"] / a["pt_s"], 3)
        self.records.append(rec)
        self.records = self.records[-RECORD_HOURS:]

    def refit(self, now_ts: float) -> None:
        """The floor's emission, again every hour."""
        hour = int(now_ts // 3600)
        if self.model_hour == hour and self.model:
            return
        self.model = fit_emission(self.records)
        self.model_hour = hour

    def cop_ratio(self, heat_hist: dict[str, float]) -> float:
        """Thermal / electric kWh over the hours both are known."""
        th = el = 0.0
        for r in self.records:
            e = heat_hist.get(str(int(r["h"])))
            if e and e > 0.1 and r.get("th_kwh", 0) > 0.2:
                th += r["th_kwh"]
                el += e
        return round(th / el, 2) if el > 1.0 and 1.0 < th / el < 8.0 else DEFAULT_COP
