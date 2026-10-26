"""The phone notifications of the Victron EV charger (as of 2026.10.27) -
pure Python: the texts (English / Dutch, by Home Assistant's language) and
the payload for the Home Assistant Companion app's notify service, with
buttons or a reply field (actionable notifications). The answer comes back
as a `mobile_app_notification_action` event with the action id (and
`reply_text` for the reply field).

Action ids: "ESSEV:<entry id>:<token>:<what>" - the token is the
conversation's, so a tap on an old notification does nothing.
"""
from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any, Optional

PREFIX = "ESSEV"
# Android shows at most three buttons; more cars than this are typed
MAX_BUTTONS = 3

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Electric car",
        "connected": "{car} is plugged in. What should happen?",
        "connected_nocar": "A car is plugged in. What should happen?",
        "asap": "As fast as possible",
        "calm": "Slowly now",
        "deadline": "Full by a time",
        "which_car": "A car is plugged in. Which one?",
        "which_car_typed": "A car is plugged in. Which one? Type its number or name:\n{list}",
        "day": "Full by when?",
        "today": "Today",
        "tomorrow": "Tomorrow",
        "any": "Doesn't matter",
        "hour": "At what time should it be full ({day})? E.g. 7 or 7:30",
        "hour_past": "That time has passed - at what time should it be full ({day})?",
        "soc": "What is the car's state of charge now (%)?",
        "kwh": "How much energy (kWh) should go in?",
        "bad": "Couldn't read that. ",
        "reply": "Answer",
        "send": "Send",
        "ph_soc": "e.g. 45",
        "ph_kwh": "e.g. 20",
        "ph_hour": "e.g. 7:00",
        "ph_car": "e.g. 1",
        "plan_asap": "Charging at full speed ({kw} kW): {kwh} kWh, full at about {end}.",
        "plan_calm": "Charging slowly ({kw} kW): {kwh} kWh, full at about {end}.",
        "plan_deadline": "Full by {deadline}: {kwh} kWh - {solar} kWh expected from the sun, {grid} kWh bought in the cheapest hours at {amps} A{windows}. Full at about {end} (an hour to spare).",
        "plan_tight": "Full by {deadline} doesn't fit, not even at full power: {kwh} kWh needed, {reach} kWh in by then{pct}. Charging at full power, full at about {end}.",
        "plan_solar": "Charging on the solar surplus only: {kwh} kWh as far as the sun allows.",
        "plan_short": "Full by {deadline} doesn't fit: {kwh} kWh needed, {short} kWh short. Charging as much as possible{windows}.",
        "plan_any": "Charging on the sun first, the rest in the cheapest hours known: {kwh} kWh{windows}, full at about {end}.",
        "plan_unknown_end": "not known yet",
        "windows": " ({list})",
        "morning": "A charging session is planned today at {time} ({kwh} kWh). Still right?",
        "adopted": "{car} is plugged in - the planned session is taken over: {plan}, {kwh} kWh. Is that right?",
        "other": "Something else",
        "w_deadline": "full by {t}",
        "w_solar": "on the solar surplus",
        "w_calm": "slowly",
        "w_asap": "as fast as possible",
        "yes": "Yes",
        "no": "No",
        "morning_soc": "Charging at {time}: what will the car's state of charge be (%)?",
        "morning_kwh": "Charging at {time}: how much energy (kWh) should go in?",
        "morning_removed": "The session at {time} is removed.",
        "morning_set": "Session at {time}: {kwh} kWh.",
    },
    "nl": {
        "title": "Elektrische auto",
        "connected": "{car} is aangesloten. Wat moet er gebeuren?",
        "connected_nocar": "Er is een auto aangesloten. Wat moet er gebeuren?",
        "asap": "Zo snel mogelijk",
        "calm": "Nu rustig",
        "deadline": "Vol voor tijd X",
        "which_car": "Er is een auto aangesloten. Welke?",
        "which_car_typed": "Er is een auto aangesloten. Welke? Typ het nummer of de naam:\n{list}",
        "day": "Wanneer moet hij vol zijn?",
        "today": "Vandaag",
        "tomorrow": "Morgen",
        "any": "Maakt niet uit",
        "hour": "Hoe laat moet hij vol zijn ({day})? Bijv. 7 of 7:30",
        "hour_past": "Die tijd is al voorbij - hoe laat moet hij vol zijn ({day})?",
        "soc": "Wat is de laadstand van de auto nu (%)?",
        "kwh": "Hoeveel energie (kWh) moet erin?",
        "bad": "Dat kon ik niet lezen. ",
        "reply": "Antwoord",
        "send": "Verstuur",
        "ph_soc": "bijv. 45",
        "ph_kwh": "bijv. 20",
        "ph_hour": "bijv. 7:00",
        "ph_car": "bijv. 1",
        "plan_asap": "Laden op vol vermogen ({kw} kW): {kwh} kWh, vol rond {end}.",
        "plan_calm": "Rustig laden ({kw} kW): {kwh} kWh, vol rond {end}.",
        "plan_deadline": "Vol om {deadline}: {kwh} kWh - {solar} kWh verwacht van de zon, {grid} kWh ingekocht in de goedkoopste uren op {amps} A{windows}. Vol rond {end} (een uur speling).",
        "plan_tight": "Vol om {deadline} lukt niet, ook niet op vol vermogen: {kwh} kWh nodig, {reach} kWh op tijd{pct}. Laden op vol vermogen, vol rond {end}.",
        "plan_solar": "Laden op zon-overschot: {kwh} kWh zover de zon het toelaat.",
        "plan_short": "Vol om {deadline} past niet: {kwh} kWh nodig, {short} kWh tekort. Laden zoveel als kan{windows}.",
        "plan_any": "Eerst op de zon, de rest in de goedkoopste bekende uren: {kwh} kWh{windows}, vol rond {end}.",
        "plan_unknown_end": "nog niet bekend",
        "windows": " ({list})",
        "morning": "Er staat vandaag om {time} een laadsessie gepland ({kwh} kWh). Klopt dat nog?",
        "adopted": "{car} is aangesloten - de geplande sessie is overgenomen: {plan}, {kwh} kWh. Klopt dat?",
        "other": "Anders",
        "w_deadline": "vol om {t}",
        "w_solar": "op zon-overschot",
        "w_calm": "rustig",
        "w_asap": "zo snel mogelijk",
        "yes": "Ja",
        "no": "Nee",
        "morning_soc": "Laden om {time}: wat wordt de laadstand van de auto (%)?",
        "morning_kwh": "Laden om {time}: hoeveel energie (kWh) moet erin?",
        "morning_removed": "De sessie van {time} is verwijderd.",
        "morning_set": "Sessie van {time}: {kwh} kWh.",
    },
}


def lang(language: Optional[str]) -> str:
    return "nl" if (language or "").lower().startswith("nl") else "en"


def t(language: str, key: str, **values: Any) -> str:
    return TEXTS[language][key].format(**values)


def action_id(entry_id: str, token: str, what: str) -> str:
    return f"{PREFIX}:{entry_id}:{token}:{what}"


def parse_action(action: Any) -> Optional[tuple[str, str, str]]:
    """(entry id, token, what) of one of our action ids, None otherwise."""
    if not isinstance(action, str) or not action.startswith(PREFIX + ":"):
        return None
    parts = action.split(":", 3)
    if len(parts) != 4:
        return None
    return parts[1], parts[2], parts[3]


def clock(epoch: Optional[int], tz: tzinfo, now_epoch: Optional[int] = None, language: str = "en") -> str:
    """"18:45", or with the day when it isn't today ("Tue 07:00" / "di 07:00")."""
    if epoch is None:
        return t(language, "plan_unknown_end")
    when = datetime.fromtimestamp(int(epoch), tz)
    if now_epoch is not None and when.date() != datetime.fromtimestamp(int(now_epoch), tz).date():
        days = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "nl": ["ma", "di", "wo", "do", "vr", "za", "zo"]}
        return f"{days[language][when.weekday()]} {when:%H:%M}"
    return f"{when:%H:%M}"


def windows_text(windows: list[list[int]], tz: tzinfo, now_epoch: int, language: str) -> str:
    if not windows:
        return ""
    parts = [f"{clock(a, tz, now_epoch, language)}-{datetime.fromtimestamp(int(b), tz):%H:%M}" for a, b in windows[:4]]
    if len(windows) > 4:
        parts.append("...")
    return t(language, "windows", list=", ".join(parts))


def buttons(entry_id: str, token: str, items: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"action": action_id(entry_id, token, what), "title": title} for what, title in items]


def reply(entry_id: str, token: str, what: str, language: str, placeholder_key: str) -> list[dict[str, Any]]:
    return [
        {
            "action": action_id(entry_id, token, what),
            "title": t(language, "reply"),
            "behavior": "textInput",
            "textInputButtonTitle": t(language, "send"),
            "textInputPlaceholder": t(language, placeholder_key),
        }
    ]


def payload(language: str, message: str, tag: str, actions: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """The notify service call data."""
    data: dict[str, Any] = {"tag": tag, "group": "ess_manager_ev"}
    if actions:
        data["actions"] = actions
    return {"title": t(language, "title"), "message": message, "data": data}


def clear(tag: str) -> dict[str, Any]:
    return {"message": "clear_notification", "data": {"tag": tag}}
