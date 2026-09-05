"""The tool surface the model is allowed to call.

Every tool is a deterministic engine operation. The model chooses WHICH to call and with
what arguments; it never computes the answer itself. Note that no tool accepts a duty
hour, a cost or a legality verdict as input -- those only ever come out.
"""
from __future__ import annotations

from datetime import date

from app.alerts.sentinel import build_alerts
from app.engine.state import BASE_STATE
from app.services import actions as A
from app.services import lookups as L
from app.services.lookups import ToolResult

_DATE = {"type": "string", "description": "UTC date, YYYY-MM-DD"}
_CREW = {"type": "string", "description": "Crew id, e.g. C-1042"}
_PAIRING = {"type": "string", "description": "Pairing id, e.g. P-2291"}
_ROLE = {
    "type": "string",
    "enum": ["Captain", "First Officer", "Senior Cabin Crew", "Cabin Crew"],
}


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


TOOL_SPECS: list[dict] = [
    {
        "name": "get_crew_profile",
        "description": "Full profile for one crew member: rank, base, ratings, "
                       "reachability, reserve window, duty clocks, risk score, pairings.",
        "parameters": {"type": "object", "properties": {"crew_id": _CREW},
                       "required": ["crew_id"]},
    },
    {
        "name": "get_crew_roster",
        "description": "What one crew member is rostered to fly on ONE date: pairings, "
                       "sectors, report and release times, duty hours. Use this for "
                       "'what is X flying tomorrow' rather than the profile tool.",
        "parameters": {"type": "object", "properties": {
            "crew_id": _CREW,
            "date": {"type": "string", "description": "ISO date, e.g. 2026-09-15"},
        }, "required": ["crew_id"]},
    },
    {
        "name": "search_crew",
        "description": "Find crew by rank, base and/or aircraft rating.",
        "parameters": {"type": "object", "properties": {
            "rank": _ROLE,
            "base": {"type": "string", "description": "Station code, e.g. BLR"},
            "rating": {"type": "string", "description": "Aircraft type, e.g. A320"},
        }},
    },
    {
        "name": "get_reserves",
        "description": "Reserve crew on call for a date, optionally filtered by base, "
                       "rank, and whether their window covers a given callout time.",
        "parameters": {"type": "object", "properties": {
            "date": _DATE, "base": {"type": "string"}, "rank": _ROLE,
            "callout_utc": {"type": "string", "description": "HH:MM UTC"},
        }, "required": ["date"]},
    },
    {
        "name": "get_duty_clock",
        "description": "Duty hours in the 7 calendar days and block hours in the 28 "
                       "calendar days ending on a date, with headroom under each rule.",
        "parameters": {"type": "object", "properties": {"crew_id": _CREW, "date": _DATE},
                       "required": ["crew_id"]},
    },
    {
        "name": "find_crew_near_duty_limit",
        "description": "Crew at or above a duty-hour threshold for the 7 days ending on a date.",
        "parameters": {"type": "object", "properties": {
            "date": _DATE, "threshold_hours": {"type": "number"},
        }, "required": ["date", "threshold_hours"]},
    },
    {
        "name": "search_flights",
        "description": "Query the schedule by date, departure/arrival station, flight "
                       "number or tail.",
        "parameters": {"type": "object", "properties": {
            "date": _DATE, "dep_station": {"type": "string"}, "arr_station": {"type": "string"},
            "flight_no": {"type": "string"}, "tail": {"type": "string"},
        }},
    },
    {
        "name": "get_expiring_certifications",
        "description": "Certifications expiring within N days of a date.",
        "parameters": {"type": "object", "properties": {
            "date": _DATE, "within_days": {"type": "integer"},
        }, "required": ["date"]},
    },
    {
        "name": "get_pairing",
        "description": "A pairing's crew, roles, days and legs.",
        "parameters": {"type": "object", "properties": {"pairing_id": _PAIRING},
                       "required": ["pairing_id"]},
    },
    {
        "name": "analyse_disruption",
        "description": "Tier 2/3. Apply one or more disruptions to a copy of the "
                       "operation and report what breaks: uncovered legs, broken "
                       "pairings, downstream rule breaches, passengers affected. For a "
                       "STATION CLOSURE it returns the complete plan -- per-leg minimum "
                       "delay to reopen, crew FDP after that delay against the limit, and "
                       "costed options (delay / re-crew the tail / cancel) -- so no "
                       "further tool call is needed. Never mutates the real roster.",
        "parameters": {"type": "object", "properties": {
            "sick_crew_ids": {"type": "array", "items": _CREW},
            "closed_station": {"type": "string"},
            "closure_date": _DATE,
            "closure_start_utc": {"type": "string", "description": "HH:MM"},
            "closure_end_utc": {"type": "string", "description": "HH:MM"},
            "delayed_flight_id": {"type": "string"},
            "delay_hours": {"type": "number"},
        }},
    },
    {
        "name": "check_assignment_legality",
        "description": "Tier 2. Would assigning this crew member to this pairing be "
                       "legal? Returns a rule-by-rule verdict with actuals, limits and "
                       "margins, plus before/after duty position.",
        "parameters": {"type": "object", "properties": {
            "crew_id": _CREW, "pairing_id": _PAIRING,
        }, "required": ["crew_id", "pairing_id"]},
    },
    {
        "name": "get_cancellation_impact",
        "description": "Passengers affected and direct cost of cancelling specific legs.",
        "parameters": {"type": "object", "properties": {
            "flight_ids": {"type": "array", "items": {"type": "string"}},
        }, "required": ["flight_ids"]},
    },
    {
        "name": "recommend_recovery",
        "description": "Tier 3. Ranked, rule-checked recovery options for a vacancy, "
                       "including multi-step swap chains, costs, coverage, resilience and "
                       "why each rejected candidate was rejected.",
        "parameters": {"type": "object", "properties": {
            "pairing_id": _PAIRING, "role": _ROLE, "crew_out": _CREW,
            "sectors_flown": {
                "type": "integer",
                "description": "Sectors already operated when the crew member became "
                               "unavailable. Use only for a mid-duty callout ('sick "
                               "after the second sector'); omit for an ordinary one, "
                               "where the whole pairing is vacant.",
            },
        }, "required": ["pairing_id", "role"]},
    },
    {
        "name": "get_earliest_report",
        "description": "Earliest legal next report after a release time (RULE-REST-04).",
        "parameters": {"type": "object", "properties": {
            "release_utc": {"type": "string", "description": "HH:MM"}, "date": _DATE,
        }, "required": ["release_utc", "date"]},
    },
    {
        "name": "get_alerts",
        "description": "Proactive operational signals for a date: duty headroom, "
                       "certification expiry, reserve depth, thin cover, provided risk scores.",
        "parameters": {"type": "object", "properties": {"date": _DATE}},
    },
    {
        "name": "draft_crew_notification",
        "description": "Draft the callout message for a crew member on a pairing.",
        "parameters": {"type": "object", "properties": {
            "crew_id": _CREW, "pairing_id": _PAIRING,
        }, "required": ["crew_id", "pairing_id"]},
    },
]


TOOL_TIERS: dict[str, int] = {
    "get_crew_profile": 1,
    "get_crew_roster": 1,
    "search_crew": 1,
    "get_reserves": 1,
    "get_duty_clock": 1,
    "find_crew_near_duty_limit": 1,
    "search_flights": 1,
    "get_expiring_certifications": 1,
    "get_pairing": 1,
    "get_earliest_report": 1,
    "analyse_disruption": 2,
    "check_assignment_legality": 2,
    "get_cancellation_impact": 2,
    "get_alerts": 2,
    "recommend_recovery": 3,
    "draft_crew_notification": 3,
}


def tool_catalogue() -> list[dict]:
    """Name, tier and description for every tool, for the UI and for MCP clients."""
    return [
        {
            "name": spec["name"],
            "tier": TOOL_TIERS.get(spec["name"], 1),
            "description": spec["description"],
        }
        for spec in TOOL_SPECS
    ]


# Which tools are worth offering for which shape of question. Sending all fifteen every
# round costs ~1,500 tokens of schema and gives the model fifteen ways to go wrong; the
# deterministic layer already knows roughly what is being asked, so it narrows the menu
# and the model chooses within it. Fewer distractors, faster answers, far fewer tokens.
_BUCKETS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("sick", "unavailable", "out for", "is out", "what should i do", "options",
         "recommend", "resolve", "recovery", "cheapest", "cover", "callout", "plan"),
        ("recommend_recovery", "analyse_disruption", "check_assignment_legality",
         "get_reserves", "get_pairing", "draft_crew_notification"),
    ),
    (
        ("closed", "closure", "delay", "delayed", "uncrewed", "uncovered", "affected",
         "impact", "breaks", "cancel", "cancelled", "at risk"),
        ("analyse_disruption", "get_cancellation_impact", "recommend_recovery",
         "get_pairing", "check_assignment_legality", "search_flights"),
    ),
    (
        ("legal", "legally", "breach", "can ", "may ", "what if", "move ", "assign"),
        ("check_assignment_legality", "get_duty_clock", "get_pairing",
         "get_crew_profile", "recommend_recovery"),
    ),
    (
        ("brief", "worry", "risky", "alert", "watch", "expire", "expiring",
         "certification", "licence", "license", "medical"),
        ("get_alerts", "get_expiring_certifications", "find_crew_near_duty_limit",
         "get_crew_profile"),
    ),
    (
        ("reserve", "on call", "standby"),
        ("get_reserves", "get_crew_profile", "get_pairing", "check_assignment_legality"),
    ),
    (
        ("duty hours", "flight hours", "block hours", "headroom", "clock", "accrued"),
        ("get_duty_clock", "find_crew_near_duty_limit", "get_crew_profile"),
    ),
    (
        ("flight", "depart", "arriv", "schedule", "leg", "aircraft", "seats", "block"),
        ("search_flights", "get_pairing", "get_cancellation_impact"),
    ),
    (
        ("draft", "notify", "notification", "message"),
        ("draft_crew_notification", "get_pairing", "recommend_recovery"),
    ),
    (
        ("rest", "earliest", "next report"),
        ("get_earliest_report", "get_duty_clock"),
    ),
]

# Offered when nothing matches, and topped up onto every subset.
_CORE = ("get_crew_profile", "get_crew_roster", "get_pairing", "search_flights", "get_reserves",
         "recommend_recovery", "analyse_disruption")

MAX_TOOLS = 7

_BY_NAME = {spec["name"]: spec for spec in TOOL_SPECS}


def relevant_tools(question: str) -> list[str]:
    """Narrow the toolset to what this question could plausibly need."""
    low = question.lower()
    chosen: list[str] = []
    for triggers, names in _BUCKETS:
        if any(t in low for t in triggers):
            for name in names:
                if name not in chosen:
                    chosen.append(name)
    if not chosen:
        chosen = list(_CORE)
    return chosen[:MAX_TOOLS]


def openai_schema(question: str | None = None) -> list[dict]:
    """Tool schema for the model. Pass the question to get the narrowed set."""
    names = relevant_tools(question) if question else [s["name"] for s in TOOL_SPECS]
    return [
        {"type": "function", "function": _BY_NAME[name]}
        for name in names if name in _BY_NAME
    ]


def dispatch(repo, name: str, args: dict) -> ToolResult:
    """Execute one tool call. Unknown tools fail loudly rather than silently."""
    from app.config import SNAPSHOT_UTC
    from app.domain.time_utils import time_on_date

    default_date = SNAPSHOT_UTC.date()

    if name == "get_crew_profile":
        return L.crew_profile(repo, args["crew_id"])

    if name == "get_crew_roster":
        return L.crew_roster_on(repo, args["crew_id"], _d(args.get("date")) or default_date)

    if name == "search_crew":
        return L.crew_search(repo, args.get("rank"), args.get("base"), args.get("rating"))

    if name == "get_reserves":
        on = _d(args.get("date")) or default_date
        report = time_on_date(on, args["callout_utc"]) if args.get("callout_utc") else None
        return L.reserves_on_date(repo, on, args.get("base"), args.get("rank"), report)

    if name == "get_duty_clock":
        return L.duty_clock(repo, args["crew_id"], _d(args.get("date")))

    if name == "find_crew_near_duty_limit":
        return L.crew_near_limit(repo, _d(args["date"]) or default_date,
                                 float(args["threshold_hours"]))

    if name == "search_flights":
        return L.flights_query(
            repo, _d(args.get("date")), args.get("dep_station"), args.get("arr_station"),
            args.get("flight_no"), args.get("tail"),
        )

    if name == "get_expiring_certifications":
        return L.expiring_certifications(
            repo, _d(args.get("date")) or default_date, int(args.get("within_days", 30))
        )

    if name == "get_pairing":
        return L.pairing_detail(repo, args["pairing_id"])

    if name == "analyse_disruption":
        state = BASE_STATE
        for crew_id in args.get("sick_crew_ids") or []:
            state = state.with_crew_unavailable(crew_id, "unavailable")
        if args.get("closed_station"):
            on = _d(args.get("closure_date")) or default_date
            state = state.with_station_closure(
                args["closed_station"],
                time_on_date(on, args.get("closure_start_utc", "00:00")),
                time_on_date(on, args.get("closure_end_utc", "23:59")),
            )
        if args.get("delayed_flight_id"):
            state = state.with_flight_delay(
                args["delayed_flight_id"], float(args.get("delay_hours", 0))
            )
        if state.closures:
            # for a closure the per-leg delay/FDP assessment IS the impact, and it
            # carries the recovery options with it -- returning "legs uncovered" here
            # would send the model looking for replacement crew that nobody needs
            closure_result = A.recover_closure(repo, state)
            if closure_result is not None:
                return closure_result
        return A.analyse_impact(repo, state)

    if name == "check_assignment_legality":
        return A.assess_assignment(repo, args["crew_id"], args["pairing_id"])

    if name == "get_cancellation_impact":
        return A.cancellation_impact(repo, args["flight_ids"])

    if name == "recommend_recovery":
        return A.recommend_cover(repo, args["pairing_id"], args["role"],
                                 args.get("crew_out"),
                                 sectors_flown=args.get("sectors_flown"))

    if name == "get_earliest_report":
        return L.rest_calculator(repo, args["release_utc"], _d(args["date"]) or default_date)

    if name == "get_alerts":
        return build_alerts(repo, _d(args.get("date")))

    if name == "draft_crew_notification":
        return A.draft_notification(repo, args["crew_id"], args["pairing_id"])

    return ToolResult(
        summary=f"No such tool: {name}.", confidence="cannot_answer",
    )
