"""Hide entities that have nothing to do with the current configuration
(as of v0.3.2) - the Automatic control switch while direct control is off,
and each plan's own sensors/numbers while that plan is switched off in
Configure. Uses Home Assistant's own "hidden" flag (entity registry
hidden_by), so a hidden entity keeps working and keeps its value/history,
and is still listed on the device page under "hidden entities".

Rules:
- It only acts when the relevant setting CHANGES. The state it last acted
  on is stored in the entity's registry options, so this survives restarts
  and a user who unhides an entity anyway keeps it visible.
- Switched off -> hidden, unless the user already hid it themselves (then
  nothing to do).
- Switched on -> ALWAYS shown again, even if the user hid it themselves:
  they may not know the entity belonged to the plan they just switched on
  (Timo's rule).
- The very first time (nothing stored yet), only the integration's own
  hiding is undone - a user-hidden entity on an already-enabled plan stays
  hidden.
"""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

_OPTION_KEY = "relevant"


@callback
def async_sync_visibility(entity: Entity, relevant: bool) -> None:
    """Apply the rules above for `entity`, given whether it's currently
    relevant (its plan / direct control is switched on)."""
    entry = entity.registry_entry
    if entry is None or entity.hass is None:
        return
    stored = (entry.options.get(DOMAIN) or {}).get(_OPTION_KEY)
    if stored is not None and bool(stored) == relevant:
        return
    registry = er.async_get(entity.hass)
    if not relevant:
        if entry.hidden_by is None:
            registry.async_update_entity(entity.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION)
    elif entry.hidden_by is not None and (stored is not None or entry.hidden_by == er.RegistryEntryHider.INTEGRATION):
        registry.async_update_entity(entity.entity_id, hidden_by=None)
    registry.async_update_entity_options(entity.entity_id, DOMAIN, {_OPTION_KEY: relevant})
