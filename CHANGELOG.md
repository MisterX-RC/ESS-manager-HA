# Changelog

Every push to this repo bumps `custom_components/ess_manager/manifest.json`'s
`version` by 0.0.1 (the patch digit) and gets an entry here - this is what
lets HACS reliably tell installed instances an update exists. Cutting an
actual GitHub Release with a matching `vX.Y.Z` tag is a separate, manual
step (see the README) - do that whenever you want HACS to pick up
everything published since the last release, not necessarily after every
single patch bump.

## [0.1.29] - 2026-09-21

### Changed
- **`dashboard/battery_forecast_chart.yaml`**'s chart height reduced from
  300px to 270px.

## [0.1.28] - 2026-09-21

### Changed
- **`dashboard/entities_card.yaml`** gained a third `multiple-entity-row`
  line, "Price alerts", showing `sensor.ess_manager_spike_status` and
  `sensor.ess_manager_negative_price_status` side by side (Spike /
  Negative), alongside the existing Charge and Discharge lines.

## [0.1.27] - 2026-09-21

### Added
- **A new `sensor.ess_manager_negative_price_status` sensor**, mirroring
  the existing `sensor.ess_manager_spike_status`: shows "Active (below
  €<threshold>, <achievable charge> kWh)" while the negative price plan
  is active, "Inactive" otherwise. The negative price plan previously had
  no standalone status sensor at all - only `spike_plan` did.

## [0.1.26] - 2026-09-21

### Changed
- **`number.ess_manager_maximum_soc`** now ranges 50-150% (was 0-150%). The
  setup/options-flow field for the same underlying value (Maximum SOC %)
  is now bounded 50-150 as well, so the one-time setup form and the live
  dashboard entity can never disagree.
- **`number.ess_manager_minimum_charge_target`** now ranges 0-10 kWh (was
  0-100 kWh) - a much more usable slider step for a value that's realistically
  only ever a few kWh.

## [0.1.25] - 2026-09-21

### Changed
- **The price dashboard chart (`dashboard/price_apexcharts_card.yaml`) no
  longer needs its own separate reference to your Nordpool (or similar)
  price sensor.** Timo asked whether the chart could pull price data
  straight from `sensor.ess_manager_status` instead, since the integration
  already imports it from Nordpool during its own update cycle - it can:
  every series now reads `sensor.ess_manager_status`'s own `all_price`/
  `current_price_unit` attributes directly, converting each array index to
  a timestamp the same way the battery forecast chart already converts
  plan-window unit indices to timestamps (`now + (i - current_price_unit) *
  15min`), and comparing plan windows by unit index directly instead of
  first converting everything to milliseconds via a locally-reconstructed
  "midnight". Added a new `today_price_units` attribute to `sensor
  .ess_manager_status` (the length of today's own price list) so the chart
  can split `all_price` back into its today/tomorrow halves by index
  exactly, without guessing a 96-unit boundary that would be wrong on a DST
  transition day. The card's setup comment now only asks you to replace
  `sensor.ess_manager_status`'s entity_id - no second price-sensor
  placeholder to fill in.

## [0.1.24] - 2026-09-20

### Fixed
- **Race condition that could silently skip a genuinely-due holding phase.**
  `coordinator.py` used to reset `_last_full_reached` (and thus the "days
  since last full charge" clock) the instant raw SOC crossed 99.5%,
  computed *before* calling `compute_full_charge_plan` each cycle. On the
  exact cycle a due, waiting-on-solar plan's SOC first crossed 99.5% (a
  `relying_on_peak_unit`-style scenario), that same-cycle reset could flip
  the plan's own `due` check to `False` before it ever got a chance to
  enter `holding` - silently skipping the whole balance cycle. The reset
  now happens strictly *after* `compute_full_charge_plan` runs, and only
  when its own output says balance was genuinely confirmed (see
  `balance_confirmed` below) - never from an independent, earlier SOC
  check.

### Added
- **Full-charge balancing reworked per Timo's two-situation spec.**
  `compute_full_charge_plan` and `compute_system_status` now handle both:
  - *Nothing due, but the battery reaches 100% anyway* (typically solar
    alone) - nothing is forced. The plan quietly checks all three
    confirmation legs (below) every cycle in the background and, once
    satisfied together, reports `balance_confirmed: true` so
    `coordinator.py` can reset the interval clock without ever starting an
    active plan.
  - *A full balance is due* and the plan is waiting on a forecasted solar
    peak - unchanged up to the point SOC reaches 99.5%, at which the hold
    phase starts exactly as before. What's new: `compute_system_status`
    now reports `Start charge` for the **entire** holding duration,
    instead of only once the setpoint readback ramps up past
    `charge_engaged_at` (previously `Balancing` in between). Solar alone
    can hold the battery at 100% with zero grid setpoint ever needed, so
    the old setpoint-based check could show a stuck `Start charge` (or
    never show any indication a hold was even active). `Balancing` is
    retired as a `Status` state - it was never an automation trigger to
    begin with (see `dashboard/automation_example.yaml`), purely cosmetic.
    `Start charge` is the actual signal external automations react to, so
    keeping it up for the whole hold is what actually prevents household
    loads from eroding the SOC while the cells finish balancing.
- **Third confirmation leg: battery pack voltage vs. a new adjustable
  target-voltage `number` entity.** On top of SOC (>=99.5%) and the cell
  voltage differential, "genuinely balanced" now also requires the
  battery's own pack voltage (a new required-alongside-the-full-charge-plan
  entity, `battery_voltage_entity`) to be at or above a new
  `full_charge_target_voltage` `number` entity's value, minus 0.1V. Unlike
  the fixed hardware properties added in earlier versions
  (`max_battery_charge/discharge_speed_kw`), this target voltage is meant
  to be tuned live from a dashboard, so it follows the ordinary
  seed-value + `number`-entity pattern, defaulting to 55.2V (a 48V-class
  LiFePO4 pack, fully charged) - adjust it to your own pack's actual
  full-charge voltage after setup. A missing reading on either the
  battery-voltage sensor or the cell-voltage-differential sensor is always
  treated as "not yet confirmed," never as satisfied.
- **A timed-out hold no longer immediately re-forces another hold.** If
  the "Full charge max hold" safety timeout elapses without ever
  confirming balance, the plan now defers to the same forward-looking
  logic used before any charge was ever forced: if a genuine future solar
  peak is still expected to reach the overshoot ceiling on its own, it
  quietly waits for that (still passively checking for balance
  confirmation the whole time); if not, the charging logic schedules a
  fresh grid-charge session at the cheapest available window instead. A
  new internal `retry_after_timeout` flag (not user-facing) is what
  prevents the very next evaluation from shortcutting straight back into
  `holding` just because SOC still happens to be >=99.5%.
- New `battery_voltage` attribute on `sensor.ess_manager_status`, exposing
  the raw reading alongside the existing `cell_voltage_differential_mv`.

### Changed
- `battery_voltage_entity` is required during setup (and re-editable from
  **Configure**) whenever the full-charge balancing plan is enabled -
  validated the same way `solar_forecast_entities` already is
  (`battery_voltage_entity_required`).

## [0.1.23] - 2026-09-20

### Added
- New `Status` sensor state, `Awaiting solar (full charge)`, for a real gap
  Timo caught from a live entities-card screenshot: `sensor.ess_manager_status`
  showed plain "Standby" while `full_charge_plan.active` was `false` but
  `relying_on_peak_unit: 540` was set - i.e. the full-charge plan had
  correctly concluded a genuine future solar peak (21.24 kWh forecast,
  well past the 15.75 kWh overshoot ceiling, ~4.8 days out) would reach
  the ceiling on its own, so nothing needed buying - but that conclusion
  was completely invisible on the dashboard, indistinguishable from
  "nothing planned at all."
  - `compute_system_status` (`plans.py`) is now a thin wrapper around the
    previous logic (renamed `_compute_system_status_raw`): whenever the
    raw result would be exactly `"Standby"` *and* `full.relying_on_peak_unit`
    is set with `full.active` still `False`, it returns
    `"Awaiting solar (full charge)"` instead. This only ever replaces a
    genuine "nothing else going on" `Standby` - it never overrides a real
    in-progress action from another plan (verified with a dedicated test:
    a low-charge-plan window actively engaged still reports `"Actief"`
    even with `relying_on_peak_unit` set at the same time).
  - Added to the `Status` sensor's documented state list in the README,
    alongside `Full charge scheduled` (added commit 13/v0.1.12, and found
    to have been missing from that same list this whole time - fixed now
    too).
  - Added 2 new tests: the new status shows up when relying on a peak
    with nothing else active, and is correctly *not* shown when a real
    plan (e.g. the low charge plan) is genuinely active at the same time.
    Check count: 77 → 79.
  - No change to `high_discharge_plan`'s own suppression behavior
    (`suppressed_by_full_charge`, added commit 22/v0.1.21) - this is a
    display-only fix, on top of already-correct underlying logic.

## [0.1.22] - 2026-09-20

### Changed
- Max battery charge speed and max battery discharge speed (added in
  0.1.20) are no longer `number` entities. Timo pointed out these aren't
  something to adjust from a live dashboard - they're a fixed hardware
  property (the battery's own physical power limit) - so exposing them as
  a `number` entity that could be nudged in normal use was more than
  needed. They're still set during initial setup, and per Timo's explicit
  choice they remain editable afterward too: through the integration's
  **Configure** (options) screen, the same way entity references
  (`voltage_diff_entity`, `low_cell_voltage_entity`, etc.) are already
  re-editable there, rather than requiring the whole integration to be
  deleted and re-added over a typo or a battery/inverter upgrade.
  - Removed the `NUM_MAX_BATTERY_CHARGE_SPEED_KW`/
    `NUM_MAX_BATTERY_DISCHARGE_SPEED_KW` constants and their two
    `NUMBER_DEFINITIONS` entries from `const.py` - `number.py` needed no
    changes since it's fully data-driven off that list.
  - Added matching `NumberSelector` fields to `EssManagerOptionsFlow`'s
    `init` schema in `config_flow.py` (the setup-time fields in
    `_main_schema` are unchanged).
  - `coordinator.py` now reads `max_battery_charge_speed_kw`/
    `max_battery_discharge_speed_kw` straight from the merged config
    entry (`conf.get(CONF_MAX_BATTERY_CHARGE_SPEED_KW, DEFAULT_...)`)
    instead of `self.get_number(...)`, so an options-flow edit takes
    effect on the next update cycle exactly like the other
    options-editable, non-number config keys.
  - `strings.json`/`translations/en.json` gained labels for the two new
    options-step fields, and the README's tunables section and
    Configuration intro were updated to describe them as a setup+options
    field rather than a `number` entity.
  - No behavior change to the battery energy forecast itself
    (`forecasting.build_battery_forecast`'s capping logic is untouched) -
    only where the two kW values are sourced from changes. Test suite
    unaffected (still 77/77 - none of the changed files are exercised by
    `tests/test_pipeline.py`).

## [0.1.21] - 2026-09-20

### Fixed
- Fixed a real conflict Timo caught from a live attribute dump: the high
  discharge plan (`compute_high_discharge_plan`) could independently sell
  off exactly the future solar surplus the full-charge plan is relying on
  to reach a genuine, sustained overshoot for free. The two plans were
  computed with no awareness of each other - the discharge plan's own
  peak-scan only looks `planning_horizon_hours` ahead (a few days by
  default), while the full-charge plan's peak-scan spans the *entire*
  ~5-day `battery_forecast`. As the timeline advances and a big future
  peak the full-charge plan is counting on slides into the discharge
  plan's shorter horizon, the discharge plan would schedule a real
  discharge at the priciest window before that peak - actual energy
  leaving the real battery - while the full-charge plan kept reading the
  same unadjusted, undischarged forecast and kept concluding "solar
  handles it, nothing to buy." The balance charge the full-charge plan
  was silently counting on would then never actually happen.
  - `compute_full_charge_plan` now returns a `relying_on_peak_unit` field
    (the price unit of the genuine future peak it's anchored to) in both
    the "scheduled" case (buying a partial top-up) and, critically, the
    "skip scheduling entirely" case too (previously that branch just
    returned a bare `{"active": False, "phase": None}`, discarding the
    peak info that made the skip decision safe). `None` for the
    no-future-rise (cheapest-window-anchored) case, which never had this
    conflict to begin with.
  - `compute_high_discharge_plan` gained an optional `suppress_new`
    parameter (default `False`, fully backward compatible): when set, it
    won't schedule a *new* discharge window, but a window already locked
    in and in progress still finishes normally rather than being cut off
    mid-window.
  - `coordinator.py` now computes the full-charge plan first (moved up
    from after the low/high charge plans - it never depended on them),
    and derives `suppress_high_discharge` from it: suppress whenever the
    full-charge plan is actively `charging`/`holding` (discharging then
    would directly fight the charge/hold setpoint), or whenever it's
    relying on a future peak that hasn't happened yet
    (`relying_on_peak_unit` set and still in the future). When suppressed
    this way, `high_discharge_plan` also carries a
    `suppressed_by_full_charge: true` field for visibility on live
    attribute dumps.
  - This is a suppression-only fix (Timo's primary ask): a much larger
    overshoot (e.g. a peak reaching 120%+ against a 110% ceiling) still
    just gets suppressed/curtailed rather than having the discharge plan
    trim the excess back down in a way synchronized to the same peak -
    that's a bigger follow-on feature, deferred for now.
  - Added 6 new tests: `relying_on_peak_unit` is set correctly in both
    the scheduled and skip-entirely cases and left `None` for the
    no-future-rise case; `suppress_new` blocks a brand-new discharge
    window; discharge scheduling is unaffected when `suppress_new` is
    left at its default; and an already-locked-in discharge window
    finishes normally even if `suppress_new` turns on mid-window. Check
    count: 71 → 77.

## [0.1.20] - 2026-09-20

### Added
- Two new setup-time configurables: **Max battery charge speed** and **Max
  battery discharge speed** (kW), seeding two new `number` entities the
  same way battery capacity/charge speed/discharge speed already do.
  These are distinct from the existing "Normal charge speed"/"Normal
  discharge speed" tunables, which are how fast the planning engines
  deliberately charge/discharge *from the grid* - the new pair represents
  the battery's own physical power limit, and only affects the passive,
  solar/usage-driven battery energy forecast
  (`forecasting.build_battery_forecast`), not any of the planning engines.
  Per Timo's spec: when a forecasted hour's solar surplus exceeds the max
  charge speed, only the max charge speed counts toward the battery's
  forecasted energy for that hour (the rest is assumed exported to the
  grid instead); symmetrically, when a forecasted hour's usage deficit
  exceeds the max discharge speed, only the max discharge speed is drawn
  from the battery (the rest is assumed imported from the grid instead).
  `build_battery_forecast` gained two new optional parameters
  (`max_charge_kw`/`max_discharge_kw`, both defaulting to `None` = no
  cap, fully backward compatible) that clamp each hour's net energy
  before it's accumulated - applied to the full-hour-equivalent rate
  *before* the existing partial-current-hour scaling, since that scaling
  only accounts for elapsed time, not the physical power limit. The
  unclamped `net_energy_120h` attribute is untouched, so it still shows
  the raw solar-minus-usage figure for transparency; only
  `battery_forecast` (and everything downstream of it - the low/high/full
  charge plans' peak-anchoring, `battery_forecast_adjusted`, etc.) sees
  the clamped version. Added 5 new tests: the uncapped case is unaffected,
  each cap independently clamps only the hour(s) that exceed it, hours
  already within both limits pass through unchanged, and the cap is
  applied before (not after) the partial-hour scaling. Check count:
  66 → 71.

## [0.1.19] - 2026-09-20

### Fixed
- Fixed a design flaw in v0.1.18's peak-anchored full-charge scheduling:
  when the deficit is anchored to a genuine future peak, the purchased
  top-up window was being scheduled to start *at or after* that peak
  (`search_start = max(cur_unit, anchor_unit)`) - i.e. only once the
  optimal moment had already passed. The peak is where a grid top-up
  should land, combining with solar's own still-rising contribution to
  maximize the real battery's dwell time at true 100% - not a floor to
  wait out. `anchor_unit` is now used as a deadline the window must
  *finish by* (`search_end = min(anchor_unit, len(all_price))`, with the
  search itself starting from right now), mirroring the existing
  `breach_unit` deadline pattern already used by
  `compute_low_charge_plan`/`compute_high_discharge_plan`. The
  no-future-rise (cheapest-window-anchored) case is unaffected - it never
  had a peak-as-floor problem in the first place.
  - `_extend_flat_price_window` gains a new optional `max_end` parameter
    so its flat-price rightward extension also respects this deadline
    instead of potentially growing the window past the peak; left at its
    default (`None`) it behaves exactly as before.
  - Updated the `future_peak_plan` test's expected `start_unit`/`end_unit`
    (previously asserting the window landed *after* the peak at
    `[24, 30)`; now asserts it lands *before/by* the peak at `[0, 24)`,
    recomputed from the actual code rather than by hand) and added two
    new tests for `_extend_flat_price_window`'s `max_end` parameter.

## [0.1.18] - 2026-09-20

### Changed
- The full-charge plan's deficit is no longer always based on the
  battery's level right now. `compute_full_charge_plan` now scans the raw
  (uncapped) battery forecast for its highest point anywhere in the
  forecast horizon (up to ~5 days out):
  - If that peak is genuinely in the future (solar expected to raise the
    battery further), the deficit is anchored to the peak's own
    forecasted level instead of today's, and the charge window is never
    scheduled earlier than when that peak actually happens - buying grid
    energy before a free solar rise would be wasted, even if much
    cheaper prices exist beforehand.
  - If that peak already reaches the same max-SOC-based overshoot
    ceiling used elsewhere for solar headroom (`high_threshold_kwh`, 110%
    by default) - not just a fleeting graze past 100% but a genuine,
    sustained surplus - nothing is scheduled at all. Live SOC crossing
    99.5% (the existing `is_full` check) still drives the holding phase
    on its own, for free.
  - If there's no meaningful future rise (e.g. no solar forecast, so
    today's level effectively already is the peak), the deficit is
    anchored to the battery's own forecasted level at whichever point
    the cheapest available price window actually lands, rather than to
    right now - ordinary usage between now and then still moves the
    number even with no solar in the picture.
  - The deficit reference point itself changed from the nominal 100%
    capacity to the max-SOC overshoot ceiling (`high_threshold_kwh`):
    targeting only 100% would treat the very first instant the forecast
    grazes full as "solar handles it," which usually isn't a real,
    sustained plateau - real physical SOC is still safety-valved to
    never exceed true 100% by the existing `is_full` check regardless of
    this higher reference point.
  - `compute_full_charge_plan`'s `upper_limit_kwh` parameter is renamed
    `high_threshold_kwh` (now passed `high_threshold_kwh` from the
    coordinator instead of the nominal-100% `upper_limit_kwh`), and it
    gains a new required `battery_forecast` parameter (the raw,
    unadjusted solar/usage projection, with no price-driven charging
    baked in). The "scheduled"/"charging" plan dict gains three new
    debug/display fields: `anchor_kwh`, `anchor_unit`, and `peak_kwh`.
  - Added 5 new tests covering all three cases (anchored to a genuine
    future peak and refusing to schedule earlier than it even with
    cheaper prices available first; skipping entirely when the peak
    already reaches the overshoot ceiling; anchoring to the forecasted
    level at the cheapest window when there's no future rise) and
    updated every existing `compute_full_charge_plan` test call for the
    renamed/new parameters (existing tests pass a flat forecast so their
    previously-asserted numbers are unaffected).

## [0.1.17] - 2026-09-20

### Changed
- The full-charge session cap now also floors at a 4-hour-equivalent
  minimum window, expressed in kWh via this session's own
  `charge_speed_kw` (`min_session_kwh = charge_speed_kw * 4`), instead of
  being based purely on 30x the 5-day average hourly usage. This makes
  charge speed itself a factor in whether the cap ever actually binds, per
  Timo: a fast charger (e.g. 10 kW) can fully charge a typical battery in
  a few hours regardless, so its 4-hour floor (40 kWh) sits above any
  realistic single-session deficit and the cap becomes a no-op there -
  `is_full` remains the real backstop, same as before this cap existed at
  all. A slow charger (e.g. 1.8 kW) would otherwise need 8+ hours for the
  same battery, so its much lower 4-hour floor (7.2 kWh) still lets the
  usage-based cap - or the floor itself, whichever is larger - meaningfully
  spread a large deficit across multiple days. The floor only ever raises
  a cap that would otherwise be shorter than 4 hours; a usage-based cap
  that already implies a longer window is left unchanged. Added three new
  tests covering all three cases (floor irrelevant on a fast charger,
  usage-average cap still binding on a slow charger, and the floor itself
  becoming the binding constraint when usage is very low) and updated the
  existing session-cap tests' expected numbers to reflect the new floor.

## [0.1.16] - 2026-09-20

### Changed
- Reverted 0.1.15's blanket rule that a session-capped full charge never
  gets the flat-price window extension. Timo clarified the session cap's
  actual purpose: it exists so the *initial* window search doesn't have
  to reach into meaningfully pricier hours just to fit a large deficit's
  `units_needed` into one sitting - not to put a hard ceiling on how much
  energy a session can ever deliver. The flat-price extension can't
  violate that on its own: it only ever grows a window into neighboring
  units within the same 8%/EUR 0.02 tolerance of the window's own average
  price (see `_extend_flat_price_window`) - by construction, never into
  "the expensive part". So if a long, genuinely flat, cheap price valley
  happens to be available right where a capped session lands, it's fine
  - good, even - to use more of it rather than stopping at the bare
  minimum. The extension now applies uniformly again, whether or not a
  session's target was reduced by the cap. Updated the 0.1.15 regression
  test to assert the opposite of what it asserted before (the window DOES
  extend into an available flat valley, using the same numbers from
  Timo's original report).

## [0.1.15] - 2026-09-20

### Fixed
- A session-capped full charge (see 0.1.13) could silently deliver far
  more energy than its own cap allowed, driven by the 0.1.13 flat-price
  window extension - reported live: a session capped to 6.318 kWh (16
  units) landed on a 37-unit window (start_unit 34, end_unit 71) because
  a long stretch of near-identical, near-zero prices was available to
  extend into. The extension was designed on the assumption that
  charging longer than strictly needed is harmless, since `is_full`
  would cut a session off the moment the battery actually reached
  100% regardless of how long its window ran - true for an *uncapped*
  session, but not for a capped one: capping intentionally sets the
  target below what would ever reach 100% in this session (that's the
  whole point - spreading a too-big charge across multiple days), so
  `is_full` never fires, and the extended `end_unit` becomes the only
  thing bounding how long the setpoint stays on. A 37-unit window at
  this session's charge rate would have delivered roughly 15 kWh -
  nearly the entire original 13.21 kWh deficit in one sitting, defeating
  the multi-day spread outright. Fixed: a session that actually got
  capped now keeps its tight, `units_needed`-sized window instead of
  being extended; the extension still applies normally to uncapped
  sessions, where it stays harmless. Added a regression test
  reproducing the exact reported scenario (a capped session with a long
  flat-priced valley available to extend into).

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
