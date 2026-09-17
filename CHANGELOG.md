# Changelog

Every push to this repo bumps `custom_components/ess_manager/manifest.json`'s
`version` by 0.0.1 (the patch digit) and gets an entry here - this is what
lets HACS reliably tell installed instances an update exists. Cutting an
actual GitHub Release with a matching `vX.Y.Z` tag is a separate, manual
step (see the README) - do that whenever you want HACS to pick up
everything published since the last release, not necessarily after every
single patch bump.

## [0.1.5] - 2026-09-17

### Fixed
- Opening the integration's options (the gear icon on the configured hub)
  crashed with a generic "Config flow could not be loaded: 500 Internal
  Server Error" instead of showing the options form. Cause: the options
  flow's `__init__` stored `self.config_entry = config_entry` itself, which
  recent Home Assistant core versions handle automatically after
  constructing the flow - an integration that also assigns it manually
  raises an unhandled exception, which the frontend reports as a bare 500.
  The options flow no longer takes or stores `config_entry` in `__init__`;
  it relies on Home Assistant to set `self.config_entry` for it, same as
  current HA's own guidance for custom integrations.

## [0.1.4] - 2026-09-17

### Fixed
- The optional single-entity fields (grid/inverter setpoint sensor, cell
  voltage differential sensor, and the calculated-usage-forecast's battery
  charge/discharge energy entities) defaulted to an empty string, which the
  Home Assistant frontend's entity picker flags as "Entity is neither a
  valid entity ID nor a valid UUID" even though the field is optional and
  left blank. They now default to no value, so the setup and options forms
  no longer show a false validation error on fields you don't need to fill
  in.

## [0.1.3] - 2026-09-17

### Added
- This changelog, and the versioning policy described above.

## [0.1.2] - 2026-09-17

### Added
- `sync-and-push.command` - a double-clickable macOS helper that syncs the
  newest update zip from Downloads into this folder, commits, and pushes.

## [0.1.1] - 2026-09-16

### Added
- Calculated household usage forecast: the integration can now derive its
  own `h0`..`h120` usage forecast directly from Home Assistant's recorder
  statistics, instead of requiring an external SQL sensor. Supports any
  number of grid import/export and solar production entities (so both
  single- and dual-tariff meters work), with optional battery
  charge/discharge energy entities.

## [0.1.0] - 2026-09-16

### Added
- Initial release: full Home Assistant custom integration, ported from the
  original hand-written `sensor.ess_manager` template sensor - config-flow
  based setup, all five planning engines, every tunable exposed as a
  `number` entity, and restart-durable plan lock-in state.
