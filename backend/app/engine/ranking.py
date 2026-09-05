"""Turn a vacancy into ranked, explained recovery options.

Order of business:
  1. enumerate every same-rank candidate and run the full ruleset (candidates.py)
  2. discard illegal ones -- a hard filter, never a penalty term
  3. search multi-step swap chains when direct cover is thin (chains.py)
  4. always offer cancellation as the honest fallback
  5. rank on cost, then crew_id for stability
  6. attach resilience so the cheap-but-brittle option is visibly cheap-but-brittle

The dataset's own answer keys rank purely on cost, so cost is the primary key and
resilience is surfaced as decision support rather than silently reordering results.
"""
from __future__ import annotations

from app.engine import chains as chains_mod
from app.engine import resilience as resilience_mod
from app.engine.candidates import Candidate, enumerate_candidates
from app.engine.cost import cancellation_cost
from app.domain.models import PairingDay
from app.rules.registry import ALL_RULES, summarise


def _coverage(days: list[PairingDay]) -> tuple[str, list[str]]:
    flight_ids = [f for d in days for f in d.flight_ids]
    return f"all {len(flight_ids)} flights", flight_ids


def _option_from_candidate(
    repo, candidate: Candidate, days: list[PairingDay], rank: int, resilience
) -> dict:
    coverage, flight_ids = _coverage(days)
    return {
        "rank": rank,
        "action": candidate.action,
        "legal": True,
        "rules_checked": ALL_RULES,
        "rule_checks": summarise(candidate.verdict),
        "cost_inr": candidate.cost_inr,
        "cost_breakdown": candidate.cost.to_list(),
        "coverage": coverage,
        "covered_flight_ids": flight_ids,
        "uncovered_flight_ids": [],
        "delay_minutes": int(round(candidate.delay_hours * 60)),
        "resilience_score": resilience.score if resilience else 1.0,
        "resilience_note": resilience.note if resilience else "",
        "chain": [],
        "reasoning": _reasoning(repo, candidate),
    }


def _reasoning(repo, candidate: Candidate) -> str:
    crew = repo.crew[candidate.crew_id]
    bits = [f"{crew.base}-based", f"{'/'.join(crew.ratings)}-rated"]
    if repo.is_reserve(candidate.crew_id):
        reserve = repo.reserves[candidate.crew_id]
        bits.append(f"on call {reserve.window_start}-{reserve.window_end}Z")
    else:
        bits.append("not rostered on these dates")
    bits.append(f"reachable in {crew.reachability_minutes} min")

    duty = next(
        (r for r in candidate.verdict.results if r.rule_id == "RULE-DUTY-02"), None
    )
    if duty and duty.margin is not None:
        bits.append(f"{duty.margin}h duty headroom remaining")
    if candidate.positioning.required:
        bits.append(candidate.positioning.detail)
    return "; ".join(bits) + "."


def _option_from_chain(repo, chain: chains_mod.Chain, days: list[PairingDay], rank: int) -> dict:
    coverage, flight_ids = _coverage(days)
    merged_checks: list[dict] = []
    for link in chain.links:
        merged_checks.extend(summarise(link.candidate.verdict))
    return {
        "rank": rank,
        "action": chain.describe(),
        "legal": True,
        "rules_checked": ALL_RULES,
        "rule_checks": merged_checks,
        "cost_inr": chain.cost_inr,
        "cost_breakdown": [
            line for link in chain.links for line in link.candidate.cost.to_list()
        ],
        "coverage": coverage,
        "covered_flight_ids": flight_ids,
        "uncovered_flight_ids": [],
        "delay_minutes": int(round(chain.delay_hours * 60)),
        "resilience_score": 1.0,
        "resilience_note": (
            f"{chain.depth}-step swap keeps the reserve pool intact; "
            f"every move was checked against all seven rules"
        ),
        "chain": [link.to_dict(i + 1) for i, link in enumerate(chain.links)],
        "reasoning": (
            "No single free crew member could cover the whole pairing legally, so this "
            "moves a rostered crew member across and backfills the pairing they leave."
        ),
    }


def _cancellation_option(repo, days: list[PairingDay], rank: int) -> dict:
    _, flight_ids = _coverage(days)
    breakdown = cancellation_cost(repo, len(flight_ids))
    return {
        "rank": rank,
        "action": f"Cancel all {len(flight_ids)} flights of the pairing",
        "legal": True,
        "rules_checked": [],
        "rule_checks": [],
        "cost_inr": breakdown.total,
        "cost_breakdown": breakdown.to_list(),
        "coverage": "no flights covered",
        "covered_flight_ids": [],
        "uncovered_flight_ids": flight_ids,
        "delay_minutes": 0,
        "resilience_score": 1.0,
        "resilience_note": "consumes no crew capacity",
        "chain": [],
        "reasoning": (
            f"Baseline fallback. {sum(repo.flights[f].seats for f in flight_ids)} seats "
            f"to reaccommodate; shown so every cheaper option can be read against it."
        ),
    }


def rank_options(
    repo,
    days: list[PairingDay],
    role: str,
    exclude_crew: set[str] | None = None,
    exclude_pairing: str | None = None,
    include_chains: bool = True,
) -> dict:
    """Full Tier-3 result for one vacancy."""
    exclude_crew = set(exclude_crew or set())
    legal, excluded = enumerate_candidates(
        repo, days, role, exclude_crew=exclude_crew, exclude_pairing=exclude_pairing
    )

    pool = [c.crew_id for c in legal]
    options: list[dict] = []
    for candidate in legal:
        res = resilience_mod.assess(repo, days, role, {candidate.crew_id}, pool)
        options.append(_option_from_candidate(repo, candidate, days, 0, res))

    chain_options: list[dict] = []
    if include_chains and len(legal) <= 2:
        # direct cover is thin, so a swap cascade is worth the search
        found = chains_mod.search(
            repo, days, role, exclude_crew | set(pool), vacated_pairing=exclude_pairing
        )
        chain_options = [_option_from_chain(repo, c, days, 0) for c in found[:3]]

    options.extend(chain_options)
    options.sort(key=lambda o: (o["cost_inr"], o["action"]))
    options.append(_cancellation_option(repo, days, 0))

    for i, option in enumerate(options, start=1):
        option["rank"] = i

    relaxations: list[dict] = []
    if not legal and not chain_options:
        from app.engine import relaxation as relaxation_mod

        relaxations = [
            r.to_dict()
            for r in relaxation_mod.analyse(repo, days, role, exclude_crew)
        ]

    return {
        "options": options,
        "excluded": excluded,
        "relaxations": relaxations,
        "legal_count": len(legal),
        "chain_count": len(chain_options),
        "pool": pool,
    }
