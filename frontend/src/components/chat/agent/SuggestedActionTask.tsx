import React, { useState } from 'react';
import {
    Loader2, CheckCircle2, XCircle, Check, X,
    AlertTriangle, RotateCcw, Network, Terminal,
} from 'lucide-react';
import styles from '../styles/ChatPanel.module.css';
import { conversations } from '../../../services/api';
import { AIModel } from '../components/ModelSelector';
import { AgentEvent, TaskStatus, MappedContact } from './types';
import { classifyFailure } from './classifyFailure';
import { detectTaskCategory, CATEGORY_CONFIG } from './constants';
import { InlineEventStream } from './InlineEventStream';

export const SuggestedActionTask: React.FC<{
    action: { label: string; prompt: string; razao?: string; categoria?: string; status?: TaskStatus; logs?: AgentEvent[] };
    streamV2Url: string;
    confirmV2Url: string;
    orgId?: number | null;
    selectedOrgName?: string | null;
    threadId?: string;
    parentMessageId?: string;
    actionIndex?: number;
    approvedSuggestedActions?: Record<string, TaskStatus>;
    onApproveSuggestedAction?: (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => void;
    onRetrySuggestedAction?: (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => void;
    onAction?: (prompt: string) => void;
    isLast?: boolean;
    sameCompanyAsNext?: boolean;
    model: AIModel;
    onOpenTaskConsole?: (action: any, index: number, parentMessageId?: string) => void;
    onToggleBatch?: (action: { label: string; prompt: string; categoria?: string }, index: number, parentMessageId?: string) => void;
    isInBatch?: boolean;
}> = ({ action, streamV2Url, confirmV2Url, orgId, selectedOrgName, threadId, parentMessageId, actionIndex, approvedSuggestedActions = {}, onApproveSuggestedAction, onRetrySuggestedAction, onAction, isLast = false, sameCompanyAsNext = false, model, onOpenTaskConsole, onToggleBatch, isInBatch = false }) => {
    const taskKey = `${parentMessageId}-${actionIndex}`;
    const externalStatus = approvedSuggestedActions[taskKey];
    const [localStatus, setLocalStatus] = useState<TaskStatus>(action.status || 'pending');

    const [taskEvents, setTaskEvents] = useState<AgentEvent[]>(() => {
        if (!action.logs) return [];
        if (typeof action.logs === 'string') {
            try {
                const parsed = JSON.parse(action.logs);
                return Array.isArray(parsed) ? parsed : [];
            } catch {
                return [];
            }
        }
        return Array.isArray(action.logs) ? action.logs : [];
    });

    let status = externalStatus || localStatus;

    // 🔥 Correção Retroativa:
    // Se o banco salvou como 'done' no passado (falso positivo),
    // reavaliamos os logs na montagem usando a regra estrita atual.
    if (status === 'done' && taskEvents.length > 0) {
        const retroactiveFailure = classifyFailure(taskEvents);
        if (retroactiveFailure) {
            status = retroactiveFailure;
        }
    }

    const [isExpanded, setIsExpanded] = useState(() => {
        if (!action.logs) return false;
        if (typeof action.logs === 'string') {
            try {
                const parsed = JSON.parse(action.logs);
                return Array.isArray(parsed) && parsed.length > 0;
            } catch {
                return false;
            }
        }
        return Array.isArray(action.logs) && action.logs.length > 0;
    });
    const [inlineConfirmed, setInlineConfirmed] = useState<Record<string, boolean>>(() => {
        const confirmed: Record<string, boolean> = {};
        let logsArray: any[] = [];
        if (action.logs) {
            if (typeof action.logs === 'string') {
                try {
                    const parsed = JSON.parse(action.logs);
                    if (Array.isArray(parsed)) {
                        logsArray = parsed;
                    }
                } catch { /* ignore */ }
            } else if (Array.isArray(action.logs)) {
                logsArray = action.logs;
            }
        }
        logsArray.forEach(ev => {
            if (ev && typeof ev === 'object' && ev.type === 'tool_result' && ev.tool_use_id) {
                confirmed[ev.tool_use_id] = true;
            }
        });
        return confirmed;
    });
    const [isRowHovered, setIsRowHovered] = useState(false);

    const streamInto = async (url: string, body: object): Promise<AgentEvent[]> => {
        const collected: AgentEvent[] = [];
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
                        const ev: AgentEvent = JSON.parse(line);
                        collected.push(ev);
                        setTaskEvents(prev => [...prev, ev]);
                    } catch { /* ignore */ }
                }
            }
        } catch { /* network error */ }
        return collected;
    };

    const handleApprove = async () => {
        if (onApproveSuggestedAction && actionIndex !== undefined) {
            onApproveSuggestedAction(action, actionIndex, parentMessageId);
            return;
        }

        setLocalStatus('streaming');
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

        const hierarchyEv = collected.find(e => e.type === 'hierarchy_mapping_required');
        const pendingConfirm = collected.find(e => e.type === 'confirmation_required' && e.action_id);
        const failure = classifyFailure(collected);

        if (hierarchyEv) {
            setLocalStatus('awaiting_mapping');
        } else if (pendingConfirm) {
            setLocalStatus('awaiting_confirm');
        } else if (failure) {
            setLocalStatus(failure);
        } else {
            setLocalStatus('done');
        }
    };

    const handleMappingComplete = async (contacts: MappedContact[]) => {
        const hierarchyEv = taskEvents.find(e => e.type === 'hierarchy_mapping_required');
        if (!hierarchyEv) return;

        setLocalStatus('streaming');

        // Formata contatos reais encontrados pelo mapeamento para a IA usar sem alucinar
        const contactsSummary = contacts.length > 0
            ? `Contatos reais encontrados pelo mapeamento (${contacts.length} total): ` +
              contacts.slice(0, 8).map(c =>
                  `${c.name} (${c.role}${c.email ? ', ' + c.email : ''}${c.temperature ? ', temp=' + c.temperature : ''})`
              ).join(' | ')
            : 'Nenhum contato foi encontrado no mapeamento.';

        const preTaskClause = hierarchyEv.pre_task_id
            ? `Marque a tarefa de rastreamento pre_task_id=${hierarchyEv.pre_task_id} como concluída com pipedrive_update_task done=true. `
            : '';

        const continuation = (
            `EXECUTE ESTAS ETAPAS EM ORDEM:\n` +
            `1. Mapeamento de hierarquia concluído para "${hierarchyEv.org_name}". ${contactsSummary}\n` +
            `2. REGRA DE INTELIGÊNCIA: Os contatos listados acima foram recém-mapeados do LinkedIn (cold leads) e são 100% novos. Como você já investigou a empresa e não havia histórico anterior de e-mail ou WhatsApp, VOCÊ ESTÁ PROIBIDO de chamar 'whatsapp_get_messages', 'email_get_contact_history' ou 'whatsapp_list_chats' para qualquer uma dessas novas pessoas, pois não existe histórico com elas.\n` +
            `3. PLANO DE PROSPECÇÃO: Use a ferramenta 'generate_prospecting_plan' passando org_id=${orgId} para cruzar os contatos mapeados com nosso portfólio de produtos e gerar/salvar automaticamente o plano SPIN Selling no contexto da empresa.\n` +
            `4. ANÁLISE E EXECUÇÃO ("Encontrar contato"): Analise os perfis mapeados acima e selecione o(s) melhor(es) contato(s) (priorizando decisores de compras, cargos de liderança ou temperature=hot/warm). Em seguida, CONCLUA A TAREFA CADASTRANDO ESTE CONTATO NO PIPEDRIVE chamando a ferramenta 'pipedrive_create_person' atrelado à organização org_id=${orgId}` +
            (hierarchyEv.deal_id ? ` e vinculado ao negócio deal_id=${hierarchyEv.deal_id}` : '') + `.\n` +
            (preTaskClause ? `5. ${preTaskClause}\n` : '') +
            (hierarchyEv.activity_id
                ? `6. A atividade original activity_id=${hierarchyEv.activity_id} NÃO deve ser marcada como concluída — ela só termina após a ligação real. Sugira criar uma nova tarefa "Ligar para [nome do decisor]".\n`
                : '') +
            `PROIBIDO: NÃO invente dados. Use APENAS os contatos listados acima.`
        );

        const newEvents = await streamInto(streamV2Url, {
            message: continuation,
            org_id: orgId,
            thread_id: threadId,
            history: [],
            direct_action: true,
            parent_message_id: parentMessageId,
            action_index: actionIndex,
        });

        const pendingConfirm = newEvents.find(e => e.type === 'confirmation_required' && e.action_id);
        const failure = classifyFailure(newEvents);

        if (pendingConfirm) {
            setLocalStatus('awaiting_confirm');
        } else if (failure) {
            setLocalStatus(failure);
        } else {
            setLocalStatus('done');
        }
    };

    const handleInlineConfirm = async (action_id: string, approved: boolean) => {
        setInlineConfirmed(prev => ({ ...prev, [action_id]: approved }));
        setLocalStatus('streaming');
        const newEvents = await streamInto(confirmV2Url, {
            action_id,
            approved,
            thread_id: threadId,
        });
        const failure = classifyFailure(newEvents);
        if (failure) {
            setLocalStatus(failure);
        } else {
            setLocalStatus('done');
        }
    };

    const canExpand = status !== 'pending' && status !== 'rejected';
    const isActive = status === 'streaming';

    // Canal a partir da categoria (mais confiável que detectar pelo texto do label)
    const CHANNEL_CFG: Record<string, { img?: string; label: string; accentColor: string }> = {
        whatsapp:   { img: '/wppicon.png',   label: 'WHATSAPP',   accentColor: '#22c55e' },
        email:      { img: '/outlook.png',   label: 'E-MAIL',     accentColor: '#0078d4' },
        tarefa_crm: { img: '/pipedrive.png', label: 'PIPEDRIVE',  accentColor: '#f36e21' },
        reuniao:    { img: '/pipedrive.png', label: 'PIPEDRIVE',  accentColor: '#f59e0b' },
        estrategia: {                        label: 'ESTRATÉGIA', accentColor: '#ec4899' },
    };

    let categoryKey = action.categoria || '';
    if (!CHANNEL_CFG[categoryKey]) {
        const p = (action.prompt || '').toLowerCase();
        const l = (action.label || '').toLowerCase();
        if (p.includes('pipedrive_') || l.includes('pipedrive')) {
            categoryKey = 'tarefa_crm';
        } else if (p.includes('whatsapp') || l.includes('whatsapp')) {
            categoryKey = 'whatsapp';
        } else if (p.includes('email') || l.includes('email') || p.includes('e-mail') || l.includes('e-mail')) {
            categoryKey = 'email';
        } else if (p.includes('reuniao') || l.includes('reunião') || p.includes('reunião') || l.includes('reuniao')) {
            categoryKey = 'reuniao';
        }
    }
    const channelCfg = CHANNEL_CFG[categoryKey] ?? { label: 'TAREFA', accentColor: '#6b7280' };
    const accentColor = channelCfg.accentColor;

    // Limpa prefixos de canal do label (legado de prompts anteriores)
    const LABEL_PREFIXES = ['whatsapp:', 'e-mail:', 'email:', 'tarefa crm:', 'tarefa:', 'estratégia:', 'estrategia:', 'reunião:', 'reuniao:', 'pipedrive:'];
    const cleanLabel = (() => {
        const lower = action.label.toLowerCase();
        for (const prefix of LABEL_PREFIXES) {
            if (lower.startsWith(prefix)) return action.label.slice(prefix.length).trim();
        }
        return action.label;
    })();

    const category = detectTaskCategory(action.label);
    const catCfg = CATEGORY_CONFIG[category];
    const isManual = action.label.toLowerCase().includes('linkedin') || catCfg.isManual;

    // Estado compacto (concluído / rejeitado apenas — erro fica expandido com botão de retry)
    if (status === 'done' || status === 'rejected') {
        const isClickable = status === 'done';
        const statusColor = status === 'done' ? accentColor : 'var(--sw-text-muted)';
        const statusLabel = status === 'done' ? 'executado' : 'ignorado';
        return (
            <div
                onClick={isClickable ? () => onOpenTaskConsole && onOpenTaskConsole(action, actionIndex!, parentMessageId) : undefined}
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '5px 8px',
                    marginBottom: isLast ? 0 : 10,
                    borderRadius: 8,
                    opacity: status === 'rejected' ? 0.45 : 1,
                    cursor: isClickable ? 'pointer' : 'default',
                    transition: 'background 0.15s ease',
                }}
                onMouseEnter={isClickable ? (e) => {
                    (e.currentTarget as HTMLDivElement).style.background = 'var(--sw-hover)';
                } : undefined}
                onMouseLeave={isClickable ? (e) => {
                    (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                } : undefined}
            >
                {/* Ícone de canal */}
                {channelCfg.img
                    ? <img src={channelCfg.img} alt={channelCfg.label} style={{ width: 13, height: 13, borderRadius: 2, objectFit: 'contain', flexShrink: 0, opacity: status === 'rejected' ? 0.5 : 1 }} />
                    : <span style={{ color: accentColor, display: 'flex', alignItems: 'center', flexShrink: 0 }}>{catCfg.icon}</span>
                }

                {/* Label da ação */}
                <span style={{
                    flex: 1,
                    fontSize: 'var(--font-sm)',
                    fontWeight: 500,
                    color: 'var(--sw-text-base)',
                    lineHeight: 1.4,
                    minWidth: 0,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                }}>
                    {cleanLabel}
                </span>

                {/* Badge de status */}
                <span style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 'calc(var(--font-xs) - 1px)',
                    fontWeight: 600,
                    color: statusColor,
                    background: `${statusColor}14`,
                    borderRadius: 5,
                    padding: '2px 7px',
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    flexShrink: 0,
                }}>
                    {status === 'done'
                        ? <CheckCircle2 size={10} style={{ flexShrink: 0 }} />
                        : <XCircle size={10} style={{ flexShrink: 0 }} />
                    }
                    {statusLabel}
                </span>

                {/* Hint de clique */}
                {isClickable && (
                    <Terminal size={12} style={{ color: 'var(--sw-text-muted)', opacity: 0.4, flexShrink: 0 }} />
                )}
            </div>
        );
    }

    return (
        <div style={{
            borderRadius: 10,
            border: 'var(--sw-border-width) solid var(--sw-border)',
            background: 'var(--chat-console-bg)',
            overflow: 'hidden',
            marginBottom: isLast ? 0 : 10,
            transition: 'border-color 0.2s ease',
        }}>
            {/* Header — mesmo padrão do ConfirmationCard */}
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                borderBottom: 'var(--sw-border-width) solid var(--sw-border)',
                background: 'var(--chat-console-bg)',
            }}>
                {channelCfg.img
                    ? <img src={channelCfg.img} alt={channelCfg.label} style={{ width: 14, height: 14, borderRadius: 2, objectFit: 'contain' }} />
                    : <span style={{ color: accentColor, display: 'flex', alignItems: 'center', flexShrink: 0 }}>{catCfg.icon}</span>
                }
                <span style={{ fontSize: 'var(--font-xs)', color: 'var(--sw-text-muted)', letterSpacing: '0.07em', fontWeight: 700, textTransform: 'uppercase' }}>
                    {channelCfg.label}
                </span>
                {isManual && (
                    <span style={{ fontSize: 'calc(var(--font-xs) - 2px)', color: '#eab308', background: 'rgba(234,179,8,0.12)', borderRadius: 3, padding: '2px 5px', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                        Ação Manual
                    </span>
                )}
                {/* Checkbox de seleção em lote — visível apenas em estado pendente */}
                {status === 'pending' && onToggleBatch && actionIndex !== undefined && (
                    <div
                        onClick={(e) => { e.stopPropagation(); onToggleBatch(action, actionIndex, parentMessageId); }}
                        title={isInBatch ? 'Remover da fila' : 'Adicionar à fila de execução em lote'}
                        style={{
                            marginLeft: 'auto',
                            width: 16,
                            height: 16,
                            borderRadius: 4,
                            border: `2px solid ${isInBatch ? accentColor : 'var(--sw-border-strong, var(--sw-border))'}`,
                            background: isInBatch ? accentColor : 'transparent',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            cursor: 'pointer',
                            flexShrink: 0,
                            transition: 'all 0.15s ease',
                        }}
                    >
                        {isInBatch && <Check size={10} strokeWidth={3} color="white" />}
                    </div>
                )}
                {/* Status badge (execução ativa ou erro) */}
                {(status === 'streaming' || status === 'awaiting_confirm' || status === 'awaiting_mapping' || status === 'cancelled' || status === 'error') && (
                    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, fontSize: 'var(--font-xs)', color: status === 'error' ? '#ef4444' : status === 'awaiting_confirm' ? '#f59e0b' : status === 'awaiting_mapping' ? '#818cf8' : status === 'cancelled' ? 'var(--sw-text-muted)' : 'var(--sw-text-muted)' }}>
                        {status === 'streaming'
                            ? <><Loader2 size={10} className={styles.spinner} /><span>Executando...</span></>
                            : status === 'awaiting_confirm'
                                ? <><AlertTriangle size={10} /><span>Aguardando confirmação</span></>
                                : status === 'awaiting_mapping'
                                    ? <><Network size={10} /><span>Mapeando...</span></>
                                    : status === 'error'
                                        ? <><XCircle size={10} /><span style={{ fontWeight: 700 }}>Falhou</span></>
                                        : <><XCircle size={10} /><span>Cancelado — pode tentar novamente</span></>
                        }
                    </div>
                )}
            </div>

            {/* Body */}
            <div className={styles.actionCardBody}>
                {/* Título da ação — sem prefixo de canal */}
                <div style={{ fontSize: 'var(--font-base)', fontWeight: 600, color: 'var(--sw-text-base)', marginBottom: action.razao ? 6 : 0, lineHeight: 1.4 }}>
                    {cleanLabel}
                </div>

                {/* Razão — itálico, como preview no ConfirmationCard */}
                {action.razao && (
                    <div style={{ fontSize: 'var(--font-sm)', color: 'var(--sw-text-subtle)', fontStyle: 'italic', lineHeight: 1.5 }}>
                        {action.razao}
                    </div>
                )}

                {/* Accordion de eventos inline */}
                {canExpand && taskEvents.length > 0 && (
                    <div
                        style={{ marginTop: 10, cursor: 'pointer' }}
                        onClick={() => setIsExpanded(e => !e)}
                    >
                        <div style={{ fontSize: 'var(--font-xs)', color: 'var(--sw-text-muted)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ display: 'inline-block', transform: isExpanded ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 0.15s' }}>▶</span>
                            {isExpanded ? 'ocultar detalhes' : 'ver detalhes'}
                        </div>
                        {isExpanded && (
                            <div
                                style={{ background: 'var(--sw-hover)', border: 'var(--sw-border-width) solid var(--sw-border)', borderRadius: 8, padding: '10px 12px' }}
                                onClick={e => e.stopPropagation()}
                            >
                                <InlineEventStream
                                    events={taskEvents}
                                    isStreaming={isActive}
                                    inlineConfirmed={inlineConfirmed}
                                    onInlineConfirm={handleInlineConfirm}
                                    onHierarchyMappingDone={handleMappingComplete}
                                    onAction={onAction}
                                    model={model}
                                />
                            </div>
                        )}
                    </div>
                )}

                {/* Botões — pending/cancelled: Executar + Ignorar; error: Tentar novamente + Ignorar */}
                {(status === 'pending' || status === 'cancelled' || status === 'error') && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                        {status === 'error' ? (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (onRetrySuggestedAction && actionIndex !== undefined) {
                                        onRetrySuggestedAction(action, actionIndex, parentMessageId);
                                    }
                                }}
                                style={{
                                    flex: 1,
                                    padding: '7px 12px',
                                    borderRadius: 7,
                                    border: 'none',
                                    background: 'transparent',
                                    color: '#ef4444',
                                    fontSize: 'var(--font-sm)',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: 5,
                                    transition: 'all 0.15s ease',
                                }}
                                onMouseEnter={e => { e.currentTarget.style.background = '#ef444414'; }}
                                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                            >
                                <RotateCcw size={12} strokeWidth={2.5} />
                                Tentar novamente
                            </button>
                        ) : (
                            <button
                                onClick={handleApprove}
                                style={{
                                    flex: 1,
                                    padding: '7px 12px',
                                    borderRadius: 7,
                                    border: 'none',
                                    background: 'transparent',
                                    color: accentColor,
                                    fontSize: 'var(--font-sm)',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: 5,
                                    transition: 'all 0.15s ease',
                                }}
                                onMouseEnter={e => { e.currentTarget.style.background = `${accentColor}12`; }}
                                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                            >
                                <Check size={12} strokeWidth={2.5} />
                                {isManual ? 'Marcar como feito' : 'Executar'}
                            </button>
                        )}
                        <button
                            onClick={async () => {
                                setLocalStatus('rejected');
                                if (parentMessageId && actionIndex !== undefined) {
                                    try {
                                        await conversations.updateSuggestedActionStatus(parentMessageId, actionIndex, 'rejected');
                                    } catch (e) {
                                        console.error('Failed to persist rejected status', e);
                                    }
                                }
                            }}
                            style={{
                                flex: 1,
                                padding: '7px 12px',
                                borderRadius: 7,
                                border: 'var(--sw-border-width) solid var(--sw-border)',
                                background: 'transparent',
                                color: 'var(--sw-text-subtle)',
                                fontSize: 'var(--font-sm)',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: 5,
                                transition: 'all 0.15s ease',
                            }}
                            onMouseEnter={e => { e.currentTarget.style.color = 'var(--sw-text-base)'; e.currentTarget.style.background = 'var(--sw-hover)'; }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--sw-text-subtle)'; e.currentTarget.style.background = 'transparent'; }}
                        >
                            <X size={12} strokeWidth={2.5} />
                            Ignorar
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};
