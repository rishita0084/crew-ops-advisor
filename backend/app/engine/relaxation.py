"""Near-miss analysis: when nothing is legal, what would MAKE something legal?

"No legal option exists" is a true answer and a useless one. A controller needs to know
how close the closest option was and what specific change closes the gap. Every rule
reports a signed margin, so inverting the binding constraint is arithmetic, not
guesswork.

This never relaxes a rule on its own authority -- it states the trade the controller
would have to authorise.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import PairingDay
from app.domain.time_utils import fmt_hours_minutes
from app.engine.candidates import Candidate, build_candidate


@dataclass
class Relaxation:
    rule_id: str
    breach_detail: str
    breach_magnitude: str
    remedy: str
    crew_id: str
    resulting_option_rank: int | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "breach_detail": self.breach_detail,
            "breach_magnitude": self.breach_magnitude,
            "remedy": self.remedy,
            "resulting_option_rank": self.resulting_option_rank,
        }


def _drop_leg_remedy(repo, candidate: Candidate, shortfall: float) -> str | None:
    """Can dropping the last sector of a day bring the duty back under the limit?"""
    for day in reversed(candidate.days):
        if day.sectors <= 1:
            continue
        last = repo.flights[day.flight_ids[-1]]
        prev_arrival = repo.flights[day.flight_ids[-2]].arr_utc
        # release tracks the last arrival, so dropping the final leg shortens the duty
        # by the gap between the two arrivals
        saved = round((last.arr_utc - prev_arrival).total_seconds() / 3600.0, 2)
        if saved >= shortfall:
            return (
                f"drop {last.flight_no} ({last.dep_station}-{last.arr_station}) from "
                f"{day.date}: releases {saved}h of duty, {last.seats} seats to reaccommodate"
            )
    return None


def analyse(
    repo, days: list[PairingDay], role: str, exclude_crew: set[str], limit: int = 3
) -> list[Relaxation]:
    """Rank illegal candidates by how small their breach is, and say what would fix each."""
    near: list[tuple[float, Candidate]] = []

    for crew in repo.crew_by_rank(role, active_only=True):
        if crew.crew_id in exclude_crew:
            continue
        candidate = build_candidate(repo, crew.crew_id, days)
        if candidate.legal:
            continue
        failures = candidate.verdict.failures
        # only quantifiable, single-rule breaches are actionable
        rules_failed = {f.rule_id for f in failures}
        if len(rules_failed) != 1:
            continue
        quantified = [f for f in failures if f.margin is not None]
        if not quantified:
            continue
        worst = min(quantified, key=lambda f: f.margin)
        if worst.margin is None or worst.margin >= 0:
            continue
        near.append((abs(worst.margin), candidate))

    near.sort(key=lambda pair: (pair[0], pair[1].crew_id))
    out: list[Relaxation] = []

    for shortfall, candidate in near[:limit]:
        worst = min(
            (f for f in candidate.verdict.failures if f.margin is not None),
            key=lambda f: f.margin,
        )
        remedy = _remedy_for(repo, worst.rule_id, candidate, shortfall)
        out.append(
            Relaxation(
                rule_id=worst.rule_id,
                breach_detail=f"{candidate.rank} {candidate.crew_id}: {worst.detail}",
                breach_magnitude=fmt_hours_minutes(shortfall),
                remedy=remedy,
                crew_id=candidate.crew_id,
            )
        )
    return out


def _remedy_for(repo, rule_id: str, candidate: Candidate, shortfall: float) -> str:
    who = f"{candidate.rank} {candidate.crew_id}"
    if rule_id in ("RULE-DUTY-02", "RULE-FDP-01"):
        drop = _drop_leg_remedy(repo, candidate, shortfall)
        if drop:
            return f"To use {who}, {drop}."
        return (
            f"To use {who}, {fmt_hours_minutes(shortfall)} of duty must come off their "
            f"window -- release another rostered duty in the same 7 days, or split the "
            f"pairing across two crew."
        )
    if rule_id == "RULE-FLT-03":
        return (
            f"To use {who}, {fmt_hours_minutes(shortfall)} of block time must come off "
            f"their 28-day window -- assign the shortest day of the pairing only."
        )
    if rule_id == "RULE-REST-04":
        return (
            f"To use {who}, delay the first departure by {fmt_hours_minutes(shortfall)} "
            f"so the 12h rest requirement is met, or release them from the adjacent duty."
        )
    return f"{who} is {fmt_hours_minutes(shortfall)} short of {rule_id}."
