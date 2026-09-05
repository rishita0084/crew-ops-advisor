"""Multi-step recovery chains.

A single substitution is often impossible: nobody free is legal for the whole pairing.
Real crew control then does a cascade -- move a rostered crew member onto the broken
pairing, and backfill the pairing they just vacated. This is a beam search over those
cascades, to MAX_CHAIN_DEPTH moves, with every step validated against the full ruleset
before it can be extended.

Deliberately not a solver: each step has to be explainable to a controller, so we keep
a readable move list rather than an opaque optimum.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import BEAM_WIDTH, MAX_CHAIN_DEPTH
from app.domain.models import PairingDay
from app.engine.candidates import Candidate, build_candidate


@dataclass
class ChainLink:
    crew_id: str
    rank: str
    pairing_id: str
    day_indexes: list[int]
    flight_ids: list[str]
    action: str
    candidate: Candidate

    def to_dict(self, step: int) -> dict:
        from app.rules.registry import summarise

        return {
            "step": step,
            "action": self.action,
            "crew_id": self.crew_id,
            "pairing_id": self.pairing_id,
            "flight_ids": self.flight_ids,
            "rule_checks": summarise(self.candidate.verdict),
        }


@dataclass
class Chain:
    links: list[ChainLink] = field(default_factory=list)
    vacated: tuple[str, str] | None = None   # (pairing_id, crew_id) still needing a backfill

    @property
    def cost_inr(self) -> int:
        return sum(link.candidate.cost_inr for link in self.links)

    @property
    def delay_hours(self) -> float:
        return max((link.candidate.delay_hours for link in self.links), default=0.0)

    @property
    def complete(self) -> bool:
        return self.vacated is None

    @property
    def depth(self) -> int:
        return len(self.links)

    def crew_used(self) -> set[str]:
        return {link.crew_id for link in self.links}

    def describe(self) -> str:
        if self.depth == 1:
            return self.links[0].action
        moves = " then ".join(link.action for link in self.links)
        return f"{self.depth}-step swap: {moves}"


def _rostered_movers(repo, role: str, exclude: set[str]) -> list[str]:
    """Crew of the right rank who ARE on a pairing -- the pool a swap can draw from."""
    return sorted(
        c.crew_id
        for c in repo.crew_by_rank(role, active_only=True)
        if c.crew_id not in exclude and repo.roster.get(c.crew_id)
    )


def search(
    repo,
    days: list[PairingDay],
    role: str,
    exclude_crew: set[str],
    vacated_pairing: str | None = None,
) -> list[Chain]:
    """Find complete recovery chains covering `days` at `role`.

    Depth 1 is a straight assignment. Depth 2+ means somebody was moved off their own
    pairing and that pairing then had to be backfilled -- recursively, until every
    vacancy the chain created is filled.
    """
    complete: list[Chain] = []
    frontier: list[Chain] = []

    # ---- depth 1: move a rostered crew member onto the broken pairing ----
    for crew_id in _rostered_movers(repo, role, exclude_crew):
        own = sorted(set(repo.crew_pairings.get(crew_id, [])))
        for source_pairing in own:
            if source_pairing == vacated_pairing:
                continue
            candidate = build_candidate(repo, crew_id, days, exclude_pairing=source_pairing)
            if not candidate.legal:
                continue
            link = ChainLink(
                crew_id=crew_id,
                rank=candidate.rank,
                pairing_id=days[0].pairing_id,
                day_indexes=[d.day_index for d in days],
                flight_ids=[f for d in days for f in d.flight_ids],
                action=(
                    f"Move {candidate.rank} {crew_id} off {source_pairing} onto "
                    f"{days[0].pairing_id}"
                ),
                candidate=candidate,
            )
            frontier.append(Chain(links=[link], vacated=(source_pairing, crew_id)))

    frontier.sort(key=lambda c: c.cost_inr)
    frontier = frontier[: BEAM_WIDTH * 2]

    # ---- backfill the hole each move leaves, until the chain closes ----
    for _ in range(MAX_CHAIN_DEPTH - 1):
        if not frontier:
            break
        next_frontier: list[Chain] = []
        for chain in frontier:
            if chain.complete:
                complete.append(chain)
                continue
            source_pairing, moved_crew = chain.vacated
            pairing = repo.pairings[source_pairing]
            gap_days = pairing.days
            used = chain.crew_used() | exclude_crew | {moved_crew}

            for crew in repo.crew_by_rank(role, active_only=True):
                if crew.crew_id in used:
                    continue
                candidate = build_candidate(repo, crew.crew_id, gap_days)
                if not candidate.legal:
                    continue
                link = ChainLink(
                    crew_id=crew.crew_id,
                    rank=candidate.rank,
                    pairing_id=source_pairing,
                    day_indexes=[d.day_index for d in gap_days],
                    flight_ids=[f for d in gap_days for f in d.flight_ids],
                    action=f"Backfill {source_pairing} with {candidate.rank} {crew.crew_id} ({candidate.label})",
                    candidate=candidate,
                )
                closed = Chain(links=chain.links + [link], vacated=None)
                next_frontier.append(closed)

        next_frontier.sort(key=lambda c: c.cost_inr)
        frontier = next_frontier[:BEAM_WIDTH]
        complete.extend(c for c in frontier if c.complete)
        frontier = [c for c in frontier if not c.complete]

    # dedupe on the crew sequence, keep the cheapest of each shape
    best: dict[tuple[str, ...], Chain] = {}
    for chain in complete:
        key = tuple(link.crew_id for link in chain.links)
        if key not in best or chain.cost_inr < best[key].cost_inr:
            best[key] = chain
    return sorted(best.values(), key=lambda c: (c.cost_inr, c.depth))
