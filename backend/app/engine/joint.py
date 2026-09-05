"""Joint assignment across simultaneous vacancies.

Solving two sick calls independently is wrong, and wrong in a way that looks right: each
vacancy picks the cheapest legal crew member, and both pick the *same* person. One body
cannot fly two pairings, so the "plan" is not a plan.

This solves them together -- minimum total cost subject to every vacancy getting a
different crew member. The search space is tiny (a handful of vacancies against a
shortlist each), so an exhaustive search over the cheapest candidates finds the true
optimum without a solver, and every step stays explainable.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from app.engine.candidates import Candidate, enumerate_candidates

# how many candidates per vacancy to consider; the optimum never needs the tail of a
# cost-sorted list once every vacancy has this many distinct options available
SHORTLIST = 6


@dataclass
class Vacancy:
    pairing_id: str
    role: str
    crew_out: str | None = None


@dataclass
class JointPlan:
    assignments: list[tuple[Vacancy, Candidate]]
    total_cost_inr: int
    per_vacancy_options: dict[str, list[Candidate]]
    infeasible: list[Vacancy]

    def describe(self) -> str:
        parts = [
            f"{v.pairing_id}: {c.action} at INR {c.cost_inr:,}"
            for v, c in self.assignments
        ]
        return "; ".join(parts)


def solve(repo, vacancies: list[Vacancy]) -> JointPlan:
    """Cheapest set of assignments in which no crew member is used twice."""
    shortlists: dict[str, list[Candidate]] = {}
    infeasible: list[Vacancy] = []
    solvable: list[Vacancy] = []

    for vac in vacancies:
        legal, _ = enumerate_candidates(
            repo, repo.pairings[vac.pairing_id].days, vac.role,
            exclude_crew={vac.crew_out} if vac.crew_out else set(),
            exclude_pairing=vac.pairing_id,
        )
        if not legal:
            infeasible.append(vac)
            continue
        shortlists[vac.pairing_id] = legal[:SHORTLIST]
        solvable.append(vac)

    if not solvable:
        return JointPlan([], 0, shortlists, infeasible)

    best: tuple[int, list[tuple[Vacancy, Candidate]]] | None = None
    for combo in product(*(shortlists[v.pairing_id] for v in solvable)):
        used = {c.crew_id for c in combo}
        if len(used) != len(combo):
            continue                      # the same person cannot fly both
        total = sum(c.cost_inr for c in combo)
        if best is None or total < best[0]:
            best = (total, list(zip(solvable, combo)))

    if best is None:
        # every combination collided: fall back to a greedy pass that at least
        # respects distinctness, so the controller still gets a workable plan
        used: set[str] = set()
        chosen: list[tuple[Vacancy, Candidate]] = []
        total = 0
        for vac in solvable:
            pick = next(
                (c for c in shortlists[vac.pairing_id] if c.crew_id not in used), None
            )
            if pick is None:
                infeasible.append(vac)
                continue
            used.add(pick.crew_id)
            chosen.append((vac, pick))
            total += pick.cost_inr
        return JointPlan(chosen, total, shortlists, infeasible)

    return JointPlan(best[1], best[0], shortlists, infeasible)
