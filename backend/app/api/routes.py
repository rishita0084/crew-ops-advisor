"""HTTP surface. Thin by design -- routes translate, the engine decides."""
from __future__ import annotations

import time
from datetime import date

from fastapi import APIRouter, Query

from app.api import envelope
from app.api.schemas import (
    ChatRequest,
    ImpactRequest,
    RecommendRequest,
    SimulateRequest,
)
from app.alerts.sentinel import build_alerts
from app.db.repository import get_repository
from app.engine.state import BASE_STATE
from app.fallback import structured_query
from app.llm.orchestrator import answer as llm_answer
from app.services import actions as A

router = APIRouter()

# in-memory conversation history, keyed by session; multi-turn context only
_SESSIONS: dict[str, list[dict]] = {}
MAX_TURNS = 12


def _d(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


@router.get("/health")
def health() -> dict:
    from app.config import LLM_ENABLED, LLM_MODEL, LLM_PROVIDER

    repo = get_repository()
    return {
        "status": "ok",
        "crew": len(repo.crew),
        "flights": len(repo.flights),
        "pairings": len(repo.pairings),
        "llm_enabled": LLM_ENABLED,
        "llm_provider": LLM_PROVIDER if LLM_ENABLED else None,
        "llm_model": LLM_MODEL if LLM_ENABLED else None,
    }


@router.post("/chat")
def chat(body: ChatRequest) -> dict:
    repo = get_repository()
    history = _SESSIONS.setdefault(body.session_id or "anon", [])
    result = llm_answer(repo, body.question, history)

    history.append({"role": "user", "content": body.question})
    history.append({"role": "assistant", "content": result.text})
    del history[:-MAX_TURNS]

    return envelope.from_answer(body.question, result)


@router.post("/impact")
def impact(body: ImpactRequest) -> dict:
    """Tier 2 without the conversation: name the disruption, get the blast radius."""
    repo = get_repository()
    started = time.perf_counter()
    state = BASE_STATE
    label = []

    if body.crew_id:
        state = state.with_crew_unavailable(body.crew_id, "unavailable")
        label.append(body.crew_id)
    if body.flight_id:
        state = state.with_flight_delay(body.flight_id, 0.0)
        label.append(body.flight_id)

    result = A.analyse_impact(repo, state, _d(body.date))
    return envelope.from_tool(
        " ".join(label) or "impact", "impact",
        result, int((time.perf_counter() - started) * 1000),
    )


@router.post("/simulate")
def simulate(body: SimulateRequest) -> dict:
    """What-if. Branches a copy of the operation; the real roster is never touched."""
    repo = get_repository()
    started = time.perf_counter()

    if body.crew_id and body.pairing_id:
        result = A.assess_assignment(repo, body.crew_id, body.pairing_id)
        return envelope.from_tool(
            f"{body.crew_id} on {body.pairing_id}", "simulate",
            result, int((time.perf_counter() - started) * 1000),
        )

    if body.question:
        answer = llm_answer(repo, body.question, [])
        return envelope.from_answer(body.question, answer)

    result = structured_query.route(repo, body.crew_id or body.pairing_id or "")
    return envelope.from_tool("simulate", "simulate", result,
                              int((time.perf_counter() - started) * 1000))


@router.post("/recommend")
def recommend(body: RecommendRequest) -> dict:
    """Tier 3: ranked, rule-checked options for a named vacancy."""
    repo = get_repository()
    started = time.perf_counter()

    pairing_id = body.pairing_id
    role = None
    if body.crew_id:
        role = repo.crew[body.crew_id].rank if body.crew_id in repo.crew else None
        if not pairing_id:
            pairings = repo.crew_pairings.get(body.crew_id, [])
            on = _d(body.date)
            for pid in pairings:
                if on is None or any(d.date == on for d in repo.pairings[pid].days):
                    pairing_id = pid
                    break

    if not pairing_id:
        state = BASE_STATE
        if body.crew_id:
            state = state.with_crew_unavailable(body.crew_id, "unavailable")
        result = A.recover_from_state(repo, state)
    else:
        result = A.recommend_cover(repo, pairing_id, role or "Captain", crew_out=body.crew_id)

    return envelope.from_tool(
        f"recover {pairing_id or body.crew_id}", "recommend",
        result, int((time.perf_counter() - started) * 1000),
    )


@router.get("/alerts")
def alerts(date_: str | None = Query(default=None, alias="date")) -> dict:
    repo = get_repository()
    started = time.perf_counter()
    result = build_alerts(repo, _d(date_))
    return envelope.from_tool("alerts", "alerts", result,
                              int((time.perf_counter() - started) * 1000))


@router.get("/mcp")
def mcp_info() -> dict:
    """Everything a client needs to connect this engine over MCP.

    Served rather than hardcoded in the UI for two reasons: the config can then carry
    the absolute paths for THIS machine (the usual reason a first connection fails), and
    the tool list is generated from the same specs the server registers, so the page
    cannot drift from the code.
    """
    import json as _json
    import sys as _sys

    from app.config import BACKEND_DIR
    from app.llm.tools import tool_catalogue

    interpreter = _sys.executable
    script = str(BACKEND_DIR / "mcp_server" / "index.py")
    config = {
        "mcpServers": {
            "crew-ops": {"command": interpreter, "args": [script]}
        }
    }
    return {
        "server_name": "crew-ops",
        "transport": "stdio",
        "command": interpreter,
        "args": [script],
        "config_json": _json.dumps(config, indent=2),
        "config_path": {
            "windows": "%APPDATA%\Claude\claude_desktop_config.json",
            "macos": "~/Library/Application Support/Claude/claude_desktop_config.json",
        },
        "tools": tool_catalogue(),
    }


@router.get("/scorecard")
def scorecard() -> dict:
    """Runs the dataset's own 38 questions and 6 scenarios through the live engine."""
    from app.services.scorecard import run_scorecard

    return run_scorecard(get_repository())
