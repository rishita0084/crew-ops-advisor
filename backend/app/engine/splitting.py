"""Splitting a duty when a delay pushes it past the FDP limit.

A delayed duty does not have to be abandoned. If the crew can legally fly the first N
sectors and only the tail of the duty is illegal, the operational answer is to let them
finish those sectors and re-crew the last leg with a fresh complement. That is cheaper
than cancelling and keeps the passengers moving, and it is invisible to any engine that
only asks "can this crew do the whole pairing, yes or no?".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.domain.models import PairingDay
from app.engine.candidates import build_candidate
from app.rules.r01_fdp import fdp_limit
from app.rules.result import CoverRequest
from app.rules import registry

# report/release brackets come from repo.conventions, derived from the rostered data


@dataclass
class Split:
    keep_flight_ids: list[str]
    recrew_flight_ids: list[str]
    kept_duty_hours: float
    kept_limit: float
    kept_legal: bool
    recrew_crew: dict[str, str]        # role -> crew_id
    recrew_cost_inr: int
    cost_lines: list[dict]
    feasible: bool
    detail: str


def synthetic_day(repo, source: PairingDay, flight_ids: list[str],
                  delay_hours: float = 0.0) -> PairingDay:
    """A duty period covering just these legs, with report/release recomputed."""
    offset = timedelta(hours=delay_hours)
    first = repo.flights[flight_ids[0]]
    last = repo.flights[flight_ids[-1]]
    return PairingDay(
        pairing_id=source.pairing_id,
        day_index=source.day_index,
        date=source.date,
        report_utc=first.dep_utc + offset - repo.conventions.report_lead,
        release_utc=last.arr_utc + offset + repo.conventions.release_trail,
        flight_ids=tuple(flight_ids),
    )


def plan_split(repo, day: PairingDay, incumbent_crew: dict[str, str],
               delay_hours: float) -> Split | None:
    """Find the longest prefix of the duty the rostered crew can still legally fly.

    Returns None when the duty is legal as-is or when no split helps.
    """
    legs = list(day.flight_ids)
    if len(legs) < 2:
        return None

    for keep_count in range(len(legs) - 1, 0, -1):
        keep = legs[:keep_count]
        recrew = legs[keep_count:]
        kept = synthetic_day(repo, day, keep, delay_hours)
        limit = fdp_limit(repo, len(keep))
        duty = kept.duty_hours

        if duty > limit + 1e-6:
            continue   # still too long, drop another leg

        # confirm against the FULL ruleset for every rostered crew member, not just FDP
        all_legal = True
        for crew_id in incumbent_crew:
            verdict = registry.evaluate(
                repo,
                CoverRequest(crew_id=crew_id, days=[kept],
                             exclude_pairing=day.pairing_id),
            )
            if not verdict.legal:
                all_legal = False
                break
        if not all_legal:
            continue

        assignment, cost, lines, ok, detail = _crew_the_remainder(
            repo, day, recrew, delay_hours
        )
        return Split(
            keep_flight_ids=keep,
            recrew_flight_ids=recrew,
            kept_duty_hours=duty,
            kept_limit=limit,
            kept_legal=True,
            recrew_crew=assignment,
            recrew_cost_inr=cost,
            cost_lines=lines,
            feasible=ok,
            detail=detail,
        )
    return None


def _crew_the_remainder(repo, day: PairingDay, flight_ids: list[str],
                        delay_hours: float) -> tuple[dict[str, str], int, list[dict], bool, str]:
    """Assemble a complete fresh complement for the legs the rostered crew cannot fly."""
    tail_day = synthetic_day(repo, day, flight_ids, delay_hours)
    actype = repo.flights[flight_ids[0]].aircraft_type
    needed = repo.conventions.complement.get(actype, {})

    assignment: dict[str, str] = {}
    total = 0
    callout_total = 0
    positioning_total = 0
    used: set[str] = set()
    missing: list[str] = []

    for role, count in needed.items():
        # cost the whole eligible pool before choosing, so reserves (cheaper callout)
        # are taken ahead of day-off crew rather than whoever iterates first
        pool = []
        for crew in repo.crew_by_rank(role, active_only=True):
            if crew.crew_id in used:
                continue
            candidate = build_candidate(repo, crew.crew_id, [tail_day])
            if candidate.legal:
                pool.append(candidate)
        pool.sort(key=lambda c: (c.cost_inr, c.crew_id))

        picked = 0
        for candidate in pool[:count]:
            used.add(candidate.crew_id)
            assignment[f"{role} {picked + 1}" if count > 1 else role] = candidate.crew_id
            total += candidate.cost_inr
            # split the figure so a controller sees callout and positioning separately
            for line in candidate.cost.to_list():
                if "eadhead" in line["label"] or "elay" in line["label"]:
                    positioning_total += line["amount_inr"]
                else:
                    callout_total += line["amount_inr"]
            picked += 1
        if picked < count:
            missing.append(f"{count - picked} x {role}")

    legs = ", ".join(repo.flights[f].flight_no for f in flight_ids)
    station = repo.flights[flight_ids[0]].dep_station
    lines = [{"label": f"Callout x {len(assignment)} crew", "amount_inr": callout_total}]
    if positioning_total:
        lines.append({
            "label": f"Positioning to {station} x {len(assignment)} crew",
            "amount_inr": positioning_total,
        })

    if missing:
        return assignment, total, lines, False, (
            f"cannot assemble a full {actype} complement for {legs}: short of "
            + ", ".join(missing)
        )
    detail = f"fresh {actype} complement ({len(assignment)} crew) operates {legs}"
    if positioning_total:
        detail += (
            f"; {legs} departs {station}, so the complement must be positioned there "
            f"(INR {positioning_total:,})"
        )
    return assignment, total, lines, True, detail
