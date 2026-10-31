"""Prices including taxes (as of 2026.10.44) - the pure part (no Home
Assistant imports, unit-tested in tests/test_pipeline.py).

The price sensor (e.g. Nordpool) gives the bare market price. What a
household really pays per kWh is more: the supplier's purchase fee, the
energy tax and VAT. Two ways to know it, chosen in Configure:

- **Manual**: incl = (price + purchase fee + energy tax) x (1 + VAT).
- **Supplier sensor**: a sensor whose state is the supplier's current price
  including taxes (per quarter or per hour). Every quarter its value is
  noted next to the bare price of that quarter; from the last WINDOW_DAYS
  a straight line incl = a x price + b is fitted (least squares). It only
  counts once there are MIN_SAMPLES quarters with at least MIN_SPREAD
  between the cheapest and dearest price (with flat prices a and b can't be
  told apart), the fit is close (RMS <= MAX_RMS) and a is plausible
  (A_RANGE). A change of tax or fee shows as JUMP_N quarters in a row that
  are more than JUMP off the line, all to the same side: the old quarters
  are dropped and the line is moved by the jump (same a) until there's
  enough data for a new fit.

Selling is always at the bare price (the price sensor's own, no transport):
as from 2027, when net metering (salderen) ends in the Netherlands, selling
no longer gets the energy tax and VAT back. The planning already counts
that way (2026.10.44).

The transport tariff (transport.py) stays separate: the buy price incl is
the line applied to price + transport.
"""
from __future__ import annotations

import math
from typing import Any, Optional

MODE_NONE = "none"
MODE_MANUAL = "manual"
MODE_SENSOR = "sensor"
MODES = (MODE_NONE, MODE_MANUAL, MODE_SENSOR)

WINDOW_DAYS = 7
MIN_SAMPLES = 96
MIN_SPREAD = 0.03
MAX_RMS = 0.005
A_RANGE = (0.8, 1.6)
JUMP = 0.01
JUMP_N = 4
SHIFT_MIN = 4


def to_eur_per_kwh(value: Optional[float], unit: Optional[str]) -> Optional[float]:
    """A supplier's price in €/kWh: a unit in cents (ct/kWh, c/kWh) / 100."""
    if value is None or not math.isfinite(value):
        return None
    u = (unit or "").lower().replace(" ", "")
    if u.startswith("ct") or u.startswith("c/") or "cent" in u:
        return value / 100.0
    return value


def fit_line(samples: list[list[float]]) -> Optional[dict[str, float]]:
    """Least-squares a, b for incl = a x price + b, with its RMS error and
    the price spread; None with fewer than two different prices."""
    n = len(samples)
    if n < 2:
        return None
    xs = [s[1] for s in samples]
    ys = [s[2] for s in samples]
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b = my - a * mx
    rms = math.sqrt(sum((y - a * x - b) ** 2 for x, y in zip(xs, ys)) / n)
    return {"a": a, "b": b, "rms": rms, "spread": max(xs) - min(xs), "n": n}


def hourly(samples: list[list[float]]) -> list[list[float]]:
    """The quarters averaged per hour - for a supplier with hourly prices
    next to a price sensor with quarters."""
    groups: dict[int, list[list[float]]] = {}
    for s in samples:
        groups.setdefault(int(s[0] // 3600), []).append(s)
    return [[h * 3600.0, sum(q[1] for q in g) / len(g), sum(q[2] for q in g) / len(g)]
            for h, g in sorted(groups.items()) if len(g) == 4]


class PriceModel:
    """The learned line for a supplier sensor, and the quarters behind it."""

    def __init__(self) -> None:
        self.samples: list[list[float]] = []   # [unit start (epoch), price, incl]
        self.model: Optional[dict[str, Any]] = None
        self.reason: str = "learning"

    # -- storage -----------------------------------------------------------
    def as_store(self) -> dict[str, Any]:
        return {"samples": self.samples, "model": self.model}

    def restore(self, data: Optional[dict[str, Any]]) -> None:
        if not isinstance(data, dict):
            return
        self.samples = [list(s) for s in data.get("samples") or [] if isinstance(s, (list, tuple)) and len(s) == 3]
        model = data.get("model")
        self.model = model if isinstance(model, dict) and "a" in model and "b" in model else None
        self.reason = "ready" if self.model else "learning"

    def reset(self) -> None:
        self.samples = []
        self.model = None
        self.reason = "learning"

    # -- learning ----------------------------------------------------------
    def add(self, unit_ts: float, price: float, incl: float) -> None:
        """One quarter: the bare price and the supplier's price incl."""
        if self.samples and self.samples[-1][0] >= unit_ts:
            return
        self.samples.append([float(unit_ts), round(float(price), 6), round(float(incl), 6)])
        cutoff = unit_ts - WINDOW_DAYS * 86400
        self.samples = [s for s in self.samples if s[0] > cutoff]
        if self.model is not None and len(self.samples) >= JUMP_N:
            last = self.samples[-JUMP_N:]
            off = [s[2] - (self.model["a"] * s[1] + self.model["b"]) for s in last]
            if all(o > JUMP for o in off) or all(o < -JUMP for o in off):
                # a tax or fee changed: start over from these quarters
                self.samples = last
                self.model = {**self.model, "b": self.model["b"] + sum(off) / len(off),
                              "since": unit_ts, "shifted": True}
        self.refit(unit_ts)

    def refit(self, now_ts: float) -> None:
        fit = fit_line(self.samples)
        hour_fit = fit_line(hourly(self.samples))
        if fit and hour_fit and hour_fit["rms"] < fit["rms"] / 2:
            # a supplier with hourly prices: compare hour averages
            fit = {**hour_fit, "n": fit["n"], "resolution": "hour"}
        if fit and fit["n"] >= MIN_SAMPLES and fit["spread"] >= MIN_SPREAD:
            if A_RANGE[0] <= fit["a"] <= A_RANGE[1] and fit["rms"] <= MAX_RMS:
                since = self.model.get("since") if self.model and not self.model.get("shifted") else now_ts
                self.model = {"a": round(fit["a"], 5), "b": round(fit["b"], 5), "rms": round(fit["rms"], 5),
                              "n": fit["n"], "since": since, "shifted": False,
                              "resolution": fit.get("resolution", "quarter")}
                self.reason = "ready"
                return
            self.reason = "poor_fit"
        elif self.model is not None and len(self.samples) >= SHIFT_MIN:
            # not enough for a new line yet: keep a, follow b
            a = self.model["a"]
            b = sum(s[2] - a * s[1] for s in self.samples) / len(self.samples)
            self.model = {**self.model, "b": round(b, 5)}
            self.reason = "ready"
            return
        elif fit and fit["n"] >= MIN_SAMPLES:
            self.reason = "flat_prices"
        else:
            self.reason = "learning"
        if self.model is not None:
            self.reason = "ready"

    def attribute(self) -> dict[str, Any]:
        """For the cards and the diagnostics."""
        fit = fit_line(self.samples)
        return {
            "status": self.reason,
            "a": self.model["a"] if self.model else None,
            "b": self.model["b"] if self.model else None,
            "rms": self.model.get("rms") if self.model else None,
            "since": self.model.get("since") if self.model else None,
            "resolution": self.model.get("resolution") if self.model else None,
            "samples": len(self.samples),
            "needed": MIN_SAMPLES,
            "spread": round(fit["spread"], 4) if fit else None,
        }


def incl_line(mode: str, model: Optional[dict[str, Any]], manual: dict[str, float]) -> Optional[tuple[float, float]]:
    """(a, b) of incl = a x price + b for the chosen way; None when there's
    none (yet)."""
    if mode == MODE_SENSOR:
        return (float(model["a"]), float(model["b"])) if model else None
    if mode == MODE_MANUAL:
        vat = 1.0 + float(manual.get("vat_percent") or 0.0) / 100.0
        fee = float(manual.get("purchase_fee") or 0.0) + float(manual.get("energy_tax") or 0.0)
        return vat, fee * vat
    return None


def apply_line(prices: list[Optional[float]], line: tuple[float, float]) -> list[Optional[float]]:
    a, b = line
    return [round(a * p + b, 5) if p is not None else None for p in prices]
