# ESS Manager

[![Validate](https://github.com/MisterX-RC/ESS-manager-HA/actions/workflows/validate.yaml/badge.svg)](https://github.com/MisterX-RC/ESS-manager-HA/actions/workflows/validate.yaml)
[![GitHub release](https://img.shields.io/github/v/release/MisterX-RC/ESS-manager-HA)](https://github.com/MisterX-RC/ESS-manager-HA/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Home Assistant custom integration for battery/solar/price-aware charge and
discharge planning: it watches your battery's state of charge, a solar
production forecast, a household usage forecast, and dynamic electricity
prices, and decides when to charge, when to discharge, and how much. It can send the
charge/discharge setpoint to your inverter itself (optional - see "Direct
control"), or leave that to a separate, small automation that
acts on its Status sensor.

This started as a hand-written Home Assistant template sensor (that
original configuration is still in this repository's git history, up to
v0.2.20) and was rebuilt here as a proper, configurable custom
integration so it can be shared and installed on other systems via HACS,
without every install needing to hand-edit Jinja templates or hardcode
someone else's entity IDs.

## Screenshots

**Battery forecast** - always five whole days, today included. Left of
"now" what happened (the measured battery level, solar and household
usage), right of it what's expected: the battery level with the planned
actions in it, coloured by what the battery does (red for a sale, blue for
a charge, more intense for a spike or negative price plan), the solar and
usage forecast, and as a thin dotted line the battery level without any
plan. The band is your min / max SOC, everything after the planning
horizon is dimmed. Top right: the battery level now and how long you'd
last without the grid; below the chart a tile per day. Tap (or hover) for
the values at a moment.

![Battery forecast card](https://raw.githubusercontent.com/MisterX-RC/ESS-manager-HA/main/docs/images/battery-card.jpg)

**Prices** - today's and tomorrow's prices, coloured from cheap to
expensive (negative prices apart). The planned buy and sell moments stand
out in full colour, the rest is dimmed; what's past sits under a darker
layer, with the plans that ran still visible. Top: the price now, the buy
price and the cheapest / most expensive moment still to come.

![Price card](https://raw.githubusercontent.com/MisterX-RC/ESS-manager-HA/main/docs/images/price-card.jpg)

**Status** - the planned sale (Sell) and charge (Buy) side by side, with
start, stop, a bar that fills as the battery gets there, the energy and
the target SOC; an active spike or negative price plan outlines the block
it drives. Below: the price plan status and a timeline of what the battery
did over the last hours. Top right: the control toggle and a Settings
button to the ESS Manager device page.

![Status card](https://raw.githubusercontent.com/MisterX-RC/ESS-manager-HA/main/docs/images/status-card.jpg)

These are the integration's own dashboard cards (**ESS Manager - Battery
forecast**, **- Prices** and **- Status** in the "Add card" picker) - see
"Dashboard" below for their options.

## What it does

Five planning engines, all documented in detail in the code
(`custom_components/ess_manager/plans.py`):

1. **Low charge plan** - charges before the battery would otherwise drop
   below your minimum SOC, in the cheapest quarters before it's needed -
   just what's missing to keep the dip at the minimum SOC plus the
   **Safety buffer** (rounded up to the **Minimum charge target**), not a
   full battery. A charge split over several blocks is finished: once its
   first block has run, the rest still counts up to minimum SOC + buffer
   (not just minimum SOC) until the last planned block, so it isn't dropped
   just because the first block already lifted the dip above the minimum
   (as of 2026.10.13). As of 2026.10.19 a charge aims at the **lowest point
   of the planning horizon**, not just the first dip: every later dip gets
   its part before its own hours, in the cheapest quarters (what the first
   dip needs before the first dip, the rest before the lowest point), and
   only as much as fits under 100% before it - a sunny day that fills the
   battery in between moves that part to after it. The battery is kept
   higher all along (more left in a power cut), and a later dip can wait
   for a cheaper valley because the level is already higher. A dip below
   the surplus minimum is always met; the plan shows `lowest_kwh` and
   `horizon_target_kwh`.
2. **High discharge plan** - discharges before the battery would otherwise
   overshoot your maximum SOC, during the priciest available price window,
   selling the forecast peak back down to 100% (so with a max SOC of 110%
   a sale is always at least 10% of the battery),
   never selling below your minimum SOC plus the **Safety buffer**. A
   low charge lifts the dip to that same minimum + buffer.
   Selling before the battery would run full only pays when it earns
   clearly more (2 ct/kWh) than what the sun gets for that energy anyway -
   above 100% the extra solar simply goes to the grid at that hour's price.
   When it doesn't (say the best moment before the overflow is 0.13 while
   the overflow exports at 0.125 and tonight goes to 0.24), the overflow is
   left to the grid and what's still too much is sold before the next
   overflow, at its best price (as of 2026.10.10; the Status attribute
   `high_discharge_plan.overflow_to_grid` lists what was left to the grid).
   An expensive morning before a cheap midday overflow is still sold in
   the morning.
3. **Full charge plan** *(optional)* - periodically charges all the way to
   100% and holds there briefly to let the BMS balance cells, on a
   configurable interval. With a slow charger it's spread over several
   sessions (each at most four hours at the charge speed, or 30x the
   average hourly usage when that's more); the status card's Buy block
   shows the session - its energy over all its blocks and the level it
   ends at (as of 2026.10.33; up to then always "-> 100%"). While it's
   charging or balancing it comes first. While it's only **scheduled**
   (as of 2026.10.33) it no longer holds the other plans back: the low
   charge plan counts the full charge's quarters (it only buys what the
   full charge doesn't bring in in time, and never in the same quarters),
   and a low charge, negative price or spike plan whose window is now goes
   ahead - the status says `Full charge scheduled` only when nothing else
   is going on. Up to then a scheduled full charge kept everything else
   idle until it started, which with a slow charger could be days. A sale
   of the surplus (the max SOC sale) isn't planned while a full charge is
   due: that energy is what fills the battery.
4. **Spike arbitrage plan** - on a day with a large enough price spread,
   deliberately charges cheap and discharges into the peak instead of just
   capping at your normal SOC band. Before a discharge, it tops the battery
   back up to full if the forecast expects it to have drifted down a bit by
   then (so there's more to sell at the peak) - but skips that top-up
   entirely if the gap is smaller than **Minimum charge target**, rather
   than scheduling a trivial charge just to close a tiny forecasted dip.
   Between the charge and the sale it keeps re-planning on the live SOC
   (see "When plans move" below).
5. **Negative price plan** - when the price goes low enough that charging
   pays you outright, buys as much as your hardware can take in that
   window, clearing room beforehand if needed.

**When plans move and when they're fixed.** Every plan is worked out again
every cycle (once a minute) from the live battery level and forecast, so a window
still ahead can move or change size. Only a window that is running is
kept as it is until it ends (a low charge or high discharge also stops
early once it reaches its target): the charge or sale of the low charge /
high discharge / full charge plans, the cheap charge and the sale of the
spike plan, the room-making sale and the charge of the negative price
plan. Between the spike plan's charge and its sale, and before the
negative price charge, the plan keeps adapting to the real SOC (more
usage or less solar than forecast). Once the spike charge has run, a
further top-up before the peak is only bought in quarters where the buy
price is at least the **Spike margin** below the peak price, and only if
it's at least the **Minimum charge target**; the sale is sized on what the
battery is then expected to hold at the peak. (Up to v0.5.11 the spike and
negative price plans were fixed as a whole.)

**Charging in the cheapest quarters, each part before it's needed** (as of
2026.10.6). The low charge and full charge plans don't look for one long
window that holds the whole amount. Every part of a charge is bought in the
cheapest quarters before the moment it's needed: if the battery runs short
tonight and keeps draining until the day after tomorrow, it buys tonight
only what's needed to reach tomorrow's cheaper valley, and the rest there.
That can mean several blocks - each at least the **Minimum charge/sale duration**
(15-120 minutes, default 30), so it doesn't switch on and off every quarter.
The plan's window (what the Status, the stop and the status card follow) is
the first block; the status card shows "+2" for the blocks after it (hover
for when) and the charts draw them all. After a block the rest is planned
again from the real battery level. A part that's only needed after the last
known price waits until the next prices are in (they're published around
13:00, well before). A charge also only goes where the battery has room
for it (under 100% at every later hour) as long as it can. Making a block
long enough can add more than needed; what's then left over is dropped in
the way that leaves the cheapest plan (as of 2026.10.32 - up to then whole
blocks went first, so a cheap short block could go while dearer quarters
added to lengthen another block stayed).

**Selling in the priciest quarters too** (as of 2026.10.10). A sale isn't
one window either: it goes into the priciest quarters before the moment
it's needed, possibly in several blocks of at least the same **Minimum
charge/sale duration**. Each quarter is only used as far as the forecast
stays at or above your minimum SOC + Safety buffer from then on, so a sale
that can't go all at once before a low point (say tonight's 19:30 peak,
with a low point at 07:00) sells what fits there and the rest after that
low point - instead of either selling less, or all of it at the cheaper
moment. The first block is the plan's window, like a charge.

**Charging with the sun in mind** (as of 2026.10.4). The battery takes at
most your **max battery charge speed**. In a sunny hour the sun already
charges it, so a grid charge can only add what's left up to that max -
nothing at all when the sun alone fills it (say a 1.8 kW charger with
2.5 kW of sun and 0.4 kW of house use). The charge plans (low charge, full
charge, spike top-up, negative price charge) work out per quarter what the
grid really adds: the sun only makes a window longer - quarters it already
fills add nothing, so the window runs on until the amount is in - and the
cheapest window is still chosen, costed on what's really bought (minus
what would go straight back to the grid, which only costs extra with a
transport tariff). A
low charge stops at the forecast level at the end of its window plus its
amount (never above 100%), so the sun shining during the window doesn't
count toward what was meant to be bought; and it's only planned where the
amount still fits in the battery.

**A settings change re-checks running windows.** When you change one of the
integration's numbers (or save Configure), the next cycle plans everything
afresh, running windows included - so a charge started because of a
threshold you've since changed back stops if it's no longer needed (or
continues, resized, if it still is). A switch between solar surplus and
deficit does the same, since it changes the minimum SOC every plan works
with. A (re)start of Home Assistant or the integration does it too (as of
2026.10.14), so a window stored before the restart is checked against the
current settings and forecast. When a sensor it needs (battery SOC, price)
isn't there yet right after a restart (as of 2026.10.15), the entities are unavailable until
the next cycle (once a minute) finds it - no reload needed. For the first 10
minutes after a start it also waits for the solar forecast sensor(s) and the
household usage statistics, so it never plans with "no sun" or "no usage"
just because those weren't loaded yet; after that it plans with what there
is. The full-charge balancing wait at 100% is
never interrupted by it.

All five compose on top of a 121-hour (5-day) forecast pipeline: solar
forecast minus usage forecast, cumulatively summed into a projected battery
level, compensated for the fact that the current hour is only partially
elapsed (see the code comments in `forecasting.py` for why that matters).

**Two forecasts at the top: clipped and not.** The running sum of solar
minus usage has no top - on a sunny day it can "fill" the battery to 106%.
In reality the battery stops at 100% and the rest goes to the grid. So
(as of 2026.10.1) the charge plan, the negative price and spike plans and
the cards use the forecast clipped at 100% - after a full day the next dip
starts from 100%, not 106%, so a morning dip isn't underestimated (and the
negative price plan never plans to charge above 100%, whatever the max
SOC). The sale plan keeps the unclipped one:
the highest expected level is exactly what it sells off (with a max SOC
of 110%, the part between 100% and 110% isn't sold and shows as solar
surplus instead). The solar mode also keeps looking at the unclipped
forecast, since "fills up" means going over 100%. Status attributes:
`battery_forecast_adjusted` (clipped) and
`battery_forecast_adjusted_uncapped`.

**Two minimum SOCs: solar deficit and solar surplus.** The minimum SOC is
the backup energy you keep for a grid failure. How much you need depends on
whether the sun or the grid refills the battery, so there are two:

- **Minimum SOC (solar deficit)** - used when the raw battery forecast
  (solar and usage only, no planned charges or sales) runs empty (below 0%)
  before it would fill up past 100%. The grid will have to refill the
  battery, so keep a real reserve.
- **Minimum SOC (solar surplus)** - used when the forecast fills up past
  100% before it would run empty. The sun refills the battery, so this one
  can be set close to 0. A short dip followed by a climb to 100% stays
  surplus, so it doesn't trigger a charge the sun would make useless.

The whole 121-hour forecast counts, and the nearest of the two moments
decides. 0% and 100% are the only switch points: when the forecast does
neither within the 5 days (it stays between 0% and 100% all along), the
mode simply stays what it was (as of 2026.10.8 - before that it went back
to surplus). The mode is stored, so a restart or an update keeps it too; a
brand-new installation starts in surplus. The minimum in use is the low threshold for every plan - when to
charge, and how far a sale may go. The **Solar mode** sensor shows
`Deficit` or `Surplus`, the minimum in use, in how many hours the raw
forecast runs empty or fills up, and `held` (true while it does neither and
the previous mode is kept); the battery chart's min SOC line follows
the minimum in use.

**In deficit mode the surplus minimum stays the hard floor.** Deficit mode
looks 120 hours ahead, so there's no hurry to get above the (higher)
deficit minimum - the battery may well sit below it when the mode
switches. The charge plan therefore treats the two differently:

- A dip below the **surplus minimum** is charged for before the battery
  gets there, the full amount, exactly as in surplus mode.
- A dip that only reaches into the band between the two minimums is
  charged in the cheapest window before its lowest point (as of
  2026.10.8 - until then before the dip was over, so part of it could be
  bought after the lowest point, when it no longer lifts anything) -
  just what's missing (rounded up to the **Minimum charge target**), and
  never more than still fits under 100% at the forecast peaks after the
  charge (a peak before it, like this afternoon's for a charge tomorrow,
  doesn't count - the window goes after it), so nothing
  bought now is lost again on a later solar day that fills the battery. If
  less than the Minimum charge target fits, it isn't charged now; the
  deficit minimum is picked up again once that peak is behind it. A dip in
  the band that's at its lowest right now (the sun lifts it on its own)
  needs no charge.

A charge for a dip below the surplus minimum buys what's missing up to
the surplus minimum plus the band part that fits. No charge fills the
battery up to 100% any more (as of 2026.10.7).

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
  with the planning engines' 15-minute unit indexing. The lists run in
  real time from local midnight, so the day summer time ends has 100
  quarters and the day it starts 92; ESS Manager counts the current
  quarter the same way (as of 2026.10.25).
- **Household usage forecast**: nothing extra if your Home Assistant
  Energy dashboard is set up (at least a grid source) - the integration
  calculates the forecast itself from the statistics the Energy dashboard
  already uses. Alternatively, a sensor reporting your home's total energy
  consumption (cumulative kWh). See "Household usage forecast" below.
- **Solar forecast**: one or more sensors in either of two formats - the
  integration recognises which one each sensor has by itself:
  - **Solcast**: a `detailedHourly` attribute, a list of
    `{"period_start": <ISO timestamp>, "pv_estimate": <kWh>}` objects. Add as
    many forecast-day sensors as you need to cover 121 hours from whatever
    time of day updates happen to run (Solcast typically needs
    today/tomorrow/day_3 at minimum, more if you want headroom late in the
    day).
  - **Helios Forecast** *(as of 2026.10.21)*: pick its "Power now" sensor
    (`sensor.helios_forecast_power_now`). Its `forecast` attribute holds one
    point per quarter hour (`{"datetime", "watts", ...}`) from midnight
    today through seven days ahead, so that one sensor covers the whole
    horizon. Each hour's quarters are averaged: W / 1000 = kWh in that hour.
    Helios set up once per roof plane (one installation per plane) gives
    one "Power now" sensor per plane: add them all, the integration adds
    them up per hour. One Helios installation with several planes already
    gives the total in one sensor.
  Sensors that cover the same hours are added up (several roof planes);
  Solcast's day sensors each cover their own day, so they simply follow
  on. A sensor with neither attribute counts as no sun at all, so the
  integration logs a warning for it once.
- **Grid/inverter setpoint** *(optional but recommended)*: the entity that
  holds your current commanded charge/discharge power - a sensor, a
  `number` or an `input_number` (for example the input_number your own ESS
  automation writes to). Right below it you choose its polarity:
  "Positive = import from the grid (battery charges)" (the default) or
  "Positive = export to the grid (battery discharges)". W or kW is
  taken from the entity's unit, so give an input_number a unit of `W` or
  `kW` (no unit counts as W). Used to make the "Status" sensor's engaged-vs-starting
  distinction accurate; nothing is ever written to it. With direct control
  of a number entity you can leave it empty (see below).
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

The planning runs once a minute, and also right at every quarter boundary
(:00, :15, :30, :45 - as of 2026.10.20; it was every 30 seconds), so a
planned block or the night limit still starts and stops on the quarter.
Changing a setting on the card replans straight away. The heavy parts - the battery plans
and the heat-pump model - run in a worker thread (as of 2026.10.20), so
even on a Raspberry Pi they don't hold up the rest of Home Assistant;
only reading the sensors, sending the setpoint and setting the thermostat
happen on Home Assistant's event loop.

## Household usage forecast

Every planning engine needs a household usage forecast. There are two
sources: **your Energy dashboard** (recommended) and **a home energy
consumption sensor**. Both average the same hour-of-day/day-of-week over
however many weeks back you choose (default 6), from Home Assistant's own
long-term statistics. That works the same whether your recorder is SQLite,
MariaDB/MySQL or Postgres, is recomputed about once an hour (statistics only
land once an hour anyway), and a week with a genuine gap in the data (an
entity that didn't exist yet, a recorder outage) is left out of that hour's
average rather than counted as zero.

**Short history** (for example a statistic you just added to the Energy
dashboard, or a new consumption sensor): an hour with no usable week at all
uses the same clock hour on each of the last 7 days that has data, whatever
the weekday. With one day of history that's yesterday's hour; after a week
the normal same-weekday average takes over by itself. Note that every
statistic has to have data for an hour: one new statistic in the energy
balance also makes the older grid and solar history for that hour unusable
until it has history of its own. Only with less than a day of data is an
hour counted as 0 kWh.

The **Usage forecast history** sensor (diagnostic, on the device) shows how
the forecast is filled in: `OK` (every hour has a same-weekday average),
`Short history` (some hours use the last days) or `No history` (some hours
have no data and count as 0 kWh), with the hour counts as attributes. A
change is logged once, and while more than half of the forecast has no
history, a notice under Settings -> System -> Repairs asks you to keep an eye
on the plans; it disappears by itself. The Status sensor is not affected by
any of this.

*Removed in 0.3.0:* the older **existing h0..h120 sensor** and **calculated
from hand-picked sensors** sources (deprecated since 0.2.10). When an
installation that still used one updates to 0.3.0, it's switched to the
Energy dashboard source automatically if the Energy dashboard has a grid
source, with a notice under Settings -> System -> Repairs asking you to
check the forecast. If that's not possible, planning pauses and Repairs
shows an error until you pick a source in Configure - it never plans with
zero household usage.

**Calculated from your Energy dashboard** *(recommended)* - the
integration reads the grid, solar and battery statistics straight from
Home Assistant's own Energy dashboard configuration (Settings -> Dashboards
-> Energy). They're re-read about once an hour, so any change you make in
the Energy dashboard is picked up automatically - there's nothing to keep in
sync. The setup step shows exactly which statistics it detected before you
confirm, and the Status sensor's `energy_dashboard_sources` attribute shows
what's currently in use. Multiple grid connections, solar arrays and
batteries are all supported (every one is summed into its term), as are
external statistics that have no sensor behind them (e.g. `tibber:...`). The
household usage is derived with the energy balance

```
consumption = solar produced + grid imported + battery discharged
              - grid exported - battery charged
```

The Energy dashboard needs at least a grid source configured; gas, water and
individual-device entries are ignored. This relies on an internal Home
Assistant interface - if a future HA version changes it and the
configuration can't be read, the integration logs a warning and keeps using
the last good forecast rather than failing.

**A home energy consumption sensor** - if you already have a sensor that
reports your home's total energy consumed (cumulative kWh), point the
integration at it directly. No energy balance is derived at all, which also
avoids a failure mode the Energy dashboard option can hit when one of the grid/
solar/battery sensors reports much more coarsely than the others (e.g. a
grid meter that only ticks in 0.1 kWh steps a few times an hour) - Home
Assistant's hourly statistics then lump that sensor's flow into whichever
hour it happened to tick over in, giving odd (even negative) hourly swings.

Both options read the recorder's statistics converted to kWh, so sensors
reporting in Wh or MWh work too.

## Electric car

For an electric car that charges **from the home battery** (as of
2026.10.11). A car that doesn't take power from the battery doesn't need
any of this - its charging never shows up in the battery's planning.

Switch it on in Configure, on the price plans page (**Electric car that
charges from the home battery**); two pages follow:

- **The charger**: its **energy sensor** (cumulative kWh - Wh works too)
  and **power sensor** (W or kW) - or a **Victron EV charging station**,
  which ESS Manager then drives (see below) - the **minimum and maximum charging
  current** (default 6 and 16 A, up to 75 A), the **phases** (1 or 3, at
  230 V per phase - 16 A on 3 phases is 11.0 kW) and **Predict sessions
  from history**.
- **The cars**: a name, optionally the battery size (kWh) and the usual
  target (%). Add as many as you like ("Add another car"), or remove them.

**Household usage without the car.** The charger's energy is always taken
out of the household usage history (also with prediction off), so the
usage forecast is the house alone. The car only enters the 120-hour
forecast through its **charging sessions**: they're added to the usage the
plans work with (`energy_usage_120h` - the battery card's usage includes
them). The measured usage in the battery card still includes the car.

**Predicted sessions.** With prediction on, a session that started around
the same hour on the same weekday in **more than half** of your lookback
weeks is predicted for that day: at the most common whole start hour, with
the average energy, and charging at the typical full hour's current (between
your minimum and maximum). When it charged from the solar surplus (at least
80% of its energy fitted in what the sun had left after the house - only
known with the Energy dashboard as usage source) it's predicted as a solar
session, with a red border on the card. With prediction off the list
starts empty and every session is added by hand.

**Cars.** With **one** car, every session (predicted ones too) is that car's
and - with a battery size - shown in %: the start SOC is worked back from
the target and the energy, and changing it changes the energy and the
duration. With **more** cars a predicted session has no car (kWh only)
until you pick one.

**Fixed current or solar surplus.** A fixed session charges at its current
from its start until its energy is in. A solar session charges per hour on
what the solar forecast has left after the house, at most the maximum
current and only when that's at least the minimum current, until the end of
its day; sessions on the same day share the surplus in start order. When
there's no surplus that day, or not enough, the card says so.

**Running.** While the power sensor is above 0 (50 W), the session it
belongs to (started up to two hours early or late, as of 2026.10.29) is running: its day and
start time are fixed, the rest can still change, and what's already charged
(from the energy sensor) counts. Charging that matches no session becomes a
manual session from the current hour (with the typical energy - change it
on the card). Ten minutes without power and the session is done.

### Victron EV charging station

*(As of 2026.10.27.)* Instead of an energy and a power sensor, the charger
page can take a **Victron EV charging station** - the device of the
**Victron GX** integration (in Home Assistant itself since 2026.5). Its
entities are found on the device by themselves (status, power, total
energy, mode, charge current setpoint, EV charging; a car is plugged in when
the Status isn't "disconnected"); the energy and
power then also feed the history and the prediction, so leave those two
sensors empty. Then ESS Manager **drives the charger** and asks on your
phone what to do. Pick the phones under **Phones to ask on**: the Home
Assistant Companion app's notify services (`notify.mobile_app_...`) -
those show buttons and a reply field. Without a phone nothing is asked
and ESS Manager doesn't start the charger (unless a planned or predicted
session is taken over - see below).

**A car is plugged in** (the charger's Status is anything but "disconnected"): a session
starts and planned sessions it overlaps are dropped (the first one's energy
is the estimate until you say more). With more than one car the first
question is which one (buttons; with more than three cars - Android shows
three buttons - you type its number or name). Then: **As fast as
possible**, **Slowly now** or **Full by a time**.

- **As fast as possible**: the charger starts right away at the maximum
  current (Manual mode). Then it asks for the car's state of charge (%) -
  for a car without a battery size: the kWh to charge - and answers when
  it will be full.
- **Slowly now**: the same at the minimum current.
- **Full by a time**: today, tomorrow, the day after or "doesn't matter"
  (as of 2026.10.31 tomorrow and the day after are shown as their day of
  the week - *Tuesday*, *Wednesday*; that's four buttons: an iPhone shows
  them all, Android only the first three, so "doesn't matter" is then on
  the card); for a day it asks the hour (typed: `7`, `7:30`, `19u`), then the state of
  charge. What's needed (to the car's target %) is planned: **the sun
  first** - the charger on its own **Auto** mode, which charges on the
  solar surplus - and whatever the solar forecast can't deliver in time
  is **bought in the cheapest quarters before the deadline** ("doesn't
  matter": within the prices known), in Manual mode, in blocks of at least
  half an hour. ESS Manager picks the speed itself (as of 2026.10.29): the
  **lowest current** that still gets it in on time - a calm charge where
  there's time - and it plans to be done **an hour before** the time given
  (full by 10:00 = done by 09:00). When even the maximum current doesn't
  make it, it charges at the maximum right away and says how far it gets
  (red on the card). The answer says how much comes from the sun, how much
  is bought when and at what current, and when it's full. The plan is worked out again every cycle (new prices, a
  different solar forecast, what's charged so far); a grid window that's
  running finishes.
- **During a grid window the house battery stays out of it**: with direct
  control, the grid setpoint sent goes up by what the car takes (measured),
  so the grid supplies the car and the battery does what it was going to
  do anyway; the battery forecast leaves that energy out too.

**Until there's an answer** - and when there never is one - ESS Manager
**doesn't start anything** (as of 2026.10.31; up to then the charger was put
on its Auto mode), unless the car is plugged in during a planned or
predicted session: then that plan is taken over and charging starts (see
*Planned "full by" sessions* below). **Unplugging puts the charger back to
rest** (Manual mode, charging off - once), so the next car plugged in
without a plan doesn't charge by itself on what the last session left
behind. ESS Manager sends a value to the
charger only when its plan changes (plugging in, a choice, a grid window
starting or ending, done); what you change on the charger itself in
between - e.g. starting a charge by hand - is left alone (as of
2026.10.28). A charge the charger starts **by itself** before there's a
choice - by hand on the charger, its own auto start, a schedule or its own
Auto mode - counts as "now, at the current it's set to": it goes on, the
session is forecast at that current, and the card says so. A choice made
afterwards takes over. The plugged-in car's
session can't be removed on the card while the car is plugged in. Once the
energy is in according to the sums (or the charger says "charged") the
charger is **left as it is** (as of 2026.10.29; up to then it was switched
off): the car stops by itself when it's really full, and a state of charge
or a battery size that's a bit off doesn't leave it short. Unplugging ends
the session and clears the notification. With direct control's **Automatic
control** switch off, ESS Manager doesn't touch the charger.

**The plug-in log and the predictions** (as of 2026.10.29). With the Victron
charger ESS Manager keeps its own log of every time a car was plugged in
(car, plugged in, unplugged, kWh, the way of charging chosen, the time for
"full by"), 12 weeks long - the recorder keeps plugged-in states only about
10 days. Once the log covers your usage lookback (usually 6 weeks), the
predicted sessions come from it, per connection instead of per charge: a
"full by" that the prices split into two blocks is one session. A
connection that comes back on the same weekday around the same time (within
two hours) in more than half the weeks becomes a session with the average
energy and the way of charging chosen most often - "full by" the usual time
(the times chosen, else the usual unplug time), also without a choice when
the car usually stays plugged in well over twice as long as charging takes.
Until then the predictions come from the charging energy, as before.

**Planned "full by" sessions.** A planned session can be "full by" as well
(on the card, or predicted from the log): it's forecast with its own plan
(the lowest current that gets it in an hour before its time, sun first, the
cheapest hours; where the prices for then aren't known yet, a calm charge
from its start), and the battery forecast leaves its grid part out. **Plugged
in during a planned session** - one predicted from the log or from the
charging energy, edited or added on the card - its plan is taken over right
away, and the phone only asks
"the planned session is taken over: full by 07:30, 9 kWh. Is that right?" -
**Yes** keeps it (the end time follows), **Something else** brings the usual
questions (the plan stays until a new choice). As of 2026.10.31 sessions
predicted from the charging energy are taken over too (up to then they
weren't); a session counts from two hours before its start to two hours
after it (or to its end or "full by" time). Nothing planned or predicted
then: only the question, and the charger isn't started.

**09:00 on a day with a planned session** (predicted or added on the
card): "A charging session is planned today at 18:00 - still right?"
**No** removes it; **Yes** asks the expected state of charge (or kWh),
which then sets the session's energy.

**The same on the EV card** (rebuilt in 2026.10.29: one way of charging for
every session, one panel). At the top, **Now**: the plugged-in car. Without
a choice yet, four buttons - **Fast**, **Slow**, **On the sun** (the solar
surplus only - the charger's Auto mode) and **Full by …** - open the panel:
for "full by" the day (today, tomorrow, the day after - those two by their
day of the week - or doesn't matter) and the time, then sliders for the state of charge
now and the target (or the kWh for a car without a battery size), and the
result, worked out live while you slide: how much from the sun, how much
from the grid in which windows, the current ESS Manager picks, when it's
full and the hour to spare - or, in red, that it doesn't fit and how far it
gets. **Start** sets it all at once; the open question on the phone goes
away and the end time arrives as a notification, the same as after
answering there. With a plan the block shows the progress (state of
charge), for "full by" a timeline of the grid windows up to the deadline,
and **Change** opens the panel again - for Fast/Slow with a slider for the
charging current; the end time follows the slider. Below, **Planned**: the
predicted and added sessions, each with its way of charging (fast, slow or
on the sun); tap one to edit it in the same kind of panel (day, plug-in
time, way of charging, state of charge when plugged in and target; for
"full by" the day and the time it should be full - as of 2026.10.32 the day
is picked too: the plug-in day or one of the three after it, moving along
when the plug-in day changes). The card uses the service `ess_manager.ev_charge_plan` (`choice`: asap / calm /
solar / deadline, `day`: today / tomorrow / after / any, `hour`: "07:00", `soc` or
`kwh`, `target_soc`, `current_a` for asap/calm, `car`) - also usable in
automations.

The plugged-in car's plan is on the Status sensor's `ev` attribute
(`charger`: connected, status, and the session - question, choice,
deadline, needed / left kWh, grid windows, solar / grid / short kWh,
expected end) and on the EV card under the running session.

Edits are stored and survive a restart; the planning is worked out again
right after each one. The sessions are on the Status sensor's `ev`
attribute; the card uses the services `ess_manager.ev_session_save` and
`ess_manager.ev_session_remove` (also usable in automations - see
Developer tools > Actions).

## Heat pump

For a heat pump whose electricity follows the weather (as of 2026.10.16).
The household usage forecast is the same hour and weekday averaged over the
last weeks - for a heat pump that lags behind: too low in autumn, too high
in spring. With this switched on, the heat pump is forecast from the weather
forecast instead, with a model ESS Manager keeps itself.

Switch it on in Configure, on the price plans page (**Heat pump: forecast
its usage from the weather**); two pages follow:

- **Metering**: **separate sensors** per mode (heating, and optionally
  cooling - hot water stays in the household usage, whose weekday/hour
  average forecasts its fixed rhythm well), **one total sensor** (the model
  splits it: what is used every day regardless of the weather - hot water,
  standby - becomes its daily base, what grows with the cold is heating,
  what grows with the warmth cooling), or **no own metering** (the model
  works on the total household usage and only adds the weather difference
  to the usual forecast - least accurate).
- **Sensors**: the energy sensor(s), the **outdoor temperature** (it needs
  long-term statistics; one from the internet, like the heat pump's own, is
  fine), the **weather forecast** (a weather entity: Met.no, Buienradar,
  Open-Meteo, ...; read per day, per hour where it has it) and optionally
  wind speed, wind direction, indoor temperature (it also teaches the model
  how fast the house cools - see below; without it a thermostat's own
  temperature is used) and the wanted
  temperature (a thermostat or a sensor/number).

**How it works.**

- **The journal**: one row per day in the integration's own storage - the
  heat pump's energy, the mean outdoor temperature, wind, wind direction,
  sun (the measured solar production with the Energy dashboard, else the
  day's solar forecast) and the wanted temperature - up to two years. On
  the first start it's filled from the long-term statistics that already
  exist; after that yesterday is added every day. What has no statistics
  (a wind direction, a thermostat) is recorded live from then on.
- **The slow part, an energy signature**: per day, kWh = base + kWh per
  degree below the balance temperature (+ wind x degrees, + wind direction
  once there are enough days in most directions) - sun (+ kWh per degree
  above the cooling temperature, with cooling data - from 16 °C at the
  lowest). With the indoor temperature on most cool days the heat loss
  follows indoor - outdoor: the balance temperature belongs to the usual
  indoor temperature and moves with each day's own, so a degree warmer
  inside costs the kWh per degree colder; the coming days are forecast with
  the usual indoor temperature of the last heating days, moved by how much
  the thermostat now differs (a holiday at 16 °C). Without it, the wanted
  temperature moves the balance temperature once it has varied. The balance and
  cooling temperatures are found by the model. It uses a smoothed outdoor
  temperature (70% today, 30% yesterday - floor heating reacts slowly). It's
  worked out again every night; recent days weigh more (half-life about a
  season), but the three newest days of each temperature class keep
  weighing, so last winter's frost days count until newer ones come.
- **The fast part, a correction**: measured against the model over the last
  four days; a difference of 5% or more is taken along (between 0.6 and 1.6
  times) and fades when the difference goes - say a thermostat set a degree
  higher, or a holiday.
- **Into the forecast**: the expected energy per day, spread over the hours
  with the hourly pattern of the last two weeks; past the weather forecast
  the usual average. With its own metering the heat pump's energy is then
  taken out of the household usage history (like the electric car) and the
  model's forecast added; without, the model's difference to the usual
  average is added.
- **Days left out**: a cool day without heat demand (with a thermostat -
  a climate entity - as the wanted temperature: it asked for heat less than
  half an hour that day; its hvac_action, else indoor below wanted; the
  recorder's last ~10 days on the first start, live after that), a cool day
  on which the house lived on its stored heat
  (with an indoor temperature: it cooled 0.3 °C or more from midnight to
  midnight while the heat pump heated at most 4 hours - typical for autumn,
  out of the summer) says nothing about what such a day needs, and a day far
  off the model is a meter jump: both are left out of the fit. On the
  Signature tab they're grey rings.
- **Falling back**: with fewer than 21 heating days, or heating days in fewer
  than 3 temperature classes of 2.5 °C (3+ days each), a poor fit or no
  weather forecast, the heat pump stays in the household usage as before
  (6-week average). In summer (no heating day in the coming days) only the
  daily base counts.
- **The house's own heat** (with an indoor temperature and the heat pump's
  own metering - the indoor temperature is a separate sensor with long-term
  statistics, or else a thermostat's own current temperature: that one has
  no statistics, so its last ~10 days come from the recorder and from then
  on ESS Manager keeps it per hour itself; it gets better as the weeks go): every day the model learns
  how fast the house cools from the hours the heat pump didn't heat (the last
  60 days, hours with 15 °C or less outside and at least 4 °C difference -
  summer hours with windows open say little): per hour the indoor
  temperature drops by a share of the difference with outside - more with wind, less with sun (the measured solar
  production with the Energy dashboard) and what the house gives off itself.
  A floor keeps giving heat after the heat pump stops, so the three hours
  before count as heating too - six when the measurements show the house
  still warming up in between (otherwise it would look like it cools slower
  than it does). With the energy signature that gives the heat the house
  holds, as heat pump electricity per °C indoor.
- **Compared with what's usual**: the reference is the usual indoor
  temperature at this hour, from the last 14 heating days (summer days don't
  count). A heating schedule - a little warmer in the evening so the floor
  bridges the night, when the outside air gives a worse COP - is in that
  usual temperature and already in the hourly pattern of the forecast, so it
  isn't counted as "colder than wanted" in the evening or "warmer than
  wanted" at night. Only what differs from usual counts. A house **warmer
  than usual** (0.3 °C or more) coasts: with the hourly weather forecast it's
  worked out when it's back on its usual track, and until then only the base
  (hot water, standby) is forecast - at most the heat the house holds.
  Typical for autumn: out of the summer, a warm house while it suddenly gets
  cold outside. A house **colder than usual** (after a holiday, say) needs
  that heat extra, in the first 6 hours. Without 5 heating days with indoor
  data yet, the wanted temperature is the reference - and also when the thermostat is
  set outside its usual range (a holiday at 16 °C: the house then coasts
  until it's down there). Holiday days don't count for the usual
  temperature. Only in the heating season.
- **A changing wanted temperature**: the coming days are forecast with the
  average wanted temperature of the last week (a whole day with its
  schedule), not the value of this moment - otherwise every day would look
  like the evening (or the night).

**The house hour by hour (step 1) and steering (step 2)** - two switches on
the heat pump page in Configure, as of 2026.10.17:

- **Step 1, the forecast**: the model also learns how the indoor
  temperature follows the outdoor temperature, wind, sun and the heat put
  in - with the floor's delay (its time constant it finds itself) and,
  with the optional **COP sensor**, the COP by the outdoor temperature (so
  it counts the heat, not only the electricity). It forecasts the indoor
  temperature and the heating per hour for 48 hours, the heat pump emulated
  keeping the house on its usual temperature per hour. **Self-check**: every
  day the newest 14 heating days are played again with their measured
  weather, with a model fitted on the days before them: is the energy put
  in the right hours (compared with the usual hourly pattern, both scaled
  to the measured day total) and does the house follow the measured
  temperature with the measured heating? When the energy per hour is
  clearly better (at most 90 % of the pattern's error) and the indoor
  temperature within 0.6 °C, the battery planning places the heat pump's
  hours by the model (each day's kWh stays the energy signature's); when
  that's no longer so it falls back to the pattern by itself. Nothing to
  switch by hand.
- **Step 2, steering** (needs step 1 and a thermostat - a climate entity):
  on the card a steering switch, a day and a night temperature with the
  hours they start, and a buffer range. Steering on: the thermostat follows
  the day/night temperatures; once step 1 has passed its self-check the
  house is also used as a buffer within the range - warmer in cheap or
  sunny hours (an evening boost before a cold night), cooler in the most
  expensive ones - when it saves at least 0.10 over the hours with prices.
  It weighs the prices, the solar surplus, the COP at each hour's outdoor
  temperature and how long the house holds its heat, once an hour. A change
  by hand on the thermostat wins until the next day/night switch; switched
  off, the thermostat goes back to the plain day/night temperature once and
  is then left alone. Entities (only with both steps on): **Heat pump
  steering** (switch, off by default), **Heat pump day temperature**,
  **night temperature**, **buffer range**, **day from**, **night from**.

The model is on the Status sensor's `heat_pump` attribute and on its own
diagnostic sensor **Heat pump model** (state active / learning / summer /
fallback, attributes the figures), hidden while the heat pump is off.

### Floor control

*(as of 2026.10.23)* With a thermostat the heat pump runs until the room
reaches its setpoint - by then the floor still holds a few hours of heat
that comes out afterwards, and the room overshoots. With floor control ESS
Manager heats the floor itself: the hour-by-hour house model plans the heat
per hour that keeps the room on its wanted temperature (easing off before
the room is there, because it knows the floor keeps giving), and that heat
becomes

- a **return setpoint** for the heat pump: the floor gives off heat in
  proportion to the mean water temperature above the room (or above the
  screed, with a floor sensor). How much - kW per °C - ESS Manager learns
  from the supply and return temperatures, the room and the heat pump's
  thermal power. Little heat needed: a low setpoint and a better COP;
- **heat demand** on/off: on when the heat owed (planned minus delivered)
  is worth a run, off once it's in - at least 45 minutes on and 20 off for
  the compressor, and always on more than 1 °C too cold / off more than
  1 °C too warm (1.5 °C: even within those times). A safety net for a floor
  that gives off less than learned: from 0.2 °C too cold the power goes up
  (full at 1.2 °C), and 1 °C too cold the return setpoint never goes below
  the one the heat pump had before.

**Three stages**, chosen on the heat pump card (tab **Floor**, or the
select **Floor control**), each only running once the one before has
proven itself:

| Stage | What happens | Runs once |
|---|---|---|
| Watch (default) | nothing changes: the thermostat switches, the return setpoint stays; ESS Manager learns and shows what it would do | - |
| Return setpoint | ESS Manager sets the return setpoint by the planned heat, the thermostat still switches heat demand | the floor's heat output is learned: 30 settled running hours, at most 25 % off on the newest hours |
| Full | ESS Manager also switches heat demand; the thermostat is only where the wanted temperature is set | the heat pump delivered the target power within 30 % for 24 running hours in the return setpoint stage, and the house model passed its self-check |

The supply and return sensors sit in the heat pump: with the circulation
pump stopped they warm up from the cabinet, so only samples with the pump
running (and settled for 10 minutes) count. A **floor sensor** in the
screed (optional, between two pipes, about half way down) is used as the
reference instead of the room once most running hours have it.

**Setting it up:**

1. Let your `generic_thermostat` switch a helper instead of the heat
   pump - create an `input_boolean` (e.g. `input_boolean.thermostat_heat_demand`)
   and make it the thermostat's `heater`. The thermostat stays exactly as it
   is on your dashboard: that's where you (or anyone at home) set the wanted
   temperature, also a temporary raise.
2. Add the fallback automation: it copies the helper to the heat pump's heat
   demand whenever ESS Manager isn't in the stage *full* - also when ESS
   Manager is stopped (the stage sensor then is unavailable) - but never
   while the heat pump cools. Settings > Automations > Create automation >
   three dots > *Edit in YAML*, paste, and replace the four entity ids with
   yours (the helper, ESS Manager's *Floor control stage* sensor, the
   changeover switch for cooling and the heat pump's heat demand switch):

   ```yaml
   alias: "Heat demand: thermostat to the heat pump"
   description: >-
     Copies the thermostat's helper to the heat pump's heat demand while
     ESS Manager doesn't switch it itself (stage not 'full', or ESS Manager
     stopped) and the heat pump isn't cooling.
   mode: queued
   triggers:
     - trigger: state
       entity_id: input_boolean.thermostat_heat_demand
     - trigger: state
       entity_id: sensor.thuis_floor_control_stage
     - trigger: state
       entity_id: switch.qube_cooling_changeover
       to: "off"
     - trigger: homeassistant
       event: start
   conditions:
     - condition: not
       conditions:
         - condition: state
           entity_id: sensor.thuis_floor_control_stage
           state: "full"
     - condition: state
       entity_id: switch.qube_cooling_changeover
       state: "off"
   actions:
     - if:
         - condition: state
           entity_id: input_boolean.thermostat_heat_demand
           state: "on"
       then:
         - action: switch.turn_on
           target:
             entity_id: switch.qube_heat_demand
       else:
         - action: switch.turn_off
           target:
             entity_id: switch.qube_heat_demand
   ```

   Your own cooling automation keeps the heat demand switch to itself while
   the changeover is on. Let it switch the changeover on a few seconds
   *before* it turns heat demand on (the cooling thermostat calling for
   cooling already counts before that).
3. Configure > the heat pump page: switch on **Floor control** (needs step 1
   and the thermostat as the wanted temperature); the next page asks for the
   return setpoint, the heat demand switch, the thermostat's helper, the
   supply / return temperatures, the circulation pump (%), the thermal power,
   optionally the floor sensor and - with cooling - the changeover switch
   and/or the cooling thermostat.

**Cooling.** The heat pump's heat demand switch also starts cooling (with
the changeover switch on). While the changeover is on, or the cooling
thermostat calls for cooling (its action is *cooling* - left on *cool* and
idle all year it doesn't count, as of 2026.10.24), floor control steps aside
completely: the return
setpoint goes back to its old value once, the heat demand switch is never
touched (also not when ESS Manager stops), nothing is learned, and the
stage sensor says **cooling**. Once cooling is over it goes on in the stage
you chose (from *return setpoint* again: the heat pump's response is
measured anew).

Switching the thermostat off (mode off) means no heating in every stage:
in *full* the heat pump goes back to the thermostat until it's on again.
Going back to a lower stage, switching the select back, unloading ESS
Manager or stopping Home Assistant hands the heat pump back: the return
setpoint as it was before ESS Manager took over, heat demand as the
thermostat wants it. With steering on, the day/night temperatures and the
buffer are still written to the thermostat, so its card always shows the
wanted temperature; a change by hand counts until the next day/night switch.

## Forecast check

*(as of 2026.10.22)* How good were the forecasts, and how big does the
Safety buffer need to be? The **Forecast check** card (and the attribute
`forecast_check` on the Status sensor) answers that, once a day from the
statistics - nothing to set up.

**Household usage.** The usage forecast for any past day can be worked out
again from the statistics, so this part is complete from the first day.
Three ways of forecasting the house's usage (without heat pump and car,
which have their own forecasts) are tested on the last 8 weeks:

- the same hour on the same weekday, averaged over the lookback weeks
  (usually 6) - what the integration always did;
- the same with recent weeks weighing more (6, 5, ..., 1);
- the pattern of the lookback weeks with the level of the last week: the
  average x (last 7 days / the weekly average of the lookback weeks, which
  includes those 7 days), limited to 0.80-1.25. It's worked out fresh every
  day, not accumulated, so it fades back to 1 by itself as the average
  catches up with a changed usage - it doesn't overshoot, the way a
  correction learned from last week's error would (the higher week would
  count twice).

The best one is used for the planning, but only when it beat the plain
average by at least 5 % (daily error) over at least 14 complete days.

**Solar.** The forecast sensors keep no history, so each day's forecast is
stored at the day's first cycle and compared once the production is
measured (the solar production in the Energy dashboard). It takes a couple
of weeks to fill.

**Safety buffer advice.** Per day, the worst shortfall since midnight:
usage above the forecast and solar below it, added up hour by hour (the
car is left out - an unplanned charge session isn't something the buffer
should grow for; the heat pump counts). The advice is the smallest buffer
that would have covered 95 % of the last 28 days, between 2 and 30 %, once
14 days are measured. The sensor **Safety buffer advice** has it, with how
often the current buffer and the advice would have been enough.

**Automatic safety buffer** (switch, also on the card, off by default): the
plans use the advice instead of the Safety buffer number, approached by at
most 2 %-points a day. Until there's an advice, and whenever the switch is
off, the number is used; the number itself is never changed.

The card has three tabs: **Overview** (usage and solar against the
forecast, the buffer advice and the switch, the usage method in use),
**Per day** (the last 14 days, forecast against measured) and **Methods**
(the backtest of the three usage methods).

## Grid transport tariff

In the Netherlands grid transport is going to be charged per kWh, with a
tariff that depends on the month and the hour. It's paid on energy you
**buy**, not on energy you sell. ESS Manager therefore works with two
prices per 15-minute unit:

- **Sell price** = the price sensor's own price (the `all_price` attribute).
- **Buy price** = price + (transport tariff x factor for that unit) (the
  `all_buy_price` attribute).

Every buy decision uses the buy price: the low charge plan's window,
full-charge balancing's window, the negative price plan's trigger ("is
buying below the threshold?") and the spike plan's charge window. Every
sell decision uses the sell price: the high discharge plan, making room
before a negative price window, and the spike plan's discharge window. The
spike plan's spread is the day's highest sell price minus its lowest buy
price (so its `day_min_price` is a buy price, `day_max_price` a sell price),
and its discharge price floor is that lowest buy price plus the margin.

**The factors** (month x local hour) come with the integration in
`custom_components/ess_manager/transport_factors.json` - currently the draft
plan (winter: 0.5-0.7, 1.0 from 16:00 to 23:00; summer: 0.0 from 10:00 to
17:00, 0.3-0.7 otherwise). They're updated with the integration when the
plan changes; for a different table, fork the repository.

**The tariff** is the integration's own **Transport tariff** number entity
(on the ESS Manager device, default 0), in the same unit as your price
sensor and on the same basis (with or without VAT). At 0 the buy price is
the plain price and nothing changes; once the tariff is known, enter it
there. The Status sensor shows the value in use as `transport_tariff`.

## Installation

### Via HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MisterX-RC&repository=ESS-manager-HA&category=integration)

The button above opens ESS Manager in HACS on your own Home Assistant (and
offers to add the repository if needed). Or by hand:

1. In Home Assistant open **HACS**, click the **⋮** menu (top right) ->
   **Custom repositories**.
2. Repository: `https://github.com/MisterX-RC/ESS-manager-HA`, type
   **Integration** -> **Add**. (Once ESS Manager is in the HACS default list
   you can skip this step and just search for it.)
3. Search for **ESS Manager** in HACS -> **Download**, then restart Home
   Assistant.
4. Add the integration:

   [![Open your Home Assistant instance and start setting up ESS Manager.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=ess_manager)

   or Settings -> Devices & services -> **Add integration** -> "ESS Manager".

Updates show up in HACS like any other integration.

### Manual

Download the latest [release](https://github.com/MisterX-RC/ESS-manager-HA/releases),
copy its `custom_components/ess_manager/` folder into your Home Assistant
`config/custom_components/` folder, restart, then add the integration as in
step 4 above. You'll have to repeat this for every update.

## Configuration

The setup wizard walks through these pages:

1. **Sensors** - name, battery SOC sensor, price sensor, solar forecast
   sensor(s), grid/inverter setpoint and its polarity (optional), the
   household usage source, and a switch for full-charge balancing.
2. **Usage source** - for the Energy dashboard: shows which statistics it
   found, plus the lookback weeks; for a consumption sensor: pick the
   sensor(s), plus the lookback weeks.
3. **Full-charge balancing** - only when that switch is on: cell voltage
   differential (or lowest/highest cell voltage), battery pack voltage,
   days-since-full-charge tracking, and the full charge target voltage.
4. **Battery and system** - capacity, normal charge/discharge speed, max
   battery charge/discharge speed, charge/discharge efficiency, min/max SOC.
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

### Hidden entities

Entities that belong to something that's switched off are hidden (Home
Assistant's own "hidden" flag - they keep working and keeping their values,
and are listed on the device page under "hidden entities"):

| Switched off in Configure | Hidden |
|---|---|
| Negative price plan | Negative price status, Negative price threshold, Negative price charge speed |
| Spike arbitrage plan | Spike status, Spike margin, Spike discharge speed |
| Full-charge balancing | Next full charge in, Full charge interval, Full charge max hold, Full charge target voltage |
| Direct control ("Status sensor only") | Automatic control |

Switching one on again always shows its entities, even ones you hid
yourself. Only changes of the setting count: if you unhide an entity anyway,
it stays visible, also after a restart.

### Tunable `number` entities

Created automatically once you finish setup - find them under the ESS
Manager device in Settings -> Devices & Services -> Entities:

| Entity | What it controls |
|---|---|
| Minimum SOC (solar deficit) | Battery %, below which the low charge plan triggers while there's a solar deficit - see "Two minimum SOCs" above |
| Minimum SOC (solar surplus) | The same while there's a solar surplus; can be set close to 0. Starts at the deficit value |
| Maximum SOC | Battery %, above which the high discharge plan triggers (can be set above 100% to allow deliberate solar overshoot before discharging - the original hand-written version hardcoded this to 110% of a 30 kWh battery). Once triggered, a sale brings the forecast peak down to 100%, not just under this value, so e.g. 110% means sales of at least 10% of capacity; set below 100%, this value itself is the target |
| Battery capacity | kWh, used to convert the SOC % settings above into kWh thresholds |
| Charge speed / Discharge speed | Normal charge/discharge rate (kW) as a grid setpoint: how much is taken from / sent to the grid during a charge / sale - the house is covered out of it, the battery gets the rest up to its max speed (see Direct control) |
| Negative price charge speed | The same, during a negative-price event |
| Spike discharge speed | The same, during a spike-arbitrage discharge |
| Negative price threshold | Price (EUR/kWh) below which charging is considered "getting paid" |
| Spike margin | Minimum day price spread (EUR/kWh) to treat a day as spike-worthy |
| Minimum charge target | The smallest amount (kWh) any charge buys. Low charge plan: the dip is lifted back to the low threshold; if that needs less than this, the charge is rounded up to it (but never so far that a later peak would cross your max SOC and just be sold again). Spike plan: a pre-peak top-up smaller than this is skipped. Full-charge balancing and the negative price plan are not affected |
| Minimum charge/sale duration | The shortest charge or sale block, in minutes (15-120 in steps of 15, default 30). A charge may be split over the cheapest quarters before it's needed, a sale over the priciest ones (as of 2026.10.10), but never into blocks shorter than this |
| Safety buffer | % of battery capacity kept on top of your min SOC (default 5%), both ways. With the **Automatic safety buffer** switch on (as of 2026.10.22) the forecast check's advice is used instead - see [Forecast check](#forecast-check). Selling: a sale never brings the forecast below min SOC + buffer - e.g. min SOC 10% + buffer 5% = sales stop at 15%, so a sale doesn't end in buying energy back. Charging (as of 2026.10.4): a charge lifts the dip to min SOC + buffer, not just to min SOC, so a bit more usage or less sun than forecast doesn't take the battery just under it (when to charge still follows min SOC itself - except for the rest of a charge in several blocks whose first block has run, which counts from min SOC + buffer until its last block, as of 2026.10.13). 0 = right down to / up to min SOC |
| Transport tariff | Base grid transport tariff (EUR/kWh, default 0): buying costs price + (tariff x factor for that hour), selling doesn't - see "Grid transport tariff" above. 0 = no transport |
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
instead), and what a charge or sale really moves in and out of the
battery: the speeds above are grid setpoints, the battery side is capped
at these (as of 2026.10.27). They don't limit the setpoint that is sent -
set the inverter's own limits (e.g. Victron DVCC max charge current) to
protect the battery.

**Charge efficiency** and **discharge efficiency** (%, default 100 = no
losses) are set the same way. They account for the inverter and battery
losses in the battery forecast and in every plan: at 90% charge
efficiency, 2.0 kWh of solar or grid power puts 1.8 kWh into the battery;
at 90% discharge efficiency, 0.5 kWh of usage (or of a sale) takes
0.5 / 0.9 = 0.56 kWh out of it. Charge and sale windows are sized for what
actually reaches or leaves the battery; the setpoint that's sent stays the
configured (grid-side) speed.

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
during this same wait). `Solar export` and `Grid usage` are labels only
(the setpoint stays at idle): `Solar export` means there's solar left over
now, the battery is forecast to reach 100% later today, and the price now
is higher than every price until then - exporting now pays more than
storing (and in a negative price plan, solar going to the grid before the
negative window); `Grid usage` means a charge is planned and the
battery is within 1 kWh of the low threshold, waiting for that window.
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
entity's own min/max. The speeds are **grid setpoints** (as of
2026.10.27): what the inverter takes from (or sends to) the grid. The
house is covered out of it and the battery gets the rest, but never more
than its max charge/discharge speed - the inverter limits that by itself,
and the plans count with it. So a Charge speed above the battery's max
charges the battery at its max and keeps the house on the grid too (the
battery fills faster than with a setpoint at the max, which the house
would share); a Charge speed below it is a gentler charge, which the
house shares. (Up to 2026.10.26 the setpoint was cut down to the max
battery speed, and the sales were sized at the full Discharge speed even
when the battery couldn't deliver it.) Every
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

**Night limit** (as of 2026.10.18): on the battery page in Configure,
"Limit the charge/discharge speed at night (22:00-07:00)" asks for a night
charge and a night discharge speed. Between 22:00 and 07:00 those limit
every other speed - normal, negative-price, spike and full charge: a speed
above the night speed is lowered to it, a lower one stays as it is (as of
2026.10.27; up to then the night speeds replaced the others, also when they
were higher). The charge plans count with that speed for those quarters (so
a charge at night gets a longer window; 0 means no grid charging at night),
and a sale is worked out per quarter too - at the average of the night
speed in its night quarters and its own speed in the others, so a block
across 07:00 or 22:00 plans exactly what is sent. The setpoint switches by
itself at 07:00 and 22:00 (also in the middle of a running block). Like
the other speeds, the night speeds are grid setpoints: the battery side
stays within its max speeds.
Outside those hours nothing changes. Shown on the Status sensor as
`night_limit` (enabled, active now, the speeds).

Safety:

- **Automatic control** switch (an entity on the device): turn it off to
  take over by hand - it sends idle once, then leaves the target alone
  until you turn it back on. Its state survives restarts; on by default.
  While direct control isn't set up ("Status sensor only"), the switch is
  hidden (it has nothing to control); choosing a number / input_number
  entity in Configure shows it again - see "Hidden entities" under
  Configuration.
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
  that doesn't exist is not, and says so in `last_error` (as of 2026.10.18).

**Planned setpoint** (a sensor, kW, positive = charge) and the Status
sensor's `control_action` / `control` attributes show what would be sent -
also while direct control is off. That's the easy way to switch over:
leave control on "Status sensor only", compare Planned setpoint with what
your automation does for a few days, then choose direct control and
**disable your own ESS automation** so the two don't fight over the
setpoint.

If you leave the grid/inverter setpoint on the first page empty, the
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
starts. For the whole hold the battery is told to charge, so household
loads can't erode the SOC while the cells finish balancing, even when solar
alone is what's holding the battery full. `Status` reports it like the
charging phase: `Start charge` until the setpoint readback shows the charge
applied, then `Actief` (up to v0.5.10 it said `Start charge` for the whole
hold). Your automation reacts to `Start charge` and sets the setpoint;
should it drop away mid-hold, the Status goes back to `Start charge` and
the automation sets it again. The **Battery action** sensor says
`balancing` during the hold. Once the three conditions above are satisfied
(or the "Full charge max hold" safety timeout elapses first), the setpoint
is released back to idle.

A hold that times out without ever confirming balance does **not**
immediately force another hold attempt - it falls back to the normal flow:
if there's a genuine future point where solar is forecast to push the
battery back into overshoot, the plan quietly waits for that; if not, the
charging logic schedules a fresh grid-charge session at the cheapest
available window to complete the balance.

A grid-charge session for a full charge can be split over the cheapest
quarters before it's needed, in blocks; the cards and the Charge amount
sensor show the block that's planned or running, and the rest is planned
again after it. A session is worked out afresh when the capacity or max
SOC it was sized against changes, and a stored session ends at its own end
time (as of 2026.10.14).

## Problem notices

*(as of 2026.10.23)* When something keeps the integration from doing its
job, a notice appears in **Settings > Repairs** - and goes away by itself
once the problem is over. A problem has to last a while first, so a sensor
that's briefly gone after a restart doesn't raise one:

| Notice | When | After |
|---|---|---|
| The setpoint can't be sent | direct control is on, but the target entity doesn't exist, is unavailable or the service call fails - the battery isn't steered meanwhile | 5 minutes |
| Planning paused - a sensor has no value | the battery SOC sensor has no number, or the price sensor is unavailable / has no prices for today - nothing is planned and direct control keeps the battery idle | 15 minutes |
| A solar forecast sensor can't be read | a chosen solar forecast sensor is available but has neither a Solcast `detailedHourly` nor a Helios Forecast `forecast` attribute - it would count as no sun (an attribute that's just empty for now is fine) | 15 minutes |
| Battery expected below its minimum | even with the plans, the battery is expected to run into a dip below its minimum within the next 24 hours that have prices and lie within the planning horizon - usually a charge that can't be fitted (charge speed, night limit, too little room) | 30 minutes |

What's going on right now (also before it becomes a notice) is in the
diagnostics download under `problems`. Unloading or removing the
integration clears its notices.

## Diagnostics

*(as of 2026.10.22)* Settings > Devices & services > ESS Manager > the
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

ESS Manager stores no passwords or tokens, so nothing is blanked out; the
file does contain your energy data and entity names - share it with whom
you choose.

## Dashboard

The integration brings its own dashboard cards. After installing (and a
browser refresh), edit a dashboard, choose **Add card** and search for
**ESS Manager**:

| Card | Shows |
|---|---|
| ESS Manager - Battery forecast (`custom:ess-manager-battery-card`) | five whole days: the measured and the expected battery level, solar, usage, the planned buy / sell moments and how long you'd last without the grid |
| ESS Manager - Prices (`custom:ess-manager-price-card`) | today's and tomorrow's prices coloured by price level, with the planned buy / sell moments |
| ESS Manager - Status (`custom:ess-manager-status-card`) | the planned sale and charge with their progress, the price plans, the control toggle and a timeline |
| ESS Manager - Electric car (`custom:ess-manager-ev-card`) | the electric car's charging sessions in the planning: check, edit or add them (only with the electric car switched on, see [Electric car](#electric-car)) |
| ESS Manager - Heat pump (`custom:ess-manager-heatpump-card`) | the heat pump forecast from the weather: the coming days, the energy signature and what the model has learned (only with the heat pump switched on, see [Heat pump](#heat-pump)) |
| ESS Manager - Forecast check (`custom:ess-manager-forecast-card`) | how good the usage and solar forecasts were, which usage forecast is in use and the Safety buffer advice, with the "adjust automatically" switch (see [Forecast check](#forecast-check)) |

All of them are drawn by the integration itself - nothing else to install
(since v0.5.1 also not apexcharts-card). The integration loads the card
file on every page and also adds it as a dashboard resource
(`/ess_manager/ess-manager-cards.js?v=<version>&resource=1`, under
Settings > Dashboards > Resources), kept on the current version and removed
again with the last installation. Its URL deliberately differs from the
file loaded on every page: a browser remembers a module that failed to load
under its URL until the page is reloaded. That resource is what keeps the cards from showing
"Configuration error" when the app starts without a connection yet (e.g.
the iOS app coming back from the background) - with dashboards whose
resources are set in YAML, add it there yourself as a JavaScript module
(`url: /ess_manager/ess-manager-cards.js?resource=1`, `type: module` - with
something after the `?`, so it differs from the file loaded on every page). Each card only asks for the
installation's **Status** sensor (picked automatically when there's one);
it finds the other sensors itself. In YAML:

```yaml
type: custom:ess-manager-price-card
entity: sensor.home_status
```

The cards are updated together with the integration. Texts follow your
Home Assistant language (Dutch or English, English for any other
language); times, numbers and the currency follow Home Assistant's
language, region and time zone settings.

**Battery forecast card.** Always whole days from today 00:00 - five by
default. Left of the white "now" line (slightly dimmed) what happened:
the battery level from your SOC sensor's history, coloured by what the
**Battery action** sensor says the battery did, and today's measured solar
and household usage (the Status sensor's `history_today` attribute: the
usage from the same statistics as the usage forecast; the solar from the
Energy dashboard's solar statistics, or the solar forecast for those hours
when the usage comes from a consumption meter). Right of it what's
expected:

- the battery level with the plans in it (`battery_forecast_adjusted`):
  green, red during a sale, blue during a charge, intense red / blue for a
  spike sale / negative price charge, with a label at each planned moment.
  It never goes above 100% (as of 2026.10.1): what solar would add on top
  goes to the grid, so after a full day the line drains from 100%;
- a thin dotted line: the battery level without any plan
  (`battery_forecast`, solar minus usage only), not cut off at the min /
  max SOC;
- the solar forecast (yellow) and the usage forecast (grey line);
- the band between your minimum and maximum SOC (the minimum that applies
  now - solar deficit or surplus - see "Two minimum SOCs" above);
- the stretch from now to the **planning horizon** (the Planning horizon
  number - what the plans cover) a little brighter, everything after it
  dimmed.

Top right: the battery level now (% and kWh) and **without grid**: when
the forecast without plans runs empty ("without grid: empty Wed 06:15",
with an orange ring on the 0 % line) or full ("full Sat 13:30", a yellow
ring on the 100 % line) - the nearest one, the same rule as the solar
mode - or "5+ days" when neither happens within the forecast. Below the
chart one tile per day, right under its day label (today's slightly
lighter): the solar and usage in kWh (today: measured + expected) and, as
a slim vertical bar beside them, the lowest - highest battery level that
day on a 0 - 100 % scale (hover a tile for the numbers). Tap the chart
(or hover with a mouse) for the values at that hour: battery level, without
plans, solar, usage and the price; tap the same spot again to close.

| Option | Default | What it does |
|---|---|---|
| `title` | Battery forecast | the card's title |
| `days` | `5` | how many whole days (1 - 5) |
| `height` | `210` | chart height in px |
| `show_days` | `true` | the day tiles |
| `show_outlook` | `true` | the "without grid" line and its ring |
| `show_raw` | `true` | the dotted line without plans |
| `show_solar` / `show_usage` | `true` | solar / usage (chart, tiles, tap values) |
| `soc_color` / `solar_color` / `usage_color` | green / yellow / grey | colours (`[r, g, b]` or `"#rrggbb"`) |
| `sell_color` / `buy_color` | red / blue | the colours of a sale / charge |

**Price card.** Always two whole days: today and tomorrow (that half
stays empty until tomorrow's prices are published), as bars coloured by price level: a gradient from cheap (green) via average
to expensive (orange), negative prices in turquoise. The planned buy and
sell moments (the same as the status card's blocks) keep their full
colour, with a light column and a line under it in the plan's colour and
a label ("Sell 19:15", "Negative price 13:00"); the other bars are dimmed.
Everything before "now" sits under a darker layer; the plans that ran
today (from the Battery action history - "Charged 03:00", "Sold 19:15")
still show in it. The dotted line is the buy price (with transport - only
when a transport tariff is set, otherwise it equals the price). Top:
the price now, the buy price, and the cheapest and most expensive moment
still to come. Tap (or hover) for the price of a quarter.

**Solar surplus** (yellow column and line, "Solar surplus 14:15" - or
just a sun at the top where the label doesn't fit next to another one): the
hours the forecast expects solar to go to the grid, because the battery is
full (at 100% - with a max SOC above 100% it isn't sold off first) or
because there's more solar than the battery can charge (above your max
battery charge speed). Tap it for the reason and roughly how many kWh go
to the grid. From the Status sensor's `solar_surplus` attribute.

| Option | Default | What it does |
|---|---|---|
| `title` | Electricity price | the card's title |
| `height` | `170` | chart height in px |
| `show_extremes` | `true` | cheapest / most expensive at the top |
| `show_buy_line` | `true` | the dotted buy price line (only drawn when a transport tariff makes it differ from the price) |
| `legend` | `true` | the legend under the chart |
| `cheap_color` / `mid_color` / `high_color` / `negative_color` | green / yellow / orange / turquoise | the price level colours |
| `sell_color` / `buy_color` | red / blue | the colours of a planned sale / charge |
| `surplus_color` | yellow | the colour of the solar surplus |

Options from before v0.5.1 (`show_<item>`, `legend_<item>`, `labels_<item>`
and so on) are ignored - they belonged to the apexcharts version.

**Status card.** At the top the title, the Status and a toggle for the
control (the integration's **Automatic control** switch when it controls
the battery itself, otherwise the automation you choose in the card's
options; hover it for its name) and next to it **Settings**, which opens
the ESS Manager device page with all its numbers, switches and sensors
(written out when there's room, just the cog on a narrow card; only shown
to admins). Below, two blocks side by side: **Sell**
on the left, **Buy** on the right. Each shows the start (with the day when
it hasn't started yet) and stop time, a bar with the duration and - once
the window runs - how far it is, measured on the energy (it fills as the
battery moves towards the plan's target, and says how long is left; hover
it for the kWh done), the energy (kWh) and the target battery level (SOC
expected after it). An active spike or negative price plan shows in the
block it drives, with a chip and an outline in that plan's colour (a spike
drives both blocks: the cheap charge and the sale in the peak); full-charge
balancing gets a chip too. While the battery waits at 100% for the cells to
balance, the Buy block turns lilac: the bar runs from the start of the wait
to the "Full charge max hold" timeout ("max 1 h 20 min" left), and below it
the cell voltage difference against the goal ("18 mV → < 10 mV", green
once below; hover it for the battery voltage against the target voltage).
Below the blocks: the spike and negative price
plan status and a slim timeline of the last hours - calm blue / red for
normal charging / discharging, intense blue / red for the faster negative
price charge / spike discharge, lilac for balancing, dark grey for idle
(following the card's Sell / Buy colours). The timeline comes from
the **Battery action** sensor (`idle`, `charge`, `discharge`,
`negative_price_charge`, `spike_discharge`, `balancing`). Texts follow your Home
Assistant language (Dutch or English).

| Option | Default | What it does |
|---|---|---|
| `title` | `ESS Manager` | the card's title |
| `automation` | - | your own ESS automation (or `input_boolean` / `switch`) for the toggle, when the integration doesn't control the battery itself |
| `show_history` | `true` | show the timeline |
| `hours` | `24` | how many hours the timeline shows |
| `sell_color` / `buy_color` | red / blue | the Sell / Buy colours (`[r, g, b]` or `"#rrggbb"`) - the timeline follows them too (a darker shade for a normal charge / discharge, the colour itself for a negative price charge / spike discharge) |
| `spike_color` / `negative_color` | amber / turquoise | the colour of an active spike / negative price plan |

**Electric car card.** The car's charging sessions for today and the next
four days (see [Electric car](#electric-car)), with the total that's in the
planning. Each session shows its day, start and expected end, its energy,
a chip - **average** (predicted from history), **edited** or **manual** -
the car and how it charges (the power, or solar surplus); with a car with a
battery size a bar from the start to the target SOC. A checkbox per session
decides whether it counts in the planning (unticked it stays in the list,
struck through). A solar session predicted from history has a **red
border**: whether it charges depends on the sun. A running session is
outlined and shows "charging now", the live power and how far it is. A
solar session that won't get (all of) its energy that day says so in
orange.

Tap a session to edit it in the block at the bottom: the car (with more
than one), the day and the start hour (fixed while it's running, with a
lock), the start and target SOC (with a battery size - the dashed line is
the start SOC the history expects) or the energy, and **Fixed current**
(a slider between your minimum and maximum current, with the power) or
**Solar surplus**. Below it what that gives: when it's done, how long it
takes and the kWh in the planning, or a warning for a solar session. **Save**
stores it (the chip becomes "edited"), **Back to average** drops the edit
of a predicted session, **Delete** removes a manual one. **Add manual
session** opens an empty block (the next whole hour, your maximum current).

| Option | Default | What it does |
|---|---|---|
| `title` | the car's name with one car, otherwise `Electric cars` | the card's title |
| `ev_color` / `solar_color` | green / yellow | the car colour (fixed current) and the solar colour |

**Heat pump card.** At the top the model's state (active, still learning,
summer, not used) and the heat pump's total for the next five days - while
the model doesn't forecast, the 6-week average it falls back to. A notice
below it when there's something to tell: the learning progress in heating
days, "no heating in the coming days" in summer, why the model isn't used,
or a correction (the last days used more or less than the model said, with
the thermostat change when a wanted temperature is set). With the house
warmer or colder than usual a second notice says so: "House 1.9 °C warmer
than usual at this time: expected to heat again from 02:00 (1.0 kWh less)",
or the kWh extra to warm it up. Three tabs:

- **Forecast** (open by default): each day with its temperature, wind,
  direction and sun, a bar with the model's energy and a marker for what
  the 6-week average would say.
- **Signature**: every measured day against the (smoothed) outdoor
  temperature - fainter is older - with the model's line at the usual wind
  and sun and the coming days as rings; below it the model's figures:
  balance temperature (at which indoor temperature, with indoor data), kWh
  per degree colder, a degree warmer inside (with indoor data), the daily
  base, wind, sun,
  cooling (with cooling data) and its error over the last 14 days; with the
  house's cooling learned also the heat it holds (kWh per °C indoor) and how
  fast it cools (°C per hour at 10 °C difference, its time constant, and how
  long the floor keeps giving heat when that's longer than 3 hours).
- **Memory**: per temperature class of 2.5 °C the number of days, the
  measured and the model's mean, and the newest day in it.
- **Indoor** (with step 1): the measured indoor temperature of the last 24
  hours, the expected one for the next 48 with the target (dashed) and the
  heating per hour (bars: the measured heating electricity of the last 24
  hours solid, the expected one lighter - as of 2026.10.23, with heating
  meters chosen); the model's stage (learning, watching along,
  used, steering) with its self-check's figures; the buffer plan (warmer /
  cooler when, what it saves); COP at 7 and −2 °C, the floor's delay, the
  heat-up per 10 kWh. With step 2 the steering switch and the day/night
  temperatures, their hours and the buffer range, with − and + buttons.

| Option | Default | What it does |
|---|---|---|
| `title` | `Heat pump` | the card's title |
| `hp_color` | orange | the heat pump colour |

`dashboard/` still has the old chart cards as plain apexcharts-card YAML
and the old status card (`entities_card.yaml`), for when you'd rather
build your own: each file's header comment explains which placeholder
entity_ids to replace with your own. The built-in cards no longer use
them.

## What changed vs. the original hand-written version

This is a full rewrite (Jinja2 template sensor -> Python custom
integration), not a mechanical export, so a few things were deliberately
generalized for portability - documented here so nothing is a surprise if
you're the one who ran the original on a live system:

- **Every entity reference is configurable** - the original hardcoded
  Victron/Nordpool/Solcast entity IDs; this version only assumes the
  *shape* of data described under Requirements above.
- **The household usage forecast is calculated internally**, with no
  external SQL sensor - see "Household usage forecast" above. It also
  fixes a flagged correctness issue in the original's MySQL-specific SQL
  sensor (a week with missing data was silently averaged in as a 0 instead
  of being excluded).
- **Min/max SOC are direct % tunables**, not derived from an external
  "inverter's own minimum SOC" sensor plus a hardcoded margin. If you want
  that margin back, just set Minimum SOC a few points above your inverter's
  own floor.
- **Capacity is a tunable**, not hardcoded to 30 kWh, and the dashboard
  cards read it live from the sensor rather than a hardcoded constant.
- **Idle setpoint tolerance** is generalized to 0W (the original's -30W was
  a quirk of one specific Victron install's idle reading).
- **Plan state survives Home Assistant restarts** (persisted via
  Home Assistant's storage helper; since 2026.10.14 the first cycle after a
  restart checks running windows again against the current settings, and
  the balancing wait carries on) - the original template sensor's
  self-referencing `this.attributes` lookups would silently reset on
  restart. This is an intentional improvement, not a bug-for-bug port.
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
  timing, days to next full charge) are their own entities.

The exact YAML this was ported from (the heavily-commented Jinja2 source
and the original project notes) is in the git history up to v0.2.20.

## Repository layout

```
custom_components/ess_manager/   the integration itself (frontend/ = its dashboard cards)
dashboard/                       the old dashboard cards as YAML + example automation (not needed with direct control)
tools/build_cards.py             builds frontend/ess-manager-cards.js from tools/cards_template.js
docs/images/                     screenshots used in this README
tests/                           standalone tests (no Home Assistant needed)
.github/workflows/validate.yaml  HACS + hassfest validation on every push
LICENSE                          MIT
```

## Versioning

Versions are **year.month.release**, like Home Assistant's own: the year
and month the release is made, then a number counting the releases in that
month from 0 - `2026.10.0`, `2026.10.1`, ..., then `2026.11.0`. Every push
gets a new one in `custom_components/ess_manager/manifest.json` - see
`CHANGELOG.md` for what changed at each version (up to 0.5.13 versions went
up by 0.0.1). This is what lets HACS tell installed instances an update
exists: it compares the tag on your most recent GitHub Release against
whatever version they currently have installed - note that this means an
actual GitHub *Release*, not just a git tag; HACS's own docs are explicit
that "just publishing tags is not enough, you need to publish releases,"
and without any release at all it falls back to tracking raw commits on
the default branch instead.

Every version gets a GitHub Release tagged `v<version>` (e.g.
`v2026.10.0`) whose notes are that
version's own section of `CHANGELOG.md`, so HACS's update dialog shows what
actually changed. HACS re-checks custom repositories roughly every 6 hours and
at Home Assistant startup; to see an update right after syncing instead of
waiting, use HACS's own repository menu -> "Redownload" or "Update
information."

## License

MIT - see [LICENSE](LICENSE).
