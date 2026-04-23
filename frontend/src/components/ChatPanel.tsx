import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Loader2, ChevronRight, Sparkles, ArrowLeft, PanelRightOpen, PanelRightClose, Clock, Trash2 } from 'lucide-react';
import styles from './ChatPanel.module.css';

import { Message, CompanyResult } from './chat/ChatInterfaces';
import { ChatInput } from './chat/ChatInput';
import { ChatMessage, RichLogRenderer } from './chat/ChatMessage';
import { ActivitySidebar } from './chat/ActivitySidebar';
import { ThreadList } from './chat/ThreadList';
import { Avatar, Modal, Button } from './ui';

import { useSpeechToText } from '../hooks/useSpeechToText';
import { ai, communication, conversations } from '@/services/api';
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
    const { isListening, transcript, startListening, stopListening } = useSpeechToText();

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
    const [model, setModel] = useState<'gemini' | 'groq'>('gemini');
    const [pipedriveCooldown, setPipedriveCooldown] = useState<number>(0);

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
    const [threadToDelete, setThreadToDelete] = useState<ThreadOut | null>(null);

    // ─── Scroll ──────────────────────────────────────────────
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, currentLogs]);

    // ─── Voice input ─────────────────────────────────────────
    useEffect(() => {
        if (transcript) setInputValue(prev => prev + transcript);
    }, [transcript]);

    // ─── Cooldown ────────────────────────────────────────────
    useEffect(() => {
        if (pipedriveCooldown > 0) {
            const timer = setInterval(() => setPipedriveCooldown(p => Math.max(0, p - 1)), 1000);
            return () => clearInterval(timer);
        }
    }, [pipedriveCooldown]);

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
        setActivities([]);
        setThreads([]);

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
                setMessages(msgs.map((m: MessageOut) => ({
                    id: m.id,
                    role: m.role as 'user' | 'assistant',
                    content: m.content,
                    timestamp: new Date(m.timestamp),
                    ui_module: (m.ui_module as any) ?? undefined,
                    data: m.data ?? undefined,
                    logs: m.logs ?? undefined,
                })));
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
        if (selectedOrgId) {
            void loadThreads();
        }
    };

    // ─── Delete thread ───────────────────────────────────────
    const confirmDeleteThread = async () => {
        if (!threadToDelete) return;
        try {
            await conversations.deleteThread(threadToDelete.id);
            setThreads(prev => prev.filter(t => t.id !== threadToDelete.id));
            if (activeThread?.id === threadToDelete.id) {
                handleBackToList();
            }
            setThreadToDelete(null);
        } catch (err) {
            console.error('[ChatPanel] Erro ao deletar thread:', err);
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
        } catch { return null; }
    };

    // ─── Send message ────────────────────────────────────────
    const handleSendMessage = async (text: string, companiesSelected: CompanyResult[]) => {
        if (!text.trim() && companiesSelected.length === 0) return;

        const threadId = await ensureThread();

        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: text,
            timestamp: new Date(),
            selectedCompanies: companiesSelected.length > 0 ? [...companiesSelected] : undefined,
        };

        setMessages(prev => [...prev, userMsg]);
        setInputValue('');
        setSelectedCompanies([]);
        setIsLoading(true);
        setCurrentLogs([]);

        try {
            const response = await fetch(ai.getChatStreamUrl(), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMsg.content,
                    orgId: selectedOrgId,
                    selectedCompanies: companiesSelected,
                    context: 'hierarchy_analysis',
                    model,
                    thread_id: threadId,
                    history: messages.slice(-6).map(m => ({ role: m.role, content: m.content })),
                }),
            });

            if (response.ok) {
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
            }
        } catch (error) {
            console.error('Erro ao enviar mensagem:', error);
        } finally {
            setIsLoading(false);
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
                <div className={styles.messagesContainer}>
                    {messages.map(message => (
                        <ChatMessage
                            key={message.id}
                            message={message}
                            onApprove={handleApproveAction}
                            onReject={handleRejectAction}
                            onOpenWhatsApp={onOpenWhatsApp}
                            approvalStatuses={approvalStatuses}
                        />
                    ))}

                    {/* Thinking panel */}
                    {isLoading && (
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
                startListening={startListening}
                stopListening={stopListening}
                theme={theme}
                pipedriveCooldown={pipedriveCooldown}
            />
        </div>
    );
};
