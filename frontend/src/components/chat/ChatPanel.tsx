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
    const [approvalStatuses, setApprovalStatuses] = useState<Record<string, 'pending' | 'approving' | 'approved' | 'rejected'>>({});
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
    // Modelo ativo em tempo real durante fallback (só visível quando não está em strict mode)
    const [liveModel, setLiveModel] = useState<AIModel | null>(null);
    const [modelActivity, setModelActivity] = useState<ModelActivityEvent[]>([]);
    const modelActivityIdRef = useRef(0);
    const [pipedriveCooldown, setPipedriveCooldown] = useState<number>(0);

    // ─── Agente: eventos em streaming para a mensagem sendo construída ──────────
    const [agentEvents, setAgentEvents] = useState<any[]>([]);
    const [agentStreaming, setAgentStreaming] = useState(false);
    // Confirmações já decididas { action_id -> approved }
    const [agentConfirmedActions, setAgentConfirmedActions] = useState<Record<string, boolean>>({});
    const abortControllerRef = useRef<AbortController | null>(null);

    const handleStopStreaming = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setIsLoading(false);
        setAgentStreaming(false);
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
        logs: AgentEvent[];
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

        try {
            const jobData = JSON.parse(activeJob);
            if (jobData) {
                if (Number(jobData.orgId) !== Number(selectedOrgId)) {
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
            if (eventOrgId && Number(eventOrgId) !== Number(selectedOrgId)) {
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
    }, [selectedOrgId]);



    const streamTaskInto = async (url: string, body: object, initialTaskState: typeof activeRunningTask) => {
        const collected: AgentEvent[] = [];
        
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
                        const ev: AgentEvent = JSON.parse(line);
                        collected.push(ev);

                        // Side effects based on tool results
                        if (ev.type === 'tool_result' && ev.ok) {
                            const tool = ev.tool || '';
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

    const handleCancelActiveTask = () => {
        if (activeRunningTask) {
            const { parentMessageId, actionIndex } = activeRunningTask;
            if (parentMessageId && actionIndex !== undefined) {
                const taskKey = `${parentMessageId}-${actionIndex}`;
                setApprovedSuggestedActions(prev => {
                    const currentStatus = prev[taskKey];
                    if (currentStatus === 'done' || currentStatus === 'error') return prev;
                    
                    // Persiste o cancelamento para o backend (resetando para pending)
                    conversations.updateSuggestedActionStatus(parentMessageId, actionIndex, 'pending').catch(err => {
                        console.error('Failed to persist task cancellation', err);
                    });
                    
                    return { ...prev, [taskKey]: 'pending' };
                });
            }
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
            setActiveRunningTask(null);
        }
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
            logs: [] as AgentEvent[],
            isExpanded: true, // Autoexpand upon approval for immersive execution Console!
            orgId: selectedOrgId,
            threadId: activeThread?.id,
            actionIndex: index,
            parentMessageId,
        };
        
        setActiveRunningTask(newTask);
        setTaskInlineConfirmed({});

        try {
            const collected = await streamTaskInto(AGENT_STREAM_URL, {
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

            // Persiste para o backend para garantir que o estado se mantenha ao sair/voltar
            if (parentMessageId) {
                conversations.updateSuggestedActionStatus(parentMessageId, index, finalStatus).catch(err => {
                    console.error('Failed to persist task status', err);
                });
            }
            
            if (finalStatus === 'done') {
                setTimeout(() => {
                    setActiveRunningTask(prev => {
                        if (prev && prev.actionIndex === index) return null;
                        return prev;
                    });
                }, 1500);
            }
            
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

        setActiveRunningTask(prev => prev ? { ...prev, status: 'streaming' } : null);
        if (activeRunningTask.parentMessageId) {
            const taskKey = `${activeRunningTask.parentMessageId}-${activeRunningTask.actionIndex}`;
            setApprovedSuggestedActions(prev => ({ ...prev, [taskKey]: 'streaming' }));
        }

        try {
            const collected = await streamTaskInto(AGENT_CONFIRM_URL, {
                action_id,
                approved,
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

                // Persiste para o backend para garantir persistência ao sair/voltar
                conversations.updateSuggestedActionStatus(activeRunningTask.parentMessageId, activeRunningTask.actionIndex, finalStatus).catch(err => {
                    console.error('Failed to persist task status', err);
                });
            }
            if (finalStatus === 'done') {
                const currentIdx = activeRunningTask.actionIndex;
                setTimeout(() => {
                    setActiveRunningTask(prev => {
                        if (prev && prev.actionIndex === currentIdx) return null;
                        return prev;
                    });
                }, 1500);
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
            const newEvents = await streamTaskInto(AGENT_STREAM_URL, {
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

                // Persiste para o backend para garantir persistência ao sair/voltar
                conversations.updateSuggestedActionStatus(activeRunningTask.parentMessageId, activeRunningTask.actionIndex, finalStatus).catch(err => {
                    console.error('Failed to persist task status', err);
                });
            }
            if (finalStatus === 'done') {
                const currentIdx = activeRunningTask.actionIndex;
                setTimeout(() => {
                    setActiveRunningTask(prev => {
                        if (prev && prev.actionIndex === currentIdx) return null;
                        return prev;
                    });
                }, 1500);
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

    // ─── Open thread ─────────────────────────────────────────
    const openThread = useCallback(async (thread: ThreadOut) => {
        setActiveThread(thread);
        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            window.localStorage.setItem(`active-thread-id-${targetOrgId}`, thread.id);
            window.localStorage.setItem('chat-panel-view', 'chat');
        }
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
                                        threadId: thread.id,
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
                setApprovedSuggestedActions(initialSuggestedActions);
                if (restoredTask) {
                    setActiveRunningTask(restoredTask);
                } else {
                    setActiveRunningTask(null);
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
        setApprovedSuggestedActions({});
        setAgentConfirmedActions({});
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
        setApprovedSuggestedActions({});
        setAgentConfirmedActions({});
        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            window.localStorage.removeItem(`active-thread-id-${targetOrgId}`);
            window.localStorage.setItem('chat-panel-view', 'list');
        }
        setActiveThread(null);
        setMessages([]);
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
    const executeAgent = async (text: string, threadId: string, historyForApi: any[]) => {
        setIsLoading(true);
        setAgentEvents([]);
        setAgentStreaming(true);

        const msgId = (Date.now() + 1).toString();

        // Adiciona mensagem "em andamento" do assistente
        setMessages(prev => [...prev, {
            id: msgId,
            role: 'assistant' as const,
            content: '',
            timestamp: new Date(),
            agentEvents: [] as any[],
            isAgent: true,
        }]);

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        let hasMappingRequired = false;
        let hasConfirmationRequired = false;

        let apiMessage = text;
        if (selectedOrgId && selectedOrgName) {
            apiMessage = `[ALERTA DE CONTEXTO DO SISTEMA: O usuário está na página da empresa "${selectedOrgName}" (org_id=${selectedOrgId}).\nREGRA CRÍTICA: Se o usuário pedir para atualizar ou concluir uma tarefa e NÃO fornecer o ID explícito na mensagem atual, VOCÊ É ESTRITAMENTE PROIBIDO de adivinhar ou usar IDs de tarefas do histórico. Você DEVE obrigatoriamente chamar a ferramenta \`pipedrive_get_activities\` com org_id=${selectedOrgId} para descobrir o ID correto antes de atualizar. Não atualize atividades cegamente.]\n\n${text}`;
        }

        try {
            const response = await fetch(AGENT_STREAM_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: apiMessage, history: historyForApi, org_id: selectedOrgId, thread_id: threadId }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                const errText = response.ok ? 'Sem corpo na resposta' : `Erro ${response.status}`;
                setMessages(prev => prev.map(m =>
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
                            m.id === msgId ? { ...m, agentEvents: [...collectedEvents] } : m
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
            // Não alteramos agentStreaming aqui; faremos no finally com base em hasMappingRequired

        } catch (err) {
            if ((err as any)?.name === 'AbortError') {
                console.log('[Agent] Stream cancelado pelo usuário');
            } else {
                console.error('[Agent] Erro:', err);
            }
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            
            
            setMessages(prev => prev.map(m =>
                m.id === msgId ? { ...m, agentStreaming: hasMappingRequired ? true : false } : m
            ));

            if (!hasMappingRequired && !hasConfirmationRequired) {
                setIsLoading(false);
                setAgentStreaming(false);
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

        // ── SEGURANÇA: Remove qualquer contato rejeitado ou pendente que possa ter escapado
        const approvedContacts = contacts.filter((c: any) => {
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
                `Nenhum contato foi aprovado pelo usuário no carrossel de revisão.\n` +
                `Chame find_company_contact com org_name="${orgName}" para buscar o telefone geral/PABX da empresa. ` +
                `Se encontrar dados, crie um contato genérico no Pipedrive com pipedrive_create_person (org_id=${orgId}${dealClause}) ` +
                `e prossiga executando a tarefa original. ` +
                `Se não encontrar nada, informe ao João e sugira próximas ações.`;
        } else {
            const decisionMakers = approvedContacts.filter((c: any) => c.decision_maker || isBuyingDecisionMaker(c.role, c.department));
            // Exclui "Análise Humana" de ser o "melhor" candidato automático — prefere cargos reais
            const definedRoles = approvedContacts.filter((c: any) => c.role !== 'Análise Humana');
            const best = decisionMakers[0] || definedRoles[0] || approvedContacts[0];

            const contactsBlock = `Contatos aprovados pelo usuário (${approvedContacts.length}):\n${contactsSummary}`;
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
            } else if (best.role === 'Análise Humana') {
                // Cenário D: todos os contatos precisam de análise humana — não há cargo definido
                taskInstruction =
                    `${contactsBlock}\n\n` +
                    `ANÁLISE: Nenhum contato tem cargo definido — todos estão como "Análise Humana". ` +
                    `Não há decisor claro de compras. ` +
                    `Informe ao João quais contatos estão disponíveis e pergunte com qual ele quer prosseguir antes de cadastrar qualquer pessoa no Pipedrive. ` +
                    `NÃO cadastre nenhum contato automaticamente neste cenário.`;
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
            `[SISTEMA]: Mapeamento de hierarquia concluído para "${orgName}". ${approvedContacts.length} contato(s) aprovados pelo usuário.\n` +
            baseProhibition +
            taskInstruction +
            (preTaskClause ? `\n${preTaskClause}` : '') +
            activityClause
        );

        const targetMsg = messages.find(m => m.agentEvents && m.agentEvents.some(e => e.type === 'hierarchy_mapping_required'));
        if (!targetMsg || !targetMsg.id) {
            // Fallback se não encontrar a mensagem anterior
            setIsLoading(false);
            setAgentStreaming(false);
            setTimeout(() => handleSendMessage(continuation, [], true), 0);
            return;
        }

        const targetMsgId = targetMsg.id;
        const existingEvents = targetMsg.agentEvents || [];

        setIsLoading(true);
        setAgentStreaming(true);
        setMessages(prev => prev.map(m => m.id === targetMsgId ? { ...m, agentStreaming: true } : m));

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

        const threadId = activeThread?.id || '';

        try {
            const response = await fetch(AGENT_STREAM_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: continuation, direct_action: true, org_id: selectedOrgId, thread_id: threadId }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                setMessages(prev => prev.map(m => m.id === targetMsgId ? { ...m, agentStreaming: false } : m));
                setIsLoading(false);
                setAgentStreaming(false);
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
                            m.id === targetMsgId ? { ...m, agentEvents: [...existingEvents, ...collectedEvents] } : m
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
            console.error('[Agent Continuation] Erro:', err);
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            setMessages(prev => prev.map(m => m.id === targetMsgId ? { ...m, agentStreaming: false } : m));
            setIsLoading(false);
            setAgentStreaming(false);
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
        const threadId = activeThread?.id || '';
        setIsLoading(true);
        setAgentStreaming(true);
        
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
        }]);

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        const controller = new AbortController();
        abortControllerRef.current = controller;

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

                        setMessages(prev => prev.map(m =>
                            m.id === msgId ? { ...m, agentEvents: [...collectedEvents] } : m
                        ));
                    } catch { /* ignore */ }
                }
            }

            setMessages(prev => prev.map(m =>
                m.id === msgId ? { ...m, agentEvents: [...collectedEvents], agentStreaming: false } : m
            ));
        } catch (err) {
            if ((err as any)?.name === 'AbortError') {
                console.log('[Agent Confirm] Stream cancelado pelo usuário');
            } else {
                console.error('[Agent] Confirm error:', err);
            }
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            setIsLoading(false);
            setAgentStreaming(false);
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

        await executeAgent(text, threadId, historyForApi);
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
                    style={{ border: selectedOrgLogo ? '3px solid var(--sw-border-strong)' : 'none' }}
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

            {/* Accordion de Contexto da Investigação */}
            <ConversationContextAccordion 
                messages={messages} 
                orgId={selectedOrgId}
                orgName={cleanOrgName}
                dealId={activeThread?.meta?.deal_id}
            />

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
