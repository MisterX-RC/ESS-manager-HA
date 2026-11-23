# Heat pump

The heat pump's day and hour models, the learned thermostat, steering the wanted temperature and floor control.

[← Back to the README](../README.md)

## Heat pump

For a heat pump whose electricity follows the weather.
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
  wind speed, wind direction (without them the weather entity's own wind
  is used), indoor temperature (it also teaches the model
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
- **Wind from the weather entity**: without a wind
  speed or wind direction sensor of its own, the model takes them from the
  weather entity's current state (`wind_speed` in its `wind_speed_unit`,
  converted to m/s, and `wind_bearing`) - nothing to set up. A weather
  entity has no statistics, so ESS Manager keeps its own hourly series (mean
  speed, speed-weighted mean direction, about two months) and, once per
  weather entity, reads the recorder's ~10 days of its states to start with.
  Journal days without wind are filled from that series (12 hours of the
  day needed). Learning and forecasting then use the same source. A wind
  sensor that is set still wins (read from its own statistics). The day model
  uses wind once it's known on **21 cool days** (or on 60 % of
  them) - days without get the median of those that have it, not 0; the
  wind direction still needs 30 cool days in 3 directions. The house model
  and the cooling fit use a wind term once 70 % of their hours have it (as
  before). `heat_pump.wind` shows the hours recorded, the source, the
  journal days with wind and the days needed.
  the start is read per part: the **speed** from the
  wind speed sensor's own recorded states when one is set (it may have no
  statistics yet), else from the weather entity; the **direction** from the
  direction sensor, else from the weather entity. An entity left out of the
  recorder gives nothing - then that part builds up live only, and the read
  is tried again a day later. With a wind sensor, the house model and the
  cooling fit take its statistics and fill the hours they lack from the
  series recorded here. `heat_pump.wind.read` shows what was read (states
  per entity, hours of speed and of direction). A day's live wind and
  direction go into its journal row only with 12 of its hours; right after
  the recorder is read, days the series covers get the whole day's wind.
  a wind speed sensor with a `forecast` list of its own
  (entries with `datetime` and `wind_speed`, like a solar forecast
  integration's wind sensor) also gives the forecast's wind speed - per hour
  where it has the hour, per day with 12 of its hours - so the model learns
  and forecasts from the same source; the direction stays the weather
  entity's. `heat_pump.wind.forecast` shows where it comes from, and
  `heat_pump.wind.cool_days` the cool days with wind the day model counts.
  The heat pump card's Signature tab shows **Wind x / 21** ("learning") until
  the model uses wind, then the wind term itself.
- **The slow part, an energy signature**: per day, kWh = base + kWh per
  degree below the balance temperature (+ wind x degrees, + wind direction
  once there are enough days in most directions) - sun (+ kWh per degree
  above the cooling temperature, with cooling data - from 16 °C at the
  lowest). With the indoor temperature on most cool days the heat loss
  follows indoor - outdoor: the balance temperature belongs to the usual
  indoor temperature on the cool days (a summer-warm house doesn't move
  it) and moves with each day's own, so a degree warmer
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
- **Days left out**: a cool day without heat demand (heat asked less than
  half an hour that day; the recorder's last ~10 days on the first start,
  live after that), a cool day
  on which the house lived on its stored heat
  (with an indoor temperature: it cooled 0.3 °C or more from midnight to
  midnight while the heat pump heated at most 4 hours - typical for autumn,
  out of the summer) says nothing about what such a day needs, and a day far
  off the model is a meter jump: both are left out of the fit. On the
  Signature tab they're grey rings. *Heat demand* comes from the heat
  pump's **heat demand switch** when floor control is set up (the heat pump
  heats only while it's on, hot water and cooling run outside it, so it works for any heat pump without its own
  sensors), else from the thermostat (a climate entity as the wanted
  temperature: its hvac_action, else indoor below wanted). Switching
  between the two clears the demand hours of the old source once; the
  recorder's last days refill them.
- **Falling back**: with fewer than 21 heating days, or heating days in fewer
  than 3 temperature classes of 2.5 °C (3+ days each), a poor fit or no
  weather forecast, the heat pump stays in the household usage (6-week
  average). In summer (no heating day in the coming days) only the
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
the heat pump page in Configure:

- **Step 1, the forecast**: the model also learns how the indoor
  temperature follows the outdoor temperature, wind, sun and the heat put
  in - with the floor's delay (its time constant it finds itself, from 1 up
  to 24 hours, over the heat of the last 36 hours - a concrete floor heated
  in a block of a few hours gives its heat off over many hours) and,
  with the optional **COP sensor**, the COP by the outdoor temperature (so
  it counts the heat, not only the electricity). Only
  hours the COP sensor never dropped below 1 count - the heat pump ran the
  whole hour: a COP sensor reads 0 while the heat pump is off, so the mean
  of an hour it ran for part of is far too low. With fewer than 48 such
  hours there's no COP model yet; floor control then uses its measured
  heat / electricity. `house_model.cop_check` in the
  diagnostics says how many of the COP sensor's hours fell out and why: no
  outdoor temperature, hardly any heating that hour (hot water or standby -
  the heating meter didn't count it), a COP outside 1-10, or not running the
  whole hour.
  **Heat meter**: with the heat pump's heat meter (kWh
  of heat - heating and hot water together, e.g. the Qube's "thermic yield
  total") and the meter of **all its electricity** (separate metering
  only), the model counts the heat that really went into the house: each
  hour's heat by the heating's share of the heat pump's electricity
  (heating electricity / all electricity - an hour of only hot water counts
  0, only heating all of it, a mixed hour shared out). The COP then comes
  from the meters (the heating's heat / its electricity per hour, hours with
  at least 0.2 kWh of heating) - no whole running hours needed. Without the
  total meter every hour with heating counts whole. The floor's delay is
  chosen on how well the model plays the last heating days again (the
  indoor temperature over each whole day, with the measured heat) - not on
  the step of one hour, where a sensor's 0.1 degC and the noise favour a
  short delay; `model.day_error_c` is that error. The **house's own
  electricity** counts as heat too (ironing, cooking, appliances - the
  household usage from the Energy dashboard minus the heat pump and the
  car, `model.kg` degC per kWh; for the forecast its usual amount per hour
  of the day), and an hour far off the fit - the room jumping a few
  degrees while ironing and falling back right after - is left out of it
  (`model.spikes_left_out`); the self-check compares with the room's trend
  (the median of each hour and its neighbours). It forecasts the indoor
  temperature and the heating per hour for 48 hours, the heat pump emulated
  keeping the house on its usual temperature per hour. **Self-check**: every
  day the newest 14 heating days are played again with their measured
  weather, cross-validated: split into 3 groups, each group played with a
  model fitted on all other hours (so it never saw those days) - is the energy put
  in the right part of the day and does the house follow the measured
  temperature with the measured heating? the energy is
  checked in **blocks of 6 hours**, each started again from the measured
  room and the heat measured before it - as the live control starts from
  the measurement every minute - and compared per block with the usual
  hourly pattern (both scaled to the measured day total). Before, each day
  was played blind from midnight and compared per hour: whether an on/off
  run landed at 3 or at 4 o'clock counted as two hours wrong, while that
  timing is the live control's job, not the model's; and a wrong heat loss
  hardly moved the hours, so it could pass. When the energy per block is
  clearly better (at most 90 % of the pattern's error) and the indoor
  temperature within 0.6 °C, the battery planning places the heat pump's
  hours by the model (each day's kWh stays the energy signature's); when
  that's no longer so it falls back to the pattern by itself. A **drift
  guard** watches the newest 4 heating days on their own, with a model of
  only the hours before them: no better than the pattern there, or the room
  more than 1 °C off, and the model doesn't pass even when the
  cross-validation does (`review.recent`). Nothing to switch by hand.
  `review.block_hours` says the block length (the errors `hour_error_kwh` /
  `pattern_error_kwh` are per block); `review.ess_hours` how many of the
  tested hours floor control switched the heat demand itself (below).
  `review.per_day` lists each test day on its own,
  newest first: its error and the pattern's per block, their ratio (under
  0.9 is what passing asks of the whole), the indoor error, the wanted
  temperature's range and number of changes that day (a night setback or a
  change by hand), the hours floor control switched and the part of the
  day's heat the minimum floor temperature gave (`min_kwh`) - to see which
  days score badly and why. It changes nothing in the verdict.
  **With a minimum floor temperature** the hours floor control switched
  are played with the heat the minimum asked that hour (kept per hour), as
  floor control planned them - also with the room above the wanted
  temperature. And the energy test only looks at the heat **above** the
  minimum, for the measurement, the model and the pattern alike: where the
  minimum gives most of the heat, when a run lands follows the heat pump's
  minimum run time rather than the house, and the usual pattern turns as
  flat as the minimum - no model can beat it there. Above the minimum is
  what the model decides. A day with less than 1 kWh above it isn't a test
  day. The indoor temperature test still uses all of the measured heat.
  With the learned thermostat the self-check only plays
  days whose wanted temperature per hour is known (the thermostat's history
  is kept from its first read on): a day from before that would have the
  thermostat switch around a guessed wanted temperature. Those days are left
  out while the thermostat is used (`review.skipped_days`), the thermostat is
  compared with the smooth controller on the same days.
  **How many test days are needed follows how much the
  days differ**, like the learned thermostat's switches:
  each day's margin is 0.9 × the pattern's error minus the model's error
  (per block), and its average must be clearly above zero - at least 2
  standard errors. Needed = (2 × spread ÷ average margin)², at least 6 and
  at most the 14 test days: steady good days pass after 6, days that differ
  a lot need more, and with more than 14 needed the self-check waits for
  steadier days (the oldest ones move out of the window). One bad day
  among few counts heavily - that's on purpose. In the diagnostics
  `review.needed_days`, `review.needed_raw` (before the 6-14 limits),
  `review.margin_kwh` and `review.margin_sd_kwh`; the card's Indoor tab
  shows how many days are needed. The fit itself runs once a day just
  after midnight and waits until yesterday's last hour
  is in Home Assistant's statistics (they're written a few seconds after the
  hour; at most two hours, then it fits without it), so yesterday is always
  part of the self-check.
  **The thermostat learned from the house**: with a
  thermostat (a climate entity as the wanted temperature) ESS Manager reads
  its history every day and keeps each switch of its heat demand
  (`hvac_action`) with the room and wanted temperature at that moment. From
  those it learns at how many degrees below the wanted temperature the
  thermostat switches on and how far above it switches off (for a
  `generic_thermostat` that comes out as its `cold_tolerance` and
  `hot_tolerance`), and a minimum run or pause when it keeps one - no
  settings, any make. Switches within 15 minutes of a setpoint or mode
  change don't count (the change made them, not the room).
  how many switches each way are needed depends on how close
  together they are: learned once the threshold is known to 0.1 °C (the
  sensor's step) with about 95 % certainty - at least 5 each way when they
  agree, more when they scatter (about 16 at a spread of 0.2 °C), at most
  30; the spread is the median absolute deviation, so one stray switch
  doesn't hold it up (before: always 10). The Indoor tab shows the progress
  (`house_model.thermostat`: `n_on` / `needed_on`, `n_off` / `needed_off`,
  `sd_on_c` / `sd_off_c`) and, once learned, the thresholds. The heat pump's heat per hour of demand is learned
  alongside (more when it's colder outside). The house model then plays the
  hours quarter by quarter with that on/off behaviour instead of a smooth
  controller, so the heat lands in the hours it really does. Both are played
  in the self-check, and the thermostat is only used when it places the hours
  better (`review.thermostat`: both errors and `used`). 
  hours in which floor control (stage Full) switched the heat demand itself
  are played as ESS Manager plans them, with the smooth controller - the
  thermostat didn't switch the heat pump then - and their thermostat demand
  time doesn't count for the heat pump's learned power. What ESS Manager
  plans itself - the floor's heat per hour, and the forecast while it
  switches the heat demand - always uses the smooth controller, so the floor
  keeps easing off before the room is there. A thermostat that
  modulates shows its switches scattered (`kind: modulating`) and the
  smooth controller stays. What was learned: `house_model.thermostat`; the
  switches themselves are in the diagnostics (`thermostat_events`). Its history is read with every recorded
  update, also those where only the attributes changed (a thermostat's
  state stays "heat" - its switches and wanted temperature are in the
  attributes). What the last read found is in the diagnostics as
  `thermostat_read` (rows, rows with a heat demand, switches, clean ones, an
  error if the read failed - then it's logged as a warning and tried again
  30 minutes later).
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

 With a thermostat the heat pump runs until the room
reaches its setpoint - by then the floor still holds a few hours of heat
that comes out afterwards, and the room overshoots. With floor control ESS
Manager heats the floor itself: the hour-by-hour house model plans the heat
per hour that keeps the room on its wanted temperature (easing off before
the room is there, because it knows the floor keeps giving), and that heat
becomes

- a **return setpoint** for the heat pump: the floor gives off heat in
  proportion to the mean water temperature above the room (or above the
  screed, with a floor sensor - see below). How much - kW per °C - ESS
  Manager learns from the supply and return temperatures, the room and the
  heat pump's thermal power. Little heat needed: a low setpoint and a better COP.
  It stays within 20-35 °C and the setpoint entity's own range, and never
  above the number **Floor control maximum return setpoint** (default
  35 °C, also on the Floor tab of the heat pump card) -
  for a floor whose pipes take less, like PVC. That also goes for the old
  setpoint it hands back when it stops;
- **heat demand** on/off: on when the heat owed (planned minus delivered)
  is worth a run, off once it's in - at least 45 minutes on and 20 off for
  the compressor, and always on more than 1 °C too cold / off more than
  1 °C too warm (1.5 °C: even within those times). While the minimum floor
  temperature (below) asks for heat, off only from 2 °C too warm (2.5 °C:
  straight away); the too-cold side stays the same. A safety net for a floor
  that gives off less than learned: from 0.2 °C too cold the power goes up
  (full at 1.2 °C), and 1 °C too cold the return setpoint never goes below
  the one the heat pump had before.

 **Minimum floor temperature** (number **Floor control
minimum floor temperature**, on the Indoor tab of the heat pump card under
the buffer range; 0 = off, the default; on the card "+" from off jumps to
20 °C). For comfort - warm feet - the floor is kept at least at this
temperature. What the number means depends on whether there's a floor
sensor:

- **Without a floor sensor** it's the **mean water temperature**
  ((supply + return) / 2) the floor model works with; the floor's surface
  itself is somewhat cooler. With the circulation pump stopped the water
  can't be measured, so the minimum is planned rather than switched on a
  reading: the floor held at that temperature gives off U × (minimum -
  wanted room) kW, and floor control's heat plan never plans less than that
  per hour. In the Full stage that heat is what ESS Manager switches the
  heat demand for, and the house forecast on the Indoor tab includes it.
- **With a floor sensor** it's the **measured floor temperature** in the
  screed, watched every minute from the moment the sensor is set up (no
  learning needed): the floor is too cold below the minimum - 0.2 °C and
  stays so until the minimum + 0.2 °C. While it's too cold, in the Full
  stage the heat demand goes on (after the 20 minutes off) and stays on
  (at least 45 minutes) even when nothing else is planned; once it's warm
  enough the normal plan takes over again. The house forecast plans the
  heat a floor at the minimum gives the room: k × (minimum - wanted room),
  with k the screed's emission to the room (from the two learned emissions,
  below; until the screed's is learned the room's U). The card shows the
  measured floor under the setting, and when it's too cold. If the sensor
  has no value, the minimum is planned as above until it's back.

The minimum only counts while **today's mean outdoor temperature is below
the heating limit** the day model learned (its balance temperature, on the
Signature tab): on warmer days - summer, and warm days in spring and autumn
- it asks for nothing, and the card says so under the setting; the setting
itself stays. The house's normal heating isn't affected by this: a room
below its wanted temperature is heated as always. Without a learned day
model or a forecast the minimum counts as set.

Both ways the 2 °C too-warm limit above applies while the minimum asks for
heat (with a floor sensor: while the floor is too cold; without one: while
the minimum is above the wanted temperature) - on a sunny day the room gets
warmer, that's the price of a warm floor. In the Return setpoint stage,
where the thermostat switches, only the return setpoint is held up: never
below minimum - half the supply-return difference, rounded up to the
setpoint's step (the planned setpoints on the Floor tab too).
A floor held at a temperature gives off heat whether the house needs it or
not. From the house model (heat loss at the forecast weather and wanted
temperatures, minus sun and the house's own electricity) ESS Manager works
out the temperature above which the floor gives more than the house loses
over the next 24 hours: mean wanted room + mean heat needed / U (with a
floor sensor: / k). A minimum
above it shows a **warning bar** under the setting (the house gets warmer
than wanted); the limit follows the weather, so on mild or sunny days the
bar can appear and on cold days go away again. Diagnostics: the floor
attribute's `min_floor` (`t_c`, `limit_c`, `target_c`, `too_warm`, `sp_min`,
`active`, `sensor`, `mode` measured / planned / off_season, `season`
(`t_out_c`, `balance_c`, `heating`), `t_slab`, `floor_cold`, `k`,
`comfort_band_c`).

 **Down gently while the compressor runs.** A big drop
of the return setpoint below the return made the heat pump switch off and
start again instead of modulating down. So while the compressor runs (the
Qube's status *heating* or starting up with the valve on CH; without a Qube
device: thermal power above 0) the setpoint goes down **one step of the
entity at a time** (0.5 °C on a Qube), and the next step only once the
return has come within **0.1 °C** of the current setpoint - never below the
value it's after. Up, with the compressor off or on hot water, or with the
return already at the new value (a cold start), it goes straight there.
The diagnostics show both: `sp_planned` (what's sent) and `sp_goal` (where
it's going), with `compressor_running`.

 Heat counts as the floor's only while the heat demand
switch is on. With it off the heat pump makes hot water (the circulation
pump may run too): those minutes aren't learned as running hours, their
heat isn't counted as delivered to the floor, and they don't enter the
floor's COP.

**Three stages**, chosen on the heat pump card (tab **Floor**, or the
select **Floor control**), each only running once the one before has
proven itself:

| Stage | What happens | Runs once |
|---|---|---|
| Watch (default) | nothing changes: the thermostat switches, the return setpoint stays; ESS Manager learns and shows what it would do | - |
| Return setpoint | ESS Manager sets the return setpoint by the planned heat, the thermostat still switches heat demand | the floor's heat output is learned: 30 settled running hours, at most 25 % off on the newest hours |
| Full | ESS Manager also switches heat demand; the thermostat is only where the wanted temperature is set | the heat pump delivered the target power within 30 % in the return setpoint stage - 8 to 24 running hours depending on how steadily (see below), from at least 3 separate heating periods - and the house model passed its self-check |

 **How many running hours the response check needs**
follows how steadily the heat pump delivered the target power (24 fixed
before): each settled running hour's error (|delivered - target| / target)
must on average be clearly below 30 % - at least 2 standard errors. Needed
= (2 × spread ÷ (0.30 - average error))², at least 8 and at most 24 hours,
and the hours have to come from at least 3 separate heating periods (runs
more than 6 hours apart, such as different nights): a few hours of one
night say little about other situations. A heat pump that follows closely
reaches Full after 8 hours over 3 nights; one that wavers needs more. The
check keeps running in Full and falls back to Return setpoint when it no
longer holds. The diagnostics show `response.needed`, `response.periods`
and `response.sd`; the card shows the hours and periods still to go.

 The house model's self-check runs every night, also in
Full - and the days ESS Manager switched are judged as it switched them,
with the minimum floor temperature's heat in them and the energy compared
above it (see the house model above), so a model that passed stays in Full
instead of failing on its own days and falling back to Return setpoint.
Right after the minimum is first set, while the usual pattern still comes
from days without it, the self-check can drop back to Return setpoint for a
few days; after about two weeks that settles.

The supply and return sensors sit in the heat pump: with the circulation
pump stopped they warm up from the cabinet, so only samples with the pump
running (and settled for 10 minutes) count. A **floor sensor** in the
screed (optional, between two pipes, about half way down) gives a second
emission, learned apart against the screed on the running hours that have
the sensor (30 hours, error at most 25 %, like the room's). It's used once
it fits and the sensor has a value; otherwise - still learning, not fitting,
or the sensor without a value for a moment - the room's, so floor control
keeps going on the room instead of dropping back to Watch. Only when neither
fits does it wait for the emission. The screed's mainly makes the return
setpoint fit better after a long pause (a cold screed takes more) and
during long runs (a warm one less); the room temperature stays what's
controlled. The Floor tab shows which one is used ("kW per °C to the
screed / to the room"); diagnostics: the floor's `model` (the one in use,
`ref` room / slab and `ref_reason` no_sensor / sensor_unavailable /
slab_learning / slab_inaccurate) with `room_fit` and `slab_fit`.

 With a **Qube heat pump** chosen as a device (the
`qube_heatpump` integration, optional, on the floor control page) its
*Heat pump status* and *Three-way valve status* sensors are found by
themselves, and only the minutes it really heats the floor count: status
*heating* with the valve on CH, from 3 minutes after the compressor got
there. Its start-up, the waits after it reached the return setpoint (heat
demand stays on, the pump runs, no heat) and hot water - also inside a
heating run - don't. Once hours come with the status, the floor is learned
from those only (`floor_records` in the diagnostics: `heat_s`, `dhw_s`).

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
   optionally the floor sensor, the Qube as a device and - with cooling -
   the changeover switch and/or the cooling thermostat.

**Cooling.** The heat pump's heat demand switch also starts cooling (with
the changeover switch on). While the changeover is on, or the cooling
thermostat calls for cooling (its action is *cooling* - left on *cool* and
idle all year it doesn't count), floor control steps aside
completely: the return
setpoint goes back to its old value once, the heat demand switch is never
touched (also not when ESS Manager stops), nothing is learned, and the
stage sensor says **cooling**. Once cooling is over it goes on in the stage
you chose (from *return setpoint* again; the response hours gathered
before still count).

Switching the thermostat off (mode off) means no heating in every stage:
in *full* the heat pump goes back to the thermostat until it's on again.
Going back to a lower stage, switching the select back, unloading ESS
Manager or stopping Home Assistant hands the heat pump back: the return
setpoint as it was before ESS Manager took over, heat demand as the
thermostat wants it. With steering on, the day/night temperatures and the
buffer are still written to the thermostat, so its card always shows the
wanted temperature; a change by hand counts until the next day/night switch.

 The **24 running hours of the response check** are
kept over such a hand-back for a moment - an input missing for a cycle (a
Qube on modbus right after a restart), a restart or update, the thermostat
off, cooling: only hours ESS Manager set the return setpoint in count
anyway. Only the select set to *watch* starts the check over.
