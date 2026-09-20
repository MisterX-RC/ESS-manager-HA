# ESS Manager

A Home Assistant custom integration for battery/solar/price-aware charge and
discharge planning: it watches your battery's state of charge, a solar
production forecast, a household usage forecast, and dynamic electricity
prices, and decides when to charge, when to discharge, and how much - so a
separate, small automation (or your inverter integration's own automation)
can act on that decision.

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
   capping at your normal SOC band.
5. **Negative price plan** - when the price goes low enough that charging
   pays you outright, buys as much as your hardware can take in that
   window, clearing room beforehand if needed.

All five compose on top of a 121-hour (5-day) forecast pipeline: solar
forecast minus usage forecast, cumulatively summed into a projected battery
level, compensated for the fact that the current hour is only partially
elapsed (see the code comments in `forecasting.py` for why that matters).

The integration's own sensor (`Status`) never writes to your inverter
directly - see "Wiring it to your inverter" below.

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
- **Household usage forecast**: either an existing sensor exposing `h0`
  through `h120` attributes (one float per forecast hour, h0 = current
  hour), or nothing at all - the integration can calculate this forecast
  itself directly from Home Assistant's own recorder statistics. See
  "Household usage forecast" below for how the built-in calculation works
  and what it needs.
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

## Household usage forecast

Every planning engine needs a household usage forecast, but there's no one
right way to produce it, so the setup wizard offers two:

**An existing sensor** - point the integration at any sensor exposing
`h0`..`h120` attributes, however you produce it. This is the original
system's approach: a hand-written SQL sensor averaging the same calendar
hour/weekday over several weeks of recorder history (see
`legacy-yaml-config/` for that exact query, if you're curious or want to
build your own variant).

**Calculated internally** *(no external sensor needed)* - the integration
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

The setup wizard asks for the entities above, plus seed values for the
initial battery capacity, charge/discharge speed, max battery
charge/discharge speed, and min/max SOC - these seed a set of `number`
entities (see below) that you actually tune afterward. Entity references
(which sensors to read) can be changed later from the integration's
**Configure** options; the number entities are adjusted directly, the same
way you'd adjust an `input_number` helper - no need to create separate
helpers.

### Tunable `number` entities

Created automatically once you finish setup - find them under the ESS
Manager device in Settings -> Devices & Services -> Entities:

| Entity | What it controls |
|---|---|
| Minimum SOC | Battery %, below which the low charge plan triggers |
| Maximum SOC | Battery %, above which the high discharge plan triggers (can be set above 100% to allow deliberate solar overshoot before discharging - the original hand-written version hardcoded this to 110% of a 30 kWh battery) |
| Battery capacity | kWh, used to convert the SOC % settings above into kWh thresholds |
| Charge speed / Discharge speed | Normal charge/discharge rate (kW) used by the planning engines to size grid-driven charge/discharge windows |
| Max battery charge speed / Max battery discharge speed | The battery's own physical power limit (kW) - caps the passive, solar/usage-driven battery energy forecast only; anything solar or usage implies faster than this is assumed to flow to/from the grid instead |
| Negative price charge speed | Rate used specifically during a negative-price event |
| Spike discharge speed | Rate used specifically during a spike-arbitrage discharge |
| Negative price threshold | Price (EUR/kWh) below which charging is considered "getting paid" |
| Spike margin | Minimum day price spread (EUR/kWh) to treat a day as spike-worthy |
| Minimum charge target | Always charge at least this many kWh once a charge session starts |
| Planning horizon | How many hours ahead the low/high plans are allowed to react to (price data usually doesn't exist much beyond ~48h anyway) |
| Full charge interval | Days between full-charge/balance cycles |
| Full charge max hold | Safety timeout (minutes) for the 100%-hold/balance phase |

## Wiring it to your inverter

The integration produces a `Status` sensor whose state is one of `Standby`,
`Start charge`, `Actief` (engaged), `Start discharge`, `Stop`, `Grid usage`,
`Solar export`, `Balancing`, `Start negative price charge`,
`Negative price charge`, `Start spike discharge`, `Spike discharge` - see
`custom_components/ess_manager/plans.py`'s `compute_system_status` for the
exact meaning of each. It deliberately does **not** write to any inverter
or battery control entity itself, since every make/model exposes a
different control surface (an `input_number`, a native `number` entity from
that inverter's own integration, an MQTT topic, ...).

`dashboard/automation_example.yaml` is a starting point for the small glue
automation that turns `Status` into an actual command - adapt the
`target: entity_id:` lines to whatever your inverter setup actually uses.

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
- **"Days since last full charge" is tracked internally** (the moment SOC
  last crossed 99.5%), rather than depending on an external
  "time since last full charge" sensor that not everyone will have. Until
  the integration has observed a full charge once, it treats a full-charge
  cycle as overdue, so expect one shortly after first setup if you enable
  that plan.
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
dashboard/                       adapted Lovelace cards + example automation
legacy-yaml-config/              the original template-sensor config, preserved as-is
sync-and-push.command            macOS helper - see "Keeping this repo in sync" below
```

## Versioning

`custom_components/ess_manager/manifest.json`'s `version` bumps by 0.0.1
(the patch digit) on every push - see `CHANGELOG.md` for what changed at
each version. This is what lets HACS tell installed instances an update
exists: it compares the tag on your most recent GitHub Release against
whatever version they currently have installed. Cutting a release is a
separate, manual step (GitHub -> Releases -> Draft a new release -> tag it
`vX.Y.Z` to match the manifest version -> Publish) - do it whenever you
want HACS to pick up everything pushed since the last release, not
necessarily after every single patch bump.

## Keeping this repo in sync (macOS)

If you're developing this alongside Claude rather than editing it directly
in GitHub: `sync-and-push.command` is a double-clickable script that lives
in this same folder. Each time it runs, it looks in your Downloads folder
for the newest `ess-manager-ha-repo*.zip`, copies its contents over this
folder (leaving this script and this folder's own `.git` history/remote
alone), commits whatever changed, and pushes to GitHub - so picking up an
update is one double-click instead of unzipping and typing git commands by
hand.

The first time it runs, git will ask for your GitHub username and a
personal access token right there in the Terminal window it opens; macOS
Keychain remembers it after that, so every run after the first is silent.
If macOS refuses to run it the very first time ("cannot be opened because
it is from an unidentified developer"), right-click the file, choose
**Open**, and confirm once - after that, double-clicking works normally.
