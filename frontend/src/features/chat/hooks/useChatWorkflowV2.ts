import { useState, useRef, useCallback } from 'react';
import { ai } from '@/services/api';
import type { AIModel } from '../components/ModelSelector';
import type { ModelActivityEvent } from '../components/ModelActivityBar';
import type { Message } from '../components/ChatInterfaces';
import type { V2Event } from '../components/AgentV2Message';

export const useChatWorkflowV2 = (
    selectedOrgId: number | null,
    activeThreadId: string | null,
    model: AIModel,
    strictMode: boolean,
    setMessages: React.Dispatch<React.SetStateAction<Message[]>>
) => {
    const [isLoading, setIsLoading] = useState(false);
    const [v2Streaming, setV2Streaming] = useState(false);
    const [liveModel, setLiveModel] = useState<AIModel | null>(null);
    const [modelActivity, setModelActivity] = useState<ModelActivityEvent[]>([]);
    const [v2ConfirmedActions, setV2ConfirmedActions] = useState<Record<string, boolean>>({});
    const modelActivityIdRef = useRef(0);
    const abortControllerRef = useRef<AbortController | null>(null);

    const stopStreaming = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setIsLoading(false);
        setV2Streaming(false);
        setLiveModel(null);
        setModelActivity([]);
    }, []);

    const executeV2Workflow = async (text: string, threadId: string) => {
        setIsLoading(true);
        setV2Streaming(true);
        setLiveModel(null);
        setModelActivity([]);

        const targetMsgId = (Date.now() + 1).toString();
        setMessages(prev => [...prev, {
            id: targetMsgId,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            v2Events: [],
            isV2: true,
            v2Streaming: true,
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
                body: JSON.stringify({
                    message: text,
                    org_id: selectedOrgId,
                    thread_id: threadId,
                    model: model,
                    strict: strictMode
                }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                setMessages(prev => prev.map(m => m.id === targetMsgId ? { ...m, v2Streaming: false } : m));
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const collectedEvents: V2Event[] = [];

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
                            m.id === targetMsgId ? { ...m, v2Events: [...collectedEvents] } : m
                        ));
                    } catch { /* ignore */ }
                }
            }
        } catch (err: any) {
            if (err.name === 'AbortError') return;
            console.error('[useChatWorkflowV2] Error:', err);
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            setMessages(prev => prev.map(m => m.id === targetMsgId ? { ...m, v2Streaming: false } : m));
            setIsLoading(false);
            setV2Streaming(false);
            setLiveModel(null);
            setTimeout(() => setModelActivity([]), 3000);
        }
    };

    const handleV2Confirm = async (action_id: string, approved: boolean) => {
        setV2ConfirmedActions(prev => ({ ...prev, [action_id]: approved }));

        setMessages(prev => prev.map(m => {
            if (!m.isV2 || !m.v2Events) return m;
            const hasAction = m.v2Events.some((e: any) => e.action_id === action_id);
            if (!hasAction) return m;
            return { ...m, v2ConfirmedActions: { ...(m.v2ConfirmedActions || {}), [action_id]: approved } };
        }));

        if (!approved) return;

        const threadId = activeThreadId || '';
        setIsLoading(true);
        setV2Streaming(true);

        const msgId = (Date.now() + 2).toString();
        setMessages(prev => [...prev, {
            id: msgId,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            v2Events: [],
            isV2: true,
            v2Streaming: true,
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
                setMessages(prev => prev.map(m => m.id === msgId ? { ...m, v2Streaming: false } : m));
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const collectedEvents: V2Event[] = [];

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
                        setMessages(prev => prev.map(m =>
                            m.id === msgId ? { ...m, v2Events: [...collectedEvents] } : m
                        ));
                    } catch { /* ignore */ }
                }
            }
        } catch (err: any) {
            if (err.name === 'AbortError') return;
            console.error('[useChatWorkflowV2] Confirm Error:', err);
        } finally {
            if (abortControllerRef.current === controller) {
                abortControllerRef.current = null;
            }
            setMessages(prev => prev.map(m => m.id === msgId ? { ...m, v2Streaming: false } : m));
            setIsLoading(false);
            setV2Streaming(false);
        }
    };

    return {
        isLoading,
        v2Streaming,
        liveModel,
        modelActivity,
        v2ConfirmedActions,
        executeV2Workflow,
        handleV2Confirm,
        stopStreaming
    };
};
