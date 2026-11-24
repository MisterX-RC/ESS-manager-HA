# Control, problem notices and diagnostics

Wiring the Status to your inverter with your own automation, or letting ESS Manager send the setpoint itself; the problem notices and the diagnostics download.

[← Back to the README](../README.md)

## Wiring it to your inverter

The integration produces a `Status` sensor whose state is one of `Standby`,
`Start charge`, `Actief` (engaged), `Start discharge`, `Stop`,
`House from grid` (see plan 6),
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
during this same wait). `Solar export`: there's solar left over now, the
battery is forecast to reach 100% later today, and the price now is higher
than every price until then - exporting now pays more than storing (and in
a negative price plan, solar going to the grid before the negative window).
"Full" means the sun alone - the forecast without any
plan - takes the battery over the max SOC (the level that triggers a sale);
a battery that only gets full through a grid charge never exports: ESS
Manager buys and sells as little as it can, only the spike and negative
price plans trade.
With direct control and the battery's power sensor
(battery page) it's steered: the grid setpoint follows the battery's power
every 15 seconds (the same fast loop, 60% of the deviation per step) so
the battery keeps charging at **1000 W** and the solar above that goes
to the grid - export only, never above the idle value, so nothing is
bought for it (with less than 1000 W of surplus the battery just takes
what there is). Before a negative price window the battery is kept at
0 W instead, so the room stays free. Without the power sensor there's no
`Solar export` at all: the Status says `Standby`. The cards show it in orange: where it's
**expected** - the same rule on the forecast (solar left over, full later
today, the price above every price until then, plus the negative price
plan's export window), attribute `solar_export_expected` - as a block
with a dashed line on the price chart ("Export expected") and in that
colour on the battery chart's forecast line and tooltip; afterwards when
it really ran (the Battery action `solar_export`, only when steered).
Unless you switch on "Direct control" (below), it
does **not** write to any inverter or battery control entity itself, since
every make/model exposes a different control surface (an `input_number`, a
native `number` entity from that inverter's own integration, an MQTT
topic, ...).

`dashboard/automation_example.yaml` is a starting point for the small glue
automation that turns `Status` into an actual command - adapt the
`target: entity_id:` lines to whatever your inverter setup actually uses.

For the low charge plan and the high discharge plan, `Stop` can arrive
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

*(Optional.)* Instead of an external automation, ESS Manager
can send the setpoint itself. Choose **Set a number / input_number
entity** on the **Battery control** page (setup or Configure) and pick the
entity - e.g. your inverter's own grid setpoint `number` entity (Victron
Modbus/MQTT integrations expose one), or the `input_number` your existing
inverter automation already reads.

What gets sent: each action uses the speed its plan was sized with -
Charge speed for normal charges (low charge, spike top-up, full charge),
Discharge speed for normal discharges, Negative price charge speed and
Spike discharge speed for those plans - limited only to the target
entity's own min/max. The speeds are **grid setpoints**:
what the inverter takes from (or sends to) the grid. The
house is covered out of it and the battery gets the rest, but never more
than its max charge/discharge speed - the inverter limits that by itself,
and the plans count with it. So a Charge speed above the battery's max
charges the battery at its max and keeps the house on the grid too (the
battery fills faster than with a setpoint at the max, which the house
would share); a Charge speed below it is a gentler charge, which the
house shares. Every
Status that means "do nothing" (`Stop`, `Standby`, `Full charge scheduled`, `Awaiting solar (full charge)`)
sends your **idle value** exactly as entered (usually 0; some Victron
systems idle at -30 W). This is the same mapping as
`dashboard/automation_example.yaml`, with the speeds taken from the
integration instead of typed into the automation. The action is decided
together with the Status, so "Actief" is never ambiguous: it means keep
charging in a charge window and keep discharging in a discharge window.

The entity is only written when the value changes, or when something else
changed it (then at most once a minute).

**Night limit**: on the battery page in Configure,
"Limit the charge/discharge speed at night (22:00-07:00)" asks for a night
charge and a night discharge speed. Between 22:00 and 07:00 those limit
every other speed - normal, negative-price, spike and full charge: a speed
above the night speed is lowered to it, a lower one stays as it is. The
charge plans count with that speed for those quarters (so
a charge at night gets a longer window; 0 means no grid charging at night),
and a sale is worked out per quarter too - at the average of the night
speed in its night quarters and its own speed in the others, so a block
across 07:00 or 22:00 plans exactly what is sent. The setpoint switches by
itself at 07:00 and 22:00 (also in the middle of a running block).

*With the battery's power measured* (the battery power
sensor of the house-from-the-grid plan), the night speeds are limits **on
the battery itself**, as if they were the inverter's own - they're there
to keep the inverter cool and quiet at night, which is about what the
battery does, not about the grid. ESS Manager holds them with the same
loop as the house from the grid (every minute and in between): a night
charge puts exactly the night charge speed into the battery and the house
comes from the grid on top of it; a sale gives at most the night discharge
speed from the battery - the house first, the rest to the grid; and on
standby the battery covers the house up to the night discharge speed, a
peak above it (the oven, the kettle, a car without control) comes from the
grid, and back to idle when it's over (`night_grid_kw` in the decisions).
The plans count the same way: a night charge adds the night speed plus the
house it no longer feeds, a night sale exports the night speed minus the
usual night usage, and the battery forecast never gives the house more than
the night speed at night - and a car's "full by" only gets a battery
quarter at night when it fits under the night speed minus the house (else
grid quarters at their real price). What a night charge costs is what really comes
from the grid - the battery's night speed and the house, nothing sent back,
so a slow night charge isn't made to look dearer than a full-speed evening
block. The loop follows the measured power, so a sudden
peak is above the limit for the few seconds it takes to catch up. Turning
the night limit on in Configure therefore needs the battery power sensor on
the same page; an older setup without it keeps the grid-setpoint limit
until it's configured again.
Outside those hours nothing changes. Shown on the Status sensor as
`night_limit` (enabled, active now, the speeds).

Safety:

- **Automatic control** switch (an entity on the device): turn it off to
  take over by hand - it sends idle once, then leaves the target alone
  until you turn it back on. Its state survives restarts; on by default.
  Turning it off also turns **EV charger control** off (see "EV charger
  control and manual charging" under Electric car).
- **Grid setpoint by hand**: while Automatic control
  is off, the status card shows an orange block with a slider for the grid
  setpoint (only with a setpoint entity set up - with "Status sensor only"
  there's no switch and no slider). The slider runs over +/- 20 kW (the
  inverter's whole range; within the entity's own min/max), in the entity's
  own step (at least 100 W for a W entity), with - / + and quick picks:
  +/- 20 kW, idle, and 80 % of the configured max battery charge and
  discharge power. A value is sent once when you let go (or press a button),
  converted to the entity's own unit and sign - via the service
  `ess_manager.manual_setpoint` (`power_kw`, + = charge; or `idle: true`),
  which refuses while Automatic control is on. It shows in the diagnostics'
  `decisions_24h` (action `manual`). The plan blocks below are greyed and
  can't be used meanwhile. With a separate readback entity the inverter's
  readback is shown next to it. The setpoint stays until you change it or
  switch Automatic control back on (then ESS Manager takes over at the next
  cycle).
  While direct control isn't set up ("Status sensor only"), the switch is
  hidden (it has nothing to control); choosing a number / input_number
  entity in Configure shows it again - see [Hidden entities](setup.md#hidden-entities).
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
- A target that shows "unknown" (no value read back yet - some Modbus/MQTT
  numbers, like a Victron grid setpoint over MQTT without keepalive) is
  still written, only without the readback check; "unavailable" or a target
  that doesn't exist is not, and says so in `last_error`.

**Planned setpoint** (a sensor, kW, positive = charge) and the Status
sensor's `control_action` / `control` attributes show what would be sent -
also while direct control is off. That's the easy way to switch over:
leave control on "Status sensor only", compare Planned setpoint with what
your automation does for a few days, then choose direct control and
**disable your own ESS automation** so the two don't fight over the
setpoint.

If you leave the separate readback on the Battery control - target page
empty, the number entity you control is used as the setpoint readback for
the Status (`Start charge` vs `Actief`). Pick one when the entity you
control is only an in-between and the inverter reports what it really
took over - then the Status shows whether the inverter followed. A
readback equal to the controlled entity is cleared on saving (it's the
same thing), and switching between Status sensor only and direct control
never leaves an older readback behind unseen.

When does `Start charge` become `Actief` (and `Start discharge` become
`Actief`)? Once the readback holds at least half of the charge (discharge)
speed - or, with direct control, at least half of the
setpoint ESS Manager itself sent last. A charge that's deliberately below
the charge speed - the night limit, a car charging on the same grid - so
reads `Actief` as soon as the inverter has taken the setpoint, instead of
staying `Start charge` for the whole charge.

## Problem notices

 When something keeps the integration from doing its
job, a notice appears in **Settings > Repairs** - and goes away by itself
once the problem is over. A problem has to last a while first, so a sensor
that's briefly gone after a restart doesn't raise one:

| Notice | When | After |
|---|---|---|
| The setpoint can't be sent | direct control is on, but the target entity doesn't exist, is unavailable or the service call fails - the battery isn't steered meanwhile | 5 minutes |
| Planning paused - a sensor has no value | the battery SOC sensor has no number, or the price sensor is unavailable / has no prices for today - nothing is planned and direct control keeps the battery idle - for prices only when there are no stored prices for now either (see below) | 15 minutes |
| Planning on stored prices | the price sensor has no good prices, planning goes on with the stored ones, and two reloads of the price integration didn't bring them back | after the second reload + 5 minutes |
| A solar forecast sensor can't be read | a chosen solar forecast sensor is unavailable or gone (after the first 10 minutes from the start), or it has neither a Solcast `detailedHourly` nor a Helios Forecast `forecast` attribute - planning goes on but counts it as no sun (an attribute that's just empty for now is fine) | 15 minutes |
| Battery expected below its minimum | even with the plans, the battery is expected to run into a dip below its minimum within the next 24 hours that have prices and lie within the planning horizon - usually a charge that can't be fitted (charge speed, night limit, too little room) | 30 minutes |
| Planning stopped - unexpected error | the cycle keeps stopping on an error none of the other notices covers (a bug, a recorder error, data it can't handle) - nothing is planned and direct control keeps the battery idle; the notice shows the error, the log has the details | 15 minutes |
| A battery sensor stopped updating | the battery SOC, or the battery's power while the setpoint follows it (House from grid / Solar export), still has a value but no longer updates - the Status shows **Standby** and direct control keeps the battery idle until it updates again (see below) | at once (the check itself waits) |

**Prices missing: stored prices and a reload.** A price integration
(Nord Pool, say) sometimes leaves its sensor unavailable until it's
reloaded. Day-ahead prices don't change once they're published, so ESS
Manager keeps the last complete lists of today and tomorrow (stored, so
they survive a restart) and handles a sensor without good prices in two
ways at once:

- **It plans on with the stored prices.** Today's list from the store,
  tomorrow's when it was known; after midnight the stored "tomorrow" is
  today. Planning only stops (the *Planning paused* notice) when there's no
  list for the current day at all - the sensor was gone from before
  tomorrow's prices came out until after midnight.
- **It reloads the integration the price sensor belongs to** - the same as
  **Reload** on that integration's page in Settings > Devices & services.
  Nothing to set: the integration is looked up from the price sensor. The
  first reload comes after 5 minutes (never within 10 minutes of ESS
  Manager's start or while Home Assistant is still starting), then after
  15 minutes, 30 minutes and every hour, until the prices are back. Not
  while that integration is loading or unloading, or when it's disabled. A
  price sensor that doesn't belong to an integration (a YAML template
  sensor, say) is never reloaded - that's logged once.

What counts as no good prices: the sensor is unavailable, unknown or gone,
has no list for today, or - for a sensor with start times per price
(`raw_today` / `raw_tomorrow`, as the Nordpool HACS integration has) - a
list that belongs to another day. An empty tomorrow list is normal before
the prices come out (around 13:00). A list is only stored when it's
complete (96 quarters, 92 / 100 on a day the clock changes).

Only once two reloads didn't help (5 minutes after the second, so about 25
minutes) does it show: the notice *Planning on stored prices* (with how
long the prices are known and how often it reloaded) and a label on the
price card. Each reload is logged (warning). The diagnostics show it under
`coordinator.price_reload` (since when, the number of reloads, the last one
and its result: `ok`, `not_loaded`, `failed: ...`, `busy`, `disabled` or
`no_integration`) and `coordinator.price_cache` (the stored days and where
this cycle's prices came from: `sensor`, `cached` or `none`).

**A sensor that stopped updating.** An integration that loses its
connection often keeps the sensor's last value instead of making it
unavailable - and steering on a battery level or power that's no longer
true can charge or discharge the wrong way. So ESS Manager watches two
signs:

- *No new report:* the battery SOC for more than 10 minutes, the battery's
  power for more than 2 minutes while the setpoint follows it. Only for a
  sensor that reports regularly - one Home Assistant sees reporting the
  same value again (`last_reported` later than `last_updated`, e.g. the
  Victron GX integration). A sensor that only reports changes can keep the
  same value for hours while the battery stands still; for those this sign
  is skipped.
- *Flat while steered:* the setpoint changed 4 times in a row (about a
  minute in the 15-second loop) and the battery's power stayed exactly the
  same, at least 50 W - a real battery always moves a little. Not at 0 W (a
  full battery that takes nothing).

Meanwhile the Status is **Standby** - so an automation that follows the
Status idles too - and with direct control the battery gets the idle
value. As soon as the sensor reports again (or its value changes) the
notice goes away and the steering resumes by itself. Which sensors report
regularly and which are stuck is in the diagnostics under
`coordinator.sensor_watch`.

What's going on right now (also before it becomes a notice) is in the
diagnostics download under `problems`. Unloading or removing the
integration clears its notices.

## Diagnostics

 Settings > Devices & services > ESS Manager > the
three-dot menu > **Download diagnostics** gives one JSON file with
everything needed to see why the integration does what it does - handy to
attach to an issue instead of copying YAML out of Developer tools:

- the integration and Home Assistant version, the Configure settings, the
  number entities and switches;
- every entity chosen in Configure as the integration sees it: state,
  unit, availability and last update (a missing entity is marked as such).
  The price lists are included whole; a solar forecast sensor shows which
  format was recognised (Solcast or Helios Forecast) and the kWh per hour
  read from it; other long attributes are summarised;
- the last result: forecasts, all plans, the direct-control state (last
  value sent, when, why, last error), night limit, heat pump and EV;
- **the decision history**: every moment of the last 24 hours the battery
  action, the setpoint, the status or a control error changed, with time,
  SOC and price - what it did last night and why. Kept in memory, so it
  starts empty after a restart.
- **the floor's learning hours** (`floor_records`):
  every hour the heat pump ran for the floor with its averages (supply,
  return, thermal power, room, running seconds) - what floor control's
  emission model is fitted on.

ESS Manager stores no passwords or tokens, so nothing is blanked out; the
file does contain your energy data and entity names - share it with whom
you choose.
