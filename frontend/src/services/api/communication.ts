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
