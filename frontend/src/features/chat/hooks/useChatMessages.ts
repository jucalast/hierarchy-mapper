import { useState, useCallback, useRef, useEffect } from 'react';
import { conversations } from '@/services/api';
import type { Message } from '../components/ChatInterfaces';
import type { MessageOut } from '@/services/api/conversations';

export const useChatMessages = (activeThreadId: string | null, cleanOrgName: string, hasValidOrg: boolean) => {
    const [messages, setMessages] = useState<Message[]>([]);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [isAtBottom, setIsAtBottom] = useState(true);

    const loadMessages = useCallback(async (threadId: string) => {
        try {
            const msgs = await conversations.getMessages(threadId);
            if (msgs.length === 0) {
                setMessages([{
                    id: 'welcome',
                    role: 'assistant',
                    content: hasValidOrg ? `Como posso te ajudar com a @${cleanOrgName}?` : "Como posso te ajudar hoje?",
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
            console.error('[useChatMessages] Error loading messages:', err);
            setMessages([{
                id: 'welcome',
                role: 'assistant',
                content: hasValidOrg ? `Como posso te ajudar com a @${cleanOrgName}?` : "Como posso te ajudar hoje?",
                timestamp: new Date(),
            }]);
        }
    }, [cleanOrgName, hasValidOrg]);

    const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
        messagesEndRef.current?.scrollIntoView({ behavior });
    }, []);

    const handleScroll = useCallback(() => {
        const el = scrollContainerRef.current;
        if (!el) return;
        const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        setIsAtBottom(distanceFromBottom < 80);
    }, []);

    useEffect(() => {
        if (isAtBottom) {
            scrollToBottom();
        }
    }, [messages, isAtBottom, scrollToBottom]);

    return {
        messages,
        setMessages,
        messagesEndRef,
        scrollContainerRef,
        isAtBottom,
        setIsAtBottom,
        loadMessages,
        scrollToBottom,
        handleScroll
    };
};
