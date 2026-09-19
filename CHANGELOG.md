# Changelog

Every push to this repo bumps `custom_components/ess_manager/manifest.json`'s
`version` by 0.0.1 (the patch digit) and gets an entry here - this is what
lets HACS reliably tell installed instances an update exists. Cutting an
actual GitHub Release with a matching `vX.Y.Z` tag is a separate, manual
step (see the README) - do that whenever you want HACS to pick up
everything published since the last release, not necessarily after every
single patch bump.

## [0.1.14] - 2026-09-19

### Fixed
- Neither dashboard chart actually showed the full-charge plan's window:
  the price chart's "Buy" price highlight and Today's/Tomorrow's-prices
  exclusion logic were updated for it back in 0.1.12, but the battery/
  energy forecast chart (`dashboard/battery_forecast_chart.yaml`) never
  was, and separately, the underlying `battery_forecast_adjusted`
  attribute that its "SOC new" line is drawn from never factored the
  full-charge plan into its math at all - only the low/high charge plans
  did. So even a correctly-updated chart would have shown a flat line
  straight through a scheduled or in-progress full charge. Fixed both:
  `plans.compose_forecast_adjusted` now also takes the full-charge plan
  and adds its charging-phase energy the same way it already does for the
  low charge plan (over the plan's own `start_unit`/`end_unit`), and
  `battery_forecast_chart.yaml`'s "Buy" area highlight now checks the
  full-charge plan first, same priority order as the price chart.
- The full-charge plan's "holding" phase (waiting for the cells to
  balance after reaching 100%, up to `full_charge_max_hold_minutes`) was
  invisible to the forecast entirely - the battery genuinely sits pinned
  at 100% during that wait rather than declining with usage like it
  normally would, but nothing modeled that. `compute_full_charge_plan`'s
  "holding" phase result now also carries `hold_start_unit`/
  `hold_end_unit` (an estimate of the hold's span, from when it started
  to `max_hold_minutes` later - the real end is still decided live, by
  voltage balance or the timeout), and `compose_forecast_adjusted` pins
  the forecast to the battery's full capacity across that range instead
  of applying a delta. `battery_forecast_chart.yaml` also gained a
  separate "Balancing" band using the same fields, so the chart doesn't
  look like the charge window just ends with nothing explaining the flat
  100% line that follows it.
- Along the way, `battery_forecast_adjusted` was being computed before
  the full-charge plan even existed for the cycle (the full-charge plan
  was computed further down in `coordinator.py`) - reordered so the
  full-charge plan is computed first; it doesn't depend on anything from
  the low/high charge plans or `forecast_with_spike`, so this only
  changes what the forecast can see, not the full-charge plan's own
  result.

## [0.1.13] - 2026-09-19

### Added
- A cap on how much a single full-charge/balance session commits to, and
  the ability to spread a too-big charge across multiple days/sessions
  instead of one very long window - ported from the same pattern already
  proven on Timo's houseboat charge system. A single session's energy
  target is now capped at 30x the home's own average hourly consumption
  over the forecasted next 5 days (a new `session_cap_kwh` attribute on
  `full_charge_plan`), which matters most with a slow charger and a large
  deficit: previously the plan would size one very long single window
  (potentially extending past the known price horizon) and, once started,
  hold the setpoint on indefinitely regardless of price until the battery
  actually reached 100%. Now, if a session's window runs out without
  reaching full, it stops and lets the next cycle plan a fresh session
  against the reduced remaining deficit - since the "days since last full
  charge" tracking only resets once the battery is genuinely full, this
  naturally repeats over consecutive days, each time picking whatever's
  cheapest, until the charge actually completes.
- Once a cheap window is found, the plan now also checks the price
  immediately before and after it and extends the window (in either
  direction, one 15-minute unit at a time) as long as the neighboring
  price stays within 8% or EUR 0.02 of the window's own average price -
  whichever tolerance is easier to satisfy. Same "extend into a flat
  block" idea as the houseboat system: it's fine to charge a bit longer
  than the strict minimum if the surrounding price is basically
  unchanged, rather than always stopping exactly at the computed minimum
  duration.

## [0.1.12] - 2026-09-19

### Fixed
- The full-charge balancing plan could be genuinely scheduled or actively
  charging and yet the "Charge amount"/"Charge start"/"Charge stop"
  sensors (and the dashboard's blue "Buy" price-chart overlay) showed
  nothing at all - `charge_energy_kwh`/`charge_start_time`/
  `charge_stop_time` were derived only from the negative-price, spike, and
  low-charge plans; `full_charge_plan` was never wired into that display
  logic, even though it was already wired into `system_status`. On top of
  that, `system_status` itself only special-cased the full-charge plan's
  "charging"/"holding" phases - its "scheduled" phase (a window has been
  picked, but hasn't started yet) fell through to a plain "Standby",
  giving no indication anything was planned. Fixed both: `display.
  charge_display` now takes the full-charge plan as its highest-priority
  input (ahead of the day-to-day cost-driven plans, since a full charge is
  a deliberate, infrequent maintenance action) for its "scheduled" and
  "charging" phases - "holding" isn't a charge window and correctly falls
  through to the other plans instead; `system_status` now reports "Full
  charge scheduled" during the scheduled phase instead of "Standby"; and
  `dashboard/price_apexcharts_card.yaml`'s "Buy" series and Today's/
  Tomorrow's-prices exclusion logic now also recognize the full-charge
  plan's window, with the same priority order, so the chart actually shows
  it.

## [0.1.11] - 2026-09-19

### Fixed
- "Charge amount" and "Discharge amount" showed "Unknown" whenever no plan
  was active, while "Charge start"/"Charge stop"/"Discharge start"/
  "Discharge stop" showed the friendlier "-" placeholder for the exact same
  situation - an inconsistency, not something intentional. They now all
  show "-". The reason the amount sensors couldn't just do this before
  (the v0.1.6 fix) is that they carry a unit of measurement (kWh), and
  Home Assistant raises instead of showing "unknown" if a unit-bearing
  sensor is ever given a non-numeric state like "-". Fixed by hiding the
  unit itself whenever there's nothing to show (a new
  `native_unit_of_measurement` override alongside `native_value`), so "-"
  is safe to report; the kWh unit reappears normally the moment a real
  amount is available again.

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
