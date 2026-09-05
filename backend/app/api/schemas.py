"""Pydantic mirrors of frontend/src/types/api.ts.

The frontend was built first, so its types are the contract and this file conforms to
them field for field. Do not rename anything here without changing the UI.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "review", "cannot_answer"]


class RuleCheck(BaseModel):
    rule_id: str
    status: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    actual: float | str | None = None
    limit: float | str | None = None
    margin: float | None = None
    detail: str


class ChainStep(BaseModel):
    step: int
    action: str
    crew_id: str
    pairing_id: str | None = None
    flight_ids: list[str] = Field(default_factory=list)
    rule_checks: list[RuleCheck] = Field(default_factory=list)


class CostLine(BaseModel):
    label: str
    amount_inr: int


class RecoveryOption(BaseModel):
    rank: int
    action: str
    legal: bool
    rules_checked: list[str] = Field(default_factory=list)
    rule_checks: list[RuleCheck] = Field(default_factory=list)
    cost_inr: int
    cost_breakdown: list[CostLine] = Field(default_factory=list)
    coverage: str
    covered_flight_ids: list[str] = Field(default_factory=list)
    uncovered_flight_ids: list[str] = Field(default_factory=list)
    delay_minutes: int = 0
    resilience_score: float = 1.0
    resilience_note: str = ""
    chain: list[ChainStep] = Field(default_factory=list)
    reasoning: str = ""


class Relaxation(BaseModel):
    rule_id: str
    breach_detail: str
    breach_magnitude: str
    remedy: str
    resulting_option_rank: int | None = None


class GraphNode(BaseModel):
    id: str
    label: str
    type: Literal["crew", "pairing", "flight"]
    status: Literal["ok", "at_risk", "broken"]


class GraphEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str

    model_config = {"populate_by_name": True}


class ImpactGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class DownstreamRisk(BaseModel):
    crew_id: str
    rule: str
    detail: str


class ImpactReport(BaseModel):
    trigger: str
    uncrewed_flights: list[str] = Field(default_factory=list)
    pairing_broken: list[str] = Field(default_factory=list)
    downstream_risks: list[DownstreamRisk] = Field(default_factory=list)
    passengers_affected: int = 0
    graph: ImpactGraph = Field(default_factory=ImpactGraph)


class Alert(BaseModel):
    id: str
    severity: Literal["info", "warning", "critical"]
    subject: str
    subject_type: Literal["crew", "flight", "station", "pool"]
    message: str
    date: str


class NotificationDraft(BaseModel):
    crew_id: str
    pairing_id: str
    message: str
    acknowledge_within_minutes: int = 0
    legal: bool = False
    delivered: bool = False


class EvidenceItem(BaseModel):
    source: str
    fact: str
    value: str


class Grounding(BaseModel):
    verified: bool
    unverified_claims: list[str] = Field(default_factory=list)


class ResultTable(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class BeforeAfter(BaseModel):
    field: str
    before: str
    after: str
    delta: str
    legal: bool


class AdvisorResponse(BaseModel):
    query: str
    intent: str
    tier: int
    answer_text: str
    confidence: Confidence
    grounding: Grounding
    table: ResultTable | None = None
    impact: ImpactReport | None = None
    options: list[RecoveryOption] | None = None
    relaxations: list[Relaxation] | None = None
    alerts: list[Alert] | None = None
    before_after: list[BeforeAfter] | None = None
    notification: NotificationDraft | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    timing_ms: int = 0


class ScorecardTier(BaseModel):
    tier: int
    passed: int
    total: int


class ScorecardScenarios(BaseModel):
    passed: int
    total: int


class ScorecardCase(BaseModel):
    id: str
    tier: int
    question: str
    passed: bool
    detail: str


class ScorecardResponse(BaseModel):
    generated_at: str
    total_ms: int
    tiers: list[ScorecardTier]
    scenarios: ScorecardScenarios
    cases: list[ScorecardCase]


# ---- request bodies ----

class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None


class ImpactRequest(BaseModel):
    crew_id: str | None = None
    flight_id: str | None = None
    pairing_id: str | None = None
    date: str | None = None
    session_id: str | None = None


class SimulateRequest(BaseModel):
    question: str | None = None
    crew_id: str | None = None
    flight_id: str | None = None
    pairing_id: str | None = None
    date: str | None = None
    session_id: str | None = None


class RecommendRequest(BaseModel):
    crew_id: str | None = None
    pairing_id: str | None = None
    flight_ids: list[str] | None = None
    date: str | None = None
    session_id: str | None = None
