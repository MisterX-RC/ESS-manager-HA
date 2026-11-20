# Electric car

Charging sessions in the planning, the Victron EV charging station and the myenergi zappi, the phone questions, predictions and charging by hand.

[← Back to the README](../README.md)

## Electric car

For an electric car that charges **from the home battery**.
A car that doesn't take power from the battery doesn't need
any of this - its charging never shows up in the battery's planning.

Switch it on in Configure, on the price plans page (**Electric car that
charges from the home battery**); two pages follow:

- **The charger**: its **energy sensor** (cumulative kWh - Wh works too)
  and **power sensor** (W or kW) - or a **Victron EV charging station**,
  which ESS Manager then drives (see below) - the **minimum and maximum charging
  current** (default 6 and 16 A, up to 75 A), the **phases** (1 or 3, at
  230 V per phase - 16 A on 3 phases is 11.0 kW) and **Predict sessions
  from history**.
- **The cars**: a name, optionally the battery size (kWh), the usual
  target (%) and the **charge efficiency** (%,
  default 90): what reaches the car's battery of the energy the charger
  delivers. The energy a state of charge needs is divided by it, so the
  plan counts what comes from the house battery or the grid (40 -> 80% of
  60 kWh = 24 kWh into the car = 26.7 kWh at 90%). Add as many cars as you
  like ("Add another car"), remove them, or pick one under **Change a
  car** to change its battery size, target or charge efficiency.

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
belongs to (started up to two hours early or late) is running: its day and
start time are fixed, the rest can still change, and what's already charged
(from the energy sensor) counts. Charging that matches no session becomes a
manual session from the current hour (with the typical energy - change it
on the card). Ten minutes without power and the session is done.

**While the house battery charges from the grid** *(without a charger of
its own, with direct control)*: the grid setpoint sent
goes up by what the car takes (the power sensor), so the battery still
charges at the planned speed - also at the night speed, where a car taking
more than that would otherwise be fed by the battery. The battery forecast
leaves the car's energy out for the rest of that running charge.

### Victron EV charging station

Instead of an energy and a power sensor, the charger
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
  (tomorrow and the day after are shown as their day of
  the week - *Tuesday*, *Wednesday*; that's four buttons: an iPhone shows
  them all, Android only the first three, so "doesn't matter" is then on
  the card); for a day it asks the hour (typed: `7`, `7:30`, `19u`), then the state of
  charge. What's needed (to the car's target %) is planned: **the sun
  first** - the charger on its own **Auto** mode, which charges on the
  solar surplus - and whatever the solar forecast can't deliver in time
  is **bought in the cheapest quarters before the deadline** ("doesn't
  matter": within the prices known), in Manual mode, in blocks of at least
  half an hour. ESS Manager picks the speed itself, **calm by
  preference**: the **lowest current that costs at most
  2 ct/kWh more** than the cheapest plan. Where a calm charge needs really
  dear quarters (a faster charge fits in the cheap ones) it's the faster
  current; when the calm one doesn't make it in time, a higher one. It plans to be done **an hour before** the time given
  (full by 10:00 = done by 09:00). When even the maximum current doesn't
  make it, it charges at the maximum right away and says how far it gets
  (red on the card). The answer says how much comes from the sun, how much
  is bought when and at what current, and when it's full. The plan is worked out again every cycle (new prices, a
  different solar forecast, what's charged so far); a grid window that's
  running finishes.
- **Full by a time after the known prices**: when the
  car has to be done (an hour before the time given) later than the prices
  known so far - say full by Friday 07:00 while only Thursday's are in -
  the known quarters are only used at or below the **reference price of
  the last week** (the median over 7 days of each day's 6 cheapest hours,
  the same one the battery planning uses). What they don't bring in waits
  for the next day's prices (in at about 13:00), as long as it fits, at the
  maximum current, between the end of the known prices and the time it has
  to be done; it's planned from the end of the known prices on, so it still
  charges in time if no new prices come in. Once they're in, the time lies
  within the known prices and the cheapest quarters are chosen.
  Doesn't the rest fit in the unknown hours, or isn't there a reference
  price yet (fewer than 3 days of prices): the cheapest known quarters, as
  before. The answer and the card's charge plan say what waits, from when,
  and the reference price; its window shows "price not known yet".
- **Dear quarters out of the house battery**: per
  quarter the car's energy can also come out of the house battery, at what
  it costs to fill it up again - the cheapest price after that quarter
  divided by the charge x discharge efficiency (e.g. 0.20 / 0.855 = 0.23).
  Where that's cheaper than the grid at that moment (an evening peak), the
  car charges from the battery: the charger on Manual at the plan's
  current, the grid setpoint **not** raised. Only as much as the battery
  can give without going below its minimum + Safety buffer on the house
  alone until the deadline, and only where its max discharge speed minus
  the house still covers the car's power. That energy counts as usage in
  the battery forecast, so the charge plan fills it up again in the
  cheapest hours. On the EV card these quarters show in green ("House
  battery"). The card's own preview while sliding shows the grid only. A window that's running ends where it was
  planned: its last quarter doesn't count as a "lone quarter" that takes a
  neighbour along, so it doesn't grow and push out cheaper quarters later on.
- **During a grid window the house battery stays out of it**: with direct
  control, the grid setpoint sent goes up by what the car takes (measured),
  so the grid supplies the car and the battery does what it was going to
  do anyway; the battery forecast leaves that energy out too.

**Until there's an answer** - and when there never is one - ESS Manager
**doesn't start anything**, unless the car is plugged in during a planned or
predicted session: then that plan is taken over and charging starts (see
*Planned "full by" sessions* below). **Unplugging puts the charger back to
rest** (Manual mode, charging off - once), so the next car plugged in
without a plan doesn't charge by itself on what the last session left
behind. ESS Manager sends a value to the
charger only when its plan changes (plugging in, a choice, a grid window
starting or ending, done); what you change on the charger itself in
between - e.g. starting a charge by hand - is left alone.
When the plan changes, the charger is checked as a whole -
mode, current and start: a grid window that puts the
charger on Manual also sends start, even when start was already sent
before the window. A charge the charger starts **by itself** before there's a
choice - by hand on the charger, its own auto start, a schedule or its own
Auto mode - counts as "now, at the current it's set to": it goes on, the
session is forecast at that current, and the card says so. A choice made
afterwards takes over. The plugged-in car's
session can't be removed on the card while the car is plugged in. Once the
energy is in according to the sums (or the charger says "charged") the
charger is **left as it is**: the car stops by itself when it's really full, and a state of charge
or a battery size that's a bit off doesn't leave it short. When the car
stops itself well before the goal (at least 1 kWh and 10 % still to go by
the sums), the card says so: "The car stopped at about
80 % instead of 90 % - is its own charge limit set lower?". Unplugging ends
the session and clears the notification. With direct control's **Automatic
control** switch off, ESS Manager doesn't touch the charger.

**A session added while a car is plugged in** that
starts before that car is done waits for it: it stays on the card ("waits
for the plugged-in car - counts from 15:15"), and counts in the forecast
only from the plugged-in car's end on - one charger, one car at a time.
It isn't dropped while the car stays plugged in, and when the car
is unplugged it starts then, so the next car plugged in takes it over.

**State-of-charge correction**. What really goes into
the car rarely matches the state-of-charge sum exactly (charging losses, a
battery size or state of charge that's a bit off). So every charge with a
state of charge **you gave** (on the phone, on the card, or the start SOC
of a session you set on the card - not a predicted one) that the car
**finishes while still plugged in** is measured: the charger says
"charged", or it's switched on (Manual, on) but nothing has gone in for 15
minutes. The energy that went in since the state of charge was given,
against what the state of charge said was needed, is one sample. From
three samples on, the energy charged over the energy planned in the car's
last ten samples - on top of its charge efficiency - is
its **correction factor** (kept between 0.7 and 1.5),
and every state-of-charge sum for that car is multiplied by it - the
energy a session needs, when it's full, "full by", the forecast. A sample
under 3 kWh doesn't count, nor one that's far off: more than 25% from the
car's long-term average once there is one (all its samples), outside
0.6-1.6 before that - most likely a state of charge typed wrong, or the car
stopping at another limit than its target in ESS Manager (so set the
target in ESS Manager to the car's own charge limit). The EV card shows
the factor per car ("State-of-charge correction: x1.08 (5 charges)"), the
diagnostics the last samples.

**The plug-in log and the predictions**. With a charger of its own (Victron or zappi) ESS Manager keeps
its own log of every time a car was plugged in (car, plugged in, unplugged,
kWh, the way of charging chosen, the time for "full by"), 12 weeks long -
the recorder keeps plugged-in states only about 10 days. Once the log
covers your usage lookback (usually 6 weeks), the predicted sessions come
from it, per connection instead of per charge: a "full by" that the prices
split into two blocks is one session.

A prediction is a **block in which the car is usually
plugged in**, not a plug-in time. For each day the connections of the same
weekday in the lookback weeks are laid over each other (followed up to 36
hours past that day's midnight, so Friday evening to Saturday morning stays
Friday); where the car was plugged in in more than half the weeks, for at
least an hour, that block becomes a session. A car plugged in every Friday
evening at very different times (17:10, 19:40, 21:05, ...) and unplugged on
Saturday morning gets one session from when it's there in most weeks (the
start rounded up to the quarter) to when it's still there in most weeks.
The session has the average energy of those connections per week, the car
and the way of charging chosen most often, and "full by" the usual time
chosen (at most the block's end) - else the block's end, also without a
choice when the block is at least 3 hours and well over twice as long as
charging takes; a shorter block without a choice charges at a fixed current
from its start. Plugging in from the **earliest plug-in** of that block on
takes the session over (attribute `plug_from`), so an early plug-in still
charges "full by" in the cheapest quarters from then on. Plug-in times
that vary a lot don't stop a prediction: it's the block the car is there
that counts.

Until the log covers the lookback there are **no** predictions with a
charger of its own: the charging energy then follows the
hours the planning chose for "full by", not when the car was there, so it
would predict sessions at the wrong time and of the wrong kind. Without a
charger of its own the predictions come from the charging energy.

**Planned "full by" sessions.** A planned session can be "full by" as well
(on the card, or predicted from the log): it's forecast with its own plan
(calm by preference - the lowest current at most 2 ct/kWh dearer than the cheapest - done an hour before its time, sun
first, the cheapest hours, dear quarters out of the house battery; where the prices for then aren't known yet, planned as a
plugged-in car would be - the known quarters up to the reference price, the rest after the known prices - or, without a
reference price yet, a calm charge from its start), and the battery forecast leaves its grid part out. **Plugged
in during a planned session** - one predicted from the log (from its
earliest plug-in on, see above) or from the charging energy, edited or
added on the card - its plan is taken over right
away, and the phone only asks
"the planned session is taken over: full by 07:30, 9 kWh. Is that right?" -
**Yes** keeps it (the end time follows), **Something else** brings the usual
questions (the plan stays until a new choice). With a car
whose battery size is known it talks in the state of charge the car shows,
not kWh: "... taken over: full by 07:30, from 60 % to 80 %. Is it at 60 %?
Tap Yes, or fill in its state of charge." (without a planned state of
charge: "What is its state of charge now?") - a **State of charge** reply
field next to Yes and Something else; the answer sets what's needed (to the plan's target), the
plan itself stays, and it counts for the state-of-charge correction. Sessions
predicted from the charging energy are taken over too; a session counts from two hours before its start to two hours
after it (or to its end or "full by" time). Nothing planned or predicted
then: only the question, and the charger isn't started.

**09:00 on a day with a planned session** (predicted or added on the
card): "A charging session is planned today at 18:00 - still right?"
**No** switches it off (it stays on the card with its tick off); **Yes**
asks the expected state of charge (or kWh), which then sets the session's
energy. This question also comes without a charger of its own (energy and power
sensors only), on the phones picked under **Phones to ask on**.

**When a session starts and ends**. Right after
plugging in, the Victron charger passes "waiting for start" and sometimes
even "charged" before it really charges. A session only really starts
when the Status is **charging and power goes in** - until then it's
"plugged in", and a "charged" doesn't end it. Unplugged without ever charging, it
wasn't a session: nothing goes into the plug-in log and the planned
sessions it took over come back. A finished session stays on the card
as **completed**, with the energy that went in, for **6 hours** after the
car is unplugged (Victron) or after the charging stopped (sensors only).

**The same on the EV card** (one way of charging for every session, one
panel). At the top, **Now**: the plugged-in car. Without
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
charging current; the end time follows the slider. The
state-of-charge controls (now and target, in both panels) sit one under the
other over the full width, with a bigger slider that leaves a vertical swipe
to scrolling, **−** and **+** buttons (1% per tap, hold to keep going) and
the value as a field: tap it and the number pad opens, type the number and
press Enter (or leave the field) - empty or nonsense puts the old value
back, a value out of range is held to 0-100 and the state of charge still
stops at the target (and the target at the state of charge). Under the
target, quick picks **60 / 70 / 80 / 90 / 100%**. Below, **Planned**: the
predicted and added sessions, each with its way of charging (fast, slow or
on the sun); tap one to edit it in the same kind of panel (day, plug-in
time, way of charging, state of charge when plugged in and target; for
"full by" the day and the time it should be full - the day is the
plug-in day or one of the three after it, moving along when the plug-in day
changes). A "full by" shows its **charge plan** in that panel: the price per quarter from the start to the
deadline, the charge windows on it (blue = grid, green = house battery) and
per window the time, the current, the kWh and the average price, with the
estimated cost below. A saved session that's opened unchanged shows the
integration's own plan; as soon as something is changed the card's preview
("preview") until it's saved. The session's line shows its planned start
(as set) and the time it's full; when the charging starts later, that
start goes with the number of blocks ("1 block from 20:45"). The
plugged-in car's panel shows the same charge plan: the
integration's own plan while the choice is unchanged, the preview once
it's changed; its day comes from the deadline itself, so "tomorrow" chosen
in the evening shows as today after midnight. The card uses the service `ess_manager.ev_charge_plan` (`choice`: asap / calm /
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

### myenergi zappi

 A zappi of the
[myenergi integration](https://github.com/CJNE/ha-myenergi) works like the
Victron charging station - plugging in starts a session, the questions on
the phone, taking over a planned session, "full by" with its charge plan,
"stopped early" - except that it has no current to set: ESS Manager picks
its **charge mode**. In Configure > Electric car pick "myenergi zappi" and
the zappi's device; its charge mode, status and plug status are found on
the device (by the end of their unique id). The energy and the power come
from the charger's own meter - pick those sensors yourself (a separate kWh
meter in the meter cabinet; the zappi's own CT values are cloud-polled and
coarse).

| Choice | zappi mode |
|---|---|
| Now (fast) / a grid or battery window of "full by" | Fast |
| Now, slowly | Eco - at least 6 A (about 1.4 kW on one phase); Fast when the min current set here equals the max |
| "Full by" between its windows / on the sun | Stopped |
| No choice, done, unplugged | Stopped (once after unplugging, so the next car doesn't start by itself) |

 The zappi's **Grid CT clamp sits between the Victron
and the grid** - the point the Victron keeps at its grid setpoint. Eco and
Eco+ never see consumption there: once started (a short export when a load
switches off is enough) they keep taking more, the house battery covering
it, up to the max current - live Eco+ in the dark between the windows of a
"full by" charged at 1.4 kW and then 2.9 kW out of the house battery. So
ESS Manager only puts the zappi on Eco or Fast in a planned or chosen
charge, and on **Stopped** otherwise; a "full by" is planned with its
windows at Fast (the max current set here) and without the sun in between.
"On the sun" (a planned session) therefore doesn't charge with a zappi for
now. With min and max current both at the max (e.g. 13 A), "now, slowly"
is the same as "now" and runs at Fast as well. A mode is sent when the plan's mode changes, not again while
it stays the same - a change in the myenergi app is left alone meanwhile,
once the zappi has shown the mode sent. Until it does, the mode is sent
again every 3 minutes, at most 4 times, then a warning - so a command lost
on its way through the cloud isn't taken for a change in the app.
The integration polls the myenergi cloud (every 60 s by default), so a mode
change can take a minute or two to show on the meter; each command and how
long the meter took to follow is in the diagnostics
(`ev_charger_commands`). Set the zappi itself to **Stopped**, turn on
**charge when locked** if it has a PIN (locked without it, it doesn't charge
on a command - the EV card says so: `charger.blocked`), and remove boost
timers and smart boost in the myenergi app (they work in Eco and Eco+):
ESS Manager plans the charging.

### EV charger control and manual charging

 With a charger of its own (Victron or zappi) the device
has an **EV charger control** switch, also on top of the EV card ("Automatic
charging"). On (default): ESS Manager drives the charger as the plugged-in
car's plan says, as described above. Off:

- the plan is still worked out and shown, but **greyed and not usable**,
  marked "not active" - nothing of it is sent to the charger;
- **no EV notifications** go out (no question at plug-in, no 09:00 question);
- an orange block on top of the card drives the charger **by hand**:

  | Button | Victron EV charger | zappi |
  |---|---|---|
  | Slow | manual mode, minimum current, charging on | Eco |
  | Fast | manual mode, maximum current, charging on | Fast |
  | Off | charging off | Stopped |

  Each press sends one command; after that the charger is left alone (a
  change on the charger or in its app stays). The button that matches the
  charger's own state is highlighted. Without a car plugged in the buttons
  are greyed out;
- a choice **From grid / From battery** at the top of that block: from the
  grid, the grid setpoint goes up by what the car takes (as in a planned grid
  window), so the house battery stays out of it; from the battery, the car
  counts as house usage. Kept across restarts. It only applies while the
  battery's setpoint is sent (direct control with Automatic control on).

Switching it off leaves the charger as it is. Switching it on again sends
the plan's values afresh. With direct control, switching **Automatic
control** (the battery) off switches EV charger control off too - the plan
can't be followed without the battery's setpoint - and it can't be switched
on again until Automatic control is on. The card's buttons call the service
`ess_manager.ev_manual` (`action`: slow / fast / off, `source`: grid /
battery). Diagnostics: `switches.ev_charger_control`,
`switches.ev_manual_source`, and per cycle `ev.manual`.
