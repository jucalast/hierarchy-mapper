import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Trash2, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import styles from '../styles/ChatPanel.module.css';

// Components
import { ChatInput } from './ChatInput';
import { ChatMessage } from './ChatMessage';
import { AgentV2Message } from './AgentV2Message';
import { ActivitySidebar } from './ActivitySidebar';
import { ThreadListView } from './ThreadListView';
import { ChatSubHeader } from './ChatSubHeader';
import { ActiveTaskConsole } from './ActiveTaskConsole';
import { Modal, Button } from '@/components/ui';

// Hooks
import { useChatThreads } from '../hooks/useChatThreads';
import { useChatMessages } from '../hooks/useChatMessages';
import { useChatWorkflowV2 } from '../hooks/useChatWorkflowV2';
import { useTaskRunner } from '../hooks/useTaskRunner';
import { useSpeechToText } from '@/hooks/useSpeechToText';

// Types & Services
import type { CompanyResult } from '../types';
import type { AIModel } from './ui/ModelSelector';
import { ai, conversations } from '@/services/api';

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
    selectedOrgId = null,
    selectedOrgName = 'Organização',
    theme = 'light',
    onToggleTheme,
    onOpenWhatsApp,
    selectedOrgLogo,
}) => {
    // ─── Core Hooks ──────────────────────────────────────────
    const { 
        isListening, isTranscribing, finalTranscript, startListening, 
        stopListening, clearTranscript, isSupported, analyserNode, error: voiceError 
    } = useSpeechToText();

    const {
        threads, setThreads, isLoadingThreads, activeThread, setActiveThread,
        threadToDelete, setThreadToDelete, loadThreads, createThread, deleteThread
    } = useChatThreads(selectedOrgId);

    const cleanOrgName = selectedOrgName?.trim() || '';
    const hasValidOrg = cleanOrgName !== '';

    const {
        messages, setMessages, messagesEndRef, scrollContainerRef,
        isAtBottom, handleScroll, loadMessages, scrollToBottom
    } = useChatMessages(activeThread?.id || null, cleanOrgName, hasValidOrg);

    const [model, setModel] = useState<AIModel>(() => (localStorage.getItem('ai_preferred_model') as AIModel) || 'claude');
    const [strictMode, setStrictMode] = useState<boolean>(() => localStorage.getItem('ai_strict_mode') === 'true');

    const {
        isLoading, v2Streaming, liveModel, modelActivity, v2ConfirmedActions,
        executeV2Workflow, handleV2Confirm, stopStreaming
    } = useChatWorkflowV2(selectedOrgId, activeThread?.id || null, model, strictMode, setMessages);

    const {
        activeRunningTask, setActiveRunningTask, approvedSuggestedActions,
        taskInlineConfirmed, handleApproveSuggestedAction, handleTaskInlineConfirm,
        handleTaskMappingComplete
    } = useTaskRunner(selectedOrgId, activeThread, setThreads);

    // ─── UI State ────────────────────────────────────────────
    const [view, setView] = useState<PanelView>('chat');
    const [showActivitySidebar, setShowActivitySidebar] = useState(false);
    const [activities, setActivities] = useState<any[]>([]);
    const [isLoadingActivities, setIsLoadingActivities] = useState(false);
    const [inputValue, setInputValue] = useState('');
    const [selectedCompanies, setSelectedCompanies] = useState<CompanyResult[]>([]);
    const [pipedriveCooldown, setPipedriveCooldown] = useState<number>(0);
    const [searchTerm, setSearchTerm] = useState('');
    const [companies, setCompanies] = useState<CompanyResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [showAutocomplete, setShowAutocomplete] = useState(false);

    // ─── Initialization ──────────────────────────────────────
    useEffect(() => {
        const targetOrgId = selectedOrgId || 0;
        const savedThreadId = localStorage.getItem(`active-thread-id-${targetOrgId}`);
        const savedView = localStorage.getItem('chat-panel-view') as PanelView;
        
        if (savedView === 'list' && !savedThreadId) {
            setView('list');
        } else {
            setView('chat');
        }
        
        loadThreads().then(threadList => {
            if (savedThreadId) {
                const matched = threadList.find(t => t.id === savedThreadId);
                if (matched) {
                    setActiveThread(matched);
                    loadMessages(matched.id);
                }
            }
        });
        
        if (selectedOrgId) {
            conversations.listActivities(selectedOrgId).then(setActivities).catch(() => {});
        }
    }, [selectedOrgId]);

    // ─── Persistent Model Sync ──────────────────────────────
    useEffect(() => {
        ai.updatePreference(model, strictMode).catch(() => {});
        localStorage.setItem('ai_preferred_model', model);
        localStorage.setItem('ai_strict_mode', String(strictMode));
    }, [model, strictMode]);

    // ─── Voice Integration ──────────────────────────────────
    useEffect(() => {
        if (finalTranscript) {
            setInputValue(prev => {
                const hasSpace = prev.length > 0 && prev[prev.length - 1] !== ' ';
                return prev + (hasSpace ? ' ' : '') + finalTranscript;
            });
            clearTranscript();
        }
    }, [finalTranscript, clearTranscript]);

    // ─── Handlers ───────────────────────────────────────────
    const handleOpenThread = (thread: any) => {
        setActiveThread(thread);
        const targetOrgId = selectedOrgId || 0;
        localStorage.setItem(`active-thread-id-${targetOrgId}`, thread.id);
        localStorage.setItem('chat-panel-view', 'chat');
        setView('chat');
        loadMessages(thread.id);
    };

    const handleNewThread = async () => {
        setActiveThread(null);
        const targetOrgId = selectedOrgId || 0;
        localStorage.removeItem(`active-thread-id-${targetOrgId}`);
        localStorage.setItem('chat-panel-view', 'chat');
        setView('chat');
        setMessages([{
            id: 'welcome',
            role: 'assistant',
            content: hasValidOrg ? `Como posso te ajudar com a @${cleanOrgName}?` : "Como posso te ajudar hoje?",
            timestamp: new Date(),
        }]);
    };

    const handleBackToList = () => {
        setView('list');
        const targetOrgId = selectedOrgId || 0;
        localStorage.removeItem(`active-thread-id-${targetOrgId}`);
        localStorage.setItem('chat-panel-view', 'list');
        setActiveThread(null);
        loadThreads();
    };

    const handleSendMessage = async (text: string, entities: CompanyResult[]) => {
        if (!text.trim() && entities.length === 0) return;
        
        let threadId = activeThread?.id;
        if (!threadId) {
            const newThread = await createThread();
            if (!newThread) return;
            threadId = newThread.id;
            const targetOrgId = selectedOrgId || 0;
            localStorage.setItem(`active-thread-id-${targetOrgId}`, threadId);
        }

        const userMsg: any = {
            id: Date.now().toString(),
            role: 'user',
            content: text,
            timestamp: new Date(),
            data: { selectedCompanies: entities }
        };

        setMessages(prev => [...prev, userMsg]);
        setInputValue('');
        setSelectedCompanies([]);
        
        await executeV2Workflow(text, threadId);
    };

    // ─── Autocomplete Search Logic ──────────────────────────
    const handleInputChange = (val: string) => {
        setInputValue(val);
        const lastAt = val.lastIndexOf('@');
        if (lastAt !== -1) {
            const query = val.substring(lastAt + 1).trim();
            setSearchTerm(query);
            if (query.length >= 2) {
                setShowAutocomplete(true);
                setIsSearching(true);
                ai.searchEntities(query).then(res => {
                    setCompanies(res);
                    setIsSearching(false);
                }).catch(() => setIsSearching(false));
            } else {
                setShowAutocomplete(false);
            }
        } else {
            setShowAutocomplete(false);
        }
    };

    const selectSearchResult = (item: CompanyResult) => {
        if (!selectedCompanies.find(c => c.id === item.id)) {
            setSelectedCompanies([...selectedCompanies, item]);
        }
        const lastAt = inputValue.lastIndexOf('@');
        if (lastAt !== -1) setInputValue(inputValue.substring(0, lastAt) + '@' + item.name + ' ');
        setShowAutocomplete(false);
    };

    // ─── Render Helpers ─────────────────────────────────────
    if (!showChat) return null;

    return (
        <aside className={`${styles.chatPanel} ${theme === 'dark' ? styles.dark : styles.light}`}>
            {view === 'list' ? (
                <ThreadListView
                    threads={threads}
                    isLoadingThreads={isLoadingThreads}
                    onNewThread={handleNewThread}
                    onOpenThread={handleOpenThread}
                    onDeleteThread={setThreadToDelete}
                    selectedOrgName={selectedOrgName}
                    selectedOrgLogo={selectedOrgLogo}
                    isCreatingThread={false}
                />
            ) : (
                <div className="flex flex-col h-full overflow-hidden" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
                    <ChatSubHeader
                        onBack={handleBackToList}
                        selectedOrgName={selectedOrgName}
                        selectedOrgLogo={selectedOrgLogo}
                        activeThreadTitle={activeThread?.title || undefined}
                        showActivitySidebar={showActivitySidebar}
                        setShowActivitySidebar={setShowActivitySidebar}
                        activityCount={activities.length}
                    />
                    
                    <div className={styles.messagesContainer} ref={scrollContainerRef} onScroll={handleScroll}>
                        {messages.map((msg) => (
                            msg.isV2 ? (
                                <AgentV2Message
                                    key={msg.id}
                                    messageId={msg.id}
                                    events={msg.v2Events || []}
                                    isStreaming={msg.v2Streaming}
                                    onConfirm={handleV2Confirm}
                                    confirmedActions={v2ConfirmedActions}
                                    onApproveSuggestedAction={handleApproveSuggestedAction}
                                    approvedSuggestedActions={approvedSuggestedActions}
                                    model={model}
                                />
                            ) : (
                                <ChatMessage 
                                    key={msg.id} 
                                    message={msg} 
                                    theme={theme} 
                                />
                            )
                        ))}
                        <div ref={messagesEndRef} />
                    </div>

                    <div className="relative mt-auto" style={{ position: 'relative', marginTop: 'auto', padding: '0 20px 20px' }}>
                        {activeRunningTask && (
                            <ActiveTaskConsole
                                task={activeRunningTask}
                                onToggleExpand={() => setActiveRunningTask({ ...activeRunningTask, isExpanded: !activeRunningTask.isExpanded })}
                                inlineConfirmed={taskInlineConfirmed}
                                onInlineConfirm={handleTaskInlineConfirm}
                                onMappingComplete={handleTaskMappingComplete}
                                model={model}
                                theme={theme}
                            />
                        )}
                        
                        {!activeRunningTask?.isExpanded && (
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
                                showAutocomplete={showAutocomplete}
                                isSearching={isSearching}
                                searchingCategory={null}
                                searchTerm={searchTerm}
                                companies={companies}
                                selectSearchResult={selectSearchResult}
                                isListening={isListening}
                                isTranscribing={isTranscribing}
                                startListening={startListening}
                                stopListening={stopListening}
                                voiceError={voiceError}
                                voiceSupported={isSupported}
                                analyserNode={analyserNode}
                                theme={theme}
                                pipedriveCooldown={pipedriveCooldown}
                                onStop={stopStreaming}
                            />
                        )}
                    </div>
                </div>
            )}

            {showActivitySidebar && (
                <ActivitySidebar
                    activities={activities}
                    isLoading={isLoadingActivities}
                    onRefresh={() => conversations.listActivities(selectedOrgId || 0).then(setActivities)}
                    onClose={() => setShowActivitySidebar(false)}
                />
            )}

            {/* Modals */}
            <Modal
                isOpen={!!threadToDelete}
                onClose={() => setThreadToDelete(null)}
                title="Excluir Conversa?"
            >
                <div className="p-4">
                    <p className="text-sm text-gray-400 mb-6">
                        Isso removerá todo o histórico desta conversa. Esta ação não pode ser desfeita.
                    </p>
                    <div className="flex justify-end gap-3">
                        <Button variant="ghost" onClick={() => setThreadToDelete(null)}>Cancelar</Button>
                        <Button variant="danger" onClick={() => threadToDelete && deleteThread(threadToDelete.id)}>Excluir</Button>
                    </div>
                </div>
            </Modal>
        </aside>
    );
};
