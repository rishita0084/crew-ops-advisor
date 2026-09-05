"""RULE-FLT-03 - max block (flight) hours in a rolling window of CALENDAR days.

Same calendar-window semantics as RULE-DUTY-02, but accruing block hours.
"""
from __future__ import annotations

from datetime import date

from app.domain.time_utils import calendar_window, fmt_hours_minutes
from app.rules.result import CoverRequest, RuleResult

RULE_ID = "RULE-FLT-03"
EPS = 1e-6


def accrued_flight(repo, crew_id: str, end: date, days: int, exclude_pairing: str | None = None) -> float:
    start, stop = calendar_window(end, days)
    total = 0.0
    for day, (_duty, flight) in repo.duty_history.get(crew_id, {}).items():
        if start <= day <= stop:
            total += flight
    for block in repo.roster.get(crew_id, []):
        if block.pairing_id == exclude_pairing:
            continue
        if start <= block.date <= stop:
            total += block.flight_hours
    return round(total, 2)


def evaluate(repo, request: CoverRequest) -> list[RuleResult]:
    limit = float(repo.rule_param(RULE_ID, "max_flight_hours", 100))
    window = int(repo.rule_param(RULE_ID, "window_days", 28))

    results: list[RuleResult] = []
    for day in request.days:
        base = accrued_flight(repo, request.crew_id, day.date, window, request.exclude_pairing)
        added = sum(
            repo.day_flight_hours(d) for d in request.days if d.date <= day.date
        )
        total = round(base + added, 2)
        margin = round(limit - total, 2)
        ok = total <= limit + EPS
        detail = (
            f"{day.date}: {total}h block in {window} calendar days, limit {limit}h"
            if ok
            else (
                f"would exceed {limit:g}h/{window}d by {fmt_hours_minutes(total - limit)} "
                f"on {day.date} (total {total}h)"
            )
        )
        results.append(
            RuleResult(
                rule_id=RULE_ID,
                status="PASS" if ok else "FAIL",
                actual=total,
                limit=limit,
                margin=margin,
                detail=detail,
            )
        )
    return results
