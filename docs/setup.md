# Requirements, installation and configuration

What your Home Assistant needs, how to install, every setting in Configure and the tunable numbers.

[← Back to the README](../README.md)

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
  quarter the same way. With `raw_today` / `raw_tomorrow` (start times,
  as the Nordpool HACS integration has) a list of the wrong day is
  recognised; the last good lists are kept for when the sensor drops out
  (see [Control](control.md#problem-notices)).
- **Household usage forecast**: nothing extra if your Home Assistant
  Energy dashboard is set up (at least a grid source) - the integration
  calculates the forecast itself from the statistics the Energy dashboard
  already uses. Alternatively, a sensor reporting your home's total energy
  consumption (cumulative kWh). See [Household usage forecast](battery-planning.md#household-usage-forecast).
- **Solar forecast**: one or more sensors in either of two formats - the
  integration recognises which one each sensor has by itself:
  - **Solcast**: a `detailedHourly` attribute, a list of
    `{"period_start": <ISO timestamp>, "pv_estimate": <kWh>}` objects. Add as
    many forecast-day sensors as you need to cover 121 hours from whatever
    time of day updates happen to run (Solcast typically needs
    today/tomorrow/day_3 at minimum, more if you want headroom late in the
    day).
  - **Helios Forecast**: pick its "Power now" sensor
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
- **Grid/inverter setpoint** *(optional but recommended; on the Battery
  control pages)*: the entity that holds your current
  commanded charge/discharge power - a sensor, a `number` or an
  `input_number`. With **Status sensor only** it's asked on the Battery
  control page itself: the setpoint your own ESS automation writes. With
  **direct control** it's an optional separate readback on the next page
  (Battery control - target): what the inverter actually took over, for
  when the entity ESS Manager sets is only an in-between (e.g. an
  input_number an automation passes on); left empty, the entity ESS
  Manager sets is used. Right below it you choose its polarity:
  "Positive = import from the grid (battery charges)" (the default) or
  "Positive = export to the grid (battery discharges)". W or kW is
  taken from the entity's unit, so give an input_number a unit of `W` or
  `kW` (no unit counts as W). Used to make the "Status" sensor's engaged-vs-starting
  distinction accurate; nothing is ever written to it.
- **Cell voltage differential** *(optional)*: only needed if you enable the
  full-charge balancing plan.
- **Battery pack voltage** *(required if you enable the full-charge balancing
  plan)*: a sensor reporting the battery pack's own overall voltage. This is
  a third, independent confirmation leg on top of SOC and the cell voltage
  differential above - see [Full-charge balancing](battery-planning.md#full-charge-balancing).
- **Days since full charge sensor** *(optional)*: only needed if you enable
  the full-charge balancing plan and choose the external-sensor tracking
  option instead of the default internal tracking - see [Full-charge balancing](battery-planning.md#full-charge-balancing).

The planning runs once a minute, and also right at every quarter boundary
(:00, :15, :30, :45), so a
planned block or the night limit still starts and stops on the quarter.
Changing a setting on the card replans straight away. The heavy parts - the battery plans
and the heat-pump model - run in a worker thread, so
even on a Raspberry Pi they don't hold up the rest of Home Assistant;
only reading the sensors, sending the setpoint and setting the thermostat
happen on Home Assistant's event loop.

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
   sensor(s), the household usage source, and a switch for full-charge
   balancing.
2. **Usage source** - for the Energy dashboard: shows which statistics it
   found, plus the lookback weeks; for a consumption sensor: pick the
   sensor(s), plus the lookback weeks.
3. **Full-charge balancing** - only when that switch is on: cell voltage
   differential (or lowest/highest cell voltage), battery pack voltage,
   days-since-full-charge tracking, and the full charge target voltage.
4. **Battery and system** - capacity, normal charge/discharge speed, max
   battery charge/discharge speed, charge/discharge efficiency, min/max SOC.
5. **Price plans** - a short explanation of the negative price and spike
   arbitrage plans, with a switch for each (and one for
   the house from the grid at low prices - its page with the battery's
   power sensor follows).
6. **Battery control** - whether ESS Manager sends the setpoint itself
   (see [Direct control](control.md#direct-control)). "Status sensor only" is the default; with it,
   the setpoint your own automation writes and its polarity (optional) are
   on this page too.
7. **Battery control - target** - only when direct control is chosen: the
   number/input_number entity, its unit (W/kW), sign convention and idle
   value, and an optional separate readback with its polarity.

Depending on what you switch on, more pages follow: the electric car
(charger, cars), the heat pump (metering, sensors, floor control), the
house from the grid at low prices, prices including taxes and the night
limit (22:00-07:00).

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
| Electric car off, or without a charger of its own (Victron / zappi) | EV charger control |

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
| Minimum charge/sale duration | The shortest charge or sale block, in minutes (15-120 in steps of 15, default 30). A charge may be split over the cheapest quarters before it's needed, a sale over the priciest ones, but never into blocks shorter than this |
| Safety buffer | % of battery capacity kept on top of your min SOC (default 5%), both ways. With the **Automatic safety buffer** switch on the forecast check's advice is used instead - see [Forecast check](battery-planning.md#forecast-check). Selling: a sale never brings the forecast below min SOC + buffer - e.g. min SOC 10% + buffer 5% = sales stop at 15%, so a sale doesn't end in buying energy back. Charging: a charge lifts the dip to min SOC + buffer, not just to min SOC, so a bit more usage or less sun than forecast doesn't take the battery just under it (when to charge still follows min SOC itself - except for the rest of a charge in several blocks whose first block has run, which counts from min SOC + buffer until its last block; only what keeps that rest's dip at min SOC itself is due before the dip: the buffer on top comes with the next charge, in its cheaper quarters, before the end of the known prices - and isn't bought at all when it doesn't fit under 100% there, e.g. because the sun fills the battery after it anyway). 0 = right down to / up to min SOC |
| Transport tariff | Base grid transport tariff (EUR/kWh, default 0): buying costs price + (tariff x factor for that hour), selling doesn't - see [Grid transport tariff](prices.md#grid-transport-tariff). 0 = no transport |
| Planning horizon | How many hours ahead the low/high plans are allowed to react to (price data usually doesn't exist much beyond ~48h anyway) |
| Full charge interval | Days between full-charge/balance cycles |
| Full charge max hold | Safety timeout (minutes) for the 100%-hold/balance phase |
| Full charge target voltage | Battery pack voltage (V) that counts as "genuinely full" - checked minus 0.1V (see [Full-charge balancing](battery-planning.md#full-charge-balancing)) |

Max battery charge speed and max battery discharge speed are set during
setup and re-editable later from **Configure** (see above) rather than
appearing in this table - they're a fixed hardware property (the battery's
own physical power limit, in kW), not a live dashboard setpoint. They cap
the passive, solar/usage-driven battery energy forecast (anything solar or
usage implies faster than this is assumed to flow to/from the grid
instead), and what a charge or sale really moves in and out of the
battery: the speeds above are grid setpoints, the battery side is capped
at these. They don't limit the setpoint that is sent -
set the inverter's own limits (e.g. Victron DVCC max charge current) to
protect the battery.

**Charge efficiency** and **discharge efficiency** (%, default 100 = no
losses) are set the same way. They account for the inverter and battery
losses in the battery forecast and in every plan: at 90% charge
efficiency, 2.0 kWh of solar or grid power puts 1.8 kWh into the battery;
at 90% discharge efficiency, 0.5 kWh of usage (or of a sale) takes
0.5 / 0.9 = 0.56 kWh out of it. Charge and sale windows are sized for what
actually reaches or leaves the battery; the setpoint that's sent stays the
configured (grid-side) speed. With the **Energy
dashboard** as the usage source, the house's own solar and usage are taken
as they are: that usage is worked out from the grid, solar and battery
meters, so the losses are already in it (this needs battery meters on the
DC side, like a battery monitor - with meters on the AC side of the
inverter they'd be left out). A grid charge, a sale and the grid-use
threshold still count both efficiencies; with a consumption sensor (the
loads themselves) everything does.

**On a Raspberry Pi**: a cycle runs once a minute.
The Status sensor's attributes (~15 KB of forecasts and plans) are kept
out of the recorder, and the diagnostics show what a cycle costs
(`coordinator.cycle_timing`: last, average and longest of the last 60, in
ms).
