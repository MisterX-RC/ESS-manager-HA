# Battery planning

How ESS Manager decides when to charge, sell, hold or take the house from the grid: the planning engines, the forecasts they work on, the household usage forecast, the forecast check and full-charge balancing.

[← Back to the README](../README.md)

## The plans

The planning engines are documented in
detail in the code (`custom_components/ess_manager/plans.py`):

1. **Low charge plan** - charges before the battery would otherwise drop
   below your minimum SOC, in the cheapest quarters before it's needed -
   just what's missing to keep the dip at the minimum SOC plus the
   **Safety buffer** (rounded up to the **Minimum charge target**), not a
   full battery. A charge split over several blocks is finished: once its
   first block has run, the rest still counts up to minimum SOC + buffer
   (not just minimum SOC) until the last planned block, so it isn't dropped
   just because the first block already lifted the dip above the minimum.
   A charge aims at the **lowest point of the planning horizon**, not just the first dip: every later dip gets
   its part before its own hours, in the cheapest quarters (what the first
   dip needs before the first dip, the rest before the lowest point), and
   only as much as fits under 100% before it - a sunny day that fills the
   battery in between moves that part to after it. The battery is kept
   higher all along (more left in a power cut), and a later dip can wait
   for a cheaper valley because the level is already higher. A dip below
   the surplus minimum is always met; the plan shows `lowest_kwh` and
   `horizon_target_kwh`. What's needed after the end of the known prices
   isn't left until they come in: it's bought now, before that end, as far as it fits under 100% - so a battery that
   only drains for days (little sun, cars to charge) is topped up a bit
   more every day instead of getting just enough to reach midnight. Those
   not-yet-urgent parts (and every other part only needed "where it fits")
   only go in quarters at most the **average buy price of the known
   quarters**, and a block of only such parts that would have to be
   lengthened to the Minimum charge duration into dearer quarters is left
   out - a charge is never stretched into the expensive hours for them.
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
   overflow, at its best price (the Status attribute
   `high_discharge_plan.overflow_to_grid` lists what was left to the grid).
   An expensive morning before a cheap midday overflow is still sold in
   the morning.
3. **Full charge plan** *(optional)* - periodically charges all the way to
   100% and holds there briefly to let the BMS balance cells, on a
   configurable interval. With a slow charger it's spread over several
   sessions (each at most four hours at the charge speed, or 30x the
   average hourly usage when that's more); the status card's Buy block
   shows the session - its energy over all its blocks and the level it
   ends at. While it's charging or balancing it comes first. While it's
   only **scheduled** it doesn't hold the other plans back: the low
   charge plan counts the full charge's quarters (it only buys what the
   full charge doesn't bring in in time, and never in the same quarters),
   and a low charge, negative price or spike plan whose window is now goes
   ahead - the status says `Full charge scheduled` only when nothing else
   is going on. A sale
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
6. **The house from the grid at low prices** *(optional)*
   - every kWh put into the battery and taken out again loses something
   (charge x discharge efficiency, e.g. 90% x 90% = 81%). With flat prices
   that means charging and then using the battery at about the same price
   only costs money. With this plan on, the low charge plan has two ways
   to cover a need: a **charge** (costs the price / charge efficiency per
   kWh into the battery) or **taking the house from the grid** in a quarter
   instead of from the battery (costs the price x discharge efficiency per
   kWh that stays in the battery - no losses). Both go in the same
   cheapest-first choice, so on a flat day it's: the house from the grid,
   then a charge in the really cheapest stretch, then the grid again while
   the price is still low enough. Rules: the house only comes from the grid
   **below the lowest known price after the losses** (lowest price /
   (charge x discharge efficiency): with 0.21 and 81%, up to 0.26) -
   except for a **hard** part (the floor, or the
   minimum without a surplus minimum, that has to be met by a certain
   hour): that one may take the house from the grid in any quarter before
   its deadline, also an expensive one, since in the same quarter that
   always beats a charge. A battery about to hit the floor before the cheap
   hours then has the house taken from the grid in the cheapest quarters
   left before it (the dearest skipped) instead of being charged in the
   morning peak; only
   when there **is** a charge need (a solar deficit - with enough sun in the
   planning window nothing is taken from the grid); never so the battery
   would go **over 100%** later (a peak of 97% in 4 hours leaves 3% to take
   from the grid, in the cheapest quarters); a quarter is a charge or from
   the grid, not both (a charge covers the house anyway), and a quarter from
   the grid can still become a charge when that's cheaper. Solar left over
   still goes into the battery. A short solar gap (up to an hour) between
   two such quarters comes along: a 15-minute forecast average can hide a
   peak above the sun. With a shortfall to plan for
   (a charge is triggered), **every** quarter at or below that price limit
   is taken from the grid - also where no requirement needs it, and where
   the sun is forecast to cover the house (at 0 kWh) - as long as the
   battery stays under the top in every later hour (the cheapest first):
   an unplanned load or a peak (the washing machine) or less sun than
   forecast then comes from the grid at that low price instead of out of
   the battery; a real surplus still charges it. No shortfall, nothing from
   the grid. In a **solar deficit** (the sun alone
   doesn't fill the battery) that check is made with the battery stopping at
   100%: a planned charge that would go over the top doesn't count its
   overshoot in every later hour. And a quarter after which the battery does
   reach the top still goes from the grid when a planned charge lies between
   it and that moment - the charge then simply needs less (it stops at its
   target). Without a charge in between, what's kept in the battery would go
   to the grid later, so there it stays out. In a surplus it isn't capped.
   **A reference price from the last week** while
   tomorrow's prices aren't known yet: until they are, the planner only sees the
   rest of today, and on a day that is dear as a whole "the cheapest quarter
   left today" is itself dear - the house would be taken from the grid and the
   battery topped up at prices well above what a charge normally costs. The
   reference is what a charge usually cost: per day the average buy price of
   its **6 cheapest hours**, and of the last **7 days** the **median** (at
   least 3 days; one day with very low or negative prices doesn't drag it
   along). While it applies, the house only comes from the grid below
   min(lowest known price, reference) / (charge x discharge efficiency), and
   what is needed **after** the known prices is only bought at or below the
   reference - the rest waits for tomorrow's prices, and once those are in
   the plan is made over today and tomorrow. It only applies
   while no prices after today are known, **before 18:00** and when the
   battery doesn't drop below the low threshold within **12 hours** (the
   safety net: otherwise it plans in the cheapest quarters left today). **Hard** parts (below the threshold before the end of the known
   prices) are never held back by it. The day prices come from those the
   savings card keeps (the last 14 days; days missing are read from the
   recorder). The `price_reference` attribute shows the price, whether it
   applies (`reason`: `active`, `tomorrow_known`, `after_18`, `empty_soon`,
   `too_few_days`) and the value per day. No setting.
   A quarter that started from the grid is finished that way, like a
   running charge window - unless a charge takes it over - so with the
   battery nearly full and the sun filling it to the top later on, it
   doesn't flip between the grid and the battery every minute or two. Meanwhile the Status is **House from grid** and, with
   direct control, the grid setpoint follows the battery's measured power
   **every 15 seconds** (a fast loop that only does this - the rest of the
   cycle stays once a minute): the last setpoint plus 60% of what the
   battery discharges (minus what it charges), so it settles where the
   battery is at 0 W in a few steps without overshooting - never below the
   idle value, a car or a kettle included, back to idle by itself when the
   sun comes out (±30 W counts as 0; without a power reading: idle). The
   setpoint entity's own `step` is taken into account: a
   coarse one (say whole kW) gets a dead band of half a step, at least one
   whole step per correction and values rounded to its step, so it settles
   on the nearest step instead of jumping between two (the battery then
   stays within half a step of 0); a fine one (W) is followed directly. The forecast keeps that energy in the
   battery. The cards show it in purple: on the price
   chart as blocks labelled "From the grid", on the battery chart the
   forecast line in that colour with a label for stretches of 45 minutes
   or more (blocks of the same kind less than three hours apart share one
   label, "+2"; a label that would overlap another is left out) and a line
   in the hover tooltip ("House from the grid
   23:15-08:00 · ~1.2 kWh"); afterwards both charts show when it ran (the
   Battery action `grid_use`).
   Switched on on the price plans page in Configure. The battery's power
   sensor and its direction are on the battery page (also used by solar
   export); when it's still empty there, a page for it follows the switch.

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
battery is then expected to hold at the peak.

**Charging in the cheapest quarters, each part before it's needed**.
The low charge and full charge plans don't look for one long
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
the way that leaves the cheapest plan. A block also stops lower when the
sun after it - before the next block - would take the battery over 100%:
it keeps its quarters, so its minimum length, but stops
earlier on its level, and the sun fills the battery to the top instead of
going to the grid. Never so low that an hour in between drops under min SOC
plus the Safety buffer. That check counts the high side of the solar
forecast (Helios Forecast's p90, Solcast's
pv_estimate90) instead of the forecast itself, so the block leaves room for
a sunnier afternoon than expected (the floor check stays on the forecast;
the current hour and hours without a band count the forecast). After such a
block the battery can end a little under 100% on an ordinary day; on a
sunny one the room is filled by the sun instead of exported. A later block
only ends the hours looked at when it still has room to fill. The high
side per hour is in the diagnostics (`solar_120h_p90`).

**Selling in the priciest quarters too**. A sale isn't
one window either: it goes into the priciest quarters before the moment
it's needed, possibly in several blocks of at least the same **Minimum
charge/sale duration**. Each quarter is only used as far as the forecast
stays at or above your minimum SOC + Safety buffer from then on, so a sale
that can't go all at once before a low point (say tonight's 19:30 peak,
with a low point at 07:00) sells what fits there and the rest after that
low point - instead of either selling less, or all of it at the cheaper
moment. The first block is the plan's window, like a charge.

**Charging with the sun in mind**. The battery takes at
most your **max battery charge speed**. In a sunny hour the sun already
charges it, so a grid charge can only add what's left up to that max -
nothing at all when the sun alone fills it (say a 1.8 kW charger with
2.5 kW of sun and 0.4 kW of house use). The charge plans (low charge, full
charge, spike top-up, negative price charge) work out per quarter what the
grid really adds: the sun only makes a window longer - quarters it already
fills add nothing, so the window runs on until the amount is in - and the
cheapest window is still chosen, costed on what's really bought.
What's bought is what the grid can really deliver during a
charge: the house's shortfall plus what the battery still takes up to its
max (after the sun), never more than the Charge speed - nothing is counted
as sold back. A Charge speed well above the battery's max (so that without
sun the inverter charges at its max and the house is covered on top)
doesn't make charge quarters look dearer: a cheap midday dip is costed
at its own price and chosen. A
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
with. A (re)start of Home Assistant or the integration does it too,
so a window stored before the restart is checked against the
current settings and forecast. When a sensor it needs (battery SOC, price)
isn't there yet right after a restart, the entities are unavailable until
the next cycle (once a minute) finds it - no reload needed. For the first 10
minutes after a start it also waits for the solar forecast sensor(s) and the
household usage statistics, so it never plans with "no sun" or "no usage"
just because those weren't loaded yet; after that it plans with what there
is. The full-charge balancing wait at 100% is
never interrupted by it.

All plans build on a 121-hour (5-day) forecast pipeline: solar
forecast minus usage forecast, cumulatively summed into a projected battery
level, compensated for the fact that the current hour is only partially
elapsed (see the code comments in `forecasting.py` for why that matters).

**Two forecasts at the top: clipped and not.** The running sum of solar
minus usage has no top - on a sunny day it can "fill" the battery to 106%.
In reality the battery stops at 100% and the rest goes to the grid. So
 the charge plan, the negative price and spike plans and
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
mode simply stays what it was. The mode is stored, so a restart or an update keeps it too; a
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
  charged in the cheapest window before its lowest point (after it, a
  charge would no longer lift anything) - just what's missing (rounded up to the **Minimum charge target**), and
  never more than still fits under 100% at the forecast peaks after the
  charge (a peak before it, like this afternoon's for a charge tomorrow,
  doesn't count - the window goes after it), so nothing
  bought now is lost again on a later solar day that fills the battery. If
  less than the Minimum charge target fits, it isn't charged now; the
  deficit minimum is picked up again once that peak is behind it. A dip in
  the band that's at its lowest right now (the sun lifts it on its own)
  needs no charge.

A charge for a dip below the surplus minimum buys what's missing up to
the surplus minimum plus the band part that fits. A charge never fills the
battery to 100% just because it charges (that's the full charge plan's job).

By default the integration only decides: its `Status` sensor says what
should happen and your own automation acts on it - see [Wiring it to your inverter](control.md#wiring-it-to-your-inverter). Optionally it sends the setpoint itself - see [Direct control](control.md#direct-control).

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

## Forecast check

 How good were the forecasts, and how big does the
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

 A day counts as soon as it's measured completely and
the plain average can be made for it (one week of history is enough). The
level method needs 90 % of the lookback weeks before the day complete in
the statistics (with 6 weeks: about 6 weeks); on days where it can't be
made it just sits that day out. It's only chosen with at least 14 days of
its own, compared with the average on the days both have. So with a young
history (a new installation, a battery or meter added recently to the
Energy dashboard) the usage days show up after about a week, and the
level method joins in later.

**Short-term correction**. The usage forecast is a
weekly pattern: a load that started a few days ago (or a house left empty)
only shows in it after weeks, and the level method above is a day factor.
So every hour the last **3 complete hours** are measured against what was
forecast for them (the same identity, heat pump and car left out like the
forecast does), and the **difference per hour** goes onto the coming
hours, **fading out over 6 hours**: in full this hour, half in the 3rd,
nothing from the 6th on. A difference, not a factor: an extra load that
keeps running adds the same kWh to a quiet hour as to a peak. Only when
it's clear - at least 0.3 kWh off over the 3 hours together - and both
ways (less used than forecast lowers it, never below 0). Nothing to set.
After a restart it waits for 3 hours of its own. The attribute
`usage_correction` on the Status sensor (and the diagnostics) shows the
difference, the 3 hours (forecast and measured) and what was added to the
next 6. The forecast check above still judges the pattern itself, without
this correction.

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
applied, then `Actief`. Your automation reacts to `Start charge` and sets the setpoint;
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

A grid-charge session for a full charge is planned
**together with its balancing wait**: one stretch of charge quarters with
the "Full charge max hold" right after it - a charge of 1 hour with a
2-hour hold needs a 3-hour stretch. The stretch is chosen on the charge at
the buy price plus the house's usage over the hold at the buy price (the
battery is held full then, the house runs on the grid), so the hold doesn't
land in the evening peak just because the cheapest charge quarter came
right before it. The session is planned half an hour
longer for the slower last part (within the known prices: a session that
charges up to the last known price ends there), and a session whose window runs out at
95 % or more charges on to full (at most an hour) before the balancing
wait starts. The Buy block on the card says until when it balances at
the latest, and the forecast holds the battery at 100 % over it. A session is worked out afresh when the capacity or max
SOC it was sized against changes, and a stored session ends at its own end
time.
