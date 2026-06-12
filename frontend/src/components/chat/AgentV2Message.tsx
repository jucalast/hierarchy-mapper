import React, { useState, useEffect, useRef } from 'react';
import {
    Loader2, CheckCircle2, XCircle, Check, X, AlertTriangle,
    Copy, RotateCcw, Clock, AlertCircle, Network,
    Phone, Mail, Calendar, Building2, User, Paperclip,
    FileText, Package, Lightbulb, Target, ClipboardList,
    Box, Layers, MessageSquare, TrendingUp, Wand2, Terminal, ChevronDown
} from 'lucide-react';
import styles from './ChatPanel.module.css';
import timelineStyles from '../prospecting/HistoryTimeline.module.css';
import { refineMessage } from '../../services/api/ai';

// Função auxiliar para converter marcação markdown básica (negrito, itálico, listas) para HTML
function parseMarkdownToHTML(text: string): string {
    if (!text) return '';
    let html = text;
    // Bold (support multiline)
    html = html.replace(/\*\*(.*?)\*\*/gs, '<b>$1</b>');
    // Italic (support multiline, not matching **)
    html = html.replace(/(^|[^\*])\*([^\*]+)\*(?!\*)/gs, '$1<i>$2</i>');
    
    // Lists
    const lines = html.split('\n');
    let inList = false;
    let parsedLines = [];
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];
        // Match * item or - item
        const listMatch = line.match(/^[\*\-]\s+(.*)/);
        if (listMatch) {
            if (!inList) {
                parsedLines.push('<ul style="margin-top: 4px; margin-bottom: 4px; padding-left: 20px;">');
                inList = true;
            }
            parsedLines.push(`<li>${listMatch[1]}</li>`);
        } else {
            if (inList) {
                parsedLines.push('</ul>');
                inList = false;
            }
            parsedLines.push(line);
        }
    }
    if (inList) parsedLines.push('</ul>');
    return parsedLines.join('\n');
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AgentEvent {
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
    data?: any;
    options?: any[];
}

import { AIModel } from './ModelSelector';

export interface AgentMessageProps {
    messageId?: string;
    events: AgentEvent[];
    isStreaming?: boolean;
    onConfirm?: (action_id: string, approved: boolean, file?: File) => void;
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
    onHierarchyMappingDone?: (contacts: any[], event?: AgentEvent) => void;
    model: AIModel;
    onOpenTaskConsole?: (action: any, index: number, parentMessageId?: string) => void;
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
    prepare_live_coaching_session: '#3b82f6',
    open_ligacao_view: '#10b981',
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
    event: AgentEvent;
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
            // Se o chat está esperando por este mapeamento, começamos como 'waiting' (útil para scan manual)
            const pending = window.localStorage.getItem('pending-hierarchy-continuation');
            if (pending) {
                try {
                    const parsed = JSON.parse(pending);
                    if (parsed && (parsed.org_id === event.org_id || Number(parsed.org_id) === Number(event.org_id))) {
                        return 'waiting';
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
        let isWaitingForChat = false;
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
            const pending = window.localStorage.getItem('pending-hierarchy-continuation');
            if (pending) {
                try {
                    const parsed = JSON.parse(pending);
                    if (parsed && (parsed.org_id === event.org_id || Number(parsed.org_id) === Number(event.org_id))) {
                        isWaitingForChat = true;
                    }
                } catch { /* ignore */ }
            }
        }

        // Só encerra prematuramente se: não está em streaming, sem job ativo, sem pendência de chat 
        // E o drawer nunca foi aberto nesta sessão do componente.
        if (!isStreaming && !isActiveJobRunning && !isWaitingForChat && !drawerOpenedRef.current) {
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
            const detail = (e as CustomEvent).detail || {};
            const eventOrgId = detail.orgId;
            // Validar se este evento é realmente para esta empresa
            if (eventOrgId && Number(eventOrgId) !== Number(event.org_id)) {
                return;
            }
            // Se o scan finalizado não foi iniciado pelo chat panel, não faz nada no chat
            if (detail.chatPrompted === false) {
                return;
            }
            const contacts: MappedContact[] = detail.contacts || [];
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
    text.split(/(\*\*.*?\*\*|`.*?`)/g).map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
            return <strong key={i}>{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith('`') && part.endsWith('`')) {
            const inner = part.slice(1, -1);
            return (
                <span key={i} style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '2px 8px',
                    borderRadius: '12px',
                    background: 'var(--sw-hover)',
                    color: 'var(--sw-text-base)',
                    fontSize: '0.85em',
                    fontWeight: 500,
                    margin: '0 2px',
                    fontFamily: 'monospace',
                    verticalAlign: 'baseline',
                    lineHeight: '1.4'
                }}>
                    {inner}
                </span>
            );
        }
        return part as any;
    });

const renderMarkdown = (text: string): React.ReactNode => {
    if (!text) return null;
    return text.split('\n').map((line, idx) => {
        if (line.trim() === '---')
            return <hr key={idx} style={{ margin: '10px 0', border: 'none', borderTop: 'var(--sw-border-width) solid var(--sw-border)' }} />;
        if (line.startsWith('### '))
            return <h3 key={idx} style={{ fontSize: '15px', fontWeight: 700, margin: '4px 0 8px' }}>{renderInline(line.slice(4))}</h3>;
        if (line.startsWith('## '))
            return <h3 key={idx} style={{ fontSize: '16px', fontWeight: 700, margin: '4px 0 8px' }}>{renderInline(line.slice(3))}</h3>;
        
        let trimmed = line.trim();
        if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
            return (
                <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '4px', marginLeft: '12px' }}>
                    <span style={{ opacity: 0.6 }}>•</span>
                    <div>{renderInline(trimmed.slice(2))}</div>
                </div>
            );
        }

        return <div key={idx} style={{ marginBottom: '10px', lineHeight: '1.65' }}>{renderInline(line)}</div>;
    });
};

// ─── ConfirmationCard ─────────────────────────────────────────────────────────

const ConfirmationCard: React.FC<{
    event: AgentEvent;
    onConfirm: (action_id: string, approved: boolean, file?: File) => void;
    decided?: boolean;
    approvedResult?: boolean;
}> = ({ event, onConfirm, decided, approvedResult }) => {
    const [previewText, setPreviewText] = useState(event.preview ?? '');
    const [refineText, setRefineText] = useState('');
    const [isRefining, setIsRefining] = useState(false);
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleRefine = async () => {
        if (!refineText.trim() || isRefining || !event.action_id) return;
        setIsRefining(true);
        try {
            const res = await refineMessage({ action_id: event.action_id, feedback: refineText });
            if (res.ok && res.refined_message) {
                setPreviewText(res.refined_message);
                setRefineText('');
            }
        } catch (e: any) {
            console.error('Refine message failed:', e);
            alert(`Erro ao refinar mensagem: ${e.message || 'Erro desconhecido'}`);
        } finally {
            setIsRefining(false);
        }
    };

    const tool = event.tool || '';
    const isEmail = tool === 'email_send' || tool === 'email_reply';
    const isPipedrive = tool.startsWith('pipedrive_') || tool === 'evaluate_prospects';
    const isCall = tool === 'open_ligacao_view';
    
    // Configurações visuais por canal
    const channelConfig = {
        bg: 'transparent',
        border: 'var(--sw-border)',
        headerBg: 'var(--sw-hover)',
        icon: isEmail ? '/outlook.png' : isPipedrive ? '/pipedrive.png' : isCall ? '/telefone.png' : '/wppicon.png',
        iconSize: isEmail ? 16 : isPipedrive ? 16 : 14,
        accentColor: isEmail ? '#0078d4' : isPipedrive ? '#f36e21' : isCall ? '#10b981' : '#22c55e',
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

    const options = event.options || [];
    const hasOptions = options.length > 0;

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
                background: 'var(--chat-console-bg)' 
            }}>
                {isCall
                    ? <img src="/telefone.png" alt="Ligação" style={{ width: 20, height: 20, objectFit: 'contain' }} />
                    : <img src={channelConfig.icon!} alt="Channel" style={{ width: channelConfig.iconSize, height: channelConfig.iconSize, borderRadius: 3 }} />
                }
                <span style={{ fontSize: 'var(--font-xs)', color: 'var(--sw-text-muted)', letterSpacing: '0.06em', fontWeight: 700, textTransform: 'uppercase' }}>
                    {hasOptions ? 'DECISÃO NECESSÁRIA' : isEmail ? 'CONFIRMAR E-MAIL' : isPipedrive ? 'CONFIRMAR PIPEDRIVE' : isCall ? 'INICIAR LIGAÇÃO' : 'CONFIRMAR WHATSAPP'}
                </span>
            </div>
            <div style={{ padding: '12px' }}>
                <div style={{ fontSize: 'var(--font-sm)', color: 'var(--sw-text-base)', marginBottom: 8, fontWeight: 700, lineHeight: '1.4' }}>
                    {hasOptions ? (event.label || 'O que deseja fazer?') : hasAttachment ? labelStr.replace(/\s*\(.*?anexo.*?\)/i, '') : labelStr}
                </div>
                {previewText && (
                    <div 
                        style={{
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
                        }}
                        dangerouslySetInnerHTML={{ __html: parseMarkdownToHTML(previewText) }}
                    />
                )}

                {hasAttachment && (
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 12,
                        padding: '8px 12px',
                        background: 'transparent',
                        border: 'var(--sw-border-width) solid var(--sw-border)',
                        borderRadius: 6,
                        marginBottom: 10,
                    }}>
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: 32,
                            height: 32,
                            borderRadius: 4,
                            background: 'rgba(239, 68, 68, 0.1)',
                            color: '#ef4444',
                        }}>
                            <FileText size={18} />
                        </div>
                        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--sw-text-base)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {attachmentName?.endsWith('.pdf') ? attachmentName : `${attachmentName}.pdf`}
                            </span>
                            <span style={{ fontSize: 11, color: 'var(--sw-text-muted)', marginTop: 2 }}>
                                7 MB
                            </span>
                        </div>
                        <ChevronDown size={16} style={{ color: 'var(--sw-text-muted)', cursor: 'pointer' }} />
                    </div>
                )}

                {event.action_id && !isCall && !hasOptions && (
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
                            {(isEmail || !isPipedrive) && (
                                <>
                                    <input 
                                        type="file" 
                                        accept="image/*,.pdf" 
                                        ref={fileInputRef} 
                                        style={{ display: 'none' }} 
                                        onChange={e => {
                                            if (e.target.files && e.target.files.length > 0) {
                                                setAttachedFile(e.target.files[0]);
                                            }
                                        }} 
                                    />
                                    <button
                                        onClick={() => fileInputRef.current?.click()}
                                        title="Anexar arquivo (PDF ou Imagem)"
                                        style={{
                                            flexShrink: 0,
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            padding: '7px 10px',
                                            background: attachedFile ? 'var(--sw-hover)' : 'transparent',
                                            border: 'var(--sw-border-width) solid var(--sw-border)',
                                            borderRadius: 8,
                                            color: attachedFile ? channelConfig.accentColor : 'var(--sw-text-subtle)',
                                            cursor: 'pointer',
                                            transition: 'all 0.18s ease',
                                        }}
                                        onMouseEnter={e => { if (!attachedFile) e.currentTarget.style.color = 'var(--sw-text-base)'; }}
                                        onMouseLeave={e => { if (!attachedFile) e.currentTarget.style.color = 'var(--sw-text-subtle)'; }}
                                    >
                                        <Paperclip size={14} />
                                    </button>
                                </>
                            )}
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
                
                {attachedFile && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, padding: '6px 10px', background: 'var(--sw-hover)', borderRadius: 6, border: 'var(--sw-border-width) solid var(--sw-border)' }}>
                        <Paperclip size={12} style={{ color: channelConfig.accentColor }} />
                        <span style={{ fontSize: 11, color: 'var(--sw-text-base)', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {attachedFile.name}
                        </span>
                        <button 
                            onClick={() => { setAttachedFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                            style={{ background: 'transparent', border: 'none', color: 'var(--sw-text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                        >
                            <X size={12} />
                        </button>
                    </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                    {hasOptions ? (
                        options.map((opt: any, idx: number) => (
                            <button
                                key={idx}
                                onClick={() => onConfirm(event.action_id!, idx === 0)}
                                style={{
                                    flex: 1,
                                    padding: '8px 12px',
                                    borderRadius: 7,
                                    border: idx === 0 ? 'none' : 'var(--sw-border-width) solid var(--sw-border)',
                                    background: idx === 0 ? channelConfig.accentColor : 'transparent',
                                    color: idx === 0 ? '#fff' : 'var(--sw-text-base)',
                                    fontSize: 12,
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: 5,
                                    transition: 'all 0.15s ease'
                                }}
                                onMouseEnter={e => { if (idx !== 0) e.currentTarget.style.background = 'var(--sw-hover)'; }}
                                onMouseLeave={e => { if (idx !== 0) e.currentTarget.style.background = 'transparent'; }}
                            >
                                {idx === 0 ? <Check size={13} strokeWidth={2.5} /> : <X size={13} />}
                                {opt.label}
                            </button>
                        ))
                    ) : (
                        <>
                            <button 
                                onClick={() => onConfirm(event.action_id!, true, attachedFile || undefined)} 
                                style={{ 
                                    flex: 1, 
                                    padding: '8px 12px', 
                                    borderRadius: 7, 
                                    border: 'none', 
                                    background: isCall ? `${channelConfig.accentColor}18` : 'transparent', 
                                    color: channelConfig.accentColor, 
                                    fontSize: 12, 
                                    fontWeight: 600, 
                                    cursor: 'pointer', 
                                    display: 'flex', 
                                    alignItems: 'center', 
                                    justifyContent: 'center', 
                                    gap: 5,
                                    transition: 'all 0.15s ease'
                                }}
                                onMouseEnter={e => { e.currentTarget.style.background = `${channelConfig.accentColor}22`; }}
                                onMouseLeave={e => { e.currentTarget.style.background = isCall ? `${channelConfig.accentColor}18` : 'transparent'; }}
                            >
                                <Check size={13} strokeWidth={2.5} />
                                {isCall ? 'Ligar agora' : 'Confirmar'}
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
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};


// ─── RateWaitBadge ────────────────────────────────────────────────────────────

const RateWaitBadge: React.FC<{ event: AgentEvent; isStreaming: boolean }> = ({ event, isStreaming }) => {
    const [remaining, setRemaining] = useState(event.wait_sec || 0);
    React.useEffect(() => {
        if (!isStreaming || remaining <= 0) return;
        const t = setInterval(() => setRemaining(r => Math.max(0, r - 1)), 1000);
        return () => clearInterval(t);
    }, [isStreaming]);
    const label = event.reason === 'TPM' ? 'tokens/min' : 'req/min';
    const done = remaining <= 0;
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--font-sm)', color: done ? 'var(--sw-text-muted)' : '#f59e0b', margin: '3px 0' }}>
            {done ? <CheckCircle2 size={11} style={{ color: '#10b981', flexShrink: 0 }} /> : <Clock size={11} style={{ flexShrink: 0 }} />}
            <span>{done ? `Cota ${label} liberada — retomando` : `Aguardando cota ${label} (${remaining}s) · ${event.model}`}</span>
        </div>
    );
};

const ContextOverflowBadge: React.FC<{ event: AgentEvent }> = ({ event }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--font-sm)', color: 'var(--sw-text-subtle)', margin: '3px 0' }}>
        <AlertCircle size={11} style={{ flexShrink: 0, color: '#f59e0b' }} />
        <span>{event.model} não suporta {event.estimated_tokens?.toLocaleString()} tokens (limite {event.limit?.toLocaleString()}) · usando modelo maior</span>
    </div>
);

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
                    const color = TOOL_COLORS[ev.tool || ''] || '#888';
                    const isFindContact = ev.tool === 'find_company_contact';
                    const quota = result?.data?.quota;

                    return (
                        <div key={i} className={styles.logLine}>
                            {running
                                ? <Loader2 size={12} className={styles.spinner} style={{ color, flexShrink: 0 }} />
                                : ok
                                    ? <CheckCircle2 size={12} style={{ color: '#10b981', flexShrink: 0 }} />
                                    : <XCircle size={12} style={{ color: '#ef4444', flexShrink: 0 }} />
                            }
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                <span>{ev.label}</span>
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

// ─── SuggestedActionTask — card de tarefa com streaming inline ────────────────

import { conversations } from '../../services/api';

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
    onAction?: (prompt: string) => void;
    isLast?: boolean;
    sameCompanyAsNext?: boolean;
    model: AIModel;
    onOpenTaskConsole?: (action: any, index: number, parentMessageId?: string) => void;
}> = ({ action, streamV2Url, confirmV2Url, orgId, selectedOrgName, threadId, parentMessageId, actionIndex, approvedSuggestedActions = {}, onApproveSuggestedAction, onAction, isLast = false, sameCompanyAsNext = false, model, onOpenTaskConsole }) => {
    const taskKey = `${parentMessageId}-${actionIndex}`;
    const externalStatus = approvedSuggestedActions[taskKey];
    const [localStatus, setLocalStatus] = useState<TaskStatus>(action.status || 'pending');
    const status = externalStatus || localStatus;
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
        const hasError = collected.length === 0 || collected.some(e => e.type === 'error' || (e.type === 'tool_result' && e.ok === false));

        if (hierarchyEv) {
            setLocalStatus('awaiting_mapping');
        } else if (pendingConfirm) {
            setLocalStatus('awaiting_confirm');
        } else if (hasError) {
            setLocalStatus('error');
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
        const hasError = newEvents.length === 0 || newEvents.some(e => e.type === 'error' || (e.type === 'tool_result' && e.ok === false));

        if (pendingConfirm) {
            setLocalStatus('awaiting_confirm');
        } else if (hasError) {
            setLocalStatus('error');
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
        const hasError = newEvents.length === 0 || newEvents.some(e => e.type === 'error' || (e.type === 'tool_result' && e.ok === false));
        if (hasError) {
            setLocalStatus('error');
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
        const isClickable = status === 'done' || status === 'error';
        const statusColor = status === 'done' ? accentColor : status === 'error' ? '#ef4444' : 'var(--sw-text-muted)';
        const statusLabel = status === 'done' ? 'executado' : status === 'rejected' ? 'ignorado' : 'erro';
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
                        : status === 'error'
                            ? <XCircle size={10} style={{ flexShrink: 0 }} />
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
                {/* Status badge (execução ativa) */}
                {(status === 'streaming' || status === 'awaiting_confirm' || status === 'awaiting_mapping') && (
                    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, fontSize: 'var(--font-xs)', color: status === 'awaiting_confirm' ? '#f59e0b' : status === 'awaiting_mapping' ? '#818cf8' : 'var(--sw-text-muted)' }}>
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

const ProspectingPlanCard = ({
    isGenerating,
    planMarkdown,
    orgName
}: {
    isGenerating: boolean;
    planMarkdown: string | null;
    orgName: string | null;
}) => {
    return (
        <div style={{
            margin: '12px 0',
            background: 'var(--bg-card)',
            border: 'var(--sw-border-width) solid var(--sw-border)',
            borderRadius: 12,
            overflow: 'hidden',
            boxShadow: 'var(--shadow-sm)'
        }}>
            <div style={{
                padding: '12px 14px',
                borderBottom: 'var(--sw-border-width) solid var(--sw-border)',
                background: 'var(--chat-console-bg)',
                display: 'flex',
                alignItems: 'center',
                gap: 8
            }}>
                {isGenerating ? (
                    <Loader2 size={14} className={styles.spinner} style={{ color: '#a78bfa' }} />
                ) : (
                    <Target size={14} style={{ color: '#a78bfa' }} />
                )}
                <span style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--sw-text-base)' }}>
                    Plano de Prospecção (SPIN)
                </span>
                {orgName && (
                    <span style={{ fontSize: 'var(--font-xs)', color: 'var(--sw-text-muted)', marginLeft: 'auto' }}>
                        {orgName}
                    </span>
                )}
            </div>
            
            <div style={{ padding: '14px', fontSize: 'var(--font-sm)', color: 'var(--sw-text-base)', maxHeight: 400, overflowY: 'auto' }}>
                {isGenerating ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '10px 4px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--sw-text-muted)' }}>
                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'pulse 1.5s infinite' }} />
                            Analisando perfil dos decisores mapeados...
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--sw-text-muted)', opacity: 0.7 }}>
                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'pulse 1.5s infinite 0.5s' }} />
                            Avaliando ICP e fit de produto...
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--sw-text-muted)', opacity: 0.4 }}>
                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'pulse 1.5s infinite 1s' }} />
                            Redigindo sequências de abordagem e hooks...
                        </div>
                    </div>
                ) : planMarkdown ? (
                    <div className={styles.aiMessage}>
                        {renderMarkdown(planMarkdown)}
                    </div>
                ) : (
                    <div style={{ color: '#ef4444' }}>Plano não disponível ou erro na geração.</div>
                )}
            </div>
        </div>
    );
};

// ─── AgentMessage — componente principal ─────────────────────────────────────

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
    onHierarchyMappingDone,
    model,
    onOpenTaskConsole,
}) => {
    const [copied, setCopied] = useState(false);
    const notifiedToolResultsRef = useRef<Set<string>>(new Set());

    useEffect(() => {
        let hasNewCrmUpdate = false;
        for (const ev of events) {
            if (ev.type === 'tool_result' && ev.call_id && !notifiedToolResultsRef.current.has(ev.call_id)) {
                notifiedToolResultsRef.current.add(ev.call_id);
                if (ev.ok && ev.tool) {
                    if (ev.tool.startsWith('pipedrive_update_') || ev.tool.startsWith('pipedrive_create_') || ev.tool.startsWith('pipedrive_delete_')) {
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
                                onAction={onAction}
                                isLast={idx === suggestedActions.length - 1}
                                sameCompanyAsNext={sameCompanyAsNext}
                                model={model}
                                onOpenTaskConsole={onOpenTaskConsole}
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
