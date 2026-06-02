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

export function refineHierarchy(employees: HierarchyEmployee[]) {
  return api.post<{ nodes?: HierarchyEmployee[] }>(
    '/hierarchy/refine',
    employees,
    { timeout: TIMEOUTS.long },
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

