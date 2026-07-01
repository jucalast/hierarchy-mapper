import React from 'react';
import { Loader2, CheckCircle2, XCircle, X } from 'lucide-react';
import styles from '../styles/ChatPanel.module.css';
import { AIModel } from '../components/ModelSelector';
import { AgentEvent, MappedContact } from './types';
import { TOOL_COLORS, CONTEXT_TOOLS } from './constants';
import { renderMarkdown } from './markdown';
import { ConfirmationCard } from './cards/ConfirmationCard';
import { HierarchyMappingCard } from './cards/HierarchyMappingCard';

// ─── Renderizador inline de eventos (reutilizado no accordion) ────────────────

export const InlineEventStream: React.FC<{
    events: AgentEvent[];
    isStreaming: boolean;
    inlineConfirmed: Record<string, boolean>;
    onInlineConfirm: (action_id: string, approved: boolean) => void;
    onHierarchyMappingDone?: (contacts: MappedContact[]) => void;
    onAction?: (prompt: string) => void;
    model: AIModel;
}> = ({ events, isStreaming, inlineConfirmed, onInlineConfirm, onHierarchyMappingDone, onAction, model }) => {
    const resultMap: Record<string, AgentEvent> = {};
    for (const ev of events) {
        if (ev.type === 'tool_result' && ev.call_id) resultMap[ev.call_id] = ev;
    }
    const seenIds = new Set<string>();

    // Detecta se está na fase de leitura de contexto
    const calledContextTools = new Set(
        events
            .filter(e => e.type === 'tool_call' && e.tool && CONTEXT_TOOLS.has(e.tool))
            .map(e => e.tool!)
    );
    const doneContextTools = new Set(
        events
            .filter(e => e.type === 'tool_result' && e.tool && CONTEXT_TOOLS.has(e.tool))
            .map(e => e.tool!)
    );
    let iconShown = false;
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {events.map((ev, i) => {
                if (ev.type === 'thinking') {
                    const displayModel = ev.model as any || model;
                    const showIcon = !iconShown;
                    if (showIcon) iconShown = true;
                    return (
                        <div key={i} className={styles.aiMessageWrapper} style={{ marginBottom: 4 }}>

                            <div className={styles.aiMessage}>
                                {renderMarkdown(ev.content || '')}
                            </div>
                        </div>
                    );
                }
                if (ev.type === 'tool_call' && ev.call_id && !seenIds.has(ev.call_id)) {
                    seenIds.add(ev.call_id);
                    if (ev.tool === 'suggest_next_actions') return null;
                    const result = resultMap[ev.call_id];
                    const running = !result && isStreaming;
                    const ok = result?.ok;
                    const cancelled = !ok && (result?.cancelled || result?.data?.cancelled);
                    const color = TOOL_COLORS[ev.tool || ''] || '#888';
                    const isFindContact = ev.tool === 'find_company_contact';
                    const quota = result?.data?.quota;

                    return (
                        <div key={i} className={styles.logLine}>
                            {running
                                ? <Loader2 size={12} className={styles.spinner} style={{ color, flexShrink: 0 }} />
                                : ok
                                    ? <CheckCircle2 size={12} style={{ color: '#10b981', flexShrink: 0 }} />
                                    : cancelled
                                        ? <X size={12} style={{ color: 'var(--sw-text-muted)', flexShrink: 0 }} />
                                        : <XCircle size={12} style={{ color: '#ef4444', flexShrink: 0 }} />
                            }
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                <span>{ev.label}</span>
                                {cancelled && (
                                    <span style={{ fontSize: 10, color: 'var(--sw-text-muted)', fontStyle: 'italic' }}>(cancelado pelo usuário)</span>
                                )}
                                {isFindContact && quota && (
                                    <span style={{ display: 'inline-flex', alignItems: 'center', background: 'var(--sw-hover)', padding: '2px 6px', borderRadius: 12, fontSize: 10, border: 'var(--sw-border-width) solid var(--sw-border)', opacity: 0.9 }}>
                                        <img src="/Google_Maps.svg.png" alt="Google Maps" style={{ width: 10, height: 10, marginRight: 4 }} />
                                        {quota.used}/{quota.limit}
                                    </span>
                                )}
                                {result?.summary && <span style={{ opacity: 0.5, marginLeft: 5 }}>· {result.summary}</span>}
                            </span>
                        </div>
                    );
                }
                if (ev.type === 'tool_result') return null;
                if (ev.type === 'context_saved') {
                    return (
                        <div key={i} className={styles.logLine} style={{ opacity: 0.3, fontSize: 'var(--font-xs)', letterSpacing: '0.04em' }}>
                            <span>· contexto salvo</span>
                        </div>
                    );
                }
                if (ev.type === 'rate_wait') return null;
                if (ev.type === 'context_overflow') return null;
                if (ev.type === 'final') {
                    const displayModel = ev.model as any || model;
                    const showIcon = !iconShown;
                    if (showIcon) iconShown = true;
                    return (
                        <div key={i} className={styles.aiMessageWrapper} style={{ marginTop: 6 }}>

                            <div className={styles.aiMessage}>
                                {renderMarkdown(ev.response || '')}
                            </div>
                        </div>
                    );
                }
                if (ev.type === 'error') {
                    return (
                        <div key={i} style={{ fontSize: 'var(--font-base)', color: '#ef4444', marginTop: 4 }}>
                            {ev.content}
                        </div>
                    );
                }
                if (ev.type === 'confirmation_required' && ev.action_id) {
                    const isDecided = (ev.call_id && !!resultMap[ev.call_id]) || (ev.action_id in inlineConfirmed);
                    const isApproved = ev.call_id && resultMap[ev.call_id]
                        ? resultMap[ev.call_id].ok
                        : inlineConfirmed[ev.action_id];

                    return (
                        <ConfirmationCard
                            key={i}
                            event={ev}
                            onConfirm={onInlineConfirm}
                            decided={isDecided}
                            approvedResult={isApproved}
                        />
                    );
                }
                if (ev.type === 'hierarchy_mapping_required' && onHierarchyMappingDone) {
                    return (
                        <HierarchyMappingCard
                            key={i}
                            event={ev}
                            onMappingDone={onHierarchyMappingDone}
                            isStreaming={isStreaming}
                        />
                    );
                }
                if (ev.type === 'suggested_actions') {
                    return null;
                }
                return null;
            })}
            {isStreaming && (
                <div className={styles.logLine} style={{ marginTop: 4, opacity: 0.6 }}>
                    <Loader2 size={11} className={styles.spinner} />
                    <span style={{ fontSize: 'var(--font-sm)' }}>Executando...</span>
                </div>
            )}
        </div>
    );
};
