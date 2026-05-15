import React, { useRef, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { InlineEventStream, MappedContact, TaskStatus, V2Event } from './AgentV2Message';
import type { AIModel } from './ModelSelector';
import styles from './ChatInput.module.css'; // Will split this later

interface ActiveTaskConsoleProps {
    task: {
        label: string;
        status: TaskStatus;
        logs: V2Event[];
        isExpanded: boolean;
    };
    onToggleExpand: () => void;
    inlineConfirmed: Record<string, boolean>;
    onInlineConfirm: (action_id: string, approved: boolean) => void;
    onMappingComplete: (contacts: MappedContact[]) => void;
    model: AIModel;
    theme: string;
}

export const ActiveTaskConsole: React.FC<ActiveTaskConsoleProps> = ({
    task,
    onToggleExpand,
    inlineConfirmed,
    onInlineConfirm,
    onMappingComplete,
    model,
    theme
}) => {
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (task.isExpanded) {
            bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [task.logs, task.isExpanded]);

    const isStreaming = task.status === 'streaming';
    const isAwaiting = task.status === 'awaiting_mapping' || task.status === 'awaiting_confirm';
    const isDone = task.status === 'done';
    const isErr = task.status === 'error';

    const statusColor = isStreaming ? '#7a8bff' : isAwaiting ? '#f59e0b' : isDone ? '#22c55e' : '#ef4444';
    const statusLabel = isStreaming ? 'Executando tarefa' : isAwaiting ? 'Ação requerida' : isDone ? 'Tarefa concluída' : 'Falha na tarefa';
    const consoleBg = theme === 'dark' ? '#1e1e1e' : 'var(--chat-bg-primary)';

    return (
        <div style={{
            border: 'var(--chat-border-width) solid var(--chat-border-weak)',
            background: consoleBg,
            borderRadius: 16,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            flex: task.isExpanded ? 1 : 'none',
            height: task.isExpanded ? '100%' : 'auto',
            marginBottom: 8
        }}>
            {/* Minimized Bar / Header */}
            <div
                onClick={onToggleExpand}
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '8px 16px',
                    fontSize: 11,
                    fontWeight: 500,
                    color: 'rgba(255, 255, 255, 0.75)',
                    letterSpacing: '0.01em',
                    cursor: 'pointer',
                    userSelect: 'none',
                    background: '#1e1e1e',
                }}
            >
                <span style={{ color: statusColor, fontWeight: 600 }}>{statusLabel}</span>
                <span style={{ opacity: 0.25, color: '#fff' }}>·</span>
                <span style={{
                    flex: 1,
                    minWidth: 0,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis'
                }}>
                    {task.label}
                </span>

                <span style={{
                    fontSize: 9,
                    color: 'rgba(255, 255, 255, 0.35)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    fontWeight: 600,
                    marginRight: 4
                }}>
                    Console
                </span>

                <span style={{
                    width: 5,
                    height: 5,
                    borderRadius: '50%',
                    background: statusColor,
                    flexShrink: 0,
                    animation: (isStreaming || isAwaiting) ? 'modelLivePulse 1.4s ease-in-out infinite' : 'none',
                }} />
            </div>

            {/* Expanded Console */}
            {task.isExpanded && (
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
                        borderRadius: '0 0 12px 12px',
                        borderTop: 'var(--chat-border-width, 1.5px) solid rgba(255, 255, 255, 0.08)',
                    }}
                >
                    {task.logs.length === 0 ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: 'rgba(255, 255, 255, 0.35)' }}>
                            <Loader2 size={12} className={styles.spinner} />
                            <span>Iniciando pipeline de tarefa em console dedicado...</span>
                        </div>
                    ) : (
                        <InlineEventStream
                            events={task.logs}
                            isStreaming={isStreaming}
                            inlineConfirmed={inlineConfirmed}
                            onInlineConfirm={onInlineConfirm}
                            onHierarchyMappingDone={onMappingComplete}
                            model={model}
                        />
                    )}
                    <div ref={bottomRef} />
                </div>
            )}
        </div>
    );
};
