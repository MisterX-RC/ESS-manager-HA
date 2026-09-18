"""DataUpdateCoordinator that ties the forecasting pipeline and the five
planning engines together every 30 seconds, reading live entity state and
the user-tunable `number` entities, and persisting the plans' self-locking
state (and the full-charge-plan's "last time the battery was full" tracker)
across Home Assistant restarts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import display, forecasting, plans
from .const import (
    CONF_BATTERY_CHARGE_ENERGY_ENTITY,
    CONF_BATTERY_DISCHARGE_ENERGY_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_ENABLE_FULL_CHARGE_PLAN,
    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN,
    CONF_GRID_EXPORT_ENTITIES,
    CONF_GRID_IMPORT_ENTITIES,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_PRICE_ENTITY,
    CONF_SOLAR_FORECAST_ENTITIES,
    CONF_SOLAR_PRODUCTION_ENTITIES,
    CONF_USAGE_CONSUMPTION_ENTITIES,
    CONF_USAGE_FORECAST_ENTITY,
    CONF_USAGE_LOOKBACK_WEEKS,
    CONF_USAGE_SOURCE,
    CONF_VOLTAGE_DIFF_ENTITY,
    DEFAULT_USAGE_LOOKBACK_WEEKS,
    DEFAULT_USAGE_SOURCE,
    DOMAIN,
    FORECAST_HOURS,
    NUM_BATTERY_CAPACITY_KWH,
    NUM_CHARGE_SPEED_KW,
    NUM_DISCHARGE_SPEED_KW,
    NUM_FULL_CHARGE_INTERVAL_DAYS,
    NUM_FULL_CHARGE_MAX_HOLD_MINUTES,
    NUM_MAX_SOC_PERCENT,
    NUM_MIN_SOC_PERCENT,
    NUM_MINIMUM_CHARGE_TARGET_KWH,
    NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW,
    NUM_NEGATIVE_PRICE_THRESHOLD,
    NUM_PLANNING_HORIZON_HOURS,
    NUM_SPIKE_DISCHARGE_SPEED_KW,
    NUM_SPIKE_MARGIN,
    STORAGE_VERSION,
    STORAGE_KEY_SUFFIX,
    UPDATE_INTERVAL_SECONDS,
    USAGE_FORECAST_RECALC_MINUTES,
    USAGE_SOURCE_CALCULATED,
    USAGE_SOURCE_CONSUMPTION_SENSOR,
)
from .statistics_source import async_fetch_hourly_sums
from .usage_forecast import compute_usage_forecast, compute_usage_forecast_from_consumption

_LOGGER = logging.getLogger(__name__)

FULL_SOC_THRESHOLD = 99.5
# Idle grid-setpoint tolerance window (W). The original hardcoded -30W as
# "idle" because that specific Victron install's setpoint never quite sat at
# 0. Generalized to 0W here - if your inverter has a similar quirk, that's a
# small constant worth reintroducing as another number entity later.
IDLE_SETPOINT_W = 0.0
IDLE_TOLERANCE_W = 50.0


def _get_float_state(hass: HomeAssistant, entity_id: Optional[str], default: float = 0.0) -> float:
    if not entity_id:
        return default
    state = hass.states.get(entity_id)
    if state is None or state.state in (None, "unknown", "unavailable"):
        return default
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return default


class EssManagerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns the whole compute pipeline for one ESS Manager config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}{STORAGE_KEY_SUFFIX}")

        self._numbers: dict[str, Any] = {}

        self._negative_price_plan: Optional[dict] = None
        self._spike_plan: Optional[dict] = None
        self._low_charge_plan: Optional[dict] = None
        self._high_discharge_plan: Optional[dict] = None
        self._full_charge_plan: Optional[dict] = None
        self._last_full_reached: Optional[datetime] = None
        self._was_full_prev_cycle: bool = False
        self._restored = False

        # Calculated-usage-forecast cache - recomputed at most once every
        # USAGE_FORECAST_RECALC_MINUTES, not every 30s cycle (see
        # _async_get_calculated_usage_forecast).
        self._usage_forecast_cache: Optional[list[float]] = None
        self._usage_forecast_computed_at: Optional[datetime] = None

    # -- wiring from number.py --------------------------------------------------
    def register_number(self, key: str, entity: Any) -> None:
        self._numbers[key] = entity

    def get_number(self, key: str, default: float = 0.0) -> float:
        entity = self._numbers.get(key)
        if entity is not None and entity.native_value is not None:
            return float(entity.native_value)
        return default

    # -- persistence --------------------------------------------------------
    async def _async_restore(self) -> None:
        data = await self.store.async_load()
        if data:
            self._negative_price_plan = data.get("negative_price_plan")
            self._spike_plan = data.get("spike_plan")
            self._low_charge_plan = data.get("low_charge_plan")
            self._high_discharge_plan = data.get("high_discharge_plan")
            self._full_charge_plan = data.get("full_charge_plan")
            last_full = data.get("last_full_reached")
            self._last_full_reached = dt_util.parse_datetime(last_full) if last_full else None
            self._was_full_prev_cycle = bool(data.get("was_full_prev_cycle", False))
        self._restored = True

    async def _async_persist(self) -> None:
        await self.store.async_save(
            {
                "negative_price_plan": self._negative_price_plan,
                "spike_plan": self._spike_plan,
                "low_charge_plan": self._low_charge_plan,
                "high_discharge_plan": self._high_discharge_plan,
                "full_charge_plan": self._full_charge_plan,
                "last_full_reached": self._last_full_reached.isoformat() if self._last_full_reached else None,
                "was_full_prev_cycle": self._was_full_prev_cycle,
            }
        )

    # -- calculated usage forecast --------------------------------------------
    async def _async_get_calculated_usage_forecast(self, conf: dict[str, Any], now: datetime) -> list[float]:
        """The h0..h120 usage forecast, computed from recorder statistics
        instead of an external sensor - cached and only recomputed once
        every USAGE_FORECAST_RECALC_MINUTES, since the underlying long-term
        statistics only ever land once per hour anyway.
        """
        stale = (
            self._usage_forecast_cache is None
            or self._usage_forecast_computed_at is None
            or (now - self._usage_forecast_computed_at) >= timedelta(minutes=USAGE_FORECAST_RECALC_MINUTES)
        )
        if not stale:
            return self._usage_forecast_cache

        import_entities = [e for e in conf.get(CONF_GRID_IMPORT_ENTITIES, []) or [] if e]
        export_entities = [e for e in conf.get(CONF_GRID_EXPORT_ENTITIES, []) or [] if e]
        solar_entities = [e for e in conf.get(CONF_SOLAR_PRODUCTION_ENTITIES, []) or [] if e]
        battery_charge_entity = conf.get(CONF_BATTERY_CHARGE_ENERGY_ENTITY) or None
        battery_discharge_entity = conf.get(CONF_BATTERY_DISCHARGE_ENERGY_ENTITY) or None
        lookback_weeks = int(conf.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS))

        all_entities = [*solar_entities, *import_entities, *export_entities]
        if battery_charge_entity:
            all_entities.append(battery_charge_entity)
        if battery_discharge_entity:
            all_entities.append(battery_discharge_entity)

        if not all_entities:
            # Nothing configured yet (e.g. mid-setup) - fall back to zeros
            # rather than failing the whole coordinator update over it.
            self._usage_forecast_cache = [0.0] * FORECAST_HOURS
            self._usage_forecast_computed_at = now
            return self._usage_forecast_cache

        base_hour = now.replace(minute=0, second=0, microsecond=0)
        # Need every hour from (lookback_weeks weeks + 1 hour) before the
        # current hour through the current hour itself - every historical
        # sample this feature ever looks up falls somewhere in that range,
        # since it only ever looks *backward* in time regardless of how far
        # forward the forecast itself projects.
        range_start = base_hour - timedelta(weeks=lookback_weeks, hours=1)
        range_end = base_hour + timedelta(hours=1)

        try:
            hourly_sums = await async_fetch_hourly_sums(self.hass, all_entities, range_start, range_end)
        except Exception as err:  # noqa: BLE001 - a statistics/DB hiccup shouldn't fail the whole update
            _LOGGER.warning("ESS Manager: could not fetch usage-forecast statistics: %s", err)
            if self._usage_forecast_cache is not None:
                return self._usage_forecast_cache
            return [0.0] * FORECAST_HOURS

        self._usage_forecast_cache = compute_usage_forecast(
            hourly_sums,
            import_entities,
            export_entities,
            solar_entities,
            battery_charge_entity,
            battery_discharge_entity,
            now,
            FORECAST_HOURS,
            lookback_weeks,
        )
        self._usage_forecast_computed_at = now
        return self._usage_forecast_cache

    async def _async_get_measured_usage_forecast(self, conf: dict[str, Any], now: datetime) -> list[float]:
        """The h0..h120 usage forecast, read directly from one or more
        home-energy-consumption sensors instead of derived from the
        solar/import/export/battery energy-balance identity - see
        usage_forecast.compute_usage_forecast_from_consumption for why this
        is a separate, simpler path (no derivation, so none of the
        cross-sensor resolution mismatches the calculated identity can run
        into). Deliberately structured as a standalone twin of
        _async_get_calculated_usage_forecast above (same caching, same
        USAGE_FORECAST_RECALC_MINUTES cadence, same "not enough
        history/data yet -> fall back to zeros or the last good cache"
        behavior) rather than a shared helper, so a future change to one
        source's fetch/caching logic can't accidentally change the other's.
        """
        stale = (
            self._usage_forecast_cache is None
            or self._usage_forecast_computed_at is None
            or (now - self._usage_forecast_computed_at) >= timedelta(minutes=USAGE_FORECAST_RECALC_MINUTES)
        )
        if not stale:
            return self._usage_forecast_cache

        consumption_entities = [e for e in conf.get(CONF_USAGE_CONSUMPTION_ENTITIES, []) or [] if e]
        lookback_weeks = int(conf.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS))

        if not consumption_entities:
            # Nothing configured yet (e.g. mid-setup) - fall back to zeros
            # rather than failing the whole coordinator update over it.
            self._usage_forecast_cache = [0.0] * FORECAST_HOURS
            self._usage_forecast_computed_at = now
            return self._usage_forecast_cache

        base_hour = now.replace(minute=0, second=0, microsecond=0)
        # Same backward-looking range as the calculated path: every
        # historical sample this feature ever looks up falls somewhere in
        # [now - lookback_weeks - 1h, now + 1h], since it only ever looks
        # backward regardless of how far forward the forecast itself
        # projects.
        range_start = base_hour - timedelta(weeks=lookback_weeks, hours=1)
        range_end = base_hour + timedelta(hours=1)

        try:
            hourly_sums = await async_fetch_hourly_sums(self.hass, consumption_entities, range_start, range_end)
        except Exception as err:  # noqa: BLE001 - a statistics/DB hiccup shouldn't fail the whole update
            _LOGGER.warning("ESS Manager: could not fetch usage-forecast statistics: %s", err)
            if self._usage_forecast_cache is not None:
                return self._usage_forecast_cache
            return [0.0] * FORECAST_HOURS

        self._usage_forecast_cache = compute_usage_forecast_from_consumption(
            hourly_sums,
            consumption_entities,
            now,
            FORECAST_HOURS,
            lookback_weeks,
        )
        self._usage_forecast_computed_at = now
        return self._usage_forecast_cache

    # -- main update ----------------------------------------------------------
    async def _async_update_data(self) -> dict[str, Any]:
        if not self._restored:
            await self._async_restore()

        conf = {**self.entry.data, **self.entry.options}
        now = dt_util.now()

        battery_soc_entity = conf.get(CONF_BATTERY_SOC_ENTITY)
        battery_soc_state = self.hass.states.get(battery_soc_entity) if battery_soc_entity else None
        if battery_soc_state is None or battery_soc_state.state in ("unknown", "unavailable", None):
            raise UpdateFailed(f"Battery SOC entity {battery_soc_entity} is unavailable")
        try:
            soc_now_percent = float(battery_soc_state.state)
        except (TypeError, ValueError) as err:
            raise UpdateFailed(f"Battery SOC entity {battery_soc_entity} has a non-numeric state") from err

        price_entity = conf.get(CONF_PRICE_ENTITY)
        price_state = self.hass.states.get(price_entity) if price_entity else None
        if price_state is None:
            raise UpdateFailed(f"Price entity {price_entity} is unavailable")
        today_price = list(price_state.attributes.get("today") or [])
        tomorrow_price = list(price_state.attributes.get("tomorrow") or [])
        all_price = [float(p) for p in (today_price + tomorrow_price)]

        usage_source = conf.get(CONF_USAGE_SOURCE, DEFAULT_USAGE_SOURCE)
        if usage_source == USAGE_SOURCE_CALCULATED:
            usage_forecast = await self._async_get_calculated_usage_forecast(conf, now)
        elif usage_source == USAGE_SOURCE_CONSUMPTION_SENSOR:
            usage_forecast = await self._async_get_measured_usage_forecast(conf, now)
        else:
            usage_entity = conf.get(CONF_USAGE_FORECAST_ENTITY)
            usage_state = self.hass.states.get(usage_entity) if usage_entity else None
            usage_attrs = usage_state.attributes if usage_state else {}
            usage_forecast = forecasting.build_usage_forecast(usage_attrs, FORECAST_HOURS)

        solar_points: list[list[dict]] = []
        for entity_id in conf.get(CONF_SOLAR_FORECAST_ENTITIES, []):
            state = self.hass.states.get(entity_id)
            if state is not None:
                solar_points.append(list(state.attributes.get("detailedHourly") or []))

        setpoint_w = _get_float_state(self.hass, conf.get(CONF_GRID_SETPOINT_ENTITY), default=0.0)
        voltage_diff_entity = conf.get(CONF_VOLTAGE_DIFF_ENTITY)
        voltage_diff = (
            _get_float_state(self.hass, voltage_diff_entity, default=999.0) if voltage_diff_entity else None
        )

        # -- tunables (numbers) ------------------------------------------------
        capacity_kwh = self.get_number(NUM_BATTERY_CAPACITY_KWH, 30.0)
        min_soc_percent = self.get_number(NUM_MIN_SOC_PERCENT, 15.0)
        max_soc_percent = self.get_number(NUM_MAX_SOC_PERCENT, 110.0)
        charge_speed_kw = self.get_number(NUM_CHARGE_SPEED_KW, 7.0)
        discharge_speed_kw = self.get_number(NUM_DISCHARGE_SPEED_KW, 10.0)
        negative_price_charge_speed_kw = self.get_number(NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW, charge_speed_kw * 2)
        spike_discharge_speed_kw = self.get_number(NUM_SPIKE_DISCHARGE_SPEED_KW, discharge_speed_kw * 1.5)
        negative_price_threshold = self.get_number(NUM_NEGATIVE_PRICE_THRESHOLD, -0.20)
        spike_margin = self.get_number(NUM_SPIKE_MARGIN, 0.40)
        minimum_charge_target_kwh = self.get_number(NUM_MINIMUM_CHARGE_TARGET_KWH, 5.0)
        planning_horizon_hours = int(self.get_number(NUM_PLANNING_HORIZON_HOURS, 72))
        full_charge_interval_days = self.get_number(NUM_FULL_CHARGE_INTERVAL_DAYS, 14.0)
        full_charge_max_hold_minutes = self.get_number(NUM_FULL_CHARGE_MAX_HOLD_MINUTES, 120.0)

        low_threshold_kwh = round((min_soc_percent / 100) * capacity_kwh, 2)
        high_threshold_kwh = round((max_soc_percent / 100) * capacity_kwh, 2)
        upper_limit_kwh = capacity_kwh  # nominal 100% - the normal charge-target ceiling

        # -- forecasting pipeline ----------------------------------------------
        merged_solar_points = forecasting.merge_hourly_points(solar_points)
        solar_forecast = forecasting.build_solar_forecast(merged_solar_points, now, FORECAST_HOURS)
        net_energy = forecasting.build_net_energy(solar_forecast, usage_forecast)
        battery_now_kwh = round(capacity_kwh * (soc_now_percent / 100), 2)
        battery_forecast = forecasting.build_battery_forecast(net_energy, battery_now_kwh, now)

        current_price_unit = (now.hour * 4) + (now.minute // 15)

        # -- negative price plan -------------------------------------------------
        if conf.get(CONF_ENABLE_NEGATIVE_PRICE_PLAN, True):
            self._negative_price_plan = plans.compute_negative_price_plan(
                self._negative_price_plan,
                current_price_unit,
                now,
                all_price,
                negative_price_threshold,
                battery_forecast,
                discharge_speed_kw,
                negative_price_charge_speed_kw,
                low_threshold_kwh,
                high_threshold_kwh,
            )
        else:
            self._negative_price_plan = {"active": False}

        forecast_with_negative_price = plans.compose_forecast_with_negative_price(
            battery_forecast, self._negative_price_plan, current_price_unit, now, high_threshold_kwh - 0.01
        )

        # -- spike plan ------------------------------------------------------
        if conf.get(CONF_ENABLE_SPIKE_PLAN, True):
            self._spike_plan = plans.compute_spike_plan(
                self._spike_plan,
                current_price_unit,
                all_price,
                battery_forecast,
                usage_forecast,
                low_threshold_kwh,
                upper_limit_kwh,
                high_threshold_kwh,
                spike_margin,
                charge_speed_kw,
                spike_discharge_speed_kw,
                self._negative_price_plan,
            )
        else:
            self._spike_plan = {"active": False}

        forecast_with_spike = plans.compose_forecast_with_spike(
            forecast_with_negative_price, self._spike_plan, current_price_unit, now, high_threshold_kwh - 0.01
        )

        # -- low charge / high discharge plans -----------------------------------
        self._low_charge_plan = plans.compute_low_charge_plan(
            self._low_charge_plan,
            current_price_unit,
            forecast_with_spike,
            now,
            charge_speed_kw,
            low_threshold_kwh,
            minimum_charge_target_kwh,
            upper_limit_kwh,
            usage_forecast,
            all_price,
            planning_horizon_hours,
        )
        self._high_discharge_plan = plans.compute_high_discharge_plan(
            self._high_discharge_plan,
            current_price_unit,
            forecast_with_spike,
            now,
            discharge_speed_kw,
            high_threshold_kwh,
            low_threshold_kwh,
            usage_forecast,
            all_price,
            planning_horizon_hours,
        )

        battery_forecast_adjusted = plans.compose_forecast_adjusted(
            forecast_with_spike, self._low_charge_plan, self._high_discharge_plan, current_price_unit, now
        )

        # -- full charge plan (self-tracked "days since last full") -------------
        is_full_now = soc_now_percent >= FULL_SOC_THRESHOLD
        if is_full_now and not self._was_full_prev_cycle:
            self._last_full_reached = now
        self._was_full_prev_cycle = is_full_now
        if self._last_full_reached is not None:
            time_since_full_days = (now - self._last_full_reached).total_seconds() / 86400
        else:
            # Never observed full since this integration was set up - treat
            # as overdue so an initial calibration charge gets scheduled.
            time_since_full_days = full_charge_interval_days

        if conf.get(CONF_ENABLE_FULL_CHARGE_PLAN, False):
            self._full_charge_plan = plans.compute_full_charge_plan(
                self._full_charge_plan,
                current_price_unit,
                now,
                full_charge_interval_days,
                time_since_full_days,
                soc_now_percent,
                full_charge_max_hold_minutes,
                voltage_diff,
                battery_now_kwh,
                upper_limit_kwh,
                usage_forecast,
                charge_speed_kw,
                all_price,
            )
        else:
            self._full_charge_plan = {"active": False, "phase": None}

        system_status = plans.compute_system_status(
            setpoint_w,
            IDLE_SETPOINT_W,
            current_price_unit,
            self._full_charge_plan,
            self._negative_price_plan,
            self._spike_plan,
            self._low_charge_plan,
            self._high_discharge_plan,
            battery_now_kwh,
            low_threshold_kwh,
            charge_speed_kw,
            discharge_speed_kw,
            all_price,
        )

        charge_kwh, charge_start_text, charge_stop_text = display.charge_display(
            self._negative_price_plan, self._spike_plan, self._low_charge_plan, current_price_unit, now
        )
        discharge_kwh, discharge_start_text, discharge_stop_text = display.discharge_display(
            self._negative_price_plan, self._spike_plan, self._high_discharge_plan, current_price_unit, now
        )

        await self._async_persist()

        return {
            "system_status": system_status,
            "battery_energy_kwh": battery_now_kwh,
            "battery_soc_percent": soc_now_percent,
            "low_threshold_kwh": low_threshold_kwh,
            "high_threshold_kwh": high_threshold_kwh,
            "capacity_kwh": capacity_kwh,
            "current_price_unit": current_price_unit,
            "all_price": all_price,
            "solar_120h": solar_forecast,
            "energy_usage_120h": usage_forecast,
            "net_energy_120h": net_energy,
            "battery_forecast": battery_forecast,
            "battery_forecast_with_negative_price": forecast_with_negative_price,
            "battery_forecast_with_spike": forecast_with_spike,
            "battery_forecast_adjusted": battery_forecast_adjusted,
            "negative_price_plan": self._negative_price_plan,
            "spike_plan": self._spike_plan,
            "low_charge_plan": self._low_charge_plan,
            "high_discharge_plan": self._high_discharge_plan,
            "full_charge_plan": self._full_charge_plan,
            "time_since_full_charge_days": round(time_since_full_days, 2),
            "planning_horizon_hours": planning_horizon_hours,
            "charge_energy_kwh": charge_kwh,
            "charge_start_time": charge_start_text,
            "charge_stop_time": charge_stop_text,
            "discharge_energy_kwh": discharge_kwh,
            "discharge_start_time": discharge_start_text,
            "discharge_stop_time": discharge_stop_text,
            "spike_status_text": display.spike_status_text(self._spike_plan),
            "next_full_charge_in_days": display.next_full_charge_in_days(
                full_charge_interval_days, time_since_full_days
            ),
        }
