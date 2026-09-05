"""Domain objects. Plain dataclasses so the engine never touches SQL rows directly."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.domain.time_utils import hours_between

PILOT_RANKS = ("Captain", "First Officer")

# Crew complement per aircraft type is NOT written down here: it is derived from the
# shapes actually rostered in the data (repo.conventions.complement). Hardcoding it
# would be a second source of truth that a fleet change could silently invalidate.


@dataclass(frozen=True)
class Crew:
    crew_id: str
    name: str
    rank: str
    base: str
    ratings: tuple[str, ...]
    seniority: int
    reachability_minutes: int
    status: str

    @property
    def is_pilot(self) -> bool:
        return self.rank in PILOT_RANKS


@dataclass(frozen=True)
class Flight:
    flight_id: str
    flight_no: str
    date: str
    dep_station: str
    arr_station: str
    dep_utc: datetime
    arr_utc: datetime
    block_hours: float
    aircraft: str
    aircraft_type: str
    seats: int


@dataclass(frozen=True)
class PairingDay:
    pairing_id: str
    day_index: int
    date: date
    report_utc: datetime
    release_utc: datetime
    flight_ids: tuple[str, ...]

    @property
    def sectors(self) -> int:
        return len(self.flight_ids)

    @property
    def duty_hours(self) -> float:
        return hours_between(self.report_utc, self.release_utc)

    @property
    def key(self) -> tuple[str, int]:
        return (self.pairing_id, self.day_index)


@dataclass
class Pairing:
    pairing_id: str
    aircraft: str
    days: list[PairingDay] = field(default_factory=list)
    crew: dict[str, str] = field(default_factory=dict)  # crew_id -> role

    @property
    def all_flight_ids(self) -> list[str]:
        return [fid for d in self.days for fid in d.flight_ids]

    @property
    def dates(self) -> list[date]:
        return [d.date for d in self.days]


@dataclass(frozen=True)
class Reserve:
    crew_id: str
    base: str
    window_start: str
    window_end: str
    dates: frozenset[str]


@dataclass(frozen=True)
class Certification:
    crew_id: str
    cert_type: str
    valid_from: date
    valid_to: date


@dataclass(frozen=True)
class RiskSignal:
    crew_id: str
    score: float
    drivers: tuple[str, ...]


@dataclass(frozen=True)
class DutyBlock:
    """One occupied duty period for a crew member, real or simulated."""
    date: date
    report_utc: datetime
    release_utc: datetime
    duty_hours: float
    flight_hours: float
    pairing_id: str

    @property
    def is_simulated(self) -> bool:
        return self.pairing_id == "COVER"
