"""Tier-2 and Tier-3 tools: consequence analysis, simulation and ranked recovery.

Nothing here mutates the operation. Every scenario branches a copy-on-write state, so a
what-if is arithmetic on a hypothetical, never a change to the roster.
"""
from __future__ import annotations

from datetime import date

from app.engine import impact as impact_mod
from app.engine import ranking as ranking_mod
from app.engine.candidates import build_candidate
from app.engine.state import BASE_STATE, OperationalState
from app.explain.ledger import EvidenceLedger
from app.rules.registry import ALL_RULES, summarise
from app.services.lookups import ToolResult, _table


def _ledger_for_impact(repo, result: impact_mod.ImpactResult) -> EvidenceLedger:
    led = EvidenceLedger()
    led.add("computed", "trigger", result.trigger)
    for pid in result.pairings_broken:
        led.add("rosters.json", "pairing affected", pid)
    for fid in result.uncrewed_flights:
        flight = repo.flights[fid]
        led.add("flights.json", "uncovered leg", f"{flight.flight_no} on {flight.date}")
        led.allow(fid, flight.flight_no, flight.seats)
    led.add("flights.json", "passengers affected", result.passengers_affected)
    for risk in result.downstream_risks:
        led.add("computed", f"downstream risk {risk['crew_id']}", risk["detail"])
        led.allow(risk["crew_id"], risk["rule"])
    return led


# ------------------------------------------------------------------ Tier 2

def analyse_impact(repo, state: OperationalState, on: date | None = None) -> ToolResult:
    """What does this disruption break, directly and downstream?"""
    result = impact_mod.analyse(repo, state, on)
    led = _ledger_for_impact(repo, result)

    flight_nos = [repo.flights[f].flight_no for f in result.uncrewed_flights]
    breaches = [r for r in result.downstream_risks if r["rule"] != "COVERAGE"]
    if not result.uncrewed_flights and not result.blocked_flights:
        if breaches:
            # no leg loses its crew, but somebody's duty stops being legal -- that is
            # the whole point of asking
            listed = "; ".join(
                f"{b['crew_id']} breaches {b['rule']} ({b['detail']})" for b in breaches[:4]
            )
            summary = (
                f"{state.describe()} leaves every leg crewed, but {len(breaches)} rule "
                f"breach(es) result: {listed}."
            )
            confidence = "high"
        else:
            summary = f"{state.describe()} does not leave any flight uncovered."
            confidence = "high"
        rows = [
            [b["crew_id"], b["rule"], b["detail"]] for b in result.downstream_risks
        ]
        return ToolResult(
            summary=summary,
            data={"impact": result.to_dict(), "vacancies": result.vacancies,
                  "blocked": result.blocked_flights},
            table=_table(["Crew", "Rule", "Detail"], rows) if rows else None,
            ledger=led, tier=2, confidence=confidence,
        )
    else:
        summary = (
            f"{state.describe()}. {len(result.uncrewed_flights)} legs are uncovered "
            f"({', '.join(flight_nos[:6])}"
            + (f" +{len(flight_nos) - 6} more" if len(flight_nos) > 6 else "")
            + f"), affecting {result.passengers_affected} passengers across "
            f"{len(result.pairings_broken)} pairing(s)."
        )

    rows = []
    for fid in result.uncrewed_flights:
        f = repo.flights[fid]
        rows.append([f.flight_no, f.date, f.dep_station + "-" + f.arr_station,
                     f.dep_utc.strftime("%H:%M") + "Z", f.seats,
                     repo.flight_to_pairing.get(fid, "-")])

    return ToolResult(
        summary=summary,
        data={"impact": result.to_dict(), "vacancies": result.vacancies,
              "blocked": result.blocked_flights},
        table=_table(["Flight", "Date", "Sector", "Dep", "Seats", "Pairing"], rows) if rows else None,
        ledger=led,
        tier=2,
    )


def assess_assignment(repo, crew_id: str, pairing_id: str,
                      day_index: int | None = None) -> ToolResult:
    """Would putting this crew member on this pairing be legal? Full rule-by-rule answer."""
    led = EvidenceLedger()
    if crew_id not in repo.crew:
        return ToolResult(summary=f"No crew member {crew_id}.", confidence="cannot_answer", ledger=led)
    if pairing_id not in repo.pairings:
        return ToolResult(summary=f"No pairing {pairing_id}.", confidence="cannot_answer", ledger=led)

    pairing = repo.pairings[pairing_id]
    days = pairing.days if day_index is None else [pairing.days[day_index]]
    # If they are already rostered on this pairing the question is "may they operate
    # their own duty?", not "may they take on a second one" -- otherwise every crew
    # member would fail as double-booked against themselves.
    already_on = crew_id in pairing.crew
    candidate = build_candidate(
        repo, crew_id, days, exclude_pairing=pairing_id if already_on else None
    )
    checks = summarise(candidate.verdict)

    crew = repo.crew[crew_id]
    led.add("crew.json", f"{crew_id} rank", crew.rank)
    led.add("crew.json", f"{crew_id} base", crew.base)
    led.add("crew.json", f"{crew_id} ratings", "/".join(crew.ratings))
    for check in checks:
        led.add(check["rule_id"], check["status"], check["detail"])
        led.allow(check["rule_id"], check["actual"], check["limit"], check["margin"])
    led.add("costs.json", "assignment cost", candidate.cost_inr)
    led.allow(pairing_id, *[f for d in days for f in d.flight_ids],
              *[repo.flights[f].flight_no for d in days for f in d.flight_ids])

    verb = "operate their rostered" if already_on else "cover"
    if candidate.legal:
        summary = (
            f"Yes. {crew.rank} {crew_id} can legally {verb} {pairing_id} "
            f"({len([f for d in days for f in d.flight_ids])} legs). All seven rules pass."
            + ("" if already_on else f" Cost INR {candidate.cost_inr:,}.")
        )
    else:
        summary = (
            f"No. {crew.rank} {crew_id} cannot {verb} {pairing_id}: "
            f"{candidate.verdict.reason()}."
        )

    before_after = _before_after(repo, crew_id, candidate)

    return ToolResult(
        summary=summary,
        data={
            "crew_id": crew_id, "pairing_id": pairing_id, "legal": candidate.legal,
            "rule_checks": checks, "cost_inr": candidate.cost_inr,
            "delay_minutes": int(round(candidate.delay_hours * 60)),
            "before_after": before_after,
            "failures": [f.to_dict() for f in candidate.verdict.failures],
        },
        table=_table(
            ["Rule", "Status", "Actual", "Limit", "Detail"],
            [[c["rule_id"], c["status"], c["actual"], c["limit"], c["detail"]] for c in checks],
        ),
        ledger=led,
        tier=2,
    )


def _before_after(repo, crew_id: str, candidate) -> list[dict]:
    """Duty/flight/rest position before and after the proposed assignment."""
    from app.rules.r02_duty_7d import accrued_duty
    from app.rules.r03_flight_28d import accrued_flight

    last_day = candidate.days[-1].date
    duty_before = accrued_duty(repo, crew_id, last_day, 7)
    flight_before = accrued_flight(repo, crew_id, last_day, 28)
    duty_added = sum(d.duty_hours for d in candidate.days)
    flight_added = sum(repo.day_flight_hours(d) for d in candidate.days)

    duty_check = next(
        (r for r in candidate.verdict.results if r.rule_id == "RULE-DUTY-02"), None
    )
    flight_check = next(
        (r for r in candidate.verdict.results if r.rule_id == "RULE-FLT-03"), None
    )

    return [
        {
            "field": "Duty hours (7 calendar days)",
            "before": f"{duty_before}h",
            "after": f"{round(duty_before + duty_added, 2)}h",
            "delta": f"+{round(duty_added, 2)}h",
            "legal": bool(duty_check and not duty_check.failed),
        },
        {
            "field": "Block hours (28 calendar days)",
            "before": f"{flight_before}h",
            "after": f"{round(flight_before + flight_added, 2)}h",
            "delta": f"+{round(flight_added, 2)}h",
            "legal": bool(flight_check and not flight_check.failed),
        },
        {
            "field": "Overall legality",
            "before": "available",
            "after": "legal" if candidate.legal else "ILLEGAL",
            "delta": candidate.verdict.reason(),
            "legal": candidate.legal,
        },
    ]


def cancellation_impact(repo, flight_ids: list[str]) -> ToolResult:
    led = EvidenceLedger()
    known = [f for f in flight_ids if f in repo.flights]
    if not known:
        return ToolResult(summary="No matching flights.", confidence="cannot_answer", ledger=led)

    seats = sum(repo.flights[f].seats for f in known)
    rate = repo.cost("cancellation_per_flight")
    total = int(rate * len(known))
    for f in known:
        flight = repo.flights[f]
        led.add("flights.json", f"{flight.flight_no} seats", flight.seats)
        led.allow(f, flight.flight_no)
    led.add("costs.json", "cancellation_per_flight", int(rate))
    led.add("computed", "total cancellation cost", total)
    led.add("computed", "passengers affected", seats)

    return ToolResult(
        summary=(
            f"Cancelling {len(known)} leg(s) affects {seats} passengers at a direct "
            f"cancellation cost of INR {total:,}."
        ),
        data={"flight_ids": known, "passengers": seats, "cost_inr": total},
        table=_table(
            ["Flight", "Sector", "Seats", "Cost"],
            [[repo.flights[f].flight_no,
              repo.flights[f].dep_station + "-" + repo.flights[f].arr_station,
              repo.flights[f].seats, int(rate)] for f in known],
        ),
        ledger=led,
        tier=2,
    )


# ------------------------------------------------------------------ Tier 3

def recommend_cover(repo, pairing_id: str, role: str, crew_out: str | None = None,
                    day_index: int | None = None) -> ToolResult:
    """Ranked, rule-checked recovery options for one vacancy."""
    led = EvidenceLedger()
    pairing = repo.pairings.get(pairing_id)
    if not pairing:
        return ToolResult(summary=f"No pairing {pairing_id}.", confidence="cannot_answer", ledger=led)

    days = pairing.days if day_index is None else [pairing.days[day_index]]
    exclude = {crew_out} if crew_out else set()
    result = ranking_mod.rank_options(
        repo, days, role, exclude_crew=exclude, exclude_pairing=pairing_id
    )

    options = result["options"]
    led.add("computed", "candidates evaluated",
            result["legal_count"] + len(result["excluded"]))
    led.add("computed", "legal options", result["legal_count"])
    # every rule really was evaluated for every candidate, so every rule id is grounded
    # -- without this the verifier flags a correct citation as unverified
    led.allow(*ALL_RULES)
    for option in options:
        led.add("computed", f"option {option['rank']}", option["action"])
        led.add("costs.json", f"option {option['rank']} cost", option["cost_inr"])
        led.allow(option["resilience_note"], option["reasoning"], *option["covered_flight_ids"])
        for check in option["rule_checks"]:
            led.allow(check["rule_id"], check["actual"], check["limit"],
                      check["margin"], check["detail"])
    for excluded in result["excluded"][:20]:
        led.add("computed", f"excluded {excluded['crew_id']}", excluded["reason"])
    for relax in result["relaxations"]:
        led.add("computed", "near miss", relax["breach_detail"])
        led.allow(relax["remedy"], relax["breach_magnitude"])
    led.allow(pairing_id, crew_out, *[f for d in days for f in d.flight_ids],
              *[repo.flights[f].flight_no for d in days for f in d.flight_ids])

    top = options[0] if options else None
    if result["legal_count"] == 0 and result["chain_count"] == 0:
        summary = (
            f"No legal cover exists for {pairing_id} at {role}. "
            f"{len(result['excluded'])} candidates were checked and all failed. "
            + (f"Closest miss: {result['relaxations'][0]['breach_detail']}."
               if result["relaxations"] else "")
        )
        confidence = "review"
    else:
        summary = (
            f"{result['legal_count']} legal option(s) cover {pairing_id}. "
            f"Recommended: {top['action']} at INR {top['cost_inr']:,}, covering "
            f"{top['coverage']}."
        )
        confidence = "high"

    return ToolResult(
        summary=summary,
        data={
            "pairing_id": pairing_id, "role": role,
            "options": options, "excluded": result["excluded"],
            "relaxations": result["relaxations"],
            "legal_count": result["legal_count"], "chain_count": result["chain_count"],
        },
        ledger=led,
        tier=3,
        confidence=confidence,
    )


def recover_from_state(repo, state: OperationalState) -> ToolResult:
    """End-to-end Tier 3: work out what broke, then rank cover for every vacancy."""
    # a closure strands flights rather than uncrewing them, so it has its own recovery
    closure_result = recover_closure(repo, state)
    if closure_result is not None:
        return closure_result

    impact_result = impact_mod.analyse(repo, state)
    led = _ledger_for_impact(repo, impact_result)

    if not impact_result.vacancies:
        # no empty seat, but a delay may have made a rostered duty illegal -- the
        # recovery there is to split the duty, not to replace a person
        split_result = recover_delayed_duty(repo, state, impact_result)
        if split_result is not None:
            return split_result
        base = analyse_impact(repo, state)
        base.tier = 3
        return base

    # group vacancies by (pairing, role) -- one recovery problem each
    problems: dict[tuple[str, str, str | None], list] = {}
    for vac in impact_result.vacancies:
        problems.setdefault((vac["pairing_id"], vac["role"], vac["crew_out"]), []).append(vac)

    all_options: list[dict] = []
    all_relaxations: list[dict] = []
    parts: list[str] = []

    joint = _joint_plan(repo, sorted(problems)) if len(problems) > 1 else None

    for (pairing_id, role, crew_out), _vacs in sorted(problems.items()):
        result = recommend_cover(repo, pairing_id, role, crew_out=crew_out)
        for item in result.ledger.items:
            led.items.append(item)
        led.allow(*result.ledger.tokens)
        options = result.data.get("options", [])
        for option in options:
            option = dict(option)
            option["action"] = f"[{pairing_id} {role}] {option['action']}"
            all_options.append(option)
        all_relaxations.extend(result.data.get("relaxations", []))
        if options:
            parts.append(
                f"{pairing_id} ({role}): {options[0]['action']} at INR {options[0]['cost_inr']:,}"
            )
        else:
            parts.append(f"{pairing_id} ({role}): no legal cover found")

    for i, option in enumerate(all_options, start=1):
        option["rank"] = i

    if joint is not None and joint.assignments:
        # the per-pairing lists above each name their own cheapest crew member, and for
        # simultaneous vacancies that is often the SAME person. The joint plan is the
        # cheapest combination in which nobody is assigned twice.
        parts = [
            f"{vac.pairing_id} ({vac.role}): {cand.action} at INR {cand.cost_inr:,}"
            for vac, cand in joint.assignments
        ]
        for vac, cand in joint.assignments:
            led.add("computed", f"joint assignment {vac.pairing_id}", cand.action)
            led.add("costs.json", f"joint {vac.pairing_id} cost", cand.cost_inr)
            led.allow(cand.crew_id, cand.cost_inr)
        led.add("computed", "joint plan total", joint.total_cost_inr)
        summary = (
            f"{state.describe()}. {len(impact_result.uncrewed_flights)} legs uncovered, "
            f"{impact_result.passengers_affected} passengers exposed. "
            f"Optimal joint plan (no crew member assigned twice): "
            + "; ".join(parts)
            + f". Total INR {joint.total_cost_inr:,}."
        )
    else:
        summary = (
            f"{state.describe()}. {len(impact_result.uncrewed_flights)} legs uncovered, "
            f"{impact_result.passengers_affected} passengers exposed. "
            f"Recommended plan: " + "; ".join(parts) + "."
        )

    return ToolResult(
        summary=summary,
        data={
            "impact": impact_result.to_dict(),
            "options": all_options,
            "relaxations": all_relaxations,
            "joint_plan": (
                [
                    {"pairing_id": v.pairing_id, "role": v.role,
                     "crew_id": c.crew_id, "action": c.action, "cost_inr": c.cost_inr}
                    for v, c in joint.assignments
                ] if joint else []
            ),
            "joint_cost_inr": joint.total_cost_inr if joint else None,
        },
        ledger=led,
        tier=3,
    )


def _joint_plan(repo, problem_keys):
    """Solve simultaneous vacancies together so nobody is assigned to two pairings."""
    from app.engine import joint as joint_mod

    vacancies = [
        joint_mod.Vacancy(pairing_id=pid, role=role, crew_out=crew_out)
        for (pid, role, crew_out) in problem_keys
    ]
    return joint_mod.solve(repo, vacancies)


def recover_closure(repo, state: OperationalState) -> ToolResult | None:
    """Recovery for a station closure: delay where the duty survives, re-crew where not.

    A closure does not uncrew a flight, it strands it. Treating the legs as "uncovered"
    and reaching for replacement crew answers the wrong question -- and cancelling the
    lot is the expensive fallback, not the plan.
    """
    from app.engine import closure as closure_mod

    if not state.closures:
        return None

    led = EvidenceLedger()
    led.allow(*ALL_RULES)
    all_options: list[dict] = []
    all_legs: list[dict] = []
    rows: list[list] = []
    stations: list[str] = []
    total_pax = 0

    for station, start, end in state.closures:
        plan = closure_mod.plan(repo, station, start, end)
        if not plan.legs:
            continue
        stations.append(station)
        total_pax += plan.passengers

        led.add("computed", f"{station} closure",
                f"{start:%H:%M}-{end:%H:%M}Z on {start:%Y-%m-%d}")
        led.add("computed", "reopen buffer",
                f"{closure_mod.REOPEN_BUFFER_MINUTES} min after reopen")

        for leg in plan.legs:
            all_legs.append(leg.to_dict())
            rows.append([
                leg.flight_no, leg.pairing_id, f"{leg.side} {leg.event_utc:%H:%M}Z",
                leg.min_delay_hours, leg.crew_fdp_after_delay, leg.fdp_limit,
                "legal" if leg.legal else "FDP BREACH",
            ])
            led.add("computed", f"{leg.flight_no} minimum delay",
                    f"{leg.min_delay_hours}h")
            led.add("RULE-FDP-01", f"{leg.flight_no} FDP after delay",
                    f"{leg.crew_fdp_after_delay}h vs {leg.fdp_limit}h limit")
            led.allow(leg.flight_id, leg.flight_no, leg.pairing_id, leg.seats,
                      leg.min_delay_hours, leg.crew_fdp_after_delay, leg.fdp_limit)

        for option in plan.options:
            led.add("computed", f"option {option['pairing_id']}", option["action"])
            led.add("costs.json", f"{option['pairing_id']} {option['kind']} cost",
                    option["cost_inr"])
            led.allow(option["reasoning"], option["resilience_note"],
                      *option["covered_flight_ids"], *option["uncovered_flight_ids"])
        all_options.extend(plan.options)

    if not all_legs:
        return None

    for i, option in enumerate(all_options, start=1):
        option["rank"] = i

    breaching = [x for x in all_legs if x["action"] != closure_mod.ACTION_LEGAL]
    delayable = len(all_legs) - len(breaching)
    plan_cost = sum(
        o["cost_inr"] for o in all_options
        if o["kind"] in ("delay", "recrew")
    )
    cancel_all = sum(o["cost_inr"] for o in all_options if o["kind"] == "cancel")
    led.add("computed", "recommended plan cost", plan_cost)

    return ToolResult(
        summary=(
            f"{'/'.join(stations)} closure: {len(all_legs)} legs blocked across "
            f"{len({x['pairing_id'] for x in all_legs})} pairings, {total_pax} passengers. "
            f"{delayable} leg(s) can simply be delayed to reopen within crew FDP; "
            f"{len(breaching)} would push the rostered crew past RULE-FDP-01 and need the "
            f"tail of the duty re-crewed. Recommended plan INR {plan_cost:,} "
            f"(cancelling the blocked legs instead would cost INR {cancel_all:,})."
        ),
        data={
            "closure_legs": all_legs,
            "options": all_options,
            "relaxations": [],
        },
        table=_table(
            ["Flight", "Pairing", "Blocked", "Min delay (h)", "FDP after", "Limit", "Verdict"],
            rows,
        ),
        ledger=led,
        tier=3,
    )


def recover_delayed_duty(repo, state: OperationalState, impact_result) -> ToolResult | None:
    """Recovery for a delay that breaks FDP: split the duty rather than cancel it."""
    from app.engine import splitting
    from app.engine.cost import cancellation_cost

    fdp_breaches = [r for r in impact_result.downstream_risks if r["rule"] == "RULE-FDP-01"]
    if not fdp_breaches:
        return None

    delayed: dict[str, float] = {}
    for flight_id, hours in state.delayed_flights:
        pairing_id = repo.flight_to_pairing.get(flight_id)
        if pairing_id:
            delayed[pairing_id] = max(delayed.get(pairing_id, 0.0), hours)

    led = EvidenceLedger()
    options: list[dict] = []
    parts: list[str] = []

    for pairing_id, hours in sorted(delayed.items()):
        pairing = repo.pairings[pairing_id]
        for day in pairing.days:
            split = splitting.plan_split(repo, day, pairing.crew, hours)
            if not split:
                continue

            kept_nos = [repo.flights[f].flight_no for f in split.keep_flight_ids]
            recrew_nos = [repo.flights[f].flight_no for f in split.recrew_flight_ids]
            seats = sum(repo.flights[f].seats for f in split.recrew_flight_ids)

            led.add("RULE-FDP-01", f"{pairing_id} delayed duty",
                    f"{round(day.duty_hours + hours, 2)}h vs "
                    f"{fdp_limit_for(repo, day.sectors)}h limit ({day.sectors} sectors)")
            led.add("RULE-FDP-01", f"{pairing_id} reduced duty",
                    f"{split.kept_duty_hours}h vs {split.kept_limit}h limit "
                    f"({len(split.keep_flight_ids)} sectors)")
            led.allow(*kept_nos, *recrew_nos, *split.recrew_crew.values(),
                      split.recrew_cost_inr, seats)

            if split.feasible:
                led.add("costs.json", "fresh complement callout", split.recrew_cost_inr)
                options.append({
                    "rank": 0,
                    "action": (
                        f"Original crew operates {'-'.join([kept_nos[0], kept_nos[-1]]) if len(kept_nos) > 1 else kept_nos[0]}"
                        f" (delayed); fresh complement operates {', '.join(recrew_nos)}"
                    ),
                    "legal": True,
                    "rules_checked": ALL_RULES,
                    "rule_checks": [],
                    "cost_inr": split.recrew_cost_inr,
                    "cost_breakdown": split.cost_lines,
                    "coverage": f"all {len(day.flight_ids)} flights",
                    "covered_flight_ids": list(day.flight_ids),
                    "uncovered_flight_ids": [],
                    "delay_minutes": int(round(hours * 60)),
                    "resilience_score": 1.0,
                    "resilience_note": (
                        f"consumes {len(split.recrew_crew)} crew for one sector rather "
                        f"than a whole pairing"
                    ),
                    "chain": [],
                    "reasoning": (
                        f"Reduced duty runs {split.kept_duty_hours}h against a "
                        f"{split.kept_limit}h limit over {len(split.keep_flight_ids)} "
                        f"sectors, so the rostered crew stay legal. {split.detail}."
                    ),
                })

            cancel = cancellation_cost(repo, len(split.recrew_flight_ids))
            options.append({
                "rank": 0,
                "action": f"Cancel {', '.join(recrew_nos)}",
                "legal": True,
                "rules_checked": [],
                "rule_checks": [],
                "cost_inr": cancel.total,
                "cost_breakdown": cancel.to_list(),
                "coverage": f"{len(split.keep_flight_ids)} of {len(day.flight_ids)} flights",
                "covered_flight_ids": split.keep_flight_ids,
                "uncovered_flight_ids": split.recrew_flight_ids,
                "delay_minutes": int(round(hours * 60)),
                "resilience_score": 1.0,
                "resilience_note": "consumes no crew capacity",
                "chain": [],
                "reasoning": f"Legal but strands {seats} passengers.",
            })
            led.add("costs.json", f"cancel {', '.join(recrew_nos)}", cancel.total)
            parts.append(
                f"{pairing_id}: re-crew {', '.join(recrew_nos)} rather than cancel"
                if split.feasible else f"{pairing_id}: no fresh complement available"
            )

    if not options:
        return None

    options.sort(key=lambda o: o["cost_inr"])
    for i, option in enumerate(options, start=1):
        option["rank"] = i

    breach = fdp_breaches[0]
    return ToolResult(
        summary=(
            f"{state.describe()}. {breach['detail']} "
            f"Recommended: {options[0]['action']} at INR {options[0]['cost_inr']:,} "
            f"(cancelling instead costs INR {options[-1]['cost_inr']:,})."
        ),
        data={"impact": impact_result.to_dict(), "options": options, "relaxations": []},
        ledger=led,
        tier=3,
    )


def fdp_limit_for(repo, sectors: int) -> float:
    from app.rules.r01_fdp import fdp_limit

    return fdp_limit(repo, sectors)


def eligible_reserves(repo, pairing_id: str, role: str,
                      crew_out: str | None = None) -> ToolResult:
    """Which reserves could actually take this callout, and why the others could not.

    "On call" is not the same as "usable": the window has to cover the required report
    time AND the rating has to match AND the clocks have to allow it. Answering with the
    on-call list alone is the mistake this tool exists to prevent.
    """
    led = EvidenceLedger()
    pairing = repo.pairings.get(pairing_id)
    if not pairing:
        return ToolResult(summary=f"No pairing {pairing_id}.", confidence="cannot_answer", ledger=led)

    days = pairing.days
    report = days[0].report_utc
    actype = repo.day_aircraft_type(days[0])
    led.add("rosters.json", f"{pairing_id} required report", report.strftime("%H:%M") + "Z")
    led.add("flights.json", f"{pairing_id} aircraft type", actype)
    led.allow(*ALL_RULES)

    eligible, excluded = [], []
    for cid in sorted(repo.reserves):
        crew = repo.crew[cid]
        if crew.rank != role or cid == crew_out or crew.status != "active":
            continue
        candidate = build_candidate(repo, cid, days)
        window = f"{repo.reserves[cid].window_start}-{repo.reserves[cid].window_end}Z"
        if candidate.legal:
            eligible.append([cid, crew.rank, crew.base, window,
                             "/".join(crew.ratings), f"INR {candidate.cost_inr:,}"])
            led.add("computed", f"{cid} eligible", candidate.verdict.reason())
            led.allow(cid, window, candidate.cost_inr, *crew.ratings)
        else:
            excluded.append({
                "crew_id": cid,
                "reason": candidate.verdict.reason(),
                "rules_failed": sorted({f.rule_id for f in candidate.verdict.failures}),
            })
            led.add("computed", f"{cid} excluded", candidate.verdict.reason())
            led.allow(cid, window)

    names = ", ".join(r[0] for r in eligible) or "none"
    return ToolResult(
        summary=(
            f"{len(eligible)} reserve {role.lower()}(s) can actually take the "
            f"{pairing_id} callout (report {report.strftime('%H:%M')}Z, {actype}): {names}. "
            f"{len(excluded)} on-call reserve(s) were excluded on window, rating or clocks."
        ),
        data={
            "pairing_id": pairing_id, "role": role,
            "eligible": [r[0] for r in eligible], "excluded": excluded,
            "required_report_utc": report.isoformat(), "aircraft_type": actype,
        },
        table=_table(["Crew", "Rank", "Base", "On-call window", "Ratings", "Cost"], eligible),
        ledger=led,
        tier=2,
    )


def draft_notification(repo, crew_id: str, pairing_id: str) -> ToolResult:
    """Draft the callout message. Every operational detail comes from the engine."""
    led = EvidenceLedger()
    crew = repo.crew.get(crew_id)
    pairing = repo.pairings.get(pairing_id)
    if not crew or not pairing:
        return ToolResult(summary="Unknown crew or pairing.", confidence="cannot_answer", ledger=led)

    candidate = build_candidate(repo, crew_id, pairing.days)
    first = pairing.days[0]
    legs = [repo.flights[f] for f in pairing.all_flight_ids]

    # A multi-day pairing needs a report time PER DAY and an overnight: telling a crew
    # member only the day-1 report is how people miss a down-route sign-on.
    day_blocks: list[str] = []
    overnights: list[str] = []
    for index, day in enumerate(pairing.days, start=1):
        day_legs = [repo.flights[f] for f in day.flight_ids]
        routing = " / ".join(f"{f.flight_no} {f.dep_station}-{f.arr_station}" for f in day_legs)
        block = (
            f"Day {index} - {day.date:%a %d %b}\n"
            f"  Report   {day.report_utc:%H:%M}Z at {day_legs[0].dep_station} crew room\n"
            f"  Flights  {routing}\n"
            f"  Release  {day.release_utc:%H:%M}Z at {day_legs[-1].arr_station}"
        )
        led.add("rosters.json", f"{pairing_id} day {index} report",
                f"{day.report_utc:%Y-%m-%d %H:%M}Z at {day_legs[0].dep_station}")
        led.add("rosters.json", f"{pairing_id} day {index} routing", routing)
        led.allow(day.report_utc.strftime("%H:%M"), day.release_utc.strftime("%H:%M"),
                  day_legs[0].dep_station, day_legs[-1].arr_station)

        if index < len(pairing.days):
            station = day_legs[-1].arr_station
            overnights.append(station)
            block += f"\n  Overnight {station} - hotel arranged by Crew Control"
            led.add("costs.json", f"hotel at {station}", int(repo.cost("hotel_overnight")))
        day_blocks.append(block)

    deadline = crew.reachability_minutes
    led.add("costs.json", "callout cost", candidate.cost_inr)
    led.add("crew.json", f"{crew_id} reachability", f"{deadline} min")
    led.allow(crew.name, crew_id, pairing_id, *[f.flight_no for f in legs])

    body = (
        f"CALLOUT - {pairing_id}\n"
        f"To: {crew.rank} {crew.name} ({crew_id})\n"
        f"From: Crew Control, dCortex Air\n"
        f"{'-' * 58}\n\n"
        f"You are called out to operate {pairing_id}: {len(pairing.days)} day(s), "
        f"{len(legs)} sectors.\n\n"
        + "\n\n".join(day_blocks)
        + "\n\n"
        + (
            "Legality: checked against all seven rules - no exceedances.\n"
            if candidate.legal
            else f"Legality: REVIEW REQUIRED - {candidate.verdict.reason()}\n"
        )
        + f"\nPlease acknowledge within {deadline} minutes of receipt.\n"
        f"Questions or unable to accept: contact Crew Control on the ops desk line, "
        f"quoting {pairing_id}.\n"
    )

    headline = (
        f"Callout drafted for {crew.rank} {crew.name} ({crew_id}) on {pairing_id}: "
        f"{len(pairing.days)} day(s), {len(legs)} sectors, report "
        f"{first.report_utc:%H:%M}Z at {legs[0].dep_station}. "
        f"Acknowledgement requested within {deadline} minutes. "
        f"Draft only - not sent."
    )

    return ToolResult(
        summary=headline,
        data={
            "crew_id": crew_id, "pairing_id": pairing_id, "message": body,
            "legal": candidate.legal,
            "report_utc": first.report_utc.isoformat(),
            "acknowledge_within_minutes": deadline,
            "overnight_stations": overnights,
            "days": [
                {
                    "date": d.date.isoformat(),
                    "report_utc": d.report_utc.isoformat(),
                    "release_utc": d.release_utc.isoformat(),
                    "flight_nos": [repo.flights[f].flight_no for f in d.flight_ids],
                }
                for d in pairing.days
            ],
        },
        ledger=led,
        tier=3,
    )
