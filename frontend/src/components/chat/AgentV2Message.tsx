import React, { useState, useEffect, useRef } from 'react';
import {
    Loader2, CheckCircle2, XCircle, Check, X, AlertTriangle,
    Copy, RotateCcw, Clock, AlertCircle, Network,
    Phone, Mail, Calendar, Building2, User, Paperclip,
    FileText, Package, Lightbulb, Target, ClipboardList,
    Box, Layers, MessageSquare, TrendingUp, Wand2,
} from 'lucide-react';
import styles from './ChatPanel.module.css';
import timelineStyles from '../prospecting/HistoryTimeline.module.css';
import { refineMessage } from '../../services/api/ai';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface V2Event {
    type: 'thinking' | 'tool_call' | 'tool_result' | 'confirmation_required' | 'final' | 'error' | 'context_saved' | 'rate_wait' | 'context_overflow' | 'suggested_actions' | 'hierarchy_mapping_required';
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
    actions?: Array<{ label: string; prompt: string; razao?: string; categoria?: string }>;
    response?: string;
    model?: string;
    wait_sec?: number;
    reason?: string;
    estimated_tokens?: number;
    limit?: number;
    // hierarchy_mapping_required
    org_name?: string;
    org_id?: number | null;
    deal_id?: number | null;
    activity_id?: number | null;
    pre_task_id?: number | null;
    error?: string;
}

import { AIModel } from './ModelSelector';

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
    selectedOrgName?: string | null;
    threadId?: string;
    approvedSuggestedActions?: Record<string, 'pending' | 'streaming' | 'awaiting_confirm' | 'awaiting_mapping' | 'done' | 'rejected' | 'error'>;
    onApproveSuggestedAction?: (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => void;
    onHierarchyMappingDone?: (contacts: any[], event?: V2Event) => void;
    model: AIModel;
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
    pipedrive_create_person: '#f36e21',
    email_get_inbox: '#7a8bff',
    email_get_contact_history: '#7a8bff',
    email_send: '#7a8bff',
    email_reply: '#7a8bff',
    web_search: '#60a5fa',
    web_search_external: '#60a5fa',
    find_company_contact: '#60a5fa',
    evaluate_prospects: '#a78bfa',
    generate_dossier: '#a78bfa',
    generate_call_script: '#3b82f6',
    open_hierarchy_drawer: '#818cf8',
    suggest_next_actions: '#10b981',
};

// ─── Categorias de tarefa ─────────────────────────────────────────────────────

type TaskCategory =
    | 'find_contact' | 'call' | 'meeting' | 'followup'
    | 'presentation' | 'quote' | 'message' | 'insight'
    | 'order' | 'homologation' | 'sample' | 'strategic' | 'unknown';

const detectTaskCategory = (label: string): TaskCategory => {
    const l = label.toLowerCase();
    if (/(encontrar|conseguir|buscar|mapear|pesquisar).*(contato|decisor)|decisor.*(real|certo)/.test(l)) return 'find_contact';
    if (/(ligar|ligação|chamada|telefonar|provocar|primeiro contato|call)/.test(l)) return 'call';
    if (/(reunião|meeting|agendar|marcar reunião|visita|reagendar|cold meet|ir pessoalmente)/.test(l)) return 'meeting';
    if (/(follow.?up|cobrar retorno|acompanhar|aguardar retorno)/.test(l)) return 'followup';
    if (/(apresentação|apresentacao|proposta comercial|linkb2b)/.test(l)) return 'presentation';
    if (/(orçamento|cotação|orcamento|cotacao|realizar orçamento|fazer cotação)/.test(l)) return 'quote';
    if (/(insight|insigth|mercado|tendência)/.test(l)) return 'insight';
    if (/(pedido|compra|programação de pedidos|cobrar pedido|colocar pedido)/.test(l)) return 'order';
    if (/(homologação|homologacao|confidencialidade|formulário|cadastro de fornecedor)/.test(l)) return 'homologation';
    if (/(amostra|levar amostra|retirar amostra)/.test(l)) return 'sample';
    if (/(linkedin|seguir no linkedin|conexão no linkedin|qualificar oportunidade|saneamento)/.test(l)) return 'strategic';
    if (/(email|e-mail|mensagem|whatsapp|escrever|enviar)/.test(l)) return 'message';
    return 'unknown';
};

const CATEGORY_CONFIG: Record<TaskCategory, { icon: React.ReactNode; color: string; label: string; isManual?: boolean }> = {
    find_contact:  { icon: <Network size={14} />,        color: '#818cf8', label: 'Mapear Decisor' },
    call:          { icon: <Phone size={14} />,           color: '#3b82f6', label: 'Ligação' },
    meeting:       { icon: <Calendar size={14} />,        color: '#f59e0b', label: 'Reunião' },
    followup:      { icon: <Clock size={14} />,           color: '#10b981', label: 'Follow-up' },
    presentation:  { icon: <Layers size={14} />,          color: '#a855f7', label: 'Apresentação' },
    quote:         { icon: <FileText size={14} />,        color: '#06b6d4', label: 'Orçamento' },
    message:       { icon: <MessageSquare size={14} />,   color: '#7a8bff', label: 'Mensagem' },
    insight:       { icon: <Lightbulb size={14} />,       color: '#eab308', label: 'Insight' },
    order:         { icon: <Package size={14} />,         color: '#f97316', label: 'Pedido' },
    homologation:  { icon: <ClipboardList size={14} />,   color: '#14b8a6', label: 'Homologação' },
    sample:        { icon: <Box size={14} />,             color: '#8b5cf6', label: 'Amostra' },
    strategic:     { icon: <Target size={14} />,          color: '#ec4899', label: 'Estratégico', isManual: true },
    unknown:       { icon: <Clock size={14} />,           color: '#6b7280', label: 'Tarefa' },
};

// ─── Contexto de leitura: ferramentas que fazem parte da Fase 1 ───────────────

const CONTEXT_TOOLS = new Set([
    'pipedrive_get_org', 'pipedrive_get_persons', 'pipedrive_get_deals',
    'pipedrive_get_activities', 'whatsapp_get_messages', 'email_get_contact_history',
]);

const CONTEXT_STEPS: { tool: string; label: string }[] = [
    { tool: 'pipedrive_get_org',           label: 'Empresa' },
    { tool: 'pipedrive_get_persons',       label: 'Contatos' },
    { tool: 'pipedrive_get_deals',         label: 'Negócios' },
    { tool: 'pipedrive_get_activities',    label: 'Atividades' },
    { tool: 'whatsapp_get_messages',       label: 'WhatsApp' },
    { tool: 'email_get_contact_history',   label: 'E-mail' },
];

// ─── HierarchyMappingCard ─────────────────────────────────────────────────────

type MappingStatus = 'waiting' | 'scanning' | 'done';

export interface MappedContact {
    name: string;
    role: string;
    email?: string;
    phone?: string;
    department?: string;
    temperature?: string;
    level?: number;
    decision_maker?: boolean;
}

/**
 * Card de status do mapeamento de hierarquia.
 * NÃO inicia o scan — apenas abre a empresa no Drawer (via CustomEvent) e aguarda
 * o sinal `hierarchy_scan_done` disparado pelo useHierarchy quando o worker termina.
 * Os contatos recebidos já passaram pelo carrossel "Análise Humana" do grafo.
 */
const HierarchyMappingCard: React.FC<{
    event: V2Event;
    onMappingDone: (contacts: MappedContact[]) => void;
    isStreaming?: boolean;
}> = ({ event, onMappingDone, isStreaming }) => {
    const [status, setStatus] = useState<MappingStatus>(() => {
        if (typeof window !== 'undefined') {
            const saved = window.localStorage.getItem('active-discovery-job');
            if (saved) {
                try {
                    const jobData = JSON.parse(saved);
                    if (jobData && (jobData.orgId === event.org_id || Number(jobData.orgId) === Number(event.org_id))) {
                        return 'scanning';
                    }
                } catch { /* ignore */ }
            }
        }
        return isStreaming ? 'waiting' : 'done';
    });
    const [contactCount, setContactCount] = useState(0);
    const doneCalledRef = useRef(false);
    // Marcado true assim que open_org_in_drawer é disparado — impede que o fim
    // do stream do agente encerre o card antes do worker terminar.
    const drawerOpenedRef = useRef(false);

    useEffect(() => {
        let isActiveJobRunning = false;
        if (typeof window !== 'undefined') {
            const saved = window.localStorage.getItem('active-discovery-job');
            if (saved) {
                try {
                    const jobData = JSON.parse(saved);
                    if (jobData && (jobData.orgId === event.org_id || Number(jobData.orgId) === Number(event.org_id))) {
                        isActiveJobRunning = true;
                    }
                } catch { /* ignore */ }
            }
        }

        // Só encerra prematuramente se: não está em streaming, sem job ativo no
        // localStorage E o drawer nunca foi aberto nesta sessão do componente.
        if (!isStreaming && !isActiveJobRunning && !drawerOpenedRef.current) {
            setStatus('done');
            return;
        }

        // Abre a org no background graph apenas uma vez
        if (!drawerOpenedRef.current) {
            drawerOpenedRef.current = true;
            const payload = { org_id: event.org_id, org_name: event.org_name, openDrawer: false };
            setTimeout(() => {
                window.dispatchEvent(new CustomEvent('open_org_in_drawer', { detail: payload }));
            }, 800);
        }

        const handleScanDone = (e: Event) => {
            const contacts: MappedContact[] = (e as CustomEvent).detail?.contacts || [];
            setContactCount(contacts.length);
            setStatus('done');
            if (!doneCalledRef.current) {
                doneCalledRef.current = true;
                // Pequeno delay para o grafo processar os aprovados antes do agente agir
                setTimeout(() => onMappingDone(contacts), 600);
            }
        };

        const handleScanStart = () => setStatus('scanning');

        window.addEventListener('hierarchy_scan_done', handleScanDone);
        window.addEventListener('hierarchy_scan_started', handleScanStart);
        return () => {
            window.removeEventListener('hierarchy_scan_done', handleScanDone);
            window.removeEventListener('hierarchy_scan_started', handleScanStart);
        };
    }, [isStreaming, event.org_id, event.org_name]); // eslint-disable-line react-hooks/exhaustive-deps

    const color = '#818cf8';

    return (
        <div className={styles.logLine} style={{ marginBottom: 8 }}>
            {status === 'waiting' && (
                <>
                    <Network size={12} style={{ color, flexShrink: 0 }} />
                    <span>
                        Mapeamento de Hierarquia · <strong style={{ color: 'var(--sw-text-base)', fontWeight: 500 }}>{event.org_name}</strong>
                        <span style={{ opacity: 0.5, marginLeft: 5 }}>· empresa aberta, insira o CNPJ para mapear</span>
                    </span>
                </>
            )}
            {status === 'scanning' && (
                <>
                    <Loader2 size={12} className={styles.spinner} style={{ color, flexShrink: 0 }} />
                    <span>
                        Mapeamento de Hierarquia · <strong style={{ color: 'var(--sw-text-base)', fontWeight: 500 }}>{event.org_name}</strong>
                        <span style={{ opacity: 0.5, marginLeft: 5 }}>· mapeando...</span>
                    </span>
                </>
            )}
            {status === 'done' && (
                <>
                    <CheckCircle2 size={12} style={{ color: '#10b981', flexShrink: 0 }} />
                    <span>
                        Mapeamento concluído · <strong style={{ color: 'var(--sw-text-base)', fontWeight: 500 }}>{event.org_name}</strong>
                        <span style={{ opacity: 0.5, marginLeft: 5 }}>· {contactCount} contato(s) aprovados · analisando…</span>
                    </span>
                </>
            )}
        </div>
    );
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
            return <hr key={idx} style={{ margin: '10px 0', border: 'none', borderTop: 'var(--sw-border-width) solid var(--sw-border)' }} />;
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
    const [previewText, setPreviewText] = useState(event.preview ?? '');
    const [refineText, setRefineText] = useState('');
    const [isRefining, setIsRefining] = useState(false);

    const handleRefine = async () => {
        if (!refineText.trim() || isRefining || !event.action_id) return;
        setIsRefining(true);
        try {
            const res = await refineMessage({ action_id: event.action_id, feedback: refineText });
            if (res.ok && res.refined_message) {
                setPreviewText(res.refined_message);
                setRefineText('');
            }
        } catch {
            // silent — mantém a mensagem atual
        } finally {
            setIsRefining(false);
        }
    };

    const tool = event.tool || '';
    const isEmail = tool === 'email_send' || tool === 'email_reply';
    const isPipedrive = tool.startsWith('pipedrive_');
    
    // Configurações visuais por canal
    const channelConfig = {
        bg: 'transparent',
        border: 'var(--sw-border)',
        headerBg: 'var(--sw-hover)',
        icon: isEmail ? '/outlook.png' : isPipedrive ? '/pipedrive.png' : '/wppicon.png',
        iconSize: isEmail ? 16 : isPipedrive ? 16 : 14,
        accentColor: isEmail ? '#0078d4' : isPipedrive ? '#f36e21' : '#22c55e',
        labelColor: 'var(--sw-text-muted)',
    };

    if (decided) {
        return (
            <div className={styles.logLine} style={{ marginBottom: 8 }}>
                {approvedResult
                    ? <CheckCircle2 size={12} style={{ color: channelConfig.accentColor, flexShrink: 0 }} />
                    : <XCircle size={12} style={{ color: 'var(--sw-text-muted)', opacity: 0.5, flexShrink: 0 }} />
                }
                <span>{approvedResult ? 'Ação aprovada' : 'Ação cancelada'}</span>
                <span style={{ opacity: 0.4 }}>· {event.label}</span>
            </div>
        );
    }

    const labelStr = event.label || '';
    const hasAttachment = labelStr.includes('+ anexo:') || labelStr.includes('attachment');
    const attachmentName = hasAttachment
        ? (labelStr.match(/\+\s*anexo:\s*([^)]+)\)/i)?.[1]?.trim() || 'Arquivo')
        : null;

    return (
        <div style={{ 
            borderRadius: 10, 
            border: `var(--sw-border-width) solid var(--sw-border)`, 
            background: 'transparent', 
            overflow: 'hidden', 
            marginBottom: 12,
            transition: 'all 0.3s ease'
        }}>
            <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 8, 
                padding: '8px 12px', 
                borderBottom: 'var(--sw-border-width) solid var(--sw-border)', 
                background: 'var(--sw-hover)' 
            }}>
                <img src={channelConfig.icon} alt="Channel" style={{ width: channelConfig.iconSize, height: channelConfig.iconSize, borderRadius: 3 }} />
                <span style={{ fontSize: 'var(--font-xs)', color: 'var(--sw-text-muted)', letterSpacing: '0.06em', fontWeight: 700, textTransform: 'uppercase' }}>
                    {isEmail ? 'CONFIRMAR E-MAIL' : isPipedrive ? 'CONFIRMAR PIPEDRIVE' : 'CONFIRMAR WHATSAPP'}
                </span>
                {hasAttachment && (
                    <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#a855f7', background: 'rgba(168,85,247,0.12)', borderRadius: 4, padding: '2px 7px', fontWeight: 600 }}>
                        <Paperclip size={10} /> {attachmentName}
                    </span>
                )}
            </div>
            <div style={{ padding: '12px' }}>
                <div style={{ fontSize: 'var(--font-sm)', color: 'var(--sw-text-base)', marginBottom: 8, fontWeight: 700, lineHeight: '1.4' }}>
                    {hasAttachment ? labelStr.replace(/\s*\(.*?anexo.*?\)/i, '') : labelStr}
                </div>
                {previewText && (
                    <div style={{
                        fontSize: 'var(--font-md)',
                        color: 'var(--sw-text-base)',
                        opacity: 0.85,
                        padding: '6px 0',
                        borderRadius: 6,
                        fontStyle: 'italic',
                        marginBottom: 10,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        lineHeight: '1.6'
                    }}>
                        {previewText}
                    </div>
                )}
                {event.action_id && (
                    <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                        <input
                            value={refineText}
                            onChange={e => setRefineText(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter' && refineText.trim() && !isRefining) handleRefine(); }}
                            placeholder="O que você quer mudar na mensagem?"
                            disabled={isRefining}
                            style={{
                                flex: 1,
                                background: 'var(--sw-hover)',
                                border: 'var(--sw-border-width) solid var(--sw-border)',
                                borderRadius: 8,
                                padding: '7px 10px',
                                fontSize: 12,
                                color: 'var(--sw-text-base)',
                                outline: 'none',
                                minWidth: 0,
                                opacity: isRefining ? 0.4 : 1,
                            }}
                        />
                        <button
                            onClick={handleRefine}
                            disabled={isRefining || !refineText.trim()}
                            style={{
                                flexShrink: 0,
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                                padding: '7px 12px',
                                background: 'var(--sw-hover)',
                                border: 'var(--sw-border-width) solid var(--sw-border)',
                                borderRadius: 8,
                                color: 'var(--sw-text-subtle)',
                                fontSize: 12,
                                cursor: isRefining || !refineText.trim() ? 'not-allowed' : 'pointer',
                                opacity: isRefining || !refineText.trim() ? 0.4 : 1,
                                whiteSpace: 'nowrap',
                                transition: 'all 0.18s ease',
                            }}
                            onMouseEnter={e => { if (!refineText.trim()) return; e.currentTarget.style.color = 'var(--sw-text-base)'; }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--sw-text-subtle)'; }}
                        >
                            {isRefining ? <Loader2 size={12} className={styles.spinner} /> : <Wand2 size={12} />}
                            <span>{isRefining ? 'Refinando...' : 'Refinar'}</span>
                        </button>
                    </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                    <button 
                        onClick={() => onConfirm(event.action_id!, true)} 
                        style={{ 
                            flex: 1, 
                            padding: '8px 12px', 
                            borderRadius: 7, 
                            border: 'none', 
                            background: channelConfig.accentColor, 
                            color: '#fff', 
                            fontSize: 12, 
                            fontWeight: 600, 
                            cursor: 'pointer', 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'center', 
                            gap: 5,
                            transition: 'opacity 0.2s'
                        }}
                    >
                        <Check size={13} /> Confirmar
                    </button>
                    <button 
                        onClick={() => onConfirm(event.action_id!, false)} 
                        style={{ 
                            flex: 1, 
                            padding: '8px 12px', 
                            borderRadius: 7, 
                            border: 'var(--sw-border-width) solid var(--sw-border)', 
                            background: 'transparent', 
                            color: 'var(--sw-text-subtle)', 
                            fontSize: 12, 
                            cursor: 'pointer', 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'center', 
                            gap: 5,
                            transition: 'all 0.15s ease'
                        }}
                        onMouseEnter={e => { e.currentTarget.style.color = 'var(--sw-text-base)'; e.currentTarget.style.background = 'var(--sw-hover)'; }}
                        onMouseLeave={e => { e.currentTarget.style.color = 'var(--sw-text-subtle)'; e.currentTarget.style.background = 'transparent'; }}
                    >
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: done ? 'var(--sw-text-muted)' : '#f59e0b', margin: '3px 0' }}>
            {done ? <CheckCircle2 size={11} style={{ color: '#10b981', flexShrink: 0 }} /> : <Clock size={11} style={{ flexShrink: 0 }} />}
            <span>{done ? `Cota ${label} liberada — retomando` : `Aguardando cota ${label} (${remaining}s) · ${event.model}`}</span>
        </div>
    );
};

const ContextOverflowBadge: React.FC<{ event: V2Event }> = ({ event }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--sw-text-subtle)', margin: '3px 0' }}>
        <AlertCircle size={11} style={{ flexShrink: 0, color: '#f59e0b' }} />
        <span>{event.model} não suporta {event.estimated_tokens?.toLocaleString()} tokens (limite {event.limit?.toLocaleString()}) · usando modelo maior</span>
    </div>
);

// ─── Renderizador inline de eventos (reutilizado no accordion) ────────────────

export const InlineEventStream: React.FC<{
    events: V2Event[];
    isStreaming: boolean;
    inlineConfirmed: Record<string, boolean>;
    onInlineConfirm: (action_id: string, approved: boolean) => void;
    onHierarchyMappingDone?: (contacts: MappedContact[]) => void;
    model: AIModel;
}> = ({ events, isStreaming, inlineConfirmed, onInlineConfirm, onHierarchyMappingDone, model }) => {
    const resultMap: Record<string, V2Event> = {};
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
                            <div className={styles.aiMessageIconArea}>
                                {showIcon && <AIAsterisk model={displayModel} />}
                            </div>
                            <div className={styles.aiMessage}>
                                {renderMarkdown(ev.content || '')}
                            </div>
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
                    const displayModel = ev.model as any || model;
                    const showIcon = !iconShown;
                    if (showIcon) iconShown = true;
                    return (
                        <div key={i} className={styles.aiMessageWrapper} style={{ marginTop: 6 }}>
                            <div className={styles.aiMessageIconArea}>
                                {showIcon && <AIAsterisk model={displayModel} />}
                            </div>
                            <div className={styles.aiMessage}>
                                {renderMarkdown(ev.response || '')}
                            </div>
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

export type TaskStatus = 'pending' | 'streaming' | 'awaiting_confirm' | 'awaiting_mapping' | 'done' | 'rejected' | 'error';

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

const SuggestedActionTask: React.FC<{
    action: { label: string; prompt: string; razao?: string; categoria?: string; status?: TaskStatus; logs?: V2Event[] };
    streamV2Url: string;
    confirmV2Url: string;
    orgId?: number | null;
    selectedOrgName?: string | null;
    threadId?: string;
    parentMessageId?: string;
    actionIndex?: number;
    approvedSuggestedActions?: Record<string, TaskStatus>;
    onApproveSuggestedAction?: (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => void;
    isLast?: boolean;
    sameCompanyAsNext?: boolean;
    model: AIModel;
}> = ({ action, streamV2Url, confirmV2Url, orgId, selectedOrgName, threadId, parentMessageId, actionIndex, approvedSuggestedActions = {}, onApproveSuggestedAction, isLast = false, sameCompanyAsNext = false, model }) => {
    const taskKey = `${parentMessageId}-${actionIndex}`;
    const externalStatus = approvedSuggestedActions[taskKey];
    const [localStatus, setLocalStatus] = useState<TaskStatus>(action.status || 'pending');
    const status = externalStatus || localStatus;
    const [taskEvents, setTaskEvents] = useState<V2Event[]>(() => {
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
        if (hierarchyEv) {
            setLocalStatus('awaiting_mapping');
        } else if (pendingConfirm) {
            setLocalStatus('awaiting_confirm');
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
            `3. ANÁLISE E EXECUÇÃO ("Encontrar contato"): Analise os perfis mapeados acima e selecione o(s) melhor(es) contato(s) (priorizando decisores de compras, cargos de liderança ou temperature=hot/warm). Em seguida, CONCLUA A TAREFA CADASTRANDO ESTE CONTATO NO PIPEDRIVE chamando a ferramenta 'pipedrive_create_person' atrelado à organização org_id=${orgId}` +
            (hierarchyEv.deal_id ? ` e vinculado ao negócio deal_id=${hierarchyEv.deal_id}` : '') + `.\n` +
            (preTaskClause ? `4. ${preTaskClause}\n` : '') +
            (hierarchyEv.activity_id
                ? `5. A atividade original activity_id=${hierarchyEv.activity_id} NÃO deve ser marcada como concluída — ela só termina após a ligação real. Sugira criar uma nova tarefa "Ligar para [nome do decisor]".\n`
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
        if (pendingConfirm) {
            setLocalStatus('awaiting_confirm');
        } else {
            setLocalStatus('done');
        }
    };

    const handleInlineConfirm = async (action_id: string, approved: boolean) => {
        setInlineConfirmed(prev => ({ ...prev, [action_id]: approved }));
        if (!approved) {
            setLocalStatus('done');
            return;
        }
        setLocalStatus('streaming');
        await streamInto(confirmV2Url, {
            action_id,
            approved: true,
            thread_id: threadId,
        });
        setLocalStatus('done');
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
    const channelCfg = CHANNEL_CFG[action.categoria || ''] ?? { label: 'TAREFA', accentColor: '#6b7280' };
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

    // Estado compacto (concluído / rejeitado / erro)
    if (status === 'done' || status === 'rejected' || status === 'error') {
        return (
            <div className={styles.logLine} style={{ marginBottom: isLast ? 0 : 6 }}>
                {status === 'done'
                    ? <CheckCircle2 size={12} style={{ color: accentColor, flexShrink: 0 }} />
                    : status === 'error'
                        ? <XCircle size={12} style={{ color: '#ef4444', flexShrink: 0 }} />
                        : <XCircle size={12} style={{ color: 'var(--sw-text-muted)', opacity: 0.4, flexShrink: 0 }} />
                }
                <span style={{ opacity: status === 'rejected' ? 0.35 : 1 }}>{action.label}</span>
                <span style={{ opacity: 0.3 }}>· {status === 'done' ? 'executado' : status === 'rejected' ? 'ignorado' : 'erro'}</span>
            </div>
        );
    }

    return (
        <div style={{
            borderRadius: 10,
            border: 'var(--sw-border-width) solid var(--sw-border)',
            background: 'transparent',
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
                background: 'var(--sw-hover)',
            }}>
                {channelCfg.img
                    ? <img src={channelCfg.img} alt={channelCfg.label} style={{ width: 14, height: 14, borderRadius: 2, objectFit: 'contain' }} />
                    : <span style={{ color: accentColor, display: 'flex', alignItems: 'center', flexShrink: 0 }}>{catCfg.icon}</span>
                }
                <span style={{ fontSize: 10, color: 'var(--sw-text-muted)', letterSpacing: '0.07em', fontWeight: 700, textTransform: 'uppercase' }}>
                    {channelCfg.label}
                </span>
                {isManual && (
                    <span style={{ fontSize: 9, color: '#eab308', background: 'rgba(234,179,8,0.12)', borderRadius: 3, padding: '2px 5px', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                        Ação Manual
                    </span>
                )}
                {/* Status badge (execução ativa) */}
                {(status === 'streaming' || status === 'awaiting_confirm' || status === 'awaiting_mapping') && (
                    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, color: status === 'awaiting_confirm' ? '#f59e0b' : status === 'awaiting_mapping' ? '#818cf8' : 'var(--sw-text-muted)' }}>
                        {status === 'streaming'
                            ? <><Loader2 size={10} className={styles.spinner} /><span>Executando...</span></>
                            : status === 'awaiting_confirm'
                                ? <><AlertTriangle size={10} /><span>Aguardando confirmação</span></>
                                : <><Network size={10} /><span>Mapeando...</span></>
                        }
                    </div>
                )}
            </div>

            {/* Body */}
            <div style={{ padding: '10px 12px' }}>
                {/* Título da ação — sem prefixo de canal */}
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--sw-text-base)', marginBottom: action.razao ? 6 : 0, lineHeight: 1.4 }}>
                    {cleanLabel}
                </div>

                {/* Razão — itálico, como preview no ConfirmationCard */}
                {action.razao && (
                    <div style={{ fontSize: 12, color: 'var(--sw-text-subtle)', fontStyle: 'italic', lineHeight: 1.5 }}>
                        {action.razao}
                    </div>
                )}

                {/* Accordion de eventos inline */}
                {canExpand && taskEvents.length > 0 && (
                    <div
                        style={{ marginTop: 10, cursor: 'pointer' }}
                        onClick={() => setIsExpanded(e => !e)}
                    >
                        <div style={{ fontSize: 10, color: 'var(--sw-text-muted)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
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
                                    model={model}
                                />
                            </div>
                        )}
                    </div>
                )}

                {/* Botões — apenas no estado pending */}
                {status === 'pending' && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                        <button
                            onClick={handleApprove}
                            style={{
                                flex: 1,
                                padding: '7px 12px',
                                borderRadius: 7,
                                border: 'none',
                                background: accentColor,
                                color: '#fff',
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: 5,
                                transition: 'opacity 0.15s',
                            }}
                            onMouseEnter={e => { e.currentTarget.style.opacity = '0.85'; }}
                            onMouseLeave={e => { e.currentTarget.style.opacity = '1'; }}
                        >
                            <Check size={12} strokeWidth={2.5} />
                            {isManual ? 'Marcar como feito' : 'Executar'}
                        </button>
                        <button
                            onClick={() => setLocalStatus('rejected')}
                            style={{
                                flex: 1,
                                padding: '7px 12px',
                                borderRadius: 7,
                                border: 'var(--sw-border-width) solid var(--sw-border)',
                                background: 'transparent',
                                color: 'var(--sw-text-subtle)',
                                fontSize: 12,
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

// ─── AIAsterisk ──────────────────────────────────────────────────────────────

const MODEL_LOGO_MAP: Record<string, string> = {
    claude: '/claude.png',
    gemini: '/gemini.png',
    groq: '/groq llama.svg',
    cerebras: '/cerebras.png',
    deepseek: '/deepseek.png',
    sambanova: '/sambanova.png',
};

const MODEL_INVERT_DARK: Record<string, boolean> = {
    groq: true,
};

const AIAsterisk = ({ model }: { model: string }) => {
    // Tenta encontrar a chave correta (ex: 'claude-3-5' -> 'claude')
    const key = Object.keys(MODEL_LOGO_MAP).find(k => model.toLowerCase().includes(k)) || 'claude';
    
    return (
        <img
            src={MODEL_LOGO_MAP[key]}
            alt={`${model} AI`}
            width="16"
            height="16"
            className="shrink-0 object-contain"
            style={{
                filter: MODEL_INVERT_DARK[key] ? 'brightness(0) invert(1)' : 'none'
            }}
        />
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
    selectedOrgName,
    threadId,
    approvedSuggestedActions = {},
    onApproveSuggestedAction,
    onHierarchyMappingDone,
    model,
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
                    <div className={styles.aiMessageIconArea}>
                        {showIcon && <AIAsterisk model={displayModel} />}
                    </div>
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
                    {/* Debug integrado — colapsável, estilo consistente com o card */}
                    {result && (typeof window !== 'undefined' && (window.location.search.includes('debug=true') || !ok)) && (
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
                            }}>
                                {ev.args && Object.keys(ev.args).length > 0 && (
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
                                    <div style={{ opacity: 0.6 }}>{result.summary}</div>
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
                <div key={`ctx-${i}`} className={styles.logLine} style={{ opacity: 0.3, fontSize: 10, margin: '2px 0 8px', letterSpacing: '0.04em' }}>
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
                    <div className={styles.aiMessageIconArea}>
                        {!iconShown && <AIAsterisk model={(finalEvent.model as any) || model} />}
                    </div>
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
                                isLast={idx === suggestedActions.length - 1}
                                sameCompanyAsNext={sameCompanyAsNext}
                                model={model}
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
