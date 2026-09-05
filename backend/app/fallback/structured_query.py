"""Deterministic intent router.

Two jobs. It is the fallback when the LLM is disabled or unreachable, so the advisor
degrades to "terse but correct" instead of going dark. It is also the reference
implementation of what each intent means, which keeps the LLM path honest.

Ordered most-specific first. When nothing matches confidently it says so rather than
guessing -- an unrecognised question is a better outcome than a confident wrong tool.
"""
from __future__ import annotations

import re
from datetime import timedelta

from app.config import SNAPSHOT_UTC
from app.engine.state import BASE_STATE
from app.services import actions as A
from app.services import lookups as L
from app.services.entities import Entities, extract
from app.services.lookups import ToolResult

SNAPSHOT_DATE = SNAPSHOT_UTC.date()


def _stations(repo) -> set[str]:
    stations = {f.dep_station for f in repo.flights.values()}
    stations |= {f.arr_station for f in repo.flights.values()}
    return stations


def _role_for(repo, crew_id: str | None, ent: Entities) -> str:
    if crew_id and crew_id in repo.crew:
        return repo.crew[crew_id].rank
    return ent.rank or "Captain"


def _pairing_for_tail(repo, tail: str, on) -> str | None:
    for pairing in sorted(repo.pairings.values(), key=lambda p: p.pairing_id):
        if pairing.aircraft == tail and any(d.date == on for d in pairing.days):
            return pairing.pairing_id
    return None


def _crew_in_role(repo, pairing_id: str, role: str) -> str | None:
    for cid, r in repo.pairings[pairing_id].crew.items():
        if r == role:
            return cid
    return None


def _joint_recovery(repo, targets: list[tuple[str, str, str | None]], on) -> ToolResult:
    """Several vacancies at the same moment, solved as one problem.

    Ranking each pairing separately would hand the same cheapest reserve to both.
    """
    from app.engine import joint as joint_mod
    from app.explain.ledger import EvidenceLedger
    from app.rules.registry import ALL_RULES, summarise

    vacancies = [joint_mod.Vacancy(pid, role, out) for pid, role, out in targets]
    plan = joint_mod.solve(repo, vacancies)

    led = EvidenceLedger()
    led.allow(*ALL_RULES)
    options: list[dict] = []
    parts: list[str] = []

    for rank, (vac, cand) in enumerate(plan.assignments, start=1):
        pairing = repo.pairings[vac.pairing_id]
        flight_ids = pairing.all_flight_ids
        led.add("computed", f"joint assignment {vac.pairing_id}", cand.action)
        led.add("costs.json", f"{vac.pairing_id} cost", cand.cost_inr)
        led.allow(cand.crew_id, vac.crew_out, vac.pairing_id, *flight_ids)
        parts.append(f"{vac.pairing_id}: {cand.action} at INR {cand.cost_inr:,}")
        options.append({
            "rank": rank,
            "action": f"[{vac.pairing_id}] {cand.action}",
            "legal": True,
            "rules_checked": ALL_RULES,
            "rule_checks": summarise(cand.verdict),
            "cost_inr": cand.cost_inr,
            "cost_breakdown": cand.cost.to_list(),
            "coverage": f"all {len(flight_ids)} flights",
            "covered_flight_ids": flight_ids,
            "uncovered_flight_ids": [],
            "delay_minutes": int(round(cand.delay_hours * 60)),
            "resilience_score": 1.0,
            "resilience_note": "part of a joint plan; no crew member is assigned twice",
            "chain": [],
            "reasoning": (
                f"Chosen as part of the cheapest combination covering all "
                f"{len(plan.assignments)} vacancies with distinct crew."
            ),
        })

    for vac in plan.infeasible:
        parts.append(f"{vac.pairing_id}: no legal cover found")

    led.add("computed", "joint plan total", plan.total_cost_inr)
    return ToolResult(
        summary=(
            f"Optimal joint plan across {len(targets)} simultaneous vacancies on {on} "
            f"(no crew member assigned twice): " + "; ".join(parts)
            + f". Total INR {plan.total_cost_inr:,}."
        ),
        data={
            "options": options,
            "joint_cost_inr": plan.total_cost_inr,
            "joint_plan": [
                {"pairing_id": v.pairing_id, "role": v.role, "crew_id": c.crew_id,
                 "action": c.action, "cost_inr": c.cost_inr}
                for v, c in plan.assignments
            ],
        },
        ledger=led,
        tier=3,
    )


def _merge_plans(results: list[ToolResult], on) -> ToolResult:
    """Several simultaneous vacancies -- one joint plan, options renumbered end to end."""
    from app.explain.ledger import EvidenceLedger

    led = EvidenceLedger()
    options: list[dict] = []
    parts: list[str] = []
    for result in results:
        for item in result.ledger.items:
            led.items.append(item)
        led.allow(*result.ledger.tokens)
        pairing_id = result.data.get("pairing_id", "?")
        for option in result.data.get("options", []):
            option = dict(option)
            option["action"] = f"[{pairing_id}] {option['action']}"
            options.append(option)
        top = (result.data.get("options") or [{}])[0]
        if top:
            parts.append(f"{pairing_id}: {top['action']} at INR {top['cost_inr']:,}")

    options.sort(key=lambda o: (o["action"].split("]")[0], o["cost_inr"]))
    for i, option in enumerate(options, start=1):
        option["rank"] = i

    total = sum(
        (result.data.get("options") or [{"cost_inr": 0}])[0]["cost_inr"] for result in results
    )
    led.add("computed", "joint plan cost", total)
    return ToolResult(
        summary=(
            f"Joint plan across {len(results)} simultaneous vacancies on {on}: "
            + "; ".join(parts)
            + f". Combined cost INR {total:,}."
        ),
        data={"options": options, "joint_cost_inr": total},
        ledger=led,
        tier=3,
    )


def _pairing_for_crew(repo, crew_id: str, ent: Entities) -> str | None:
    pairings = repo.crew_pairings.get(crew_id, [])
    if not pairings:
        return None
    if ent.date:
        for pid in pairings:
            if any(d.date == ent.date for d in repo.pairings[pid].days):
                return pid
    return pairings[0]


def route(repo, question: str) -> ToolResult:
    """Map a controller's question to exactly one tool call."""
    text = question.strip()
    low = text.lower()
    ent = extract(text, _stations(repo))
    on = ent.date or SNAPSHOT_DATE

    # ---------- Tier 3: recovery and recommendation ----------
    if re.search(r"\b(draft|write|compose)\b.*\b(notification|message|callout|sms)\b", low):
        if ent.crew_id and ent.pairing_id:
            return A.draft_notification(repo, ent.crew_id, ent.pairing_id)
        if ent.crew_id:
            pid = _pairing_for_crew(repo, ent.crew_id, ent)
            if pid:
                return A.draft_notification(repo, ent.crew_id, pid)

    asks_impact = bool(
        re.search(
            r"(which flights|what flights|uncrewed|uncovered|now at risk|"
            r"immediately|which legs|crew impact|what breaks|affected)",
            low,
        )
    )
    wants_options = bool(
        re.search(
            r"\b(what should|what do i do|what to do|how (?:do|should) (?:i|we)|"
            r"options|recommend|resolve|recovery|cheapest|handle|deal with|"
            r"best (?:option|plan)|resolution|crewing plan|outline the)\b",
            low,
        )
    )
    is_disruption = bool(
        re.search(r"\b(sick|calls? in sick|called in sick|unavailable|out for|is out)\b", low)
    )

    if (wants_options and not asks_impact) or (is_disruption and ent.crew_id and not asks_impact):
        crew_out = ent.crew_id
        pairing_id = ent.pairing_id or (crew_out and _pairing_for_crew(repo, crew_out, ent))

        # "the VT-DXF First Officer on 20 Sep" -- identify the person from tail + date + rank
        if not pairing_id and ent.tails and ent.rank:
            targets = []
            for tail in ent.tails:
                pid = _pairing_for_tail(repo, tail, on)
                if pid:
                    targets.append((pid, ent.rank, _crew_in_role(repo, pid, ent.rank)))
            if len(targets) == 1:
                pid, role, occupant = targets[0]
                return A.recommend_cover(repo, pid, role, crew_out=occupant)
            if targets:
                # several vacancies at once: solve them jointly, or the same reserve
                # gets promised to two aircraft
                return _joint_recovery(repo, targets, on)

        if pairing_id:
            role = _role_for(repo, crew_out, ent)
            # "C-1042 is sick and C-3310, C-1526 are already committed" -- the first id
            # is the vacancy, the rest are crew the controller has already spent
            committed = {c for c in ent.crew_ids[1:]} if len(ent.crew_ids) > 1 else set()
            return A.recommend_cover(
                repo, pairing_id, role, crew_out=crew_out, also_unavailable=committed
            )
        if crew_out:
            state = BASE_STATE.with_crew_unavailable(crew_out, "sick")
            return A.recover_from_state(repo, state)

    if re.search(
        r"\b(briefing|brief me|anything (?:risky|i should)|what should i watch|"
        r"alerts?|worry|heads up|proactive|watch ?list)\b", low
    ):
        from app.alerts.sentinel import build_alerts

        return build_alerts(repo, ent.date)

    # ---------- Tier 2: consequence and simulation ----------
    if re.search(r"\b(clos(?:e|es|ed|ing|ure)|shut(?:down|s)?)\b", low) and ent.station and ent.time_range:
        start, end = ent.time_range
        from app.domain.time_utils import time_on_date

        state = BASE_STATE.with_station_closure(
            ent.station, time_on_date(on, start), time_on_date(on, end)
        )
        # the closure view supersedes the generic impact view even for a plain
        # "what is affected?" -- a closure delays flights, it does not uncrew them
        closure_result = A.recover_closure(repo, state)
        if closure_result is not None:
            return closure_result
        return A.analyse_impact(repo, state, None)

    if re.search(r"\b(delay(?:ed)?|late)\b", low) and (ent.minutes or ent.hours):
        hours = ent.hours if ent.hours else (ent.minutes or 0) / 60.0
        target = None
        if ent.flight_ids:
            target = ent.flight_ids[0]
        elif ent.flight_nos:
            target = next(
                (f.flight_id for f in repo.flights_by_date[on.isoformat()]
                 if f.flight_no == ent.flight_nos[0]), None,
            )
        elif ent.tails:
            legs = [f for f in repo.flights_by_date[on.isoformat()] if f.aircraft == ent.tails[0]]
            target = legs[0].flight_id if legs else None
        if target:
            state = BASE_STATE.with_flight_delay(target, round(hours, 2))
            if ent.tails:
                # an aircraft-level delay shifts every leg that tail flies that day
                for leg in repo.flights_by_date[on.isoformat()]:
                    if leg.aircraft == ent.tails[0] and leg.flight_id != target:
                        state = state.with_flight_delay(leg.flight_id, round(hours, 2))
            if wants_options:
                return A.recover_from_state(repo, state)
            return A.analyse_impact(repo, state, None)

    if re.search(r"\b(cancel(?:led|ling)?)\b", low) and (ent.flight_nos or ent.flight_ids):
        ids = list(ent.flight_ids)
        for no in ent.flight_nos:
            ids += [f.flight_id for f in repo.flights_by_date[on.isoformat()] if f.flight_no == no]
        if ids:
            return A.cancellation_impact(repo, ids)

    if re.search(r"\b(legal|legally|breach|can .* cover|may .* operate|does .* breach|"
                 r"if i (?:move|assign|put))\b", low) and ent.crew_id:
        pairing_id = ent.pairing_id
        if not pairing_id and ent.flight_nos:
            target = next(
                (f.flight_id for f in repo.flights_by_date[on.isoformat()]
                 if f.flight_no == ent.flight_nos[0]), None,
            )
            pairing_id = repo.flight_to_pairing.get(target) if target else None
        if not pairing_id:
            pairing_id = _pairing_for_crew(repo, ent.crew_id, ent)
        if pairing_id:
            return A.assess_assignment(repo, ent.crew_id, pairing_id)

    if is_disruption and ent.crew_id:
        state = BASE_STATE.with_crew_unavailable(ent.crew_id, "sick")
        return A.analyse_impact(repo, state, ent.date)

    if re.search(r"\b(uncrewed|uncovered|affected|impact|which flights are now)\b", low) and ent.crew_id:
        state = BASE_STATE.with_crew_unavailable(ent.crew_id, "unavailable")
        return A.analyse_impact(repo, state, ent.date)

    if re.search(r"\b(earliest|next report|report next|rest)\b", low) and re.search(r"\d{1,2}:\d{2}", text):
        clock = re.search(r"(\d{1,2}:\d{2})", text).group(1)
        return L.rest_calculator(repo, clock, on)

    if re.search(r"\b(45|50|55|\d{2})\s*(?:or more|\+)?\s*duty hours\b", low) or re.search(
        r"\bduty hours\b.*\b(or more|at least|above|over)\b", low
    ):
        m = re.search(r"\b(\d{2}(?:\.\d)?)\s*(?:or more|\+|hours)", low)
        if m:
            return L.crew_near_limit(repo, on, float(m.group(1)))

    # "which reserves could actually take this callout" is a legality question, not a
    # roster lookup -- the on-call list alone would be a wrong answer
    if "reserve" in low and re.search(r"\b(cover|callout|eligible|take the|able to)\b", low):
        pairing_id = ent.pairing_id
        crew_out = ent.crew_id
        if not pairing_id and ent.tails:
            pairing_id = _pairing_for_tail(repo, ent.tails[0], on)
        if not pairing_id and crew_out:
            pairing_id = _pairing_for_crew(repo, crew_out, ent)
        if pairing_id:
            role = ent.rank or _role_for(repo, crew_out, ent)
            if not crew_out:
                crew_out = _crew_in_role(repo, pairing_id, role)
            return A.eligible_reserves(repo, pairing_id, role, crew_out)

    # ---------- Tier 1: retrieval ----------
    if "reserve" in low and re.search(r"\b(who|which|list|on reserve|on call|standby)\b", low):
        # "which reserve captains' windows cover the callout" -- narrow by rank and,
        # when a callout time is quoted, by whether the window actually covers it
        report = None
        clock = re.search(r"\b(\d{1,2}:\d{2})\s*Z\b", text, re.I)
        if clock and re.search(r"\b(callout|called|cover|window)\b", low):
            from app.domain.time_utils import time_on_date

            report = time_on_date(on, clock.group(1))
        return L.reserves_on_date(repo, on, ent.station, rank=ent.rank, report_utc=report)

    if re.search(r"\b(certification|licence|license|medical|training|expir)\w*\b", low):
        window = ent.days or 30
        return L.expiring_certifications(repo, on, window)

    if ent.pairing_id and re.search(r"\b(who|crew|assigned|roles?)\b", low):
        return L.pairing_detail(repo, ent.pairing_id)

    if ent.tails and re.search(r"\b(who|crew|senior cabin|captain|first officer|pairing)\b", low):
        return L.pairing_for_tail(repo, ent.tails[0], on)

    if re.search(r"\b(risk|disruption[- ]risk|drives?|driver)\b", low) and ent.crew_id:
        return L.risk_profile(repo, ent.crew_id)

    if re.search(r"\b(duty hours|flight hours|block hours|headroom|accrued|clock)\b", low) and ent.crew_id:
        return L.duty_clock(repo, ent.crew_id, on)

    if re.search(r"\b(longest|shortest)\b.*\bblock\b", low):
        return L.longest_block(repo)

    if re.search(r"\b(most seats|seats at risk|largest.*(?:seat|exposure))\b", low):
        return L.biggest_seat_exposure(repo, ent.date)

    if re.search(r"\b(nonstop|non-stop|destinations|serve[sd]?|network)\b", low) and ent.station:
        return L.network_map(repo, ent.station)

    if ent.crew_id and re.search(
        r"\b(base|rating|rated|reachab|on-call window|window|rank|who is|profile|seniority)\b", low
    ):
        return L.crew_profile(repo, ent.crew_id)

    if re.search(r"\b(how many|which|list|show)\b", low) and (
        ent.rank or (ent.station and "based" in low)
    ):
        base = ent.station if "based" in low or "base" in low else None
        return L.crew_search(repo, rank=ent.rank, base=base)

    if re.search(r"\b(flight|depart|arriv|operate|schedule|leg)\w*\b", low):
        dep = arr = None
        if len(ent.stations) >= 2:
            dep, arr = ent.stations[0], ent.stations[1]
            m = re.search(r"\b([A-Z]{3})\s*(?:->|-|to|→)\s*([A-Z]{3})\b", text.upper())
            if m:
                dep, arr = m.group(1), m.group(2)
        elif ent.station:
            if re.search(r"\b(depart|from|out of)\b", low):
                dep = ent.station
            elif re.search(r"\b(arriv|into|to)\b", low):
                arr = ent.station
            else:
                dep = ent.station
        return L.flights_query(
            repo, ent.date, dep=dep, arr=arr,
            flight_no=ent.flight_nos[0] if ent.flight_nos else None,
            tail=ent.tails[0] if ent.tails else None,
        )

    if ent.crew_id:
        return L.crew_profile(repo, ent.crew_id)

    if ent.pairing_id:
        return L.pairing_detail(repo, ent.pairing_id)

    return ToolResult(
        summary=(
            "I could not map that to an operation I can answer reliably from this "
            "dataset. Try naming a crew id (C-1042), a pairing (P-2291), a flight "
            "(DX412) or a station and date."
        ),
        confidence="cannot_answer",
    )
