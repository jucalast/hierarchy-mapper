import { useState, useRef, useCallback } from 'react';
import { ai, conversations } from '@/services/api';
import type { TaskStatus, V2Event, MappedContact } from '../components/AgentV2Message';
import type { ThreadOut } from '@/services/api/conversations';

export const useTaskRunner = (
    selectedOrgId: number | null,
    activeThread: ThreadOut | null,
    setThreads: React.Dispatch<React.SetStateAction<ThreadOut[]>>
) => {
    const [activeRunningTask, setActiveRunningTask] = useState<{
        label: string;
        prompt: string;
        status: TaskStatus;
        logs: V2Event[];
        isExpanded: boolean;
        orgId?: number | null;
        threadId?: string;
        actionIndex: number;
        parentMessageId?: string;
    } | null>(null);

    const [approvedSuggestedActions, setApprovedSuggestedActions] = useState<Record<string, TaskStatus>>({});
    const [taskInlineConfirmed, setTaskInlineConfirmed] = useState<Record<string, boolean>>({});
    const abortControllerRef = useRef<AbortController | null>(null);

    const streamTaskInto = async (url: string, body: object) => {
        const collected: V2Event[] = [];
        
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...body }),
                signal: controller.signal,
            });
            if (!response.ok || !response.body) return collected;

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const ev: V2Event = JSON.parse(line);
                        collected.push(ev);
                        setActiveRunningTask(prev => prev ? { ...prev, logs: [...prev.logs, ev] } : null);
                    } catch { /* ignore */ }
                }
            }
        } catch (err: any) {
            if (err.name !== 'AbortError') console.error('[useTaskRunner] Task stream error:', err);
        } finally {
            if (abortControllerRef.current === controller) abortControllerRef.current = null;
        }
        return collected;
    };

    const handleApproveSuggestedAction = async (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => {
        const taskKey = `${parentMessageId}-${index}`;
        setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: 'streaming' }));

        const newTask = {
            label: action.label,
            prompt: action.prompt,
            status: 'streaming' as const,
            logs: [] as V2Event[],
            isExpanded: true,
            orgId: selectedOrgId,
            threadId: activeThread?.id,
            actionIndex: index,
            parentMessageId,
        };
        
        setActiveRunningTask(newTask);
        setTaskInlineConfirmed({});

        try {
            const collected = await streamTaskInto(ai.getV2ChatStreamUrl(), {
                message: action.prompt,
                org_id: selectedOrgId,
                thread_id: activeThread?.id,
                history: [],
                direct_action: true,
                parent_message_id: parentMessageId,
                action_index: index,
            });

            const hierarchyEv = collected.find(e => e.type === 'hierarchy_mapping_required');
            const pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
            
            let finalStatus: TaskStatus = 'done';
            if (hierarchyEv) {
                finalStatus = 'awaiting_mapping';
            } else if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            }

            setActiveRunningTask(prev => prev ? { ...prev, status: finalStatus } : null);
            setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: finalStatus }));
            
            if (selectedOrgId) conversations.listThreads(selectedOrgId).then(setThreads).catch(() => {});
        } catch {
            setActiveRunningTask(prev => prev ? { ...prev, status: 'error' } : null);
            setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: 'error' }));
        }
    };

    const handleTaskInlineConfirm = async (action_id: string, approved: boolean) => {
        if (!activeRunningTask) return;
        setTaskInlineConfirmed(prev => ({ ...prev, [action_id]: approved }));

        if (!approved) {
            setActiveRunningTask(prev => prev ? { ...prev, status: 'done' } : null);
            if (activeRunningTask.parentMessageId) {
                const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
                setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: 'done' }));
            }
            return;
        }

        setActiveRunningTask(prev => prev ? { ...prev, status: 'streaming' } : null);
        if (activeRunningTask.parentMessageId) {
            const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
            setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: 'streaming' }));
        }

        try {
            const collected = await streamTaskInto(ai.getV2ConfirmStreamUrl(), {
                action_id,
                approved: true,
                thread_id: activeThread?.id,
            });
            
            const pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
            let finalStatus: TaskStatus = 'done';
            if (pendingConfirm) finalStatus = 'awaiting_confirm';

            setActiveRunningTask(prev => prev ? { ...prev, status: finalStatus } : null);
            if (activeRunningTask.parentMessageId) {
                const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
                setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: finalStatus }));
            }
        } catch {
            setActiveRunningTask(prev => prev ? { ...prev, status: 'error' } : null);
            if (activeRunningTask.parentMessageId) {
                const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
                setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: 'error' }));
            }
        }
    };

    const handleTaskMappingComplete = async (contacts: MappedContact[]) => {
        if (!activeRunningTask) return;
        const hierarchyEv = activeRunningTask.logs.find(e => e.type === 'hierarchy_mapping_required');
        if (!hierarchyEv) return;

        setActiveRunningTask(prev => prev ? { ...prev, status: 'streaming' } : null);
        if (activeRunningTask.parentMessageId) {
            const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
            setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: 'streaming' }));
        }

        const contactsSummary = contacts.length > 0
            ? `Contatos reais encontrados: ` + contacts.slice(0, 8).map(c => `${c.name} (${c.role})`).join(' | ')
            : 'Nenhum contato encontrado.';

        const continuation = `EXECUTE ESTAS ETAPAS: 1. Mapeamento concluído. ${contactsSummary} 2. Sugira ações para contatos relevantes.`;

        try {
            const newEvents = await streamTaskInto(ai.getV2ChatStreamUrl(), {
                message: continuation,
                org_id: selectedOrgId,
                thread_id: activeThread?.id,
                history: [],
                direct_action: true,
                parent_message_id: activeRunningTask.parentMessageId,
                action_index: activeRunningTask.actionIndex,
            });

            const pendingConfirm = newEvents.find(e => e.type === 'confirmation_required' && e.action_id);
            let finalStatus: TaskStatus = 'done';
            if (pendingConfirm) finalStatus = 'awaiting_confirm';
            setActiveRunningTask(prev => prev ? { ...prev, status: finalStatus } : null);
            if (activeRunningTask.parentMessageId) {
                const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
                setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: finalStatus }));
            }
        } catch {
            setActiveRunningTask(prev => prev ? { ...prev, status: 'error' } : null);
            if (activeRunningTask.parentMessageId) {
                const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
                setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: 'error' }));
            }
        }
    };

    return {
        activeRunningTask,
        setActiveRunningTask,
        approvedSuggestedActions,
        setApprovedSuggestedActions,
        taskInlineConfirmed,
        handleApproveSuggestedAction,
        handleTaskInlineConfirm,
        handleTaskMappingComplete
    };
};
