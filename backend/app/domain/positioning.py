"""Deadhead positioning (RULE-BASE-07).

Crew based away from the departure station can still cover a pairing, but they have
to be flown in first. Rather than hardcoding the DEL->BLR pair, we search the actual
schedule for the earliest same-day flight from their base to the station needed, then
work out how far that pushes the first departure.

Convention (dataset README): new report = positioning arrival + 15 min transit, and
report is 60 min before departure -- so the earliest the duty can start is
arrival + 75 min.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.domain.models import Flight, PairingDay

# Minimum ground time between a positioning arrival and signing on for the next duty.
# Not stated anywhere in the dataset, so it stays an explicit assumption rather than a
# derivation pretending to be one.
TRANSIT_MINUTES = 15


@dataclass(frozen=True)
class Positioning:
    required: bool
    feasible: bool
    flight: Flight | None
    delay_hours: float
    detail: str


def plan(repo, crew_id: str, first_day: PairingDay) -> Positioning:
    """Work out whether `crew_id` needs positioning for `first_day`, and at what delay."""
    crew = repo.crew[crew_id]
    origin_flight = repo.flights[first_day.flight_ids[0]]
    station_needed = origin_flight.dep_station

    if crew.base == station_needed:
        return Positioning(
            required=False, feasible=True, flight=None, delay_hours=0.0,
            detail=f"based at {station_needed}, no positioning required",
        )

    candidates = [
        f for f in repo.flights_by_date.get(first_day.date.isoformat(), [])
        if f.dep_station == crew.base and f.arr_station == station_needed
    ]
    if not candidates:
        return Positioning(
            required=True, feasible=False, flight=None, delay_hours=0.0,
            detail=(
                f"no same-day positioning flight {crew.base}->{station_needed} "
                f"on {first_day.date}"
            ),
        )

    best = min(candidates, key=lambda f: f.arr_utc)
    earliest_departure = (
        best.arr_utc + timedelta(minutes=TRANSIT_MINUTES) + repo.conventions.report_lead
    )
    delay = max(0.0, round((earliest_departure - origin_flight.dep_utc).total_seconds() / 3600.0, 2))
    return Positioning(
        required=True, feasible=True, flight=best, delay_hours=delay,
        detail=(
            f"deadhead {crew.base}->{station_needed} on {best.flight_no} "
            f"(arrives {best.arr_utc.strftime('%H:%M')}Z); first departure delayed {delay}h"
            if delay > 0
            else f"deadhead {crew.base}->{station_needed} on {best.flight_no}, no delay"
        ),
    )
