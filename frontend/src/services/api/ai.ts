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

/** URL do endpoint de streaming do agente V2. */
export function getV2ChatStreamUrl(): string {
  return `${API_V1_URL}/ai/v2/chat`;
}

/** URL do endpoint de confirmação de ação do agente V2. */
export function getV2ConfirmStreamUrl(): string {
  return `${API_V1_URL}/ai/v2/confirm`;
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

export function getQuotas() {
  return api.get<Record<string, Record<string, {
    limit: number;
    remaining: number;
    used: number;
    pct: number;
    tokens_limit?: number;
    tokens_remaining?: number;
    tokens_pct?: number;
    status: string;
    updated_at: number;
  }>>>('/ai/quotas');
}

