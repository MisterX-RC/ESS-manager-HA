"""Pure-Python household usage forecasting from raw energy statistics.

This is the calculated alternative to reading an existing "h0..h120"
usage-forecast sensor (see forecasting.build_usage_forecast): instead of
depending on an external sensor, derive the same shape of forecast directly
from Home Assistant's own long-term recorder statistics (imported via
statistics_source.py, which is the only HA-dependent half of this feature).

Ported from the original hand-written system's SQL sensor (a single query
against MySQL's `statistics`/`statistics_meta` tables - see
legacy-yaml-config/ and the project handoff notes), but reimplemented here
in plain Python against a pre-fetched dict of hourly cumulative sums rather
than a raw SQL query, for two reasons: it works against any recorder
backend (the original query used MySQL-specific syntax like
UNIX_TIMESTAMP()/CAST(...AS UNSIGNED), which isn't portable to SQLite or
Postgres installs), and it can be unit-tested here with zero Home Assistant
dependency, the same way the rest of this module's siblings are.

Methodology (unchanged from the original): for each forecast hour, look at
the same calendar hour/day-of-week 1..N weeks in the past, and average the
actual household consumption Home Assistant's own energy statistics show
for each of those historical hours. Consumption for one historical hour is
derived from the energy-balance identity:

    consumption = solar_generated + grid_imported + battery_discharged
                  - grid_exported - battery_charged

each term being a delta between that hour's start and end cumulative
statistics ("sum") values.

Deliberate improvement over the original: the original's SQL used
`COALESCE(cur.sum - prev.sum, 0)` for every term, meaning a week with
genuinely missing data (an entity that didn't exist yet, a recorder gap)
silently contributed a 0 to the average instead of being excluded from it -
quietly pulling the forecast down (flagged, but never fixed, in the
original project's notes). Here, a week is only used if every configured
term has real data for that hour; weeks with any missing term are skipped
entirely rather than treated as zero.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional, Union

HOUR_SECONDS = 3600
WEEK_SECONDS = 7 * 24 * HOUR_SECONDS

# A battery energy term can be a single statistic id (the manual
# "calculated" config, which only ever had one charge/one discharge field),
# a list of them (the Energy-dashboard source, since HA's Energy dashboard
# lets you configure any number of batteries), or None/empty.
BatteryTerm = Union[None, str, list[str]]


def _as_list(term: BatteryTerm) -> list[str]:
    if not term:
        return []
    if isinstance(term, str):
        return [term]
    return [t for t in term if t]


def _hour_delta(
    hourly_sums: dict[str, dict[int, float]], entity_id: str, hour_start_epoch: int
) -> Optional[float]:
    """The change in a cumulative 'sum' statistic over one hour, or None if
    either endpoint is missing (entity didn't exist yet, a recorder gap,
    etc.) - callers treat None as "this week's sample is unusable", not 0.
    """
    series = hourly_sums.get(entity_id)
    if not series:
        return None
    cur = series.get(hour_start_epoch)
    prev = series.get(hour_start_epoch - HOUR_SECONDS)
    if cur is None or prev is None:
        return None
    return cur - prev


def _week_sample(
    hourly_sums: dict[str, dict[int, float]],
    import_entities: list[str],
    export_entities: list[str],
    solar_entities: list[str],
    battery_charge_entity: BatteryTerm,
    battery_discharge_entity: BatteryTerm,
    hour_start_epoch: int,
) -> Optional[float]:
    """One historical hour's household consumption via the energy-balance
    identity, or None if any configured term is missing data for that hour
    (the whole sample is dropped rather than letting a missing term
    silently default to 0 - see module docstring).
    """
    total = 0.0
    added = list(solar_entities) + list(import_entities) + _as_list(battery_discharge_entity)
    subtracted = list(export_entities) + _as_list(battery_charge_entity)
    for entity_id in added:
        delta = _hour_delta(hourly_sums, entity_id, hour_start_epoch)
        if delta is None:
            return None
        total += delta
    for entity_id in subtracted:
        delta = _hour_delta(hourly_sums, entity_id, hour_start_epoch)
        if delta is None:
            return None
        total -= delta
    return total


def compute_usage_forecast(
    hourly_sums: dict[str, dict[int, float]],
    import_entities: list[str],
    export_entities: list[str],
    solar_entities: list[str],
    battery_charge_entity: BatteryTerm,
    battery_discharge_entity: BatteryTerm,
    now: datetime,
    forecast_hours: int,
    lookback_weeks: int,
) -> list[float]:
    """Build the h0..h(forecast_hours-1) usage forecast array. h0 is the
    current (floor-aligned) hour, matching forecasting.build_usage_forecast
    and build_net_energy's expectations exactly - this is a drop-in
    alternative source for the same array, not a different shape.
    """
    base_hour = now.replace(minute=0, second=0, microsecond=0)
    result: list[float] = []
    for h in range(forecast_hours):
        target_hour_epoch = int(base_hour.timestamp()) + h * HOUR_SECONDS
        samples: list[float] = []
        for week in range(1, lookback_weeks + 1):
            hist_epoch = target_hour_epoch - week * WEEK_SECONDS
            sample = _week_sample(
                hourly_sums,
                import_entities,
                export_entities,
                solar_entities,
                battery_charge_entity,
                battery_discharge_entity,
                hist_epoch,
            )
            if sample is not None:
                samples.append(sample)
        result.append(round(sum(samples) / len(samples), 3) if samples else 0.0)
    return result


def compute_usage_forecast_from_consumption(
    hourly_sums: dict[str, dict[int, float]],
    consumption_entities: list[str],
    now: datetime,
    forecast_hours: int,
    lookback_weeks: int,
) -> list[float]:
    """Same historical-hour-averaging methodology as compute_usage_forecast,
    for a home that already has one or more direct "total energy consumed"
    sensors, instead of needing to derive consumption from the
    solar/import/export/battery energy-balance identity.

    There's nothing to balance here - a direct consumption meter already
    *is* the answer, so this is just compute_usage_forecast with every term
    except "import" zeroed out (grid_import_entities is really just "sum
    and average whatever cumulative energy sensor(s) these are", which is
    exactly what a direct consumption meter needs too). Kept as its own
    named function rather than relying on callers to know that trick, so a
    future change to the balance-identity math doesn't silently change this
    path too without a deliberate decision.

    This also sidesteps a real failure mode the balance identity is exposed
    to: if one of its four terms comes from a coarser/less-frequently
    updating sensor than the others (e.g. a grid meter that only reports in
    0.1 kWh steps a few times an hour, next to a battery shunt updating
    every couple of minutes), Home Assistant's hourly statistics can
    attribute a real, continuous energy flow entirely to whichever single
    hour the coarse sensor happened to tick over in - producing
    nonsensical per-hour swings (including impossible negative
    "consumption") even though the day's total works out fine. A direct
    consumption meter has only one term, so there's nothing for it to be
    inconsistent with.
    """
    return compute_usage_forecast(
        hourly_sums,
        import_entities=consumption_entities,
        export_entities=[],
        solar_entities=[],
        battery_charge_entity=None,
        battery_discharge_entity=None,
        now=now,
        forecast_hours=forecast_hours,
        lookback_weeks=lookback_weeks,
    )


def energy_prefs_to_sources(prefs: Optional[dict[str, Any]]) -> dict[str, list[str]]:
    """Map Home Assistant's Energy dashboard preferences (what
    `homeassistant.components.energy.data.async_get_manager(hass).data`
    holds) onto the five statistic-id lists compute_usage_forecast's
    energy-balance identity needs: grid import, grid export, solar
    production, battery charged, battery discharged.

    Kept pure (a plain dict in, plain lists out) so it can be unit-tested
    without Home Assistant - the only HA-dependent part is fetching the
    prefs dict itself (coordinator.py).

    Handles BOTH shapes HA has used for grid sources:
      - legacy: one "grid" entry with `flow_from: [{stat_energy_from}, ...]`
        and `flow_to: [{stat_energy_to}, ...]` arrays (one item per tariff/
        meter);
      - current: one "grid" entry per connection, carrying its own
        `stat_energy_from` (import) and optional `stat_energy_to` (export)
        directly.
    Solar: `stat_energy_from` = production. Battery: `stat_energy_from` =
    energy discharged OUT of the battery, `stat_energy_to` = energy charged
    INTO it (HA's naming is from the house's point of view). Gas/water and
    device-level consumption are ignored - they're not part of the
    electricity balance. Duplicates and blanks are dropped, order kept.
    These are statistic ids, not necessarily entity ids - an external
    statistic like "tibber:energy_consumption" is valid and is fetched the
    same way by statistics_source.py.
    """
    out: dict[str, list[str]] = {
        "import": [],
        "export": [],
        "solar": [],
        "battery_charge": [],
        "battery_discharge": [],
    }

    def add(key: str, value: Any) -> None:
        if isinstance(value, str) and value and value not in out[key]:
            out[key].append(value)

    for source in (prefs or {}).get("energy_sources") or []:
        if not isinstance(source, dict):
            continue
        kind = source.get("type")
        if kind == "grid":
            for flow in source.get("flow_from") or []:
                if isinstance(flow, dict):
                    add("import", flow.get("stat_energy_from"))
            for flow in source.get("flow_to") or []:
                if isinstance(flow, dict):
                    add("export", flow.get("stat_energy_to"))
            add("import", source.get("stat_energy_from"))
            add("export", source.get("stat_energy_to"))
        elif kind == "solar":
            add("solar", source.get("stat_energy_from"))
        elif kind == "battery":
            add("battery_discharge", source.get("stat_energy_from"))
            add("battery_charge", source.get("stat_energy_to"))
    return out


def usage_cache_is_stale(computed_at: Optional[datetime], now: datetime) -> bool:
    """Whether a cached usage forecast must be recomputed: once per hour,
    as soon as the current hour differs from the hour it was computed in.

    The forecast array is anchored to the hour it was computed in (h0 is
    *that* hour), so it's only valid within that same hour - reused after
    the hour changes, every value lands one hour early (a live dump at 19:04
    still showed the 18:00 value at h0, under the old 55-minute age limit).
    Within the hour nothing it depends on can change: it only looks at the
    same hour one or more weeks back, and hourly long-term statistics only
    land once an hour - so there's no reason to recompute more often, and
    recomputing right at the top of the hour is safe (it never needs the
    hour that just ended).
    """
    if computed_at is None:
        return True
    return now.replace(minute=0, second=0, microsecond=0) != computed_at.replace(minute=0, second=0, microsecond=0)
