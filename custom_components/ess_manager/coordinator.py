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

from . import control, display, forecasting, plans
from .const import (
    CONF_BATTERY_CHARGE_ENERGY_ENTITY,
    CONF_BATTERY_DISCHARGE_ENERGY_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_VOLTAGE_ENTITY,
    CONF_DAYS_SINCE_FULL_CHARGE_ENTITY,
    CONF_ENABLE_FULL_CHARGE_PLAN,
    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN,
    CONF_FULL_CHARGE_TARGET_VOLTAGE,
    CONF_FULL_CHARGE_TRACKING_SOURCE,
    CONF_GRID_EXPORT_ENTITIES,
    CONF_GRID_IMPORT_ENTITIES,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_HIGH_CELL_VOLTAGE_ENTITY,
    CONF_LOW_CELL_VOLTAGE_ENTITY,
    CONF_MAX_BATTERY_CHARGE_SPEED_KW,
    CONF_MAX_BATTERY_DISCHARGE_SPEED_KW,
    CONF_PRICE_ENTITY,
    CONF_SOLAR_FORECAST_ENTITIES,
    CONF_SOLAR_PRODUCTION_ENTITIES,
    CONF_USAGE_CONSUMPTION_ENTITIES,
    CONF_USAGE_FORECAST_ENTITY,
    CONF_USAGE_LOOKBACK_WEEKS,
    CONF_USAGE_SOURCE,
    CONF_VOLTAGE_DIFF_ENTITY,
    DEFAULT_FULL_CHARGE_TARGET_VOLTAGE,
    DEFAULT_FULL_CHARGE_TRACKING_SOURCE,
    DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW,
    DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW,
    DEFAULT_USAGE_LOOKBACK_WEEKS,
    LEGACY_DEFAULT_USAGE_SOURCE,
    DOMAIN,
    FORECAST_HOURS,
    FULL_CHARGE_TRACKING_EXTERNAL_SENSOR,
    NUM_BATTERY_CAPACITY_KWH,
    NUM_CHARGE_SPEED_KW,
    NUM_DISCHARGE_SPEED_KW,
    NUM_FULL_CHARGE_INTERVAL_DAYS,
    NUM_FULL_CHARGE_MAX_HOLD_MINUTES,
    NUM_FULL_CHARGE_TARGET_VOLTAGE,
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
    USAGE_SOURCE_CALCULATED,
    USAGE_SOURCE_CONSUMPTION_SENSOR,
    USAGE_SOURCE_ENERGY_DASHBOARD,
)
from .controller import ControlSettings, EssController
from .energy_source import async_get_energy_prefs
from .statistics_source import async_fetch_hourly_sums
from .usage_forecast import (
    compute_usage_forecast,
    compute_usage_forecast_from_consumption,
    energy_prefs_to_sources,
    usage_cache_is_stale,
)

_LOGGER = logging.getLogger(__name__)

# Idle grid-setpoint tolerance window (W). The original hardcoded -30W as
# "idle" because that specific Victron install's setpoint never quite sat at
# 0. Generalized to 0W here - if your inverter has a similar quirk, that's a
# small constant worth reintroducing as another number entity later.
IDLE_SETPOINT_W = 0.0
IDLE_TOLERANCE_W = 50.0


def _get_float_state(
    hass: HomeAssistant, entity_id: Optional[str], default: Optional[float] = 0.0
) -> Optional[float]:
    """Read one entity's state as a float, or `default` if it's missing/
    unavailable/non-numeric. `default` accepts None (not just a float) so a
    caller can tell "no reading available" apart from any real number -
    used by the low/high cell voltage fields below, where a missing reading
    on either side has to cancel the whole computed differential rather
    than silently substituting some fallback voltage into the subtraction.
    """
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
        self._restored = False

        # Statistics-based usage-forecast cache - recomputed once per hour,
        # on the first cycle after the hour changes, not every 30s cycle
        # (see usage_forecast.usage_cache_is_stale).
        self._usage_forecast_cache: Optional[list[float]] = None
        self._usage_forecast_computed_at: Optional[datetime] = None
        # What the Energy-dashboard usage source last detected (see
        # _async_get_energy_dashboard_usage_forecast) - exposed on the Status
        # sensor so it can be checked against the Energy dashboard itself.
        self._energy_dashboard_sources: Optional[dict[str, list[str]]] = None
        # Direct control (as of v0.2.14) - see controller.py.
        self.controller = EssController(hass, entry.title)

    def control_settings(self) -> ControlSettings:
        return ControlSettings({**self.entry.data, **self.entry.options})

    def invalidate_usage_forecast(self) -> None:
        """Drop the cached usage forecast so the next cycle recomputes it.
        Called when Configure is saved: options changes don't reload the
        integration (only refresh it), so without this a switch of usage
        source - or new entities/lookback weeks - would keep showing the old
        cached forecast until the hour changed.
        """
        self._usage_forecast_cache = None
        self._usage_forecast_computed_at = None
        self._energy_dashboard_sources = None

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
        else:
            # Nothing stored yet: a brand-new installation (as of v0.2.13).
            # Assume the battery has just been balanced, so the internal
            # "days since last full" clock starts at 0 and the first
            # full-charge cycle comes after the normal interval, instead of
            # the system spending its first hours on a forced full charge.
            # Existing installations always have stored data, so upgrading
            # doesn't move their clock.
            self._last_full_reached = dt_util.now()
            _LOGGER.info(
                "New ESS Manager installation: assuming the battery was just fully charged; "
                "the first full-charge balance is planned after the normal interval"
            )
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
            }
        )

    # -- calculated usage forecast --------------------------------------------
    async def _async_get_calculated_usage_forecast(self, conf: dict[str, Any], now: datetime) -> list[float]:
        """The h0..h120 usage forecast, computed from recorder statistics
        instead of an external sensor - cached and only recomputed once per
        hour (when the hour changes), since the underlying long-term
        statistics only ever land once per hour anyway.
        """
        stale = self._usage_forecast_cache is None or usage_cache_is_stale(
            self._usage_forecast_computed_at, now
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
        once-per-hour cadence, same "not enough
        history/data yet -> fall back to zeros or the last good cache"
        behavior) rather than a shared helper, so a future change to one
        source's fetch/caching logic can't accidentally change the other's.
        """
        stale = self._usage_forecast_cache is None or usage_cache_is_stale(
            self._usage_forecast_computed_at, now
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

    async def _async_get_energy_dashboard_usage_forecast(self, conf: dict[str, Any], now: datetime) -> list[float]:
        """The h0..h120 usage forecast via the same energy-balance identity as
        _async_get_calculated_usage_forecast, but with the grid/solar/battery
        statistics read live from Home Assistant's own Energy dashboard
        configuration (energy_source.py) instead of picked by hand in this
        integration's setup. Re-read on every recompute (not copied at setup),
        so an edit to the Energy dashboard is picked up automatically.

        A standalone twin of the calculated path (same caching cadence, same
        fall-back-to-last-good-cache behavior) rather than a shared helper,
        so this new, not-yet-verified-live source can't accidentally change
        the behavior of the already-live calculated one. What was actually
        detected is kept in self._energy_dashboard_sources and exposed on the
        Status sensor, so it can be checked against the Energy dashboard.
        """
        stale = self._usage_forecast_cache is None or usage_cache_is_stale(
            self._usage_forecast_computed_at, now
        )
        if not stale:
            return self._usage_forecast_cache

        prefs = await async_get_energy_prefs(self.hass)
        sources = energy_prefs_to_sources(prefs)
        self._energy_dashboard_sources = sources
        lookback_weeks = int(conf.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS))

        if not sources["import"]:
            # No grid import configured in the Energy dashboard (or it couldn't
            # be read at all) - there's no balance to compute. Keep the last
            # good forecast if there is one, otherwise zeros, rather than
            # failing the whole coordinator update.
            _LOGGER.warning(
                "ESS Manager: usage source is the Energy dashboard, but no grid import "
                "statistic was found there - configure the Energy dashboard's grid source"
            )
            if self._usage_forecast_cache is not None:
                return self._usage_forecast_cache
            return [0.0] * FORECAST_HOURS

        all_ids = [
            *sources["solar"],
            *sources["import"],
            *sources["export"],
            *sources["battery_charge"],
            *sources["battery_discharge"],
        ]
        base_hour = now.replace(minute=0, second=0, microsecond=0)
        range_start = base_hour - timedelta(weeks=lookback_weeks, hours=1)
        range_end = base_hour + timedelta(hours=1)

        try:
            hourly_sums = await async_fetch_hourly_sums(self.hass, all_ids, range_start, range_end)
        except Exception as err:  # noqa: BLE001 - a statistics/DB hiccup shouldn't fail the whole update
            _LOGGER.warning("ESS Manager: could not fetch usage-forecast statistics: %s", err)
            if self._usage_forecast_cache is not None:
                return self._usage_forecast_cache
            return [0.0] * FORECAST_HOURS

        self._usage_forecast_cache = compute_usage_forecast(
            hourly_sums,
            sources["import"],
            sources["export"],
            sources["solar"],
            sources["battery_charge"],
            sources["battery_discharge"],
            now,
            FORECAST_HOURS,
            lookback_weeks,
        )
        self._usage_forecast_computed_at = now
        return self._usage_forecast_cache

    def _get_voltage_diff(self, conf: dict[str, Any]) -> Optional[float]:
        """The cell voltage differential (millivolts) fed to the full-charge
        balancing plan, from whichever of the two configured sources
        applies - see const.py's CONF_VOLTAGE_DIFF_ENTITY docstring for the
        full reasoning. Which source is used is decided purely by which
        fields are configured (not by their live availability this cycle),
        so behavior doesn't flip between the two sources moment to moment:

        - Both CONF_LOW_CELL_VOLTAGE_ENTITY and CONF_HIGH_CELL_VOLTAGE_ENTITY
          set: derive it as (highest - lowest), converted from volts (how
          individual per-cell voltage sensors are conventionally reported in
          Home Assistant) to millivolts by multiplying by 1000, to match the
          millivolt convention the single-sensor path and
          plans.compute_full_charge_plan's balance_threshold default (10.0)
          already assume. If either reading is currently unavailable, the
          result is None for this cycle rather than falling back to some
          fixed voltage - compute_full_charge_plan already treats None as
          "assume not balanced yet" (its own 999.0 fallback), which is the
          correct, conservative behavior here too.
        - Otherwise, CONF_VOLTAGE_DIFF_ENTITY set: read it directly, assumed
          to already be in millivolts (this is how it worked before this
          option existed, e.g. a JK BMS's own "cell voltage differential"
          sensor - unchanged for anyone with this already configured).
        - Neither set: None (the full-charge plan just never ends its
          holding phase on voltage, only via its max-hold-minutes timeout).
        """
        low_entity = conf.get(CONF_LOW_CELL_VOLTAGE_ENTITY)
        high_entity = conf.get(CONF_HIGH_CELL_VOLTAGE_ENTITY)
        if low_entity and high_entity:
            low_v = _get_float_state(self.hass, low_entity, default=None)
            high_v = _get_float_state(self.hass, high_entity, default=None)
            return display.cell_voltage_differential_mv(low_v, high_v)

        voltage_diff_entity = conf.get(CONF_VOLTAGE_DIFF_ENTITY)
        if voltage_diff_entity:
            return _get_float_state(self.hass, voltage_diff_entity, default=999.0)
        return None

    # -- main update ----------------------------------------------------------
    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._async_compute()
        except Exception as err:
            # Fail-safe for direct control: never leave the last command
            # running while the integration can't see what's happening.
            # Does nothing unless direct control is on.
            await self.controller.async_idle(self.control_settings(), f"update failed: {err}")
            raise

    async def _async_compute(self) -> dict[str, Any]:
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

        # LEGACY_DEFAULT_USAGE_SOURCE, not DEFAULT_USAGE_SOURCE: an entry with
        # no usage_source stored predates the choice and has always meant the
        # external sensor - see const.py. The external-sensor and calculated
        # branches below are DEPRECATED - REMOVE IN 0.3.0.
        usage_source = conf.get(CONF_USAGE_SOURCE, LEGACY_DEFAULT_USAGE_SOURCE)
        if usage_source == USAGE_SOURCE_CALCULATED:
            usage_forecast = await self._async_get_calculated_usage_forecast(conf, now)
        elif usage_source == USAGE_SOURCE_CONSUMPTION_SENSOR:
            usage_forecast = await self._async_get_measured_usage_forecast(conf, now)
        elif usage_source == USAGE_SOURCE_ENERGY_DASHBOARD:
            usage_forecast = await self._async_get_energy_dashboard_usage_forecast(conf, now)
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

        control_settings = ControlSettings(conf)
        if conf.get(CONF_GRID_SETPOINT_ENTITY):
            setpoint_w = _get_float_state(self.hass, conf.get(CONF_GRID_SETPOINT_ENTITY), default=0.0)
        else:
            # No separate readback sensor: with direct control, the target
            # number entity's own value is the best readback there is.
            readback = self.controller.readback_power_w(control_settings)
            setpoint_w = readback if readback is not None else 0.0
        # With direct control, "idle" is whatever idle value is sent (e.g.
        # -30 W), so the Status's idle check uses that instead of 0 W.
        idle_setpoint_w = control_settings.idle_power_w if control_settings.active else IDLE_SETPOINT_W
        voltage_diff = self._get_voltage_diff(conf)
        # Third full-charge confirmation leg - the battery pack's own
        # measured voltage, checked against the adjustable target-voltage
        # number entity below (see compute_full_charge_plan's
        # voltage_at_target check). default=None (not 0.0) so a missing
        # reading is distinguishable from a genuine 0V reading.
        battery_voltage = _get_float_state(self.hass, conf.get(CONF_BATTERY_VOLTAGE_ENTITY), default=None)

        # -- tunables (numbers) ------------------------------------------------
        capacity_kwh = self.get_number(NUM_BATTERY_CAPACITY_KWH, 30.0)
        min_soc_percent = self.get_number(NUM_MIN_SOC_PERCENT, 15.0)
        max_soc_percent = self.get_number(NUM_MAX_SOC_PERCENT, 110.0)
        charge_speed_kw = self.get_number(NUM_CHARGE_SPEED_KW, 7.0)
        discharge_speed_kw = self.get_number(NUM_DISCHARGE_SPEED_KW, 10.0)
        # Not a `number` entity - a fixed hardware property set/edited via the
        # config/options flow, not a dashboard-adjustable setpoint.
        max_battery_charge_speed_kw = conf.get(CONF_MAX_BATTERY_CHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW)
        max_battery_discharge_speed_kw = conf.get(
            CONF_MAX_BATTERY_DISCHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW
        )
        negative_price_charge_speed_kw = self.get_number(NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW, charge_speed_kw * 2)
        spike_discharge_speed_kw = self.get_number(NUM_SPIKE_DISCHARGE_SPEED_KW, discharge_speed_kw * 1.5)
        negative_price_threshold = self.get_number(NUM_NEGATIVE_PRICE_THRESHOLD, -0.20)
        spike_margin = self.get_number(NUM_SPIKE_MARGIN, 0.40)
        minimum_charge_target_kwh = self.get_number(NUM_MINIMUM_CHARGE_TARGET_KWH, 5.0)
        planning_horizon_hours = int(self.get_number(NUM_PLANNING_HORIZON_HOURS, 72))
        full_charge_interval_days = self.get_number(NUM_FULL_CHARGE_INTERVAL_DAYS, 14.0)
        full_charge_max_hold_minutes = self.get_number(NUM_FULL_CHARGE_MAX_HOLD_MINUTES, 120.0)
        # Live-adjustable, unlike max_battery_charge/discharge_speed_kw above -
        # a calibration figure meant to be dialed in/tweaked from a dashboard,
        # not a fixed hardware property, so it's an ordinary `number` entity.
        full_charge_target_voltage = self.get_number(NUM_FULL_CHARGE_TARGET_VOLTAGE, DEFAULT_FULL_CHARGE_TARGET_VOLTAGE)

        low_threshold_kwh = round((min_soc_percent / 100) * capacity_kwh, 2)
        high_threshold_kwh = round((max_soc_percent / 100) * capacity_kwh, 2)
        upper_limit_kwh = capacity_kwh  # nominal 100% - the normal charge-target ceiling

        # -- forecasting pipeline ----------------------------------------------
        merged_solar_points = forecasting.merge_hourly_points(solar_points)
        solar_forecast = forecasting.build_solar_forecast(merged_solar_points, now, FORECAST_HOURS)
        net_energy = forecasting.build_net_energy(solar_forecast, usage_forecast)
        battery_now_kwh = round(capacity_kwh * (soc_now_percent / 100), 2)
        # max_battery_charge_speed_kw/max_battery_discharge_speed_kw are the
        # battery's own physical power limit - distinct from
        # charge_speed_kw/discharge_speed_kw above, which are how fast the
        # planning engines deliberately charge/discharge *from the grid*.
        # Whatever solar or usage would otherwise push the battery faster
        # than it can physically go is assumed to flow to/from the grid
        # instead, not the battery - see forecasting.build_battery_forecast.
        battery_forecast = forecasting.build_battery_forecast(
            net_energy, battery_now_kwh, now, max_battery_charge_speed_kw, max_battery_discharge_speed_kw
        )

        current_price_unit = (now.hour * 4) + (now.minute // 15)

        # -- full charge plan ("days since last full" tracking) -----------------
        # Computed early, before every other plan, for two reasons: (1) so
        # battery_forecast_adjusted below can reflect it (see v0.1.14), and
        # (2) so the high discharge plan (below) can be told not to sell
        # off a future solar peak this plan is relying on - see
        # relying_on_peak_unit and the suppress_high_discharge logic just
        # before compute_high_discharge_plan's call. It doesn't depend on
        # any other plan or on forecast_with_spike for anything, so
        # computing it first changes nothing about its own result.
        #
        # "Days since last full" is tracked one of two ways, per
        # CONF_FULL_CHARGE_TRACKING_SOURCE: either read directly from an
        # external sensor that already tracks it (e.g. a BMS's own entity,
        # which resets to 0 the moment it observes a genuine full charge),
        # or self-tracked internally from the last time this integration's
        # own compute_full_charge_plan reported balance_confirmed. A missing/
        # unavailable external sensor falls back to full_charge_interval_days
        # (i.e. "treat as due"), matching the same bootstrapping convention
        # as "never observed full yet" below.
        if conf.get(CONF_FULL_CHARGE_TRACKING_SOURCE, DEFAULT_FULL_CHARGE_TRACKING_SOURCE) == (
            FULL_CHARGE_TRACKING_EXTERNAL_SENSOR
        ):
            time_since_full_days = _get_float_state(
                self.hass, conf.get(CONF_DAYS_SINCE_FULL_CHARGE_ENTITY), default=full_charge_interval_days
            )
        elif self._last_full_reached is not None:
            time_since_full_days = (now - self._last_full_reached).total_seconds() / 86400
        else:
            # Never observed full and no install time recorded - only an
            # installation from before v0.2.13 that has never balanced (new
            # installations start the clock at setup, see _async_restore).
            # Treat as overdue so a calibration charge gets scheduled.
            time_since_full_days = full_charge_interval_days

        if conf.get(CONF_ENABLE_FULL_CHARGE_PLAN, False):
            # Passes high_threshold_kwh (the max-SOC-based overshoot
            # ceiling, ~110% by default) rather than upper_limit_kwh
            # (nominal 100%) - compute_full_charge_plan uses it both to
            # decide whether a forecasted future solar peak already
            # amounts to a real, sustained overshoot (long enough to
            # finish cell-balancing on its own) and, if not, as the
            # reference point for how much to buy. battery_forecast (the
            # raw, unadjusted solar/usage projection - no price-driven
            # charging baked in) is what it searches for that peak in.
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
                high_threshold_kwh,
                usage_forecast,
                charge_speed_kw,
                all_price,
                battery_forecast,
                battery_voltage,
                full_charge_target_voltage,
            )
        else:
            self._full_charge_plan = {"active": False, "phase": None}

        # Situation 1 (passive confirmation) and the fix for the old
        # SOC-crossing race condition both come from the same change: the
        # "days since last full" clock now resets strictly AFTER
        # compute_full_charge_plan runs, and only when ITS OWN output says
        # all three legs (SOC, voltage differential, battery voltage) were
        # genuinely satisfied together - never on a bare SOC threshold
        # crossing computed independently beforehand.
        if self._full_charge_plan.get("balance_confirmed"):
            self._last_full_reached = now

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
                minimum_charge_target_kwh,
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
            battery_now_kwh,
        )
        # A full charge relying on a future solar peak (either genuinely
        # scheduled to buy up to it, or silently skipped because that peak
        # already reaches high_threshold_kwh on its own - see
        # relying_on_peak_unit in compute_full_charge_plan) needs that peak
        # left alone until it happens: compute_high_discharge_plan's own
        # peak-scan only looks planning_horizon_hours ahead and has no idea
        # the full-charge plan exists, so without this it could sell off
        # exactly the surplus energy the full-charge plan is counting on to
        # reach that peak for free. Also suppressed outright while a full
        # charge is actively charging or holding, since discharging then
        # would directly fight the charge/hold setpoint. Only blocks
        # scheduling a *new* discharge window - one already in progress
        # (locked in via compute_high_discharge_plan's own prev check)
        # finishes normally regardless.
        full_charging_or_holding = self._full_charge_plan.get("active") and self._full_charge_plan.get("phase") in (
            "charging",
            "holding",
        )
        full_relying_on_peak_unit = self._full_charge_plan.get("relying_on_peak_unit")
        full_peak_not_yet_reached = full_relying_on_peak_unit is not None and current_price_unit < full_relying_on_peak_unit
        suppress_high_discharge = bool(full_charging_or_holding or full_peak_not_yet_reached)

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
            battery_now_kwh,
            suppress_high_discharge,
            minimum_charge_target_kwh=minimum_charge_target_kwh,
        )

        battery_forecast_adjusted = plans.compose_forecast_adjusted(
            forecast_with_spike,
            self._low_charge_plan,
            self._high_discharge_plan,
            current_price_unit,
            now,
            full=self._full_charge_plan,
            upper_limit_kwh=upper_limit_kwh,
        )

        system_status, control_action = plans.compute_system_status_and_action(
            setpoint_w,
            idle_setpoint_w,
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
            self._full_charge_plan, self._negative_price_plan, self._spike_plan, self._low_charge_plan, current_price_unit, now
        )
        discharge_kwh, discharge_start_text, discharge_stop_text = display.discharge_display(
            self._negative_price_plan, self._spike_plan, self._high_discharge_plan, current_price_unit, now
        )

        await self._async_persist()

        # -- direct control ----------------------------------------------------
        # Always worked out (and shown), even with control off, so the
        # planned setpoint can be compared against an existing automation
        # before switching over. Only sent when a control mode is chosen and
        # the "Automatic control" switch is on.
        control_power_kw = control.action_power_kw(
            control_action,
            charge_speed_kw,
            discharge_speed_kw,
            negative_price_charge_speed_kw,
            spike_discharge_speed_kw,
            max_battery_charge_speed_kw,
            max_battery_discharge_speed_kw,
        )
        await self.controller.async_apply(control_settings, control_action, control_power_kw, system_status)

        return {
            "system_status": system_status,
            "control_action": control_action,
            "control_power_kw": round(control_power_kw, 3),
            "control": self.controller.as_attribute(control_settings, control_action, control_power_kw),
            "battery_energy_kwh": battery_now_kwh,
            "battery_soc_percent": soc_now_percent,
            "low_threshold_kwh": low_threshold_kwh,
            "high_threshold_kwh": high_threshold_kwh,
            "capacity_kwh": capacity_kwh,
            "current_price_unit": current_price_unit,
            "all_price": all_price,
            # Where the "tomorrow" half of all_price begins (i.e. len(today's
            # own price list)) - lets a dashboard split all_price back into
            # its today/tomorrow halves by index without guessing a 96-unit
            # boundary (which can be wrong on a DST transition day), so the
            # price chart can be built entirely from this sensor instead of
            # also referencing the raw price entity directly.
            "today_price_units": len(today_price),
            "solar_120h": solar_forecast,
            "energy_usage_120h": usage_forecast,
            "usage_source": usage_source,
            "energy_dashboard_sources": (
                self._energy_dashboard_sources if usage_source == USAGE_SOURCE_ENERGY_DASHBOARD else None
            ),
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
            "cell_voltage_differential_mv": voltage_diff,
            "battery_voltage": battery_voltage,
            "time_since_full_charge_days": round(time_since_full_days, 2),
            "planning_horizon_hours": planning_horizon_hours,
            "charge_energy_kwh": charge_kwh,
            "charge_start_time": charge_start_text,
            "charge_stop_time": charge_stop_text,
            "discharge_energy_kwh": discharge_kwh,
            "discharge_start_time": discharge_start_text,
            "discharge_stop_time": discharge_stop_text,
            "spike_status_text": display.spike_status_text(self._spike_plan),
            "negative_price_status_text": display.negative_price_status_text(self._negative_price_plan),
            "next_full_charge_in_days": display.next_full_charge_in_days(
                full_charge_interval_days, time_since_full_days
            ),
        }
