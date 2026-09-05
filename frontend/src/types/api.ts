// Response envelope contract shared with the FastAPI backend.
// Field names are fixed by the backend — do not rename.

export type Confidence = 'high' | 'review' | 'cannot_answer';

export interface RuleCheck {
  rule_id: string;
  status: 'PASS' | 'FAIL' | 'NOT_APPLICABLE';
  actual: number | string | null;
  limit: number | string | null;
  margin: number | null;
  detail: string;
}

export interface ChainStep {
  step: number;
  action: string;
  crew_id: string;
  pairing_id: string | null;
  flight_ids: string[];
  rule_checks: RuleCheck[];
}

export interface RecoveryOption {
  rank: number;
  action: string;
  legal: boolean;
  rules_checked: string[];
  rule_checks: RuleCheck[];
  cost_inr: number;
  cost_breakdown: {label: string;amount_inr: number;}[];
  coverage: string;
  covered_flight_ids: string[];
  uncovered_flight_ids: string[];
  delay_minutes: number;
  resilience_score: number;
  resilience_note: string;
  chain: ChainStep[];
  reasoning: string;
}

export interface Relaxation {
  rule_id: string;
  breach_detail: string;
  breach_magnitude: string;
  remedy: string;
  resulting_option_rank: number | null;
}

export interface ImpactReport {
  trigger: string;
  uncrewed_flights: string[];
  /** Legs losing crew on the disruption date itself. Drives the passenger count. */
  immediate_flights?: string[];
  /** Later legs of the same pairing: equally uncovered, further out. */
  at_risk_flights?: string[];
  pairing_broken: string[];
  downstream_risks: {crew_id: string;rule: string;detail: string;}[];
  passengers_affected: number;
  graph: {
    nodes: {
      id: string;
      label: string;
      type: 'crew' | 'pairing' | 'flight';
      status: 'ok' | 'at_risk' | 'broken';
    }[];
    edges: {from: string;to: string;}[];
  };
}

export interface Alert {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  subject: string;
  subject_type: 'crew' | 'flight' | 'station' | 'pool';
  message: string;
  date: string;
}

/** A crew message the engine drafted. Never sent -- the dataset has no contact
 *  details, and delivery is an airline-system integration, not this system's job. */
export interface NotificationDraft {
  crew_id: string;
  pairing_id: string;
  message: string;
  acknowledge_within_minutes: number;
  legal: boolean;
  delivered: boolean;
}

export interface EvidenceItem {
  source: string;
  fact: string;
  value: string;
}

export interface AdvisorResponse {
  query: string;
  intent: string;
  tier: 1 | 2 | 3;
  answer_text: string;
  confidence: Confidence;
  grounding: {verified: boolean;unverified_claims: string[];};
  table?: {columns: string[];rows: (string | number)[][];};
  impact?: ImpactReport;
  options?: RecoveryOption[];
  relaxations?: Relaxation[];
  alerts?: Alert[];
  before_after?: {field: string;before: string;after: string;delta: string;legal: boolean;}[];
  notification?: NotificationDraft;
  evidence: EvidenceItem[];
  timing_ms: number;
}

export interface McpTool {
  name: string;
  tier: number;
  description: string;
}

/** How to reach this engine over MCP. Served by the backend so the paths are the
 *  real ones for the machine it is running on. */
export interface McpInfo {
  server_name: string;
  transport: string;
  command: string;
  args: string[];
  config_json: string;
  config_path: {windows: string;macos: string;};
  tools: McpTool[];
}

export interface ScorecardResponse {
  generated_at: string;
  total_ms: number;
  tiers: {tier: number;passed: number;total: number;}[];
  scenarios: {passed: number;total: number;};
  cases: {id: string;tier: number;question: string;passed: boolean;detail: string;}[];
}

// ---- Request bodies ----
// TODO: shapes are the minimum the console sends; confirm against backend schemas.py.

export interface ImpactRequest {
  crew_id?: string;
  flight_id?: string;
  pairing_id?: string;
  date?: string;
  session_id?: string;
}

export interface SimulateRequest {
  question?: string;
  crew_id?: string;
  flight_id?: string;
  pairing_id?: string;
  date?: string;
  session_id?: string;
}

export interface RecommendRequest {
  crew_id?: string;
  pairing_id?: string;
  flight_ids?: string[];
  date?: string;
  session_id?: string;
}