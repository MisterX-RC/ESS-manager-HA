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

The battery's stock (as of 2026.11.8): what's in it is valued at what it
cost to put in - grid charging at the buy price incl of that quarter,
solar at the bare sell price of that quarter (what it would have brought
in without the battery). What comes out goes at the average of what's in
it: E kWh (the battery's own state of charge x capacity) worth W. A day's
saving gets the change of W: a day the battery is filled cheaply comes out
at about 0, the day it gives that energy back gets the price saved minus
what it cost. Losses come out of W without energy for them (the state of
charge rises less than was charged, falls more than was given), so they
count too. W is kept as a = line, b = fixed and plain EUR parts, so the
line incl taxes is put on when shown, like the rest.

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
RAW = ("iw", "iwp", "ew", "ewp", "io", "iop", "eo", "eop", "sp", "sg", "ss")
# the stock's change (as of 2026.11.8): sp kWh x bare buy price, sg kWh
# (the fixed part of the line), ss EUR (solar at the sell price) - see priced
STOCK = ("e", "xp", "xg", "xs")
# a state of charge that moves less than this without charging or giving
# is taken as noise (kWh)
SOC_NOISE_KWH = 0.3

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


def init_stock(e_kwh: float, buy: list[Optional[float]]) -> dict[str, float]:
    """A stock to start from (as of 2026.11.8): what's in the battery at the
    day's average buy price - nothing is known about how it got there; after
    a few charges it's gone."""
    known = [b for b in buy if b is not None]
    avg = sum(known) / len(known) if known else 0.0
    return {"e": float(e_kwh), "xp": float(e_kwh) * avg, "xg": float(e_kwh), "xs": 0.0}


def stock_step(stock: dict[str, float], c: float, d: float, i: float, b: Optional[float], p: Optional[float],
               soc_kwh: Optional[float], ce: float, de: float) -> None:
    """One 5-minute slot of the stock: charged c (from the grid as far as
    the grid gave as much, min(c, import), the rest solar) goes in at what
    it cost; then the stock follows the state of charge, and what went out
    of it takes its share of the value."""
    g = min(c, max(i, 0.0))
    if c > 0:
        stock["xp"] += g * (b or 0.0)
        stock["xg"] += g
        stock["xs"] += (c - g) * (p or 0.0)
    e_in = stock["e"] + c * ce
    if soc_kwh is not None:
        e_new = soc_kwh
        if c <= 0 and d <= 0 and abs(e_new - stock["e"]) < SOC_NOISE_KWH:
            e_new = stock["e"]
    else:
        e_new = e_in - d / max(de, 0.01)
    e_new = max(e_new, 0.0)
    out = e_in - e_new
    if out > 0 and e_in > 0:
        keep = max(1.0 - out / e_in, 0.0)
        stock["xp"] *= keep
        stock["xg"] *= keep
        stock["xs"] *= keep
    stock["e"] = e_new


def day_rows(day_start: float, n_quarters: int, until: float, stats: Stats, sources: dict[str, list[str]],
             buy: list[Optional[float]], sell: list[Optional[float]], why: Optional[list[str]] = None,
             soc: Optional[dict[int, float]] = None, stock: Optional[dict[str, Any]] = None,
             eff: tuple[float, float] = (1.0, 1.0)) -> Optional[list[list[float]]]:
    """The raw sums (RAW) per quarter of one day, up to `until`; None when
    the statistics cover less than MIN_COVERAGE of the slots, or energy
    fell in a quarter without a price - `why` gets the reason then.
    `soc` (kWh per slot) and `stock` (as of 2026.11.8): the battery's stock
    is carried through the day (changed in place; started from the first
    state of charge when it's empty) and its change per quarter goes in
    the rows."""
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
        if why is not None:
            why.append(f"statistics cover {covered_grid}/{len(slots)} slots (grid), {covered_batt}/{len(slots)} (battery)")
        return None
    rows = [[0.0] * len(RAW) for _ in range(n_quarters)]
    soc = soc or {}
    if stock is not None and not stock and soc:
        first = next((soc[s] for s in slots if s in soc), None)
        if first is not None:
            stock.update(init_stock(first, buy))
    track = stock is not None and bool(stock)
    work = dict(stock) if track else None
    ce, de = eff
    for s in slots:
        q = int((s - day_start) // QUARTER)
        i, e = imp.get(s, 0.0), exp.get(s, 0.0)
        c, d = ch.get(s, 0.0), dis.get(s, 0.0)
        b = buy[q] if q < len(buy) else None
        p = sell[q] if q < len(sell) else None
        if track:
            before = (work["xp"], work["xg"], work["xs"])
            stock_step(work, c, d, i, b, p, soc.get(s), ce, de)
            r = rows[q]
            r[8] += work["xp"] - before[0]
            r[9] += work["xg"] - before[1]
            r[10] += work["xs"] - before[2]
        if not (i or e or c or d):
            continue
        if b is None or p is None:
            if why is not None:
                why.append(f"no price for quarter {q}")
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
    if track:
        stock.update(work)
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
        # (as of 2026.11.8) the battery's stock went up (+) or down by this
        "stock": (a * raw[8] + b * raw[9] + raw[10]) if len(raw) >= 11 else 0.0,
    }
    out["cost_with"] = out["buy_with"] - out["sell_with"]
    out["cost_without"] = out["buy_without"] - out["sell_without"]
    out["saving"] = out["cost_without"] - out["cost_with"] + out["stock"]
    return {k: round(v, 4) for k, v in out.items()}


FetchStats = Callable[[list[str], datetime, datetime], Awaitable[Stats]]
FetchPrices = Callable[[datetime, datetime], Awaitable[list[tuple[float, float]]]]
FetchSoc = Callable[[datetime, datetime], Awaitable[dict[int, float]]]
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
        self.skipped: dict[str, str] = {}
        # the price sensor's quarter prices per day, kept by the integration
        # itself (as of 2026.11.1): a price sensor left out of the recorder
        # (often done for its big attributes) has no history to look back on
        self.prices: dict[str, list[float]] = {}
        # the battery's stock at the end of `date` (as of 2026.11.8), and
        # the days stored before there was a stock (worked out again while
        # the recorder still has them)
        self.stock: Optional[dict[str, Any]] = None
        self.legacy: set[str] = set()
        self.live_stock: Optional[dict[str, Any]] = None

    def as_store(self) -> dict[str, Any]:
        return {"days": self.days, "prices": self.prices, "stock": self.stock}

    def restore(self, data: Optional[dict[str, Any]]) -> None:
        if isinstance(data, dict) and isinstance(data.get("days"), dict):
            self.days = {}
            for k, v in data["days"].items():
                if isinstance(v, list) and len(v) == len(RAW):
                    self.days[k] = list(v)
                elif isinstance(v, list) and len(v) == 8:
                    # before 2026.11.8: no stock - kept, and worked out again when it can be
                    self.days[k] = list(v) + [0.0, 0.0, 0.0]
                    self.legacy.add(k)
        if isinstance(data, dict) and isinstance(data.get("stock"), dict) and all(k in data["stock"] for k in STOCK):
            self.stock = dict(data["stock"])
        if isinstance(data, dict) and isinstance(data.get("prices"), dict):
            self.prices = {k: list(v) for k, v in data["prices"].items() if isinstance(v, list)}

    def note_prices(self, day: str, prices: list[float]) -> bool:
        """Keep today's price list (the last 14 days). True when it's new
        or changed - then it's worth storing."""
        if not prices or self.prices.get(day) == list(prices):
            return False
        self.prices[day] = list(prices)
        for k in sorted(self.prices)[:-14]:
            del self.prices[k]
        return True

    @staticmethod
    def _day_start(d: date, tz) -> datetime:
        return datetime.combine(d, time(0), tzinfo=tz)

    async def async_fill(self, now: datetime, keep_days: int, sources: dict[str, list[str]],
                         fetch_stats: FetchStats, fetch_prices: FetchPrices, buy_of: BuyOf,
                         fetch_soc: Optional[FetchSoc] = None, eff: tuple[float, float] = (1.0, 1.0)) -> bool:
        """Add the finished days the recorder still has (the last `keep_days`)
        that aren't stored yet. True when something was added. As of
        2026.11.8 the battery's stock runs through them: from the first day
        missing on every day up to yesterday is worked out (in order), from
        the stock the day before ended with when that's known."""
        self.history_days = keep_days
        today = now.date()
        wanted = [today - timedelta(days=k) for k in range(max(keep_days, 1), 0, -1)]
        first = next((d for d in wanted if d.isoformat() not in self.days or d.isoformat() in self.legacy), None)
        missing = [d for d in wanted if first is not None and d >= first]
        self.filled_for = today.isoformat()
        if not missing:
            return False
        tz = now.tzinfo
        start = self._day_start(missing[0], tz)
        end = self._day_start(today, tz)
        ids = [i for k in ("import", "export", "battery_charge", "battery_discharge") for i in sources.get(k) or []]
        stats = await fetch_stats(ids, start, end)
        states = await fetch_prices(start - timedelta(hours=1), end)
        socs = await fetch_soc(start, end) if fetch_soc is not None else {}
        before = (missing[0] - timedelta(days=1)).isoformat()
        stock: Optional[dict[str, Any]] = (
            {k: self.stock[k] for k in STOCK} if self.stock and self.stock.get("date") == before else {}
        ) if fetch_soc is not None else None
        added = False
        self.skipped = {}
        for d in missing:
            ds = self._day_start(d, tz)
            de = self._day_start(d + timedelta(days=1), tz)
            n = int(round((de - ds).total_seconds() / QUARTER))
            kept = self.prices.get(d.isoformat())
            raw_prices = list(kept) if kept and len(kept) == n else quarter_prices(states, ds.timestamp(), n)
            why: list[str] = []
            rows = day_rows(ds.timestamp(), n, de.timestamp(), stats, sources, buy_of(raw_prices, ds), raw_prices, why,
                            socs, stock, eff)
            if rows is None:
                self.skipped[d.isoformat()] = why[0] if why else "nothing measured"
                if stock is not None:
                    stock = {}    # the chain is broken: start again from the next day's state of charge
                continue
            self.days[d.isoformat()] = total(rows)
            self.legacy.discard(d.isoformat())
            added = True
            if stock:
                self.stock = {**{k: round(stock[k], 6) for k in STOCK}, "date": d.isoformat()}
        cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
        self.days = {k: v for k, v in sorted(self.days.items()) if k >= cutoff}
        return added

    async def async_today(self, now: datetime, sources: dict[str, list[str]], fetch_stats: FetchStats,
                          prices_today: list[float], buy_of: BuyOf,
                          fetch_soc: Optional[FetchSoc] = None, eff: tuple[float, float] = (1.0, 1.0)) -> None:
        """Today so far, per quarter (worked out at most once a quarter)."""
        tz = now.tzinfo
        ds = self._day_start(now.date(), tz)
        ids = [i for k in ("import", "export", "battery_charge", "battery_discharge") for i in sources.get(k) or []]
        stats = await fetch_stats(ids, ds, now)
        n = len(prices_today) or 96
        stock: Optional[dict[str, Any]] = None
        socs: dict[int, float] = {}
        if fetch_soc is not None:
            socs = await fetch_soc(ds, now)
            yesterday = (now.date() - timedelta(days=1)).isoformat()
            stock = {k: self.stock[k] for k in STOCK} if self.stock and self.stock.get("date") == yesterday else {}
        rows = day_rows(ds.timestamp(), n, now.timestamp(), stats, sources, buy_of(list(prices_today), ds), list(prices_today),
                        None, socs, stock, eff)
        self.live_stock = dict(stock) if stock else (dict(self.stock) if self.stock else None)
        self.today = {"date": now.date().isoformat(), "rows": rows} if rows is not None else None
        self.today_at = now.timestamp()

    def attribute(self, line: tuple[float, float]) -> dict[str, Any]:
        """For the savings card: per day [date, kWh bought, EUR bought, kWh
        sold, EUR sold] with battery and then without, today's quarters
        (the saving per quarter, EUR) and its totals."""
        def row(day: str, raw: list[float]) -> list[Any]:
            p = priced(raw, line)
            return [day, p["import_with"], round(p["buy_with"], 3), p["export_with"], round(p["sell_with"], 3),
                    p["import_without"], round(p["buy_without"], 3), p["export_without"], round(p["sell_without"], 3),
                    round(p["stock"], 3)]

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
            # (as of 2026.11.8) what's in the battery now and what it cost
            "stock": self._stock_attr(line),
        }

    def _stock_attr(self, line: tuple[float, float]) -> Optional[dict[str, float]]:
        st = self.live_stock or self.stock
        if not st or not all(k in st for k in STOCK):
            return None
        value = line[0] * st["xp"] + line[1] * st["xg"] + st["xs"]
        e = float(st["e"])
        return {"kwh": round(e, 2), "value": round(value, 2), "avg": round(value / e, 4) if e > 0.05 else None}
