import type { OrganizationSummary } from '@/types';
import { api } from './client';

/** Lista organizações do CRM (cache local prioritário no backend). */
export function listOrganizations() {
  return api.get<OrganizationSummary[]>('/pipedrive/organizations');
}

const detailsCache = new Map<string, Promise<any>>();

/** Detalhes 'Raio-X' de uma organização (deals, persons, activities, notes). */
export function getOrganizationDetails(orgId: number, done?: 0 | 1) {
  const cacheKey = `${orgId}_${done}`;
  const cached = detailsCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  const qs = done !== undefined ? `?done=${done}` : '';
  const promise = api.get<Record<string, unknown>>(`/pipedrive/organizations/${orgId}/details${qs}`);
  
  detailsCache.set(cacheKey, promise);
  
  promise.finally(() => {
    detailsCache.delete(cacheKey);
  });
  
  return promise;
}

export function getLocalOrganization(orgId: number) {
  return api.get<Record<string, unknown>>(`/organizations/${orgId}`);
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

export function createPerson(data: Record<string, unknown>) {
  return api.post<{ status?: string; message?: string; data?: unknown }>('/pipedrive/persons', data);
}
export function updatePerson(personId: number, data: Record<string, unknown>) {
  return api.put<{ status?: string; message?: string }>(`/pipedrive/persons/${personId}`, data);
}

export function deletePerson(personId: number) {
  return api.delete<{ status?: string; message?: string }>(`/pipedrive/persons/${personId}`);
}
export function resetOrganization(orgId: number) {
  return api.post<{ status?: string; message?: string }>(
    `/pipedrive/organizations/${orgId}/reset`,
  );
}



/** Sincronização completa Pipedrive → banco local (heavy). */
export function triggerPipedriveSync() {
  return api.post<{ status?: string }>('/pipedrive_sync');
}

export function triggerSmartSync() {
  return api.post<{ status?: string; message?: string; job_id?: string }>('/pipedrive_smart_sync');
}

export function updateActivity(activityId: number | string, data: Record<string, unknown>) {
  return api.put<Record<string, unknown>>(`/pipedrive/activities/${activityId}`, data);
}

export function deleteActivity(activityId: number | string) {
  return api.delete<{ status?: string; message?: string }>(`/pipedrive/activities/${activityId}`);
}

export function deleteNote(noteId: number | string) {
  return api.delete<{ status?: string; message?: string }>(`/pipedrive/notes/${noteId}`);
}

export function getPipelineBoard() {
  return api.get<{ stages: any[]; deals: any[] }>('/pipedrive/pipeline/board');
}

export function batchValidateEmails(orgId: number) {
  return api.post<{ ok?: boolean; message?: string }>(`/organizations/${orgId}/validate-emails`);
}

export function deleteProspectingPlan(orgId: number) {
  return api.delete<{ ok?: boolean; message?: string }>(`/organizations/${orgId}/prospecting-plan`);
}

export function getOrganizationPhoto(orgId: number) {
  return api.get<{ ok: boolean; photo_url: string | null }>(`/organizations/${orgId}/photo`);
}

