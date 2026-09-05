"""Operating conventions, read from the dataset rather than assumed.

Four facts the engine needs are stated by the data itself, so we derive them instead of
writing them down a second time:

  * the snapshot ("now")     -- duty_clocks.as_of_utc
  * the operating week       -- min/max flight date
  * crew complement per type -- the shapes actually rostered
  * report / release offsets -- the gap between report and first departure

Hardcoding any of these would create a second source of truth that can silently fall out
of step with the data. Each derivation asserts the dataset is self-consistent and says so
loudly if it is not, because a dataset with two different complements for one aircraft
type is something a controller needs told, not quietly averaged.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Conventions:
    snapshot_utc: datetime
    week_start: str
    week_end: str
    complement: dict[str, dict[str, int]]
    report_lead: timedelta
    release_trail: timedelta

    @property
    def snapshot_date(self):
        return self.snapshot_utc.date()


def _derive_snapshot(repo) -> datetime:
    """Every duty clock is stated 'as of' the same instant; that instant is now."""
    from app.domain.time_utils import parse_utc

    stamps = {c["as_of_utc"] for c in repo.clocks.values()}
    if len(stamps) != 1:
        raise ValueError(f"duty_clocks disagree about the snapshot: {sorted(stamps)}")
    return parse_utc(next(iter(stamps)))


def _derive_week(repo) -> tuple[str, str]:
    dates = {f.date for f in repo.flights.values()}
    return min(dates), max(dates)


def _derive_complement(repo) -> dict[str, dict[str, int]]:
    """The crew composition each aircraft type is actually rostered with."""
    shapes: dict[str, Counter] = defaultdict(Counter)
    for pairing in repo.pairings.values():
        if not pairing.days:
            continue
        actype = repo.day_aircraft_type(pairing.days[0])
        roles = Counter(pairing.crew.values())
        shapes[actype][tuple(sorted(roles.items()))] += 1

    out: dict[str, dict[str, int]] = {}
    for actype, seen in shapes.items():
        if len(seen) > 1:
            # more than one shape flown on a type: report it rather than pick one
            raise ValueError(
                f"{actype} is rostered with {len(seen)} different complements: "
                f"{[dict(s) for s in seen]}"
            )
        out[actype] = dict(next(iter(seen)))
    return out


def _derive_brackets(repo) -> tuple[timedelta, timedelta]:
    """How far report sits before the first departure, and release after the last arrival."""
    leads: set[float] = set()
    trails: set[float] = set()
    for pairing in repo.pairings.values():
        for day in pairing.days:
            legs = sorted((repo.flights[f] for f in day.flight_ids), key=lambda f: f.dep_utc)
            leads.add((legs[0].dep_utc - day.report_utc).total_seconds() / 60)
            trails.add((day.release_utc - legs[-1].arr_utc).total_seconds() / 60)
    if len(leads) != 1 or len(trails) != 1:
        raise ValueError(
            f"inconsistent duty brackets: report leads {sorted(leads)}, "
            f"release trails {sorted(trails)}"
        )
    return timedelta(minutes=leads.pop()), timedelta(minutes=trails.pop())


def derive(repo) -> Conventions:
    week_start, week_end = _derive_week(repo)
    lead, trail = _derive_brackets(repo)
    return Conventions(
        snapshot_utc=_derive_snapshot(repo),
        week_start=week_start,
        week_end=week_end,
        complement=_derive_complement(repo),
        report_lead=lead,
        release_trail=trail,
    )
