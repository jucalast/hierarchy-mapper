import type { ChatPayload, ChatResponse } from '@/types';
import { api } from './client';
import { API_V1_URL, TIMEOUTS } from '../config';

/** Chat padrão (sem stream). Para stream do agent_workflow, use getChatStreamUrl. */
export function chat(payload: ChatPayload) {
  return api.post<ChatResponse>('/ai/chat', payload, { timeout: TIMEOUTS.long });
}

/** URL do endpoint de streaming (NDJSON). Consumir via `useJobStream` ou fetch manual. */
export function getChatStreamUrl(): string {
  return `${API_V1_URL}/ai/chat`;
}

export interface AgentActionPayload {
  action_id: string;
  approved: boolean;
  thread_id?: string | null;
}

export function agentAction(payload: AgentActionPayload) {
  return api.post<Record<string, unknown>>('/ai/agent-action', payload);
}

export interface PreferenceResponse {
  status: string;
  preferred_model: string;
  strict_mode: boolean;
}

export function updatePreference(model: string, strictMode: boolean = false) {
  return api.post<PreferenceResponse>('/ai/preference', { model, strict_mode: strictMode });
}

export function getPreference() {
  return api.get<{ preferred_model: string; strict_mode: boolean }>('/ai/preference');
}
