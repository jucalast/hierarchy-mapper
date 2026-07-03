import type { HierarchyEmployee, HierarchyResponse } from '@/types';
import { api } from './client';
import { TIMEOUTS, API_V1_URL } from '../config';

export interface DiscoverBrandPayload {
  cnpj?: string;
  domain?: string;
  force?: boolean;
}

export function discoverBrand(payload: DiscoverBrandPayload) {
  const qs = new URLSearchParams();
  if (payload.cnpj) qs.append('cnpj', payload.cnpj);
  if (payload.domain) qs.append('domain', payload.domain);
  if (payload.force) qs.append('force', 'true');
  return api.get<{ alternatives?: unknown[] }>(
    `/brand/discover?${qs.toString()}`,
    { timeout: TIMEOUTS.long },
  );
}

/**
 * URL do stream SSE para descoberta incremental de marcas.
 * Retorna URL pura; o consumidor faz fetch manual com AbortController.
 */
export function getDiscoverBrandStreamUrl(payload: DiscoverBrandPayload): string {
  const qs = new URLSearchParams();
  if (payload.cnpj) qs.append('cnpj', payload.cnpj);
  if (payload.domain) qs.append('domain', payload.domain);
  if (payload.force) qs.append('force', 'true');
  qs.append('stream', 'true');
  return `${API_V1_URL}/brand/discover?${qs.toString()}`;
}

export interface FetchHierarchyPayload {
  identifier: string;
  domain?: string;
  product_focus?: string | null;
  force_refresh?: boolean;
}

export function fetchHierarchy(payload: FetchHierarchyPayload) {
  return api.post<HierarchyResponse>(
    '/hierarchy/fetch',
    payload,
    { timeout: TIMEOUTS.long },
  );
}

export function refineHierarchy(employees: HierarchyEmployee[], options?: { signal?: AbortSignal }) {
  return api.post<{ nodes?: HierarchyEmployee[] }>(
    '/hierarchy/refine',
    employees,
    { timeout: TIMEOUTS.long, signal: options?.signal },
  );
}

export function loadHierarchyByPipedrive(orgId: number) {
  return api.get<{ nodes?: HierarchyEmployee[]; company_name?: string; status?: string }>(
    `/hierarchy/pipedrive/${orgId}`,
  );
}

export function loadHierarchyByLocalId(orgId: number) {
  return api.get<{ nodes?: HierarchyEmployee[]; company_name?: string; status?: string }>(
    `/hierarchy/${orgId}`,
  );
}

export function candidateAction(employeeId: string, action: 'approve' | 'reject') {
  return api.post<Record<string, unknown>>('/hierarchy/candidate-action', {
    employee_id: String(employeeId),
    action,
  });
}

export function enrichManual(employeeId: string, rawText: string) {
  return api.post<{ status: string; message: string; employee: HierarchyEmployee }>(
    '/hierarchy/enrich-manual',
    {
      employee_id: String(employeeId),
      raw_text: rawText,
    },
    { timeout: TIMEOUTS.long }
  );
}

export function updateEmployeeDetails(employeeId: string, updates: Partial<HierarchyEmployee>) {
  return api.post<Record<string, unknown>>(
    `/hierarchy/update-employee?employee_id=${employeeId}`,
    updates
  );
}

export interface ConfirmIntelligencePayload {
  name: string;
  cnpj?: string;
  domain?: string;
  address?: string;
  pipedrive_id?: number;
  linkedin_url?: string;
  logo_url?: string;
  partners?: Array<Record<string, unknown>>;
}

export function confirmIntelligence(payload: ConfirmIntelligencePayload) {
  return api.post<{
    status?: string;
    is_update?: boolean;
    local_id?: number;
    pipedrive_id?: number;
  }>('/intelligence/confirm', payload);
}

export interface StartLinkedinScrapePayload {
  companyUrl: string;
  sessionCookie?: string;
  headless?: boolean;
  areaFocus?: string;
  productFocus?: string;
  model?: string;
}

/** Enfileira o scraping do LinkedIn como background job — sobrevive a reload de página. */
export function startLinkedinScrape(payload: StartLinkedinScrapePayload) {
  const qs = new URLSearchParams();
  qs.append('company_url', payload.companyUrl);
  if (payload.sessionCookie) qs.append('session_cookie', payload.sessionCookie);
  qs.append('headless', String(payload.headless ?? true));
  if (payload.areaFocus) qs.append('area_focus', payload.areaFocus);
  if (payload.productFocus) qs.append('product_focus', payload.productFocus);
  if (payload.model) qs.append('model', payload.model);
  return api.post<{ job_id: string; status?: string }>(
    `/hierarchy/linkedin-scrape/start?${qs.toString()}`
  );
}

export function interactLinkedinScrape(
  jobId: string,
  action: 'click' | 'type' | 'press',
  params: { x?: number; y?: number; text?: string; key?: string } = {}
) {
  const qs = new URLSearchParams({ job_id: jobId, action });
  if (params.x !== undefined) qs.append('x', String(params.x));
  if (params.y !== undefined) qs.append('y', String(params.y));
  if (params.text !== undefined) qs.append('text', params.text);
  if (params.key !== undefined) qs.append('key', params.key);
  return api.post<{ status: string; message: string }>(
    `/hierarchy/linkedin-scrape/interact?${qs.toString()}`
  );
}

export function stopLinkedinScrape(jobId: string) {
  return api.post<{ status: string; message: string }>(
    `/hierarchy/linkedin-scrape/stop?job_id=${encodeURIComponent(jobId)}`
  );
}

export function enrichIntelligence(params: { name?: string; cnpj: string; force?: boolean }) {
  const qs = new URLSearchParams();
  if (params.name) qs.append('name', params.name);
  qs.append('cnpj', params.cnpj);
  if (params.force) qs.append('force', 'true');
  return api.get<{
    success?: boolean;
    main_option?: {
      domain?: string;
      cnpj?: string;
      official_name?: string;
      [k: string]: unknown;
    };
  }>(`/intelligence/enrich?${qs.toString()}`, { timeout: TIMEOUTS.long });
}

export interface DiscoverEmailPayload {
  contact_name: string;
  org_name?: string | null;
  domain?: string | null;
}

export interface DiscoverEmailResponse {
  ok: boolean;
  contact_name?: string;
  domain?: string;
  valid_emails?: Array<{ email: string; status: string; source: string }>;
  recommended?: string;
  error?: string;
}

export function discoverEmail(payload: DiscoverEmailPayload) {
  return api.post<DiscoverEmailResponse>('/intelligence/discover-email', payload);
}

