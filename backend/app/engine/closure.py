"""Station closure recovery.

A closure is not a crew shortage, and modelling it as one gives the wrong answer. The
flights are not uncrewed -- they are *stuck*. The real question per leg is:

    how long until it can move, and does the crew's duty survive that delay?

For each leg touching the closed station inside the window:

    min_delay      = (reopen + turnaround buffer) - scheduled time at that station
                     (departure if it departs there, arrival if it arrives there)
    fdp_after      = the duty's normal length + that delay
                     -- a delay EXTENDS a duty, it does not shift it: the crew have
                        already reported, so only the release moves
    legal          = fdp_after <= RULE-FDP-01 limit for that sector count

Where the duty survives, the answer is simply "delay it". Where it does not, the crew
run out of hours mid-rotation and the choice is to re-crew the tail of the duty or
cancel those legs. Cancelling everything is the expensive fallback, not the plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.engine import splitting
from app.engine.cost import cancellation_cost
from app.rules.r01_fdp import fdp_limit

# Slots do not reopen instantly: the first movement clears a little after the field does.
REOPEN_BUFFER_MINUTES = 30

ACTION_LEGAL = "delay (crew legal)"
ACTION_BREACH = "delay exceeds crew FDP - re-crew tail legs from reserves or cancel"


@dataclass
class ClosureLeg:
    flight_id: str
    flight_no: str
    pairing_id: str
    day_index: int
    side: str                    # "departure" | "arrival"
    event_utc: datetime
    min_delay_hours: float
    duty_hours: float
    crew_fdp_after_delay: float
    fdp_limit: float
    seats: int

    @property
    def legal(self) -> bool:
        return self.crew_fdp_after_delay <= self.fdp_limit + 1e-6

    @property
    def action(self) -> str:
        return ACTION_LEGAL if self.legal else ACTION_BREACH

    def to_dict(self) -> dict:
        return {
            "flight_id": self.flight_id,
            "flight_no": self.flight_no,
            "pairing_id": self.pairing_id,
            "min_delay_hours": self.min_delay_hours,
            "crew_fdp_after_delay": self.crew_fdp_after_delay,
            "fdp_limit": self.fdp_limit,
            "action": self.action,
        }


@dataclass
class ClosurePlan:
    station: str
    start: datetime
    end: datetime
    legs: list[ClosureLeg] = field(default_factory=list)
    options: list[dict] = field(default_factory=list)

    @property
    def pairings(self) -> list[str]:
        seen: list[str] = []
        for leg in self.legs:
            if leg.pairing_id not in seen:
                seen.append(leg.pairing_id)
        return seen

    @property
    def passengers(self) -> int:
        return sum(leg.seats for leg in self.legs)


def _affected_legs(repo, station: str, start: datetime, end: datetime) -> list[ClosureLeg]:
    reopen = end + timedelta(minutes=REOPEN_BUFFER_MINUTES)
    legs: list[ClosureLeg] = []

    for flight in repo.flights.values():
        if flight.dep_station == station and start <= flight.dep_utc <= end:
            side, event = "departure", flight.dep_utc
        elif flight.arr_station == station and start <= flight.arr_utc <= end:
            side, event = "arrival", flight.arr_utc
        else:
            continue

        pairing_id = repo.flight_to_pairing.get(flight.flight_id)
        if not pairing_id:
            continue
        day = next(
            d for d in repo.pairings[pairing_id].days if flight.flight_id in d.flight_ids
        )

        delay = round((reopen - event).total_seconds() / 3600.0, 2)
        legs.append(
            ClosureLeg(
                flight_id=flight.flight_id,
                flight_no=flight.flight_no,
                pairing_id=pairing_id,
                day_index=day.day_index,
                side=side,
                event_utc=event,
                min_delay_hours=delay,
                duty_hours=day.duty_hours,
                crew_fdp_after_delay=round(day.duty_hours + delay, 2),
                fdp_limit=fdp_limit(repo, day.sectors),
                seats=flight.seats,
            )
        )

    legs.sort(key=lambda x: (-x.min_delay_hours, x.flight_no))
    return legs


def plan(repo, station: str, start: datetime, end: datetime) -> ClosurePlan:
    """Per-leg delay analysis plus a costed recovery option for each affected pairing."""
    legs = _affected_legs(repo, station, start, end)
    result = ClosurePlan(station=station, start=start, end=end, legs=legs)

    by_pairing: dict[str, list[ClosureLeg]] = {}
    for leg in legs:
        by_pairing.setdefault(leg.pairing_id, []).append(leg)

    for pairing_id, pairing_legs in sorted(by_pairing.items()):
        pairing = repo.pairings[pairing_id]
        day = pairing.days[pairing_legs[0].day_index]
        # the whole duty shifts behind its earliest blocked leg
        delay = max(leg.min_delay_hours for leg in pairing_legs)
        blocked_nos = ", ".join(leg.flight_no for leg in pairing_legs)

        if all(leg.legal for leg in pairing_legs):
            hourly = repo.cost("delay_cost_per_duty_hour")
            result.options.append({
                "pairing_id": pairing_id,
                "action": f"[{pairing_id}] Delay {blocked_nos} to reopen (+{delay}h)",
                "legal": True,
                "kind": "delay",
                "cost_inr": int(round(delay * hourly)),
                "cost_breakdown": [{
                    "label": f"Delay cost ({delay}h x {int(hourly):,}/h)",
                    "amount_inr": int(round(delay * hourly)),
                }],
                "coverage": f"all {len(day.flight_ids)} flights",
                "covered_flight_ids": list(day.flight_ids),
                "uncovered_flight_ids": [],
                "delay_minutes": int(round(delay * 60)),
                "resilience_score": 1.0,
                "resilience_note": "consumes no crew capacity",
                "chain": [],
                "reasoning": (
                    f"Duty runs {round(day.duty_hours + delay, 2)}h against a "
                    f"{fdp_limit(repo, day.sectors)}h limit over {day.sectors} sectors, "
                    f"so the rostered crew stay legal through the delay."
                ),
            })
            continue

        # the incumbent crew cannot absorb the delay: fly what they legally can and
        # bring in a fresh complement for the rest
        split = splitting.plan_split(repo, day, pairing.crew, delay)
        if split and split.feasible:
            kept = ", ".join(repo.flights[f].flight_no for f in split.keep_flight_ids)
            recrew = ", ".join(repo.flights[f].flight_no for f in split.recrew_flight_ids)
            result.options.append({
                "pairing_id": pairing_id,
                "action": (
                    f"[{pairing_id}] Delay to reopen; original crew operate {kept}, "
                    f"fresh complement operates {recrew}"
                ),
                "legal": True,
                "kind": "recrew",
                "cost_inr": split.recrew_cost_inr,
                "cost_breakdown": split.cost_lines,
                "coverage": f"all {len(day.flight_ids)} flights",
                "covered_flight_ids": list(day.flight_ids),
                "uncovered_flight_ids": [],
                "delay_minutes": int(round(delay * 60)),
                "resilience_score": 1.0,
                "resilience_note": (
                    f"commits {len(split.recrew_crew)} crew for {len(split.recrew_flight_ids)} "
                    f"sector(s) instead of losing the rotation"
                ),
                "chain": [],
                "reasoning": (
                    f"A {delay}h delay pushes the duty to "
                    f"{round(day.duty_hours + delay, 2)}h against a "
                    f"{fdp_limit(repo, day.sectors)}h limit. The reduced duty runs "
                    f"{split.kept_duty_hours}h against {split.kept_limit}h, so the "
                    f"rostered crew stay legal for {kept}. {split.detail}."
                ),
            })

        cancel_ids = [leg.flight_id for leg in pairing_legs]
        breakdown = cancellation_cost(repo, len(cancel_ids))
        seats = sum(leg.seats for leg in pairing_legs)
        result.options.append({
            "pairing_id": pairing_id,
            "action": f"[{pairing_id}] Cancel {blocked_nos}",
            "legal": True,
            "kind": "cancel",
            "cost_inr": breakdown.total,
            "cost_breakdown": breakdown.to_list(),
            "coverage": f"{len(day.flight_ids) - len(cancel_ids)} of {len(day.flight_ids)} flights",
            "covered_flight_ids": [f for f in day.flight_ids if f not in cancel_ids],
            "uncovered_flight_ids": cancel_ids,
            "delay_minutes": 0,
            "resilience_score": 1.0,
            "resilience_note": "consumes no crew capacity",
            "chain": [],
            "reasoning": (
                f"Fallback if no fresh complement can be assembled. Strands {seats} "
                f"passengers."
            ),
        })

    # cheapest workable option per pairing first, cancellation last within each pairing
    order = {"delay": 0, "recrew": 1, "cancel": 2}
    result.options.sort(key=lambda o: (o["pairing_id"], order[o["kind"]], o["cost_inr"]))
    for i, option in enumerate(result.options, start=1):
        option["rank"] = i
    return result
