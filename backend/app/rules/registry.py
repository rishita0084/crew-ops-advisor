"""The legality engine: evaluates one CoverRequest against all seven rules.

This is the only place in the system that decides whether something is legal. The LLM
never does. Rule order is fixed so explanations read consistently.
"""
from __future__ import annotations

from app.domain import positioning as positioning_mod
from app.rules import (
    r01_fdp,
    r02_duty_7d,
    r03_flight_28d,
    r04_rest,
    r05_qualification,
    r06_certification,
    r07_base_callout,
)
from app.rules.result import CoverRequest, RuleResult, Verdict, build_timeline

ALL_RULES = [
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07",
]


def evaluate(repo, request: CoverRequest, positioning=None) -> Verdict:
    """Run every rule. Returns a Verdict carrying each rule's result and margin."""
    if not request.days:
        return Verdict(crew_id=request.crew_id, legal=False, results=[])

    if positioning is None:
        positioning = positioning_mod.plan(repo, request.crew_id, request.days[0])

    flight_hours = {
        d.pairing_id + str(d.day_index): repo.day_flight_hours(d) for d in request.days
    }
    timeline = build_timeline(repo.roster.get(request.crew_id, []), request, flight_hours)

    results: list[RuleResult] = []
    results += r01_fdp.evaluate(repo, request)
    results += r02_duty_7d.evaluate(repo, request)
    results += r03_flight_28d.evaluate(repo, request)
    results += r04_rest.evaluate(repo, request, timeline)
    results += r05_qualification.evaluate(repo, request)
    results += r06_certification.evaluate(repo, request)
    results += r07_base_callout.evaluate(repo, request, positioning)

    legal = not any(r.failed for r in results)
    return Verdict(crew_id=request.crew_id, legal=legal, results=results)


def summarise(verdict: Verdict) -> list[dict]:
    """One representative RuleResult per rule -- the worst outcome for that rule.

    The UI shows a rule-by-rule checklist, not one row per pairing-day, so collapse
    multi-day results down to the binding one.
    """
    worst: dict[str, RuleResult] = {}
    for r in verdict.results:
        current = worst.get(r.rule_id)
        if current is None:
            worst[r.rule_id] = r
            continue
        if r.failed and not current.failed:
            worst[r.rule_id] = r
        elif r.failed == current.failed and r.margin is not None:
            if current.margin is None or r.margin < current.margin:
                worst[r.rule_id] = r
    return [worst[rid].to_dict() for rid in ALL_RULES if rid in worst]
