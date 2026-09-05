"""Shared vocabulary for the legality engine.

Every rule returns a RuleResult. `margin` is signed headroom in the rule's own unit
(negative = size of the breach) and is what the relaxation engine inverts to answer
"what would make this legal?".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from app.domain.models import DutyBlock, PairingDay
from app.domain.time_utils import hours_between

Status = Literal["PASS", "FAIL", "NOT_APPLICABLE"]


@dataclass
class RuleResult:
    rule_id: str
    status: Status
    actual: float | str | None
    limit: float | str | None
    margin: float | None
    detail: str

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "status": self.status,
            "actual": self.actual,
            "limit": self.limit,
            "margin": self.margin,
            "detail": self.detail,
        }


@dataclass
class CoverRequest:
    """A proposal: put `crew_id` on `days`, optionally vacating `exclude_pairing`.

    Two different kinds of time change, and conflating them is a real modelling error:

      `delay_hours`  SHIFTS the whole duty later -- deadhead positioning, where the crew
                     reports late and finishes late. Duty length is unchanged.
      `extend_hours` EXTENDS the duty -- an operational delay, where the crew has already
                     reported and now finishes later. Duty length grows, which is exactly
                     what puts an FDP limit at risk.
    """
    crew_id: str
    days: list[PairingDay]
    exclude_pairing: str | None = None
    delay_hours: float = 0.0
    extend_hours: float = 0.0

    def shifted(self, day: PairingDay) -> tuple[datetime, datetime]:
        shift = timedelta(hours=self.delay_hours)
        stretch = timedelta(hours=self.delay_hours + self.extend_hours)
        return day.report_utc + shift, day.release_utc + stretch

    def duty_hours(self, day: PairingDay) -> float:
        report, release = self.shifted(day)
        return hours_between(report, release)


@dataclass
class Verdict:
    """Outcome of evaluating one CoverRequest against the full ruleset."""
    crew_id: str
    legal: bool
    results: list[RuleResult] = field(default_factory=list)

    @property
    def failures(self) -> list[RuleResult]:
        return [r for r in self.results if r.failed]

    @property
    def rules_checked(self) -> list[str]:
        seen: list[str] = []
        for r in self.results:
            if r.rule_id not in seen:
                seen.append(r.rule_id)
        return seen

    def margins(self) -> dict[str, float]:
        """Tightest signed margin per rule -- the binding constraint for each."""
        out: dict[str, float] = {}
        for r in self.results:
            if r.margin is None:
                continue
            if r.rule_id not in out or r.margin < out[r.rule_id]:
                out[r.rule_id] = r.margin
        return out

    def reason(self) -> str:
        """Why this was rejected, each clause tagged with the rule that rejected it.

        The rule id belongs in the sentence, not just in a sibling field: this string is
        what a controller reads in the exclusion list and what the answer keys phrase as
        "RULE-QUAL-05: no ATR72 rating".
        """
        return "; ".join(
            f"{r.rule_id}: {r.detail}" for r in self.failures
        ) or "all rules satisfied"


def build_timeline(
    existing: list[DutyBlock], request: CoverRequest, flight_hours: dict[str, float]
) -> list[DutyBlock]:
    """Existing roster (minus any vacated pairing) plus the proposed duty, in time order.

    The proposed blocks carry pairing_id "COVER" so downstream rules can tell which
    side of a rest conflict is the new assignment.
    """
    timeline = [b for b in existing if b.pairing_id != request.exclude_pairing]
    for day in request.days:
        report, release = request.shifted(day)
        timeline.append(
            DutyBlock(
                date=day.date,
                report_utc=report,
                release_utc=release,
                duty_hours=hours_between(report, release),
                flight_hours=flight_hours.get(day.pairing_id + str(day.day_index), 0.0),
                pairing_id="COVER",
            )
        )
    timeline.sort(key=lambda b: b.report_utc)
    return timeline
