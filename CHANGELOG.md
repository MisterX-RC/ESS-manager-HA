# Changelog

Every push to this repo bumps `custom_components/ess_manager/manifest.json`'s
`version` by 0.0.1 (the patch digit) and gets an entry here - this is what
lets HACS reliably tell installed instances an update exists, since
`sync-and-push.command` now publishes a matching GitHub Release (tag
`vX.Y.Z`) automatically as the last step of every push (see the README) -
a plain git tag on its own isn't enough for HACS to notice.

## [0.3.0] - 2026-09-24

### Removed
- **The two old household usage sources**, deprecated since 0.2.10: an
  existing sensor with h0..h120 attributes, and calculating it from
  hand-picked energy statistics. The usage forecast now always comes from
  your Energy dashboard or from a home energy consumption sensor.
- The leftover "script" direct-control setting from 0.2.14.

### Changed
- **Automatic migration on update.** An installation that still used a
  removed source is switched to the Energy dashboard source automatically
  when the Energy dashboard has a grid source, and Settings > Repairs shows
  a notice asking you to check the forecast (it disappears once you save
  Configure, or when you ignore it). If that's not possible, planning
  pauses and Repairs shows an error until you pick a source in Configure;
  it never plans with zero household usage. Settings that only the removed
  sources used are cleaned up.
- **After updating you can't go back to a 0.2.x version** without removing
  and re-adding the integration: the stored configuration moved to a new
  format (version 2).
- **The repository is smaller:** the original template-sensor YAML
  (`legacy-yaml-config/`) and the maintainer's sync script are no longer
  part of it. Both are still in the git history.

## [0.2.20] - 2026-09-24

### Added
- **MIT license.** ESS Manager is now published under the MIT license
  (see `LICENSE`): anyone may use, change and share it, as long as the
  copyright notice stays with it. No change to the integration itself.

## [0.2.19] - 2026-09-24

### Added
- **Integration icon.** ESS Manager now ships its own icon (a battery
  between the sun and the grid, with charge/discharge arrows), shown in
  Home Assistant 2026.3 and newer and in HACS.
- **Validation on GitHub**: a workflow that runs the HACS action and
  Home Assistant's hassfest on every push, as required for the HACS
  default list. It only checks; nothing is published or changed.

### Fixed
- `manifest.json` keys are now in the order Home Assistant's validator
  requires (domain, name, then alphabetical).

## [0.2.18] - 2026-09-24

### Fixed
- **The adjusted battery forecast (the chart line) showed a running sale
  going deeper than it really does.** Mid-sale it subtracted the full
  rate for every remaining quarter of the window, even when the battery
  was ahead of schedule and would reach its stop target sooner. It also
  counted the house use during the window twice. A live sale at 20:07
  showed the battery dipping to 3.76 kWh at 07:00, below the 4.5 kWh
  safety floor; the realistic low point was about 6.4 kWh. Now:
  - A running charge/discharge draws only what's left, the distance
    from the battery now to its target level, and nothing once the target
    is reached.
  - Planned and running windows take into account that the stop target
    is a battery level: the house's own use during a sale counts toward
    it (so the line drops a little less), and during a charge it comes on
    top.
  - Only the chart line changes; what the system does is unchanged.

## [0.2.17] - 2026-09-24

### Added
- **Safety buffer** (new number entity, % of battery capacity, default
  5%). A sale never brings the forecast below your min SOC plus this
  buffer: with min SOC 10% and a 5% buffer, sales stop at 15% instead of
  10%. It leaves room for usage or solar to differ from the forecast, so a
  sale doesn't end in buying energy back. Set it to 0 to sell right down
  to min SOC as before.

### Changed
- **Minimum charge target now means the smallest amount any charge
  buys.** Until now it was also a battery level: the low charge plan
  charged up to it, and since 0.2.9 sales stopped at it. Now:
  - Low charge plan: the dip is lifted back to the low threshold, and a
    smaller need is rounded up to the Minimum charge target (never so far
    that a later peak would go over your max SOC and be sold again).
  - Spike plan: a pre-peak top-up smaller than it is skipped (unchanged).
  - Selling: no longer uses it; that's the Safety buffer now.
  - Check both values after updating: the Safety buffer starts at 5%,
    and the Minimum charge target keeps its current value with the new
    meaning.

## [0.2.16] - 2026-09-24

### Fixed
- **A sale could move to a cheaper window just because it sold a little
  more.** When the best-priced window is capped (the battery would
  otherwise drop below the low threshold or Minimum charge target before
  the next solar), the plan also tries selling after that low point. It
  used to pick whichever option sold more kWh. It now picks whichever
  earns more (kWh x the window's average price). Live example: this
  evening 18:45 (18.23 kWh at 0.267 = 4.87) now wins over tomorrow 08:00
  (18.65 kWh at 0.210 = 3.92). Whatever the capped sale leaves unsold is
  still surplus, so the next plan after it sells that too, in the best
  window left before the breach.

## [0.2.15] - 2026-09-24

### Removed
- **The "Run a script" option for direct control.** Direct control now
  always sets a number / input_number entity. An installation that had
  chosen a script in 0.2.14 falls back to "Status sensor only" (nothing is
  sent), with a warning in the log; pick a number / input_number entity in
  Configure to turn direct control back on.

## [0.2.14] - 2026-09-24

### Added
- **Direct control (optional).** ESS Manager can now send the
  charge/discharge setpoint to your inverter itself, instead of an external
  automation reacting to the Status sensor. Choose it on the new **Battery
  control** page in Configure:
  - **Set a number / input_number entity** (e.g. your inverter's grid
    setpoint), or **Run a script** that gets `setpoint`, `power_kw`,
    `action` and `reason` as variables.
  - Set the unit (W or kW), the sign convention and the idle value (sent
    as-is, e.g. 0 or -30).
  - Each action uses the speed its plan was sized with (charge,
    discharge, negative price charge, spike discharge), limited to your max
    battery speeds and to the target entity's own min/max.
  - "Status sensor only" stays the default, so nothing changes until you
    switch it on.
- **Safety** around direct control:
  - A new **Automatic control** switch lets you take over by hand at any
    time: it sends idle once, then leaves the target alone.
  - It also sends idle when an update fails (for example the SOC sensor is
    unavailable), when the integration is unloaded or removed, and when
    Home Assistant stops.
  - Changing the target in Configure idles the old one first.
  - A failed send is logged once and shown in the Status sensor, and never
    stops the planning.
- **Planned setpoint** sensor (kW, positive = charge), plus
  `control_action` / `control` attributes on the Status sensor. They show
  what direct control sends, or would send while it's off, so you can
  compare it with your own automation before switching over. When you do
  switch, disable your own ESS automation.
- The setup now ends with the Battery control page(s).

## [0.2.13] - 2026-09-24

### Changed
- **A new installation no longer starts with a full charge.** Until now a
  fresh install with full-charge balancing on (and internal tracking)
  treated the battery as overdue for a balance, so the first thing it did
  was charge to 100%. A new installation now assumes the battery has just
  been balanced: the "days since last full charge" clock starts at 0 on
  setup, and the first full-charge cycle comes after the normal "Full
  charge interval". Existing installations are not affected; their clock
  keeps running as before. If you track this with an external sensor
  (e.g. your BMS), that sensor still decides.

## [0.2.12] - 2026-09-24

### Changed
- **HACS now shows the real release notes when updating.** The GitHub
  release that `sync-and-push.command` publishes used to say only "See
  CHANGELOG.md for details on this release." It now contains that
  version's own section of this changelog, which is what HACS shows in its
  update dialog. Re-running the script for a version that already has a
  release refreshes that release's notes the same way. No change to the
  integration itself.
- **One-time step:** the sync script never overwrites itself, so copy the
  new `sync-and-push.command` from this zip into your ess-manager-ha folder
  by hand (replacing the old one) before running it.

## [0.2.11] - 2026-09-24

### Changed
- **Setup and Configure are split into separate pages** instead of one long
  form:
  1. **Sensors** - name (setup only), battery SOC, price, solar forecast(s),
     grid/inverter setpoint, the usage source, and the full-charge
     balancing switch.
  2. **Usage source page** for the chosen source (Energy dashboard: what it
     found + lookback weeks; consumption sensor: the sensor(s) + lookback
     weeks).
  3. **Full-charge balancing** - only shown when that switch is on: cell
     voltage differential or lowest/highest cell voltage, battery pack
     voltage (required), days-since-full-charge tracking and its sensor,
     and (setup only - it's a number entity afterwards) the target voltage.
  4. **Battery and system** - capacity, normal charge/discharge speed, max
     battery charge/discharge speed, min/max SOC. In Configure only the max
     battery speeds (the rest are number entities).
  5. **Price plans** - a short explanation of the negative price and spike
     arbitrage plans, with their switches.
  No settings were added, removed or renamed, so existing installations
  are unaffected. Saving Configure now keeps settings on pages that were
  skipped (e.g. the full-charge sensors while that plan is off) instead of
  dropping them.

## [0.2.10] - 2026-09-23

### Deprecated
- **Two household-usage sources are deprecated and will be removed in
  0.3.0: "An existing sensor with h0..h120 attributes" and "Calculate it
  from my energy statistics" (hand-picked sensors).** The setup wizard now
  only offers the two supported sources - **the Energy dashboard**
  (recommended, and the new default) and **a home energy consumption
  sensor**. Installations already on a deprecated source keep working
  exactly as before for the rest of 0.2.x; Configure still shows their
  current source (marked "deprecated") so other settings can be saved
  without switching. Home Assistant shows a warning under
  Settings -> System -> Repairs on those installations, explaining how to
  switch; it disappears as soon as a supported source is saved (it's
  re-checked at startup and on every Configure save), and is removed if the
  installation is deleted. A warning is also written to the log.

### Fixed
- **Saving Configure now recomputes the usage forecast straight away.**
  Options changes only refresh the integration (they don't reload it), so
  switching usage source - or changing its entities or lookback weeks -
  kept the old cached forecast until the next hour change.

## [0.2.9] - 2026-09-23

### Changed
- **A planned sale no longer drains the battery right down to the bare low
  threshold.** The high discharge plan's safety cap now keeps the forecast
  after the sale at or above the higher of the low threshold and the
  **Minimum charge target** - the same level the low charge plan tops the
  battery back up to. Before, a sale could be sized to land exactly on the
  low threshold, so any forecast error (a bit more evening usage, a bit
  less morning solar) pushed the battery under it and made the low charge
  plan buy energy back - possibly the energy it had just sold. No new
  setting: it reuses the existing Minimum charge target. If that's set at
  or below the low threshold, nothing changes. New plan field
  `sale_floor_kwh` shows the floor in use. README tunables row corrected
  (the low charge plan uses Minimum charge target as a target level, not a
  minimum session size). 2 new tests (125 -> 127).

## [0.2.8] - 2026-09-23

### Changed
- **The statistics-based usage forecast is now recomputed exactly once per
  hour**, on the first cycle after the hour changes. v0.2.7 added the
  hour-change refresh but kept the old 55-minute age limit as well, which
  caused a second, pointless recalculation around xx:55 (same hour, same
  inputs, same result). Nothing the forecast depends on changes within an
  hour, so the age limit (`USAGE_FORECAST_RECALC_MINUTES`) is removed.
  No change in results - just one database query per hour instead of two.

## [0.2.7] - 2026-09-23

### Fixed
- **The statistics-based usage forecast ran one hour behind for most of
  every hour.** It's cached and recomputed at most every 55 minutes, but the
  array is anchored to the hour it was computed in (h0 = that hour). Reused
  after the clock moved into the next hour, every value landed one hour
  early - a live dump at 19:04 showed the 18:00 value at h0 (confirmed by
  comparing it with an earlier dump: identical values, shifted exactly one
  hour). This shifted usage an hour against the solar forecast in every
  battery forecast and plan built from it. Affects all three
  statistics-based sources (manual calculated, consumption sensor, Energy
  dashboard) and has been there since the calculated source was added. The
  cache is now also refreshed as soon as the hour changes; that's safe to
  do right at the top of the hour, because the forecast only looks at the
  same hour one or more weeks back. 3 new tests (122 -> 125).

## [0.2.6] - 2026-09-23

### Fixed
- **The high discharge plan's low-threshold cap counted low points that
  happen before the sale.** It limited how much could be sold by the lowest
  point anywhere in the planning horizon - but selling only lowers the
  battery from the moment of the sale onward, so a low point earlier than
  the sale can't be affected by it. Caught from a live dump: the cap was
  0.84 kWh because of a 5.34 kWh low point at 05:00, while the sale itself
  was scheduled for 19:45 that evening; the lowest point after the sale was
  9.5 kWh, leaving room for the full 1.79 kWh surplus. The cap now uses the
  lowest point from the sale's own hour to the end of the horizon (still
  including hours after the peak - with a max SOC below 100% the peak isn't
  clipped, so the sold energy really is missing from later hours too).
  Because the amount and the time depend on each other, it starts from the
  full surplus and shrinks it until the window it lands in is safe. If the
  best-priced window is capped by a low point right after it, it also tries
  selling only after the lowest point before the breach, and uses that if
  it can sell more. New plan field `low_point_after_sale_kwh`. A low point
  after the sale still caps it exactly as before. 3 new tests (119 -> 122).

## [0.2.5] - 2026-09-23

### Fixed
- **The low charge plan sized its charge against the first hour the
  forecast dipped under the low threshold, not the lowest point of that
  dip.** Caught from a live dump: the forecast first crossed the 3.0 kWh
  threshold at 2.89 kWh, so the plan scheduled a 0.11 kWh "charge" - but
  the same dip kept falling for five more hours to -0.38 kWh before solar
  recovered it, so the real shortfall was 3.38 kWh and the battery would
  have run empty overnight. `compute_low_charge_plan` now finds where the
  dip ends (the forecast climbing back to the threshold, or the end of the
  horizon) and sizes `deficit_kwh`/`target_kwh` against the lowest point
  in between; the deadline (`breach_unit`) is still the first crossing, so
  the charge still has to be in before the battery first runs short. A
  separate, later dip is not lumped in - it gets its own plan once this
  one is behind us. The plan gains a `dip_min_kwh` field showing the low
  point it sized against. This first-crossing sizing came straight from
  the original template sensor. 3 new tests (116 -> 119).

## [0.2.4] - 2026-09-23

### Added
- **Fourth household-usage source: "Calculate it using the entities from my
  Energy dashboard".** The same energy-balance calculation as the existing
  "Calculate it from my energy statistics" option (solar + grid import +
  battery discharge - grid export - battery charge, averaged over the same
  hour/weekday), but the grid, solar and battery statistics are read live
  from Home Assistant's own Energy dashboard configuration instead of being
  picked by hand - re-read about once an hour, so edits in the Energy
  dashboard carry over automatically. Handles both shapes HA has used for
  grid sources (the older `flow_from`/`flow_to` arrays and the current one
  entry per grid connection), any number of grid connections/solar arrays/
  batteries, and external statistics (e.g. `tibber:...`); gas, water and
  device-level entries are ignored. The setup/Configure step shows exactly
  which statistics were detected and refuses to continue if the Energy
  dashboard has no grid import configured; the Status sensor gains
  `usage_source` and `energy_dashboard_sources` attributes so what's
  actually in use can be checked live. Reading the Energy dashboard uses an
  internal Home Assistant interface, so any failure to read it is logged
  and the last good forecast is kept rather than failing the update.
  Added alongside the existing three options (none removed yet) so it can
  be verified first. The manual "calculated" option's battery fields are
  unchanged; internally the battery terms now also accept lists (needed
  for multiple Energy-dashboard batteries). 6 new tests (110 -> 116):
  legacy and current Energy-dashboard shapes, unreadable/empty config,
  duplicate/blank handling, same result as the equivalent hand-picked
  config, and multiple batteries summed.

### Fixed
- **Energy statistics are now always read in kWh.** The recorder statistics
  fetch used by all three statistics-based usage sources didn't request a
  unit, so a sensor reporting in Wh (or MWh) was read in its own unit -
  1000x off from the kWh everything downstream assumes. Now asks the
  recorder to convert to kWh.

## [0.2.3] - 2026-09-22

### Fixed
- **The battery/SOC forecast (`battery_forecast_adjusted`) charted a
  discharge or charge plan's full per-unit rate for its whole committed
  window, instead of the plan's real, intended amount - producing a
  phantom overshoot/undershoot on the forecast and dashboard that never
  actually happens.** Caught from a live report: a genuine `high_discharge_plan`
  target of just 0.09 kWh (against an ~10kW discharge speed, whose
  `effective_discharge_per_unit` for one whole 15-minute unit is 2.72 kWh)
  showed up on the SOC forecast as a ~2.72 kWh drop reaching below
  `low_threshold_kwh` - looking like the discharge plan was creating an
  undershoot before the far-future price peak it was scheduled against.
  Investigating confirmed the plan's own sizing was already safe (the
  existing `max_safe_surplus` cap in `compute_high_discharge_plan` already
  limits how much surplus can be sold so the raw forecast's own low point
  can't be pushed under `low_threshold_kwh` - which is exactly why the real
  target came out to a tiny, safe 0.09 kWh here); the bug was entirely in
  `compose_forecast_adjusted` assuming the full configured rate gets
  delivered for the whole rounded-up unit, rather than the plan's own
  `target_kwh`. Since v0.2.2's live target-energy stop now halts the real
  hardware at `target_kwh` (not the whole unit), the forecast needed the
  same correction to match reality: `compose_forecast_adjusted` now derives
  each plan's per-unit rate from `target_kwh` spread evenly over its own
  committed window, so the total delta by the window's end always equals
  the plan's real, intended amount - not an inflated, whole-unit-rounded
  one. Applies to both the low charge plan and the high discharge plan;
  `compute_full_charge_plan` is unaffected (it stops on live SOC, not a
  per-unit floor, so it never had this overshoot to begin with). 2 new
  tests (108 -> 110): an undersized discharge plan and an undersized
  charge plan each chart only their real `target_kwh`, not their much
  larger effective per-unit rate.

## [0.2.2] - 2026-09-22

### Added
- **Live target-energy stop, alongside the existing timer, for the low
  charge plan and the high discharge plan.** Every plan window is sized in
  whole 15-minute price units at the full configured charge/discharge rate
  (`math.ceil(...)`), so a genuine need smaller than one unit's capacity
  finishes well before the unit's 15 minutes are up - caught from a live
  report of a 0.96 kWh discharge target against a ~10kW discharge speed
  (2.72 kWh/unit), which meant continuing to discharge at full rate for the
  rest of the window sold off far more stored energy than intended, an
  overshoot that can force buying back energy later at a worse price.
  Rather than only ever stopping when the window's own timer runs out,
  `compute_low_charge_plan` and `compute_high_discharge_plan` now also
  compute a `target_energy_kwh` the moment a window is found (the battery
  level, plus or minus the plan's own sizing, that corresponds to "target
  reached") and `compute_system_status` reports **Stop** the instant the
  live battery level (`battery_now_kwh`) crosses it - whichever of the two
  triggers, timer or target, comes first. Once crossed, `target_reached`
  latches permanently for the rest of that window (checked here, not
  recomputed live) so a brief post-stop dip or bounce in the setpoint
  readback can't flip the status back to "Actief"/"Start charge" (or the
  discharge equivalents) and reopen a session that already finished. 6 new
  tests (102 -> 108): both plans latch `target_reached` once the target is
  crossed mid-window, both keep the latch even when a later reading moves
  back the other way, and `compute_system_status` reports "Stop" for both
  once latched.
- **Scoped out for now:** the spike plan and the negative-price plan have
  the same whole-unit overshoot risk, but their *entire* plan (both the
  charge leg and the discharge leg) locks in the moment it's first found -
  which can be hours or days before either leg's own window actually
  begins - so a naive single anchor taken at lock-in time would use a
  stale battery reading for whichever leg runs later. The negative-price
  plan additionally reuses its `discharge_needed_kwh` field name for the
  already-whole-unit-quantized amount rather than the true continuous
  need, which would need a new field before a target could be anchored
  correctly. Left as a follow-up.

## [0.2.1] - 2026-09-22

### Added
- **Spike plan skips a sub-minimum pre-peak top-up instead of scheduling it.**
  Before its price-spike discharge, the spike plan tops the battery back up
  to full if the forecast expects a small natural dip beforehand (so
  there's more to sell at the peak price) - caught from a live report where
  a 1.16 kWh top-up showed up as a real "Start charge" trigger and a real
  entry on the charge sensors, purely to counteract a forecasted dip that
  small. `compute_spike_plan` now takes the same **Minimum charge target**
  value the low charge plan already uses, and if the forecasted gap is
  smaller than it, treats the battery as "close enough to full" and
  schedules nothing - no charge window, nothing on `charge_start_time`/
  `charge_stop_time`/`charge_energy_kwh`, no "Start charge" status. Applied
  differently than in the low charge plan, deliberately: there, the value
  raises the *target level* charged up to (the spike plan's target is
  already the top of the battery, so there's no floor to raise); here it's
  a floor on whether the resulting top-up is worth doing at all. The
  discharge side is unaffected - its sizing was already independent of the
  charge top-up. 2 new tests (100 -> 102): a sub-minimum gap is skipped
  entirely (zero-length charge window), a gap just above the minimum still
  schedules a real charge.

## [0.2.0] - 2026-09-22

### Changed
- **No functional change from 0.1.35** - this release exists to mark the
  switch to actually-published GitHub Releases. Every version up through
  0.1.35 was pushed to GitHub but never had a matching Release cut for it
  (that was previously a separate, manual "GitHub -> Releases -> Draft a
  new release" step - see the old wording in the README/this file's
  header - which never actually got done), so HACS had no release to
  compare against and could only fall back to tracking raw commits on the
  default branch, missing every one of those 36 pushes as a proper
  "update available."
- `sync-and-push.command` now cuts the release itself: after pushing, it
  reads the version straight out of `manifest.json`, checks GitHub for a
  release already tagged `vX.Y.Z`, and if there isn't one, publishes it
  via the GitHub API using the same personal access token macOS Keychain
  already has saved for the push - no separate manual step anymore.
- Renumbered to 0.2.0 (rather than continuing as 0.1.36) simply to mark
  this as the first version with a real release behind it. Versioning
  continues in 0.0.1 steps from here (0.2.0 -> 0.2.1 -> 0.2.2 -> ...),
  exactly as before.

## [0.1.35] - 2026-09-22

### Fixed
- **`sensor.ess_manager_status` could stay stuck on "Standby" right at a low
  charge plan's own start time**, if the spike plan happened to still be
  "active" (waiting on a later discharge phase, or - as in the reported
  case - reduced to a zero-length/zero-kWh no-op charge window) with
  neither its own charge nor discharge window currently applicable.
  `compute_system_status`'s spike branch unconditionally returned "Standby"
  in that gap instead of falling through to check the low charge plan below
  it - the same root cause already fixed in `display.charge_display`
  (v0.1.30) and the dashboard charts (v0.1.31), just never carried over to
  this function, and never covered by this suite's existing
  `compute_system_status` tests (none of which included an active spike
  plan). Fixed by letting the spike branch fall through instead of
  returning early when neither of its own windows currently applies. 3 new
  tests (97 → 100): the regression itself, plus confirming the spike
  plan's own charge and discharge windows still correctly take priority
  when genuinely current.

## [0.1.34] - 2026-09-22

### Added
- **A second, independent trigger for entering the full-charge plan's
  holding phase**: SOC reaching 99.5% (unchanged) or the battery pack's
  own measured voltage getting within 1.0V of the configured full-charge
  target voltage - either one on its own is now enough. SOC (coulomb
  counted on most BMS/inverter setups) can drift over time, so pack
  voltage gives the plan a second, independent way to notice a genuinely
  full battery even when SOC under- or over-reports, and start commanding
  a charge setpoint before household loads can erode a battery that's
  really already full. This 1.0V margin only decides when *holding
  starts* - it's deliberately much looser than the existing 0.1V margin
  used to confirm genuine balance, so it never lets balance_confirmed
  (which still requires real SOC>=99.5%, alongside the cell voltage
  differential and the stricter 0.1V pack-voltage check) fire on voltage
  alone. See the README's "Full-charge balancing" section for the updated
  spec.

## [0.1.33] - 2026-09-21

### Added
- **Choice of "days since full charge" tracking source** for the full-charge
  balancing plan, alongside the existing `Enable periodic full-charge
  balancing plan` toggle (in both the initial setup flow and the
  integration's Options): track it internally (the original, still
  default, behavior), or read it directly from an external sensor that
  already tracks it - e.g. a BMS's own "days since full charge" entity,
  which resets to 0 the moment it observes a genuine full charge. Selecting
  the external-sensor option requires picking that sensor, validated the
  same way `CONF_BATTERY_VOLTAGE_ENTITY` is required alongside the plan
  itself. A missing/unavailable external sensor falls back to treating a
  full-charge cycle as due, matching the existing "never observed full
  yet" bootstrapping behavior. See the README's "Full-charge balancing"
  section for details.

## [0.1.32] - 2026-09-21

### Fixed
- **The charge/discharge start/stop time sensors could show an off-grid
  minute** (e.g. "19:08" instead of "19:00"/"19:15"), drifting by a
  couple of minutes between updates. `display._format_time` was adding
  the whole-15-minute-unit offset to the coordinator's exact wall-clock
  timestamp at recalculation time (e.g. 19:23:07) rather than to the
  start of the current price unit (19:15) - so every displayed time
  inherited whatever odd number of minutes "now" happened to be past the
  last quarter-hour. `now` is now floored to the current unit's start
  before the offset is applied. 1 new test (93 → 94).

## [0.1.31] - 2026-09-21

### Fixed
- **The dashboard charts could hide a genuinely upcoming charge plan
  behind a spike plan's already-past charge window** - the same root
  cause as 0.1.30's `charge_display` fix, but in the two chart YAMLs'
  own JavaScript. `dashboard/price_apexcharts_card.yaml`'s "Buy" series
  and its combined "Today's/Tomorrow's prices" series, and
  `dashboard/battery_forecast_chart.yaml`'s "Buy" series, all picked the
  spike plan's `charge_start_unit`/`charge_end_unit` for as long as
  `spike_plan.active` was true - which, like `charge_display`, is true
  for the plan's entire charge-through-discharge lifecycle - instead of
  checking whether the charge window itself had already passed. Once a
  spike's charge window ended but its discharge window hadn't started
  yet, the chart kept highlighting the stale charge window and never
  fell through to show a genuinely upcoming low charge plan. Fixed by
  additionally requiring `curUnit < spike.charge_end_unit` before using
  the spike plan for the buy window (the sell/discharge side was already
  correct, since `spike_plan.active` only stays true while the discharge
  window is still ahead). The price chart's Sell highlighting is
  unaffected.

## [0.1.30] - 2026-09-21

### Fixed
- **The charge sensors (`charge_energy_kwh`/`charge_start_time`/
  `charge_stop_time`) could show a spike plan's charge window well after
  it had already passed.** `display.charge_display`'s spike branch was
  gating on the spike plan's `discharge_end_unit` (the same check
  `discharge_display` correctly uses for the *discharge* side) instead of
  its own `charge_end_unit` - so for the entire gap between a spike
  plan's charge window ending and its later discharge window starting,
  the charge sensors kept echoing the now-stale charge window instead of
  falling through to the low charge plan (or showing nothing). Now checks
  `charge_end_unit`, matching the pattern already used for the negative
  price plan's own charge branch just above it.

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
