# Dashboard cards

The seven dashboard cards and their options.

[← Back to the README](../README.md)

## Dashboard

The integration brings its own dashboard cards. After installing (and a
browser refresh), edit a dashboard, choose **Add card** and search for
**ESS Manager**:

| Card | Shows |
|---|---|
| ESS Manager - Battery forecast (`custom:ess-manager-battery-card`) | five whole days: the measured and the expected battery level, solar, usage, the planned buy / sell moments and how long you'd last without the grid |
| ESS Manager - Prices (`custom:ess-manager-price-card`) | today's and tomorrow's prices coloured by price level, with the planned buy / sell moments |
| ESS Manager - Status (`custom:ess-manager-status-card`) | the planned sale and charge with their progress, the price plans, the control toggle and a timeline |
| ESS Manager - Electric car (`custom:ess-manager-ev-card`) | the electric car's charging sessions in the planning: check, edit or add them (only with the electric car switched on, see [Electric car](electric-car.md#electric-car)) |
| ESS Manager - Heat pump (`custom:ess-manager-heatpump-card`) | the heat pump forecast from the weather: the coming days, the energy signature and what the model has learned (only with the heat pump switched on, see [Heat pump](heat-pump.md#heat-pump)) |
| ESS Manager - Forecast check (`custom:ess-manager-forecast-card`) | how good the usage and solar forecasts were, which usage forecast is in use and the Safety buffer advice, with the "adjust automatically" switch (see [Forecast check](battery-planning.md#forecast-check)) |
| ESS Manager - Savings (`custom:ess-manager-savings-card`) | what the battery saved against the same house without one - per day, week, month and year, with what was bought and sold and the average price per kWh |

All of them are drawn by the integration itself - nothing else to install
(no apexcharts-card needed). The integration loads the card
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
language) - the status card shows the status in Dutch too, while the
sensor's state itself stays English for your automations. The setup and
Configure screens are in Dutch as well; times, numbers and the currency follow Home Assistant's
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
  It never goes above 100%: what solar would add on top
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
when a transport tariff is set, otherwise it equals the price).
a dashed line across the whole chart - the part without
prices yet included - marks the **reference price of the last week**
("ref € 0.33", the buy price, so not in the sell view): bold while it's in
use (the battery's plans, or a car's "full by" waiting for the next day's
prices), faint otherwise; hover it for what it is. Top:
the price now, the buy price, and the cheapest and most expensive moment
still to come. Tap (or hover) for the price of a quarter.

**With prices including taxes** (see above) the card shows one kind of
price at a time: the **buy** prices with a solar deficit, the **sell**
prices with a solar surplus. The header says which ("Electricity price ·
buy · now") and whether the price now is **incl** (buying) or **excl**
(selling) taxes; tap the header to switch between the two. The tooltip
always shows both, each labelled. The battery forecast's tooltip follows that choice:
its price is the buy price incl taxes or the sell
price excl, labelled the same way.

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

**Status card.** At the top the title, the Status and a toggle for the
control (the integration's **Automatic control** switch when it controls
the battery itself, otherwise the automation you choose in the card's
options; hover it for its name) and next to it **Settings**, which opens
the ESS Manager device page with all its numbers, switches and sensors
(written out when there's room, just the cog on a narrow card; only shown
to admins). Below, two blocks side by side: **Sell**
on the left, **Buy** on the right - with the house from
the grid at low prices switched on a third, **From the grid**: the current
or next window the house is taken from the grid (start and stop, "+2" for
the later ones - hover it for their times, a bar that fills while it
runs), and what it keeps in the battery or "sun covers the house" (then a
peak comes from the grid). The three stay in one row:
a block without a plan shrinks to a narrow strip (its icon,
name and "none") and the planned ones share the rest of the width - a
sale and a charge are never planned at the same time, so at most two are
wide; a block narrower than about 200 px gets compact lines ("5,1 🔋 67 %",
"0,2 kWh kept"). On a phone (up to 380 px) they're under each other, an
empty block a low bar. With nothing planned at all
the three empty blocks share the full width evenly instead of three narrow
strips on the left. `show_grid: false` in the card's YAML hides the
grid block. Tapping a planned block (or its "+2") opens
the **planning panel**: every plan from now on in time order - charges,
sales, the house from the grid, the full charge (with until when it
balances) and the balancing wait, spike and negative price plans, solar
export, and the expected solar surplus as on the price
chart (battery full or more than it can take, with the kWh to the grid) -
with the time, the kWh, the average price and the battery level
after it, grouped by day, "now" / "next" on the running and next one, and
a timeline of the coming 24 hours on top. Closed with the cross, a tap
outside it or Escape. Each shows the start (with the day when
it hasn't started yet) and stop time, a bar with the duration and - once
the window runs - how far it is, measured on the energy (it fills as the
battery moves towards the plan's target, and says how long is left; hover
it for the kWh done), the energy (kWh) and the target battery level (SOC
expected after it). An active spike or negative price plan shows in the
block it drives, with a chip in that plan's colour (a spike drives both
blocks: the cheap charge and the sale in the peak); full-charge balancing
gets a chip too. In a narrow block (three blocks side by side, or on a
phone) the chip shows only the plan's icon, with its name as a tooltip.
A block that is running - charge, sale or the house from the grid - is
outlined: in the colour of the plan that drives it (spike, negative price,
balancing), otherwise in the block's own colour. The outline stays until
the block's stop time, also once the target is reached; a block that is
only planned has no outline. While the battery waits at 100% for the cells to
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
| `grid_color` / `export_color` | purple / orange | the timeline's House from grid / Solar export (the same colours as on the price and battery charts) |

**Electric car card.** The car's charging sessions for today and the next
four days (see [Electric car](electric-car.md#electric-car)), with the total that's in the
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
  hours solid, the expected one lighter - with heating meters chosen); the model's stage (learning, watching along,
  used, steering) with its self-check's figures; the buffer plan (warmer /
  cooler when, what it saves); COP at 7 and −2 °C, the floor's delay, the
  heat-up per 10 kWh. With step 2 the steering switch and the day/night
  temperatures, their hours and the buffer range, with − and + buttons.

| Option | Default | What it does |
|---|---|---|
| `title` | `Heat pump` | the card's title |
| `hp_color` | orange | the heat pump colour |

**Savings card**. What the battery saved against the
same house without a battery: per quarter, the grid import and export
that were measured, against what would have gone through the grid without
the battery (export - import + charged - discharged, per 5 minutes) -
bought at the buy price incl taxes and transport (see [Prices including
taxes](prices.md#prices-including-taxes)), sold at the bare price. The battery's
losses are in it by themselves: only measured energy counts.

**The battery's stock**. Energy put in the battery counts
on the day it comes out, at what it cost to put in - so a day the battery
is filled cheaply for the next day doesn't show as a loss, and the next
day as a big saving. The integration keeps what's in the battery (its state
of charge x capacity) and what that cost: grid charging at the buy price
incl of that quarter (the part of the charge the grid gave as much as:
min(charged, import)), solar at the bare sell price of that quarter - what
it would have brought in without the battery, so the missed sale and the
stock cancel out and nothing counts twice. What comes out goes at the
average of what's in it; cheaper energy put in later pulls the average
down, weighted by how much. Losses come out of the value without energy
for them (the state of charge rises less than was charged, falls more than
was given), so they count too. A day's saving = cost without - cost with +
the change of the stock: a day the battery is filled cheaply comes out at
about 0, the day it gives the energy back gets the price saved minus what
it cost. The card shows the change in the **with ESS Manager** box ("into
the battery" / "out of the battery") and below the chart what's in the
battery now and its average price. Over a month it's the same money; only
the days are fairer. It needs the state of charge sensor's statistics
(state_class measurement); without them the stock isn't counted. The stock
starts at the first day the recorder still has, valued at that day's
average buy price.

At the top the saving in the period - **Day** (just the totals, no bars:
within a day the money goes out while charging and the saving comes when
the battery is used, which bars per hour would show as losses), **Week**
(Monday to Sunday, a bar per day), **Month** (a bar per day, with the
average per day), **Year** (a bar per month) or **365 d** (365 days up to
today, a bar per month) - and how much less
that is than without the battery. Below it **without battery** and **with
ESS Manager** side by side: what it cost, the kWh bought and sold and the
average price per kWh of each (with ESS Manager: including the change of
the battery's stock). A day that cost more with the battery (e.g. losses
on a day with flat prices) is a red bar below zero. Tap a bar for
that day: the saving and the cost with and without. Below the tabs the
arrows go back and forth a day, week, month, year or 365 days, like on the
Energy dashboard (back as far as there are stored days).

Where it comes from: the Energy dashboard's **grid import and export** and
**battery charged and discharged** statistics in 5-minute steps (the
recorder's short-term statistics) and the price sensor's recorded states.
Every night yesterday is added; at the start the integration looks back as
far as the recorder keeps its history (`keep_days` of the recorder, 10 days
by default - set it higher in `configuration.yaml` to look back further).
Days the statistics don't cover are skipped (the reason is in the
sensor's `skipped` attribute). The prices of each day are kept by the
integration itself - for days before it started keeping them it reads
the price sensor's recorded history. Without the battery in the
Energy dashboard the card says so instead. A day is stored as raw sums
(kWh and kWh x price), so the line incl taxes is put on when shown - a
learned line or a tax change applies to the past days too. The days are
on the **Savings this month** sensor (state: this month's saving), its
attributes out of the recorder.

| Option | Default | What it does |
|---|---|---|
| `title` | `Savings` | the card's title |
| `saving_color` / `loss_color` | green / red | a day saved / a day more expensive |

`dashboard/` still has the old chart cards as plain apexcharts-card YAML
and the old status card (`entities_card.yaml`), for when you'd rather
build your own: each file's header comment explains which placeholder
entity_ids to replace with your own. The built-in cards no longer use
them.
