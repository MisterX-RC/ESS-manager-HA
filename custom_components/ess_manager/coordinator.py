"""DataUpdateCoordinator that ties the forecasting pipeline and the five
planning engines together every minute (and at every quarter boundary), reading live entity state and
the user-tunable `number` entities, and persisting the plans' self-locking
state (and the full-charge-plan's "last time the battery was full" tracker)
across Home Assistant restarts.
"""
from __future__ import annotations

import asyncio
import functools
import time
from collections import deque

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import control, display, forecasting, plans, transport, units
from .ev_runtime import EvRuntime
from . import ev_charger as evc, ev_notify as evn
from . import heatpump
from .heatpump_runtime import HeatPumpRuntime
from . import heatpump_house
from . import accuracy
from .accuracy_runtime import AccuracyRuntime
from .problems import ProblemTracker, below_minimum
from . import floor_control as fc
from .const import (
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_VOLTAGE_ENTITY,
    CONF_DAYS_SINCE_FULL_CHARGE_ENTITY,
    CONF_ENABLE_FULL_CHARGE_PLAN,
    CONF_ENABLE_NEGATIVE_PRICE_PLAN,
    CONF_ENABLE_SPIKE_PLAN,
    CONF_EV_CARS,
    CONF_EV_CHARGER,
    CONF_EV_NOTIFY,
    CONF_EV_VICTRON_DEVICE,
    EV_CHARGER_VICTRON,
    CONF_HP_COOL_ENTITIES,
    CONF_HP_ENABLED,
    CONF_HP_HEAT_ENTITIES,
    CONF_HP_INDOOR_ENTITY,
    CONF_HP_COP_ENTITY,
    CONF_NIGHT_LIMIT_ENABLED,
    CONF_NIGHT_CHARGE_SPEED_KW,
    CONF_NIGHT_DISCHARGE_SPEED_KW,
    DEFAULT_NIGHT_CHARGE_SPEED_KW,
    DEFAULT_NIGHT_DISCHARGE_SPEED_KW,
    CONF_HP_BUFFER_ENABLED,
    CONF_FLOOR_COOL_CLIMATE_ENTITY,
    CONF_FLOOR_COOL_SWITCH_ENTITY,
    CONF_FLOOR_DEMAND_ENTITY,
    CONF_FLOOR_ENABLED,
    CONF_FLOOR_HELPER_ENTITY,
    CONF_FLOOR_POWER_ENTITY,
    CONF_FLOOR_PUMP_ENTITY,
    CONF_FLOOR_RETURN_ENTITY,
    CONF_FLOOR_SETPOINT_ENTITY,
    CONF_FLOOR_SLAB_ENTITY,
    CONF_FLOOR_SUPPLY_ENTITY,
    FLOOR_REQUIRED,
    CONF_HP_HOURLY_ENABLED,
    HP_STEERING_PLAN,
    NUM_HP_DAY_TEMP,
    NUM_HP_NIGHT_TEMP,
    NUM_HP_BUFFER_DELTA,
    NUM_HP_DAY_FROM,
    NUM_HP_NIGHT_FROM,
    CONF_HP_METER,
    CONF_HP_OUTDOOR_ENTITY,
    CONF_HP_SETPOINT_ENTITY,
    CONF_HP_TOTAL_ENTITY,
    CONF_HP_WEATHER_ENTITY,
    CONF_HP_WIND_DIR_ENTITY,
    CONF_HP_WIND_ENTITY,
    DEFAULT_HP_METER,
    HP_METER_NONE,
    HP_METER_SEPARATE,
    HP_METER_TOTAL,
    CONF_EV_ENABLED,
    CONF_EV_ENERGY_ENTITY,
    CONF_EV_MAX_CURRENT,
    CONF_EV_MIN_CURRENT,
    CONF_EV_PHASES,
    CONF_EV_POWER_ENTITY,
    CONF_EV_PREDICT,
    DEFAULT_EV_MAX_CURRENT,
    DEFAULT_EV_MIN_CURRENT,
    DEFAULT_EV_PHASES,
    DEFAULT_EV_PREDICT,
    EV_DAYS,
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
    DECISION_HISTORY_HOURS,
    DECISION_HISTORY_MAX,
    USAGE_SOURCE_CONSUMPTION_SENSOR,
    USAGE_SOURCE_ENERGY_DASHBOARD,
)
from .controller import ControlSettings, EssController
from .energy_source import async_get_energy_prefs
from .statistics_source import async_fetch_hourly_means, async_fetch_state_changes, async_fetch_hourly_sums, async_last_recorded_state
from .usage_forecast import (
    _week_sample,
    HISTORY_NONE,
    HISTORY_STATUS_NONE,
    compute_usage_forecast_detailed,
    compute_usage_forecast_from_consumption_detailed,
    energy_prefs_to_sources,
    ev_hourly_history,
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

# The first minutes after a (re)start (as of 2026.10.14): no plans while a
# solar forecast sensor or the usage statistics aren't there yet - planning
# with "no sun" or "no household usage" could start a wrong charge or sale
# right away. After this it plans with what there is, as before.
STARTUP_GRACE = timedelta(minutes=10)


def ev_energy_entity(conf: dict[str, Any]) -> Optional[str]:
    """The car charger's energy statistic when the EV feature is on (as of
    2026.10.11) - taken out of the household usage history - else None."""
    if not conf.get(CONF_EV_ENABLED):
        return None
    return conf.get(CONF_EV_ENERGY_ENTITY) or None


def hp_meter(conf: dict[str, Any]) -> Optional[str]:
    """The heat pump's metering when the heat pump model is on (as of
    2026.10.16), else None."""
    if not conf.get(CONF_HP_ENABLED):
        return None
    return conf.get(CONF_HP_METER) or DEFAULT_HP_METER


def hp_energy_entities(conf: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(heating entities, cooling entities) - the total sensor counts as
    heating; none for 'no own metering'."""
    meter = hp_meter(conf)
    if meter == HP_METER_SEPARATE:
        return [e for e in conf.get(CONF_HP_HEAT_ENTITIES) or [] if e], [e for e in conf.get(CONF_HP_COOL_ENTITIES) or [] if e]
    if meter == HP_METER_TOTAL and conf.get(CONF_HP_TOTAL_ENTITY):
        return [conf[CONF_HP_TOTAL_ENTITY]], []
    return [], []


def _float_state(state: Any) -> Optional[float]:
    try:
        return float(state.state)
    except (TypeError, ValueError, AttributeError):
        return None


WIND_FACTORS = {"m/s": 1.0, "km/h": 1 / 3.6, "mph": 0.44704, "kn": 0.514444, "ft/s": 0.3048}


def _state_in_unit(hass: HomeAssistant, entity_id: Optional[str], kilo_units: tuple[str, ...], factor: float) -> Optional[float]:
    """An entity's numeric state; multiplied by `factor` when its unit is
    one of `kilo_units` (kW -> W, Wh -> kWh, ...). None when unknown."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in (None, "unknown", "unavailable"):
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    if state.attributes.get("unit_of_measurement") in kilo_units:
        value *= factor
    return value


def _efficiency(percent: Any) -> float:
    """A 50-100 % efficiency setting as a 0.5-1.0 fraction (anything
    unreadable counts as 100 %, i.e. no losses)."""
    try:
        value = float(percent)
    except (TypeError, ValueError):
        return 1.0
    return min(max(value, 50.0), 100.0) / 100.0


def _float_or(value: Any, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


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
        # A (re)start plans everything afresh, running windows included
        # (as of 2026.10.14): a stored window may stem from other settings
        # or another day.
        self._replan_requested = 1
        self._started_logged = False
        self._solar_format_warned: set[str] = set()
        # Decision history for the diagnostics download (as of 2026.10.22):
        # only the moments the action, setpoint, status or control error
        # changed, kept for 24 hours (in memory - starts empty after a restart).
        self._decisions: deque[dict[str, Any]] = deque(maxlen=DECISION_HISTORY_MAX)
        self._last_solar_mode: Optional[str] = None

        # Statistics-based usage-forecast cache - recomputed once per hour,
        # on the first cycle after the hour changes, not every cycle
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
        # See STARTUP_GRACE: when this run started, and whether the usage
        # forecast is a stand-in (statistics couldn't be read, nothing cached).
        self._started_at = dt_util.now()
        self._usage_missing = False
        # The electric car (as of 2026.10.11) - see ev_runtime.py.
        self.ev = EvRuntime()
        # the Victron charger (as of 2026.10.27): what was written to it
        # (entity -> (value, monotonic time)), its last error, and the grid
        # setpoint offset that keeps the house battery out of a grid window
        self._ev_writes: dict[str, tuple[Any, float]] = {}
        self._ev_error: Optional[str] = None
        self._ev_offset_w = 0.0
        self._ev_target: Optional[dict[str, Any]] = None
        # The heat pump model (as of 2026.10.16) - see heatpump_runtime.py.
        self.hp = HeatPumpRuntime()
        # whether the cached usage forecast left the heat pump out
        self._usage_hp_subtracted = False
        self._hp_weather: dict[str, Any] = {}
        self._hp_weather_at: Optional[datetime] = None
        self._hp_backfill_tried_at: Optional[datetime] = None
        self._hp_hourly: list[dict[str, Any]] = []
        self._hp_wind_factor = 1.0
        self._hp_thermal_tried_at = 0.0
        self._hp_demand_day: Optional[str] = None
        # step 2's switch on the card (restored by switch.py)
        self.hp_steering_on = False
        # The forecast check (as of 2026.10.22) - accuracy_runtime.py; the
        # "Automatic safety buffer" switch sets auto_buffer_on.
        self.acc = AccuracyRuntime()
        # Problem notices in Settings > Repairs (as of 2026.10.23) - problems.py.
        self.problems = ProblemTracker(hass, entry)
        # Floor control (as of 2026.10.23) - floor_control.py; the "Floor
        # control" select on the heat pump card sets floor_mode.
        self.floor = fc.FloorRuntime()
        self.floor_mode = fc.MODE_WATCH
        self.floor_mode_entity_id: Optional[str] = None
        self.auto_buffer_on = False
        self.auto_buffer_entity_id: Optional[str] = None
        self.hp_steering_entity: Any = None

    def control_settings(self) -> ControlSettings:
        return ControlSettings({**self.entry.data, **self.entry.options})

    def plan_enabled(self, plan: str) -> bool:
        """Whether a plan's Configure switch (CONF_ENABLE_*) is on - same
        defaults as the update cycle uses."""
        conf = {**self.entry.data, **self.entry.options}
        if plan == HP_STEERING_PLAN:
            return bool(conf.get(CONF_HP_ENABLED) and conf.get(CONF_HP_HOURLY_ENABLED) and conf.get(CONF_HP_BUFFER_ENABLED))
        return bool(conf.get(plan, PLAN_ENABLED_DEFAULTS[plan]))

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

    # -- problem notices (as of 2026.10.23) --------------------------------------
    def _report_input_problem(self, conf: dict[str, Any], now: datetime) -> None:
        """The battery SOC or the price sensor without a usable value."""
        bad: Optional[str] = None
        soc_id = conf.get(CONF_BATTERY_SOC_ENTITY)
        soc = self.hass.states.get(soc_id) if soc_id else None
        try:
            soc_ok = soc is not None and float(soc.state) == float(soc.state)
        except (TypeError, ValueError):
            soc_ok = False
        if not soc_ok:
            bad = soc_id or "battery SOC"
        else:
            price_id = conf.get(CONF_PRICE_ENTITY)
            price = self.hass.states.get(price_id) if price_id else None
            if price is None or price.state in ("unavailable", "unknown") or not price.attributes.get("today"):
                bad = price_id or "price"
        self.problems.report("input_unavailable", bad is not None, now, {"entity": bad or ""})

    def _report_control_problem(self, now: datetime) -> None:
        """Direct control that can't send its setpoint."""
        settings = self.control_settings()
        error = self.controller.last_error
        active = bool(settings.active and self.controller.enabled and error)
        reason = ""
        if active:
            if "doesn't exist" in error:
                reason = "the entity doesn't exist (renamed or removed?)"
            elif error.endswith("is unavailable"):
                reason = "the entity is unavailable"
            else:
                reason = error.split(" failed: ", 1)[-1]
        self.problems.report("control_write_failed", active, now, {"target": settings.target or "", "reason": reason})

    # -- decision history (diagnostics, as of 2026.10.22) -----------------------
    _DECISION_KEYS = ("action", "value", "status", "error", "sending", "night_limit")

    def _record_decision(self, entry: dict[str, Any]) -> None:
        """Keep `entry` when what it decides differs from the previous one;
        drop what's older than DECISION_HISTORY_HOURS."""
        now = dt_util.now()
        last = self._decisions[-1] if self._decisions else None
        if last is None or any(last.get(k) != entry.get(k) for k in self._DECISION_KEYS):
            self._decisions.append({"time": now.isoformat(timespec="seconds"), **entry})
        self._prune_decisions(now)

    def _prune_decisions(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=DECISION_HISTORY_HOURS)
        while self._decisions:
            ts = dt_util.parse_datetime(self._decisions[0]["time"])
            if ts is not None and ts >= cutoff:
                break
            self._decisions.popleft()

    def decision_history(self) -> list[dict[str, Any]]:
        """The last 24 hours of decisions, oldest first."""
        self._prune_decisions(dt_util.now())
        return list(self._decisions)

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
            self.ev.restore(data.get("ev"))
            self.hp.restore(data.get("hp"))
            self.acc.restore(data.get("accuracy"))
            self.floor.restore(data.get("floor"))
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

    def now(self) -> datetime:
        return dt_util.now()

    # -- the Victron EV charger (as of 2026.10.27) -------------------------------------
    def _victron_entities(self, device_id: Optional[str]) -> dict[str, str]:
        """The charger's Victron GX entities by role, found on its device by
        translation key (ev_charger.VICTRON_KEYS)."""
        if not device_id:
            return {}
        by_key = {v: k for k, v in evc.VICTRON_KEYS.items()}
        out: dict[str, str] = {}
        for entry in er.async_entries_for_device(er.async_get(self.hass), device_id):
            role = by_key.get(entry.translation_key or "")
            if role and not entry.disabled_by:
                out[role] = entry.entity_id
        return out

    def _victron_inputs(self, conf: dict[str, Any], ents: dict[str, str], now: datetime, buy_price: list[float]) -> dict[str, Any]:
        status_state = self.hass.states.get(ents.get("status", ""))
        status = status_state.state if status_state and status_state.state not in ("unknown", "unavailable") else None
        # A car is plugged in when the charger's Status isn't "disconnected".
        # Not its "Connected" entity (as of 2026.10.30): that's whether the
        # charger itself is connected to the GX, not the car - with it a car
        # was never seen as unplugged.
        if status is None:
            # the charger can't be read: keep what we had (no false unplug)
            connected = self.ev.flow is not None
        else:
            connected = status != evc.STATUS_DISCONNECTED
        notify = [s for s in (conf.get(CONF_EV_NOTIFY) or []) if self.hass.services.has_service("notify", s)]
        mode_state = self.hass.states.get(ents.get("mode", ""))
        current_state = self.hass.states.get(ents.get("current", ""))
        return {
            "connected": connected,
            "status": status,
            # when the Status last changed: the unplug time for the log
            "status_since": int(status_state.last_changed.timestamp()) if status_state is not None else None,
            "mode": mode_state.state if mode_state and mode_state.state not in ("unknown", "unavailable") else None,
            "set_current": _float_state(current_state) if current_state is not None else None,
            "power_w": _state_in_unit(self.hass, ents.get("power"), ("kW",), 1000.0),
            "entry_id": self.entry.entry_id,
            "language": evn.lang(self.hass.config.language),
            "notify": bool(notify),
            "notify_services": notify,
            "prices": list(buy_price),
            "price_start": int(units.local_midnight(now).timestamp()),
        }

    def _ev_grid_offset_kw(self, victron: dict[str, Any], ents: dict[str, str], now: datetime) -> float:
        """What the car takes now (kW) when it's in a grid window, else 0."""
        flow = self.ev.flow
        if not flow or flow.get("done") or not evc.in_windows(int(now.timestamp()), flow.get("windows") or []):
            return 0.0
        power_w = _state_in_unit(self.hass, ents.get("power"), ("kW",), 1000.0)
        if not power_w or power_w <= 0:
            return 0.0
        return round(power_w / 1000.0, 1)

    async def _async_ev_charger(
        self, conf: dict[str, Any], ents: dict[str, str], now: datetime, control_settings: ControlSettings
    ) -> None:
        """Drive the charger: mode, current and start/stop as the plugged-in
        car's plan says. Paused while direct control's Automatic control
        switch is off. A value is sent when the plan's value changes (plug-in,
        a choice, a grid window starting or ending, done) - not again while
        it stays the same: what's changed on the charger itself in between
        (e.g. started by hand) is left alone (as of 2026.10.28; up to then
        it was put back every minute, so a charge started on the charger
        was stopped again). The values sent are kept in the flow (stored)."""
        target = evc.charger_target(
            self.ev.flow, int(now.timestamp()),
            float(conf.get(CONF_EV_MIN_CURRENT, DEFAULT_EV_MIN_CURRENT)),
            float(conf.get(CONF_EV_MAX_CURRENT, DEFAULT_EV_MAX_CURRENT)),
        )
        resting = False
        if target is None and self.ev.flow is None and self.ev.rest_charger:
            # unplugged: once back to rest (as of 2026.10.31)
            target = dict(evc.REST_TARGET)
            resting = True
        self._ev_target = target
        if target is None or (control_settings.active and not self.controller.enabled):
            return
        flow = self.ev.flow
        applied: dict[str, Any] = flow.setdefault("applied", {}) if flow is not None else {}
        calls: list[tuple[str, str, str, str, dict[str, Any], Any]] = []
        if applied.get("mode") != target["mode"]:
            mode_state = self.hass.states.get(ents.get("mode", ""))
            if mode_state is not None and target["mode"] in (mode_state.attributes.get("options") or [target["mode"]]):
                if mode_state.state == target["mode"]:
                    applied["mode"] = target["mode"]
                else:
                    calls.append(("mode", ents["mode"], "select", "select_option", {"option": target["mode"]}, target["mode"]))
        if target.get("current") is not None and applied.get("current") != target["current"]:
            cur_state = self.hass.states.get(ents.get("current", ""))
            if cur_state is not None:
                want = float(target["current"])
                lo, hi = cur_state.attributes.get("min"), cur_state.attributes.get("max")
                if lo is not None:
                    want = max(want, float(lo))
                if hi is not None:
                    want = min(want, float(hi))
                have = _float_state(cur_state)
                if have is not None and abs(have - want) < 0.5:
                    applied["current"] = target["current"]
                else:
                    calls.append(("current", ents["current"], "number", "set_value", {"value": want}, target["current"]))
        if applied.get("charge") != bool(target["charge"]):
            charge_state = self.hass.states.get(ents.get("charge", ""))
            if charge_state is not None and charge_state.state in ("on", "off"):
                if (charge_state.state == "on") == bool(target["charge"]):
                    applied["charge"] = bool(target["charge"])
                else:
                    service = "turn_on" if target["charge"] else "turn_off"
                    calls.append(("charge", ents["charge"], "switch", service, {}, bool(target["charge"])))
        mono = time.monotonic()
        pending = False
        for role, entity_id, domain, service, data, value in calls:
            last = self._ev_writes.get(entity_id)
            if last is not None and last[0] == value and mono - last[1] < 60:
                pending = True
                continue
            try:
                await asyncio.wait_for(
                    self.hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True), 10
                )
            except Exception as err:  # noqa: BLE001 - a failed write must not fail the cycle
                message = f"EV charger: {domain}.{service} on {entity_id} failed: {type(err).__name__}: {err}"
                if message != self._ev_error:
                    _LOGGER.warning("ESS Manager (%s): %s", self.entry.title, message)
                self._ev_error = message
                pending = True
                continue
            self._ev_writes[entity_id] = (value, mono)
            applied[role] = value
            self._ev_error = None
            _LOGGER.info("ESS Manager (%s): EV charger %s.%s %s %s (%s)", self.entry.title, domain, service, entity_id, data or "", target.get("why"))
        if resting and not pending:
            # back at rest (or already was): leave the charger alone from now on
            self.ev.rest_charger = False

    async def _async_ev_send(self) -> None:
        """The notifications the EV runtime queued (questions, plans)."""
        outbox, self.ev.outbox = self.ev.outbox, []
        services = (self.ev.ctx or {}).get("notify_services") or []
        for item in outbox:
            for service in services:
                try:
                    await self.hass.services.async_call("notify", service, item["payload"], blocking=False)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("ESS Manager (%s): notify.%s failed: %s", self.entry.title, service, err)

    async def async_ev_flush(self) -> None:
        """Send what the EV runtime queued outside a cycle (the card's plan)."""
        await self._async_ev_send()

    async def async_ev_action(self, action: Any, reply_text: Any) -> None:
        """A tap or reply on one of the EV notifications (the Companion
        app's mobile_app_notification_action event)."""
        parsed = evn.parse_action(action)
        if parsed is None or parsed[0] != self.entry.entry_id or not self.ev.ctx:
            return
        _, token, what = parsed
        changed = self.ev.answer(token, what, reply_text if isinstance(reply_text, str) else None, int(self.now().timestamp()))
        await self._async_ev_send()
        if changed:
            self.request_replan()
            await self.async_persist_state()
            await self.async_refresh()

    async def async_persist_state(self) -> None:
        """Store now (after an edit on the EV card), not only at the end of
        the next cycle."""
        if self._restored:
            await self._async_persist()

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
                "ev": self.ev.as_store(),
                "hp": self.hp.as_store(),
                "accuracy": self.acc.as_store(),
                "floor": self.floor.as_store(),
            }
        )

    # -- heat pump (as of 2026.10.16) ------------------------------------------
    def _hp_subtract_ids(self, conf: dict[str, Any]) -> list[str]:
        """The heat pump entities the usage history leaves out right now: only
        with its own metering and while the model is used."""
        heat, cool = hp_energy_entities(conf)
        return [*heat, *cool] if self.hp.subtract else []

    def _hp_key(self, conf: dict[str, Any]) -> str:
        heat, cool = hp_energy_entities(conf)
        return "|".join([hp_meter(conf) or "", ",".join(heat), ",".join(cool), conf.get(CONF_HP_OUTDOOR_ENTITY) or ""])

    def _hp_energy_ids(self, conf: dict[str, Any]) -> list[str]:
        """Statistics behind the journal's energy: the heat pump's own, or for
        'no own metering' the household usage."""
        heat, cool = hp_energy_entities(conf)
        if heat or cool:
            return [*heat, *cool]
        if conf.get(CONF_USAGE_SOURCE) == USAGE_SOURCE_CONSUMPTION_SENSOR:
            return [e for e in conf.get(CONF_USAGE_CONSUMPTION_ENTITIES, []) or [] if e]
        src = self._energy_dashboard_sources or {}
        return [*src.get("import", []), *src.get("export", []), *src.get("solar", []), *src.get("battery_charge", []), *src.get("battery_discharge", [])]

    async def _async_hp_rows(self, conf: dict[str, Any], first: date, last: date, tz) -> list[dict[str, Any]]:
        """Journal rows for first..last from the long-term statistics."""
        start = datetime.combine(first - timedelta(days=1), datetime.min.time(), tzinfo=tz)
        end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=tz) + timedelta(hours=1)
        heat, cool = hp_energy_entities(conf)
        solar_ids = list((self._energy_dashboard_sources or {}).get("solar", []))
        ev_entity = ev_energy_entity(conf)
        ids = [*self._hp_energy_ids(conf), *solar_ids, *([ev_entity] if ev_entity else [])]
        sums = await async_fetch_hourly_sums(self.hass, ids, start, end)
        indoor_id, from_stats = self._hp_indoor_source(conf)
        mean_ids = [conf.get(CONF_HP_OUTDOOR_ENTITY), conf.get(CONF_HP_WIND_ENTITY), indoor_id if from_stats else None]
        means = await async_fetch_hourly_means(self.hass, [m for m in mean_ids if m], start, end)
        if indoor_id and not from_stats:
            means[indoor_id] = self.hp.indoor_series()
        deltas = {k: heatpump.hourly_deltas(v) for k, v in sums.items()}
        parts: dict[str, dict[int, float]] = {}
        if heat or cool:
            heat_d = heatpump.add_series(*[deltas.get(e, {}) for e in heat]) if heat else {}
            cool_d = heatpump.add_series(*[deltas.get(e, {}) for e in cool]) if cool else {}
            energy = heatpump.add_series(*[x for x in (heat_d if heat else None, cool_d if cool else None) if x is not None])
            if heat and cool:
                parts = {"heat": heat_d, "cool": cool_d}
        else:
            if conf.get(CONF_USAGE_SOURCE) == USAGE_SOURCE_CONSUMPTION_SENSOR:
                energy = heatpump.add_series(*[deltas.get(e, {}) for e in self._hp_energy_ids(conf)])
            else:
                src = self._energy_dashboard_sources or {}
                energy = {}
                for epoch in range(int(start.timestamp()), int(end.timestamp()), 3600):
                    value = _week_sample(sums, src.get("import", []), src.get("export", []), src.get("solar", []),
                                         src.get("battery_charge") or None, src.get("battery_discharge") or None, epoch)
                    if value is not None:
                        energy[epoch] = max(value, 0.0)
            if ev_entity and ev_entity in deltas:
                ev_d = deltas[ev_entity]
                energy = {k: max(v - ev_d.get(k, 0.0), 0.0) for k, v in energy.items()}
        sun = heatpump.add_series(*[deltas.get(e, {}) for e in solar_ids]) if solar_ids else None
        return heatpump.build_rows(
            first, last, tz, energy, means.get(conf.get(CONF_HP_OUTDOOR_ENTITY)) or {}, parts,
            means.get(conf.get(CONF_HP_WIND_ENTITY)) if conf.get(CONF_HP_WIND_ENTITY) else None, sun,
            means.get(indoor_id) if indoor_id else None,
        )

    async def _async_hp_weather(self, conf: dict[str, Any], now: datetime, tz) -> dict[str, Any]:
        """The weather entity's forecast per day, read every 30 minutes."""
        entity_id = conf.get(CONF_HP_WEATHER_ENTITY)
        if not entity_id:
            return {}
        if self._hp_weather_at is not None and now - self._hp_weather_at < timedelta(minutes=30):
            return self._hp_weather
        self._hp_weather_at = now
        lists: dict[str, list] = {}
        for kind in ("hourly", "daily"):
            try:
                resp = await self.hass.services.async_call(
                    "weather", "get_forecasts", {"entity_id": entity_id, "type": kind}, blocking=True, return_response=True
                )
                lists[kind] = list(((resp or {}).get(entity_id) or {}).get("forecast") or [])
            except Exception as err:  # noqa: BLE001 - a weather entity without this forecast type
                _LOGGER.debug("ESS Manager: no %s forecast from %s: %s", kind, entity_id, err)
                lists[kind] = []
        state = self.hass.states.get(entity_id)
        unit = (state.attributes.get("wind_speed_unit") if state else None) or "km/h"
        self._hp_wind_factor = WIND_FACTORS.get(unit, 1.0)
        self._hp_hourly = lists["hourly"]
        self._hp_weather = heatpump.weather_days(lists["hourly"], lists["daily"], tz, self._hp_wind_factor)
        return self._hp_weather

    def _hp_indoor_source(self, conf: dict[str, Any]) -> tuple[Optional[str], bool]:
        """(entity, from statistics): the indoor temperature sensor when set,
        else a thermostat's current temperature (as of 2026.10.17 - no
        statistics: the recorder's last ~10 days, then recorded live)."""
        if conf.get(CONF_HP_INDOOR_ENTITY):
            return conf[CONF_HP_INDOOR_ENTITY], True
        sp = conf.get(CONF_HP_SETPOINT_ENTITY) or ""
        if sp.startswith("climate."):
            return sp, False
        return None, False

    def _climate_temp(self, value: Any) -> Optional[float]:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if self.hass.config.units.temperature_unit == "\u00b0F":
            v = (v - 32) / 1.8
        return v

    async def _async_hp_demand(self, conf: dict[str, Any], now: datetime, tz) -> None:
        """The thermostat's heat demand per day of the last days (the
        recorder keeps about 10) into the journal: a cool day without demand
        isn't fitted (2026.10.17). Needs a climate entity as the wanted
        temperature; from then on it's also recorded live."""
        entity_id = conf.get(CONF_HP_SETPOINT_ENTITY) or ""
        if not entity_id.startswith("climate."):
            return
        start = now - timedelta(days=11)
        midnight = dt_util.start_of_local_day(now)
        states = await async_fetch_state_changes(self.hass, entity_id, start, now)
        changes = [(int(st.last_updated.timestamp()), heatpump.climate_demand(st.state, dict(st.attributes))) for st in states]
        hours = heatpump.demand_hours(changes, int(start.timestamp()), int(midnight.timestamp()), tz)
        if hours:
            self.hp.set_demand(hours, now.astimezone(tz).date())
        # its current temperature too, per hour (the indoor temperature
        # without a separate sensor)
        # and its wanted temperature per day
        wanted = [(int(st.last_updated.timestamp()), self._climate_temp(st.attributes.get("temperature"))) for st in states]
        sp_days = heatpump.daily_means(
            heatpump.step_hourly_means(wanted, int(start.timestamp()), int(midnight.timestamp())), tz
        )
        if sp_days:
            self.hp.set_setpoints(sp_days, now.astimezone(tz).date())
        temps = [(int(st.last_updated.timestamp()), self._climate_temp(st.attributes.get("current_temperature"))) for st in states]
        self.hp.add_indoor_hours(
            heatpump.step_hourly_means(temps, int(start.timestamp()), int(now.timestamp()) // 3600 * 3600), now.timestamp()
        )

    async def _async_hp_thermal(self, conf: dict[str, Any], today: date, tz) -> None:
        """The house's cooling rate (heatpump.fit_thermal) from the last
        THERMAL_DAYS of the indoor temperature (its statistics, or what was
        recorded of the thermostat's), once a day. Needs the heat pump's own
        metering (the hours it didn't heat)."""
        indoor_id, from_stats = self._hp_indoor_source(conf)
        heat, cool = hp_energy_entities(conf)
        if not indoor_id or not (heat or cool):
            self.hp.thermal = None
            self.hp.indoor_days = {}
            return
        start = datetime.combine(today - timedelta(days=heatpump.THERMAL_DAYS), datetime.min.time(), tzinfo=tz)
        end = datetime.combine(today, datetime.min.time(), tzinfo=tz)
        solar_ids = list((self._energy_dashboard_sources or {}).get("solar", []))
        sums = await async_fetch_hourly_sums(self.hass, [*heat, *cool, *solar_ids], start, end)
        cop_id = conf.get(CONF_HP_COP_ENTITY)
        mean_ids = [indoor_id if from_stats else None, conf.get(CONF_HP_OUTDOOR_ENTITY), conf.get(CONF_HP_WIND_ENTITY), cop_id]
        means = await async_fetch_hourly_means(self.hass, [m for m in mean_ids if m], start, end)
        if not from_stats:
            means[indoor_id] = {h: v for h, v in self.hp.indoor_series().items() if start.timestamp() <= h < end.timestamp()}
        deltas = {k: heatpump.hourly_deltas(v) for k, v in sums.items()}
        energy = heatpump.add_series(*[deltas.get(e, {}) for e in [*heat, *cool]])
        sun = heatpump.add_series(*[deltas.get(e, {}) for e in solar_ids]) if solar_ids else None
        wind = means.get(conf.get(CONF_HP_WIND_ENTITY)) if conf.get(CONF_HP_WIND_ENTITY) else None
        # the usual indoor temperature per hour comes from these days
        self.hp.indoor_days = heatpump.indoor_hours(means.get(indoor_id) or {}, tz)
        self.hp.thermal = heatpump.fit_thermal(
            means.get(indoor_id) or {}, means.get(conf.get(CONF_HP_OUTDOOR_ENTITY)) or {}, energy, wind, sun
        )
        self.hp.thermal_day = today.isoformat()
        if self.hp.thermal:
            self.hp.thermal["src"] = indoor_id
            _LOGGER.info(
                "ESS Manager (%s): house cooling learned from %d hours: %.3f per hour (time constant %.0f h, floor heat %d h)",
                self.entry.title, self.hp.thermal["n"], self.hp.thermal["k"], 1 / self.hp.thermal["k"], self.hp.thermal["off_hours"],
            )
        # the house hour by hour (2026.10.17, step 1): COP, fit, self-check
        if not conf.get(CONF_HP_HOURLY_ENABLED):
            self.hp.house = None
            return
        heat_only = heatpump.add_series(*[deltas.get(e, {}) for e in heat]) if heat else {}
        cool_only = heatpump.add_series(*[deltas.get(e, {}) for e in cool]) if cool else None
        model = self.hp.model
        profile = (heatpump.indoor_profile(self.hp.indoor_days, heatpump.heating_dates(model, self.hp.journal))
                   if model and self.hp.indoor_days else None)
        learned = await self.hass.async_add_executor_job(
            heatpump_house.learn,
            means.get(indoor_id) or {}, means.get(conf.get(CONF_HP_OUTDOOR_ENTITY)) or {}, heat_only, wind, sun,
            cool_only, means.get(cop_id) if cop_id else None, tz, today, profile, heatpump.hourly_shape(self.hp.journal, today),
        )
        self.hp.house = {**learned, "day": today.isoformat()}
        rev = learned.get("review") or {}
        _LOGGER.info(
            "ESS Manager (%s): house model %s - self-check over %s days: hour error %s kWh (pattern %s), indoor %s degC%s",
            self.entry.title, "fitted" if learned.get("model") else "not fitted yet", rev.get("days"),
            rev.get("hour_error_kwh"), rev.get("pattern_error_kwh"), rev.get("temp_error_c"),
            " - used for the planning" if rev.get("passed") else "",
        )

    def _hp_setpoint(self, conf: dict[str, Any]) -> Optional[float]:
        entity_id = conf.get(CONF_HP_SETPOINT_ENTITY)
        if not entity_id:
            return None
        if entity_id.startswith("climate."):
            state = self.hass.states.get(entity_id)
            value = state.attributes.get("temperature") if state else None
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None
        return _get_float_state(self.hass, entity_id, default=None)

    def _hp_controls(self) -> Optional[dict[str, Any]]:
        """The card's steering controls (entity ids) while both steps are on."""
        if not self.plan_enabled(HP_STEERING_PLAN):
            return None
        ids = {}
        for name, key in (("day", NUM_HP_DAY_TEMP), ("night", NUM_HP_NIGHT_TEMP), ("delta", NUM_HP_BUFFER_DELTA),
                          ("day_from", NUM_HP_DAY_FROM), ("night_from", NUM_HP_NIGHT_FROM)):
            entity = self._numbers.get(key)
            ids[name] = getattr(entity, "entity_id", None)
        ids["switch"] = getattr(self.hp_steering_entity, "entity_id", None)
        ids["on"] = self.hp_steering_on
        return ids

    def hp_schedule(self, hour0: int, hours: int, tz) -> list[float]:
        """The day/night temperature per hour from the card's settings."""
        return heatpump_house.day_night(
            self.get_number(NUM_HP_DAY_TEMP, 20.5), self.get_number(NUM_HP_NIGHT_TEMP, 19.0),
            int(self.get_number(NUM_HP_DAY_FROM, 7)), int(self.get_number(NUM_HP_NIGHT_FROM, 22)), hour0, hours, tz,
        )

    def hp_steering_active(self, conf: dict[str, Any]) -> bool:
        return (
            self.plan_enabled(HP_STEERING_PLAN) and self.hp_steering_on
            and (conf.get(CONF_HP_SETPOINT_ENTITY) or "").startswith("climate.")
        )

    async def _async_hp_steer(self, conf: dict[str, Any], now: datetime, tz, attribute: dict[str, Any]) -> None:
        """Step 2, steering (as of 2026.10.17; on in Configure and on the
        card): the thermostat follows the day/night temperatures - plus the
        buffer plan (warmer in cheap/sunny hours, cooler in expensive ones,
        within the range) once the hour-by-hour model passed its self-check.
        A change by hand wins until the next day/night switch. Switched off:
        back to the plain day/night temperature once, then left alone."""
        entity_id = conf.get(CONF_HP_SETPOINT_ENTITY) or ""
        if not entity_id.startswith("climate."):
            return
        steer = self.hp.steer
        state = self.hass.states.get(entity_id)
        try:
            current = float(state.attributes.get("temperature")) if state else None
        except (TypeError, ValueError):
            current = None
        hour0 = int(now.replace(minute=0, second=0, microsecond=0).timestamp())
        schedule = self.hp_schedule(hour0, 48, tz)
        if not self.hp_steering_active(conf):
            if steer.get("last_set") is not None and current is not None and abs(current - steer["last_set"]) <= 0.05 \
                    and abs(current - schedule[0]) > 0.05:
                await self._async_set_climate(entity_id, schedule[0])
                _LOGGER.info("ESS Manager (%s): steering off - thermostat back to %.1f", self.entry.title, schedule[0])
            self.hp.steer = {}
            return
        if state is None or state.state in ("off", "unavailable", "unknown") or current is None:
            return
        if steer.get("override_until"):
            if now.timestamp() < steer["override_until"]:
                return
            steer.pop("override_until", None)
            steer.pop("last_set", None)
        last = steer.get("last_set")
        if last is not None and abs(current - last) > 0.05:
            switch = next((hour0 + i * 3600 for i in range(1, len(schedule)) if schedule[i] != schedule[i - 1]), hour0 + 12 * 3600)
            steer["override_until"] = switch
            steer.pop("last_set", None)
            _LOGGER.info("ESS Manager (%s): thermostat changed by hand - steering waits until the next day/night switch", self.entry.title)
            return
        house = attribute.get("house_model") or {}
        desired = house.get("setpoint_now")
        if desired is None:
            desired = schedule[0]
        step = state.attributes.get("target_temp_step") or 0.5
        try:
            step = float(step)
        except (TypeError, ValueError):
            step = 0.5
        desired = round(round(desired / step) * step, 2)
        if abs(current - desired) > 0.05:
            await self._async_set_climate(entity_id, desired)
            _LOGGER.info("ESS Manager (%s): steering - thermostat %.1f -> %.1f", self.entry.title, current, desired)
        steer["last_set"] = desired

    # -- floor control (as of 2026.10.23) -------------------------------------------
    def floor_configured(self, conf: Optional[dict[str, Any]] = None) -> bool:
        conf = conf if conf is not None else {**self.entry.data, **self.entry.options}
        return bool(
            conf.get(CONF_HP_ENABLED) and conf.get(CONF_FLOOR_ENABLED)
            and (conf.get(CONF_HP_SETPOINT_ENTITY) or "").startswith("climate.")
            and all(conf.get(k) for k in FLOOR_REQUIRED)
        )

    def _temp_state(self, entity_id: Optional[str]) -> Optional[float]:
        value = _get_float_state(self.hass, entity_id, default=None) if entity_id else None
        if value is not None:
            st = self.hass.states.get(entity_id)
            if st and st.attributes.get("unit_of_measurement") == "\u00b0F":
                value = (value - 32) / 1.8
        return value

    def _is_on(self, entity_id: Optional[str]) -> Optional[bool]:
        st = self.hass.states.get(entity_id) if entity_id else None
        if st is None or st.state not in ("on", "off"):
            return None
        return st.state == "on"

    async def _async_floor_switch(self, entity_id: str, on: bool) -> None:
        domain = entity_id.split(".", 1)[0]
        await self.hass.services.async_call(domain, "turn_on" if on else "turn_off", {"entity_id": entity_id}, blocking=True)

    async def _async_floor_setpoint(self, entity_id: str, value: float) -> None:
        domain = entity_id.split(".", 1)[0]
        await self.hass.services.async_call(domain, "set_value", {"entity_id": entity_id, "value": value}, blocking=True)

    def floor_cooling(self, conf: Optional[dict[str, Any]] = None) -> bool:
        """The heat pump cools (as of 2026.10.23): the changeover switch is on,
        or the cooling thermostat calls for cooling (hvac_action "cooling" -
        as of 2026.10.24; a cooling thermostat left on "cool" all year with a
        high setpoint doesn't count while it's idle). Floor control then
        leaves the heat pump alone - also its heat demand, which cooling
        uses too."""
        conf = conf if conf is not None else {**self.entry.data, **self.entry.options}
        if self._is_on(conf.get(CONF_FLOOR_COOL_SWITCH_ENTITY)):
            return True
        climate_id = conf.get(CONF_FLOOR_COOL_CLIMATE_ENTITY)
        st = self.hass.states.get(climate_id) if climate_id else None
        return st is not None and st.state not in ("off", "unavailable", "unknown") \
            and st.attributes.get("hvac_action") == "cooling"

    async def async_floor_release(self, conf: Optional[dict[str, Any]] = None) -> None:
        """Hand the heat pump back: the return setpoint as it was before ESS
        Manager took over, heat demand as the thermostat wants it (not while
        the heat pump cools: that heat demand is the cooling's)."""
        conf = conf if conf is not None else {**self.entry.data, **self.entry.options}
        stage = self.floor.stage
        if stage in (fc.MODE_SETPOINT, fc.MODE_FULL) and self.floor.baseline_sp is not None and conf.get(CONF_FLOOR_SETPOINT_ENTITY):
            try:
                await self._async_floor_setpoint(conf[CONF_FLOOR_SETPOINT_ENTITY], self.floor.baseline_sp)
            except Exception as err:  # noqa: BLE001 - best effort
                _LOGGER.warning("ESS Manager (%s): return setpoint not restored: %s", self.entry.title, err)
        if stage == fc.MODE_FULL and conf.get(CONF_FLOOR_DEMAND_ENTITY) and not self.floor_cooling(conf):
            helper = self._is_on(conf.get(CONF_FLOOR_HELPER_ENTITY))
            if helper is not None:
                try:
                    await self._async_floor_switch(conf[CONF_FLOOR_DEMAND_ENTITY], helper)
                except Exception as err:  # noqa: BLE001 - best effort
                    _LOGGER.warning("ESS Manager (%s): heat demand not handed back: %s", self.entry.title, err)
        if stage != fc.MODE_WATCH:
            _LOGGER.info("ESS Manager (%s): floor control - heat pump handed back to the thermostat", self.entry.title)
        self.floor.stage = fc.MODE_WATCH
        self.floor.baseline_sp = None
        self.floor.setpoint_since = None

    def _floor_targets(self, conf: dict[str, Any], hour0: int, setpoint: Optional[float], attribute: dict[str, Any]) -> Optional[list[float]]:
        """The wanted temperature per hour for floor control: the thermostat's
        setpoint (what's set there by hand counts), with steering on the
        day/night temperatures and buffer plan from the hour-by-hour model
        (after a change by hand from the next day/night switch on)."""
        if setpoint is None:
            return None
        n = 24
        fc_target = ((attribute.get("house_model") or {}).get("forecast") or {}).get("target") or []
        if not self.hp_steering_active(conf) or len(fc_target) < 2:
            return [setpoint] * n
        override = self.hp.steer.get("override_until")
        if override and override > hour0:
            k = min(max(int((override - hour0) // 3600), 1), n)
            return ([setpoint] * k + list(fc_target[k:n]) + [fc_target[-1]] * n)[:n]
        return ([setpoint] + list(fc_target[1:n]) + [fc_target[-1]] * n)[:n]

    async def _async_floor(
        self, conf: dict[str, Any], now: datetime, hour0: int, indoor: Optional[float], hourly: list,
        setpoint: Optional[float], attribute: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """One cycle of floor control - see floor_control.py."""
        if not self.floor_configured(conf):
            if self.floor.stage != fc.MODE_WATCH:
                await self.async_floor_release(conf)
            return None
        now_ts = now.timestamp()
        if self.floor_cooling(conf):
            # summer: the heat pump cools (its heat demand is the cooling's):
            # the return setpoint back once, then nothing - and nothing learned
            if self.floor.stage != fc.MODE_WATCH:
                await self.async_floor_release(conf)
                _LOGGER.info("ESS Manager (%s): floor control - the heat pump cools, stepping aside", self.entry.title)
            self.floor.sample(now_ts, {"pump": None}, None, None, cooling=True)
            return {
                "mode": self.floor_mode, "stage": fc.STAGE_COOLING, "waiting": [],
                "model": {k: (self.floor.model or {}).get(k) for k in ("u", "delta", "p_min", "p_max", "n", "err", "ok", "slab")},
                "min_hours": fc.MIN_EMIT_HOURS, "response": {"n": 0, "err": None, "ok": False, "min_hours": fc.MIN_RESPONSE_HOURS},
                "now": {"reason": "cooling"}, "next": [], "select": self.floor_mode_entity_id,
                "recent": [{k: r.get(k) for k in ("h", "th_kwh", "plan_kwh", "sp", "run_s", "room", "slab")}
                           for r in self.floor.records if r["h"] >= hour0 - 24 * 3600],
            }
        sp_id = conf[CONF_FLOOR_SETPOINT_ENTITY]
        sp_state = self.hass.states.get(sp_id)
        sp_actual = _get_float_state(self.hass, sp_id, default=None)
        readings = {
            "pump": _get_float_state(self.hass, conf.get(CONF_FLOOR_PUMP_ENTITY), default=None),
            "t_sup": self._temp_state(conf.get(CONF_FLOOR_SUPPLY_ENTITY)),
            "t_ret": self._temp_state(conf.get(CONF_FLOOR_RETURN_ENTITY)),
            "t_room": indoor,
            "t_slab": self._temp_state(conf.get(CONF_FLOOR_SLAB_ENTITY)),
            "p_th": _state_in_unit(self.hass, conf.get(CONF_FLOOR_POWER_ENTITY), ("W",), 0.001),
            "sp": sp_actual,
        }
        demand_id = conf[CONF_FLOOR_DEMAND_ENTITY]
        demand_on = self._is_on(demand_id)
        helper_on = self._is_on(conf.get(CONF_FLOOR_HELPER_ENTITY))
        floor = self.floor
        floor.refit(now_ts)
        model = floor.model or {}
        cop = floor.cop_ratio(self.hp.heat_hist)
        targets = self._floor_targets(conf, hour0, setpoint, attribute)
        plan = self.hp.plan_heat(hour0, indoor, hourly, targets, cop) if targets else None
        plan_kw = plan["q_th"][0] if plan and plan["q_th"] else None
        house = self.hp.house or {}
        house_ok = bool((house.get("review") or {}).get("passed")) and bool(house.get("model"))
        response = fc.response_check(floor.records, floor.setpoint_since)
        inputs_ok = (
            all(readings[k] is not None for k in ("pump", "t_sup", "t_ret", "t_room", "p_th", "sp"))
            and demand_on is not None and helper_on is not None and plan_kw is not None
        )
        stage, waiting = fc.effective_stage(self.floor_mode, bool(model.get("ok")), response["ok"], house_ok, inputs_ok)
        # the thermostat switched off (as of 2026.10.25): no heating wanted -
        # the heat pump goes back to the thermostat (whose helper is off then)
        thermostat = self.hass.states.get(conf.get(CONF_HP_SETPOINT_ENTITY) or "")
        if thermostat is not None and thermostat.state == "off":
            stage, waiting = fc.MODE_WATCH, ["thermostat_off"]

        p_min = model.get("p_min") or fc.DEFAULT_P_MIN
        p_max = max(model.get("p_max") or p_min * 3, p_min)
        prev = floor.stage
        if stage == fc.MODE_FULL and prev != fc.MODE_FULL:
            # start from what the heat pump does now
            floor.ctl.update({"on": bool(demand_on), "since": now_ts, "debt": 0.0})
        step = fc.control_step(floor.ctl, now_ts, plan_kw or 0.0, readings["p_th"] or 0.0, indoor, setpoint, p_min, p_max)

        # the return setpoint: the target power while running (full), the
        # planned power while the thermostat switches (setpoint stage)
        if stage == fc.MODE_FULL:
            p_sp = step["p_target"] if step["on"] else min(max(plan_kw or 0.0, p_min), p_max)
        else:
            p_sp = min(max(plan_kw or 0.0, p_min), p_max)
        # the room lagging behind: more power (full at 1.2 degC too cold)
        p_sp = fc.comfort_power(p_sp, indoor, setpoint, p_min, p_max)
        lo, hi = fc.SP_LIMITS
        if sp_state is not None:
            lo = max(lo, _float_or(sp_state.attributes.get("min"), lo))
            hi = min(hi, _float_or(sp_state.attributes.get("max"), hi))
        sp_step = _float_or(sp_state.attributes.get("step"), 0.5) if sp_state is not None else 0.5
        t_ref = readings["t_slab"] if model.get("slab") and readings["t_slab"] is not None else indoor
        sp_planned = fc.return_setpoint(model, p_sp, t_ref, lo, hi, sp_step) if t_ref is not None else None
        # a COMFORT_BAND too cold: never below the setpoint the heat pump had before
        if (sp_planned is not None and floor.baseline_sp is not None and indoor is not None and setpoint is not None
                and setpoint - indoor >= fc.COMFORT_BAND):
            sp_planned = max(sp_planned, floor.baseline_sp)

        # stage changes
        if stage in (fc.MODE_SETPOINT, fc.MODE_FULL) and prev == fc.MODE_WATCH:
            floor.baseline_sp = sp_actual
            floor.setpoint_since = floor.setpoint_since or now_ts
            _LOGGER.info("ESS Manager (%s): floor control - %s (return setpoint was %s)", self.entry.title, stage, sp_actual)
        if stage == fc.MODE_WATCH and prev != fc.MODE_WATCH:
            await self.async_floor_release(conf)
            prev = fc.MODE_WATCH
        elif prev == fc.MODE_FULL and stage == fc.MODE_SETPOINT and helper_on is not None and demand_on != helper_on:
            await self._async_floor_switch(demand_id, helper_on)
            _LOGGER.info("ESS Manager (%s): floor control - heat demand back to the thermostat", self.entry.title)
        floor.stage = stage

        # what's sent
        if stage in (fc.MODE_SETPOINT, fc.MODE_FULL) and sp_planned is not None and sp_actual is not None:
            due = now_ts - floor.last_sp_ts >= fc.SP_WRITE_EVERY_S or prev == fc.MODE_WATCH
            if abs(sp_planned - sp_actual) >= sp_step / 2 and due:
                await self._async_floor_setpoint(sp_id, sp_planned)
                floor.last_sp_ts = now_ts
                floor.last_sp = sp_planned
        if stage == fc.MODE_FULL and demand_on is not None and demand_on != step["on"]:
            await self._async_floor_switch(demand_id, step["on"])
            _LOGGER.info("ESS Manager (%s): floor control - heat demand %s (%s)", self.entry.title,
                         "on" if step["on"] else "off", step["reason"])

        p_rec = p_sp if stage in (fc.MODE_SETPOINT, fc.MODE_FULL) and readings["pump"] is not None else None
        floor.sample(now_ts, readings, p_rec, plan_kw)

        # for the card: the next 12 hours as planned, the last 24 as measured
        nxt = []
        if plan:
            for i, q in enumerate(plan["q_th"][:12]):
                sp_i = fc.return_setpoint(model, min(max(q, p_min), p_max), t_ref, lo, hi, sp_step) if (t_ref is not None and q > 0.05) else None
                nxt.append({"h": hour0 + i * 3600, "kwh": q, "sp": sp_i, "temp": plan["temps"][i + 1] if i + 1 < len(plan["temps"]) else None})
        recent = [
            {k: r.get(k) for k in ("h", "th_kwh", "plan_kwh", "sp", "run_s", "room", "slab")}
            for r in floor.records if r["h"] >= hour0 - 24 * 3600
        ]
        return {
            "mode": self.floor_mode,
            "stage": stage,
            "waiting": waiting,
            "model": {k: model.get(k) for k in ("u", "delta", "p_min", "p_max", "n", "err", "ok", "slab")},
            "min_hours": fc.MIN_EMIT_HOURS,
            "response": {**response, "min_hours": fc.MIN_RESPONSE_HOURS},
            "house_ok": house_ok,
            "cop": cop,
            "now": {
                "plan_kw": plan_kw, "p_target": step["p_target"], "would_heat": step["on"], "reason": step["reason"],
                "debt_kwh": step["debt"], "demand_on": demand_on, "thermostat_on": helper_on,
                "sp": sp_actual, "sp_planned": sp_planned, "baseline_sp": floor.baseline_sp,
                **{k: readings[k] for k in ("pump", "t_sup", "t_ret", "t_slab", "p_th")},
                "target": setpoint, "room": indoor,
            },
            "next": nxt,
            "recent": recent,
            "select": self.floor_mode_entity_id,
        }

    async def _async_set_climate(self, entity_id: str, temperature: float) -> None:
        await self.hass.services.async_call(
            "climate", "set_temperature", {"entity_id": entity_id, "temperature": temperature}, blocking=True
        )

    async def _async_heat_pump(
        self, conf: dict[str, Any], now: datetime, merged_solar_points: list, prices: Optional[dict[str, list[float]]] = None
    ) -> tuple[list[float], dict[str, Any]]:
        tz = dt_util.get_default_time_zone()
        today = now.astimezone(tz).date()
        meter = hp_meter(conf)
        key = self._hp_key(conf)
        if self.hp.key != key:
            self.hp.reset(key)
            self._hp_backfill_tried_at = None
        # the thermostat's heat demand and current temperature of the last days:
        # after a start and daily - before the journal, whose rows use them
        if self._hp_demand_day != today.isoformat():
            self._hp_demand_day = today.isoformat()
            try:
                await self._async_hp_demand(conf, now, tz)
            except Exception as err:  # noqa: BLE001 - the recorder's history is optional here
                _LOGGER.debug("ESS Manager: thermostat heat demand not read: %s", err)
        # the journal: two years of statistics once, then yesterday every day
        try:
            indoor_src = self._hp_indoor_source(conf)[0] or ""
            empty = not self.hp.journal or not any(r.get("e") is not None for r in self.hp.journal)
            if empty or self.hp.rows_src != indoor_src:
                # (also once with another indoor sensor - or as of 2026.10.17
                # the indoor temperature per day in the rows: refilled, the
                # live records stay)
                if self._hp_backfill_tried_at is None or now - self._hp_backfill_tried_at > timedelta(hours=1):
                    self._hp_backfill_tried_at = now
                    rows = await self._async_hp_rows(conf, today - timedelta(days=heatpump.JOURNAL_DAYS), today - timedelta(days=1), tz)
                    if not empty:
                        self.hp.forget_indoor()
                    self.hp.merge(rows, today)
                    self.hp.stats_day = today.isoformat()
                    self.hp.rows_src = indoor_src
                    _LOGGER.info("ESS Manager (%s): heat pump journal filled with %d days of statistics", self.entry.title, len(rows))
            elif self.hp.stats_day != today.isoformat() and (now.timestamp() - self.hp.stats_tried_at) > 900:
                self.hp.stats_tried_at = now.timestamp()
                rows = await self._async_hp_rows(conf, today - timedelta(days=3), today - timedelta(days=1), tz)
                self.hp.merge(rows, today)
                if any(r["d"] == (today - timedelta(days=1)).isoformat() for r in rows):
                    self.hp.stats_day = today.isoformat()
        except Exception as err:  # noqa: BLE001 - the recorder is needed for this, planning goes on without
            _LOGGER.debug("ESS Manager: heat pump statistics not read: %s", err)
        # the house's cooling rate: once a day
        other_sensor = bool(self.hp.thermal) and self.hp.thermal.get("src") != self._hp_indoor_source(conf)[0]
        if (self.hp.thermal_day != today.isoformat() or other_sensor) and (now.timestamp() - self._hp_thermal_tried_at) > 3600:
            self._hp_thermal_tried_at = now.timestamp()
            try:
                await self._async_hp_thermal(conf, today, tz)
            except Exception as err:  # noqa: BLE001 - as above
                _LOGGER.debug("ESS Manager: house cooling not learned: %s", err)
        # today's live readings
        day_start = dt_util.start_of_local_day(now)
        sun_today = sum(v or 0.0 for v in forecasting.build_solar_forecast(merged_solar_points, day_start, 24))
        outdoor = conf.get(CONF_HP_OUTDOOR_ENTITY)
        t_out = _get_float_state(self.hass, outdoor, default=None) if outdoor else None
        if t_out is not None and outdoor:
            st = self.hass.states.get(outdoor)
            if st and st.attributes.get("unit_of_measurement") == "\u00b0F":
                t_out = (t_out - 32) / 1.8
        wind = None
        if conf.get(CONF_HP_WIND_ENTITY):
            st = self.hass.states.get(conf[CONF_HP_WIND_ENTITY])
            wind = _get_float_state(self.hass, conf[CONF_HP_WIND_ENTITY], default=None)
            if wind is not None and st:
                wind *= WIND_FACTORS.get(st.attributes.get("unit_of_measurement") or "m/s", 1.0)
        wind_dir = _get_float_state(self.hass, conf.get(CONF_HP_WIND_DIR_ENTITY), default=None) if conf.get(CONF_HP_WIND_DIR_ENTITY) else None
        setpoint = self._hp_setpoint(conf)
        indoor_id, from_stats = self._hp_indoor_source(conf)
        indoor = None
        if indoor_id and from_stats:
            indoor = _get_float_state(self.hass, indoor_id, default=None)
            st = self.hass.states.get(indoor_id)
            if indoor is not None and st and st.attributes.get("unit_of_measurement") == "\u00b0F":
                indoor = (indoor - 32) / 1.8
        elif indoor_id:
            st = self.hass.states.get(indoor_id)
            indoor = self._climate_temp(st.attributes.get("current_temperature")) if st else None
        demand = None
        sp_entity = conf.get(CONF_HP_SETPOINT_ENTITY) or ""
        if sp_entity.startswith("climate."):
            st = self.hass.states.get(sp_entity)
            demand = heatpump.climate_demand(st.state, dict(st.attributes)) if st else None
        heat_ids, _ = hp_energy_entities(conf)
        heat_vals = [_state_in_unit(self.hass, e, ("Wh",), 0.001) for e in heat_ids]
        heat_kwh = sum(heat_vals) if heat_vals and all(v is not None for v in heat_vals) else None
        self.hp.sample(now, tz, t_out, wind, wind_dir, setpoint, indoor, sun_today, demand, heat_kwh)
        # forecast
        weather = await self._async_hp_weather(conf, now, tz)
        sun_by_day: dict[str, float] = {}
        hourly_sun = forecasting.build_solar_forecast(merged_solar_points, day_start, 24 * 7)
        for i, v in enumerate(hourly_sun):
            d = (day_start + timedelta(hours=i)).astimezone(tz).date().isoformat()
            sun_by_day[d] = round(sun_by_day.get(d, 0.0) + (v or 0.0), 2)
        hour0 = int(now.replace(minute=0, second=0, microsecond=0).timestamp())
        offset = max(int((hour0 - day_start.timestamp()) // 3600), 0)
        hourly = heatpump.hourly_weather(
            self._hp_hourly, weather, hour0, FORECAST_HOURS, tz, self._hp_wind_factor, hourly_sun[offset:]
        )
        # on a worker thread (as of 2026.10.20): the energy signature's fit (a
        # grid search over up to two years of days), the forecast and the
        # hour-by-hour model are pure Python and too heavy for the event loop
        # on a small machine - the arguments are all gathered here first
        steering = self.hp_steering_active(conf)
        total, attribute, used = await self.hass.async_add_executor_job(functools.partial(
            self.hp.compute,
            meter, now, tz, hour0, FORECAST_HOURS, weather, sun_by_day,
            int(conf.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS)), setpoint, with_cooling=True,
            indoor=indoor, hourly_weather=hourly, prices=prices,
            steering=steering,
            schedule=self.hp_schedule(hour0, 48, tz) if steering else None,
            buffer_delta=self.get_number(NUM_HP_BUFFER_DELTA, 1.0),
            hourly_model=bool(conf.get(CONF_HP_HOURLY_ENABLED)),
        ))
        subtract = used and meter != HP_METER_NONE
        if subtract != self.hp.subtract:
            # the usage history has to leave the heat pump out (or take it
            # back): recomputed next cycle, until then nothing is doubled
            self.hp.subtract = subtract
            self.invalidate_usage_forecast()
        if meter != HP_METER_NONE and not self._usage_hp_subtracted:
            total = None
        attribute["weather_days"] = len(weather)
        try:
            await self._async_hp_steer(conf, now, tz, attribute)
        except Exception as err:  # noqa: BLE001 - a thermostat that refuses: the planning goes on
            _LOGGER.warning("ESS Manager (%s): thermostat not set: %s", self.entry.title, err)
        if "house_model" in attribute:
            attribute["house_model"]["steer"] = dict(self.hp.steer)
            attribute["house_model"]["controls"] = self._hp_controls()
        try:
            attribute["floor"] = await self._async_floor(conf, now, hour0, indoor, hourly, setpoint, attribute)
        except Exception as err:  # noqa: BLE001 - floor control must never stop the planning
            _LOGGER.warning("ESS Manager (%s): floor control skipped this cycle: %s", self.entry.title, err)
        return total, attribute

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
        ev_entity = ev_energy_entity(conf)
        if ev_entity:
            # the car's sessions are looked up per whole local day
            range_start -= timedelta(days=1)
        hp_ids = self._hp_subtract_ids(conf)

        try:
            hourly_sums = await async_fetch_hourly_sums(
                self.hass, [*consumption_entities, *([ev_entity] if ev_entity else []), *hp_ids], range_start, range_end
            )
        except Exception as err:  # noqa: BLE001 - a statistics/DB hiccup shouldn't fail the whole update
            _LOGGER.warning("ESS Manager: could not fetch usage-forecast statistics: %s", err)
            if self._usage_forecast_cache is not None:
                return self._usage_forecast_cache
            self._set_usage_history([HISTORY_NONE] * FORECAST_HOURS, lookback_weeks)
            self._usage_missing = True
            return [0.0] * FORECAST_HOURS

        self._usage_forecast_cache, hour_sources = compute_usage_forecast_from_consumption_detailed(
            hourly_sums,
            consumption_entities,
            now,
            FORECAST_HOURS,
            lookback_weeks,
            subtract_entities=[*([ev_entity] if ev_entity else []), *hp_ids] or None,
            week_weights=self.acc.week_weights(lookback_weeks),
        )
        self._usage_hp_subtracted = bool(hp_ids)
        if ev_entity:
            self.ev.history = ev_hourly_history(
                hourly_sums, [ev_entity], None, [], int(range_start.timestamp()), int(base_hour.timestamp())
            )
        self._usage_forecast_computed_at = now
        self._usage_missing = False
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

    @staticmethod
    def _day_hours(day: date) -> list[int]:
        """The hour epochs of a local day (23 or 25 on a DST change)."""
        start = int(dt_util.start_of_local_day(day).timestamp())
        end = int(dt_util.start_of_local_day(day + timedelta(days=1)).timestamp())
        return list(range(start, end, 3600))

    def _usage_terms(self, conf: dict[str, Any], usage_source: Any) -> Optional[tuple]:
        """(import, export, solar, battery charge, battery discharge) for the
        household-usage identity, like the usage forecast."""
        if usage_source == USAGE_SOURCE_CONSUMPTION_SENSOR:
            ids = [e for e in conf.get(CONF_USAGE_CONSUMPTION_ENTITIES, []) or [] if e]
            return (ids, [], [], None, None) if ids else None
        if usage_source == USAGE_SOURCE_ENERGY_DASHBOARD and self._energy_dashboard_sources:
            src = self._energy_dashboard_sources
            if not src["import"]:
                return None
            return (src["import"], src["export"], src["solar"], src["battery_charge"], src["battery_discharge"])
        return None

    async def _async_forecast_check(self, conf: dict[str, Any], usage_source: Any, now: datetime) -> None:
        """Once a day (and an hour after a failed try): the forecast check
        from the statistics - see accuracy.py / accuracy_runtime.py.
        Display and buffer advice only: a failure keeps the last result."""
        today = now.date()
        today_iso = today.isoformat()
        if not self.acc.needs_refresh(today_iso, now.timestamp()):
            return
        # yesterday's last hour lands in the statistics a few minutes after midnight
        if self.acc.refreshed_day is not None and now.hour == 0 and now.minute < 20:
            return
        terms = self._usage_terms(conf, usage_source)
        if terms is None:
            return
        self.acc.tried_at = now.timestamp()
        try:
            solar_ids: list[str] = []
            try:
                solar_ids = list(energy_prefs_to_sources(await async_get_energy_prefs(self.hass)).get("solar") or [])
            except Exception:  # noqa: BLE001 - solar is optional here
                solar_ids = []
            ev_entity = ev_energy_entity(conf)
            hp_ids = self._hp_subtract_ids(conf)
            lookback = int(conf.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS))
            test_days = [
                ((today - timedelta(days=i)).isoformat(), self._day_hours(today - timedelta(days=i)))
                for i in range(accuracy.TEST_DAYS, 0, -1)
            ]
            today_start = dt_util.start_of_local_day(today)
            range_start = dt_util.start_of_local_day(today - timedelta(days=accuracy.TEST_DAYS)) - timedelta(
                weeks=lookback, hours=2
            )
            usage_ids = [*terms[0], *terms[1], *terms[2], *(terms[3] or []), *(terms[4] or [])]
            ids = list(dict.fromkeys([*usage_ids, *solar_ids, *([ev_entity] if ev_entity else []), *hp_ids]))
            sums = await async_fetch_hourly_sums(self.hass, ids, range_start, today_start + timedelta(hours=1))
            first = int(range_start.timestamp()) + 3600
            last = int(today_start.timestamp())
            ev_ids = [ev_entity] if ev_entity else []
            capacity = self.get_number(NUM_BATTERY_CAPACITY_KWH, 30.0)

            def _work() -> bool:
                # ~15 weeks of hours and a backtest: in a worker thread
                base = {e: accuracy.usage_hour(sums, terms, e, [*ev_ids, *hp_ids]) for e in range(first, last, 3600)}
                check_from = test_days[0][1][0]
                house = {e: accuracy.usage_hour(sums, terms, e, ev_ids) for e in range(check_from, last, 3600)}
                solar = (
                    {e: accuracy.sum_hour(sums, solar_ids, e) for e in range(check_from, last, 3600)} if solar_ids else None
                )
                excluded = [k for k, on in (("heat_pump", bool(hp_ids)), ("ev", bool(ev_ids))) if on]
                return self.acc.refresh(
                    today_iso=today_iso,
                    today_start=last,
                    base_series=base,
                    house_series=house,
                    solar_series=solar,
                    test_days=test_days,
                    lookback_weeks=lookback,
                    capacity_kwh=capacity,
                    excluded=excluded,
                )

            changed = await self.hass.async_add_executor_job(_work)
        except Exception as err:  # noqa: BLE001 - display / advice only
            _LOGGER.warning("ESS Manager (%s): forecast check failed, trying again in an hour: %s", self.entry.title, err)
            return
        if changed:
            # the weights are in the cached usage forecast
            self._usage_forecast_cache = None
            self._usage_forecast_computed_at = None
        result = self.acc.result or {}
        _LOGGER.info(
            "ESS Manager (%s): forecast check - usage method %s (level %s, %s test days), buffer days %s",
            self.entry.title, self.acc.method, self.acc.level, (result.get("methods") or {}).get("test_days"),
            len(result.get("needed_pct") or []),
        )

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
            self._usage_missing = True
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
        ev_entity = ev_energy_entity(conf)
        if ev_entity:
            all_ids.append(ev_entity)
            range_start -= timedelta(days=1)  # whole local days for the car's sessions
        hp_ids = self._hp_subtract_ids(conf)
        all_ids.extend(hp_ids)

        try:
            hourly_sums = await async_fetch_hourly_sums(self.hass, all_ids, range_start, range_end)
        except Exception as err:  # noqa: BLE001 - a statistics/DB hiccup shouldn't fail the whole update
            _LOGGER.warning("ESS Manager: could not fetch usage-forecast statistics: %s", err)
            if self._usage_forecast_cache is not None:
                return self._usage_forecast_cache
            self._set_usage_history([HISTORY_NONE] * FORECAST_HOURS, lookback_weeks)
            self._usage_missing = True
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
            subtract_entities=[*([ev_entity] if ev_entity else []), *hp_ids] or None,
            week_weights=self.acc.week_weights(lookback_weeks),
        )
        self._usage_hp_subtracted = bool(hp_ids)
        if ev_entity:
            self.ev.history = ev_hourly_history(
                hourly_sums,
                [ev_entity],
                (sources["import"], sources["export"], sources["solar"], sources["battery_charge"], sources["battery_discharge"]),
                sources["solar"],
                int(range_start.timestamp()),
                int(base_hour.timestamp()),
            )
        self._usage_forecast_computed_at = now
        self._usage_missing = False
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
        # One cycle at a time: Home Assistant's coordinator runs every
        # refresh (the minute timer, the quarter boundary, a setting changed)
        # under one lock, so the plans in the worker thread never run twice
        # alongside each other (checked by a test, 2026.10.20).
        try:
            return await self._async_compute()
        except Exception as err:
            # Fail-safe for direct control: never leave the last command
            # running while the integration can't see what's happening.
            # Does nothing unless direct control is on.
            await self.controller.async_idle(self.control_settings(), f"update failed: {err}")
            self._record_decision({"action": "idle (fail-safe)", "status": f"update failed: {err}"})
            self._report_control_problem(dt_util.now())
            raise

    async def _async_compute(self) -> dict[str, Any]:
        if not self._restored:
            await self._async_restore()

        conf = {**self.entry.data, **self.entry.options}
        now = dt_util.now()

        battery_soc_entity = conf.get(CONF_BATTERY_SOC_ENTITY)
        battery_soc_state = self.hass.states.get(battery_soc_entity) if battery_soc_entity else None
        self._report_input_problem(conf, now)
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
        # The forecast check (as of 2026.10.22): once a day from the
        # statistics; the "pattern 6 weeks + level last week" method scales
        # the forecast when its backtest showed it's clearly better.
        await self._async_forecast_check(conf, usage_source, now)
        usage_factor = self.acc.usage_factor()
        if usage_factor != 1.0:
            usage_forecast = [round(u * usage_factor, 3) for u in usage_forecast]

        solar_points: list[list[dict]] = []
        waiting_for: list[str] = []
        unreadable: list[str] = []
        for entity_id in conf.get(CONF_SOLAR_FORECAST_ENTITIES, []):
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unavailable", "unknown"):
                waiting_for.append(entity_id)
            if state is not None:
                points = forecasting.solar_points_from_attributes(state.attributes)
                solar_points.append(points)
                # Logged once per sensor (as of 2026.10.21): a sensor without a
                # known forecast attribute would otherwise count as no sun at all.
                # a known attribute that's empty for now (a Solcast day sensor
                # without data yet) is a format we read, just no sun in it
                known = "detailedHourly" in state.attributes or isinstance(state.attributes.get("forecast"), list)
                if not points and not known and state.state not in ("unavailable", "unknown"):
                    unreadable.append(entity_id)
                    if entity_id not in self._solar_format_warned:
                        self._solar_format_warned.add(entity_id)
                        _LOGGER.warning(
                            "ESS Manager (%s): %s has no solar forecast the integration can read "
                            "(a Solcast 'detailedHourly' or a Helios Forecast 'forecast' attribute) - "
                            "it counts as 0 kWh; check the solar forecast sensors in Configure",
                            self.entry.title, entity_id,
                        )
                elif points or known:
                    self._solar_format_warned.discard(entity_id)
        self.problems.report("solar_unreadable", bool(unreadable), now, {"entities": ", ".join(unreadable)})
        if self._usage_missing:
            waiting_for.append("the household usage statistics")
        if waiting_for and now - self._started_at < STARTUP_GRACE:
            # see STARTUP_GRACE: no plans on half the data right after a start
            raise UpdateFailed(f"Just started - waiting for {', '.join(waiting_for)}")

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
        # the car's grid window offset sent last cycle isn't the battery's
        # (as of 2026.10.27)
        setpoint_w -= self._ev_offset_w
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
        # The Safety buffer (as of 2026.10.22): the number entity, or - with
        # the "Automatic safety buffer" switch on and enough days measured -
        # the forecast check's advice, approached by at most 2 %-points a day.
        buffer_info = self.acc.buffer(
            self.get_number(NUM_SAFETY_BUFFER_PERCENT, 5.0), self.auto_buffer_on, now.date().isoformat()
        )
        safety_buffer_percent = buffer_info["effective"]
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
        # The heat pump (as of 2026.10.16): with its own metering its energy
        # is left out of the usage history and added here from the model;
        # without, the model's weather difference is added to the usual
        # forecast.
        hp_attribute = None
        if hp_meter(conf):
            day_start = int(dt_util.start_of_local_day(now).timestamp())
            hour0 = int(now.replace(minute=0, second=0, microsecond=0).timestamp())
            per_day = len(today_price) or 24
            hp_prices = {
                "buy": heatpump_house.hourly_prices(buy_price, per_day, day_start, hour0, 48),
                "sell": heatpump_house.hourly_prices(all_price, per_day, day_start, hour0, 48),
                "surplus": [max(v, 0.0) for v in net_energy[:48]],
            }
            hp_total, hp_attribute = await self._async_heat_pump(conf, now, merged_solar_points, hp_prices)
            if hp_total and any(hp_total):
                usage_forecast = [round(max(u + h, 0.0), 3) for u, h in zip(usage_forecast, hp_total)]
                net_energy = forecasting.build_net_energy(solar_forecast, usage_forecast)
        # The electric car (as of 2026.10.11): its sessions are added to the
        # household usage (whose history leaves the car out); a solar
        # session charges on what the solar forecast has left after the house.
        ev_attribute = None
        ev_total = None
        ev_victron = None
        ev_entities: dict[str, str] = {}
        if conf.get(CONF_EV_ENABLED) and conf.get(CONF_EV_CHARGER) == EV_CHARGER_VICTRON:
            ev_entities = self._victron_entities(conf.get(CONF_EV_VICTRON_DEVICE))
            ev_victron = self._victron_inputs(conf, ev_entities, now, buy_price)
        if conf.get(CONF_EV_ENABLED):
            ev_total, ev_attribute = self.ev.update(
                {
                    "phases": conf.get(CONF_EV_PHASES, DEFAULT_EV_PHASES),
                    "min_current": conf.get(CONF_EV_MIN_CURRENT, DEFAULT_EV_MIN_CURRENT),
                    "max_current": conf.get(CONF_EV_MAX_CURRENT, DEFAULT_EV_MAX_CURRENT),
                    "predict": conf.get(CONF_EV_PREDICT, DEFAULT_EV_PREDICT),
                    "cars": conf.get(CONF_EV_CARS) or [],
                },
                now,
                dt_util.get_default_time_zone(),
                int(conf.get(CONF_USAGE_LOOKBACK_WEEKS, DEFAULT_USAGE_LOOKBACK_WEEKS)),
                net_energy,
                _state_in_unit(self.hass, conf.get(CONF_EV_POWER_ENTITY), ("kW",), 1000.0),
                _state_in_unit(self.hass, conf.get(CONF_EV_ENERGY_ENTITY), ("Wh",), 0.001),
                EV_DAYS,
                victron=ev_victron,
            )
            # the car's grid windows (Victron charger) don't come out of the
            # house battery: the grid setpoint covers them
            ev_grid = (ev_attribute or {}).get("grid_120h") or [0.0] * len(ev_total)
            if any(ev_total):
                usage_forecast = [round(u + e - g, 3) for u, e, g in zip(usage_forecast, ev_total, ev_grid)]
                net_energy = forecasting.build_net_energy(solar_forecast, usage_forecast)
        # the forecast check's snapshot of today (once, at the day's first
        # cycle): solar and the house's usage without the car
        day_hours = self._day_hours(now.date())
        house_forecast = usage_forecast if not ev_total else [round(u - e, 3) for u, e in zip(usage_forecast, ev_total)]
        self.acc.snapshot(
            now.date().isoformat(), day_hours, int(now.replace(minute=0, second=0, microsecond=0).timestamp()),
            solar_forecast, house_forecast,
        )
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

        # real quarters since midnight (as of 2026.10.25): the price list has
        # 100 units the day summer time ends and 92 the day it starts
        current_price_unit = units.price_unit(now)

        # What a grid charge really adds to the battery per quarter (as of
        # 2026.10.4): the battery's max charge speed minus the solar already
        # charging it, so the charge plans skip quarters the sun already fills
        # and make their windows long enough.
        rate_units = max(len(all_price), 192)
        # The night limit (as of 2026.10.18): 22:00-07:00 its own speeds
        # replace every other charge/discharge speed
        night_on = bool(conf.get(CONF_NIGHT_LIMIT_ENABLED))
        night_charge_kw = float(conf.get(CONF_NIGHT_CHARGE_SPEED_KW, DEFAULT_NIGHT_CHARGE_SPEED_KW)) if night_on else None
        night_discharge_kw = float(conf.get(CONF_NIGHT_DISCHARGE_SPEED_KW, DEFAULT_NIGHT_DISCHARGE_SPEED_KW)) if night_on else None
        charge_rates = forecasting.grid_charge_rates(
            net_energy, now, charge_speed_kw, max_battery_charge_speed_kw, rate_units,
            charge_efficiency, discharge_efficiency, night_kw=night_charge_kw,
        )
        negative_charge_rates = forecasting.grid_charge_rates(
            net_energy, now, negative_price_charge_speed_kw, max_battery_charge_speed_kw, rate_units,
            charge_efficiency, discharge_efficiency, night_kw=night_charge_kw,
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
        if not self._started_logged:
            self._started_logged = True
            _LOGGER.info(
                "ESS Manager (%s): first plan with capacity %s kWh, min SOC %s%%, max SOC %s%%, charge speed %s kW, "
                "discharge speed %s kW", self.entry.title, capacity_kwh, min_soc_deficit_percent, max_soc_percent,
                charge_speed_kw, discharge_speed_kw,
            )
        if replan:
            _LOGGER.info("ESS Manager (%s): started or a setting changed - re-planning, running windows included", self.entry.title)
        # A switch between solar surplus and deficit changes the minimum SOC
        # every plan works with, so it re-plans running windows too (v0.5.13).
        if self._last_solar_mode is not None and solar_mode["mode"] != self._last_solar_mode:
            _LOGGER.info(
                "ESS Manager (%s): solar mode %s -> %s - re-planning, running windows included",
                self.entry.title, self._last_solar_mode, solar_mode["mode"],
            )
            replan = True
        self._last_solar_mode = solar_mode["mode"]

        # -- the plans --------------------------------------------------------------
        # As of 2026.10.20 worked out on a worker thread: pure Python, and on a
        # small machine (a Raspberry Pi) heavy enough to stall Home Assistant's
        # event loop - every other integration with it - for a moment each
        # cycle. It only reads the values gathered above and writes this
        # coordinator's own plan state; nothing else touches that meanwhile
        # (the cycle is awaited), and a setting changed meanwhile is counted
        # by _replan_requested, settled below on the event loop.
        def _plans() -> dict[str, Any]:
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
                self._negative_price_plan = forecasting.night_discharge_plan(lambda kw: plans.compute_negative_price_plan(
                    self._negative_price_plan,
                    current_price_unit,
                    now,
                    all_price,
                    negative_price_threshold,
                    battery_forecast_clipped,
                    kw,
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
                    max_discharge_kw=max_battery_discharge_speed_kw,
                    usage=usage_forecast,
                ), discharge_speed_kw, night_discharge_kw, now=now)
            else:
                self._negative_price_plan = {"active": False}

            forecast_with_negative_price = plans.compose_forecast_with_negative_price(
                battery_forecast, self._negative_price_plan, current_price_unit, now, high_threshold_kwh - 0.01
            )

            # -- spike plan ------------------------------------------------------
            if conf.get(CONF_ENABLE_SPIKE_PLAN, True):
                self._spike_plan = forecasting.night_discharge_plan(lambda kw: plans.compute_spike_plan(
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
                    kw,
                    self._negative_price_plan,
                    minimum_charge_target_kwh,
                    buy_price=buy_price,
                    charge_efficiency=charge_efficiency,
                    discharge_efficiency=discharge_efficiency,
                    replan=replan,
                    charge_rates=charge_rates,
                    today_units=len(today_price) or 96,
                    max_discharge_kw=max_battery_discharge_speed_kw,
                ), spike_discharge_speed_kw, night_discharge_kw, now=now)
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

            self._high_discharge_plan = forecasting.night_discharge_plan(lambda kw: plans.compute_high_discharge_plan(
                self._high_discharge_plan,
                current_price_unit,
                forecast_with_spike,
                now,
                kw,
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
                # a sale before an overflow has to beat the overflow's own price
                # (as of 2026.10.10)
                capacity_kwh=upper_limit_kwh,
                # sales in blocks too, no shorter than a charge block (2026.10.10)
                min_sale_units=min_charge_units,
                max_discharge_kw=max_battery_discharge_speed_kw,
            ), discharge_speed_kw, night_discharge_kw, now=now)

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
                today_units=len(today_price) or 96,
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

            return {
                "battery_forecast_adjusted": battery_forecast_adjusted,
                "battery_forecast_adjusted_uncapped": battery_forecast_adjusted_uncapped,
                "card_plans": card_plans,
                "charge_kwh": charge_kwh,
                "charge_start_text": charge_start_text,
                "charge_stop_text": charge_stop_text,
                "control_action": control_action,
                "discharge_kwh": discharge_kwh,
                "discharge_start_text": discharge_start_text,
                "discharge_stop_text": discharge_stop_text,
                "forecast_with_negative_price": forecast_with_negative_price,
                "forecast_with_spike": forecast_with_spike,
                "solar_surplus": solar_surplus,
                "system_status": system_status,
            }

        _planned = await self.hass.async_add_executor_job(_plans)
        battery_forecast_adjusted = _planned["battery_forecast_adjusted"]
        battery_forecast_adjusted_uncapped = _planned["battery_forecast_adjusted_uncapped"]
        card_plans = _planned["card_plans"]
        charge_kwh = _planned["charge_kwh"]
        charge_start_text = _planned["charge_start_text"]
        charge_stop_text = _planned["charge_stop_text"]
        control_action = _planned["control_action"]
        discharge_kwh = _planned["discharge_kwh"]
        discharge_start_text = _planned["discharge_start_text"]
        discharge_stop_text = _planned["discharge_stop_text"]
        forecast_with_negative_price = _planned["forecast_with_negative_price"]
        forecast_with_spike = _planned["forecast_with_spike"]
        solar_surplus = _planned["solar_surplus"]
        system_status = _planned["system_status"]
        if replan:
            # only what this cycle saw - a change made meanwhile still counts
            self._replan_requested = max(self._replan_requested - replan_seen, 0)

        # Problem notice (as of 2026.10.23): even with the plans the battery
        # runs into a dip below its (hard) minimum within the next 24 hours
        # that have prices and lie within the planning horizon - e.g. a
        # charge that can't fit.
        priced_hours = max((len(all_price) - current_price_unit) // 4, 0)
        floor_kwh = deficit_floor_kwh if deficit_floor_kwh is not None else low_threshold_kwh
        dip = below_minimum(
            battery_forecast_adjusted, floor_kwh, min(24, priced_hours, planning_horizon_hours), max(0.3, 0.02 * capacity_kwh)
        )
        dip_placeholders = {}
        if dip is not None:
            at = units.shift(now.replace(minute=0, second=0, microsecond=0), timedelta(hours=dip[0] + 1))
            dip_placeholders = {
                "time": at.strftime("%H:%M"),
                "soc": f"{dip[1] / capacity_kwh * 100:.0f}" if capacity_kwh else "?",
                "minimum": f"{floor_kwh / capacity_kwh * 100:.0f}" if capacity_kwh else "?",
            }
        self.problems.report("battery_below_minimum", dip is not None, now, dip_placeholders)

        await self._async_persist()

        # -- direct control ----------------------------------------------------
        # Always worked out (and shown), even with control off, so the
        # planned setpoint can be compared against an existing automation
        # before switching over. Only sent when a control mode is chosen and
        # the "Automatic control" switch is on.
        night_now = night_on and forecasting.is_night_hour(now.hour)
        control_power_kw = control.action_power_kw(
            control_action,
            # the night speeds limit every speed (as of 2026.10.27)
            forecasting.night_limit(charge_speed_kw, night_charge_kw) if night_now else charge_speed_kw,
            forecasting.night_limit(discharge_speed_kw, night_discharge_kw) if night_now else discharge_speed_kw,
            forecasting.night_limit(negative_price_charge_speed_kw, night_charge_kw) if night_now else negative_price_charge_speed_kw,
            forecasting.night_limit(spike_discharge_speed_kw, night_discharge_kw) if night_now else spike_discharge_speed_kw,
        )
        # the Victron charger (as of 2026.10.27): in a grid window of the
        # plugged-in car the grid setpoint goes up by what the car takes, so
        # the house battery stays out of it
        ev_offset_kw = self._ev_grid_offset_kw(ev_victron, ev_entities, now) if ev_victron else 0.0
        await self.controller.async_apply(
            control_settings, control_action, control_power_kw, system_status, offset_kw=ev_offset_kw
        )
        self._ev_offset_w = ev_offset_kw * 1000.0 if control_settings.active and self.controller.enabled else 0.0
        if ev_victron is not None:
            await self._async_ev_charger(conf, ev_entities, now, control_settings)
        await self._async_ev_send()
        control_attr = self.controller.as_attribute(control_settings, control_action, control_power_kw)
        self._report_control_problem(now)
        self._record_decision({
            "action": control_action,
            "power_kw": round(control_power_kw, 3),
            "value": control_attr.get("planned_value"),
            "unit": control_attr.get("unit"),
            "sending": control_attr.get("sending"),
            "status": system_status,
            "error": control_attr.get("last_error"),
            "soc_percent": round(soc_now_percent, 1),
            "price": all_price[current_price_unit] if 0 <= current_price_unit < len(all_price) else None,
            "night_limit": bool(night_now),
        })

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
            "control": control_attr,
            "night_limit": {
                "enabled": night_on, "active_now": night_now, "from": f"{forecasting.NIGHT_FROM_HOUR:02d}:00",
                "until": f"{forecasting.NIGHT_UNTIL_HOUR:02d}:00", "charge_kw": night_charge_kw, "discharge_kw": night_discharge_kw,
            } if night_on else None,
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
            # The electric car's sessions and forecast (as of 2026.10.11) -
            # ev_runtime.EvRuntime.update; None while the EV is switched off.
            "ev": ev_attribute,
            # The heat pump model (as of 2026.10.16) - heatpump_runtime.
            "heat_pump": hp_attribute,
            # The forecast check (as of 2026.10.22) - the forecast check card.
            "forecast_check": self.acc.attribute(buffer_info, self.auto_buffer_entity_id),
            # problems going on and whether they became a Repairs notice (2026.10.23)
            "problems": self.problems.active(),
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
