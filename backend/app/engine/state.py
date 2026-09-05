"""Copy-on-write operational state.

Every scenario is an alternate timeline branched from the base snapshot. Applying an
event returns a NEW state; the base is never mutated, so scenarios cannot contaminate
each other and a what-if can never change the real roster. Several events can be layered
onto one state, which is how simultaneous disruptions are solved jointly rather than
one at a time.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime

from app.domain.models import Flight, PairingDay
from app.domain.time_utils import parse_date, parse_utc, time_on_date


@dataclass(frozen=True)
class Event:
    kind: str                    # crew_unavailable | flight_delay | station_closure | crew_reassignment
    detail: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OperationalState:
    """An immutable view of the operation with zero or more disruptions applied."""

    unavailable_crew: frozenset[str] = frozenset()
    delayed_flights: tuple[tuple[str, float], ...] = ()          # (flight_id, hours)
    closures: tuple[tuple[str, datetime, datetime], ...] = ()    # (station, from, to)
    reassignments: tuple[tuple[str, str, str], ...] = ()         # (pairing_id, out, in)
    events: tuple[Event, ...] = ()

    # ---------- event application (each returns a new state) ----------
    def with_crew_unavailable(self, crew_id: str, reason: str = "unavailable") -> "OperationalState":
        return replace(
            self,
            unavailable_crew=self.unavailable_crew | {crew_id},
            events=self.events + (Event("crew_unavailable", f"{crew_id} {reason}", {"crew_id": crew_id}),),
        )

    def with_flight_delay(self, flight_id: str, hours: float) -> "OperationalState":
        return replace(
            self,
            delayed_flights=self.delayed_flights + ((flight_id, hours),),
            events=self.events + (
                Event("flight_delay", f"{flight_id} delayed {hours}h",
                      {"flight_id": flight_id, "hours": hours}),
            ),
        )

    def with_station_closure(self, station: str, start: datetime, end: datetime) -> "OperationalState":
        return replace(
            self,
            closures=self.closures + ((station, start, end),),
            events=self.events + (
                Event(
                    "station_closure",
                    f"{station} closed {start.strftime('%H:%M')}-{end.strftime('%H:%M')}Z "
                    f"on {start.date()}",
                    {"station": station, "start": start.isoformat(), "end": end.isoformat()},
                ),
            ),
        )

    def with_reassignment(self, pairing_id: str, crew_out: str, crew_in: str) -> "OperationalState":
        return replace(
            self,
            reassignments=self.reassignments + ((pairing_id, crew_out, crew_in),),
            events=self.events + (
                Event(
                    "crew_reassignment", f"{crew_in} replaces {crew_out} on {pairing_id}",
                    {"pairing_id": pairing_id, "crew_out": crew_out, "crew_in": crew_in},
                ),
            ),
        )

    # ---------- derived views ----------
    def is_available(self, crew_id: str) -> bool:
        return crew_id not in self.unavailable_crew

    def delay_for(self, flight_id: str) -> float:
        return sum(h for fid, h in self.delayed_flights if fid == flight_id)

    def flight_blocked(self, flight: Flight) -> tuple[bool, str]:
        """Is this flight stopped by a station closure at either end?"""
        for station, start, end in self.closures:
            if flight.dep_station == station and start <= flight.dep_utc <= end:
                return True, (
                    f"{flight.flight_no} departs {station} at "
                    f"{flight.dep_utc.strftime('%H:%M')}Z inside the closure"
                )
            if flight.arr_station == station and start <= flight.arr_utc <= end:
                return True, (
                    f"{flight.flight_no} arrives {station} at "
                    f"{flight.arr_utc.strftime('%H:%M')}Z inside the closure"
                )
        return False, ""

    def crew_on(self, repo, pairing_id: str) -> dict[str, str]:
        """Crew of a pairing after reassignments, keyed crew_id -> role."""
        roster = dict(repo.pairings[pairing_id].crew)
        for pid, out, incoming in self.reassignments:
            if pid == pairing_id and out in roster:
                roster[incoming] = roster.pop(out)
        return roster

    def uncovered_days(self, repo) -> list[tuple[PairingDay, list[str]]]:
        """Pairing-days missing at least one crew member, with the vacant roles."""
        gaps: list[tuple[PairingDay, list[str]]] = []
        for pairing in repo.pairings.values():
            roster = self.crew_on(repo, pairing.pairing_id)
            missing = [role for cid, role in roster.items() if cid in self.unavailable_crew]
            if missing:
                for day in pairing.days:
                    gaps.append((day, missing))
        return gaps

    @property
    def is_base(self) -> bool:
        return not self.events

    def describe(self) -> str:
        return "; ".join(e.detail for e in self.events) or "base snapshot"


BASE_STATE = OperationalState()


def state_from_events(repo, events: list[dict]) -> OperationalState:
    """Build a state from event dicts, in the shapes scenarios.json and the API use."""
    state = BASE_STATE
    for ev in events:
        kind = (ev.get("type") or ev.get("kind") or "").upper()

        if kind in ("MULTI_SICK", "MULTI", "COMBINED"):
            # simultaneous disruptions are layered onto ONE state and solved jointly
            for nested in ev.get("events", []):
                nested = dict(nested)
                nested.setdefault("type", "SICK_CREW")
                state = state_from_events_into(repo, state, nested)
            continue

        state = state_from_events_into(repo, state, ev)
    return state


def state_from_events_into(repo, state: "OperationalState", ev: dict) -> "OperationalState":
    kind = (ev.get("type") or ev.get("kind") or "").upper()

    if kind in ("SICK_CREW", "CREW_UNAVAILABLE", "CREW_SICK"):
        return state.with_crew_unavailable(ev["crew_id"], ev.get("reason", "sick"))

    if kind in ("CERT_EXPIRY", "CERTIFICATION_LAPSE"):
        # a lapsed certification removes the crew member exactly as a sick call does;
        # the difference is the reason a controller reads, not the arithmetic
        return state.with_crew_unavailable(ev["crew_id"], "certification lapsed")

    if kind in ("FLIGHT_DELAY", "DELAY", "TECH_DELAY"):
        hours = float(ev.get("delay_hours", ev.get("hours", 0)))
        if ev.get("flight_id"):
            return state.with_flight_delay(ev["flight_id"], hours)
        # aircraft-level delay: every leg that tail flies that day shifts
        tail, day = ev.get("aircraft"), ev.get("date")
        if tail and day:
            for flight in repo.flights_by_date.get(day, []):
                if flight.aircraft == tail:
                    state = state.with_flight_delay(flight.flight_id, hours)
        return state

    if kind in ("STATION_CLOSURE", "AIRPORT_CLOSURE"):
        window = ev.get("window_utc") or {}
        day = ev.get("date")
        start = window.get("start") or ev.get("start_utc") or ev.get("from")
        end = window.get("end") or ev.get("end_utc") or ev.get("to")
        return state.with_station_closure(
            ev["station"], _as_dt(day, start), _as_dt(day, end)
        )

    if kind in ("CREW_REASSIGNMENT", "REASSIGN"):
        return state.with_reassignment(ev["pairing_id"], ev["crew_out"], ev["crew_in"])

    return state


def _as_dt(day: str | date | None, value: str) -> datetime:
    """Accept either a full ISO timestamp or an 'HH:MM' paired with a date."""
    if value and len(value) > 5:
        return parse_utc(value) if value.endswith("Z") else datetime.fromisoformat(value)
    target = day if isinstance(day, date) else parse_date(str(day))
    return time_on_date(target, value)
