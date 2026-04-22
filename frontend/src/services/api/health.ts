import { API_V1_URL } from '../config';
import { api } from './client';

export function ping() {
  return api.get<{ status: string }>('/api/../health');
}

export function ready() {
  // /ready não está sob /api/v1, então usamos a origin direta
  const origin = API_V1_URL.replace(/\/api\/v1$/, '');
  return api.get<{ status: string; checks: Record<string, unknown> }>(`${origin}/ready`);
}
