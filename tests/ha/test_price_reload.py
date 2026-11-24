"""The integration behind the price sensor is reloaded when the prices stay
missing (price_reload.py): not right after the start, then less and less
often, starting over once the prices are back; a sensor without an
integration is never reloaded."""
from datetime import timedelta

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import BASE_DATA, base_states, prices_today_tomorrow


async def _entry(hass):
    entry = MockConfigEntry(domain="ess_manager", version=2, title="Thuis", data=dict(BASE_DATA))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data["ess_manager"][entry.entry_id]["coordinator"]


def _price_integration(hass):
    """sensor.price belongs to a (fake) price integration's config entry."""
    price_entry = MockConfigEntry(domain="fake_prices", title="Prices")
    price_entry.add_to_hass(hass)
    reg = er.async_get(hass)
    ent = reg.async_get_or_create("sensor", "fake_prices", "price-1", config_entry=price_entry,
                                  suggested_object_id="price")
    assert ent.entity_id == "sensor.price"
    return price_entry


def _record_reloads(hass, monkeypatch):
    reloads: list = []

    async def fake_reload(entry_id):
        reloads.append(entry_id)
        return True

    monkeypatch.setattr(hass.config_entries, "async_reload", fake_reload)
    return reloads


async def _minutes(hass, freezer, coordinator, minutes):
    for _ in range(minutes):
        freezer.tick(timedelta(minutes=1))
        await coordinator.async_refresh()
        await hass.async_block_till_done()


async def test_price_integration_reloaded_with_backoff(hass, freezer, monkeypatch):
    price_entry = _price_integration(hass)
    base_states(hass, dt_util.now())
    entry, coordinator = await _entry(hass)
    reloads = _record_reloads(hass, monkeypatch)
    hass.states.async_set("sensor.price", "unavailable")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    await _minutes(hass, freezer, coordinator, 8)
    assert reloads == []                                     # missing > 5 min, but within 10 min of the start
    await _minutes(hass, freezer, coordinator, 2)
    assert reloads == [price_entry.entry_id]                 # first reload
    await _minutes(hass, freezer, coordinator, 14)
    assert len(reloads) == 1
    await _minutes(hass, freezer, coordinator, 1)
    assert len(reloads) == 2                                 # 15 min later
    await _minutes(hass, freezer, coordinator, 30)
    assert len(reloads) == 3                                 # 30 min later
    await _minutes(hass, freezer, coordinator, 60)
    assert len(reloads) == 4                                 # then every hour
    await _minutes(hass, freezer, coordinator, 60)
    assert len(reloads) == 5
    diag = coordinator.price_reload.as_diag()
    assert diag["attempts"] == 5 and diag["last_result"] == "ok" and diag["entry_id"] == price_entry.entry_id
    # today's prices were stored: planning goes on, the notice says so (not "paused")
    assert ir.async_get(hass).async_get_issue("ess_manager", f"input_unavailable_{entry.entry_id}") is None
    issue = ir.async_get(hass).async_get_issue("ess_manager", f"prices_cached_{entry.entry_id}")
    assert issue is not None and issue.translation_placeholders["reloads"] == "5"
    # prices back: everything starts over
    hass.states.async_set("sensor.price", "0.25", prices_today_tomorrow(dt_util.now()))
    await _minutes(hass, freezer, coordinator, 1)
    assert coordinator.price_reload.attempts == 0 and coordinator.price_reload.since is None
    assert ir.async_get(hass).async_get_issue("ess_manager", f"prices_cached_{entry.entry_id}") is None
    # missing again later: first reload 5 minutes after it went missing
    hass.states.async_set("sensor.price", "unavailable")
    await _minutes(hass, freezer, coordinator, 5)          # the first cycle that sees it + 4 minutes
    assert len(reloads) == 5
    await _minutes(hass, freezer, coordinator, 1)
    assert len(reloads) == 6


async def test_price_reload_without_integration(hass, freezer, monkeypatch):
    # no registry entry for sensor.price (e.g. a YAML template): never reloaded
    base_states(hass, dt_util.now())
    entry, coordinator = await _entry(hass)
    reloads = _record_reloads(hass, monkeypatch)
    hass.states.async_set("sensor.price", "unavailable")
    await _minutes(hass, freezer, coordinator, 30)
    assert reloads == []
    assert coordinator.price_reload.last_result == "no_integration"


async def test_price_reload_skips_disabled_entry(hass, freezer, monkeypatch):
    from homeassistant.config_entries import ConfigEntryDisabler

    price_entry = _price_integration(hass)
    base_states(hass, dt_util.now())
    entry, coordinator = await _entry(hass)
    await hass.config_entries.async_set_disabled_by(price_entry.entry_id, ConfigEntryDisabler.USER)
    reloads = _record_reloads(hass, monkeypatch)            # after disabling (that reloads by itself)
    hass.states.async_set("sensor.price", "unavailable")
    await _minutes(hass, freezer, coordinator, 30)
    assert reloads == []
    assert coordinator.price_reload.last_result == "disabled"
