"""MCP adapter over the same engine.

The REST API serves the console UI. This exposes the identical tools over the Model
Context Protocol, so the advisor is usable from any MCP client -- Claude Desktop, an IDE,
another agent -- without a second implementation of anything.

Every function here is a thin typed wrapper whose only job is to give the MCP SDK a
signature to build a schema from. The body always delegates to `app.llm.tools.dispatch`,
so there is exactly one rules engine, one cost model and one source of truth behind both
doors.

Run:
    python mcp_server/index.py          (or: python -m mcp_server.index)

Claude Desktop config -- note the ABSOLUTE SCRIPT PATH:
    {"mcpServers": {"crew-ops": {
        "command": "<repo>/backend/.venv/Scripts/python.exe",
        "args": ["<repo>/backend/mcp_server/index.py"]}}}

Do NOT use `"args": ["-m", "mcp_server.index"]` there. Claude Desktop launches the
process without applying a working directory, so the module form cannot resolve the
package and the server dies instantly with "Server disconnected". Everything this file
touches is resolved from __file__, so the absolute script path works from anywhere.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Works whether launched as a script or with -m, and regardless of the caller's cwd.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import DB_PATH  # noqa: E402
from app.db.repository import get_repository  # noqa: E402
from app.llm import tools as tool_mod  # noqa: E402

try:
    from mcp.server import MCPServer
except ImportError:  # pragma: no cover - optional dependency
    print(
        "The MCP SDK is not installed. Install it with:  pip install mcp\n"
        "The REST API in app/main.py does not need it.",
        file=sys.stderr,
    )
    raise SystemExit(1)

if not DB_PATH.exists():
    # An MCP client shows only "Server disconnected", so say what is actually wrong
    # on stderr where the client's log will capture it.
    print(
        f"No operational database at {DB_PATH}.\n"
        f"Build it first:  cd {BACKEND_DIR} && python scripts/import_data.py",
        file=sys.stderr,
    )
    raise SystemExit(1)

server = MCPServer(name="crew-ops-advisor", version="1.0.0")

DESCRIPTIONS = {spec["name"]: spec["description"] for spec in tool_mod.TOOL_SPECS}


def _run(name: str, **arguments) -> str:
    """Execute an engine tool and return its result plus the evidence behind it."""
    arguments = {k: v for k, v in arguments.items() if v is not None}
    result = tool_mod.dispatch(get_repository(), name, arguments)
    return json.dumps(
        {
            "summary": result.summary,
            "confidence": result.confidence,
            "tier": result.tier,
            "data": result.data,
            "table": result.table,
            # the evidence travels with the answer so an MCP client can audit it too
            "evidence": result.ledger.to_list(),
        },
        indent=2,
        default=str,
    )


# --------------------------------------------------------------- Tier 1 lookups

def get_crew_profile(crew_id: str) -> str:
    return _run("get_crew_profile", crew_id=crew_id)


def get_crew_roster(crew_id: str, date: str | None = None) -> str:
    return _run("get_crew_roster", crew_id=crew_id, date=date)


def search_crew(rank: str | None = None, base: str | None = None,
                rating: str | None = None) -> str:
    return _run("search_crew", rank=rank, base=base, rating=rating)


def get_reserves(date: str, base: str | None = None, rank: str | None = None,
                 callout_utc: str | None = None) -> str:
    return _run("get_reserves", date=date, base=base, rank=rank, callout_utc=callout_utc)


def get_duty_clock(crew_id: str, date: str | None = None) -> str:
    return _run("get_duty_clock", crew_id=crew_id, date=date)


def find_crew_near_duty_limit(date: str, threshold_hours: float) -> str:
    return _run("find_crew_near_duty_limit", date=date, threshold_hours=threshold_hours)


def search_flights(date: str | None = None, dep_station: str | None = None,
                   arr_station: str | None = None, flight_no: str | None = None,
                   tail: str | None = None) -> str:
    return _run("search_flights", date=date, dep_station=dep_station,
                arr_station=arr_station, flight_no=flight_no, tail=tail)


def get_expiring_certifications(date: str, within_days: int = 30) -> str:
    return _run("get_expiring_certifications", date=date, within_days=within_days)


def get_pairing(pairing_id: str) -> str:
    return _run("get_pairing", pairing_id=pairing_id)


def get_earliest_report(release_utc: str, date: str) -> str:
    return _run("get_earliest_report", release_utc=release_utc, date=date)


# ------------------------------------------------------- Tier 2 / 3 reasoning

def analyse_disruption(sick_crew_ids: list[str] | None = None,
                       closed_station: str | None = None,
                       closure_date: str | None = None,
                       closure_start_utc: str | None = None,
                       closure_end_utc: str | None = None,
                       delayed_flight_id: str | None = None,
                       delay_hours: float | None = None) -> str:
    return _run("analyse_disruption", sick_crew_ids=sick_crew_ids,
                closed_station=closed_station, closure_date=closure_date,
                closure_start_utc=closure_start_utc, closure_end_utc=closure_end_utc,
                delayed_flight_id=delayed_flight_id, delay_hours=delay_hours)


def check_assignment_legality(crew_id: str, pairing_id: str) -> str:
    return _run("check_assignment_legality", crew_id=crew_id, pairing_id=pairing_id)


def get_cancellation_impact(flight_ids: list[str]) -> str:
    return _run("get_cancellation_impact", flight_ids=flight_ids)


def recommend_recovery(pairing_id: str, role: str, crew_out: str | None = None) -> str:
    return _run("recommend_recovery", pairing_id=pairing_id, role=role, crew_out=crew_out)


def get_alerts(date: str | None = None) -> str:
    return _run("get_alerts", date=date)


def draft_crew_notification(crew_id: str, pairing_id: str) -> str:
    return _run("draft_crew_notification", crew_id=crew_id, pairing_id=pairing_id)


TOOLS = [
    get_crew_profile, get_crew_roster, search_crew, get_reserves, get_duty_clock,
    find_crew_near_duty_limit, search_flights, get_expiring_certifications,
    get_pairing, analyse_disruption, check_assignment_legality,
    get_cancellation_impact, recommend_recovery, get_earliest_report,
    get_alerts, draft_crew_notification,
]

for _fn in TOOLS:
    server.add_tool(_fn, name=_fn.__name__, description=DESCRIPTIONS.get(_fn.__name__))


if __name__ == "__main__":
    server.run(transport="stdio")
