/*
 * ESS Manager dashboard cards - loaded automatically by the integration,
 * shown in the dashboard's "Add card" picker:
 *
 *   custom:ess-manager-battery-card   battery forecast: five whole days, measured + expected
 *   custom:ess-manager-price-card     today's and tomorrow's prices with the planned moments
 *   custom:ess-manager-status-card    Sell / Buy blocks, price plans, control toggle, timeline
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
    spike: "Spike", negative: "Negative price", balancing: "Balancing",
    active: "Active", inactive: "Inactive", below: "below", auto_control: "Automatic control",
    h: "h", min: "min", ago: (h) => `-${h} h`, now: "now",
    // battery card
    battery_title: "Battery forecast", today: "today", horizon: "planning horizon",
    offgrid_empty: (w) => `without grid: empty ${w}`, offgrid_full: (w) => `without grid: full ${w}`,
    offgrid_days: "without grid: 5+ days", measured: "measured", expected: "expected",
    soc: "SOC", without_plans: "Without plans", solar: "Solar", usage: "Usage", price: "Price",
    min_label: (p) => `min ${p} %`, max_label: (p) => `max ${p} %`,
    // plans (battery + price card)
    plan_sell: "Sell", plan_buy: "Buy", plan_spike: "Spike", plan_negative: "Negative price",
    plan_full: "Full charge", plan_charged: "Charged", plan_sold: "Sold",
    // price card
    price_title: "Electricity price", buy_price: "buy", incl_transport: "incl. transport",
    cheapest: "cheapest", most_expensive: "most expensive", per_kwh: "/kWh",
    legend_level: "price level", legend_sell: "Sell planned", legend_buy: "Buy planned", legend_buy_line: "Buy price",
    no_prices: "No prices yet",
    // editors
    ed_entity: "ESS Manager Status sensor", ed_title: "Title", ed_colours: "Colours", ed_height: "Chart height (px)",
    ed_days: "Days", ed_show_days: "Show the day tiles", ed_show_raw: "Show the forecast without plans",
    ed_show_solar: "Show solar", ed_show_usage: "Show usage", ed_show_outlook: "Show \"without grid\"",
    ed_soc_color: "SOC", ed_solar_color: "Solar", ed_usage_color: "Usage", ed_sell_color: "Sell", ed_buy_color: "Buy",
    ed_show_extremes: "Show cheapest / most expensive", ed_show_buy_line: "Show the buy price line",
    ed_legend: "Show the legend", ed_cheap_color: "Cheap", ed_mid_color: "Average", ed_high_color: "Expensive",
    ed_negative_color: "Negative",
    ed_automation: "Your own ESS automation (when the integration doesn't control the battery itself)",
    ed_hours: "Timeline period (h)", ed_show_history: "Show the timeline",
    ed_spike_color: "Spike plan", ed_negative_plan_color: "Negative price plan",
  },
  nl: {
    planned: "gepland", running: "bezig", done: "klaar", of: "van", stop: "stop",
    left: (d) => `nog ${d}`, no_sell: "Geen sale gepland", no_buy: "Geen laadactie gepland",
    spike: "Spike", negative: "Negatieve prijs", balancing: "Balanceren",
    active: "Actief", inactive: "Inactief", below: "onder", auto_control: "Automatische aansturing",
    h: "u", min: "min", ago: (h) => `-${h} u`, now: "nu",
    battery_title: "Batterijprognose", today: "vandaag", horizon: "planningshorizon",
    offgrid_empty: (w) => `zonder stroomnet leeg ${w}`, offgrid_full: (w) => `zonder stroomnet vol ${w}`,
    offgrid_days: "zonder stroomnet 5+ dagen", measured: "gemeten", expected: "verwacht",
    soc: "SOC", without_plans: "Zonder plannen", solar: "Zon", usage: "Verbruik", price: "Prijs",
    min_label: (p) => `min ${p} %`, max_label: (p) => `max ${p} %`,
    plan_sell: "Sell", plan_buy: "Buy", plan_spike: "Spike", plan_negative: "Negatieve prijs",
    plan_full: "Vol laden", plan_charged: "Geladen", plan_sold: "Verkocht",
    price_title: "Stroomprijs", buy_price: "inkoop", incl_transport: "incl. transport",
    cheapest: "goedkoopst", most_expensive: "duurst", per_kwh: "/kWh",
    legend_level: "prijsniveau", legend_sell: "Sell gepland", legend_buy: "Buy gepland", legend_buy_line: "Inkoopprijs",
    no_prices: "Nog geen prijzen",
    ed_entity: "ESS Manager Status-sensor", ed_title: "Titel", ed_colours: "Kleuren", ed_height: "Hoogte grafiek (px)",
    ed_days: "Dagen", ed_show_days: "Dagtegels tonen", ed_show_raw: "Voorspelling zonder plannen tonen",
    ed_show_solar: "Zon tonen", ed_show_usage: "Verbruik tonen", ed_show_outlook: "\"Zonder stroomnet\" tonen",
    ed_soc_color: "SOC", ed_solar_color: "Zon", ed_usage_color: "Verbruik", ed_sell_color: "Sell", ed_buy_color: "Buy",
    ed_show_extremes: "Goedkoopst / duurst tonen", ed_show_buy_line: "Lijn met inkoopprijs tonen",
    ed_legend: "Legenda tonen", ed_cheap_color: "Goedkoop", ed_mid_color: "Gemiddeld", ed_high_color: "Duur",
    ed_negative_color: "Negatief",
    ed_automation: "Je eigen ESS-automatisering (als de integratie de accu niet zelf aanstuurt)",
    ed_hours: "Periode tijdlijn (u)", ed_show_history: "Tijdlijn tonen",
    ed_spike_color: "Spike-plan", ed_negative_plan_color: "Negatieve-prijsplan",
  },
};

function hassLang(hass) {
  return (hass && ((hass.locale && hass.locale.language) || hass.language)) || "en";
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
  return Math.floor(ms / 60000) * 60000 - (hour * 60 + minute) * 60000;
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
  return `<ha-card><div style="padding:16px">ESS Manager: ${esc(entity)} ${stateObj ? "is not an ESS Manager Status sensor - choose the \"Status\" sensor" : "not found"}.</div></ha-card>`;
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
const ACTION_KIND = { charge: "buy", negative_price_charge: "negative", discharge: "sell", spike_discharge: "spike" };

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
  }
  return out;
}

function planLabel(hass, w) {
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
    else out.push({ side: kind === "buy" || kind === "negative" ? "buy" : "sell", kind, start: t, stop, past: true });
  });
  return out;
}

// The pill-shaped plan labels in the charts.
function planPill(hass, w, colors) {
  const color = colors[w.kind];
  const ic = { sell: "up", spike: "spike", buy: "down", negative: "negative" }[w.kind];
  return { color, html: `${icon(ic, color, 12, 2.4)}${esc(planLabel(hass, w))} ${esc(formats(hass).time(w.start))}` };
}

const BASE_CSS = `
  :host { display: block; }
  ha-card { padding: 16px; display: flex; flex-direction: column; gap: 14px; overflow: hidden; container-type: inline-size; }
  .top { display: flex; align-items: flex-start; gap: 10px; }
  .title { font-size: 17px; font-weight: 600; flex-grow: 1; }
  .dim { color: var(--secondary-text-color, #a0a0a0); }
  .batt { width: 22px; height: 12px; border: 2px solid var(--secondary-text-color, #a0a0a0); border-radius: 3px; padding: 1px; box-sizing: border-box; display: inline-flex; flex-shrink: 0; }
  .batt span { border-radius: 1px; }
  .chart { position: relative; touch-action: pan-y; user-select: none; -webkit-user-select: none; }
  .chart svg { display: block; position: absolute; left: 0; top: 0; overflow: visible; }
  .chart text { fill: var(--secondary-text-color, #a0a0a0); font-size: 10px; font-family: inherit; }
  .pill { position: absolute; display: flex; align-items: center; gap: 4px; font-size: 11px; line-height: 16px; padding: 1px 8px; border-radius: 999px; white-space: nowrap; pointer-events: none; }
  .plabel { position: absolute; font-size: 10px; white-space: nowrap; pointer-events: none; transform: translateX(-50%); }
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
};
const BATTERY_COLOR_KEYS = ["soc_color", "solar_color", "usage_color", "sell_color", "buy_color"];
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
        sell_color: "ed_sell_color", buy_color: "ed_buy_color",
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
      windows: planWindows(attrs).filter((w) => w.stop > now),
    };
  }

  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj || !isStatusSensor(stateObj)) {
      this.shadowRoot.innerHTML = notStatusMessage(this._hass, this._config.entity, stateObj);
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

    const colors = { normal: opt.soc_color, buy: opt.buy_color, negative: "#2f8cff", sell: opt.sell_color, spike: "#ff4545" };
    this._colors = colors;
    const W = width;
    const top = 30;
    const H = Math.max(clamp(Number(opt.height) || 210, 120, 600) - top - 4, 60);
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
    for (const s of m.starts.slice(1, -1)) svg += `<line x1="${r1(x(s))}" y1="${top}" x2="${r1(x(s))}" y2="${bottom}" stroke="rgba(127,127,127,.25)"/>`;
    // solar (hourly values drawn at the middle of their hour), usage
    const mid = (list) => list.filter(([t]) => t + HOUR_MS > m.T0 && t < m.T1).map(([t, v]) => [t + HOUR_MS / 2, v]);
    const solar = mid(m.flows.solar);
    if (opt.show_solar !== false && solar.length > 1) {
      const line = pts(solar, yk);
      svg += `<path d="M${r1(x(solar[0][0]))} ${bottom} L${line.join(" L")} L${r1(x(solar[solar.length - 1][0]))} ${bottom} Z" fill="${opt.solar_color}" fill-opacity="0.16" stroke="${opt.solar_color}" stroke-opacity="0.4" stroke-width="1"/>`;
    }
    const usage = mid(m.flows.usage);
    if (opt.show_usage !== false && usage.length > 1) {
      svg += `<path d="M${pts(usage, yk).join(" L")}" fill="none" stroke="${opt.usage_color}" stroke-opacity="0.55" stroke-width="1"/>`;
    }
    // the forecast without plans, cut off at the chart's edges
    if (opt.show_raw !== false && m.raw.length > 1) {
      svg += `<defs><clipPath id="plot"><rect x="0" y="${top}" width="${W}" height="${H}"/></clipPath></defs>`;
      svg += `<path d="M${pts(m.raw, ys).join(" L")}" fill="none" stroke="${opt.soc_color}" stroke-opacity="0.6" stroke-width="1.3" stroke-dasharray="1.5 3" stroke-linecap="round" clip-path="url(#plot)"/>`;
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
    const all = m.hist.map((p) => [...p, true]).concat(m.future.map((p) => [...p, false]));
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
    svg += `<rect x="0" y="${top}" width="${r1(clamp(xNow, 0, W))}" height="${H}" style="fill:${bg}" fill-opacity="0.35"/>`;
    const xHor = x(m.horizon);
    if (xHor < W) {
      svg += `<rect x="${r1(xHor)}" y="${top}" width="${r1(W - xHor)}" height="${H}" style="fill:${bg}" fill-opacity="0.45"/>`;

    }
    svg += `<line x1="${r1(xNow)}" y1="${top - 6}" x2="${r1(xNow)}" y2="${bottom}" style="stroke:var(--primary-text-color, #e8e8e8)" stroke-width="1.2"/>`;
    svg += `<text x="${r1(xNow)}" y="${top - 10}" text-anchor="middle" style="fill:var(--primary-text-color, #e8e8e8);font-weight:600">${esc(this._t("now"))}</text>`;
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
    const placed = [];
    const socAt = (t) => this._interp(t < m.now ? m.hist : m.future, t);
    for (const w of m.windows) {
      if (w.start >= m.T1) continue;
      const p = planPill(this._hass, w, colors);
      const t = Math.max(w.start, m.T0);
      const estW = 30 + (planLabel(this._hass, w).length + 6) * 6.2;
      const left = clamp(x(t) - 6, 0, Math.max(W - estW, 0));
      const v = socAt(t);
      const yLine = ys(clamp(v === null ? 50 : v, 0, 100));
      let y = yLine - 28 < 0 ? yLine + 10 : yLine - 28;
      const clash = placed.find((q) => left < q.left + q.w && q.left < left + estW && Math.abs(q.y - y) < 20);
      if (clash) y = y < yLine ? yLine + 10 : yLine - 28;
      placed.push({ left, y, w: estW });
      pills += `<span class="pill" style="left:${r1(left)}px;top:${r1(clamp(y, 0, bottom - 18))}px;background:${tint(p.color, 0.2)};color:var(--primary-text-color, #e8e8e8)">${p.html}</span>`;
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

    this.shadowRoot.innerHTML = `<style>${BASE_CSS}
      .right { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
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
    </style>
    <ha-card>
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
    </ha-card>`;
    this._wireTooltip((px) => this._showTip(px));
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
    const price = attrs.all_price && unit >= 0 && unit < attrs.all_price.length ? num(attrs.all_price[unit]) : null;
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
    if (price !== null) html += `<div class="row sep"><span class="k">${esc(this._t("price"))}</span><b>${esc(f.money(price))}</b></div>`;
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
};
const PRICE_COLOR_KEYS = ["cheap_color", "mid_color", "high_color", "negative_color", "sell_color", "buy_color"];
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
      this.shadowRoot.innerHTML = notStatusMessage(this._hass, this._config.entity, stateObj);
      return;
    }
    const attrs = stateObj.attributes;
    const siblings = attrs.card_entities || {};
    const actionObj = siblings.battery_action ? this._hass.states[siblings.battery_action] : null;
    const width = this._chartWidth();
    const key = [stateObj, actionObj, this._hist, width, hassLang(this._hass)];
    if (this._renderKey && key.every((v, i) => v === this._renderKey[i])) return;
    this._renderKey = key;

    const opt = colorOptions(this._config, PRICE_DEFAULTS, PRICE_COLOR_KEYS);
    const f = formats(this._hass);
    const now = Date.now();
    const T0 = localMidnight(this._hass, now);
    this._ensureHistory(siblings, T0, actionObj);
    const title = esc(opt.title || this._t("price_title"));
    const prices = (attrs.all_price || []).map(num);
    if (!prices.length) {
      this.shadowRoot.innerHTML = `<style>${BASE_CSS}</style><ha-card><div class="top"><span class="title">${title}</span></div><div class="dim">${esc(this._t("no_prices"))}</div></ha-card>`;
      return;
    }
    const buy = (attrs.all_buy_price || attrs.all_price).map(num);
    // 15-minute prices; an hourly price list (24 values a day) works too.
    const unitMs = (num(attrs.today_price_units) || 96) <= 25 ? HOUR_MS : UNIT_MS;
    const n = prices.length;
    const T1 = T0 + n * unitMs;
    const cur = clamp(Math.floor((now - T0) / unitMs), 0, n - 1);
    const W = width;
    const X0 = 34;
    const top = 18;
    const H = Math.max(clamp(Number(opt.height) || 170, 100, 600) - top, 60);
    const bottom = top + H;
    const valid = prices.filter((v) => v !== null);
    const lineVals = opt.show_buy_line !== false ? buy.filter((v) => v !== null) : [];
    let lo = Math.min(0, ...valid, ...lineVals);
    let hi = Math.max(...valid, ...lineVals);
    const steps = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5];
    const step = steps.find((s) => (hi - lo) / s <= 5) || 10;
    lo = Math.floor(lo / step - 1e-9) * step;
    hi = Math.ceil(hi / step + 1e-9) * step;
    if (hi <= lo) hi = lo + step;
    const bw = (W - X0) / n;
    const x = (t) => X0 + ((t - T0) / (T1 - T0)) * (W - X0);
    const xi = (i) => X0 + i * bw;
    const y = (v) => top + ((hi - v) / (hi - lo)) * H;
    const base = y(0);
    this._geo = { W, X0, top, H, bottom, bw, xi, y, T0, unitMs, n };
    this._prices = { prices, buy };

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
    const colors = { buy: opt.buy_color, negative: opt.buy_color, sell: opt.sell_color, spike: opt.sell_color };
    const upcoming = planWindows(attrs).filter((w) => w.stop > T0 && w.start < T1);
    const ran = pastWindows(this._hist && this._hist.action, now)
      .filter((w) => w.stop > T0 && !upcoming.some((u) => u.side === w.side && u.start < w.stop && w.start < u.stop));
    const windows = ran.concat(upcoming).sort((a, b) => a.start - b.start);
    const inWindow = (i) => {
      const t = T0 + i * unitMs;
      return windows.some((w) => t + unitMs > w.start && t < w.stop);
    };
    const all = [...Array(n).keys()];
    let under = "";
    let streaks = "";
    let labels = "";
    let lastRight = -Infinity;
    for (const w of windows) {
      const x0 = x(Math.max(w.start, T0));
      const x1 = x(Math.min(w.stop, T1));
      const c = colors[w.kind];
      under += `<rect x="${r1(x0 - 1)}" y="${top - 4}" width="${r1(Math.max(x1 - x0 + 2, 2))}" height="${r1(H + 4)}" rx="3" fill="${c}" fill-opacity="0.07"/>`;
      streaks += `<rect x="${r1(x0 - 1)}" y="${r1(bottom + 3)}" width="${r1(Math.max(x1 - x0 + 2, 2))}" height="3" rx="1.5" fill="${c}"/>`;
      const text = `${planLabel(this._hass, w)} ${f.time(w.start)}`;
      const cx = (x0 + x1) / 2;
      const half = text.length * 3;
      if (cx - half > lastRight + 4) {
        labels += `<span class="plabel" style="left:${r1(clamp(cx, X0 + half, W - half))}px;top:0;color:${w.past ? "var(--secondary-text-color, #a0a0a0)" : tint(c, 1)}">${esc(text)}</span>`;
        lastRight = cx + half;
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
    if (opt.show_buy_line !== false) {
      const d = buy.map((v, i) => (v === null ? "" : `${i === 0 || buy[i - 1] === null ? "M" : "L"}${r1(xi(i))} ${r1(y(v))}H${r1(xi(i + 1))}`)).join("");
      buyLine = `<path d="${d}" fill="none" style="stroke:var(--primary-text-color, #e8e8e8)" stroke-opacity="0.4" stroke-width="1" stroke-dasharray="2 2"/>`;
    }
    const dayLine = n * unitMs > 26 * HOUR_MS ? nextMidnight(this._hass, T0) : null;
    const svg = `<defs>${grad}</defs>${axis}${under}
      <path d="${bars(all)}" fill="url(#lvl)" fill-opacity="0.6"/>
      <path d="${bars(all.filter(inWindow))}" fill="url(#lvl)"/>
      ${streaks}${buyLine}
      <rect x="${X0}" y="0" width="${r1(clamp(xNow - X0, 0, W - X0))}" height="${r1(bottom + 8)}" style="fill:${bg}" fill-opacity="0.7"/>
      ${dayLine ? `<line x1="${r1(x(dayLine))}" y1="${top - 4}" x2="${r1(x(dayLine))}" y2="${r1(bottom + 8)}" stroke="rgba(127,127,127,.45)"/>` : ""}
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
    if (nowB !== null && (tariff > 0 || nowB !== nowP)) buyText = `${this._t("buy_price")} ${f.money(nowB)}${tariff > 0 ? ` ${this._t("incl_transport")}` : ""}`;
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
      ${opt.show_buy_line !== false ? `<span><i style="width:12px;height:0;border-top:1px dashed var(--primary-text-color, #e8e8e8);border-radius:0"></i>${esc(this._t("legend_buy_line"))}</span>` : ""}
    </div>`;

    this.shadowRoot.innerHTML = `<style>${BASE_CSS}
      .now { display: flex; flex-direction: column; gap: 2px; flex-grow: 1; min-width: 0; }
      .big { font-size: 28px; font-weight: 700; line-height: 1.1; white-space: nowrap; }
      .big small { font-size: 13px; font-weight: 500; color: var(--secondary-text-color, #a0a0a0); }
      .ext { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
      .xp { display: flex; align-items: center; gap: 6px; font-size: 12px; padding: 4px 10px; border-radius: 999px; white-space: nowrap; }
      .xl { flex-grow: 1; overflow: hidden; text-overflow: ellipsis; }
      @container (max-width: 420px) { .top { flex-direction: column; align-items: stretch; } }
    </style>
    <ha-card>
      <div class="top">
        <div class="now"><span class="dim" style="font-size:13px">${title} \u00b7 ${esc(this._t("now"))}</span>
          <span class="big">${nowP === null ? "\u2013" : esc(f.money(nowP))}<small> ${esc(this._t("per_kwh"))}</small></span>
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
    </ha-card>`;
    this._windows = windows;
    this._wireTooltip((px) => this._showTip(px));
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
    const i = clamp(Math.floor(px / g.bw), 0, g.n - 1);
    const t = g.T0 + i * g.unitMs;
    const p = this._prices.prices[i];
    const b = this._prices.buy[i];
    const xx = g.xi(i) + g.bw / 2;
    cross.innerHTML = `<line x1="${r1(xx)}" y1="${g.top}" x2="${r1(xx)}" y2="${g.bottom}" style="stroke:var(--primary-text-color, #e8e8e8)" stroke-opacity="0.7" stroke-dasharray="3 3"/>${
      p === null ? "" : `<circle cx="${r1(xx)}" cy="${r1(g.y(p))}" r="4" style="fill:var(--primary-text-color, #e8e8e8)" stroke="rgba(0,0,0,.5)" stroke-width="1.5"/>`
    }`;
    const w = (this._windows || []).find((win) => t + g.unitMs > win.start && t < win.stop);
    let html = `<div class="row"><b>${esc(f.dayLabel(t))} \u00b7 ${esc(f.time(t))}\u2013${esc(f.time(t + g.unitMs))}</b></div>`;
    if (p !== null) html += `<div class="row"><span class="k">${esc(this._t("price"))}</span><b>${esc(f.money(p))}</b></div>`;
    if (b !== null && b !== p) html += `<div class="row"><span class="k">${esc(this._t("buy_price"))}</span><b>${esc(f.money(b))}</b></div>`;
    if (w) html += `<div class="row sep"><span class="k">${esc(planLabel(this._hass, w))}</span><b>${esc(f.time(w.start))}\u2013${esc(f.time(w.stop))}</b></div>`;
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
const STATUS_DEFAULTS = {
  title: "ESS Manager",
  automation: "",
  hours: 24,
  show_history: true,
  sell_color: [255, 107, 107],
  buy_color: [79, 163, 247],
  spike_color: [255, 179, 0],
  negative_color: [77, 208, 225],
};
const STATUS_COLOR_KEYS = ["sell_color", "buy_color", "spike_color", "negative_color"];
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
// The timeline: calm blue / red for normal charging / discharging, intense
// blue / red for the faster negative price charge / spike discharge.
const TIMELINE_COLORS = {
  idle: "#3b3b3b",
  charge: "#24527f",
  negative_price_charge: "#2f8cff",
  discharge: "#7a2f2f",
  spike_discharge: "#ff4545",
};

class EssManagerStatusCard extends HTMLElement {
  static get info() {
    return {
      name: "ESS Manager - Status",
      description: "Sell and buy plans with progress, price plans, control toggle and timeline.",
      schema: STATUS_SCHEMA,
      defaults: STATUS_DEFAULTS,
      labels: {
        title: "ed_title", automation: "ed_automation", hours: "ed_hours", show_history: "ed_show_history",
        sell_color: "ed_sell_color", buy_color: "ed_buy_color", spike_color: "ed_spike_color", negative_color: "ed_negative_plan_color",
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
  }

  disconnectedCallback() {
    clearInterval(this._timer);
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
      full_charge: [this._t("balancing"), "#b39ddb", "balancing"],
    }[plan.source];
    const outline = plan && (plan.source === "spike" || plan.source === "negative_price") ? chipInfo[1] : "transparent";
    const head = `<div class="head"><span class="name" style="color:${color}">${icon(sell ? "up" : "down", color, 16, 2.2)}${sell ? "Sell" : "Buy"}</span>${
      chipInfo ? `<span class="chip" style="background:${tint(chipInfo[1], 0.18)};color:${chipInfo[1]}">${icon(chipInfo[2], chipInfo[1], 12, 2.4)}${esc(chipInfo[0])}</span>` : ""
    }</div>`;
    if (!plan) {
      return `<div class="block" style="border-color:transparent">${head}<div class="empty">${esc(this._t(sell ? "no_sell" : "no_buy"))}</div></div>`;
    }
    const minutes = (new Date(plan.stop) - new Date(plan.start)) / 60000;
    const energy = plan.energy_kwh || 0;
    const progress = energy > 0 ? Math.min(Math.max(plan.done_kwh / energy, 0), 1) : 0;
    let inBar;
    let below;
    if (plan.target_reached) {
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
    const fill = plan.target_reached ? 100 : plan.started ? progress * 100 : 0;
    const soc = plan.target_soc_percent;
    return `<div class="block" style="border-color:${outline}">${head}
      <div class="times"><span>${esc(this._time(plan.start))}</span><span>${esc(this._time(plan.stop))}</span></div>
      <div class="bar" style="background:${tint(color, 0.22)}"><div class="fill" style="width:${fill.toFixed(1)}%;background:${color}"></div><div class="bartext">${inBar}</div></div>
      <div class="below"><span>${below}</span><span>${esc(this._t("stop"))}</span></div>
      <div class="stat">${icon("bolt", color, 16)}<b>${this._num(energy, 1)}</b><span class="dim">kWh</span><span class="dim arrow">\u2192</span>${
        soc == null ? "" : `${batteryIcon(soc, color)}<b>${this._num(soc, 0)} %</b>`
      }</div>
    </div>`;
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
      this.shadowRoot.innerHTML = notStatusMessage(this._hass, this._config.entity, stateObj);
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
    const dot = { charge: opt.buy_color, negative_price_charge: opt.buy_color, discharge: opt.sell_color, spike_discharge: opt.sell_color }[action] || "#8a8a8a";

    let toggle = "";
    if (toggleObj) {
      const on = toggleObj.state === "on";
      const isOwn = !this._config.automation;
      const label = isOwn ? this._t("auto_control") : toggleObj.attributes.friendly_name || toggleId;
      toggle = `<div class="toggle">${icon("robot", "#a0a0a0", 18)}<span class="tlabel">${esc(label)}</span>
        <button type="button" class="switch ${on ? "on" : ""}" aria-pressed="${on}" aria-label="${esc(label)}" style="background:${on ? opt.buy_color : "#4a4a4a"}"><span></span></button></div>`;
    }

    let timeline = "";
    if (opt.show_history && actionId) {
      const segs = this._history || [];
      const total = segs.reduce((sum, seg) => sum + seg.seconds, 0);
      const parts = total
        ? segs.map((seg) => `<span style="flex:${seg.seconds} 0 0;background:${TIMELINE_COLORS[seg.state] || "#2a2a2a"}"></span>`).join("")
        : `<span style="flex:1 0 0;background:#2a2a2a"></span>`;
      const hours = opt.hours;
      timeline = `<div class="timeline">${parts}</div>
        <div class="axis"><span>${esc(this._t("ago")(hours))}</span><span>${esc(this._t("ago")(Math.round(hours / 2)))}</span><span>${esc(this._t("now"))}</span></div>`;
    }

    this.shadowRoot.innerHTML = `<style>
      ha-card { padding: 16px; display: flex; flex-direction: column; gap: 14px; container-type: inline-size; }
      .top { display: flex; align-items: center; gap: 10px; }
      .title { font-size: 17px; font-weight: 600; flex-grow: 1; }
      .status { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--secondary-text-color, #a0a0a0); }
      .status i { width: 8px; height: 8px; border-radius: 999px; display: inline-block; }
      .blocks, .tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
      @container (max-width: 380px) { .blocks, .tiles { grid-template-columns: minmax(0, 1fr); } }
      .block { display: flex; flex-direction: column; gap: 10px; border: 2px solid transparent; border-radius: 12px; padding: 8px; }
      .head { display: flex; align-items: center; gap: 6px; }
      .name { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; flex-grow: 1; }
      .chip { display: flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
      .empty { font-size: 13px; color: var(--secondary-text-color, #a0a0a0); padding: 18px 0; text-align: center; }
      .times, .below { display: flex; justify-content: space-between; }
      .times { font-size: 13px; }
      .below { font-size: 11px; color: var(--secondary-text-color, #a0a0a0); }
      .bar { position: relative; height: 22px; border-radius: 6px; overflow: hidden; }
      .fill { position: absolute; left: 0; top: 0; bottom: 0; }
      .bartext { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: 4px; font-size: 12px; font-weight: 600; color: #ffffff; text-shadow: 0 0 3px rgba(0,0,0,.6); }
      .stat { display: flex; align-items: center; gap: 6px; white-space: nowrap; background: rgba(127,127,127,.12); border-radius: 10px; padding: 7px 10px; }
      .stat b { font-size: 15px; }
      .dim { font-size: 12px; color: var(--secondary-text-color, #a0a0a0); }
      .arrow { font-size: 13px; padding: 0 2px; }
      .batt { width: 22px; height: 12px; border: 2px solid var(--secondary-text-color, #a0a0a0); border-radius: 3px; padding: 1px; box-sizing: border-box; display: inline-flex; flex-shrink: 0; }
      .batt span { border-radius: 1px; }
      .tile { border-radius: 10px; padding: 10px 12px; display: flex; align-items: center; gap: 10px; }
      .col { display: flex; flex-direction: column; min-width: 0; }
      .tname { font-size: 13px; font-weight: 600; }
      .tdetail { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .toggle { display: flex; align-items: center; gap: 10px; border-top: 1px solid rgba(127,127,127,.2); padding-top: 10px; }
      .tlabel { font-size: 13px; flex-grow: 1; }
      .switch { width: 44px; height: 26px; border-radius: 999px; border: none; position: relative; padding: 0; cursor: pointer; }
      .switch span { position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 999px; background: #ffffff; transition: left .15s; }
      .switch.on span { left: 21px; }
      .timeline { display: flex; height: 14px; border-radius: 999px; overflow: hidden; }
      .axis { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color, #a0a0a0); margin-top: -8px; }
    </style>
    <ha-card>
      <div class="top"><span class="title">${esc(opt.title)}</span><span class="status"><i style="background:${dot}"></i>${esc(stateObj.state)}</span></div>
      <div class="blocks">${this._block("sell", plans.sell, opt)}${this._block("buy", plans.buy, opt)}</div>
      <div class="tiles">${this._planTile("spike", attrs.spike_plan, opt)}${this._planTile("negative", attrs.negative_price_plan, opt)}</div>
      ${toggle}
      ${timeline}
    </ha-card>`;
    const button = this.shadowRoot.querySelector(".switch");
    if (button) {
      button.addEventListener("click", () => this._hass.callService("homeassistant", "toggle", { entity_id: toggleId }));
    }
  }
}

// -- Registration -------------------------------------------------------------------
if (!customElements.get("ess-manager-card-editor")) {
  customElements.define("ess-manager-card-editor", EssManagerCardEditor);
}
window.customCards = window.customCards || [];
for (const [type, cls] of [
  ["ess-manager-status-card", EssManagerStatusCard],
  ["ess-manager-battery-card", EssManagerBatteryCard],
  ["ess-manager-price-card", EssManagerPriceCard],
]) {
  if (customElements.get(type)) continue;
  customElements.define(type, cls);
  window.customCards.push({ type, name: cls.info.name, description: cls.info.description, preview: true, documentationURL: DOCS_URL });
}
console.info("%c ESS Manager cards %c loaded ", "color:#fff;background:#4caf50", "");
