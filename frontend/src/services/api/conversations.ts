import { api } from './client';

export interface ThreadOut {
    id: string;
    org_id: number | null;
    title: string | null;
    created_at: string;
    updated_at: string;
    last_message_at: string | null;
    message_count: number;
    meta: Record<string, any> | null;
}

export interface MessageOut {
    id: string;
    thread_id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
    ui_module: string | null;
    data: Record<string, any> | null;
    logs: any[] | null;
    sources: number | null;
}

export interface ActivityOut {
    id: string;
    org_id: number | null;
    thread_id: string | null;
    activity_type: string;
    status: string;
    payload: Record<string, any> | null;
    created_at: string;
    resolved_at: string | null;
    external_ref: string | null;
}

export function listThreads(orgId: number, limit = 20): Promise<ThreadOut[]> {
    return api.get<ThreadOut[]>(`/conversations/${orgId}?limit=${limit}`);
}

export function createThread(orgId: number, title?: string): Promise<ThreadOut> {
    return api.post<ThreadOut>(`/conversations/${orgId}`, { title });
}

export function getMessages(threadId: string, limit = 50): Promise<MessageOut[]> {
    return api.get<MessageOut[]>(`/conversations/thread/${threadId}/messages?limit=${limit}`);
}

export function deleteThread(threadId: string): Promise<void> {
    return api.delete(`/conversations/thread/${threadId}`);
}

export function deleteThreadsBulk(threadIds: string[]): Promise<void> {
    const params = new URLSearchParams();
    threadIds.forEach(id => params.append('thread_ids', id));
    return api.delete(`/conversations/threads/bulk?${params.toString()}`);
}

export function listActivities(orgId: number, limit = 30): Promise<ActivityOut[]> {
    return api.get<ActivityOut[]>(`/conversations/${orgId}/activities?limit=${limit}`);
}
