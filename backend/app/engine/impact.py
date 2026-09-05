"""Blast radius: what a disruption actually breaks.

The obvious answer is "the flight this crew was on". The useful answer traverses
crew -> pairing -> every day of that pairing -> every leg -> the aircraft rotation
behind those legs, and then back out to the OTHER crew whose duty now sits at risk.
That traversal is the whole point of Tier 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.engine.state import OperationalState
from app.rules import registry
from app.rules.result import CoverRequest


@dataclass
class ImpactResult:
    trigger: str
    uncrewed_flights: list[str] = field(default_factory=list)
    immediate_flights: list[str] = field(default_factory=list)
    at_risk_flights: list[str] = field(default_factory=list)
    pairings_broken: list[str] = field(default_factory=list)
    downstream_risks: list[dict] = field(default_factory=list)
    passengers_affected: int = 0
    blocked_flights: list[dict] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    vacancies: list[dict] = field(default_factory=list)   # role gaps to fill

    def to_dict(self) -> dict:
        return {
            "trigger": self.trigger,
            "uncrewed_flights": self.uncrewed_flights,
            "immediate_flights": self.immediate_flights,
            "at_risk_flights": self.at_risk_flights,
            "pairing_broken": self.pairings_broken,
            "downstream_risks": self.downstream_risks,
            "passengers_affected": self.passengers_affected,
            "graph": {"nodes": self.nodes, "edges": self.edges},
        }


def analyse(repo, state: OperationalState, on_date: date | None = None) -> ImpactResult:
    """Full consequence analysis for the disruptions currently applied to `state`."""
    result = ImpactResult(trigger=state.describe())
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_flights: set[str] = set()

    def node(node_id: str, label: str, kind: str, status: str) -> None:
        # a node already marked broken stays broken
        if node_id in nodes and nodes[node_id]["status"] == "broken":
            return
        nodes[node_id] = {"id": node_id, "label": label, "type": kind, "status": status}

    def edge(src: str, dst: str) -> None:
        if {"from": src, "to": dst} not in edges:
            edges.append({"from": src, "to": dst})

    # ---- 1. crew unavailability -> pairings -> legs ----
    for crew_id in sorted(state.unavailable_crew):
        crew = repo.crew.get(crew_id)
        label = f"{crew.rank} {crew_id}" if crew else crew_id
        node(crew_id, label, "crew", "broken")

        for pairing_id in repo.crew_pairings.get(crew_id, []):
            pairing = repo.pairings[pairing_id]
            role = pairing.crew.get(crew_id, "Crew")
            if pairing_id not in result.pairings_broken:
                result.pairings_broken.append(pairing_id)
            node(pairing_id, pairing_id, "pairing", "broken")
            edge(crew_id, pairing_id)

            for day in pairing.days:
                # A multi-day pairing loses day 1 immediately; later days are equally
                # uncovered but sit further out, and the pairing overnights down-route.
                # Both are reported; only the immediate day drives the passenger count.
                if on_date and day.date < on_date:
                    continue
                immediate = (on_date is None) or (day.date == on_date)
                result.vacancies.append(
                    {
                        "pairing_id": pairing_id,
                        "day_index": day.day_index,
                        "date": day.date.isoformat(),
                        "role": role,
                        "crew_out": crew_id,
                        "immediate": immediate,
                    }
                )
                for fid in day.flight_ids:
                    flight = repo.flights[fid]
                    node(fid, flight.flight_no, "flight",
                         "broken" if immediate else "at_risk")
                    edge(pairing_id, fid)
                    if fid not in seen_flights:
                        seen_flights.add(fid)
                        result.uncrewed_flights.append(fid)
                        if immediate:
                            result.immediate_flights.append(fid)
                            result.passengers_affected += flight.seats
                        else:
                            result.at_risk_flights.append(fid)

    # ---- 2. station closures -> blocked legs -> their pairings ----
    for flight in repo.flights.values():
        blocked, why = state.flight_blocked(flight)
        if not blocked:
            continue
        result.blocked_flights.append({"flight_id": flight.flight_id, "reason": why})
        node(flight.flight_id, flight.flight_no, "flight", "broken")
        pairing_id = repo.flight_to_pairing.get(flight.flight_id)
        if pairing_id:
            node(pairing_id, pairing_id, "pairing", "at_risk")
            edge(pairing_id, flight.flight_id)
            if pairing_id not in result.pairings_broken:
                result.pairings_broken.append(pairing_id)
        if flight.flight_id not in seen_flights:
            seen_flights.add(flight.flight_id)
            result.uncrewed_flights.append(flight.flight_id)
            result.passengers_affected += flight.seats

    # ---- 3. delays -> downstream legs on the same aircraft ----
    for flight_id, hours in state.delayed_flights:
        flight = repo.flights.get(flight_id)
        if not flight:
            continue
        node(flight_id, f"{flight.flight_no} +{hours:g}h", "flight", "at_risk")
        rotation = repo.aircraft_rotation.get(flight.aircraft, [])
        following = [f for f in rotation if f.dep_utc > flight.dep_utc and f.date == flight.date]
        for nxt in following:
            node(nxt.flight_id, nxt.flight_no, "flight", "at_risk")
            edge(flight_id, nxt.flight_id)
            flight = nxt   # cascade forward along the rotation

    # ---- 4. downstream crew risk: who is now at risk because of these events ----
    result.downstream_risks = _downstream_risks(repo, state, result)

    result.nodes = list(nodes.values())
    result.edges = edges
    return result


def _downstream_risks(repo, state: OperationalState, result: ImpactResult) -> list[dict]:
    """Crew whose own duty becomes illegal once the disruption's delays are applied.

    Only reports genuine rule failures -- a controller reading a risk list needs it to
    mean something.
    """
    risks: list[dict] = []
    delayed_pairings: dict[str, float] = {}
    for flight_id, hours in state.delayed_flights:
        pairing_id = repo.flight_to_pairing.get(flight_id)
        if pairing_id:
            delayed_pairings[pairing_id] = max(delayed_pairings.get(pairing_id, 0.0), hours)

    for pairing_id, hours in delayed_pairings.items():
        pairing = repo.pairings[pairing_id]
        for crew_id in pairing.crew:
            if crew_id in state.unavailable_crew:
                continue
            # the crew has already reported, so the delay lengthens the duty rather
            # than moving it -- this is what puts RULE-FDP-01 at risk
            request = CoverRequest(
                crew_id=crew_id, days=pairing.days,
                exclude_pairing=pairing_id, extend_hours=hours,
            )
            verdict = registry.evaluate(repo, request)
            for failure in verdict.failures:
                risks.append(
                    {"crew_id": crew_id, "rule": failure.rule_id, "detail": failure.detail}
                )

    # crew sharing a pairing with someone who has gone unavailable are exposed too:
    # their duty is intact but the pairing cannot operate until the gap is filled.
    for pairing_id in result.pairings_broken:
        pairing = repo.pairings.get(pairing_id)
        if not pairing:
            continue
        for crew_id in pairing.crew:
            if crew_id in state.unavailable_crew:
                continue
            risks.append(
                {
                    "crew_id": crew_id,
                    "rule": "COVERAGE",
                    "detail": (
                        f"rostered on {pairing_id} which cannot operate until the "
                        f"vacancy is filled"
                    ),
                }
            )
    return risks
