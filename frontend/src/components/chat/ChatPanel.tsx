import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Loader2, Sparkles, ArrowLeft, PanelRightOpen, PanelRightClose, Clock, Trash2, Plus, CheckCircle2, XCircle, AlertTriangle, Maximize2, Minimize2, Terminal, Check, X } from 'lucide-react';
import styles from './ChatPanel.module.css';

import { Message, CompanyResult } from './ChatInterfaces';
import { ChatInput } from './ChatInput';
import { AIModel, ModelSelector } from './ModelSelector';
import { ChatMessage } from './ChatMessage';
import { AgentMessage, AgentEvent, TaskStatus, InlineEventStream, MappedContact } from './AgentV2Message';
import { ModelActivityEvent } from './ModelActivityBar';
import { ActivitySidebar } from './ActivitySidebar';
import { ThreadList } from './ThreadList';
import { ConversationContextAccordion } from './ConversationContextAccordion';
import { Avatar, Modal, Button } from '../ui';

import { useSpeechToText } from '../../hooks/useSpeechToText';
import { ai, communication, conversations } from '@/services/api';
import { useChatStore } from '@/store/chatStore';
import { ChatTabs } from './ChatTabs';

const AGENT_STREAM_URL = ai.getAgentChatStreamUrl();
const AGENT_CONFIRM_URL = ai.getAgentConfirmStreamUrl();
import type { ThreadOut, ActivityOut, MessageOut } from '@/services/api/conversations';

interface ChatPanelProps {
    showChat: boolean;
    setShowChat: (show: boolean) => void;
    selectedOrgId?: number | null;
    selectedOrgName?: string;
    theme?: string;
    onToggleTheme?: () => void;
    onOpenWhatsApp?: (info: { name: string, id?: string }) => void;
    selectedOrgLogo?: string;
    prospectingContext?: string | null;
    isOrgLoading?: boolean;
}

type PanelView = 'list' | 'chat';

export const ChatPanel: React.FC<ChatPanelProps> = ({
    showChat,
    setShowChat,
    selectedOrgId,
    selectedOrgName = 'Organização',
    theme = 'light',
    onToggleTheme,
    onOpenWhatsApp,
    selectedOrgLogo,
    prospectingContext,
    isOrgLoading,
}) => {
    const { isListening, isTranscribing, transcript, finalTranscript, error: voiceError, startListening, stopListening, clearTranscript, isSupported: voiceSupported, analyserNode } = useSpeechToText();

    // ─── View state ──────────────────────────────────────────
    const [view, setView] = useState<PanelView>(() => {
        if (typeof window !== 'undefined') {
            const savedView = window.localStorage.getItem('chat-panel-view');
            if (savedView === 'list') {
                return 'list';
            }
            return (savedView as PanelView) || 'chat';
        }
        return 'chat';
    });
    const [activeThread, setActiveThread] = useState<ThreadOut | null>(null);

    // ─── Thread list state ───────────────────────────────────
    const [threads, setThreads] = useState<ThreadOut[]>([]);
    const [isLoadingThreads, setIsLoadingThreads] = useState(false);
    const [isCreatingThread, setIsCreatingThread] = useState(false);

    // ─── Zustand Global Chat Store ───────────────────────────
    const store = useChatStore();
    const activeThreadId = activeThread?.id;

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
        if (activeOrgId === selectedOrgId) {
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
                        const cachedOrg = list.find((o: any) => Number(o.id) === activeOrgId || Number(o.pipedrive_id) === activeOrgId || Number(o.local_id) === activeOrgId);
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

    const [model, setModel] = useState<AIModel>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('ai_preferred_model');
            return (saved as AIModel) || 'claude';
        }
        return 'claude';
    });
    const [strictMode, setStrictMode] = useState<boolean>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('ai_strict_mode');
            return saved === 'true';
        }
        return false;
    });
    const modelActivityIdRef = useRef(0);
    const [pipedriveCooldown, setPipedriveCooldown] = useState<number>(0);
    const abortControllersRef = useRef<Record<string, AbortController>>({});
    // Guarda o threadId que está atualmente em streaming (para restaurar loading ao voltar)
    const streamingThreadIdRef = useRef<string | null>(null);
    const activeThreadIdRef = useRef<string | null>(null);

    useEffect(() => {
        activeThreadIdRef.current = activeThread?.id || null;
    }, [activeThread]);


    const handleStopStreaming = useCallback((targetThreadId?: string) => {
        const tId = targetThreadId || activeThreadIdRef.current || 'global';
        if (abortControllersRef.current[tId]) {
            abortControllersRef.current[tId].abort();
            delete abortControllersRef.current[tId];
        }
        if (tId === streamingThreadIdRef.current) {
            streamingThreadIdRef.current = null;
        }
        setIsLoading(false);
        setAgentStreaming(false);
        setActiveRunningTask((prev: any) => prev?.status === 'streaming' ? { ...prev, status: 'done' } : prev);
        setLiveModel(null);
        setModelActivity([]);
    }, []);

    // ─── Activity sidebar ────────────────────────────────────
    const [showActivitySidebar, setShowActivitySidebar] = useState(false);
    const [activities, setActivities] = useState<ActivityOut[]>([]);
    const [isLoadingActivities, setIsLoadingActivities] = useState(false);

    // ─── Autocomplete ────────────────────────────────────────
    const [showAutocomplete, setShowAutocomplete] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [companies, setCompanies] = useState<CompanyResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [searchingCategory, setSearchingCategory] = useState<string | null>(null);
    const lastSearchId = useRef(0);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [isAtBottom, setIsAtBottom] = useState(true);
    const [threadsToDelete, setThreadsToDelete] = useState<ThreadOut[]>([]);

    // ─── External Task Runner State & Handlers ───────────────
    const activeRunningTask = session.activeRunningTask;
    const approvedSuggestedActions = session.approvedSuggestedActions;
    const taskInlineConfirmed = session.taskInlineConfirmed;

    const setActiveRunningTask = useCallback((val: any | ((prev: any | null) => any | null)) => store.setActiveRunningTask(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setApprovedSuggestedActions = useCallback((val: Record<string, any> | ((prev: Record<string, any>) => Record<string, any>)) => store.setApprovedSuggestedActions(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
    const setTaskInlineConfirmed = useCallback((val: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)) => store.setTaskInlineConfirmed(activeOrgId, activeThreadId, val), [store, activeOrgId, activeThreadId]);
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

    // ─── Recover: retoma mapeamento após reload de página ───────────────────
    // ATENÇÃO: este path só deve ser ativo em sessão de RELOAD.
    // Durante sessão normal o HierarchyMappingCard tem seu próprio listener e
    // chama handleMainChatMappingDone via onMappingDone — não usar aqui.
    useEffect(() => {
        const pending = localStorage.getItem('pending-hierarchy-continuation');
        const activeJob = localStorage.getItem('active-discovery-job');
        if (!pending || !activeJob) return;

        try {
            const jobData = JSON.parse(activeJob);
            if (jobData) {
                if (Number(jobData.orgId) !== Number(activeOrgId)) {
                    return; // O job ativo pertence a outra empresa!
                }
                if (jobData.chatPrompted === false) {
                    return; // O job ativo foi manual/usuário, o chat não precisa esperar!
                }
            }
        } catch {}

        // Valida se realmente é um reload: messages ainda não foram carregadas
        // (se o chat já tem mensagens renderizadas com o event, o card cuida disso)
        // Usamos um flag de "fresh mount" via sessionStorage para distinguir reload de navegação normal
        const isReload = !sessionStorage.getItem('chat-session-active');
        sessionStorage.setItem('chat-session-active', '1');
        if (!isReload) return;

        let ctx: any;
        try { ctx = JSON.parse(pending); } catch { return; }

        // Mostra estado de loading enquanto o worker ainda roda
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

        // Dispara evento para o HierarchyMappingCard (se ainda montado) mostrar "scanning"
        window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));

        return () => window.removeEventListener('hierarchy_scan_done', handleScanDone);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeOrgId]);



    const streamTaskInto = async (url: string, body: object, initialTaskState: typeof activeRunningTask) => {
        const collected: AgentEvent[] = [];
        
        const tId = 'global_task';
        if (abortControllersRef.current[tId]) {
            abortControllersRef.current[tId].abort();
        }
        const controller = new AbortController();
        abortControllersRef.current[tId] = controller;

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

                        // Side effects based on tool results
                        if (ev.type === 'tool_result' && ev.ok) {
                            const tool = ev.tool || '';
                            if (tool === 'generate_prospecting_plan') {
                                window.dispatchEvent(new CustomEvent('prospecting_plan_updated'));
                            }
                            
                            const isWriteTool = tool.includes('create') || tool.includes('update') || tool.includes('send') || tool.includes('reply');
                            
                            if ((tool.startsWith('pipedrive_') || tool.includes('send') || tool.includes('reply')) && isWriteTool) {
                                window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
                                if (tool === 'pipedrive_update_task') {
                                    // Tenta extrair se foi concluída
                                    try {
                                        const summary = ev.summary || '';
                                        if (summary.toLowerCase().includes('concluída') || summary.toLowerCase().includes('done')) {
                                            window.dispatchEvent(new CustomEvent('crm_task_completed'));
                                        } else {
                                            window.dispatchEvent(new CustomEvent('crm_task_uncompleted'));
                                        }
                                    } catch {}
                                }
                                // Atualiza lista de atividades local
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
                    
                    conversations.updateSuggestedActionStatus(actualParentId, actionIndex, 'pending').catch(err => {
                        console.error('Failed to persist task cancellation', err);
                    });
                    
                    return { ...prev, [taskKey]: 'pending' };
                });
            }
            if (abortControllersRef.current['global_task']) {
                abortControllersRef.current['global_task'].abort();
            }
            setActiveRunningTask(null);
        }
    };

    const handleApproveSuggestedAction = async (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => {
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
            isExpanded: true,
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

            const hierarchyEv = collected.find(e => e.type === 'hierarchy_mapping_required');
            const pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
            const ligacaoEv = collected.find(e => e.type === 'tool_call' && e.tool === 'open_ligacao_view');
            const hasError = collected.length === 0 || collected.some(e => e.type === 'error' || (e.type === 'tool_result' && e.ok === false));
            
            let finalStatus: TaskStatus = 'done';
            if (hierarchyEv) {
                finalStatus = 'awaiting_mapping';
            } else if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            } else if (ligacaoEv) {
                finalStatus = 'streaming';
            } else if (hasError) {
                finalStatus = 'pending';
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

            // Captura os logs acumulados no activeRunningTask (via ref de closure)
            // para persistir no backend e no estado local de messages
            const finalLogs = (() => {
                // Lê os logs do state atual (closure sobre setActiveRunningTask)
                return collected;
            })();

            // Persiste status + logs no backend
            if (actualParentId) {
                conversations.updateSuggestedActionStatus(actualParentId, index, finalStatus, finalLogs).catch(err => {
                    console.error('Failed to persist task status/logs', err);
                });
            }

            // Atualiza messages state localmente para que o console mostre os logs
            // imediatamente ao clicar no card concluído (sem precisar recarregar)
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

        // Toggle if clicking the same one that is already active
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
            let finalStatus: TaskStatus = 'done';
            if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            } else if (ligacaoEv) {
                finalStatus = 'streaming'; // Mantém em loading
            }

            setActiveRunningTask((prev: any) => prev ? { ...prev, status: finalStatus } : null);
            if (actualParentId) {
                const { actionIndex: aidx } = activeRunningTask;
                const pid = actualParentId;
                const taskKey = `${pid}-${aidx}`;
                setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: finalStatus }));

                // Lê os logs acumulados no activeRunningTask para persistir
                const allLogs = [...(activeRunningTask.logs || []), ...collected];

                // Persiste status + logs no backend
                conversations.updateSuggestedActionStatus(pid, aidx, finalStatus, allLogs).catch(err => {
                    console.error('Failed to persist task status/logs', err);
                });

                // Atualiza messages state localmente
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
            let finalStatus: TaskStatus = 'done';
            if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            }
            setActiveRunningTask((prev: any) => prev ? { ...prev, status: finalStatus } : null);
            if (activeRunningTask.parentMessageId) {
                const { parentMessageId: pid, actionIndex: aidx } = activeRunningTask;
                const taskKey = `${pid}-${aidx}`;
                setApprovedSuggestedActions((prev: any) => ({ ...prev, [taskKey]: finalStatus }));

                // Logs = os que já existiam + os novos desta fase de mapeamento
                const allLogs = [...(activeRunningTask.logs || []), ...newEvents];

                // Persiste status + logs no backend
                conversations.updateSuggestedActionStatus(pid, aidx, finalStatus, allLogs).catch(err => {
                    console.error('Failed to persist task status/logs', err);
                });

                // Atualiza messages state localmente
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



    const renderActiveTaskConsoleOverlay = () => {
        return null;
    };

    const renderChatInput = () => (
        <ChatInput
            inputValue={inputValue}
            setInputValue={handleInputChange}
            isLoading={isLoading || activeRunningTask?.status === 'streaming'}
            onSend={handleSendMessage}
            selectedCompanies={selectedCompanies}
            setSelectedCompanies={setSelectedCompanies}
            model={model}
            setModel={setModel}
            strictMode={strictMode}
            setStrictMode={setStrictMode}
            liveModel={liveModel}
            modelActivity={modelActivity}
            isStreamingActivity={isLoading}
            showAutocomplete={showAutocomplete}
            isSearching={isSearching}
            searchingCategory={searchingCategory}
            searchTerm={searchTerm}
            companies={companies}
            selectSearchResult={item => {
                if (!selectedCompanies.find(c => c.id === item.id)) {
                    setSelectedCompanies([...selectedCompanies, item]);
                }
                const lastAt = inputValue.lastIndexOf('@');
                if (lastAt !== -1) setInputValue(inputValue.substring(0, lastAt) + '@' + item.name + ' ');
                setShowAutocomplete(false);
            }}
            isListening={isListening}
            isTranscribing={isTranscribing}
            startListening={startListening}
            stopListening={stopListening}
            voiceError={voiceError}
            voiceSupported={voiceSupported}
            analyserNode={analyserNode}
            theme={theme}
            pipedriveCooldown={pipedriveCooldown}
            onStop={handleStopStreaming}
            activeRunningTask={activeRunningTask}
            setActiveRunningTask={setActiveRunningTask}
            taskInlineConfirmed={taskInlineConfirmed}
            onTaskInlineConfirm={handleTaskInlineConfirm}
            onTaskMappingComplete={handleTaskMappingComplete}
            onCancelActiveTask={handleCancelActiveTask}
        />
    );

    // ─── Scroll ──────────────────────────────────────────────
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

    // ─── Voice input ─────────────────────────────────────────
    useEffect(() => {
        if (finalTranscript) {
            setInputValue(prev => {
                const hasSpace = prev.length > 0 && prev[prev.length - 1] !== ' ';
                return prev + (hasSpace ? ' ' : '') + finalTranscript;
            });
            clearTranscript();
        }
    }, [finalTranscript, clearTranscript]);

    // ─── Cooldown ────────────────────────────────────────────
    useEffect(() => {
        if (pipedriveCooldown > 0) {
            const timer = setInterval(() => setPipedriveCooldown(p => Math.max(0, p - 1)), 1000);
            return () => clearInterval(timer);
        }
    }, [pipedriveCooldown]);



    // ─── AI Model Preference Persistence ─────────────────────
    useEffect(() => {
        // Sincroniza a escolha do usuário com o backend para que
        // tarefas de background (triggers) também usem este modelo.
        const syncPreference = async () => {
            try {
                await ai.updatePreference(model, strictMode);
                // Salva no localStorage como backup
                localStorage.setItem('ai_preferred_model', model);
                localStorage.setItem('ai_strict_mode', String(strictMode));
            } catch (err) {
                console.warn('[ChatPanel] Erro ao sincronizar preferência:', err);
                // Salva no localStorage mesmo se falhar no backend
                localStorage.setItem('ai_preferred_model', model);
                localStorage.setItem('ai_strict_mode', String(strictMode));
            }
        };
        void syncPreference();
    }, [model, strictMode]);

    // ─── Refresh messages ────────────────────────────────────
    const refreshMessages = useCallback(async (threadId: string) => {
        try {
            const msgs = await conversations.getMessages(threadId);
            if (msgs.length === 0) {
                setMessages([{
                    id: 'welcome',
                    role: 'assistant',
                    content: hasValidOrg ? `Como posso te ajudar com a @${cleanOrgName}?` : "Como posso te ajudar hoje?",
                    timestamp: new Date(),
                }]);
                if (activeOrgId && !prospectingContext) {
                    store.setInputValue(activeOrgId, threadId, "Gerar plano de prospecção para esta empresa");
                }
            } else {
                let hasActiveJobLoading = false;
                let hasAwaitingConfirmation = false;
                
                // Constrói o mapeamento global de ações decididas no histórico da thread
                const callIdToActionId: Record<string, string> = {};
                const actionIdToApproved: Record<string, boolean> = {};
                const initialSuggestedActions: Record<string, TaskStatus> = {};
                let restoredTask: any = null;

                msgs.forEach((m: MessageOut) => {
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
                                
                                // Restaura a tarefa ativa se não estiver concluída ou com erro
                                if (run.status !== 'done' && run.status !== 'error') {
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
                                        isExpanded: true, // Expande ao carregar para o usuário ver os botões de ação e status
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

                msgs.forEach((m: MessageOut) => {
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

                const mappedMsgs = msgs.map((m: MessageOut) => {
                    const isAgent = !!(m.logs && Array.isArray(m.logs) && m.logs.some((l: any) => l.type === 'tool_call' || l.type === 'thinking' || l.type === 'final'));
                    let forceAgentStreaming = false;
                    if (isAgent && m.logs && Array.isArray(m.logs)) {
                        const hasMapping = m.logs.some((l: any) => l.type === 'hierarchy_mapping_required');
                        if (hasMapping && typeof window !== 'undefined') {
                            const activeJob = window.localStorage.getItem('active-discovery-job');
                            if (activeJob) {
                                try {
                                    const jobData = JSON.parse(activeJob);
                                    if (jobData && Number(jobData.orgId) === Number(selectedOrgId)) {
                                        forceAgentStreaming = true;
                                        hasActiveJobLoading = true;
                                    }
                                } catch {
                                    forceAgentStreaming = true;
                                    hasActiveJobLoading = true;
                                }
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

                    // Reconstrói as ações confirmadas deste agent message especificamente
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
                    setAgentStreaming(true);
                }
                if (hasActiveJobLoading) {
                    setIsLoading(true);
                }
                setApprovedSuggestedActions(prev => ({ ...prev, ...initialSuggestedActions }));
                if (restoredTask) {
                    setActiveRunningTask(restoredTask);
                } else {
                    setActiveRunningTask(null);
                }
                setMessages(mappedMsgs);
            }
        } catch (err) {
            console.error('[ChatPanel] Erro ao carregar/atualizar mensagens:', err);
        }
    }, [activeOrgId, currentOrgInfo.name, hasValidOrg, cleanOrgName]);

    // ─── Open thread ─────────────────────────────────────────
    const openThread = useCallback(async (thread: ThreadOut) => {
        const isSameStreamingThread = streamingThreadIdRef.current === thread.id;

        if (!isSameStreamingThread) {
            // Troca de thread: mantemos o stream em background (não abortamos)
            setActiveRunningTask(null);
            setLiveModel(null);
            setModelActivity([]);
        }
        // Se é o mesmo thread que estava streamando, restauramos/mantemos o loading visual
        if (isSameStreamingThread) {
            setIsLoading(true);
            setAgentStreaming(true);
        }
        // Se é o mesmo thread que estava streamando: não reseta o loading
        // Os estados isLoading/agentStreaming/activeRunningTask ainda estão ativos

        setActiveThread(thread);
        if (typeof window !== 'undefined') {
            const targetOrgId = activeOrgId || 0;
            window.localStorage.setItem(`active-thread-id-${targetOrgId}`, thread.id);
            window.localStorage.setItem('chat-panel-view', 'chat');
        }
        setView('chat');
        await refreshMessages(thread.id);
    }, [activeOrgId, refreshMessages]);

    // ─── Load threads and activities ────────────────────────
    const loadThreads = useCallback(async () => {
        setIsLoadingThreads(true);
        try {
            const targetOrgId = activeOrgId || 0;
            const [threadList, actList] = await Promise.all([
                conversations.listThreads(targetOrgId),
                conversations.listActivities(targetOrgId),
            ]);
            setThreads(threadList);
            setActivities(actList);

            // Restore active thread from localStorage (only if the view is not 'list')
            if (typeof window !== 'undefined') {
                const savedThreadId = window.localStorage.getItem(`active-thread-id-${targetOrgId}`);
                const savedView = window.localStorage.getItem('chat-panel-view');
                if (savedThreadId && savedView !== 'list') {
                    const matched = threadList.find(t => t.id === savedThreadId);
                    if (matched) {
                        void openThread(matched);
                    }
                }
            }
        } catch (err) {
            console.error('[ChatPanel] Erro ao carregar dados:', err);
        } finally {
            setIsLoadingThreads(false);
        }
    }, [activeOrgId, openThread]);

    // ─── Load threads when org changes ──────────────────────
    useEffect(() => {
        setActiveThread(null);
        store.setMessages(activeOrgId, null, []);
        
        if (typeof window !== 'undefined') {
            const savedView = window.localStorage.getItem('chat-panel-view');
            if (savedView === 'list') {
                setView('list');
            } else {
                setView('chat');
            }
        } else {
            setView('chat');
        }
        
    // Sempre carrega threads, mesmo que orgId seja nulo (orgId=0 no backend pega tudo)
        void loadThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeOrgId]);

    useEffect(() => {
        const currentThreadId = activeThread?.id || null;
        const currentSession = store.getSession(activeOrgId, currentThreadId);
        
        if (activeOrgId && !prospectingContext) {
            if (!currentSession.inputValue) {
                store.setInputValue(activeOrgId, currentThreadId, "Gerar plano de prospecção para esta empresa");
            }
        } else if (prospectingContext) {
            if (currentSession.inputValue === "Gerar plano de prospecção para esta empresa") {
                store.setInputValue(activeOrgId, currentThreadId, "");
            }
        }
    }, [activeOrgId, prospectingContext, activeThread?.id, store]);

    const handleNewThread = () => {
        // O stream em background não é cancelado quando se inicia uma nova conversa.
        streamingThreadIdRef.current = null;
        setActiveRunningTask(null);
        setLiveModel(null);
        setModelActivity([]);
        setAgentEvents([]);

        setActiveThread(null);
        setApprovedSuggestedActions({});
        setAgentConfirmedActions({});
        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            window.localStorage.removeItem(`active-thread-id-${targetOrgId}`);
            window.localStorage.setItem('chat-panel-view', 'chat');
        }
        store.setMessages(activeOrgId, null, []);
        if (activeOrgId && !prospectingContext) {
            store.setInputValue(activeOrgId, null, "Gerar plano de prospecção para esta empresa");
        } else {
            store.setInputValue(activeOrgId, null, "");
        }
        setView('chat');
    };

    // ─── Back to list ────────────────────────────────────────
    const handleBackToList = async () => {
        // NÃO cancela o stream — o agente continua rodando em background.
        // O streamingThreadIdRef preserva o threadId para restaurar o loading ao voltar.
        // O stream só é cancelado se o usuário abrir um thread DIFERENTE ou clicar em Novo Chat.
        setView('list');
        if (typeof window !== 'undefined') {
            window.localStorage.setItem('chat-panel-view', 'list');
            // Mantém active-thread-id para que loadThreads saiba restaurar o thread ao voltar
        }
        setActiveThread(null);
        store.setMessages(activeOrgId, null, []);
        const defaultInput = (activeOrgId && !prospectingContext) ? "Gerar plano de prospecção para esta empresa" : "";
        store.setInputValue(activeOrgId, null, defaultInput);
        // Refresh thread list to show updated message counts
        void loadThreads();
    };

    // ─── Delete thread ───────────────────────────────────────
    const confirmDeleteThread = async () => {
        if (!threadsToDelete.length) return;
        const targetIds = threadsToDelete.map(t => t.id);
        
        try {
            await conversations.deleteThreadsBulk(targetIds);
            setThreads(prev => prev.filter(t => !targetIds.includes(t.id)));
            if (activeThread && targetIds.includes(activeThread.id)) {
                handleBackToList();
            }
        } catch (err: any) {
            // Se for 404, já foi deletada, então removemos da UI também
            if (err.status === 404) {
                setThreads(prev => prev.filter(t => !targetIds.includes(t.id)));
                if (activeThread && targetIds.includes(activeThread.id)) {
                    handleBackToList();
                }
            } else {
                console.error('[ChatPanel] Erro ao deletar thread(s):', err);
            }
        } finally {
            setThreadsToDelete([]);
        }
    };

    // ─── Refresh activities ──────────────────────────────────
    const refreshActivities = useCallback(async () => {
        if (!selectedOrgId) return;
        setIsLoadingActivities(true);
        try {
            const acts = await conversations.listActivities(selectedOrgId);
            setActivities(acts);
        } catch { /* silent */ } finally {
            setIsLoadingActivities(false);
        }
    }, [selectedOrgId]);

    // ─── Ensure thread before sending ───────────────────────
    const ensureThread = async (): Promise<string | null> => {
        if (activeThread) return activeThread.id;
        const targetOrgId = selectedOrgId || 0;
        try {
            const t = await conversations.createThread(targetOrgId);
            setActiveThread(t);
            setThreads(prev => [t, ...prev]);
            return t.id;
        } catch (err) {
            console.error('[ChatPanel] Erro ao criar thread:', err);
            setMessages(prev => [...prev, {
                id: Date.now().toString(),
                role: 'assistant',
                content: 'Não foi possível iniciar a conversa. Verifique a conexão com o servidor.',
                timestamp: new Date(),
            }]);
            return null;
        }
    };

    // ─── Agente: executar workflow ────────────────────────────
    const executeAgent = async (text: string, threadId: string, historyForApi: any[], directAction: boolean = false) => {
        store.setIsLoading(activeOrgId, threadId, true);
        store.setAgentEvents(activeOrgId, threadId, []);
        store.setAgentStreaming(activeOrgId, threadId, true);
        // Registra qual thread está em streaming para preservar o loading ao navegar e voltar
        streamingThreadIdRef.current = threadId;

        const msgId = (Date.now() + 1).toString();

        // Adiciona mensagem "em andamento" do assistente
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

                        // Side effects based on tool results
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

                        // Modelo ativo — atualiza o selector e a barra de atividade
                        if (event.type === 'model_active') {
                            if (!strictMode) store.setLiveModel(activeOrgId, threadId, event.provider as AIModel);
                            store.setModelActivity(activeOrgId, threadId, prev => {
                                const last = prev[prev.length - 1];
                                // Suprime duplicata consecutiva do mesmo provider
                                if (last?.type === 'model_active' && last.provider === event.provider) return prev;
                                // Adiciona evento de "switch" quando troca de provider
                                const extra: ModelActivityEvent[] = [];
                                if (last && last.provider !== event.provider && event.provider) {
                                    extra.push({ id: ++modelActivityIdRef.current, type: 'model_switch', provider: event.provider as AIModel, model: event.model, timestamp: Date.now() });
                                }
                                return [...prev, ...extra, { id: ++modelActivityIdRef.current, type: 'model_active', provider: event.provider as AIModel, model: event.model, timestamp: Date.now() }];
                            });
                        }

                        // Rate limit / context overflow — sempre na barra
                        if (event.type === 'rate_wait') {
                            store.setModelActivity(activeOrgId, threadId, prev => [...prev, { id: ++modelActivityIdRef.current, type: 'rate_wait', provider: event.provider as AIModel | undefined, model: event.model, wait_sec: event.wait_sec, reason: event.reason, timestamp: Date.now() }]);
                        }
                        if (event.type === 'context_overflow') {
                            store.setModelActivity(activeOrgId, threadId, prev => [...prev, { id: ++modelActivityIdRef.current, type: 'context_overflow', model: event.model, estimated_tokens: event.estimated_tokens, limit: event.limit, timestamp: Date.now() }]);
                        }

                        // Atualiza a mensagem em tempo real
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
                    // Persiste contexto para sobreviver a reloads enquanto o worker roda
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

            // Marca streaming como concluído, limpa modelos live
            store.setLiveModel(activeOrgId, threadId, null);
            // Mantém a barra visível por 3s se houver eventos de espera, depois limpa
            const hadWaits = store.getSession(activeOrgId, threadId).modelActivity.some(e => e.type === 'rate_wait' || e.type === 'context_overflow');
            if (hadWaits) {
                setTimeout(() => store.setModelActivity(activeOrgId, threadId, []), 3000);
            } else {
                store.setModelActivity(activeOrgId, threadId, []);
            }
            // Não alteramos agentStreaming aqui; faremos no finally com base em hasMappingRequired

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

    // ─── Agente: lidar com finalização de mapeamento no chat principal ──────────
    const handleMainChatMappingDone = async (contacts: any[], event?: AgentEvent) => {
        // Limpa contexto persistido — mapeamento concluído com sucesso
        localStorage.removeItem('pending-hierarchy-continuation');
        const orgId = selectedOrgId || event?.org_id;
        const orgName = event?.org_name || 'a empresa';

        const preTaskClause = event?.pre_task_id
            ? `Marque a tarefa de rastreamento pre_task_id=${event.pre_task_id} como concluída com pipedrive_update_task done=true. `
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

        // ── SEGURANÇA: Remove qualquer contato rejeitado ou pendente que possa ter escapado, além de PJs
        const approvedContacts = contacts.filter((c: any) => {
            if (isLegalEntity(c.name)) return false;
            const r = (c.role || '').toLowerCase();
            const d = (c.department || '').toLowerCase();
            if (r.includes('reprovado') || d.includes('reprovado')) return false;
            if (r.includes('análise humana') || r.includes('analise humana')) return false;
            return true;
        });

        // Detecta decisores de compras/logística pelo cargo
        const isBuyingDecisionMaker = (role: string, dept?: string) => {
            const r = (role || '').toLowerCase();
            const d = (dept || '').toLowerCase();
            const keywords = ['compras', 'procurement', 'suprimentos', 'logística', 'logistica',
                    'supply chain', 'supply', 'materiais', 'aquisição', 'aquisicao',
                    'estoque', 'sourcing'];
            return keywords.some(k => r.includes(k) || d.includes(k));
        };

        const contactsSummary = approvedContacts.length > 0
            ? approvedContacts.map((c: any) => `- ${c.name} (${c.role}${c.department ? ', ' + c.department : ''}${c.email ? ', ' + c.email : ''}${c.temperature ? ', temp=' + c.temperature : ''}${c.decision_maker ? ', DECISOR' : ''})`).join('\n')
            : '';

        const baseProhibition = `REGRA CRÍTICA: Estes contatos são leads frios do LinkedIn — PROIBIDO chamar whatsapp_get_messages, email_get_contact_history ou whatsapp_list_chats para eles.\n`;

        let taskInstruction: string;

        if (approvedContacts.length === 0) {
            // Cenário C: nenhum contato aprovado pelo usuário
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
            // Fallback se não encontrar a mensagem anterior
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
            streamingThreadIdRef.current = null;
            store.setMessages(activeOrgId, threadId, prev => prev.map(m => m.id === targetMsgId ? { ...m, agentStreaming: false } : m));
            store.setIsLoading(activeOrgId, threadId, false);
            store.setAgentStreaming(activeOrgId, threadId, false);
        }
    };

    // ─── Agente: lidar com confirmação de ação ───────────────
    const handleAgentConfirm = async (action_id: string, approved: boolean, file?: File) => {
        setAgentConfirmedActions(prev => ({ ...prev, [action_id]: approved }));

        // Marca todas as mensagens com esse action_id
        setMessages(prev => prev.map(m => {
            if (!m.isAgent || !m.agentEvents) return m;
            const hasAction = m.agentEvents.some((e: any) => e.action_id === action_id);
            if (!hasAction) return m;
            return { ...m, agentConfirmedActions: { ...(m.agentConfirmedActions || {}), [action_id]: approved } };
        }));

        // Chama o endpoint de confirmação e faz streaming do resultado
        const threadId = activeThread?.id || 'global';
        setIsLoading(true);
        setAgentStreaming(true);
        streamingThreadIdRef.current = threadId;
        
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

                        // Side effects based on tool results
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
            streamingThreadIdRef.current = null;
            
            // Verifica se precisamos manter o loading ativo por conta da view de ligacao
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

    // ─── Send message ────────────────────────────────────────
    const handleSendMessage = async (text: string, companiesSelected: CompanyResult[] = [], isSuggestedAction: boolean = false, directAction: boolean = false) => {
        if (!text.trim() && (!companiesSelected || companiesSelected.length === 0)) return;

        // Garante transição visual para a tela do chat ativo ao enviar qualquer mensagem
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
    }, [handleSendMessage]);

    // ─── Regenerate response ─────────────────────────────────
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

        // Mantém apenas até a última mensagem do usuário (remove a resposta da IA anterior)
        const newHistory = messages.slice(0, lastUserMsgIndex + 1);
        
        // Envia histórico incluindo a última mensagem do assistente para detecção de regeneração no backend
        // Isso permite que o backend identifique que é uma regeneração e delete a resposta anterior
        const messagesIncludingLastAssistant = messages.slice(0, lastUserMsgIndex + 2);
        const historyForApi = messagesIncludingLastAssistant.slice(-6).map(m => ({ role: m.role, content: m.content }));
        
        setMessages(newHistory);
        await executeAgent(lastUserMsg.content, threadId, historyForApi);
    };

    // ─── Approve / Reject ────────────────────────────────────
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

    // ─── Autocomplete ────────────────────────────────────────
    const handleInputChange = (val: string) => {
        setInputValue(val);
        const lastAt = val.lastIndexOf('@');
        if (lastAt !== -1) {
            let query = val.substring(lastAt + 1);
            const matched = selectedCompanies.find(c => query.toLowerCase().startsWith(c.name.toLowerCase()));
            if (matched && query.substring(matched.name.length).length > 0) { setShowAutocomplete(false); return; }
            const catMatch = query.match(/^(contato|email|empresa|cnpj|lead)\s+(.*)/i);
            if (catMatch) {
                let cat = catMatch[1].toLowerCase();
                if (cat === 'contato') cat = 'whatsapp';
                setSearchingCategory(cat);
                setSearchTerm(catMatch[2]);
                setShowAutocomplete(true);
                searchUniversal(catMatch[2], cat);
                return;
            }
            if (query.trim().length > 0 && query.length < 30) {
                setSearchTerm(query);
                setShowAutocomplete(true);
                setSearchingCategory(null);
                searchUniversal(query);
            } else {
                setShowAutocomplete(false);
            }
            return;
        }
        setShowAutocomplete(false);
    };

    const searchUniversal = async (query: string, category: string | null = null) => {
        if (query.length < 1) { setCompanies([]); return; }
        const searchId = ++lastSearchId.current;
        setIsSearching(true);
        try {
            const data = await communication.universalSearch(query, category || undefined);
            if (searchId !== lastSearchId.current) return;
            let results = data.results || [];
            if (category) results = results.filter((item: any) =>
                category === 'whatsapp' ? item.type === 'whatsapp' :
                category === 'email'    ? item.type === 'email' : true
            );
            setCompanies(results as CompanyResult[]);
        } catch { /* ignore */ } finally {
            if (searchId === lastSearchId.current) setIsSearching(false);
        }
    };

    // ─── Call Ended Listener ─────────────────────────────────
    useEffect(() => {
        const handleCallEnded = (e: any) => {
            // Remove o estado de loading da mensagem que chamou a ligação
            store.setMessages(activeOrgId, activeThreadIdRef.current || 'global', prev => prev.map(m => ({ ...m, agentStreaming: false })));
            store.setIsLoading(activeOrgId, activeThreadIdRef.current || 'global', false);
            store.setAgentStreaming(activeOrgId, activeThreadIdRef.current || 'global', false);

            const { contactName, transcript } = e.detail || {};
            
            // Converte o array de transcrição em texto legível
            const transcriptText = Array.isArray(transcript) 
                ? transcript.map((m: any) => `[${m.role}]: ${m.text}`).join('\n')
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
    }, [handleSendMessage]);

    // ═══════════════════════════════════════════
    // RENDER: Collapsed handle view
    // ═══════════════════════════════════════════
    if (!showChat) {
        return (
            <div 
                style={{
                    width: '56px',
                    height: '100%',
                    backgroundColor: '#131313',
                    borderLeft: '1px solid rgba(255, 255, 255, 0.04)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    paddingTop: '16px',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    flexShrink: 0
                }}
                onClick={() => setShowChat(true)}
                title="Abrir Assistente de IA"
            >
                <button 
                    style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--sw-text-muted)',
                        cursor: 'pointer',
                        padding: '8px',
                        borderRadius: '8px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        transition: 'color 0.2s',
                    }}
                >
                    <PanelRightOpen size={20} />
                </button>
            </div>
        );
    }

    if (view === 'list') {
        return (
            <div className={styles.chatPanel} data-theme={theme}>
                <ThreadList
                    orgName={hasValidOrg ? cleanOrgName : 'Geral'}
                    threads={threads}
                    isLoading={isLoadingThreads}
                    onSelectThread={openThread}
                    onNewThread={handleNewThread}
                    isCreating={isCreatingThread}
                    selectedOrgLogo={currentOrgInfo.logo}
                    onDeleteThread={(t) => setThreadsToDelete([t])}
                    onDeleteThreadsBulk={setThreadsToDelete}
                    onCloseChat={() => setShowChat(false)}
                    onBackToChat={() => {
                        setView('chat');
                        if (typeof window !== 'undefined') {
                            window.localStorage.setItem('chat-panel-view', 'chat');
                            const targetOrgId = activeOrgId || 0;
                            const savedThreadId = window.localStorage.getItem(`active-thread-id-${targetOrgId}`);
                            if (savedThreadId) {
                                const matched = threads.find(t => t.id === savedThreadId);
                                if (matched) {
                                    void openThread(matched);
                                }
                            }
                        }
                    }}
                />

                <Modal
                    isOpen={threadsToDelete.length > 0}
                    onClose={() => setThreadsToDelete([])}
                    title={threadsToDelete.length > 1 ? "Excluir Conversas" : "Excluir Conversa"}
                    width={400}
                    footer={
                        <>
                            <Button variant="secondary" size="sm" onClick={() => setThreadsToDelete([])}>
                                Cancelar
                            </Button>
                            <Button variant="danger" size="sm" onClick={confirmDeleteThread}>
                                Excluir {threadsToDelete.length > 1 ? `(${threadsToDelete.length})` : ''}
                            </Button>
                        </>
                    }
                >
                    <p style={{ margin: 0, color: 'var(--chat-text-secondary)', fontSize: '14px', lineHeight: '1.5' }}>
                        {threadsToDelete.length > 1 
                            ? `Tem certeza que deseja excluir as ${threadsToDelete.length} conversas selecionadas? Esta ação não poderá ser desfeita.`
                            : 'Tem certeza que deseja excluir esta conversa? Esta ação removerá permanentemente todo o histórico e não poderá ser desfeita.'}
                    </p>
                </Modal>
            </div>
        );
    }

    // ═══════════════════════════════════════════
    // RENDER: Chat view
    // ═══════════════════════════════════════════

    return (
        <div className={styles.chatPanel} data-theme={theme}>

            {/* Chat sub-header: back + thread title + activities toggle */}
            <div className={styles.chatHeader} style={{ paddingLeft: '16px', gap: '12px' }}>
                <Avatar 
                    kind="company"
                    src={currentOrgInfo.logo}
                    name={currentOrgInfo.name}
                    size={32}
                    style={{ border: currentOrgInfo.logo ? '3px solid var(--sw-border-strong)' : 'none' }}
                />
                <div className={styles.chatHeaderInfo} style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '8px', flex: '0 1 auto', minWidth: 0 }}>
                    <span style={{ color: 'var(--sw-text-muted)', fontWeight: 600, fontSize: '0.88rem', flexShrink: 0 }}>
                        {activeThread?.title || 'Nova conversa'}
                    </span>
                    <span style={{ color: 'var(--sw-border)', fontWeight: 300, fontSize: '0.88rem', flexShrink: 0 }}>/</span>
                    <span 
                        style={{ 
                            color: 'var(--sw-text-base)', 
                            fontWeight: 600, 
                            fontSize: '0.88rem', 
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            maxWidth: '180px',
                            flexShrink: 1
                        }}
                        title={hasValidOrg ? cleanOrgName : 'Geral'}
                    >
                        {hasValidOrg ? cleanOrgName : 'Geral'}
                    </span>
                </div>
                <div style={{ flex: 1 }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginRight: '12px' }}>
                    <button
                        className={styles.tlNewBtn}
                        onClick={handleNewThread}
                        title="Nova conversa"
                        style={{ height: '32px', padding: '0 12px', fontSize: '12px' }}
                    >
                        <Plus size={13} />
                        <span>Nova</span>
                    </button>
                    <button
                        className={styles.chatHeaderIconBtn}
                        onClick={handleBackToList}
                        title="Histórico de conversas"
                    >
                        <Clock size={20} />
                    </button>
                </div>
            </div>

            {/* Abas dinâmicas para multi-chat */}
            <ChatTabs />

            {/* Accordion de Contexto da Investigação */}
            <ConversationContextAccordion 
                messages={messages} 
                orgId={activeOrgId}
                orgName={cleanOrgName}
                dealId={activeThread?.meta?.deal_id}
            />

            {/* Body: messages + optional sidebar */}
            <div className={`${styles.chatBody} ${messages.length === 0 || (messages.length === 1 && messages[0].id === 'welcome') ? styles.emptyChatBody : ''}`}>
                {isOrgLoading && messages.length === 0 ? (
                    <div className={styles.emptyWelcomeContainer} style={{ opacity: 0.7 }}>
                        <h2 className={styles.emptyWelcomeText}>
                            Carregando contexto da{' '}
                            <span className={styles.highlightPurple}>
                                @{cleanOrgName}
                            </span>
                            ...
                        </h2>
                    </div>
                ) : activeOrgId && !prospectingContext && (messages.length === 0 || (messages.length === 1 && messages[0].id === 'welcome')) ? (
                    <div className={styles.emptyWelcomeContainer}>
                        <h2 className={styles.emptyWelcomeText}>
                            A{' '}
                            <span className={styles.highlightPurple}>
                                @{cleanOrgName}
                            </span>
                            {' '}ainda não possui um plano de prospecção.
                        </h2>
                        <div className={styles.emptyInputWrapper}>
                            {renderChatInput()}
                        </div>
                    </div>
                ) : messages.length === 0 ? (
                    <div className={styles.emptyWelcomeContainer}>
                        <h2 className={styles.emptyWelcomeText}>
                            {hasValidOrg ? (
                                <>
                                    Como posso te ajudar com a{' '}
                                    <span className={styles.highlightPurple}>
                                        @{cleanOrgName}
                                    </span>
                                    ?
                                </>
                            ) : (
                                "Como posso te ajudar hoje?"
                            )}
                        </h2>
                        <div className={styles.emptyInputWrapper}>
                            {renderChatInput()}
                        </div>
                    </div>
                ) : messages.length === 1 && messages[0].id === 'welcome' ? (
                    <div className={styles.emptyWelcomeContainer}>
                        <h2 className={styles.emptyWelcomeText}>
                            {messages[0].content}
                        </h2>
                        <div className={styles.emptyInputWrapper}>
                            {renderChatInput()}
                        </div>
                    </div>
                ) : (
                    <>
                        <div 
                            className={styles.messagesContainer} 
                            style={{
                                paddingBottom: activeRunningTask?.isExpanded ? '440px' : undefined,
                                opacity: activeRunningTask?.isExpanded ? 0.55 : 1,
                                transition: 'opacity 0.3s ease, padding-bottom 0.3s ease',
                            }}
                            ref={scrollContainerRef} 
                            onScroll={handleScroll}
                        >
                            {messages.map(message => {
                                if (message.isAgent && message.role === 'assistant') {
                                    return (
                                        <AgentMessage
                                            key={message.id}
                                            messageId={message.id}
                                            events={message.agentEvents || []}
                                            isStreaming={message.agentStreaming !== false && agentStreaming}
                                            onConfirm={handleAgentConfirm}
                                            confirmedActions={message.agentConfirmedActions || {}}
                                            onRegenerate={() => handleRegenerate(message.id)}
                                            onAction={(prompt: string) => handleSendMessage(prompt, [], true)}
                                            streamV2Url={AGENT_STREAM_URL}
                                            confirmV2Url={AGENT_CONFIRM_URL}
                                            orgId={activeOrgId}
                                            selectedOrgName={cleanOrgName}
                                            threadId={activeThread?.id}
                                            approvedSuggestedActions={approvedSuggestedActions}
                                            onApproveSuggestedAction={handleApproveSuggestedAction}
                                            onHierarchyMappingDone={handleMainChatMappingDone}
                                            model={model}
                                            onOpenTaskConsole={handleOpenTaskConsole}
                                        />
                                    );
                                }
                                return (
                                    <ChatMessage
                                        key={message.id}
                                        message={message}
                                        onApprove={handleApproveAction}
                                        onReject={handleRejectAction}
                                        onOpenWhatsApp={onOpenWhatsApp}
                                        approvalStatuses={approvalStatuses}
                                        onRegenerate={handleRegenerate}
                                        onSuggestedAction={(prompt) => handleSendMessage(prompt, [], true)}
                                        model={model}
                                    />
                                );
                            })}
                            <div ref={messagesEndRef} />
                        </div>
                        {renderChatInput()}
                    </>
                )}
            </div>
            {renderActiveTaskConsoleOverlay()}
        </div>
    );
};
