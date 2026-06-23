import { useState, useCallback, useEffect } from 'react';
import { conversations } from '@/services/api';
import type { ThreadOut } from '@/services/api/conversations';

interface UseChatThreadsProps {
    activeOrgId: number | null;
    selectedOrgId: number | null | undefined;
    prospectingContext: string | null | undefined;
    setView: (view: 'list' | 'chat') => void;
    onOpenThread: (thread: ThreadOut, isSameStreamingThread: boolean) => Promise<void>;
    onNewThread: () => void;
    onBackToList: () => void;
    streamingThreadIdRef: React.MutableRefObject<string | null>;
    setMessages: (messages: any[] | ((prev: any[]) => any[])) => void;
    setInputValue: (val: string) => void;
}

export const useChatThreads = ({
    activeOrgId,
    selectedOrgId,
    prospectingContext,
    setView,
    onOpenThread,
    onNewThread,
    onBackToList,
    streamingThreadIdRef,
    setMessages,
    setInputValue,
}: UseChatThreadsProps) => {
    const [threads, setThreads] = useState<ThreadOut[]>([]);
    const [isLoadingThreads, setIsLoadingThreads] = useState(false);
    const [isCreatingThread, setIsCreatingThread] = useState(false);
    const [threadsToDelete, setThreadsToDelete] = useState<ThreadOut[]>([]);
    const [activeThread, setActiveThread] = useState<ThreadOut | null>(null);

    const openThread = useCallback(async (thread: ThreadOut) => {
        const isSameStreamingThread = streamingThreadIdRef.current === thread.id;
        setActiveThread(thread);
        if (typeof window !== 'undefined') {
            const targetOrgId = activeOrgId || 0;
            window.localStorage.setItem(`active-thread-id-${targetOrgId}`, thread.id);
            window.localStorage.setItem('chat-panel-view', 'chat');
        }
        setView('chat');
        await onOpenThread(thread, isSameStreamingThread);
    }, [activeOrgId, onOpenThread, setView, streamingThreadIdRef]);

    const loadThreads = useCallback(async () => {
        setIsLoadingThreads(true);
        try {
            const targetOrgId = activeOrgId || 0;
            const threadList = await conversations.listThreads(targetOrgId);
            setThreads(threadList);

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
            console.error('[useChatThreads] Erro ao carregar dados:', err);
        } finally {
            setIsLoadingThreads(false);
        }
    }, [activeOrgId, openThread]);

    useEffect(() => {
        setActiveThread(null);
        
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
        
        void loadThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeOrgId]);

    const handleNewThread = () => {
        setActiveThread(null);
        if (typeof window !== 'undefined') {
            const targetOrgId = selectedOrgId || 0;
            window.localStorage.removeItem(`active-thread-id-${targetOrgId}`);
            window.localStorage.setItem('chat-panel-view', 'chat');
        }
        setMessages([]);
        const defaultInput = (activeOrgId && !prospectingContext) ? "Gerar plano de prospecção para esta empresa" : "";
        setInputValue(defaultInput);
        setView('chat');
        onNewThread();
    };

    const handleBackToList = async () => {
        setView('list');
        if (typeof window !== 'undefined') {
            window.localStorage.setItem('chat-panel-view', 'list');
        }
        setActiveThread(null);
        setMessages([]);
        const defaultInput = (activeOrgId && !prospectingContext) ? "Gerar plano de prospecção para esta empresa" : "";
        setInputValue(defaultInput);
        onBackToList();
        void loadThreads();
    };

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
            if (err.status === 404) {
                setThreads(prev => prev.filter(t => !targetIds.includes(t.id)));
                if (activeThread && targetIds.includes(activeThread.id)) {
                    handleBackToList();
                }
            } else {
                console.error('[useChatThreads] Erro ao deletar thread(s):', err);
            }
        } finally {
            setThreadsToDelete([]);
        }
    };

    const ensureThread = async (): Promise<string | null> => {
        if (activeThread) return activeThread.id;
        const targetOrgId = selectedOrgId || 0;
        try {
            const t = await conversations.createThread(targetOrgId);
            setActiveThread(t);
            setThreads(prev => [t, ...prev]);
            return t.id;
        } catch (err) {
            console.error('[useChatThreads] Erro ao criar thread:', err);
            return null;
        }
    };

    return {
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
    };
};
