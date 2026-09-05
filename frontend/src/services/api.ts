// The only module components and hooks talk to.
// Switching from mocks to the live backend is an env change, never a component change.

import { USE_MOCKS, delay, get, post } from './client';
import type {
  AdvisorResponse,
  ImpactRequest,
  RecommendRequest,
  McpInfo,
  ScorecardResponse,
  SimulateRequest } from
'../types/api';
import { resolveMockChat, mockSimulateResponse } from '../mocks/chat';
import { mockImpactResponse } from '../mocks/impact';
import { mockRecommendResponse } from '../mocks/recommend';
import { mockAlertsResponse } from '../mocks/alerts';
import { mockScorecard } from '../mocks/scorecard';
import { mockMcpInfo } from '../mocks/mcp';

export function askAdvisor(question: string, sessionId?: string): Promise<AdvisorResponse> {
  if (USE_MOCKS) return delay(resolveMockChat(question));
  return post<AdvisorResponse>('/api/chat', { question, session_id: sessionId });
}

export function getImpact(body: ImpactRequest): Promise<AdvisorResponse> {
  if (USE_MOCKS) return delay(mockImpactResponse);
  return post<AdvisorResponse>('/api/impact', body);
}

export function simulate(body: SimulateRequest): Promise<AdvisorResponse> {
  if (USE_MOCKS) {
    return delay({ ...mockSimulateResponse, query: body.question || mockSimulateResponse.query });
  }
  return post<AdvisorResponse>('/api/simulate', body);
}

export function recommend(body: RecommendRequest): Promise<AdvisorResponse> {
  if (USE_MOCKS) return delay(mockRecommendResponse);
  return post<AdvisorResponse>('/api/recommend', body);
}

export function getAlerts(date?: string): Promise<AdvisorResponse> {
  if (USE_MOCKS) return delay(mockAlertsResponse, 320);
  return get<AdvisorResponse>('/api/alerts', { date });
}

export function getMcpInfo(): Promise<McpInfo> {
  if (USE_MOCKS) return delay(mockMcpInfo, 200);
  return get<McpInfo>('/api/mcp');
}

export function getScorecard(): Promise<ScorecardResponse> {
  if (USE_MOCKS) return delay(mockScorecard, 420);
  return get<ScorecardResponse>('/api/scorecard');
}