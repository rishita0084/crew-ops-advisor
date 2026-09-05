"""Engine tests.

These assert the arithmetic, not the prose. Where the dataset README states an
engineered fact ("C-2087 breaches DUTY-02 by 1h20m"), that exact figure is asserted --
if a refactor silently changes a duty calculation, these fail.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db.repository import get_repository
from app.engine import splitting
from app.engine.candidates import build_candidate, enumerate_candidates
from app.engine.impact import analyse
from app.engine.ranking import rank_options
from app.engine.state import BASE_STATE, state_from_events
from app.explain.ledger import EvidenceLedger
from app.explain.verifier import verify
from app.rules import registry
from app.rules.result import CoverRequest
from app.services import actions as A
from app.services import lookups as L


@pytest.fixture(scope="module")
def repo():
    return get_repository()


@pytest.fixture(scope="module")
def p2291(repo):
    return repo.pairings["P-2291"].days


# ---------------------------------------------------------------- dataset shape

def test_dataset_loaded(repo):
    assert len(repo.crew) == 150
    assert len(repo.flights) == 147
    assert len(repo.pairings) == 39
    assert len(repo.reserves) == 16


def test_p2291_is_the_documented_pairing(repo, p2291):
    assert [d.date.isoformat() for d in p2291] == ["2026-09-15", "2026-09-16"]
    assert [repo.flights[f].flight_no for f in p2291[0].flight_ids] == [
        "DX412", "DX413", "DX588",
    ]
    assert repo.day_passengers(p2291[0]) == 486


# ------------------------------------------------------------------- each rule

def test_rule_duty_02_breach_is_exactly_one_hour_twenty(repo, p2291):
    """README: covering P-2291 with C-2087 breaches DUTY-02 by 1h20m (61.33h)."""
    verdict = registry.evaluate(repo, CoverRequest(crew_id="C-2087", days=p2291))
    failure = next(f for f in verdict.failures if f.rule_id == "RULE-DUTY-02")
    assert failure.actual == pytest.approx(61.33, abs=0.01)
    assert "1h20m" in failure.detail
    assert failure.margin == pytest.approx(-1.33, abs=0.01)


def test_rule_qual_05_excludes_atr_only_captain(repo, p2291):
    """README: C-2091 is ATR-only, the RULE-QUAL-05 exclusion case."""
    verdict = registry.evaluate(repo, CoverRequest(crew_id="C-2091", days=p2291))
    assert not verdict.legal
    assert any(f.rule_id == "RULE-QUAL-05" for f in verdict.failures)


def test_rule_base_07_reserve_window_excludes_early_reserve(repo, p2291):
    """C-3305's 00:00-05:30Z window cannot cover a 06:00Z report."""
    verdict = registry.evaluate(repo, CoverRequest(crew_id="C-3305", days=p2291))
    assert any(
        f.rule_id == "RULE-BASE-07" and "on-call window" in f.detail
        for f in verdict.failures
    )


def test_rule_cert_06_catches_the_flagged_exception(repo):
    """The one deliberately illegal roster row: C-5417 on 2026-09-19."""
    result = A.assess_assignment(repo, "C-5417", "P-2213")
    assert result.data["legal"] is False
    assert any(f["rule_id"] == "RULE-CERT-06" for f in result.data["failures"])


def test_rule_fdp_01_reduces_with_sectors(repo):
    from app.rules.r01_fdp import fdp_limit

    assert fdp_limit(repo, 2) == 13.0
    assert fdp_limit(repo, 3) == 12.5
    assert fdp_limit(repo, 4) == 12.0


def test_rule_rest_04_minimum(repo):
    result = L.rest_calculator(repo, "15:30", date(2026, 9, 16))
    assert "03:30Z" in result.summary
    assert result.data["min_rest_hours"] == 12


def test_calendar_window_is_calendar_not_rolling(repo):
    """Q02: C-1042 has 20.93h duty in the 7 dates ending 2026-09-14, 39.07h headroom."""
    result = L.duty_clock(repo, "C-1042", date(2026, 9, 14))
    assert result.data["duty_hours_7d"] == pytest.approx(20.93, abs=0.01)
    assert result.data["headroom_hours"] == pytest.approx(39.07, abs=0.01)


# ---------------------------------------------------------------- candidates

def test_candidate_costs_match_the_answer_key(repo, p2291):
    legal, _ = enumerate_candidates(
        repo, p2291, "Captain", exclude_crew={"C-1042"}, exclude_pairing="P-2291"
    )
    by_id = {c.crew_id: c.cost_inr for c in legal}
    assert by_id["C-3310"] == 18500          # reserve callout
    assert by_id["C-1526"] == 24000          # day-off callout
    assert by_id["C-2210"] == 41200          # + deadhead from DEL + 3h delay cost


def test_deadhead_delay_is_derived_from_the_schedule(repo, p2291):
    candidate = build_candidate(repo, "C-2210", p2291)
    assert candidate.positioning.required
    assert candidate.delay_hours == pytest.approx(3.0, abs=0.01)


# -------------------------------------------------------------------- impact

def test_impact_traverses_the_whole_pairing(repo):
    state = BASE_STATE.with_crew_unavailable("C-1042", "sick")
    result = analyse(repo, state, date(2026, 9, 15))
    nos = {repo.flights[f].flight_no for f in result.uncrewed_flights}
    assert {"DX412", "DX413", "DX588"} <= nos          # day 1, immediate
    assert {"DX589", "DX590", "DX591"} <= nos          # day 2, also uncovered
    assert result.passengers_affected == 486           # immediate day only


def test_delay_extends_duty_and_breaches_fdp(repo):
    """A delay lengthens a duty; it does not shift it. That is what breaks FDP."""
    state = BASE_STATE.with_flight_delay("DX401-2026-09-16", 1.5)
    result = analyse(repo, state)
    fdp = [r for r in result.downstream_risks if r["rule"] == "RULE-FDP-01"]
    assert fdp, "a 90-minute delay on a 4-sector duty must breach the 12h FDP limit"
    assert "12.75" in fdp[0]["detail"]


def test_station_closure_blocks_both_ends(repo):
    from app.domain.time_utils import time_on_date

    state = BASE_STATE.with_station_closure(
        "HYD", time_on_date(date(2026, 9, 19), "05:00"),
        time_on_date(date(2026, 9, 19), "09:00"),
    )
    result = analyse(repo, state)
    assert {repo.flights[f].flight_no for f in result.uncrewed_flights} == {"DX461", "DX462"}


# ------------------------------------------------------- copy-on-write safety

def test_scenarios_never_mutate_the_base_state(repo):
    a = BASE_STATE.with_crew_unavailable("C-1042", "sick")
    b = BASE_STATE.with_crew_unavailable("C-2087", "sick")
    assert BASE_STATE.unavailable_crew == frozenset()
    assert a.unavailable_crew == {"C-1042"}
    assert b.unavailable_crew == {"C-2087"}
    assert "C-1042" not in b.unavailable_crew


def test_what_if_leaves_the_roster_untouched(repo):
    before = [b.pairing_id for b in repo.roster["C-1042"]]
    A.assess_assignment(repo, "C-2087", "P-2291")
    A.recommend_cover(repo, "P-2291", "Captain", crew_out="C-1042")
    assert [b.pairing_id for b in repo.roster["C-1042"]] == before


def test_simultaneous_disruptions_are_solved_jointly(repo):
    state = state_from_events(repo, [{
        "type": "MULTI_SICK",
        "events": [
            {"crew_id": "C-3940", "pairing_id": "P-2205"},
            {"crew_id": "C-1938", "pairing_id": "P-2212"},
        ],
    }])
    assert state.unavailable_crew == {"C-3940", "C-1938"}
    result = A.recover_from_state(repo, state)
    assert result.data["options"]


# -------------------------------------------------------------------- ranking

def test_ranking_matches_the_answer_key_order(repo, p2291):
    result = rank_options(
        repo, p2291, "Captain", exclude_crew={"C-1042"}, exclude_pairing="P-2291"
    )
    costs = [o["cost_inr"] for o in result["options"]]
    assert costs == sorted(costs), "options must be cheapest-first"
    assert result["options"][0]["cost_inr"] == 18500
    assert result["options"][-1]["cost_inr"] == 1_500_000     # cancel all 6 legs
    assert result["options"][-1]["action"].startswith("Cancel")


def test_illegal_candidates_are_filtered_not_penalised(repo, p2291):
    result = rank_options(
        repo, p2291, "Captain", exclude_crew={"C-1042"}, exclude_pairing="P-2291"
    )
    assert all(o["legal"] for o in result["options"])
    assert any(e["crew_id"] == "C-2087" for e in result["excluded"])


def test_resilience_is_reported(repo, p2291):
    result = rank_options(
        repo, p2291, "Captain", exclude_crew={"C-1042"}, exclude_pairing="P-2291"
    )
    top = result["options"][0]
    assert 0.0 <= top["resilience_score"] <= 1.0
    assert top["resilience_note"]


# ------------------------------------------------------------------ splitting

def test_duty_split_recrews_only_the_illegal_tail(repo):
    pairing = repo.pairings[repo.flight_to_pairing["DX401-2026-09-16"]]
    split = splitting.plan_split(repo, pairing.days[0], pairing.crew, 1.5)
    assert split is not None
    assert len(split.keep_flight_ids) == 3
    assert split.recrew_flight_ids == ["DX404-2026-09-16"]
    assert split.kept_duty_hours == pytest.approx(9.5, abs=0.01)
    assert split.kept_limit == 12.5
    assert split.feasible
    assert len(split.recrew_crew) == 6          # full A320 complement


# ------------------------------------------------------------------ verifier

def test_verifier_rejects_a_fabricated_crew_id():
    ledger = EvidenceLedger()
    ledger.add("crew.json", "C-3310 rank", "Captain")
    result = verify("Assign C-9999 instead of C-3310.", ledger)
    assert not result.verified
    assert any("C-9999" in claim for claim in result.unverified_claims)


def test_verifier_rejects_an_invented_cost():
    ledger = EvidenceLedger()
    ledger.add("costs.json", "option 1 cost", 18500)
    result = verify("This costs INR 18,500.", ledger)
    assert result.verified
    bad = verify("This costs INR 99,999.", ledger)
    assert not bad.verified


def test_verifier_passes_grounded_text():
    ledger = EvidenceLedger()
    ledger.add("crew.json", "C-3310 rank", "Captain")
    ledger.add("costs.json", "callout", 18500)
    assert verify("Captain C-3310, INR 18,500.", ledger).verified


# ------------------------------------------------------- deterministic fallback

def test_router_answers_without_an_llm(repo):
    from app.fallback import structured_query

    result = structured_query.route(
        repo, "Who is on reserve at BLR on 2026-09-15?"
    )
    assert result.confidence == "high"
    assert "reserve" in result.summary.lower()


def test_router_refuses_rather_than_guesses(repo):
    from app.fallback import structured_query

    result = structured_query.route(repo, "What is the meaning of life?")
    assert result.confidence == "cannot_answer"


def test_unknown_crew_is_refused_not_invented(repo):
    result = L.crew_profile(repo, "C-0000")
    assert result.confidence == "cannot_answer"


# ------------------------------------------------------------------ scorecard

def test_scorecard_runs_clean(repo):
    from app.services.scorecard import run_scorecard

    card = run_scorecard(repo)
    failures = [c for c in card["cases"] if not c["passed"]]
    assert not failures, f"scorecard regressions: {[(c['id'], c['detail']) for c in failures]}"
    assert card["scenarios"]["total"] == 6
    assert sum(t["total"] for t in card["tiers"]) == 38


def test_verifier_normalises_unicode_dashes():
    """Models emit "C-3310" with a non-breaking hyphen; the check must still fire."""
    ledger = EvidenceLedger()
    ledger.add("crew.json", "C-3310 rank", "Captain")
    assert verify("Assign C\u20113310.", ledger).verified
    bad = verify("Assign C\u20119999.", ledger)
    assert not bad.verified
    assert any("C-9999" in claim for claim in bad.unverified_claims)


# ------------------------------------------------------------------------ MCP

def test_mcp_adapter_exposes_the_same_engine(repo):
    """The MCP door and the REST door must return the same answer, not similar ones."""
    mcp_index = pytest.importorskip(
        "mcp_server.index", reason="MCP SDK not installed (pip install mcp)"
    )
    import json as _json

    assert len(mcp_index.TOOLS) == len(mcp_index.tool_mod.TOOL_SPECS) == 16

    via_mcp = _json.loads(
        mcp_index.recommend_recovery(pairing_id="P-2291", role="Captain", crew_out="C-1042")
    )
    via_engine = A.recommend_cover(repo, "P-2291", "Captain", crew_out="C-1042")

    assert via_mcp["summary"] == via_engine.summary
    assert via_mcp["data"]["options"][0]["cost_inr"] == 18500
    assert via_mcp["evidence"], "evidence must travel with the MCP answer too"


# ---------------------------------------------------------------- closures

def test_closure_delay_arithmetic_matches_the_answer_key(repo):
    """Every one of the 13 legs in the Q35/S3 key, to the exact quarter-hour.

    min_delay = (reopen + 30min turnaround) - the leg's scheduled time at the closed
    station; fdp_after = the duty's own length + that delay.
    """
    import json as _json
    from datetime import datetime

    from app.config import DATA_DIR
    from app.engine import closure as closure_mod

    with open(DATA_DIR / "questions.json", encoding="utf-8") as fh:
        expected = {q["question_id"]: q for q in _json.load(fh)}["Q35"]["expected_answer"]

    plan = closure_mod.plan(
        repo, "BLR", datetime(2026, 9, 17, 8, 0), datetime(2026, 9, 17, 14, 0)
    )
    produced = {leg.flight_id: leg for leg in plan.legs}

    assert len(produced) == len(expected) == 13
    for row in expected:
        leg = produced[row["flight_id"]]
        assert leg.pairing_id == row["pairing_id"]
        assert leg.min_delay_hours == pytest.approx(row["min_delay_hours"], abs=0.01)
        assert leg.crew_fdp_after_delay == pytest.approx(row["crew_fdp_after_delay"], abs=0.01)
        assert leg.fdp_limit == pytest.approx(row["fdp_limit"], abs=0.01)
        # the key phrases the verdict two ways; what matters is which side of the limit
        assert leg.legal == row["action"].startswith("delay (crew legal)")


def test_closure_recovery_beats_cancelling_everything(repo):
    """A closure strands flights; it does not uncrew them. Cancelling all 13 legs is
    the fallback, not the plan."""
    from datetime import datetime

    from app.engine.state import BASE_STATE

    state = BASE_STATE.with_station_closure(
        "BLR", datetime(2026, 9, 17, 8, 0), datetime(2026, 9, 17, 14, 0)
    )
    result = A.recover_closure(repo, state)
    assert result is not None

    options = result.data["options"]
    kinds = {o["kind"] for o in options}
    assert "recrew" in kinds, "must offer re-crewing the tail, not only cancellation"
    assert "delay" in kinds, "P-2232 absorbs the delay legally and should just be delayed"

    workable = sum(o["cost_inr"] for o in options if o["kind"] in ("delay", "recrew"))
    cancel_all = sum(o["cost_inr"] for o in options if o["kind"] == "cancel")
    assert workable < cancel_all / 4, (
        f"recovery plan {workable} should be far cheaper than cancelling {cancel_all}"
    )


def test_closure_recovery_is_reachable_from_plain_english(repo):
    """The phrasings a controller actually types must all land on the closure plan."""
    from app.fallback import structured_query

    for question in (
        "BLR closes 08:00\u201314:00Z on 17 Sep. Outline the recovery plan across affected pairings.",
        "BLR closes 0800-1400Z on 17 Sep. What is the recovery plan?",
        "What happens if BLR shuts from 08:00 until 14:00Z on 17 September?",
        "BLR closure 08:00-14:00Z 17 Sep - recovery plan?",
    ):
        result = structured_query.route(repo, question)
        assert result.confidence != "cannot_answer", f"router lost: {question}"
        assert "13 legs" in result.summary or "13" in str(result.data)


# -------------------------------------------------------------- strict audit

def test_every_question_matches_its_answer_key(repo):
    """All 38 questions, checked field-by-field against questions.json.

    This is the guard that matters: a loose grader once let Q35 pass while the closure
    engine was answering a different question entirely.
    """
    from app.services.audit import audit

    rows = audit(repo)
    assert len(rows) == 38
    failures = [(r["id"], r["detail"]) for r in rows if not r["passed"]]
    assert not failures, f"answer-key mismatches: {failures}"


def test_joint_plan_never_assigns_one_person_twice(repo):
    """Two simultaneous captain sick calls must not both be given the same reserve."""
    from app.engine import joint as joint_mod

    vacancies = [
        joint_mod.Vacancy("P-2205", "Captain", "C-3940"),
        joint_mod.Vacancy("P-2212", "Captain", "C-1938"),
    ]
    plan = joint_mod.solve(repo, vacancies)
    assigned = [c.crew_id for _v, c in plan.assignments]
    assert len(assigned) == 2
    assert len(set(assigned)) == 2, f"double-assigned {assigned}"
    # cheapest distinct pairing is one reserve callout plus one day-off callout
    assert plan.total_cost_inr == 42500


def test_callout_draft_covers_every_item_the_key_requires(repo):
    """Q36's key lists six things a callout must contain. All six, from the roster."""
    result = A.draft_notification(repo, "C-3310", "P-2291")
    message = result.data["message"]

    assert "C-3310" in message and "P-2291" in message
    # a report time for EACH day, not just the first
    assert "06:00Z at BLR" in message, "day 1 report missing"
    assert "04:00Z at DEL" in message, "day 2 down-route report missing"
    assert "Overnight DEL" in message and "hotel" in message.lower()
    for flight in ("DX412", "DX413", "DX588", "DX589", "DX590", "DX591"):
        assert flight in message
    assert "acknowledge within 45 minutes" in message
    assert "contact" in message.lower()

    assert result.data["overnight_stations"] == ["DEL"]
    assert len(result.data["days"]) == 2


# ------------------------------------------------------- derived conventions

def test_operating_conventions_are_derived_not_hardcoded(repo):
    """Snapshot, week, complement and duty brackets all come from the data.

    Each of these was once written down in the code. A second source of truth that a new
    dataset could silently invalidate is exactly the failure mode this project exists to
    avoid, so they are derived and asserted against the data here.
    """
    import json as _json

    from app.config import DATA_DIR, SNAPSHOT_UTC, WEEK_END, WEEK_START

    with open(DATA_DIR / "duty_clocks.json", encoding="utf-8") as fh:
        stamps = {c["as_of_utc"] for c in _json.load(fh)}
    assert len(stamps) == 1
    assert SNAPSHOT_UTC.strftime("%Y-%m-%dT%H:%M:%SZ") == next(iter(stamps))

    with open(DATA_DIR / "flights.json", encoding="utf-8") as fh:
        dates = {f["date"] for f in _json.load(fh)}
    assert (WEEK_START, WEEK_END) == (min(dates), max(dates))

    conv = repo.conventions
    # complement matches what is actually rostered, per aircraft type
    for pairing in repo.pairings.values():
        actype = repo.day_aircraft_type(pairing.days[0])
        counts: dict[str, int] = {}
        for role in pairing.crew.values():
            counts[role] = counts.get(role, 0) + 1
        assert counts == conv.complement[actype], f"{pairing.pairing_id} breaks {actype}"

    # report is one hour before the first departure, release 30 min after the last arrival
    for pairing in repo.pairings.values():
        for day in pairing.days:
            legs = sorted((repo.flights[f] for f in day.flight_ids), key=lambda f: f.dep_utc)
            assert legs[0].dep_utc - day.report_utc == conv.report_lead
            assert day.release_utc - legs[-1].arr_utc == conv.release_trail


def test_engine_never_reads_the_wall_clock(repo):
    """Every operational date resolves from the frozen snapshot, not from today.

    Mixing the two would produce answers that look plausible and are silently wrong, so
    the only permitted real-clock use is the scorecard's "generated at" stamp.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = set()
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"datetime\.now\(|date\.today\(|utcnow\(", text):
            # as_posix so the assertion does not depend on the OS path separator
            offenders.add(path.relative_to(root).as_posix())

    # scorecard.py stamps "generated at", which is a genuine real-world fact.
    # Anything else reading the clock would silently mix real time with the frozen
    # snapshot and produce answers that look plausible and are wrong.
    assert offenders == {"services/scorecard.py"}, (
        f"unexpected wall-clock use in the engine: {sorted(offenders)}"
    )


# ------------------------------------------- scarcity: chains and near-misses

def test_near_misses_are_reported_even_when_options_exist(repo, p2291):
    """Relaxation used to run only at zero legal cover, so on a well-crewed week it
    never spoke. How close the next candidate came is useful either way."""
    result = rank_options(
        repo, p2291, "Captain", exclude_crew={"C-1042"}, exclude_pairing="P-2291"
    )
    assert result["legal_count"] > 0
    assert result["relaxations"], "near-misses should be reported alongside legal options"
    near = result["relaxations"][0]
    assert near["breach_magnitude"]
    assert near["remedy"]


def test_swap_chains_appear_once_direct_cover_runs_out(repo, p2291):
    """Reserves spent on an earlier call is how cover actually runs out. When it does,
    the answer should be a swap cascade rather than a shrug."""
    committed = {"C-1042", "C-3310", "C-1526", "C-3983"}
    result = rank_options(
        repo, p2291, "Captain", exclude_crew=committed, exclude_pairing="P-2291"
    )
    assert result["legal_count"] <= 2
    assert result["chain_count"] > 0, "thin cover should trigger the chain search"

    chained = [o for o in result["options"] if o["chain"]]
    assert chained
    steps = chained[0]["chain"]
    assert len(steps) == 2, "a backfilled swap is two moves"
    assert "Move" in steps[0]["action"] and "Backfill" in steps[1]["action"]
    # every move in the chain carries its own rule checks
    assert all(step["rule_checks"] for step in steps)
    # and nobody is used twice inside one chain
    assert len({step["crew_id"] for step in steps}) == len(steps)


def test_a_controller_can_say_which_crew_are_already_committed(repo):
    """The scarcity path has to be reachable in plain English, not just in code."""
    from app.fallback import structured_query

    result = structured_query.route(
        repo,
        "Captain C-1042 is out for P-2291 and C-3310, C-1526, C-3983 are already "
        "committed. What should I do?",
    )
    assert result.data["chain_count"] > 0
    assert "already committed" in result.summary


def test_a_single_match_reads_like_a_sentence(repo):
    """This fleet really does have one DEL-based captain, so the singular case is
    not an edge case -- it is an answer a judge will see. It has to read as an
    answer rather than as a broken format string."""
    from app.services import lookups

    one = lookups.crew_search(repo, rank="Captain", base="DEL")
    assert one.data["count"] == 1
    assert one.summary == "1 crew member matches Captain based at DEL."

    many = lookups.crew_search(repo, rank="Captain", base="BLR")
    assert many.data["count"] > 1
    assert many.summary.startswith(f"{many.data['count']} crew members match ")


def test_an_unrelated_earlier_turn_is_not_used_as_the_answer(repo):
    """The thread may supply which crew member we mean. It may not supply the question.

    Asking "which captains are based in DEL?" and then "today's captain called in
    sick, who should replace them?" used to confidently re-serve the DEL lookup --
    a real answer, fully grounded, to a question nobody asked.
    """
    from app.llm import orchestrator

    history = [
        {"role": "user", "content": "which captains are based in DEL?"},
        {"role": "assistant", "content": "1 crew member matches Captain based at DEL."},
    ]
    answer = orchestrator._deterministic(
        repo, "Today's captain just called in sick. Who should replace them?",
        0.0, "test", history,
    )
    assert answer.confidence == "cannot_answer"
    assert "DEL" not in answer.text

    # ...but a real follow-up, about the same pairing, still resolves from the thread
    thread = [{"role": "user", "content": "Captain C-1042 is sick for P-2291, what should I do?"}]
    followup = orchestrator._deterministic(repo, "why not the cheapest option?", 0.0, "test", thread)
    assert followup.confidence != "cannot_answer"
    assert "P-2291" in followup.text


def test_a_long_rate_limit_wait_is_not_slept_through(repo):
    """A daily cap says "try again in 54s". Sleeping through that three times turned
    a fallback that should be instant into a 24-second stall at the desk."""
    import httpx
    from app.llm.providers import openai_compat

    daily_cap = httpx.Response(
        429,
        headers={"retry-after": "54"},
        text='{"error":{"message":"Rate limit reached ... tokens per day (TPD)"}}',
    )
    per_minute = httpx.Response(429, headers={"retry-after": "2"}, text="{}")

    assert openai_compat._retry_after(daily_cap) == 54.0, "the real wait, unclamped"
    assert openai_compat._retry_after(daily_cap) > openai_compat.MAX_BACKOFF_SECONDS
    assert openai_compat._retry_after(per_minute) <= openai_compat.MAX_BACKOFF_SECONDS


def test_a_roster_question_is_answered_with_the_roster(repo):
    """"What is C-1042 flying tomorrow?" is a date question. Answering it with a
    profile card -- rank, base, every pairing they hold all week -- is not an answer,
    and it was doing exactly that for every date anyone asked about."""
    from app.fallback import structured_query
    from datetime import date

    tomorrow = structured_query.route(repo, "what is C-1042 flying tomorrow?")
    assert "P-2291" in tomorrow.summary and "DX412" in tomorrow.summary
    assert tomorrow.data["date"] == "2026-09-15"

    # a different date must give a different answer, which is what was broken
    later = structured_query.route(repo, "what is C-1042 flying on 16 Sep?")
    assert later.data["date"] == "2026-09-16"
    assert later.data["flights"] != tomorrow.data["flights"]


def test_a_date_outside_the_published_week_is_said_out_loud(repo):
    """Returning "nothing rostered" for a week we do not hold reads as fact. It isn't."""
    from app.fallback import structured_query

    for question, word in [("what is C-1042 flying on 2026-09-25?", "after"),
                           ("what is C-1042 flying on 2026-09-10?", "before")]:
        result = structured_query.route(repo, question)
        assert result.confidence == "cannot_answer"
        assert word in result.summary and "2026-09-20" in result.summary


def test_two_sick_crew_are_two_vacancies_not_a_thinner_pool(repo):
    """"Both sick" and "already committed" are different questions. Reading the first
    as the second silently leaves the second pairing uncrewed."""
    from app.fallback import structured_query

    both = structured_query.route(
        repo, "C-1042 and C-1526 are both sick on 15 Sep, what should I do?")
    assert "joint" in both.summary.lower()
    assert "no crew member assigned twice" in both.summary

    spent = structured_query.route(
        repo, "C-1042 is out for P-2291 and C-3310, C-1526 are already committed. "
              "What should I do?")
    assert "already committed" in spent.summary
    assert "joint" not in spent.summary.lower()

    # and nobody named as sick may be offered as their own cover
    named = structured_query.route(
        repo, "C-1042 and C-3310 are both sick for 2026-09-15, what should I do?")
    assert "C-3310" not in named.summary


def test_it_refuses_what_the_dataset_does_not_hold(repo):
    """Naming a crew member is not the same as asking something answerable about them.
    "How much does C-1042 get paid?" returned their profile at high confidence: every
    word true, none of it the answer."""
    from app.fallback import structured_query

    for question in ["How much does C-1042 get paid?",
                     "What is the weather at BLR?",
                     "What is C-1042's phone number?"]:
        result = structured_query.route(repo, question)
        assert result.confidence == "cannot_answer", question
        assert "not in this dataset" in result.summary


def test_legality_survives_the_words_a_controller_actually_uses(repo):
    """"Allowed to operate" is the same question as "can cover", and must not be read
    as a request for that crew member's schedule."""
    from app.fallback import structured_query

    for question in ["Is C-2087 allowed to operate P-2291?",
                     "can C-2087 cover P-2291?",
                     "If C-2087 covers P-2291 does anything break?"]:
        result = structured_query.route(repo, question)
        assert "RULE-DUTY-02" in result.summary, question
        assert "61.33" in result.summary, question


def test_our_own_thresholds_are_grounded_too(repo):
    """The verifier does not get to make an exception for numbers we chose ourselves.
    A duty threshold quoted in the summary but never recorded as evidence was flagged
    unverified -- correctly, and the fix is to record it, not to relax the check."""
    from app.explain.verifier import verify
    from app.fallback import structured_query

    result = structured_query.route(repo, "who is near their duty limit?")
    assert verify(result.summary, result.ledger).verified
    # and the headroom column is measured against the rule, not a literal 60
    limit = float(repo.rule_param("RULE-DUTY-02", "max_duty_hours", 60))
    for row in result.table["rows"]:
        assert row[4] == round(limit - row[3], 2)
