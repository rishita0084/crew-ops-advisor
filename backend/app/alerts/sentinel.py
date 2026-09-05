"""Proactive alerts: what a controller should worry about before it happens.

risk_signals.json is a PROVIDED input, treated like a weather forecast. This system
builds no prediction model. What it does is the controller's half of the job: combine
that forecast with hard operational facts -- duty headroom, certification expiry,
reserve depth, single-cover pairings -- and say which of them deserves attention.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.config import SNAPSHOT_UTC
from app.engine.candidates import build_candidate
from app.explain.ledger import EvidenceLedger
from app.rules.r02_duty_7d import accrued_duty
from app.services.lookups import ToolResult

SNAPSHOT_DATE = SNAPSHOT_UTC.date()

DUTY_WARN_RATIO = 0.85          # flag crew inside 15% of the 7-day duty ceiling
CERT_WARN_DAYS = 14
RISK_WARN_SCORE = 0.70


def _alert(aid: str, severity: str, subject: str, subject_type: str,
           message: str, day: date) -> dict:
    return {
        "id": aid, "severity": severity, "subject": subject,
        "subject_type": subject_type, "message": message, "date": day.isoformat(),
    }


def build_alerts(repo, on: date | None = None) -> ToolResult:
    on = on or (SNAPSHOT_DATE + timedelta(days=1))
    led = EvidenceLedger()
    alerts: list[dict] = []

    duty_limit = float(repo.rule_param("RULE-DUTY-02", "max_duty_hours", 60))
    window = int(repo.rule_param("RULE-DUTY-02", "window_days", 7))
    threshold = duty_limit * DUTY_WARN_RATIO

    # the limit and the window are quoted in the alert text, so they belong in the
    # evidence -- otherwise the verifier flags a correct citation as ungrounded
    led.add("RULE-DUTY-02", "max duty hours", duty_limit)
    led.add("RULE-DUTY-02", "window days", window)
    led.add("RULE-CERT-06", "alert horizon days", CERT_WARN_DAYS)

    # ---- 1. crew approaching the duty ceiling ----
    tight: list[tuple[str, float]] = []
    for cid in sorted(repo.crew):
        if repo.crew[cid].status != "active":
            continue
        total = accrued_duty(repo, cid, on, window)
        if total >= threshold:
            tight.append((cid, total))
    for cid, total in sorted(tight, key=lambda x: -x[1])[:6]:
        headroom = round(duty_limit - total, 2)
        crew = repo.crew[cid]
        alerts.append(_alert(
            f"duty-{cid}", "critical" if headroom < 3 else "warning", cid, "crew",
            f"{crew.rank} {cid} ({crew.base}) is at {total}h of the {duty_limit:g}h "
            f"{window}-day duty limit - {headroom}h headroom left.",
            on,
        ))
        led.add("duty_clocks.json", f"{cid} duty hours to {on}", total)
        led.add("RULE-DUTY-02", f"{cid} headroom", headroom)

    # ---- 2. certifications lapsing inside the horizon ----
    horizon = on + timedelta(days=CERT_WARN_DAYS)
    for cid in sorted(repo.certifications):
        if repo.crew[cid].status != "active":
            continue
        for cert in repo.certifications[cid]:
            if on <= cert.valid_to <= horizon:
                days_left = (cert.valid_to - on).days
                rostered = any(
                    block.date > cert.valid_to for block in repo.roster.get(cid, [])
                )
                alerts.append(_alert(
                    f"cert-{cid}-{cert.cert_type}",
                    "critical" if rostered else "warning",
                    cid, "crew",
                    f"{repo.crew[cid].rank} {cid} - {cert.cert_type} expires "
                    f"{cert.valid_to} ({days_left} days)"
                    + (" and they are rostered beyond that date." if rostered
                       else " - no duty rostered past expiry."),
                    on,
                ))
                led.add("certifications.json", f"{cid} {cert.cert_type} expires", cert.valid_to)

    # ---- 3. reserve depth by base ----
    iso = on.isoformat()
    depth: dict[tuple[str, str], int] = {}
    for cid, reserve in repo.reserves.items():
        if iso in reserve.dates:
            key = (reserve.base, repo.crew[cid].rank)
            depth[key] = depth.get(key, 0) + 1
    for (base, rank), count in sorted(depth.items()):
        if count <= 1:
            alerts.append(_alert(
                f"pool-{base}-{rank}", "warning", f"{base} {rank}", "pool",
                f"Only {count} {rank.lower()} reserve on call at {base} on {on}.", on,
            ))
            led.add("reserve_pool.json", f"{base} {rank} reserves on {on}", count)
    if not depth:
        alerts.append(_alert(
            f"pool-none-{iso}", "critical", "reserve pool", "pool",
            f"No reserve crew are on call anywhere on {on}.", on,
        ))

    # ---- 4. pairings with only one legal cover at Captain ----
    thin = _single_cover_pairings(repo, on)
    for pairing_id, count, rank in thin[:4]:
        alerts.append(_alert(
            f"thin-{pairing_id}-{rank}", "warning" if count == 1 else "critical",
            pairing_id, "flight",
            f"{pairing_id} on {on} has {count} legal {rank.lower()} substitute"
            f"{'' if count == 1 else 's'} available if the rostered crew drops out.",
            on,
        ))
        led.add("computed", f"{pairing_id} legal {rank} substitutes", count)

    # ---- 5. provided risk signals on crew actually flying that day ----
    flying = {
        cid for pairing in repo.pairings.values()
        for cid in pairing.crew
        if any(d.date == on for d in pairing.days)
    }
    risky = sorted(
        (repo.risk[cid] for cid in flying if cid in repo.risk and repo.risk[cid].score >= RISK_WARN_SCORE),
        key=lambda r: -r.score,
    )[:4]
    for signal in risky:
        crew = repo.crew[signal.crew_id]
        alerts.append(_alert(
            f"risk-{signal.crew_id}", "info", signal.crew_id, "crew",
            f"{crew.rank} {signal.crew_id} carries a provided disruption-risk score of "
            f"{signal.score}: {'; '.join(signal.drivers)}.",
            on,
        ))
        led.add("risk_signals.json", f"{signal.crew_id} score", signal.score)

    order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (order[a["severity"]], a["id"]))

    counts = {s: sum(1 for a in alerts if a["severity"] == s) for s in order}
    summary = (
        f"{len(alerts)} operational signals for {on}: {counts['critical']} critical, "
        f"{counts['warning']} warning, {counts['info']} informational."
        if alerts else f"Nothing flagged for {on}."
    )

    return ToolResult(
        summary=summary,
        data={"alerts": alerts, "date": on.isoformat(), "counts": counts},
        ledger=led,
        tier=2,
    )


def _single_cover_pairings(repo, on: date) -> list[tuple[str, int, str]]:
    """Pairings where at most one substitute is legal -- the operation's thin spots."""
    out: list[tuple[str, int, str]] = []
    for pairing in repo.pairings.values():
        days = [d for d in pairing.days if d.date == on]
        if not days:
            continue
        for rank in ("Captain", "First Officer"):
            incumbent = next((c for c, r in pairing.crew.items() if r == rank), None)
            covers = 0
            for crew in repo.crew_by_rank(rank, active_only=True):
                if crew.crew_id == incumbent:
                    continue
                if build_candidate(repo, crew.crew_id, days).legal:
                    covers += 1
                    if covers > 1:
                        break
            if covers <= 1:
                out.append((pairing.pairing_id, covers, rank))
    out.sort(key=lambda x: (x[1], x[0]))
    return out
