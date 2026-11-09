"""The thermostat's history from the real recorder (2026.11.27): updates where
only the attributes change (hvac_action, wanted temperature) come in too -
a climate entity's state stays "heat" all the time."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.ess_manager import statistics_source


async def test_thermostat_attribute_changes_are_read(recorder_mock, hass):
    start = dt_util.utcnow() - timedelta(minutes=5)
    attrs = {"current_temperature": 20.8, "temperature": 21.0}
    for action, temp in (("idle", 21.0), ("heating", 21.0), ("idle", 21.0), ("idle", 20.0), ("heating", 20.0)):
        hass.states.async_set("climate.woonkamer", "heat", {**attrs, "hvac_action": action, "temperature": temp})
        await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    states = await statistics_source.async_fetch_state_changes(
        hass, "climate.woonkamer", start, dt_util.utcnow() + timedelta(seconds=1))
    actions = [st.attributes.get("hvac_action") for st in states]
    wanted = [st.attributes.get("temperature") for st in states]
    assert actions == ["idle", "heating", "idle", "idle", "heating"], actions
    assert wanted[-1] == 20.0
