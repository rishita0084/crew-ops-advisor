"""RULE-DUTY-02 - max duty hours in a rolling window of CALENDAR days.

The window is N UTC dates inclusive of the duty date, not a rolling 168h clock.
Accrual = historical daily_history + the crew's own planned week duties (minus any
pairing they are vacating) + the proposed cover days up to and including that date.
"""
from __future__ import annotations

from datetime import date

from app.domain.time_utils import calendar_window, fmt_hours_minutes
from app.rules.result import CoverRequest, RuleResult

RULE_ID = "RULE-DUTY-02"
EPS = 1e-6


def accrued_duty(repo, crew_id: str, end: date, days: int, exclude_pairing: str | None = None) -> float:
    """Duty hours already on the books for the calendar window ending `end`."""
    start, stop = calendar_window(end, days)
    total = 0.0
    for day, (duty, _flight) in repo.duty_history.get(crew_id, {}).items():
        if start <= day <= stop:
            total += duty
    for block in repo.roster.get(crew_id, []):
        if block.pairing_id == exclude_pairing:
            continue
        if start <= block.date <= stop:
            total += block.duty_hours
    return round(total, 2)


def evaluate(repo, request: CoverRequest) -> list[RuleResult]:
    limit = float(repo.rule_param(RULE_ID, "max_duty_hours", 60))
    window = int(repo.rule_param(RULE_ID, "window_days", 7))

    results: list[RuleResult] = []
    for day in request.days:
        base = accrued_duty(repo, request.crew_id, day.date, window, request.exclude_pairing)
        # cover days land inside the same window only up to the date being tested
        added = sum(request.duty_hours(d) for d in request.days if d.date <= day.date)
        total = round(base + added, 2)
        margin = round(limit - total, 2)
        ok = total <= limit + EPS
        detail = (
            f"{day.date}: {total}h duty in {window} calendar days, limit {limit}h"
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
