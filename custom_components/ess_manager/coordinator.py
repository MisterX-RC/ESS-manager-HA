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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import control, display, forecasting, plans, transport
from .const import (
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_VOLTAGE_ENTITY,
    CONF_DAYS_SINCE_FULL_CHARGE_ENTITY,
    CONF_ENABLE_FULL_CHARGE_PLAN,
    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN,
    CONF_FULL_CHARGE_TRACKING_SOURCE,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_GRID_SETPOINT_SIGN,
    DEFAULT_GRID_SETPOINT_SIGN,
    CONF_HIGH_CELL_VOLTAGE_ENTITY,
    CONF_LOW_CELL_VOLTAGE_ENTITY,
    CONF_MAX_BATTERY_CHARGE_SPEED_KW,
    CONF_MAX_BATTERY_DISCHARGE_SPEED_KW,
    CONF_CHARGE_EFFICIENCY_PERCENT,
    CONF_DISCHARGE_EFFICIENCY_PERCENT,
    CONF_PRICE_ENTITY,
    CONF_SOLAR_FORECAST_ENTITIES,
    CONF_USAGE_CONSUMPTION_ENTITIES,
    CONF_USAGE_LOOKBACK_WEEKS,
    CONF_USAGE_SOURCE,
    CONF_VOLTAGE_DIFF_ENTITY,
    DEFAULT_FULL_CHARGE_TARGET_VOLTAGE,
    DEFAULT_FULL_CHARGE_TRACKING_SOURCE,
    DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW,
    DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW,
    DEFAULT_CHARGE_EFFICIENCY_PERCENT,
    DEFAULT_DISCHARGE_EFFICIENCY_PERCENT,
    DEFAULT_USAGE_LOOKBACK_WEEKS,
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
    NUM_MIN_SOC_SURPLUS_PERCENT,
    NUM_MINIMUM_CHARGE_MINUTES,
    NUM_MINIMUM_CHARGE_TARGET_KWH,
    NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW,
    NUM_NEGATIVE_PRICE_THRESHOLD,
    NUM_SAFETY_BUFFER_PERCENT,
    NUM_TRANSPORT_TARIFF,
    NUM_PLANNING_HORIZON_HOURS,
    NUM_SPIKE_DISCHARGE_SPEED_KW,
    NUM_SPIKE_MARGIN,
    PLAN_ENABLED_DEFAULTS,
    STORAGE_VERSION,
    STORAGE_KEY_SUFFIX,
    UPDATE_INTERVAL_SECONDS,
    USAGE_SOURCE_CONSUMPTION_SENSOR,
    USAGE_SOURCE_ENERGY_DASHBOARD,
)
from .controller import ControlSettings, EssController
from .energy_source import async_get_energy_prefs
from .statistics_source import async_fetch_hourly_sums, async_last_recorded_state
from .usage_forecast import (
    HISTORY_NONE,
    HISTORY_STATUS_NONE,
    compute_usage_forecast_detailed,
    compute_usage_forecast_from_consumption_detailed,
    energy_prefs_to_sources,
    measured_hours,
    summarize_usage_history,
    usage_cache_is_stale,
)

_LOGGER = logging.getLogger(__name__)

# Repairs issue kind for a usage forecast that is mostly without history
# (as of v0.3.5) - see _update_usage_history_issue.
USAGE_HISTORY_ISSUE = "usage_forecast_no_history"

# Idle grid-setpoint tolerance window (W). The original hardcoded -30W as
# "idle" because that specific Victron install's setpoint never quite sat at
# 0. Generalized to 0W here - if your inverter has a similar quirk, that's a
# small constant worth reintroducing as another number entity later.
IDLE_SETPOINT_W = 0.0
IDLE_TOLERANCE_W = 50.0


def _efficiency(percent: Any) -> float:
    """A 50-100 % efficiency setting as a 0.5-1.0 fraction (anything
    unreadable counts as 100 %, i.e. no losses)."""
    try:
        value = float(percent)
    except (TypeError, ValueError):
        return 1.0
    return min(max(value, 50.0), 100.0) / 100.0


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
        # A setting changed (a number entity, or Configure saved; as of
        # v0.5.12): the next cycle checks running windows again instead of
        # keeping them locked - see request_replan.
        self._replan_requested = 0
        self._last_solar_mode: Optional[str] = None

        # Statistics-based usage-forecast cache - recomputed once per hour,
        # on the first cycle after the hour changes, not every 30s cycle
        # (see usage_forecast.usage_cache_is_stale).
        self._usage_forecast_cache: Optional[list[float]] = None
        self._usage_forecast_computed_at: Optional[datetime] = None
        # What the Energy-dashboard usage source last detected (see
        # _async_get_energy_dashboard_usage_forecast) - exposed on the Status
        # sensor so it can be checked against the Energy dashboard itself.
        self._energy_dashboard_sources: Optional[dict[str, list[str]]] = None
        # How much history the cached usage forecast is based on (as of
        # v0.3.5) - see usage_forecast.summarize_usage_history. Shown on its
        # own diagnostic sensor (not on Status, whose state automations
        # trigger on), logged when it changes, and a Repairs notice while
        # most of the forecast has no history at all.
        self._usage_history: Optional[dict[str, Any]] = None
        self._usage_history_logged_status: Optional[str] = None
        # Today's measured hours (as of v0.5.1) - see usage_forecast.measured_hours;
        # computed with the usage forecast, from the same statistics.
        self._measured_today: Optional[dict[str, Any]] = None
        self._measured_today_at: Optional[datetime] = None
        # Transport tariff factors (as of v0.4.0) - transport_factors.json,
        # read once (in an executor) the first time a tariff above 0 is set.
        self._transport_factors: Optional[dict[int, list[float]]] = None
        # Direct control (as of v0.2.14) - see controller.py.
        self.controller = EssController(hass, entry.title)

    def control_settings(self) -> ControlSettings:
        return ControlSettings({**self.entry.data, **self.entry.options})

    def plan_enabled(self, plan: str) -> bool:
        """Whether a plan's Configure switch (CONF_ENABLE_*) is on - same
        defaults as the update cycle uses."""
        return bool({**self.entry.data, **self.entry.options}.get(plan, PLAN_ENABLED_DEFAULTS[plan]))

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
        self._usage_history = None
        self._measured_today = None
        self._measured_today_at = None

    def request_replan(self) -> None:
        """A setting changed: on the next cycle every plan is worked out
        afresh, including a window that's already running (normally kept
        as it is until it ends). Without this, raising and lowering a
        threshold could leave a charge running that's no longer needed."""
        self._replan_requested += 1

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
            # the solar mode it was in, so a forecast that stays between 0%
            # and 100% keeps it after a restart or an update (2026.10.8)
            self._last_solar_mode = data.get("solar_mode")
            if "solar_mode" not in data:
                # stored by a version from before 2026.10.8: take it from
                # the Solar mode sensor's history, once
                self._last_solar_mode = await self._async_recorded_solar_mode()
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

    async def _async_recorded_solar_mode(self) -> Optional[str]:
        """The Solar mode sensor's last recorded Deficit/Surplus, or None."""
        try:
            entity_id = er.async_get(self.hass).async_get_entity_id(
                "sensor", DOMAIN, f"{self.entry.entry_id}_solar_mode"
            )
            if not entity_id:
                return None
            mode = await async_last_recorded_state(
                self.hass, entity_id, (forecasting.SOLAR_MODE_DEFICIT, forecasting.SOLAR_MODE_SURPLUS)
            )
        except Exception as err:  # noqa: BLE001 - the recorder is optional here; surplus is the fallback
            _LOGGER.debug("ESS Manager: no recorded solar mode (%s)", err)
            return None
        if mode:
            _LOGGER.info("ESS Manager (%s): solar mode %s taken over from the sensor's history", self.entry.title, mode)
        return mode

    async def _async_persist(self) -> None:
        await self.store.async_save(
            {
                "negative_price_plan": self._negative_price_plan,
                "spike_plan": self._spike_plan,
                "low_charge_plan": self._low_charge_plan,
                "high_discharge_plan": self._high_discharge_plan,
                "full_charge_plan": self._full_charge_plan,
                "last_full_reached": self._last_full_reached.isoformat() if self._last_full_reached else None,
                "solar_mode": self._last_solar_mode,
            }
        )

    # -- usage forecast sources ---------------------------------------------------
    async def _async_get_measured_usage_forecast(self, conf: dict[str, Any], now: datetime) -> list[float]:
        """The h0..h120 usage forecast, read directly from one or more
        home-energy-consumption sensors instead of derived from the
        solar/import/export/battery energy-balance identity - see
        usage_forecast.compute_usage_forecast_from_consumption for why this
        is a separate, simpler path (no derivation, so none of the
        cross-sensor resolution mismatches the calculated identity can run
        into). Cached and recomputed once per hour, like the Energy
        dashboard source below; not enough history/data yet -> falls back to
        zeros or the last good cache.
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
            self._set_usage_history([HISTORY_NONE] * FORECAST_HOURS, lookback_weeks)
            return self._usage_forecast_cache

        base_hour = now.replace(minute=0, second=0, microsecond=0)
        # Backward-looking range: every
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
            self._set_usage_history([HISTORY_NONE] * FORECAST_HOURS, lookback_weeks)
            return [0.0] * FORECAST_HOURS

        self._usage_forecast_cache, hour_sources = compute_usage_forecast_from_consumption_detailed(
            hourly_sums,
            consumption_entities,
            now,
            FORECAST_HOURS,
            lookback_weeks,
        )
        self._usage_forecast_computed_at = now
        self._set_usage_history(hour_sources, lookback_weeks)
        return self._usage_forecast_cache

    async def _async_refresh_measured_today(self, conf: dict[str, Any], usage_source: Any, now: datetime) -> None:
        """Today's measured hours for the battery card (as of v0.5.1) - see
        usage_forecast.measured_hours. Read from the same statistics as the
        usage forecast, every 15 minutes (a just-ended hour's statistic lands
        a few minutes after the hour). Display only: a failure keeps the
        last result and never fails the update."""
        day_start = dt_util.start_of_local_day(now)
        if (
            self._measured_today_at is not None
            and self._measured_today is not None
            and self._measured_today["start"] == day_start
            and now - self._measured_today_at < timedelta(minutes=15)
        ):
            return
        if usage_source == USAGE_SOURCE_CONSUMPTION_SENSOR:
            terms = ([e for e in conf.get(CONF_USAGE_CONSUMPTION_ENTITIES, []) or [] if e], [], [], None, None)
        elif usage_source == USAGE_SOURCE_ENERGY_DASHBOARD and self._energy_dashboard_sources:
            src = self._energy_dashboard_sources
            terms = (src["import"], src["export"], src["solar"], src["battery_charge"], src["battery_discharge"])
        else:
            return
        if not terms[0]:
            return
        ids = [*terms[0], *terms[1], *terms[2], *(terms[3] or []), *(terms[4] or [])]
        self._measured_today_at = now
        try:
            hourly_sums = await async_fetch_hourly_sums(
                self.hass, ids, day_start - timedelta(hours=1), now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            )
            hours = measured_hours(hourly_sums, *terms, day_start, now)
        except Exception as err:  # noqa: BLE001 - display only
            _LOGGER.debug("ESS Manager: could not read today's measured hours: %s", err)
            return
        self._measured_today = {"start": day_start, **hours}

    def _history_today(self, now: datetime, solar_points: list[dict]) -> Optional[dict[str, Any]]:
        """The Status sensor's history_today attribute (as of v0.5.1): today's
        complete hours since local midnight - measured household usage and
        solar production (the solar forecast for those hours when no solar
        statistic is known). None until the usage forecast has run today."""
        measured = self._measured_today
        day_start = dt_util.start_of_local_day(now)
        if not measured or measured["start"] != day_start:
            return None
        usage = measured["usage"]
        solar = measured["solar"]
        solar_measured = solar is not None
        if solar is None:
            solar = forecasting.build_solar_forecast(solar_points, day_start, len(usage))
        return {
            "start": day_start.isoformat(),
            "usage": usage,
            "solar": solar,
            "solar_measured": solar_measured,
        }

    async def _async_get_energy_dashboard_usage_forecast(self, conf: dict[str, Any], now: datetime) -> list[float]:
        """The h0..h120 usage forecast via the energy-balance identity
        (usage_forecast.compute_usage_forecast), with the grid/solar/battery
        statistics read live from Home Assistant's own Energy dashboard
        configuration (energy_source.py). Re-read on every recompute (not
        copied at setup), so an edit to the Energy dashboard is picked up
        automatically. Cached and recomputed once per hour; on a statistics
        error it falls back to the last good cache. What was actually
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
            self._set_usage_history([HISTORY_NONE] * FORECAST_HOURS, lookback_weeks)
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
            self._set_usage_history([HISTORY_NONE] * FORECAST_HOURS, lookback_weeks)
            return [0.0] * FORECAST_HOURS

        self._usage_forecast_cache, hour_sources = compute_usage_forecast_detailed(
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
        self._set_usage_history(hour_sources, lookback_weeks)
        return self._usage_forecast_cache

    async def _async_buy_prices(self, all_price: list[float]) -> tuple[float, list[float]]:
        """(tariff, buy prices) from the "Transport tariff" number entity
        (default 0 = no transport: the buy prices are the prices)."""
        tariff = max(self.get_number(NUM_TRANSPORT_TARIFF, 0.0), 0.0)
        if not tariff:
            return 0.0, list(all_price)
        if self._transport_factors is None:
            try:
                self._transport_factors = await self.hass.async_add_executor_job(transport.load_factors)
            except (OSError, ValueError) as err:
                # Shipped with the integration and unit-tested, so this
                # shouldn't happen - but never stop planning over it.
                _LOGGER.error("ESS Manager: could not read transport_factors.json (%s) - using factor 1.0", err)
                self._transport_factors = {month: [1.0] * 24 for month in range(1, 13)}
        times = transport.unit_local_times(dt_util.start_of_local_day(), len(all_price), dt_util.now().tzinfo)
        factors = transport.unit_factors(times, self._transport_factors)
        return tariff, transport.compute_buy_prices(all_price, tariff, factors)

    def _set_usage_history(self, hour_sources: list[str], lookback_weeks: int) -> None:
        """Store how the usage forecast was filled in, and log it once
        whenever the status changes (not every hour)."""
        history = summarize_usage_history(hour_sources, lookback_weeks)
        self._usage_history = history
        status = history["status"]
        if status == self._usage_history_logged_status:
            return
        if history["hours_without_history"]:
            _LOGGER.warning(
                "ESS Manager (%s): %s of the next %s hours have no household usage history yet and count "
                "as 0 kWh - usually a new statistic or sensor; this fills in as history builds up",
                self.entry.title,
                history["hours_without_history"],
                history["forecast_hours"],
            )
        elif history["hours_recent_days"]:
            _LOGGER.warning(
                "ESS Manager (%s): %s of the next %s hours have no same-weekday usage history yet and use "
                "the average of the last days instead - usually a statistic or sensor younger than a week",
                self.entry.title,
                history["hours_recent_days"],
                history["forecast_hours"],
            )
        elif self._usage_history_logged_status is not None:
            _LOGGER.info("ESS Manager (%s): usage forecast has full same-weekday history again", self.entry.title)
        self._usage_history_logged_status = status

    def _update_usage_history_issue(self) -> None:
        """Repairs notice while more than half of the forecast has no usage
        history at all; removed by itself once history is there."""
        issue_id = f"{USAGE_HISTORY_ISSUE}_{self.entry.entry_id}"
        if not self.usage_history_mostly_missing():
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        history = self._usage_history or {}
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=USAGE_HISTORY_ISSUE,
            translation_placeholders={
                "entry_title": self.entry.title,
                "hours": str(history.get("hours_without_history", 0)),
                "total": str(history.get("forecast_hours", 0)),
            },
            learn_more_url="https://github.com/MisterX-RC/ESS-manager-HA#household-usage-forecast",
        )

    @property
    def usage_history(self) -> Optional[dict[str, Any]]:
        return self._usage_history

    def usage_history_mostly_missing(self) -> bool:
        """More than half the forecast hours have no usage history at all
        (the Repairs notice condition)."""
        history = self._usage_history
        return bool(
            history
            and history["status"] == HISTORY_STATUS_NONE
            and history["hours_without_history"] * 2 > history["forecast_hours"]
        )

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
        # Buying costs price + (transport tariff x factor) per unit; selling
        # is the plain price (as of v0.4.0 - see transport.py).
        transport_tariff, buy_price = await self._async_buy_prices(all_price)

        # Only the two supported sources exist (v0.3.0). Anything else - an
        # entry still on a removed source that the v2 migration couldn't
        # switch automatically - stops planning with a clear error (and a
        # Repairs issue, see __init__.py) rather than planning with zero
        # household usage, which would schedule wildly wrong sales.
        usage_source = conf.get(CONF_USAGE_SOURCE)
        if usage_source == USAGE_SOURCE_CONSUMPTION_SENSOR:
            usage_forecast = await self._async_get_measured_usage_forecast(conf, now)
        elif usage_source == USAGE_SOURCE_ENERGY_DASHBOARD:
            usage_forecast = await self._async_get_energy_dashboard_usage_forecast(conf, now)
        else:
            raise UpdateFailed(
                f"Household usage source '{usage_source}' is no longer supported - choose the Energy "
                "dashboard or a consumption sensor in Configure (see Settings > Repairs)"
            )
        self._update_usage_history_issue()
        await self._async_refresh_measured_today(conf, usage_source, now)

        solar_points: list[list[dict]] = []
        for entity_id in conf.get(CONF_SOLAR_FORECAST_ENTITIES, []):
            state = self.hass.states.get(entity_id)
            if state is not None:
                solar_points.append(list(state.attributes.get("detailedHourly") or []))

        control_settings = ControlSettings(conf)
        if conf.get(CONF_GRID_SETPOINT_ENTITY):
            # A sensor, number or input_number (as of v0.3.4 - e.g. the
            # input_number an external automation writes), converted to W
            # from its own unit (kW input_numbers are common) and flipped
            # when its polarity is "positive = discharge".
            setpoint_state = self.hass.states.get(conf.get(CONF_GRID_SETPOINT_ENTITY))
            raw = _get_float_state(self.hass, conf.get(CONF_GRID_SETPOINT_ENTITY), default=0.0)
            unit = setpoint_state.attributes.get("unit_of_measurement") if setpoint_state else None
            setpoint_w = control.readback_to_watts(
                raw, unit, conf.get(CONF_GRID_SETPOINT_SIGN) or DEFAULT_GRID_SETPOINT_SIGN
            )
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
        # Two minimum SOCs (as of v0.4.2): the solar-deficit one (the
        # original "Minimum SOC") and the solar-surplus one - which applies
        # is decided below, from the raw battery forecast.
        min_soc_deficit_percent = self.get_number(NUM_MIN_SOC_PERCENT, 15.0)
        surplus_entity = self._numbers.get(NUM_MIN_SOC_SURPLUS_PERCENT)
        if surplus_entity is not None:
            surplus_entity.seed_if_unset(min_soc_deficit_percent)
        min_soc_surplus_percent = self.get_number(NUM_MIN_SOC_SURPLUS_PERCENT, min_soc_deficit_percent)
        max_soc_percent = self.get_number(NUM_MAX_SOC_PERCENT, 110.0)
        charge_speed_kw = self.get_number(NUM_CHARGE_SPEED_KW, 7.0)
        discharge_speed_kw = self.get_number(NUM_DISCHARGE_SPEED_KW, 10.0)
        # Not a `number` entity - a fixed hardware property set/edited via the
        # config/options flow, not a dashboard-adjustable setpoint.
        max_battery_charge_speed_kw = conf.get(CONF_MAX_BATTERY_CHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_CHARGE_SPEED_KW)
        max_battery_discharge_speed_kw = conf.get(
            CONF_MAX_BATTERY_DISCHARGE_SPEED_KW, DEFAULT_MAX_BATTERY_DISCHARGE_SPEED_KW
        )
        # Inverter/battery efficiency (as of v0.4.3), also from the flow:
        # charged energy x efficiency reaches the battery, energy taken out
        # / efficiency leaves it - in the forecast and in every plan's
        # battery-side rates (the setpoints sent stay the grid-side speeds).
        charge_efficiency = _efficiency(conf.get(CONF_CHARGE_EFFICIENCY_PERCENT, DEFAULT_CHARGE_EFFICIENCY_PERCENT))
        discharge_efficiency = _efficiency(
            conf.get(CONF_DISCHARGE_EFFICIENCY_PERCENT, DEFAULT_DISCHARGE_EFFICIENCY_PERCENT)
        )
        negative_price_charge_speed_kw = self.get_number(NUM_NEGATIVE_PRICE_CHARGE_SPEED_KW, charge_speed_kw * 2)
        spike_discharge_speed_kw = self.get_number(NUM_SPIKE_DISCHARGE_SPEED_KW, discharge_speed_kw * 1.5)
        negative_price_threshold = self.get_number(NUM_NEGATIVE_PRICE_THRESHOLD, -0.20)
        spike_margin = self.get_number(NUM_SPIKE_MARGIN, 0.40)
        minimum_charge_target_kwh = self.get_number(NUM_MINIMUM_CHARGE_TARGET_KWH, 5.0)
        # the shortest charge block, in quarters (as of 2026.10.6)
        min_charge_units = max(int(round(self.get_number(NUM_MINIMUM_CHARGE_MINUTES, 30.0) / 15)), 1)
        safety_buffer_percent = self.get_number(NUM_SAFETY_BUFFER_PERCENT, 5.0)
        planning_horizon_hours = int(self.get_number(NUM_PLANNING_HORIZON_HOURS, 72))
        full_charge_interval_days = self.get_number(NUM_FULL_CHARGE_INTERVAL_DAYS, 14.0)
        full_charge_max_hold_minutes = self.get_number(NUM_FULL_CHARGE_MAX_HOLD_MINUTES, 120.0)
        # Live-adjustable, unlike max_battery_charge/discharge_speed_kw above -
        # a calibration figure meant to be dialed in/tweaked from a dashboard,
        # not a fixed hardware property, so it's an ordinary `number` entity.
        full_charge_target_voltage = self.get_number(NUM_FULL_CHARGE_TARGET_VOLTAGE, DEFAULT_FULL_CHARGE_TARGET_VOLTAGE)

        # Kept on top of the low threshold when selling (see
        # compute_high_discharge_plan) - % of capacity, like min/max SOC.
        safety_buffer_kwh = round((safety_buffer_percent / 100) * capacity_kwh, 2)
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
            net_energy,
            battery_now_kwh,
            now,
            max_battery_charge_speed_kw,
            max_battery_discharge_speed_kw,
            charge_efficiency=charge_efficiency,
            discharge_efficiency=discharge_efficiency,
        )

        # Solar deficit or surplus (as of v0.4.2): does the raw forecast run
        # empty before solar fills the battery? That decides which minimum
        # SOC - and so the low threshold every plan uses - applies.
        # Between 0% and 100% all along: the mode stays what it was (as of
        # 2026.10.8 - also across a restart, see _async_restore).
        solar_mode = forecasting.compute_solar_mode(battery_forecast, capacity_kwh, self._last_solar_mode)
        min_soc_percent = (
            min_soc_deficit_percent
            if solar_mode["mode"] == forecasting.SOLAR_MODE_DEFICIT
            else min_soc_surplus_percent
        )
        solar_mode["min_soc_percent"] = min_soc_percent
        solar_mode["min_soc_deficit_percent"] = min_soc_deficit_percent
        solar_mode["min_soc_surplus_percent"] = min_soc_surplus_percent
        low_threshold_kwh = round((min_soc_percent / 100) * capacity_kwh, 2)
        # In deficit mode the surplus minimum stays the hard floor below the
        # (higher) deficit minimum: the band between them isn't urgent and is
        # only charged as far as it fits (as of v0.5.13; see
        # plans.compute_low_charge_plan's floor_kwh).
        deficit_floor_kwh = (
            round((min_soc_surplus_percent / 100) * capacity_kwh, 2)
            if solar_mode["mode"] == forecasting.SOLAR_MODE_DEFICIT and min_soc_surplus_percent < min_soc_deficit_percent
            else None
        )

        current_price_unit = (now.hour * 4) + (now.minute // 15)

        # What a grid charge really adds to the battery per quarter (as of
        # 2026.10.4): the battery's max charge speed minus the solar already
        # charging it, so the charge plans skip quarters the sun already fills
        # and make their windows long enough.
        rate_units = max(len(all_price), 192)
        charge_rates = forecasting.grid_charge_rates(
            net_energy, now, charge_speed_kw, max_battery_charge_speed_kw, rate_units,
            charge_efficiency, discharge_efficiency,
        )
        negative_charge_rates = forecasting.grid_charge_rates(
            net_energy, now, negative_price_charge_speed_kw, max_battery_charge_speed_kw, rate_units,
            charge_efficiency, discharge_efficiency,
        )

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

        # A setting changed since the last cycle: check running windows
        # again (see request_replan). Taken here, cleared once the plans are
        # done, so a cycle that fails before this point doesn't lose it.
        replan_seen = self._replan_requested
        replan = replan_seen > 0
        if replan:
            _LOGGER.info("ESS Manager (%s): a setting changed - re-planning, running windows included", self.entry.title)
        # A switch between solar surplus and deficit changes the minimum SOC
        # every plan works with, so it re-plans running windows too (v0.5.13).
        if self._last_solar_mode is not None and solar_mode["mode"] != self._last_solar_mode:
            _LOGGER.info(
                "ESS Manager (%s): solar mode %s -> %s - re-planning, running windows included",
                self.entry.title, self._last_solar_mode, solar_mode["mode"],
            )
            replan = True
        self._last_solar_mode = solar_mode["mode"]

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
                buy_price=buy_price,
                charge_efficiency=charge_efficiency,
                replan=replan,
                charge_rates=charge_rates,
                min_charge_units=min_charge_units,
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

        # The negative price and spike plans size their charges and sales on
        # the level the battery will really be at, so they get the forecast
        # clipped at 100% too (as of 2026.10.1): after a day that fills it,
        # the energy over the top is gone. The chain of composed forecasts
        # below (for the sale plan) stays unclipped.
        battery_forecast_clipped, _ = forecasting.clip_at_capacity(battery_forecast, battery_now_kwh, upper_limit_kwh)

        # -- negative price plan -------------------------------------------------
        if conf.get(CONF_ENABLE_NEGATIVE_PRICE_PLAN, True):
            self._negative_price_plan = plans.compute_negative_price_plan(
                self._negative_price_plan,
                current_price_unit,
                now,
                all_price,
                negative_price_threshold,
                battery_forecast_clipped,
                discharge_speed_kw,
                negative_price_charge_speed_kw,
                low_threshold_kwh,
                # the most it can charge to: max SOC, but never above 100% -
                # the battery can't hold more (as of 2026.10.1; up to then a
                # max SOC of 110% let it plan 10% that can't go in)
                min(high_threshold_kwh, upper_limit_kwh),
                buy_price=buy_price,
                charge_efficiency=charge_efficiency,
                discharge_efficiency=discharge_efficiency,
                replan=replan,
                charge_rates=negative_charge_rates,
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
                battery_forecast_clipped,
                usage_forecast,
                low_threshold_kwh,
                upper_limit_kwh,
                high_threshold_kwh,
                spike_margin,
                charge_speed_kw,
                spike_discharge_speed_kw,
                self._negative_price_plan,
                minimum_charge_target_kwh,
                buy_price=buy_price,
                charge_efficiency=charge_efficiency,
                discharge_efficiency=discharge_efficiency,
                replan=replan,
                charge_rates=charge_rates,
            )
        else:
            self._spike_plan = {"active": False}

        forecast_with_spike = plans.compose_forecast_with_spike(
            forecast_with_negative_price, self._spike_plan, current_price_unit, now, high_threshold_kwh - 0.01
        )

        # -- low charge / high discharge plans -----------------------------------
        # The charge plan works with the forecast clipped at 100% (as of
        # 2026.10.1): energy over the top goes to the grid, so after a day that
        # fills the battery the next dip starts from 100%, not from the running
        # sum. How much still fits is measured against the unclipped peak; the
        # sale plan below keeps the unclipped forecast (its highest point is
        # what it sells off).
        forecast_with_spike_clipped, _ = forecasting.clip_at_capacity(forecast_with_spike, battery_now_kwh, upper_limit_kwh)
        horizon_peak_kwh = max(forecast_with_spike[0 : planning_horizon_hours + 1] or [battery_now_kwh])
        self._low_charge_plan = plans.compute_low_charge_plan(
            self._low_charge_plan,
            current_price_unit,
            forecast_with_spike_clipped,
            now,
            charge_speed_kw,
            low_threshold_kwh,
            minimum_charge_target_kwh,
            upper_limit_kwh,
            usage_forecast,
            all_price,
            planning_horizon_hours,
            battery_now_kwh,
            high_threshold_kwh=high_threshold_kwh,
            buy_price=buy_price,
            charge_efficiency=charge_efficiency,
            discharge_efficiency=discharge_efficiency,
            replan=replan,
            floor_kwh=deficit_floor_kwh,
            peak_kwh=horizon_peak_kwh,
            charge_rates=charge_rates,
            # charge up to the low threshold plus the same Safety buffer a
            # sale keeps (as of 2026.10.4)
            charge_buffer_kwh=safety_buffer_kwh,
            min_charge_units=min_charge_units,
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
            safety_buffer_kwh=safety_buffer_kwh,
            # A sale triggered by the max-SOC threshold brings the peak down
            # to 100% (as of v0.3.2), not to just under the threshold.
            sale_target_kwh=upper_limit_kwh,
            discharge_efficiency=discharge_efficiency,
            replan=replan,
        )
        if replan:
            # only what this cycle saw - a change made meanwhile still counts
            self._replan_requested = max(self._replan_requested - replan_seen, 0)

        battery_forecast_adjusted_uncapped = plans.compose_forecast_adjusted(
            forecast_with_spike,
            self._low_charge_plan,
            self._high_discharge_plan,
            current_price_unit,
            now,
            full=self._full_charge_plan,
            upper_limit_kwh=upper_limit_kwh,
            battery_now_kwh=battery_now_kwh,
        )
        # What the battery will really hold (never above 100%) - shown on the
        # cards - and the solar surplus: hours the battery is full or can't
        # take all the solar, so it goes to the grid (as of 2026.10.1).
        battery_forecast_adjusted, spill_full = forecasting.clip_at_capacity(
            battery_forecast_adjusted_uncapped, battery_now_kwh, upper_limit_kwh
        )
        eff = charge_efficiency if charge_efficiency > 0 else 1.0
        solar_surplus = forecasting.solar_surplus_windows(
            [v / eff for v in spill_full],
            forecasting.rate_spill(net_energy, now, max_battery_charge_speed_kw, charge_efficiency),
            now,
        )

        # For "Solar export" (as of 2026.10.3): the last quarter of the hour
        # the forecast (with the plans) reaches 100%, and whether there's
        # solar left over right now.
        hour0_unit = current_price_unit - (now.minute // 15)
        full_hour = next(
            (h for h, v in enumerate(battery_forecast_adjusted) if v >= upper_limit_kwh - 0.01), None
        )
        full_unit = hour0_unit + full_hour * 4 + 3 if full_hour is not None else None
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
            full_unit=full_unit,
            solar_surplus_now=bool(net_energy) and net_energy[0] > 0,
        )

        charge_kwh, charge_start_text, charge_stop_text = display.charge_display(
            self._full_charge_plan, self._negative_price_plan, self._spike_plan, self._low_charge_plan, current_price_unit, now
        )
        discharge_kwh, discharge_start_text, discharge_stop_text = display.discharge_display(
            self._negative_price_plan, self._spike_plan, self._high_discharge_plan, current_price_unit, now
        )
        # The Buy / Sell blocks of the status card (as of v0.5.0).
        card_plans = display.card_plans(
            self._full_charge_plan,
            self._negative_price_plan,
            self._spike_plan,
            self._low_charge_plan,
            self._high_discharge_plan,
            current_price_unit,
            now,
            battery_now_kwh,
            capacity_kwh,
            battery_forecast_adjusted,
            # The live readings for the balancing wait (as of v0.5.11).
            {
                "max_hold_minutes": full_charge_max_hold_minutes,
                "voltage_diff_mv": voltage_diff,
                "balance_threshold_mv": plans.BALANCE_THRESHOLD_MV,
                "battery_voltage": battery_voltage,
                "target_voltage": full_charge_target_voltage,
            },
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
            # The Battery action sensor's state: the control action, except
            # "balancing" while the full charge plan holds at 100% (still a
            # charge for direct control; as of v0.5.11).
            "battery_action": (
                "balancing"
                if control_action == control.ACTION_CHARGE
                and (self._full_charge_plan or {}).get("active")
                and (self._full_charge_plan or {}).get("phase") == "holding"
                else control_action
            ),
            "card_plans": card_plans,
            "control_power_kw": round(control_power_kw, 3),
            "control": self.controller.as_attribute(control_settings, control_action, control_power_kw),
            "battery_energy_kwh": battery_now_kwh,
            "battery_soc_percent": soc_now_percent,
            "low_threshold_kwh": low_threshold_kwh,
            "solar_mode": solar_mode,
            "high_threshold_kwh": high_threshold_kwh,
            "capacity_kwh": capacity_kwh,
            "current_price_unit": current_price_unit,
            "all_price": all_price,
            # What buying costs per unit: price + (transport tariff x
            # factor) - the same as all_price without a tariff (v0.4.0).
            "all_buy_price": buy_price,
            "transport_tariff": transport_tariff,
            # Where the "tomorrow" half of all_price begins (i.e. len(today's
            # own price list)) - lets a dashboard split all_price back into
            # its today/tomorrow halves by index without guessing a 96-unit
            # boundary (which can be wrong on a DST transition day), so the
            # price chart can be built entirely from this sensor instead of
            # also referencing the raw price entity directly.
            "today_price_units": len(today_price),
            "solar_120h": solar_forecast,
            # Today's measured hours for the battery card (as of v0.5.1).
            "history_today": self._history_today(now, merged_solar_points),
            "energy_usage_120h": usage_forecast,
            "usage_source": usage_source,
            "usage_history": self._usage_history,
            "energy_dashboard_sources": (
                self._energy_dashboard_sources if usage_source == USAGE_SOURCE_ENERGY_DASHBOARD else None
            ),
            "net_energy_120h": net_energy,
            "battery_forecast": battery_forecast,
            "battery_forecast_with_negative_price": forecast_with_negative_price,
            "battery_forecast_with_spike": forecast_with_spike,
            "battery_forecast_adjusted": battery_forecast_adjusted,
            "battery_forecast_adjusted_uncapped": battery_forecast_adjusted_uncapped,
            "solar_surplus": solar_surplus,
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
