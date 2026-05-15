import { useState, useCallback, useEffect } from 'react';
import { conversations } from '@/services/api';
import type { ThreadOut } from '@/services/api/conversations';

export const useChatThreads = (selectedOrgId: number | null) => {
    const [threads, setThreads] = useState<ThreadOut[]>([]);
    const [isLoadingThreads, setIsLoadingThreads] = useState(false);
    const [activeThread, setActiveThread] = useState<ThreadOut | null>(null);
    const [threadToDelete, setThreadToDelete] = useState<ThreadOut | null>(null);

    const loadThreads = useCallback(async () => {
        setIsLoadingThreads(true);
        try {
            const targetOrgId = selectedOrgId || 0;
            const threadList = await conversations.listThreads(targetOrgId);
            setThreads(threadList);
            return threadList;
        } catch (err) {
            console.error('[useChatThreads] Error loading threads:', err);
            return [];
        } finally {
            setIsLoadingThreads(false);
        }
    }, [selectedOrgId]);

    const createThread = useCallback(async () => {
        const targetOrgId = selectedOrgId || 0;
        try {
            const t = await conversations.createThread(targetOrgId);
            setActiveThread(t);
            setThreads(prev => [t, ...prev]);
            return t;
        } catch (err) {
            console.error('[useChatThreads] Error creating thread:', err);
            return null;
        }
    }, [selectedOrgId]);

    const deleteThread = useCallback(async (threadId: string) => {
        try {
            await conversations.deleteThread(threadId);
            setThreads(prev => prev.filter(t => t.id !== threadId));
            if (activeThread?.id === threadId) {
                setActiveThread(null);
            }
            return true;
        } catch (err: any) {
            if (err.status === 404) {
                setThreads(prev => prev.filter(t => t.id !== threadId));
                if (activeThread?.id === threadId) {
                    setActiveThread(null);
                }
                return true;
            }
            console.error('[useChatThreads] Error deleting thread:', err);
            return false;
        }
    }, [activeThread]);

    return {
        threads,
        setThreads,
        isLoadingThreads,
        activeThread,
        setActiveThread,
        threadToDelete,
        setThreadToDelete,
        loadThreads,
        createThread,
        deleteThread
    };
};
