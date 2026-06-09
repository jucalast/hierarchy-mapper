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

