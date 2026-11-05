"""Fetches raw hourly long-term statistics from Home Assistant's recorder.

This is the only Home Assistant-dependent half of the statistics-based usage
forecast feature - it just pulls data out of the recorder and hands it to
usage_forecast.py (pure Python, unit-tested) to do the actual math. Kept
deliberately thin so there's as little here as possible that can't be
exercised outside a running Home Assistant instance.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


async def async_fetch_hourly_sums(
    hass: HomeAssistant,
    entity_ids: Iterable[str],
    start: datetime,
    end: datetime,
) -> dict[str, dict[int, float]]:
    """Return, for each entity, its hourly cumulative 'sum' statistic across
    [start, end], keyed by the UTC epoch-second of each hour's start.

    Uses Home Assistant's own statistics API (statistics_during_period)
    rather than a raw SQL query against the recorder database, so this
    works regardless of which database backend the recorder actually uses
    (SQLite, MariaDB/MySQL, Postgres, ...) - the original hand-written
    version of this forecast used MySQL-specific SQL syntax that wasn't
    portable. This is a synchronous recorder/database call under the hood,
    so it's dispatched through the recorder's own executor.
    """
    ids = {entity_id for entity_id in entity_ids if entity_id}
    if not ids:
        return {}

    recorder = get_instance(hass)
    # units: ask the recorder to convert every energy statistic to kWh on
    # the way out. Without this, values come back in each statistic's own
    # native unit - a Wh or MWh meter (both allowed by HA's Energy
    # dashboard) would be read 1000x too high/low, since everything
    # downstream (the energy-balance identity, the battery forecast) is kWh.
    raw = await recorder.async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        end,
        ids,
        "hour",
        {"energy": "kWh"},
        {"sum"},
    )

    result: dict[str, dict[int, float]] = {}
    for entity_id, rows in raw.items():
        series: dict[int, float] = {}
        for row in rows:
            value = row.get("sum")
            if value is None:
                continue
            row_start = row.get("start")
            if isinstance(row_start, (int, float)):
                # Some Home Assistant versions return 'start' as an epoch
                # float already, to avoid constructing a datetime per row.
                epoch = int(row_start)
            else:
                epoch = int(dt_util.as_utc(row_start).timestamp())
            series[epoch] = float(value)
        result[entity_id] = series
    return result


async def async_fetch_hourly_means(
    hass: HomeAssistant,
    entity_ids: Iterable[str],
    start: datetime,
    end: datetime,
    field: str = "mean",
) -> dict[str, dict[int, float]]:
    """Like async_fetch_hourly_sums, but each hour's MEAN (temperature, wind
    speed) - converted to degC and m/s (as of 2026.10.16, the heat pump
    model). `field` "min" / "max" gives that instead (as of 2026.10.38: the
    COP sensor's minimum - an hour the heat pump ran throughout)."""
    ids = {entity_id for entity_id in entity_ids if entity_id}
    if not ids:
        return {}
    raw = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        end,
        ids,
        "hour",
        {"temperature": "\u00b0C", "speed": "m/s"},
        {field},
    )
    result: dict[str, dict[int, float]] = {}
    for entity_id, rows in raw.items():
        series: dict[int, float] = {}
        for row in rows:
            value = row.get(field)
            if value is None:
                continue
            row_start = row.get("start")
            epoch = int(row_start) if isinstance(row_start, (int, float)) else int(dt_util.as_utc(row_start).timestamp())
            series[epoch] = float(value)
        result[entity_id] = series
    return result


async def async_last_recorded_state(hass: HomeAssistant, entity_id: str, wanted: Iterable[str]) -> str | None:
    """The most recent recorded state of `entity_id` that is one of
    `wanted` (compared lower-case) - skipping unavailable/unknown, which an
    entity briefly is around a restart. None when the recorder has none (or
    can't be read). Used once, to carry the solar mode over the update that
    starts storing it (2026.10.8)."""
    from homeassistant.components.recorder.history import get_last_state_changes

    wanted_lower = {w.lower() for w in wanted}
    changes = await get_instance(hass).async_add_executor_job(get_last_state_changes, hass, 10, entity_id)
    for state in reversed(changes.get(entity_id.lower(), [])):
        if state.state.lower() in wanted_lower:
            return state.state.lower()
    return None


async def async_fetch_state_changes(hass: HomeAssistant, entity_id: str, start, end) -> list:
    """The recorded states of `entity_id` (with attributes) between start and
    end, the state at `start` first - the recorder keeps these about 10 days.
    Used for a thermostat's heat demand (2026.10.17)."""
    from homeassistant.components.recorder.history import state_changes_during_period

    changes = await get_instance(hass).async_add_executor_job(
        lambda: state_changes_during_period(
            hass, start, end, entity_id, no_attributes=False, include_start_time_state=True
        )
    )
    return list(changes.get(entity_id.lower(), []))


async def async_fetch_5min_changes(hass: HomeAssistant, ids: Iterable[str], start: datetime, end: datetime) -> dict[str, dict[int, float]]:
    """Each statistic's energy per 5-minute slot (kWh, the recorder's
    short-term statistics' `change`) between start and end, keyed by the
    slot's start (epoch) - for the savings card (2026.11.0). The recorder
    keeps these as long as its history (`keep_days`)."""
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    raw = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start, end, wanted, "5minute", {"energy": "kWh"}, {"change"}
    )
    result: dict[str, dict[int, float]] = {}
    for sid, rows in raw.items():
        series: dict[int, float] = {}
        for row in rows:
            value = row.get("change")
            if value is None:
                continue
            row_start = row.get("start")
            epoch = int(row_start) if isinstance(row_start, (int, float)) else int(dt_util.as_utc(row_start).timestamp())
            series[epoch] = float(value)
        result[sid] = series
    return result


async def async_fetch_5min_soc(hass: HomeAssistant, statistic_id: str, start: datetime, end: datetime,
                               capacity_kwh: float) -> dict[int, float]:
    """The battery's content per 5-minute slot (kWh: the state of charge's
    short-term statistics' `mean` x capacity), keyed by the slot's start -
    for the savings card's battery stock (2026.11.8). Empty when the state
    of charge sensor has no statistics (no state_class)."""
    if not statistic_id:
        return {}
    raw = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start, end, {statistic_id}, "5minute", None, {"mean"}
    )
    out: dict[int, float] = {}
    for row in raw.get(statistic_id, []):
        value = row.get("mean")
        if value is None:
            continue
        row_start = row.get("start")
        epoch = int(row_start) if isinstance(row_start, (int, float)) else int(dt_util.as_utc(row_start).timestamp())
        out[epoch] = max(min(float(value), 100.0), 0.0) / 100.0 * float(capacity_kwh)
    return out


async def async_fetch_numeric_states(hass: HomeAssistant, entity_id: str, start: datetime, end: datetime) -> list[tuple[float, float]]:
    """The recorded numeric states of an entity [(epoch, value)], oldest
    first, the state at `start` included - the price sensor's quarter
    prices of the last days, for the savings card (2026.11.0)."""
    from homeassistant.components.recorder.history import state_changes_during_period

    changes = await get_instance(hass).async_add_executor_job(
        lambda: state_changes_during_period(hass, start, end, entity_id, no_attributes=True, include_start_time_state=True)
    )
    out: list[tuple[float, float]] = []
    for st in changes.get(entity_id.lower(), []):
        try:
            out.append((st.last_changed.timestamp(), float(st.state)))
        except (TypeError, ValueError):
            continue
    return out


def recorder_keep_days(hass: HomeAssistant) -> int:
    """How many days the recorder keeps its history (and the 5-minute
    statistics) - 10 by default."""
    try:
        return int(get_instance(hass).keep_days)
    except Exception:  # noqa: BLE001 - no recorder: nothing to look back on
        return 0
