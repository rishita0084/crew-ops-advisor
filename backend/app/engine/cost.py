"""Cost model. Every rupee shown to a controller is itemised here, never estimated.

Rates come from costs.json via the repository, so a rate change is a data change.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.positioning import Positioning


@dataclass
class CostBreakdown:
    lines: list[dict] = field(default_factory=list)

    def add(self, label: str, amount: float) -> None:
        if amount:
            self.lines.append({"label": label, "amount_inr": int(round(amount))})

    @property
    def total(self) -> int:
        return int(sum(line["amount_inr"] for line in self.lines))

    def to_list(self) -> list[dict]:
        return list(self.lines)


def callout_cost(repo, crew_id: str) -> tuple[float, str]:
    """Reserve callout if they are on the reserve roster, otherwise a day-off callout."""
    crew = repo.crew[crew_id]
    pilot = crew.is_pilot
    if repo.is_reserve(crew_id):
        key = "reserve_callout_pilot" if pilot else "reserve_callout_cabin"
        return repo.cost(key), "reserve callout"
    key = "dayoff_callout_pilot" if pilot else "dayoff_callout_cabin"
    return repo.cost(key), "day-off callout"


def assignment_cost(repo, crew_id: str, positioning: Positioning) -> tuple[CostBreakdown, str]:
    """Full cost of putting `crew_id` on a pairing, including any positioning."""
    breakdown = CostBreakdown()
    amount, label = callout_cost(repo, crew_id)
    breakdown.add(label.capitalize(), amount)

    if positioning.required and positioning.feasible:
        crew = repo.crew[crew_id]
        breakdown.add(f"Deadhead positioning from {crew.base}", repo.cost("deadhead_positioning"))
        if positioning.delay_hours > 0:
            breakdown.add(
                f"Delay cost ({positioning.delay_hours}h x "
                f"{int(repo.cost('delay_cost_per_duty_hour')):,}/h)",
                positioning.delay_hours * repo.cost("delay_cost_per_duty_hour"),
            )
        label += f" + deadhead from {crew.base}"
        if positioning.delay_hours > 0:
            label += f" (first departure delayed ~{positioning.delay_hours}h)"

    return breakdown, label


def cancellation_cost(repo, flight_count: int) -> CostBreakdown:
    breakdown = CostBreakdown()
    breakdown.add(
        f"Cancellation ({flight_count} legs x {int(repo.cost('cancellation_per_flight')):,})",
        flight_count * repo.cost("cancellation_per_flight"),
    )
    return breakdown
