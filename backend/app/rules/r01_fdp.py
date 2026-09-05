"""RULE-FDP-01 - max flight duty period, reduced by sectors flown.

    limit = base_fdp_hours - reduction_per_extra_sector_hours * max(0, sectors - free_sectors)
"""
from __future__ import annotations

from app.rules.result import CoverRequest, RuleResult

RULE_ID = "RULE-FDP-01"
EPS = 1e-6


def fdp_limit(repo, sectors: int) -> float:
    base = float(repo.rule_param(RULE_ID, "base_fdp_hours", 13.0))
    step = float(repo.rule_param(RULE_ID, "reduction_per_extra_sector_hours", 0.5))
    free = int(repo.rule_param(RULE_ID, "free_sectors", 2))
    return base - step * max(0, sectors - free)


def evaluate(repo, request: CoverRequest) -> list[RuleResult]:
    results: list[RuleResult] = []
    for day in request.days:
        sectors = day.sectors
        limit = fdp_limit(repo, sectors)
        actual = request.duty_hours(day)
        margin = round(limit - actual, 2)
        ok = actual <= limit + EPS
        results.append(
            RuleResult(
                rule_id=RULE_ID,
                status="PASS" if ok else "FAIL",
                actual=actual,
                limit=limit,
                margin=margin,
                detail=(
                    f"{day.date}: FDP {actual}h over {sectors} sectors, limit {limit}h"
                    + ("" if ok else f" - exceeds by {round(actual - limit, 2)}h")
                ),
            )
        )
    return results
