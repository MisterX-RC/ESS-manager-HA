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
    CONF_BATTERY_SOC_ENTITY,
    CONF_ENABLE_FULL_CHARGE_PLAN,
    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_PRICE_ENTITY,
    CONF_SOLAR_FORECAST_ENTITIES,
    CONF_USAGE_FORECAST_ENTITY,
    CONF_VOLTAGE_DIFF_ENTITY,
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
)

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

        usage_entity = conf.get(CONF_USAGE_FORECAST_ENTITY)
        usage_state = self.hass.states.get(usage_entity) if usage_entity else None
        usage_attrs = usage_state.attributes if usage_state else {}

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
        usage_forecast = forecasting.build_usage_forecast(usage_attrs, FORECAST_HOURS)
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
