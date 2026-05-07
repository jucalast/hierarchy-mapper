import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Loader2, ChevronRight, Sparkles, ArrowLeft, PanelRightOpen, PanelRightClose, Clock, Trash2 } from 'lucide-react';
import styles from './ChatPanel.module.css';

import { Message, CompanyResult } from './chat/ChatInterfaces';
import { ChatInput } from './chat/ChatInput';
import { AIModel, ModelSelector } from './chat/ModelSelector';
import { ChatMessage, RichLogRenderer } from './chat/ChatMessage';
import { AgentV2Message } from './chat/AgentV2Message';
import { ModelActivityEvent } from './chat/ModelActivityBar';
import { ActivitySidebar } from './chat/ActivitySidebar';
import { ThreadList } from './chat/ThreadList';
import { Avatar, Modal, Button } from './ui';

import { useSpeechToText } from '../hooks/useSpeechToText';
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

    // ─── View state ──────────────────────────────────────────
    const [view, setView] = useState<PanelView>('list');
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
    const [threadToDelete, setThreadToDelete] = useState<ThreadOut | null>(null);

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
        } catch (err) {
            console.error('[ChatPanel] Erro ao carregar dados:', err);
        } finally {
            setIsLoadingThreads(false);
        }
    }, [selectedOrgId]);

    // ─── Load threads when org changes ──────────────────────
    useEffect(() => {
        setView('list');
        setActiveThread(null);
        setMessages([]);
        // Sempre carrega threads, mesmo que orgId seja nulo (orgId=0 no backend pega tudo)
        void loadThreads();
    }, [selectedOrgId, loadThreads]);

    // ─── Open thread ─────────────────────────────────────────
    const openThread = async (thread: ThreadOut) => {
        setActiveThread(thread);
        setCurrentLogs([]);
        setView('chat');

        try {
            const msgs = await conversations.getMessages(thread.id);
            if (msgs.length === 0) {
                setMessages([{
                    id: 'welcome',
                    role: 'assistant',
                    content: `Olá! Como posso ajudar com a @${selectedOrgName}?`,
                    timestamp: new Date(),
                }]);
            } else {
                setMessages(msgs.map((m: MessageOut) => {
                    const isV2 = !!(m.logs && Array.isArray(m.logs) && m.logs.some((l: any) => l.type === 'tool_call' || l.type === 'thinking' || l.type === 'final'));
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
                    };
                }));
            }
        } catch (err) {
            console.error('[ChatPanel] Erro ao carregar mensagens:', err);
            setMessages([{
                id: 'welcome',
                role: 'assistant',
                content: `Olá! Como posso ajudar com a @${selectedOrgName}?`,
                timestamp: new Date(),
            }]);
        }
    };

    // ─── Create new thread ───────────────────────────────────
    const handleNewThread = async () => {
        setIsCreatingThread(true);
        try {
            const targetOrgId = selectedOrgId || 0;
            const newThread = await conversations.createThread(targetOrgId);
            setThreads(prev => [newThread, ...prev]);
            await openThread(newThread);
        } catch (err) {
            console.error('[ChatPanel] Erro ao criar thread:', err);
        } finally {
            setIsCreatingThread(false);
        }
    };

    // ─── Back to list ────────────────────────────────────────
    const handleBackToList = async () => {
        setView('list');
        setActiveThread(null);
        setMessages([]);
        setCurrentLogs([]);
        // Refresh thread list to show updated message counts
        void loadThreads();
    };

    // ─── Delete thread ───────────────────────────────────────
    const confirmDeleteThread = async () => {
        if (!threadToDelete) return;
        const targetId = threadToDelete.id;
        try {
            await conversations.deleteThread(targetId);
            setThreads(prev => prev.filter(t => t.id !== targetId));
            if (activeThread?.id === targetId) {
                handleBackToList();
            }
        } catch (err: any) {
            // Se for 404, já foi deletada, então removemos da UI também
            if (err.status === 404) {
                setThreads(prev => prev.filter(t => t.id !== targetId));
                if (activeThread?.id === targetId) {
                    handleBackToList();
                }
            } else {
                console.error('[ChatPanel] Erro ao deletar thread:', err);
            }
        } finally {
            setThreadToDelete(null);
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
        if (!selectedOrgId) return null;
        try {
            const t = await conversations.createThread(selectedOrgId);
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
                                if (selectedOrgId) {
                                    conversations.listThreads(selectedOrgId).then(setThreads).catch(() => {});
                                }
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

            // Marca streaming como concluído, limpa modelos live
            setLiveModel(null);
            // Mantém a barra visível por 3s se houver eventos de espera, depois limpa
            const hadWaits = modelActivity.some(e => e.type === 'rate_wait' || e.type === 'context_overflow');
            if (hadWaits) {
                setTimeout(() => setModelActivity([]), 3000);
            } else {
                setModelActivity([]);
            }
            setMessages(prev => prev.map(m =>
                m.id === msgId ? { ...m, v2Events: [...collectedEvents], v2Streaming: false } : m
            ));

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
                        color: 'rgba(255, 255, 255, 0.6)',
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
                    orgName={selectedOrgName}
                    threads={threads}
                    isLoading={isLoadingThreads}
                    onSelectThread={openThread}
                    onNewThread={handleNewThread}
                    isCreating={isCreatingThread}
                    selectedOrgLogo={selectedOrgLogo}
                    onDeleteThread={setThreadToDelete}
                    onCloseChat={() => setShowChat(false)}
                />

                <Modal
                    isOpen={!!threadToDelete}
                    onClose={() => setThreadToDelete(null)}
                    title="Excluir Conversa"
                    width={400}
                    footer={
                        <>
                            <Button variant="secondary" size="sm" onClick={() => setThreadToDelete(null)}>
                                Cancelar
                            </Button>
                            <Button variant="danger" size="sm" onClick={confirmDeleteThread}>
                                Excluir
                            </Button>
                        </>
                    }
                >
                    <p style={{ margin: 0, color: 'var(--chat-text-secondary)', fontSize: '14px', lineHeight: '1.5' }}>
                        Tem certeza que deseja excluir esta conversa? Esta ação removerá permanentemente todo o histórico e não poderá ser desfeita.
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
            <div className={styles.chatSubHeader}>
                <button className={styles.chatBackBtn} onClick={handleBackToList} title="Voltar">
                    <ArrowLeft size={15} />
                </button>
                <div className={styles.chatSubHeaderAvatar}>
                    <Avatar 
                        kind="company"
                        src={selectedOrgLogo}
                        name={selectedOrgName}
                        size={32}
                        noInitialFallback={true}
                        style={{ border: selectedOrgLogo ? '3px solid #272727ff' : 'none' }}
                    />
                </div>
                <div className={styles.chatSubHeaderInfo}>
                    <span className={styles.chatSubHeaderTitle}>
                        {activeThread?.title || 'Conversa'}
                    </span>
                    <span className={styles.chatSubHeaderOrg}>{selectedOrgName || 'Geral'}</span>
                </div>
                <div style={{ flex: 1 }} />
                <button 
                    className={styles.chatHeaderDeleteBtn}
                    onClick={() => setThreadToDelete(activeThread)}
                    title="Excluir esta conversa"
                >
                    <Trash2 size={16} />
                </button>

            </div>

            {/* Body: messages + optional sidebar */}
            <div className={styles.chatBody}>
                <div className={styles.messagesContainer} ref={scrollContainerRef} onScroll={handleScroll}>
                    {messages.map(message => {
                        if (message.isV2 && message.role === 'assistant') {
                            return (
                                <AgentV2Message
                                    key={message.id}
                                    events={message.v2Events || []}
                                    isStreaming={message.v2Streaming !== false && v2Streaming}
                                    onConfirm={handleV2Confirm}
                                    confirmedActions={message.v2ConfirmedActions || {}}
                                    onRegenerate={() => handleRegenerate(message.id)}
                                    onAction={(prompt: string) => handleSendMessage(prompt, [], true)}
                                    streamV2Url={V2_STREAM_URL}
                                    confirmV2Url={V2_CONFIRM_URL}
                                    orgId={selectedOrgId}
                                    threadId={activeThread?.id}
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

            </div>

            <ChatInput
                    inputValue={inputValue}
                    setInputValue={handleInputChange}
                    isLoading={isLoading}
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
                />
        </div>
    );
};
