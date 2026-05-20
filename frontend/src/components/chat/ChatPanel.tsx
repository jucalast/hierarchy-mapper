import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Loader2, ChevronRight, Sparkles, ArrowLeft, PanelRightOpen, PanelRightClose, Clock, Trash2, Plus, CheckCircle2, XCircle, AlertTriangle, Maximize2, Minimize2, Terminal, Check, X } from 'lucide-react';
import styles from './ChatPanel.module.css';

import { Message, CompanyResult } from './ChatInterfaces';
import { ChatInput } from './ChatInput';
import { AIModel, ModelSelector } from './ModelSelector';
import { ChatMessage, RichLogRenderer } from './ChatMessage';
import { AgentV2Message, V2Event, TaskStatus, InlineEventStream, MappedContact } from './AgentV2Message';
import { ModelActivityEvent } from './ModelActivityBar';
import { ActivitySidebar } from './ActivitySidebar';
import { ThreadList } from './ThreadList';
import { Avatar, Modal, Button } from '../ui';

import { useSpeechToText } from '../../hooks/useSpeechToText';
import { ai, communication, conversations } from '@/services/api';

const V2_STREAM_URL = ai.getV2ChatStreamUrl();
const V2_CONFIRM_URL = ai.getV2ConfirmStreamUrl();
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
}) => {
    const { isListening, isTranscribing, transcript, finalTranscript, error: voiceError, startListening, stopListening, clearTranscript, isSupported: voiceSupported, analyserNode } = useSpeechToText();

    const hasValidOrg = !!(selectedOrgName && selectedOrgName.trim() !== '');
    const cleanOrgName = hasValidOrg ? selectedOrgName!.trim() : '';

    // ─── View state ──────────────────────────────────────────
    const [view, setView] = useState<PanelView>(() => {
        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            const savedThreadId = window.localStorage.getItem(`active-thread-id-${targetOrgId}`);
            const savedView = window.localStorage.getItem('chat-panel-view');
            if (savedView === 'list' && !savedThreadId) {
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

    // ─── Chat state ──────────────────────────────────────────
    const [messages, setMessages] = useState<Message[]>([]);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [selectedCompanies, setSelectedCompanies] = useState<CompanyResult[]>([]);
    const [currentLogs, setCurrentLogs] = useState<any[]>([]);
    const [approvalStatuses, setApprovalStatuses] = useState<Record<string, 'pending' | 'approving' | 'approved' | 'rejected'>>({});
    const [model, setModel] = useState<AIModel>(() => {
        const saved = localStorage.getItem('ai_preferred_model');
        return (saved as AIModel) || 'claude';
    });
    const [strictMode, setStrictMode] = useState<boolean>(() => {
        const saved = localStorage.getItem('ai_strict_mode');
        return saved === 'true';
    });
    // Modelo ativo em tempo real durante fallback (só visível quando não está em strict mode)
    const [liveModel, setLiveModel] = useState<AIModel | null>(null);
    const [modelActivity, setModelActivity] = useState<ModelActivityEvent[]>([]);
    const modelActivityIdRef = useRef(0);
    const [pipedriveCooldown, setPipedriveCooldown] = useState<number>(0);

    // ─── Agent mode (v1 = padrão, v2 = agente autônomo) ─────
    const [agentMode, setAgentMode] = useState<'v1' | 'v2'>('v2');
    // v2: eventos em streaming para a mensagem sendo construída
    const [v2Events, setV2Events] = useState<any[]>([]);
    const [v2Streaming, setV2Streaming] = useState(false);
    // v2: confirmações já decididas { action_id -> approved }
    const [v2ConfirmedActions, setV2ConfirmedActions] = useState<Record<string, boolean>>({});
    const abortControllerRef = useRef<AbortController | null>(null);

    const handleStopStreaming = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setIsLoading(false);
        setV2Streaming(false);
        setActiveRunningTask(prev => prev?.status === 'streaming' ? { ...prev, status: 'done' } : prev);
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
    const taskConsoleLogsBottomRef = useRef<HTMLDivElement>(null);

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
        setV2Streaming(true);

        const handleScanDone = (e: Event) => {
            window.removeEventListener('hierarchy_scan_done', handleScanDone);
            const contacts = (e as CustomEvent).detail?.contacts || [];
            handleMainChatMappingDone(contacts, ctx.event as V2Event);
        };

        window.addEventListener('hierarchy_scan_done', handleScanDone);

        // Dispara evento para o HierarchyMappingCard (se ainda montado) mostrar "scanning"
        window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));

        return () => window.removeEventListener('hierarchy_scan_done', handleScanDone);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);



    const streamTaskInto = async (url: string, body: object, initialTaskState: typeof activeRunningTask) => {
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
                        setActiveRunningTask(prev => {
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
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
        }
        return collected;
    };

    const handleApproveSuggestedAction = async (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => {
        const taskKey = `${parentMessageId}-${index}`;
        
        setApprovedSuggestedActions(prev => ({
            ...prev,
            [taskKey]: 'streaming'
        }));

        const newTask = {
            label: action.label,
            prompt: action.prompt,
            status: 'streaming' as const,
            logs: [] as V2Event[],
            isExpanded: true, // Autoexpand upon approval for immersive execution Console!
            orgId: selectedOrgId,
            threadId: activeThread?.id,
            actionIndex: index,
            parentMessageId,
        };
        
        setActiveRunningTask(newTask);
        setTaskInlineConfirmed({});

        try {
            const collected = await streamTaskInto(V2_STREAM_URL, {
                message: action.prompt,
                org_id: selectedOrgId,
                thread_id: activeThread?.id,
                history: [],
                direct_action: true,
                parent_message_id: parentMessageId,
                action_index: index,
            }, newTask);

            const hierarchyEv = collected.find(e => e.type === 'hierarchy_mapping_required');
            const pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
            
            let finalStatus: TaskStatus = 'done';
            if (hierarchyEv) {
                finalStatus = 'awaiting_mapping';
            } else if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            }

            setActiveRunningTask(prev => prev ? { ...prev, status: finalStatus } : null);
            setApprovedSuggestedActions(prev => ({
                ...prev,
                [taskKey]: finalStatus
            }));
            
            if (selectedOrgId) {
                conversations.listThreads(selectedOrgId).then(setThreads).catch(() => {});
            }
        } catch {
            setActiveRunningTask(prev => prev ? { ...prev, status: 'error' } : null);
            setApprovedSuggestedActions(prev => ({
                ...prev,
                [taskKey]: 'error'
            }));
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
            const collected = await streamTaskInto(V2_CONFIRM_URL, {
                action_id,
                approved: true,
                thread_id: activeThread?.id,
            }, activeRunningTask);
            
            const pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
            let finalStatus: TaskStatus = 'done';
            if (pendingConfirm) {
                finalStatus = 'awaiting_confirm';
            }

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
            const newEvents = await streamTaskInto(V2_STREAM_URL, {
                message: continuation,
                org_id: selectedOrgId,
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
            agentMode={agentMode}
            setAgentMode={setAgentMode}
            onStop={handleStopStreaming}
            activeRunningTask={activeRunningTask}
            setActiveRunningTask={setActiveRunningTask}
            taskInlineConfirmed={taskInlineConfirmed}
            onTaskInlineConfirm={handleTaskInlineConfirm}
            onTaskMappingComplete={handleTaskMappingComplete}
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
    }, [messages, currentLogs, isAtBottom]);

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

    // ─── Open thread ─────────────────────────────────────────
    const openThread = useCallback(async (thread: ThreadOut) => {
        setActiveThread(thread);
        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            window.localStorage.setItem(`active-thread-id-${targetOrgId}`, thread.id);
            window.localStorage.setItem('chat-panel-view', 'chat');
        }
        setCurrentLogs([]);
        setView('chat');

        try {
            const msgs = await conversations.getMessages(thread.id);
            if (msgs.length === 0) {
                setMessages([{
                    id: 'welcome',
                    role: 'assistant',
                    content: hasValidOrg ? `Como posso te ajudar com a @${cleanOrgName}?` : "Como posso te ajudar hoje?",
                    timestamp: new Date(),
                }]);
            } else {
                let hasActiveJobLoading = false;
                const mappedMsgs = msgs.map((m: MessageOut) => {
                    const isV2 = !!(m.logs && Array.isArray(m.logs) && m.logs.some((l: any) => l.type === 'tool_call' || l.type === 'thinking' || l.type === 'final'));
                    let forceV2Streaming = false;
                    if (isV2 && m.logs && Array.isArray(m.logs)) {
                        const hasMapping = m.logs.some((l: any) => l.type === 'hierarchy_mapping_required');
                        if (hasMapping && typeof window !== 'undefined') {
                            const activeJob = window.localStorage.getItem('active-discovery-job');
                            if (activeJob) {
                                forceV2Streaming = true;
                                hasActiveJobLoading = true;
                            }
                        }
                    }
                    return {
                        id: m.id,
                        role: m.role as 'user' | 'assistant',
                        content: m.content,
                        timestamp: new Date(m.timestamp),
                        ui_module: (m.ui_module as any) ?? undefined,
                        data: m.data ?? undefined,
                        logs: m.logs ?? undefined,
                        isV2: isV2,
                        v2Events: isV2 ? (m.logs ?? undefined) : undefined,
                        v2Streaming: forceV2Streaming ? true : undefined,
                    };
                });

                if (hasActiveJobLoading) {
                    setIsLoading(true);
                    setV2Streaming(true);
                }
                setMessages(mappedMsgs);
            }
        } catch (err) {
            console.error('[ChatPanel] Erro ao carregar mensagens:', err);
            setMessages([{
                id: 'welcome',
                role: 'assistant',
                content: hasValidOrg ? `Como posso te ajudar com a @${cleanOrgName}?` : "Como posso te ajudar hoje?",
                timestamp: new Date(),
            }]);
        }
    }, [selectedOrgId, selectedOrgName, hasValidOrg, cleanOrgName]);

    // ─── Load threads and activities ────────────────────────
    const loadThreads = useCallback(async () => {
        setIsLoadingThreads(true);
        try {
            const targetOrgId = selectedOrgId || 0;
            const [threadList, actList] = await Promise.all([
                conversations.listThreads(targetOrgId),
                conversations.listActivities(targetOrgId),
            ]);
            setThreads(threadList);
            setActivities(actList);

            // Restore active thread from localStorage
            if (typeof window !== 'undefined') {
                const savedThreadId = window.localStorage.getItem(`active-thread-id-${targetOrgId}`);
                if (savedThreadId) {
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
    }, [selectedOrgId, openThread]);

    // ─── Load threads when org changes ──────────────────────
    useEffect(() => {
        setActiveThread(null);
        setMessages([]);

        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            const savedThreadId = window.localStorage.getItem(`active-thread-id-${targetOrgId}`);
            const savedView = window.localStorage.getItem('chat-panel-view');
            if (savedView === 'list' && !savedThreadId) {
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
    }, [selectedOrgId]);

    const handleNewThread = () => {
        setActiveThread(null);
        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            window.localStorage.removeItem(`active-thread-id-${targetOrgId}`);
            window.localStorage.setItem('chat-panel-view', 'chat');
        }
        setMessages([]);
        setView('chat');
    };

    // ─── Back to list ────────────────────────────────────────
    const handleBackToList = async () => {
        setView('list');
        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            window.localStorage.removeItem(`active-thread-id-${targetOrgId}`);
            window.localStorage.setItem('chat-panel-view', 'list');
        }
        setActiveThread(null);
        setMessages([]);
        setCurrentLogs([]);
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

    // ─── Core Chat Workflow ──────────────────────────────────
    const executeChatWorkflow = async (
        text: string,
        companiesSelected: CompanyResult[],
        threadId: string,
        historyForApi: { role: string, content: string }[],
        isSuggestedAction: boolean = false
    ) => {
        setIsLoading(true);
        setCurrentLogs([]);

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        try {
            const response = await fetch(ai.getChatStreamUrl(), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    orgId: selectedOrgId,
                    selectedCompanies: companiesSelected,
                    context: 'hierarchy_analysis',
                    model,
                    thread_id: threadId,
                    history: historyForApi,
                    suggested_action: isSuggestedAction,
                }),
                signal: controller.signal,
            });

            if (!response.ok) {
                let errorMsg = `Erro ${response.status}`;
                try { const e = await response.json(); errorMsg = e?.detail || e?.error?.message || errorMsg; } catch { /* ignore */ }
                setMessages(prev => [...prev, {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: `Não consegui processar sua mensagem. ${errorMsg}`,
                    timestamp: new Date(),
                }]);
                return;
            }

            const contentType = response.headers.get('content-type');
            if (contentType?.includes('application/x-ndjson') && response.body) {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                const sessionLogs: any[] = [];

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.trim()) continue;
                        try {
                            const chunk = JSON.parse(line);
                            if (['log','thought','status','data_found','warning','stage_blocked','stage_ok'].includes(chunk.type)) {
                                sessionLogs.push(chunk);
                                setCurrentLogs([...sessionLogs]);
                                if (chunk.pipedrive_cooldown) setPipedriveCooldown(chunk.pipedrive_cooldown);
                            } else if (chunk.type === 'final') {
                                if (chunk.pipedrive_cooldown) setPipedriveCooldown(chunk.pipedrive_cooldown);
                                setMessages(prev => [...prev, {
                                    id: (Date.now() + 1).toString(),
                                    role: 'assistant',
                                    content: chunk.response || 'Finalizado.',
                                    timestamp: new Date(),
                                    ui_module: chunk.ui_module,
                                    data: chunk.data,
                                    logs: [...sessionLogs],
                                    pending_approvals: chunk.data?.pending_approvals || [],
                                    suggested_actions: chunk.data?.suggested_actions || [],
                                }]);
                                // Refresh thread title/count silently
                                const targetOrgId = selectedOrgId || 0;
                                conversations.listThreads(targetOrgId).then(setThreads).catch(() => {});
                            }
                        } catch { /* ignore */ }
                    }
                }
            } else {
                const data = await response.json();
                if (data.pipedrive_cooldown) setPipedriveCooldown(data.pipedrive_cooldown);
                setMessages(prev => [...prev, {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: data.response,
                    timestamp: new Date(),
                    ui_module: data.ui_module,
                    data: data.data,
                }]);
            }
        } catch (error) {
            if ((error as any)?.name === 'AbortError') {
                console.log('[Chat] Stream cancelado pelo usuário');
            } else {
                console.error('Erro ao executar workflow:', error);
            }
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            setIsLoading(false);
        }
    };

    // ─── V2: executar workflow do agente autônomo ────────────
    const executeAgentV2 = async (text: string, threadId: string, historyForApi: any[]) => {
        setIsLoading(true);
        setV2Events([]);
        setV2Streaming(true);

        const msgId = (Date.now() + 1).toString();

        // Adiciona mensagem "em andamento" do assistente
        setMessages(prev => [...prev, {
            id: msgId,
            role: 'assistant' as const,
            content: '',
            timestamp: new Date(),
            v2Events: [] as any[],
            isV2: true,
        }]);

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        let hasMappingRequired = false;
        let hasConfirmationRequired = false;

        try {
            const response = await fetch(ai.getV2ChatStreamUrl(), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, history: historyForApi, org_id: selectedOrgId, thread_id: threadId }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                const errText = response.ok ? 'Sem corpo na resposta' : `Erro ${response.status}`;
                setMessages(prev => prev.map(m =>
                    m.id === msgId ? { ...m, content: `Não consegui processar: ${errText}`, v2Streaming: false } : m
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

                        // Modelo ativo — atualiza o selector e a barra de atividade
                        if (event.type === 'model_active') {
                            if (!strictMode) setLiveModel(event.provider as AIModel);
                            setModelActivity(prev => {
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
                            setModelActivity(prev => [...prev, { id: ++modelActivityIdRef.current, type: 'rate_wait', provider: event.provider as AIModel | undefined, model: event.model, wait_sec: event.wait_sec, reason: event.reason, timestamp: Date.now() }]);
                        }
                        if (event.type === 'context_overflow') {
                            setModelActivity(prev => [...prev, { id: ++modelActivityIdRef.current, type: 'context_overflow', model: event.model, estimated_tokens: event.estimated_tokens, limit: event.limit, timestamp: Date.now() }]);
                        }

                        // Atualiza a mensagem em tempo real
                        setMessages(prev => prev.map(m =>
                            m.id === msgId ? { ...m, v2Events: [...collectedEvents] } : m
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
            }

            // Marca streaming como concluído, limpa modelos live
            setLiveModel(null);
            // Mantém a barra visível por 3s se houver eventos de espera, depois limpa
            const hadWaits = modelActivity.some(e => e.type === 'rate_wait' || e.type === 'context_overflow');
            if (hadWaits) {
                setTimeout(() => setModelActivity([]), 3000);
            } else {
                setModelActivity([]);
            }
            // Não alteramos o v2Streaming aqui pois faremos isso no finally com base na variável hasMappingRequired

        } catch (err) {
            if ((err as any)?.name === 'AbortError') {
                console.log('[AgentV2] Stream cancelado pelo usuário');
            } else {
                console.error('[AgentV2] Erro:', err);
            }
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            
            
            setMessages(prev => prev.map(m =>
                m.id === msgId ? { ...m, v2Streaming: hasMappingRequired ? true : false } : m
            ));
            
            if (!hasMappingRequired && !hasConfirmationRequired) {
                setIsLoading(false);
                setV2Streaming(false);
            }
        }
    };

    // ─── V2: lidar com finalização de mapeamento no chat principal
    // ─── V2: lidar com finalização de mapeamento no chat principal
    const handleMainChatMappingDone = async (contacts: any[], event?: V2Event) => {
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

        // Detecta decisores de compras/logística pelo cargo
        const isBuyingDecisionMaker = (role: string) => {
            const r = (role || '').toLowerCase();
            return ['compras', 'procurement', 'suprimentos', 'logística', 'logistica',
                    'supply chain', 'supply', 'materiais', 'aquisição', 'aquisicao',
                    'estoque', 'sourcing'].some(k => r.includes(k));
        };

        const contactsSummary = contacts.length > 0
            ? contacts.map((c: any) => `- ${c.name} (${c.role}${c.department ? ', ' + c.department : ''}${c.email ? ', ' + c.email : ''}${c.temperature ? ', temp=' + c.temperature : ''}${c.decision_maker ? ', DECISOR' : ''})`).join('\n')
            : '';

        const baseProhibition = `REGRA CRÍTICA: Estes contatos são leads frios do LinkedIn — PROIBIDO chamar whatsapp_get_messages, email_get_contact_history ou whatsapp_list_chats para eles.\n`;

        let taskInstruction: string;

        if (contacts.length === 0) {
            // Cenário C: nenhum contato aprovado pelo usuário
            taskInstruction =
                `Nenhum contato foi aprovado pelo usuário no carrossel de revisão.\n` +
                `Chame find_company_contact com org_name="${orgName}" para buscar o telefone geral/PABX da empresa. ` +
                `Se encontrar dados, crie um contato genérico no Pipedrive com pipedrive_create_person (org_id=${orgId}${dealClause}) ` +
                `e prossiga executando a tarefa original. ` +
                `Se não encontrar nada, informe ao João e sugira próximas ações.`;
        } else {
            const decisionMakers = contacts.filter((c: any) => c.decision_maker || isBuyingDecisionMaker(c.role));
            const best = decisionMakers[0] || contacts[0];

            const contactsBlock = `Contatos aprovados pelo usuário (${contacts.length}):\n${contactsSummary}`;
            const createCmd =
                `Cadastre ${best.name} no Pipedrive chamando pipedrive_create_person ` +
                `(org_id=${orgId}${dealClause}${best.email ? `, email="${best.email}"` : ''}). ` +
                `Após cadastrar, execute a tarefa original com esse contato.`;

            if (decisionMakers.length > 0) {
                // Cenário A: decisor de compras/logística encontrado
                taskInstruction =
                    `${contactsBlock}\n\n` +
                    `ANÁLISE: ${best.name} (${best.role}) é decisor de compras/logística — contato ideal para a prospecção.\n` +
                    createCmd;
            } else {
                // Cenário B: contatos encontrados mas sem decisor direto de compras
                taskInstruction =
                    `${contactsBlock}\n\n` +
                    `ANÁLISE: Nenhum aprovado tem cargo de compras/logística. ` +
                    `${best.name} (${best.role}) é o contato mais relevante disponível. ` +
                    `Nota para tarefas de prospecção: ${best.name} pode servir como porta de entrada para chegar ao decisor de compras via indicação interna.\n` +
                    createCmd;
            }
        }

        const continuation = (
            `[SISTEMA]: Mapeamento de hierarquia concluído para "${orgName}". ${contacts.length} contato(s) aprovados pelo usuário.\n` +
            baseProhibition +
            taskInstruction +
            (preTaskClause ? `\n${preTaskClause}` : '') +
            activityClause
        );

        const targetMsg = messages.find(m => m.v2Events && m.v2Events.some(e => e.type === 'hierarchy_mapping_required'));
        if (!targetMsg || !targetMsg.id) {
            // Fallback se não encontrar a mensagem anterior
            setIsLoading(false);
            setV2Streaming(false);
            setTimeout(() => handleSendMessage(continuation, [], true), 0);
            return;
        }

        const targetMsgId = targetMsg.id;
        const existingEvents = targetMsg.v2Events || [];

        setIsLoading(true);
        setV2Streaming(true);
        setMessages(prev => prev.map(m => m.id === targetMsgId ? { ...m, v2Streaming: true } : m));

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        const threadId = activeThread?.id || '';

        try {
            const response = await fetch(V2_STREAM_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: continuation, direct_action: true, org_id: selectedOrgId, thread_id: threadId }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                setMessages(prev => prev.map(m => m.id === targetMsgId ? { ...m, v2Streaming: false } : m));
                setIsLoading(false);
                setV2Streaming(false);
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
                            if (!strictMode) setLiveModel(eventObj.provider as AIModel);
                            setModelActivity(prev => {
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
                            setModelActivity(prev => [...prev, { id: ++modelActivityIdRef.current, type: 'rate_wait', provider: eventObj.provider as AIModel | undefined, model: eventObj.model, wait_sec: eventObj.wait_sec, reason: eventObj.reason, timestamp: Date.now() }]);
                        }
                        if (eventObj.type === 'context_overflow') {
                            setModelActivity(prev => [...prev, { id: ++modelActivityIdRef.current, type: 'context_overflow', model: eventObj.model, estimated_tokens: eventObj.estimated_tokens, limit: eventObj.limit, timestamp: Date.now() }]);
                        }

                        setMessages(prev => prev.map(m =>
                            m.id === targetMsgId ? { ...m, v2Events: [...existingEvents, ...collectedEvents] } : m
                        ));
                    } catch { /* ignore */ }
                }
            }

            setLiveModel(null);
            const hadWaits = modelActivity.some(e => e.type === 'rate_wait' || e.type === 'context_overflow');
            if (hadWaits) {
                setTimeout(() => setModelActivity([]), 3000);
            } else {
                setModelActivity([]);
            }
        } catch (err) {
            console.error('[AgentV2 Continuation] Erro:', err);
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            setMessages(prev => prev.map(m => m.id === targetMsgId ? { ...m, v2Streaming: false } : m));
            setIsLoading(false);
            setV2Streaming(false);
        }
    };

    // ─── V2: lidar com confirmação de ação ───────────────────
    const handleV2Confirm = async (action_id: string, approved: boolean) => {
        setV2ConfirmedActions(prev => ({ ...prev, [action_id]: approved }));

        // Marca todas as mensagens com esse action_id
        setMessages(prev => prev.map(m => {
            if (!m.isV2 || !m.v2Events) return m;
            const hasAction = m.v2Events.some((e: any) => e.action_id === action_id);
            if (!hasAction) return m;
            return { ...m, v2ConfirmedActions: { ...(m.v2ConfirmedActions || {}), [action_id]: approved } };
        }));

        if (!approved) return;

        // Chama o endpoint de confirmação e faz streaming do resultado
        const threadId = activeThread?.id || '';
        setIsLoading(true);
        setV2Streaming(true);

        const msgId = (Date.now() + 2).toString();
        setMessages(prev => [...prev, {
            id: msgId,
            role: 'assistant' as const,
            content: '',
            timestamp: new Date(),
            v2Events: [],
            isV2: true,
        }]);

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        try {
            const response = await fetch(ai.getV2ConfirmStreamUrl(), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action_id, approved, thread_id: threadId }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                const errText = response.ok ? 'Sem corpo na resposta' : `Erro ${response.status}`;
                setMessages(prev => prev.map(m =>
                    m.id === msgId ? { ...m, content: `Falha ao confirmar ação: ${errText}`, v2Streaming: false } : m
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
                        setMessages(prev => prev.map(m =>
                            m.id === msgId ? { ...m, v2Events: [...collectedEvents] } : m
                        ));
                    } catch { /* ignore */ }
                }
            }

            setMessages(prev => prev.map(m =>
                m.id === msgId ? { ...m, v2Events: [...collectedEvents], v2Streaming: false } : m
            ));
        } catch (err) {
            if ((err as any)?.name === 'AbortError') {
                console.log('[AgentV2 Confirm] Stream cancelado pelo usuário');
            } else {
                console.error('[AgentV2] Confirm error:', err);
            }
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            setIsLoading(false);
            setV2Streaming(false);
        }
    };

    // ─── Send message ────────────────────────────────────────
    const handleSendMessage = async (text: string, companiesSelected: CompanyResult[], isSuggestedAction: boolean = false) => {
        if (!text.trim() && companiesSelected.length === 0) return;

        // Garante transição visual para a tela do chat ativo ao enviar qualquer mensagem
        setView('chat');

        const threadId = await ensureThread();
        if (!threadId) return;

        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: text,
            timestamp: new Date(),
            selectedCompanies: companiesSelected.length > 0 ? [...companiesSelected] : undefined,
        };

        const historyForApi = messages.slice(-6).map(m => ({ role: m.role, content: m.content }));

        setIsAtBottom(true);
        setMessages(prev => [...prev, userMsg]);
        setInputValue('');
        setSelectedCompanies([]);

        if (agentMode === 'v2') {
            await executeAgentV2(text, threadId, historyForApi);
        } else {
            await executeChatWorkflow(text, companiesSelected, threadId, historyForApi, isSuggestedAction);
        }
    };

    useEffect(() => {
        const handleAgentPrompt = (e: Event) => {
            const customEvent = e as CustomEvent<{ prompt: string }>;
            if (customEvent.detail && customEvent.detail.prompt) {
                handleSendMessage(customEvent.detail.prompt, [], false);
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
        if (agentMode === 'v2') {
            await executeAgentV2(lastUserMsg.content, threadId, historyForApi);
        } else {
            await executeChatWorkflow(lastUserMsg.content, lastUserMsg.selectedCompanies || [], threadId, historyForApi);
        }
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

    if (!showChat) return null;

    // ═══════════════════════════════════════════
    // RENDER: List view
    // ═══════════════════════════════════════════

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
            <div className={`${styles.chatPanel} ${styles[theme]}`} data-theme={theme}>
                <ThreadList
                    orgName={hasValidOrg ? cleanOrgName : 'Geral'}
                    threads={threads}
                    isLoading={isLoadingThreads}
                    onSelectThread={openThread}
                    onNewThread={handleNewThread}
                    isCreating={isCreatingThread}
                    selectedOrgLogo={selectedOrgLogo}
                    onDeleteThread={(t) => setThreadsToDelete([t])}
                    onDeleteThreadsBulk={setThreadsToDelete}
                    onCloseChat={() => setShowChat(false)}
                    onBackToChat={() => setView('chat')}
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
        <div className={`${styles.chatPanel} ${styles[theme]}`} data-theme={theme}>

            {/* Chat sub-header: back + thread title + activities toggle */}
            <div className={styles.chatSubHeader} style={{ paddingLeft: '16px', gap: '12px' }}>
                <Avatar 
                    kind="company"
                    src={selectedOrgLogo}
                    name={selectedOrgName}
                    size={32}
                    noInitialFallback={true}
                    style={{ border: selectedOrgLogo ? '1.5px solid var(--sw-border-strong)' : 'none' }}
                />
                <div className={styles.chatSubHeaderInfo} style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '8px', flex: '0 1 auto', minWidth: 0 }}>
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

            {/* Body: messages + optional sidebar */}
            <div className={`${styles.chatBody} ${messages.length === 0 ? styles.emptyChatBody : ''}`}>
                {messages.length === 0 ? (
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
                                if (message.isV2 && message.role === 'assistant') {
                                    return (
                                        <AgentV2Message
                                            key={message.id}
                                            messageId={message.id}
                                            events={message.v2Events || []}
                                            isStreaming={message.v2Streaming !== false && v2Streaming}
                                            onConfirm={handleV2Confirm}
                                            confirmedActions={message.v2ConfirmedActions || {}}
                                            onRegenerate={() => handleRegenerate(message.id)}
                                            onAction={(prompt: string) => handleSendMessage(prompt, [], true)}
                                            streamV2Url={V2_STREAM_URL}
                                            confirmV2Url={V2_CONFIRM_URL}
                                            orgId={selectedOrgId}
                                             selectedOrgName={cleanOrgName}
                                            threadId={activeThread?.id}
                                            approvedSuggestedActions={approvedSuggestedActions}
                                            onApproveSuggestedAction={handleApproveSuggestedAction}
                                            onHierarchyMappingDone={handleMainChatMappingDone}
                                            model={model}
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

                            {/* Thinking panel */}
                            {isLoading && agentMode === 'v1' && (
                                <div className={styles.debugPanel}>
                                    <details className={styles.debugSection} style={{ border: 'none', background: 'transparent' }} open>
                                        <summary className={styles.debugSummary}>
                                            <span>Agente está pensando...</span>
                                            <ChevronRight size={12} className={styles.chevron} />
                                        </summary>
                                        <div className={styles.streamingLogs}>
                                            {currentLogs.length === 0
                                                ? <div className={styles.logLine}><Loader2 size={12} className={styles.spinner} /> <span>Iniciando pipeline...</span></div>
                                                : currentLogs.map((log, i) => <RichLogRenderer key={i} log={log} onOpenWhatsApp={onOpenWhatsApp} />)
                                            }
                                        </div>
                                    </details>
                                </div>
                            )}
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
