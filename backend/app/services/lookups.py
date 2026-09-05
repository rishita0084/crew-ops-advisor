"""Tier-1 retrieval tools.

Each returns a ToolResult: prose seed, an optional table for the UI, and the evidence
that backs every figure in it. No tool ever returns a value it did not read from the
operational store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.config import SNAPSHOT_UTC
from app.domain.time_utils import calendar_window, time_on_date
from app.explain.ledger import EvidenceLedger
from app.rules.r02_duty_7d import accrued_duty
from app.rules.r03_flight_28d import accrued_flight

SNAPSHOT_DATE = SNAPSHOT_UTC.date()


@dataclass
class ToolResult:
    summary: str
    data: dict = field(default_factory=dict)
    table: dict | None = None
    ledger: EvidenceLedger = field(default_factory=EvidenceLedger)
    tier: int = 1
    confidence: str = "high"

    def to_dict(self) -> dict:
        return {"summary": self.summary, "data": self.data, "table": self.table}


def _table(columns: list[str], rows: list[list]) -> dict:
    return {"columns": columns, "rows": rows}


# --------------------------------------------------------------------------- crew

def crew_profile(repo, crew_id: str) -> ToolResult:
    crew = repo.crew.get(crew_id)
    led = EvidenceLedger()
    if not crew:
        return ToolResult(
            summary=f"No crew member {crew_id} exists in the roster.",
            confidence="cannot_answer", ledger=led,
        )

    led.add("crew.json", f"{crew_id} rank", crew.rank)
    led.add("crew.json", f"{crew_id} base", crew.base)
    led.add("crew.json", f"{crew_id} ratings", ", ".join(crew.ratings))
    led.add("crew.json", f"{crew_id} reachability", f"{crew.reachability_minutes} min")
    led.add("crew.json", f"{crew_id} status", crew.status)
    led.allow(crew.name, crew.seniority)

    rows = [
        ["Name", crew.name], ["Rank", crew.rank], ["Base", crew.base],
        ["Ratings", ", ".join(crew.ratings)], ["Seniority", crew.seniority],
        ["Reachability", f"{crew.reachability_minutes} min"], ["Status", crew.status],
    ]

    reserve = repo.reserves.get(crew_id)
    if reserve:
        window = f"{reserve.window_start}-{reserve.window_end}Z"
        rows.append(["Reserve on-call", window])
        led.add("reserve_pool.json", f"{crew_id} on-call window", window)

    clock = repo.clocks.get(crew_id)
    if clock:
        rows.append(["Duty hours (7d)", clock["duty_hours_7d"]])
        rows.append(["Block hours (28d)", clock["flight_hours_28d"]])
        led.add("duty_clocks.json", f"{crew_id} duty_hours_7d", clock["duty_hours_7d"])
        led.add("duty_clocks.json", f"{crew_id} flight_hours_28d", clock["flight_hours_28d"])

    risk = repo.risk.get(crew_id)
    if risk:
        rows.append(["Disruption risk", risk.score])
        rows.append(["Risk drivers", "; ".join(risk.drivers)])
        led.add("risk_signals.json", f"{crew_id} disruption_risk_score", risk.score)
        led.allow(*risk.drivers)

    pairings = repo.crew_pairings.get(crew_id, [])
    if pairings:
        rows.append(["Rostered pairings", ", ".join(pairings)])
        led.add("rosters.json", f"{crew_id} pairings", ", ".join(pairings))

    return ToolResult(
        summary=(
            f"{crew.rank} {crew_id} ({crew.name}) is based at {crew.base}, rated "
            f"{'/'.join(crew.ratings)}, reachable in {crew.reachability_minutes} minutes."
        ),
        data={
            "crew_id": crew_id, "name": crew.name, "rank": crew.rank, "base": crew.base,
            "ratings": list(crew.ratings), "seniority": crew.seniority,
            "reachability_minutes": crew.reachability_minutes, "status": crew.status,
            "reserve_window": (
                {"start": reserve.window_start, "end": reserve.window_end}
                if reserve else None
            ),
            "duty_hours_7d": clock["duty_hours_7d"] if clock else None,
            "flight_hours_28d": clock["flight_hours_28d"] if clock else None,
            "risk_score": risk.score if risk else None,
            "pairings": pairings,
        },
        table=_table(["Field", "Value"], rows),
        ledger=led,
    )


def crew_roster_on(repo, crew_id: str, on: date) -> ToolResult:
    """What one crew member is actually flying on one date.

    "What is C-1042 flying tomorrow?" is the most ordinary question on a crew desk,
    and answering it with a profile card -- rank, base, every pairing they hold all
    week -- is not an answer. A date outside the published week gets said out loud
    rather than returned as an empty list, because silence there reads as "nothing
    rostered" when the truth is "we do not hold that week".
    """
    led = EvidenceLedger()
    crew = repo.crew.get(crew_id)
    if not crew:
        return ToolResult(
            summary=f"No crew member {crew_id} exists in the roster.",
            confidence="cannot_answer", ledger=led,
        )

    # conventions carry the week as ISO strings, derived from the flight dates
    week_start = date.fromisoformat(repo.conventions.week_start)
    week_end = date.fromisoformat(repo.conventions.week_end)
    led.add("crew.json", f"{crew_id} rank", crew.rank)
    led.allow(crew.name, crew_id, on.isoformat())

    if not (week_start <= on <= week_end):
        where = "before" if on < week_start else "after"
        return ToolResult(
            summary=(
                f"{on} is {where} the published schedule, which runs {week_start} to "
                f"{week_end}. I cannot say what {crew.rank} {crew_id} is flying that day."
            ),
            data={"crew_id": crew_id, "date": on.isoformat(), "in_schedule": False,
                  "week_start": week_start.isoformat(), "week_end": week_end.isoformat()},
            confidence="cannot_answer",
            ledger=led,
        )

    blocks = [b for b in repo.roster.get(crew_id, []) if b.date == on]
    if not blocks:
        return ToolResult(
            summary=f"{crew.rank} {crew_id} ({crew.name}) has no duty rostered on {on}.",
            data={"crew_id": crew_id, "date": on.isoformat(), "in_schedule": True,
                  "pairings": [], "flights": []},
            ledger=led,
        )

    rows: list[list] = []
    flight_nos: list[str] = []
    for block in blocks:
        pairing = repo.pairings.get(block.pairing_id)
        day = next((d for d in pairing.days if d.date == on), None) if pairing else None
        legs = [repo.flights[f] for f in day.flight_ids] if day else []
        for leg in legs:
            flight_nos.append(leg.flight_no)
            rows.append([
                leg.flight_no, f"{leg.dep_station}-{leg.arr_station}",
                f"{leg.dep_utc:%H:%M}Z", f"{leg.arr_utc:%H:%M}Z",
                leg.aircraft, block.pairing_id,
            ])
            led.allow(leg.flight_no, leg.dep_station, leg.arr_station, leg.aircraft)
        led.add("rosters.json", f"{crew_id} on {on}", block.pairing_id)
        led.add("rosters.json", f"{block.pairing_id} duty on {on}", block.duty_hours)

    pairings = sorted({b.pairing_id for b in blocks})
    report = min(b.report_utc for b in blocks)
    release = max(b.release_utc for b in blocks)
    duty = round(sum(b.duty_hours for b in blocks), 2)
    led.allow(f"{report:%H:%M}", f"{release:%H:%M}", duty)

    return ToolResult(
        summary=(
            f"{crew.rank} {crew_id} ({crew.name}) flies {', '.join(pairings)} on {on}: "
            f"{len(rows)} sector(s) {' '.join(flight_nos)}, report {report:%H:%M}Z, "
            f"release {release:%H:%M}Z, {duty}h duty."
        ),
        data={
            "crew_id": crew_id, "date": on.isoformat(), "in_schedule": True,
            "pairings": pairings, "flights": flight_nos, "duty_hours": duty,
            "report_utc": f"{report:%H:%M}", "release_utc": f"{release:%H:%M}",
        },
        table=_table(["Flight", "Route", "Dep", "Arr", "Aircraft", "Pairing"], rows),
        ledger=led,
    )


def crew_search(repo, rank: str | None = None, base: str | None = None,
                rating: str | None = None) -> ToolResult:
    led = EvidenceLedger()
    matches = [
        c for c in repo.crew.values()
        if (not rank or c.rank == rank)
        and (not base or c.base == base)
        and (not rating or rating in c.ratings)
    ]
    matches.sort(key=lambda c: c.crew_id)
    for c in matches:
        led.allow(c.crew_id, c.name, c.base, c.seniority)
    led.add("crew.json", "matching crew", len(matches))

    descriptor = " ".join(x for x in [rank, f"based at {base}" if base else None,
                                      f"rated {rating}" if rating else None] if x)
    # Agree the verb with the count. A bare "1 crew match ..." reads as a broken
    # string rather than a real answer, and a genuinely small result -- this fleet
    # has exactly one DEL-based captain -- is then mistaken for a bug.
    n = len(matches)
    noun = "crew member" if n == 1 else "crew members"
    verb = "matches" if n == 1 else "match"
    return ToolResult(
        summary=f"{n} {noun} {verb} {descriptor or 'the filter'}.",
        data={"count": len(matches), "crew_ids": [c.crew_id for c in matches]},
        table=_table(
            ["Crew", "Name", "Rank", "Base", "Ratings", "Seniority"],
            [[c.crew_id, c.name, c.rank, c.base, "/".join(c.ratings), c.seniority] for c in matches],
        ),
        ledger=led,
    )


# ----------------------------------------------------------------------- reserves

def reserves_on_date(repo, on: date, base: str | None = None,
                     rank: str | None = None, report_utc=None) -> ToolResult:
    led = EvidenceLedger()
    iso = on.isoformat()
    rows, ids = [], []
    for cid, reserve in sorted(repo.reserves.items()):
        if iso not in reserve.dates:
            continue
        if base and reserve.base != base:
            continue
        crew = repo.crew[cid]
        if rank and crew.rank != rank:
            continue
        if report_utc is not None:
            start = time_on_date(report_utc.date(), reserve.window_start)
            end = time_on_date(report_utc.date(), reserve.window_end)
            if not (start <= report_utc <= end):
                continue
        window = f"{reserve.window_start}-{reserve.window_end}Z"
        rows.append([cid, crew.name, crew.rank, reserve.base, window,
                     f"{crew.reachability_minutes} min"])
        ids.append(cid)
        led.add("reserve_pool.json", f"{cid} on-call {iso}", window)
        led.allow(crew.name, crew.rank, crew.reachability_minutes)

    where = f" at {base}" if base else ""
    who = f"{rank} " if rank else ""
    when = (f", covering a {report_utc.strftime('%H:%M')}Z callout"
            if report_utc is not None else "")
    return ToolResult(
        summary=f"{len(rows)} {who}reserve crew are on call{where} on {iso}{when}.",
        data={"date": iso, "base": base, "rank": rank, "crew_ids": ids},
        table=_table(["Crew", "Name", "Rank", "Base", "On-call window", "Reachability"], rows),
        ledger=led,
    )


# ------------------------------------------------------------------- duty clocks

def duty_clock(repo, crew_id: str, on: date | None = None) -> ToolResult:
    led = EvidenceLedger()
    crew = repo.crew.get(crew_id)
    if not crew:
        return ToolResult(summary=f"No crew member {crew_id}.", confidence="cannot_answer", ledger=led)

    on = on or SNAPSHOT_DATE
    duty_limit = float(repo.rule_param("RULE-DUTY-02", "max_duty_hours", 60))
    duty_window = int(repo.rule_param("RULE-DUTY-02", "window_days", 7))
    flight_limit = float(repo.rule_param("RULE-FLT-03", "max_flight_hours", 100))
    flight_window = int(repo.rule_param("RULE-FLT-03", "window_days", 28))

    duty = accrued_duty(repo, crew_id, on, duty_window)
    flight = accrued_flight(repo, crew_id, on, flight_window)
    duty_head = round(duty_limit - duty, 2)
    flight_head = round(flight_limit - flight, 2)

    start, stop = calendar_window(on, duty_window)
    led.add("duty_clocks.json", f"{crew_id} duty hours {start}..{stop}", duty)
    led.add("RULE-DUTY-02", "limit", duty_limit)
    led.add("RULE-DUTY-02", f"{crew_id} headroom", duty_head)
    fstart, fstop = calendar_window(on, flight_window)
    led.add("duty_clocks.json", f"{crew_id} block hours {fstart}..{fstop}", flight)
    led.add("RULE-FLT-03", "limit", flight_limit)
    led.add("RULE-FLT-03", f"{crew_id} headroom", flight_head)

    return ToolResult(
        summary=(
            f"{crew.rank} {crew_id} has {duty}h duty in the {duty_window} calendar days "
            f"ending {on} ({duty_head}h headroom under RULE-DUTY-02) and {flight}h block "
            f"in the {flight_window} days ending {on} ({flight_head}h under RULE-FLT-03)."
        ),
        data={
            "crew_id": crew_id, "duty_hours_7d": duty, "headroom_hours": duty_head,
            "flight_hours_28d": flight, "flight_headroom_hours": flight_head,
            "as_of": on.isoformat(),
        },
        table=_table(
            ["Measure", "Accrued", "Limit", "Headroom"],
            [
                [f"Duty hours / {duty_window}d", duty, duty_limit, duty_head],
                [f"Block hours / {flight_window}d", flight, flight_limit, flight_head],
            ],
        ),
        ledger=led,
    )


def crew_near_limit(repo, on: date, threshold: float) -> ToolResult:
    """Crew at or above a duty threshold in the 7 days ending `on`, planned duty included."""
    led = EvidenceLedger()
    window = int(repo.rule_param("RULE-DUTY-02", "window_days", 7))
    limit = float(repo.rule_param("RULE-DUTY-02", "max_duty_hours", 60))
    # the threshold and the limit are both stated in the answer, so both have to be
    # grounded -- otherwise the verifier correctly flags our own arithmetic
    led.add("rules.json", "RULE-DUTY-02 max duty hours", limit)
    led.add("rules.json", "RULE-DUTY-02 window days", window)
    led.add("computed", "duty threshold", threshold)
    rows = []
    for cid in sorted(repo.crew):
        total = accrued_duty(repo, cid, on, window)
        if total >= threshold:
            crew = repo.crew[cid]
            rows.append([cid, crew.rank, crew.base, total, round(limit - total, 2)])
            led.add("duty_clocks.json", f"{cid} duty hours to {on}", total)
            led.allow(cid, crew.rank, crew.base)
    return ToolResult(
        summary=(
            f"{len(rows)} crew have {threshold}h or more duty in the {window} calendar "
            f"days ending {on}."
        ),
        data={"threshold": threshold, "date": on.isoformat(),
              "crew_ids": [r[0] for r in rows]},
        table=_table(["Crew", "Rank", "Base", "Duty hours", "Headroom"], rows),
        ledger=led,
    )


# ---------------------------------------------------------------------- flights

def flights_query(repo, on: date | None = None, dep: str | None = None,
                  arr: str | None = None, flight_no: str | None = None,
                  tail: str | None = None) -> ToolResult:
    led = EvidenceLedger()
    pool = repo.flights_by_date[on.isoformat()] if on else list(repo.flights.values())
    matches = [
        f for f in pool
        if (not dep or f.dep_station == dep)
        and (not arr or f.arr_station == arr)
        and (not flight_no or f.flight_no == flight_no)
        and (not tail or f.aircraft == tail)
    ]
    matches.sort(key=lambda f: f.dep_utc)

    rows = []
    for f in matches:
        rows.append([
            f.flight_no, f.date, f.dep_station, f.arr_station,
            f.dep_utc.strftime("%H:%M") + "Z", f.arr_utc.strftime("%H:%M") + "Z",
            f.block_hours, f.aircraft, f.aircraft_type, f.seats,
        ])
        led.allow(f.flight_no, f.flight_id, f.aircraft, f.aircraft_type,
                  f.seats, f.block_hours, f.dep_station, f.arr_station)
    led.add("flights.json", "matching legs", len(matches))

    parts = [p for p in [
        f"departing {dep}" if dep else None,
        f"arriving {arr}" if arr else None,
        f"on {on}" if on else None,
        f"numbered {flight_no}" if flight_no else None,
        f"operated by {tail}" if tail else None,
    ] if p]
    return ToolResult(
        summary=f"{len(matches)} flights {' '.join(parts)}." if parts
                else f"{len(matches)} flights in the schedule.",
        data={"count": len(matches), "flight_ids": [f.flight_id for f in matches],
              "flight_nos": sorted({f.flight_no for f in matches})},
        table=_table(
            ["Flight", "Date", "From", "To", "Dep", "Arr", "Block", "Tail", "Type", "Seats"],
            rows,
        ),
        ledger=led,
    )


def network_map(repo, station: str) -> ToolResult:
    led = EvidenceLedger()
    destinations = sorted({f.arr_station for f in repo.flights.values() if f.dep_station == station})
    origins = sorted({f.dep_station for f in repo.flights.values() if f.arr_station == station})
    led.add("flights.json", f"nonstop destinations from {station}", ", ".join(destinations))
    return ToolResult(
        summary=(
            f"{station} serves {len(destinations)} nonstop destinations: "
            f"{', '.join(destinations)}."
        ),
        data={"station": station, "destinations": destinations, "origins": origins},
        table=_table(["Direction", "Stations"],
                     [["Nonstop from " + station, ", ".join(destinations)],
                      ["Nonstop to " + station, ", ".join(origins)]]),
        ledger=led,
    )


def longest_block(repo) -> ToolResult:
    led = EvidenceLedger()
    longest = max(f.block_hours for f in repo.flights.values())
    matches = sorted(
        {f.flight_no for f in repo.flights.values() if f.block_hours == longest}
    )
    led.add("flights.json", "longest block time", longest)
    led.add("flights.json", "flights at that block time", ", ".join(matches))
    sample = next(f for f in repo.flights.values() if f.block_hours == longest)
    led.allow(sample.dep_station, sample.arr_station)
    return ToolResult(
        summary=(
            f"The longest block time in the schedule is {longest}h, flown by "
            f"{', '.join(matches)} ({sample.dep_station}-{sample.arr_station})."
        ),
        data={"block_hours": longest, "flight_nos": matches},
        table=_table(["Flight", "Block hours"], [[n, longest] for n in matches]),
        ledger=led,
    )


def biggest_seat_exposure(repo, on: date | None = None) -> ToolResult:
    led = EvidenceLedger()
    pool = repo.flights_by_date[on.isoformat()] if on else list(repo.flights.values())
    top = max(pool, key=lambda f: f.seats)
    peers = sorted({f.flight_no for f in pool if f.seats == top.seats})
    led.add("flights.json", "highest seat count on a single leg", top.seats)
    led.add("flights.json", "legs at that seat count", ", ".join(peers))
    led.allow(top.aircraft_type, top.flight_no)
    return ToolResult(
        summary=(
            f"The largest single-leg exposure is {top.seats} seats, flown by the "
            f"{top.aircraft_type} on {', '.join(peers[:6])}"
            + (f" and {len(peers) - 6} others." if len(peers) > 6 else ".")
        ),
        data={"seats": top.seats, "flight_nos": peers},
        table=_table(["Flight", "Type", "Seats"], [[n, top.aircraft_type, top.seats] for n in peers[:20]]),
        ledger=led,
    )


# ----------------------------------------------------------------- certifications

def expiring_certifications(repo, as_of: date, within_days: int = 30) -> ToolResult:
    led = EvidenceLedger()
    horizon = as_of + timedelta(days=within_days)
    rows = []
    for cid in sorted(repo.certifications):
        for cert in sorted(repo.certifications[cid], key=lambda c: c.valid_to):
            if as_of <= cert.valid_to <= horizon:
                crew = repo.crew[cid]
                days_left = (cert.valid_to - as_of).days
                rows.append([cid, crew.rank, crew.base, cert.cert_type,
                             cert.valid_to.isoformat(), days_left])
                led.add("certifications.json", f"{cid} {cert.cert_type} expires", cert.valid_to)
                led.allow(days_left, crew.rank, crew.base)
    rows.sort(key=lambda r: (r[4], r[0]))
    return ToolResult(
        summary=(
            f"{len(rows)} certifications expire within {within_days} days of {as_of} "
            f"(through {horizon})."
        ),
        data={"as_of": as_of.isoformat(), "within_days": within_days,
              "count": len(rows), "crew_ids": sorted({r[0] for r in rows})},
        table=_table(["Crew", "Rank", "Base", "Certification", "Expires", "Days left"], rows),
        ledger=led,
    )


# ---------------------------------------------------------------------- pairings

def pairing_detail(repo, pairing_id: str) -> ToolResult:
    led = EvidenceLedger()
    pairing = repo.pairings.get(pairing_id)
    if not pairing:
        return ToolResult(summary=f"No pairing {pairing_id}.", confidence="cannot_answer", ledger=led)

    rows = []
    for cid, role in pairing.crew.items():
        crew = repo.crew[cid]
        rows.append([cid, crew.name, role, crew.base, "/".join(crew.ratings)])
        led.add("rosters.json", f"{pairing_id} {role}", cid)
        led.allow(crew.name, crew.base)

    leg_rows = []
    for day in pairing.days:
        for fid in day.flight_ids:
            f = repo.flights[fid]
            leg_rows.append([day.date.isoformat(), f.flight_no, f.dep_station, f.arr_station,
                             f.dep_utc.strftime("%H:%M") + "Z", f.block_hours])
            led.allow(f.flight_no, fid, f.block_hours)
        led.add("rosters.json", f"{pairing_id} day {day.date} duty",
                f"{day.report_utc.strftime('%H:%M')}Z-{day.release_utc.strftime('%H:%M')}Z "
                f"({day.duty_hours}h)")

    return ToolResult(
        summary=(
            f"{pairing_id} is a {len(pairing.days)}-day pairing on {pairing.aircraft} with "
            f"{len(pairing.all_flight_ids)} legs and {len(pairing.crew)} crew."
        ),
        data={"pairing_id": pairing_id,
              "crew": pairing.crew,
              "flight_ids": pairing.all_flight_ids,
              "dates": [d.date.isoformat() for d in pairing.days]},
        table=_table(["Crew", "Name", "Role", "Base", "Ratings"], rows),
        ledger=led,
    )


def pairing_for_tail(repo, tail: str, on: date) -> ToolResult:
    led = EvidenceLedger()
    for pairing in sorted(repo.pairings.values(), key=lambda p: p.pairing_id):
        if pairing.aircraft != tail:
            continue
        if any(d.date == on for d in pairing.days):
            led.add("rosters.json", f"{tail} pairing on {on}", pairing.pairing_id)
            result = pairing_detail(repo, pairing.pairing_id)
            for item in result.ledger.items:
                led.items.append(item)
            led.allow(*result.ledger.tokens)
            result.ledger = led
            result.summary = (
                f"{tail} operates {pairing.pairing_id} on {on}. " + result.summary
            )
            return result
    return ToolResult(
        summary=f"No pairing found for {tail} on {on}.",
        confidence="cannot_answer", ledger=led,
    )


# ------------------------------------------------------------------------- misc

def rest_calculator(repo, release_time: str, on: date) -> ToolResult:
    led = EvidenceLedger()
    minimum = float(repo.rule_param("RULE-REST-04", "min_rest_hours", 12))
    release = time_on_date(on, release_time)
    earliest = release + timedelta(hours=minimum)
    led.add("RULE-REST-04", "minimum rest", f"{minimum:g}h")
    led.add("computed", "release", release.strftime("%Y-%m-%dT%H:%MZ"))
    led.add("computed", "earliest next report", earliest.strftime("%Y-%m-%dT%H:%MZ"))
    return ToolResult(
        summary=(
            f"Released {release.strftime('%H:%M')}Z on {on}, the earliest next report is "
            f"{earliest.strftime('%H:%M')}Z on {earliest.date()} "
            f"(RULE-REST-04 requires {minimum:g}h)."
        ),
        data={"release_utc": release.isoformat(), "earliest_report_utc": earliest.isoformat(),
              "min_rest_hours": minimum},
        table=_table(["Field", "Value"],
                     [["Release", release.strftime("%Y-%m-%d %H:%M") + "Z"],
                      ["Minimum rest", f"{minimum:g}h"],
                      ["Earliest report", earliest.strftime("%Y-%m-%d %H:%M") + "Z"]]),
        ledger=led,
    )


def risk_profile(repo, crew_id: str) -> ToolResult:
    led = EvidenceLedger()
    risk = repo.risk.get(crew_id)
    if not risk:
        return ToolResult(summary=f"No risk signal for {crew_id}.",
                          confidence="cannot_answer", ledger=led)
    led.add("risk_signals.json", f"{crew_id} disruption_risk_score", risk.score)
    for driver in risk.drivers:
        led.add("risk_signals.json", f"{crew_id} driver", driver)
    return ToolResult(
        summary=(
            f"{crew_id} carries a disruption-risk score of {risk.score}, driven by: "
            f"{'; '.join(risk.drivers)}. This is a provided signal, not a prediction "
            f"this system makes."
        ),
        data={"crew_id": crew_id, "score": risk.score, "drivers": list(risk.drivers)},
        table=_table(["Field", "Value"],
                     [["Risk score", risk.score]] + [["Driver", d] for d in risk.drivers]),
        ledger=led,
    )
