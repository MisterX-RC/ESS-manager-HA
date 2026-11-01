"""What the battery saves (as of 2026.11.0) - no Home Assistant imports, the
recorder is reached through the fetch functions the coordinator hands in
(unit-tested in tests/test_pipeline.py).

Per quarter it compares two households with the same usage and the same
sun: the real one, and the same one without a battery. Without a battery
whatever the battery took or gave would have gone through the grid, so per
5-minute slot:

    net without = export - import + charged - discharged   (kWh, + = to the grid)

- with: import x buy price, export x sell price (what the meters measured)
- without: max(-net, 0) x buy price, max(net, 0) x sell price

The buy price is price + transport (transport.py), made incl taxes with the
line of price_incl.py; the sell price is the bare price (as from 2027).
Because that line is straight, a day is stored as raw sums - kWh and
kWh x price - and the line is put on when it's shown: a newer line (a tax
change, the model learned) needs no recalculation.

Data: the Energy dashboard's grid import / export and battery charged /
discharged statistics in 5-minute steps (the recorder's short-term
statistics - kept as long as the recorder keeps its history, `keep_days`,
10 by default), and the price sensor's recorded states for the price of
each quarter. Every night yesterday is added; at the start the days the
recorder still has are filled in. Today is worked out every quarter.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable, Optional

SLOT = 300
QUARTER = 900
KEEP_DAYS = 400
MIN_COVERAGE = 0.9
# raw sums per day / quarter: kWh and kWh x price, with and without battery
RAW = ("iw", "iwp", "ew", "ewp", "io", "iop", "eo", "eop")

Stats = dict[str, dict[int, float]]


def quarter_prices(states: list[tuple[float, float]], day_start: float, n: int) -> list[Optional[float]]:
    """The price of each quarter of a day from the price sensor's recorded
    states [(epoch, price)], oldest first: the last one at most 2 minutes
    after the quarter began (a sensor changes a moment after the quarter)."""
    out: list[Optional[float]] = []
    j = -1
    for q in range(n):
        t = day_start + q * QUARTER + 120
        while j + 1 < len(states) and states[j + 1][0] <= t:
            j += 1
        out.append(states[j][1] if j >= 0 else None)
    return out


def _sum_ids(stats: Stats, ids: list[str]) -> dict[int, float]:
    out: dict[int, float] = {}
    for sid in ids:
        for slot, v in (stats.get(sid) or {}).items():
            out[slot] = out.get(slot, 0.0) + v
    return out


def day_rows(day_start: float, n_quarters: int, until: float, stats: Stats, sources: dict[str, list[str]],
             buy: list[Optional[float]], sell: list[Optional[float]]) -> Optional[list[list[float]]]:
    """The raw sums (RAW) per quarter of one day, up to `until`; None when
    the statistics cover less than MIN_COVERAGE of the slots, or energy
    fell in a quarter without a price."""
    imp = _sum_ids(stats, sources.get("import") or [])
    exp = _sum_ids(stats, sources.get("export") or [])
    ch = _sum_ids(stats, sources.get("battery_charge") or [])
    dis = _sum_ids(stats, sources.get("battery_discharge") or [])
    slots = [int(day_start + k * SLOT) for k in range(n_quarters * 3) if day_start + (k + 1) * SLOT <= until + 1]
    if not slots:
        return None
    covered_grid = sum(1 for s in slots if s in imp)
    covered_batt = sum(1 for s in slots if s in ch or s in dis)
    if covered_grid < MIN_COVERAGE * len(slots) or covered_batt < MIN_COVERAGE * len(slots):
        return None
    rows = [[0.0] * len(RAW) for _ in range(n_quarters)]
    for s in slots:
        q = int((s - day_start) // QUARTER)
        i, e = imp.get(s, 0.0), exp.get(s, 0.0)
        c, d = ch.get(s, 0.0), dis.get(s, 0.0)
        if not (i or e or c or d):
            continue
        b = buy[q] if q < len(buy) else None
        p = sell[q] if q < len(sell) else None
        if b is None or p is None:
            return None
        net = e - i + c - d
        io, eo = max(-net, 0.0), max(net, 0.0)
        r = rows[q]
        r[0] += i
        r[1] += i * b
        r[2] += e
        r[3] += e * p
        r[4] += io
        r[5] += io * b
        r[6] += eo
        r[7] += eo * p
    return rows


def total(rows: list[list[float]]) -> list[float]:
    return [round(sum(r[k] for r in rows), 4) for k in range(len(RAW))]


def priced(raw: list[float], line: tuple[float, float]) -> dict[str, float]:
    """A day's (or quarter's) raw sums with the buy line put on: kWh and EUR
    bought / sold, with and without battery, and the saving."""
    a, b = line
    out = {
        "import_with": raw[0], "buy_with": a * raw[1] + b * raw[0],
        "export_with": raw[2], "sell_with": raw[3],
        "import_without": raw[4], "buy_without": a * raw[5] + b * raw[4],
        "export_without": raw[6], "sell_without": raw[7],
    }
    out["cost_with"] = out["buy_with"] - out["sell_with"]
    out["cost_without"] = out["buy_without"] - out["sell_without"]
    out["saving"] = out["cost_without"] - out["cost_with"]
    return {k: round(v, 4) for k, v in out.items()}


FetchStats = Callable[[list[str], datetime, datetime], Awaitable[Stats]]
FetchPrices = Callable[[datetime, datetime], Awaitable[list[tuple[float, float]]]]
BuyOf = Callable[[list[Optional[float]], datetime], list[Optional[float]]]


class SavingsData:
    """The stored days and today so far."""

    def __init__(self) -> None:
        self.days: dict[str, list[float]] = {}
        self.today: Optional[dict[str, Any]] = None
        self.filled_for: Optional[str] = None
        self.today_at = 0.0
        self.status = "waiting"
        self.history_days: Optional[int] = None
        self.skipped: list[str] = []

    def as_store(self) -> dict[str, Any]:
        return {"days": self.days}

    def restore(self, data: Optional[dict[str, Any]]) -> None:
        if isinstance(data, dict) and isinstance(data.get("days"), dict):
            self.days = {k: list(v) for k, v in data["days"].items() if isinstance(v, list) and len(v) == len(RAW)}

    @staticmethod
    def _day_start(d: date, tz) -> datetime:
        return datetime.combine(d, time(0), tzinfo=tz)

    async def async_fill(self, now: datetime, keep_days: int, sources: dict[str, list[str]],
                         fetch_stats: FetchStats, fetch_prices: FetchPrices, buy_of: BuyOf) -> bool:
        """Add the finished days the recorder still has (the last `keep_days`)
        that aren't stored yet. True when something was added."""
        self.history_days = keep_days
        today = now.date()
        wanted = [today - timedelta(days=k) for k in range(max(keep_days, 1), 0, -1)]
        missing = [d for d in wanted if d.isoformat() not in self.days]
        self.filled_for = today.isoformat()
        if not missing:
            return False
        tz = now.tzinfo
        start = self._day_start(missing[0], tz)
        end = self._day_start(today, tz)
        ids = [i for k in ("import", "export", "battery_charge", "battery_discharge") for i in sources.get(k) or []]
        stats = await fetch_stats(ids, start, end)
        states = await fetch_prices(start - timedelta(hours=1), end)
        added = False
        self.skipped = []
        for d in missing:
            ds = self._day_start(d, tz)
            de = self._day_start(d + timedelta(days=1), tz)
            n = int(round((de - ds).total_seconds() / QUARTER))
            raw_prices = quarter_prices(states, ds.timestamp(), n)
            rows = day_rows(ds.timestamp(), n, de.timestamp(), stats, sources, buy_of(raw_prices, ds), raw_prices)
            if rows is None:
                self.skipped.append(d.isoformat())
                continue
            self.days[d.isoformat()] = total(rows)
            added = True
        cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
        self.days = {k: v for k, v in sorted(self.days.items()) if k >= cutoff}
        return added

    async def async_today(self, now: datetime, sources: dict[str, list[str]], fetch_stats: FetchStats,
                          prices_today: list[float], buy_of: BuyOf) -> None:
        """Today so far, per quarter (worked out at most once a quarter)."""
        tz = now.tzinfo
        ds = self._day_start(now.date(), tz)
        ids = [i for k in ("import", "export", "battery_charge", "battery_discharge") for i in sources.get(k) or []]
        stats = await fetch_stats(ids, ds, now)
        n = len(prices_today) or 96
        rows = day_rows(ds.timestamp(), n, now.timestamp(), stats, sources, buy_of(list(prices_today), ds), list(prices_today))
        self.today = {"date": now.date().isoformat(), "rows": rows} if rows is not None else None
        self.today_at = now.timestamp()

    def attribute(self, line: tuple[float, float]) -> dict[str, Any]:
        """For the savings card: per day [date, kWh bought, EUR bought, kWh
        sold, EUR sold] with battery and then without, today's quarters
        (the saving per quarter, EUR) and its totals."""
        def row(day: str, raw: list[float]) -> list[Any]:
            p = priced(raw, line)
            return [day, p["import_with"], round(p["buy_with"], 3), p["export_with"], round(p["sell_with"], 3),
                    p["import_without"], round(p["buy_without"], 3), p["export_without"], round(p["sell_without"], 3)]

        today = None
        if self.today and self.today.get("rows"):
            rows = self.today["rows"]
            today = {"row": row(self.today["date"], total(rows)),
                     "quarters": [round(priced(r, line)["saving"], 4) for r in rows]}
        return {
            "status": self.status,
            "days": [row(d, raw) for d, raw in sorted(self.days.items())],
            "today": today,
            "history_days": self.history_days,
            "skipped": self.skipped,
            "line": [round(line[0], 5), round(line[1], 5)],
        }
