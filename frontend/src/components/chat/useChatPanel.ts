import { useState, useRef, useEffect, useCallback } from 'react';
import { useSpeechToText } from '../../hooks/useSpeechToText';
import { ai, conversations } from '@/services/api';
import { useChatStore } from '@/store/chatStore';
import { Message, CompanyResult } from './ChatInterfaces';
import { AIModel } from './ModelSelector';
import { AgentEvent, TaskStatus, MappedContact, classifyFailure } from './AgentV2Message';
import { ModelActivityEvent } from './ModelActivityBar';
import type { ThreadOut } from '@/services/api/conversations';

import { useChatAutocomplete } from './hooks/useChatAutocomplete';
import { useChatActivities } from './hooks/useChatActivities';
import { useChatThreads } from './hooks/useChatThreads';

const AGENT_STREAM_URL = ai.getAgentChatStreamUrl();
const AGENT_CONFIRM_URL = ai.getAgentConfirmStreamUrl();

interface UseChatPanelProps {
    selectedOrgId?: number | null;
    selectedOrgName?: string;
    selectedOrgLogo?: string;
    prospectingContext?: string | null;
    isOrgLoading?: boolean;
    showChat?: boolean;
}

export const useChatPanel = ({
    selectedOrgId,
    selectedOrgName = 'Organização',
    selectedOrgLogo,
    prospectingContext,
    isOrgLoading,
    showChat = false,
}: UseChatPanelProps) => {
    const {
        isListening,
        isTranscribing,
        transcript,
        finalTranscript,
        error: voiceError,
        startListening,
        stopListening,
        clearTranscript,
        isSupported: voiceSupported,
        analyserNode,
    } = useSpeechToText();

    const [view, setView] = useState<'list' | 'chat'>('chat');

    // ─── Zustand Global Chat Store ───────────────────────────
    const store = useChatStore();

    // Sincroniza a organização ativa no store
    useEffect(() => {
        store.setCurrentOrgId(selectedOrgId || null);
    }, [selectedOrgId]);

    const activeOrgId = store.currentOrgId;

    // Sincroniza informações da organização focada (nome e logo)
    const [currentOrgInfo, setCurrentOrgInfo] = useState({
        name: selectedOrgName,
        logo: selectedOrgLogo || ''
    });

    const hasValidOrg = !!(currentOrgInfo?.name && currentOrgInfo.name.trim() !== '' && currentOrgInfo.name !== 'Assistente IA');
    const cleanOrgName = hasValidOrg ? currentOrgInfo.name.trim() : '';

    useEffect(() => {
        if (selectedOrgId) {
            // URL tem uma empresa: cleanOrgName sempre reflete a empresa da URL,
            // independente do store.currentOrgId (que pode estar desatualizado por clique em aba).
            setCurrentOrgInfo({
                name: selectedOrgName,
                logo: selectedOrgLogo || ''
            });
        } else if (activeOrgId) {
            const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
            if (cachedOrgsStr) {
                try {
                    const list = JSON.parse(cachedOrgsStr);
                    if (Array.isArray(list)) {
                        const cachedOrg = list.find((o: any) => Number(o.id) === activeOrgId);
                        if (cachedOrg) {
                            const foundLogo = cachedOrg.logo || cachedOrg.organization_logo || cachedOrg.logo_url || cachedOrg.company_logo || "";
                            setCurrentOrgInfo({
                                name: cachedOrg.name || cachedOrg.title || "Empresa",
                                logo: foundLogo
                            });
                        } else {
                            setCurrentOrgInfo({
                                name: `Empresa #${activeOrgId}`,
                                logo: ''
                            });
                        }
                    }
                } catch {
                    setCurrentOrgInfo({
                        name: `Empresa #${activeOrgId}`,
                        logo: ''
                    });
                }
            } else {
                setCurrentOrgInfo({
                    name: `Empresa #${activeOrgId}`,
                    logo: ''
                });
            }
        } else {
            setCurrentOrgInfo({
                name: 'Assistente IA',
                logo: ''
            });
        }
    }, [activeOrgId, selectedOrgId, selectedOrgName, selectedOrgLogo]);

    // ─── Pipedrive Activities Sub-hook ────────────────────────
    const {
        activities,
        setActivities,
        isLoadingActivities,
        refreshActivities,
    } = useChatActivities(selectedOrgId);

    // ─── Local controls/states ─────────────────────────────────
    const [model, setModel] = useState<AIModel>('gemini');
    const [strictMode, setStrictMode] = useState<boolean>(true);

    // Carrega preferências do localStorage no client-side para evitar hydration mismatch
    // strict mode e modelo sempre iniciam com os defaults (gemini + strict) independente do que estava salvo
    useEffect(() => {}, []);

    const modelActivityIdRef = useRef(0);
    const [pipedriveCooldown, setPipedriveCooldown] = useState<number>(0);
    const abortControllersRef = useRef<Record<string, AbortController>>({});
    // True quando o último abort do stream de tarefa ('global_task') foi um cancelamento
    // explícito do usuário (botão de stop), e não uma falha de rede/tool — consultado pelos
    // handlers de streamTaskInto para reportar status 'cancelled' em vez de 'error'.
    const userCancelledTaskRef = useRef(false);
    // Guarda o threadId em streaming POR org (chave = String(orgId)).
    // Mapa em vez de valor único permite que múltiplas orgs façam streaming
    // simultaneamente sem que trocar de org limpe o tracking da outra.
    const streamingThreadIdRef = useRef<Record<string, string | null>>({});
    const activeThreadIdRef = useRef<string | null>(null);

    // ─── Refresh messages ────────────────────────────────────
    const refreshMessages = useCallback(async (threadId: string) => {
        try {
            const msgs = await conversations.getMessages(threadId);
            if (msgs.length === 0) {
                store.setMessages(activeOrgId, threadId, [{
                    id: 'welcome',
                    role: 'assistant',
                    content: hasValidOrg ? `Como posso te ajudar com a @${cleanOrgName}?` : "Como posso te ajudar hoje?",
                    timestamp: new Date(),
                }]);
            } else {
                let hasActiveJobLoading = false;
                let hasAwaitingConfirmation = false;
                
                const callIdToActionId: Record<string, string> = {};
                const actionIdToApproved: Record<string, boolean> = {};
                const initialSuggestedActions: Record<string, TaskStatus> = {};
                let restoredTask: any = null;

                msgs.forEach((m) => {
                    if (m.logs && Array.isArray(m.logs)) {
                        m.logs.forEach((event: any) => {
                            if (event.type === 'confirmation_required' && event.action_id && event.call_id) {
                                callIdToActionId[event.call_id] = event.action_id;
                            }
                        });
                    }
                    if (m.data && m.data.suggested_actions_runs) {
                        const runs = m.data.suggested_actions_runs;
                        Object.keys(runs).forEach((idx) => {
                            const run = runs[idx];
                            if (run.status) {
                                initialSuggestedActions[`${m.id}-${idx}`] = run.status as TaskStatus;
                                
                                if (run.status === 'streaming' || run.status === 'awaiting_confirm' || run.status === 'awaiting_mapping') {
                                    let label = 'Tarefa em andamento';
                                    let prompt = '';
                                    if (m.logs && Array.isArray(m.logs)) {
                                        const event = m.logs.find((e: any) => e.type === 'suggested_actions');
                                        if (event && event.actions && event.actions[Number(idx)]) {
                                            label = event.actions[Number(idx)].label || label;
                                            prompt = event.actions[Number(idx)].prompt || prompt;
                                        }
                                    }
                                    restoredTask = {
                                        label,
                                        prompt,
                                        status: run.status as TaskStatus,
                                        logs: run.logs || [],
                                        isExpanded: true,
                                        orgId: selectedOrgId,
                                        threadId,
                                        actionIndex: Number(idx),
                                        parentMessageId: m.id,
                                    };
                                }
                            }
                            if (run.logs && Array.isArray(run.logs)) {
                                run.logs.forEach((event: any) => {
                                    if (event.type === 'confirmation_required' && event.action_id && event.call_id) {
                                        callIdToActionId[event.call_id] = event.action_id;
                                    }
                                });
                            }
                        });
                    }
                });

                msgs.forEach((m) => {
                    if (m.logs && Array.isArray(m.logs)) {
                        m.logs.forEach((event: any) => {
                            if (event.type === 'tool_result' && event.call_id) {
                                const actionId = callIdToActionId[event.call_id];
                                if (actionId) {
                                    actionIdToApproved[actionId] = event.ok === true;
                                }
                            }
                        });
                    }
                    if (m.data && m.data.suggested_actions_runs) {
                        const runs = m.data.suggested_actions_runs;
                        Object.keys(runs).forEach((idx) => {
                            const run = runs[idx];
                            if (run.logs && Array.isArray(run.logs)) {
                                run.logs.forEach((event: any) => {
                                    if (event.type === 'tool_result' && event.call_id) {
                                        const actionId = callIdToActionId[event.call_id];
                                        if (actionId) {
                                            actionIdToApproved[actionId] = event.ok === true;
                                        }
                                    }
                                });
                            }
                        });
                    }
                });

                const mappedMsgs = msgs.map((m) => {
                    const isAgent = !!(m.logs && Array.isArray(m.logs) && m.logs.some((l: any) => l.type === 'tool_call' || l.type === 'thinking' || l.type === 'final'));
                    let forceAgentStreaming = false;
                    if (isAgent && m.logs && Array.isArray(m.logs)) {
                        const hasMapping = m.logs.some((l: any) => l.type === 'hierarchy_mapping_required');
                        if (hasMapping && typeof window !== 'undefined') {
                            const activeJob = window.localStorage.getItem(`active-discovery-job-${selectedOrgId}`);
                            if (activeJob) {
                                forceAgentStreaming = true;
                                hasActiveJobLoading = true;
                            }
                        }

                        let hasUndecidedConfirmation = false;
                        m.logs.forEach((l: any) => {
                            if (l.type === 'confirmation_required' && l.action_id) {
                                if (!(l.action_id in actionIdToApproved)) {
                                    hasUndecidedConfirmation = true;
                                }
                            }
                        });

                        if (m.data && m.data.suggested_actions_runs) {
                            Object.values(m.data.suggested_actions_runs).forEach((run: any) => {
                                if (run.status === 'awaiting_confirm') {
                                    hasUndecidedConfirmation = true;
                                }
                            });
                        }

                        if (hasUndecidedConfirmation) {
                            forceAgentStreaming = true;
                            hasAwaitingConfirmation = true;
                        }
                    }

                    const msgConfirmedActions: Record<string, boolean> = {};
                    if (m.logs && Array.isArray(m.logs)) {
                        m.logs.forEach((event: any) => {
                            if (event.type === 'confirmation_required' && event.action_id) {
                                if (event.action_id in actionIdToApproved) {
                                    msgConfirmedActions[event.action_id] = actionIdToApproved[event.action_id];
                                }
                            }
                        });
                    }

                    return {
                        id: m.id,
                        role: m.role as 'user' | 'assistant',
                        content: m.content,
                        timestamp: new Date(m.timestamp),
                        ui_module: (m.ui_module as any) ?? undefined,
                        data: m.data ?? undefined,
                        logs: m.logs ?? undefined,
                        isAgent: isAgent,
                        agentEvents: isAgent ? (m.logs ?? undefined) : undefined,
                        agentStreaming: forceAgentStreaming ? true : undefined,
                        agentConfirmedActions: msgConfirmedActions,
                    };
                });

                if (hasActiveJobLoading || hasAwaitingConfirmation) {
                    store.setAgentStreaming(activeOrgId, threadId, true);
                }
                if (hasActiveJobLoading) {
                    store.setIsLoading(activeOrgId, threadId, true);
                }
                store.setApprovedSuggestedActions(activeOrgId, threadId, prev => ({ ...prev, ...initialSuggestedActions }));
                if (restoredTask) {
                    store.setActiveRunningTask(activeOrgId, threadId, restoredTask);
                } else {
                    store.setActiveRunningTask(activeOrgId, threadId, null);
                }
                store.setMessages(activeOrgId, threadId, mappedMsgs);
            }
        } catch (err) {
            console.error('[ChatPanel] Erro ao carregar/atualizar mensagens:', err);
        }
    }, [activeOrgId, currentOrgInfo.name, hasValidOrg, cleanOrgName, prospectingContext, selectedOrgId]);

    // ─── Threads Sub-hook ─────────────────────────────────────
    const {
        threads,
        setThreads,
        isLoadingThreads,
        isCreatingThread,
        threadsToDelete,
        setThreadsToDelete,
        activeThread,
        setActiveThread,
        openThread,
        loadThreads,
        handleNewThread,
        handleBackToList,
        confirmDeleteThread,
        ensureThread,
    } = useChatThreads({
        activeOrgId,
        selectedOrgId,
        prospectingContext,
        showChat,
        setView,
        streamingThreadIdRef,
        clearNewThreadState: () => {
            store.setMessages(activeOrgId, null, []);
            store.setInputValue(activeOrgId, null, "");
            store.setActiveRunningTask(activeOrgId, null, null);
        },
        onOpenThread: async (thread, isSameStreamingThread) => {
            if (!isSameStreamingThread) {
                // Reseta estados de loading/streaming antes de refreshMessages para
                // não herdar valores presos de uma sessão de streaming anterior que
                // terminou enquanto o usuário estava em outra empresa.
                store.setIsLoading(activeOrgId, thread.id, false);
                store.setAgentStreaming(activeOrgId, thread.id, false);
                store.setActiveRunningTask(activeOrgId, thread.id, null);
                store.setLiveModel(activeOrgId, thread.id, null);
                store.setModelActivity(activeOrgId, thread.id, []);
                await refreshMessages(thread.id);
            } else {
                store.setIsLoading(activeOrgId, thread.id, true);
                store.setAgentStreaming(activeOrgId, thread.id, true);
            }
        },
        onNewThread: () => {
            streamingThreadIdRef.current[String(activeOrgId || 0)] = null;
            setActiveRunningTask(null);
            setLiveModel(null);
            setModelActivity([]);
            setAgentEvents([]);
            setApprovedSuggestedActions({});
            setAgentConfirmedActions({});
        },
        onBackToList: () => {
            // silent/no-op
        }
    });

    const activeThreadId = activeThread?.id;

    // Auto-preenche ou limpa o input com base na existência de plano de prospecção
    useEffect(() => {
        if (!isOrgLoading && activeOrgId && activeThreadId) {
            const currentSession = store.getSession(activeOrgId, activeThreadId);
            const msgs = currentSession.messages;
            const isEmptyConversation = msgs.length === 0 || (msgs.length === 1 && msgs[0].id === 'welcome');
            if (!isEmptyConversation) return;

            const PRE_FILL = "Gerar plano de prospecção para esta empresa";
            if (!prospectingContext && currentSession.inputValue === '') {
                store.setInputValue(activeOrgId, activeThreadId, PRE_FILL);
            } else if (prospectingContext && currentSession.inputValue === PRE_FILL) {
                store.setInputValue(activeOrgId, activeThreadId, '');
            }
        }
    }, [isOrgLoading, activeOrgId, prospectingContext, activeThreadId, store]);

    useEffect(() => {
        activeThreadIdRef.current = activeThread?.id || null;
    }, [activeThread]);

    const session = store.getSession(activeOrgId, activeThreadId);

    const messages = session.messages;
    const inputValue = session.inputValue;
    const isLoading = session.isLoading;
    const selectedCompanies = session.selectedCompanies;
    const approvalStatuses = session.approvalStatuses;
    const liveModel = session.liveModel as AIModel | null;
    const modelActivity = session.modelActivity;
    const agentEvents = session.agentEvents;
    const agentStreaming = session.agentStreaming;
    const agentConfirmedActions = session.agentConfirmedActions;

    const setInputValue = useCallback((val: string | ((prev: string) => string)) => {
        const currentVal = store.getSession(activeOrgId, activeThreadId).inputValue;
        const nextVal = typeof val === 'function' ? val(currentVal) : val;
        store.setInputValue(activeOrgId, activeThreadId, nextVal);
    }, [store, activeOrgId, activeThreadId]);

    const setMessages = useCallback((val: Message[] | ((prev: Message[]) => Message[])) => store.setMessages(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setIsLoading = useCallback((val: boolean) => store.setIsLoading(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setAgentStreaming = useCallback((val: boolean) => store.setAgentStreaming(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setSelectedCompanies = useCallback((val: CompanyResult[] | ((prev: CompanyResult[]) => CompanyResult[])) => store.setSelectedCompanies(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setApprovalStatuses = useCallback((val: Record<string, any> | ((prev: Record<string, any>) => Record<string, any>)) => store.setApprovalStatuses(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setLiveModel = useCallback((val: AIModel | null) => store.setLiveModel(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setModelActivity = useCallback((val: any[] | ((prev: any[]) => any[])) => store.setModelActivity(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setAgentEvents = useCallback((val: any[] | ((prev: any[]) => any[])) => store.setAgentEvents(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setAgentConfirmedActions = useCallback((val: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)) => store.setAgentConfirmedActions(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);

    const activeRunningTask = session.activeRunningTask;
    const approvedSuggestedActions = session.approvedSuggestedActions;
    const taskInlineConfirmed = session.taskInlineConfirmed;
    const batchQueue = session.batchQueue || [];
    const isBatchRunning = session.isBatchRunning || false;
    const batchRunningSnapshot = session.batchRunningSnapshot || [];
    const batchCurrentIndex = session.batchCurrentIndex ?? -1;

    const setActiveRunningTask = useCallback((val: any | ((prev: any | null) => any | null)) => store.setActiveRunningTask(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setApprovedSuggestedActions = useCallback((val: Record<string, any> | ((prev: Record<string, any>) => Record<string, any>)) => store.setApprovedSuggestedActions(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setTaskInlineConfirmed = useCallback((val: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)) => store.setTaskInlineConfirmed(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setBatchQueue = useCallback((val: any[] | ((prev: any[]) => any[])) => store.setBatchQueue(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setIsBatchRunning = useCallback((val: boolean) => store.setIsBatchRunning(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setBatchRunningSnapshot = useCallback((val: any[]) => store.setBatchRunningSnapshot(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setBatchCurrentIndex = useCallback((val: number) => store.setBatchCurrentIndex(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);

    // ─── Autocomplete / universal search Sub-hook ─────────────
    const {
        showAutocomplete,
        setShowAutocomplete,
        searchTerm,
        setSearchTerm,
        companies,
        setCompanies,
        isSearching,
        searchingCategory,
        setSearchingCategory,
        handleInputChange,
    } = useChatAutocomplete({
        selectedCompanies,
        setSelectedCompanies,
        inputValue,
        setInputValue,
    });

    const taskConsoleLogsBottomRef = useRef<HTMLDivElement>(null);
    const messagesRef = useRef(messages);
    useEffect(() => {
        messagesRef.current = messages;
    }, [messages]);

    useEffect(() => {
        if (activeRunningTask?.isExpanded) {
            taskConsoleLogsBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [activeRunningTask?.logs, activeRunningTask?.isExpanded]);

    const handleStopStreaming = useCallback((targetThreadId?: string) => {
        const tId = targetThreadId || activeThreadIdRef.current || 'global';
        if (abortControllersRef.current[tId]) {
            abortControllersRef.current[tId].abort();
            delete abortControllersRef.current[tId];
        }
        const orgKey = String(activeOrgId || 0);
        if (streamingThreadIdRef.current[orgKey] === tId) {
            streamingThreadIdRef.current[orgKey] = null;
        }
        // O console de tarefa roda em stream próprio por org+thread — sem chave global
        // para não matar o stream de outra org quando duas rodam ao mesmo tempo.
        const taskKey = `task_${activeOrgId || 0}_${activeThreadIdRef.current || 'none'}`;
        if (abortControllersRef.current[taskKey]) {
            userCancelledTaskRef.current = true;
            abortControllersRef.current[taskKey].abort();
            setActiveRunningTask((prev: any) => prev ? { ...prev, status: 'cancelled' } : prev);
        } else {
            setActiveRunningTask((prev: any) => prev?.status === 'streaming' ? { ...prev, status: 'done' } : prev);
        }
        setIsLoading(false);
        setAgentStreaming(false);
        setLiveModel(null);
        setModelActivity([]);
    }, [setIsLoading, setAgentStreaming, setActiveRunningTask, setLiveModel, setModelActivity, activeOrgId]);

    const handleCancelActiveTask = () => {
        if (activeRunningTask) {
            const { parentMessageId, actionIndex } = activeRunningTask;
            let actualParentId = parentMessageId;
            if (actualParentId && /^\d+$/.test(actualParentId)) {
                const realMsg = messagesRef.current.find(m =>
                    m.logs?.some((e: any) => e.type === 'suggested_actions' && e.actions?.[actionIndex])
                );
                if (realMsg) actualParentId = realMsg.id;
            }

            if (actualParentId !== undefined && actionIndex !== undefined) {
                const taskKey = `${actualParentId}-${actionIndex}`;
                setApprovedSuggestedActions((prev: any) => {
                    const currentStatus = prev[taskKey];
                    if (currentStatus === 'done' || currentStatus === 'error') return prev;

                    conversations.updateSuggestedActionStatus(actualParentId, actionIndex, 'cancelled').catch(err => {
                        console.error('Failed to persist task cancellation', err);
                    });

                    return { ...prev, [taskKey]: 'cancelled' };
                });
            }
            // Marca o abort ANTES de chamar .abort() — o handler do streamTaskInto em
            // andamento consulta essa flag para saber que foi um cancelamento intencional
            // do usuário e não sobrescrever este status com o que vier de classifyFailure.
            userCancelledTaskRef.current = true;
            const taskKey = `task_${activeOrgId || 0}_${activeThreadIdRef.current || 'none'}`;
            if (abortControllersRef.current[taskKey]) {
                abortControllersRef.current[taskKey].abort();
            }
            // Mostra "cancelada" por um instante em vez de simplesmente desaparecer,
            // dando ao usuário a confirmação de que a tarefa parou (e não terminou em erro).
            setActiveRunningTask((prev: any) => prev ? { ...prev, status: 'cancelled' } : null);
            setIsLoading(false);
            setAgentStreaming(false);
            const cancelledIdx = actionIndex;
            setTimeout(() => {
                setActiveRunningTask((prev: any) => {
                    if (prev && prev.actionIndex === cancelledIdx && prev.status === 'cancelled') return null;
                    return prev;
                });
            }, 1500);
        }
    };

    const streamTaskInto = async (url: string, body: object, initialTaskState: typeof activeRunningTask) => {
        const collected: AgentEvent[] = [];

        // Chave por org+thread: permite múltiplas orgs com tarefas simultâneas
        // sem que uma aborte a outra ao usar a mesma chave 'global_task'.
        const capturedOrgId = activeOrgId;
        const capturedThreadId = activeThread?.id;
        const tId = `task_${capturedOrgId || 0}_${capturedThreadId || 'none'}`;
        if (abortControllersRef.current[tId]) {
            abortControllersRef.current[tId].abort();
        }
        const controller = new AbortController();
        abortControllersRef.current[tId] = controller;
        userCancelledTaskRef.current = false;

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
                        const ev: AgentEvent = JSON.parse(line);
                        collected.push(ev);

                        if (ev.type === 'tool_result' && ev.ok) {
                            const tool = ev.tool || '';
                            if (tool === 'generate_prospecting_plan') {
                                window.dispatchEvent(new CustomEvent('prospecting_plan_updated'));
                            }
                            
                            const isWriteTool = tool.includes('create') || tool.includes('update') || tool.includes('send') || tool.includes('reply');
                            
                            if ((tool.startsWith('pipedrive_') || tool.includes('send') || tool.includes('reply')) && isWriteTool) {
                                window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
                                if (tool === 'pipedrive_update_task') {
                                    try {
                                        const summary = ev.summary || '';
                                        if (summary.toLowerCase().includes('concluída') || summary.toLowerCase().includes('done')) {
                                            window.dispatchEvent(new CustomEvent('crm_task_completed'));
                                        } else {
                                            window.dispatchEvent(new CustomEvent('crm_task_uncompleted'));
                                        }
                                    } catch {}
                                }
                                refreshActivities();
                            }
                        }

                        setActiveRunningTask((prev: any) => {
                            if (!prev) return null;
                            return {
                                ...prev,
                                logs: [...prev.logs, ev]
                            };
                        });
                    } catch { /* ignore */ }
                }
            }
        } catch (err) {
            if ((err as any)?.name === 'AbortError') {
                console.log('[Task Console] Stream cancelado');
            } else {
                console.error('[Task Console] Erro:', err);
            }
        } finally {
            if (abortControllersRef.current[tId] === controller) {
                delete abortControllersRef.current[tId];
            }
        }
        return collected;
    };

    const handleSendMessage = async (text: string, companiesSelected: CompanyResult[] = [], isSuggestedAction: boolean = false, directAction: boolean = false) => {
        if (!text.trim() && (!companiesSelected || companiesSelected.length === 0)) return;

        setView('chat');

        const threadId = await ensureThread();
        if (!threadId) return;

        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: text,
            timestamp: new Date(),
            selectedCompanies: companiesSelected && companiesSelected.length > 0 ? [...companiesSelected] : undefined,
        };

        const historyForApi = messages.slice(-6).map(m => ({ role: m.role, content: m.content }));

        setIsAtBottom(true);
        store.setMessages(activeOrgId, threadId, prev => [...prev, userMsg]);
        store.setInputValue(activeOrgId, threadId, "");
        setSelectedCompanies([]);

        await executeAgent(text, threadId, historyForApi, directAction);
    };

    const handleApproveSuggestedAction = async (action: { label: string; prompt: string }, index: number, parentMessageId?: string, autoConfirm = false) => {
        let actualParentId = parentMessageId;
        if (actualParentId && /^\d+$/.test(actualParentId)) {
            const realMsg = messagesRef.current.find(m => 
                m.logs?.some((e: any) => e.type === 'suggested_actions' && e.actions?.[index]?.label === action.label)
            );
            if (realMsg) actualParentId = realMsg.id;
        }

        const taskKey = `${actualParentId}-${index}`;
        
        setApprovedSuggestedActions((prev: any) => ({
            ...prev,
            [taskKey]: 'streaming'
        }));
        setIsLoading(true);
        setAgentStreaming(true);

        const newTask = {
            label: action.label,
            prompt: action.prompt,
            status: 'streaming' as const,
            logs: [] as AgentEvent[],
            isExpanded: !autoConfirm,
            orgId: activeOrgId,
            threadId: activeThread?.id,
            actionIndex: index,
            parentMessageId: actualParentId,
        };
        
        setActiveRunningTask(newTask);
        setTaskInlineConfirmed({});

        try {
            const collected = await streamTaskInto(AGENT_STREAM_URL, {
                message: action.prompt,
                org_id: activeOrgId,
                thread_id: activeThread?.id,
                history: [],
                direct_action: true,
                parent_message_id: actualParentId,
                action_index: index,
            }, newTask);

            let hierarchyEv = collected.find(e => e.type === 'hierarchy_mapping_required');
            let pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
            let ligacaoEv = collected.find(e => e.type === 'tool_call' && e.tool === 'open_ligacao_view');
            let wasCancelled = userCancelledTaskRef.current;
            let allCollected = [...collected];

            // Modo batch: auto-confirma sem parar para pedir aprovação
            while (autoConfirm && pendingConfirm && !wasCancelled) {
                setActiveRunningTask((prev: any) => prev ? { ...prev, status: 'streaming' } : null);
                setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: 'streaming' }));
                const confirmCollected = await streamTaskInto(AGENT_CONFIRM_URL, {
                    action_id: pendingConfirm.action_id,
                    approved: true,
                    thread_id: activeThread?.id,
                }, null);
                allCollected = [...allCollected, ...confirmCollected];
                hierarchyEv = allCollected.find(e => e.type === 'hierarchy_mapping_required');
                pendingConfirm = confirmCollected.find(e => e.type === 'confirmation_required' && e.action_id);
                ligacaoEv = allCollected.find(e => e.type === 'tool_call' && e.tool === 'open_ligacao_view');
                wasCancelled = userCancelledTaskRef.current;
            }

            const failure = classifyFailure(allCollected);

            let finalStatus: TaskStatus = 'done';
            if (wasCancelled) {
                finalStatus = 'cancelled';
            } else if (hierarchyEv) {
                finalStatus = 'awaiting_mapping';
            } else if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            } else if (ligacaoEv) {
                finalStatus = 'streaming';
            } else if (failure) {
                finalStatus = failure;
            }

            setActiveRunningTask((prev: any) => prev ? { ...prev, status: finalStatus } : null);
            setApprovedSuggestedActions((prev: any) => ({
                ...prev,
                [taskKey]: finalStatus
            }));

            if (finalStatus !== 'streaming') {
                setIsLoading(false);
                setAgentStreaming(false);
            }

            const finalLogs = allCollected;

            if (actualParentId) {
                conversations.updateSuggestedActionStatus(actualParentId, index, finalStatus, finalLogs).catch(err => {
                    console.error('Failed to persist task status/logs', err);
                });
            }

            if (actualParentId) {
                setMessages(prev => prev.map(m => {
                    if (m.id !== actualParentId) return m;
                    const existingData = m.data || {};
                    const existingRuns = existingData.suggested_actions_runs || {};
                    return {
                        ...m,
                        data: {
                            ...existingData,
                            suggested_actions_runs: {
                                ...existingRuns,
                                [String(index)]: {
                                    ...(existingRuns[String(index)] || {}),
                                    status: finalStatus,
                                    logs: finalLogs,
                                },
                            },
                        },
                    };
                }));
            }
            
            if (finalStatus === 'done') {
                setTimeout(() => {
                    setActiveRunningTask((prev: any) => {
                        if (prev && prev.actionIndex === index) return null;
                        return prev;
                    });
                }, 1500);
            }
            
            if (activeOrgId) {
                conversations.listThreads(activeOrgId).then(setThreads).catch(() => {});
            }
        } catch {
            setActiveRunningTask((prev: any) => prev ? { ...prev, status: 'error' } : null);
            setApprovedSuggestedActions((prev: any) => ({
                ...prev,
                [taskKey]: 'error'
            }));
            setIsLoading(false);
            setAgentStreaming(false);
        }
    };

    /** Recupera os logs persistidos de uma execução anterior de uma suggested action. */
    const getPersistedTaskLogs = (actualParentId: string | undefined, index: number): AgentEvent[] => {
        if (!actualParentId) return [];
        const msg = messagesRef.current.find(m => m.id === actualParentId);
        const run = msg?.data?.suggested_actions_runs?.[index];
        if (!run?.logs) return [];
        if (typeof run.logs === 'string') {
            try {
                const parsed = JSON.parse(run.logs);
                return Array.isArray(parsed) ? parsed : [];
            } catch {
                return [];
            }
        }
        return Array.isArray(run.logs) ? run.logs : [];
    };

    /**
     * Refaz uma tarefa que falhou, informando ao agente o erro da tentativa anterior
     * para que ele use a própria inteligência e as ferramentas disponíveis para tentar
     * resolver a causa (em vez de simplesmente repetir a mesma chamada que já falhou).
     */
    const handleRetrySuggestedAction = async (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => {
        let actualParentId = parentMessageId;
        if (actualParentId && /^\d+$/.test(actualParentId)) {
            const realMsg = messagesRef.current.find(m =>
                m.logs?.some((e: any) => e.type === 'suggested_actions' && e.actions?.[index]?.label === action.label)
            );
            if (realMsg) actualParentId = realMsg.id;
        }

        const lastLogs = getPersistedTaskLogs(actualParentId, index);
        const errorEvent: any = [...lastLogs].reverse().find(
            (e: any) => e.type === 'error' || (e.type === 'tool_result' && e.ok === false && !e.cancelled)
        );
        const lastErrorMsg = errorEvent?.content || errorEvent?.summary || errorEvent?.data?.error || 'motivo não registrado nos logs';

        const retryPrompt = (
            `${action.prompt}\n\n` +
            `CONTEXTO DE FALHA ANTERIOR: a última tentativa desta ação falhou com o erro: "${lastErrorMsg}". ` +
            `Investigue a causa provável (parâmetros incorretos, dados faltantes, IDs desatualizados, registro já existente, etc.) ` +
            `e tente resolver usando as ferramentas disponíveis antes de repetir a mesma chamada que falhou. ` +
            `Se não for possível corrigir, explique objetivamente o motivo em vez de tentar de novo às cegas.`
        );

        await handleApproveSuggestedAction({ label: action.label, prompt: retryPrompt }, index, parentMessageId);
    };

    const handleOpenTaskConsole = (action: any, index: number, parentMessageId?: string) => {
        let logs: AgentEvent[] = [];
        if (action.logs) {
            if (typeof action.logs === 'string') {
                try {
                    const parsed = JSON.parse(action.logs);
                    logs = Array.isArray(parsed) ? parsed : [];
                } catch {}
            } else if (Array.isArray(action.logs)) {
                logs = action.logs;
            }
        }

        let actualParentId = parentMessageId;
        if (actualParentId && /^\d+$/.test(actualParentId)) {
            const realMsg = messagesRef.current.find(m => 
                m.logs?.some((e: any) => e.type === 'suggested_actions' && e.actions?.[index])
            );
            if (realMsg) actualParentId = realMsg.id;
        }

        if (logs.length === 0 && actualParentId) {
            const msg = messages.find(m => m.id === actualParentId);
            const run = msg?.data?.suggested_actions_runs?.[index];
            if (run && run.logs) {
                if (typeof run.logs === 'string') {
                    try {
                        const parsed = JSON.parse(run.logs);
                        logs = Array.isArray(parsed) ? parsed : [];
                    } catch {}
                } else if (Array.isArray(run.logs)) {
                    logs = run.logs;
                }
            }
        }

        const taskKey = `${actualParentId}-${index}`;
        const currentStatus = approvedSuggestedActions[taskKey] || action.status || 'done';

        if (activeRunningTask && activeRunningTask.parentMessageId === actualParentId && activeRunningTask.actionIndex === index) {
            setActiveRunningTask((prev: any) => prev ? { ...prev, isExpanded: !prev.isExpanded } : null);
            return;
        }

        setActiveRunningTask({
            label: action.label,
            prompt: action.prompt,
            status: currentStatus as TaskStatus,
            logs: logs,
            isExpanded: true,
            orgId: activeOrgId,
            threadId: activeThread?.id,
            actionIndex: index,
            parentMessageId: actualParentId,
        });
    };

    const handleTaskInlineConfirm = async (action_id: string, approved: boolean) => {
        if (!activeRunningTask) return;
        
        setTaskInlineConfirmed((prev: any) => ({ ...prev, [action_id]: approved }));

        setActiveRunningTask((prev: any) => prev ? { ...prev, status: 'streaming' } : null);

        let actualParentId = activeRunningTask.parentMessageId;
        if (actualParentId && /^\d+$/.test(actualParentId)) {
            const realMsg = messagesRef.current.find(m => 
                m.logs?.some((e: any) => e.type === 'suggested_actions' && e.actions?.[activeRunningTask.actionIndex])
            );
            if (realMsg) actualParentId = realMsg.id;
        }

        if (actualParentId) {
            const taskKey = `${actualParentId}-${activeRunningTask.actionIndex}`;
            setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: 'streaming' }));
        }
        setIsLoading(true);
        setAgentStreaming(true);

        try {
            const collected = await streamTaskInto(AGENT_CONFIRM_URL, {
                action_id,
                approved,
                thread_id: activeThread?.id,
            }, activeRunningTask);
            
            const pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
            const ligacaoEv = collected.find(e => e.type === 'tool_call' && e.tool === 'open_ligacao_view');
            const wasCancelled = userCancelledTaskRef.current;
            const failure = classifyFailure(collected);
            let finalStatus: TaskStatus = 'done';
            if (wasCancelled) {
                finalStatus = 'cancelled';
            } else if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            } else if (ligacaoEv) {
                finalStatus = 'streaming';
            } else if (failure) {
                finalStatus = failure;
            }

            setActiveRunningTask((prev: any) => prev ? { ...prev, status: finalStatus } : null);
            if (actualParentId) {
                const { actionIndex: aidx } = activeRunningTask;
                const pid = actualParentId;
                const taskKey = `${pid}-${aidx}`;
                setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: finalStatus }));

                const allLogs = [...(activeRunningTask.logs || []), ...collected];

                conversations.updateSuggestedActionStatus(pid, aidx, finalStatus, allLogs).catch(err => {
                    console.error('Failed to persist task status/logs', err);
                });

                setMessages(prev => prev.map(m => {
                    if (m.id !== pid) return m;
                    const existingData = m.data || {};
                    const existingRuns = existingData.suggested_actions_runs || {};
                    return {
                        ...m,
                        data: {
                            ...existingData,
                            suggested_actions_runs: {
                                ...existingRuns,
                                [String(aidx)]: {
                                    ...(existingRuns[String(aidx)] || {}),
                                    status: finalStatus,
                                    logs: allLogs,
                                },
                            },
                        },
                    };
                }));
            }

            if (finalStatus !== 'streaming') {
                setIsLoading(false);
                setAgentStreaming(false);
            }

            if (finalStatus === 'done') {
                const currentIdx = activeRunningTask.actionIndex;
                setTimeout(() => {
                    setActiveRunningTask((prev: any) => {
                        if (prev && prev.actionIndex === currentIdx) return null;
                        return prev;
                    });
                }, 1500);
            }
        } catch {
            setActiveRunningTask((prev: any) => prev ? { ...prev, status: 'error' } : null);
            if (activeRunningTask.parentMessageId) {
                const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
                setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: 'error' }));
            }
            setIsLoading(false);
            setAgentStreaming(false);
        }
    };

    const handleTaskMappingComplete = async (contacts: MappedContact[]) => {
        if (!activeRunningTask) return;

        const hierarchyEv = activeRunningTask.logs.find(e => e.type === 'hierarchy_mapping_required');
        if (!hierarchyEv) return;

        setActiveRunningTask((prev: any) => prev ? { ...prev, status: 'streaming' } : null);
        if (activeRunningTask.parentMessageId) {
            const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
            setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: 'streaming' }));
        }

        const contactsSummary = contacts.length > 0
            ? `Contatos reais encontrados pelo mapeamento (${contacts.length} total): ` +
              contacts.slice(0, 8).map((c: MappedContact) =>
                  `${c.name} (${c.role}${c.email ? ', ' + c.email : ''}${c.temperature ? ', temp=' + c.temperature : ''})`
              ).join(' | ')
            : 'Nenhum contato foi encontrado no mapeamento.';

        const preTaskClause = hierarchyEv.pre_task_id
            ? `Marque a tarefa de rastreamento pre_task_id=${hierarchyEv.pre_task_id} como concluída com pipedrive_update_task done=true. `
            : '';

        const continuation = (
            `EXECUTE ESTAS ETAPAS EM ORDEM:\n` +
            `1. Mapeamento de hierarquia concluído para "${hierarchyEv.org_name}". ${contactsSummary}\n` +
            `2. Para cada contato relevante acima (priorize decisores de compras, level alto ou temperature=hot/warm), ` +
            `sugira criá-lo no Pipedrive com pipedrive_create_person` +
            (hierarchyEv.deal_id ? ` vinculado ao deal_id=${hierarchyEv.deal_id}` : '') + `.\n` +
            (preTaskClause ? `3. ${preTaskClause}\n` : '') +
            (hierarchyEv.activity_id
                ? `4. A atividade original activity_id=${hierarchyEv.activity_id} NÃO deve ser marcada como concluída — ela só termina após a ligação real. Sugira criar uma nova tarefa "Ligar para [nome do decisor]".\n`
                : '') +
            `PROIBIDO: NÃO invente dados. Use APENAS os contatos listados acima.`
        );

        try {
            const newEvents = await streamTaskInto(AGENT_STREAM_URL, {
                message: continuation,
                org_id: activeOrgId,
                thread_id: activeThread?.id,
                history: [],
                direct_action: true,
                parent_message_id: activeRunningTask.parentMessageId,
                action_index: activeRunningTask.actionIndex,
            }, activeRunningTask);

            const pendingConfirm = newEvents.find(e => e.type === 'confirmation_required' && e.action_id);
            const wasCancelled = userCancelledTaskRef.current;
            const failure = classifyFailure(newEvents);
            let finalStatus: TaskStatus = 'done';
            if (wasCancelled) {
                finalStatus = 'cancelled';
            } else if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            } else if (failure) {
                finalStatus = failure;
            }
            setActiveRunningTask((prev: any) => prev ? { ...prev, status: finalStatus } : null);
            if (activeRunningTask.parentMessageId) {
                const { parentMessageId: pid, actionIndex: aidx } = activeRunningTask;
                const taskKey = `${pid}-${aidx}`;
                setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: finalStatus }));

                const allLogs = [...(activeRunningTask.logs || []), ...newEvents];

                conversations.updateSuggestedActionStatus(pid, aidx, finalStatus, allLogs).catch(err => {
                    console.error('Failed to persist task status/logs', err);
                });

                setMessages(prev => prev.map(m => {
                    if (m.id !== pid) return m;
                    const existingData = m.data || {};
                    const existingRuns = existingData.suggested_actions_runs || {};
                    return {
                        ...m,
                        data: {
                            ...existingData,
                            suggested_actions_runs: {
                                ...existingRuns,
                                [String(aidx)]: {
                                    ...(existingRuns[String(aidx)] || {}),
                                    status: finalStatus,
                                    logs: allLogs,
                                },
                            },
                        },
                    };
                }));
            }
            if (finalStatus === 'done') {
                const currentIdx = activeRunningTask.actionIndex;
                setTimeout(() => {
                    setActiveRunningTask((prev: any) => {
                        if (prev && prev.actionIndex === currentIdx) return null;
                        return prev;
                    });
                }, 1500);
            }
        } catch {
            setActiveRunningTask((prev: any) => prev ? { ...prev, status: 'error' } : null);
            if (activeRunningTask.parentMessageId) {
                const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
                setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: 'error' }));
            }
        }
    };

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [isAtBottom, setIsAtBottom] = useState(true);

    const handleScroll = useCallback(() => {
        const el = scrollContainerRef.current;
        if (!el) return;
        const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        setIsAtBottom(distanceFromBottom < 80);
    }, []);

    useEffect(() => {
        if (isAtBottom) {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isAtBottom]);

    useEffect(() => {
        if (finalTranscript) {
            setInputValue(prev => {
                const hasSpace = prev.length > 0 && prev[prev.length - 1] !== ' ';
                return prev + (hasSpace ? ' ' : '') + finalTranscript;
            });
            clearTranscript();
        }
    }, [finalTranscript, clearTranscript, setInputValue]);

    useEffect(() => {
        if (pipedriveCooldown > 0) {
            const timer = setInterval(() => setPipedriveCooldown(p => Math.max(0, p - 1)), 1000);
            return () => clearInterval(timer);
        }
    }, [pipedriveCooldown]);

    useEffect(() => {
        const syncPreference = async () => {
            try {
                await ai.updatePreference(model, strictMode);
                localStorage.setItem('ai_preferred_model', model);
                localStorage.setItem('ai_strict_mode', String(strictMode));
            } catch (err) {
                console.warn('[ChatPanel] Erro ao sincronizar preferência:', err);
                localStorage.setItem('ai_preferred_model', model);
                localStorage.setItem('ai_strict_mode', String(strictMode));
            }
        };
        void syncPreference();
    }, [model, strictMode]);

    const executeAgent = async (text: string, threadId: string, historyForApi: any[], directAction: boolean = false) => {
        store.setIsLoading(activeOrgId, threadId, true);
        store.setAgentEvents(activeOrgId, threadId, []);
        store.setAgentStreaming(activeOrgId, threadId, true);
        streamingThreadIdRef.current[String(activeOrgId || 0)] = threadId;

        const msgId = (Date.now() + 1).toString();

        store.setMessages(activeOrgId, threadId, prev => [...prev, {
            id: msgId,
            role: 'assistant' as const,
            content: '',
            timestamp: new Date(),
            agentEvents: [] as any[],
            isAgent: true,
            agentStreaming: true,
        }]);

        if (abortControllersRef.current[threadId]) {
            abortControllersRef.current[threadId].abort();
        }
        const controller = new AbortController();
        abortControllersRef.current[threadId] = controller;

        let hasMappingRequired = false;
        let hasConfirmationRequired = false;
        let hasLigacaoView = false;

        let apiMessage = text;
        if (selectedOrgId && selectedOrgName) {
            apiMessage = `[ALERTA DE CONTEXTO DO SISTEMA: O usuário está na página da empresa "${selectedOrgName}" (org_id=${selectedOrgId}).\nREGRA CRÍTICA: Se o usuário pedir para atualizar ou concluir uma tarefa e NÃO fornecer o ID explícito na mensagem atual, VOCÊ É ESTRITAMENTE PROIBIDO de adivinhar ou usar IDs de tarefas do histórico. Você DEVE obrigatoriamente chamar a ferramenta \`pipedrive_get_activities\` com org_id=${selectedOrgId} para descobrir o ID correto antes de atualizar. Não atualize atividades cegamente.]\n\n${text}`;
        }

        let activeMsgId = msgId;

        try {
            const response = await fetch(AGENT_STREAM_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: apiMessage, history: historyForApi, org_id: selectedOrgId, thread_id: threadId, direct_action: directAction }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                const errText = response.ok ? 'Sem corpo na resposta' : `Erro ${response.status}`;
                store.setMessages(activeOrgId, threadId, prev => prev.map(m =>
                    m.id === msgId ? { ...m, content: `Não consegui processar: ${errText}`, agentStreaming: false } : m
                ));
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const collectedEvents: any[] = [];

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const event = JSON.parse(line);
                        collectedEvents.push(event);

                        if (event.type === 'tool_result' && event.ok) {
                            const tool = event.tool || '';
                            const isWriteTool = tool.includes('create') || tool.includes('update') || tool.includes('send') || tool.includes('reply');

                            if ((tool.startsWith('pipedrive_') || tool.includes('send') || tool.includes('reply')) && isWriteTool) {
                                window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
                                if (tool === 'pipedrive_update_task') {
                                    try {
                                        const summary = event.summary || '';
                                        if (summary.toLowerCase().includes('concluída') || summary.toLowerCase().includes('done')) {
                                            window.dispatchEvent(new CustomEvent('crm_task_completed'));
                                        } else {
                                            window.dispatchEvent(new CustomEvent('crm_task_uncompleted'));
                                        }
                                    } catch {}
                                }
                                refreshActivities();
                            }
                        }

                        if (event.type === 'model_active') {
                            if (!strictMode) store.setLiveModel(activeOrgId, threadId, event.provider as AIModel);
                            store.setModelActivity(activeOrgId, threadId, prev => {
                                const last = prev[prev.length - 1];
                                if (last?.type === 'model_active' && last.provider === event.provider) return prev;
                                const extra: ModelActivityEvent[] = [];
                                if (last && last.provider !== event.provider && event.provider) {
                                    extra.push({ id: ++modelActivityIdRef.current, type: 'model_switch', provider: event.provider as AIModel, model: event.model, timestamp: Date.now() });
                                }
                                return [...prev, ...extra, { id: ++modelActivityIdRef.current, type: 'model_active', provider: event.provider as AIModel, model: event.model, timestamp: Date.now() }];
                            });
                        }

                        if (event.type === 'rate_wait') {
                            store.setModelActivity(activeOrgId, threadId, prev => [...prev, { id: ++modelActivityIdRef.current, type: 'rate_wait', provider: event.provider as AIModel | undefined, model: event.model, wait_sec: event.wait_sec, reason: event.reason, timestamp: Date.now() }]);
                        }
                        if (event.type === 'context_overflow') {
                            store.setModelActivity(activeOrgId, threadId, prev => [...prev, { id: ++modelActivityIdRef.current, type: 'context_overflow', model: event.model, estimated_tokens: event.estimated_tokens, limit: event.limit, timestamp: Date.now() }]);
                        }

                        if (event.type === 'message_saved' && event.message_id) {
                            activeMsgId = event.message_id;
                            store.setMessages(activeOrgId, threadId, prev => prev.map(m =>
                                (m.id === msgId || m.id === activeMsgId) ? { ...m, id: activeMsgId, agentEvents: [...collectedEvents] } : m
                            ));
                            continue;
                        }

                        store.setMessages(activeOrgId, threadId, prev => prev.map(m =>
                            (m.id === msgId || m.id === activeMsgId) ? { ...m, agentEvents: [...collectedEvents] } : m
                        ));
                    } catch { /* ignore */ }
                }
            }

            for (const ev of collectedEvents) {
                if (ev.type === 'hierarchy_mapping_required') {
                    hasMappingRequired = true;
                    localStorage.setItem('pending-hierarchy-continuation', JSON.stringify({
                        thread_id: activeThread?.id || null,
                        org_id: selectedOrgId || null,
                        org_name: selectedOrgName || ev.org_name || null,
                        event: ev,
                    }));
                }
                if (ev.type === 'confirmation_required') hasConfirmationRequired = true;
                if (ev.type === 'tool_call' && ev.tool === 'open_ligacao_view') {
                    hasLigacaoView = true;
                }
            }

            store.setLiveModel(activeOrgId, threadId, null);
            const hadWaits = store.getSession(activeOrgId, threadId).modelActivity.some(e => e.type === 'rate_wait' || e.type === 'context_overflow');
            if (hadWaits) {
                setTimeout(() => store.setModelActivity(activeOrgId, threadId, []), 3000);
            } else {
                store.setModelActivity(activeOrgId, threadId, []);
            }
        } catch (err) {
            if ((err as any)?.name === 'AbortError') {
                console.log('[Agent] Stream cancelado pelo usuário');
            } else {
                console.error('[Agent] Erro:', err);
            }
        } finally {
            if (abortControllersRef.current[threadId] === controller) {
                delete abortControllersRef.current[threadId];
            }
            
            const _orgKey = String(activeOrgId || 0);
            if (streamingThreadIdRef.current[_orgKey] === threadId) {
                streamingThreadIdRef.current[_orgKey] = null;
            }
            
            store.setMessages(activeOrgId, threadId, prev => prev.map(m =>
                (m.id === msgId || m.id === activeMsgId) ? { ...m, agentStreaming: (hasMappingRequired || hasLigacaoView) ? true : false } : m
            ));

            if (!hasMappingRequired && !hasConfirmationRequired && !hasLigacaoView) {
                store.setIsLoading(activeOrgId, threadId, false);
                store.setAgentStreaming(activeOrgId, threadId, false);
            }

            if (threadId) {
                void refreshMessages(threadId);
            }
        }
    };

    const handleMainChatMappingDone = async (contacts: any[], event?: AgentEvent) => {
        localStorage.removeItem('pending-hierarchy-continuation');
        const orgId = selectedOrgId || event?.org_id;
        const orgName = event?.org_name || 'a empresa';

        const preTaskClause = event?.pre_task_id
            ? `Marque a tarefa de rastreamento pre_task_id=${event.pre_task_id} as concluída com pipedrive_update_task done=true. `
            : '';
        const activityClause = event?.activity_id
            ? ` A atividade original activity_id=${event.activity_id} NÃO deve ser marcada como concluída.`
            : '';
        const dealClause = event?.deal_id ? ` atrelado ao negócio deal_id=${event.deal_id}` : '';

        const isLegalEntity = (name: string): boolean => {
            const n = (name || '').toUpperCase();
            const pjTerms = [
                'LTDA', 'S.A.', 'S/A', 'PARTICIPACOES', 'PARTICIPACAO', 'PARTICIPACÕES', 'PARTICIPACÃO', 
                'HOLDING', 'EMPREENDIMENTOS', 'ADMINISTRADORA', 'INVESTIMENTOS', 'GRUPO', 'CORP', 'INC',
                'COOPERATIVA', 'ASSOCIACAO', 'ASSOCIAÇÃO', 'FUNDACAO', 'FUNDAÇÃO', 'SERVICOS', 'SERVIÇOS'
            ];
            return pjTerms.some(term => n.includes(term));
        };

        const approvedContacts = contacts.filter((c: any) => {
            if (isLegalEntity(c.name)) return false;
            const r = (c.role || '').toLowerCase();
            const d = (c.department || '').toLowerCase();
            if (r.includes('reprovado') || d.includes('reprovado')) return false;
            if (r.includes('análise humana') || r.includes('analise humana')) return false;
            return true;
        });

        const contactsSummary = approvedContacts.length > 0
            ? approvedContacts.map((c: any) => `- ${c.name} (${c.role}${c.department ? ', ' + c.department : ''}${c.email ? ', ' + c.email : ''}${c.temperature ? ', temp=' + c.temperature : ''}${c.decision_maker ? ', DECISOR' : ''})`).join('\n')
            : '';

        const baseProhibition = `REGRA CRÍTICA: Estes contatos são leads frios do LinkedIn — PROIBIDO chamar whatsapp_get_messages, email_get_contact_history ou whatsapp_list_chats para eles.\n`;

        let taskInstruction: string;

        if (approvedContacts.length === 0) {
            taskInstruction =
                `Nenhum contato decisor válido foi encontrado ou aprovado no mapeador de hierarquia.\n` +
                `Você deve simplesmente informar ao usuário de forma clara que nenhum contato relevante foi encontrado para a empresa "${orgName}".\n` +
                `NÃO tente criar nenhum contato no Pipedrive. NÃO crie novas tarefas nem chame find_company_contact. Apenas informe o resultado negativo e conclua a tarefa.`;
        } else {
            const contactsBlock = `Contatos aprovados pelo usuário (${approvedContacts.length}):\n${contactsSummary}`;
            taskInstruction =
                `${contactsBlock}\n\n` +
                `Sua missão agora:\n` +
                `1. Chame a ferramenta \`generate_prospecting_plan\` (com org_id=${orgId}, force_regenerate=true) para analisar os contatos aprovados e gerar o plano de prospecção SPIN Selling.\n` +
                `2. No próprio plano de prospecção, defina e justifique qual é o melhor contato decisor a ser abordado.\n` +
                `3. Após gerar e exibir o plano de prospecção, sugira cadastrar esse decisor principal no Pipedrive (gerando a sugestão de chamar pipedrive_create_person com org_id=${orgId}${dealClause} para o contato ideal) e proponha as próximas ações estratégicas usando a ferramenta \`suggest_next_actions\`.\n\n` +
                `⚠️ REGRA CRÍTICA: Você está ESTRITAMENTE PROIBIDO de chamar \`pipedrive_create_person\` ou \`generate_sales_message\` antes de gerar o plano de prospecção. O plano de prospecção é a prioridade absoluta agora.`;
        }

        const continuation = (
            `[SISTEMA]: Mapeamento de hierarquia concluído para "${orgName}". ${approvedContacts.length} contato(s) aprovados pelo usuário.\n` +
            baseProhibition +
            taskInstruction +
            (preTaskClause ? `\n${preTaskClause}` : '') +
            activityClause
        );

        const targetMsg = messages.find(m => m.agentEvents && m.agentEvents.some(e => e.type === 'hierarchy_mapping_required'));
        if (!targetMsg || !targetMsg.id) {
            store.setIsLoading(activeOrgId, activeThread?.id || 'global', false);
            store.setAgentStreaming(activeOrgId, activeThread?.id || 'global', false);
            setTimeout(() => handleSendMessage(continuation, [], true), 0);
            return;
        }

        let targetMsgId = targetMsg.id;
        const existingEvents = targetMsg.agentEvents || [];

        store.setIsLoading(activeOrgId, activeThread?.id || 'global', true);
        store.setAgentStreaming(activeOrgId, activeThread?.id || 'global', true);
        store.setMessages(activeOrgId, activeThread?.id || 'global', prev => prev.map(m => m.id === targetMsgId ? { ...m, agentStreaming: true } : m));

        const threadId = activeThread?.id || 'global';
        if (abortControllersRef.current[threadId]) {
            abortControllersRef.current[threadId].abort();
        }
        const controller = new AbortController();
        abortControllersRef.current[threadId] = controller;

        try {
            const response = await fetch(AGENT_STREAM_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: continuation, direct_action: true, org_id: selectedOrgId, thread_id: threadId }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                store.setMessages(activeOrgId, threadId, prev => prev.map(m => m.id === targetMsgId ? { ...m, agentStreaming: false } : m));
                store.setIsLoading(activeOrgId, threadId, false);
                store.setAgentStreaming(activeOrgId, threadId, false);
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const collectedEvents: any[] = [];

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const eventObj = JSON.parse(line);
                        collectedEvents.push(eventObj);

                        if (eventObj.type === 'model_active') {
                            if (!strictMode) store.setLiveModel(activeOrgId, threadId, eventObj.provider as AIModel);
                            store.setModelActivity(activeOrgId, threadId, prev => {
                                const last = prev[prev.length - 1];
                                if (last?.type === 'model_active' && last.provider === eventObj.provider) return prev;
                                const extra: ModelActivityEvent[] = [];
                                if (last && last.provider !== eventObj.provider && eventObj.provider) {
                                    extra.push({ id: ++modelActivityIdRef.current, type: 'model_switch', provider: eventObj.provider as AIModel, model: eventObj.model, timestamp: Date.now() });
                                }
                                return [...prev, ...extra, { id: ++modelActivityIdRef.current, type: 'model_active', provider: eventObj.provider as AIModel, model: eventObj.model, timestamp: Date.now() }];
                            });
                        }

                        if (eventObj.type === 'rate_wait') {
                            store.setModelActivity(activeOrgId, threadId, prev => [...prev, { id: ++modelActivityIdRef.current, type: 'rate_wait', provider: eventObj.provider as AIModel | undefined, model: eventObj.model, wait_sec: eventObj.wait_sec, reason: eventObj.reason, timestamp: Date.now() }]);
                        }
                        if (eventObj.type === 'context_overflow') {
                            store.setModelActivity(activeOrgId, threadId, prev => [...prev, { id: ++modelActivityIdRef.current, type: 'context_overflow', model: eventObj.model, estimated_tokens: eventObj.estimated_tokens, limit: eventObj.limit, timestamp: Date.now() }]);
                        }

                        if (eventObj.type === 'message_saved' && eventObj.message_id) {
                            const prevId = targetMsgId;
                            targetMsgId = eventObj.message_id;
                            store.setMessages(activeOrgId, threadId, prev => prev.map(m =>
                                (m.id === prevId || m.id === targetMsgId) ? { ...m, id: targetMsgId, agentEvents: [...existingEvents, ...collectedEvents] } : m
                            ));
                            continue;
                        }

                        store.setMessages(activeOrgId, threadId, prev => prev.map(m =>
                            m.id === targetMsgId ? { ...m, agentEvents: [...existingEvents, ...collectedEvents] } : m
                        ));
                    } catch { /* ignore */ }
                }
            }

            store.setLiveModel(activeOrgId, threadId, null);
            const hadWaits = store.getSession(activeOrgId, threadId).modelActivity.some(e => e.type === 'rate_wait' || e.type === 'context_overflow');
            if (hadWaits) {
                setTimeout(() => store.setModelActivity(activeOrgId, threadId, []), 3000);
            } else {
                store.setModelActivity(activeOrgId, threadId, []);
            }
        } catch (err) {
            console.error('[Agent Continuation] Erro:', err);
        } finally {
            if (abortControllersRef.current[threadId] === controller) {
                delete abortControllersRef.current[threadId];
            }
            const _contOrgKey = String(activeOrgId || 0);
            if (streamingThreadIdRef.current[_contOrgKey] === threadId) {
                streamingThreadIdRef.current[_contOrgKey] = null;
            }
            store.setMessages(activeOrgId, threadId, prev => prev.map(m => m.id === targetMsgId ? { ...m, agentStreaming: false } : m));
            store.setIsLoading(activeOrgId, threadId, false);
            store.setAgentStreaming(activeOrgId, threadId, false);
        }
    };

    const handleAgentConfirm = async (action_id: string, approved: boolean, file?: File) => {
        setAgentConfirmedActions(prev => ({ ...prev, [action_id]: approved }));

        setMessages(prev => prev.map(m => {
            if (!m.isAgent || !m.agentEvents) return m;
            const hasAction = m.agentEvents.some((e: any) => e.action_id === action_id);
            if (!hasAction) return m;
            return { ...m, agentConfirmedActions: { ...(m.agentConfirmedActions || {}), [action_id]: approved } };
        }));

        const threadId = activeThread?.id || 'global';
        setIsLoading(true);
        setAgentStreaming(true);
        streamingThreadIdRef.current[String(activeOrgId || 0)] = threadId;
        
        let attachment_path = undefined;
        if (file && approved) {
            try {
                const formData = new FormData();
                formData.append('file', file);
                const baseUrl = AGENT_CONFIRM_URL.replace('/confirm', '');
                const uploadRes = await fetch(`${baseUrl}/upload`, {
                    method: 'POST',
                    body: formData,
                });
                if (uploadRes.ok) {
                    const uploadData = await uploadRes.json();
                    attachment_path = uploadData.attachment_path;
                } else {
                    console.error('[Agent Confirm] Erro no upload:', uploadRes.status);
                }
            } catch (err) {
                console.error('[Agent Confirm] Falha no upload:', err);
            }
        }

        const msgId = (Date.now() + 2).toString();
        setMessages(prev => [...prev, {
            id: msgId,
            role: 'assistant' as const,
            content: '',
            timestamp: new Date(),
            agentEvents: [],
            isAgent: true,
            agentStreaming: true,
        }]);
        if (abortControllersRef.current[threadId]) {
            abortControllersRef.current[threadId].abort();
        }
        const controller = new AbortController();
        abortControllersRef.current[threadId] = controller;

        let activeMsgId = msgId;

        try {
            const response = await fetch(AGENT_CONFIRM_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action_id, approved, thread_id: threadId, attachment_path }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                const errText = response.ok ? 'Sem corpo na resposta' : `Erro ${response.status}`;
                setMessages(prev => prev.map(m =>
                    m.id === msgId ? { ...m, content: `Falha ao confirmar ação: ${errText}`, agentStreaming: false } : m
                ));
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const collectedEvents: any[] = [];

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const event = JSON.parse(line);
                        collectedEvents.push(event);

                        if (event.type === 'tool_result' && event.ok) {
                            const tool = event.tool || '';
                            const isWriteTool = tool.includes('create') || tool.includes('update') || tool.includes('send') || tool.includes('reply');

                            if ((tool.startsWith('pipedrive_') || tool.includes('send') || tool.includes('reply')) && isWriteTool) {
                                window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
                                if (tool === 'pipedrive_update_task') {
                                    try {
                                        const summary = event.summary || '';
                                        if (summary.toLowerCase().includes('concluída') || summary.toLowerCase().includes('done')) {
                                            window.dispatchEvent(new CustomEvent('crm_task_completed'));
                                        } else {
                                            window.dispatchEvent(new CustomEvent('crm_task_uncompleted'));
                                        }
                                    } catch {}
                                }
                                refreshActivities();
                            }
                        }

                        if (event.type === 'message_saved' && event.message_id) {
                            activeMsgId = event.message_id;
                            setMessages(prev => prev.map(m =>
                                (m.id === msgId || m.id === activeMsgId) ? { ...m, id: activeMsgId, agentEvents: [...collectedEvents] } : m
                            ));
                            continue;
                        }

                        store.setMessages(activeOrgId, threadId, prev => prev.map(m =>
                            (m.id === msgId || m.id === activeMsgId) ? { ...m, agentEvents: [...collectedEvents] } : m
                        ));
                    } catch { /* ignore */ }
                }
            }

            store.setMessages(activeOrgId, threadId, prev => prev.map(m =>
                (m.id === msgId || m.id === activeMsgId) ? { ...m, agentEvents: [...collectedEvents], agentStreaming: false } : m
            ));
        } catch (err) {
            if ((err as any)?.name === 'AbortError') {
                console.log('[Agent Confirm] Stream cancelado pelo usuário');
            } else {
                console.error('[Agent] Confirm error:', err);
            }
        } finally {
            if (abortControllersRef.current[threadId] === controller) {
                delete abortControllersRef.current[threadId];
            }
            const _confirmOrgKey = String(activeOrgId || 0);
            if (streamingThreadIdRef.current[_confirmOrgKey] === threadId) {
                streamingThreadIdRef.current[_confirmOrgKey] = null;
            }

            setMessages(prev => {
                const targetMsg = prev.find(m => m.id === msgId);
                const isLigacaoOpen = targetMsg?.agentEvents?.some(e => e.type === 'tool_call' && e.tool === 'open_ligacao_view');
                if (!isLigacaoOpen) {
                    store.setIsLoading(activeOrgId, threadId, false);
                    store.setAgentStreaming(activeOrgId, threadId, false);
                }
                return prev;
            });
        }
    };

    const handleRegenerate = async (fromMessageId?: string) => {
        if (isLoading) return;

        let lastUserMsg;
        let lastUserMsgIndex;

        if (fromMessageId) {
            const msgIndex = messages.findIndex(m => m.id === fromMessageId);
            if (msgIndex === -1) return;
            
            const priorUserMessages = messages.slice(0, msgIndex).filter(m => m.role === 'user');
            if (priorUserMessages.length === 0) return;
            
            lastUserMsg = priorUserMessages[priorUserMessages.length - 1];
            lastUserMsgIndex = messages.indexOf(lastUserMsg);
        } else {
            const userMessages = messages.filter(m => m.role === 'user');
            if (userMessages.length === 0) return;
            lastUserMsg = userMessages[userMessages.length - 1];
            lastUserMsgIndex = messages.lastIndexOf(lastUserMsg);
        }

        const threadId = await ensureThread();
        if (!threadId) return;

        const newHistory = messages.slice(0, lastUserMsgIndex + 1);
        const messagesIncludingLastAssistant = messages.slice(0, lastUserMsgIndex + 2);
        const historyForApi = messagesIncludingLastAssistant.slice(-6).map(m => ({ role: m.role, content: m.content }));
        
        setMessages(newHistory);
        await executeAgent(lastUserMsg.content, threadId, historyForApi);
    };

    const handleApproveAction = async (actionId: string) => {
        setApprovalStatuses(prev => ({ ...prev, [actionId]: 'approving' }));
        try {
            await ai.agentAction({ action_id: actionId, approved: true, thread_id: activeThread?.id });
            setApprovalStatuses(prev => ({ ...prev, [actionId]: 'approved' }));
            setTimeout(refreshActivities, 600);
        } catch {
            setApprovalStatuses(prev => ({ ...prev, [actionId]: 'pending' }));
        }
    };

    const handleRejectAction = async (actionId: string) => {
        setApprovalStatuses(prev => ({ ...prev, [actionId]: 'rejected' }));
        try {
            await ai.agentAction({ action_id: actionId, approved: false, thread_id: activeThread?.id });
        } catch { /* silent */ }
    };


    useEffect(() => {
        const handleAgentPrompt = (e: Event) => {
            const customEvent = e as CustomEvent<{ prompt: string, direct_action?: boolean }>;
            if (customEvent.detail && customEvent.detail.prompt) {
                handleSendMessage(customEvent.detail.prompt, [], false, customEvent.detail.direct_action);
            }
        };
        window.addEventListener('submit_agent_prompt', handleAgentPrompt);
        return () => {
            window.removeEventListener('submit_agent_prompt', handleAgentPrompt);
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [messages, activeOrgId, activeThread]);

    useEffect(() => {
        const pending = localStorage.getItem('pending-hierarchy-continuation');
        const activeJob = localStorage.getItem(`active-discovery-job-${activeOrgId}`);
        if (!pending || !activeJob) return;

        try {
            const jobData = JSON.parse(activeJob);
            if (jobData && jobData.chatPrompted === false) {
                return;
            }
        } catch {}

        const isReload = !sessionStorage.getItem('chat-session-active');
        sessionStorage.setItem('chat-session-active', '1');
        if (!isReload) return;

        let ctx: any;
        try { ctx = JSON.parse(pending); } catch { return; }

        setIsLoading(true);
        setAgentStreaming(true);

        const handleScanDone = (e: Event) => {
            const detail = (e as CustomEvent).detail || {};
            const eventOrgId = detail.orgId;
            if (eventOrgId && Number(eventOrgId) !== Number(activeOrgId)) {
                return;
            }
            if (detail.chatPrompted === false) {
                return;
            }
            window.removeEventListener('hierarchy_scan_done', handleScanDone);
            const contacts = detail.contacts || [];
            handleMainChatMappingDone(contacts, ctx.event as AgentEvent);
        };

        window.addEventListener('hierarchy_scan_done', handleScanDone);
        window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));

        return () => window.removeEventListener('hierarchy_scan_done', handleScanDone);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeOrgId]);

    useEffect(() => {
        const handleCallEnded = (e: any) => {
            const threadId = activeThreadIdRef.current || 'global';
            store.setMessages(activeOrgId, threadId, prev => prev.map(m => ({ ...m, agentStreaming: false })));
            store.setIsLoading(activeOrgId, threadId, false);
            store.setAgentStreaming(activeOrgId, threadId, false);

            const { contactName, transcript: callTranscript } = e.detail || {};
            
            const transcriptText = Array.isArray(callTranscript) 
                ? callTranscript.map((m: any) => `[${m.role}]: ${m.text}`).join('\n')
                : "Sem transcrição disponível.";

            const text = `[ALERTA DE CONTEXTO: LIGAÇÃO FINALIZADA]
A ligação com ${contactName || "o contato"} terminou.

### TRANSCRIÇÃO DA CONVERSA:
${transcriptText}

### SUA MISSÃO AGORA:
1. **Resuma** os pontos principais discutidos.
2. **Identifique** compromissos, reuniões agendadas ou dores mencionadas.
3. **Próximos Passos (OBRIGATÓRIO)**: EXECUTE IMEDIATAMENTE as ações concretas no CRM usando as ferramentas disponíveis (ex: 'pipedrive_update_task' para concluir a tarefa atual, 'pipedrive_create_note' para salvar o resumo, 'pipedrive_create_task' para agendar follow-up).
4. **Inteligência**: NÃO crie tarefas que já existem no Pipedrive. Verifique o histórico de atividades primeiro se necessário.
5. **Estratégia (Plano e Fit)**: Se a ligação revelou um NOVO decisor principal, instrua a recriar o plano de prospecção ('generate_prospecting_plan'). Se a ligação revelou que a empresa NÃO TEM FIT com nosso produto, chame 'pipedrive_update_deal' com status 'lost'.
6. **Ação CRÍTICA**: VOCÊ ESTÁ PROIBIDO de apenas responder com texto. VOCÊ DEVE EMITIR AS CHAMADAS DE FERRAMENTA (tool calls) PARA O CRM AGORA MESMO.
`;
            handleSendMessage(text, [], false);
        };
        window.addEventListener('call_ended', handleCallEnded);
        return () => window.removeEventListener('call_ended', handleCallEnded);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeOrgId, messages, activeThread]);

    // Pre-populate input with instruction when company has no prospecting plan and chat is in empty welcome state.
    // If the company has a prospecting plan, clear the default instruction from the input if it is present.
    useEffect(() => {
        if (activeOrgId) {
            const tId = activeThread?.id;
            const currentSession = store.getSession(activeOrgId, tId);
            if (!prospectingContext) {
                const isEmptyWelcome = messages.length === 0 || (messages.length === 1 && messages[0].id === 'welcome');
                if (isEmptyWelcome) {
                    if (!currentSession.inputValue || currentSession.inputValue.trim() === '') {
                        store.setInputValue(activeOrgId, tId, "Gerar plano de prospecção para esta empresa");
                    }
                }
            } else {
                if (currentSession.inputValue === "Gerar plano de prospecção para esta empresa") {
                    store.setInputValue(activeOrgId, tId, "");
                }
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeOrgId, activeThread?.id, prospectingContext, messages.length]);

    // ─── Batch execution ─────────────────────────────────────────────────────────

    const handleToggleBatchItem = useCallback((messageId: string, actionIndex: number, action: { label: string; prompt: string; categoria?: string }) => {
        const currentQueue = store.getSession(activeOrgId, activeThreadId).batchQueue || [];
        const exists = currentQueue.some(i => i.messageId === messageId && i.actionIndex === actionIndex);
        if (exists) {
            setBatchQueue(currentQueue.filter(i => !(i.messageId === messageId && i.actionIndex === actionIndex)));
        } else {
            setBatchQueue([...currentQueue, { messageId, actionIndex, action }]);
        }
    }, [store, activeOrgId, activeThreadId, setBatchQueue]);

    const handleClearBatch = useCallback(() => {
        setBatchQueue([]);
    }, [setBatchQueue]);

    const handleExecuteBatch = useCallback(async () => {
        const currentQueue = store.getSession(activeOrgId, activeThreadId).batchQueue || [];
        if (isBatchRunning || currentQueue.length === 0) return;
        setIsBatchRunning(true);
        setBatchRunningSnapshot(currentQueue);
        setBatchCurrentIndex(0);
        setBatchQueue([]);
        for (let i = 0; i < currentQueue.length; i++) {
            setBatchCurrentIndex(i);
            const item = currentQueue[i];
            await handleApproveSuggestedAction(item.action, item.actionIndex, item.messageId, true);
            await new Promise(resolve => setTimeout(resolve, 800));
        }
        setIsBatchRunning(false);
        setBatchRunningSnapshot([]);
        setBatchCurrentIndex(-1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [store, activeOrgId, activeThreadId, isBatchRunning, setIsBatchRunning, setBatchQueue, setBatchRunningSnapshot, setBatchCurrentIndex]);

    return {
        isListening,
        isTranscribing,
        transcript,
        finalTranscript,
        voiceError,
        startListening,
        stopListening,
        clearTranscript,
        voiceSupported,
        analyserNode,

        view,
        setView,
        activeThread,
        setActiveThread,
        threads,
        setThreads,
        isLoadingThreads,
        isCreatingThread,
        currentOrgInfo,
        hasValidOrg,
        cleanOrgName,

        messages,
        inputValue,
        isLoading,
        selectedCompanies,
        approvalStatuses,
        liveModel,
        modelActivity,
        agentEvents,
        agentStreaming,
        agentConfirmedActions,
        activeRunningTask,
        approvedSuggestedActions,
        taskInlineConfirmed,
        setInputValue,
        setMessages,
        setIsLoading,
        setAgentStreaming,
        setSelectedCompanies,
        setApprovalStatuses,
        setLiveModel,
        setModelActivity,
        setAgentEvents,
        setAgentConfirmedActions,
        setActiveRunningTask,
        setApprovedSuggestedActions,
        setTaskInlineConfirmed,

        model,
        setModel,
        strictMode,
        setStrictMode,
        pipedriveCooldown,
        activities,
        setActivities,
        isLoadingActivities,
        showAutocomplete,
        setShowAutocomplete,
        searchTerm,
        setSearchTerm,
        companies,
        setCompanies,
        isSearching,
        searchingCategory,
        threadsToDelete,
        setThreadsToDelete,

        messagesEndRef,
        scrollContainerRef,
        taskConsoleLogsBottomRef,

        handleStopStreaming,
        handleCancelActiveTask,
        handleApproveSuggestedAction,
        handleRetrySuggestedAction,
        handleOpenTaskConsole,
        handleTaskInlineConfirm,
        handleTaskMappingComplete,
        handleToggleBatchItem,
        handleClearBatch,
        handleExecuteBatch,
        batchQueue,
        isBatchRunning,
        batchRunningSnapshot,
        batchCurrentIndex,
        handleScroll,
        handleInputChange,
        handleSendMessage,
        handleNewThread,
        handleBackToList,
        confirmDeleteThread,
        refreshActivities,
        refreshMessages,
        openThread,
        loadThreads,
        handleRegenerate,
        handleApproveAction,
        handleRejectAction,
        handleMainChatMappingDone,
        handleAgentConfirm,
    };
};
