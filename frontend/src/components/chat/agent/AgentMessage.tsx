import React, { useState, useEffect, useRef } from 'react';
import { Loader2, CheckCircle2, XCircle, Check, Copy, RotateCcw } from 'lucide-react';
import styles from '../styles/ChatPanel.module.css';
import { AgentEvent, AgentMessageProps } from './types';
import { TOOL_COLORS, CONTEXT_TOOLS } from './constants';
import { renderMarkdown } from './markdown';
import { ConfirmationCard } from './cards/ConfirmationCard';
import { HierarchyMappingCard } from './cards/HierarchyMappingCard';
import { ProspectingPlanCard } from './cards/ProspectingPlanCard';
import { SuggestedActionTask } from './SuggestedActionTask';

const getCompanyFromLabel = (label: string): string => {
    const clean = label.replace('->', '→').replace('·', '→').replace('•', '→');
    const parts = clean.split('→');
    if (parts.length > 1) {
        return parts[parts.length - 1].trim().toLowerCase();
    }
    const lowercase = label.toLowerCase();
    const paraIdx = lowercase.lastIndexOf(' para ');
    if (paraIdx !== -1) {
        return label.substring(paraIdx + 6).trim().toLowerCase();
    }
    const comIdx = lowercase.lastIndexOf(' com ');
    if (comIdx !== -1) {
        return label.substring(comIdx + 5).trim().toLowerCase();
    }
    return label.trim().toLowerCase();
};

export const AgentMessage: React.FC<AgentMessageProps> = ({
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
    selectedOrgName,
    threadId,
    approvedSuggestedActions = {},
    onApproveSuggestedAction,
    onRetrySuggestedAction,
    onHierarchyMappingDone,
    model,
    onOpenTaskConsole,
    onToggleBatch,
    batchQueue = [],
}) => {
    const [copied, setCopied] = useState(false);
    const notifiedToolResultsRef = useRef<Set<string>>(new Set());

    useEffect(() => {
        let hasNewCrmUpdate = false;
        for (const ev of events) {
            if (ev.type === 'tool_result' && ev.call_id && !notifiedToolResultsRef.current.has(ev.call_id)) {
                notifiedToolResultsRef.current.add(ev.call_id);
                if (ev.ok && ev.tool) {
                    if (ev.tool.startsWith('pipedrive_update_') || ev.tool.startsWith('pipedrive_create_') || ev.tool.startsWith('pipedrive_delete_') || ev.tool === 'generate_prospecting_plan') {
                        hasNewCrmUpdate = true;
                    }
                    if (ev.tool === 'open_ligacao_view') {
                        // O backend enviou o pedido de abrir a LigacaoView após confirmação
                        console.log("[AgentV2Message] open_ligacao_view detected", ev);
                        const originalCall = events.find(e => (e.type === 'confirmation_required' || e.type === 'tool_call') && e.call_id === ev.call_id);
                        let detailData = {
                            ...(originalCall?.args || {}),
                            ...(ev.args || {}),
                            ...(ev.data || {})
                        };

                        // 🚀 SEGURANÇA: Garante que flight_plan não venha como string JSON
                        if (typeof detailData.flight_plan === 'string') {
                            try {
                                detailData.flight_plan = JSON.parse(detailData.flight_plan);
                            } catch (e) {
                                console.error("[AgentV2Message] Failed to parse flight_plan string", e);
                            }
                        }

                        console.log("[AgentV2Message] Dispatching open_ligacao_view event with detail", detailData);
                        window.dispatchEvent(new CustomEvent('open_ligacao_view', { detail: detailData }));
                    }
                }
            }
        }
        if (hasNewCrmUpdate) {
            window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
        }
    }, [events]);

    const resultMap: Record<string, AgentEvent> = {};
    for (const ev of events) {
        if (ev.type === 'tool_result' && ev.call_id) resultMap[ev.call_id] = ev;
    }

    const finalEvent = events.find(e => e.type === 'final');
    const errorEvent = events.find(e => e.type === 'error');
    const confirmations = events.filter(e => e.type === 'confirmation_required' && e.action_id);
    const suggestedActions = events
        .filter(e => e.type === 'suggested_actions' && e.actions?.length)
        .flatMap(e => e.actions || []);

    // Progresso da fase de contexto no fluxo principal
    const mainCalledCtx = new Set(events.filter(e => e.type === 'tool_call' && e.tool && CONTEXT_TOOLS.has(e.tool)).map(e => e.tool!));
    const mainDoneCtx   = new Set(events.filter(e => e.type === 'tool_result' && e.tool && CONTEXT_TOOLS.has(e.tool)).map(e => e.tool!));
    const showMainCtxProgress = mainCalledCtx.size > 0 && !finalEvent && !errorEvent;

    const handleCopy = () => {
        navigator.clipboard.writeText(finalEvent?.response || '');
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
    };

    const seenCallIds = new Set<string>();
    const orderedItems: React.ReactNode[] = [];
    let iconShown = false;

    for (let i = 0; i < events.length; i++) {
        const ev = events[i];

        if (ev.type === 'thinking') {
            const displayModel = ev.model as any || model;
            const showIcon = !iconShown;
            if (showIcon) iconShown = true;
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

            // Renderização customizada para generate_prospecting_plan
            if (ev.tool === 'generate_prospecting_plan') {
                let planData = result?.data?.plan || result?.plan;
                if (!planData && result?.result?.plan) planData = result.result.plan;
                if (!planData && typeof result?.result === 'string') {
                    try { const parsed = JSON.parse(result.result); planData = parsed.plan; } catch {}
                }
                if (!planData && typeof result?.content === 'string') {
                    try { const parsed = JSON.parse(result.content); planData = parsed.plan; } catch {}
                }
                if (!planData && typeof result?.content === 'object') {
                    planData = (result.content as any).plan;
                }

                let orgNameData = result?.data?.org_name || result?.org_name;
                if (!orgNameData && result?.result?.org_name) orgNameData = result.result.org_name;
                if (!orgNameData && typeof result?.result === 'string') {
                    try { const parsed = JSON.parse(result.result); orgNameData = parsed.org_name; } catch {}
                }
                if (!orgNameData && typeof result?.content === 'string') {
                    try { const parsed = JSON.parse(result.content); orgNameData = parsed.org_name; } catch {}
                }
                if (!orgNameData && typeof result?.content === 'object') {
                    orgNameData = (result.content as any).org_name;
                }

                orderedItems.push(
                    <ProspectingPlanCard
                        key={`plan-${ev.call_id}`}
                        isGenerating={isRunning}
                        planMarkdown={planData || null}
                        orgName={orgNameData || null}
                    />
                );
                continue;
            }

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
                    </span>
                    {/* Sempre exibe o accordion se houver summary, erro ou debug=true */}
                    {result && (result.summary || !ok || (typeof window !== 'undefined' && window.location.search.includes('debug=true'))) && (
                        <details
                            open={!ok}
                            style={{ marginTop: 4, marginLeft: 18 }}
                        >
                            <summary style={{
                                fontSize: 10,
                                color: ok ? 'var(--sw-text-muted)' : 'rgba(239,68,68,0.7)',
                                cursor: 'pointer',
                                userSelect: 'none',
                                letterSpacing: '0.03em',
                                listStyle: 'none',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                             }}>
                                <span style={{
                                    display: 'inline-block',
                                    width: 12,
                                    textAlign: 'center',
                                    fontSize: 8,
                                }}>▶</span>
                                {ok ? 'detalhes' : 'erro · ver detalhes'}
                            </summary>
                            <div style={{
                                marginTop: 4,
                                borderLeft: `2px solid ${ok ? color + '40' : '#ef444440'}`,
                                paddingLeft: 8,
                                fontFamily: 'monospace',
                                fontSize: 10,
                                lineHeight: 1.5,
                                color: 'var(--sw-text-subtle)',
                                maxHeight: 200,
                                overflowY: 'auto'
                            }}>
                                {ev.args && Object.keys(ev.args).length > 0 && (typeof window !== 'undefined' && window.location.search.includes('debug=true')) && (
                                    <div style={{ marginBottom: 4 }}>
                                        {Object.entries(ev.args).map(([k, v]) => (
                                            <div key={k}>
                                                <span style={{ color: color, opacity: 0.8 }}>{k}</span>
                                                <span style={{ opacity: 0.4 }}>: </span>
                                                <span>{typeof v === 'string' ? v : JSON.stringify(v)}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {result.error && (
                                    <div style={{ color: '#ef4444', opacity: 0.85 }}>
                                        {typeof result.error === 'string' ? result.error : JSON.stringify(result.error)}
                                    </div>
                                )}
                                {!result.error && result.summary && (
                                    <div style={{ opacity: 0.8, whiteSpace: 'pre-wrap' }}>{result.summary}</div>
                                )}
                            </div>
                        </details>
                    )}
                </div>
            );
        } else if (ev.type === 'tool_result') {
            continue;
        } else if (ev.type === 'context_saved') {
            orderedItems.push(
                <div key={`ctx-${i}`} className={styles.logLine} style={{ opacity: 0.3, fontSize: 'var(--font-xs)', margin: '2px 0 8px', letterSpacing: '0.04em' }}>
                    <span>· contexto salvo</span>
                </div>
            );
        } else if (ev.type === 'rate_wait') {
            continue;
        } else if (ev.type === 'context_overflow') {
            continue;
        } else if (ev.type === 'hierarchy_mapping_required' && onHierarchyMappingDone) {
            orderedItems.push(
                <HierarchyMappingCard
                    key={`mapping-${i}`}
                    event={ev}
                    onMappingDone={(contacts) => onHierarchyMappingDone(contacts, ev)}
                    isStreaming={isStreaming}
                />
            );
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
                    {suggestedActions.map((action, idx) => {
                        const nextAction = suggestedActions[idx + 1];
                        const currentCompany = getCompanyFromLabel(action.label);
                        const nextCompany = nextAction ? getCompanyFromLabel(nextAction.label) : null;
                        const sameCompanyAsNext = nextCompany ? currentCompany === nextCompany : false;
                        const isInBatch = batchQueue.some(
                            i => i.messageId === messageId && i.actionIndex === idx
                        );

                        return (
                            <SuggestedActionTask
                                key={idx}
                                action={action}
                                streamV2Url={streamV2Url!}
                                confirmV2Url={confirmV2Url!}
                                orgId={orgId}
                                selectedOrgName={selectedOrgName}
                                threadId={threadId}
                                parentMessageId={messageId}
                                actionIndex={idx}
                                approvedSuggestedActions={approvedSuggestedActions}
                                onApproveSuggestedAction={onApproveSuggestedAction}
                                onRetrySuggestedAction={onRetrySuggestedAction}
                                onAction={onAction}
                                isLast={idx === suggestedActions.length - 1}
                                sameCompanyAsNext={sameCompanyAsNext}
                                model={model}
                                onOpenTaskConsole={onOpenTaskConsole}
                                onToggleBatch={onToggleBatch}
                                isInBatch={isInBatch}
                            />
                        );
                    })}

                </div>
            )}

            {/* Botões da mensagem */}
            {(!isStreaming || errorEvent) && (
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
