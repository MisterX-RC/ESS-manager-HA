"""Fetches raw hourly long-term statistics from Home Assistant's recorder.

This is the only Home Assistant-dependent half of the calculated usage
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
