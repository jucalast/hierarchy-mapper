import type { OrganizationSummary } from '@/types';
import { api } from './client';

/** Lista organizações do CRM (cache local prioritário no backend). */
export function listOrganizations() {
  return api.get<OrganizationSummary[]>('/pipedrive/organizations');
}

/** Detalhes 'Raio-X' de uma organização (deals, persons, activities, notes). */
export function getOrganizationDetails(orgId: number, done?: 0 | 1) {
  const qs = done !== undefined ? `?done=${done}` : '';
  return api.get<Record<string, unknown>>(`/pipedrive/organizations/${orgId}/details${qs}`);
}

export function deleteOrganization(orgId: number) {
  return api.delete<{ success?: boolean }>(`/pipedrive/organizations/${orgId}`);
}

export function updateOrganization(orgId: number, data: Record<string, unknown>) {
  return api.put<Record<string, unknown>>(`/pipedrive/organizations/${orgId}`, data);
}

export function createOrganization(data: Record<string, unknown>) {
  return api.post<{ id?: number }>('/pipedrive/organizations', data);
}

export function resetOrganization(orgId: number) {
  return api.post<{ status?: string; message?: string }>(
    `/pipedrive/organizations/${orgId}/reset`,
  );
}

export function renameOrganization(orgId: number, name: string) {
  return api.post<Record<string, unknown>>(`/pipedrive/organizations/${orgId}/rename`, { name });
}

/** Sincronização completa Pipedrive → banco local (heavy). */
export function triggerPipedriveSync() {
  return api.post<{ status?: string }>('/pipedrive_sync');
}

export function triggerSmartSync() {
  return api.post<{ status?: string; message?: string }>('/pipedrive_smart_sync');
}

export function updateActivity(activityId: number | string, data: Record<string, unknown>) {
  return api.put<Record<string, unknown>>(`/pipedrive/activities/${activityId}`, data);
}

