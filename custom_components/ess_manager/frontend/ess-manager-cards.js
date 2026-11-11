/*
 * ESS Manager dashboard cards - loaded automatically by the integration,
 * shown in the dashboard's "Add card" picker:
 *
 *   custom:ess-manager-battery-card   battery forecast: five whole days, measured + expected
 *   custom:ess-manager-price-card     today's and tomorrow's prices with the planned moments
 *   custom:ess-manager-status-card    Sell / Buy blocks, price plans, control toggle, timeline
 *   custom:ess-manager-ev-card        the electric car's charging sessions (as of 2026.10.11)
 *   custom:ess-manager-heatpump-card  the heat pump forecast from the weather (as of 2026.10.16)
 *
 * Each card only needs `entity:` - the installation's Status sensor. All
 * three are drawn by this file itself (as of v0.5.1 also the battery and
 * price cards, which used to build on apexcharts-card) - no other card is
 * needed. Texts follow the user's Home Assistant language (English and
 * Dutch, English for anything else); times, numbers and the currency follow
 * Home Assistant's language, region and time zone settings.
 *
 * GENERATED into custom_components/ess_manager/frontend/ess-manager-cards.js
 * by tools/build_cards.py - edit this file, then run the script.
 */

const ESS_DOMAIN = "ess_manager";
const DOCS_URL = "https://github.com/MisterX-RC/ESS-manager-HA#dashboard";
const UNIT_MS = 15 * 60000;
const HOUR_MS = 3600000;

// -- Translations ----------------------------------------------------------------
// One table for all cards and their editors. A missing key falls back to
// English, an unknown language too.
const I18N = {
  en: {
    // status card
    planned: "planned", running: "running", done: "done", of: "of", stop: "stop",
    left: (d) => `${d} left`, no_sell: "No sale planned", no_buy: "No charge planned",
    spike: "Spike", negative: "Negative price", balancing: "Balancing", balancing_max: (d) => `max ${d}`, cell_diff: "Cell voltage difference", pack_voltage: "Battery voltage",
    more_blocks: (n) => `+${n}`, more_blocks_tip: (n) => `and ${n} more ${n === 1 ? "block" : "blocks"}`,
    balance_after: (t) => `then balancing at 100 % until ${t} at the latest`,
    active: "Active", inactive: "Inactive", below: "below", auto_control: "Automatic control",
    h: "h", min: "min", ago: (h) => `-${h} h`, now: "now", settings: "Settings",
    // battery card
    battery_title: "Battery forecast", today: "today", horizon: "planning horizon",
    offgrid_empty: (w) => `without grid: empty ${w}`, offgrid_full: (w) => `without grid: full ${w}`,
    offgrid_days: "without grid: 5+ days", measured: "measured", expected: "expected",
    soc: "SOC", without_plans: "Without plans", solar: "Solar", usage: "Usage", price: "Price",
    min_label: (p) => `min ${p} %`, max_label: (p) => `max ${p} %`,
    // plans (battery + price card)
    plan_sell: "Sell", plan_buy: "Buy", plan_spike: "Spike", plan_negative: "Negative price",
    pp_title: "Planning", pp_close: "Close", pp_none: "Nothing planned", pp_now: "now", pp_next: "next",
    pp_charge: "Charge", pp_sell: "Sale", pp_grid: "From the grid", pp_full_charge: "Full charge", pp_balancing: "Balancing",
    pp_spike_charge: "Spike: charge", pp_spike_sell: "Spike: sale", pp_negative_charge: "Negative price: charge",
    pp_negative_sell: "Negative price: discharge first", pp_solar_export: "Solar export", pp_surplus: "Solar surplus",
    balance_until: (t) => `balancing until ${t}`,
    plan_grid: "From the grid", no_grid: "No grid use planned", grid_kept: "kWh kept in the battery", grid_kept_short: "kWh kept", none_short: "none",
    grid_sun: "sun covers the house", grid_sun_tip: "The sun is forecast to cover the house - an unplanned load or a peak comes from the grid, not from the battery.", grid_more_tip: (n) => `and ${n} more ${n === 1 ? "block" : "blocks"}`,
    plan_full: "Full charge", plan_charged: "Charged", plan_sold: "Sold",
    // price card
    price_title: "Electricity price", buy_price: "buy", incl_transport: "incl. transport", sell_price: "sell", incl_tax: "incl", excl_tax: "excl", switch_view: "Tap to switch between buy and sell prices",
    cheapest: "cheapest", most_expensive: "most expensive", per_kwh: "/kWh",
    legend_level: "price level", legend_sell: "Sell planned", legend_buy: "Buy planned", legend_buy_line: "Buy price",
    solar_surplus: "Solar surplus", legend_surplus: "Solar surplus", surplus_full: "battery full", surplus_rate: "more than the battery can take",
    surplus_kwh: (v) => `~${v} kWh to the grid`, ed_surplus_color: "Solar surplus",
    grid_use: "From the grid", legend_grid_use: "House from the grid", ed_grid_color: "House from the grid",
    plan_export: "Solar export", plan_exported: "Exported", export_expected: "Export expected", legend_export: "Solar export",
    ed_export_color: "Solar export", tip_grid_use: "House from the grid", tip_export: "Solar export (expected)",
    no_prices: "No prices yet",
    msg_not_found: (e) => `ESS Manager: ${e} not found - choose the installation's "Status" sensor.`,
    msg_not_status: (e) => `ESS Manager: ${e} is not an ESS Manager Status sensor - choose the "Status" sensor.`,
    msg_unavailable: (e) => `ESS Manager has no data yet: ${e} is unavailable. Right after a restart that's normal for a moment; if it stays, look in Settings > System > Logs for "ess_manager".`,
    // editors
    ed_entity: "ESS Manager Status sensor", ed_title: "Title", ed_saving_color: "Saved", ed_loss_color: "More expensive", ed_colours: "Colours", ed_height: "Chart height (px)",
    ed_days: "Days", ed_show_days: "Show the day tiles", ed_show_raw: "Show the forecast without plans",
    ed_show_solar: "Show solar", ed_show_usage: "Show usage", ed_show_outlook: "Show \"without grid\"",
    ed_soc_color: "SOC", ed_solar_color: "Solar", ed_usage_color: "Usage", ed_sell_color: "Sell", ed_buy_color: "Buy",
    ed_show_extremes: "Show cheapest / most expensive", ed_show_buy_line: "Show the buy price line",
    ed_legend: "Show the legend", ed_cheap_color: "Cheap", ed_mid_color: "Average", ed_high_color: "Expensive",
    ed_negative_color: "Negative",
    ed_automation: "Your own ESS automation (when the integration doesn't control the battery itself)",
    ed_hours: "Timeline period (h)", ed_show_history: "Show the timeline",
    ed_spike_color: "Spike plan", ed_negative_plan_color: "Negative price plan",

    // EV card
    ev_title: "Electric cars", ev_sub: (n) => `charging sessions in the planning \u00b7 next ${n} days`,
    ev_sessions: (n) => `${n} ${n === 1 ? "session" : "sessions"}`,
    ev_off: "The electric car is switched off - switch it on in the integration's Configure (price plans page).",
    ev_none: "No charging sessions predicted for the coming days.", ev_none_manual: "No charging sessions yet - add one below.",
    ev_hist_legend: "solar session from history: depends on the sun \u00b7 tap to make it a fixed session",
    ev_waits: "waits for the plugged-in car - counts once it's done", ev_waits_until: (t) => `waits for the plugged-in car - counts from ${t}`,
    ev_corr: "State-of-charge correction", ev_corr_n: (n) => `${n} charge${n === 1 ? "" : "s"}`, ev_corr_wait: (n, m) => `${n} of ${m} charges measured`,
    ev_corr_tip: "What really went into the car against what its state of charge and charge efficiency said, on charges it finished while plugged in - the state-of-charge sums are multiplied by this, on top of the charge efficiency",
    ev_add: "Add manual session", ev_label_history: "average", ev_label_edited: "edited", ev_label_manual: "manual", ev_label_done: "completed",
    ev_mode_solar_hist: "solar surplus (history)", ev_mode_solar: "solar surplus", ev_charging_now: "charging now",
    ev_vc_waiting: "waiting for the answer on the phone \u00b7 ESS Manager leaves the charger alone", ev_vc_asap: "as fast as possible",
    ev_vc_external: "started on the charger itself \u00b7 charging now at its current, left alone",
    ev_vc_calm: "slowly", ev_vc_deadline: (t) => `full by ${t}`, ev_vc_any: "sun first, then the cheapest hours",
    ev_vc_grid: (w) => `grid: ${w}`, ev_vc_done: "done - the charger is stopped", ev_vc_short: (k) => `${k} short`,
    ev_vp_title: "Charge plan", ev_vp_car: "Car", ev_vp_pick: "pick the car", ev_vp_asap: "As fast as possible", ev_vp_calm: "Slowly now",
    ev_vp_deadline: "Full by a time", ev_vp_today: "Today", ev_vp_tomorrow: "Tomorrow", ev_vp_any: "Doesn't matter", ev_vp_time: "Full at",
    ev_vp_soc: "State of charge now (%)", ev_vp_kwh: "Energy to charge (kWh)", ev_vp_known: "known - leave empty to keep",
    ev_vp_go: "Start", ev_vp_cancel: "Cancel", ev_vc_change: "Change plan",
    ev_vp_hint: "The same choices as the question on the phone - that one goes away.",
    ev_now_soc: (p, k) => `now \u00b1 ${p}% \u00b7 ${k} charged`, ev_charged: (k) => `${k} charged`,
    ev_warn_none: "No solar surplus that day - this session won't charge.",
    ev_warn_short: (got, need) => `Not enough sun that day: \u00b1 ${got} of ${need}`,
    ev_edit_aria: "Edit", ev_count: "Count this session", ev_edit_running: "Edit running session", ev_edit: "Edit session", ev_new: "New session",
    ev_no_car: "No car", ev_car: "Car", ev_day: "Day", ev_start: "Start time",
    ev_running_note: "The charger is charging: day and start time are fixed, the rest can still change.",
    ev_start_soc: "Battery at start", ev_target: "Target", ev_energy: "Energy", ev_mode: "Way of charging",
    ev_fixed: "Fixed current", ev_solar: "Solar surplus", ev_current: "Charging current", ev_phases: (n) => `${n} ${n === 1 ? "phase" : "phases"}`,
    ev_solar_hint: (lo, hi) => `Charges on what the sun has left after the house, from ${lo} up to ${hi}.`,
    ev_hist_hint: "From history this session charged on the sun - switch to a fixed current to make it independent of the sun.",
    ev_hist_mark: (p) => `dash = expected battery at start according to history (${p}%)`,
    ev_back_average: "Back to average", ev_remove: "Delete", ev_cancel: "Cancel", ev_save: "Save",
    ev_left: (k) => `${k} to go`, ev_at: "done at", ev_in_plan: (k) => `${k} in the planning`,
    // the EV card as of 2026.10.29: one session model, one panel
    ev_now: "Now", ev_planned: "Planned", ev_plan_add: "Plan a session", ev_n_planned: (n) => `${n} planned`, ev_n_busy: "1 charging",
    ev_st_plugged: (c) => `${c} plugged in`, ev_st_charging: (c, kw) => `${c} charging \u00b7 ${kw}`, ev_st_done: (c) => `${c} \u00b7 done`, ev_st_running: "Charging now",
    ev_chip_wait: "waiting for a choice", ev_chip_ext: "started by the charger", ev_chip_asap: (a) => `fast \u00b7 ${a} A`, ev_chip_calm: (a) => `slow \u00b7 ${a} A`,
    ev_chip_solar: "on the sun", ev_chip_by: (t) => `full by ${t}`, ev_chip_done: "done", ev_chip_fixed: (a) => `fixed \u00b7 ${a} A`,
    ev_wait_text: "Until you choose, ESS Manager doesn't start the charger (what it starts itself goes on). The same question is on your phone.",
    ev_ext_text: "The charger started by itself and charges at its own current - ESS Manager leaves it alone until you choose.",
    ev_st_stopped: (c) => `${c} \u00b7 stopped charging`,
    ev_zappi_blocked: "The zappi is locked and won't charge - turn on \"charge when locked\" in the myenergi app.",
    ev_done_early: (soc, to) => `The car stopped at about ${soc} % instead of ${to} % - is its own charge limit set lower? Unplug the car to end the session.`,
    ev_done_early_kwh: (k) => `The car stopped with ${k} still to go by the sums - is its own charge limit set lower? Unplug the car to end the session.`,
    ev_done_text: "Full according to the sums - the charger stays as it is, the car stops by itself when it's really full. Unplug the car to end the session.",
    ev_r_by_fixed: (amps, kw, a, b) => `${amps} A \u00b7 ${kw} \u00b7 planned to be done by ${a} (an hour before ${b})`, ev_r_estimate: "prices for then not known yet: estimated as a calm charge",
    ev_pl_title: "Charge plan", ev_pl_preview: "preview - saved, the integration plans it", ev_pl_grid: "grid", ev_pl_batt: "battery", ev_pl_sun: "sun",
    ev_pl_cost: "Estimated cost", ev_pl_avg: (p) => `avg ${p}/kWh`, ev_pl_legend: "bars = price per quarter \u00b7 blue = grid \u00b7 green = house battery \u00b7 yellow = full by",
    ev_pl_batt_note: "battery: the cheapest refill after it, with the losses", ev_pl_blocks: (n) => (n === 1 ? "1 block" : `${n} blocks`), ev_pl_blocks_from: (n, t) => `${n === 1 ? "1 block" : `${n} blocks`} from ${t}`,
    ev_st_full: (c) => `${c} \u00b7 full by the sums`,
    ev_how_q: "How do you want to charge?", ev_how: "How", ev_h_asap: "Fast", ev_h_calm: "Slow", ev_h_solar: "On the sun", ev_h_by: "Full by",
    ev_h_solar_sub: "solar surplus only", ev_h_by_sub: "sun first, rest cheapest",
    ev_full_day: "Full on", ev_r_before_start: "The full-by time is before the start - pick a later day or time.", ev_when_full: "Full when", ev_d_today: "Today", ev_d_tomorrow: "Tomorrow", ev_d_any: "Doesn't matter", ev_full_at: "Full at",
    ev_soc_now: "State of charge now", ev_soc_plug: "State of charge when plugged in",
    ev_r_need: "Needed", ev_r_sun: (t) => `Sun before ${t}`, ev_r_grid: (w) => (w ? `Grid \u00b7 ${w}` : "Grid"), ev_r_speed: "Speed (calm where it costs little)",
    ev_r_end: "Full at about", ev_r_margin: (a, b) => `Planned to be done by ${a}: an hour to spare before ${b}.`,
    ev_r_tight_t: (t) => `Full by ${t} doesn't fit`, ev_r_tight: (need, max, reach, end) => `Needed ${need}. At full power (${max}) you get \u00b1 ${reach} by then. Full at about ${end}.`,
    ev_r_tight_go: "Start charges at full power", ev_r_past: "That time has passed.",
    ev_r_fixed: (k, t) => `${k} to go \u00b7 full at about ${t}`, ev_r_solar_ok: (k, t) => `${k} on the solar surplus \u00b7 full at about \u00b1 ${t}`,
    ev_r_solar_none: "No solar surplus in sight - this way it won't charge.", ev_r_solar_short: (got, need) => `Not enough sun: \u00b1 ${got} of ${need}`,
    ev_r_solar_hint: (lo, hi) => `Charges only on what the sun has left after the house (${lo} - ${hi}).`,
    ev_go_start: "Start", ev_go_save: "Save", ev_change: "Change", ev_edit_btn: "Edit", ev_phone_note: "The question on your phone goes away",
    ev_legend_grid: (a) => `Grid, ${a} A`, ev_legend_sun: "Sun", ev_none_short: "none", ev_legend_batt: (a) => `House battery, ${a} A`,
    ev_tl_from: (t) => `plugged in ${t}`, ev_tl_to: (a, b) => (a ? `done ${a} \u00b7 full by ${b}` : `full by ${b}`),
    ev_soc_line: (p, k, n) => `now \u00b1 ${p}% \u00b7 ${k} of ${n} charged`, ev_kwh_line: (k, n) => `${k} of ${n} charged`,
    ev_tight_full: "Full at about",
    ed_ev_color: "Car",
    // heat pump card
    hp_title: "Heat pump", hp_off: "The heat pump model is switched off - switch it on in the integration's Configure (price plans page).",
    hp_sub_active: (n) => `model active \u00b7 ${n} heating days`, hp_sub_learning: "model still learning", hp_sub_summer: "summer \u00b7 no heating",
    hp_sub_fallback: "model not used: 6-week average", hp_sub_correction: (p) => `model active \u00b7 correction ${p}`,
    hp_next_days: "next 5 days", hp_average: "6-week average", hp_view: "View",
    hp_tab_forecast: "Forecast", hp_tab_signature: "Signature", hp_tab_memory: "Memory",
    hp_heating_days: "Heating days in the journal", hp_learning_text: "Until there are enough days at different temperatures, the planning uses the 6-week average, as before.",
    hp_summer_text: (b) => `No heating in the coming days: only the daily base of ${b}.`,
    hp_fallback_fit: "The model isn't used right now: it doesn't fit the measured days well enough yet. The planning uses the 6-week average.",
    hp_fallback_weather: "The model isn't used right now: no weather forecast. The planning uses the 6-week average.",
    hp_corr_more: "Used more than the model said over the last days - taken along for now; the model itself doesn't change.",
    hp_corr_less: "Used less than the model said over the last days - taken along for now; the model itself doesn't change.",
    hp_setpoint_change: (d) => `Wanted temperature ${d} since a few days.`,
    hp_wind: "wind", hp_sun: "sun", hp_model: "model", hp_average_learning: "6-week average (model still learning)",
    hp_none_note: "No own metering: the bars are the household's day totals; only the weather difference is added to the planning.",
    hp_no_model: "No model yet - it needs at least two weeks of days.", hp_axis: "outdoor \u00b0C (day, smoothed)",
    hp_balance: "Balance temperature", hp_per_degree: "Per degree colder", hp_per_day: "per day", hp_base: "Base",
    hp_wind_t: "Wind", hp_wind_unit: "kWh per m/s per degree", hp_sun_t: "Sun", hp_sun_unit: "kWh per kWh of sun",
    hp_cool_t: "Cooling", hp_from: "from", hp_per_degree_short: "per degree", hp_error: "Error 14 days",
    hp_measured_day: "measured day (fainter = older)", hp_expected: "expected",
    hp_outdoor: "outdoor", hp_days: "days", hp_measured: "measured", hp_last: "last", hp_to: "to",
    hp_memory_note: (n, h) => `Frost days of last winter keep counting until a newer day of the same class comes. Journal: ${n} days, ${h} heating days.`,
    hp_house_warm: (d, ref, when, kwh) => `House ${d} warmer than ${ref}: expected to heat again from ${when} (${kwh} less).`,
    hp_house_warm_long: (d, ref, kwh) => `House ${d} warmer than ${ref}: it keeps that heat for the coming days (${kwh} less).`,
    hp_house_cold: (d, ref, kwh) => `House ${d} colder than ${ref}: ${kwh} extra to warm it up, in the coming hours.`,
    hp_at_indoor: (t) => `at ${t} \u00b0C indoor`, hp_warmer_t: "A degree warmer inside",
    hp_tab_indoor: "Indoor",
    hp_stage_learning: "Hour-by-hour model: still learning", hp_stage_shadow: "Hour-by-hour model: watching along (the planning uses the usual pattern)",
    hp_stage_used: "Hour-by-hour model: used for the planning", hp_stage_steering: "Hour-by-hour model: used, steering the thermostat",
    hp_review: (d, a, b, t) => `Self-check over ${d} heating days: energy per hour \u00b1${a} kWh (usual pattern \u00b1${b}), indoor \u00b1${t} \u00b0C.`,
    hp_review_wait: (d) => `Self-check waits for enough heating days (${d} of 10).`,
    hp_review_drift: (d, a, b) => `The newest ${d} heating days run worse (\u00b1${a} kWh per hour, pattern \u00b1${b}) - the usual pattern stays until it settles.`,
    hp_measured_in: "measured", hp_expected_in: "expected", hp_target_in: "target", hp_heat_kwh: "heating kWh", hp_heat_meas: "kWh measured", hp_heat_exp: "kWh expected",
    hp_plan_boost: (a, b) => `Warmer ${a}\u2013${b}`, hp_plan_dip: (a, b) => `cooler ${a}\u2013${b}`, hp_plan_saving: (v) => `saves about ${v}`,
    hp_cop_t: "COP at 7 / \u22122 \u00b0C", hp_cop_unit: "learned from the COP sensor", hp_floor_t: "Floor delay", hp_floor_unit: "time constant",
    hp_heatup_t: "Heat-up", hp_heatup_unit_th: "per 10 kWh of heat", hp_heatup_unit_el: "per 10 kWh",
    hp_steering: "Steering", hp_on: "On", hp_off_short: "Off", hp_day_t: "Day temperature", hp_night_t: "Night temperature",
    hp_day_from_t: "Day from", hp_night_from_t: "Night from", hp_hour: "h", hp_delta_t: "Buffer range (\u00b1)",
    hp_steer_wait: "Steering follows the day/night temperatures; the buffer starts once the hour-by-hour model has passed its self-check.",
    hp_override: (t) => `Thermostat changed by hand - steering waits until ${t}.`,
    hp_left_out: "left out", hp_heating_classes: "Temperature ranges with 3+ heating days",
    hp_left_out_note: (c, o, n) => [n ? `${n} cool day${n === 1 ? "" : "s"} without heat demand from the thermostat` : "", c ? `${c} cool day${c === 1 ? "" : "s"} on which the house lived on its stored heat (it cooled while the heat pump hardly heated)` : "", o ? `${o} day${o === 1 ? "" : "s"} far off the model (a meter jump)` : ""].filter(Boolean).join(", ") + " left out of the model.",
    hp_ref_usual: "usual at this time", hp_ref_wanted: "wanted", hp_floor: (h) => `floor keeps heating ${h} h`,
    hp_hold_t: "Heat held", hp_hold_unit: "per \u00b0C indoor", hp_cooling_t: "Cooling", hp_cooling_unit: "at 10 \u00b0C difference, not heating",
    hp_tau: (h) => `time constant ${h} h`, hp_thermal_learning: "House cooling not learned yet: it needs hours in which the heat pump didn't heat (from the indoor sensor's statistics, or what has been recorded of the thermostat's temperature).",
    ed_hp_color: "Heat pump", ed_fc_color: "Accent",
    // heat pump card, floor tab (2026.10.23)
    hp_tab_floor: "Floor", fl_mode: "Floor control", fl_mode_watch: "Watch", fl_mode_setpoint: "Return setpoint", fl_mode_full: "Full",
    fl_max_return: "Max. return setpoint",
    fl_stage_watch: "Watching along: the thermostat switches, ESS Manager learns the floor",
    fl_stage_setpoint: "ESS Manager sets the return setpoint, the thermostat switches heat demand",
    fl_stage_full: "ESS Manager heats the floor: return setpoint and heat demand",
    fl_stage_cooling: "The heat pump cools: floor control leaves it alone", fl_r_cooling: "cooling season",
    fl_waits: "A higher stage waits for", fl_wait_inputs: "a sensor, the thermostat helper or the house model's heat plan",
    fl_wait_emission: (n, need) => `the floor's heat output: ${n} of ${need} running hours`,
    fl_wait_emission_err: (e) => `the floor's heat output fits better (now ${e} % off)`,
    fl_wait_response: (n, need) => `the heat pump following the setpoint: ${n} of ${need} running hours`,
    fl_wait_house: "the house model's self-check (Indoor tab)", fl_wait_thermostat_off: "the thermostat switched on again (it's off: no heating)",
    fl_u_t: "Floor output", fl_u_unit: "kW per \u00b0C", fl_p_t: "Heat pump", fl_p_unit: "kW min - max", fl_delta_t: "Supply - return",
    fl_sp_t: "Return setpoint", fl_sp_unit: "planned / now", fl_debt_t: "Heat owed", fl_slab_t: "Floor", fl_slab_unit: "in the screed",
    fl_would: (on, why) => `${on ? "Would heat now" : "Wouldn't heat now"} - ${why}`,
    fl_is: (on, why) => `${on ? "Heating" : "Not heating"} - ${why}`,
    fl_r_heat_owed: "heat owed", fl_r_running: "heat still owed", fl_r_delivered: "the planned heat is in", fl_r_too_warm: "room too warm",
    fl_r_too_cold: "room too cold", fl_r_idle: "no heat owed",
    fl_delivered: "heat delivered", fl_planned: "heat planned", fl_sp_actual: "return setpoint", fl_sp_plan: "planned return setpoint",
    fl_note: "Heat in thermal kWh per hour. The supply and return temperatures only count with the circulation pump running.",
    fl_learned: (n, e) => `Floor output learned from ${n} running hours, ${e} % off on the newest hours.`,
    // forecast check card (2026.10.22)
    fc_title: "Forecast check", fc_sub: (n) => `last ${n} days`, fc_head_sub: "usage error per day",
    fc_tab_overview: "Overview", fc_tab_days: "Per day", fc_tab_methods: "Methods",
    fc_usage: "Usage", fc_solar: "Solar", fc_per_day: "kWh/day", fc_forecast: (v) => `forecast ${v}`,
    fc_low: (p) => `${p} % too low`, fc_high: (p) => `${p} % too high`, fc_ok: "on target", fc_corrected: "corrected:",
    fc_err: (v) => `\u00b1${v} kWh per day`, fc_days: (a, b) => `${a} of ${b} days`, fc_no_solar: "no solar production in the Energy dashboard",
    fc_solar_wait: "solar forecasts are kept from now on",
    fc_buffer: "Safety buffer", fc_advice: (v) => `advice ${v} %`, fc_now: "now",
    fc_buffer_text: (m, cm, a, ca, n) => `How often the buffer would have covered what the forecasts got wrong during the day, over the last ${n} days: ${m} % on ${cm} % of the days, ${a} % on ${ca} %.`,
    fc_buffer_wait: (have, need) => `The advice comes once ${need} days are measured (${have} so far): the solar forecasts are kept from the installation on.`,
    fc_auto: "Adjust automatically",
    fc_auto_on: (e, m) => `In use: ${e} % (the number: ${m} %). Moves at most 2 %-points a day towards the advice.`,
    fc_auto_wait: (m) => `On - until there are enough days, the number (${m} %) is used.`,
    fc_auto_off: (m) => `Off - the plans use the Safety buffer number (${m} %).`,
    fc_method: "Usage forecast", fc_m_average: (l) => `${l}-week average`, fc_m_weighted: "recent weeks weigh more",
    fc_m_level: (l) => `pattern ${l} wk + level 1 wk`,
    fc_level_text: (p, n) => `Level now ${p} (limits 0.80-1.25). Clearly better than the average in the backtest over ${n} days, so in use.`,
    fc_weighted_text: (n) => `Clearly better than the average in the backtest over ${n} days, so in use.`,
    fc_avg_text: (n) => `In the backtest over ${n} days no other method was clearly better, so the average stays.`,
    fc_learning: (have, need) => `The backtest needs ${need} complete days (${have} so far); until then the average stays.`,
    fc_excl: (list) => `Without ${list} - they have their own forecast.`, fc_hp: "heat pump", fc_ev: "car", fc_and: "and",
    fc_measured: "measured", fc_forecast_l: "forecast", fc_usage_day: "Usage per day", fc_solar_day: "Solar per day",
    fc_avg_err: (v) => `avg \u00b1${v} kWh`,
    fc_days_note: "Usage is recalculated from the statistics, so it's complete from day one. Solar forecasts are kept from the installation on (grey = no forecast yet).",
    fc_col_method: "usage forecast", fc_col_err: "error", fc_col_bias: "bias", fc_in_use: "in use",
    fc_methods_note: (n) => `Backtest over the last ${n} complete days, kWh per day. "Bias": on average forecast too low (-) or too high (+). A method is only used when it is clearly (5 %) better.`,
    fc_waiting: "The first check runs within a few minutes.",
  },
  nl: {
    planned: "gepland", running: "bezig", done: "klaar", of: "van", stop: "stop",
    left: (d) => `nog ${d}`, no_sell: "Geen sale gepland", no_buy: "Geen laadactie gepland",
    spike: "Piek", negative: "Negatieve prijs", balancing: "Balanceren", balancing_max: (d) => `max ${d}`, cell_diff: "Celspanningsverschil", pack_voltage: "Accuspanning",
    more_blocks: (n) => `+${n}`, more_blocks_tip: (n) => `en nog ${n} ${n === 1 ? "blok" : "blokken"}`,
    balance_after: (t) => `daarna balanceren op 100 % tot uiterlijk ${t}`,
    active: "Actief", inactive: "Inactief", below: "onder", auto_control: "Automatische aansturing",
    h: "u", min: "min", ago: (h) => `-${h} u`, now: "nu", settings: "Instellingen",
    battery_title: "Batterijprognose", today: "vandaag", horizon: "planningshorizon",
    offgrid_empty: (w) => `zonder stroomnet leeg ${w}`, offgrid_full: (w) => `zonder stroomnet vol ${w}`,
    offgrid_days: "zonder stroomnet 5+ dagen", measured: "gemeten", expected: "verwacht",
    soc: "SOC", without_plans: "Zonder plannen", solar: "Zon", usage: "Verbruik", price: "Prijs",
    min_label: (p) => `min ${p} %`, max_label: (p) => `max ${p} %`,
    plan_sell: "Verkoop", plan_buy: "Laden", plan_spike: "Piek", plan_negative: "Negatieve prijs",
    pp_title: "Planning", pp_close: "Sluiten", pp_none: "Niets gepland", pp_now: "nu", pp_next: "volgende",
    pp_charge: "Laden", pp_sell: "Verkoop", pp_grid: "Uit het net", pp_full_charge: "Volle lading", pp_balancing: "Balanceren",
    pp_spike_charge: "Piek: laden", pp_spike_sell: "Piek: verkoop", pp_negative_charge: "Negatieve prijs: laden",
    pp_negative_sell: "Negatieve prijs: vooraf ontladen", pp_solar_export: "Teruglevering", pp_surplus: "Zonoverschot",
    balance_until: (t) => `balanceren tot ${t}`,
    plan_grid: "Uit het net", no_grid: "Geen net-gebruik gepland", grid_kept: "kWh blijft in de accu", grid_kept_short: "kWh bewaard", none_short: "geen",
    grid_sun: "zon dekt het huis", grid_sun_tip: "Volgens de voorspelling dekt de zon het huis - een onverwacht verbruik of een piek komt uit het net, niet uit de accu.", grid_more_tip: (n) => `en nog ${n} ${n === 1 ? "blok" : "blokken"}`,
    plan_full: "Vol laden", plan_charged: "Geladen", plan_sold: "Verkocht",
    price_title: "Stroomprijs", buy_price: "inkoop", incl_transport: "incl. transport", sell_price: "verkoop", incl_tax: "incl", excl_tax: "excl", switch_view: "Tik om te wisselen tussen inkoop- en verkoopprijzen",
    cheapest: "goedkoopst", most_expensive: "duurst", per_kwh: "/kWh",
    legend_level: "prijsniveau", legend_sell: "Verkoop gepland", legend_buy: "Laden gepland", legend_buy_line: "Inkoopprijs",
    solar_surplus: "Zonoverschot", legend_surplus: "Zonoverschot", surplus_full: "accu vol", surplus_rate: "meer dan de accu kan laden",
    surplus_kwh: (v) => `~${v} kWh naar het net`, ed_surplus_color: "Zonoverschot",
    grid_use: "Uit het net", legend_grid_use: "Huis uit het net", ed_grid_color: "Huis uit het net",
    plan_export: "Teruglevering", plan_exported: "Teruggeleverd", export_expected: "Teruglevering verwacht", legend_export: "Teruglevering",
    ed_export_color: "Teruglevering", tip_grid_use: "Huis uit het net", tip_export: "Teruglevering (verwacht)",
    no_prices: "Nog geen prijzen",
    msg_not_found: (e) => `ESS Manager: ${e} niet gevonden - kies de "Status"-sensor van de installatie.`,
    msg_not_status: (e) => `ESS Manager: ${e} is geen ESS Manager Status-sensor - kies de "Status"-sensor.`,
    msg_unavailable: (e) => `ESS Manager heeft nog geen gegevens: ${e} is niet beschikbaar. Vlak na een herstart is dat even normaal; blijft het zo, kijk dan in Instellingen > Systeem > Logboeken naar "ess_manager".`,
    ed_entity: "ESS Manager Status-sensor", ed_title: "Titel", ed_saving_color: "Bespaard", ed_loss_color: "Duurder", ed_colours: "Kleuren", ed_height: "Hoogte grafiek (px)",
    ed_days: "Dagen", ed_show_days: "Dagtegels tonen", ed_show_raw: "Voorspelling zonder plannen tonen",
    ed_show_solar: "Zon tonen", ed_show_usage: "Verbruik tonen", ed_show_outlook: "\"Zonder stroomnet\" tonen",
    ed_soc_color: "SOC", ed_solar_color: "Zon", ed_usage_color: "Verbruik", ed_sell_color: "Verkoop", ed_buy_color: "Laden",
    ed_show_extremes: "Goedkoopst / duurst tonen", ed_show_buy_line: "Lijn met inkoopprijs tonen",
    ed_legend: "Legenda tonen", ed_cheap_color: "Goedkoop", ed_mid_color: "Gemiddeld", ed_high_color: "Duur",
    ed_negative_color: "Negatief",
    ed_automation: "Je eigen ESS-automatisering (als de integratie de accu niet zelf aanstuurt)",
    ed_hours: "Periode tijdlijn (u)", ed_show_history: "Tijdlijn tonen",
    ed_spike_color: "Spike-plan", ed_negative_plan_color: "Negatieve-prijsplan",

    ev_title: "Elektrische auto's", ev_sub: (n) => `laadsessies in de planning \u00b7 komende ${n} dagen`,
    ev_sessions: (n) => `${n} ${n === 1 ? "sessie" : "sessies"}`,
    ev_off: "De elektrische auto staat uit - zet hem aan bij Configureren van de integratie (pagina prijsplannen).",
    ev_none: "Geen laadsessies voorspeld voor de komende dagen.", ev_none_manual: "Nog geen laadsessies - voeg er hieronder een toe.",
    ev_hist_legend: "zon-sessie volgens de historie: hangt van de zon af \u00b7 tik om er een vaste sessie van te maken",
    ev_waits: "wacht op de aangesloten auto - telt mee als die klaar is", ev_waits_until: (t) => `wacht op de aangesloten auto - telt mee vanaf ${t}`,
    ev_corr: "Laadstandcorrectie", ev_corr_n: (n) => `${n} laadbeurt${n === 1 ? "" : "en"}`, ev_corr_wait: (n, m) => `${n} van ${m} laadbeurten gemeten`,
    ev_corr_tip: "Wat er werkelijk in de auto ging tegenover wat de laadstand en het laadrendement zeiden, gemeten op laadbeurten die de auto afmaakte terwijl hij aangesloten was - de laadstandsommen worden hiermee vermenigvuldigd, bovenop het laadrendement",
    ev_add: "Handmatige sessie toevoegen", ev_label_history: "gemiddelde", ev_label_edited: "aangepast", ev_label_manual: "handmatig", ev_label_done: "voltooid",
    ev_mode_solar_hist: "zon-overschot (historie)", ev_mode_solar: "zon-overschot", ev_charging_now: "laadt nu",
    ev_vc_waiting: "wacht op het antwoord op de telefoon \u00b7 ESS Manager laat de lader met rust", ev_vc_asap: "zo snel mogelijk",
    ev_vc_external: "door de lader zelf gestart \u00b7 laadt nu op zijn eigen stroom, ESS Manager laat hem met rust",
    ev_vc_calm: "rustig", ev_vc_deadline: (t) => `vol om ${t}`, ev_vc_any: "eerst de zon, dan de goedkoopste uren",
    ev_vc_grid: (w) => `net: ${w}`, ev_vc_done: "klaar - de lader staat stil", ev_vc_short: (k) => `${k} tekort`,
    ev_vp_title: "Laadplan", ev_vp_car: "Auto", ev_vp_pick: "kies de auto", ev_vp_asap: "Zo snel mogelijk", ev_vp_calm: "Nu rustig",
    ev_vp_deadline: "Vol voor tijd X", ev_vp_today: "Vandaag", ev_vp_tomorrow: "Morgen", ev_vp_any: "Maakt niet uit", ev_vp_time: "Vol om",
    ev_vp_soc: "Laadstand nu (%)", ev_vp_kwh: "Energie erin (kWh)", ev_vp_known: "bekend - leeg laten om te houden",
    ev_vp_go: "Start", ev_vp_cancel: "Annuleren", ev_vc_change: "Plan wijzigen",
    ev_vp_hint: "Dezelfde keuzes als de vraag op de telefoon - die verdwijnt dan.",
    ev_now_soc: (p, k) => `nu \u00b1 ${p}% \u00b7 ${k} geladen`, ev_charged: (k) => `${k} geladen`,
    ev_warn_none: "Geen zon-overschot die dag - deze sessie laadt niet.",
    ev_warn_short: (got, need) => `Te weinig zon die dag: \u00b1 ${got} van ${need}`,
    ev_edit_aria: "Bewerk", ev_count: "Sessie meenemen", ev_edit_running: "Lopende sessie bewerken", ev_edit: "Sessie bewerken", ev_new: "Nieuwe sessie",
    ev_no_car: "Geen auto", ev_car: "Auto", ev_day: "Dag", ev_start: "Starttijd",
    ev_running_note: "De laadpaal laadt (vermogen > 0): dag en starttijd liggen vast, de rest kun je nog aanpassen.",
    ev_start_soc: "Accu bij start", ev_target: "Doel", ev_energy: "Energie", ev_mode: "Manier van laden",
    ev_fixed: "Vast vermogen", ev_solar: "Zon-overschot", ev_current: "Laadstroom", ev_phases: (n) => `${n} ${n === 1 ? "fase" : "fasen"}`,
    ev_solar_hint: (lo, hi) => `Laadt op wat de zon na het huis overhoudt, van ${lo} tot ${hi}.`,
    ev_hist_hint: "Volgens de historie laadde deze sessie op de zon - kies vast vermogen om hem los van de zon te maken.",
    ev_hist_mark: (p) => `streepje = verwachte stand bij start volgens historie (${p}%)`,
    ev_back_average: "Terug naar gemiddelde", ev_remove: "Verwijderen", ev_cancel: "Annuleren", ev_save: "Opslaan",
    ev_left: (k) => `Nog ${k}`, ev_at: "klaar om", ev_in_plan: (k) => `${k} in de planning`,
    ev_now: "Nu", ev_planned: "Gepland", ev_plan_add: "Sessie plannen", ev_n_planned: (n) => `${n} gepland`, ev_n_busy: "1 bezig",
    ev_st_plugged: (c) => `${c} aangesloten`, ev_st_charging: (c, kw) => `${c} laadt \u00b7 ${kw}`, ev_st_done: (c) => `${c} \u00b7 klaar`, ev_st_running: "Laadt nu",
    ev_chip_wait: "wacht op keuze", ev_chip_ext: "door lader gestart", ev_chip_asap: (a) => `snel \u00b7 ${a} A`, ev_chip_calm: (a) => `rustig \u00b7 ${a} A`,
    ev_chip_solar: "op zon", ev_chip_by: (t) => `vol om ${t}`, ev_chip_done: "klaar", ev_chip_fixed: (a) => `vast \u00b7 ${a} A`,
    ev_wait_text: "Tot je kiest start ESS Manager de lader niet (wat de lader zelf start, loopt door). Dezelfde vraag staat op je telefoon.",
    ev_ext_text: "De lader is zelf begonnen en laadt op zijn eigen stroom - ESS Manager laat hem met rust tot je kiest.",
    ev_st_stopped: (c) => `${c} \u00b7 gestopt met laden`,
    ev_zappi_blocked: "De zappi is vergrendeld en laadt niet - zet \"laden als vergrendeld\" aan in de myenergi-app.",
    ev_done_early: (soc, to) => `De auto stopte rond ${soc} % in plaats van ${to} % - staat de laadlimiet in de auto lager? Koppel de auto los om de sessie af te sluiten.`,
    ev_done_early_kwh: (k) => `De auto stopte terwijl er volgens de berekening nog ${k} bij moest - staat de laadlimiet in de auto lager? Koppel de auto los om de sessie af te sluiten.`,
    ev_done_text: "Vol volgens de berekening - de lader blijft zoals hij staat, de auto stopt zelf als hij echt vol is. Koppel de auto los om de sessie af te sluiten.",
    ev_r_by_fixed: (amps, kw, a, b) => `${amps} A \u00b7 ${kw} \u00b7 gepland klaar om ${a} (een uur voor ${b})`, ev_r_estimate: "prijzen voor dan nog niet bekend: geschat als rustige lading",
    ev_pl_title: "Laadplan", ev_pl_preview: "voorbeeld - na opslaan plant de integratie het", ev_pl_grid: "net", ev_pl_batt: "accu", ev_pl_sun: "zon",
    ev_pl_cost: "Geschatte kosten", ev_pl_avg: (p) => `gem. ${p}/kWh`, ev_pl_legend: "balkjes = prijs per kwartier \u00b7 blauw = net \u00b7 groen = thuisaccu \u00b7 geel = vol om",
    ev_pl_batt_note: "accu: goedkoopste aanvulmoment daarna, met de verliezen", ev_pl_blocks: (n) => (n === 1 ? "1 blok" : `${n} blokken`), ev_pl_blocks_from: (n, t) => `${n === 1 ? "1 blok" : `${n} blokken`} vanaf ${t}`,
    ev_st_full: (c) => `${c} \u00b7 vol volgens berekening`,
    ev_how_q: "Hoe wil je laden?", ev_how: "Hoe", ev_h_asap: "Snel", ev_h_calm: "Rustig", ev_h_solar: "Op zon", ev_h_by: "Vol om",
    ev_h_solar_sub: "alleen zon-overschot", ev_h_by_sub: "zon eerst, rest goedkoopst",
    ev_full_day: "Vol op", ev_r_before_start: "De vol-om-tijd ligt voor de start - kies een latere dag of tijd.", ev_when_full: "Wanneer vol", ev_d_today: "Vandaag", ev_d_tomorrow: "Morgen", ev_d_any: "Maakt niet uit", ev_full_at: "Vol om",
    ev_soc_now: "Laadstand nu", ev_soc_plug: "Laadstand bij aansluiten",
    ev_r_need: "Nodig", ev_r_sun: (t) => `Zon voor ${t}`, ev_r_grid: (w) => (w ? `Net \u00b7 ${w}` : "Net"), ev_r_speed: "Snelheid (rustig waar het weinig kost)",
    ev_r_end: "Vol rond", ev_r_margin: (a, b) => `Gepland klaar om ${a}: een uur speling voor ${b}.`,
    ev_r_tight_t: (t) => `Vol om ${t} lukt niet`, ev_r_tight: (need, max, reach, end) => `Nodig ${need}. Op vol vermogen (${max}) haal je tot dan \u00b1 ${reach}. Vol rond ${end}.`,
    ev_r_tight_go: "Start laadt dan op vol vermogen", ev_r_past: "Die tijd is al voorbij.",
    ev_r_fixed: (k, t) => `nog ${k} \u00b7 vol rond ${t}`, ev_r_solar_ok: (k, t) => `${k} op zon-overschot \u00b7 vol rond \u00b1 ${t}`,
    ev_r_solar_none: "Geen zon-overschot in zicht - zo laadt hij niet.", ev_r_solar_short: (got, need) => `Te weinig zon: \u00b1 ${got} van ${need}`,
    ev_r_solar_hint: (lo, hi) => `Laadt alleen op wat de zon na het huis over heeft (${lo} - ${hi}).`,
    ev_go_start: "Start", ev_go_save: "Opslaan", ev_change: "Wijzigen", ev_edit_btn: "Bewerken", ev_phone_note: "De vraag op je telefoon verdwijnt",
    ev_legend_grid: (a) => `Net, ${a} A`, ev_legend_sun: "Zon", ev_none_short: "geen", ev_legend_batt: (a) => `Thuisaccu, ${a} A`,
    ev_tl_from: (t) => `aangesloten ${t}`, ev_tl_to: (a, b) => (a ? `klaar ${a} \u00b7 vol om ${b}` : `vol om ${b}`),
    ev_soc_line: (p, k, n) => `nu \u00b1 ${p}% \u00b7 ${k} van ${n} geladen`, ev_kwh_line: (k, n) => `${k} van ${n} geladen`,
    ev_tight_full: "Vol rond",
    ed_ev_color: "Auto",
    hp_title: "Warmtepomp", hp_off: "Het warmtepompmodel staat uit - zet het aan bij Configureren van de integratie (pagina prijsplannen).",
    hp_sub_active: (n) => `model actief \u00b7 ${n} stookdagen`, hp_sub_learning: "model leert nog", hp_sub_summer: "zomer \u00b7 niet stoken",
    hp_sub_fallback: "model niet gebruikt: 6-weken-gemiddelde", hp_sub_correction: (p) => `model actief \u00b7 correctie ${p}`,
    hp_next_days: "komende 5 dagen", hp_average: "6-weken-gemiddelde", hp_view: "Weergave",
    hp_tab_forecast: "Verwachting", hp_tab_signature: "Signatuur", hp_tab_memory: "Geheugen",
    hp_heating_days: "Stookdagen in het dagboek", hp_learning_text: "Tot er genoeg dagen met verschillende temperaturen zijn, rekent de planning met het 6-weken-gemiddelde, zoals nu.",
    hp_summer_text: (b) => `De komende dagen niet stoken: alleen de vaste basis van ${b} per dag.`,
    hp_fallback_fit: "Het model wordt nu niet gebruikt: het past nog niet goed genoeg bij de gemeten dagen. De planning rekent met het 6-weken-gemiddelde.",
    hp_fallback_weather: "Het model wordt nu niet gebruikt: geen weersverwachting. De planning rekent met het 6-weken-gemiddelde.",
    hp_corr_more: "De laatste dagen meer verbruikt dan het model zei - tijdelijk meegenomen; het model zelf verandert er niet door.",
    hp_corr_less: "De laatste dagen minder verbruikt dan het model zei - tijdelijk meegenomen; het model zelf verandert er niet door.",
    hp_setpoint_change: (d) => `Gewenste temperatuur sinds een paar dagen ${d}.`,
    hp_wind: "wind", hp_sun: "zon", hp_model: "model", hp_average_learning: "6-weken-gemiddelde (model leert nog)",
    hp_none_note: "Geen eigen meting: de balken zijn de dagtotalen van het huis; alleen het verschil door het weer gaat de planning in.",
    hp_no_model: "Nog geen model - daar zijn minstens twee weken aan dagen voor nodig.", hp_axis: "buiten \u00b0C (etmaal, uitgevlakt)",
    hp_balance: "Grenstemperatuur", hp_per_degree: "Per graad kouder", hp_per_day: "per dag", hp_base: "Basis",
    hp_wind_t: "Wind", hp_wind_unit: "kWh per m/s per graad", hp_sun_t: "Zon", hp_sun_unit: "kWh per kWh zon",
    hp_cool_t: "Koelen", hp_from: "vanaf", hp_per_degree_short: "per graad", hp_error: "Afwijking 14 dagen",
    hp_measured_day: "gemeten dag (vager = ouder)", hp_expected: "verwachting",
    hp_outdoor: "buiten", hp_days: "dagen", hp_measured: "gemeten", hp_last: "laatst", hp_to: "tot",
    hp_memory_note: (n, h) => `Vorstdagen van vorige winter tellen mee tot er een nieuwere dag in dezelfde klasse is. Dagboek: ${n} dagen, ${h} stookdagen.`,
    hp_house_warm: (d, ref, when, kwh) => `Huis ${d} warmer dan ${ref}: stookt naar verwachting pas weer vanaf ${when} (${kwh} minder).`,
    hp_house_warm_long: (d, ref, kwh) => `Huis ${d} warmer dan ${ref}: houdt die warmte de komende dagen vast (${kwh} minder).`,
    hp_house_cold: (d, ref, kwh) => `Huis ${d} kouder dan ${ref}: ${kwh} extra om op te warmen, de komende uren.`,
    hp_at_indoor: (t) => `bij ${t} \u00b0C binnen`, hp_warmer_t: "Graad warmer binnen",
    hp_tab_indoor: "Binnen",
    hp_stage_learning: "Uurmodel: leert nog", hp_stage_shadow: "Uurmodel: kijkt mee (de planning gebruikt het gebruikelijke patroon)",
    hp_stage_used: "Uurmodel: gebruikt voor de planning", hp_stage_steering: "Uurmodel: gebruikt, stuurt de thermostaat",
    hp_review: (d, a, b, t) => `Zelfcontrole over ${d} stookdagen: energie per uur \u00b1${a} kWh (gebruikelijk patroon \u00b1${b}), binnen \u00b1${t} \u00b0C.`,
    hp_review_wait: (d) => `Zelfcontrole wacht op genoeg stookdagen (${d} van 10).`,
    hp_review_drift: (d, a, b) => `De nieuwste ${d} stookdagen lopen slechter (\u00b1${a} kWh per uur, patroon \u00b1${b}) - het vaste patroon blijft tot het weer klopt.`,
    hp_measured_in: "gemeten", hp_expected_in: "verwacht", hp_target_in: "doel", hp_heat_kwh: "verwarming kWh", hp_heat_meas: "kWh gemeten", hp_heat_exp: "kWh verwacht",
    hp_plan_boost: (a, b) => `Warmer ${a}\u2013${b}`, hp_plan_dip: (a, b) => `koeler ${a}\u2013${b}`, hp_plan_saving: (v) => `bespaart ongeveer ${v}`,
    hp_cop_t: "COP bij 7 / \u22122 \u00b0C", hp_cop_unit: "geleerd van de COP-sensor", hp_floor_t: "Vertraging vloer", hp_floor_unit: "tijdconstante",
    hp_heatup_t: "Opwarmen", hp_heatup_unit_th: "per 10 kWh warmte", hp_heatup_unit_el: "per 10 kWh",
    hp_steering: "Sturing", hp_on: "Aan", hp_off_short: "Uit", hp_day_t: "Temperatuur overdag", hp_night_t: "Temperatuur 's nachts",
    hp_day_from_t: "Dag vanaf", hp_night_from_t: "Nacht vanaf", hp_hour: "uur", hp_delta_t: "Bufferbereik (\u00b1)",
    hp_steer_wait: "De sturing volgt de dag- en nachttemperatuur; de buffer begint zodra het uurmodel zijn zelfcontrole heeft gehaald.",
    hp_override: (t) => `Thermostaat met de hand aangepast - de sturing wacht tot ${t}.`,
    hp_left_out: "weggelaten", hp_heating_classes: "Temperatuurklassen met 3+ stookdagen",
    hp_left_out_note: (c, o, n) => [n ? `${n} koele dag${n === 1 ? "" : "en"} zonder warmtevraag van de thermostaat` : "", c ? `${c} koele dag${c === 1 ? "" : "en"} waarop het huis op zijn opgeslagen warmte teerde (het koelde af terwijl de warmtepomp nauwelijks stookte)` : "", o ? `${o} dag${o === 1 ? "" : "en"} ver naast het model (een meetsprong)` : ""].filter(Boolean).join(", ") + " niet meegenomen in het model.",
    hp_ref_usual: "gebruikelijk om deze tijd", hp_ref_wanted: "gewenst", hp_floor: (h) => `vloer warmt ${h} uur na`,
    hp_hold_t: "Warmte vasthouden", hp_hold_unit: "per \u00b0C binnen", hp_cooling_t: "Afkoelen", hp_cooling_unit: "bij 10 \u00b0C verschil, zonder stoken",
    hp_tau: (h) => `tijdconstante ${h} uur`, hp_thermal_learning: "Afkoelsnelheid van het huis nog niet geleerd: daar zijn uren voor nodig waarin de warmtepomp niet stookte (uit de statistieken van de binnensensor, of wat er van de temperatuur van de thermostaat is bijgehouden).",
    ed_hp_color: "Warmtepomp", ed_fc_color: "Accent",
    fl_max_return: "Max. retoursetpoint",
    hp_tab_floor: "Vloer", fl_mode: "Vloersturing", fl_mode_watch: "Meekijken", fl_mode_setpoint: "Retoursetpoint", fl_mode_full: "Volledig",
    fl_stage_watch: "Meekijken: de thermostaat schakelt, ESS Manager leert de vloer",
    fl_stage_setpoint: "ESS Manager zet het retoursetpoint, de thermostaat schakelt de warmtevraag",
    fl_stage_full: "ESS Manager stookt de vloer: retoursetpoint en warmtevraag",
    fl_stage_cooling: "De warmtepomp koelt: de vloersturing doet niets", fl_r_cooling: "koelseizoen",
    fl_waits: "Een hogere stap wacht op", fl_wait_inputs: "een sensor, de hulpschakelaar van de thermostaat of het warmteplan van het huismodel",
    fl_wait_emission: (n, need) => `de warmteafgifte van de vloer: ${n} van ${need} draaiuren`,
    fl_wait_emission_err: (e) => `een betere fit van de warmteafgifte (nu ${e} % ernaast)`,
    fl_wait_response: (n, need) => `de warmtepomp die het setpoint volgt: ${n} van ${need} draaiuren`,
    fl_wait_house: "de zelfcontrole van het huismodel (tabblad Binnen)", fl_wait_thermostat_off: "de thermostaat weer aan (hij staat uit: niet stoken)",
    fl_u_t: "Afgifte vloer", fl_u_unit: "kW per \u00b0C", fl_p_t: "Warmtepomp", fl_p_unit: "kW min - max", fl_delta_t: "Aanvoer - retour",
    fl_sp_t: "Retoursetpoint", fl_sp_unit: "gepland / nu", fl_debt_t: "Warmte te goed", fl_slab_t: "Vloer", fl_slab_unit: "in de dekvloer",
    fl_would: (on, why) => `${on ? "Zou nu stoken" : "Zou nu niet stoken"} - ${why}`,
    fl_is: (on, why) => `${on ? "Stookt" : "Stookt niet"} - ${why}`,
    fl_r_heat_owed: "warmte te goed", fl_r_running: "nog warmte te goed", fl_r_delivered: "de geplande warmte zit erin", fl_r_too_warm: "kamer te warm",
    fl_r_too_cold: "kamer te koud", fl_r_idle: "geen warmte te goed",
    fl_delivered: "warmte geleverd", fl_planned: "warmte gepland", fl_sp_actual: "retoursetpoint", fl_sp_plan: "gepland retoursetpoint",
    fl_note: "Warmte in thermische kWh per uur. De aanvoer- en retourtemperatuur tellen alleen als de circulatiepomp draait.",
    fl_learned: (n, e) => `Afgifte vloer geleerd uit ${n} draaiuren, ${e} % ernaast op de nieuwste uren.`,
    fc_title: "Prognose-check", fc_sub: (n) => `laatste ${n} dagen`, fc_head_sub: "afwijking verbruik per dag",
    fc_tab_overview: "Overzicht", fc_tab_days: "Per dag", fc_tab_methods: "Methodes",
    fc_usage: "Verbruik", fc_solar: "Zon", fc_per_day: "kWh/dag", fc_forecast: (v) => `voorspeld ${v}`,
    fc_low: (p) => `${p} % te laag`, fc_high: (p) => `${p} % te hoog`, fc_ok: "klopt", fc_corrected: "gecorrigeerd:",
    fc_err: (v) => `\u00b1${v} kWh per dag`, fc_days: (a, b) => `${a} van ${b} dagen`, fc_no_solar: "geen zonneopbrengst in het Energy dashboard",
    fc_solar_wait: "zonnevoorspellingen worden vanaf nu bewaard",
    fc_buffer: "Veiligheidsbuffer", fc_advice: (v) => `advies ${v} %`, fc_now: "nu",
    fc_buffer_text: (m, cm, a, ca, n) => `Hoe vaak de buffer genoeg was geweest om op te vangen wat de voorspellingen in de loop van de dag misten, over de laatste ${n} dagen: ${m} % op ${cm} % van de dagen, ${a} % op ${ca} %.`,
    fc_buffer_wait: (have, need) => `Het advies komt zodra er ${need} dagen gemeten zijn (nu ${have}): de zonnevoorspellingen worden vanaf de installatie bewaard.`,
    fc_auto: "Automatisch bijsturen",
    fc_auto_on: (e, m) => `In gebruik: ${e} % (handmatig: ${m} %). Beweegt maximaal 2 %-punt per dag richting het advies.`,
    fc_auto_wait: (m) => `Aan - tot er genoeg dagen zijn, geldt de handmatige ${m} %.`,
    fc_auto_off: (m) => `Uit - de planning gebruikt de ingestelde ${m} %.`,
    fc_method: "Verbruiksvoorspelling", fc_m_average: (l) => `${l}-weken-gemiddelde`, fc_m_weighted: "recente weken zwaarder",
    fc_m_level: (l) => `patroon ${l} wk + niveau 1 wk`,
    fc_level_text: (p, n) => `Niveau nu ${p} (grens 0,80-1,25). In de terugtest over ${n} dagen duidelijk beter dan het gemiddelde, dus in gebruik.`,
    fc_weighted_text: (n) => `In de terugtest over ${n} dagen duidelijk beter dan het gemiddelde, dus in gebruik.`,
    fc_avg_text: (n) => `In de terugtest over ${n} dagen was geen andere methode duidelijk beter, dus het gemiddelde blijft.`,
    fc_learning: (have, need) => `De terugtest heeft ${need} complete dagen nodig (nu ${have}); tot dan blijft het gemiddelde.`,
    fc_excl: (list) => `Zonder ${list} - die hebben een eigen voorspelling.`, fc_hp: "warmtepomp", fc_ev: "auto", fc_and: "en",
    fc_measured: "gemeten", fc_forecast_l: "voorspeld", fc_usage_day: "Verbruik per dag", fc_solar_day: "Zon per dag",
    fc_avg_err: (v) => `gem. \u00b1${v} kWh`,
    fc_days_note: "Verbruik is terugberekend uit de statistieken, dus vanaf dag 1 compleet. Zonnevoorspellingen worden pas vanaf de installatie bewaard (grijs = nog geen voorspelling).",
    fc_col_method: "verbruiksvoorspelling", fc_col_err: "afwijking", fc_col_bias: "scheef", fc_in_use: "in gebruik",
    fc_methods_note: (n) => `Terugtest over de laatste ${n} complete dagen, kWh per dag. "Scheef": gemiddeld te laag (-) of te hoog (+) voorspeld. Een methode wordt alleen gebruikt als hij duidelijk (5 %) beter is.`,
    fc_waiting: "De eerste controle volgt binnen een paar minuten.",
  },
};

function hassLang(hass) {
  return (hass && ((hass.locale && hass.locale.language) || hass.language)) || "en";
}

// The Status sensor's states shown in the user's language (as of 2026.10.44);
// the state itself stays English - automations listen to those texts.
const STATUS_NL = {
  Standby: "Stand-by", "Start charge": "Start laden", Actief: "Actief", "Start discharge": "Start ontladen", Stop: "Stop",
  "House from grid": "Huis uit het net", "Solar export": "Teruglevering",
  "Start negative price charge": "Start laden (negatieve prijs)", "Negative price charge": "Laden (negatieve prijs)",
  "Start spike discharge": "Start piekverkoop", "Spike discharge": "Piekverkoop",
  "Full charge scheduled": "Vol laden gepland", "Awaiting solar (full charge)": "Wacht op zon (vol laden)",
};

function statusText(hass, state) {
  return hassLang(hass).slice(0, 2) === "nl" && STATUS_NL[state] ? STATUS_NL[state] : state;
}

function tr(hass, key) {
  const table = I18N[hassLang(hass).slice(0, 2)] || I18N.en;
  return key in table ? table[key] : I18N.en[key];
}

// Times are shown in Home Assistant's time zone, unless the user's profile
// says "use my device's time zone".
function hassTimeZone(hass) {
  if (hass && hass.locale && hass.locale.time_zone === "local") return undefined;
  return (hass && hass.config && hass.config.time_zone) || undefined;
}

const _formats = {};
function formats(hass) {
  const lang = hassLang(hass);
  const tz = hassTimeZone(hass);
  const currency = (hass && hass.config && hass.config.currency) || "EUR";
  const key = `${lang}|${tz}|${currency}`;
  if (_formats[key]) return _formats[key];
  const make = (options, fallbackOptions) => {
    try {
      return new Intl.DateTimeFormat(lang, { ...options, timeZone: tz });
    } catch (err) {
      return new Intl.DateTimeFormat("en", fallbackOptions || options);
    }
  };
  const time = make({ hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const weekday = make({ weekday: "short" });
  const weekdayLong = make({ weekday: "long" });
  const dayLabel = make({ weekday: "short", day: "numeric" });
  const clock = make({ hour: "numeric", minute: "numeric", hourCycle: "h23" });
  let money;
  try {
    money = new Intl.NumberFormat(lang, { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } catch (err) {
    money = new Intl.NumberFormat("en", { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  const numbers = {};
  _formats[key] = {
    time: (ms) => time.format(ms),
    weekday: (ms) => weekday.format(ms),
    weekdayLong: (ms) => weekdayLong.format(ms),
    dayLabel: (ms) => dayLabel.format(ms),
    // [hour, minute] on the wall clock of the shown time zone
    clock: (ms) => {
      const parts = clock.formatToParts(ms);
      const get = (type) => Number((parts.find((p) => p.type === type) || {}).value || 0);
      return [get("hour") % 24, get("minute")];
    },
    num: (value, digits) => {
      if (!numbers[digits]) numbers[digits] = new Intl.NumberFormat(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits });
      return numbers[digits].format(value);
    },
    money: (value) => money.format(value),
  };
  return _formats[key];
}

// Local midnight (in the shown time zone) of the day `ms` falls in, and the
// next one - 23 or 25 hours later on a daylight saving day.
function localMidnight(hass, ms) {
  const [hour, minute] = formats(hass).clock(ms);
  let t = Math.floor(ms / 60000) * 60000 - (hour * 60 + minute) * 60000;
  // On a daylight saving day the clock moved since midnight, so the clock
  // time alone lands an hour off (01:00 or 23:00) - as of 2026.10.26; up to
  // then the cards started that day an hour late (price card shifted, no
  // measured solar / usage left of "now" on the battery card).
  const [h] = formats(hass).clock(t);
  if (h === 1) t -= HOUR_MS;
  else if (h === 23) t += HOUR_MS;
  return t;
}
function nextMidnight(hass, ms) {
  let t = ms + 24 * HOUR_MS;
  const [hour] = formats(hass).clock(t);
  if (hour === 23) t += HOUR_MS;
  else if (hour === 1) t -= HOUR_MS;
  return t;
}

// -- Shared helpers ---------------------------------------------------------------
// Colours: [r, g, b] (what the card editor's colour picker gives) or a
// "#rrggbb" string in YAML.
const NAMED_COLORS = { green: "#008000", yellow: "#ffff00", red: "#ff0000", blue: "#0000ff", orange: "#ffa500", purple: "#800080" };
function hexToRgb(hex) {
  const text = String(hex || "").trim();
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(NAMED_COLORS[text.toLowerCase()] || text);
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : null;
}
function toHex(color) {
  if (Array.isArray(color) && color.length === 3) {
    return "#" + color.map((c) => Math.min(Math.max(Math.round(Number(c) || 0), 0), 255).toString(16).padStart(2, "0")).join("");
  }
  const rgb = hexToRgb(color);
  return rgb ? toHex(rgb) : null;
}
function colorOptions(config, defaults, keys) {
  const opt = { ...defaults, ...config };
  for (const key of keys) opt[key] = toHex(opt[key]) || toHex(defaults[key]);
  return opt;
}

function esc(text) {
  return String(text == null ? "" : text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function tint(hex, alpha) {
  const rgb = hexToRgb(hex) || [128, 128, 128];
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
}

const r1 = (v) => Math.round(v * 10) / 10;
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
const num = (v) => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));

const ICONS = {
  up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  down: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  spike: '<path d="M3 17l5-6 4 3 4-8 5 11"/>',
  negative: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
  balancing: '<path d="M12 3v18M5 7h14M7 7l-3 7h6zM17 7l-3 7h6z"/>',
  robot: '<rect x="5" y="8" width="14" height="11" rx="2"/><path d="M12 4v4M9 13h.01M15 13h.01M9 16h6"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  home: '<path d="M3 11l9-7 9 7v9H3z"/>',
  plugoff: '<path d="M9 2v4M15 2v4M7 6h10v4a5 5 0 0 1-10 0zM12 15v7M3 3l18 18"/>',
  cog: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};
function icon(name, color, size, width) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${width || 2}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex-shrink:0">${ICONS[name]}</svg>`;
}
function batteryIcon(percent, color) {
  return `<span class="batt"><span style="width:${clamp(Number(percent) || 0, 0, 100)}%;background:${color}"></span></span>`;
}

function isStatusSensor(stateObj) {
  return !!(stateObj && stateObj.attributes && "all_price" in stateObj.attributes && "battery_forecast" in stateObj.attributes);
}

function findStatusSensor(hass) {
  return Object.keys((hass && hass.states) || {}).find(
    (id) => id.startsWith("sensor.") && isStatusSensor(hass.states[id])
  );
}

function notStatusMessage(hass, entity, stateObj) {
  // An unavailable Status sensor has no attributes at all - that's ESS
  // Manager without data (just restarted, or an update failing), not a
  // wrong sensor.
  let text;
  if (!stateObj) text = tr(hass, "msg_not_found")(entity);
  else if (stateObj.state === "unavailable" || stateObj.state === "unknown") text = tr(hass, "msg_unavailable")(entity);
  else text = tr(hass, "msg_not_status")(entity);
  return `<div style="padding:16px">${esc(text)}</div>`;
}

// Put a card's content in place (as of v0.5.9). The <style> and <ha-card>
// are made once and kept; the content is only replaced when it changed,
// with the card's height held for a frame meanwhile - so a refresh never
// makes the card (and the dashboard around it) collapse and jump, which
// could scroll the whole page back to the top. Returns whether it changed
// (event listeners need wiring again then).
function setCardContent(host, css, inner) {
  const root = host.shadowRoot;
  if (!host._essCard || !root.contains(host._essCard)) {
    root.innerHTML = "<style></style><ha-card></ha-card>";
    host._essStyle = root.querySelector("style");
    host._essCard = root.querySelector("ha-card");
    host._essInner = null;
  }
  if (host._essStyle.textContent !== css) host._essStyle.textContent = css;
  if (host._essInner === inner) return false;
  const card = host._essCard;
  const height = card.offsetHeight;
  if (height) card.style.minHeight = `${height}px`;
  card.innerHTML = inner;
  host._essInner = inner;
  requestAnimationFrame(() => {
    card.style.minHeight = "";
  });
  return true;
}

// Recorder history of a few entities: {entity_id: [[ms, state], ...]}, the
// first entry being the state at `startMs`.
async function fetchHistory(hass, entityIds, startMs, endMs) {
  const ids = entityIds.filter(Boolean);
  if (!ids.length) return {};
  const result = await hass.callWS({
    type: "history/history_during_period",
    start_time: new Date(startMs).toISOString(),
    end_time: new Date(endMs).toISOString(),
    entity_ids: ids,
    minimal_response: true,
    no_attributes: true,
  });
  const out = {};
  for (const id of ids) {
    out[id] = ((result && result[id]) || []).map((item) => [
      Math.max((Number(item.lu != null ? item.lu : item.lc) || startMs / 1000) * 1000, startMs),
      item.s,
    ]);
  }
  return out;
}

// What the Battery action sensor's states mean for the charts.
const ACTION_KIND = {
  charge: "buy", balancing: "buy", negative_price_charge: "negative", discharge: "sell", spike_discharge: "spike",
  // as of 2026.10.41
  grid_use: "grid", solar_export: "export",
};

// The house from the grid and the expected solar export (as of 2026.10.41):
// [{side, kind, start, stop, kwh, expected}] - for the battery chart's line
// and labels.
function extraWindows(attrs) {
  const out = [];
  for (const g of attrs.grid_use || []) {
    const start = Date.parse(g.start), stop = Date.parse(g.stop);
    if (stop > start) out.push({ side: "grid", kind: "grid", start, stop, kwh: num(g.kwh) });
  }
  for (const e of attrs.solar_export_expected || []) {
    const start = Date.parse(e.start), stop = Date.parse(e.stop);
    if (stop > start) out.push({ side: "export", kind: "export", start, stop, expected: true });
  }
  return out;
}

// The upcoming / running Buy and Sell windows (the Status sensor's
// card_plans, the same the status card shows): [{side, kind, source, start, stop}].
function planWindows(attrs) {
  const plans = attrs.card_plans || {};
  const out = [];
  for (const side of ["buy", "sell"]) {
    const p = plans[side];
    if (!p || !p.start || !p.stop) continue;
    const start = Date.parse(p.start);
    const stop = Date.parse(p.stop);
    if (!(stop > start)) continue;
    let kind = side;
    if (side === "sell" && p.source === "spike") kind = "spike";
    if (side === "buy" && p.source === "negative_price") kind = "negative";
    out.push({ side, kind, source: p.source, start, stop });
    // a charge in several blocks (as of 2026.10.6): the later ones too
    for (const b of p.blocks || []) {
      const bs = Date.parse(b.start);
      const be = Date.parse(b.stop);
      if (be > bs) out.push({ side, kind, source: p.source, start: bs, stop: be });
    }
  }
  return out;
}

function planLabel(hass, w) {
  if (w.kind === "grid") return tr(hass, "grid_use");
  if (w.kind === "export") return tr(hass, w.past ? "plan_exported" : w.expected ? "export_expected" : "plan_export");
  if (w.past) return tr(hass, w.side === "sell" ? "plan_sold" : "plan_charged");
  if (w.side === "sell") return tr(hass, w.source === "spike" ? "plan_spike" : "plan_sell");
  return tr(hass, { negative_price: "plan_negative", full_charge: "plan_full", spike: "plan_spike" }[w.source] || "plan_buy");
}

// Executed plans from the Battery action history: [{side, kind, start, stop, past: true}].
function pastWindows(actionHistory, endMs) {
  const out = [];
  (actionHistory || []).forEach(([t, state], i) => {
    const kind = ACTION_KIND[state];
    const next = actionHistory[i + 1];
    const stop = next ? next[0] : endMs;
    if (!kind || !(stop > t)) return;
    const last = out[out.length - 1];
    if (last && last.kind === kind && Math.abs(last.stop - t) < 1000) last.stop = stop;
    else out.push({ side: kind === "buy" || kind === "negative" ? "buy" : kind === "grid" || kind === "export" ? kind : "sell", kind, start: t, stop, past: true });
  });
  return out;
}

// The pill-shaped plan labels in the charts.
function planPill(hass, w, colors) {
  const color = colors[w.kind];
  const ic = { sell: "up", spike: "spike", buy: "down", negative: "negative", grid: "home", export: "sun" }[w.kind];
  return { color, html: `${icon(ic, color, 12, 2.4)}${esc(planLabel(hass, w))} ${esc(formats(hass).time(w.start))}` };
}

const BASE_CSS = `
  :host { display: block; }
  ha-card { padding: 16px; display: flex; flex-direction: column; gap: 14px; overflow: hidden; container-type: inline-size; }
  .top { display: flex; align-items: flex-start; gap: 10px; }
  .title { font-family: var(--ha-card-header-font-family, inherit); font-size: var(--ha-card-header-font-size, 24px); font-weight: var(--ha-card-header-font-weight, 500); letter-spacing: -0.012em; line-height: 1.2; flex-grow: 1; }
  .dim { color: var(--secondary-text-color, #a0a0a0); }
  .batt { width: 22px; height: 12px; border: 2px solid var(--secondary-text-color, #a0a0a0); border-radius: 3px; padding: 1px; box-sizing: border-box; display: inline-flex; flex-shrink: 0; }
  .batt span { border-radius: 1px; }
  .chart { position: relative; touch-action: pan-y; user-select: none; -webkit-user-select: none; }
  .chart svg { display: block; position: absolute; left: 0; top: 0; overflow: visible; }
  .chart text { fill: var(--secondary-text-color, #a0a0a0); font-size: 10px; font-family: inherit; }
  .pill { position: absolute; display: flex; align-items: center; gap: 4px; font-size: 11px; line-height: 16px; padding: 1px 8px; border-radius: 999px; white-space: nowrap; pointer-events: none; }
  .plabel { position: absolute; display: flex; align-items: center; gap: 3px; font-size: 10px; line-height: 12px; white-space: nowrap; pointer-events: none; transform: translateX(-50%); }
  .chart .plabel svg { position: static; display: block; }
  .tip { position: absolute; display: none; flex-direction: column; gap: 4px; font-size: 12px; min-width: 132px; padding: 8px 10px; border-radius: 8px;
         background: var(--ha-card-background, var(--card-background-color, #2c2c2c)); border: 1px solid rgba(127,127,127,.35); box-shadow: 0 4px 14px rgba(0,0,0,.35); pointer-events: none; z-index: 2; }
  .tip .row { display: flex; align-items: center; gap: 6px; }
  .tip .row span.k { flex-grow: 1; color: var(--secondary-text-color, #a0a0a0); }
  .tip .dot { width: 8px; height: 8px; border-radius: 999px; flex-shrink: 0; }
  .tip .sep { border-top: 1px solid rgba(127,127,127,.3); padding-top: 4px; }
  .axisrow { position: relative; height: 14px; font-size: 11px; color: var(--secondary-text-color, #a0a0a0); }
  .axisrow span { position: absolute; white-space: nowrap; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 11px; color: var(--secondary-text-color, #a0a0a0); }
  .legend span { display: flex; align-items: center; gap: 5px; }
  .legend i { display: inline-block; width: 10px; height: 8px; border-radius: 2px; }
`;

// The price card's buy (incl taxes) / sell (excl) choice, shared per entity
// (as of 2026.11.21) - the battery forecast's tooltip shows the same price.
// Until the page reloads; without a choice it follows the sun (surplus: sell).
const PRICE_VIEWS = {};
function priceView(entity, attrs) {
  if (!Array.isArray(attrs.all_buy_price_incl) || !attrs.all_buy_price_incl.length) return null;
  const auto = attrs.solar_mode && attrs.solar_mode.mode === "surplus" ? "sell" : "buy";
  return PRICE_VIEWS[entity] || auto;
}

// Base for the two chart cards: config, hass, a re-render every minute,
// re-render on a width change, and the tap / hover tooltip plumbing.
class EssChartCard extends HTMLElement {
  static getStubConfig(hass) {
    return { entity: findStatusSensor(hass) || "" };
  }

  static getConfigElement() {
    const editor = document.createElement("ess-manager-card-editor");
    editor.cardInfo = this.info;
    return editor;
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("Choose the ESS Manager Status sensor (entity)");
    this._config = config;
    this._renderKey = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    this._timer = setInterval(() => {
      this._renderKey = null;
      this._render();
    }, 60000);
    if (!this._resize && window.ResizeObserver) {
      this._resize = new ResizeObserver(() => {
        const width = Math.floor(this.clientWidth);
        if (width && width !== this._width) {
          this._width = width;
          this._renderKey = null;
          this._render();
        }
      });
    }
    if (this._resize) this._resize.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    if (this._resize) this._resize.disconnect();
  }

  _t(key) {
    return tr(this._hass, key);
  }

  _chartWidth() {
    const width = this._width || Math.floor(this.clientWidth) || 400;
    return Math.max(width - 32, 160);
  }

  // Hover with a mouse, tap with a finger (tap the same spot again to close).
  _wireTooltip(show) {
    const layer = this.shadowRoot.querySelector(".hit");
    if (!layer) return;
    const at = (ev) => clamp(ev.clientX - layer.getBoundingClientRect().left, 0, layer.clientWidth);
    layer.addEventListener("pointermove", (ev) => {
      if (ev.pointerType === "mouse") show(at(ev));
    });
    layer.addEventListener("pointerleave", (ev) => {
      if (ev.pointerType === "mouse") show(null);
    });
    layer.addEventListener("pointerdown", (ev) => {
      if (ev.pointerType === "mouse") return;
      const x = at(ev);
      show(this._tipX != null && Math.abs(this._tipX - x) < 14 ? null : x);
    });
    if (this._tipX != null) show(this._tipX);
  }
}

// -- Battery card (as of v0.5.1) ----------------------------------------------------
// Five whole days, today included: left of "now" what happened (the SOC
// sensor's history, measured solar and household usage), right of it what's
// expected (the forecast with the plans in it). The SOC line is coloured by
// what the battery does (sell red, buy blue, the faster spike / negative
// price plans more intense), a thin dotted line is the forecast without any
// plan (solar minus usage only), the band is the minimum - maximum SOC and
// everything past the planning horizon is dimmed. Day tiles below; tap or
// hover for the values at a moment.
const BATTERY_DEFAULTS = {
  title: "",
  days: 5,
  height: 210,
  show_days: true,
  show_raw: true,
  show_solar: true,
  show_usage: true,
  show_outlook: true,
  soc_color: [111, 207, 151],
  solar_color: [242, 201, 76],
  usage_color: [201, 206, 214],
  sell_color: [255, 107, 107],
  buy_color: [79, 163, 247],
  grid_color: [167, 120, 230],
  export_color: [255, 159, 67],
};
const BATTERY_COLOR_KEYS = ["soc_color", "solar_color", "usage_color", "sell_color", "buy_color", "grid_color", "export_color"];
const BATTERY_SCHEMA = (t) => [
  { name: "title", selector: { text: {} } },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "days", selector: { number: { min: 1, max: 5, step: 1, mode: "box" } } },
      { name: "height", selector: { number: { min: 120, max: 600, step: 10, mode: "box", unit_of_measurement: "px" } } },
      { name: "show_days", selector: { boolean: {} } },
      { name: "show_outlook", selector: { boolean: {} } },
      { name: "show_raw", selector: { boolean: {} } },
      { name: "show_solar", selector: { boolean: {} } },
      { name: "show_usage", selector: { boolean: {} } },
    ],
  },
  {
    type: "expandable",
    flatten: true,
    name: "colours",
    title: t("ed_colours"),
    schema: [{ type: "grid", name: "", schema: BATTERY_COLOR_KEYS.map((name) => ({ name, selector: { color_rgb: {} } })) }],
  },
];

class EssManagerBatteryCard extends EssChartCard {
  static get info() {
    return {
      name: "ESS Manager - Battery forecast",
      description: "Five whole days: the measured and the expected battery level, solar, usage and the planned buy / sell moments.",
      schema: BATTERY_SCHEMA,
      defaults: BATTERY_DEFAULTS,
      labels: {
        title: "ed_title", days: "ed_days", height: "ed_height", show_days: "ed_show_days", show_raw: "ed_show_raw",
        show_solar: "ed_show_solar", show_usage: "ed_show_usage", show_outlook: "ed_show_outlook",
        soc_color: "ed_soc_color", solar_color: "ed_solar_color", usage_color: "ed_usage_color",
        sell_color: "ed_sell_color", buy_color: "ed_buy_color", grid_color: "ed_grid_color", export_color: "ed_export_color",
      },
    };
  }

  getCardSize() {
    return 7;
  }

  // The SOC sensor's and the Battery action sensor's history since midnight,
  // reloaded every 5 minutes, at a new day and when the action changes.
  _ensureHistory(siblings, dayStart, actionObj) {
    const ids = [siblings.battery_soc, siblings.battery_action].filter(Boolean);
    if (!ids.length || this._histLoading) return;
    const key = `${ids.join(",")}|${dayStart}`;
    const now = Date.now();
    // a new Battery action (compared as text, so a clock difference between
    // Home Assistant and this device can't make it look new forever)
    const changed = actionObj && this._histFor && actionObj.last_changed !== this._histSeen;
    if (this._histFor === key && now - this._histAt < 300000 && !changed) return;
    this._histLoading = true;
    this._histSeen = actionObj ? actionObj.last_changed : null;
    fetchHistory(this._hass, ids, dayStart, now)
      .then((data) => {
        // SOC: one value per 5 minutes is plenty for a five-day chart.
        const soc = [];
        for (const [t, s] of data[siblings.battery_soc] || []) {
          const v = num(s);
          if (v === null) continue;
          const bucket = Math.floor(t / 300000) * 300000;
          if (soc.length && soc[soc.length - 1][0] === bucket) soc[soc.length - 1][1] = v;
          else soc.push([Math.max(bucket, dayStart), v]);
        }
        this._hist = { soc, action: data[siblings.battery_action] || [] };
      })
      .catch(() => {
        this._hist = { soc: [], action: [] };
      })
      .finally(() => {
        this._histFor = key;
        this._histAt = Date.now();
        this._histLoading = false;
        this._renderKey = null;
        this._render();
      });
  }

  _model(attrs, opt) {
    const hass = this._hass;
    const now = Date.now();
    const cap = num(attrs.capacity_kwh) || 0;
    const pct = (kwh) => (cap > 0 ? (kwh / cap) * 100 : 0);
    const days = clamp(Math.round(Number(opt.days) || 5), 1, 5);
    const starts = [localMidnight(hass, now)];
    for (let d = 0; d < days; d++) starts.push(nextMidnight(hass, starts[d]));
    const T0 = starts[0];
    const T1 = starts[days];
    const baseHour = T0 + Math.floor((now - T0) / HOUR_MS) * HOUR_MS;
    const socNow = num(attrs.battery_soc_percent);
    const eNow = num(attrs.battery_energy_kwh);

    // Forecasts: entry i is the level at the end of hour i (hour 0 = this one).
    const series = (arr) => {
      const out = socNow === null ? [] : [[now, socNow]];
      (arr || []).forEach((v, i) => {
        const t = baseHour + (i + 1) * HOUR_MS;
        if (num(v) !== null && t > now && t <= T1 + HOUR_MS) out.push([t, pct(Number(v))]);
      });
      return out;
    };
    const future = series(attrs.battery_forecast_adjusted);
    const raw = series(attrs.battery_forecast);
    const hist = ((this._hist && this._hist.soc) || []).filter(([t]) => t >= T0 && t < now);
    const action = (this._hist && this._hist.action) || [];

    // Solar / usage per hour: [hourStart, kWh] - measured today (the
    // Status sensor's history_today), then the forecast from this hour on.
    const flows = { solar: [], usage: [] };
    const today = attrs.history_today;
    if (today && Math.abs(Date.parse(today.start) - T0) < 120000) {
      const t0 = Date.parse(today.start);
      for (const key of ["solar", "usage"]) {
        (today[key] || []).forEach((v, j) => {
          const t = t0 + j * HOUR_MS;
          if (num(v) !== null && t < baseHour) flows[key].push([t, Math.max(Number(v), 0)]);
        });
      }
    }
    for (const [key, attr] of [["solar", "solar_120h"], ["usage", "energy_usage_120h"]]) {
      (attrs[attr] || []).forEach((v, i) => {
        const t = baseHour + i * HOUR_MS;
        if (t < T1) flows[key].push([t, Math.max(num(v) || 0, 0)]);
      });
    }

    // Without grid: the first moment the forecast without plans runs empty
    // (< 0 kWh) or full (> capacity) - the nearest decides, like the solar mode.
    let outlook = null;
    if (eNow !== null && cap > 0) {
      let tp = now;
      let ep = eNow;
      for (let i = 0; i < (attrs.battery_forecast || []).length; i++) {
        const e = num(attrs.battery_forecast[i]);
        if (e === null) continue;
        const t = baseHour + (i + 1) * HOUR_MS;
        if (e < 0 || e > cap) {
          const frac = e < 0 ? ep / (ep - e) : (cap - ep) / (e - ep);
          const at = Math.floor((tp + clamp(frac, 0, 1) * (t - tp)) / UNIT_MS) * UNIT_MS;
          outlook = { kind: e < 0 ? "empty" : "full", at };
          break;
        }
        tp = t;
        ep = e;
      }
    }

    return {
      now, cap, days, starts, T0, T1, baseHour, socNow, eNow, future, raw, hist, action, flows, outlook,
      low: cap > 0 ? pct(num(attrs.low_threshold_kwh) || 0) : null,
      high: cap > 0 ? pct(num(attrs.high_threshold_kwh) || 0) : null,
      horizon: now + (num(attrs.planning_horizon_hours) || 0) * HOUR_MS,
      windows: planWindows(attrs).concat(extraWindows(attrs)).filter((w) => w.stop > now),
    };
  }

  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj || !isStatusSensor(stateObj)) {
      setCardContent(this, BASE_CSS, notStatusMessage(this._hass, this._config.entity, stateObj));
      return;
    }
    const attrs = stateObj.attributes;
    const siblings = attrs.card_entities || {};
    const actionObj = siblings.battery_action ? this._hass.states[siblings.battery_action] : null;
    const width = this._chartWidth();
    const key = [stateObj, actionObj, this._hist, width, hassLang(this._hass)];
    if (this._renderKey && key.every((v, i) => v === this._renderKey[i])) return;
    this._renderKey = key;

    const opt = colorOptions(this._config, BATTERY_DEFAULTS, BATTERY_COLOR_KEYS);
    const f = formats(this._hass);
    const m = this._model(attrs, opt);
    this._ensureHistory(siblings, m.T0, actionObj);
    this._m = m;
    this._opt = opt;

    const colors = { normal: opt.soc_color, buy: opt.buy_color, negative: "#2f8cff", sell: opt.sell_color, spike: "#ff4545",
                     grid: opt.grid_color, export: opt.export_color };
    this._colors = colors;
    const W = width;
    const top = 18;
    // the plot keeps its height; the 12 px saved above it make the card lower
    const H = Math.max(clamp(Number(opt.height) || 210, 120, 600) - 34, 60);
    const bottom = top + H;
    const x = (t) => ((t - m.T0) / (m.T1 - m.T0)) * W;
    const ys = (p) => top + ((100 - p) / 100) * H;
    let kmax = 1;
    for (const key2 of ["solar", "usage"]) {
      if (opt["show_" + key2] === false) continue;
      for (const [t, v] of m.flows[key2]) if (t >= m.T0 && t < m.T1) kmax = Math.max(kmax, v);
    }
    kmax = Math.ceil(kmax * 1.1);
    const yk = (k) => bottom - (k / kmax) * H;
    this._geo = { W, top, H, bottom, x, ys, yk };
    const pts = (list, yf) => list.map(([t, v]) => `${r1(x(t))} ${r1(yf(v))}`);

    let svg = "";
    // min - max SOC band
    if (m.low !== null && m.high !== null && m.high > m.low) {
      const yHi = ys(Math.min(m.high, 100));
      const yLo = ys(clamp(m.low, 0, 100));
      svg += `<rect x="0" y="${r1(yHi)}" width="${W}" height="${r1(yLo - yHi)}" fill="rgba(127,127,127,.09)"/>`;
      svg += `<text x="${W}" y="${r1(yHi - 4)}" text-anchor="end">${esc(this._t("max_label")(f.num(m.high, 0)))}</text>`;
      svg += `<text x="${W}" y="${r1(yLo + 12)}" text-anchor="end">${esc(this._t("min_label")(f.num(m.low, 0)))}</text>`;
    }
    // the stretch the plans cover (now -> planning horizon) a little brighter
    const xA = clamp(x(m.now), 0, W);
    const xB = clamp(x(m.horizon), 0, W);
    if (xB > xA) svg += `<rect x="${r1(xA)}" y="${top}" width="${r1(xB - xA)}" height="${H}" style="fill:var(--primary-text-color, #e8e8e8)" fill-opacity="0.06"/>`;
    for (const s of m.starts.slice(1, -1)) svg += `<line x1="${r1(x(s))}" y1="${top}" x2="${r1(x(s))}" y2="${bottom}" stroke="rgba(127,127,127,.25)"/>`;
    // solar (hourly values drawn at the middle of their hour), usage
    const mid = (list) => list.filter(([t]) => t + HOUR_MS > m.T0 && t < m.T1).map(([t, v]) => [t + HOUR_MS / 2, v]);
    const solar = mid(m.flows.solar);
    if (opt.show_solar !== false && solar.length > 1) {
      const line = pts(solar, yk);
      svg += `<path d="M${r1(x(solar[0][0]))} ${bottom} L${line.join(" L")} L${r1(x(solar[solar.length - 1][0]))} ${bottom} Z" fill="${opt.solar_color}" fill-opacity="0.24" stroke="${opt.solar_color}" stroke-opacity="0.6" stroke-width="1"/>`;
    }
    const usage = mid(m.flows.usage);
    if (opt.show_usage !== false && usage.length > 1) {
      svg += `<path d="M${pts(usage, yk).join(" L")}" fill="none" stroke="${opt.usage_color}" stroke-opacity="0.7" stroke-width="1"/>`;
    }
    // the forecast without plans, cut off at the chart's edges
    if (opt.show_raw !== false && m.raw.length > 1) {
      svg += `<defs><clipPath id="plot"><rect x="0" y="${top}" width="${W}" height="${H}"/></clipPath></defs>`;
      svg += `<path d="M${pts(m.raw, ys).join(" L")}" fill="none" stroke="${opt.soc_color}" stroke-opacity="0.75" stroke-width="1.3" stroke-dasharray="1.5 3" stroke-linecap="round" clip-path="url(#plot)"/>`;
    }
    // the SOC line, one stretch per colour
    const histKind = (t) => {
      let state = "idle";
      for (const [at, s] of m.action) {
        if (at <= t) state = s;
        else break;
      }
      return ACTION_KIND[state] || "normal";
    };
    const futureKind = (t) => {
      const w = m.windows.find((win) => t >= win.start && t < win.stop);
      return w ? w.kind : "normal";
    };
    // The forecast has a point per hour; a short charge block (30 minutes,
    // as of 2026.10.6) can fall between two of them, so the line gets extra
    // points on the plan windows' edges (on the line itself) to colour it.
    const edges = [];
    for (const w of m.windows) edges.push(w.start, w.stop);
    const future = [];
    m.future.forEach((p, i) => {
      if (i > 0) {
        const [ta, va] = m.future[i - 1];
        const [tb, vb] = p;
        for (const e of edges.filter((t) => t > ta && t < tb).sort((a, b) => a - b)) {
          future.push([e, va + ((vb - va) * (e - ta)) / (tb - ta)]);
        }
      }
      future.push(p);
    });
    const all = m.hist.map((p) => [...p, true]).concat(future.map((p) => [...p, false]));
    let run = null;
    const runs = [];
    for (let i = 1; i < all.length; i++) {
      const [ta, va, pa] = all[i - 1];
      const [tb, vb] = all[i];
      const midT = (ta + tb) / 2;
      const kind = pa ? histKind(midT) : futureKind(midT);
      if (!run || run.kind !== kind) {
        run = { kind, points: [[ta, va]] };
        runs.push(run);
      }
      run.points.push([tb, vb]);
    }
    for (const r of runs) {
      svg += `<path d="M${pts(r.points, (v) => ys(clamp(v, -5, 105))).join(" L")}" fill="none" stroke="${colors[r.kind]}" stroke-width="${r.kind === "normal" ? 2.2 : 3.2}" stroke-linejoin="round" stroke-linecap="round"/>`;
    }
    // the past slightly dimmed, past the planning horizon more
    const bg = "var(--ha-card-background, var(--card-background-color, #1c1c1c))";
    const xNow = x(m.now);
    svg += `<rect x="0" y="${top}" width="${r1(clamp(xNow, 0, W))}" height="${H}" style="fill:${bg}" fill-opacity="0.2"/>`;
    const xHor = x(m.horizon);
    if (xHor < W) {
      svg += `<rect x="${r1(xHor)}" y="${top}" width="${r1(W - xHor)}" height="${H}" style="fill:${bg}" fill-opacity="0.55"/>`;

    }
    svg += `<line x1="${r1(xNow)}" y1="${top}" x2="${r1(xNow)}" y2="${bottom}" style="stroke:var(--primary-text-color, #e8e8e8)" stroke-width="1.2"/>`;
    // "now" beside the line in the chart's top corner (left of it near the right edge)
    const nowW = this._t("now").length * 6 + 4;
    const nowRight = xNow + 4 + nowW <= W;
    const nowX = nowRight ? xNow + 4 : xNow - 4;
    svg += `<text x="${r1(nowX)}" y="${top + 10}" text-anchor="${nowRight ? "start" : "end"}" style="fill:var(--primary-text-color, #e8e8e8);font-weight:600;paint-order:stroke;stroke:${bg};stroke-width:3px">${esc(this._t("now"))}</text>`;
    if (m.socNow !== null) svg += `<circle cx="${r1(xNow)}" cy="${r1(ys(clamp(m.socNow, 0, 100)))}" r="4" fill="${opt.soc_color}" style="stroke:${bg}" stroke-width="2"/>`;
    if (opt.show_outlook !== false && m.outlook && m.outlook.at < m.T1) {
      const ox = x(m.outlook.at);
      const empty = m.outlook.kind === "empty";
      const c = empty ? "#ff8a65" : opt.solar_color;
      const y0 = ys(empty ? 0 : 100);
      svg += `<line x1="${r1(ox)}" y1="${r1(y0)}" x2="${r1(ox)}" y2="${r1(empty ? y0 - 10 : y0 + 10)}" stroke="${c}" stroke-width="1.5"/>`;
      svg += `<circle cx="${r1(ox)}" cy="${r1(y0)}" r="3.5" style="fill:${bg}" stroke="${c}" stroke-width="2"/>`;
    }

    // plan pills, above the line (below it when there's no room or they'd overlap)
    let pills = "";
    // the "now" label counts as taken, so a plan label steps around it
    const placed = [{ left: nowRight ? xNow : xNow - 4 - nowW, y: top, w: nowW + 4 }];
    const socAt = (t) => this._interp(t < m.now ? m.hist : m.future, t);
    // One label per group (as of 2026.10.42): blocks of the same kind less
    // than three hours apart share the first one's label, with "+n" for the
    // rest (the line keeps each block's colour); a label that would still
    // overlap another one is left out rather than stacked.
    const groups = [];
    for (const w of [...m.windows].sort((a, b) => a.start - b.start)) {
      if (w.start >= m.T1) continue;
      // short stretches from the grid / export: the line's colour only
      if ((w.kind === "grid" || w.kind === "export") && w.stop - w.start < 45 * 60000) continue;
      const same = groups.slice().reverse().find((g) => g.w.kind === w.kind);
      if (same && w.start - same.stop < 3 * HOUR_MS) {
        same.n += 1;
        same.stop = Math.max(same.stop, w.stop);
        continue;
      }
      groups.push({ w, n: 0, stop: w.stop });
    }
    for (const g of groups) {
      const w = g.w;
      const p = planPill(this._hass, w, colors);
      const more = g.n ? ` <span style="opacity:.7">+${g.n}</span>` : "";
      const t = Math.max(w.start, m.T0);
      const estW = 30 + (planLabel(this._hass, w).length + 6 + (g.n ? 3 : 0)) * 6.2;
      const left = clamp(x(t) - 6, 0, Math.max(W - estW, 0));
      const v = socAt(t);
      const yLine = ys(clamp(v === null ? 50 : v, 0, 100));
      const above = yLine - 28 < 0 ? yLine + 10 : yLine - 28;
      const below = above < yLine ? yLine + 10 : yLine - 28;
      const free = (y) => !placed.some((q) => left < q.left + q.w && q.left < left + estW && Math.abs(q.y - y) < 20);
      const y = free(above) ? above : free(below) ? below : null;
      if (y === null) continue;
      placed.push({ left, y, w: estW });
      pills += `<span class="pill" style="left:${r1(left)}px;top:${r1(clamp(y, 0, bottom - 18))}px;background:${tint(p.color, 0.2)};color:var(--primary-text-color, #e8e8e8)">${p.html}${more}</span>`;
    }

    // "planning horizon": just under the max SOC line, unless the "without
    // grid" ring or a plan label is there - then lower down
    if (xHor < W && W - xHor > 70) {
      const text = this._t("horizon");
      const tw = text.length * 5.6 + 4;
      const yHi = m.high !== null ? ys(Math.min(m.high, 100)) : top;
      const yLo = m.low !== null ? ys(clamp(m.low, 0, 100)) : bottom;
      const boxes = placed.map((q) => [q.left, q.y, q.left + q.w, q.y + 18]);
      if (opt.show_outlook !== false && m.outlook && m.outlook.at < m.T1) {
        const ox = x(m.outlook.at);
        const y0 = ys(m.outlook.kind === "empty" ? 0 : 100);
        boxes.push([ox - 8, y0 - 12, ox + 8, y0 + 12]);
      }
      const free = (y) => !boxes.some(([l, t2, r, b]) => xHor + 4 < r && l < xHor + 6 + tw && y - 10 < b && t2 < y + 2);
      const candidates = [yHi + 13, yHi + 28, (yHi + yLo) / 2, yLo - 6].map((y) => clamp(y, top + 12, bottom - 4));
      const yText = candidates.find(free) || candidates[0];
      svg += `<text x="${r1(xHor + 6)}" y="${r1(yText)}">${esc(text)}</text>`;
    }

    // day labels and tiles
    const dayW = (d) => x(m.starts[d + 1]) - x(m.starts[d]);
    const labels = m.starts.slice(0, -1).map((s, d) => `<span style="left:${r1(x(s))}px;width:${r1(dayW(d))}px;text-align:center${d === 0 ? ";color:var(--primary-text-color, #e8e8e8);font-weight:600" : ""}">${esc(f.dayLabel(s + HOUR_MS * 12))}</span>`).join("");
    let tiles = "";
    if (opt.show_days !== false) {
      tiles = `<div class="days" style="grid-template-columns:repeat(${m.days}, minmax(0, 1fr))">` + m.starts.slice(0, -1).map((s, d) => {
        const e = m.starts[d + 1];
        const sum = (list) => {
          const inDay = list.filter(([t]) => t >= s && t < e);
          return inDay.length ? inDay.reduce((acc, [, v]) => acc + v, 0) : null;
        };
        const sol = sum(m.flows.solar);
        const use = sum(m.flows.usage);
        const socs = m.hist.concat(m.future).filter(([t]) => t >= s && t <= e).map(([, v]) => v);
        const lo = socs.length ? clamp(Math.min(...socs), 0, 100) : null;
        const hi = socs.length ? clamp(Math.max(...socs), 0, 100) : null;
        // no day name: the tiles sit right under the chart's day labels
        const name = d === 0 ? this._t("today") : f.dayLabel(s + HOUR_MS * 12);
        const range = lo === null ? name : `${name} \u00b7 ${f.num(lo, 0)}\u2013${f.num(hi, 0)} %`;
        return `<div class="day${d === 0 ? " today" : ""}" title="${esc(range)}">
          <div class="drow">
            <div class="dvals">
              ${opt.show_solar !== false ? `<span class="dval">${icon("sun", opt.solar_color, 13, 2.2)}${sol === null ? "\u2013" : f.num(sol, 1)}</span>` : ""}
              ${opt.show_usage !== false ? `<span class="dval">${icon("home", opt.usage_color, 13, 2.2)}${use === null ? "\u2013" : f.num(use, 1)}</span>` : ""}
            </div>
            <div class="vbar">${lo === null ? "" : `<div style="bottom:${lo.toFixed(0)}%;height:${Math.max(hi - lo, 4).toFixed(0)}%;background:${opt.soc_color}"></div>`}</div>
          </div>
        </div>`;
      }).join("") + "</div>";
    }

    // header: SOC, energy and the "without grid" outlook
    let outlookLine = "";
    if (opt.show_outlook !== false && m.eNow !== null && m.cap > 0) {
      if (m.outlook && m.outlook.kind === "empty") {
        outlookLine = `<span class="outlook" style="color:#ffb59c">${icon("plugoff", "#ff8a65", 12)}${esc(this._t("offgrid_empty")(`${f.weekday(m.outlook.at)} ${f.time(m.outlook.at)}`))}</span>`;
      } else if (m.outlook) {
        outlookLine = `<span class="outlook" style="color:${opt.solar_color}">${icon("sun", opt.solar_color, 12)}${esc(this._t("offgrid_full")(`${f.weekday(m.outlook.at)} ${f.time(m.outlook.at)}`))}</span>`;
      } else {
        outlookLine = `<span class="outlook dim">${icon("plugoff", "var(--secondary-text-color, #a0a0a0)", 12)}${esc(this._t("offgrid_days"))}</span>`;
      }
    }
    const socText = m.socNow === null ? "\u2013" : `${f.num(m.socNow, 0)} %`;
    const kwhText = m.eNow === null ? "" : `${f.num(m.eNow, 1)} kWh`;

    const css = `${BASE_CSS}
      .right { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
      .top + div { margin-top: -8px; }
      .socrow { display: flex; align-items: center; gap: 6px; font-size: 13px; white-space: nowrap; }
      .outlook { display: flex; align-items: center; gap: 4px; font-size: 11px; white-space: nowrap; }
      .days { display: grid; gap: 6px; margin-top: 8px; }
      .day { background: rgba(127,127,127,.12); border-radius: 10px; padding: 8px; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
      .day.today { background: rgba(127,127,127,.2); }
      .drow { display: flex; align-items: stretch; gap: 6px; min-height: 30px; }
      .dvals { display: flex; flex-direction: column; justify-content: space-between; gap: 5px; flex-grow: 1; min-width: 0; }
      .dval { display: flex; align-items: center; gap: 4px; font-size: 12px; white-space: nowrap; }
      .vbar { position: relative; width: 6px; flex-shrink: 0; border-radius: 999px; background: rgba(127,127,127,.25); }
      .vbar div { position: absolute; left: 0; right: 0; border-radius: 999px; }
      @container (max-width: 400px) {
        .day { padding: 6px; }
        .drow { gap: 3px; }
        .dval { font-size: 11px; }
        .dval { gap: 3px; }
        .dval svg { width: 11px; height: 11px; }
        .vbar { width: 4px; }
      }
    `;
    const changed = setCardContent(this, css, `
      <div class="top"><span class="title">${esc(opt.title || this._t("battery_title"))}</span>
        <div class="right"><span class="socrow">${batteryIcon(m.socNow, opt.soc_color)}<b>${esc(socText)}</b><span class="dim">${esc(kwhText)}</span></span>${outlookLine}</div></div>
      <div>
        <div class="chart" style="width:${W}px;height:${bottom + 4}px">
          <svg width="${W}" height="${bottom + 4}" viewBox="0 0 ${W} ${bottom + 4}">${svg}</svg>
          <svg class="cross" width="${W}" height="${bottom + 4}" viewBox="0 0 ${W} ${bottom + 4}"></svg>
          ${pills}
          <div class="tip"></div>
          <div class="hit" style="position:absolute;left:0;top:${top}px;width:${W}px;height:${H}px"></div>
        </div>
        <div class="axisrow" style="width:${W}px;margin-top:4px">${labels}</div>
        ${tiles}
      </div>
    `);
    if (changed) this._wireTooltip((px) => this._showTip(px));
  }

  _interp(list, t) {
    if (!list.length) return null;
    if (t <= list[0][0]) return list[0][1];
    for (let i = 1; i < list.length; i++) {
      if (t <= list[i][0]) {
        const [ta, va] = list[i - 1];
        const [tb, vb] = list[i];
        return tb === ta ? vb : va + ((vb - va) * (t - ta)) / (tb - ta);
      }
    }
    return list[list.length - 1][1];
  }

  _showTip(px) {
    const cross = this.shadowRoot.querySelector(".cross");
    const tip = this.shadowRoot.querySelector(".tip");
    if (!cross || !tip || !this._m) return;
    this._tipX = px;
    if (px === null || px === undefined) {
      cross.innerHTML = "";
      tip.style.display = "none";
      return;
    }
    const m = this._m;
    const g = this._geo;
    const opt = this._opt;
    const f = formats(this._hass);
    const raw = m.T0 + (px / g.W) * (m.T1 - m.T0);
    const t = clamp(m.T0 + Math.round((raw - m.T0) / HOUR_MS) * HOUR_MS, m.T0, m.T1);
    const past = t <= m.now;
    const soc = past ? this._interp(m.hist.concat(m.socNow === null ? [] : [[m.now, m.socNow]]), t) : this._interp(m.future, t);
    const free = past ? null : this._interp(m.raw, t);
    const hourVal = (list) => {
      const found = list.find(([h]) => h === t);
      return found ? found[1] : null;
    };
    const sol = hourVal(m.flows.solar);
    const use = hourVal(m.flows.usage);
    const attrs = this._hass.states[this._config.entity].attributes;
    const unit = Math.floor((t - m.T0) / UNIT_MS);
    // as on the price card: buy incl taxes or sell excl (as of 2026.11.21)
    const pview = priceView(this._config.entity, attrs);
    const plist = pview === "buy" ? attrs.all_buy_price_incl : attrs.all_price;
    const price = plist && unit >= 0 && unit < plist.length ? num(plist[unit]) : null;
    const xx = g.x(t);
    let dots = "";
    if (soc !== null) dots += `<circle cx="${r1(xx)}" cy="${r1(g.ys(clamp(soc, 0, 100)))}" r="4.5" fill="${opt.soc_color}" stroke="rgba(0,0,0,.5)" stroke-width="1.5"/>`;
    if (opt.show_solar !== false && sol !== null) dots += `<circle cx="${r1(xx + g.W / ((m.T1 - m.T0) / HOUR_MS) / 2)}" cy="${r1(g.yk(sol))}" r="3.5" fill="${opt.solar_color}" stroke="rgba(0,0,0,.5)" stroke-width="1.5"/>`;
    if (opt.show_usage !== false && use !== null) dots += `<circle cx="${r1(xx + g.W / ((m.T1 - m.T0) / HOUR_MS) / 2)}" cy="${r1(g.yk(use))}" r="3.5" fill="${opt.usage_color}" stroke="rgba(0,0,0,.5)" stroke-width="1.5"/>`;
    cross.innerHTML = `<line x1="${r1(xx)}" y1="${g.top}" x2="${r1(xx)}" y2="${g.bottom}" style="stroke:var(--primary-text-color, #e8e8e8)" stroke-opacity="0.7" stroke-dasharray="3 3"/>${dots}`;
    const row = (dot, label, value) => `<div class="row">${dot}<span class="k">${esc(label)}</span><b>${esc(value)}</b></div>`;
    const kwh = (v) => `${f.num(v, 2)} kWh`;
    let html = `<div class="row"><b style="flex-grow:1">${esc(f.dayLabel(t))} \u00b7 ${esc(f.time(t))}</b><span class="dim" style="font-size:10px">${esc(this._t(past ? "measured" : "expected"))}</span></div>`;
    if (soc !== null) html += row(`<span class="dot" style="background:${opt.soc_color}"></span>`, this._t("soc"), `${f.num(soc, 0)} %`);
    if (opt.show_raw !== false && free !== null) html += row(`<span class="dot" style="background:transparent;border:2px dotted ${opt.soc_color};width:4px;height:4px"></span>`, this._t("without_plans"), `${f.num(free, 0)} %`);
    if (opt.show_solar !== false && sol !== null) html += row(`<span class="dot" style="background:${opt.solar_color}"></span>`, this._t("solar"), kwh(sol));
    if (opt.show_usage !== false && use !== null) html += row(`<span class="dot" style="background:${opt.usage_color}"></span>`, this._t("usage"), kwh(use));
    const plabel = pview ? `${this._t("price")} \u00b7 ${this._t(pview === "sell" ? "excl_tax" : "incl_tax")}` : this._t("price");
    if (price !== null) html += `<div class="row sep"><span class="k">${esc(plabel)}</span><b>${esc(f.money(price))}</b></div>`;
    // the house from the grid / solar export expected this hour (as of 2026.10.41)
    for (const w of (m.windows || []).filter((win) => (win.kind === "grid" || win.kind === "export") && t + HOUR_MS > win.start && t < win.stop)) {
      const c = w.kind === "grid" ? opt.grid_color : opt.export_color;
      const extra = w.kind === "grid" && w.kwh ? ` \u00b7 ~${f.num(w.kwh, 1)} kWh` : "";
      html += row(`<span class="dot" style="background:${c}"></span>`, this._t(w.kind === "grid" ? "tip_grid_use" : "tip_export"),
        `${f.time(w.start)}\u2013${f.time(w.stop)}${extra}`);
    }
    tip.innerHTML = html;
    tip.style.display = "flex";
    const tipW = tip.offsetWidth || 150;
    tip.style.left = `${r1(xx + 12 + tipW > g.W ? Math.max(xx - 12 - tipW, 0) : xx + 12)}px`;
    tip.style.top = "0px";
  }
}

// -- Price card (as of v0.5.1) ------------------------------------------------------
// Today's and (once known) tomorrow's prices as bars coloured by price level
// - a gradient from cheap to expensive, negative prices apart. The planned
// buy / sell moments stand out: their bars at full colour with a light
// column and a line under it in the plan's colour, everything else dimmed;
// what's past sits under a darker layer, with the plans that ran (from the
// Battery action history) still visible. Header: the current price, the buy
// price and the cheapest / most expensive moment still to come.
const PRICE_DEFAULTS = {
  title: "",
  height: 170,
  show_extremes: true,
  show_buy_line: true,
  legend: true,
  cheap_color: [63, 174, 106],
  mid_color: [224, 195, 65],
  high_color: [240, 112, 60],
  negative_color: [77, 208, 225],
  sell_color: [255, 107, 107],
  buy_color: [79, 163, 247],
  surplus_color: [242, 201, 76],
  grid_color: [167, 120, 230],
  export_color: [255, 159, 67],
};
const PRICE_COLOR_KEYS = ["cheap_color", "mid_color", "high_color", "negative_color", "sell_color", "buy_color", "surplus_color", "grid_color", "export_color"];
const PRICE_SCHEMA = (t) => [
  { name: "title", selector: { text: {} } },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "height", selector: { number: { min: 100, max: 600, step: 10, mode: "box", unit_of_measurement: "px" } } },
      { name: "show_extremes", selector: { boolean: {} } },
      { name: "show_buy_line", selector: { boolean: {} } },
      { name: "legend", selector: { boolean: {} } },
    ],
  },
  {
    type: "expandable",
    flatten: true,
    name: "colours",
    title: t("ed_colours"),
    schema: [{ type: "grid", name: "", schema: PRICE_COLOR_KEYS.map((name) => ({ name, selector: { color_rgb: {} } })) }],
  },
];

class EssManagerPriceCard extends EssChartCard {
  static get info() {
    return {
      name: "ESS Manager - Prices",
      description: "Today's and tomorrow's prices coloured by price level, with the planned buy / sell moments.",
      schema: PRICE_SCHEMA,
      defaults: PRICE_DEFAULTS,
      labels: {
        title: "ed_title", height: "ed_height", show_extremes: "ed_show_extremes", show_buy_line: "ed_show_buy_line",
        legend: "ed_legend", cheap_color: "ed_cheap_color", mid_color: "ed_mid_color", high_color: "ed_high_color",
        negative_color: "ed_negative_color", sell_color: "ed_sell_color", buy_color: "ed_buy_color",
        surplus_color: "ed_surplus_color", grid_color: "ed_grid_color", export_color: "ed_export_color",
      },
    };
  }

  getCardSize() {
    return 5;
  }

  _ensureHistory(siblings, dayStart, actionObj) {
    const id = siblings.battery_action;
    if (!id || this._histLoading) return;
    const key = `${id}|${dayStart}`;
    const now = Date.now();
    // a new Battery action (compared as text, so a clock difference between
    // Home Assistant and this device can't make it look new forever)
    const changed = actionObj && this._histFor && actionObj.last_changed !== this._histSeen;
    if (this._histFor === key && now - this._histAt < 300000 && !changed) return;
    this._histLoading = true;
    this._histSeen = actionObj ? actionObj.last_changed : null;
    fetchHistory(this._hass, [id], dayStart, now)
      .then((data) => {
        this._hist = { action: data[id] || [] };
      })
      .catch(() => {
        this._hist = { action: [] };
      })
      .finally(() => {
        this._histFor = key;
        this._histAt = Date.now();
        this._histLoading = false;
        this._renderKey = null;
        this._render();
      });
  }

  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj || !isStatusSensor(stateObj)) {
      setCardContent(this, BASE_CSS, notStatusMessage(this._hass, this._config.entity, stateObj));
      return;
    }
    const attrs = stateObj.attributes;
    const siblings = attrs.card_entities || {};
    const actionObj = siblings.battery_action ? this._hass.states[siblings.battery_action] : null;
    const width = this._chartWidth();
    const key = [stateObj, actionObj, this._hist, width, hassLang(this._hass), PRICE_VIEWS[this._config.entity]];
    if (this._renderKey && key.every((v, i) => v === this._renderKey[i])) return;
    this._renderKey = key;

    const opt = colorOptions(this._config, PRICE_DEFAULTS, PRICE_COLOR_KEYS);
    const f = formats(this._hass);
    const now = Date.now();
    const T0 = localMidnight(this._hass, now);
    this._ensureHistory(siblings, T0, actionObj);
    const title = esc(opt.title || this._t("price_title"));
    // Prices including taxes (as of 2026.10.44): the buy prices with a solar
    // deficit, the sell prices with a surplus - one kind at a time, named in
    // the header; tapping the header switches.
    const inclBuy = Array.isArray(attrs.all_buy_price_incl) ? attrs.all_buy_price_incl.map(num) : null;
    // selling is at the bare price (as from 2027)
    const inclSell = (attrs.all_price || []).map(num);
    const incl = !!(inclBuy && inclBuy.length);
    const autoView = attrs.solar_mode && attrs.solar_mode.mode === "surplus" ? "sell" : "buy";
    const view = incl ? PRICE_VIEWS[this._config.entity] || autoView : null;
    const prices = incl ? (view === "sell" ? inclSell : inclBuy) : (attrs.all_price || []).map(num);
    if (!prices.length) {
      setCardContent(this, BASE_CSS, `<div class="top"><span class="title">${title}</span></div><div class="dim">${esc(this._t("no_prices"))}</div>`);
      return;
    }
    const buy = incl ? prices : (attrs.all_buy_price || attrs.all_price).map(num);
    // 15-minute prices; an hourly price list (24 values a day) works too.
    const unitMs = (num(attrs.today_price_units) || 96) <= 25 ? HOUR_MS : UNIT_MS;
    const n = prices.length;
    // Always two whole days (today and tomorrow); until tomorrow's prices are
    // published, that half stays empty.
    const twoDays = nextMidnight(this._hass, nextMidnight(this._hass, T0));
    const T1 = Math.max(twoDays, T0 + n * unitMs);
    const slots = Math.max(n, Math.round((T1 - T0) / unitMs));
    const cur = clamp(Math.floor((now - T0) / unitMs), 0, n - 1);
    const W = width;
    const colors = { buy: opt.buy_color, negative: opt.buy_color, sell: opt.sell_color, spike: opt.sell_color,
                     grid: opt.grid_color, export: opt.export_color };
    const upcoming = planWindows(attrs).filter((w) => w.stop > T0 && w.start < T1);
    const ran = pastWindows(this._hist && this._hist.action, now)
      .filter((w) => w.stop > T0 && !upcoming.some((u) => u.side === w.side && u.start < w.stop && w.start < u.stop));
    const windows = ran.concat(upcoming).sort((a, b) => a.start - b.start);
    // Solar surplus (forecast): hours the battery is full or can't take all
    // the solar, so the rest goes to the grid.
    const surplus = (attrs.solar_surplus || [])
      .map((s) => ({ start: Math.max(Date.parse(s.start), now), stop: Date.parse(s.stop), kwh: num(s.kwh), reason: s.reason, surplus: true }))
      .filter((s) => s.stop > s.start && s.stop > T0 && s.start < T1);
    // the house from the grid at low prices (as of 2026.10.41)
    const gridUse = (attrs.grid_use || [])
      .map((g) => ({ start: Math.max(Date.parse(g.start), now), stop: Date.parse(g.stop), kwh: num(g.kwh) }))
      .filter((g) => g.stop > g.start && g.stop > T0 && g.start < T1);
    // solar export expected (as of 2026.10.41) - drawn like the surplus
    const exportExp = (attrs.solar_export_expected || [])
      .map((e) => ({ start: Math.max(Date.parse(e.start), now), stop: Date.parse(e.stop), export: true }))
      .filter((e) => e.stop > e.start && e.stop > T0 && e.start < T1);
    const X0 = 34;
    // room above the plot for the plan labels - only when there are plans
    const top = windows.length || surplus.length || gridUse.length || exportExp.length ? 18 : 8;
    const H = Math.max(clamp(Number(opt.height) || 170, 100, 600) - 18, 60);
    const bottom = top + H;
    const valid = prices.filter((v) => v !== null);
    // The buy price line only when it differs from the price (a transport
    // tariff is set); without one it would just trace the top of the bars.
    const showBuyLine = opt.show_buy_line !== false && buy.some((v, i) => v !== null && prices[i] !== null && Math.abs(v - prices[i]) > 1e-6);
    const lineVals = showBuyLine ? buy.filter((v) => v !== null) : [];
    let lo = Math.min(0, ...valid, ...lineVals);
    let hi = Math.max(...valid, ...lineVals);
    const steps = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5];
    const step = steps.find((s) => (hi - lo) / s <= 5) || 10;
    // round outwards to whole steps; the tiny margin absorbs float noise
    // (0 stays 0, a top of exactly 0.25 stays 0.25)
    lo = Math.floor(lo / step + 1e-9) * step;
    hi = Math.ceil(hi / step - 1e-9) * step;
    if (hi <= lo) hi = lo + step;
    const bw = (W - X0) / slots;
    const x = (t) => X0 + ((t - T0) / (T1 - T0)) * (W - X0);
    const xi = (i) => X0 + i * bw;
    const y = (v) => top + ((hi - v) / (hi - lo)) * H;
    const base = y(0);
    this._geo = { W, X0, top, H, bottom, bw, xi, y, T0, unitMs, n, slots };
    this._prices = { prices, buy, incl, inclBuy, inclSell };

    // colour by level: negative apart, then cheap -> average -> expensive
    const pmin = Math.max(0, Math.min(...valid));
    const pmax = Math.max(...valid, pmin + 0.001);
    const span = pmax - pmin;
    const off = (v) => `${clamp(((v - lo) / (hi - lo)) * 100, 0, 100).toFixed(2)}%`;
    const grad = `<linearGradient id="lvl" gradientUnits="userSpaceOnUse" x1="0" y1="${r1(y(lo))}" x2="0" y2="${r1(y(hi))}">
      <stop offset="0%" stop-color="${opt.negative_color}"/><stop offset="${off(-0.0001)}" stop-color="${opt.negative_color}"/>
      <stop offset="${off(Math.max(0.0001, pmin))}" stop-color="${opt.cheap_color}"/><stop offset="${off(pmin + span * 0.3)}" stop-color="${opt.cheap_color}"/>
      <stop offset="${off(pmin + span * 0.6)}" stop-color="${opt.mid_color}"/><stop offset="${off(pmin + span * 0.9)}" stop-color="${opt.high_color}"/>
      <stop offset="100%" stop-color="${opt.high_color}"/></linearGradient>`;
    const gap = bw > 2.5 ? 0.5 : 0;
    const bars = (indexes) => indexes
      .filter((i) => prices[i] !== null)
      .map((i) => `M${r1(xi(i))} ${r1(base)}V${r1(y(prices[i]))}H${r1(xi(i) + bw - gap)}V${r1(base)}Z`)
      .join("");

    // the plans: upcoming / running (card_plans) and what ran today
    const inWindow = (i) => {
      const t = T0 + i * unitMs;
      return windows.some((w) => t + unitMs > w.start && t < w.stop);
    };
    const all = [...Array(n).keys()];
    let under = "";
    let streaks = "";
    let labels = "";
    let lastRight = -Infinity;
    const placed = []; // label spans [left, right], so the surplus labels can avoid them
    for (const w of windows) {
      const x0 = x(Math.max(w.start, T0));
      const x1 = x(Math.min(w.stop, T1));
      const c = colors[w.kind];
      under += `<rect x="${r1(x0 - 1)}" y="${top - 4}" width="${r1(Math.max(x1 - x0 + 2, 2))}" height="${r1(H + 4)}" rx="3" fill="${c}" fill-opacity="0.07"/>`;
      streaks += `<rect x="${r1(x0 - 1)}" y="${r1(bottom + 3)}" width="${r1(Math.max(x1 - x0 + 2, 2))}" height="3" rx="1.5" fill="${c}"/>`;
      const text = `${planLabel(this._hass, w)} ${f.time(w.start)}`;
      const cx = (x0 + x1) / 2;
      const half = text.length * 3;
      if (clamp(cx, X0 + half, W - half) - half > lastRight + 4) {
        const lx = clamp(cx, X0 + half, W - half);
        labels += `<span class="plabel" style="left:${r1(lx)}px;top:0;color:${w.past ? "var(--secondary-text-color, #a0a0a0)" : tint(c, 1)}">${esc(text)}</span>`;
        placed.push([lx - half, lx + half]);
        lastRight = lx + half;
      }
    }
    // solar surplus blocks, below the plans in the label order
    let sunUnder = "";
    let sunStreaks = "";
    const sc = opt.surplus_color;
    for (const sp of surplus) {
      const x0 = x(sp.start);
      const x1 = x(Math.min(sp.stop, T1));
      const wd = Math.max(x1 - x0, 2);
      sunUnder += `<rect x="${r1(x0)}" y="${top - 4}" width="${r1(wd)}" height="${r1(H + 4)}" rx="3" fill="${sc}" fill-opacity="0.09"/>`;
      sunStreaks += `<rect x="${r1(x0)}" y="${r1(bottom + 3)}" width="${r1(wd)}" height="3" rx="1.5" fill="${sc}" fill-opacity="0.8"/>`;
      // a label where it doesn't overlap another one; otherwise just the
      // sun at the top of the column (if even that fits)
      const text = `${this._t("solar_surplus")} ${f.time(sp.start)}`;
      const free = (cx, half) => !placed.some(([a, b]) => cx - half < b + 6 && cx + half > a - 6);
      const half = text.length * 3 + 7;
      const lx = clamp((x0 + x1) / 2, X0 + half, W - half);
      const sx = clamp((x0 + x1) / 2, X0 + 6, W - 6);
      if (free(lx, half)) {
        labels += `<span class="plabel" style="left:${r1(lx)}px;top:0;color:${tint(sc, 1)}">${icon("sun", sc, 11, 2.2)}<span>${esc(text)}</span></span>`;
        placed.push([lx - half, lx + half]);
      } else if (free(sx, 6)) {
        labels += `<span class="plabel" style="left:${r1(sx)}px;top:0" title="${esc(text)}">${icon("sun", sc, 11, 2.2)}</span>`;
        placed.push([sx - 6, sx + 6]);
      }
    }
    // the house from the grid: its own colour, labelled where there's room
    const gc = opt.grid_color;
    for (const g of gridUse) {
      const x0 = x(g.start);
      const x1 = x(Math.min(g.stop, T1));
      const wd = Math.max(x1 - x0, 2);
      sunUnder += `<rect x="${r1(x0)}" y="${top - 4}" width="${r1(wd)}" height="${r1(H + 4)}" rx="3" fill="${gc}" fill-opacity="0.10"/>`;
      sunStreaks += `<rect x="${r1(x0)}" y="${r1(bottom + 3)}" width="${r1(wd)}" height="3" rx="1.5" fill="${gc}" fill-opacity="0.9"/>`;
      const text = `${this._t("grid_use")} ${f.time(g.start)}`;
      const half = text.length * 3;
      const lx = clamp((x0 + x1) / 2, X0 + half, W - half);
      if (!placed.some(([a, b]) => lx - half < b + 6 && lx + half > a - 6)) {
        labels += `<span class="plabel" style="left:${r1(lx)}px;top:0;color:${tint(gc, 1)}">${esc(text)}</span>`;
        placed.push([lx - half, lx + half]);
      }
    }
    // solar export expected: its own colour, dashed at the bottom (a forecast)
    const ec = opt.export_color;
    for (const e of exportExp) {
      const x0 = x(e.start);
      const x1 = x(Math.min(e.stop, T1));
      const wd = Math.max(x1 - x0, 2);
      sunUnder += `<rect x="${r1(x0)}" y="${top - 4}" width="${r1(wd)}" height="${r1(H + 4)}" rx="3" fill="${ec}" fill-opacity="0.10"/>`;
      sunStreaks += `<line x1="${r1(x0)}" y1="${r1(bottom + 4.5)}" x2="${r1(x0 + wd)}" y2="${r1(bottom + 4.5)}" stroke="${ec}" stroke-width="3" stroke-dasharray="4 3"/>`;
      const text = `${this._t("export_expected")} ${f.time(e.start)}`;
      const half = text.length * 3;
      const lx = clamp((x0 + x1) / 2, X0 + half, W - half);
      if (!placed.some(([a, b]) => lx - half < b + 6 && lx + half > a - 6)) {
        labels += `<span class="plabel" style="left:${r1(lx)}px;top:0;color:${tint(ec, 1)}">${esc(text)}</span>`;
        placed.push([lx - half, lx + half]);
      }
    }
    // y axis
    let axis = "";
    for (let v = lo; v <= hi + step / 2; v += step) {
      axis += `<text x="0" y="${r1(y(v) + 3)}">${esc(f.num(v, step < 0.1 ? 2 : 1))}</text>`;
      axis += `<line x1="${X0}" y1="${r1(y(v))}" x2="${W}" y2="${r1(y(v))}" stroke="rgba(127,127,127,${Math.abs(v) < step / 2 ? 0.35 : 0.12})"/>`;
    }
    const bg = "var(--ha-card-background, var(--card-background-color, #1c1c1c))";
    const xNow = x(now);
    let buyLine = "";
    if (showBuyLine) {
      const d = buy.map((v, i) => (v === null ? "" : `${i === 0 || buy[i - 1] === null ? "M" : "L"}${r1(xi(i))} ${r1(y(v))}H${r1(xi(i + 1))}`)).join("");
      buyLine = `<path d="${d}" fill="none" style="stroke:var(--primary-text-color, #e8e8e8)" stroke-opacity="0.4" stroke-width="1" stroke-dasharray="2 2"/>`;
    }
    const dayLine = nextMidnight(this._hass, T0);
    const svg = `<defs>${grad}</defs>${axis}${sunUnder}${under}
      <path d="${bars(all)}" fill="url(#lvl)" fill-opacity="0.75"/>
      <path d="${bars(all.filter(inWindow))}" fill="url(#lvl)"/>
      ${sunStreaks}${streaks}${buyLine}
      <rect x="${X0}" y="0" width="${r1(clamp(xNow - X0, 0, W - X0))}" height="${r1(bottom + 8)}" style="fill:${bg}" fill-opacity="0.6"/>
      ${dayLine ? `<line x1="${r1(x(dayLine))}" y1="${top - 4}" x2="${r1(x(dayLine))}" y2="${r1(bottom + 8)}" stroke="rgba(127,127,127,.45)"/>` : ""}
      ${n < slots ? `<text x="${r1((xi(n) + W) / 2)}" y="${r1(top + H / 2)}" text-anchor="middle" style="font-size:11px">${esc(this._t("no_prices"))}</text>` : ""}
      <line x1="${r1(xNow)}" y1="${top - 4}" x2="${r1(xNow)}" y2="${r1(bottom)}" style="stroke:var(--primary-text-color, #e8e8e8)" stroke-width="1.2"/>
      ${prices[cur] !== null ? `<circle cx="${r1(xNow)}" cy="${r1(y(prices[cur]))}" r="4" style="fill:var(--primary-text-color, #e8e8e8);stroke:${bg}" stroke-width="2"/>` : ""}`;

    // hour labels: every 6 hours, the new day by name
    let hours = "";
    for (let h = 0; T0 + h * HOUR_MS < T1; h += 6) {
      const t = T0 + h * HOUR_MS;
      const isDay = dayLine && Math.abs(t - dayLine) < HOUR_MS;
      if (h === 0 && !isDay) {
        hours += `<span style="left:${r1(x(t))}px">00</span>`;
        continue;
      }
      if (x(t) > W - 14) break;
      hours += `<span style="left:${r1(x(t) - 6)}px${isDay ? ";color:var(--primary-text-color, #e8e8e8);font-weight:600" : ""}">${esc(isDay ? f.dayLabel(t) : String(f.clock(t)[0]).padStart(2, "0"))}</span>`;
    }

    // header
    const nowP = prices[cur];
    const nowB = buy[cur];
    const tariff = num(attrs.transport_tariff) || 0;
    let buyText = "";
    if (!incl && nowB !== null && (tariff > 0 || nowB !== nowP)) buyText = `${this._t("buy_price")} ${f.money(nowB)}${tariff > 0 ? ` ${this._t("incl_transport")}` : ""}`;
    let extremes = "";
    if (opt.show_extremes !== false) {
      let iMin = null;
      let iMax = null;
      for (let i = cur; i < n; i++) {
        if (prices[i] === null) continue;
        if (iMin === null || prices[i] < prices[iMin]) iMin = i;
        if (iMax === null || prices[i] > prices[iMax]) iMax = i;
      }
      const when = (i) => `${f.weekday(T0 + i * unitMs)} ${f.time(T0 + i * unitMs)}`;
      if (iMin !== null) {
        extremes = `<div class="ext">
          <span class="xp" style="background:${tint(opt.negative_color, 0.16)}">${icon("down", opt.negative_color, 14)}<span class="xl">${esc(this._t("cheapest"))} ${esc(when(iMin))}</span><b>${esc(f.money(prices[iMin]))}</b></span>
          <span class="xp" style="background:${tint(opt.high_color, 0.16)}">${icon("up", opt.high_color, 14)}<span class="xl">${esc(this._t("most_expensive"))} ${esc(when(iMax))}</span><b>${esc(f.money(prices[iMax]))}</b></span>
        </div>`;
      }
    }
    const legend = opt.legend === false ? "" : `<div class="legend">
      <span><i style="width:36px;background:linear-gradient(90deg, ${opt.negative_color}, ${opt.cheap_color}, ${opt.mid_color}, ${opt.high_color})"></i>${esc(this._t("legend_level"))}</span>
      <span><i style="background:${tint(opt.sell_color, 0.6)}"></i>${esc(this._t("legend_sell"))}</span>
      <span><i style="background:${tint(opt.buy_color, 0.6)}"></i>${esc(this._t("legend_buy"))}</span>
      ${surplus.length ? `<span><i style="background:${tint(sc, 0.6)}"></i>${esc(this._t("legend_surplus"))}</span>` : ""}
      ${gridUse.length || windows.some((w) => w.kind === "grid") ? `<span><i style="background:${tint(gc, 0.8)}"></i>${esc(this._t("legend_grid_use"))}</span>` : ""}
      ${exportExp.length || windows.some((w) => w.kind === "export") ? `<span><i style="background:${tint(ec, 0.8)}"></i>${esc(this._t("legend_export"))}</span>` : ""}
      ${showBuyLine ? `<span><i style="width:12px;height:0;border-top:1px dashed var(--primary-text-color, #e8e8e8);border-radius:0"></i>${esc(this._t("legend_buy_line"))}</span>` : ""}
    </div>`;

    const css = `${BASE_CSS}
      .now { display: flex; flex-direction: column; gap: 2px; flex-grow: 1; min-width: 0; }
      .big { font-size: 28px; font-weight: 700; line-height: 1.1; white-space: nowrap; }
      .big small { font-size: 13px; font-weight: 500; color: var(--secondary-text-color, #a0a0a0); }
      .ext { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
      .xp { display: flex; align-items: center; gap: 6px; font-size: 12px; padding: 4px 10px; border-radius: 999px; white-space: nowrap; }
      .xl { flex-grow: 1; overflow: hidden; text-overflow: ellipsis; }
      @container (max-width: 420px) { .top { flex-direction: column; align-items: stretch; } }
      .top + div { margin-top: -8px; }
      .swap { cursor: pointer; }
    `;
    const changed = setCardContent(this, css, `
      <div class="top">
        <div class="now"><span class="dim${incl ? " swap" : ""}" style="font-size:13px"${incl ? ` title="${esc(this._t("switch_view"))}"` : ""}>${title}${incl ? ` \u00b7 ${esc(this._t(view === "sell" ? "sell_price" : "buy_price"))}` : ""} \u00b7 ${esc(this._t("now"))}</span>
          <span class="big${incl ? " swap" : ""}">${nowP === null ? "\u2013" : esc(f.money(nowP))}<small> ${esc(this._t("per_kwh"))}${incl ? ` \u00b7 ${esc(this._t(view === "sell" ? "excl_tax" : "incl_tax"))}` : ""}</small></span>
          ${buyText ? `<span class="dim" style="font-size:12px">${esc(buyText)}</span>` : ""}</div>
        ${extremes}
      </div>
      <div>
        <div class="chart" style="width:${W}px;height:${r1(bottom + 8)}px">
          <svg width="${W}" height="${r1(bottom + 8)}" viewBox="0 0 ${W} ${r1(bottom + 8)}">${svg}</svg>
          <svg class="cross" width="${W}" height="${r1(bottom + 8)}" viewBox="0 0 ${W} ${r1(bottom + 8)}"></svg>
          ${labels}
          <div class="tip"></div>
          <div class="hit" style="position:absolute;left:${X0}px;top:${top}px;width:${r1(W - X0)}px;height:${r1(H)}px"></div>
        </div>
        <div class="axisrow" style="width:${W}px;margin-top:2px">${hours}</div>
      </div>
      ${legend}
    `);
    this._windows = windows;
    this._surplus = surplus;
    for (const el of this.shadowRoot.querySelectorAll(".swap")) {
      el.onclick = () => {
        PRICE_VIEWS[this._config.entity] = view === "sell" ? "buy" : "sell";
        this._render();
      };
    }
    if (changed) this._wireTooltip((px) => this._showTip(px));
  }

  _showTip(px) {
    const cross = this.shadowRoot.querySelector(".cross");
    const tip = this.shadowRoot.querySelector(".tip");
    if (!cross || !tip || !this._geo) return;
    this._tipX = px;
    if (px === null || px === undefined) {
      cross.innerHTML = "";
      tip.style.display = "none";
      return;
    }
    const g = this._geo;
    const f = formats(this._hass);
    const i = clamp(Math.floor(px / g.bw), 0, g.slots - 1);
    if (i >= g.n) {
      // tomorrow's prices aren't known yet
      cross.innerHTML = "";
      tip.style.display = "none";
      return;
    }
    const t = g.T0 + i * g.unitMs;
    const p = this._prices.prices[i];
    const b = this._prices.buy[i];
    const xx = g.xi(i) + g.bw / 2;
    cross.innerHTML = `<line x1="${r1(xx)}" y1="${g.top}" x2="${r1(xx)}" y2="${g.bottom}" style="stroke:var(--primary-text-color, #e8e8e8)" stroke-opacity="0.7" stroke-dasharray="3 3"/>${
      p === null ? "" : `<circle cx="${r1(xx)}" cy="${r1(g.y(p))}" r="4" style="fill:var(--primary-text-color, #e8e8e8)" stroke="rgba(0,0,0,.5)" stroke-width="1.5"/>`
    }`;
    const w = (this._windows || []).find((win) => t + g.unitMs > win.start && t < win.stop);
    let html = `<div class="row"><b>${esc(f.dayLabel(t))} \u00b7 ${esc(f.time(t))}\u2013${esc(f.time(t + g.unitMs))}</b></div>`;
    const P = this._prices;
    if (P.incl) {
      const sellTax = "excl_tax";
      if (P.inclBuy[i] !== null) html += `<div class="row"><span class="k">${esc(this._t("buy_price"))} \u00b7 ${esc(this._t("incl_tax"))}</span><b>${esc(f.money(P.inclBuy[i]))}</b></div>`;
      if (P.inclSell[i] !== null) html += `<div class="row"><span class="k">${esc(this._t("sell_price"))} \u00b7 ${esc(this._t(sellTax))}</span><b>${esc(f.money(P.inclSell[i]))}</b></div>`;
    } else if (p !== null) html += `<div class="row"><span class="k">${esc(this._t("price"))}</span><b>${esc(f.money(p))}</b></div>`;
    if (!P.incl && b !== null && b !== p) html += `<div class="row"><span class="k">${esc(this._t("buy_price"))}</span><b>${esc(f.money(b))}</b></div>`;
    if (w) html += `<div class="row sep"><span class="k">${esc(planLabel(this._hass, w))}</span><b>${esc(f.time(w.start))}\u2013${esc(f.time(w.stop))}</b></div>`;
    const sp = (this._surplus || []).find((s) => t + g.unitMs > s.start && t < s.stop);
    if (sp) {
      const why = sp.reason === "rate" ? this._t("surplus_rate") : this._t("surplus_full");
      html += `<div class="row sep"><span class="k">${esc(this._t("solar_surplus"))}</span><b>${esc(f.time(sp.start))}\u2013${esc(f.time(sp.stop))}</b></div>`;
      html += `<div class="row"><span class="k">${esc(why)}</span>${sp.kwh ? `<b>${esc(this._t("surplus_kwh")(f.num(sp.kwh, 1)))}</b>` : ""}</div>`;
    }
    tip.innerHTML = html;
    tip.style.display = "flex";
    const tipW = tip.offsetWidth || 150;
    tip.style.left = `${r1(xx + 12 + tipW > g.W ? Math.max(xx - 12 - tipW, 0) : xx + 12)}px`;
    tip.style.top = "0px";
  }
}

// -- Card editor ------------------------------------------------------------------
// One editor for all cards: the Status sensor plus the card's own options,
// labelled in the user's language; only what differs from the defaults
// ends up in the card's YAML.
class EssManagerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    const info = this.cardInfo || {};
    const defaults = info.defaults || {};
    const t = (key) => tr(this._hass, key);
    const labels = { entity: "ed_entity", ...(info.labels || {}) };
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...this._config, ...ev.detail.value };
        for (const [key, value] of Object.entries(defaults)) {
          if (JSON.stringify(config[key]) === JSON.stringify(value)) delete config[key];
        }
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.computeLabel = (field) => (labels[field.name] ? t(labels[field.name]) : field.title || field.name);
    this._form.hass = this._hass;
    const schema = typeof info.schema === "function" ? info.schema(t) : info.schema || [];
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { filter: { integration: ESS_DOMAIN, domain: "sensor" } } } },
      ...schema,
    ];
    this._form.data = { ...defaults, ...this._config };
  }
}

// -- Status card (as of v0.5.0) -------------------------------------------------
// Sell (left) and Buy (right): start / stop, a bar that fills with the
// energy done (not the time - a plan stops on its target), energy and target
// SOC; an active spike or negative price plan shows in the block it drives
// (chip + outline). Below: spike and negative price status, the control
// toggle and a slim timeline of the Battery action sensor's history.
// the solar surplus in the planning panel (as of 2026.11.21) - the price card's default colour
const SURPLUS_COLOR = "rgb(242, 201, 76)";
const STATUS_DEFAULTS = {
  title: "ESS Manager",
  automation: "",
  hours: 24,
  show_history: true,
  sell_color: [255, 107, 107],
  buy_color: [79, 163, 247],
  spike_color: [255, 179, 0],
  negative_color: [77, 208, 225],
  grid_color: [167, 120, 230],
  export_color: [255, 159, 67],
};
const STATUS_COLOR_KEYS = ["sell_color", "buy_color", "spike_color", "negative_color", "grid_color", "export_color"];
const STATUS_SCHEMA = (t) => [
  { name: "title", selector: { text: {} } },
  { name: "automation", selector: { entity: { filter: [{ domain: "automation" }, { domain: "input_boolean" }, { domain: "switch" }] } } },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "show_history", selector: { boolean: {} } },
      { name: "hours", selector: { number: { min: 1, max: 72, step: 1, mode: "box", unit_of_measurement: "h" } } },
    ],
  },
  {
    type: "expandable",
    flatten: true,
    name: "colours",
    title: t("ed_colours"),
    schema: [{ type: "grid", name: "", schema: STATUS_COLOR_KEYS.map((name) => ({ name, selector: { color_rgb: {} } })) }],
  },
];
// The timeline follows the card's Sell / Buy colours (as of v0.5.9): the
// colour itself for the faster negative price charge / spike discharge, a
// darker shade of it for normal charging / discharging, dark grey for idle.
function shade(hex, factor) {
  const rgb = hexToRgb(hex) || [128, 128, 128];
  return toHex(rgb.map((c) => c * factor));
}
const BALANCE_COLOR = "#b39ddb";
function timelineColors(opt) {
  return {
    idle: "#3b3b3b",
    balancing: BALANCE_COLOR,
    charge: shade(opt.buy_color, 0.5),
    negative_price_charge: opt.buy_color,
    discharge: shade(opt.sell_color, 0.5),
    spike_discharge: opt.sell_color,
    // the house from the grid / solar export (as of 2026.11.0): the same
    // colours as on the price and battery charts
    grid_use: opt.grid_color,
    solar_export: opt.export_color,
  };
}

class EssManagerStatusCard extends HTMLElement {
  static get info() {
    return {
      name: "ESS Manager - Status",
      description: "Sell and buy plans with progress, price plans, control toggle and timeline.",
      schema: STATUS_SCHEMA,
      defaults: STATUS_DEFAULTS,
      labels: {
        title: "ed_title", automation: "ed_automation", hours: "ed_hours", show_history: "ed_show_history",
        sell_color: "ed_sell_color", buy_color: "ed_buy_color", spike_color: "ed_spike_color", negative_color: "ed_negative_plan_color", grid_color: "ed_grid_color", export_color: "ed_export_color",
      },
    };
  }

  static getStubConfig(hass) {
    return { entity: findStatusSensor(hass) || "" };
  }

  static getConfigElement() {
    const editor = document.createElement("ess-manager-card-editor");
    editor.cardInfo = this.info;
    return editor;
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("Choose the ESS Manager Status sensor (entity)");
    this._config = config;
    this._history = null;
    this._historyFor = null;
    this._renderKey = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 6;
  }

  connectedCallback() {
    this._timer = setInterval(() => {
      this._renderKey = null;
      this._render();
    }, 60000);
    // a width change can make the header too tight for "Settings" (or roomy again)
    if (!this._resize && window.ResizeObserver) this._resize = new ResizeObserver(() => this._fitHeader());
    if (this._resize) this._resize.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    if (this._resize) this._resize.disconnect();
  }

  _t(key) {
    return tr(this._hass, key);
  }

  _opt() {
    return colorOptions(this._config, STATUS_DEFAULTS, STATUS_COLOR_KEYS);
  }

  _time(iso) {
    return formats(this._hass).time(Date.parse(iso));
  }

  _weekday(iso) {
    return formats(this._hass).weekday(Date.parse(iso));
  }

  _num(value, digits) {
    return formats(this._hass).num(value, digits);
  }

  _duration(minutes) {
    const m = Math.max(Math.round(minutes), 0);
    const h = Math.floor(m / 60);
    const rest = String(m % 60).padStart(2, "0");
    return h ? `${h} ${this._t("h")} ${rest} ${this._t("min")}` : `${m % 60} ${this._t("min")}`;
  }

  _toggleEntity(attrs) {
    if (this._config.automation) return this._config.automation;
    const control = attrs.control || {};
    const siblings = attrs.card_entities || {};
    if (control.mode === "number" && control.target && siblings.automatic_control) return siblings.automatic_control;
    return null;
  }

  _block(side, plan, opt) {
    const sell = side === "sell";
    const color = sell ? opt.sell_color : opt.buy_color;
    const chipInfo = plan && {
      spike: [this._t("spike"), opt.spike_color, "spike"],
      negative_price: [this._t("negative"), opt.negative_color, "negative"],
      full_charge: [this._t("balancing"), BALANCE_COLOR, "balancing"],
    }[plan.source];
    // the plan that drives the block outlines it in its colour: spike, negative price, full-charge balancing
    const outline = plan && ["spike", "negative_price", "full_charge"].includes(plan.source) ? chipInfo[1] : "transparent";
    const head = `<div class="head"><span class="name" style="color:${color}">${icon(sell ? "up" : "down", color, 16, 2.2)}${esc(this._t(sell ? "plan_sell" : "plan_buy"))}</span>${
      chipInfo ? `<span class="chip" style="background:${tint(chipInfo[1], 0.18)};color:${chipInfo[1]}">${icon(chipInfo[2], chipInfo[1], 12, 2.4)}${esc(chipInfo[0])}</span>` : ""
    }</div>`;
    if (!plan) {
      return `<div class="block none" style="border-color:transparent">${head}<div class="empty"><span class="long">${esc(this._t(sell ? "no_sell" : "no_buy"))}</span><span class="short">${esc(this._t("none_short"))}</span></div></div>`;
    }
    const minutes = (new Date(plan.stop) - new Date(plan.start)) / 60000;
    const energy = plan.energy_kwh || 0;
    const progress = energy > 0 ? Math.min(Math.max(plan.done_kwh / energy, 0), 1) : 0;
    let inBar;
    let below;
    const holding = plan.phase === "holding";
    if (holding) {
      // at 100 %, waiting for the cells to balance - until they are, at the latest at stop
      inBar = esc(this._t("balancing_max")(this._duration((new Date(plan.stop) - Date.now()) / 60000)));
      below = esc(this._t("balancing"));
    } else if (plan.target_reached) {
      inBar = `${icon("check", "#ffffff", 14, 2.6)} ${esc(this._t("done"))}`;
      below = esc(this._t("done"));
    } else if (plan.started) {
      const left = plan.rate_kw > 0 ? (plan.remaining_kwh / plan.rate_kw) * 60 : (new Date(plan.stop) - Date.now()) / 60000;
      inBar = esc(this._t("left")(this._duration(left)));
      below = `${esc(this._t("running"))} \u00b7 ${this._num(plan.done_kwh, 1)} ${esc(this._t("of"))} ${this._num(energy, 1)} kWh`;
    } else {
      inBar = esc(this._duration(minutes));
      below = `${esc(this._t("planned"))} \u00b7 ${esc(this._weekday(plan.start))}`;
    }
    const span = new Date(plan.stop) - new Date(plan.start);
    const elapsed = span > 0 ? Math.min(Math.max((Date.now() - new Date(plan.start)) / span, 0), 1) : 0;
    const fill = holding ? elapsed * 100 : plan.target_reached ? 100 : plan.started ? progress * 100 : 0;
    const barColor = holding ? BALANCE_COLOR : color;
    const soc = plan.target_soc_percent;
    return `<div class="block" style="border-color:${outline}">${head}
      <div class="times"><span>${plan.started ? "" : `<span class="dim">${esc(this._weekday(plan.start))}</span> `}${esc(this._time(plan.start))}</span><span>${esc(this._time(plan.stop))}${plan.more_blocks ? ` <span class="dim" title="${esc(this._moreBlocksTip(plan))}">${esc(this._t("more_blocks")(plan.more_blocks))}</span>` : ""}</span></div>
      <div class="bar" title="${below}" style="background:${tint(barColor, 0.22)}"><div class="fill" style="width:${fill.toFixed(1)}%;background:${barColor}"></div><div class="bartext">${inBar}</div></div>
      ${holding ? this._balanceStat(plan) : `<div class="stat">${icon("bolt", color, 16)}<b>${this._num(energy, 1)}</b><span class="dim unit">kWh</span><span class="dim arrow">\u2192</span>${
        soc == null ? "" : `${batteryIcon(soc, color)}<b>${this._num(soc, 0)} %</b>`
      }</div>`}
      ${!holding && plan.hold_until ? `<div class="dim" style="font-size:12px;margin-top:4px">${esc(this._t("balance_after")(this._time(plan.hold_until)))}</div>` : ""}
    </div>`;
  }

  // The planning panel (as of 2026.11.19): every plan from now on in time
  // order (card_plans.all), a 24-hour timeline on top; a sheet over the
  // page, closed with the cross, a tap outside it or Escape.
  _renderPanel(attrs, opt) {
    const root = this.shadowRoot;
    let el = root.querySelector(".pp-overlay");
    if (!this._panelOpen) {
      if (el) el.remove();
      return;
    }
    if (!el) {
      el = document.createElement("div");
      el.className = "pp-overlay";
      root.appendChild(el);
      el.addEventListener("click", (ev) => {
        if (ev.target === el || ev.target.closest(".pp-x")) { this._panelOpen = false; this._renderPanel(attrs, opt); }
      });
      if (!this._escHandler) {
        this._escHandler = (ev) => { if (ev.key === "Escape" && this._panelOpen) { this._panelOpen = false; this._renderPanel(attrs, opt); } };
        window.addEventListener("keydown", this._escHandler);
      }
    }
    const f = formats(this._hass);
    const plans = ((attrs.card_plans || {}).all || []).filter((i) => new Date(i.stop).getTime() > Date.now());
    // (as of 2026.11.21) the solar surplus too, as on the price chart - not a plan, so not "next"
    const surplus = (attrs.solar_surplus || []).filter((s) => new Date(s.stop).getTime() > Date.now()).map((s) => ({
      kind: "surplus", start: s.start, stop: s.stop, kwh: s.kwh, reason: s.reason, info: true,
      running: new Date(s.start).getTime() <= Date.now(),
    }));
    const items = [...plans, ...surplus].sort((a, b) => new Date(a.start) - new Date(b.start));
    const firstPlan = items.findIndex((i) => !i.info);
    const colors = {
      charge: opt.buy_color, sell: opt.sell_color, grid: opt.grid_color, full_charge: BALANCE_COLOR, balancing: BALANCE_COLOR,
      spike_charge: opt.spike_color, spike_sell: opt.spike_color, negative_charge: opt.negative_color,
      negative_sell: opt.negative_color, solar_export: opt.export_color, surplus: SURPLUS_COLOR,
    };
    const now = Date.now();
    const span = 24 * 3600000;
    const segs = items.map((i) => {
      const a = Math.max(new Date(i.start).getTime(), now);
      const b = Math.min(new Date(i.stop).getTime(), now + span);
      if (b <= a) return "";
      return `<span style="left:${(((a - now) / span) * 100).toFixed(2)}%;width:${Math.max(((b - a) / span) * 100, 0.6).toFixed(2)}%;background:${colors[i.kind]}"></span>`;
    }).join("");
    let rows = "";
    let day = null;
    items.forEach((i, n) => {
      const d = this._weekday(i.start);
      const dkey = new Date(i.start).toDateString();
      if (dkey !== day) {
        day = dkey;
        rows += `<div class="pp-day">${esc(d)}</div>`;
      }
      const bits = [];
      if (i.kind === "grid") bits.push((i.kwh || 0) >= 0.05 ? `${this._num(i.kwh, 1)} ${this._t("grid_kept_short")}` : this._t("grid_sun"));
      else if (i.kind === "surplus") {
        bits.push(this._t(i.reason === "rate" ? "surplus_rate" : "surplus_full"));
        if (i.kwh) bits.push(this._t("surplus_kwh")(this._num(i.kwh, 1)));
      }
      else if (i.kwh != null && i.kwh > 0) bits.push(`${this._num(i.kwh, 1)} kWh`);
      if (i.price != null && i.kind !== "grid" && i.kind !== "surplus") bits.push(f.money(i.price));
      if (i.hold_until) bits.push(this._t("balance_until")(this._time(i.hold_until)));
      const tag = i.running ? this._t("pp_now") : n === firstPlan ? this._t("pp_next") : "";
      const c = colors[i.kind] || "#888";
      rows += `<div class="pp-item${i.running ? " run" : ""}" style="--c:${c}"><span class="pp-chip"></span><span class="pp-time">${esc(this._time(i.start))} \u2013 ${esc(this._time(i.stop))}</span><span class="pp-what"><b>${esc(this._t("pp_" + i.kind))}</b> <span class="dim">${esc(bits.join(" \u00b7 "))}</span></span><span class="pp-end">${
        tag ? `<span class="pp-tag">${esc(tag)}</span>` : i.soc != null ? `\u2192 ${this._num(i.soc, 0)} %` : ""
      }</span></div>`;
    });
    el.innerHTML = `<div class="pp-sheet" role="dialog" aria-label="${esc(this._t("pp_title"))}">
      <div class="pp-grab"></div>
      <div class="pp-head"><b>${esc(this._t("pp_title"))}</b><button class="pp-x" aria-label="${esc(this._t("pp_close"))}">\u2715</button></div>
      <div class="pp-tl">${segs}</div>
      <div class="pp-ax"><span>${esc(this._t("now"))}</span><span>+6 ${esc(this._t("h"))}</span><span>+12 ${esc(this._t("h"))}</span><span>+18 ${esc(this._t("h"))}</span><span>+24 ${esc(this._t("h"))}</span></div>
      ${rows || `<div class="empty">${esc(this._t("pp_none"))}</div>`}
    </div>`;
  }

  // The house from the grid (as of 2026.11.17): the current or next window
  // of grid use - its times, a bar that fills while it runs, what it keeps
  // in the battery; "+n" for the later windows (their times as a tooltip).
  _gridBlock(windows, opt) {
    const color = opt.grid_color;
    const head = `<div class="head"><span class="name" style="color:${color}">${icon("home", color, 16, 2.2)}${esc(this._t("plan_grid"))}</span></div>`;
    const now = Date.now();
    const list = (windows || []).filter((w) => new Date(w.stop).getTime() > now);
    if (!list.length) {
      return `<div class="block grid-block none" style="border-color:transparent">${head}<div class="empty"><span class="long">${esc(this._t("no_grid"))}</span><span class="short">${esc(this._t("none_short"))}</span></div></div>`;
    }
    const w = list[0];
    const start = new Date(w.start).getTime();
    const stop = new Date(w.stop).getTime();
    const running = start <= now;
    const more = list.length - 1;
    const tip = more ? [this._t("grid_more_tip")(more)].concat(list.slice(1).map((b) => `${this._weekday(b.start)} ${this._time(b.start)}\u2013${this._time(b.stop)}`)).join("\n") : "";
    const fill = running && stop > start ? Math.min(Math.max((now - start) / (stop - start), 0), 1) * 100 : 0;
    const inBar = running ? this._t("left")(this._duration((stop - now) / 60000)) : this._duration((stop - start) / 60000);
    const kwh = Number(w.kwh) || 0;
    const stat = kwh >= 0.05
      ? `<div class="stat">${icon("home", color, 16)}<b>${this._num(kwh, 1)}</b><span class="dim long">${esc(this._t("grid_kept"))}</span><span class="dim short">${esc(this._t("grid_kept_short"))}</span></div>`
      : `<div class="stat" title="${esc(this._t("grid_sun_tip"))}">${icon("sun", color, 16)}<span class="dim">${esc(this._t("grid_sun"))}</span></div>`;
    return `<div class="block grid-block" style="border-color:transparent">${head}
      <div class="times"><span>${running ? "" : `<span class="dim">${esc(this._weekday(w.start))}</span> `}${esc(this._time(w.start))}</span><span>${esc(this._time(w.stop))}${more ? ` <span class="dim" title="${esc(tip)}">${esc(this._t("more_blocks")(more))}</span>` : ""}</span></div>
      <div class="bar" style="background:${tint(color, 0.22)}"><div class="fill" style="width:${fill.toFixed(1)}%;background:${color}"></div><div class="bartext">${esc(inBar)}</div></div>
      ${stat}
    </div>`;
  }

  // While balancing: the cell voltage differential against its target, the
  // value in the balance colour until it's below it.
  // The holding phase's stat row: the cell voltage difference and the goal
  // (green once below it); the battery voltage against its target as a
  // tooltip.
  // the later blocks of a charge in several blocks, for the "+2" tooltip
  _moreBlocksTip(plan) {
    const list = (plan.blocks || []).map((b) => `${this._weekday(b.start)} ${this._time(b.start)}\u2013${this._time(b.stop)}`);
    return [this._t("more_blocks_tip")(plan.more_blocks)].concat(list).join("\n");
  }

  _balanceStat(plan) {
    const diff = plan.voltage_diff_mv;
    const goal = plan.balance_threshold_mv;
    const ok = diff != null && goal != null && diff < goal;
    const mv = (v) => (v == null ? "\u2013" : `${this._num(v, 0)} mV`);
    const volt = (v) => (v == null ? "\u2013" : this._num(v, 1));
    let tip = `${this._t("cell_diff")}: ${mv(diff)}`;
    if (plan.battery_voltage != null || plan.target_voltage != null) {
      tip += `\n${this._t("pack_voltage")}: ${volt(plan.battery_voltage)} / ${volt(plan.target_voltage)} V`;
    }
    return `<div class="stat" title="${esc(tip)}">${icon("balancing", BALANCE_COLOR, 16)}<b style="color:${ok ? "#6fcf97" : BALANCE_COLOR}">${esc(mv(diff))}</b><span class="dim arrow">\u2192</span><span class="dim">&lt;</span><b>${esc(mv(goal))}</b></div>`;
  }

  _planTile(kind, plan, opt) {
    const isSpike = kind === "spike";
    const color = isSpike ? opt.spike_color : opt.negative_color;
    const active = !!(plan && plan.active);
    let detail = this._t(active ? "active" : "inactive");
    const money = (v) => formats(this._hass).money(v);
    if (active && isSpike && plan.day_min_price != null) {
      detail += ` \u00b7 ${money(plan.day_min_price)} \u2192 ${money(plan.day_max_price)}`;
    } else if (active && !isSpike && plan.threshold != null) {
      detail += ` \u00b7 ${this._t("below")} ${money(plan.threshold)}`;
    }
    return `<div class="tile" style="background:${active ? tint(color, 0.16) : "rgba(127,127,127,.12)"}">${icon(isSpike ? "spike" : "negative", active ? color : "#a0a0a0", 20)}
      <div class="col"><span class="tname">${esc(this._t(isSpike ? "spike" : "negative"))}</span><span class="tdetail" style="color:${active ? color : "var(--secondary-text-color, #a0a0a0)"}">${esc(detail)}</span></div></div>`;
  }

  async _loadHistory(entityId, hours) {
    const key = `${entityId}|${hours}`;
    const now = Date.now();
    if (this._historyFor === key && this._historyAt && now - this._historyAt < 300000) return;
    if (this._historyLoading) return;
    this._historyLoading = true;
    const actionObj = this._hass.states[entityId];
    this._historySeen = actionObj ? actionObj.last_changed : null;
    try {
      const start = now - hours * HOUR_MS;
      const items = (await fetchHistory(this._hass, [entityId], start, now))[entityId] || [];
      const segments = [];
      items.forEach(([from, state], i) => {
        const to = items[i + 1] ? Math.min(items[i + 1][0], now) : now;
        if (to > from) segments.push({ state, seconds: (to - from) / 1000 });
      });
      this._history = segments;
    } catch (err) {
      this._history = [];
    } finally {
      this._historyFor = key;
      this._historyAt = now;
      this._historyLoading = false;
      this._renderKey = null;
      this._render();
    }
  }

  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const opt = this._opt();
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj || !isStatusSensor(stateObj)) {
      setCardContent(this, BASE_CSS, notStatusMessage(this._hass, this._config.entity, stateObj));
      return;
    }
    const attrs = stateObj.attributes;
    const siblings = attrs.card_entities || {};
    const actionId = siblings.battery_action;
    const actionObj = actionId ? this._hass.states[actionId] : null;
    const toggleId = this._toggleEntity(attrs);
    const toggleObj = toggleId ? this._hass.states[toggleId] : null;
    const key = [stateObj, actionObj, toggleObj, this._history, hassLang(this._hass)];
    if (this._renderKey && key.every((v, i) => v === this._renderKey[i])) return;
    this._renderKey = key;
    if (opt.show_history && actionId && this._historyFor !== `${actionId}|${opt.hours}` && !this._historyLoading) {
      this._loadHistory(actionId, opt.hours);
    } else if (opt.show_history && actionId && actionObj && this._historyAt && actionObj.last_changed !== this._historySeen) {
      // a new Battery action (compared as text: a clock difference between
      // Home Assistant and this device must not reload it over and over)
      this._historyAt = 0;
      this._loadHistory(actionId, opt.hours);
    }

    const plans = attrs.card_plans || {};
    const action = actionObj ? actionObj.state : attrs.control_action;
    const dot = { charge: opt.buy_color, negative_price_charge: opt.buy_color, discharge: opt.sell_color, spike_discharge: opt.sell_color, balancing: BALANCE_COLOR }[action] || "#8a8a8a";

    // the control toggle sits in the header, its name as a tooltip
    let toggle = "";
    if (toggleObj) {
      const on = toggleObj.state === "on";
      const label = !this._config.automation ? this._t("auto_control") : toggleObj.attributes.friendly_name || toggleId;
      toggle = `<button type="button" class="switch ${on ? "on" : ""}" title="${esc(label)}" aria-pressed="${on}" aria-label="${esc(label)}" style="background:${on ? opt.buy_color : "#4a4a4a"}"><span></span></button>`;
    }

    // Settings (as of v0.5.10): to the ESS Manager device page with all its
    // numbers, switches and sensors - only for admins, who can open it.
    let settings = "";
    if (!this._hass.user || this._hass.user.is_admin) {
      const label = this._t("settings");
      settings = `<button type="button" class="setbtn" title="${esc(label)}" aria-label="${esc(label)}">${icon("cog", "currentColor", 15)}<span class="lbl">${esc(label)}</span></button>`;
    }

    let timeline = "";
    if (opt.show_history && actionId) {
      const segs = this._history || [];
      const colors = timelineColors(opt);
      const total = segs.reduce((sum, seg) => sum + seg.seconds, 0);
      const parts = total
        ? segs.map((seg) => `<span style="flex:${seg.seconds} 0 0;background:${colors[seg.state] || "#2a2a2a"}"></span>`).join("")
        : `<span style="flex:1 0 0;background:#2a2a2a"></span>`;
      const hours = opt.hours;
      timeline = `<div class="timeline">${parts}</div>
        <div class="axis"><span>${esc(this._t("ago")(hours))}</span><span>${esc(this._t("ago")(Math.round(hours / 2)))}</span><span>${esc(this._t("now"))}</span></div>`;
    }

    const css = `
      ha-card { padding: 16px; display: flex; flex-direction: column; gap: 14px; container-type: inline-size; container-name: card; }
      .top .title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
      .top { display: flex; align-items: center; gap: 10px; }
      .title { font-family: var(--ha-card-header-font-family, inherit); font-size: var(--ha-card-header-font-size, 24px); font-weight: var(--ha-card-header-font-weight, 500); letter-spacing: -0.012em; line-height: 1.2; flex-grow: 1; }
      .status { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--secondary-text-color, #a0a0a0); white-space: nowrap; }
      .status i { width: 8px; height: 8px; border-radius: 999px; display: inline-block; }
      .setbtn { border: none; cursor: pointer; background: rgba(127,127,127,.15); color: var(--secondary-text-color, #a0a0a0); display: inline-flex; align-items: center; justify-content: center; gap: 5px; font: inherit; font-size: 12px; height: 28px; border-radius: 999px; padding: 0 10px 0 8px; flex-shrink: 0; margin-left: 4px; white-space: nowrap; }
      .setbtn:hover { background: rgba(127,127,127,.25); color: var(--primary-text-color, #e8e8e8); }
      .top.tight .setbtn { width: 30px; height: 30px; padding: 0; }
      .top.tight .setbtn .lbl { display: none; }
      .blocks, .tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
      @container card (max-width: 380px) { .blocks, .tiles { grid-template-columns: minmax(0, 1fr); } }
      /* three blocks (as of 2026.11.18): one row, a block without a plan a
         narrow strip, the planned ones share the rest; a block narrower than
         200 px gets compact lines; on a phone under each other, an empty
         block a low bar */
      .block .short, .stat .short { display: none; }
      .blocks > .block:not(.none) { cursor: pointer; }
      .pp-overlay { position: fixed; inset: 0; z-index: 9; background: rgba(0,0,0,.65); -webkit-backdrop-filter: blur(3px); backdrop-filter: blur(3px); display: flex; align-items: flex-end; justify-content: center; }
      .pp-sheet { width: 100%; max-width: 560px; max-height: 82vh; overflow: auto; background-color: var(--primary-background-color, #1c1c1e); background-image: linear-gradient(var(--ha-card-background, var(--card-background-color, #26282e)), var(--ha-card-background, var(--card-background-color, #26282e))); -webkit-backdrop-filter: blur(24px) saturate(1.3); backdrop-filter: blur(24px) saturate(1.3); color: var(--primary-text-color, #e8e8e8); border-radius: 18px 18px 0 0; padding: 12px 16px 18px; box-shadow: 0 -8px 30px rgba(0,0,0,.45); }
      .pp-grab { width: 40px; height: 4px; border-radius: 2px; background: rgba(127,127,127,.5); margin: 0 auto 10px; }
      .pp-head { display: flex; align-items: center; margin-bottom: 10px; }
      .pp-head b { flex: 1; font-size: 16px; }
      .pp-x { border: none; background: rgba(127,127,127,.18); color: inherit; width: 30px; height: 30px; border-radius: 999px; cursor: pointer; font-size: 14px; }
      .pp-tl { position: relative; height: 12px; border-radius: 6px; background: rgba(127,127,127,.25); overflow: hidden; }
      .pp-tl span { position: absolute; top: 0; bottom: 0; border-radius: 2px; }
      .pp-ax { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color, #a0a0a0); margin: 3px 0 6px; }
      .pp-day { font-size: 12px; color: var(--secondary-text-color, #a0a0a0); text-transform: uppercase; letter-spacing: .06em; margin: 10px 0 6px; }
      .pp-item { display: grid; grid-template-columns: 10px 96px minmax(0, 1fr) auto; gap: 8px; align-items: center; padding: 8px 10px; border-radius: 8px; background: rgba(127,127,127,.12); margin-bottom: 6px; font-size: 13px; }
      .pp-item.run { box-shadow: inset 0 0 0 1.5px var(--c); }
      .pp-chip { width: 10px; height: 10px; border-radius: 3px; background: var(--c); }
      .pp-what { min-width: 0; }
      .pp-what b { font-weight: 600; }
      .pp-end { white-space: nowrap; }
      .pp-tag { font-size: 11px; padding: 1px 7px; border-radius: 999px; color: var(--c); background: color-mix(in srgb, var(--c) 20%, transparent); }
      @container card (max-width: 380px) { .pp-item { grid-template-columns: 10px 84px minmax(0, 1fr); } .pp-end { grid-column: 2 / -1; } }
      .blocks.three { display: flex; gap: 10px; }
      .blocks.three > .block { flex: 1 1 0; min-width: 0; container-type: inline-size; }
      .blocks.three > .block.none { flex: 0 0 72px; align-items: center; justify-content: center; padding: 10px 6px; }
      .blocks.three > .block.none .long { display: none; }
      .blocks.three > .block.none .short { display: inline; }
      .blocks.three > .block.none .head { flex-direction: column; }
      .blocks.three > .block.none .name { flex-direction: column; gap: 6px; font-size: 11px; text-align: center; white-space: normal; flex-grow: 0; }
      .blocks.three > .block.none .empty { padding: 0; font-size: 11px; }
      @container (max-width: 200px) {
        .stat { flex-wrap: wrap; row-gap: 2px; justify-content: center; }
        .stat .unit, .stat .arrow, .stat .long { display: none; }
        .stat .short { display: inline; }
      }
      @container card (max-width: 380px) {
        .blocks.three { flex-direction: column; }
        .blocks.three > .block, .blocks.three > .block.none { flex: none; }
        .blocks.three > .block.none { flex-direction: row; justify-content: space-between; padding: 8px 10px; }
        .blocks.three > .block.none .head { flex-direction: row; }
        .blocks.three > .block.none .name { flex-direction: row; font-size: 13px; }
      }
      @container card (min-width: 381px) and (max-width: 480px) { .stat { gap: 4px; padding: 7px 6px; } .stat b { font-size: 14px; } .stat .dim { font-size: 11px; } .arrow { padding: 0; } }
      @container card (min-width: 381px) and (max-width: 440px) { .stat .unit { display: none; } }
      .block { display: flex; flex-direction: column; gap: 7px; border: 2px solid transparent; border-radius: 10px; padding: 10px; background: rgba(127,127,127,.12); }
      .head { display: flex; align-items: center; gap: 6px; }
      .name { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; flex-grow: 1; }
      .chip { display: flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
      .empty { font-size: 13px; color: var(--secondary-text-color, #a0a0a0); padding: 18px 0; text-align: center; }
      .times { display: flex; justify-content: space-between; }
      .times { font-size: 13px; }
      .bar { position: relative; height: 22px; border-radius: 6px; overflow: hidden; }
      .fill { position: absolute; left: 0; top: 0; bottom: 0; }
      .bartext { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: 4px; font-size: 12px; font-weight: 600; color: #ffffff; text-shadow: 0 0 3px rgba(0,0,0,.6); white-space: nowrap; }
      .stat { display: flex; align-items: center; gap: 5px; white-space: nowrap; background: rgba(127,127,127,.12); border-radius: 8px; padding: 7px 8px; min-width: 0; overflow: hidden; }
      .stat b { font-size: 15px; }
      .dim { font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
      .arrow { font-size: 13px; padding: 0 2px; }
      .batt { width: 22px; height: 12px; border: 2px solid var(--secondary-text-color, #a0a0a0); border-radius: 3px; padding: 1px; box-sizing: border-box; display: inline-flex; flex-shrink: 0; }
      .batt span { border-radius: 1px; }
      .tile { border-radius: 10px; padding: 10px 12px; display: flex; align-items: center; gap: 10px; }
      .col { display: flex; flex-direction: column; min-width: 0; }
      .tname { font-size: 13px; font-weight: 600; }
      .tdetail { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .switch { width: 44px; height: 26px; border-radius: 999px; border: none; position: relative; padding: 0; cursor: pointer; flex-shrink: 0; margin-left: 4px; }
      .switch span { position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 999px; background: #ffffff; transition: left .15s; }
      .switch.on span { left: 21px; }
      .timeline { display: flex; height: 14px; border-radius: 999px; overflow: hidden; }
      .axis { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color, #a0a0a0); margin-top: -8px; }
    `;
    // the grid block when the integration plans grid use (the attribute is there)
    const gridOn = Array.isArray(attrs.grid_use) && attrs.grid_use_enabled !== false && this._config.show_grid !== false;
    const changed = setCardContent(this, css, `
      <div class="top"><span class="title">${esc(opt.title)}</span><span class="status"><i style="background:${dot}"></i>${esc(statusText(this._hass, stateObj.state))}</span>${settings}${toggle}</div>
      <div class="blocks${gridOn ? " three" : ""}">${this._block("sell", plans.sell, opt)}${this._block("buy", plans.buy, opt)}${gridOn ? this._gridBlock(attrs.grid_use, opt) : ""}</div>
      <div class="tiles">${this._planTile("spike", attrs.spike_plan, opt)}${this._planTile("negative", attrs.negative_price_plan, opt)}</div>
      ${timeline}
    `);
    const button = changed ? this.shadowRoot.querySelector(".switch") : null;
    if (button) {
      button.addEventListener("click", () => this._hass.callService("homeassistant", "toggle", { entity_id: toggleId }));
    }
    const setbtn = changed ? this.shadowRoot.querySelector(".setbtn") : null;
    if (setbtn) setbtn.addEventListener("click", () => this._openSettings());
    // the planning panel (as of 2026.11.19): a planned block or its "+n" opens it
    if (changed) {
      for (const el of this.shadowRoot.querySelectorAll(".blocks > .block:not(.none)")) {
        el.addEventListener("click", () => { this._panelOpen = true; this._renderPanel(attrs, opt); });
      }
    }
    if (this._panelOpen) this._renderPanel(attrs, opt);
    this._fitHeader();
    // and again once the browser has laid the card out at its real width
    requestAnimationFrame(() => this._fitHeader());
  }

  // "Settings" written out, shortened to just the cog when the title would
  // otherwise not fit on its line.
  _fitHeader() {
    const top = this.shadowRoot && this.shadowRoot.querySelector(".top");
    const title = top && top.querySelector(".title");
    if (!title || !top.querySelector(".setbtn")) return;
    top.classList.remove("tight");
    if (title.scrollWidth > title.clientWidth) top.classList.add("tight");
  }

  _openSettings() {
    const entry = this._hass.entities && this._hass.entities[this._config.entity];
    const path = entry && entry.device_id ? `/config/devices/device/${entry.device_id}` : `/config/integrations/integration/${ESS_DOMAIN}`;
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }
}

// -- EV card (as of 2026.10.11; one session model, one panel as of 2026.10.29) --------
// The electric car (the Status sensor's `ev` attribute). "Now": the plugged-in
// car (Victron charger) - the choice right on the card (fast / slow / on the
// sun / full by), then its progress and plan (a timeline of the grid windows
// for "full by"), "Change" opens the same panel with a current slider; or a
// running session of a plain charger. "Planned": the sessions predicted from
// history ("average"), edited or added - tap one to edit it in the same kind
// of panel (day, plug-in time, fast / slow / on the sun, SOCs); a checkbox per
// session decides whether it counts. A solar session predicted from history
// has a red border: it depends on the sun.
const EV_DEFAULTS = {
  title: "",
  ev_color: [67, 197, 158],
  solar_color: [242, 201, 76],
};
const EV_COLOR_KEYS = ["ev_color", "solar_color"];
const EV_SCHEMA = (t) => [
  { name: "title", selector: { text: {} } },
  {
    type: "expandable",
    flatten: true,
    name: "colours",
    title: t("ed_colours"),
    schema: [{ type: "grid", name: "", schema: EV_COLOR_KEYS.map((name) => ({ name, selector: { color_rgb: {} } })) }],
  },
];
const EV_VOLTAGE = 230;
const EV_WARN = "#ff8a65";
const EV_HIST_BORDER = "#e5534b";
const evPower = (amps, phases) => Math.max(Number(amps) || 0, 0) * EV_VOLTAGE * Math.max(Number(phases) || 1, 1) / 1000;

const EV_CSS = `
  .pl { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
  .pl-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 12px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--secondary-text-color,#a0a0a0); }
  .pl-head .dim { font-weight: 400; letter-spacing: 0; text-transform: none; text-align: right; }
  .pl-tl { position: relative; height: 64px; border-radius: 8px; background: rgba(127,127,127,.1); overflow: hidden; }
  .pl-tl i { position: absolute; bottom: 0; border-radius: 2px 2px 0 0; }
  .pl-tl b { position: absolute; top: 0; bottom: 0; background: color-mix(in srgb, var(--c) 14%, transparent); border-left: 1px solid var(--c); border-right: 1px solid var(--c); }
  .pl-tl u { position: absolute; top: 0; bottom: 0; right: 0; width: 2px; background: #f2c14e; }
  .pl-ticks { position: relative; height: 14px; font-size: 11px; color: var(--secondary-text-color,#a0a0a0); }
  .pl-ticks span { position: absolute; transform: translateX(-50%); }
  .pl-ticks span:first-child { transform: none; }
  .pl-rows { display: flex; flex-direction: column; }
  .pl-row { display: grid; grid-template-columns: 10px auto 40px 1fr auto; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid rgba(127,127,127,.18); font-size: 13px; }
  .pl-row i { width: 9px; height: 9px; border-radius: 3px; }
  .pl-row span:nth-child(3) { font-size: 12px; }
  .pl-sum { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; padding-top: 2px; }
  .ev-list { display: flex; flex-direction: column; gap: 6px; }
  .ev-row { display: flex; align-items: center; gap: 4px; padding: 8px 4px 8px 12px; border-radius: 10px; background: rgba(127,127,127,.12); }
  .ev-row.off { opacity: .55; }
  .ev-row.done { opacity: .75; }
  .ev-row.done .chip.done { background: rgba(111,207,151,.2); color: #6fcf97; }
  .ev-row.hist { outline: 2px solid ${EV_HIST_BORDER}; outline-offset: -2px; }
  .ev-row.sel { outline: 2px solid var(--ev); outline-offset: -2px; background: color-mix(in srgb, var(--ev) 14%, transparent); }
  .ev-row.run { outline: 2px solid var(--ev); outline-offset: -2px; background: color-mix(in srgb, var(--ev) 14%, transparent); }
  .ev-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 6px; background: transparent; border: 0; padding: 0; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .ev-line { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
  .ev-when { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  .ev-kwh { font-size: 14px; font-weight: 600; white-space: nowrap; }
  .ev-row.off .ev-kwh { text-decoration: line-through; color: var(--secondary-text-color, #a0a0a0); }
  .ev-meta { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
  .ev-meta .car { color: var(--primary-text-color, #e1e1e1); }
  .chip { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: color-mix(in srgb, var(--ev) 22%, transparent); }
  .chip.strong { background: var(--ev); color: #0f1f19; }
  .ev-warn { font-size: 12px; color: ${EV_WARN}; display: flex; gap: 6px; align-items: center; }
  .socline { display: flex; align-items: center; gap: 8px; font-size: 12px; }
  .socline .from { color: var(--secondary-text-color, #a0a0a0); min-width: 30px; }
  .socline .to { font-weight: 600; min-width: 30px; text-align: right; }
  .bar { position: relative; flex: 1 1 auto; height: 8px; border-radius: 4px; background: rgba(127,127,127,.3); overflow: hidden; }
  .bar i { position: absolute; top: 0; bottom: 0; }
  .ev-check { display: flex; align-items: center; justify-content: center; min-width: 44px; min-height: 44px; }
  .ev-check input { width: 20px; height: 20px; accent-color: var(--ev); cursor: pointer; }
  .dot { width: 8px; height: 8px; border-radius: 4px; background: var(--ev); flex-shrink: 0; }
  .legend-hist { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
  .legend-hist span { width: 14px; height: 14px; border-radius: 4px; border: 2px solid ${EV_HIST_BORDER}; box-sizing: border-box; flex: 0 0 auto; }
  .ev-add { min-height: 48px; border-radius: 10px; border: 1px dashed rgba(127,127,127,.5); background: transparent; color: inherit; font: inherit; font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 8px; cursor: pointer; }
  .ev-empty { font-size: 14px; color: var(--secondary-text-color, #a0a0a0); padding: 6px 2px; }
  .ev-edit { border-radius: 12px; background: rgba(127,127,127,.12); padding: 14px; display: flex; flex-direction: column; gap: 14px; }
  .ev-edit .head { display: flex; justify-content: space-between; align-items: center; font-size: 15px; font-weight: 600; }
  .grid3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
  @container (max-width: 400px) { .grid3 { grid-template-columns: repeat(2, minmax(0, 1fr)); } .grid3 .fld:first-child { grid-column: 1 / -1; } }
  .fld { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); min-width: 0; }
  .fld select, .fld .locked { min-height: 44px; border-radius: 8px; background: var(--ha-card-background, var(--card-background-color, #1c1c1c)); color: var(--primary-text-color, #e1e1e1); border: 1px solid rgba(127,127,127,.35); padding: 0 8px; font: inherit; font-size: 15px; box-sizing: border-box; width: 100%; }
  .fld select:disabled, .fld .locked { color: var(--secondary-text-color, #8a8a8a); display: flex; align-items: center; gap: 6px; }
  .note { font-size: 12px; color: var(--secondary-text-color, #a0a0a0); margin-top: -6px; }
  .slider { display: flex; flex-direction: column; gap: 6px; }
  .slider .lab { display: flex; justify-content: space-between; font-size: 13px; }
  .slider .lab label { color: var(--secondary-text-color, #a0a0a0); }
  .slider .lab span { font-weight: 600; }
  .slider input { width: 100%; accent-color: var(--ev); }
  .slider .ends { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color, #7a7a7a); }
  .socbig { position: relative; height: 22px; border-radius: 11px; background: rgba(127,127,127,.3); }
  .socbig i { position: absolute; top: 0; bottom: 0; }
  .socbig .txt { position: absolute; top: 0; bottom: 0; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #0f1f19; white-space: nowrap; overflow: hidden; }
  .socbig .mark { position: absolute; top: -4px; bottom: -4px; width: 0; border-left: 2px dashed var(--secondary-text-color, #bdbdbd); }
  .hint { font-size: 11px; color: var(--secondary-text-color, #9b9b9b); }
  .seg { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px; padding: 4px; border-radius: 22px; background: var(--ha-card-background, var(--card-background-color, #1c1c1c)); }
  .seg button { min-height: 40px; border-radius: 18px; border: 0; background: transparent; color: inherit; font: inherit; font-size: 14px; line-height: 1.15; padding: 2px 4px; cursor: pointer; }
  .seg button[aria-checked="true"] { background: var(--ev); color: #0f1f19; font-weight: 600; }
  .result { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; background: color-mix(in srgb, var(--ev) 10%, transparent); font-size: 14px; }
  .result.warn { background: color-mix(in srgb, ${EV_WARN} 14%, transparent); }
  .actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .actions .grow { flex: 1 1 auto; }
  .btn { min-height: 44px; padding: 0 18px; border-radius: 22px; border: 1px solid rgba(127,127,127,.45); background: transparent; color: inherit; font: inherit; font-size: 14px; cursor: pointer; }
  .btn.primary { border: 0; background: var(--ev); color: #0f1f19; font-weight: 600; padding: 0 22px; }
  .btn.link { border: 0; padding: 0 12px; text-decoration: underline; color: var(--secondary-text-color, #9b9b9b); font-size: 13px; }
  .btn:disabled { opacity: .5; cursor: default; }
  .err { font-size: 13px; color: ${EV_WARN}; }
  .fld input { min-height: 44px; border-radius: 8px; background: var(--ha-card-background, var(--card-background-color, #1c1c1c)); color: var(--primary-text-color, #e1e1e1); border: 1px solid rgba(127,127,127,.35); padding: 0 8px; font: inherit; font-size: 15px; box-sizing: border-box; width: 100%; }
  .seg.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .seg.three button { font-size: 13px; padding: 0 4px; }
  .ev-plan-bar { display: flex; justify-content: flex-end; margin-top: -4px; }
  .sec { font-size: 11px; font-weight: 700; letter-spacing: .08em; color: var(--secondary-text-color, #a0a0a0); text-transform: uppercase; margin-bottom: -6px; }
  .nu { border-radius: 12px; padding: 14px; display: flex; flex-direction: column; gap: 12px; background: color-mix(in srgb, var(--ev) 10%, transparent); outline: 2px solid var(--ev); outline-offset: -2px; }
  .nuhead { display: flex; align-items: center; gap: 10px; }
  .nuname { flex-grow: 1; font-size: 15px; font-weight: 600; min-width: 0; }
  .nutext { font-size: 13px; color: var(--secondary-text-color, #b0b0b0); }
  .nuq { font-size: 13px; font-weight: 600; margin-bottom: -4px; }
  .nuhead .chip { font-size: 12px; padding: 3px 10px; border-radius: 12px; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
  .chip.wait { background: color-mix(in srgb, #f2c94c 18%, transparent); color: #f2c94c; }
  .chip.ext { background: color-mix(in srgb, var(--ev) 22%, transparent); }
  .chip.sun { background: color-mix(in srgb, var(--evsun) 22%, transparent); }
  .chip.grid { background: rgba(79,163,247,.18); color: #9ccbfb; }
  .choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .choice { min-height: 64px; border-radius: 12px; border: 1px solid rgba(127,127,127,.45); background: var(--ha-card-background, var(--card-background-color, #1c1c1c)); color: inherit; font: inherit; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 2px; padding: 8px 12px; cursor: pointer; text-align: left; }
  .choice b { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
  .choice span { font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
  .bar.big { height: 10px; border-radius: 5px; }
  .tl { display: flex; flex-direction: column; gap: 6px; }
  .ticks { position: relative; height: 14px; }
  .tick { position: absolute; top: 0; font-size: 11px; color: var(--secondary-text-color, #a0a0a0); transform: translateX(-50%); }
  .tlbar { position: relative; height: 18px; border-radius: 4px; background: rgba(127,127,127,.18); }
  .tlbar i { position: absolute; top: 0; bottom: 0; }
  .tlbar .now { top: -4px; bottom: -4px; width: 2px; background: var(--primary-text-color, #fff); }
  .tlbar .mark { top: -4px; bottom: -4px; width: 0; border-left: 2px dashed var(--secondary-text-color, #a0a0a0); }
  .tlfoot { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color, #a0a0a0); gap: 8px; }
  .legend2 { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
  .legend2 div { display: flex; gap: 8px; align-items: center; }
  .legend2 i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; flex: 0 0 auto; }
  .legend2 span:nth-of-type(1) { flex-grow: 1; }
  .resgrid { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-radius: 10px; background: color-mix(in srgb, var(--ev) 12%, transparent); font-size: 13px; }
  .rr { display: flex; justify-content: space-between; gap: 10px; }
  .rr.tot { font-size: 14px; font-weight: 600; border-top: 1px solid rgba(127,127,127,.3); padding-top: 6px; }
  .result.bad { background: color-mix(in srgb, #e5534b 16%, transparent); border: 1px solid #e5534b; align-items: flex-start; line-height: 1.4; }
  .fldgrp { display: flex; flex-direction: column; gap: 6px; }
  .fldgrp .lab { font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
  .ev-meta .how { display: inline-flex; align-items: center; gap: 4px; color: var(--primary-text-color, #e1e1e1); }
`;

const ICON_LOCK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V8a4 4 0 0 1 8 0v3"></path></svg>';
const ICON_CLOCK = (c) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" aria-hidden="true" style="flex-shrink:0"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>`;
const ICON_PLUS = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"></path></svg>';

// The energy (kWh) the charger delivers per 100% of a car's state of charge:
// its battery size divided by its charge efficiency (as of 2026.10.36) times
// its state-of-charge correction (as of 2026.10.35, from finished charges)
function evCap(car) {
  const eff = Math.min(Math.max(Number(car && car.efficiency) || 90, 10), 100) / 100;
  return ((Number(car && car.capacity_kwh) || 0) * (Number(car && car.kwh_factor) || 1)) / eff;
}

// "Full by" planned in the card itself (as of 2026.10.29) - the same rules as
// ev_charger.plan_deadline / plan_full_by, so the panel shows the result live
// while you slide: sun first (from the charger's min power up to its max),
// the rest in the cheapest priced quarters, no lone quarters.
function evPlanDeadline(nowMs, deadlineMs, need, net, hour0Ms, prices, priceStartMs, pMin, pMax, gridKw) {
  const U = UNIT_MS;
  const first = Math.floor(nowMs / U) * U;
  const qs = [];
  for (let q = first; q < deadlineMs; q += U) qs.push(q);
  const inQs = new Set(qs);
  const frac = (q) => Math.max(Math.min(q + U, deadlineMs) - Math.max(q, nowMs), 0) / U;
  const price = (q) => {
    const i = Math.floor((q - priceStartMs) / U);
    return i >= 0 && i < prices.length && prices[i] != null && isFinite(Number(prices[i])) ? Number(prices[i]) : null;
  };
  const sun = new Map(qs.map((q) => {
    const h = Math.floor((q - hour0Ms) / HOUR_MS);
    const spare = h >= 0 && h < net.length && net[h] != null ? Number(net[h]) : 0;
    const rate = spare >= pMin ? Math.min(Math.max(spare, 0), pMax) : 0;
    return [q, (rate / 4) * frac(q)];
  }));
  const gq = gridKw / 4;
  const chosen = new Set();
  let total = qs.reduce((a, q) => a + sun.get(q), 0);
  const cand = qs.filter((q) => price(q) !== null && frac(q) > 0).sort((a, b) => price(a) - price(b) || a - b);
  for (const q of cand) {
    if (total >= need - 1e-9) break;
    chosen.add(q);
    total += gq * frac(q) - sun.get(q);
  }
  for (const q of [...chosen].sort((a, b) => a - b)) {
    if (chosen.has(q - U) || chosen.has(q + U)) continue;
    const opts = [q - U, q + U].filter((n) => inQs.has(n) && price(n) !== null && frac(n) > 0).sort((a, b) => price(a) - price(b) || a - b);
    if (opts.length) chosen.add(opts[0]);
  }
  let got = 0;
  let end = null;
  let solar = 0;
  let grid = 0;
  let cost = 0;
  for (const q of qs) {
    const e = chosen.has(q) ? gq * frac(q) : sun.get(q);
    if (e <= 0) continue;
    const take = Math.min(e, Math.max(need - got, 0));
    if (take <= 0) break;
    if (chosen.has(q)) {
      grid += take;
      cost += take * price(q);
    } else solar += take;
    got += take;
    if (end === null && got >= need - 1e-9) end = Math.max(q, nowMs) + (take / e) * frac(q) * U;
  }
  if (need <= 0) end = nowMs;
  const windows = [];
  for (const q of [...chosen].sort((a, b) => a - b)) {
    if (windows.length && windows[windows.length - 1][1] === q) windows[windows.length - 1][1] = q + U;
    else windows.push([q, q + U]);
  }
  return { windows, solar, grid, short: Math.max(need - got, 0), end, cost };
}

const EV_CALM_MARGIN = 0.02;

function evPlanFullBy(nowMs, deadlineMs, need, net, hour0Ms, prices, priceStartMs, phases, minA, maxA, marginMs, sunMinA) {
  const readyBy = Math.max(deadlineMs - marginMs, nowMs);
  // the sun from this current on (a zappi's windows at the max; as of 2026.11.31 it gets no sun)
  const pMin = evPower(sunMinA != null ? sunMinA : minA, phases);
  const pMax = evPower(maxA, phases);
  // (the house battery's dear quarters are left to the integration: the
  // panel shows the grid) (as of 2026.11.7) calm by preference: the lowest current that costs at
  // most EV_CALM_MARGIN per kWh more than the cheapest - like plan_full_by
  const fits = [];
  for (let a = Math.round(minA); a <= Math.round(maxA); a++) {
    const kw = evPower(a, phases);
    const plan = evPlanDeadline(nowMs, readyBy, need, net, hour0Ms, prices, priceStartMs, pMin, pMax, kw);
    if (plan.short <= 0.05) fits.push({ ...plan, amps: a, kw, tight: false, readyBy, deadline: deadlineMs, reach: need });
  }
  if (fits.length) {
    const allowed = Math.min(...fits.map((f) => f.cost)) + EV_CALM_MARGIN * Math.max(need, 0) + 1e-9;
    return fits.find((f) => f.cost <= allowed);
  }
  const reach = Math.min((pMax * Math.max(deadlineMs - nowMs, 0)) / HOUR_MS, Math.max(need, 0));
  const end = pMax > 0 ? nowMs + (Math.max(need, 0) / pMax) * HOUR_MS : null;
  return { windows: end ? [[nowMs, end]] : [], solar: 0, grid: need, short: need - reach, end, amps: Math.round(maxA), kw: pMax, tight: true, readyBy, deadline: deadlineMs, reach };
}

const EV_ICON = {
  car: (c) => `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 17h14v-5l-2-5H7l-2 5v5z"></path><circle cx="8" cy="17" r="1.5"></circle><circle cx="16" cy="17" r="1.5"></circle></svg>`,
  asap: (c) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 2L4 14h7l-1 8 9-12h-7z"></path></svg>`,
  calm: (c) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 12h16"></path></svg>`,
  solar: (c) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>`,
  deadline: (c) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>`,
  check: (c) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 12l5 5 9-10"></path></svg>`,
  warn: (c) => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" aria-hidden="true" style="flex-shrink:0"><path d="M12 3l10 18H2z"></path><path d="M12 10v5M12 18v.5"></path></svg>`,
};
const EV_GRID = "#4fa3f7";
const EV_BATT = "#6fcf97";
const EV_RED = "#e5534b";
const EV_HOW_COLOR = { asap: "var(--ev)", calm: "var(--ev)", solar: "var(--evsun)", deadline: EV_GRID };

class EssManagerEvCard extends EssChartCard {
  static get info() {
    return {
      name: "ESS Manager - Electric car",
      description: "The electric car: the plugged-in car's plan and the planned charging sessions - check, choose, edit or add them.",
      schema: EV_SCHEMA,
      defaults: EV_DEFAULTS,
      labels: { title: "ed_title", ev_color: "ed_ev_color", solar_color: "ed_solar_color" },
    };
  }

  getCardSize() {
    return 7;
  }

  setConfig(config) {
    this._edit = null;
    this._error = null;
    this._plan = null;
    this._planError = null;
    super.setConfig(config);
  }

  _opt() {
    return colorOptions(this._config, EV_DEFAULTS, EV_COLOR_KEYS);
  }

  _num(v, d) {
    return formats(this._hass).num(v, d);
  }

  _kwh(v) {
    return `${this._num(Number(v) || 0, 1)} kWh`;
  }

  _kw(v) {
    return `${this._num(Number(v) || 0, 1)} kW`;
  }

  _day(ms) {
    return formats(this._hass).dayLabel(ms);
  }

  _time(ms) {
    return formats(this._hass).time(ms);
  }

  // "18:45", with the day when it isn't today
  _when(ms) {
    if (ms == null) return "\u2014";
    const today = localMidnight(this._hass, Date.now());
    return localMidnight(this._hass, ms) === today ? this._time(ms) : `${this._day(ms)} ${this._time(ms)}`;
  }

  _car(ev, id) {
    return (ev.cars || []).find((c) => c.id === id) || null;
  }

  _carFor(ev, s) {
    const cars = ev.cars || [];
    return this._car(ev, s && s.car) || (cars.length === 1 ? cars[0] : null);
  }

  _days(ev) {
    const out = [localMidnight(this._hass, Date.now())];
    for (let i = 1; i < (ev.days || 5); i++) out.push(nextMidnight(this._hass, out[i - 1]));
    return out;
  }

  // a local clock time on the day starting at `day` (ms), corrected on a daylight saving day
  _at(day, hour, minute) {
    let t = day + hour * HOUR_MS + (minute || 0) * 60000;
    const c = formats(this._hass).clock(t)[0];
    if (c !== hour) t += ((((hour - c + 36) % 24) - 12) * HOUR_MS);
    return t;
  }

  // The session's way of charging: asap / calm / solar (planned sessions keep a fixed current)
  _howOf(ev, s) {
    if (s.mode === "deadline") return "deadline";
    if (s.mode === "solar") return "solar";
    return Number(s.current_a) <= Number(ev.min_current) ? "calm" : "asap";
  }

  _howText(ev, s) {
    if (s.mode === "deadline") return this._t("ev_chip_by")(s.deadline ? this._when(Date.parse(s.deadline)) : "\u2014");
    if (s.mode === "solar") return this._t("ev_chip_solar");
    const a = Math.round(Number(s.current_a) || ev.max_current);
    if (a <= ev.min_current) return this._t("ev_chip_calm")(a);
    if (a >= ev.max_current) return this._t("ev_chip_asap")(a);
    return this._t("ev_chip_fixed")(a);
  }

  // -- the plugged-in car (Victron charger) or a running session -------------------
  _nu(ev) {
    const sessions = ev.sessions || [];
    const cs = ev.charger && ev.charger.session ? ev.charger.session : null;
    if (cs) return { cs, s: sessions.find((x) => x.id === cs.id) || null };
    const s = sessions.find((x) => x.running);
    return s ? { cs: null, s } : null;
  }

  _prices() {
    const st = this._hass.states[this._config.entity];
    const a = (st && st.attributes) || {};
    // (as of 2026.11.5) incl taxes once known - the prices the planning uses
    return (a.all_buy_price_incl || a.all_buy_price || a.all_price || []).map((v) => (v == null ? null : Number(v)));
  }

  // -- the panel for the plugged-in car ---------------------------------------------
  _planInit(ev, cs, s, how) {
    const car = this._carFor(ev, { car: cs.car || (s && s.car) });
    let hour = "07:00";
    if (cs.deadline) {
      const [h, m] = formats(this._hass).clock(Date.parse(cs.deadline));
      hour = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    }
    const choice = how || cs.choice || "asap";
    let soc = cs.soc_now != null ? Math.round(cs.soc_now) : null;
    if (soc == null && s && s.start_soc != null) soc = Math.round(s.start_soc);
    const target = cs.target_soc != null ? Math.round(cs.target_soc) : car ? Math.round(Number(car.target_soc) || 80) : 80;
    // (as of 2026.11.7) the day from the deadline itself: "tomorrow" chosen
    // last evening is today after midnight (up to then the panel showed the
    // day after, and saving would have moved the deadline a day)
    let day = cs.day;
    if (cs.deadline && cs.day !== "any") {
      const today = localMidnight(this._hass, Date.now());
      const dl = localMidnight(this._hass, Date.parse(cs.deadline));
      let d = today;
      for (let i = 0; i < 3; i++) {
        if (d === dl) day = ["today", "tomorrow", "after"][i];
        d = nextMidnight(this._hass, d);
      }
    }
    const out = {
      sid: cs.id,
      active: !!cs.choice,
      how: choice,
      car: car ? car.id : "",
      current: Math.round(cs.current_a || (choice === "calm" ? ev.min_current : ev.max_current)),
      day: day || (new Date().getHours() >= 12 ? "tomorrow" : "today"),
      hour,
      soc: soc != null ? soc : Math.max(target - 30, 0),
      target,
      kwh: Math.round((Number(cs.need_kwh) || Number(s && s.kwh) || 10) * 2) / 2,
    };
    out.orig = this._planKey(out);
    return out;
  }

  _planKey(p) {
    return JSON.stringify([p.how, p.day, p.hour, p.soc, p.target, p.kwh, p.car, p.active]);
  }

  // The integration's plan for the plugged-in car (as of 2026.11.7), while
  // the panel shows its own choice unchanged - in the shape of _planBlock
  _flowPlan(ev, p) {
    const nu = this._nu(ev);
    const cs = nu && nu.cs;
    if (!cs || cs.choice !== "deadline" || !p.active || p.how !== "deadline" || p.orig !== this._planKey(p)) return null;
    if (cs.tight || !Array.isArray(cs.window_kwh)) return null;
    const ms = (w) => (w || []).map(([a, b]) => [Date.parse(a), Date.parse(b)]);
    const amps = cs.plan_current_a || ev.max_current;
    return {
      real: true,
      windows: ms(cs.windows), windowKwh: cs.window_kwh, windowCost: cs.window_cost || [],
      bwindows: ms(cs.battery_windows), bwindowKwh: cs.battery_window_kwh || [], bwindowCost: cs.battery_window_cost || [],
      solar: Number(cs.solar_kwh) || 0, grid: Number(cs.grid_kwh) || 0, battery: Number(cs.battery_kwh) || 0,
      amps, kw: Number(cs.grid_kw) || evPower(amps, ev.phases || 3),
      end: cs.end ? Date.parse(cs.end) : null,
      readyBy: cs.ready_by ? Date.parse(cs.ready_by) : null,
      deadline: cs.deadline ? Date.parse(cs.deadline) : null,
      any: cs.day === "any",
    };
  }

  _planNeed(ev, p) {
    const car = this._car(ev, p.car);
    if (car && car.capacity_kwh) return Math.max(((p.target - p.soc) / 100) * evCap(car), 0);
    return Math.max(Number(p.kwh) || 0, 0);
  }

  _deadlineMs(p) {
    const today = localMidnight(this._hass, Date.now());
    const offset = { tomorrow: 1, after: 2 }[p.day] || 0;
    let day = today;
    for (let i = 0; i < offset; i++) day = nextMidnight(this._hass, day);
    const [h, m] = String(p.hour || "07:00").split(":").map((v) => Number(v) || 0);
    return this._at(day, h, m);
  }

  // What the panel's choice gives, worked out here so it follows the sliders.
  _planPreview(ev, p) {
    const now = Date.now();
    const phases = ev.phases || 3;
    const need = this._planNeed(ev, p);
    const out = { need };
    if (p.how === "asap" || p.how === "calm") {
      const a = p.active ? clamp(p.current, ev.min_current, ev.max_current) : p.how === "asap" ? ev.max_current : ev.min_current;
      out.amps = a;
      out.kw = evPower(a, phases);
      out.end = out.kw > 0 ? now + (need / out.kw) * HOUR_MS : null;
      return out;
    }
    const net = ev.house_net_120h || [];
    const hour0 = Math.floor(now / HOUR_MS) * HOUR_MS;
    if (p.how === "solar") {
      const pMax = evPower(ev.max_current, phases);
      const pMin = evPower(ev.min_current, phases);
      let left = need;
      for (let h = 0; h < net.length && left > 1e-9; h++) {
        const w0 = Math.max(hour0 + h * HOUR_MS, now);
        const span = (hour0 + (h + 1) * HOUR_MS - w0) / HOUR_MS;
        const spare = Math.max(Number(net[h]) || 0, 0);
        const rate = spare >= pMin ? Math.min(spare, pMax) : 0;
        if (!rate || span <= 0) continue;
        const take = Math.min(rate * span, left);
        left -= take;
        if (left <= 1e-9) out.end = w0 + (take / rate) * HOUR_MS;
      }
      out.got = need - left;
      out.warning = need > 0 && out.got <= 0.05 ? "none" : left > 0.05 ? "short" : null;
      return out;
    }
    // full by
    const prices = this._prices();
    const priceStart = localMidnight(this._hass, now);
    let deadline;
    let margin = HOUR_MS;
    if (p.day === "any") {
      deadline = priceStart + prices.length * UNIT_MS;
      margin = 0;
    } else deadline = this._deadlineMs(p);
    if (deadline <= now) return { ...out, past: true };
    const [fNet, fLo, fHi] = this._fbRange(ev, net);
    const plan = evPlanFullBy(now, deadline, need, fNet, hour0, prices, priceStart, phases, fLo, fHi, margin, ev.min_current);
    return { ...out, ...plan, any: p.day === "any" };
  }

  // (as of 2026.11.21) a zappi has no current to set: its "full by" windows run
  // at the max current (Fast); as of 2026.11.31 it's Stopped between them (its
  // Eco+ chases the house battery), so no sun - as the integration plans it
  _fbRange(ev, net) {
    if (ev.charger && ev.charger.type === "zappi") return [(net || []).map(() => 0), ev.max_current, ev.max_current];
    return [net, ev.min_current, ev.max_current];
  }

  _windowsText(windows) {
    return (windows || []).slice(0, 3).map(([a, b]) => `${this._time(a)}\u2013${this._time(b)}`).join(", ") + ((windows || []).length > 3 ? ", \u2026" : "");
  }

  _planResult(ev, p) {
    const real = this._flowPlan(ev, p);
    const r = real ? { ...real, need: this._planNeed(ev, p) } : this._planPreview(ev, p);
    const phases = ev.phases || 3;
    if (p.how === "asap" || p.how === "calm") {
      return `<div class="result">${ICON_CLOCK("var(--ev)")}<div>${esc(this._t("ev_r_fixed")(this._kwh(r.need), this._when(r.end)))}</div></div>`;
    }
    if (p.how === "solar") {
      if (r.warning === "none") return `<div class="result warn">${ICON_CLOCK(EV_WARN)}<div>${esc(this._t("ev_r_solar_none"))}</div></div>`;
      if (r.warning === "short") return `<div class="result warn">${ICON_CLOCK(EV_WARN)}<div>${esc(this._t("ev_r_solar_short")(this._kwh(r.got), this._kwh(r.need)))}</div></div>`;
      return `<div class="result">${EV_ICON.solar("var(--evsun)")}<div>${esc(this._t("ev_r_solar_ok")(this._kwh(r.need), this._when(r.end)))}</div></div>`;
    }
    if (r.past) return `<div class="result bad">${EV_ICON.warn("#ff7b72")}<div>${esc(this._t("ev_r_past"))}</div></div>`;
    if (r.tight) {
      const car = this._car(ev, p.car);
      let reach = this._kwh(r.reach);
      if (car && car.capacity_kwh) reach += ` (\u00b1 ${Math.round(p.soc + (r.reach / evCap(car)) * 100)}%)`;
      return `<div class="result bad">${EV_ICON.warn("#ff7b72")}<div style="display:flex;flex-direction:column;gap:4px"><b style="color:#ffb4ad">${esc(this._t("ev_r_tight_t")(this._when(r.deadline)))}</b><span>${esc(this._t("ev_r_tight")(this._kwh(r.need), `${ev.max_current} A \u00b7 ${this._kw(evPower(ev.max_current, phases))}`, reach, this._when(r.end)))}</span></div></div>`;
    }
    const by = r.any ? this._when(r.readyBy) : this._time(r.readyBy);
    const rows = [
      [this._t("ev_r_need"), this._kwh(r.need)],
      [this._t("ev_r_sun")(by), this._kwh(r.solar)],
      [this._t("ev_r_grid")(this._windowsText(r.windows)), this._kwh(r.grid)],
    ];
    if (r.battery > 0.05) rows.push([this._t("ev_legend_batt")(r.amps) + " \u00b7 " + this._windowsText(r.bwindows), this._kwh(r.battery)]);
    if (r.grid + (r.battery || 0) > 0.05) rows.push([this._t("ev_r_speed"), `${r.amps} A \u00b7 ${this._kw(r.kw)}`]);
    let html = `<div class="resgrid">${rows.map(([k, v]) => `<div class="rr"><span class="dim">${esc(k)}</span><span>${esc(v)}</span></div>`).join("")}`;
    html += `<div class="rr tot"><span>${esc(this._t("ev_r_end"))}</span><span>${esc(this._when(r.end))}</span></div>`;
    if (!r.any) html += `<div class="hint">${esc(this._t("ev_r_margin")(this._time(r.readyBy), this._time(r.deadline)))}</div>`;
    html += "</div>";
    // (as of 2026.11.7) the charge plan, as in a planned session's panel
    if (!r.any && r.deadline) html += this._planBlock(real || this._previewParts(r), Date.now());
    return html;
  }

  _seg(attr, items, cur, cols) {
    return `<div class="seg" role="radiogroup" style="grid-template-columns:repeat(${cols || items.length},minmax(0,1fr))">${items
      .map(([v, label]) => `<button type="button" role="radio" ${attr}="${v}" aria-checked="${cur === v}">${esc(label)}</button>`)
      .join("")}</div>`;
  }

  _planPanel(ev, cs) {
    const p = this._plan;
    const cars = ev.cars || [];
    const car = this._car(ev, p.car);
    const phases = ev.phases || 3;
    let out = "";
    if (cars.length > 1) {
      const opts = [`<option value="" ${p.car ? "" : "selected"}>${esc(this._t("ev_vp_pick"))}</option>`]
        .concat(cars.map((c) => `<option value="${esc(c.id)}" ${c.id === p.car ? "selected" : ""}>${esc(c.name)}</option>`));
      out += `<label class="fld">${esc(this._t("ev_car"))}<select data-pf="car">${opts.join("")}</select></label>`;
    }
    out += `<div class="fldgrp"><span class="lab">${esc(this._t("ev_how"))}</span>${this._seg("data-ph", [["asap", this._t("ev_h_asap")], ["calm", this._t("ev_h_calm")], ["solar", this._t("ev_h_solar")], ["deadline", this._t("ev_h_by")]], p.how, 4)}</div>`;
    if ((p.how === "asap" || p.how === "calm") && p.active) {
      const a = clamp(Math.round(p.current), ev.min_current, ev.max_current);
      out += `
        <div class="slider">
          <div class="lab"><label for="ev-pcur">${esc(this._t("ev_current"))}</label><span data-k="pcur">${a} A \u00b7 ${esc(this._kw(evPower(a, phases)))}</span></div>
          <input id="ev-pcur" type="range" data-ps="current" min="${ev.min_current}" max="${ev.max_current}" step="1" value="${a}">
          <div class="ends"><span>${ev.min_current} A \u00b7 ${esc(this._kw(evPower(ev.min_current, phases)))}</span><span>${esc(this._t("ev_phases")(phases))}</span><span>${ev.max_current} A \u00b7 ${esc(this._kw(evPower(ev.max_current, phases)))}</span></div>
        </div>`;
    }
    if (p.how === "solar") {
      out += `<div class="hint">${esc(this._t("ev_r_solar_hint")(`${ev.min_current} A`, `${ev.max_current} A`))}</div>`;
    }
    if (p.how === "deadline") {
      // tomorrow and the day after by their day of the week (as of 2026.10.31)
      const today = localMidnight(this._hass, Date.now());
      const d1 = nextMidnight(this._hass, today);
      const d2 = nextMidnight(this._hass, d1);
      const dayName = (ms) => {
        const w = formats(this._hass).weekdayLong(ms + 12 * 3600000);
        return w.charAt(0).toUpperCase() + w.slice(1);
      };
      out += `<div class="fldgrp"><span class="lab">${esc(this._t("ev_when_full"))}</span>${this._seg("data-pd", [["today", this._t("ev_d_today")], ["tomorrow", dayName(d1)], ["after", dayName(d2)], ["any", this._t("ev_d_any")]], p.day, 4)}</div>`;
      if (p.day !== "any") out += `<label class="fld">${esc(this._t("ev_full_at"))}<input type="time" data-p="hour" value="${esc(p.hour)}"></label>`;
    }
    if (car && car.capacity_kwh) {
      out += `<div class="grid2">
        ${this._pslider("soc", this._t("ev_soc_now"), p.soc, 0, 100, 1, `${Math.round(p.soc)}%`, "var(--secondary-text-color,#9b9b9b)")}
        ${this._pslider("target", this._t("ev_target"), p.target, 0, 100, 1, `${Math.round(p.target)}%`)}
      </div>`;
    } else {
      out += this._pslider("kwh", this._t("ev_energy"), p.kwh, 0.5, Math.max(100, Math.ceil(p.kwh)), 0.5, this._kwh(p.kwh));
    }
    out += `<div data-k="presult">${this._planResult(ev, p)}</div>`;
    if (this._planError) out += `<div class="err">${esc(this._planError)}</div>`;
    if (!cs.choice) out += `<div class="hint">${esc(this._t("ev_phone_note"))}</div>`;
    out += `<div class="actions"><span class="grow"></span>
      <button type="button" class="btn" data-act="plan-cancel">${esc(this._t("ev_cancel"))}</button>
      <button type="button" class="btn primary" data-act="plan-go" ${this._saving || (cars.length > 1 && !p.car) ? "disabled" : ""}>${esc(this._t(p.active ? "ev_go_save" : "ev_go_start"))}</button></div>`;
    return out;
  }

  _pslider(key, label, value, min, max, step, text, accent) {
    return `
      <div class="slider">
        <div class="lab"><label for="ev-p${key}">${esc(label)}</label><span data-k="p${key}">${esc(text)}</span></div>
        <input id="ev-p${key}" type="range" data-ps="${key}" min="${min}" max="${max}" step="${step}" value="${value}"${accent ? ` style="accent-color:${accent}"` : ""}>
      </div>`;
  }

  // -- the "Now" block ---------------------------------------------------------------
  _nuBlock(ev, nu) {
    const { cs, s } = nu;
    const car = this._carFor(ev, cs ? { car: cs.car || (s && s.car) } : s);
    const name = car ? car.name : this._t("ev_car");
    const charging = Number(ev.power_w) > 50;
    let head;
    let chip = "";
    if (!cs) {
      head = `<span class="dot"></span><div class="nuname">${esc(this._t("ev_st_running"))}${charging ? ` \u00b7 ${esc(this._kw(ev.power_w / 1000))}` : ""}</div>`;
    } else {
      const title = cs.done ? this._t(charging ? "ev_st_charging" : cs.stopped_early ? "ev_st_stopped" : "ev_st_full")(name, this._kw(ev.power_w / 1000)) : charging ? this._t("ev_st_charging")(name, this._kw(ev.power_w / 1000)) : this._t("ev_st_plugged")(name);
      head = `${charging && !cs.done ? `<span class="dot"></span>` : EV_ICON.car("var(--ev)")}<div class="nuname">${esc(title)}</div>`;
      if (cs.done) chip = `<span class="chip">${esc(this._t("ev_chip_done"))}</span>`;
      else if (!cs.choice && cs.external) chip = `<span class="chip ext">${esc(this._t("ev_chip_ext"))}</span>`;
      else if (!cs.choice) chip = `<span class="chip wait">${esc(this._t("ev_chip_wait"))}</span>`;
      else if (cs.choice === "asap") chip = `<span class="chip">${esc(this._t("ev_chip_asap")(Math.round(cs.current_a || ev.max_current)))}</span>`;
      else if (cs.choice === "calm") chip = `<span class="chip">${esc(this._t("ev_chip_calm")(Math.round(cs.current_a || ev.min_current)))}</span>`;
      else if (cs.choice === "solar") chip = `<span class="chip sun">${esc(this._t("ev_chip_solar"))}</span>`;
      else chip = `<span class="chip grid">${EV_ICON.deadline("currentColor").replace('width="16" height="16"', 'width="13" height="13"')}${esc(cs.day === "any" ? this._t("ev_d_any") : this._t("ev_chip_by")(this._when(Date.parse(cs.deadline))))}</span>`;
    }
    let out = `<div class="nu"><div class="nuhead">${head}${chip}</div>`;
    // (as of 2026.11.21) a zappi locked without "charge when locked" doesn't charge on a command
    if (ev.charger && ev.charger.blocked) out += `<div class="result warn">${ICON_CLOCK(EV_WARN)}<div>${esc(this._t("ev_zappi_blocked"))}</div></div>`;
    // the panel: choosing / changing
    if (cs && this._plan && this._plan.sid === cs.id) return out + this._planPanel(ev, cs) + "</div>";
    if (!cs && this._edit && s && this._edit.id === s.id) return out + this._editPanel(ev) + "</div>";
    if (!cs) {
      out += this._socLine(ev, s, car);
      return out + `<div class="actions"><span class="grow"></span><button type="button" class="btn" data-open="${esc(s.id)}">${esc(this._t("ev_edit_btn"))}</button></div></div>`;
    }
    if (cs.done) {
      // (as of 2026.11.21) the car stopped itself well short of the goal
      const se = cs.stopped_early;
      const text = !se ? this._t("ev_done_text")
        : se.soc != null && se.target != null && Number(se.target) - Number(se.soc) >= 3
          ? this._t("ev_done_early")(Math.round(Number(se.soc)), Math.round(Number(se.target)))
          : this._t("ev_done_early_kwh")(this._kwh(se.left_kwh));
      return out + `<div class="${se ? "result warn" : "nutext"}">${se ? ICON_CLOCK(EV_WARN) : ""}${se ? `<div>${esc(text)}</div>` : esc(text)}</div><div class="actions"><span class="grow"></span><button type="button" class="btn" data-act="plan-open">${esc(this._t("ev_change"))}</button></div></div>`;
    }
    if (!cs.choice) {
      out += `<div class="nutext">${esc(this._t(cs.external ? "ev_ext_text" : "ev_wait_text"))}</div>`;
      out += `<div class="nuq">${esc(this._t("ev_how_q"))}</div><div class="choices">`;
      const phases = ev.phases || 3;
      const items = [
        ["asap", this._t("ev_h_asap"), `${ev.max_current} A \u00b7 ${this._kw(evPower(ev.max_current, phases))}`],
        ["calm", this._t("ev_h_calm"), `${ev.min_current} A \u00b7 ${this._kw(evPower(ev.min_current, phases))}`],
        ["solar", this._t("ev_h_solar"), this._t("ev_h_solar_sub")],
        ["deadline", `${this._t("ev_h_by")} \u2026`, this._t("ev_h_by_sub")],
      ];
      out += items.map(([v, title, sub]) => `<button type="button" class="choice" data-pick="${v}"><b>${EV_ICON[v](EV_HOW_COLOR[v])}${esc(title)}</b><span>${esc(sub)}</span></button>`).join("");
      return out + "</div></div>";
    }
    // a plan: progress, the plan, change
    out += this._socLine(ev, s, car, cs);
    if (cs.choice === "deadline") out += this._timeline(ev, cs, s);
    else if (cs.choice === "solar") {
      const left = cs.left_kwh != null ? cs.left_kwh : s ? s.kwh : 0;
      if (s && s.warning === "no_surplus") out += `<div class="result warn">${ICON_CLOCK(EV_WARN)}<div>${esc(this._t("ev_r_solar_none"))}</div></div>`;
      else out += `<div class="result">${EV_ICON.solar("var(--evsun)")}<div>${esc(this._t("ev_r_solar_ok")(this._kwh(left), this._when(s && s.end ? Date.parse(s.end) : null)))}</div></div>`;
    } else {
      const a = Math.round(cs.current_a || (cs.choice === "calm" ? ev.min_current : ev.max_current));
      const kw = evPower(a, ev.phases || 3);
      const left = Number(cs.left_kwh) || 0;
      out += `<div class="result">${ICON_CLOCK("var(--ev)")}<div>${esc(this._t("ev_r_fixed")(this._kwh(left), this._when(Date.now() + (left / kw) * HOUR_MS)))}</div></div>`;
    }
    return out + `<div class="actions"><span class="grow"></span><button type="button" class="btn" data-act="plan-open">${esc(this._t("ev_change"))}</button></div></div>`;
  }

  _socLine(ev, s, car, cs) {
    if (car && car.capacity_kwh && cs && cs.soc != null && cs.target_soc != null) {
      const from = clamp(Number(cs.soc), 0, 100);
      const to = clamp(Number(cs.target_soc), from, 100);
      const now = clamp(Number(cs.soc_now != null ? cs.soc_now : from), from, to);
      const need = Number(cs.need_kwh) || 0;
      const done = Math.max(need - (Number(cs.left_kwh) || 0), 0);
      return `<div class="socline"><span class="from">${Math.round(from)}%</span><div class="bar big"><i style="left:0;width:${from}%;background:rgba(127,127,127,.6)"></i><i style="left:${from}%;width:${now - from}%;background:var(--ev)"></i><i style="left:${now}%;width:${to - now}%;background:var(--ev);opacity:.35"></i></div><span class="to">${Math.round(to)}%</span></div>
        <div class="dim" style="font-size:12px;text-align:center;margin-top:-6px">${esc(this._t("ev_soc_line")(Math.round(now), this._kwh(done), this._kwh(need)))}</div>`;
    }
    if (!s) return "";
    const total = Number(s.kwh) || 0;
    const got = Number(s.delivered_kwh) || 0;
    if (!total) return "";
    const part = clamp((got / total) * 100, 0, 100);
    return `<div class="socline"><div class="bar big"><i style="left:0;width:${part}%;background:var(--ev)"></i></div><span class="to">${esc(this._t("ev_kwh_line")(this._kwh(got), this._kwh(total)))}</span></div>`;
  }

  _timeline(ev, cs, s) {
    const now = Date.now();
    const deadline = cs.deadline ? Date.parse(cs.deadline) : null;
    const since = cs.since ? Date.parse(cs.since) : s ? Date.parse(s.start) : now;
    const wins = (cs.windows || []).map(([a, b]) => [Date.parse(a), Date.parse(b)]);
    const end = deadline || (wins.length ? wins[wins.length - 1][1] : now + 8 * HOUR_MS);
    const t0 = Math.min(since, now);
    const span = Math.max(end - t0, HOUR_MS);
    const pos = (t) => clamp(((t - t0) / span) * 100, 0, 100);
    let ticks = "";
    for (let t = Math.ceil(t0 / (2 * HOUR_MS)) * 2 * HOUR_MS; t < end; t += 2 * HOUR_MS) {
      ticks += `<span class="tick" style="left:${pos(t)}%">${String(formats(this._hass).clock(t)[0]).padStart(2, "0")}</span>`;
    }
    let bar = wins.map(([a, b]) => `<i style="left:${pos(a)}%;width:${pos(b) - pos(a)}%;background:${EV_GRID};border-radius:3px;opacity:.8"></i>`).join("");
    // (as of 2026.11.4) dear quarters out of the house battery
    const bwins = (cs.battery_windows || []).map(([a, b]) => [Date.parse(a), Date.parse(b)]);
    bar += bwins.map(([a, b]) => `<i style="left:${pos(a)}%;width:${pos(b) - pos(a)}%;background:${EV_BATT};border-radius:3px;opacity:.85"></i>`).join("");
    bar += `<i class="now" style="left:${pos(now)}%"></i>`;
    const ready = cs.ready_by ? Date.parse(cs.ready_by) : null;
    if (ready && deadline && ready < deadline) bar += `<i class="mark" style="left:${pos(ready)}%;border-color:var(--ev)"></i>`;
    if (deadline) bar += `<i class="mark" style="left:100%"></i>`;
    let out = `<div class="tl"><div class="ticks">${ticks}</div><div class="tlbar">${bar}</div>
      <div class="tlfoot"><span>${esc(this._t("ev_tl_from")(this._time(since)))}</span><span>${esc(deadline ? this._t("ev_tl_to")(ready && ready < deadline ? this._time(ready) : null, this._time(deadline)) : "")}</span></div></div>`;
    const amps = Math.round(cs.plan_current_a || ev.max_current);
    out += `<div class="legend2">
      <div><i style="background:${EV_GRID}"></i><span>${esc(this._t("ev_legend_grid")(amps))}</span><span>${esc(this._windowsText(wins) || this._t("ev_none_short"))}</span></div>
      ${bwins.length ? `<div><i style="background:${EV_BATT}"></i><span>${esc(this._t("ev_legend_batt")(amps))}</span><span>${esc(this._windowsText(bwins))}</span></div>` : ""}
      <div><i style="background:var(--evsun)"></i><span>${esc(this._t("ev_legend_sun"))}</span><span>${esc(cs.solar_kwh > 0.05 ? this._kwh(cs.solar_kwh) : this._t("ev_none_short"))}</span></div></div>`;
    if (cs.tight) {
      out += `<div class="result bad">${EV_ICON.warn("#ff7b72")}<div style="display:flex;flex-direction:column;gap:4px"><b style="color:#ffb4ad">${esc(this._t("ev_r_tight_t")(this._when(deadline)))}</b><span>${esc(this._t("ev_tight_full"))} ${esc(this._when(cs.end ? Date.parse(cs.end) : null))}</span></div></div>`;
    } else {
      out += `<div class="result">${EV_ICON.check("var(--ev)")}<div>${esc(this._t("ev_r_end"))} <b>${esc(this._when(cs.end ? Date.parse(cs.end) : null))}</b></div></div>`;
    }
    return out;
  }

  // -- planned sessions ----------------------------------------------------------------
  _openSession(ev, s) {
    const car = this._carFor(ev, s);
    const start = Date.parse(s.start);
    const how = this._howOf(ev, s);
    this._edit = {
      id: s.id,
      label: s.label,
      running: !!s.running,
      day: localMidnight(this._hass, start),
      hour: formats(this._hass).clock(start)[0],
      car: s.car || (car ? car.id : ""),
      kwh: Number(s.kwh) || 0,
      start_soc: s.start_soc != null ? Number(s.start_soc) : null,
      target_soc: s.target_soc != null ? Number(s.target_soc) : car ? Number(car.target_soc) || 80 : null,
      how,
      current_a: Number(s.current_a) || ev.max_current,
      enabled: s.enabled !== false,
      delivered: Number(s.delivered_kwh) || 0,
      dl: s.deadline ? this._hhmm(Date.parse(s.deadline)) : "07:00",
      // the "full by" day (as of 2026.10.32); null = the first time after the start
      dlDay: s.deadline ? localMidnight(this._hass, Date.parse(s.deadline)) : null,
    };
    this._edit.orig = this._editKey(this._edit);
    this._error = null;
  }

  // what the plan depends on (as of 2026.11.5): unchanged = the integration's plan is shown
  _editKey(e) {
    return JSON.stringify([e.day, e.hour, e.car, e.kwh, e.start_soc, e.target_soc, e.how, e.dl, e.dlDay]);
  }

  // The integration's plan of a saved "full by" (as of 2026.11.5), while the
  // panel shows it unchanged - in the card's own preview's shape
  _savedPlan(ev, e) {
    if (!e.id || e.orig !== this._editKey(e)) return null;
    const s = (ev.sessions || []).find((x) => x.id === e.id);
    const fb = s && s.full_by;
    if (!fb || !Array.isArray(fb.window_kwh) || fb.tight || fb.estimate) return null;
    const ms = (w) => (w || []).map(([a, b]) => [Date.parse(a), Date.parse(b)]);
    return {
      real: true,
      windows: ms(fb.windows), windowKwh: fb.window_kwh, windowCost: fb.window_cost || [],
      bwindows: ms(fb.battery_windows), bwindowKwh: fb.battery_window_kwh || [], bwindowCost: fb.battery_window_cost || [],
      solar: Number(fb.solar_kwh) || 0, grid: Number(fb.grid_kwh) || 0, battery: Number(fb.battery_kwh) || 0,
      cost: Number(fb.cost) || 0, amps: fb.current_a, kw: Number(fb.grid_kw) || evPower(fb.current_a, ev.phases || 3),
      end: fb.end ? Date.parse(fb.end) : s.end ? Date.parse(s.end) : null,
      readyBy: fb.ready_by ? Date.parse(fb.ready_by) : null,
      deadline: s.deadline ? Date.parse(s.deadline) : null,
    };
  }

  // the card's own preview split per window (each at the plan's power, the
  // last one only as far as needed), with the price of its quarters
  _previewParts(p) {
    const prices = this._prices();
    const priceStart = localMidnight(this._hass, Date.now());
    const now = Date.now();
    let left = p.grid || 0;
    const kwh = [];
    const cost = [];
    for (const [a, b] of p.windows || []) {
      let k = 0;
      let c = 0;
      for (let q = a; q < b && left > 1e-9; q += UNIT_MS) {
        const fr = Math.max(Math.min(q + UNIT_MS, b) - Math.max(q, now), 0) / UNIT_MS;
        const take = Math.min((p.kw / 4) * fr, left);
        const i = Math.floor((q - priceStart) / UNIT_MS);
        left -= take;
        k += take;
        c += take * (i >= 0 && i < prices.length && prices[i] != null ? prices[i] : 0);
      }
      kwh.push(k);
      cost.push(c);
    }
    return { ...p, real: false, windowKwh: kwh, windowCost: cost, bwindows: [], bwindowKwh: [], bwindowCost: [], battery: 0 };
  }

  // The charge plan of a "full by" (as of 2026.11.5): the quarters' prices
  // from the start to the deadline, the windows on them, and per window what
  // goes in and what it costs
  _planBlock(plan, begin) {
    const deadline = plan.deadline;
    if (!deadline || deadline <= begin) return "";
    const prices = this._prices();
    const priceStart = localMidnight(this._hass, Date.now());
    const first = Math.floor(begin / UNIT_MS) * UNIT_MS;
    const qs = [];
    for (let q = first; q < deadline; q += UNIT_MS) {
      const i = Math.floor((q - priceStart) / UNIT_MS);
      qs.push([q, i >= 0 && i < prices.length && prices[i] != null && isFinite(prices[i]) ? prices[i] : null]);
    }
    const known = qs.map(([, v]) => v).filter((v) => v != null);
    if (!known.length) return "";
    const lo = Math.min(...known);
    const hi = Math.max(...known);
    const span = deadline - first;
    const pos = (t) => Math.min(Math.max(((t - first) / span) * 100, 0), 100);
    const inW = (q, ws) => ws.some(([a, b]) => q >= a && q < b);
    const w = 100 / qs.length;
    let bars = qs.map(([q, v]) => {
      if (v == null) return "";
      const h = 18 + (hi > lo ? (82 * (v - lo)) / (hi - lo) : 40);
      const c = inW(q, plan.bwindows) ? EV_BATT : inW(q, plan.windows) ? EV_GRID : "rgba(127,127,127,.38)";
      return `<i style="left:${pos(q)}%;width:${w * 0.78}%;height:${h}%;background:${c}"></i>`;
    }).join("");
    bars += plan.windows.map(([a, b]) => `<b style="left:${pos(a)}%;width:${pos(b) - pos(a)}%;--c:${EV_GRID}"></b>`).join("");
    bars += plan.bwindows.map(([a, b]) => `<b style="left:${pos(a)}%;width:${pos(b) - pos(a)}%;--c:${EV_BATT}"></b>`).join("");
    const ticks = [];
    const hours = span / HOUR_MS;
    const step = hours > 36 ? 12 : hours > 18 ? 6 : hours > 8 ? 3 : 1;
    for (let t = Math.ceil(first / HOUR_MS) * HOUR_MS; t <= deadline; t += HOUR_MS) {
      const [h] = formats(this._hass).clock(t);
      if (h % step === 0) ticks.push(`<span style="left:${pos(t)}%">${String(h).padStart(2, "0")}</span>`);
    }
    const f = formats(this._hass);
    const rows = [];
    plan.windows.forEach(([a, b], k) => rows.push([a, b, "grid", plan.windowKwh[k] || 0, plan.windowCost[k] || 0]));
    plan.bwindows.forEach(([a, b], k) => rows.push([a, b, "batt", plan.bwindowKwh[k] || 0, plan.bwindowCost[k] || 0]));
    rows.sort((x, y) => x[0] - y[0]);
    let list = rows.map(([a, b, kind, k, c]) => `<div class="pl-row"><i style="background:${kind === "batt" ? EV_BATT : EV_GRID}"></i><b>${esc(this._time(a))} \u2013 ${esc(this._time(b))}</b><span style="color:${kind === "batt" ? EV_BATT : EV_GRID}">${esc(this._t(kind === "batt" ? "ev_pl_batt" : "ev_pl_grid"))}</span><span class="dim">${esc(`${plan.amps} A \u00b7 ${this._kwh(k)}`)}</span><span>${k > 0.01 ? esc(formatPrice(f, c / k)) : ""}</span></div>`).join("");
    if (plan.solar > 0.05) list += `<div class="pl-row"><i style="background:var(--evsun)"></i><b>${esc(this._t("ev_pl_sun"))}</b><span></span><span class="dim">${esc(this._kwh(plan.solar))}</span><span></span></div>`;
    const kwh = rows.reduce((a, r) => a + r[3], 0);
    const cost = rows.reduce((a, r) => a + r[4], 0);
    const sum = kwh > 0.05 ? `<div class="pl-sum"><span class="dim">${esc(this._t("ev_pl_cost"))}</span><b>${esc(f.money(cost))} \u00b7 ${esc(this._t("ev_pl_avg")(formatPrice(f, cost / kwh)))}</b></div>` : "";
    const notes = [this._t("ev_pl_legend")];
    if (plan.bwindows.length) notes.push(this._t("ev_pl_batt_note"));
    return `<div class="pl">
      <div class="pl-head"><span>${esc(this._t("ev_pl_title"))}</span>${plan.real ? "" : `<span class="dim">${esc(this._t("ev_pl_preview"))}</span>`}</div>
      <div class="pl-tl">${bars}<u></u></div>
      <div class="pl-ticks">${ticks.join("")}</div>
      ${list ? `<div class="pl-rows">${list}</div>` : ""}${sum}
      <div class="hint">${esc(notes.join(" \u00b7 "))}</div>
    </div>`;
  }

  _hhmm(ms) {
    const [h, m] = formats(this._hass).clock(ms);
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }

  // a planned "full by": `e.dl` on the day picked (as of 2026.10.32), or
  // without one the first time `e.dl` after its start
  _editDeadline(e) {
    const [h, m] = String(e.dl || "07:00").split(":").map((v) => Number(v) || 0);
    if (e.dlDay != null && e.dlDay >= e.day) return this._at(e.dlDay, h, m);
    const start = this._startMs(e);
    let t = this._at(e.day, h, m);
    if (t <= start) t = this._at(nextMidnight(this._hass, e.day), h, m);
    return t;
  }

  _openNew(ev) {
    const cars = ev.cars || [];
    const car = cars.length === 1 ? cars[0] : null;
    const next = Math.floor(Date.now() / HOUR_MS) * HOUR_MS + HOUR_MS;
    const target = car ? Number(car.target_soc) || 80 : null;
    this._edit = {
      id: null,
      label: "manual",
      running: false,
      day: localMidnight(this._hass, next),
      hour: formats(this._hass).clock(next)[0],
      car: car ? car.id : "",
      kwh: 10,
      start_soc: car && car.capacity_kwh ? Math.max(target - Math.round((10 / evCap(car)) * 100), 0) : null,
      target_soc: target,
      how: "asap",
      current_a: ev.max_current,
      enabled: true,
      delivered: 0,
      dl: "07:00",
      dlDay: null,
    };
    this._error = null;
  }

  _startMs(e) {
    return this._at(e.day, e.hour, 0);
  }

  _editKwh(ev, e) {
    const car = this._car(ev, e.car);
    if (car && car.capacity_kwh && e.start_soc != null && e.target_soc != null) {
      return Math.max(((e.target_soc - e.start_soc) / 100) * evCap(car), 0);
    }
    return Math.max(Number(e.kwh) || 0, 0);
  }

  _editAmps(ev, e) {
    if (e.running && e.how !== "solar") return clamp(Math.round(e.current_a), ev.min_current, ev.max_current);
    return e.how === "calm" ? ev.min_current : ev.max_current;
  }

  // {end ms | null, warning, got, need}: fixed from the start; solar per hour
  // on the house surplus until the end of that day.
  _preview(ev, e) {
    const need = Math.max(this._editKwh(ev, e) - (e.running ? e.delivered : 0), 0);
    const now = Date.now();
    const begin = Math.max(this._startMs(e), now);
    if (need <= 1e-9) return { end: begin, warning: null, got: 0, need };
    const phases = ev.phases || 3;
    if (e.how === "deadline") {
      const deadline = this._editDeadline(e);
      if (deadline <= begin) return { past: true, by: true, need, got: 0 };
      // (as of 2026.11.5) a saved session unchanged: the integration's own plan
      const saved = this._savedPlan(ev, e);
      if (saved) return { ...saved, deadline, readyBy: saved.readyBy || deadline - HOUR_MS, got: need, need, by: true };
      const prices = this._prices();
      const priceStart = localMidnight(this._hass, now);
      const net = ev.house_net_120h || [];
      const hour0 = Math.floor(now / HOUR_MS) * HOUR_MS;
      if (deadline - HOUR_MS <= priceStart + prices.length * UNIT_MS) {
        const [fNet, fLo, fHi] = this._fbRange(ev, net);
        const plan = evPlanFullBy(begin, deadline, need, fNet, hour0, prices, priceStart, phases, fLo, fHi, HOUR_MS, ev.min_current);
        return { ...plan, got: need - plan.short, need, by: true };
      }
      // prices not known yet: a calm charge from the start
      const ready = Math.max(deadline - HOUR_MS, begin + UNIT_MS);
      let amps = ev.max_current;
      for (let a = ev.min_current; a <= ev.max_current; a++) if ((evPower(a, phases) * (ready - begin)) / HOUR_MS >= need) { amps = a; break; }
      const kw = evPower(amps, phases);
      const reach = Math.min(need, (kw * (deadline - begin)) / HOUR_MS);
      return { end: begin + (need / kw) * HOUR_MS, amps, kw, readyBy: ready, deadline, tight: need - reach > 0.05, reach, got: need, need, by: true, estimate: true };
    }
    if (e.how !== "solar") {
      const kw = evPower(this._editAmps(ev, e), phases);
      return { end: begin + (need / kw) * HOUR_MS, warning: null, got: need, need };
    }
    const net = ev.house_net_120h || [];
    const hour0 = Math.floor(now / HOUR_MS) * HOUR_MS;
    const dayEnd = nextMidnight(this._hass, localMidnight(this._hass, this._startMs(e)));
    const pMax = evPower(ev.max_current, phases);
    const pMin = evPower(ev.min_current, phases);
    let left = need;
    let end = null;
    for (let h = 0; h < net.length && left > 1e-9; h++) {
      const w0 = hour0 + h * HOUR_MS;
      if (w0 >= dayEnd) break;
      const lo = Math.max(w0, begin);
      const hi = Math.min(w0 + HOUR_MS, dayEnd);
      if (hi <= lo) continue;
      const spare = Math.max(Number(net[h]) || 0, 0);
      const rate = spare >= pMin ? Math.min(spare, pMax) : 0;
      if (!rate) continue;
      const take = Math.min((rate * (hi - lo)) / HOUR_MS, left);
      left -= take;
      if (left <= 1e-9) end = lo + (take / rate) * HOUR_MS;
    }
    const got = need - left;
    return { end, warning: got <= 0.05 ? "no_surplus" : left > 0.05 ? "short" : null, got, need };
  }

  _result(ev, e) {
    const p = this._preview(ev, e);
    const kwh = this._editKwh(ev, e);
    if (e.how === "deadline") {
      if (p.past) return `<div class="result bad">${EV_ICON.warn("#ff7b72")}<div>${esc(this._t("ev_r_before_start"))}</div></div>`;
      if (p.tight) {
        return `<div class="result bad">${EV_ICON.warn("#ff7b72")}<div style="display:flex;flex-direction:column;gap:4px"><b style="color:#ffb4ad">${esc(this._t("ev_r_tight_t")(this._when(p.deadline)))}</b><span>${esc(this._t("ev_r_tight")(this._kwh(p.need), `${ev.max_current} A`, this._kwh(p.reach), this._when(p.end)))}</span></div></div>`;
      }
      const note = p.estimate ? `<div class="hint">${esc(this._t("ev_r_estimate"))}</div>` : "";
      const block = p.estimate ? "" : this._planBlock(p.real ? p : this._previewParts(p), Math.max(this._startMs(e), Date.now()));
      return `<div class="result">${EV_ICON.deadline(EV_GRID)}<div style="display:flex;flex-direction:column;gap:2px"><span>${esc(this._t("ev_r_end"))} <b>${esc(this._when(p.end))}</b> \u00b7 ${esc(this._t("ev_in_plan")(this._kwh(kwh)))}</span><span class="dim" style="font-size:12px">${esc(this._t("ev_r_by_fixed")(p.amps, this._kw(p.kw), this._when(p.readyBy), this._when(p.deadline)))}</span>${note}</div></div>${block}`;
    }
    if (e.how === "solar" && p.warning === "no_surplus") return `<div class="result warn">${ICON_CLOCK(EV_WARN)}<div>${esc(this._t("ev_warn_none"))}</div></div>`;
    if (e.how === "solar" && p.warning === "short") return `<div class="result warn">${ICON_CLOCK(EV_WARN)}<div>${esc(this._t("ev_warn_short")(this._kwh(p.got + (e.running ? e.delivered : 0)), this._kwh(kwh)))}</div></div>`;
    const end = p.end != null ? `${e.how === "solar" ? "\u00b1 " : ""}${this._time(p.end)}` : "\u2014";
    if (e.running) return `<div class="result">${ICON_CLOCK("var(--ev)")}<div>${esc(this._t("ev_left")(this._kwh(p.need)))} \u00b7 ${esc(this._t("ev_at"))} <b>${esc(end)}</b></div></div>`;
    return `<div class="result">${ICON_CLOCK("var(--ev)")}<div>${esc(this._t("ev_at"))} <b>${esc(end)}</b> \u00b7 ${esc(this._t("ev_in_plan")(this._kwh(kwh)))}</div></div>`;
  }

  _editPanel(ev) {
    const e = this._edit;
    const cars = ev.cars || [];
    const car = this._car(ev, e.car);
    const phases = ev.phases || 3;
    const days = this._days(ev);
    const nowHour = Math.floor(Date.now() / HOUR_MS) * HOUR_MS;
    let out = "";
    let fields = "";
    if (cars.length) {
      const opts = (cars.length > 1 ? [`<option value="" ${e.car ? "" : "selected"}>${esc(this._t("ev_no_car"))}</option>`] : [])
        .concat(cars.map((c) => `<option value="${esc(c.id)}" ${c.id === e.car ? "selected" : ""}>${esc(c.name)}</option>`));
      fields += `<label class="fld">${esc(this._t("ev_car"))}<select data-f="car">${opts.join("")}</select></label>`;
    }
    const dayOpts = days.map((d) => `<option value="${d}" ${d === e.day ? "selected" : ""}>${esc(this._day(d))}</option>`).join("");
    fields += `<label class="fld">${esc(this._t("ev_day"))}<select data-f="day" ${e.running ? "disabled" : ""}>${dayOpts}</select></label>`;
    if (e.running) {
      fields += `<label class="fld">${esc(this._t("ev_start"))}<span class="locked">${ICON_LOCK}${String(e.hour).padStart(2, "0")}:00</span></label>`;
    } else {
      const hourOpts = [];
      for (let h = 0; h < 24; h++) {
        const t = this._at(e.day, h, 0);
        if (t + HOUR_MS <= nowHour) continue;
        hourOpts.push(`<option value="${h}" ${h === e.hour ? "selected" : ""}>${String(h).padStart(2, "0")}:00</option>`);
      }
      fields += `<label class="fld">${esc(this._t("ev_start"))}<select data-f="hour">${hourOpts.join("")}</select></label>`;
    }
    out += `<div class="${cars.length ? "grid3" : "grid2"}">${fields}</div>`;
    if (e.running) out += `<div class="note">${esc(this._t("ev_running_note"))}</div>`;
    const hows = [["asap", this._t("ev_h_asap")], ["calm", this._t("ev_h_calm")], ["solar", this._t("ev_h_solar")]];
    // "full by" needs a charger ESS Manager drives (the Victron charger)
    if (ev.charger && !e.running) hows.push(["deadline", this._t("ev_h_by")]);
    out += `<div class="fldgrp"><span class="lab">${esc(this._t("ev_how"))}</span>${this._seg("data-eh", hows, e.how, hows.length)}</div>`;
    if (e.how === "deadline") {
      // the day it should be full: the start day and the three after it (as of 2026.10.32)
      const dlSel = localMidnight(this._hass, this._editDeadline(e));
      // shown = picked: typing another time doesn't move the day under you
      e.dlDay = dlSel;
      const dlDays = [e.day];
      while (dlDays.length < 4) dlDays.push(nextMidnight(this._hass, dlDays[dlDays.length - 1]));
      if (!dlDays.includes(dlSel)) dlDays.push(dlSel);
      const dlOpts = dlDays.map((d) => `<option value="${d}" ${d === dlSel ? "selected" : ""}>${esc(this._day(d))}</option>`).join("");
      out += `<div class="grid2"><label class="fld">${esc(this._t("ev_full_day"))}<select data-f="dlday">${dlOpts}</select></label><label class="fld">${esc(this._t("ev_full_at"))}<input type="time" data-et="dl" value="${esc(e.dl || "07:00")}"></label></div>`;
    } else if (e.how === "solar") {
      out += `<div class="hint">${esc(this._t("ev_r_solar_hint")(`${ev.min_current} A`, `${ev.max_current} A`))}</div>`;
    } else if (e.running) {
      const a = this._editAmps(ev, e);
      out += `
        <div class="slider">
          <div class="lab"><label for="ev-amp">${esc(this._t("ev_current"))}</label><span data-k="amp">${a} A \u00b7 ${esc(this._kw(evPower(a, phases)))}</span></div>
          <input id="ev-amp" type="range" data-s="current_a" min="${ev.min_current}" max="${ev.max_current}" step="1" value="${a}">
          <div class="ends"><span>${ev.min_current} A \u00b7 ${esc(this._kw(evPower(ev.min_current, phases)))}</span><span>${esc(this._t("ev_phases")(phases))}</span><span>${ev.max_current} A \u00b7 ${esc(this._kw(evPower(ev.max_current, phases)))}</span></div>
        </div>`;
    }
    if (car && car.capacity_kwh) {
      if (e.start_soc == null) e.start_soc = Math.max((e.target_soc || 80) - Math.round((e.kwh / evCap(car)) * 100), 0);
      if (e.target_soc == null) e.target_soc = Number(car.target_soc) || 80;
      out += `<div class="grid2">
        ${this._slider("start_soc", this._t(e.running ? "ev_start_soc" : "ev_soc_plug"), e.start_soc, 0, 100, 1, `${Math.round(e.start_soc)}%`, "var(--secondary-text-color,#9b9b9b)")}
        ${this._slider("target_soc", this._t("ev_target"), e.target_soc, 0, 100, 1, `${Math.round(e.target_soc)}%`)}
      </div>`;
    } else {
      out += this._slider("kwh", this._t("ev_energy"), e.kwh, 0.5, Math.max(100, Math.ceil(e.kwh)), 0.5, this._kwh(e.kwh));
    }
    out += `<div data-k="result">${this._result(ev, e)}</div>`;
    if (this._error) out += `<div class="err">${esc(this._error)}</div>`;
    let extra = "";
    if (e.id && e.label === "edited") extra = `<button type="button" class="btn link" data-act="average">${esc(this._t("ev_back_average"))}</button>`;
    else if (e.id && e.label === "manual" && !e.running) extra = `<button type="button" class="btn link" data-act="remove">${esc(this._t("ev_remove"))}</button>`;
    if (extra) out += `<div style="margin:-6px 0 -8px -6px">${extra}</div>`;
    out += `<div class="actions"><div class="grow"></div>
      <button type="button" class="btn" data-act="cancel">${esc(this._t("ev_cancel"))}</button>
      <button type="button" class="btn primary" data-act="save" ${this._saving ? "disabled" : ""}>${esc(this._t("ev_save"))}</button></div>`;
    return out;
  }

  _slider(key, label, value, min, max, step, text, accent) {
    return `
      <div class="slider">
        <div class="lab"><label for="ev-${key}">${esc(label)}</label><span data-k="${key}">${esc(text)}</span></div>
        <input id="ev-${key}" type="range" data-s="${key}" min="${min}" max="${max}" step="${step}" value="${value}"${accent ? ` style="accent-color:${accent}"` : ""}>
      </div>`;
  }

  _row(ev, s) {
    if (s.completed) return this._doneRow(ev, s);
    const start = Date.parse(s.start);
    const end = s.end ? Date.parse(s.end) : null;
    const car = this._car(ev, s.car);
    const solar = s.mode === "solar";
    const sel = this._edit && this._edit.id === s.id;
    const cls = ["ev-row", s.enabled ? "" : "off", sel ? "sel" : s.solar_history ? "hist" : ""].join(" ");
    const stop = end ? `${solar ? "\u00b1 " : ""}${this._time(end)}` : "\u2014";
    // a planned "full by": the line shows the planned start (as of 2026.11.21 -
    // from 2026.11.5 to .20 its first charge window), the charging's own
    // start goes with the number of blocks
    const from = start;
    let blocks = "";
    const fb = s.mode === "deadline" && !s.running ? s.full_by : null;
    if (fb && !fb.tight && !fb.estimate && !(Number(fb.solar_kwh) > 0.05)) {
      const ws = [...(fb.windows || []), ...(fb.battery_windows || [])].map(([a]) => Date.parse(a)).filter((t) => isFinite(t));
      if (ws.length) {
        const first = Math.max(Math.min(...ws), start);
        blocks = first > start + 60000
          ? ` \u00b7 ${this._t("ev_pl_blocks_from")(ws.length, this._time(first))}`
          : ` \u00b7 ${this._t("ev_pl_blocks")(ws.length)}`;
      }
    }
    const chip = { history: "ev_label_history", edited: "ev_label_edited", manual: "ev_label_manual" }[s.label] || "ev_label_manual";
    const how = this._howOf(ev, s);
    let warn = "";
    if (s.mode === "deadline" && s.warning === "short") warn = `<div class="ev-warn" style="color:#ff7b72">${esc(this._t("ev_r_tight_t")(s.deadline ? this._when(Date.parse(s.deadline)) : "\u2014"))}</div>`;
    else if (s.warning === "no_surplus") warn = `<div class="ev-warn">${esc(this._t("ev_warn_none"))}</div>`;
    else if (s.warning === "short") warn = `<div class="ev-warn">${esc(this._t("ev_warn_short")(this._kwh(s.charged_kwh), this._kwh(s.kwh)))}</div>`;
    // (as of 2026.10.36) waits for the plugged-in car: counts only after it
    if (s.waits) warn = `<div class="ev-warn" style="color:var(--secondary-text-color,#a0a0a0)">${esc(s.waits_until ? this._t("ev_waits_until")(this._when(Date.parse(s.waits_until))) : this._t("ev_waits"))}</div>` + warn;
    return `
      <div class="${cls}">
        <button type="button" class="ev-main" data-open="${esc(s.id)}" aria-label="${esc(this._t("ev_edit_aria"))} ${esc(this._day(start))} ${esc(this._time(start))}">
          <div class="ev-line"><div class="ev-when">${esc(this._day(from))} \u00b7 ${esc(this._time(from))} \u2192 ${esc(stop)}</div><div class="ev-kwh">+${esc(this._kwh(s.kwh))}</div></div>
          <div class="ev-meta">
            <span class="chip${s.label === "history" ? "" : " strong"}">${esc(this._t(chip))}</span>
            ${car ? `<span class="car">${esc(car.name)} \u00b7</span>` : ""}
            <span class="how">${EV_ICON[how](EV_HOW_COLOR[how]).replace('width="16" height="16"', 'width="14" height="14"')}${esc(this._howText(ev, s))}${blocks ? `<span class="dim">${esc(blocks)}</span>` : ""}</span>
          </div>
          ${warn}
        </button>
        <label class="ev-check"><input type="checkbox" data-toggle="${esc(s.id)}" ${s.enabled ? "checked" : ""} aria-label="${esc(this._t("ev_count"))}"></label>
      </div>`;
  }

  // A finished session (as of 2026.10.37): shown for 6 hours after the car was
  // unplugged (Victron) or the charging stopped, with what went in - not editable
  _doneRow(ev, s) {
    const start = Date.parse(s.start);
    const end = s.end ? Date.parse(s.end) : null;
    const car = this._car(ev, s.car);
    return `
      <div class="ev-row done">
        <div class="ev-main" style="cursor:default">
          <div class="ev-line"><div class="ev-when">${esc(this._day(start))} \u00b7 ${esc(this._time(start))} \u2192 ${esc(end ? this._time(end) : "\u2014")}</div><div class="ev-kwh">+${esc(this._kwh(s.charged_kwh != null ? s.charged_kwh : s.kwh))}</div></div>
          <div class="ev-meta">
            <span class="chip strong done">${esc(this._t("ev_label_done"))}</span>
            ${car ? `<span class="car">${esc(car.name)}</span>` : ""}
          </div>
        </div>
      </div>`;
  }

  // -- rendering -------------------------------------------------------------------------
  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    if (this._dragging) return; // never replace a slider while it's being dragged
    const active = this.shadowRoot.activeElement;
    if (active && active.tagName === "SELECT") return; // nor a list that's open
    if (active && active.tagName === "INPUT" && active.type === "time") return; // nor a time being typed
    const st = this._hass.states[this._config.entity];
    const opt = this._opt();
    const css = BASE_CSS + EV_CSS + `ha-card { --ev: ${opt.ev_color}; --evsun: ${opt.solar_color}; }`;
    if (!isStatusSensor(st)) {
      setCardContent(this, css, notStatusMessage(this._hass, this._config.entity, st));
      return;
    }
    const ev = st.attributes.ev;
    if (!ev) {
      setCardContent(this, css, `<div style="padding:4px">${esc(this._t("ev_off"))}</div>`);
      return;
    }
    const sessions = ev.sessions || [];
    if (this._edit && this._edit.id && !sessions.some((s) => s.id === this._edit.id)) this._edit = null;
    const nu = this._nu(ev);
    if (this._plan && (!nu || !nu.cs || nu.cs.id !== this._plan.sid)) this._plan = null;
    const planned = sessions.filter((s) => !nu || !nu.s || s.id !== nu.s.id);
    const cars = ev.cars || [];
    const counted = sessions.filter((s) => s.enabled);
    const total = counted.reduce((a, s) => a + (Number(s.charged_kwh) || 0), 0);
    const title = this._config.title || (cars.length === 1 ? cars[0].name : this._t("ev_title"));
    const sub = [nu ? this._t("ev_n_busy") : "", planned.length ? this._t("ev_n_planned")(planned.length) : ""].filter(Boolean).join(" \u00b7 ");
    let html = `
      <div class="top">
        <div style="display:flex;flex-direction:column;gap:2px;flex-grow:1;min-width:0">
          <div class="title">${esc(title)}</div>
          <div class="dim" style="font-size:13px">${esc(this._t("ev_sub")(ev.days || 5))}</div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px">
          <div style="font-size:20px;font-weight:600;white-space:nowrap">${esc(this._kwh(total))}</div>
          <div class="dim" style="font-size:12px">${esc(sub)}</div>
        </div>
      </div>`;
    if (nu) html += `<div class="sec">${esc(this._t("ev_now"))}</div>${this._nuBlock(ev, nu)}`;
    html += `<div class="sec">${esc(this._t("ev_planned"))}</div><div class="ev-list">`;
    if (!planned.length) html += `<div class="ev-empty">${esc(this._t(ev.predict ? "ev_none" : "ev_none_manual"))}</div>`;
    for (const s of planned) {
      html += this._row(ev, s);
      if (this._edit && this._edit.id === s.id) html += `<div class="ev-edit">${this._editPanel(ev)}</div>`;
    }
    html += "</div>";
    if (planned.some((s) => s.solar_history)) html += `<div class="legend-hist"><span></span>${esc(this._t("ev_hist_legend"))}</div>`;
    if (this._edit && !this._edit.id) html += `<div class="ev-edit"><div class="head"><span>${esc(this._t("ev_new"))}</span></div>${this._editPanel(ev)}</div>`;
    else html += `<button type="button" class="ev-add" data-act="add">${ICON_PLUS}${esc(this._t("ev_plan_add"))}</button>`;
    // the state-of-charge correction per car (as of 2026.10.35): measured on
    // finished charges, applied from three on
    const corr = cars
      .filter((c) => Number(c.kwh_factor_sessions) > 0)
      .map((c) => {
        const n = Number(c.kwh_factor_sessions);
        const who = cars.length > 1 ? `${c.name} ` : "";
        return n >= 3 ? `${who}\u00d7${this._num(Number(c.kwh_factor) || 1, 2)} (${this._t("ev_corr_n")(n)})` : `${who}${this._t("ev_corr_wait")(n, 3)}`;
      });
    if (corr.length) html += `<div class="dim" style="font-size:12px" title="${esc(this._t("ev_corr_tip"))}">${esc(this._t("ev_corr"))}: ${esc(corr.join(" \u00b7 "))}</div>`;
    if (setCardContent(this, css, html)) this._wire(ev);
  }

  // Live texts while a slider moves (the sliders themselves stay in place).
  _live(ev) {
    const root = this.shadowRoot;
    const set = (k, html) => {
      const el = root.querySelector(`[data-k="${k}"]`);
      if (el) el.innerHTML = html;
    };
    const phases = ev.phases || 3;
    if (this._plan) {
      const p = this._plan;
      set("psoc", `${Math.round(p.soc)}%`);
      set("ptarget", `${Math.round(p.target)}%`);
      set("pkwh", esc(this._kwh(p.kwh)));
      const a = clamp(Math.round(p.current), ev.min_current, ev.max_current);
      set("pcur", `${a} A \u00b7 ${esc(this._kw(evPower(a, phases)))}`);
      set("presult", this._planResult(ev, p));
    }
    const e = this._edit;
    if (e) {
      set("start_soc", `${Math.round(e.start_soc)}%`);
      set("target_soc", `${Math.round(e.target_soc)}%`);
      set("kwh", esc(this._kwh(e.kwh)));
      const a = this._editAmps(ev, e);
      set("amp", `${a} A \u00b7 ${esc(this._kw(evPower(a, phases)))}`);
      set("result", this._result(ev, e));
    }
  }

  _rerender() {
    this._dragging = false;
    this._essInner = null;
    this._render();
  }

  _wire(ev) {
    const root = this.shadowRoot;
    const scrollTo = (sel) => requestAnimationFrame(() => {
      const block = root.querySelector(sel);
      if (block && block.scrollIntoView) block.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    root.querySelectorAll("[data-open]").forEach((el) =>
      el.addEventListener("click", () => {
        const id = el.getAttribute("data-open");
        const s = (ev.sessions || []).find((x) => x.id === id);
        if (this._edit && this._edit.id === id) this._edit = null;
        else if (s) this._openSession(ev, s);
        this._rerender();
        if (this._edit) scrollTo(".ev-edit, .nu");
      })
    );
    root.querySelectorAll("[data-toggle]").forEach((el) =>
      el.addEventListener("change", () => this._call("ev_session_save", { id: el.getAttribute("data-toggle"), enabled: el.checked }))
    );
    const act = (name, fn) => {
      const el = root.querySelector(`[data-act="${name}"]`);
      if (el) el.addEventListener("click", fn);
    };
    act("add", () => {
      this._openNew(ev);
      this._rerender();
      scrollTo(".ev-edit");
    });
    act("cancel", () => {
      this._edit = null;
      this._rerender();
    });
    act("save", () => this._save(ev));
    act("average", () => this._call("ev_session_remove", { id: this._edit.id }, true));
    act("remove", () => this._call("ev_session_remove", { id: this._edit.id }, true));
    // the plugged-in car
    const nu = this._nu(ev);
    const openPlan = (how) => {
      if (!nu || !nu.cs) return;
      this._plan = this._planInit(ev, nu.cs, nu.s, how);
      if (how) this._plan.active = false;
      this._planError = null;
      this._rerender();
    };
    root.querySelectorAll("[data-pick]").forEach((el) => el.addEventListener("click", () => openPlan(el.getAttribute("data-pick"))));
    act("plan-open", () => openPlan(null));
    act("plan-cancel", () => {
      this._plan = null;
      this._planError = null;
      this._rerender();
    });
    act("plan-go", () => this._planGo(ev));
    const sliding = (el, apply) => {
      el.addEventListener("pointerdown", () => {
        this._dragging = true;
      });
      for (const type of ["pointerup", "pointercancel"]) el.addEventListener(type, () => {
        this._dragging = false;
      });
      el.addEventListener("input", () => {
        // apply may hand back the value it was held to (as of 2026.11.7)
        const held = apply(Number(el.value));
        if (held != null && held !== Number(el.value)) el.value = String(held);
        this._live(ev);
      });
      el.addEventListener("change", () => this._rerender());
    };
    if (this._plan) {
      const p = this._plan;
      root.querySelectorAll("[data-ph]").forEach((el) => el.addEventListener("click", () => {
        p.how = el.getAttribute("data-ph");
        if (p.how === "asap") p.current = ev.max_current;
        if (p.how === "calm") p.current = ev.min_current;
        this._rerender();
      }));
      root.querySelectorAll("[data-pd]").forEach((el) => el.addEventListener("click", () => {
        p.day = el.getAttribute("data-pd");
        this._rerender();
      }));
      root.querySelectorAll("select[data-pf]").forEach((el) => el.addEventListener("change", () => {
        p.car = el.value;
        const car = this._car(ev, p.car);
        if (car) p.target = Math.round(Number(car.target_soc) || 80);
        this._rerender();
      }));
      root.querySelectorAll('input[data-p="hour"]').forEach((el) => {
        el.addEventListener("input", () => {
          if (el.value) {
            p.hour = el.value;
            this._live(ev);
          }
        });
        el.addEventListener("change", () => {
          if (el.value) p.hour = el.value;
          this._live(ev);
        });
      });
      root.querySelectorAll("input[data-ps]").forEach((el) => {
        const key = el.getAttribute("data-ps");
        sliding(el, (v) => {
          // (as of 2026.11.7) the state of charge stops at the target and
          // the target at the state of charge - neither pushes the other
          // (up to then the target went up with the state of charge, and
          // stayed there when it came back)
          if (key === "soc" && v > p.target) v = p.target;
          if (key === "target" && v < p.soc) v = p.soc;
          p[key] = v;
          return v;
        });
      });
    }
    if (!this._edit) return;
    const e = this._edit;
    root.querySelectorAll("[data-eh]").forEach((el) =>
      el.addEventListener("click", () => {
        e.how = el.getAttribute("data-eh");
        if (e.how === "asap") e.current_a = ev.max_current;
        if (e.how === "calm") e.current_a = ev.min_current;
        this._rerender();
      })
    );
    root.querySelectorAll("select[data-f]").forEach((el) =>
      el.addEventListener("change", () => {
        const f = el.getAttribute("data-f");
        if (f === "car") {
          e.car = el.value;
          const car = this._car(ev, e.car);
          if (car && car.capacity_kwh) {
            e.target_soc = e.target_soc != null ? e.target_soc : Number(car.target_soc) || 80;
            e.start_soc = Math.max(e.target_soc - Math.round((e.kwh / evCap(car)) * 100), 0);
          } else e.start_soc = null;
        } else if (f === "day") {
          // the "full by" day moves along with the start day
          let offset = 0;
          if (e.dlDay != null) for (let d = e.day; d < e.dlDay && offset < 7; d = nextMidnight(this._hass, d)) offset++;
          e.day = Number(el.value);
          if (e.dlDay != null) {
            let d = e.day;
            for (let i = 0; i < offset; i++) d = nextMidnight(this._hass, d);
            e.dlDay = d;
          }
        } else if (f === "hour") e.hour = Number(el.value);
        else if (f === "dlday") e.dlDay = Number(el.value);
        this._rerender();
      })
    );
    root.querySelectorAll('input[data-et="dl"]').forEach((el) => {
      const apply = () => {
        if (el.value) {
          e.dl = el.value;
          this._live(ev);
        }
      };
      el.addEventListener("input", apply);
      el.addEventListener("change", apply);
    });
    root.querySelectorAll("input[data-s]").forEach((el) => {
      const key = el.getAttribute("data-s");
      sliding(el, (v) => {
        // (as of 2026.11.7) the state of charge stops at the target and the target at the state of charge
        if (key === "start_soc" && e.target_soc != null && v > e.target_soc) v = e.target_soc;
        if (key === "target_soc" && e.start_soc != null && v < e.start_soc) v = e.start_soc;
        e[key] = v;
        const car = this._car(ev, e.car);
        if (car && car.capacity_kwh && key !== "current_a") e.kwh = this._editKwh(ev, e);
        return v;
      });
    });
  }

  async _planGo(ev) {
    const p = this._plan;
    if (!p) return;
    const car = this._car(ev, p.car);
    const data = { choice: p.how };
    if (p.car) data.car = p.car;
    if (p.how === "deadline") {
      data.day = p.day;
      if (p.day !== "any") data.hour = p.hour;
    }
    if ((p.how === "asap" || p.how === "calm") && p.active) data.current_a = clamp(Math.round(p.current), ev.min_current, ev.max_current);
    if (car && car.capacity_kwh) {
      data.soc = Math.round(p.soc);
      data.target_soc = Math.round(p.target);
    } else data.kwh = Math.round(p.kwh * 10) / 10;
    this._saving = true;
    this._planError = null;
    this._rerender();
    try {
      await this._hass.callService(ESS_DOMAIN, "ev_charge_plan", { entity_id: this._config.entity, ...data });
      this._plan = null;
    } catch (err) {
      this._planError = (err && err.message) || String(err);
    }
    this._saving = false;
    this._rerender();
  }

  _save(ev) {
    const e = this._edit;
    const car = this._car(ev, e.car);
    if (e.how === "deadline" && this._editDeadline(e) <= Math.max(this._startMs(e), Date.now())) {
      this._error = this._t("ev_r_before_start");
      this._rerender();
      return;
    }
    const data = {
      mode: e.how === "solar" ? "solar" : e.how === "deadline" ? "deadline" : "fixed",
      current_a: this._editAmps(ev, e),
      car: e.car || null,
      enabled: e.enabled,
    };
    if (e.how === "deadline") data.deadline = new Date(this._editDeadline(e)).toISOString();
    if (e.id) data.id = e.id;
    if (!e.running) data.start = new Date(this._startMs(e)).toISOString();
    if (car && car.capacity_kwh) {
      data.start_soc = Math.round(e.start_soc);
      data.target_soc = Math.round(e.target_soc);
    } else {
      data.kwh = Math.round(e.kwh * 10) / 10;
      data.start_soc = null;
      data.target_soc = null;
    }
    this._call("ev_session_save", data, true);
  }

  async _call(service, data, close) {
    this._saving = true;
    this._error = null;
    try {
      await this._hass.callService(ESS_DOMAIN, service, { entity_id: this._config.entity, ...data });
      if (close) this._edit = null;
    } catch (err) {
      this._error = (err && err.message) || String(err);
    }
    this._saving = false;
    this._rerender();
  }
}

// -- Heat pump card (as of 2026.10.16) --------------------------------------------------
// The heat pump model (the Status sensor's `heat_pump` attribute): the state
// and the total of the coming days at the top, a notice when the model
// learns, rests for the summer, corrects or isn't used, and three tabs -
// Forecast (per day, with the 6-week average as a marker), Signature (the
// days measured against the outdoor temperature with the model's line) and
// Memory (per temperature class: measured against the model).
const HP_DEFAULTS = {
  title: "",
  hp_color: [255, 154, 92],
};
const HP_COLOR_KEYS = ["hp_color"];
const HP_SCHEMA = (t) => [
  { name: "title", selector: { text: {} } },
  {
    type: "expandable",
    flatten: true,
    name: "colours",
    title: t("ed_colours"),
    schema: [{ type: "grid", name: "", schema: HP_COLOR_KEYS.map((name) => ({ name, selector: { color_rgb: {} } })) }],
  },
];
const HP_FC_COLOR = "#6fa8dc";
const HP_WARN = "#e5534b";
const HP_CSS = `
  .hp-banner { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; border-radius: 10px; background: rgba(127,127,127,.14); font-size: 13px; line-height: 18px; }
  .hp-banner.warn { background: color-mix(in srgb, ${HP_WARN} 16%, transparent); outline: 1px solid ${HP_WARN}; }
  .hp-banner.sun { background: color-mix(in srgb, #f2c94c 12%, transparent); }
  .hp-banner.house { background: color-mix(in srgb, var(--hp) 14%, transparent); }
  .hp-chip { font-size: 12px; padding: 2px 8px; border-radius: 10px; font-weight: 600; flex-shrink: 0; }
  .hp-progress { position: relative; height: 8px; border-radius: 4px; background: rgba(127,127,127,.3); margin-top: 6px; }
  .hp-progress i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 4px; background: var(--hp); }
  .hp-tabs { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 4px; padding: 4px; border-radius: 22px; background: rgba(127,127,127,.14); }
  .hp-tabs button { min-height: 40px; border-radius: 18px; border: 0; background: transparent; color: inherit; font: inherit; font-size: 14px; cursor: pointer; }
  .hp-tabs button[aria-selected="true"] { background: var(--hp); color: #2a160a; font-weight: 600; }
  .hp-days { display: flex; flex-direction: column; gap: 6px; }
  .hp-day { display: flex; flex-direction: column; gap: 6px; padding: 9px 12px; border-radius: 10px; background: rgba(127,127,127,.12); }
  .hp-line { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 14px; font-weight: 600; }
  .hp-meta { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
  .hp-bar { position: relative; height: 8px; border-radius: 4px; background: rgba(127,127,127,.3); }
  .hp-bar i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 4px; }
  .hp-bar b { position: absolute; top: -3px; bottom: -3px; width: 3px; border-radius: 2px; background: var(--primary-text-color, #e1e1e1); opacity: .85; }
  .hp-tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .hp-tile { background: rgba(127,127,127,.14); border-radius: 10px; padding: 9px 10px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .hp-tile span:first-child { font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
  .hp-tile span:nth-child(2) { font-size: 16px; font-weight: 600; }
  .hp-tile span:nth-child(3) { font-size: 11px; color: var(--secondary-text-color, #8f8f8f); }
  .hp-table { display: flex; flex-direction: column; gap: 4px; }
  .hp-row { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, .7fr) minmax(0, 1fr) minmax(0, .9fr) minmax(0, 1.3fr); gap: 0 8px; align-items: center; padding: 7px 8px; border-radius: 8px; font-size: 13px; background: rgba(127,127,127,.12); }
  .hp-row.head { background: transparent; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); padding-top: 0; padding-bottom: 0; }
  .hp-row span:nth-child(2), .hp-row span:nth-child(3), .hp-row span:nth-child(4) { text-align: right; }
  .hp-row span:nth-child(5) { font-size: 12px; color: var(--secondary-text-color, #a0a0a0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .hp-legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
  .hp-legend span { display: flex; align-items: center; gap: 6px; }
  .hp-ctl { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 10px; background: rgba(127,127,127,.12); font-size: 13px; }
  .hp-ctl .val { display: flex; align-items: center; gap: 8px; font-weight: 600; }
  .hp-ctl button, .hp-toggle { min-width: 36px; min-height: 36px; border-radius: 18px; border: 0; background: rgba(127,127,127,.22); color: inherit; font: inherit; font-size: 18px; cursor: pointer; }
  .hp-toggle { padding: 0 16px; font-size: 14px; font-weight: 600; }
  .hp-toggle[aria-pressed="true"] { background: var(--hp); color: #2a160a; }
  .hp-note { font-size: 12px; line-height: 17px; color: var(--secondary-text-color, #8f8f8f); }
  @container (max-width: 400px) { .hp-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
`;
const COMPASS = { nl: ["N", "NO", "O", "ZO", "Z", "ZW", "W", "NW"], en: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] };

class EssManagerHeatPumpCard extends EssChartCard {
  static get info() {
    return {
      name: "ESS Manager - Heat pump",
      description: "The heat pump forecast from the weather: the coming days, the energy signature and what the model has learned.",
      schema: HP_SCHEMA,
      defaults: HP_DEFAULTS,
      labels: { title: "ed_title", hp_color: "ed_hp_color" },
    };
  }

  getCardSize() {
    return 7;
  }

  _num(v, d) {
    return formats(this._hass).num(v, d);
  }

  _kwh(v) {
    return `${this._num(Number(v) || 0, 1)} kWh`;
  }

  _dayLabel(iso, i) {
    const ms = Date.parse(`${iso}T12:00:00`);
    const label = formats(this._hass).dayLabel(ms);
    return i === 0 ? `${label} (${this._t("today")})` : label;
  }

  _compass(deg) {
    if (deg == null) return "";
    const names = COMPASS[hassLang(this._hass).slice(0, 2)] || COMPASS.en;
    return names[Math.round(((Number(deg) % 360) + 360) % 360 / 45) % 8];
  }

  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const st = this._hass.states[this._config.entity];
    const opt = colorOptions(this._config, HP_DEFAULTS, HP_COLOR_KEYS);
    const css = BASE_CSS + HP_CSS + `ha-card { --hp: ${opt.hp_color}; }`;
    if (!isStatusSensor(st)) {
      setCardContent(this, css, notStatusMessage(this._hass, this._config.entity, st));
      return;
    }
    const hp = st.attributes.heat_pump;
    if (!hp) {
      setCardContent(this, css, `<div style="padding:4px">${esc(this._t("hp_off"))}</div>`);
      return;
    }
    const tab = this._tab || "forecast";
    const used = !!hp.used;
    const corr = Number(hp.correction) || 1;
    const correcting = used && Math.abs(corr - 1) >= 0.05;
    const subs = {
      active: this._t("hp_sub_active")(hp.heating_days || 0),
      learning: this._t("hp_sub_learning"),
      summer: this._t("hp_sub_summer"),
      fallback: this._t("hp_sub_fallback"),
    };
    let sub = subs[hp.state] || "";
    if (correcting) sub = this._t("hp_sub_correction")(this._pct(corr));
    const total = used ? hp.total_kwh : hp.average_total_kwh;
    const title = this._config.title || this._t("hp_title");
    let html = `
      <div class="top">
        <div style="display:flex;flex-direction:column;gap:2px;flex-grow:1;min-width:0">
          <div class="title">${esc(title)}</div>
          <div class="dim" style="font-size:13px">${esc(sub)}</div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px">
          <div style="font-size:20px;font-weight:600;white-space:nowrap">${total != null ? esc(this._kwh(total)) : "\u2014"}</div>
          <div class="dim" style="font-size:12px">${esc(this._t(used ? "hp_next_days" : "hp_average"))}</div>
        </div>
      </div>`;
    html += this._banner(hp, correcting, corr);
    html += this._houseBanner(hp);
    html += `
      <div class="hp-tabs" role="tablist" aria-label="${esc(this._t("hp_view"))}">
        <button type="button" role="tab" data-tab="forecast" aria-selected="${tab === "forecast"}">${esc(this._t("hp_tab_forecast"))}</button>
        <button type="button" role="tab" data-tab="signature" aria-selected="${tab === "signature"}">${esc(this._t("hp_tab_signature"))}</button>
        <button type="button" role="tab" data-tab="memory" aria-selected="${tab === "memory"}">${esc(this._t("hp_tab_memory"))}</button>
        ${hp.house_model ? `<button type="button" role="tab" data-tab="indoor" aria-selected="${tab === "indoor"}">${esc(this._t("hp_tab_indoor"))}</button>` : ""}
        ${hp.floor ? `<button type="button" role="tab" data-tab="floor" aria-selected="${tab === "floor"}">${esc(this._t("hp_tab_floor"))}</button>` : ""}
      </div>`;
    if (tab === "signature") html += this._signature(hp, opt);
    else if (tab === "memory") html += this._memory(hp);
    else if (tab === "indoor" && hp.house_model) html += this._indoor(hp, opt);
    else if (tab === "floor" && hp.floor) html += this._floor(hp.floor, opt);
    else html += this._forecast(hp, opt);
    if (setCardContent(this, css, html)) {
      this.shadowRoot.querySelectorAll("[data-tab]").forEach((el) =>
        el.addEventListener("click", () => {
          this._tab = el.getAttribute("data-tab");
          this._essInner = null;
          this._render();
        })
      );
      // steering controls (2026.10.17)
      this.shadowRoot.querySelectorAll("[data-step]").forEach((el) =>
        el.addEventListener("click", () => {
          const id = el.getAttribute("data-entity");
          const st = this._hass.states[id];
          if (!st) return;
          const step = Number(st.attributes.step) || 0.5;
          let v = Number(st.state) + Number(el.getAttribute("data-step")) * step;
          v = Math.min(Number(st.attributes.max ?? v), Math.max(Number(st.attributes.min ?? v), v));
          this._hass.callService("number", "set_value", { entity_id: id, value: Math.round(v * 10) / 10 });
        })
      );
      this.shadowRoot.querySelectorAll("[data-toggle]").forEach((el) =>
        el.addEventListener("click", () => {
          this._hass.callService("switch", "toggle", { entity_id: el.getAttribute("data-toggle") });
        })
      );
      // floor control's stage (2026.10.23)
      this.shadowRoot.querySelectorAll("[data-select]").forEach((el) =>
        el.addEventListener("click", () => {
          this._hass.callService("select", "select_option", { entity_id: el.getAttribute("data-select"), option: el.getAttribute("data-option") });
        })
      );
    }
  }

  _floor(fl, opt) {
    // floor control (2026.10.23): stage, what it waits for, the floor's figures, heat per hour
    const f = formats(this._hass);
    const n = fl.now || {};
    const m = fl.model || {};
    const stage = fl.stage || "watch";
    const why = this._t("fl_r_" + (n.reason || "idle"));
    let html = `<div class="hp-banner${stage !== "watch" ? " house" : ""}">${icon("home", "var(--hp)", 18)}<div><b>${esc(this._t("fl_stage_" + stage))}</b>`;
    if (stage !== "cooling") html += `<br>${esc(stage === "full" ? this._t("fl_is")(!!n.demand_on, why) : this._t("fl_would")(!!n.would_heat, why))}`;
    html += "</div></div>";
    const selState = fl.select ? this._hass.states[fl.select] : null;
    const mode = selState ? selState.state : fl.mode;
    if (selState) {
      html += `<div style="display:flex;align-items:center;justify-content:space-between;gap:8px"><b>${esc(this._t("fl_mode"))}</b></div>
        <div class="hp-tabs" role="group">${["watch", "setpoint", "full"].map((k) => `<button type="button" data-select="${esc(fl.select)}" data-option="${k}" aria-selected="${mode === k}">${esc(this._t("fl_mode_" + k))}</button>`).join("")}</div>`;
    }
    // the highest return setpoint floor control may write (2026.10.38)
    const maxSt = fl.max_return ? this._hass.states[fl.max_return] : null;
    if (maxSt) {
      html += `<div class="hp-ctl"><span>${esc(this._t("fl_max_return"))}</span><span class="val"><button type="button" data-step="-1" data-entity="${esc(fl.max_return)}" aria-label="-">\u2212</button><span style="min-width:56px;text-align:center">${esc(this._num(Number(maxSt.state), 1))} \u00b0C</span><button type="button" data-step="1" data-entity="${esc(fl.max_return)}" aria-label="+">+</button></span></div>`;
    }
    const waits = [];
    for (const w of fl.waiting || []) {
      if (w === "inputs") waits.push(this._t("fl_wait_inputs"));
      else if (w === "emission") waits.push((m.n || 0) >= (fl.min_hours || 30) && m.err != null ? this._t("fl_wait_emission_err")(Math.round(m.err * 100)) : this._t("fl_wait_emission")(m.n || 0, fl.min_hours || 30));
      else if (w === "response") waits.push(this._t("fl_wait_response")((fl.response || {}).n || 0, (fl.response || {}).min_hours || 24));
      else if (w === "house") waits.push(this._t("fl_wait_house"));
      else if (w === "thermostat_off") waits.push(this._t("fl_wait_thermostat_off"));
    }
    if (waits.length && mode !== stage) html += `<div class="hp-note">${esc(this._t("fl_waits"))}: ${waits.map(esc).join(" \u00b7 ")}</div>`;

    // the chart: heat per hour (last 24 h measured, next 12 h planned) and the return setpoint
    const recent = fl.recent || [];
    const next = fl.next || [];
    if (recent.length || next.length) {
      const w = this._chartWidth();
      const h = 200;
      const left = 30, right = 34, top = 10, bottom = 24;
      const hours = recent.map((r) => r.h * 1000).concat(next.map((r) => r.h * 1000));
      const xMin = Math.min(...hours), xMax = Math.max(...hours) + 3600000;
      const X = (t) => left + ((t - xMin) / Math.max(xMax - xMin, 1)) * (w - left - right);
      const qTop = Math.max(1, ...recent.map((r) => Math.max(r.th_kwh || 0, r.plan_kwh || 0)), ...next.map((r) => r.kwh || 0));
      const qMax = qTop * 1.1;
      const QY = (q) => h - bottom - (q / qMax) * (h - top - bottom);
      const sps = recent.map((r) => r.sp).concat(next.map((r) => r.sp)).filter((v) => v != null);
      const sMin = sps.length ? Math.floor(Math.min(...sps) - 1) : 20;
      const sMax = sps.length ? Math.ceil(Math.max(...sps) + 1) : 30;
      const SY = (v) => top + (1 - (v - sMin) / Math.max(sMax - sMin, 0.1)) * (h - top - bottom);
      const bw = Math.max(2, (w - left - right) / Math.max((xMax - xMin) / 3600000, 1));
      let svg = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="display:block">`;
      for (let i = 0; i <= 2; i++) {
        const q = (qTop * i) / 2;
        svg += `<line x1="${left}" y1="${QY(q).toFixed(1)}" x2="${w - right}" y2="${QY(q).toFixed(1)}" stroke="rgba(127,127,127,.18)"></line><text x="${left - 5}" y="${(QY(q) + 4).toFixed(1)}" text-anchor="end">${this._num(q, 1)}</text>`;
      }
      for (const r of recent) {
        const x = X(r.h * 1000) + 1;
        if (r.plan_kwh) svg += `<rect x="${x.toFixed(1)}" y="${QY(r.plan_kwh).toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${(h - bottom - QY(r.plan_kwh)).toFixed(1)}" fill="none" stroke="rgba(170,170,170,.9)" stroke-dasharray="3 2"></rect>`;
        if (r.th_kwh) svg += `<rect x="${(x + bw * 0.2).toFixed(1)}" y="${QY(r.th_kwh).toFixed(1)}" width="${Math.max(bw * 0.6 - 2, 1).toFixed(1)}" height="${(h - bottom - QY(r.th_kwh)).toFixed(1)}" fill="${opt.hp_color}" fill-opacity=".85"><title>${esc(f.time(r.h * 1000))}: ${esc(this._num(r.th_kwh, 2))} / ${esc(this._num(r.plan_kwh || 0, 2))} kWh</title></rect>`;
      }
      for (const r of next) {
        if (!r.kwh) continue;
        svg += `<rect x="${(X(r.h * 1000) + 1).toFixed(1)}" y="${QY(r.kwh).toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${(h - bottom - QY(r.kwh)).toFixed(1)}" fill="${opt.hp_color}" fill-opacity=".3"><title>${esc(f.time(r.h * 1000))}: ${esc(this._num(r.kwh, 2))} kWh</title></rect>`;
      }
      const line = (pts) => pts.map(([t, v], i) => `${i ? "L" : "M"} ${X(t).toFixed(1)} ${SY(v).toFixed(1)}`).join(" ");
      const spPast = recent.filter((r) => r.sp != null).map((r) => [r.h * 1000 + 1800000, r.sp]);
      const spNext = next.filter((r) => r.sp != null).map((r) => [r.h * 1000 + 1800000, r.sp]);
      if (spPast.length > 1) svg += `<path d="${line(spPast)}" fill="none" stroke="var(--primary-text-color,#f0f0f0)" stroke-width="1.6"></path>`;
      if (spNext.length > 1) svg += `<path d="${line(spNext)}" fill="none" stroke="var(--primary-text-color,#f0f0f0)" stroke-width="1.6" stroke-dasharray="4 4"></path>`;
      svg += `<text x="${w - right + 4}" y="${(SY(sMax) + 4).toFixed(1)}" text-anchor="start">${sMax}\u00b0</text><text x="${w - right + 4}" y="${(SY(sMin) + 4).toFixed(1)}" text-anchor="start">${sMin}\u00b0</text>`;
      if (next.length) svg += `<line x1="${X(next[0].h * 1000).toFixed(1)}" y1="${top}" x2="${X(next[0].h * 1000).toFixed(1)}" y2="${h - bottom}" stroke="rgba(127,127,127,.6)"></line>`;
      for (let t = Math.ceil(xMin / 21600000) * 21600000; t <= xMax; t += 21600000) svg += `<text x="${X(t).toFixed(1)}" y="${h - 6}" text-anchor="middle">${esc(f.time(t))}</text>`;
      svg += "</svg>";
      html += `<div class="chart" style="height:${h}px">${svg}</div>`;
      html += `<div class="hp-legend"><span><i style="display:inline-block;width:10px;height:8px;background:${opt.hp_color};opacity:.85"></i>${esc(this._t("fl_delivered"))}</span><span><i style="display:inline-block;width:10px;height:8px;border:1px dashed #aaa"></i>${esc(this._t("fl_planned"))}</span><span><i style="display:inline-block;width:14px;height:2px;background:var(--primary-text-color,#f0f0f0)"></i>${esc(this._t("fl_sp_actual"))}</span><span><i style="display:inline-block;width:14px;height:0;border-top:2px dashed var(--primary-text-color,#f0f0f0)"></i>${esc(this._t("fl_sp_plan"))}</span></div>`;
    }
    const tiles = [];
    if (m.u) tiles.push([this._t("fl_u_t"), this._num(m.u, 2), this._t("fl_u_unit")]);
    if (m.p_min != null) tiles.push([this._t("fl_p_t"), `${this._num(m.p_min, 1)} - ${this._num(m.p_max, 1)}`, this._t("fl_p_unit")]);
    if (m.delta != null) tiles.push([this._t("fl_delta_t"), `${this._num(m.delta, 1)} \u00b0C`, ""]);
    tiles.push([this._t("fl_sp_t"), `${n.sp_planned != null ? this._num(n.sp_planned, 1) : "\u2014"} / ${n.sp != null ? this._num(n.sp, 1) : "\u2014"} \u00b0C`, this._t("fl_sp_unit")]);
    tiles.push([this._t("fl_debt_t"), `${this._num(Math.max(n.debt_kwh || 0, 0), 1)} kWh`, ""]);
    if (n.t_slab != null) tiles.push([this._t("fl_slab_t"), `${this._num(n.t_slab, 1)} \u00b0C`, this._t("fl_slab_unit")]);
    html += `<div class="hp-tiles">${tiles.map(([a, b, c]) => `<div class="hp-tile"><span>${esc(a)}</span><span>${esc(b)}</span><span>${esc(c)}</span></div>`).join("")}</div>`;
    if (m.n && m.err != null) html += `<div class="hp-note">${esc(this._t("fl_learned")(m.n, Math.round(m.err * 100)))}</div>`;
    html += `<div class="hp-note">${esc(this._t("fl_note"))}</div>`;
    return html;
  }

  _pct(f) {
    const p = Math.round((f - 1) * 100);
    return `${p > 0 ? "+" : ""}${p} %`;
  }

  _banner(hp, correcting, corr) {
    if (hp.state === "learning") {
      const need = hp.heating_days_needed || 21;
      const have = Math.min(hp.heating_days || 0, need);
      return `<div class="hp-banner" style="flex-direction:column;align-items:stretch;gap:2px">
        <div style="display:flex;justify-content:space-between"><span class="dim">${esc(this._t("hp_heating_days"))}</span><b>${have} ${esc(this._t("of"))} ${need}</b></div>
        <div class="hp-progress"><i style="width:${Math.round((have / need) * 100)}%"></i></div>
        ${hp.heating_classes_needed ? `<div style="display:flex;justify-content:space-between;margin-top:6px"><span class="dim">${esc(this._t("hp_heating_classes"))}</span><b>${Math.min(hp.heating_classes || 0, hp.heating_classes_needed)} ${esc(this._t("of"))} ${hp.heating_classes_needed}</b></div>
        <div class="hp-progress"><i style="width:${Math.round((Math.min(hp.heating_classes || 0, hp.heating_classes_needed) / hp.heating_classes_needed) * 100)}%"></i></div>` : ""}
        <div style="margin-top:4px">${esc(this._t("hp_learning_text"))}</div>
      </div>`;
    }
    if (hp.state === "summer") {
      const base = hp.model && hp.model.base_kwh_day;
      return `<div class="hp-banner sun">${icon("sun", "#f2c94c", 18)}<div>${esc(this._t("hp_summer_text")(base != null ? this._kwh(base) : "\u2014"))}</div></div>`;
    }
    if (hp.state === "fallback") {
      return `<div class="hp-banner">${icon("cog", "var(--secondary-text-color,#a0a0a0)", 18)}<div>${esc(this._t(hp.weather_days ? "hp_fallback_fit" : "hp_fallback_weather"))}</div></div>`;
    }
    if (correcting) {
      const sp = hp.setpoint_change_c;
      const extra = sp != null ? " " + this._t("hp_setpoint_change")(`${sp > 0 ? "+" : ""}${this._num(sp, 1)} \u00b0C`) : "";
      return `<div class="hp-banner warn"><span class="hp-chip" style="background:${HP_WARN};color:#fff">${esc(this._pct(corr))}</span><div>${esc(this._t(corr > 1 ? "hp_corr_more" : "hp_corr_less"))}${esc(extra)}</div></div>`;
    }
    return "";
  }

  _when(iso) {
    const ms = Date.parse(iso);
    const f = formats(this._hass);
    const sameDay = new Date(ms).toDateString() === new Date().toDateString();
    return sameDay ? f.time(ms) : `${f.dayLabel(ms)} ${f.time(ms)}`;
  }

  _houseBanner(hp) {
    // as of 2026.10.16 (also): the house's own heat
    const h = hp.house;
    if (!hp.used || !h || !h.kind || h.kwh == null) return "";
    const d = `${this._num(Math.abs(h.difference_c), 1)} \u00b0C`;
    const kwh = this._kwh(Math.abs(h.kwh));
    const ref = this._t(h.reference === "usual" ? "hp_ref_usual" : "hp_ref_wanted");
    if (h.kind === "deficit") {
      return `<div class="hp-banner">${icon("up", HP_WARN, 18)}<div>${esc(this._t("hp_house_cold")(d, ref, kwh))}</div></div>`;
    }
    const text = h.until && h.hours < 72 ? this._t("hp_house_warm")(d, ref, this._when(h.until), kwh) : this._t("hp_house_warm_long")(d, ref, kwh);
    return `<div class="hp-banner house">${icon("home", "var(--hp)", 18)}<div>${esc(text)}</div></div>`;
  }

  _indoor(hp, opt) {
    // the house hour by hour (2026.10.17): measured, forecast, the target
    const hm = hp.house_model;
    const stageText = this._t("hp_stage_" + (hm.stage || "learning"));
    const rev = hm.review || {};
    let html = `<div class="hp-banner${hm.stage === "used" || hm.stage === "steering" ? " house" : ""}">${icon("home", "var(--hp)", 18)}<div><b>${esc(stageText)}</b>`;
    if (rev.hour_error_kwh != null) {
      html += `<br>${esc(this._t("hp_review")(rev.days, this._num(rev.hour_error_kwh, 2), this._num(rev.pattern_error_kwh, 2), this._num(rev.temp_error_c, 1)))}`;
      // the drift guard (2026.11.12)
      const rc = rev.recent;
      if (rc && rc.drift) html += `<br>${esc(this._t("hp_review_drift")(rc.days, this._num(rc.hour_error_kwh, 2), this._num(rc.pattern_error_kwh, 2)))}`;
    } else if (hm.stage !== "learning") {
      html += `<br>${esc(this._t("hp_review_wait")(rev.days || 0))}`;
    }
    html += "</div></div>";
    const fc = hm.forecast;
    if (fc && fc.temps && fc.temps.length > 1) {
      const w = this._chartWidth();
      const h = 220;
      const left = 34, right = 30, top = 10, bottom = 24;
      const t0 = fc.start * 1000;
      const meas = (hm.measured || []).map(([e, v]) => [e * 1000, v]);
      // the heating electricity measured per hour (2026.10.23)
      const qMeas = (hm.measured_kwh || []).map(([e, v]) => [e * 1000, Number(v) || 0]).filter(([t]) => t < t0);
      const fpts = fc.temps.map((v, i) => [t0 + i * 3600000, v]);
      const tg = (fc.target || []).map((v, i) => [t0 + i * 3600000, v]);
      const xs = meas.map((p) => p[0]).concat(fpts.map((p) => p[0]), qMeas.map((p) => p[0]));
      const xMin = Math.min(...xs), xMax = Math.max(...xs);
      const vals = meas.map((p) => p[1]).concat(fpts.map((p) => p[1]), tg.map((p) => p[1]));
      const yMin = Math.floor(Math.min(...vals) - 0.5), yMax = Math.ceil(Math.max(...vals) + 0.5);
      const qMax = Math.max(1, ...(fc.kwh || []), ...qMeas.map((p) => p[1]));
      const X = (t) => left + ((t - xMin) / Math.max(xMax - xMin, 1)) * (w - left - right);
      const Y = (v) => top + (1 - (v - yMin) / Math.max(yMax - yMin, 0.1)) * (h - top - bottom);
      const QY = (q) => h - bottom - (q / qMax) * (h - top - bottom) * 0.35;
      let svg = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(this._t("hp_tab_indoor"))}" style="display:block">`;
      for (let v = yMin; v <= yMax; v += 1) {
        svg += `<line x1="${left}" y1="${Y(v).toFixed(1)}" x2="${w - right}" y2="${Y(v).toFixed(1)}" stroke="rgba(127,127,127,.18)"></line>`;
        svg += `<text x="${left - 6}" y="${(Y(v) + 4).toFixed(1)}" text-anchor="end">${v}</text>`;
      }
      const bw = Math.max(1, (w - left - right) / Math.max((xMax - xMin) / 3600000, 1) - 1);
      (fc.kwh || []).forEach((q, i) => {
        const x = X(t0 + i * 3600000);
        svg += `<rect x="${x.toFixed(1)}" y="${QY(q).toFixed(1)}" width="${bw.toFixed(1)}" height="${(h - bottom - QY(q)).toFixed(1)}" fill="${opt.hp_color}" fill-opacity=".35"></rect>`;
      });
      for (const [t, q] of qMeas) {
        if (q <= 0) continue;
        svg += `<rect x="${X(t).toFixed(1)}" y="${QY(q).toFixed(1)}" width="${bw.toFixed(1)}" height="${(h - bottom - QY(q)).toFixed(1)}" fill="${opt.hp_color}" fill-opacity=".85"><title>${esc(formats(this._hass).time(t))}: ${esc(this._num(q, 2))} kWh</title></rect>`;
      }
      svg += `<text x="${w - right + 4}" y="${(h - bottom).toFixed(1)}" text-anchor="start">0</text><text x="${w - right + 4}" y="${(QY(qMax) + 4).toFixed(1)}" text-anchor="start">${this._num(qMax, 1)}</text>`;
      const path = (pts) => pts.map(([t, v], i) => `${i ? "L" : "M"} ${X(t).toFixed(1)} ${Y(v).toFixed(1)}`).join(" ");
      if (tg.length) svg += `<path d="${path(tg)}" fill="none" stroke="rgba(160,160,160,.9)" stroke-width="1.5" stroke-dasharray="4 4"></path>`;
      if (meas.length > 1) svg += `<path d="${path(meas)}" fill="none" stroke="${opt.hp_color}" stroke-width="2"></path>`;
      svg += `<path d="${path(fpts)}" fill="none" stroke="var(--primary-text-color,#f0f0f0)" stroke-width="2"></path>`;
      svg += `<line x1="${X(t0).toFixed(1)}" y1="${top}" x2="${X(t0).toFixed(1)}" y2="${h - bottom}" stroke="rgba(127,127,127,.6)"></line>`;
      const f = formats(this._hass);
      for (let t = Math.ceil(xMin / 21600000) * 21600000; t <= xMax; t += 21600000) {
        svg += `<text x="${X(t).toFixed(1)}" y="${h - 6}" text-anchor="middle">${esc(f.time(t))}</text>`;
      }
      svg += "</svg>";
      html += `<div class="chart" style="height:${h}px">${svg}</div>`;
      html += `<div class="hp-legend"><span><i style="display:inline-block;width:14px;height:2px;background:${opt.hp_color}"></i>${esc(this._t("hp_measured_in"))}</span><span><i style="display:inline-block;width:14px;height:2px;background:var(--primary-text-color,#f0f0f0)"></i>${esc(this._t("hp_expected_in"))}</span><span><i style="display:inline-block;width:14px;height:0;border-top:2px dashed #a0a0a0"></i>${esc(this._t("hp_target_in"))}</span>${qMeas.length ? `<span><i style="display:inline-block;width:10px;height:8px;background:${opt.hp_color};opacity:.85"></i>${esc(this._t("hp_heat_meas"))}</span>` : ""}<span><i style="display:inline-block;width:10px;height:8px;background:${opt.hp_color};opacity:.4"></i>${esc(this._t(qMeas.length ? "hp_heat_exp" : "hp_heat_kwh"))}</span></div>`;
    }
    const plan = hm.plan;
    if (plan && (plan.boost || plan.dip)) {
      const f = formats(this._hass);
      const parts = [];
      if (plan.boost) parts.push(this._t("hp_plan_boost")(f.time(Date.parse(plan.boost.from)), f.time(Date.parse(plan.boost.until))));
      if (plan.dip) parts.push(this._t("hp_plan_dip")(f.time(Date.parse(plan.dip.from)), f.time(Date.parse(plan.dip.until))));
      html += `<div class="hp-banner house">${icon("bolt", "var(--hp)", 18)}<div>${esc(parts.join(" \u00b7 "))} - ${esc(this._t("hp_plan_saving")(formats(this._hass).money ? formats(this._hass).money(plan.saving) : this._num(plan.saving, 2)))}</div></div>`;
    }
    const tiles = [];
    if (hm.cop) tiles.push([this._t("hp_cop_t"), `${this._num(hm.cop.at_7, 1)} / ${this._num(hm.cop.at_minus_2, 1)}`, this._t("hp_cop_unit")]);
    if (hm.model) {
      tiles.push([this._t("hp_floor_t"), `${this._num(hm.model.tau, 0)} h`, this._t("hp_floor_unit")]);
      tiles.push([this._t("hp_heatup_t"), `${this._num(hm.model.g * 10, 2)} \u00b0C`, this._t(hm.model.thermal ? "hp_heatup_unit_th" : "hp_heatup_unit_el")]);
    }
    if (tiles.length) html += `<div class="hp-tiles">${tiles.map(([a, b, c]) => `<div class="hp-tile"><span>${esc(a)}</span><span>${esc(b)}</span><span>${esc(c)}</span></div>`).join("")}</div>`;
    const c = hm.controls;
    if (c && c.switch) {
      const on = this._hass.states[c.switch] && this._hass.states[c.switch].state === "on";
      html += `<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:4px"><b>${esc(this._t("hp_steering"))}</b><button type="button" class="hp-toggle" aria-pressed="${on}" data-toggle="${esc(c.switch)}">${esc(this._t(on ? "hp_on" : "hp_off_short"))}</button></div>`;
      const row = (label, id, unit, digits) => {
        const st = id && this._hass.states[id];
        if (!st) return "";
        return `<div class="hp-ctl"><span>${esc(label)}</span><span class="val"><button type="button" data-step="-1" data-entity="${esc(id)}" aria-label="-">\u2212</button><span style="min-width:56px;text-align:center">${esc(this._num(Number(st.state), digits))} ${esc(unit)}</span><button type="button" data-step="1" data-entity="${esc(id)}" aria-label="+">+</button></span></div>`;
      };
      html += row(this._t("hp_day_t"), c.day, "\u00b0C", 1) + row(this._t("hp_night_t"), c.night, "\u00b0C", 1)
        + row(this._t("hp_day_from_t"), c.day_from, this._t("hp_hour"), 0) + row(this._t("hp_night_from_t"), c.night_from, this._t("hp_hour"), 0)
        + row(this._t("hp_delta_t"), c.delta, "\u00b0C", 1);
      if (on && hm.stage !== "steering") html += `<div class="hp-note">${esc(this._t("hp_steer_wait"))}</div>`;
      if (hm.steer && hm.steer.override_until) html += `<div class="hp-note">${esc(this._t("hp_override")(formats(this._hass).time(hm.steer.override_until * 1000)))}</div>`;
    }
    return html;
  }

  _forecast(hp, opt) {
    const days = hp.days || [];
    const used = !!hp.used;
    const vals = days.map((d) => (used ? d.kwh : d.average_kwh) || 0).concat(days.map((d) => d.average_kwh || 0));
    const max = Math.max(4, ...vals) * 1.1;
    const color = used ? "var(--hp)" : "#8a8a8a";
    let html = '<div class="hp-days">';
    days.forEach((d, i) => {
      const v = used ? d.kwh : d.average_kwh;
      const meta = [];
      if (d.temp_c != null) meta.push(`${this._num(d.temp_c, 1)} \u00b0C`);
      if (d.wind_ms != null) meta.push(`${this._t("hp_wind")} ${this._num(d.wind_ms, 0)} m/s ${this._compass(d.wind_dir)}`.trim());
      if (d.sun_kwh != null) meta.push(`${this._t("hp_sun")} ${this._kwh(d.sun_kwh)}`);
      const bar = v != null ? `<i style="width:${((v / max) * 100).toFixed(1)}%;background:${color}"></i>` : "";
      const mark = used && d.average_kwh != null ? `<b style="left:${((d.average_kwh / max) * 100).toFixed(1)}%"></b>` : "";
      html += `<div class="hp-day">
        <div class="hp-line"><span>${esc(this._dayLabel(d.date, i))}</span><span>${v != null ? esc(this._kwh(v)) : "\u2014"}</span></div>
        ${meta.length ? `<div class="hp-meta">${meta.map((m) => `<span>${esc(m)}</span>`).join("")}</div>` : ""}
        <div class="hp-bar">${bar}${mark}</div>
      </div>`;
    });
    html += "</div>";
    html += `<div class="hp-legend"><span><i style="display:inline-block;width:14px;height:8px;border-radius:2px;background:${color}"></i>${esc(this._t(used ? "hp_model" : "hp_average_learning"))}</span>${used ? `<span><i style="display:inline-block;width:3px;height:12px;background:var(--primary-text-color,#e1e1e1)"></i>${esc(this._t("hp_average"))}</span>` : ""}</div>`;
    if (hp.meter === "none") html += `<div class="hp-note">${esc(this._t("hp_none_note"))}</div>`;
    return html;
  }

  _signature(hp, opt) {
    const m = hp.model;
    const pts = hp.points || [];
    if (!m || !pts.length) return `<div class="hp-note">${esc(this._t("hp_no_model"))}</div>`;
    const w = this._chartWidth();
    const h = 240;
    const left = 34;
    const right = 8;
    const top = 10;
    const bottom = 26;
    const temps = pts.map((p) => p[0]).concat((hp.days || []).filter((d) => d.temp_c != null).map((d) => d.temp_c));
    const tMin = Math.floor(Math.min(...temps) - 1);
    const tMax = Math.ceil(Math.max(...temps) + 1);
    const line = (t) => {
      let v = Math.max(m.base_kwh_day, 0) + m.kwh_per_degree_day * Math.max(0, m.balance_temp_c - t);
      if (m.cooling_temp_c != null && m.cooling_kwh_per_degree_day != null) v += m.cooling_kwh_per_degree_day * Math.max(0, t - m.cooling_temp_c);
      return v;
    };
    const yMax = Math.max(4, ...pts.map((p) => p[1]), line(tMin), line(tMax), ...(hp.days || []).map((d) => d.kwh || 0)) * 1.08;
    const X = (t) => left + ((t - tMin) / (tMax - tMin)) * (w - left - right);
    const Y = (v) => top + (1 - v / yMax) * (h - top - bottom);
    let svg = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(this._t("hp_tab_signature"))}" style="display:block">`;
    const step = yMax > 40 ? 20 : yMax > 16 ? 10 : 5;
    for (let v = 0; v <= yMax; v += step) {
      svg += `<line x1="${left}" y1="${Y(v).toFixed(1)}" x2="${w - right}" y2="${Y(v).toFixed(1)}" stroke="rgba(127,127,127,${v === 0 ? 0.45 : 0.18})"></line>`;
      svg += `<text x="${left - 6}" y="${(Y(v) + 4).toFixed(1)}" text-anchor="end">${v}</text>`;
    }
    const tStep = tMax - tMin > 24 ? 10 : 5;
    for (let t = Math.ceil(tMin / tStep) * tStep; t <= tMax; t += tStep) {
      svg += `<text x="${X(t).toFixed(1)}" y="${h - 10}" text-anchor="middle">${t}</text>`;
    }
    svg += `<line x1="${X(m.balance_temp_c).toFixed(1)}" y1="${top}" x2="${X(m.balance_temp_c).toFixed(1)}" y2="${h - bottom}" stroke="rgba(127,127,127,.5)" stroke-dasharray="4 4"></line>`;
    for (const [t, v, age, out] of pts) {
      if (out) {
        // left out of the fit (2026.10.17): the house coasting, or a meter jump
        svg += `<circle cx="${X(t).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="3" fill="none" stroke="#8a8a8a" stroke-width="1.5"></circle>`;
        continue;
      }
      const o = Math.max(0.2, 1 - (Number(age) || 0) / 365);
      svg += `<circle cx="${X(t).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="3" fill="${opt.hp_color}" fill-opacity="${o.toFixed(2)}"></circle>`;
    }
    // the model at the usual wind and sun (from the integration), else at none
    const lpts = (hp.line && hp.line.length ? hp.line : [[tMin, line(tMin)], [m.balance_temp_c, line(m.balance_temp_c)], [tMax, line(tMax)]])
      .filter(([t]) => t >= tMin && t <= tMax);
    svg += `<path d="${lpts.map(([t, v], i) => `${i ? "L" : "M"} ${X(t).toFixed(1)} ${Y(v).toFixed(1)}`).join(" ")}" fill="none" stroke="var(--primary-text-color,#f0f0f0)" stroke-width="2"></path>`;
    (hp.days || []).forEach((d) => {
      if (d.temp_c == null || d.kwh == null) return;
      svg += `<circle cx="${X(d.temp_c).toFixed(1)}" cy="${Y(d.kwh).toFixed(1)}" r="5.5" fill="var(--ha-card-background,var(--card-background-color,#1c1c1c))" stroke="${HP_FC_COLOR}" stroke-width="2.5"></circle>`;
    });
    svg += `<text x="${w - right}" y="${h}" text-anchor="end">${esc(this._t("hp_axis"))}</text></svg>`;
    const tiles = [
      [this._t("hp_balance"), `${this._num(m.balance_temp_c, 1)} \u00b0C`, m.indoor_ref_c != null ? this._t("hp_at_indoor")(this._num(m.indoor_ref_c, 1)) : ""],
      [this._t("hp_per_degree"), this._kwh(m.kwh_per_degree_day), this._t("hp_per_day")],
      [this._t("hp_base"), this._kwh(m.base_kwh_day), this._t("hp_per_day")],
    ];
    if (m.indoor_ref_c != null) tiles.push([this._t("hp_warmer_t"), `+${this._kwh(m.kwh_per_degree_day)}`, this._t("hp_per_day")]);
    if (m.wind_kwh_per_ms_degree != null) tiles.push([this._t("hp_wind_t"), `${m.wind_kwh_per_ms_degree >= 0 ? "+" : ""}${this._num(m.wind_kwh_per_ms_degree, 3)}`, this._t("hp_wind_unit")]);
    if (m.solar_kwh_per_kwh != null) tiles.push([this._t("hp_sun_t"), this._num(m.solar_kwh_per_kwh, 2), this._t("hp_sun_unit")]);
    if (m.cooling_temp_c != null) tiles.push([this._t("hp_cool_t"), `${this._t("hp_from")} ${this._num(m.cooling_temp_c, 0)} \u00b0C`, `+${this._kwh(m.cooling_kwh_per_degree_day)} ${this._t("hp_per_degree_short")}`]);
    const th = hp.thermal;
    if (th) {
      if (th.kwh_per_degree != null) tiles.push([this._t("hp_hold_t"), this._kwh(th.kwh_per_degree), this._t("hp_hold_unit")]);
      const floor = th.floor_hours > 3 ? ` \u00b7 ${this._t("hp_floor")(th.floor_hours)}` : "";
      tiles.push([this._t("hp_cooling_t"), `${this._num(th.cooling_per_hour * 10, 2)} \u00b0C/h`, `${this._t("hp_cooling_unit")} \u00b7 ${this._t("hp_tau")(this._num(th.time_constant_h, 0))}${floor}`]);
    }
    if (m.mae_14d_kwh != null) tiles.push([this._t("hp_error"), `\u00b1${this._kwh(m.mae_14d_kwh)}`, this._t("hp_per_day")]);
    return `<div style="display:flex;flex-direction:column;gap:10px">
      <div class="chart" style="height:${h}px">${svg}</div>
      <div class="hp-legend"><span><i style="display:inline-block;width:8px;height:8px;border-radius:4px;background:${opt.hp_color}"></i>${esc(this._t("hp_measured_day"))}</span><span><i style="display:inline-block;width:14px;height:2px;background:var(--primary-text-color,#f0f0f0)"></i>${esc(this._t("hp_model"))}</span><span><i style="display:inline-block;width:8px;height:8px;border-radius:6px;border:2px solid ${HP_FC_COLOR}"></i>${esc(this._t("hp_expected"))}</span>${pts.some((p) => p[3]) ? `<span><i style="display:inline-block;width:6px;height:6px;border-radius:5px;border:1.5px solid #8a8a8a"></i>${esc(this._t("hp_left_out"))}</span>` : ""}</div>
      <div class="hp-tiles">${tiles.map(([a, b, c]) => `<div class="hp-tile"><span>${esc(a)}</span><span>${esc(b)}</span>${c ? `<span>${esc(c)}</span>` : ""}</div>`).join("")}</div>
      ${(m.coasting_days || m.no_demand_days || (m.outlier_days || []).length) ? `<div class="hp-note">${esc(this._t("hp_left_out_note")(m.coasting_days || 0, (m.outlier_days || []).length, m.no_demand_days || 0))}</div>` : ""}
      ${!th && hp.house && hp.meter !== "none" ? `<div class="hp-note">${esc(this._t("hp_thermal_learning"))}</div>` : ""}
    </div>`;
  }

  _memory(hp) {
    const rows = hp.classes || [];
    if (!rows.length) return `<div class="hp-note">${esc(this._t("hp_no_model"))}</div>`;
    let dayMonth;
    try {
      dayMonth = new Intl.DateTimeFormat(hassLang(this._hass), { day: "numeric", month: "short" });
    } catch (err) {
      dayMonth = new Intl.DateTimeFormat("en", { day: "numeric", month: "short" });
    }
    const fmtDate = (iso) => dayMonth.format(new Date(`${iso}T12:00:00`));
    let html = `<div class="hp-table"><div class="hp-row head"><span>${esc(this._t("hp_outdoor"))}</span><span>${esc(this._t("hp_days"))}</span><span>${esc(this._t("hp_measured"))}</span><span>${esc(this._t("hp_model"))}</span><span>${esc(this._t("hp_last"))}</span></div>`;
    for (const r of rows) {
      const year = r.last.slice(0, 4);
      const last = `${fmtDate(r.last)}${year !== String(new Date().getFullYear()) ? ` ${year}` : ""}`;
      html += `<div class="hp-row"><span>${this._num(r.from, 1)} ${esc(this._t("hp_to"))} ${this._num(r.to, 1)} \u00b0C</span><span>${r.days}</span><span style="font-weight:600">${this._num(r.measured, 1)}</span><span>${this._num(r.model, 1)}</span><span>${esc(last)}</span></div>`;
    }
    html += "</div>";
    html += `<div class="hp-note">${esc(this._t("hp_memory_note")(hp.journal_days || 0, hp.heating_days || 0))}</div>`;
    return html;
  }
}

// -- Registration -------------------------------------------------------------------
if (!customElements.get("ess-manager-card-editor")) {
  customElements.define("ess-manager-card-editor", EssManagerCardEditor);
}
// -- Forecast check card (2026.10.22) ------------------------------------------------
// How good the usage and solar forecasts were, which usage method is in use
// (backtest), the Safety buffer advice and the "adjust automatically" switch.
const FC_DEFAULTS = {
  title: "",
  fc_color: [255, 138, 76],
  usage_color: [158, 203, 255],
  solar_color: [232, 195, 90],
};
const FC_COLOR_KEYS = ["fc_color", "usage_color", "solar_color"];
const FC_SCHEMA = (t) => [
  { name: "title", selector: { text: {} } },
  {
    type: "expandable",
    flatten: true,
    name: "colours",
    title: t("ed_colours"),
    schema: [{ type: "grid", name: "", schema: FC_COLOR_KEYS.map((name) => ({ name, selector: { color_rgb: {} } })) }],
  },
];
const FC_OK = "#6fcf97";
const FC_CSS = `
  .fc-tabs { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 4px; padding: 4px; border-radius: 22px; background: rgba(127,127,127,.14); }
  .fc-tabs button { min-height: 40px; border-radius: 18px; border: 0; background: transparent; color: inherit; font: inherit; font-size: 14px; cursor: pointer; }
  .fc-tabs button[aria-selected="true"] { background: var(--fc); color: #2a160a; font-weight: 600; }
  .fc-tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .fc-tile, .fc-panel { background: rgba(127,127,127,.14); border-radius: 12px; padding: 10px 12px; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .fc-tile .t { font-size: 13px; color: var(--secondary-text-color, #a0a0a0); display: flex; align-items: center; gap: 6px; }
  .fc-tile .n { font-size: 20px; font-weight: 600; }
  .fc-tile .n small { font-size: 12px; font-weight: 400; color: var(--secondary-text-color, #a0a0a0); }
  .fc-tile .s { font-size: 12px; line-height: 17px; color: var(--secondary-text-color, #a0a0a0); }
  .fc-line { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 14px; }
  .fc-line b { font-weight: 600; text-align: right; }
  .fc-bar { position: relative; height: 10px; border-radius: 5px; background: rgba(127,127,127,.3); margin: 12px 0 24px; }
  .fc-bar i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 5px; background: linear-gradient(90deg, rgba(127,127,127,.4), ${FC_OK}); }
  .fc-mk { position: absolute; top: -5px; width: 2px; height: 20px; background: var(--primary-text-color, #e1e1e1); }
  .fc-mk span { position: absolute; top: 22px; transform: translateX(-50%); font-size: 11px; white-space: nowrap; color: var(--secondary-text-color, #c0c0c0); }
  .fc-mk.adv { background: var(--fc); } .fc-mk.adv span { color: var(--fc); }
  .fc-note { font-size: 12px; line-height: 17px; color: var(--secondary-text-color, #8f8f8f); }
  .fc-ctl { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; margin-top: 6px; }
  .fc-toggle { min-height: 36px; padding: 0 16px; border-radius: 18px; border: 0; background: rgba(127,127,127,.22); color: inherit; font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
  .fc-toggle[aria-pressed="true"] { background: var(--fc); color: #2a160a; }
  .fc-legend { display: flex; gap: 14px; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
  .fc-legend span { display: flex; align-items: center; gap: 5px; }
  .fc-legend i { display: inline-block; width: 11px; height: 9px; border-radius: 2px; }
  .fc-chart svg { display: block; overflow: visible; }
  .fc-chart text { fill: var(--secondary-text-color, #a0a0a0); font-size: 10px; font-family: inherit; }
  .fc-table { display: flex; flex-direction: column; gap: 4px; }
  .fc-row { display: grid; grid-template-columns: minmax(0, 2.2fr) minmax(0, .9fr) minmax(0, .8fr) minmax(0, 1.1fr); gap: 0 8px; align-items: center; padding: 8px 10px; border-radius: 8px; font-size: 13px; background: rgba(127,127,127,.12); }
  .fc-row.head { background: transparent; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); padding-top: 0; padding-bottom: 0; }
  .fc-row span:nth-child(2), .fc-row span:nth-child(3), .fc-row span:nth-child(4) { text-align: right; }
  .fc-row.used { font-weight: 600; }
  .fc-pos { color: var(--fc); } .fc-good { color: ${FC_OK}; }
  @container (max-width: 420px) { .title { font-size: 20px; } .fc-tiles { gap: 6px; } }
`;

class EssManagerForecastCard extends EssChartCard {
  static get info() {
    return {
      name: "ESS Manager - Forecast check",
      description: "How good the usage and solar forecasts were, which usage forecast is in use and the Safety buffer advice (optionally automatic).",
      schema: FC_SCHEMA,
      defaults: FC_DEFAULTS,
      labels: { title: "ed_title", fc_color: "ed_fc_color", usage_color: "ed_usage_color", solar_color: "ed_solar_color" },
    };
  }

  getCardSize() {
    return 7;
  }

  _num(v, d) {
    return formats(this._hass).num(Number(v) || 0, d);
  }

  _bias(p) {
    if (p === null || p === undefined) return "";
    const r = Math.round(Math.abs(p));
    if (r < 2) return `<span class="fc-good">${esc(this._t("fc_ok"))}</span>`;
    const txt = p < 0 ? this._t("fc_low")(r) : this._t("fc_high")(r);
    return `<span class="${r >= 5 ? "fc-pos" : "fc-good"}">${esc(txt)}</span>`;
  }

  _methodName(key, lookback) {
    if (key === "weighted") return this._t("fc_m_weighted");
    if (key === "level") return this._t("fc_m_level")(lookback);
    return this._t("fc_m_average")(lookback);
  }

  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const st = this._hass.states[this._config.entity];
    const opt = colorOptions(this._config, FC_DEFAULTS, FC_COLOR_KEYS);
    const css = BASE_CSS + FC_CSS + `ha-card { --fc: ${opt.fc_color}; }`;
    if (!isStatusSensor(st)) {
      setCardContent(this, css, notStatusMessage(this._hass, this._config.entity, st));
      return;
    }
    const fc = st.attributes.forecast_check;
    const width = this._chartWidth();
    const key = [st, width, this._tab, hassLang(this._hass)];
    if (this._renderKey && key.every((v, i) => v === this._renderKey[i])) return;
    this._renderKey = key;
    const title = this._config.title || this._t("fc_title");
    if (!fc || !fc.ready) {
      setCardContent(this, css, `<div class="top"><div class="title">${esc(title)}</div></div><div class="fc-note">${esc(this._t("fc_waiting"))}</div>`);
      return;
    }
    const tab = this._tab || "overview";
    const u = fc.usage || {};
    const mae = u.chosen_mae != null ? u.chosen_mae : u.mae;
    let html = `
      <div class="top">
        <div style="display:flex;flex-direction:column;gap:2px;flex-grow:1;min-width:0">
          <div class="title">${esc(title)}</div>
          <div class="dim" style="font-size:13px">${esc(this._t("fc_sub")(fc.show_days || 14))}</div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px">
          <div style="font-size:20px;font-weight:600;white-space:nowrap">${mae != null ? `\u00b1${esc(this._num(mae, 1))} kWh` : "\u2014"}</div>
          <div class="dim" style="font-size:12px">${esc(this._t("fc_head_sub"))}</div>
        </div>
      </div>
      <div class="fc-tabs" role="tablist">
        ${["overview", "days", "methods"].map((k) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${tab === k}">${esc(this._t("fc_tab_" + k))}</button>`).join("")}
      </div>`;
    if (tab === "days") html += this._days(fc, opt, width);
    else if (tab === "methods") html += this._methods(fc);
    else html += this._overview(fc, opt);
    if (setCardContent(this, css, html)) {
      this.shadowRoot.querySelectorAll("[data-tab]").forEach((el) =>
        el.addEventListener("click", () => {
          this._tab = el.getAttribute("data-tab");
          this._essInner = null;
          this._renderKey = null;
          this._render();
        })
      );
      this.shadowRoot.querySelectorAll("[data-toggle]").forEach((el) =>
        el.addEventListener("click", () => {
          this._hass.callService("switch", "toggle", { entity_id: el.getAttribute("data-toggle") });
        })
      );
    }
  }

  _overview(fc, opt) {
    const u = fc.usage || {};
    const s = fc.solar || {};
    const b = fc.buffer || {};
    const m = fc.methods || {};
    const unit = `<small>${esc(this._t("fc_per_day"))}</small>`;
    const corrected = m.chosen && m.chosen !== "average" && u.chosen_bias_pct != null
      ? `<br>${esc(this._t("fc_corrected"))} ${this._bias(u.chosen_bias_pct)}` : "";
    const usageTile = `<div class="fc-tile">
        <div class="t">${icon("home", opt.usage_color, 14, 2.2)}${esc(this._t("fc_usage"))}</div>
        <div class="n">${u.actual_avg != null ? esc(this._num(u.actual_avg, 1)) : "\u2014"} ${unit}</div>
        <div class="s">${u.forecast_avg != null ? `${esc(this._t("fc_forecast")(this._num(u.forecast_avg, 1)))} \u00b7 ${this._bias(u.bias_pct)}` : ""}${corrected}</div>
      </div>`;
    let solarSub;
    if (!s.measured) solarSub = esc(this._t("fc_no_solar"));
    else if (!s.days) solarSub = esc(this._t("fc_solar_wait"));
    else solarSub = `${esc(this._t("fc_forecast")(this._num(s.forecast_avg, 1)))} \u00b7 ${this._bias(s.bias_pct)}<br>${esc(this._t("fc_err")(this._num(s.mae, 1)))} \u00b7 ${esc(this._t("fc_days")(s.days, fc.show_days || 14))}`;
    const solarTile = `<div class="fc-tile">
        <div class="t">${icon("sun", opt.solar_color, 14, 2.2)}${esc(this._t("fc_solar"))}</div>
        <div class="n">${s.actual_avg != null ? esc(this._num(s.actual_avg, 1)) : "\u2014"} ${unit}</div>
        <div class="s">${solarSub}</div>
      </div>`;

    // the buffer
    let bufferBody;
    if (b.advice == null) {
      bufferBody = `<div class="fc-note">${esc(this._t("fc_buffer_wait")(b.days || 0, b.min_days || 14))}</div>`;
    } else {
      const top = Math.max(30, b.advice + 5, b.manual + 5);
      const pos = (v) => `${clamp((v / top) * 100, 0, 100).toFixed(1)}%`;
      const close = Math.abs(b.advice - b.manual) / top < 0.12;
      bufferBody = `<div class="fc-bar"><i style="width:${pos(b.advice)}"></i>
          <div class="fc-mk" style="left:${pos(b.manual)}"><span${close ? ' style="transform:translateX(-100%)"' : ""}>${esc(this._num(b.manual, 0))} % (${esc(this._t("fc_now"))}) \u00b7 ${b.coverage_manual} %</span></div>
          <div class="fc-mk adv" style="left:${pos(b.advice)}"><span${close ? ' style="transform:none"' : ""}>${esc(this._num(b.advice, 0))} % \u00b7 ${b.coverage_advice} %</span></div>
        </div>
        <div class="fc-note">${esc(this._t("fc_buffer_text")(this._num(b.manual, 0), b.coverage_manual, this._num(b.advice, 0), b.coverage_advice, b.days))}</div>`;
    }
    let autoText;
    if (!b.auto) autoText = this._t("fc_auto_off")(this._num(b.manual, 0));
    else if (!b.auto_active) autoText = this._t("fc_auto_wait")(this._num(b.manual, 0));
    else autoText = this._t("fc_auto_on")(this._num(b.effective, 0), this._num(b.manual, 0));
    const toggle = b.switch && this._hass.states[b.switch]
      ? `<button type="button" class="fc-toggle" data-toggle="${esc(b.switch)}" aria-pressed="${!!b.auto}">${esc(this._t("fc_auto"))}</button>` : "";
    const buffer = `<div class="fc-panel">
        <div class="fc-line"><span class="dim">${esc(this._t("fc_buffer"))}</span><b>${b.advice != null ? esc(this._t("fc_advice")(this._num(b.advice, 0))) : "\u2014"}</b></div>
        ${bufferBody}
        <div class="fc-ctl"><div class="fc-note">${esc(autoText)}</div>${toggle}</div>
      </div>`;

    // the usage method
    const lookback = m.lookback_weeks || 6;
    let methodText;
    if ((m.test_days || 0) < (m.min_test_days || 14)) methodText = this._t("fc_learning")(m.test_days || 0, m.min_test_days || 14);
    else if (m.chosen === "level") methodText = this._t("fc_level_text")(m.level != null ? `${m.level >= 1 ? "+" : ""}${Math.round((m.level - 1) * 100)} %` : "\u2014", m.test_days);
    else if (m.chosen === "weighted") methodText = this._t("fc_weighted_text")(m.test_days);
    else methodText = this._t("fc_avg_text")(m.test_days);
    const excl = (u.excluded || []).map((k) => this._t(k === "ev" ? "fc_ev" : "fc_hp"));
    const exclText = excl.length ? ` ${this._t("fc_excl")(excl.join(` ${this._t("fc_and")} `))}` : "";
    const method = `<div class="fc-panel">
        <div class="fc-line"><span class="dim">${esc(this._t("fc_method"))}</span><b class="${m.chosen && m.chosen !== "average" ? "fc-good" : ""}">${esc(this._methodName(m.chosen, lookback))}</b></div>
        <div class="fc-note">${esc(methodText + exclText)}</div>
      </div>`;
    return `<div class="fc-tiles">${usageTile}${solarTile}</div>${buffer}${method}`;
  }

  _bars(rows, color, width) {
    const H = 110;
    const n = Math.max(rows.length, 1);
    const bw = width / n;
    let max = 1;
    for (const r of rows) max = Math.max(max, Number(r.forecast) || 0, Number(r.actual) || 0);
    max *= 1.08;
    const y = (v) => H - (v / max) * (H - 4);
    let svg = "";
    rows.forEach((r, i) => {
      const x = i * bw;
      if (r.forecast == null || r.actual == null) {
        svg += `<rect x="${r1(x + bw * 0.18)}" y="${H - 5}" width="${r1(bw * 0.64)}" height="5" rx="2" fill="rgba(127,127,127,.35)"/>`;
      } else {
        svg += `<rect x="${r1(x + bw * 0.12)}" y="${r1(y(r.forecast))}" width="${r1(bw * 0.36)}" height="${r1(H - y(r.forecast))}" rx="3" fill="none" stroke="rgba(160,160,160,.9)" stroke-width="1.3" stroke-dasharray="3 2"/>`;
        svg += `<rect x="${r1(x + bw * 0.52)}" y="${r1(y(r.actual))}" width="${r1(bw * 0.36)}" height="${r1(H - y(r.actual))}" rx="3" fill="${color}"><title>${esc(r.d)}: ${esc(this._num(r.forecast, 1))} / ${esc(this._num(r.actual, 1))} kWh</title></rect>`;
      }
      const label = formats(this._hass).weekday(Date.parse(`${r.d}T12:00:00`));
      svg += `<text x="${r1(x + bw / 2)}" y="${H + 13}" text-anchor="middle">${esc(label)}</text>`;
    });
    return `<div class="fc-chart"><svg width="${width}" height="${H + 16}" viewBox="0 0 ${width} ${H + 16}">${svg}</svg></div>`;
  }

  _days(fc, opt, width) {
    const u = fc.usage || {};
    const s = fc.solar || {};
    const legend = (color) => `<div class="fc-legend"><span><i style="border:1.3px dashed #a0a0a0"></i>${esc(this._t("fc_forecast_l"))}</span><span><i style="background:${color}"></i>${esc(this._t("fc_measured"))}</span></div>`;
    const mae = u.chosen_mae != null ? u.chosen_mae : u.mae;
    let html = `<div class="fc-line"><span class="dim">${esc(this._t("fc_usage_day"))}</span><b>${mae != null ? esc(this._t("fc_avg_err")(this._num(mae, 1))) : ""}</b></div>
      ${legend(opt.usage_color)}${this._bars(u.per_day || [], opt.usage_color, width)}`;
    if (s.measured) {
      html += `<div class="fc-line" style="margin-top:6px"><span class="dim">${esc(this._t("fc_solar_day"))}</span><b>${s.mae != null ? esc(this._t("fc_avg_err")(this._num(s.mae, 1))) : ""}</b></div>
        ${legend(opt.solar_color)}${this._bars(s.per_day || [], opt.solar_color, width)}`;
    }
    html += `<div class="fc-note">${esc(this._t("fc_days_note"))}</div>`;
    return html;
  }

  _methods(fc) {
    const m = fc.methods || {};
    const lookback = m.lookback_weeks || 6;
    const rows = (m.rows || []).map((r) => {
      const used = r.key === m.chosen;
      const bias = r.bias_pct == null ? "\u2014" : `${r.bias_pct > 0 ? "+" : ""}${this._num(r.bias_pct, 0)} %`;
      const cls = r.bias_pct != null && Math.abs(r.bias_pct) >= 5 ? "fc-pos" : "fc-good";
      return `<div class="fc-row${used ? " used" : ""}"><span>${esc(this._methodName(r.key, lookback))}</span><span>${r.mae != null ? `\u00b1${esc(this._num(r.mae, 1))}` : "\u2014"}</span><span class="${cls}">${esc(bias)}</span><span class="fc-good">${used ? `\u2713 ${esc(this._t("fc_in_use"))}` : ""}</span></div>`;
    }).join("");
    return `<div class="fc-table">
        <div class="fc-row head"><span>${esc(this._t("fc_col_method"))}</span><span>${esc(this._t("fc_col_err"))}</span><span>${esc(this._t("fc_col_bias"))}</span><span></span></div>
        ${rows}
      </div>
      <div class="fc-note">${esc(this._t("fc_methods_note")(m.test_days || 0))}</div>`;
  }
}

// -- Savings card (as of 2026.11.0) ----------------------------------------------
// What the battery saved against the same house without one (savings.py):
// per day what was bought and sold with the battery and without, priced
// with the buy price incl taxes (the line of the Status sensor) and the bare
// sell price. Day / week / month / year; a bar per hour, day or month.
const SV_DEFAULTS = {
  title: "",
  saving_color: [77, 208, 160],
  loss_color: [224, 95, 95],
};
const SV_COLOR_KEYS = ["saving_color", "loss_color"];
const SV_SCHEMA = (t) => [
  { name: "title", selector: { text: {} } },
  {
    type: "expandable",
    flatten: true,
    name: "colours",
    title: t("ed_colours"),
    schema: [{ type: "grid", name: "", schema: SV_COLOR_KEYS.map((name) => ({ name, selector: { color_rgb: {} } })) }],
  },
];
const SV_TEXT = {
  en: {
    title: "Savings", saved: "saved", cost_more: "more expensive", day: "Day", week: "Week", month: "Month", year: "Year", rolling: "365 d",
    p_day: "today", p_week: "last 7 days", p_month: "this month", p_year: "this year", p_rolling: "last 365 days",
    less: (p) => `${p}% less than without battery`, more: (p) => `${p}% more than without battery`,
    without: "Without battery", with: "With ESS Manager", bought: "bought", sold: "sold", at: "at", no_sale: "no sale",
    legend_saving: "saved", legend_loss: "more expensive than without battery", avg: (v) => `avg. ${v} / day`,
    tap: "tap a bar",
    note: () => "This house and its usage, compared with and without the battery.",
    no_battery: "The savings need the battery's charged and discharged energy in the Energy dashboard (Settings > Dashboards > Energy).",
    no_grid: "The savings need the grid import and export in the Energy dashboard (Settings > Dashboards > Energy).",
    waiting: "Working out the savings - the days the recorder still has are filled in shortly.",
    empty: "No savings yet - the first day is added tonight.",
    no_data: "No data for this period.",
    cost_with: "with battery", cost_without: "without battery",
    stock_in: "into the battery", stock_out: "out of the battery",
    stock_now: (k, p) => `In the battery: ${k} kWh \u00b7 avg. ${p}/kWh (what it cost to put in)`,
  },
  nl: {
    title: "Besparing", saved: "bespaard", cost_more: "duurder", day: "Dag", week: "Week", month: "Maand", year: "Jaar", rolling: "365 d",
    p_day: "vandaag", p_week: "laatste 7 dagen", p_month: "deze maand", p_year: "dit jaar", p_rolling: "laatste 365 dagen",
    less: (p) => `${p}% minder dan zonder accu`, more: (p) => `${p}% meer dan zonder accu`,
    without: "Zonder accu", with: "Met ESS Manager", bought: "ingekocht", sold: "verkocht", at: "\u00e0", no_sale: "geen verkoop",
    legend_saving: "bespaard", legend_loss: "duurder dan zonder accu", avg: (v) => `gem. ${v} / dag`,
    tap: "tik op een staaf",
    note: () => "Dit huis en zijn verbruik, vergeleken met en zonder accu.",
    no_battery: "Voor de besparing is het laden en ontladen van de accu nodig in het Energie-dashboard (Instellingen > Dashboards > Energie).",
    no_grid: "Voor de besparing zijn inkoop en teruglevering nodig in het Energie-dashboard (Instellingen > Dashboards > Energie).",
    waiting: "De besparing wordt uitgerekend - de dagen die de recorder nog heeft komen er zo bij.",
    empty: "Nog geen besparing - de eerste dag komt er vannacht bij.",
    no_data: "Geen gegevens voor deze periode.",
    cost_with: "met accu", cost_without: "zonder accu",
    stock_in: "naar de accu", stock_out: "uit de accu",
    stock_now: (k, p) => `In de accu: ${k} kWh \u00b7 gem. ${p}/kWh (wat het kostte om erin te zetten)`,
  },
};
const SV_CSS = `
  .sv-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
  .sv-big { font-size: 32px; font-weight: 700; line-height: 1.1; white-space: nowrap; }
  .sv-big small { font-size: 14px; font-weight: 500; color: var(--secondary-text-color, #a0a0a0); }
  .sv-pill { display: inline-block; margin-top: 6px; font-size: 12px; padding: 4px 10px; border-radius: 999px; }
  .sv-tabs { display: flex; gap: 2px; padding: 3px; border-radius: 999px; background: rgba(127,127,127,.14); }
  .sv-tabs button { border: 0; background: transparent; color: var(--secondary-text-color, #a0a0a0); font: inherit; font-size: 12px; padding: 5px 11px; border-radius: 999px; cursor: pointer; }
  .sv-tabs button[aria-selected="true"] { background: rgba(127,127,127,.3); color: var(--primary-text-color, #fff); }
  .sv-cmp { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 14px 0 4px; }
  .sv-box { border-radius: 14px; padding: 10px 12px; background: rgba(127,127,127,.12); min-width: 0; }
  .sv-box .v { font-size: 20px; font-weight: 600; margin: 2px 0 6px; }
  .sv-ln { display: grid; grid-template-columns: minmax(0, 1fr) auto auto minmax(56px, auto); gap: 6px; font-size: 12.5px; margin-top: 3px; align-items: baseline; }
  .sv-ln b { text-align: right; font-size: 14px; }
  .sv-legend { display: flex; gap: 14px; font-size: 12px; color: var(--secondary-text-color, #a0a0a0); margin-top: 6px; flex-wrap: wrap; }
  .sv-legend i { display: inline-block; width: 11px; height: 8px; border-radius: 3px; margin-right: 5px; vertical-align: middle; }
  .sv-note { font-size: 11.5px; line-height: 16px; color: var(--secondary-text-color, #8f8f8f); margin-top: 10px; }
  .sv-chart { position: relative; margin-top: 14px; }
  .sv-right { display: flex; flex-direction: column; align-items: stretch; gap: 8px; }
  .sv-nav { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 14px; font-weight: 500; }
  .sv-nav span { flex-grow: 1; text-align: center; white-space: nowrap; }
  .sv-nav button { width: 30px; height: 30px; border-radius: 50%; border: 0; background: rgba(127,127,127,.16); color: inherit; font: inherit; font-size: 18px; line-height: 1; cursor: pointer; }
  .sv-nav button[disabled] { opacity: .3; cursor: default; }
  .sv-chart svg { display: block; }
  .sv-chart text { fill: var(--secondary-text-color, #8f8f8f); font-size: 10px; font-family: inherit; }
  @container (max-width: 420px) { .sv-cmp { grid-template-columns: minmax(0, 1fr); } }
`;

class EssManagerSavingsCard extends EssChartCard {
  static get info() {
    return {
      name: "ESS Manager - Savings",
      description: "What the battery saved against the same house without one - per day, week, month and year, with the average buy and sell price.",
      schema: SV_SCHEMA,
      defaults: SV_DEFAULTS,
      labels: { title: "ed_title", saving_color: "ed_saving_color", loss_color: "ed_loss_color" },
    };
  }

  getCardSize() {
    return 6;
  }

  _s(key) {
    const lang = hassLang(this._hass).slice(0, 2) === "nl" ? "nl" : "en";
    return SV_TEXT[lang][key];
  }

  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const st = this._hass.states[this._config.entity];
    const opt = colorOptions(this._config, SV_DEFAULTS, SV_COLOR_KEYS);
    const css = BASE_CSS + SV_CSS;
    if (!isStatusSensor(st)) {
      setCardContent(this, css, notStatusMessage(this._hass, this._config.entity, st));
      return;
    }
    const svId = (st.attributes.card_entities || {}).savings;
    const svObj = svId ? this._hass.states[svId] : null;
    const width = this._chartWidth();
    const key = [svObj, width, this._period, this._offset, this._tip, hassLang(this._hass)];
    if (this._renderKey && key.every((v, i) => v === this._renderKey[i])) return;
    this._renderKey = key;
    const title = esc(this._config.title || this._s("title"));
    const sv = svObj ? svObj.attributes : null;
    const msg = (text) => setCardContent(this, css, `<div class="top"><span class="title">${title}</span></div><div class="sv-note" style="font-size:13px">${esc(text)}</div>`);
    if (!sv || !sv.status || sv.status === "waiting") return msg(this._s("waiting"));
    if (sv.status === "no_battery") return msg(this._s("no_battery"));
    if (sv.status === "no_grid") return msg(this._s("no_grid"));
    const f = formats(this._hass);
    const rows = (sv.days || []).slice();
    const today = sv.today && sv.today.row ? sv.today.row : null;
    if (today && !rows.some((r) => r[0] === today[0])) rows.push(today);
    if (!rows.length) return msg(this._s("empty"));

    const period = this._period || "month";
    const off = this._offset || 0;
    const todayIso = isoDate(this._hass, Date.now());
    const lang = hassLang(this._hass);
    const byDate = Object.fromEntries(rows.map((r) => [r[0], r]));
    // (as of 2026.11.8) r[9]: the change of the battery's stock - energy
    // stored counts on the day it's used, at what it cost to put in
    const sum = (list) => list.reduce((a, r) => { for (let k = 1; k < 10; k++) a[k] += Number(r[k]) || 0; return a; }, [null, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    const costWith = (t) => (t[2] - t[4]) - (Number(t[9]) || 0);
    const saving = (t) => (t[6] - t[8]) - costWith(t);
    const noon = (d) => Date.parse(`${d}T12:00:00Z`);
    const fmt = (d, o) => new Intl.DateTimeFormat(lang, { timeZone: "UTC", ...o }).format(noon(d));
    const monthBars = (months, lo, hi, withYear) => {
      for (const ym of months) {
        const list = rows.filter((r) => r[0].startsWith(ym) && r[0] >= lo && r[0] <= hi);
        inPeriod = inPeriod.concat(list);
        const name = fmt(`${ym}-15`, { month: "short" });
        bars.push([name, list.length ? saving(sum(list)) : null, list.length ? sum(list) : null, withYear ? `${name} ${ym.slice(0, 4)}` : name]);
      }
    };
    // the period shown, `off` periods back (as of 2026.11.1 - the arrows,
    // like the Energy dashboard): [label, first date], and the bars
    // [label, saving, row-or-sum, tooltip label]; Day has no bars
    let bars = [];
    let inPeriod = [];
    let label = "";
    let first = todayIso;
    if (period === "day") {
      const d = addDays(todayIso, -off);
      first = d;
      if (byDate[d]) inPeriod = [byDate[d]];
      label = off === 0 ? this._s("p_day") : fmt(d, { weekday: "short", day: "numeric", month: "long" });
    } else if (period === "week" || period === "month") {
      const dates = [];
      if (period === "week") {
        // a calendar week, Monday to Sunday
        const dow = (new Date(noon(todayIso)).getUTCDay() + 6) % 7;
        const monday = addDays(todayIso, -dow - 7 * off);
        for (let k = 0; k < 7; k++) dates.push(addDays(monday, k));
        label = `${fmt(dates[0], { day: "numeric", month: "short" })} \u2013 ${fmt(dates[6], { day: "numeric", month: "short" })}`;
      } else {
        const dt = new Date(noon(todayIso.slice(0, 8) + "01"));
        dt.setUTCMonth(dt.getUTCMonth() - off);
        const firstDay = dt.toISOString().slice(0, 10);
        for (let d = firstDay; d.slice(0, 7) === firstDay.slice(0, 7); d = addDays(d, 1)) dates.push(d);
        label = fmt(firstDay, { month: "long", year: "numeric" });
      }
      first = dates[0];
      for (const d of dates) {
        const r = d <= todayIso ? byDate[d] : null;
        if (r) inPeriod.push(r);
        bars.push([period === "week" ? fmt(d, { weekday: "short" }) : String(Number(d.slice(8))), r ? saving(sum([r])) : null, r, fmt(d, { weekday: "short", day: "numeric", month: "short" })]);
      }
    } else if (period === "rolling") {
      // 365 days up to today (or a whole such stretch back): a bar per
      // month, the first one only from the day a year back
      const to = addDays(todayIso, -365 * off);
      const from = addDays(to, -364);
      first = from;
      const months = [];
      for (let d = from.slice(0, 8) + "01"; d <= to; d = addDays(d.slice(0, 8) + "28", 4).slice(0, 8) + "01") months.push(d.slice(0, 7));
      monthBars(months, from, to, true);
      label = off === 0 ? this._s("p_rolling") : `${fmt(from, { day: "numeric", month: "short", year: "numeric" })} \u2013 ${fmt(to, { day: "numeric", month: "short", year: "numeric" })}`;
    } else {
      const year = String(Number(todayIso.slice(0, 4)) - off);
      first = `${year}-01-01`;
      monthBars(Array.from({ length: 12 }, (_, m) => `${year}-${String(m + 1).padStart(2, "0")}`), first, `${year}-12-31`, false);
      label = off === 0 ? this._s("p_year") : year;
    }
    const oldest = rows.map((r) => r[0]).sort()[0];
    const t = sum(inPeriod);
    const save = saving(t);
    const without = t[6] - t[8];
    const pct = without > 0.01 ? Math.round((Math.abs(save) / without) * 100) : null;
    const good = save >= 0;
    const tabs = ["day", "week", "month", "year", "rolling"]
      .map((p) => `<button type="button" data-p="${p}" aria-selected="${p === period}">${esc(this._s(p))}</button>`).join("");
    const priceTxt = (eur, kwh) => (kwh > 0.05 ? formatPrice(f, eur / kwh) : null);
    const box = (label, cost, imp, bought, exp, sold, color, bg, stock) => `<div class="sv-box"${bg ? ` style="background:${bg}"` : ""}>
        <div class="dim" style="font-size:12px">${esc(label)}</div>
        <div class="v"${color ? ` style="color:${color}"` : ""}>${esc(f.money(cost))}</div>
        <div class="sv-ln"><span class="dim">\u2193 ${esc(this._s("bought"))}</span><span>${esc(f.num(imp, imp < 10 ? 1 : 0))} kWh</span><span class="dim">${esc(this._s("at"))}</span><b${color ? ` style="color:${color}"` : ""}>${esc(priceTxt(bought, imp) || "\u2013")}</b></div>
        <div class="sv-ln"><span class="dim">\u2191 ${esc(this._s("sold"))}</span><span>${esc(f.num(exp, exp < 10 ? 1 : 0))} kWh</span><span class="dim">${exp > 0.05 ? esc(this._s("at")) : ""}</span><b${color ? ` style="color:${color}"` : ""}>${exp > 0.05 ? esc(priceTxt(sold, exp)) : `<span class="dim" style="font-weight:400;font-size:12px">${esc(this._s("no_sale"))}</span>`}</b></div>
        ${stock != null && Math.abs(stock) >= 0.005 ? `<div class="sv-ln"><span class="dim">\u25d0 ${esc(this._s(stock > 0 ? "stock_in" : "stock_out"))}</span><span></span><span></span><b${color ? ` style="color:${color}"` : ""}>${esc(f.money(-stock))}</b></div>` : ""}
      </div>`;

    // the chart
    const W = width;
    const H = 130;
    const X0 = 30;
    const vals = bars.map((b) => b[1]).filter((v) => v !== null);
    let hi = Math.max(0, ...vals);
    let lo = Math.min(0, ...vals);
    const steps = [0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500];
    const step = steps.find((s) => (hi - lo) / s <= 4) || 1000;
    hi = Math.max(step, Math.ceil(hi / step - 1e-9) * step);
    lo = Math.floor(lo / step + 1e-9) * step;
    const top = 8;
    const bottom = H - 16;
    const y = (v) => top + ((hi - v) / (hi - lo)) * (bottom - top);
    const n = bars.length;
    const bw = (W - X0) / n;
    let svg = "";
    for (let v = lo; v <= hi + step / 2; v += step) {
      svg += `<line x1="${X0}" y1="${r1(y(v))}" x2="${W}" y2="${r1(y(v))}" stroke="rgba(127,127,127,${Math.abs(v) < step / 2 ? 0.35 : 0.13})"/>`;
      svg += `<text x="0" y="${r1(y(v) + 3)}">${esc(f.num(v, step < 1 ? (step < 0.1 ? 2 : 1) : 0))}</text>`;
    }
    const labelEvery = n > 24 ? 5 : n > 12 ? 3 : 1;
    bars.forEach((b, i) => {
      const x = X0 + i * bw + bw * 0.15;
      const w = Math.max(bw * 0.7, 1);
      if (b[1] !== null) {
        const y0 = y(Math.max(b[1], 0));
        const h = Math.max(Math.abs(y(b[1]) - y(0)), b[1] === 0 ? 0 : 1);
        svg += `<rect x="${r1(x)}" y="${r1(b[1] >= 0 ? y0 : y(0))}" width="${r1(w)}" height="${r1(h)}" rx="2" fill="${b[1] >= 0 ? opt.saving_color : opt.loss_color}" fill-opacity="${this._tip === i ? 1 : 0.82}"/>`;
      }
      if (i % labelEvery === 0) svg += `<text x="${r1(x + w / 2)}" y="${H - 3}" text-anchor="middle">${esc(b[0])}</text>`;
    });
    let avgTxt = "";
    if ((period === "week" || period === "month") && vals.length) {
      const a = vals.reduce((x, v) => x + v, 0) / vals.length;
      svg += `<line x1="${X0}" y1="${r1(y(a))}" x2="${W}" y2="${r1(y(a))}" stroke="${opt.saving_color}" stroke-dasharray="3 3" stroke-opacity=".7"/>`;
      avgTxt = this._s("avg")(f.money(a));
      svg += `<text x="${W}" y="${r1(y(a) - 4)}" text-anchor="end" style="fill:${opt.saving_color}">${esc(avgTxt)}</text>`;
    }
    let tip = "";
    if (this._tip != null && bars[this._tip] && bars[this._tip][1] !== null) {
      const b = bars[this._tip];
      const r = b[2];
      const left = clamp(X0 + this._tip * bw - 60, 0, W - 190);
      const lines = r
        ? `<div class="row"><span class="k">${esc(this._s("cost_with"))}</span><b>${esc(f.money(costWith(r)))}</b></div><div class="row"><span class="k">${esc(this._s("cost_without"))}</span><b>${esc(f.money(r[6] - r[8]))}</b></div>`
        : "";
      tip = `<div class="tip" style="display:flex;left:${r1(left)}px;top:0"><div class="row"><b>${esc(b[3])}</b></div><div class="row"><span class="k">${esc(this._s(b[1] >= 0 ? "saved" : "cost_more"))}</span><b>${esc(f.money(Math.abs(b[1])))}</b></div>${lines}</div>`;
    }
    const pTitle = title;
    // back as long as the period before still has stored days
    const canBack = !!oldest && oldest < first;
    const pill = pct !== null
      ? `<span class="sv-pill" style="background:${tint(good ? opt.saving_color : opt.loss_color, 0.16)};color:${good ? opt.saving_color : opt.loss_color}">${good ? "\u25b2" : "\u25bc"} ${esc(this._s(good ? "less" : "more")(pct))}</span>`
      : "";
    const html = `
      <div class="sv-top">
        <div><div class="dim" style="font-size:13px">${pTitle}</div>
          <div class="sv-big">${esc(f.money(Math.abs(save)))} <small>${esc(this._s(good ? "saved" : "cost_more"))}</small></div>${pill}</div>
        <div class="sv-right"><div class="sv-tabs">${tabs}</div>
          <div class="sv-nav">
            <button type="button" class="prev" aria-label="\u2039"${canBack ? "" : " disabled"}>\u2039</button>
            <span>${esc(label)}</span>
            <button type="button" class="next" aria-label="\u203a"${off > 0 ? "" : " disabled"}>\u203a</button>
          </div></div>
      </div>
      ${inPeriod.length ? `<div class="sv-cmp">
        ${box(this._s("without"), t[6] - t[8], t[5], t[6], t[7], t[8], null, null)}
        ${box(this._s("with"), costWith(t), t[1], t[2], t[3], t[4], opt.saving_color, tint(opt.saving_color, 0.1), Number(t[9]) || 0)}
      </div>` : `<div class="sv-note" style="font-size:13px;margin:14px 0">${esc(this._s("no_data"))}</div>`}
      ${bars.length && inPeriod.length ? `<div class="sv-chart"><svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${svg}</svg>${tip}
        <div class="hit" style="position:absolute;left:${X0}px;top:0;width:${r1(W - X0)}px;height:${H}px"></div></div>
      <div class="sv-legend"><span><i style="background:${opt.saving_color}"></i>${esc(this._s("legend_saving"))}</span><span><i style="background:${opt.loss_color}"></i>${esc(this._s("legend_loss"))}</span><span style="margin-left:auto">${esc(this._s("tap"))}</span></div>` : ""}
      ${sv.stock && sv.stock.avg != null ? `<div class="sv-note" style="font-size:12.5px">${esc(this._s("stock_now")(f.num(sv.stock.kwh, 1), formatPrice(f, sv.stock.avg)))}</div>` : ""}
      <div class="sv-note">${esc(this._s("note")(sv.history_days))}</div>`;
    setCardContent(this, css, html);
    for (const btn of this.shadowRoot.querySelectorAll(".sv-tabs button")) {
      btn.onclick = () => {
        this._period = btn.dataset.p;
        this._offset = 0;
        this._tip = null;
        this._render();
      };
    }
    const nav = (d) => () => {
      this._offset = Math.max((this._offset || 0) + d, 0);
      this._tip = null;
      this._render();
    };
    const prev = this.shadowRoot.querySelector(".sv-nav .prev");
    const next = this.shadowRoot.querySelector(".sv-nav .next");
    if (prev) prev.onclick = nav(1);
    if (next) next.onclick = nav(-1);
    const hit = this.shadowRoot.querySelector(".hit");
    if (hit) {
      hit.onclick = (ev) => {
        const i = clamp(Math.floor((ev.clientX - hit.getBoundingClientRect().left) / bw), 0, n - 1);
        this._tip = this._tip === i ? null : i;
        this._render();
      };
    }
  }
}

// a price per kWh with three decimals (\u20ac 0,381)
function formatPrice(f, v) {
  const two = f.money(v);
  const digits = f.num(v, 3);
  return two.replace(/[\d.,]+/, digits.replace(/^-/, ""));
}
// the local date (YYYY-MM-DD) of a moment, in the shown time zone
function isoDate(hass, ms) {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: hassTimeZone(hass), year: "numeric", month: "2-digit", day: "2-digit" }).format(ms);
  } catch (err) {
    return new Date(ms).toISOString().slice(0, 10);
  }
}
function addDays(iso, k) {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + k);
  return d.toISOString().slice(0, 10);
}

window.customCards = window.customCards || [];
for (const [type, cls] of [
  ["ess-manager-status-card", EssManagerStatusCard],
  ["ess-manager-battery-card", EssManagerBatteryCard],
  ["ess-manager-price-card", EssManagerPriceCard],
  ["ess-manager-ev-card", EssManagerEvCard],
  ["ess-manager-heatpump-card", EssManagerHeatPumpCard],
  ["ess-manager-forecast-card", EssManagerForecastCard],
  ["ess-manager-savings-card", EssManagerSavingsCard],
]) {
  if (customElements.get(type)) continue;
  customElements.define(type, cls);
  window.customCards.push({ type, name: cls.info.name, description: cls.info.description, preview: true, documentationURL: DOCS_URL });
}
console.info("%c ESS Manager cards %c loaded ", "color:#fff;background:#4caf50", "");
