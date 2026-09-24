# ESS Manager

A Home Assistant custom integration for battery/solar/price-aware charge and
discharge planning: it watches your battery's state of charge, a solar
production forecast, a household usage forecast, and dynamic electricity
prices, and decides when to charge, when to discharge, and how much. It can send the
charge/discharge setpoint to your inverter itself (optional, as of v0.2.14 -
see "Direct control"), or leave that to a separate, small automation that
acts on its Status sensor.

This started as a hand-written Home Assistant template sensor (see
`legacy-yaml-config/` in this repo for that exact, still-in-production
configuration) and was rebuilt here as a proper, configurable custom
integration so it can be shared and installed on other systems via HACS,
without every install needing to hand-edit Jinja templates or hardcode
someone else's entity IDs.

## What it does

Five planning engines, all documented in detail in the code
(`custom_components/ess_manager/plans.py`):

1. **Low charge plan** - charges before the battery would otherwise drop
   below your minimum SOC, during the cheapest available price window.
2. **High discharge plan** - discharges before the battery would otherwise
   overshoot your maximum SOC, during the priciest available price window.
3. **Full charge plan** *(optional)* - periodically charges all the way to
   100% and holds there briefly to let the BMS balance cells, on a
   configurable interval.
4. **Spike arbitrage plan** - on a day with a large enough price spread,
   deliberately charges cheap and discharges into the peak instead of just
   capping at your normal SOC band. Before a discharge, it tops the battery
   back up to full if the forecast expects it to have drifted down a bit by
   then (so there's more to sell at the peak) - but skips that top-up
   entirely if the gap is smaller than **Minimum charge target**, rather
   than scheduling a trivial charge just to close a tiny forecasted dip.
5. **Negative price plan** - when the price goes low enough that charging
   pays you outright, buys as much as your hardware can take in that
   window, clearing room beforehand if needed.

All five compose on top of a 121-hour (5-day) forecast pipeline: solar
forecast minus usage forecast, cumulatively summed into a projected battery
level, compensated for the fact that the current hour is only partially
elapsed (see the code comments in `forecasting.py` for why that matters).

By default the integration only decides: its `Status` sensor says what
should happen and your own automation acts on it - see "Wiring it to your
inverter" below. Optionally it sends the setpoint itself - see "Direct
control".

## Requirements

Your Home Assistant instance needs entities shaped like these (the
integration reads them as configured attributes, not by name, so any
integration producing the same shape works):

- **Battery state of charge**: a sensor whose numeric state is a percentage
  (0-100).
- **Electricity price**: a sensor exposing `today` and `tomorrow` attributes
  as flat lists of **quarter-hour (15-minute)** prices - this is the shape
  the Nordpool HACS integration produces for markets settled at 15-minute
  resolution. A sensor with hourly-only prices will not line up correctly
  with the planning engines' 15-minute unit indexing.
- **Household usage forecast**: nothing extra if your Home Assistant
  Energy dashboard is set up (at least a grid source) - the integration
  calculates the forecast itself from the statistics the Energy dashboard
  already uses. Alternatively, a sensor reporting your home's total energy
  consumption (cumulative kWh). See "Household usage forecast" below.
- **Solar forecast**: one or more sensors exposing a `detailedHourly`
  attribute shaped like Solcast's: a list of
  `{"period_start": <ISO timestamp>, "pv_estimate": <kWh>}` objects. Add as
  many forecast-day sensors as you need to cover 121 hours from whatever
  time of day updates happen to run (Solcast typically needs
  today/tomorrow/day_3 at minimum, more if you want headroom late in the
  day - see the original's notes in `legacy-yaml-config/ess_manager_sensor.yaml`).
- **Grid/inverter setpoint** *(optional but recommended)*: a sensor
  reporting your current commanded charge/discharge power, used to make the
  "Status" sensor's engaged-vs-starting distinction accurate.
- **Cell voltage differential** *(optional)*: only needed if you enable the
  full-charge balancing plan.
- **Battery pack voltage** *(required if you enable the full-charge balancing
  plan)*: a sensor reporting the battery pack's own overall voltage. This is
  a third, independent confirmation leg on top of SOC and the cell voltage
  differential above - see "Full-charge balancing" below.
- **Days since full charge sensor** *(optional)*: only needed if you enable
  the full-charge balancing plan and choose the external-sensor tracking
  option instead of the default internal tracking - see "Full-charge
  balancing" below.

## Household usage forecast

Every planning engine needs a household usage forecast, but there's no one
right way to produce it. The setup wizard offers two sources: **your Energy
dashboard** (recommended) and **a home energy consumption sensor** - both
described further down. Two older sources, **an existing h0..h120 sensor**
and **calculated from hand-picked sensors**, are **deprecated**: they can't
be chosen for a new installation any more and **will be removed in 0.3.0**.
Installations already using one keep working until then, and Home
Assistant shows a notice under Settings -> System -> Repairs explaining how
to switch (Configure -> pick one of the two supported sources); the notice
disappears as soon as you save.

The deprecated ones first, for reference:

**An existing sensor** *(deprecated - removed in 0.3.0)* - point the integration at any sensor exposing
`h0`..`h120` attributes, however you produce it. This is the original
system's approach: a hand-written SQL sensor averaging the same calendar
hour/weekday over several weeks of recorder history (see
`legacy-yaml-config/` for that exact query, if you're curious or want to
build your own variant).

**Calculated from hand-picked sensors** *(deprecated - removed in 0.3.0; use the Energy dashboard source below, which does the same calculation)* - the integration
queries Home Assistant's own long-term recorder statistics itself and
computes the same kind of forecast, using the energy-balance identity:

```
consumption = solar produced + grid imported + battery discharged
              - grid exported - battery charged
```

averaged across the same hour-of-day/day-of-week for however many weeks
back you choose (default 6). You provide:

- One or more **grid import** energy sensors (cumulative kWh) - use two if
  your meter has separate day/night (tariff 1/2) sensors, or just one if it
  doesn't; every sensor you list is summed together.
- **Grid export** energy sensor(s), same idea, optional if you never export.
- One or more **solar production** energy sensors (cumulative kWh) - one
  per inverter/array if you have more than one.
- Optionally, **battery charged/discharged energy** sensors, if your
  battery monitor tracks those cumulatively (Victron shunts typically do).
  Leave either blank if you don't have one - that term is just treated as 0.

This queries Home Assistant's statistics API rather than running raw SQL
against the recorder database directly, so it works the same regardless of
whether your recorder is SQLite, MariaDB/MySQL, or Postgres (the original
hand-written query was MySQL-specific). It also only recomputes about once
an hour internally (long-term statistics only ever land once an hour
anyway), and - unlike the original query - a week with a genuine gap in the
data (an entity that didn't exist yet, a recorder outage) is excluded from
that hour's average rather than silently counted as a zero.

**Calculated from your Energy dashboard** *(recommended)* -
exactly the same calculation as above, but instead of picking the grid,
solar and battery sensors by hand, the integration reads them straight from
Home Assistant's own Energy dashboard configuration (Settings -> Dashboards
-> Energy). They're re-read about once an hour, so any change you make in
the Energy dashboard is picked up automatically - there's nothing to keep in
sync. The setup step shows exactly which statistics it detected before you
confirm, and the Status sensor's `energy_dashboard_sources` attribute shows
what's currently in use. Multiple grid connections, solar arrays and
batteries are all supported (every one is summed into its term), as are
external statistics that have no sensor behind them (e.g. `tibber:...`). The
Energy dashboard needs at least a grid source configured; gas, water and
individual-device entries are ignored. This relies on an internal Home
Assistant interface - if a future HA version changes it and the
configuration can't be read, the integration logs a warning and keeps using
the last good forecast rather than failing.

**A home energy consumption sensor** - if you already have a sensor that
reports your home's total energy consumed (cumulative kWh), point the
integration at it directly. No energy balance is derived at all, which also
avoids a failure mode the calculated options can hit when one of the grid/
solar/battery sensors reports much more coarsely than the others (e.g. a
grid meter that only ticks in 0.1 kWh steps a few times an hour) - Home
Assistant's hourly statistics then lump that sensor's flow into whichever
hour it happened to tick over in, giving odd (even negative) hourly swings.

All three statistics-based options read the recorder's statistics converted
to kWh, so sensors reporting in Wh or MWh work too.

## Installation

### Via HACS (custom repository)

1. Push this repository to your own GitHub account (or fork it).
2. In Home Assistant: HACS -> Integrations -> ⋮ -> Custom repositories ->
   add your repo URL, category **Integration**.
3. Install "ESS Manager" from HACS, restart Home Assistant.
4. Settings -> Devices & Services -> Add Integration -> "ESS Manager".

### Manual

Copy `custom_components/ess_manager/` into your Home Assistant
`config/custom_components/` folder, restart, then add the integration from
Settings -> Devices & Services as above.

## Configuration

The setup wizard walks through these pages:

1. **Sensors** - name, battery SOC sensor, price sensor, solar forecast
   sensor(s), grid/inverter setpoint sensor (optional), the household usage
   source, and a switch for full-charge balancing.
2. **Usage source** - for the Energy dashboard: shows which statistics it
   found, plus the lookback weeks; for a consumption sensor: pick the
   sensor(s), plus the lookback weeks.
3. **Full-charge balancing** - only when that switch is on: cell voltage
   differential (or lowest/highest cell voltage), battery pack voltage,
   days-since-full-charge tracking, and the full charge target voltage.
4. **Battery and system** - capacity, normal charge/discharge speed, max
   battery charge/discharge speed, min/max SOC.
5. **Price plans** - a short explanation of the negative price and spike
   arbitrage plans, with a switch for each.
6. **Battery control** - whether ESS Manager sends the setpoint itself
   (see "Direct control"). "Status sensor only" is the default.
7. **Battery control - target** - only when direct control is chosen: the
   number/input_number entity, its unit (W/kW), sign convention and idle
   value.

Capacity, normal charge/discharge speed, min/max SOC and the full charge
target voltage seed a set of `number` entities (see below) that you
actually tune afterward. Everything else can be changed later from the integration's
**Configure** options, which follows the same pages; the number entities are
adjusted directly, the same way you'd adjust an `input_number` helper - no
need to create separate helpers.

Max battery charge speed and max battery discharge speed (the battery's own
physical power limit, in kW - see the table below) are the exception: they
aren't a `number` entity at all, since they're a fixed hardware property
rather than something to tune from a dashboard. You set them during setup,
and can still change them afterward from the integration's **Configure**
options screen if you got it wrong or upgrade your hardware - just not as a
live number entity.

### Tunable `number` entities

Created automatically once you finish setup - find them under the ESS
Manager device in Settings -> Devices & Services -> Entities:

| Entity | What it controls |
|---|---|
| Minimum SOC | Battery %, below which the low charge plan triggers |
| Maximum SOC | Battery %, above which the high discharge plan triggers (can be set above 100% to allow deliberate solar overshoot before discharging - the original hand-written version hardcoded this to 110% of a 30 kWh battery) |
| Battery capacity | kWh, used to convert the SOC % settings above into kWh thresholds |
| Charge speed / Discharge speed | Normal charge/discharge rate (kW) used by the planning engines to size grid-driven charge/discharge windows |
| Negative price charge speed | Rate used specifically during a negative-price event |
| Spike discharge speed | Rate used specifically during a spike-arbitrage discharge |
| Negative price threshold | Price (EUR/kWh) below which charging is considered "getting paid" |
| Spike margin | Minimum day price spread (EUR/kWh) to treat a day as spike-worthy |
| Minimum charge target | Low charge plan: when a charge is needed, charge the battery up to at least this level (kWh), not just back to the low threshold. High discharge plan: never sell the battery below this level (or the low threshold, whichever is higher) - as of v0.2.9. Spike plan: skip its pre-peak top-up entirely if the forecasted gap is smaller than this (as of v0.2.1) - see "What it does" above |
| Planning horizon | How many hours ahead the low/high plans are allowed to react to (price data usually doesn't exist much beyond ~48h anyway) |
| Full charge interval | Days between full-charge/balance cycles |
| Full charge max hold | Safety timeout (minutes) for the 100%-hold/balance phase |
| Full charge target voltage | Battery pack voltage (V) that counts as "genuinely full" - checked minus 0.1V (see "Full-charge balancing" below) |

Max battery charge speed and max battery discharge speed are set during
setup and re-editable later from **Configure** (see above) rather than
appearing in this table - they're a fixed hardware property (the battery's
own physical power limit, in kW), not a live dashboard setpoint. They cap
the passive, solar/usage-driven battery energy forecast (anything solar or
usage implies faster than this is assumed to flow to/from the grid
instead), and, with direct control, every setpoint that is sent.

## Wiring it to your inverter

The integration produces a `Status` sensor whose state is one of `Standby`,
`Start charge`, `Actief` (engaged), `Start discharge`, `Stop`, `Grid usage`,
`Solar export`, `Start negative price charge`,
`Negative price charge`, `Start spike discharge`, `Spike discharge`,
`Full charge scheduled`, `Awaiting solar (full charge)` - see
`custom_components/ess_manager/plans.py`'s `compute_system_status` for the
exact meaning of each. `Awaiting solar (full charge)` means the full-charge
plan has concluded a forecasted future solar peak will reach the overshoot
ceiling on its own, so nothing is being bought - it's the visible version of
what would otherwise be an indistinguishable `Standby` while
`full_charge_plan.relying_on_peak_unit` is quietly set (see
`high_discharge_plan.suppressed_by_full_charge`, which is also active
during this same wait). Unless you switch on "Direct control" (below), it
does **not** write to any inverter or battery control entity itself, since
every make/model exposes a different control surface (an `input_number`, a
native `number` entity from that inverter's own integration, an MQTT
topic, ...).

`dashboard/automation_example.yaml` is a starting point for the small glue
automation that turns `Status` into an actual command - adapt the
`target: entity_id:` lines to whatever your inverter setup actually uses.

For the low charge plan and the high discharge plan, `Stop` can now arrive
*before* the window's own end time, not only at it: every window is sized
in whole 15-minute units at the full configured charge/discharge rate, so a
genuinely smaller need can finish early, and continuing to command the full
rate for the rest of the window would overshoot past what was actually
needed (buying or selling more energy than intended). Both plans track a
calculated target battery level alongside their own timer and report `Stop`
as soon as either one is reached, whichever comes first - so an automation
reacting to `Stop` should always idle the setpoint, regardless of how much
of the window's nominal duration has actually elapsed.

## Direct control

*(Optional, as of v0.2.14.)* Instead of an external automation, ESS Manager
can send the setpoint itself. Choose **Set a number / input_number
entity** on the **Battery control** page (setup or Configure) and pick the
entity - e.g. your inverter's own grid setpoint `number` entity (Victron
Modbus/MQTT integrations expose one), or the `input_number` your existing
inverter automation already reads.

What gets sent: each action uses the speed its plan was sized with -
Charge speed for normal charges (low charge, spike top-up, full charge),
Discharge speed for normal discharges, Negative price charge speed and
Spike discharge speed for those plans - always limited to your max battery
charge/discharge speed, and to the target entity's own min/max. Every
Status that means "do nothing" (`Stop`, `Standby`, `Grid usage`,
`Solar export`, `Full charge scheduled`, `Awaiting solar (full charge)`)
sends your **idle value** exactly as entered (usually 0; some Victron
systems idle at -30 W). This is the same mapping as
`dashboard/automation_example.yaml`, with the speeds taken from the
integration instead of typed into the automation. The action is decided
together with the Status, so "Actief" is never ambiguous: it means keep
charging in a charge window and keep discharging in a discharge window.

The entity is only written when the value changes, or when something else
changed it (then at most once a minute).

Safety:

- **Automatic control** switch (a new entity on the device): turn it off to
  take over by hand - it sends idle once, then leaves the target alone
  until you turn it back on. Its state survives restarts; on by default.
- **Fail-safe**: when an update fails (SOC sensor unavailable, price sensor
  missing, an unexpected error), idle is sent instead of leaving the last
  command running.
- Idle is also sent when the integration is unloaded, reloaded, disabled
  or removed, and when Home Assistant stops.
- Changing the target in Configure (or switching control off) idles the
  old target first if it was charging or discharging.
- A failed send never stops the planning; it's logged once and shown in
  the Status sensor's `control` attribute (`last_error`), and retried next
  cycle.

**Planned setpoint** (a new sensor, kW, positive = charge) and the Status
sensor's `control_action` / `control` attributes show what would be sent -
also while direct control is off. That's the easy way to switch over:
leave control on "Status sensor only", compare Planned setpoint with what
your automation does for a few days, then choose direct control and
**disable your own ESS automation** so the two don't fight over the
setpoint.

If you leave the grid/inverter setpoint sensor on the first page empty, the
number entity you control is used as the setpoint readback for the Status
(`Start charge` vs `Actief`).

## Full-charge balancing

"Days since last full charge" - the clock that decides when a full-balance
cycle is due - is tracked one of two ways, chosen during setup (or later,
via the integration's options):

- **Internal tracking** *(default)*: the integration remembers the last time
  it confirmed the battery genuinely balanced (see below) and measures
  forward from there. A new installation assumes the battery has just been
  balanced, so the first full-charge cycle comes after the normal interval
  (the "Full charge interval" setting), not right after setup.
- **External sensor**: point it at a sensor you already have that tracks
  this itself (e.g. a BMS's own "days since full charge" entity), which
  resets to 0 the moment *it* observes a genuine full charge. Useful if your
  BMS already does this and you'd rather trust its own tracking than have
  the integration keep a second, independent clock.

The battery is considered "full" - the trigger that starts the holding
phase - the moment *either* of these is true, so a problem with one
doesn't block the other:

- SOC >= 99.5%, or
- the battery pack voltage is within 1.0V of the full-charge target voltage

SOC on most BMS/inverter setups is coulomb-counted and can drift over days
or weeks, so pack voltage is a second, independent way to notice a
genuinely full battery even if SOC has under- or over-reported. This 1.0V
margin only starts holding - it's deliberately looser than the 0.1V margin
below, so it never loosens what actually counts as "genuinely balanced."

Once the battery is full by either signal, "genuinely balanced" is
confirmed only once all three of these hold together:

- SOC >= 99.5%
- the cell voltage differential is below the balance threshold
- the battery pack voltage is at or above the full-charge target voltage
  minus 0.1V

If the battery reaches 100% (typically via solar) while no full-balance
cycle is currently due, nothing is forced - the integration just quietly
watches for all three conditions in the background, and resets the "days
since last full charge" clock the moment they're satisfied together. If a
full-balance cycle *is* due and the plan is waiting on a forecasted solar
peak to reach 100% on its own, the moment SOC reaches 99.5% the hold phase
starts and `Status` reports `Start charge` for the entire holding
duration - not just once the setpoint has ramped up - so household loads
can't erode the SOC while the cells finish balancing, even when solar alone
is what's holding the battery full with no grid setpoint needed. Once the
three conditions above are satisfied (or the "Full charge max hold" safety
timeout elapses first), the setpoint is released back to idle.

A hold that times out without ever confirming balance does **not**
immediately force another hold attempt - it falls back to the normal flow:
if there's a genuine future point where solar is forecast to push the
battery back into overshoot, the plan quietly waits for that; if not, the
charging logic schedules a fresh grid-charge session at the cheapest
available window to complete the balance.

## Dashboard

`dashboard/` has ApexCharts-based Lovelace cards adapted from the original
system's dashboard (battery/SOC forecast chart, price chart with buy/sell
highlighting, and an entities card) - each file's header comment explains
which placeholder entity_ids to replace with your own. Requires the
`apexcharts-card` and `multiple-entity-row` HACS frontend cards.

## What changed vs. the original hand-written version

This is a full rewrite (Jinja2 template sensor -> Python custom
integration), not a mechanical export, so a few things were deliberately
generalized for portability - documented here so nothing is a surprise if
you're the one who ran the original on a live system:

- **Every entity reference is configurable** - the original hardcoded
  Victron/Nordpool/Solcast entity IDs; this version only assumes the
  *shape* of data described under Requirements above.
- **The household usage forecast can be calculated internally**, with no
  external SQL sensor required - see "Household usage forecast" above. The
  original's approach (a hand-written, MySQL-specific SQL sensor) still
  works too if you'd rather keep using it, but isn't required anymore, and
  the built-in version also fixes a flagged correctness issue in the
  original (a week with missing data was silently averaged in as a 0
  instead of being excluded).
- **Min/max SOC are direct % tunables**, not derived from an external
  "inverter's own minimum SOC" sensor plus a hardcoded margin. If you want
  that margin back, just set Minimum SOC a few points above your inverter's
  own floor.
- **Capacity is a tunable**, not hardcoded to 30 kWh, and the dashboard
  cards read it live from the sensor rather than a hardcoded constant.
- **Idle setpoint tolerance** is generalized to 0W (the original's -30W was
  a quirk of one specific Victron install's idle reading).
- **Plan lock-in state survives Home Assistant restarts** (persisted via
  Home Assistant's storage helper) - the original template sensor's
  self-referencing `this.attributes` lookups would silently reset on
  restart and could re-plan an in-progress session differently. This is an
  intentional improvement, not a bug-for-bug port.
- **"Days since last full charge" can be tracked internally**, rather than
  requiring an external "time since last full charge" sensor that not
  everyone will have - though if you do have one (e.g. from your BMS), you
  can point the integration at it instead; see "Full-charge balancing"
  above.
- **One rich "Status" sensor + several small display sensors**, rather than
  one sensor with ~40 flattened attributes - the forecast arrays and plan
  dictionaries the dashboard needs still live as attributes on `Status`
  (for drop-in ApexCharts compatibility), but values useful directly in
  automations or history graphs (battery level, charge/discharge amount and
  timing, days to next full charge) are now their own entities.

See `legacy-yaml-config/` for the exact, byte-for-byte YAML this was ported
from, including the full, heavily-commented Jinja2 source and the original
project handoff notes on every design decision made along the way.

## Repository layout

```
custom_components/ess_manager/   the integration itself
dashboard/                       adapted Lovelace cards + example automation (not needed with direct control)
legacy-yaml-config/              the original template-sensor config, preserved as-is
sync-and-push.command            macOS helper - see "Keeping this repo in sync" below
```

## Versioning

`custom_components/ess_manager/manifest.json`'s `version` bumps by 0.0.1
(the patch digit) on every push - see `CHANGELOG.md` for what changed at
each version. This is what lets HACS tell installed instances an update
exists: it compares the tag on your most recent GitHub Release against
whatever version they currently have installed - note that this means an
actual GitHub *Release*, not just a git tag; HACS's own docs are explicit
that "just publishing tags is not enough, you need to publish releases,"
and without any release at all it falls back to tracking raw commits on
the default branch instead.

As of v0.2.0, cutting that release is no longer a manual step: the last
thing `sync-and-push.command` does after every push is read the version
out of `manifest.json`, check GitHub for a release already tagged
`vX.Y.Z`, and publish one via the GitHub API if there isn't one yet,
reusing the same personal access token macOS Keychain already has saved
for pushing. The release notes are that version's own section of
`CHANGELOG.md` (as of v0.2.12), so HACS's update dialog shows what
actually changed; if the release already exists, its notes are refreshed
from `CHANGELOG.md`. HACS re-checks custom repositories roughly every 6 hours and
at Home Assistant startup; to see an update right after syncing instead of
waiting, use HACS's own repository menu -> "Redownload" or "Update
information."

## Keeping this repo in sync (macOS)

If you're developing this alongside Claude rather than editing it directly
in GitHub: `sync-and-push.command` is a double-clickable script that lives
in this same folder. Each time it runs, it looks in your Downloads folder
for the newest `ess-manager-ha-repo*.zip`, copies its contents over this
folder (leaving this script and this folder's own `.git` history/remote
alone), commits whatever changed, pushes to GitHub, and publishes a
matching GitHub Release if the version in `manifest.json` doesn't have one
yet - so picking up an update, and making sure HACS actually notices it,
is one double-click instead of unzipping, typing git commands, and
drafting a release by hand.

The first time it runs, git will ask for your GitHub username and a
personal access token right there in the Terminal window it opens; macOS
Keychain remembers it after that, so every run after the first is silent.
If macOS refuses to run it the very first time ("cannot be opened because
it is from an unidentified developer"), right-click the file, choose
**Open**, and confirm once - after that, double-clicking works normally.
