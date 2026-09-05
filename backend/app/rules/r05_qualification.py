"""RULE-QUAL-05 - crew must hold a valid rating for the assigned aircraft type."""
from __future__ import annotations

from app.rules.result import CoverRequest, RuleResult

RULE_ID = "RULE-QUAL-05"


def evaluate(repo, request: CoverRequest) -> list[RuleResult]:
    crew = repo.crew[request.crew_id]
    types = sorted({repo.day_aircraft_type(d) for d in request.days})
    results: list[RuleResult] = []
    for actype in types:
        ok = actype in crew.ratings
        results.append(
            RuleResult(
                rule_id=RULE_ID,
                status="PASS" if ok else "FAIL",
                actual=", ".join(crew.ratings) or "none",
                limit=actype,
                margin=None,
                detail=(
                    f"rated for {actype}" if ok
                    else f"no {actype} rating (holds {', '.join(crew.ratings) or 'none'})"
                ),
            )
        )
    return results
