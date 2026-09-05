"""Builds the single response envelope every endpoint returns.

One shape for every question keeps the UI simple: components render whichever fields are
present. This is also the last place a response can be assembled, so grounding and
evidence are attached here rather than being optional extras a route might forget.
"""
from __future__ import annotations

from app.explain.ledger import EvidenceLedger
from app.explain.verifier import verify
from app.llm.orchestrator import AdvisorAnswer
from app.services.lookups import ToolResult


def _notification(data: dict) -> dict | None:
    """A drafted crew message, if this answer produced one.

    Kept as its own field rather than buried in the prose so the console can offer it
    for review and copying -- and label plainly that nothing was sent.
    """
    if not data.get("message"):
        return None
    return {
        "crew_id": data.get("crew_id", ""),
        "pairing_id": data.get("pairing_id", ""),
        "message": data["message"],
        "acknowledge_within_minutes": data.get("acknowledge_within_minutes", 0),
        "legal": bool(data.get("legal", False)),
        "delivered": False,
    }


def _clean_options(options: list[dict] | None) -> list[dict] | None:
    if not options:
        return None
    return options


def from_answer(query: str, answer: AdvisorAnswer) -> dict:
    payload = answer.payload or {}
    return {
        "query": query,
        "intent": answer.intent,
        "tier": answer.tier,
        "answer_text": answer.text,
        "confidence": answer.confidence,
        "grounding": answer.grounding.to_dict(),
        "table": payload.get("table"),
        "impact": payload.get("impact"),
        "options": _clean_options(payload.get("options")),
        "relaxations": payload.get("relaxations") or None,
        "alerts": payload.get("alerts") or None,
        "before_after": payload.get("before_after") or None,
        "notification": _notification(payload),
        "evidence": answer.ledger.to_list(),
        "timing_ms": answer.timing_ms,
    }


def from_tool(query: str, intent: str, result: ToolResult, timing_ms: int) -> dict:
    """Envelope for the direct (non-conversational) endpoints."""
    ledger: EvidenceLedger = result.ledger
    grounding = verify(result.summary, ledger)
    data = result.data or {}
    return {
        "query": query,
        "intent": intent,
        "tier": result.tier,
        "answer_text": result.summary,
        "confidence": result.confidence,
        "grounding": grounding.to_dict(),
        "table": result.table,
        "impact": data.get("impact"),
        "options": _clean_options(data.get("options")),
        "relaxations": data.get("relaxations") or None,
        "alerts": data.get("alerts") or None,
        "before_after": data.get("before_after") or None,
        "notification": _notification(data),
        "evidence": ledger.to_list(),
        "timing_ms": timing_ms,
    }
