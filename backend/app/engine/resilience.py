"""Future resilience: what the operation looks like AFTER a decision is taken.

The cheapest legal option and the wisest legal option are not always the same. If
option A saves money by consuming the last reserve capable of covering a high-risk
pairing tomorrow, and option B costs a little more but leaves that capacity intact,
a controller wants to see that trade-off rather than discover it at 06:00 the next day.

Deterministic throughout -- this counts remaining legal cover from the precomputed
legality matrix. There is no model and no prediction here; risk_signals.json is a
provided input, treated like a weather forecast.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.domain.models import PairingDay
from app.engine.candidates import build_candidate


@dataclass
class Resilience:
    score: float          # 0..1, share of the pool still usable afterwards
    remaining: int
    baseline: int
    note: str
    exposed_pairings: list[str]


def _horizon_days(repo, after: PairingDay, days: int = 2) -> list[PairingDay]:
    """Pairing-days starting the day after the assignment, within the planning horizon."""
    start = after.date + timedelta(days=1)
    end = start + timedelta(days=days - 1)
    out: list[PairingDay] = []
    for pairing in repo.pairings.values():
        for day in pairing.days:
            if start <= day.date <= end:
                out.append(day)
    return out


def assess(
    repo, days: list[PairingDay], role: str, consumed: set[str], pool: list[str]
) -> Resilience:
    """How much legal cover remains for tomorrow once `consumed` crew are committed.

    `pool` is the set of crew who were legal for today's problem -- the operation's
    actual slack, not the headcount.
    """
    horizon = _horizon_days(repo, days[-1])
    if not horizon or not pool:
        return Resilience(
            score=1.0, remaining=len(pool), baseline=len(pool),
            note="no further pairing days inside the planning horizon",
            exposed_pairings=[],
        )

    remaining_pool = [cid for cid in pool if cid not in consumed]
    baseline = len(pool)
    remaining = len(remaining_pool)

    # which of tomorrow's pairings would now have thin cover at this rank?
    exposed: list[str] = []
    by_pairing: dict[str, list[PairingDay]] = {}
    for day in horizon:
        by_pairing.setdefault(day.pairing_id, []).append(day)

    for pairing_id, pairing_days in sorted(by_pairing.items()):
        covers = 0
        for cid in remaining_pool:
            if build_candidate(repo, cid, pairing_days).legal:
                covers += 1
                if covers > 1:
                    break
        if covers <= 1:
            exposed.append(pairing_id)

    score = round(remaining / baseline, 2) if baseline else 1.0

    if not exposed:
        note = (
            f"{remaining} of {baseline} legal {role.lower()}s remain available for the "
            f"next 2 days; no pairing is left with a single cover"
        )
    else:
        listed = ", ".join(exposed[:3])
        more = f" (+{len(exposed) - 3} more)" if len(exposed) > 3 else ""
        note = (
            f"{remaining} of {baseline} legal {role.lower()}s remain; "
            f"{len(exposed)} upcoming pairing(s) would be left with one or no cover: "
            f"{listed}{more}"
        )

    return Resilience(
        score=score, remaining=remaining, baseline=baseline,
        note=note, exposed_pairings=exposed,
    )
