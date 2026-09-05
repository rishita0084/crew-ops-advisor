"""RULE-BASE-07 - reserve callout from own base only; covering from elsewhere needs
deadhead positioning (and its cost).

This rule also carries the reserve on-call window test, because rules.json defines
reserve callout here: the required report time -- after any positioning delay -- must
fall inside the reserve's on-call window. Once activated, the reserve operates as
line crew and the window no longer applies.
"""
from __future__ import annotations

from app.domain.positioning import Positioning
from app.domain.time_utils import time_on_date
from app.rules.result import CoverRequest, RuleResult

RULE_ID = "RULE-BASE-07"


def evaluate(repo, request: CoverRequest, positioning: Positioning) -> list[RuleResult]:
    crew = repo.crew[request.crew_id]
    first = request.days[0]
    station = repo.flights[first.flight_ids[0]].dep_station
    results: list[RuleResult] = []

    if not positioning.feasible:
        results.append(
            RuleResult(
                rule_id=RULE_ID, status="FAIL", actual=crew.base, limit=station, margin=None,
                detail=positioning.detail,
            )
        )
        return results

    results.append(
        RuleResult(
            rule_id=RULE_ID, status="PASS", actual=crew.base, limit=station, margin=None,
            detail=positioning.detail,
        )
    )

    if repo.is_reserve(request.crew_id):
        reserve = repo.reserves[request.crew_id]
        report, _ = request.shifted(first)
        day = report.date()

        if first.date.isoformat() not in reserve.dates:
            results.append(
                RuleResult(
                    rule_id=RULE_ID, status="FAIL", actual=first.date.isoformat(),
                    limit="on-call date", margin=None,
                    detail=f"not on the reserve roster for {first.date}",
                )
            )
            return results

        start = time_on_date(day, reserve.window_start)
        end = time_on_date(day, reserve.window_end)
        inside = start <= report <= end
        window = f"{reserve.window_start}-{reserve.window_end}Z"
        results.append(
            RuleResult(
                rule_id=RULE_ID,
                status="PASS" if inside else "FAIL",
                actual=report.strftime("%H:%M") + "Z",
                limit=window,
                margin=None,
                detail=(
                    f"reserve on-call {window} covers required report "
                    f"{report.strftime('%H:%M')}Z"
                    if inside
                    else (
                        f"reserve on-call window {window} does not cover required report "
                        f"{report.strftime('%H:%M')}Z"
                    )
                ),
            )
        )
    return results
