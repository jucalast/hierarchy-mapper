import React, { useState } from 'react';
import {
    Loader2, CheckCircle2, XCircle, Check, X, AlertTriangle,
    Copy, RotateCcw, Clock, AlertCircle, ChevronDown,
} from 'lucide-react';
import styles from '../ChatPanel.module.css';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface V2Event {
    type: 'thinking' | 'tool_call' | 'tool_result' | 'confirmation_required' | 'final' | 'error' | 'context_saved' | 'rate_wait' | 'context_overflow' | 'suggested_actions';
    content?: string;
    call_id?: string;
    tool_use_id?: string;
    tool_name?: string;
    tool?: string;
    args?: Record<string, any>;
    label?: string;
    summary?: string;
    ok?: boolean;
    action_id?: string;
    preview?: string;
    actions?: Array<{ label: string; prompt: string }>;
    response?: string;
    model?: string;
    wait_sec?: number;
    reason?: string;
    estimated_tokens?: number;
    limit?: number;
}

export interface AgentV2MessageProps {
    messageId?: string;
    events: V2Event[];
    isStreaming?: boolean;
    onConfirm?: (action_id: string, approved: boolean) => void;
    confirmedActions?: Record<string, boolean>;
    onRegenerate?: () => void;
    onAction?: (prompt: string) => void;
    // Para streaming inline das tarefas sugeridas
    streamV2Url?: string;
    confirmV2Url?: string;
    orgId?: number | null;
    threadId?: string;
}

// ─── Cores por ferramenta ─────────────────────────────────────────────────────

const TOOL_COLORS: Record<string, string> = {
    whatsapp_get_messages: '#25d366',
    whatsapp_list_chats: '#25d366',
    whatsapp_send_message: '#25d366',
    pipedrive_get_org: '#f36e21',
    pipedrive_get_persons: '#f36e21',
    pipedrive_get_deals: '#f36e21',
    pipedrive_get_activities: '#f36e21',
    pipedrive_get_all_activities: '#f36e21',
    pipedrive_update_deal: '#f36e21',
    pipedrive_create_task: '#f36e21',
    pipedrive_update_task: '#f36e21',
    pipedrive_create_note: '#f36e21',
    email_get_inbox: '#7a8bff',
    email_get_contact_history: '#7a8bff',
    email_send: '#7a8bff',
    email_reply: '#7a8bff',
    web_search: '#60a5fa',
    generate_dossier: '#a78bfa',
};

// ─── Markdown simples ─────────────────────────────────────────────────────────

const renderInline = (text: string): React.ReactNode[] =>
    text.split(/(\*\*.*?\*\*)/g).map((part, i) =>
        part.startsWith('**') && part.endsWith('**')
            ? <strong key={i}>{part.slice(2, -2)}</strong>
            : part as any
    );

const renderMarkdown = (text: string): React.ReactNode => {
    if (!text) return null;
    return text.split('\n').map((line, idx) => {
        if (line.trim() === '---')
            return <hr key={idx} style={{ margin: '10px 0', border: 'none', borderTop: '1px solid rgba(255,255,255,0.1)' }} />;
        if (line.startsWith('### '))
            return <h3 key={idx} style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 8px' }}>{renderInline(line.slice(4))}</h3>;
        if (line.startsWith('## '))
            return <h3 key={idx} style={{ fontSize: '16px', fontWeight: 700, margin: '4px 0 8px' }}>{renderInline(line.slice(3))}</h3>;
        return <div key={idx} style={{ marginBottom: '10px', lineHeight: '1.65' }}>{renderInline(line)}</div>;
    });
};

// ─── ConfirmationCard ─────────────────────────────────────────────────────────

const ConfirmationCard: React.FC<{
    event: V2Event;
    onConfirm: (action_id: string, approved: boolean) => void;
    decided?: boolean;
    approvedResult?: boolean;
}> = ({ event, onConfirm, decided, approvedResult }) => {
    const tool = event.tool || '';
    const color = TOOL_COLORS[tool] || '#7a8bff';

    if (decided) {
        return (
            <div className={styles.logLine} style={{ marginBottom: 8 }}>
                {approvedResult
                    ? <CheckCircle2 size={12} style={{ color: '#22c55e', flexShrink: 0 }} />
                    : <XCircle size={12} style={{ color: 'rgba(255,255,255,0.3)', flexShrink: 0 }} />
                }
                <span>{approvedResult ? 'Ação aprovada' : 'Ação cancelada'}</span>
                <span style={{ opacity: 0.4 }}>· {event.label}</span>
            </div>
        );
    }

    return (
        <div style={{ borderRadius: 10, border: `1px solid ${color}33`, background: `${color}0d`, overflow: 'hidden', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: `1px solid ${color}22`, background: `${color}0a` }}>
                <AlertTriangle size={13} color={color} />
                <span style={{ fontSize: 11, fontWeight: 700, color, letterSpacing: '0.03em' }}>CONFIRMAR AÇÃO</span>
            </div>
            <div style={{ padding: '10px 12px' }}>
                <div style={{ fontSize: 13, color: 'var(--sw-text-base)', marginBottom: 6 }}>{event.label}</div>
                {event.preview && (
                    <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', background: 'rgba(0,0,0,0.2)', padding: '6px 8px', borderRadius: 6, fontStyle: 'italic', marginBottom: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                        {event.preview}
                    </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => onConfirm(event.action_id!, true)} style={{ flex: 1, padding: '7px 12px', borderRadius: 7, border: 'none', background: '#22c55e', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                        <Check size={13} /> Confirmar
                    </button>
                    <button onClick={() => onConfirm(event.action_id!, false)} style={{ flex: 1, padding: '7px 12px', borderRadius: 7, border: '1px solid rgba(255,255,255,0.12)', background: 'transparent', color: 'rgba(255,255,255,0.55)', fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                        <X size={13} /> Cancelar
                    </button>
                </div>
            </div>
        </div>
    );
};

// ─── RateWaitBadge ────────────────────────────────────────────────────────────

const RateWaitBadge: React.FC<{ event: V2Event; isStreaming: boolean }> = ({ event, isStreaming }) => {
    const [remaining, setRemaining] = useState(event.wait_sec || 0);
    React.useEffect(() => {
        if (!isStreaming || remaining <= 0) return;
        const t = setInterval(() => setRemaining(r => Math.max(0, r - 1)), 1000);
        return () => clearInterval(t);
    }, [isStreaming]);
    const label = event.reason === 'TPM' ? 'tokens/min' : 'req/min';
    const done = remaining <= 0;
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: done ? 'rgba(255,255,255,0.3)' : '#f59e0b', margin: '3px 0' }}>
            {done ? <CheckCircle2 size={11} style={{ color: '#10b981', flexShrink: 0 }} /> : <Clock size={11} style={{ flexShrink: 0 }} />}
            <span>{done ? `Cota ${label} liberada — retomando` : `Aguardando cota ${label} (${remaining}s) · ${event.model}`}</span>
        </div>
    );
};

const ContextOverflowBadge: React.FC<{ event: V2Event }> = ({ event }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'rgba(255,255,255,0.4)', margin: '3px 0' }}>
        <AlertCircle size={11} style={{ flexShrink: 0, color: '#f59e0b' }} />
        <span>{event.model} não suporta {event.estimated_tokens?.toLocaleString()} tokens (limite {event.limit?.toLocaleString()}) · usando modelo maior</span>
    </div>
);

// ─── Renderizador inline de eventos (reutilizado no accordion) ────────────────

const InlineEventStream: React.FC<{
    events: V2Event[];
    isStreaming: boolean;
    inlineConfirmed: Record<string, boolean>;
    onInlineConfirm: (action_id: string, approved: boolean) => void;
}> = ({ events, isStreaming, inlineConfirmed, onInlineConfirm }) => {
    const resultMap: Record<string, V2Event> = {};
    for (const ev of events) {
        if (ev.type === 'tool_result' && ev.call_id) resultMap[ev.call_id] = ev;
    }
    const seenIds = new Set<string>();

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {events.map((ev, i) => {
                if (ev.type === 'thinking') {
                    return (
                        <div key={i} className={styles.aiMessage} style={{ fontSize: 13, marginBottom: 4 }}>
                            {renderMarkdown(ev.content || '')}
                        </div>
                    );
                }
                if (ev.type === 'tool_call' && ev.call_id && !seenIds.has(ev.call_id)) {
                    seenIds.add(ev.call_id);
                    const result = resultMap[ev.call_id];
                    const running = !result && isStreaming;
                    const ok = result?.ok;
                    const color = TOOL_COLORS[ev.tool || ''] || '#888';
                    return (
                        <div key={i} className={styles.logLine}>
                            {running
                                ? <Loader2 size={12} className={styles.spinner} style={{ color, flexShrink: 0 }} />
                                : ok
                                    ? <CheckCircle2 size={12} style={{ color: '#10b981', flexShrink: 0 }} />
                                    : <XCircle size={12} style={{ color: '#ef4444', flexShrink: 0 }} />
                            }
                            <span>
                                {ev.label}
                                {result?.summary && <span style={{ opacity: 0.5, marginLeft: 5 }}>· {result.summary}</span>}
                            </span>
                        </div>
                    );
                }
                if (ev.type === 'tool_result') return null;
                if (ev.type === 'context_saved') {
                    return (
                        <div key={i} className={styles.logLine} style={{ opacity: 0.3, fontSize: 10, letterSpacing: '0.04em' }}>
                            <span>· contexto salvo</span>
                        </div>
                    );
                }
                if (ev.type === 'rate_wait') return null;
                if (ev.type === 'context_overflow') return null;
                if (ev.type === 'final') {
                    return (
                        <div key={i} className={styles.aiMessage} style={{ fontSize: 13, marginTop: 6 }}>
                            {renderMarkdown(ev.response || '')}
                        </div>
                    );
                }
                if (ev.type === 'error') {
                    return (
                        <div key={i} style={{ fontSize: 13, color: '#ef4444', marginTop: 4 }}>
                            {ev.content}
                        </div>
                    );
                }
                if (ev.type === 'confirmation_required' && ev.action_id) {
                    return (
                        <ConfirmationCard
                            key={i}
                            event={ev}
                            onConfirm={onInlineConfirm}
                            decided={ev.action_id in inlineConfirmed}
                            approvedResult={inlineConfirmed[ev.action_id]}
                        />
                    );
                }
                return null;
            })}
            {isStreaming && (
                <div className={styles.logLine} style={{ marginTop: 4, opacity: 0.6 }}>
                    <Loader2 size={11} className={styles.spinner} />
                    <span style={{ fontSize: 11 }}>Executando...</span>
                </div>
            )}
        </div>
    );
};

// ─── SuggestedActionTask — card de tarefa com streaming inline ────────────────

type TaskStatus = 'pending' | 'streaming' | 'awaiting_confirm' | 'done' | 'rejected' | 'error';

const SuggestedActionTask: React.FC<{
    action: { label: string; prompt: string; status?: TaskStatus; logs?: V2Event[] };
    streamV2Url: string;
    confirmV2Url: string;
    orgId?: number | null;
    threadId?: string;
    parentMessageId?: string;
    actionIndex?: number;
}> = ({ action, streamV2Url, confirmV2Url, orgId, threadId, parentMessageId, actionIndex }) => {
    const [status, setStatus] = useState<TaskStatus>(action.status || 'pending');
    const [taskEvents, setTaskEvents] = useState<V2Event[]>(action.logs || []);
    const [isExpanded, setIsExpanded] = useState(!!action.logs && action.logs.length > 0);
    const [inlineConfirmed, setInlineConfirmed] = useState<Record<string, boolean>>(() => {
        const confirmed: Record<string, boolean> = {};
        if (action.logs) {
            action.logs.forEach(ev => {
                if (ev.type === 'tool_result' && ev.tool_use_id) {
                    confirmed[ev.tool_use_id] = true;
                }
            });
        }
        return confirmed;
    });

    const streamInto = async (url: string, body: object): Promise<V2Event[]> => {
        const collected: V2Event[] = [];
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
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
                        const ev: V2Event = JSON.parse(line);
                        collected.push(ev);
                        setTaskEvents(prev => [...prev, ev]);
                    } catch { /* ignore */ }
                }
            }
        } catch { /* network error */ }
        return collected;
    };

    const handleApprove = async () => {
        setStatus('streaming');
        setIsExpanded(true);

        const collected = await streamInto(streamV2Url, {
            message: action.prompt,
            org_id: orgId,
            thread_id: threadId,
            history: [],
            direct_action: true,
            parent_message_id: parentMessageId,
            action_index: actionIndex,
        });

        const pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
        if (pendingConfirm) {
            setStatus('awaiting_confirm');
        } else {
            setStatus('done');
        }
    };

    const handleInlineConfirm = async (action_id: string, approved: boolean) => {
        setInlineConfirmed(prev => ({ ...prev, [action_id]: approved }));
        if (!approved) {
            setStatus('done');
            return;
        }
        setStatus('streaming');
        await streamInto(confirmV2Url, {
            action_id,
            approved: true,
            thread_id: threadId,
        });
        setStatus('done');
    };

    const canExpand = status !== 'pending' && status !== 'rejected';
    const isActive = status === 'streaming';

    const statusIcon = {
        pending:          <span style={{ width: 12, height: 12, borderRadius: '50%', border: '1.5px solid rgba(255,255,255,0.2)', display: 'inline-block', flexShrink: 0 }} />,
        streaming:        <Loader2 size={12} className={styles.spinner} style={{ flexShrink: 0 }} />,
        awaiting_confirm: <AlertTriangle size={12} style={{ color: '#f59e0b', flexShrink: 0 }} />,
        done:             <CheckCircle2 size={12} style={{ color: '#10b981', flexShrink: 0 }} />,
        rejected:         <XCircle size={12} style={{ color: 'rgba(255,255,255,0.2)', flexShrink: 0 }} />,
        error:            <XCircle size={12} style={{ color: '#ef4444', flexShrink: 0 }} />,
    }[status];

    const labelColor = status === 'rejected'
        ? 'rgba(255,255,255,0.25)'
        : status === 'done'
            ? 'rgba(255,255,255,0.7)'
            : 'var(--chat-text-secondary)';

    return (
        <div style={{
            overflow: 'hidden',
            marginBottom: 6,
        }}>
            {/* Header — mesmo estilo de logLine */}
            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '9px 12px',
                    fontSize: 13,
                    color: labelColor,
                    cursor: canExpand ? 'pointer' : 'default',
                    userSelect: 'none',
                }}
                onClick={() => canExpand && setIsExpanded(e => !e)}
            >
                {statusIcon}
                <span style={{ flex: 1 }}>{action.label}</span>
                {canExpand && (
                    <ChevronDown
                        size={12}
                        style={{
                            opacity: 0.35,
                            transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                            transition: 'transform 0.18s ease',
                            flexShrink: 0,
                        }}
                    />
                )}
            </div>

            {/* Botões Aprovar / Reprovar — só quando pendente */}
            {status === 'pending' && (
                <div style={{ display: 'flex', gap: 6, padding: '0 12px 10px' }}>
                    <button
                        onClick={handleApprove}
                        style={{
                            flex: 1, padding: '6px 10px', borderRadius: 6, border: 'none',
                            background: '#22c55e', color: '#fff', fontSize: 11, fontWeight: 600,
                            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
                        }}
                    >
                        <Check size={11} /> Aprovar
                    </button>
                    <button
                        onClick={() => setStatus('rejected')}
                        style={{
                            flex: 1, padding: '6px 10px', borderRadius: 6,
                            border: '1px solid rgba(255,255,255,0.08)', background: 'transparent',
                            color: 'rgba(255,255,255,0.35)', fontSize: 11,
                            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
                        }}
                    >
                        <X size={11} /> Reprovar
                    </button>
                </div>
            )}

            {/* Accordion de eventos inline */}
            {isExpanded && taskEvents.length > 0 && (
                <div style={{
                    borderTop: '1px solid rgba(255,255,255,0.05)',
                    padding: '10px 12px',
                }}>
                    <InlineEventStream
                        events={taskEvents}
                        isStreaming={isActive}
                        inlineConfirmed={inlineConfirmed}
                        onInlineConfirm={handleInlineConfirm}
                    />
                </div>
            )}

            {/* Spinner enquanto streaming mas accordion fechado */}
            {isActive && !isExpanded && (
                <div style={{ padding: '0 12px 8px', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'rgba(255,255,255,0.3)' }}>
                    <Loader2 size={10} className={styles.spinner} />
                    <span>Executando…</span>
                </div>
            )}
        </div>
    );
};

// ─── AgentV2Message — componente principal ────────────────────────────────────

export const AgentV2Message: React.FC<AgentV2MessageProps> = ({
    messageId,
    events,
    isStreaming = false,
    onConfirm,
    confirmedActions = {},
    onRegenerate,
    onAction,
    streamV2Url,
    confirmV2Url,
    orgId,
    threadId,
}) => {
    const [copied, setCopied] = useState(false);

    const resultMap: Record<string, V2Event> = {};
    for (const ev of events) {
        if (ev.type === 'tool_result' && ev.call_id) resultMap[ev.call_id] = ev;
    }

    const finalEvent = events.find(e => e.type === 'final');
    const errorEvent = events.find(e => e.type === 'error');
    const confirmations = events.filter(e => e.type === 'confirmation_required' && e.action_id);
    const suggestedActions = events
        .filter(e => e.type === 'suggested_actions' && e.actions?.length)
        .flatMap(e => e.actions || []);

    const handleCopy = () => {
        navigator.clipboard.writeText(finalEvent?.response || '');
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
    };

    const seenCallIds = new Set<string>();
    const orderedItems: React.ReactNode[] = [];

    for (let i = 0; i < events.length; i++) {
        const ev = events[i];

        if (ev.type === 'thinking') {
            orderedItems.push(
                <div key={`think-${i}`} className={styles.aiMessageWrapper} style={{ marginBottom: 4 }}>
                    <div className={styles.aiMessage}>{renderMarkdown(ev.content || '')}</div>
                </div>
            );
        } else if (ev.type === 'tool_call' && ev.call_id && !seenCallIds.has(ev.call_id)) {
            seenCallIds.add(ev.call_id);
            if (ev.tool === 'suggest_next_actions') continue;
            const result = resultMap[ev.call_id];
            const isRunning = !result && isStreaming;
            const ok = result?.ok;
            const color = TOOL_COLORS[ev.tool || ''] || '#888';
            orderedItems.push(
                <div key={`tool-${ev.call_id}`} className={styles.logLine}>
                    {isRunning
                        ? <Loader2 size={12} className={styles.spinner} style={{ color, flexShrink: 0 }} />
                        : ok
                            ? <CheckCircle2 size={12} style={{ color: '#10b981', flexShrink: 0 }} />
                            : <XCircle size={12} style={{ color: '#ef4444', flexShrink: 0 }} />
                    }
                    <span>
                        {ev.label}
                        {result?.summary && <span style={{ opacity: 0.5, marginLeft: 5 }}>· {result.summary}</span>}
                    </span>
                </div>
            );
        } else if (ev.type === 'tool_result') {
            continue;
        } else if (ev.type === 'context_saved') {
            orderedItems.push(
                <div key={`ctx-${i}`} className={styles.logLine} style={{ opacity: 0.3, fontSize: 10, margin: '2px 0 8px', letterSpacing: '0.04em' }}>
                    <span>· contexto salvo</span>
                </div>
            );
        } else if (ev.type === 'rate_wait') {
            continue;
        } else if (ev.type === 'context_overflow') {
            continue;
        }
    }

    const hasActivity = orderedItems.length > 0;
    const hasTaskCards = suggestedActions.length > 0 && streamV2Url && confirmV2Url;

    return (
        <div className={styles.assistantMessageGroup}>
            {/* Eventos em ordem */}
            {hasActivity && (
                <div style={{ marginBottom: 8 }}>
                    {orderedItems}
                    {isStreaming && !finalEvent && !errorEvent && (
                        <div className={styles.logLine} style={{ marginTop: 4 }}>
                            <Loader2 size={12} className={styles.spinner} />
                            <span>Agente trabalhando...</span>
                        </div>
                    )}
                </div>
            )}

            {/* Loading inicial */}
            {isStreaming && !hasActivity && !finalEvent && !errorEvent && (
                <div style={{ marginBottom: 8 }}>
                    <div className={styles.logLine}>
                        <Loader2 size={12} className={styles.spinner} />
                        <span>Iniciando agente...</span>
                    </div>
                </div>
            )}

            {/* Confirmações de ação (write tools do fluxo principal) */}
            {confirmations.map(ev => (
                <ConfirmationCard
                    key={ev.action_id}
                    event={ev}
                    onConfirm={onConfirm || (() => {})}
                    decided={ev.action_id! in confirmedActions}
                    approvedResult={confirmedActions[ev.action_id!]}
                />
            ))}

            {/* Erro */}
            {errorEvent && (
                <div className={styles.aiMessageWrapper}>
                    <div className={styles.aiMessage} style={{ color: '#ef4444' }}>{errorEvent.content}</div>
                </div>
            )}

            {/* Dossiê final */}
            {finalEvent && (
                <div className={styles.aiMessageWrapper}>
                    <div className={styles.aiMessage}>{renderMarkdown(finalEvent.response || '')}</div>
                </div>
            )}

            {/* Tarefas sugeridas — cards empilhados abaixo do dossiê */}
            {hasTaskCards && (
                <div style={{ marginTop: 14 }}>
                    {suggestedActions.map((action, idx) => (
                        <SuggestedActionTask
                            key={idx}
                            action={action}
                            streamV2Url={streamV2Url!}
                            confirmV2Url={confirmV2Url!}
                            orgId={orgId}
                            threadId={threadId}
                            parentMessageId={messageId}
                            actionIndex={idx}
                        />
                    ))}
                </div>
            )}

            {/* Botões da mensagem */}
            {(!isStreaming || finalEvent || errorEvent) && (
                <div className={styles.messageActions}>
                    <div className={styles.actionGroup}>
                        <button className={styles.actionBtn} title="Copiar resposta" onClick={handleCopy}>
                            {copied ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                        {onRegenerate && (
                            <button className={styles.actionBtn} title="Regerar resposta" onClick={onRegenerate}>
                                <RotateCcw size={14} />
                            </button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};
