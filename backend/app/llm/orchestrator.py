"""The tool-calling loop, and the boundary the whole design rests on.

The model does three things: read the controller's question, decide which engine tools to
call, and phrase the result. It does not compute. If it goes down or refuses, the
deterministic router answers instead, so the desk never loses the advisor.

Every response leaves here through the grounding verifier.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app.config import SNAPSHOT_UTC, WEEK_END, WEEK_START
from app.explain.ledger import EvidenceLedger
from app.explain.verifier import GroundingResult, redact, verify
from app.fallback import structured_query
from app.llm import tools as tool_mod
from app.llm.provider import ChatMessage, ProviderError, get_provider
from app.services.entities import extract
from app.services.lookups import ToolResult

MAX_ROUNDS = 4

SYSTEM_PROMPT = f"""You are the Crew Ops Advisor for dCortex Air, sitting beside an \
airline crew controller during live operations.

Ground rules, in order of importance:

1. You do not compute. Duty hours, flight hours, rest, legality, costs, crew assignments \
and passenger counts come ONLY from tool results. Never estimate, never round, never \
infer a number a tool did not return.
2. If the tools do not establish something, say so plainly. "I can't confirm that from \
the roster" is a good answer. A confident wrong answer is the worst possible outcome on \
a crew desk.
3. Quote the rule IDs the engine actually checked (RULE-FDP-01, RULE-DUTY-02, \
RULE-FLT-03, RULE-REST-04, RULE-QUAL-05, RULE-CERT-06, RULE-BASE-07) and the actual \
figures behind them.
4. Write like a controller talks: short, specific, decision-first. Lead with the answer, \
then the reason. No preamble, no restating the question.
5. Never invent a crew id, flight number or pairing id. Use exactly the ones the tools returned.
6. If the question does not say WHICH crew member, pairing or flight it is about, ask. "Today's captain called in sick" names no captain -- there are 28 of them. Ask which one, or which pairing. Do not substitute a broad search (every captain at a base, say) for the answer: a confident answer to a question the controller did not ask is worse than a question back. Only carry an id over from earlier in the conversation if the controller is plainly still talking about that same crew member or pairing.

Choosing tools. Each of these does the whole job in ONE call -- do not rebuild them by \
checking candidates one at a time:

- "X is sick / out / unavailable", "what should I do", "options", "cheapest way to cover" \
  -> recommend_recovery. It already enumerates every candidate, applies all seven rules, \
  prices each one, searches multi-step swaps and ranks the result.
- "which flights are uncrewed / affected", "station closed", "flight delayed" \
  -> analyse_disruption.
- "can X cover Y", "does it breach", "what if I move X onto Y" -> check_assignment_legality.
- Plain facts (rosters, reserves, clocks, certificates, schedule) -> the matching lookup tool.

Call at most two tools before answering. If you already have the ranked options or the \
impact report, ANSWER -- do not verify them by re-querying.

Operational context: the snapshot is {SNAPSHOT_UTC:%Y-%m-%d %H:%M}Z. The published week \
runs {WEEK_START} to {WEEK_END}. All times are UTC. Currency is INR. \
"Tomorrow" means {SNAPSHOT_UTC.date().isoformat()} plus one day.
"""


@dataclass
class AdvisorAnswer:
    text: str
    tier: int
    intent: str
    confidence: str
    grounding: GroundingResult
    ledger: EvidenceLedger
    payload: dict = field(default_factory=dict)
    timing_ms: int = 0
    used_llm: bool = False


def _from_tool_result(result: ToolResult, intent: str, text: str | None = None) -> dict:
    return {
        "intent": intent,
        "tier": result.tier,
        "confidence": result.confidence,
        "text": text or result.summary,
        "table": result.table,
        "data": result.data,
        "ledger": result.ledger,
    }


def answer(repo, question: str, history: list[dict] | None = None) -> AdvisorAnswer:
    """Answer one controller question, LLM-first with a deterministic safety net."""
    started = time.perf_counter()
    history = history or []
    provider = None
    try:
        provider = get_provider()
    except ProviderError:
        provider = None

    if provider is None:
        return _deterministic(repo, question, started, "llm_disabled", history)

    try:
        return _with_llm(repo, question, history, provider, started)
    except ProviderError:
        # the model is down; the engine is not
        return _deterministic(repo, question, started, "llm_unavailable", history)


def _carried_referents(question: str, history: list[dict]) -> list[str]:
    """Which ids from the thread may be read into an under-specified question.

    A follow-up like "why not the cheapest option?" carries no ids of its own and has
    to be resolved against the thread. The obvious way to do that -- glue the recent
    turns onto the question and re-route -- is wrong, because the *previous question's
    intent* then wins. Ask "which captains are based in DEL?", then "today's captain
    called in sick, who should replace them?", and the desk confidently re-answers the
    DEL lookup: a real answer to a question nobody asked, which is worse than a refusal.

    So the thread may supply **referents** -- which specific crew member, pairing or
    flight we were discussing -- and nothing else. It may not supply a rank, a station,
    a date or a verb, because those are what make one question a different question
    from another. And it may only do so when the current question names no referent of
    its own; a self-contained question is never reinterpreted against the thread.
    """
    here = extract(question)
    if here.crew_ids or here.pairing_ids or here.flight_ids or here.flight_nos or here.tails:
        return []

    carried: list[str] = []
    for turn in reversed(history[-4:]):
        if turn.get("role") != "user":
            continue
        ent = extract(turn.get("content", ""))
        for value in (*ent.crew_ids, *ent.pairing_ids, *ent.flight_ids,
                      *ent.flight_nos, *ent.tails):
            if value not in carried:
                carried.append(value)
    return carried


def _deterministic(repo, question: str, started: float, reason: str,
                   history: list[dict] | None = None) -> AdvisorAnswer:
    result = structured_query.route(repo, question)

    if result.confidence == "cannot_answer" and history:
        carried = _carried_referents(question, history)
        if carried:
            retry = structured_query.route(repo, f"{question} {' '.join(carried)}")
            if retry.confidence != "cannot_answer":
                result = retry

    grounding = verify(result.summary, result.ledger)
    return AdvisorAnswer(
        text=result.summary,
        tier=result.tier,
        intent=f"deterministic:{reason}",
        confidence=result.confidence,
        grounding=grounding,
        ledger=result.ledger,
        payload=result.data,
        timing_ms=int((time.perf_counter() - started) * 1000),
        used_llm=False,
    )


def _with_llm(repo, question: str, history: list[dict], provider, started: float) -> AdvisorAnswer:
    messages = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
    for turn in history[-4:]:
        # thread context only needs the gist; full answers would crowd out the tools
        messages.append(
            ChatMessage(role=turn["role"], content=turn["content"][:500])
        )
    messages.append(ChatMessage(role="user", content=question))

    ledger = EvidenceLedger()
    payload: dict = {}
    tier = 1
    called: list[str] = []
    # the deterministic layer narrows the menu; the model chooses within it
    schema = tool_mod.openai_schema(question)

    for round_index in range(MAX_ROUNDS):
        # on the last round the tools are withdrawn, which forces a written answer from
        # the evidence already gathered rather than another round of exploration
        final_round = round_index == MAX_ROUNDS - 1
        response = provider.chat(messages, tools=None if final_round and called else schema)

        if not response.tool_calls:
            text = response.content.strip()
            if not called:
                # the model answered without consulting the engine -- that answer is
                # ungrounded by construction, so use the deterministic path instead
                return _deterministic(repo, question, started, "no_tool_call", history)
            grounding = verify(text, ledger)
            return AdvisorAnswer(
                text=redact(text, grounding),
                tier=tier,
                intent="+".join(called),
                confidence=_confidence(payload, grounding),
                grounding=grounding,
                ledger=ledger,
                payload=payload,
                timing_ms=int((time.perf_counter() - started) * 1000),
                used_llm=True,
            )

        messages.append(
            ChatMessage(role="assistant", content=response.content or "",
                        tool_calls=response.tool_calls)
        )

        for call in response.tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            result = tool_mod.dispatch(repo, name, args)
            called.append(name)
            tier = max(tier, result.tier)

            for item in result.ledger.items:
                ledger.items.append(item)
            ledger.allow(*result.ledger.tokens)
            payload = _merge_payload(payload, result)

            messages.append(
                ChatMessage(
                    role="tool",
                    tool_call_id=call.get("id"),
                    name=name,
                    content=_digest(result),
                )
            )

    # ran out of rounds without a final answer -- fall back rather than guess
    return _deterministic(repo, question, started, "tool_loop_exhausted", history)


def _digest(result: ToolResult, limit: int = 2200) -> str:
    """What the model needs to WRITE the answer -- not the whole payload.

    The full structured result goes straight to the UI. Sending it through the model as
    well would waste the context window (and, on a free tier, the token budget) on data
    the model must not reinterpret anyway. It gets the summary plus the handful of facts
    a controller's sentence is built from.
    """
    data = result.data or {}
    lines = [result.summary]

    options = data.get("options") or []
    if options:
        lines.append(f"options ({len(options)} total, cheapest first):")
        for option in options[:4]:
            lines.append(
                f"  #{option['rank']} {option['action']} | INR {option['cost_inr']:,} | "
                f"legal={option['legal']} | covers {option['coverage']}"
                + (f" | {option['resilience_note']}" if option.get("resilience_note") else "")
            )

    for alert in (data.get("alerts") or [])[:8]:
        lines.append(f"[{alert['severity']}] {alert['subject']}: {alert['message']}")

    for relax in (data.get("relaxations") or [])[:2]:
        lines.append(f"near-miss: {relax['breach_detail']} -> {relax['remedy']}")

    for check in (data.get("rule_checks") or []):
        lines.append(
            f"{check['rule_id']}: {check['status']} ({check['detail']})"
        )

    impact = data.get("impact") or {}
    if impact:
        lines.append(
            f"uncovered legs: {', '.join(impact.get('uncrewed_flights', [])[:8])}; "
            f"pairings: {', '.join(impact.get('pairing_broken', []))}; "
            f"passengers: {impact.get('passengers_affected')}"
        )
        for risk in (impact.get("downstream_risks") or [])[:3]:
            lines.append(f"downstream: {risk['crew_id']} {risk['rule']} {risk['detail']}")

    if result.table and not options:
        table = result.table
        lines.append("| " + " | ".join(table["columns"]) + " |")
        for row in table["rows"][:12]:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        if len(table["rows"]) > 12:
            lines.append(f"... and {len(table['rows']) - 12} more rows")

    # exclusions are quoted verbatim with their rule ids: without them the model
    # reconstructs plausible-sounding reasons and attributes breaches to the wrong rule
    for excluded in (data.get("excluded") or [])[:6]:
        rules = "/".join(excluded.get("rules_failed") or [])
        lines.append(
            f"excluded {excluded['crew_id']}"
            + (f" [{rules}]" if rules else "")
            + f": {excluded['reason']}"
        )

    text = "\n".join(lines)
    return text[:limit] + ("\n...(truncated)" if len(text) > limit else "")


def _merge_payload(payload: dict, result: ToolResult) -> dict:
    merged = dict(payload)
    data = result.data or {}
    for key in ("impact", "options", "relaxations", "alerts", "before_after",
                "message", "crew_id", "pairing_id", "acknowledge_within_minutes", "legal"):
        if data.get(key):
            merged[key] = data[key]
    if result.table:
        merged["table"] = result.table
    if data.get("rule_checks"):
        merged["rule_checks"] = data["rule_checks"]
    return merged


def _confidence(payload: dict, grounding: GroundingResult) -> str:
    if not grounding.verified:
        return "review"
    return "high"
