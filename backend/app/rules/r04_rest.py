"""RULE-REST-04 - minimum rest between release and the next report.

Evaluated over the simulated timeline, so it catches three distinct failures:
  - too little rest BEFORE the new assignment,
  - too little rest AFTER it (a downstream conflict with the crew's existing roster),
  - a straight overlap, i.e. double-booking (negative rest).
"""
from __future__ import annotations

from app.domain.models import DutyBlock
from app.domain.time_utils import hours_between
from app.rules.result import CoverRequest, RuleResult

RULE_ID = "RULE-REST-04"
EPS = 1e-6


def _label(block: DutyBlock) -> str:
    return "the new assignment" if block.is_simulated else block.pairing_id


def evaluate(repo, request: CoverRequest, timeline: list[DutyBlock]) -> list[RuleResult]:
    minimum = float(repo.rule_param(RULE_ID, "min_rest_hours", 12))
    results: list[RuleResult] = []

    for earlier, later in zip(timeline, timeline[1:]):
        # only pairs that involve the proposed duty are this request's problem
        if not (earlier.is_simulated or later.is_simulated):
            continue

        rest = hours_between(earlier.release_utc, later.report_utc)
        margin = round(rest - minimum, 2)

        if rest < 0:
            detail = (
                f"double-booked: {_label(earlier)} on {earlier.date} overlaps "
                f"{_label(later)} on {later.date}"
            )
            status = "FAIL"
        elif rest < minimum - EPS:
            direction = "before" if later.is_simulated else "after"
            detail = (
                f"only {rest}h rest {direction} {_label(later if later.is_simulated else earlier)} "
                f"on {later.date}, minimum {minimum:g}h"
            )
            status = "FAIL"
        else:
            detail = (
                f"{rest}h rest between {_label(earlier)} ({earlier.date}) and "
                f"{_label(later)} ({later.date}), minimum {minimum:g}h"
            )
            status = "PASS"

        results.append(
            RuleResult(
                rule_id=RULE_ID, status=status, actual=rest, limit=minimum,
                margin=margin, detail=detail,
            )
        )

    if not results:
        results.append(
            RuleResult(
                rule_id=RULE_ID, status="PASS", actual=None, limit=minimum, margin=None,
                detail="no adjacent duty within the planning window",
            )
        )
    return results
