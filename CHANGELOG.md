# Changelog

Every push to this repo bumps `custom_components/ess_manager/manifest.json`'s
`version` by 0.0.1 (the patch digit) and gets an entry here - this is what
lets HACS reliably tell installed instances an update exists. Cutting an
actual GitHub Release with a matching `vX.Y.Z` tag is a separate, manual
step (see the README) - do that whenever you want HACS to pick up
everything published since the last release, not necessarily after every
single patch bump.

## [0.1.10] - 2026-09-18

### Added
- An alternative way to supply the cell voltage differential used by the
  full-charge balancing plan: instead of a BMS that already exposes the
  differential as its own sensor, you can now point the integration at the
  lowest and highest individual cell voltage sensors instead, and it
  calculates the differential itself as (highest - lowest), converted from
  volts to millivolts to match the existing single-sensor convention. Both
  fields are optional and independent of the original "cell voltage
  differential sensor" field - if you already have that configured,
  nothing changes; if you only have per-cell voltage sensors (a more
  common shape for many BMS integrations), you can use those instead. The
  computed value is also now exposed as a `cell_voltage_differential_mv`
  attribute on the Status sensor, so you can see what it's reading.

## [0.1.9] - 2026-09-18

### Added
- A third household usage forecast source: "Use a home energy consumption
  sensor I already have." If you already have a sensor that reports your
  home's total energy consumed (a whole-home energy monitor, for example),
  you can point the integration straight at it instead of deriving
  consumption from the solar/import/export/battery energy balance. This
  sidesteps a real limitation of the calculated option: if those four
  entities don't all update at similar resolution (e.g. a grid meter that
  only reports in coarse 0.1 kWh steps a few times an hour, next to a
  battery sensor updating every couple of minutes), Home Assistant's hourly
  statistics can misattribute a real, continuous energy flow entirely to
  whichever single hour the coarse sensor happened to tick over in -
  producing a noisy, sometimes even briefly negative, per-hour usage
  forecast even though the daily total works out fine. A direct
  consumption sensor has only one term, so there's nothing for it to
  disagree with. Same historical-hour-averaging methodology and lookback
  window as the calculated option, just without the derivation - accepts
  more than one entity if your home's consumption is split across multiple
  monitors/circuits (they're summed together, same as the calculated
  option's import/solar fields).

## [0.1.8] - 2026-09-18

### Fixed
- `sync-and-push.command` failed with "fatal: No configured push
  destination" on every run in a folder whose `origin` remote had never
  been set - which happens for any freshly unzipped folder, since every
  zip is deliberately built with its remote removed (so a GitHub access
  token never ends up embedded in a shipped file), and previously required
  a one-time manual `git remote add origin ...` to fix. The script now
  detects a missing `origin` and adds it automatically, and the push step
  itself sets the upstream tracking branch on every run (harmless once
  already set), which the first push after auto-adding the remote needs -
  no more one-time manual git commands.

## [0.1.7] - 2026-09-18

### Fixed
- Submitting the setup or options form with the grid/inverter setpoint,
  cell voltage differential, or either calculated-usage-forecast battery
  energy field genuinely left blank failed validation with "Entity None
  is neither a valid entity ID nor a valid UUID" - a real, blocking error
  on submit, not just a cosmetic pre-fill issue. The v0.1.4 fix (defaulting
  these fields to `None` instead of `""`) only addressed the *display*:
  voluptuous still substitutes and validates a field's default whenever
  it's missing from the submitted data, and Home Assistant's entity
  selector has no special case for `None`, so it got rejected exactly as
  if `None` were a real (bad) entity ID. All four fields' selectors are
  now wrapped in `vol.Maybe(...)`, which accepts a literal `None` outright
  before validation - confirmed against Home Assistant's own selector and
  form-serialization code that this still renders the normal entity-picker
  widget, it just no longer chokes on being left empty.

## [0.1.6] - 2026-09-17

### Fixed
- The Home Assistant log filled with repeated "Unexpected error updating
  listener" crashes from `sensor.py`, ultimately raising `ValueError:
  Sensor sensor.ess_manager_discharge_amount ... has ... unit 'kWh' ...
  however, it has the non-numeric value: '-'`. Cause: the charge/discharge
  amount, start and stop display sensors fall back to the literal text
  "-" whenever no charge or discharge plan is currently active - a normal,
  frequent state, not an error. Home Assistant treats a sensor's unit of
  measurement (kWh, in this case) as a promise that its state is always
  numeric or `None`, and raises instead of just showing "unknown" the
  moment a unit-bearing sensor reports a string like "-". Fixed by only
  using the "-" placeholder for the genuinely unit-less display sensors
  (start/stop times, spike status text); the kWh/day sensors (battery
  level, charge/discharge amount, next full charge in) now report `None`
  when there's nothing to show, which Home Assistant renders as "unknown"
  without erroring.

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
