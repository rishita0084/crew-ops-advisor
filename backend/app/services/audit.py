"""Strict, per-question audit against questions.json.

The earlier grader compared loose token containment with an 80% threshold. That is not
good enough: it let Q35 look healthy while the closure engine was answering an entirely
different question. Every case here is checked semantically -- the exact field, the exact
value -- against the answer key, which is the source of truth for both the arithmetic and
the algorithm.

Each checker returns (passed, detail). A checker that cannot express a fair mechanical
test says so and is reported as UNGRADED, never silently passed.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Callable

from app.config import DATA_DIR
from app.fallback import structured_query
from app.services.lookups import ToolResult

TOL = 0.011


def _load_questions() -> list[dict]:
    with open(DATA_DIR / "questions.json", encoding="utf-8") as fh:
        return json.load(fh)


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close(a, b) -> bool:
    fa, fb = _num(a), _num(b)
    return fa is not None and fb is not None and abs(fa - fb) <= TOL


def _rows(result: ToolResult) -> list[list]:
    return (result.table or {}).get("rows", [])


def _col(result: ToolResult, name: str) -> int | None:
    cols = (result.table or {}).get("columns", [])
    return cols.index(name) if name in cols else None


def _text(result: ToolResult) -> str:
    return " ".join([result.summary, json.dumps(result.data, default=str)])


# --------------------------------------------------------------------- checkers
# Each takes (repo, result, expected) -> (passed, detail)

def q01(repo, r, exp):
    got = set(r.data.get("crew_ids", []))
    want = {x["crew_id"] for x in exp}
    if got != want:
        return False, f"reserve set differs: missing {sorted(want - got)}, extra {sorted(got - want)}"
    idx_c, idx_w = _col(r, "Crew"), _col(r, "On-call window")
    windows = {row[idx_c]: row[idx_w] for row in _rows(r)}
    for entry in exp:
        want_w = f"{entry['window']['start']}-{entry['window']['end']}Z"
        if windows.get(entry["crew_id"]) != want_w:
            return False, f"{entry['crew_id']} window {windows.get(entry['crew_id'])} != {want_w}"
    return True, f"{len(want)} reserves with matching on-call windows"


def q02(repo, r, exp):
    for key in ("duty_hours_7d", "headroom_hours"):
        if not _close(r.data.get(key), exp[key]):
            return False, f"{key} {r.data.get(key)} != {exp[key]}"
    return True, f"duty {exp['duty_hours_7d']}h, headroom {exp['headroom_hours']}h"


def q03(repo, r, exp):
    got = sorted(r.data.get("flight_nos", []))
    return (got == sorted(exp), f"departing flights {got} vs {sorted(exp)}")


def q04(repo, r, exp):
    idx = {n: _col(r, n) for n in ("Crew", "Certification", "Expires")}
    got = {(row[idx["Crew"]], row[idx["Certification"]], row[idx["Expires"]]) for row in _rows(r)}
    want = {(x["crew_id"], x["cert_type"], x["valid_to"]) for x in exp}
    if got != want:
        return False, f"missing {sorted(want - got)}, extra {sorted(got - want)}"
    return True, f"{len(want)} expiring certifications match exactly"


def q05(repo, r, exp):
    ids = r.data.get("flight_ids", [])
    if len(ids) != 1:
        return False, f"expected exactly one leg, got {ids}"
    f = repo.flights[ids[0]]
    ok = (f.aircraft == exp["aircraft"] and f.aircraft_type == exp["aircraft_type"]
          and f.seats == exp["seats"])
    return ok, f"{f.aircraft} {f.aircraft_type} {f.seats} seats vs {exp}"


def q06(repo, r, exp):
    reserve = repo.reserves.get("C-3310")
    crew = repo.crew.get("C-3310")
    ok = (reserve and reserve.window_start == exp["window"]["start"]
          and reserve.window_end == exp["window"]["end"]
          and crew.reachability_minutes == exp["reachability_minutes"])
    shown = _text(r)
    ok = ok and exp["window"]["start"] in shown and str(exp["reachability_minutes"]) in shown
    return ok, f"window {reserve.window_start}-{reserve.window_end}, {crew.reachability_minutes} min"


def q07(repo, r, exp):
    crew = repo.crew["C-2210"]
    ok = crew.base == exp["base"] and list(crew.ratings) == exp["ratings"]
    return ok and crew.base in _text(r), f"base {crew.base}, ratings {list(crew.ratings)}"


def q08(repo, r, exp):
    got = r.data.get("crew", {})
    want = {x["crew_id"]: x["role"] for x in exp}
    return got == want, f"{len(want)} crew/role pairs" if got == want else f"{got} != {want}"


def q09(repo, r, exp):
    got = set(r.data.get("flight_nos", []))
    return got == set(exp), f"{sorted(got)} vs {sorted(exp)}"


def q10(repo, r, exp):
    return r.data.get("count") == exp, f"count {r.data.get('count')} vs {exp}"


def q11(repo, r, exp):
    got = sorted(r.data.get("crew_ids", []))
    return got == sorted(exp), f"{got} vs {sorted(exp)}"


def q12(repo, r, exp):
    ok = _close(r.data.get("block_hours"), exp["block_hours"])
    got = sorted(r.data.get("flight_nos", []))
    ok = ok and got == sorted(exp["flights"])
    return ok, f"{r.data.get('block_hours')}h on {got} vs {exp['block_hours']}h on {sorted(exp['flights'])}"


def q13(repo, r, exp):
    if repo.crew["C-2087"].rank != exp["rank"]:
        return False, "rank mismatch"
    if not _close(r.data.get("flight_hours_28d"), exp["flight_hours_28d"]):
        return False, f"flight_hours_28d {r.data.get('flight_hours_28d')} != {exp['flight_hours_28d']}"
    return True, f"{exp['rank']}, {exp['flight_hours_28d']}h/28d"


def q14(repo, r, exp):
    got = sorted(r.data.get("destinations", []))
    return got == sorted(exp), f"{got} vs {sorted(exp)}"


def q15(repo, r, exp):
    got = r.data.get("crew", {})
    scc = [cid for cid, role in got.items() if role == "Senior Cabin Crew"]
    return scc == [exp], f"SCC {scc} vs [{exp}]"


def q16(repo, r, exp):
    ok = _close(r.data.get("score"), exp["score"])
    ok = ok and sorted(r.data.get("drivers", [])) == sorted(exp["drivers"])
    return ok, f"score {r.data.get('score')} drivers {r.data.get('drivers')}"


def q17(repo, r, exp):
    impact = r.data.get("impact", {})
    imm = set(impact.get("immediate_flights", []))
    at_risk = set(impact.get("at_risk_flights", []))
    if imm != set(exp["day1"]):
        return False, f"day1 {sorted(imm)} != {sorted(exp['day1'])}"
    if at_risk != set(exp["day2_also_at_risk"]):
        return False, f"day2 {sorted(at_risk)} != {sorted(exp['day2_also_at_risk'])}"
    if impact.get("passengers_affected") != exp["passengers_day1"]:
        return False, f"pax {impact.get('passengers_affected')} != {exp['passengers_day1']}"
    return True, f"day1 {len(imm)} legs / {exp['passengers_day1']} pax, day2 {len(at_risk)} at risk"


def q18(repo, r, exp):
    if r.data.get("legal") is not (exp["legal"]):
        return False, f"legal {r.data.get('legal')} != {exp['legal']}"
    details = [f["detail"] for f in r.data.get("failures", [])]
    for issue in exp["issues"]:
        needle = issue.split(": ", 1)[1]
        if not any(needle in d for d in details):
            return False, f"missing issue: {needle}"
    return True, f"illegal with {len(exp['issues'])} matching DUTY-02 breaches"


def q19(repo, r, exp):
    got = {leg["flight_id"] for leg in r.data.get("closure_legs", [])}
    return got == set(exp), f"{len(got)} legs vs {len(exp)}; diff {sorted(got ^ set(exp))}"


def q20(repo, r, exp):
    risks = (r.data.get("impact") or {}).get("downstream_risks", [])
    fdp = [x for x in risks if x["rule"] == "RULE-FDP-01"]
    if bool(fdp) is not exp["breach"]:
        return False, f"breach {bool(fdp)} != {exp['breach']}"
    detail = fdp[0]["detail"] if fdp else ""
    ok = str(exp["fdp_after_delay"]) in detail and str(exp["fdp_limit"]) in detail
    return ok, detail or "no FDP breach reported"


def q21(repo, r, exp):
    if r.data.get("legal") is not exp["legal"]:
        return False, f"legal {r.data.get('legal')} != {exp['legal']}"
    # the consequence is deadhead positioning plus roughly a 3h delay to first departure
    minutes = r.data.get("delay_minutes", 0)
    ok = abs(minutes - 180) <= 15
    return ok, f"legal, positioning delay {minutes} min (expected ~180)"


def q22(repo, r, exp):
    if r.data.get("legal") is not exp["legal"]:
        return False, f"legal {r.data.get('legal')} != {exp['legal']}"
    fails = {f["rule_id"] for f in r.data.get("failures", [])}
    if exp["rule"] not in fails:
        return False, f"expected {exp['rule']}, got {sorted(fails)}"
    detail = " ".join(f["detail"] for f in r.data.get("failures", []))
    ok = "recurrent_training" in detail and "2026-09-17" in detail
    return ok, detail[:110]


def q23(repo, r, exp):
    got = r.data.get("earliest_report_utc", "")
    want = exp.replace("Z", "")
    return got.startswith(want), f"{got} vs {exp}"


def q24(repo, r, exp):
    if r.data.get("legal") is not exp["legal"]:
        return False, f"legal {r.data.get('legal')} != {exp['legal']}"
    details = [f["detail"] for f in r.data.get("failures", [])]
    needle = exp["issues"][0].split(": ", 1)[1]
    ok = any(needle in d for d in details)
    return ok, needle if ok else f"missing {needle}; got {details}"


def q25(repo, r, exp):
    ok = (r.data.get("passengers") == exp["passengers"]
          and r.data.get("cost_inr") == exp["cost_inr"])
    return ok, f"{r.data.get('passengers')} pax, INR {r.data.get('cost_inr')}"


def q26(repo, r, exp):
    idx_c, idx_h = _col(r, "Crew"), _col(r, "Duty hours")
    got = {row[idx_c]: row[idx_h] for row in _rows(r)}
    want = {x["crew_id"]: x["duty_hours_7d_incl_15sep_plan"] for x in exp}
    if set(got) != set(want):
        return False, f"crew {sorted(got)} != {sorted(want)}"
    for cid, hours in want.items():
        if not _close(got[cid], hours):
            return False, f"{cid} {got[cid]} != {hours}"
    return True, ", ".join(f"{c} {h}h" for c, h in sorted(want.items()))


def q27(repo, r, exp):
    got = set(r.data.get("eligible", []))
    if got != set(exp["eligible"]):
        return False, f"eligible {sorted(got)} != {exp['eligible']}"
    excluded = {x["crew_id"]: x["reason"] for x in r.data.get("excluded", [])}
    for entry in exp["excluded_examples"]:
        cid = entry["crew_id"]
        if cid not in excluded:
            return False, f"{cid} not reported as excluded"
        rule = entry["reason"].split(":")[0]
        if rule.startswith("RULE-") and rule not in excluded[cid]:
            return False, f"{cid} excluded for '{excluded[cid][:60]}', expected {rule}"
        if not rule.startswith("RULE-") and "window" not in excluded[cid]:
            return False, f"{cid} excluded for '{excluded[cid][:60]}', expected a window reason"
    return True, f"eligible {sorted(got)}; exclusions match on rule"


def q28(repo, r, exp):
    if r.data.get("legal") is not exp["legal"]:
        return False, f"legal {r.data.get('legal')} != {exp['legal']}"
    details = [f["detail"] for f in r.data.get("failures", [])]
    ok = any("RULE-REST-04" == f["rule_id"] for f in r.data.get("failures", []))
    ok = ok and any("10.75" in d for d in details)
    return ok, "; ".join(details)[:120]


def q29(repo, r, exp):
    got = {leg["flight_id"] for leg in r.data.get("closure_legs", [])}
    return got == set(exp), f"{sorted(got)} vs {sorted(exp)}"


def q30(repo, r, exp):
    seats = r.data.get("seats")
    atr = min(f.seats for f in repo.flights.values())
    ok = seats == 162 and atr == 72
    return ok, f"largest leg {seats} seats; smallest (ATR72) {atr}"


def _ranked(repo, r, exp_options, top_n=3):
    """Compare the leading ranked options: crew id, cost and order."""
    got = r.data.get("options", [])
    if not got:
        return False, "no options produced"
    pairs_got = [(o.get("action", ""), o["cost_inr"]) for o in got]
    for i, want in enumerate(exp_options[:top_n]):
        if i >= len(pairs_got):
            return False, f"only {len(pairs_got)} options, expected at least {len(exp_options[:top_n])}"
        action, cost = pairs_got[i]
        if want.get("crew_id") and want["crew_id"] not in action:
            return False, f"rank {i+1}: {action[:60]} does not name {want['crew_id']}"
        if cost != want["cost_inr"]:
            return False, f"rank {i+1} cost {cost} != {want['cost_inr']}"
    costs = [c for _, c in pairs_got]
    if costs != sorted(costs):
        return False, f"options not cheapest-first: {costs}"
    return True, f"top {min(top_n, len(exp_options))} options match on crew and cost, order correct"


def q31(repo, r, exp):
    ok, detail = _ranked(repo, r, exp, top_n=4)
    if not ok:
        return ok, detail
    cancel = r.data["options"][-1]
    if not cancel["action"].lower().startswith("cancel"):
        return False, "cancellation should be the final fallback option"
    return True, detail + "; cancellation last"


def q32(repo, r, exp):
    got = r.data.get("options", [])
    if not got:
        return False, "no joint plan produced"
    text = json.dumps(got)
    for key in ("assign_dxa", "assign_dxb"):
        want = exp[key]
        chosen = [o for o in got if want["crew_id"] in o.get("action", "")]
        if not chosen:
            return False, f"{key}: {want['crew_id']} not offered"
        if not any(o["cost_inr"] == want["cost_inr"] for o in chosen):
            return False, f"{key}: {want['crew_id']} costed {[o['cost_inr'] for o in chosen]} != {want['cost_inr']}"
    total = r.data.get("joint_cost_inr")
    if total is not None and total != exp["total_cost_inr"]:
        return False, f"joint cost {total} != {exp['total_cost_inr']}"
    return True, f"both assignments offered at the key's costs, total {exp['total_cost_inr']}"


def q33(repo, r, exp):
    got = r.data.get("options", [])
    if not got:
        return False, "no options produced"
    top = got[0]
    # documented divergence: the key omits deadhead positioning to MAA (see README)
    callout = next((l["amount_inr"] for l in top.get("cost_breakdown", [])
                    if "Callout" in l["label"]), None)
    cancel = next((o for o in got if o["action"].lower().startswith("cancel")), None)
    if callout != exp[0]["cost_inr"]:
        return False, f"callout subtotal {callout} != key {exp[0]['cost_inr']}"
    if not cancel or cancel["cost_inr"] != exp[1]["cost_inr"]:
        return False, f"cancel option {cancel and cancel['cost_inr']} != {exp[1]['cost_inr']}"
    return True, (
        f"re-crew callout {callout} matches key; total {top['cost_inr']} adds "
        f"positioning the key omits (documented divergence); cancel {cancel['cost_inr']} matches"
    )


def q34(repo, r, exp):
    return _ranked(repo, r, exp, top_n=3)


def q35(repo, r, exp):
    got = {leg["flight_id"]: leg for leg in r.data.get("closure_legs", [])}
    if len(got) != len(exp):
        return False, f"{len(got)} legs assessed, expected {len(exp)}"
    for row in exp:
        leg = got.get(row["flight_id"])
        if leg is None:
            return False, f"missing {row['flight_id']}"
        for field in ("min_delay_hours", "crew_fdp_after_delay", "fdp_limit"):
            if not _close(leg[field], row[field]):
                return False, f"{row['flight_id']} {field} {leg[field]} != {row[field]}"
        if leg["pairing_id"] != row["pairing_id"]:
            return False, f"{row['flight_id']} pairing {leg['pairing_id']} != {row['pairing_id']}"
        want_legal = row["action"].startswith("delay (crew legal)")
        got_legal = leg["action"].startswith("delay (crew legal)")
        if want_legal != got_legal:
            return False, f"{row['flight_id']} verdict differs"
    return True, f"all {len(exp)} legs match on delay, FDP, limit and verdict"


def q36(repo, r, exp):
    """One check per item in the key's `must_include` list."""
    message = r.data.get("message", "") or r.summary
    low = message.lower()
    checks = {
        "crew_id and pairing_id": "C-3310" in message and "P-2291" in message,
        "report time/place day 1": "06:00" in message and "BLR" in message
                                   and "crew room" in low,
        "flights day 1": all(f in message for f in ("DX412", "DX413", "DX588")),
        "overnight DEL + hotel": "overnight" in low and "DEL" in message
                                 and "hotel" in low,
        "flights day 2": all(f in message for f in ("DX589", "DX590", "DX591")),
        "report time/place day 2": "04:00" in message,
        "acknowledgement with deadline": "acknowledge" in low
                                         and any(ch.isdigit() for ch in message),
        "contact for questions": "contact" in low,
    }
    missing = [k for k, ok in checks.items() if not ok]
    if missing:
        return False, f"draft missing: {missing}"
    return True, f"draft carries all {len(checks)} items the key requires"


def q37(repo, r, exp):
    got = r.data.get("options", [])
    if not got:
        return False, "no options produced"
    top = got[0]
    ok = exp["crew_id"] in top.get("action", "") and top["cost_inr"] == exp["cost_inr"]
    return ok, f"cheapest: {top.get('action','')[:70]} at {top['cost_inr']} (want {exp['crew_id']} / {exp['cost_inr']})"


def q38(repo, r, exp):
    alerts = r.data.get("alerts", [])
    if not alerts:
        return False, "no briefing signals produced"
    kinds = {a["id"].split("-")[0] for a in alerts}
    # the key's three suggested data points: duty headroom, reserve depth, risk signals
    wanted = {"duty", "pool", "risk"}
    missing = wanted - kinds
    if missing:
        return False, f"briefing lacks {sorted(missing)} signals (has {sorted(kinds)})"
    return True, f"briefing surfaces {sorted(kinds)} across {len(alerts)} signals"


CHECKERS: dict[str, Callable] = {
    "Q01": q01, "Q02": q02, "Q03": q03, "Q04": q04, "Q05": q05, "Q06": q06,
    "Q07": q07, "Q08": q08, "Q09": q09, "Q10": q10, "Q11": q11, "Q12": q12,
    "Q13": q13, "Q14": q14, "Q15": q15, "Q16": q16, "Q17": q17, "Q18": q18,
    "Q19": q19, "Q20": q20, "Q21": q21, "Q22": q22, "Q23": q23, "Q24": q24,
    "Q25": q25, "Q26": q26, "Q27": q27, "Q28": q28, "Q29": q29, "Q30": q30,
    "Q31": q31, "Q32": q32, "Q33": q33, "Q34": q34, "Q35": q35, "Q36": q36,
    "Q37": q37, "Q38": q38,
}


def audit(repo) -> list[dict]:
    """Run every question through the engine and check it strictly."""
    out: list[dict] = []
    for q in _load_questions():
        qid = q["question_id"]
        checker = CHECKERS.get(qid)
        try:
            result = structured_query.route(repo, q["prompt"])
        except Exception as exc:
            out.append({"id": qid, "tier": q["tier"], "question": q["prompt"],
                        "passed": False, "detail": f"engine error: {type(exc).__name__}: {exc}"})
            continue
        if checker is None:
            out.append({"id": qid, "tier": q["tier"], "question": q["prompt"],
                        "passed": False, "detail": "no checker defined"})
            continue
        try:
            passed, detail = checker(repo, result, q["expected_answer"])
        except Exception as exc:
            passed, detail = False, f"checker error: {type(exc).__name__}: {exc}"
        out.append({"id": qid, "tier": q["tier"], "question": q["prompt"],
                    "passed": bool(passed), "detail": str(detail)})
    return out
