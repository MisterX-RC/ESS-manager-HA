"""The heat pump model with a thermostat (as of 2026.11.20): its switches read
from the climate entity's history, kept, learned and handed to the house model."""
from datetime import timedelta

from homeassistant.core import State, SupportsResponse
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ess_manager.diagnostics import async_get_config_entry_diagnostics

from .conftest import BASE_DATA, base_states

HP_DATA = {
    "hp_enabled": True, "hp_meter": "separate", "hp_heat_entities": ["sensor.qube_heat"],
    "hp_outdoor_entity": "sensor.outdoor", "hp_weather_entity": "weather.home",
    "hp_setpoint_entity": "climate.house", "hp_indoor_entity": "sensor.indoor", "hp_hourly_enabled": True,
}


def _thermostat_history(start, end):
    """A generic thermostat at 21 degC: on at 20.8 (-0.2), off at 21.1 (+0.1), four cycles a day,
    the room reported every 15 minutes before each switch."""
    out = []
    t = dt_util.start_of_local_day(start)
    while t < end:
        for minute, action, room in ((60, "heating", 20.8), (150, "idle", 21.1), (420, "heating", 20.8),
                                     (500, "idle", 21.1), (800, "heating", 20.8), (880, "idle", 21.1),
                                     (1200, "heating", 20.8), (1290, "idle", 21.1)):
            ts = t + timedelta(minutes=minute)
            if start <= ts < end:
                for back in (30, 15):       # the room moving towards the switch
                    tb = ts - timedelta(minutes=back)
                    out.append(State("climate.house", "heat", {"hvac_action": "idle" if action == "heating" else "heating",
                                                               "temperature": 21.0, "current_temperature": 21.0},
                                     last_changed=tb, last_updated=tb))
                out.append(State("climate.house", "heat", {"hvac_action": action, "temperature": 21.0,
                                                           "current_temperature": room}, last_changed=ts, last_updated=ts))
        t += timedelta(days=1)
    return sorted(out, key=lambda s: s.last_updated)


async def test_thermostat_learned_from_its_history(hass, monkeypatch):
    from custom_components.ess_manager import coordinator as coord
    from custom_components.ess_manager import heatpump_house

    now = dt_util.now()
    base_states(hass, now)
    hass.states.async_set("sensor.qube_heat", "100", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})
    hass.states.async_set("sensor.outdoor", "5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.indoor", "21.0", {"unit_of_measurement": "°C"})
    hass.states.async_set("climate.house", "heat", {"hvac_action": "idle", "temperature": 21.0, "current_temperature": 21.0})

    async def history(hass_, entity_id, start, end):
        return _thermostat_history(start, end) if entity_id == "climate.house" else []

    monkeypatch.setattr(coord, "async_fetch_state_changes", history)
    learned = {}

    def fake_learn(*args, **kwargs):
        learned["thermo"], learned["on_s"], learned["setpoint"] = args[14], args[15], args[16]
        return {"cop": None, "cop_check": None, "model": None, "review": None, "thermostat": args[14]}

    monkeypatch.setattr(heatpump_house, "learn", fake_learn)

    async def forecasts(call):
        base = dt_util.start_of_local_day(now)
        if call.data["type"] == "daily":
            return {"weather.home": {"forecast": [{"datetime": (base + timedelta(days=k, hours=12)).isoformat(),
                                                   "temperature": 6.0, "templow": 2.0} for k in range(6)]}}
        return {"weather.home": {"forecast": []}}

    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data={**BASE_DATA, **HP_DATA})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data["ess_manager"][entry.entry_id]["coordinator"]

    events = coordinator.hp.thermo["events"]
    assert len(events) >= 60 and all(e[3] == 21.0 for e in events)
    assert sum(1 for e in events if e[5]) >= 60
    thermo = learned["thermo"]
    assert thermo["kind"] == "on_off" and thermo["on_c"] == -0.2 and thermo["off_c"] == 0.1
    assert learned["setpoint"] and set(learned["setpoint"].values()) == {21.0}
    assert learned["on_s"] and max(learned["on_s"].values()) == 3600
    # kept: in the store and in the diagnostics
    stored = await coordinator.store.async_load()
    assert len(stored["hp"]["thermo"]["events"]) == len(events)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["thermostat_events"]["keys"][:2] == ["ts", "on"] and len(diag["thermostat_events"]["rows"]) == min(len(events), 200)
