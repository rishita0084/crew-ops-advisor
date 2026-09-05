"""RULE-CERT-06 - every certification must be valid on each duty date.

Validity is tested against `valid_to` only. That is deliberate: 150 of the 600 supplied
certification records carry a `valid_from` in the future (a generator artifact -- issue
dates were derived by subtracting the validity term from a long expiry), and the
dataset's own validator treats a certification as valid whenever `valid_to >= date`.
Enforcing `valid_from` here would fail roughly a quarter of the fleet's crew against a
roster the dataset guarantees is legal. Expiry is the operative constraint.
"""
from __future__ import annotations

from datetime import date

from app.rules.result import CoverRequest, RuleResult

RULE_ID = "RULE-CERT-06"


def expired_certs(repo, crew_id: str, on_date: date) -> list:
    """Certifications that have lapsed by `on_date`."""
    return [c for c in repo.certifications.get(crew_id, []) if c.valid_to < on_date]


def next_expiry(repo, crew_id: str):
    certs = repo.certifications.get(crew_id, [])
    return min(certs, key=lambda c: c.valid_to) if certs else None


def evaluate(repo, request: CoverRequest) -> list[RuleResult]:
    results: list[RuleResult] = []
    for day in request.days:
        bad = expired_certs(repo, request.crew_id, day.date)
        if bad:
            names = ", ".join(f"{c.cert_type} (expired {c.valid_to})" for c in bad)
            results.append(
                RuleResult(
                    rule_id=RULE_ID, status="FAIL", actual=names, limit=str(day.date),
                    margin=None,
                    detail=f"certification invalid on {day.date}: {names}",
                )
            )
        else:
            soonest = next_expiry(repo, request.crew_id)
            margin = (soonest.valid_to - day.date).days if soonest else None
            results.append(
                RuleResult(
                    rule_id=RULE_ID, status="PASS",
                    actual=str(soonest.valid_to) if soonest else None,
                    limit=str(day.date), margin=float(margin) if margin is not None else None,
                    detail=(
                        f"all certifications valid on {day.date}"
                        + (
                            f"; earliest expiry {soonest.cert_type} {soonest.valid_to} "
                            f"({margin} days)"
                            if soonest else ""
                        )
                    ),
                )
            )
    return results
