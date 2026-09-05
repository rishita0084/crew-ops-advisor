"""Reads SQLite once into an immutable in-memory picture.

The dataset is ~150 crew / 147 flights, so loading it whole is both correct and the
fastest option. Every consumer goes through this class, so replacing SQLite with
Postgres means rewriting only this file.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from functools import lru_cache

from app.db.connection import connect
from app.domain.models import (
    Certification,
    Crew,
    DutyBlock,
    Flight,
    Pairing,
    PairingDay,
    Reserve,
    RiskSignal,
)
from app.domain.time_utils import parse_date, parse_utc


class Repository:
    def __init__(self, conn=None) -> None:
        self.conn = conn or connect()
        self._load()

    # ---------- loading ----------
    def _load(self) -> None:
        c = self.conn

        ratings: dict[str, list[str]] = defaultdict(list)
        for row in c.execute("SELECT crew_id, aircraft_type FROM crew_ratings"):
            ratings[row["crew_id"]].append(row["aircraft_type"])

        self.crew: dict[str, Crew] = {
            r["crew_id"]: Crew(
                crew_id=r["crew_id"], name=r["name"], rank=r["rank"], base=r["base"],
                ratings=tuple(sorted(ratings[r["crew_id"]])), seniority=r["seniority"],
                reachability_minutes=r["reachability_minutes"], status=r["status"],
            )
            for r in c.execute("SELECT * FROM crew")
        }

        self.flights: dict[str, Flight] = {
            r["flight_id"]: Flight(
                flight_id=r["flight_id"], flight_no=r["flight_no"], date=r["date"],
                dep_station=r["dep_station"], arr_station=r["arr_station"],
                dep_utc=parse_utc(r["dep_utc"]), arr_utc=parse_utc(r["arr_utc"]),
                block_hours=r["block_hours"], aircraft=r["aircraft"],
                aircraft_type=r["aircraft_type"], seats=r["seats"],
            )
            for r in c.execute("SELECT * FROM flights")
        }

        day_flights: dict[tuple[str, int], list[str]] = defaultdict(list)
        for r in c.execute("SELECT * FROM pairing_day_flights ORDER BY leg_index"):
            day_flights[(r["pairing_id"], r["day_index"])].append(r["flight_id"])

        self.pairings: dict[str, Pairing] = {
            r["pairing_id"]: Pairing(pairing_id=r["pairing_id"], aircraft=r["aircraft"])
            for r in c.execute("SELECT * FROM pairings")
        }
        for r in c.execute("SELECT * FROM pairing_days ORDER BY pairing_id, day_index"):
            key = (r["pairing_id"], r["day_index"])
            self.pairings[r["pairing_id"]].days.append(
                PairingDay(
                    pairing_id=r["pairing_id"], day_index=r["day_index"],
                    date=parse_date(r["date"]), report_utc=parse_utc(r["report_utc"]),
                    release_utc=parse_utc(r["release_utc"]),
                    flight_ids=tuple(day_flights[key]),
                )
            )
        for r in c.execute("SELECT * FROM pairing_crew"):
            self.pairings[r["pairing_id"]].crew[r["crew_id"]] = r["role"]

        self.reserves: dict[str, Reserve] = {}
        res_dates: dict[str, set[str]] = defaultdict(set)
        for r in c.execute("SELECT * FROM reserve_dates"):
            res_dates[r["crew_id"]].add(r["date"])
        for r in c.execute("SELECT * FROM reserve_pool"):
            self.reserves[r["crew_id"]] = Reserve(
                crew_id=r["crew_id"], base=r["base"], window_start=r["window_start"],
                window_end=r["window_end"], dates=frozenset(res_dates[r["crew_id"]]),
            )

        self.certifications: dict[str, list[Certification]] = defaultdict(list)
        for r in c.execute("SELECT * FROM certifications"):
            self.certifications[r["crew_id"]].append(
                Certification(
                    r["crew_id"], r["cert_type"],
                    parse_date(r["valid_from"]), parse_date(r["valid_to"]),
                )
            )

        self.duty_history: dict[str, dict[date, tuple[float, float]]] = defaultdict(dict)
        for r in c.execute("SELECT * FROM duty_history"):
            self.duty_history[r["crew_id"]][parse_date(r["date"])] = (
                r["duty_hours"], r["flight_hours"],
            )

        self.clocks: dict[str, dict] = {
            r["crew_id"]: dict(r) for r in c.execute("SELECT * FROM duty_clocks")
        }

        self.rules: dict[str, dict] = {
            r["rule_id"]: {
                "rule_id": r["rule_id"], "text": r["text"], "params": json.loads(r["params"]),
            }
            for r in c.execute("SELECT * FROM rules")
        }

        self.costs: dict[str, object] = {
            r["key"]: json.loads(r["value"]) for r in c.execute("SELECT * FROM costs")
        }

        self.risk: dict[str, RiskSignal] = {
            r["crew_id"]: RiskSignal(
                r["crew_id"], r["disruption_risk_score"], tuple(json.loads(r["drivers"])),
            )
            for r in c.execute("SELECT * FROM risk_signals")
        }

        self.flagged: list[dict] = [
            dict(r) for r in c.execute("SELECT * FROM flagged_exceptions")
        ]

        self._build_indexes()

    def _build_indexes(self) -> None:
        self.roster: dict[str, list[DutyBlock]] = defaultdict(list)
        self.flight_to_pairing: dict[str, str] = {}
        self.crew_pairings: dict[str, list[str]] = defaultdict(list)

        for p in self.pairings.values():
            for d in p.days:
                for fid in d.flight_ids:
                    self.flight_to_pairing[fid] = p.pairing_id
                day_block = round(sum(self.flights[f].block_hours for f in d.flight_ids), 2)
                for cid in p.crew:
                    self.roster[cid].append(
                        DutyBlock(
                            date=d.date, report_utc=d.report_utc, release_utc=d.release_utc,
                            duty_hours=d.duty_hours, flight_hours=day_block,
                            pairing_id=p.pairing_id,
                        )
                    )
            for cid in p.crew:
                self.crew_pairings[cid].append(p.pairing_id)

        for blocks in self.roster.values():
            blocks.sort(key=lambda b: b.report_utc)

        self.flights_by_date: dict[str, list[Flight]] = defaultdict(list)
        for f in self.flights.values():
            self.flights_by_date[f.date].append(f)
        for lst in self.flights_by_date.values():
            lst.sort(key=lambda f: f.dep_utc)

        self.aircraft_rotation: dict[str, list[Flight]] = defaultdict(list)
        for f in self.flights.values():
            self.aircraft_rotation[f.aircraft].append(f)
        for lst in self.aircraft_rotation.values():
            lst.sort(key=lambda f: f.dep_utc)

    # ---------- accessors ----------
    def pairing_day(self, pairing_id: str, day_index: int) -> PairingDay:
        return self.pairings[pairing_id].days[day_index]

    def day_aircraft_type(self, day: PairingDay) -> str:
        return self.flights[day.flight_ids[0]].aircraft_type

    def day_flight_hours(self, day: PairingDay) -> float:
        return round(sum(self.flights[f].block_hours for f in day.flight_ids), 2)

    def day_passengers(self, day: PairingDay) -> int:
        return sum(self.flights[f].seats for f in day.flight_ids)

    def is_reserve(self, crew_id: str) -> bool:
        return crew_id in self.reserves

    def cost(self, key: str) -> float:
        return float(self.costs[key])

    def rule_param(self, rule_id: str, key: str, default=None):
        return self.rules[rule_id]["params"].get(key, default)

    def pairings_on_date(self, day: date) -> list[tuple[str, int]]:
        return [
            (p.pairing_id, d.day_index)
            for p in self.pairings.values() for d in p.days if d.date == day
        ]

    def crew_by_rank(self, rank: str, active_only: bool = True) -> list[Crew]:
        return [
            c for c in self.crew.values()
            if c.rank == rank and (not active_only or c.status == "active")
        ]


@lru_cache(maxsize=1)
def get_repository() -> Repository:
    """Process-wide singleton. The dataset is static, so one load serves every request."""
    return Repository()
