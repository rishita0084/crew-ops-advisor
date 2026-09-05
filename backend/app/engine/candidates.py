"""Candidate generation: who could cover this pairing, and what does each cost?

Enumerates every active crew member of the required rank, runs the full ruleset against
each, and returns legal candidates plus an audit trail of who was excluded and why.
The exclusion list is not debug output -- a controller needs to see that the obvious
person was considered and ruled out.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain import positioning as positioning_mod
from app.domain.models import PairingDay
from app.domain.positioning import Positioning
from app.engine.cost import CostBreakdown, assignment_cost
from app.rules import registry
from app.rules.result import CoverRequest, Verdict


@dataclass
class Candidate:
    crew_id: str
    rank: str
    verdict: Verdict
    positioning: Positioning
    cost: CostBreakdown
    label: str
    delay_hours: float
    days: list[PairingDay] = field(default_factory=list)
    source: str = "line"          # reserve | dayoff | line
    exclude_pairing: str | None = None

    @property
    def legal(self) -> bool:
        return self.verdict.legal

    @property
    def cost_inr(self) -> int:
        return self.cost.total

    @property
    def action(self) -> str:
        return f"Assign {self.rank} {self.crew_id} ({self.label})"


def _source(repo, crew_id: str) -> str:
    if repo.is_reserve(crew_id):
        return "reserve"
    return "dayoff" if not repo.roster.get(crew_id) else "line"


def build_candidate(
    repo, crew_id: str, days: list[PairingDay], exclude_pairing: str | None = None
) -> Candidate:
    """Evaluate one crew member against one set of pairing days."""
    positioning = positioning_mod.plan(repo, crew_id, days[0])
    request = CoverRequest(
        crew_id=crew_id, days=days, exclude_pairing=exclude_pairing,
        delay_hours=positioning.delay_hours,
    )
    verdict = registry.evaluate(repo, request, positioning)
    breakdown, label = assignment_cost(repo, crew_id, positioning)
    return Candidate(
        crew_id=crew_id,
        rank=repo.crew[crew_id].rank,
        verdict=verdict,
        positioning=positioning,
        cost=breakdown,
        label=label,
        delay_hours=positioning.delay_hours,
        days=list(days),
        source=_source(repo, crew_id),
        exclude_pairing=exclude_pairing,
    )


def enumerate_candidates(
    repo,
    days: list[PairingDay],
    role: str,
    exclude_crew: set[str] | None = None,
    exclude_pairing: str | None = None,
) -> tuple[list[Candidate], list[dict]]:
    """All legal covers for `days` at `role`, cheapest first, plus exclusions.

    Ties break on crew_id so results are stable and reproducible across runs.
    """
    exclude_crew = exclude_crew or set()
    legal: list[Candidate] = []
    excluded: list[dict] = []

    for crew in repo.crew_by_rank(role, active_only=True):
        if crew.crew_id in exclude_crew:
            continue
        candidate = build_candidate(repo, crew.crew_id, days, exclude_pairing)
        if candidate.legal:
            legal.append(candidate)
        else:
            excluded.append(
                {
                    "crew_id": crew.crew_id,
                    "rank": crew.rank,
                    "reason": candidate.verdict.reason(),
                    "rules_failed": sorted({f.rule_id for f in candidate.verdict.failures}),
                }
            )

    legal.sort(key=lambda c: (c.cost_inr, c.crew_id))
    excluded.sort(key=lambda e: e["crew_id"])
    return legal, excluded
