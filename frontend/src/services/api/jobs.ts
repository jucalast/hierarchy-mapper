import { api } from './client';
import { API_V1_URL, API_BASE_URL, TIMEOUTS } from '../config';

export interface JobStatus {
  id?: string;
  job_id?: string;
  status: 'queued' | 'in_progress' | 'success' | 'failed' | 'cancelled' | string;
  progress?: number;
  message?: string;
  result?: unknown;
  error?: string | null;
}

export function getJobStatus(jobId: string) {
  return api.get<JobStatus>(`/jobs/status/${jobId}`);
}

/** NDJSON streaming (HTTP). Apenas retorna a URL — use `useJobStream`. */
export function getJobStreamUrl(jobId: string): string {
  return `${API_V1_URL}/jobs/${jobId}/stream`;
}

/** WebSocket para atualizações ao vivo do worker de discovery. */
export function getJobWebSocketUrl(jobId: string): string {
  const base = API_BASE_URL.replace(/^http/, 'ws');
  return `${base}/api/v1/jobs/ws/${jobId}`;
}

export function cancelJob(jobId: string) {
  return api.post<JobStatus>(`/jobs/stop/${jobId}`);
}

export interface StartScanPayload {
  company_name?: string;
  cnpj?: string;
  domain?: string;
  confirmed_brand?: string;
  confirmed_logo?: string;
  product_focus?: string;
  area_focus?: 'compras' | 'logistica' | string;
  model?: string;
  strict_mode?: boolean;
}

/** Inicia scan assíncrono — retorna job_id para acompanhar via WS/stream. */
export function startScan(payload: StartScanPayload) {
  const qs = new URLSearchParams();
  Object.entries(payload).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.append(k, String(v));
  });
  return api.post<{ job_id: string; message?: string }>(
    `/jobs/start-scan?${qs.toString()}`,
    undefined,
    { timeout: TIMEOUTS.long },
  );
}
