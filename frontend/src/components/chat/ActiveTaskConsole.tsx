import React, { useRef, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { InlineEventStream, MappedContact } from './AgentV2Message'; // AgentV2Message.tsx mantém esse nome de arquivo; componente exportado agora como AgentMessage
import { AIModel } from './ModelSelector';

interface ActiveTaskConsoleProps {
    activeRunningTask: any;
    isExpanded: boolean;
    inlineConfirmed: Record<string, boolean>;
    onInlineConfirm: (action_id: string, approved: boolean) => Promise<void>;
    onMappingComplete?: (contacts: MappedContact[]) => Promise<void>;
    model: AIModel;
    theme: string;
}

export const ActiveTaskConsole: React.FC<ActiveTaskConsoleProps> = ({
    activeRunningTask,
    isExpanded,
    inlineConfirmed,
    onInlineConfirm,
    onMappingComplete,
    model,
    theme
}) => {
    const logsBottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (isExpanded) {
            logsBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [activeRunningTask?.logs, isExpanded]);

    if (!activeRunningTask || !isExpanded) return null;

    const isStreaming = activeRunningTask.status === 'streaming';

    return (
        <div
            style={{
                padding: '14px 16px',
                flex: 1,
                minHeight: 0,
                overflowY: 'auto',
                fontFamily: 'monospace',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
                background: '#1e1e1e',
                borderRadius: '12px',
                borderTop: 'var(--chat-border-width, 1.5px) solid rgba(255, 255, 255, 0.08)',
                borderLeft: 'var(--chat-border-width, 1.5px) solid rgba(255, 255, 255, 0.08)',
                borderRight: 'var(--chat-border-width, 1.5px) solid rgba(255, 255, 255, 0.08)',
                borderBottom: 'none',
            }}
        >
            {activeRunningTask.logs.length === 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: 'rgba(255, 255, 255, 0.35)' }}>
                    <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />
                    <span>Iniciando pipeline de tarefa em console dedicado...</span>
                </div>
            ) : (
                <InlineEventStream
                    events={activeRunningTask.logs}
                    isStreaming={isStreaming}
                    inlineConfirmed={inlineConfirmed}
                    onInlineConfirm={onInlineConfirm}
                    onHierarchyMappingDone={onMappingComplete}
                    model={model}
                />
            )}
            <div ref={logsBottomRef} />
        </div>
    );
};
