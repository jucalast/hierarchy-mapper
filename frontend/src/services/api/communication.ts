import { api } from './client';
import { TIMEOUTS } from '../config';

/** Endpoints sob /api/v1/communication */

export interface SendEmailPayload {
  to_email: string;
  subject: string;
  body: string;
  org_id?: number;
}

export function sendEmail(payload: SendEmailPayload) {
  return api.post<Record<string, unknown>>('/communication/send', payload, {
    timeout: TIMEOUTS.long,
  });
}

export function sendWhatsApp(payload: { number: string; message: string }) {
  return api.post<Record<string, unknown>>('/communication/whatsapp/send', payload);
}

export function getMetrics() {
  return api.get<{ data?: Array<Record<string, unknown>> }>('/communication/metrics');
}

/** Stats de cache de email (o serviço dedicado em 8002 vira proxy no backend). */
export function getEmailCacheStatus() {
  return api.get<{ is_syncing?: boolean; count?: number }>('/communication/email/cache-status');
}

/** Busca universal (empresas, contatos, whatsapp, emails, leads). */
export interface UniversalSearchResult {
  id?: string | number;
  name?: string;
  type?: string;
  [k: string]: unknown;
}

export function universalSearch(query: string, type?: string) {
  const qs = new URLSearchParams();
  qs.append('q', query);
  if (type) qs.append('type', type);
  return api.get<{ results?: UniversalSearchResult[] }>(`/search/universal?${qs.toString()}`);
}

/**
 * WhatsApp direto (serviço dedicado em port 8001).
 * Fica isolado aqui para facilitar retirar quando consolidar no backend principal.
 */
const WHATSAPP_BASE = process.env.NEXT_PUBLIC_WHATSAPP_URL || 'http://localhost:8001';

export async function fetchWhatsAppHistory(chatId: string, limit = 100) {
  const resp = await fetch(`${WHATSAPP_BASE}/api/whatsapp/chats/${chatId}/messages?limit=${limit}`);
  if (!resp.ok) throw new Error(`WhatsApp history ${resp.status}`);
  return (await resp.json()) as {
    messages?: Array<{ id: string; body: string; fromMe: boolean; timestamp: number }>;
  };
}

export async function sendWhatsAppDirect(number: string, message: string) {
  const resp = await fetch(`${WHATSAPP_BASE}/api/whatsapp/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ number, message }),
  });
  if (!resp.ok) throw new Error(`WhatsApp send ${resp.status}`);
  return resp.json();
}

// ── Cache de Mensagens ─────────────────────────────────────────────────────────

export interface TrackedContact {
  contact_identifier: string;
  contact_name: string;
  channel: 'whatsapp' | 'email';
  org_name?: string;
  org_id?: number;
  message_count: number;
  fetched_at?: string;
  last_message_preview?: string;
  chat_id?: string;
  has_unread?: boolean;
  is_key_contact?: boolean;
  profile_pic?: string;
  org_logo?: string;
  org_domain?: string;
}

export interface WaMessage {
  body: string;
  fromMe: boolean;
  timestamp: number;
  id?: string;
}

export interface EmailMessage {
  from: string;
  to: string;
  subject: string;
  date: string;
  preview: string;
  body?: string;
  entryId: string;
  direction: 'sent' | 'received';
}

export interface CachedConversation {
  contact_identifier: string;
  contact_name: string;
  channel: 'whatsapp' | 'email';
  org_name?: string;
  chat_id?: string;
  messages: WaMessage[] | EmailMessage[];
  message_count: number;
  fetched_at?: string;
}

export function fetchTrackedContacts(channel?: 'whatsapp' | 'email', orgId?: number | null) {
  const params = new URLSearchParams();
  if (channel) params.append('channel', channel);
  if (orgId != null) params.append('org_id', String(orgId));
  const qs = params.toString() ? `?${params.toString()}` : '';
  return api.get<{ contacts: TrackedContact[]; total: number; unread_count: number }>(`/messages/contacts${qs}`);
}

export function fetchCachedConversation(contactIdentifier: string, channel: string) {
  return api.get<CachedConversation>(
    `/messages/conversation?contact_identifier=${encodeURIComponent(contactIdentifier)}&channel=${channel}`
  );
}

export function syncContact(contactIdentifier: string) {
  return api.post<{ ok: boolean; synced: number; contact: string }>(
    `/messages/sync/${encodeURIComponent(contactIdentifier)}?channel=whatsapp`,
    {}
  );
}

export function markConversationRead(contactIdentifier: string, channel: string) {
  return api.patch<{ ok: boolean }>(
    `/messages/read?contact_identifier=${encodeURIComponent(contactIdentifier)}&channel=${channel}`,
    {}
  );
}

export interface SavedCallSession {
  id: string;
  pipedrive_activity_id?: string;
  org_id?: number;
  org_logo?: string;
  org_domain?: string;
  contact_name: string;
  phone: string;
  profile_pic?: string;
  flight_plan?: any;
  latest_insight?: any;
  message_count: number;
  created_at?: string;
}

export function fetchCallHistory(orgId?: number | null) {
  const params = new URLSearchParams();
  if (orgId != null) params.append('org_id', String(orgId));
  const qs = params.toString() ? `?${params.toString()}` : '';
  return api.get<{ ok: boolean; calls: SavedCallSession[] }>(`/calls/history${qs}`);
}

export function fetchCallSession(sessionId: string) {
  return api.get<any>(`/calls/session?session_id=${encodeURIComponent(sessionId)}`);
}
